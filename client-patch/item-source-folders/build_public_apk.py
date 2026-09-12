"""Convert the device-tested three-fix LAN APK to the registered public endpoint.

Preserve every SWF method and native operation. Only the endpoint constant and
installation identities change. Does not install, contact players, or deploy.
"""
import argparse
import importlib.util
import json
import struct
import sys
import uuid
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


build = module('cache_apk_build', HERE.parent / 'startup-cache/build.py')
swf = module('cache_swf_build', HERE.parent / 'startup-cache/build_swf.py')
native = module('cache_native_check', HERE.parent / 'startup-cache/verify_native.py')
checker = module('cache_baseline_check', HERE.parent / 'verify_android_baseline.py')
BASE = ROOT / 'outputs/item-source-folders-lan-test-20260912/StarPoint-CN-1.8.1-item-source-folders-lan-test-20260912.apk'
BASE_SHA = 'e79f6abcde6ce9286023689a876173a8bb9d8ed2583aee06a11a6b128e91674e'
BASE_SWF_SHA = '657ad0b8413b95fc875e62d227b1b0034b3421a2b2777dc09bb1cce7b3ec5445'
BASE_UUID = 'c123fbdd-9ee9-4eda-afd8-ce04b3a7bd3c'
PUBLIC_PARENT_SHA = 'e38ef8256a9fdabd6f834302fbde0c0fdcedf7c8972b3ed5d15b15f66d1038f1'
LAN_PARENT_SHA = '0636312d521aa0e075a7c1180cdc6d0e93817e02df63f488cdaf1b8b0f801a1b'


