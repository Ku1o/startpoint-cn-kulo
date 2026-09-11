from prepare import ROOT, LEGACY, run
from pathlib import Path
import sys, re, json, hashlib
sys.path.insert(0,str(LEGACY))
from transplant_abc_method_bodies import extract_method_pcode, extract_script_initializer, extract_only_abc
from stitch_ios_stripped_abc import body_records

targets=[('pinball.scene.playerProfile.PlayerProfileView','refreshFollowRelationButtons',79682,87249),('pinball.scene.playerProfile.profile.otherProfile.OtherProfileLogic','applyButton',79819,87420),('pinball.scene.event.rush.ranking.party.RushEventRankingPartyScene','copyPlayedParty',71659,78115)]

def main():
    pcode_source=Path(__file__).resolve().parent.parent/'pcode'
    java=Path(r'D:\java\bin\java.exe'); ffdec=Path(r'F:\codex\tools\ffdec-26.2.1\app\ffdec-cli.jar')
    current=ROOT/'baseline-full.swf'
    manifest=[]
    for i,(cls,method,body,mid) in enumerate(targets):
        block=(pcode_source/(method+'.pcode')).read_text('utf-8')
        assert not re.search(r'\b(newfunction|callstatic|newclass)\b',block), 'numeric method/class references need explicit platform remapping'
        dst=ROOT/(method+'.pcode'); dst.write_text(block,'utf-8')
        out=ROOT/f'stage-{i+1}.swf'
        log=run(java,'-Xmx4g','-jar',ffdec,'-air','-onerror','abort','-replace',current,out,cls,dst,body)
        (ROOT/f'import-{i+1}.log').write_text(log,'utf-8')
        current=out
        manifest.append(dict(class_name=cls,method=method,ios_body_index=body,ios_aot_id=mid,pcode_sha256=hashlib.sha256(block.encode()).hexdigest()))
    # AIR only emits methods of classes reachable through script newclass.
    # Restore these original lifecycle bodies for compilation only. The IPA
    # retains their accepted native entries and original stripped metadata.
    lifecycle_ids=[]
    baseline_records=body_records((ROOT/'baseline-full.abc').read_bytes())[2]
    for i,(cls,class_index,body) in enumerate([(targets[0][0],8254,79694),(targets[1][0],8261,79821)]):
        block=(pcode_source/f'lifecycle-{i+1}.pcode').read_text('utf-8')
        assert re.search(rf'newclass\s+{class_index}\b',block)
        dst=ROOT/f'lifecycle-{i+1}.pcode';dst.write_text(block,'utf-8')
        out=ROOT/f'stage-lifecycle-{i+1}.swf'
        log=run(java,'-Xmx4g','-jar',ffdec,'-air','-onerror','abort','-replace',current,out,cls,dst,body)
        (ROOT/f'lifecycle-{i+1}.log').write_text(log,'utf-8')
        current=out
        lifecycle_ids.append(baseline_records[body][0])
    (ROOT/'modified.abc').write_bytes(extract_only_abc(current))
    print(run(sys.executable, LEGACY/'restore_ios_method_infos.py',ROOT/'baseline-full.abc',ROOT/'modified.abc',ROOT/'profile-full.abc'))
    assert hashlib.sha256((ROOT/'profile-full.abc').read_bytes()).hexdigest() == 'b374e739c7da1541182f0608f6f52c2e597efafc5133f2ecad97da819f842c4c', 'compiled input no longer matches this recorded patch'
    old=body_records((ROOT/'baseline-full.abc').read_bytes())[2]
    new=body_records((ROOT/'profile-full.abc').read_bytes())[2]
    changed=[a[0] for a,b in zip(old,new) if a!=b]
    assert changed==sorted([78115,87249,87420]+lifecycle_ids), changed
    (ROOT/'methods.json').write_text(json.dumps(manifest,indent=2)+'\n','utf-8')
    compile_dir=ROOT/'compile';compile_dir.mkdir(exist_ok=True)
    (compile_dir/'profile-follow.abc').write_bytes((ROOT/'profile-full.abc').read_bytes())
    run(sys.executable,LEGACY/'wrap_abc_swf.py',ROOT/'profile-full.abc',ROOT/'profile-full.swf')
    log=run(java,'-Xmx4g','-jar',ffdec,'-onerror','abort','-format','script:pcode','-selectclass',','.join(t[0] for t in targets),'-export','script',ROOT/'final-pcode',ROOT/'profile-full.swf')
    (ROOT/'final-export.log').write_text(log,'utf-8')
    print('Changed AOT bodies:',changed)

if __name__=='__main__': main()
