"""Offline verification and fixed-identity packaging; never launches desktop AIR."""
import argparse,json,re,subprocess,uuid,zipfile
from pathlib import Path
import build_swf as b
HERE=Path(__file__).resolve().parent
JAVA=Path('D:/java/bin/java.exe')
FFDEC=Path('F:/codex/tools/ffdec_26.2.1/ffdec.jar')
BT=Path('F:/StartPointCN/wf_full_patch/build-tools')

def run(command,log=None,*,capture=False):
    proc=subprocess.Popen(list(map(str,command)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    try:
        raw,_=proc.communicate(timeout=180)
        text=raw.decode('utf8','replace')
        if log:log.write_text(text,'utf8')
        assert proc.returncode==0,('command failed',str(log),text[-1500:])
        return text
    finally:
        if proc.poll() is None:
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
            proc.wait(timeout=15)

def package(work,out):
    report=json.loads((work/'swf-report.json').read_text('utf8'));swf=Path(report['output']);base=Path(report['input_apk'])
    assert b.sha(base.read_bytes())==b.BASE_APK_SHA and b.sha(swf.read_bytes())==report['output_swf_sha256']
    assert report['all_other_methods_and_tags_preserved'] and not report['desktop_air_run']
    classes=work/'java';classes.mkdir(exist_ok=True)
    run([JAVA.with_name('javac.exe'),'-cp',FFDEC,'-d',classes,HERE/'CompareLens0910Bodies.java'],work/'javac.log')
    expected='286:56844,286:58882,286:59846,286:92450'
    output=run([JAVA,'-Xmx2g','-cp',str(classes)+';'+str(FFDEC),'CompareLens0910Bodies',work/'baseline.swf',swf,expected],work/'ffdec-bodies.log')
    assert 'PASS bodies=96422' in output
    names=[m['label'].split('/')[0].replace('::','.') for m in report['methods']]
    run([JAVA,'-Xmx2g','-jar',FFDEC,'-selectclass',','.join(names),'-export','script',work/'readback',swf],work/'ffdec-readback.log')
    texts={name:(work/'readback/scripts'/Path(name.replace('.','/')+'.as')).read_text('utf8') for name in names}
    for name,text in texts.items():
        assert text.rstrip().endswith('}') and 'Decompilation error' not in text,name
    sun=texts[names[0]].split('function getOneSideTotalAbilityDamageResistance(',1)[1].split('public function ',1)[0]
    assert '1499901' in sun and '15000' in sun and '3' in sun
    assert all(n in texts[names[2]] for n in b.SLOTS)
    assert 'white_tiger_summer' in texts[names[1]]
    preload=texts[names[3]]
    for path in ['character/white_tiger_summer/voice/battle/skill_ready_alt_1','character/white_tiger_summer/voice/battle/matched_skill_ready_alt_1',*['character/unicorn_lancer_rose/voice/battle/skill_ready_alt_'+str(i) for i in range(1,4)]]:
        assert path in preload,path
    common=b.module('lens0910_apk_common',HERE.parent/'rush-leaderboard/apk_build_common.py');common.run=run
    assert not out.exists(),'delivery output must be new'
    out.mkdir(parents=True)
    new_uuid=str(uuid.uuid4());assert new_uuid!=b.BASE_UUID
    unsigned=work/'unsigned.apk';aligned=work/'aligned.apk';assert not unsigned.exists() and not aligned.exists()
    final=out/'StarPoint-CN-1.8.1-lens0910-abyss-details-lan-test.apk'
    common.replace_apk(base,swf,unsigned,new_uuid,base_uuid=b.BASE_UUID)
    run([BT/'zipalign.exe','-p','4',unsigned,aligned],work/'zipalign-build.log')
    run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',HERE.parent/'lens0907-0908/sign_apk.ps1','-InputApk',aligned,'-OutputApk',final,'-ApkSigner',BT/'lib/apksigner.jar','-Java',JAVA],work/'signing.log')
    result=common.verify(base,final,swf,new_uuid,JAVA,BT/'lib/apksigner.jar',base_uuid=b.BASE_UUID)
    run([BT/'zipalign.exe','-c','-p','4',final],work/'zipalign-final.log')
    result.update(status='offline_verified_device_pending',apk=str(final),base_apk=str(base),base_apk_sha256=b.BASE_APK_SHA,base_swf_sha256=b.BASE_SWF_SHA,required_resource_version='1.4.112',original_bodies_checked=96422,changed_bodies=expected.split(','),added_slots=b.SLOTS,desktop_air_run=False,android_device_tested=False,all_other_apk_members_unchanged=True,manifest_only_uuid_changed=True,v1_signature=True,v2_signature=True,zipalign=True,accepted_registry_changed=False,ios_client_changed=False)
    b.savej(out/'verification-report.json',result);b.savej(out/'swf-report.json',report)
    (out/'SHA256.txt').write_text(result['apk_sha256']+'  '+final.name+'\n','utf8')
    for path in [unsigned,aligned]:assert path.resolve().parent==work.resolve();path.unlink()
    print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();package(a.work.resolve(),a.out.resolve())
