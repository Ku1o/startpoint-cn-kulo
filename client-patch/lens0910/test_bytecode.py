"""Exercise actual transplanted AVM2 blocks with test doubles, without AIR.

This checks routing/arithmetic branches, not Android rendering or combat.
"""
import argparse,copy,itertools,json
from pathlib import Path
from types import SimpleNamespace as O
import build_swf as b

def chunk(v,index,start,end):
    ins=b.g.asm.decode(v.a.bodies[index][5])[start:end]
    for x in ins:
        if x.target is not None:assert start<=x.target<=end;x.target-=start
    return ins
def execute(ins,a,regs):
    stack=[];pc=0;steps=0
    def name(i):return a.mn_name(i).split('::')[-1]
    while pc<len(ins):
        x=ins[pc];op,args,target=x.name,x.args,x.target;pc+=1;steps+=1;assert steps<1000
        if op.startswith('getlocal_'):stack.append(regs[int(op[-1])])
        elif op=='getlocal':stack.append(regs[args[0]])
        elif op.startswith('setlocal_'):regs[int(op[-1])]=stack.pop()
        elif op=='setlocal':regs[args[0]]=stack.pop()
        elif op=='getproperty':
            if a.multinames[args[0]][0] in (27,28):key=stack.pop();stack.append(stack.pop()[key])
            else:stack.append(getattr(stack.pop(),name(args[0])))
        elif op=='setproperty':value=stack.pop();setattr(stack.pop(),name(args[0]),value)
        elif op=='pushint':stack.append(a.ints[args[0]])
        elif op=='pushstring':stack.append(a.s(args[0]))
        elif op=='pushbyte':stack.append(args[0])
        elif op=='pushnull':stack.append(None)
        elif op=='getlex':stack.append(O(Some=lambda path:O(index=0,params=[path]),Unique=lambda i:('Unique',i)))
        elif op in ('callproperty','callpropvoid'):
            values=[stack.pop() for _ in range(args[1])][::-1];value=getattr(stack.pop(),name(args[0]))(*values)
            if op=='callproperty':stack.append(value)
        elif op in ('coerce','coerce_a'):pass
        elif op in ('convert_b','convert_i','convert_d'):stack.append({'convert_b':bool,'convert_i':int,'convert_d':float}[op](stack.pop()))
        elif op in ('add','multiply','subtract'):
            y,x=stack.pop(),stack.pop();stack.append(x+y if op=='add' else x*y if op=='multiply' else x-y)
        elif op=='jump':pc=target
        elif op in ('ifeq','ifne','ifle'):
            y,x=stack.pop(),stack.pop()
            if {'ifeq':x==y,'ifne':x!=y,'ifle':x<=y if isinstance(x,(int,float)) else False}[op]:pc=target
        elif op in ('iftrue','iffalse'):
            if bool(stack.pop())==(op=='iftrue'):pc=target
        else:raise AssertionError(op)
    assert not stack

