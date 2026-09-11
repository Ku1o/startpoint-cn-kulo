"""Package the cumulative LAN details UI candidate; no accepted-registry promotion."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import uuid
import importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('abyss_details_package_builder',HERE/'build_swf.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
module,run,dump=b.module,b.run,b.dump

def package(work, out, java, build_tools):
    work = work.resolve()
    out = out.resolve()
    common = module('quest_element_apk_common', HERE.parent/'rush-leaderboard/apk_build_common.py')
    common.run = run
    swf_report = json.loads((work/'swf-report.json').read_text('utf8'))
    checker = module('abyss_details_package_baseline',HERE.parent/'verify_android_baseline.py')
    assert checker.verify('lan') == swf_report['accepted']
    identity = dict(apk=swf_report['input_apk'], apk_sha256=swf_report['input_apk_sha256'],
        uniqueappversionid=swf_report['input_uniqueappversionid'])
    assert common.sha256(Path(identity['apk'])) == identity['apk_sha256']
    swf = work/'abyss-details-lan.swf'
    assert common.sha256(swf) == swf_report['output_swf_sha256']
    assert common.sha256(HERE/'src/cn/ui/AbyssDetails.as') == swf_report['helper_source_sha256']
    assert common.sha256(work/'abyss-details.swc') == swf_report['helper_swc_sha256']
    driver = module('abyss_details_package_driver', HERE/'build.py')
    state = driver.air.read(work/'air-validation.json')
    tests = driver.air.require_validated(work,driver.air_input_paths(work,Path(state['paths']['fixtures'])))
    assert tests['passed'] and len(tests['checks']) == 223
    assert (work/'ffdec-body-check.log').read_text('utf8').strip() == 'PASS original_bodies=96409 helper_bodies=13 changed=[285:71835, 285:78350]'
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
    apk = out/'StarPoint-CN-1.8.1-abyss-details-lan-test-20260910.apk'
    shutil.copy2(signed,apk); assert common.sha256(apk) == result['apk_sha256']
    result.update(status='offline_verified_local_test',variant='lan',apk=str(apk),input=identity,
        accepted_baseline=swf_report['accepted'],original_game_method_bodies_checked=96409,
        modified_game_methods=['285:71835','285:78350'],added_helper_methods=13,
        original_instructions_and_branches_preserved=True,original_constant_pools_preserved=True,
        desktop_air_checks=len(tests['checks']),desktop_air_test_passed=True,
        desktop_air_native_apis=['RichTextLayoutParser','UiText','Sprite','Quad','RichTextDialog'],
        desktop_test_runtime='AIRSDK 51.2.1.5 ADL; does not establish Android AIR compatibility',
        apk_native_air_runtime='33.1.1.620, preserved byte for byte',android_device_tested=False,
        manifest_only_uuid_changed=True,all_other_apk_members_unchanged=True,
        zipalign=True,v1_signature=True,v2_signature=True,accepted_registry_changed=False,
        required_resource_version='1.4.109',combat_changes=False,ios_changes=[])
    dump(out/'verification-report.json',result)
    for name in ['swf-report.json','harness-result.json','ffdec-body-check.log','air-validation.json','air-test-receipt.json']:
        shutil.copy2(work/name,out/name)
    guide = """覆盖安装本 APK（沿用输入包的内网地址），返回标题下载至资源 1.4.109。
深渊顶部显示封锁属性与额外 PF 调整，点击“关卡详情”查看可滚动的完整说明。
奖励预览应为：梦境纹章1000、深渊代币100、★4破星结晶2、★4星铁钢2。
优先检查第1、26、27、30层，以及返回重进、切换楼层、关闭详情后继续挑战。
本次不改变塔战斗参数，26/30换层、不出额外雷抗、15层PF-15%及此前修复均保留。
已完成离线与桌面AIR原生API验证，手机布局、触控滚动和实际战斗仍待测试。
"""
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
