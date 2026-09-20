"""Convert the pinned R10 formal APK to LAN without recompiling game code."""
import argparse
import importlib.util
import ipaddress
import json
import struct
import uuid
import zipfile
import zlib
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


s = module('r10_lan_swf', HERE.parent / 'startup-cache/build_swf.py')
b = module('r10_lan_apk', HERE.parent / 'startup-cache/build.py')
native = module('r10_lan_native', HERE.parent / 'startup-cache/verify_native.py')
checker = module('r10_lan_accepted', HERE.parent / 'verify_android_baseline.py')

APK = ROOT / 'outputs/r10-public-release-20260915/StarPoint-CN-1.8.1-r10-public-20260915.apk'
APK_SHA = 'afca9f44d1bea9edea7b573fa96dddd32bc304afd0bbaa4d3df6fb21d41c2a90'
SWF_SHA = 'a8130eabef7d0c13398688c8c22a8d8091dcd01a8b7a9572eaae2b68528265b8'
OLD_UUID = 'fc14b494-ea2a-4056-a24d-1698f502c6d2'
BUILD_ID = 'android-181-r10-20260915'
PUBLIC_ORIGIN = 'http://175.178.160.158:8001'
SWF_MEMBER = 'assets/worldflipper_android_release.swf'
SIGNATURES = {'META-INF/MANIFEST.MF', 'META-INF/WF.SF', 'META-INF/WF.RSA'}


def constants(abcs):
    matches = [(t[3], ci) for t in abcs for ci, ins in enumerate(t[3].instances)
               if t[3].mn_name(ins[0]) == 'cn.admission::BuildConfig']
    assert len(matches) == 1
    abc, ci = matches[0]
    result = {}
    for trait in abc.classes[ci][1]:
        assert trait.kind == 6 and trait.data[0] == 'slot' and trait.data[4] == 1
        result[abc.mn_name(trait.name).split('::')[-1]] = abc.s(trait.data[3])
    assert set(result) == {'ID', 'KEY', 'ORIGIN'}
    return result


def patch_strings(data, replacements):
    """Keep the compiler's exact encoding outside selected string-pool entries."""
    reader = s.m.abcfmt.R(data)
    reader.p = 4
    for read_value in (reader.s32, reader.u32, reader.d64):
        count = reader.u30()
        for _ in range(max(0, count - 1)):
            read_value()
    count = reader.u30()
    pieces = [data[:reader.p]]
    seen = set()
    for index in range(1, count):
        start = reader.p
        value = reader.raw(reader.u30())
        if index in replacements:
            before, after = replacements[index]
            assert value == before
            writer = s.m.abcfmt.W()
            writer.u30(len(after))
            writer.raw(after)
            pieces.append(writer.out())
            seen.add(index)
        else:
            pieces.append(data[start:reader.p])
    assert seen == set(replacements)
    pieces.append(data[reader.p:])
    return b''.join(pieces)


