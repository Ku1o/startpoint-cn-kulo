"""Package a channel-only APK. No quest edits, runtime sync or registry promotion."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import uuid
from build_channel import HERE, module, run, dump

def package(work, out, java, build_tools):
    common = module('quest_element_apk_common', HERE.parent/'rush-leaderboard/apk_build_common.py')
    common.run = run
    checker = module('quest_element_package_baseline', HERE.parent/'verify_android_baseline.py')
    swf_report = json.loads((work/'swf-report.json').read_text('utf8'))
    variant = swf_report.get('variant','public')
    identity = checker.verify(variant)
    assert identity == swf_report['baseline']
    swf = work/f'quest-element-{variant}.swf'
    assert common.sha256(swf) == swf_report['output_swf_sha256']
    assert common.sha256(HERE/'src/cn/rules/QuestElementResistance.as') == swf_report['helper_source_sha256']
    assert common.sha256(work/'quest-element.swc') == swf_report['helper_swc_sha256']
    tests = json.loads((work/'harness-result.json').read_text('utf8'))
    assert tests['passed'] and len(tests['checks']) == 351
    assert (work/'ffdec-body-check.log').read_text('utf8').strip() == 'PASS original_bodies=96404 helper_bodies=5 changed=[284:21496]'
    assert 'OK' in (work/'ffdec-readback.log').read_text('utf8')
    assert not out.exists(), 'delivery must use a new output directory'
    new_uuid = str(uuid.uuid4())
    unsigned = work/'unsigned.apk'; aligned = work/'aligned.apk'; signed = work/'signed.apk'
    assert not any(p.exists() for p in [unsigned,aligned,signed]), 'APK scratch outputs already exist'
    common.replace_apk(Path(identity['apk']),swf,unsigned,new_uuid,base_uuid=identity['uniqueappversionid'])
    run([build_tools/'zipalign.exe','-p','4',unsigned,aligned],work/'zipalign.log')
    run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
         HERE.parent/'lens0907-0908/sign_apk.ps1','-InputApk',aligned,'-OutputApk',signed,
         '-ApkSigner',build_tools/'lib/apksigner.jar','-Java',java],work/'sign.log')
    result = common.verify(Path(identity['apk']),signed,swf,new_uuid,java,build_tools/'lib/apksigner.jar',
                           base_uuid=identity['uniqueappversionid'])
    run([build_tools/'zipalign.exe','-c','-p','4',signed],work/'zipalign-final.log')
    out.mkdir(parents=True)
    suffix = '' if variant == 'public' else '-lan'
    apk = out/f'StarPoint-CN-1.8.1-quest-element-channel{suffix}-test-20260910.apk'
    shutil.copy2(signed,apk); assert common.sha256(apk) == result['apk_sha256']
    result.update(status='offline_verified_channel_test',variant=variant,apk=str(apk),baseline=identity,
        original_game_method_bodies_checked=96404,modified_game_methods=['284:21496'],
        original_instructions_and_branches_preserved=True,original_constant_pools_preserved=True,
        added_helper_methods=5,desktop_air_checks=351,desktop_air_test_passed=True,
        compiler_sdk='AIRSDK 51.2.1.5; helper only, SWF 44 target Player 32',
        desktop_test_runtime='AIRSDK 51.2.1.5 ADL; does not establish Android AIR compatibility',
        apk_native_air_runtime='33.1.1.620, preserved byte for byte',
        android_device_tested=False,active_quest_configuration=False,random_tower_generated=False,
        manifest_only_uuid_changed=True,all_other_apk_members_unchanged=True,
        zipalign=True,v1_signature=True,v2_signature=True,
        accepted_registry_changed=False,server_changes=[],runtime_sync_paths=[],ios_changes=[])
    dump(out/'verification-report.json',result)
    for name in ['swf-report.json','harness-result.json','ffdec-body-check.log']:
        shutil.copy2(work/name,out/name)
    guide = (HERE/'USER-GUIDE.txt').read_text('utf8')
    if variant == 'lan': guide = guide.replace('公网','内网')
    (out/'测试说明.txt').write_text(guide,encoding='utf8')
    (out/'SHA256.txt').write_text(result['apk_sha256']+'  '+apk.name+'\n',encoding='utf8')
    for path in [unsigned,aligned,signed]:
        assert path.resolve().parent == work.resolve()
        path.unlink()
    print(json.dumps({'apk':str(apk),'sha256':result['apk_sha256'],'uuid':new_uuid},ensure_ascii=False))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--work',required=True,type=Path); p.add_argument('--out',required=True,type=Path)
    p.add_argument('--java',type=Path,default=Path(r'D:\java\bin\java.exe'))
    p.add_argument('--build-tools',type=Path,default=Path(r'F:\StartPointCN\wf_full_patch\build-tools'))
    args = p.parse_args(); package(args.work,args.out,args.java,args.build_tools)
