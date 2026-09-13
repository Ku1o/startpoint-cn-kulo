"""Package the verified LAN SWF; preserve every other cumulative APK behavior."""
import argparse
import json
import uuid
import zipfile
from pathlib import Path

from patch_swf import module, s

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
b = module('shop_apk_build', HERE.parent / 'startup-cache/build.py')
native = module('shop_apk_native', HERE.parent / 'startup-cache/verify_native.py')
checker = module('shop_apk_baseline', HERE.parent / 'verify_android_baseline.py')


def main(args):
    work, out, swf = args.work.resolve(), args.out.resolve(), args.swf.resolve()
    assert not work.exists() and not out.exists()
    assert '.cdn' not in work.parts and '.cdn' not in out.parts
    # This is the pinned reproduction input, not the evolving current registry.
    accepted = checker.verify('lan', record_path=HERE.parent / 'accepted-history/android-record-holder-20260912.json')
    parent = Path(accepted['apk'])
    swf_report = json.loads(swf.with_suffix('.json').read_text('utf-8'))
    readback = json.loads(args.swf_checks.read_text('utf-8'))
    runtime = json.loads(args.runtime_checks.read_text('utf-8'))
    assert swf_report['parent_swf_sha256'] == accepted['swf_sha256']
    assert swf_report['swf_sha256'] == readback['candidate_swf_sha256'] == b.sha(swf.read_bytes())
    assert readback['passed'] and runtime['passed']
    abcs = [t[3] for t in s.parts(swf)[2] if t[0] == 82]
    assert len(abcs) == 292
    assert b.sha(abcs[290].serialize()) == runtime['helper_abc_sha256']
    assert runtime['helper_source_sha256'] == b.sha((HERE / 'src/cn/shop/ShopFirstOpen.as').read_bytes())
    assert set(swf_report['changed_original_bodies']) == {25379, 25381, 67327, 72196, 81189}
    work.mkdir(parents=True)
    out.mkdir(parents=True)
    old_uid, uid = accepted['uniqueappversionid'], str(uuid.uuid4())
    assert old_uid != uid
    (work / 'uuid.txt').write_text(uid + '\n', encoding='ascii')
    with zipfile.ZipFile(parent) as archive:
        (work / 'original.dex').write_bytes(archive.read('classes.dex'))
    java, libs, run = b.JAVA, b.ALIB, b.run
    run([java, '-jar', libs / 'baksmali.jar', 'd', '-o', work / 'smali', work / 'original.dex'],
        work, 'dex-decode')
    original = {p.relative_to(work / 'smali'): p.read_text('utf-8') for p in (work / 'smali').rglob('*.smali')}
    hits = {}
    for name, text in original.items():
        count = text.count(old_uid)
        if count:
            assert name.as_posix() in ('cn/startpoint/StartupCache.smali', 'cn/startpoint/BuildIdentity.smali')
            (work / 'smali' / name).write_text(text.replace(old_uid, uid), encoding='utf-8')
            hits[name.as_posix()] = count
    assert len(hits) == 2 and sum(hits.values()) == 2
    run([java, '-jar', libs / 'smali.jar', 'a', '-a', '21', '-o', work / 'classes.dex', work / 'smali'],
        work, 'dex-assemble')
    run([java, '-jar', libs / 'baksmali.jar', 'd', '-o', work / 'readback', work / 'classes.dex'],
        work, 'dex-readback')
    assert len(list((work / 'readback').rglob('*.smali'))) == len(original) == 6
    for name, text in original.items():
        restored = (work / 'readback' / name).read_text('utf-8').replace(uid, old_uid)
        assert native.canonical(restored) == native.canonical(text), name
    print('Native startup-cache behavior preserved; fresh AIR identity verified.', flush=True)

    signatures = {'META-INF/MANIFEST.MF', 'META-INF/WF.SF', 'META-INF/WF.RSA'}
    payloads = {'assets/worldflipper_android_release.swf': swf.read_bytes(),
                'classes.dex': (work / 'classes.dex').read_bytes()}
    with zipfile.ZipFile(parent) as source, zipfile.ZipFile(work / 'unsigned.apk', 'w') as dest:
        manifest = source.read('AndroidManifest.xml')
        assert manifest.count(old_uid.encode('utf-16le')) == 1
        payloads['AndroidManifest.xml'] = manifest.replace(old_uid.encode('utf-16le'), uid.encode('utf-16le'))
        for item in source.infolist():
            name = item.filename
            if name not in signatures:
                dest.writestr(item, payloads[name] if name in payloads else source.read(name))
    align = Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    run([align, '-p', '4', work / 'unsigned.apk', work / 'aligned.apk'], work, 'align')
    apk = out / 'StarPoint-CN-1.8.1-shop-first-open-lan-test-20260913.apk'
    run(['powershell', '-NoProfile', '-NonInteractive', '-File', HERE.parent / 'lens0907-0908/sign_apk.ps1',
         '-InputApk', work / 'aligned.apk', '-OutputApk', apk, '-ApkSigner', libs / 'apksigner.jar', '-Java', java],
        work, 'sign')
    signature = run([java, '-jar', libs / 'apksigner.jar', 'verify', '--verbose', '--print-certs', apk],
                    work, 'verify-signature')
    assert b.CERT in signature.lower()
    assert all('Verified using ' + scheme + ': true' in signature for scheme in (
        'v1 scheme (JAR signing)', 'v2 scheme (APK Signature Scheme v2)'))
    run([align, '-c', '-p', '4', apk], work, 'verify-alignment')
    with zipfile.ZipFile(parent) as source, zipfile.ZipFile(apk) as dest:
        assert len(dest.namelist()) == len(set(dest.namelist()))
        members = set(source.namelist()) - signatures
        assert members == set(dest.namelist()) - signatures
        for name in members:
            assert dest.read(name) == (payloads[name] if name in payloads else source.read(name)), name
        manifest = dest.read('AndroidManifest.xml')
        assert manifest.count(uid.encode('utf-16le')) == 1 and old_uid.encode('utf-16le') not in manifest
        assert b.sha(dest.read('assets/worldflipper_android_release.swf')) == swf_report['swf_sha256']
    report = {
        'variant': 'lan', 'apk': str(apk), 'apk_sha256': b.sha(apk.read_bytes()), 'size_bytes': apk.stat().st_size,
        'parent_apk_sha256': accepted['apk_sha256'], 'parent_registry': accepted['registry'],
        'endpoint': accepted['endpoint'], 'endpoint_unchanged': True,
        'uniqueappversionid': uid, 'native_build_identity': uid, 'native_identity_sites': hits,
        'native_behavior_unchanged': True, 'signer_sha256': b.CERT, 'zipalign': True, 'v1_v2_signatures': True,
        'changed_apk_members': list(payloads), 'all_other_apk_members_unchanged': True,
        'verified_non_signature_members': len(members), 'swf': swf_report,
        'swf_readback': readback, 'desktop_air': runtime,
        'package_name': 'com.leiting.wf', 'version_name': '1.8.1', 'version_code': 1008001,
        'device_tested_at_build': False, 'registry_promoted': False,
        'server_synced_or_restarted': False, 'ios_changed': False,
        'persistence_impact': 'No saved IDs, schema, progress or import/export changes; only read paths and UI refresh.',
    }
    (out / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'SHA256.txt').write_text(report['apk_sha256'] + '  ' + apk.name + '\n', encoding='ascii')
    print(json.dumps({'apk': str(apk), 'sha256': report['apk_sha256'], 'size_bytes': apk.stat().st_size,
                      'signing_and_payload_verification': 'passed'}, ensure_ascii=False), flush=True)
    # Only disposable, exact-name intermediates produced by this invocation.
    for name in ('unsigned.apk', 'aligned.apk'):
        file = (work / name).resolve()
        assert file.parent == work
        file.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--swf', type=Path, required=True)
    parser.add_argument('--runtime-checks', type=Path, required=True)
    parser.add_argument('--swf-checks', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args())