def convert_swf(work, origin, keys_path):
    version, header, tags = s.parts(work / 'input.swf')
    abcs = [t for t in tags if t[0] == 82]
    assert len(abcs) == 296 and sum(len(t[3].bodies) for t in abcs) == 96631
    original = constants(abcs)
    assert original['ID'] == BUILD_ID and original['ORIGIN'] == PUBLIC_ORIGIN
    # Read-only comparison with the existing private pair. Never generate, copy,
    # log or write the key or a generated BuildConfig source during conversion.
    keys = json.loads(keys_path.read_text('utf-8-sig'))
    assert keys.get(BUILD_ID) == original['KEY'], 'Formal Android private pair mismatch'
    del keys
    patches = {}
    expected = {
        0: ('cn/admission/ClientAdmission', {
            PUBLIC_ORIGIN + '/api/index.php', PUBLIC_ORIGIN + '/player-auth/logout',
            PUBLIC_ORIGIN + '/player-auth/', PUBLIC_ORIGIN + '/client-admission/prove',
            PUBLIC_ORIGIN + '/client-admission/challenge', PUBLIC_ORIGIN}),
        3: ('cn/admission/BuildConfig', {PUBLIC_ORIGIN}),
        295: ('boot_ffc6', {PUBLIC_ORIGIN.split('://', 1)[1]}),
    }
    changes = []
    for ti, (label, expected_values) in expected.items():
        tag = abcs[ti]
        assert tag[2][4:-1].decode() == label
        abc = tag[3]
        indexes = [i for i, raw in enumerate(abc.strings) if b'175.178.160.158' in raw]
        assert {abc.s(i) for i in indexes} == expected_values
        assert len(indexes) == {0: 6, 3: 1, 295: 2}[ti]
        patches[ti] = {}
        for index in indexes:
            old = abc.strings[index]
            new = old.replace(PUBLIC_ORIGIN.encode(), origin.encode()) if ti != 295 else origin.split('://', 1)[1].encode()
            patches[ti][index] = (old, new)
            abc.strings[index] = new
            changes.append({'abc': ti, 'name': label, 'string_index': index,
                            'before': old.decode(), 'after': new.decode()})
        data = tag[2] + patch_strings(tag[4], patches[ti])
        tag[1] = struct.pack('<HI', (82 << 6) | 63, len(data)) + data
    # The constructor still executes the original instruction stream and now
    # loads the LAN authority; all helper inlined URLs were changed with it.
    main = abcs[-1][3]
    code = s.m.asm.decode(main.bodies[92013][5])
    assert code[11].op == 0x2c and main.s(code[11].args[0]) == origin.split('://', 1)[1]
    assert not any(b'175.178.160.158' in value for tag in abcs for value in tag[3].strings)
    current = constants(abcs)
    assert current['ID'] == original['ID'] and current['KEY'] == original['KEY']
    assert current['ORIGIN'] == origin
    raw = header + b''.join(t[1] for t in tags)
    swf = work / 'client-admission-lan.swf'
    swf.write_bytes(b'CWS' + bytes([version]) + struct.pack('<I', len(raw) + 8) + zlib.compress(raw))
    # Read back the real output and reverse only the nine allowed constants.
    # Every ABC must then equal the original bytes, including traits, method
    # bodies, branches, exception tables, default arguments and constant pools.
    final_version, final_header, final_tags = s.parts(swf)
    assert version == final_version and header == final_header and len(tags) == len(final_tags)
    final_abcs = [t for t in final_tags if t[0] == 82]
    assert constants(final_abcs) == current
    methods = 0
    for ti, (old, final) in enumerate(zip(abcs, final_abcs)):
        assert old[2] == final[2]
        methods += len(final[3].bodies)
        if ti in patches:
            for index, (before, after) in patches[ti].items():
                assert final[3].strings[index] == after
                final[3].strings[index] = before
            reverse = {index: (after, before) for index, (before, after) in patches[ti].items()}
            assert patch_strings(final[4], reverse) == old[4], ('ABC reversal', ti)
        else:
            assert final[4] == old[4], ('Unchanged ABC', ti)
    for old, final in zip(tags, final_tags):
        assert old[0] == final[0]
        if old[0] != 82:
            assert old[1] == final[1]
    assert methods == 96631
    return swf, changes