def verify(work):
    report=json.loads((work/'swf-report.json').read_text('utf8'));v=b.g.View(b.g.SwfAbc(Path(report['output'])),b.g.asm)
    assert b.sha(Path(report['output']).read_bytes())==report['output_swf_sha256']
    sun=chunk(v,56844,241,274);skill=chunk(v,59846,111,126)
    phase=chunk(v,58882,64,78);ready=chunk(v,58882,89,254);preload=chunk(v,92450,112,160)
    cases=0
    for owner,hostile,invisible,count,total in itertools.product(range(3),(False,True),(False,True),(-2,0,1,2,3,4,100),(-90000,0,40000)):
        called=[]
        def get_count(key):assert key==('Unique',1499901);called.append(key);return count
        regs={0:O(owner=O(index=owner),get_isInvisibleSlot=lambda:invisible,getConditionAccumulationCount=get_count),1:hostile,3:total}
        execute(sun,v.a,regs);eligible=owner==2 and not hostile and not invisible
        assert regs[3]==total-(min(3,max(0,count))*15000 if eligible else 0)
        assert bool(called)==eligible;cases+=1
    for code,fever,gameplay in itertools.product(('white_tiger_summer','seris_dragon_king','unicorn_lancer_rose'),(False,True),(False,True)):
        c=O(mainCharacterStringId=code,skillVoicePaths=['n0','n1'],switchedSkillVoicePaths=['f0','f1'])
        native=c.switchedSkillVoicePaths if gameplay else c.skillVoicePaths
        regs={0:O(zoneManager=O(isFeverMode=lambda:fever)),3:c,6:gameplay,8:native}
        execute(skill,v.a,regs);assert regs[6]==gameplay
        assert regs[8]==((c.switchedSkillVoicePaths if fever else c.skillVoicePaths) if code=='white_tiger_summer' else native);cases+=1
    base='character/unicorn_lancer_rose/voice/battle/skill_ready';paths=[base,*[base+'_alt_'+str(i) for i in range(1,4)]]
    for mask,counter,matched,missing in itertools.product(range(16),range(4),(False,True),(False,True)):
        present={p for i,p in enumerate(paths) if mask&(1<<i)}
        c=O(mainCharacterStringId='unicorn_lancer_rose',logic=O(logicAssets=O(existsVoiceFileReader=lambda p:p in present)))
        hud=O(character=c,geraldReadyNext=counter,wtsReadyNormalNext=1,wtsReadyFeverNext=0)
        native=O(index=1,params=None) if missing else O(index=0,params=['native'])
        regs={0:hud,3:matched,4:native};execute(phase,v.a,regs);execute(ready,v.a,regs)
        if base in present:assert regs[4].params==[paths[counter] if paths[counter] in present else base] and hud.geraldReadyNext==(counter+1)%4
        else:assert regs[4] is native and hud.geraldReadyNext==counter
        assert regs[3]==matched and (hud.wtsReadyNormalNext,hud.wtsReadyFeverNext)==(1,0);cases+=1
    normal='character/white_tiger_summer/voice/battle/skill_ready';fp='character/white_tiger_summer/voice/battle/matched_skill_ready'
    assets={normal+'_alt_1',fp+'_alt_1'};state={'fever':False}
    c=O(mainCharacterStringId='white_tiger_summer',logic=O(logicAssets=O(existsVoiceFileReader=lambda p:p in assets)))
    hud=O(character=c,wtsReadyNormalNext=0,wtsReadyFeverNext=0,geraldReadyNext=3,gear=O(absorb=lambda *args:O(isFeverMode=lambda:state['fever'])))
    observed=[]
    for fever in [False,True,False,False,True,True]:
        state['fever']=fever;regs={0:hud,3:not fever};execute(phase,v.a,regs);assert regs[3]==fever
        regs[4]=O(index=0,params=[fp if fever else normal]);execute(ready,v.a,regs);observed.append(regs[4].params[0]);assert hud.geraldReadyNext==3;cases+=1
    assert observed==[normal,fp,normal+'_alt_1',normal,fp+'_alt_1',fp]
    assets.clear();hud.wtsReadyNormalNext=1;regs={0:hud,3:False,4:O(index=0,params=[normal])};execute(ready,v.a,regs);assert regs[4].params==[normal];cases+=1
    hud.wtsReadyNormalNext=1;regs[4]=O(index=1,params=None);execute(ready,v.a,regs);assert hud.wtsReadyNormalNext==1;cases+=1
    all_paths=[normal+'_alt_1',fp+'_alt_1',*paths[1:]]
    for cid,mask in itertools.product((149990,129992,179999),range(32)):
        present={p for i,p in enumerate(all_paths) if mask&(1<<i)};collected=[]
        regs={1:O(addSoundEffect=collected.append),5:O(characterId=cid,logicAssets=O(existsVoiceFileReader=lambda p:p in present))};execute(preload,v.a,regs)
        wanted=all_paths[:2] if cid==149990 else paths[1:] if cid==129992 else []
        assert collected==[p for p in wanted if p in present];cases+=1
    result=dict(status='passed',cases=cases,swf_sha256=report['output_swf_sha256'],execution='actual_AVM2_blocks_in_small_test_interpreter_with_doubles',desktop_air_run=False,device_tested=False)
    b.savej(work/'bytecode-verification.json',result);print(json.dumps(result))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);a=ap.parse_args();verify(a.work)
