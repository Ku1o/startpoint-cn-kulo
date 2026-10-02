"""Package and sign the independent-formations candidate from the exact 8001 APK."""
import json, os, shutil, uuid, zipfile
from pathlib import Path

from build_swf import INPUT, WORK
from common import JAVA, ROOT, SDK, dump, run, sha

OUT = Path(r'F:\codex\outputs\independent-formations-public-8001-20260923')
BUILD_ID = 'android-181-independent-party-20260923'
SOURCE_APK = Path(r'F:\codex\outputs\generic-damage-public-8001-20260923\StarPoint-CN-generic-damage-8001-public-31cfc4bd.apk')
EXPECTED_APK_SHA = '0faa82b47879437d54e2e1031c0484f8b34fe0c032d6b63e1cf7b132630b1448'
SWF_MEMBER = 'assets/worldflipper_android_release.swf'
SIGNATURE_MEMBERS = {'META-INF/MANIFEST.MF', 'META-INF/WF.SF', 'META-INF/WF.RSA'}
EXPECTED_SIGNER = '569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894'


def main():
    assert sha(SOURCE_APK.read_bytes()) == EXPECTED_APK_SHA
    swf = WORK / 'independent-formations.swf'
    swf_report = json.loads((WORK / 'swf-report.json').read_text('utf8'))
    assert sha(swf.read_bytes()) == swf_report['output_swf_sha256']
    uid = str(uuid.uuid4())
    with zipfile.ZipFile(SOURCE_APK) as src:
        original_swf = src.read(SWF_MEMBER)
        original_uuid = '31cfc4bd-f67a-4d88-aa6e-9810fefe742b'
        assert sha(original_swf) == '1ed8b35a3776912d69d28a17dc87aab36bb11028a97e990a656fed6e5a95cde1'
        manifest = src.read('AndroidManifest.xml')
        assert manifest.count(original_uuid.encode('utf-16le')) == 1
        original_dex = src.read('classes.dex')

        bt = Path(r'F:\StartPointCN\wf_full_patch\build-tools')
        libs = SDK / 'lib/android/lib'
        (WORK / 'original.dex').write_bytes(original_dex)
        smali = WORK / ('smali-' + uid)
        back = WORK / ('smali-readback-' + uid)
        run([JAVA, '-jar', libs / 'baksmali.jar', 'd', '-o', smali, WORK / 'original.dex'], 'dex-decode-independent')
        originals = {p.relative_to(smali): p.read_text('utf8') for p in smali.rglob('*.smali')}
        hits = {}
        for name, text in originals.items():
            count = text.count(original_uuid)
            if count:
                assert name.as_posix() in ('cn/startpoint/StartupCache.smali', 'cn/startpoint/BuildIdentity.smali')
                (smali / name).write_text(text.replace(original_uuid, uid), encoding='utf8')
                hits[str(name)] = count
        assert hits
        new_dex = WORK / 'classes.dex'
        run([JAVA, '-jar', libs / 'smali.jar', 'a', '-a', '21', '-o', new_dex, smali], 'dex-assemble-independent')
        run([JAVA, '-jar', libs / 'baksmali.jar', 'd', '-o', back, new_dex], 'dex-readback-independent')
        for name, text in originals.items():
            recovered = (back / name).read_text('utf8').replace(uid, original_uuid)
            assert recovered == text, str(name)

        payloads = {
            'AndroidManifest.xml': manifest.replace(original_uuid.encode('utf-16le'), uid.encode('utf-16le')),
            'classes.dex': new_dex.read_bytes(),
            SWF_MEMBER: swf.read_bytes(),
        }
        unsigned = WORK / ('unsigned-' + uid + '.apk')
        aligned = WORK / ('aligned-' + uid + '.apk')
        with zipfile.ZipFile(unsigned, 'w') as dst:
            for item in src.infolist():
                if item.filename in SIGNATURE_MEMBERS:
                    continue
                dst.writestr(item, payloads.get(item.filename, src.read(item.filename)))

    run([bt / 'zipalign.exe', '-p', '4', unsigned, aligned], 'zipalign-independent')
    OUT.mkdir(parents=True, exist_ok=True)
    apk = OUT / ('StarPoint-CN-generic-damage-8001-public-independent-formations-' + uid[:8] + '.apk')
    run(['powershell', '-NoProfile', '-NonInteractive', '-File',
         ROOT / 'client-patch/lens0907-0908/sign_apk.ps1',
         '-InputApk', aligned, '-OutputApk', apk,
         '-ApkSigner', bt / 'lib/apksigner.jar', '-Java', JAVA], 'sign-independent')
    verify = run([JAVA, '-jar', bt / 'lib/apksigner.jar', 'verify', '--verbose', '--print-certs', apk], 'verify-independent')
    assert EXPECTED_SIGNER in verify.lower()
    assert 'Verified using v1 scheme (JAR signing): true' in verify
    assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in verify
    run([bt / 'zipalign.exe', '-c', '-p', '4', apk], 'verify-alignment-independent')

    with zipfile.ZipFile(SOURCE_APK) as src, zipfile.ZipFile(apk) as dst:
        assert dst.testzip() is None
        assert set(src.namelist()) - SIGNATURE_MEMBERS == set(dst.namelist()) - SIGNATURE_MEMBERS
        for name in set(src.namelist()) - SIGNATURE_MEMBERS:
            expected = payloads.get(name, src.read(name))
            assert dst.read(name) == expected, name
        assert dst.read(SWF_MEMBER) == swf.read_bytes()

    report = {
        'status': 'offline_candidate',
        'apk': str(apk),
        'apk_sha256': sha(apk.read_bytes()),
        'swf_sha256': sha(swf.read_bytes()),
        'source_apk': str(SOURCE_APK),
        'source_apk_sha256': EXPECTED_APK_SHA,
        'source_swf_sha256': sha(original_swf),
        'uniqueappversionid': uid,
        'previous_uniqueappversionid': original_uuid,
        'build_id': BUILD_ID,
        'package_name': 'com.leiting.wf',
        'version_name': '1.8.1',
        'version_code': 1008001,
        'endpoint': os.environ.get('STARPOINT_ENDPOINT', 'http://localhost:8001'),
        'source_main_abc_index': swf_report['source_main_abc_index'],
        'final_main_abc_index': swf_report['final_main_abc_index'],
        'source_main_method_bodies': swf_report['source_main_method_bodies'],
        'helper_methods': swf_report['helper_methods'],
        'swf_changes': swf_report['changes'],
        'admission_changes': swf_report['admission_changes'],
        'admission_proof_prefix_verified': True,
        'native_identity_sites': hits,
        'signer_certificate_sha256': EXPECTED_SIGNER,
        'zipalign': True,
        'v1_signature': True,
        'v2_signature': True,
        'unchanged_apk_members_verified': True,
        'mumu_verified': False,
        'device_tested': False,
        'server_admission_pair_prepared': False,
        'scope': 'exact direct-8001 public generic-damage APK with independent Rush party-set client patch',
    }
    dump(OUT / 'package-report.json', report)
    dump(WORK / 'package-report.json', report)
    for path in (unsigned, aligned):
        if path.exists():
            path.unlink()
    for path in (smali, back):
        if path.exists():
            shutil.rmtree(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
