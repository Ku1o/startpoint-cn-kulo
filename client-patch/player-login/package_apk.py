"""Verify, package and sign a new candidate; never promote the accepted registry."""
import argparse, importlib.util, json, subprocess, uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
common=module('login_apk_common',HERE.parent/'rush-leaderboard/apk_build_common.py')
checker=module('login_apk_baseline',HERE.parent/'verify_android_baseline.py')
def run(command,*,capture=False):
    proc=subprocess.Popen([str(x) for x in command],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    try:
        raw,_=proc.communicate(timeout=180)
        result=raw.decode('utf8','replace')
        if proc.returncode:raise RuntimeError(result)
        if not capture:print(result.strip(),flush=True)
        return result
    finally:
        if proc.poll() is None:
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
            proc.wait(timeout=15)
common.run=run
def main(args):
    w=args.work.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    report=json.loads((w/'swf-report.json').read_text('utf8'));identity=checker.verify(report['baseline']['variant'])
    assert identity==report['baseline'];swf=w/'player-login.swf'
    assert common.sha256(swf)==report['swf_sha256']
    assert common.sha256(HERE/'src/cn/account/PlayerLogin.as')==report['helper_source_sha256']
    java=Path(r'D:\java\bin\java.exe');ffdec=Path(r'F:\codex\tools\ffdec_26.2.1\ffdec.jar');bt=Path(r'F:\StartPointCN\wf_full_patch\build-tools')
    classes=w/'java';classes.mkdir(exist_ok=True)
    run([java.with_name('javac.exe'),'-cp',ffdec,'-d',classes,HERE/'CompareLoginBodies.java'])
    expected=','.join(str(report['main_abc_index'])+':'+str(r['body']) for r in report['changes'])
    run([java,'-Xmx2g','-cp',str(classes)+';'+str(ffdec),'CompareLoginBodies',w/'accepted.swf',swf,expected,report['helper_bodies'],report['main_abc_index'],report['original_game_bodies']])
    uid=str(uuid.uuid4());unsigned=w/(uid+'-unsigned.apk');aligned=w/(uid+'-aligned.apk')
    apk=out/args.name;assert not apk.exists(),'new candidate path required'
    common.replace_apk(Path(identity['apk']),swf,unsigned,uid,base_uuid=identity['uniqueappversionid'])
    run([bt/'zipalign.exe','-p','4',unsigned,aligned])
    run(['powershell.exe','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1',
         '-InputApk',aligned,'-OutputApk',apk,'-ApkSigner',bt/'lib/apksigner.jar','-Java',java])
    verified=common.verify(Path(identity['apk']),apk,swf,uid,java,bt/'lib/apksigner.jar',base_uuid=identity['uniqueappversionid'])
    run([bt/'zipalign.exe','-c','-p','4',apk])
    verified.update(status='offline_verified_login_candidate',apk=str(apk),baseline=identity,endpoint=report['endpoint'],
        original_game_bodies_checked=report['original_game_bodies'],main_abc_index=report['main_abc_index']+1,changes=report['changes'],helper_bodies=report['helper_bodies'],
        zipalign=True,v1_signature=True,v2_signature=True,other_apk_members_unchanged=True,air_runtime_unchanged=True,
        android_device_tested=False,accepted_registry_changed=False)
    (out/(apk.stem+'-verification.json')).write_text(json.dumps(verified,ensure_ascii=False,indent=2)+'\n','utf8')
    (out/(apk.stem+'.sha256')).write_text(verified['apk_sha256']+'  '+apk.name+'\n','utf8')
    for p in [unsigned,aligned]:
        assert p.resolve().parent==w;p.unlink()
    print(json.dumps({'apk':str(apk),'sha256':verified['apk_sha256']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--name',default='StarPoint-CN-1.8.1-player-login-lan-test-r1.apk');main(p.parse_args())