def main(args):
    work, out, keys = args.work.resolve(), args.out.resolve(), args.keys.resolve()
    for path in (work, out, keys):
        assert '.cdn' not in [p.lower() for p in path.parts], 'Read-only CDN boundary'
    origin = args.origin
    parsed = urlsplit(origin)
    assert parsed.scheme == 'http' and not parsed.path and not parsed.query and not parsed.fragment
    assert parsed.username is None and parsed.password is None
    address = ipaddress.ip_address(parsed.hostname)
    assert address.version == 4 and address.is_private and not address.is_unspecified
    assert origin == 'http://' + str(address) + (':' + str(parsed.port) if parsed.port else '')
    assert keys.is_file()
    assert Path(args.name).name == args.name and args.name.endswith('.apk')
    assert not work.exists() and not (out / args.name).exists(), 'Fresh work/output required'
    accepted = checker.verify('public')
    assert accepted['apk_sha256'] == '35e0e7c777798594d68c9bcd74c507c6f0b7d065453e0425c301258c6bc38ac6'
    assert b.sha(APK.read_bytes()) == APK_SHA, 'The actual R10 formal input changed'
    release = json.loads((HERE / 'release.json').read_text('utf-8'))['android']
    assert release['sha256'] == APK_SHA and release['build_id'] == BUILD_ID
    work.mkdir(parents=True)
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(APK) as z:
        data = z.read(SWF_MEMBER)
        assert b.sha(data) == SWF_SHA
        (work / 'input.swf').write_bytes(data)
        (work / 'original.dex').write_bytes(z.read('classes.dex'))
    swf, changes = convert_swf(work, origin, keys)
    print('Verified all 96,631 methods; formal build ID and private pair unchanged.', flush=True)
    uid = str(uuid.uuid4())
    assert uid != OLD_UUID
    b.run([b.JAVA, '-jar', b.ALIB / 'baksmali.jar', 'd', '-o', work / 'smali', work / 'original.dex'], work, 'decode-dex')
    originals = {p.relative_to(work / 'smali'): p.read_text('utf-8') for p in (work / 'smali').rglob('*.smali')}
    assert len(originals) == 6
    changed = {}
    for name, text in originals.items():
        if OLD_UUID in text:
            assert name.as_posix() in {'cn/startpoint/StartupCache.smali', 'cn/startpoint/BuildIdentity.smali'}
            changed[name.as_posix()] = text.count(OLD_UUID)
            (work / 'smali' / name).write_text(text.replace(OLD_UUID, uid), 'utf-8')
    assert len(changed) == 2 and sum(changed.values()) == 2
    b.run([b.JAVA, '-jar', b.ALIB / 'smali.jar', 'a', '-a', '21', '-o', work / 'classes.dex', work / 'smali'], work, 'encode-dex')
    b.run([b.JAVA, '-jar', b.ALIB / 'baksmali.jar', 'd', '-o', work / 'native-readback', work / 'classes.dex'], work, 'readback-dex')
    readback_paths = {p.relative_to(work / 'native-readback') for p in (work / 'native-readback').rglob('*.smali')}
    assert readback_paths == set(originals)
    for name, original in originals.items():
        value = (work / 'native-readback' / name).read_text('utf-8')
        assert native.canonical(value.replace(uid, OLD_UUID)) == native.canonical(original), str(name)
    payloads = {SWF_MEMBER: swf.read_bytes(), 'classes.dex': (work / 'classes.dex').read_bytes()}
    with zipfile.ZipFile(APK) as source, zipfile.ZipFile(work / 'unsigned.apk', 'w') as dest:
        manifest = source.read('AndroidManifest.xml')
        assert manifest.count(OLD_UUID.encode('utf-16le')) == 1
        payloads['AndroidManifest.xml'] = manifest.replace(OLD_UUID.encode('utf-16le'), uid.encode('utf-16le'))
        for item in source.infolist():
            if item.filename not in SIGNATURES:
                dest.writestr(item, payloads.get(item.filename, source.read(item.filename)))
    align = Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    b.run([align, '-p', '4', work / 'unsigned.apk', work / 'aligned.apk'], work, 'align')
    apk = out / args.name
    b.run(['powershell', '-NoProfile', '-NonInteractive', '-File', HERE.parent / 'lens0907-0908/sign_apk.ps1',
           '-InputApk', work / 'aligned.apk', '-OutputApk', apk, '-ApkSigner', b.ALIB / 'apksigner.jar', '-Java', b.JAVA], work, 'sign')
    sig = b.run([b.JAVA, '-jar', b.ALIB / 'apksigner.jar', 'verify', '--verbose', '--print-certs', apk], work, 'verify-signature')
    assert b.CERT in sig.lower()
    assert all('Verified using ' + x + ': true' in sig for x in ['v1 scheme (JAR signing)', 'v2 scheme (APK Signature Scheme v2)'])
    b.run([align, '-c', '-p', '4', apk], work, 'verify-align')
    with zipfile.ZipFile(APK) as source, zipfile.ZipFile(apk) as final:
        assert len(final.namelist()) == len(set(final.namelist()))
        assert set(final.namelist()) - SIGNATURES == set(source.namelist()) - SIGNATURES
        members = 0
        for name in set(final.namelist()) - SIGNATURES:
            assert final.read(name) == payloads.get(name, source.read(name)), name
            members += 1
        assert b.sha(final.read(SWF_MEMBER)) == b.sha(swf.read_bytes())
        manifest = final.read('AndroidManifest.xml')
        assert manifest.count(uid.encode('utf-16le')) == 1 and OLD_UUID.encode('utf-16le') not in manifest
    assert b.sha(APK.read_bytes()) == APK_SHA
    report = {
        'apk': str(apk), 'sha256': b.sha(apk.read_bytes()), 'size_bytes': apk.stat().st_size,
        'swf_sha256': b.sha(swf.read_bytes()), 'dex_sha256': b.sha(payloads['classes.dex']),
        'build_id': BUILD_ID, 'platform': 'android', 'origin': origin,
        'package_name': 'com.leiting.wf', 'version_name': '1.8.1', 'version_code': 1008001,
        'formal_id_and_key_preserved': True, 'private_key_created_or_rotated': False,
        'input_apk': str(APK), 'input_sha256': APK_SHA, 'input_swf_sha256': SWF_SHA,
        'input_uuid': OLD_UUID, 'uniqueappversionid': uid, 'address_constants': changes,
        'abc_count': 296, 'method_bodies_checked': 96631, 'method_bytecode_changes': 0,
        'all_abc_bytes_preserved_after_reversing_address_constants': True,
        'original_preferences_preserved': True, 'diagnostics_added': False,
        'r10_and_all_cumulative_optimizations_preserved': True,
        'native_class_count': 6, 'native_changes_only_uuid': changed,
        'members_read_back': members, 'signer_sha256': b.CERT, 'v1_v2': True, 'zipalign': True,
        'registry_promoted': False, 'device_tested': False, 'save_schema_change': False,
        'server_pair': 'Use existing formal Android allow entry and private key; no new admission ID.',
    }
    (out / (apk.stem + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    (out / 'SHA256.txt').write_text(report['sha256'] + '  ' + apk.name + '\n', 'utf-8')
    print(json.dumps({k: report[k] for k in ['apk', 'sha256', 'build_id', 'uniqueappversionid']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--keys', type=Path, required=True)
    main(parser.parse_args())
