"""Repack a verified Lens SWF into the current accepted cumulative Android APK."""
import argparse
import hashlib
import json
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent/'rush-leaderboard'))
from apk_build_common import replace_apk, sha256, verify, SWF_MEMBER


def run(command, log):
    with log.open('w', encoding='utf-8') as stream:
        process = subprocess.Popen(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT)
        try:
            if process.wait(timeout=240):
                raise RuntimeError(f'packaging command failed; see {log}')
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
                process.wait(timeout=15)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--variant', choices=['public', 'lan'], required=True)
    p.add_argument('--swf', type=Path, required=True)
    p.add_argument('--validation-report', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--build-tools', type=Path, required=True)
    a = p.parse_args()
    registry = json.loads((HERE.parent/'android-accepted.json').read_text('utf-8-sig'))
    accepted = registry['variants'][a.variant]
    base = REPO/accepted['apk']
    assert sha256(base) == accepted['apk_sha256'], 'accepted APK identity changed'
    with zipfile.ZipFile(base) as z:
        assert hashlib.sha256(z.read(SWF_MEMBER)).hexdigest() == accepted['swf_sha256']
    checks = json.loads(a.validation_report.read_text('utf-8'))
    assert checks['status'] == 'passed_static_readback'
    assert checks['base_swf_sha256'] == accepted['swf_sha256']
    assert checks['swf_sha256'] == sha256(a.swf)
    graft = json.loads(a.swf.with_suffix('.report.json').read_text('utf-8'))
    assert graft['swf_sha256'] == checks['swf_sha256']
    assert graft['base_swf_sha256'] == accepted['swf_sha256']
    assert graft['existing_pools_preserved'] and graft['non_main_abc_tags_preserved']
    a.out.mkdir(parents=True, exist_ok=False)
    new_uuid = str(uuid.uuid4())
    assert new_uuid not in {v['uniqueappversionid'] for v in registry['variants'].values()}
    intent = {'variant': a.variant, 'base_apk': accepted['apk'], 'base_apk_sha256': accepted['apk_sha256'],
              'base_swf_sha256': accepted['swf_sha256'], 'swf_sha256': checks['swf_sha256'],
              'uniqueappversionid': new_uuid, 'accepted_registry_updated': False}
    (a.out/'build-intent.json').write_text(json.dumps(intent, indent=2)+'\n', 'utf-8')
    unsigned, aligned = a.out/'unsigned.apk', a.out/'aligned.apk'
    final = a.out/f'StarPoint-CN-1.8.1-lens0907-0908-{a.variant}-candidate-20260908.apk'
    aligner = a.build_tools/'zipalign.exe'
    signer = a.build_tools/'lib/apksigner.jar'
    print('Repacking accepted', a.variant, 'APK', flush=True)
    replace_apk(base, a.swf, unsigned, new_uuid, base_uuid=accepted['uniqueappversionid'])
    run([aligner, '-p', '4', unsigned, aligned], a.out/'zipalign-build.log')
    unsigned.unlink()  # exact file created above; keeps peak temporary data small
    run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', HERE/'sign_apk.ps1',
         '-InputApk', aligned, '-OutputApk', final, '-ApkSigner', signer], a.out/'signing.log')
    result = verify(base, final, a.swf, new_uuid, Path('java'), signer, base_uuid=accepted['uniqueappversionid'])
    run([aligner, '-c', '-p', '4', final], a.out/'zipalign-check.log')
    aligned.unlink()
    result.update(intent)
    result.update({'apk': str(final.resolve()), 'status': 'signed_candidate_pending_device_and_content_validation',
                   'v1_signature': True, 'v2_signature': True, 'zip_alignment': True,
                   'unrelated_apk_members_unchanged': True, 'manifest_only_air_uuid_changed': True,
                   'device_tested': False, 'shared_resource_patch_activated': False,
                   'independent_swf_checks': checks})
    (a.out/'verification-report.json').write_text(json.dumps(result, indent=2)+'\n', 'utf-8')
    (a.out/(final.name+'.sha256')).write_text(result['apk_sha256']+'  '+final.name+'\n', 'utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
