"""Execute final core query/direct and PF4 helper bodies on recording boundaries."""
import json,math
from pathlib import Path
import port_capabilities as p
from verify_guard_board import definitions,require

def main():
    receipt=json.loads((p.ROOT/'build/partial-report.json').read_text('utf-8'))
    path=Path(receipt['latest_partial_swf']);abc=p.SwfAbc(path).abc
    env=definitions(p.REFERENCES/'193-perfect-guard-wfx43/source/verify.py')
    VM=env['VM'];fallback=VM._lookup
    def lookup(obj,key):
        name=str(key).split('::')[-1]
        if isinstance(obj,list) and name=='indexOf':return lambda v:obj.index(v) if v in obj else -1
        if isinstance(obj,str) and name=='charCodeAt':return lambda i:ord(obj[i])
        return fallback(obj,key)
    VM._lookup=lookup
    w=env['GuardWorld'](abc)
    cases=[]
    def check(name,ok):
        require(ok,name);cases.append(name)
    w.lex['MaskGeneral']={'maskBit':0}
    for uid,spec,combo,expected in [
        (240001,'wfx:24:0:10000:0:test',0,2),
        (240002,'wfx:24:1:100:99:test',200,1.99),
        (240003,'wfx:24:1:100:0:test',200,3),
        (240004,'wfx:24:0:-20000:0:test',0,0)]:
        w.table[uid]=spec
        member=w.member(conditions=[w.condition(uid)],aura=False)
        member['comboCalculator']={'getCombo':lambda combo=combo:combo}
        w.bind(member,'MemberImpl',['wfxDirectFactor','wfxDirectTargetUnique'])
        actual=member['wfxDirectFactor'](None)
        check('direct_'+str(uid),abs(actual-expected)<1e-12)
    # Multiple arg1 rows use the smallest positive cap across all combo terms.
    w.table.update({240005:'wfx:24:1:100:99:test',240006:'wfx:24:1:100:50:test'})
    member=w.member(conditions=[w.condition(240005),w.condition(240006)])
    member['comboCalculator']={'getCombo':lambda:200}
    w.bind(member,'MemberImpl',['wfxDirectFactor','wfxDirectTargetUnique'])
    check('smallest_combo_cap_across_rows',abs(member['wfxDirectFactor'](None)-2)<1e-12)
    w.table[250001]='wfx:25:2:0:0:test'
    member=w.member(conditions=[w.condition(250001)])
    w.bind(member,'MemberImpl',['wfxMergeDirect'])
    check('merge_below_threshold',member['wfxMergeDirect'](1) is False)
    check('merge_at_threshold',member['wfxMergeDirect'](2) is True)

    # Real selector and qualification helpers; config/ledger/checker are recorded
    # boundaries. Source-config text parsing/cache has its own distinct scope.
    static_battle={'wfxPf4SourceConfig':lambda battle,asset,packed:[80,0x40A0FF]}
    w.lex['Battle']=static_battle
    checker_on={'getActiveCount':lambda _:1}
    checker_off={'getActiveCount':lambda _:0}
    total={'ledger':[[],[]]}
    total['wfxPfLedger']=lambda:total['ledger']
    w.bind(total,'BattleAbilityTotalizerImpl',['wfxPf4SelectRow'])
    main=[0,'main_pf4',[4],checker_on]
    unison=[1,'unison_pf4',[4],checker_on]
    total['ledger']=[[],[main,unison]]
    check('select_main_origin',total['wfxPf4SelectRow'](4,0,1) is main)
    check('select_unison_origin',total['wfxPf4SelectRow'](4,0,2) is unison)
    check('other_member_origin_not_used',total['wfxPf4SelectRow'](4,1,2) is None)
    total['ledger']=[[],[[0,'inactive',[4],checker_off]]]
    check('inactive_override_not_lv4',total['wfxPf4SelectRow'](4,0,0) is None)
    total['ledger']=[[],[[0,'only_lv3',[1,2,3],checker_on]]]
    check('lv3_override_not_lv4',total['wfxPf4SelectRow'](4,0,0) is None)
    battle={'abilityTotalizer':total}
    member={'battle':battle,'originMemberIndex':0,'logicAssets':{},
            'ball':{'_type':'BallImpl','kyubiPowerFlipInitialCombo':80},'cfg':[0,10000,10000]}
    member['wfxPfConfig']=lambda:member['cfg']
    w.bind(member,'MemberImpl',['wfxPf4State','wfxPf4ReadyState','wfxPf4Action','wfxPf4ChainId'])
    total['ledger']=[[],[unison]]
    state=member['wfxPf4State']()
    check('main_lv3_and_unison_lv4_state',state==[None,'unison_pf4',80,0x40A0FF])
    check('exact_combo_threshold_qualifies',member['wfxPf4ReadyState'](3)==state)
    member['ball']['kyubiPowerFlipInitialCombo']=79
    check('below_combo_threshold_blocked',member['wfxPf4ReadyState'](3) is None)
    member['ball']['kyubiPowerFlipInitialCombo']=80
    check('physical_non_third_slot_not_lv4',member['wfxPf4ReadyState'](2) is None)
    check('main_action_does_not_borrow_unison',member['wfxPf4Action'](state,False) is None)
    check('unison_action_uses_lv4_override',member['wfxPf4Action'](state,True)=='unison_pf4')
    check('chain_uses_lv4_at_physical_third_slot',member['wfxPf4ChainId']('old',[0,1,2,state],3)=='unison_pf4')
    check('other_slot_preserves_chain_action',member['wfxPf4ChainId']('old',[0,1,2,state],2)=='old')
    member['cfg']=[1,10000,10000]
    check('force_type_pf_excludes_unison_override',member['wfxPf4State']() is None)
    member['cfg']=None
    total['ledger']=[[],[]]
    check('config_text_alone_does_not_unlock_lv4',member['wfxPf4State']() is None)
    # Real packed-origin to character identity helper.
    party={'characters':[{'index':0,'params':[{'id':129989}]}],
           'unison_characters':[{'index':0,'params':[{'id':129999}]}]}
    source_battle={'initialData':{'sources':[{'party':party}]}}
    check('source_id_main',w.run('Battle$/wfxPf4SourceId',static_battle,source_battle,0)==129989)
    check('source_id_unison',w.run('Battle$/wfxPf4SourceId',static_battle,source_battle,1)==129999)
    check('invalid_source_slot',w.run('Battle$/wfxPf4SourceId',static_battle,source_battle,65536)==-1)
    check('invalid_source_kind',w.run('Battle$/wfxPf4SourceId',static_battle,source_battle,2)==-1)
    result={'passed':True,'assertions':len(cases),'cases':cases,'input':str(path),'sha256':p.digest(path.read_bytes()),
        'executed_methods':sorted(w.executed),'air_tested':False,
        'limits':['Ledger, active-checker and source-config outputs are controlled boundaries.',
                  'Not full MemberImpl.startPowerFlip execution, renderer, config cache, GPU or device acceptance.']}
    (p.ROOT/'build/core-pf-interpreter.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'passed':True,'assertions':len(cases),'methods':len(w.executed)},ensure_ascii=False))

if __name__=='__main__':main()