def main(args):
    work, out = args.work.resolve(), args.out.resolve()
    assert not work.exists() and not out.exists(), 'fresh directories required'
    assert '.cdn' not in work.parts and '.cdn' not in out.parts
    record = HERE.parent / 'accepted-history/android-cache-party-20260912.json'
    public, lan = checker.verify('public', record_path=record), checker.verify('lan', record_path=record)
    assert public['apk_sha256'] == PUBLIC_PARENT_SHA and lan['apk_sha256'] == LAN_PARENT_SHA
    assert build.sha(BASE.read_bytes()) == BASE_SHA
    work.mkdir(parents=True)
    out.mkdir(parents=True)
    uid = str(uuid.uuid4())
    with zipfile.ZipFile(BASE) as archive:
        before = archive.read('assets/worldflipper_android_release.swf')
        assert build.sha(before) == BASE_SWF_SHA
        (work / 'input.swf').write_bytes(before)
        (work / 'original.dex').write_bytes(archive.read('classes.dex'))
    version, header, tags = swf.parts(work / 'input.swf')
    abcs = [row for row in tags if row[0] == 82]
    assert len(abcs) == 291 and sum(len(row[3].bodies) for row in abcs) == 96535
    main_tag = abcs[290]
    abc = main_tag[3]
    assert swf.serialize(abc, main_tag[4]) == main_tag[4]
    view = swf.m.View(SimpleNamespace(abc=abc), swf.m.asm)
    body = 92013
    assert view.labels[abc.bodies[body][0]] == 'pinball.config.gbits::DevConfig_gf_android/<ctor>'
    instruction = swf.m.asm.decode(abc.bodies[body][5])[11]
    assert instruction.op == 0x2c
    index = instruction.args[0]
    local, host = lan['endpoint'].split('://', 1)[1], public['endpoint'].split('://', 1)[1]
    assert abc.strings[index] == local.encode()
    uses = []
    for bi, method in enumerate(abc.bodies):
        for ii, ins in enumerate(swf.m.asm.decode(method[5])):
            if ((ins.op in (0x2c, 0x06, 0xf1) and ins.args[0] == index)
                    or (ins.op == 0xef and ins.args[1] == index)):
                uses.append((bi, ii))
    assert uses == [(body, 11)], uses
    abc.strings[index] = host.encode()
    replacement = swf.serialize(abc, main_tag[4])
    # Restoring this one string recovers the entire original ABC byte-for-byte.
    abc.strings[index] = local.encode()
    assert swf.serialize(abc, main_tag[4]) == main_tag[4]
    data = main_tag[2] + replacement
    main_tag[1] = struct.pack('<HI', (82 << 6) | 63, len(data)) + data
    raw = header + b''.join(row[1] for row in tags)
    assert local.encode() not in raw
    target = work / 'public.swf'
    target.write_bytes(b'CWS' + bytes([version]) + struct.pack('<I', len(raw) + 8) + zlib.compress(raw))
    final_tags = swf.parts(target)[2]
    assert sum(a[1] != b[1] for a, b in zip(swf.parts(work / 'input.swf')[2], final_tags)) == 1
    final_main = [row[3] for row in final_tags if row[0] == 82][290]
    assert final_main.strings[index] == host.encode()
    final_main.strings[index] = local.encode()
    assert swf.serialize(final_main, main_tag[4]) == main_tag[4]
    print('Public endpoint verified; all 96,535 SWF methods preserved', flush=True)

    run, java, libs = build.run, build.JAVA, build.ALIB
    ffdec = Path('F:/codex/tools/ffdec_26.2.1/ffdec.jar')
    classes = work / 'java'; classes.mkdir()
    run([java.with_name('javac.exe'), '-cp', ffdec, '-d', classes,
         HERE.parent / 'character-carousel/CompareMethodBodies.java'], work, 'ffdec-compile')
    check = run([java, '-Xmx2g', '-cp', str(classes) + ';' + str(ffdec),
                 'CompareMethodBodies', work / 'input.swf', target], work, 'ffdec-compare')
    assert 'method_bodies=96535' in check and 'changed_count=0' in check
    run([java, '-jar', libs / 'baksmali.jar', 'd', '-o', work / 'smali', work / 'original.dex'], work, 'dex-decode')
    original = {p.relative_to(work / 'smali'): p.read_text() for p in (work / 'smali').rglob('*.smali')}
    count = 0
    for name, text in original.items():
        hits = text.count(BASE_UUID)
        if hits:
            assert name.as_posix() in ('cn/startpoint/StartupCache.smali', 'cn/startpoint/BuildIdentity.smali')
            count += hits
            (work / 'smali' / name).write_text(text.replace(BASE_UUID, uid))
    assert count == 2, count
    run([java, '-jar', libs / 'smali.jar', 'a', '-a', '21', '-o', work / 'classes.dex', work / 'smali'], work, 'dex-build')
    run([java, '-jar', libs / 'baksmali.jar', 'd', '-o', work / 'readback', work / 'classes.dex'], work, 'dex-readback')
    assert len(list((work / 'readback').rglob('*.smali'))) == len(original) == 6
    for name, text in original.items():
        assert native.canonical((work / 'readback' / name).read_text().replace(uid, BASE_UUID)) == native.canonical(text), name
    dex = (work / 'classes.dex').read_bytes()
    assert BASE_UUID.encode() not in dex and dex.count(uid.encode()) == 1
    print('Native cleanup identity renewed; all six classes verified', flush=True)

    excluded = {'META-INF/MANIFEST.MF', 'META-INF/WF.SF', 'META-INF/WF.RSA'}
    payloads = {'assets/worldflipper_android_release.swf': target.read_bytes(), 'classes.dex': dex}
    with zipfile.ZipFile(BASE) as source, zipfile.ZipFile(work / 'unsigned.apk', 'w') as dest:
        manifest = source.read('AndroidManifest.xml')
        assert manifest.count(BASE_UUID.encode('utf-16le')) == 1
        payloads['AndroidManifest.xml'] = manifest.replace(BASE_UUID.encode('utf-16le'), uid.encode('utf-16le'))
        for item in source.infolist():
            if item.filename not in excluded:
                dest.writestr(item, payloads.get(item.filename, source.read(item.filename)))
    align = Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    run([align, '-p', '4', work / 'unsigned.apk', work / 'aligned.apk'], work, 'align')
    apk = out / 'StarPoint-CN-1.8.1-item-source-records-public-20260912.apk'
    run(['powershell', '-NoProfile', '-NonInteractive', '-File', HERE.parent / 'lens0907-0908/sign_apk.ps1',
         '-InputApk', work / 'aligned.apk', '-OutputApk', apk, '-ApkSigner', libs / 'apksigner.jar', '-Java', java], work, 'sign')
    signature = run([java, '-jar', libs / 'apksigner.jar', 'verify', '--verbose', '--print-certs', apk], work, 'verify-signature')
    assert build.CERT in signature.lower()
    for scheme in ('v1 scheme (JAR signing)', 'v2 scheme (APK Signature Scheme v2)'):
        assert 'Verified using ' + scheme + ': true' in signature
    run([align, '-c', '-p', '4', apk], work, 'verify-alignment')
    with zipfile.ZipFile(BASE) as source, zipfile.ZipFile(apk) as dest:
        assert set(source.namelist()) - excluded == set(dest.namelist()) - excluded
        for name in set(source.namelist()) - excluded:
            assert dest.read(name) == payloads.get(name, source.read(name)), name
        manifest = dest.read('AndroidManifest.xml')
        assert manifest.count(uid.encode('utf-16le')) == 1 and BASE_UUID.encode('utf-16le') not in manifest
    report = {'apk': str(apk), 'apk_sha256': build.sha(apk.read_bytes()), 'swf_sha256': build.sha(target.read_bytes()),
              'endpoint': public['endpoint'], 'uniqueappversionid': uid, 'native_build_identity': uid,
              'signer_sha256': build.CERT, 'lan_input_apk_sha256': BASE_SHA, 'lan_input_swf_sha256': BASE_SWF_SHA,
              'changed_endpoint_pool_index': index, 'swf_methods_checked': 96535, 'changed_method_bytes': 0,
              'native_classes_checked': 6, 'native_logic_unchanged': True, 'zipalign': True, 'signature_v1_v2': True,
              'other_apk_members_unchanged': True, 'device_tested_public_apk': False,
              'lan_input_user_accepted': True, 'abyss_records_and_folder_gate_preserved': True,
              'cloud_deployed': False, 'registry_promoted': False, 'commit_created': False}
    (out / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'SHA256.txt').write_text(report['apk_sha256'] + '  ' + apk.name + '\n', encoding='ascii')
    for name in ('unsigned.apk', 'aligned.apk'):
        file = (work / name).resolve()
        assert file.parent == work
        file.unlink()
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args())
