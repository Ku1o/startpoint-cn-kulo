"""Retire legacy damage hooks after the pinned cumulative author port.

The three visual call sites survive through a dedicated helper class. Removing
each legacy block must reproduce the prior bytecode when the block is reinserted.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse, copy, hashlib, importlib.util, json, struct, subprocess, sys, zlib

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'author-content-1043'))
author_spec=importlib.util.spec_from_file_location('unified_author_port',HERE.parent/'author-content-1043/build_swf.py')
author=importlib.util.module_from_spec(author_spec);author_spec.loader.exec_module(author)
from core import asm, bodies
spec=importlib.util.spec_from_file_location('unified_tools',HERE.parent/'startup-cache/build_swf.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
EXPECTED='fce5aabaea98ffa84381de91e936a5adfd5991e955ed0c62fb804b7551c5a10c'
SDK=Path('F:/codex/ios-rush-leaderboard-port-20260830/AIRSDK_51.2.1.5')
sha=lambda b:hashlib.sha256(b).hexdigest()

def strip(source,output,work):
    assert sha(source.read_bytes())==EXPECTED,'unknown author port'
    assert not output.exists()
    work.mkdir(parents=True,exist_ok=True)
    swc=work/'inaho-visuals.swc'
    command=['D:/java/bin/java.exe','-Dflexlib='+str(SDK/'frameworks'),'-Xmx512m','-jar',str(SDK/'lib/compc-cli.jar'),
             '+configname=air','-swf-version=44','-target-player=32.0','-debug=false',
             '-compiler.source-path='+str(HERE/'src'),'-include-classes=cn.mod.InahoAbilityVisuals','-output='+str(swc)]
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    try:
        log,_=process.communicate(timeout=120)
        (work/'compile-visuals.log').write_bytes(log)
        if process.returncode:raise RuntimeError(log.decode('utf8','replace'))
    finally:
        if process.poll() is None:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15)
            process.wait(timeout=15)
    version,header,tags=s.parts(source)
    main=next(t for t in tags if t[0]==82 and t[2][4:-1]==b'boot_ffc6')
    legacy=next(t for t in tags if t[0]==82 and t[2][4:-1]==b'cn.mod.GenericDamage')
    a=main[3];before=copy.deepcopy(a);changes=[]
    helper,=[i for i in range(1,len(a.multinames)) if a.mn_name(i)=='cn.mod::GenericDamage']
    for name,offset,count,member in [
        ('MemberImpl/applyInstantAbility',-1,6,'decorate'),
        ('ActionEvaluator/addImpactToSubject',0,4,'source'),
        ('NormalAttackCalculator/calculate',-1,6,'result')]:
        bi=bodies.resolve(a,name);body=a.bodies[bi];old=bytes(body[5]);code=asm.decode(old)
        at,=[i for i,x in enumerate(code) if x.name=='getlex' and x.args==[helper]]
        at+=offset;block=copy.deepcopy(code[at:at+count])
        assert block[-1].name in ('callproperty','callpropvoid') and a.mn_name(block[-1].args[0])==member
        assert not body[6] and all(x.target is None for x in block)
        if offset==-1:assert block[0].name=='setlocal' and block[2].name=='getlocal' and block[0].args==block[2].args
        body[5]=asm.unsplice(old,at,count)
        restored=asm.splice(body,at,block,asm.ENTER)[0]
        assert restored==old,'non-reversible removal: '+name
        s.m.check_body(body,a)
        changes.append({'method':name,'body':bi,'removed_call':member,'start':at,'instructions':count,'before':sha(old),'after':sha(body[5]),'reversible':True})
    visual=[]
    view=s.m.View(SimpleNamespace(abc=a),asm)
    for bi,body in enumerate(a.bodies):
        for x in asm.decode(body[5]):
            if x.name=='getlex' and x.args==[helper]:visual.append(bi)
    expected_visual=[bodies.resolve(a,n) for n in ['InstantAbilitySource/resolvePathCollection','AbilityDamageShot/getEffect','AbilityDamageShot/finish']]
    assert sorted(visual)==sorted(expected_visual),visual
    string_index=a.multinames[helper][2]
    assert a.strings[string_index]==b'GenericDamage'
    assert sum(m[0] in (7,13) and m[2]==string_index for m in a.multinames[1:])==1
    a.strings[string_index]=b'InahoAbilityVisuals'
    changed={x['body'] for x in changes}
    assert {i for i,(x,y) in enumerate(zip(before.bodies,a.bodies)) if s.m.freeze(x)!=s.m.freeze(y)}==changed
    for field in ('methods','instances','classes','scripts','metadata','ints','uints','doubles','namespaces','ns_sets','multinames'):
        assert s.m.freeze(getattr(a,field))==s.m.freeze(getattr(before,field)),field
    def tag(prefix,abc):
        data=prefix+abc;return struct.pack('<HI',(82<<6)|63,len(data))+data
    main[1]=tag(main[2],s.serialize(a,main[4]))
    extra=s.helper_abc(swc)
    assert len(extra.instances)==1 and extra.mn_name(extra.instances[0][0])=='cn.mod::InahoAbilityVisuals'
    for body in extra.bodies:s.m.check_body(body,extra)
    legacy[1]=tag(struct.pack('<I',1)+b'cn.mod.InahoAbilityVisuals\0',extra.serialize())
    raw=header+b''.join(t[1] for t in tags)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(b'CWS'+bytes([version])+struct.pack('<I',len(raw)+8)+zlib.compress(raw))
    _,_,back=s.parts(output)
    assert len(back)==len(tags) and all(x[1]==y[1] for x,y in zip(back,tags))
    assert b'GenericDamage' not in raw and b'spGenericDamage' not in raw and b'battle/cnmod/generic_damage/v1/' not in raw
    report={'status':'offline_candidate','input_sha256':EXPECTED,'output_sha256':sha(output.read_bytes()),'removed_hooks':changes,
            'visual_call_bodies':visual,'visual_helper_methods':len(extra.bodies),'unchanged_main_bodies':len(a.bodies)-3,
            'other_abc_tags_unchanged':True,'native_629_preserved':True,'author_rules_preserved':True,
            'implicit_leader_reassignment_removed':True,'implicit_ability_activation_removed':True,'save_schema_changed':False,'device_tested':False}
    output.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--accepted',type=Path);p.add_argument('--donor',type=Path);args=p.parse_args()
    if args.accepted:
        assert args.donor and not args.source.exists()
        author.build(args.accepted,args.donor,args.source)
    strip(args.source,args.output,args.work)
