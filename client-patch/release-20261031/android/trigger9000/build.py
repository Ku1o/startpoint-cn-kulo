"""Selective cumulative-HP-loss delta. Run only in the task bounded Job slot."""
from pathlib import Path
import copy,json,sys
HERE=Path(__file__).resolve().parent;CLIENT=HERE.parent
import bootstrap
from input_config import input_path,input_sha,work_path,capability_module
p=capability_module()

SOURCE=input_path('tutorial_swf')
SOURCE_SHA='215860d0f3933b352c377309c68943a3978a80ab5c5beb209c9b94382191e325'
PARSERS=['LeaderAbilityValues$/parseAt25','AbilityValues$/parseAt27']
GAUGES=['HealthPointGaugeImpl/'+n for n in ['subtract','setRatio','setMaxHealthPoint','set','changeMaxHp','addMaxStatModifier','add']]
HOOKS=PARSERS+['InstantAbilityTriggerMasterValueTools$/resolve','InstantAbilityDescriptionGenerator/stringfyInstantTriggerBattle']+GAUGES
HELPERS=['InstantAbilityTriggerMasterValueTools$/wfxResolveHpLoss','InstantAbility/wfxAccumulateHpLoss',
         'HealthPointGaugeImpl/wfxObserveHpLoss','InstantAbilityDescriptionGenerator$/wfxHpLossTriggerDescription']
LABELS=HOOKS+HELPERS
LEDGER=('pinball.scene.battle.battle.ability::InstantAbility','wfxHpLossLedger',True)

def bounded_proof(module):
    """Use exact known insertion spans, avoiding quadratic sequence matching."""
    original=module.insertion_proof
    count=0
    def prove(left,right,spans=None):
        nonlocal count
        label=HOOKS[count];count+=1
        if spans is None:
            a,b=left[0],right[0];difference=len(b)-len(a)
            if label not in GAUGES:
                expected=34 if label in PARSERS else 9 if label.endswith('$/resolve') else 17
                assert difference==expected,'unexpected parser/resolver/description prefix'
                spans=[{'at':0,'instructions':difference}]
            else:
                returns=[i for i,row in enumerate(a) if row[0]==0x47]
                assert difference==3+3*len(returns),'unexpected HP hook insertion shape'
                spans=[{'at':0,'instructions':3}]+[{'at':i,'instructions':3} for i in returns]
        try:return original(left,right,spans)
        except AssertionError:
            print(json.dumps({'failedPreservationLabel':label,'beforeInstructions':len(left[0]),'afterInstructions':len(right[0]),'spans':spans}))
            if len(spans)==1 and spans[0]['at']==0:
                tail=right[0][spans[0]['instructions']:]
                for i,(x,y) in enumerate(zip(left[0],tail)):
                    if p.framework.FMT is not None and module.freeze(x[:2])!=module.freeze(y[:2]):
                        print(json.dumps({'firstOperandMismatch':i,'before':x[:2],'donor':y[:2]}));break
            raise
    return prove

def main():
    assert p.digest(SOURCE.read_bytes())==SOURCE_SHA
    out=work_path('trigger9000/build01');assert not out.exists(),'fresh output required'
    e=p.R11Editor(SOURCE);before=copy.deepcopy(e.abc);before_raw=before.serialize()
    old_count=len(before.bodies);old_methods=len(before.methods)
    old_load=p.load
    def load(name,path):
        mod=old_load(name,path)
        if name=='capability_named_importer':mod.insertion_proof=bounded_proof(mod)
        return mod
    p.load=load
    try:adopted=p.graft_donor(e,LABELS,[LEDGER],HOOKS)
    finally:p.load=old_load
    assert len(e.abc.methods)==old_methods+4 and len(e.abc.bodies)==old_count+4
    assert e.abc.methods[:old_methods]==before.methods,'existing MethodInfo changed'
    changed={p.bodies.resolve(e.abc,label) for label in HOOKS}
    assert len(changed)==11 and len(e.new_methods)==4 and len(e.added_state)==1
    for i,b in enumerate(before.bodies):
        if i not in changed:assert p.body_bytes(e.abc.bodies[i])==p.body_bytes(b)
    for i,instance in enumerate(before.instances):
        assert e.abc.instances[i][:6]==instance[:6]
        added=e.abc.instances[i][6][len(instance[6]):]
        assert all(t.data[0]=='method' for t in added),'no new old-class instance fields'
        assert p.framework.FMT is not None
    # Reverse exactly the allowed bodies, appended methods/traits and pool suffix.
    reverse=copy.deepcopy(e.abc)
    reverse.bodies=reverse.bodies[:old_count]
    for i in changed:reverse.bodies[i]=copy.deepcopy(before.bodies[i])
    reverse.methods=reverse.methods[:old_methods]
    for i,row in enumerate(before.instances):reverse.instances[i][6]=reverse.instances[i][6][:len(row[6])]
    for i,row in enumerate(before.classes):reverse.classes[i][1]=reverse.classes[i][1][:len(row[1])]
    for name in ('strings','ints','uints','doubles','namespaces','ns_sets','multinames'):
        setattr(reverse,name,getattr(reverse,name)[:len(getattr(before,name))])
    assert reverse.serialize()==before_raw,'unexpected cumulative ABC change'
    out.mkdir(parents=True);target=out/'production1031-trigger9000-r1.swf';target.write_bytes(p.compose(e))
    reread=p.SwfAbc(target)
    assert reread.abc.serialize()==e.abc.serialize()
    envelope=p.envelope(e.swf,reread,{'boot_ffc6'})
    report={'status':'static_candidate_pending_targeted_AIR_and_device','input':str(SOURCE),
        'inputSha256':SOURCE_SHA,'output':str(target),'outputSha256':p.digest(target.read_bytes()),
        'donor':adopted,'changedMethods':e.report,'newMethods':e.new_methods,'staticState':e.added_state,
        'existingMethodsChanged':11,'methodsAdded':4,'staticSlotsAdded':1,'instanceFieldsAdded':0,
        'originalMethodInfoRecordsExact':True,'allOldNativeInstructionsAndReachableEdgesPreserved':True,
        'unreachableEdgeBoundary':'Inherited insertion proof allows an old branch normalization only when both old and new nodes are unreachable; all live branches, switches and exception relationships are preserved.',
        'unrelatedBodiesAndOldPoolTraitPrefixesExact':True,'reverseDeltaRestoresExactInputAbc':True,
        'envelope':envelope,'totalMethods':len(e.abc.methods),'excludedOtherParserFamilies':['AbilitySoulValues','EquipmentEnhancementAbilityValues','ExAbilityValues'],
        'admissionAndBundleUnchanged':True,'tutorialF1069HelperUnchanged':True,'deviceTested':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps({k:report[k] for k in ('status','output','outputSha256','existingMethodsChanged','methodsAdded','staticSlotsAdded','instanceFieldsAdded')}))
if __name__=='__main__':main()
