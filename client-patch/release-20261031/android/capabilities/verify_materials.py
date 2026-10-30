"""Execute R11 native material paths on archived object fixtures, no old main."""
from pathlib import Path
import ast,functools,itertools,json
import port_capabilities as p
from verify_guard_board import definitions,require

def main():
    receipt=json.loads((p.ROOT/'build/partial-report.json').read_text('utf-8'))
    final=Path(receipt['latest_partial_swf']);after=p.SwfAbc(final).abc;before=p.SwfAbc(p.BASE).abc
    guard=definitions(p.REFERENCES/'193-perfect-guard-wfx43/source/verify.py')
    VM=guard['VM'];GuardWorld=guard['GuardWorld'];fallback=VM._lookup
    def lookup(obj,key):
        name=str(key).split('::')[-1]
        if isinstance(obj,list):
            if name=='sort':return lambda cmp:obj.sort(key=functools.cmp_to_key(cmp))
            if name=='indexOf':return lambda value:obj.index(value) if value in obj else -1
            if name=='join':return lambda delim:delim.join(map(str,obj))
        return fallback(obj,key)
    VM._lookup=lookup
    class Harness(GuardWorld):
        def __init__(self,abc,table=None,loaded=True):
            super().__init__(abc,table,loaded)
            self.lex.pop('Math',None)
            self.lex['CustomAbilityStringTable']=VM.Cls('CustomAbilityStringTable')
            self.asset={'getMasterTableMaybe':self.cas}
            for label in ['GeneralCharacterLogic/get_maxOverLimitStep','GeneralCharacterLogic/wfxOverlimitFull',
                          'OwnedCharacterLogic/getRestOverLimitStep','OwnedCharacterLogic/isMaxOverLimitStep',
                          'OwnedOverLimitLogic/getOwnAwakingCrystalToOverLimit','OwnedOverLimitLogic/getAwakingCrystalToOverLimit']:
                if label not in self.labels:continue
                for op in p.asm.decode(abc.bodies[self.labels[label]][5]):
                    if op.name=='getlex':
                        name=abc.mn_name(op.args[0]);short=name.split('::')[-1]
                        if short not in self.lex and short not in VM.GLOBALS:self.lex[short]=VM.Cls(short)
        def cas(self,_cls):
            if not self.loaded:return None
            return {'_type':'CustomAbilityStringTable','get_data':lambda:{
                'exists':lambda key:key in self.table,'get':lambda key:{'string':self.table[key]}}}
    source=p.REFERENCES/'136-overlimit-full-and-window-guard/source/materials/runtime.py'
    tree=ast.parse(source.read_text('utf-8-sig'))
    tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
    env={'Harness':Harness,'VM':VM,'EXT':10000320,'CORE':10000302,'RETAIL':10003}
    exec(compile(tree,str(source),'exec'),env)
    def snapshot(abc,**params):
        e,c,l,w,d,items,events=env['world'](abc,**params)
        crystals=[v for k,v in items.items() if k!=10000302]
        return {'candidates':l['getAwakingCrystalToOverLimit'](),
            'own':[x['id'] for x in l['getOwnAwakingCrystalToOverLimit'](crystals)],
            'state':l['getOverLimitState'](crystals),'window_state':w['getOverLimitState'](),
            'counts':{iid:c['getPossibleOverLimitCountByItem'](w['player'],iid) for iid in [10003,10000320]}},(e,c,l,w,items)
    counts={'no_key_comparisons':0,'full_mode_cases':0,'assertions':0};examples=[]
    def check(ok,detail):
        require(ok,str(detail));counts['assertions']+=1
    for step,crystals,cores,stack in itertools.product(range(9),(0,2),(0,1),(0,3)):
        args=dict(step=step,crystals=crystals,cores=cores,stack=stack)
        old,_=snapshot(before,**args);new,_=snapshot(after,**args)
        check(old==new,('no-key parity',args,old,new));counts['no_key_comparisons']+=1
        full,world=snapshot(after,key='1',**args)
        rest=(4 if step<4 else 8)-step
        check(full['candidates']==[10000320],('new material candidates',args,full))
        check(full['own']==([10000320] if crystals else []),('owned materials',args,full))
        check(full['state']['state']!='stack',('full key must not use duplicate',args,full))
        check(full['counts'][10000320]==min(crystals,cores,rest),('quantity gates',args,full))
        check(full['window_state']['state']==('impossible' if step==8 or not crystals or not cores else 'item'),('confirmation',args,full))
        counts['full_mode_cases']+=1
    # Original formal-server compatibility: absent extended master rows may
    # display retail candidates, but full mode cannot use those owned crystals.
    full,(e,c,l,w,items)=snapshot(after,key='1',step=0,crystals=2,cores=1,stack=3)
    old_table=l['get_itemTable']()
    kept=[iid for iid in old_table['keys']() if iid not in (10000320,10000302)]
    l['get_itemTable']=lambda:{'keys':lambda:kept,'get':old_table['get']}
    owned=[v for iid,v in items.items() if iid not in (10000320,10000302)]
    candidates=l['getAwakingCrystalToOverLimit']();own=l['getOwnAwakingCrystalToOverLimit'](owned)
    state=l['getOverLimitState'](owned)
    check(candidates==[10003],('missing master display fallback',candidates))
    check(own==[] and state['state']=='impossible',('missing master confirms disabled',own,state))
    result={'passed':True,'input':str(final),'sha256':p.digest(final.read_bytes()),'counts':counts,
            'missing_extended_master':{'display_candidates':candidates,'owned_candidates':own,'state':state},
            'coverage':'actual native candidates/owned/state/item-count/window-state bodies and new full helper',
            'air_tested':False,'ui_run_and_pedestal_behavior_tested':False}
    (p.ROOT/'build/materials-interpreter.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
