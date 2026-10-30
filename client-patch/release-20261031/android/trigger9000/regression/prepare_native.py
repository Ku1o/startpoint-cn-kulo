"""Current83fc native HP/counter fixture. Execute only in its exclusive bounded Job."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
import bootstrap
from input_config import input_path,input_sha,runtime,repo_path,work_path,tool_root
import abc_tools as a
from fixture_utils import write_sources

AFTER=input_path('final_swf')
SHA='83fc92d70d7457bb5e4b58d25d97663eeb80367ee366a947f4779a12075ff172'
DONOR_SHA='2fa334cca6b104bdcae061c5ed9bc63eb52d59db7e687c90d24742e61759e7b4'
def main():
 p=argparse.ArgumentParser();p.add_argument('--attempt',required=True);p.add_argument('--lifecycle',action='store_true');op=p.parse_args();work=(work_path('trigger9000')/op.attempt).resolve()
 if work.parent!=work_path('trigger9000') or work.exists():raise ValueError('fresh direct owned attempt required')
 cfg=runtime()
 a.configure({**cfg,'repo':str(repo_path()),'swf':str(AFTER),'swf_sha256':SHA,'tool_root':str(tool_root()),'run_root':str(work_path('trigger9000'))})
 b,abc,v,identity=a.load_current(('pinball.master.generated::LeaderAbilityValues',))
 donor=input_path('donor_swf')
 if a.sha(donor.read_bytes())!=DONOR_SHA:raise ValueError('fixed donor reference changed')
 rows={abc.mn_name(r[0]):(i,r) for i,r in enumerate(abc.instances)}
 def owner(short):
  found=[q for q in rows if q.rsplit('::',1)[-1]==short];assert len(found)==1,(short,found);return found[0]
 standard=owner('StandardPrecontentMagnification')
 groups={
 'pinball.master.generated::LeaderAbilityValues':['$parseAt25','$parseAt26','$parseAt27','$parseAt28','$parseAt32','$parseAt33'],
 'pinball.master.generated::AbilityValues':['$parseAt27','$parseAt28','$parseAt29','$parseAt30','$parseAt34','$parseAt35'],
 'pinball.common.data.ability.instant::InstantAbilityTriggerMasterValue':['<ctor>','$HpLow'],
 'pinball.common.data.ability.instant::InstantAbilityTriggerPullerMasterValue':['<ctor>','$OneOfParty'],
 'pinball.common.data.ability.instant::InstantBattleAbilityTriggerKind':['<ctor>','$Count'],
 'pinball.common.data.ability.instant::InstantAbilityTriggerKind':['<ctor>','$Battle'],
 'pinball.common.data.ability.instant::InstantAbilityTriggerMasterValueTools':['$resolve','$wfxResolveHpLoss'],
 'pinball.common.data.ability.description::InstantAbilityDescriptionGenerator':['stringfyInstantTriggerBattle','$wfxHpLossTriggerDescription'],
 'pinball.common.data.ability.description::AbilityDescriptionTools':['$stringfyConjuctionTriggerLimit'],
 'pinball.common.data.ability.description::CommonAbilityDescriptionContext':['get_triggerLimit','get_neglectOnlyOnce','get_maxTriggerPullerNumber','get_cooltime','get_byEachTriggerPuller'],
 'pinball.common.tools._FunctionTools::BindImpl2_1':['<ctor>','execute'],
 'pinball.common.data.ability::AbilityPowerValue':['<ctor>','resolveDecimal','resolve','calculateDecimal'],
 'pinball.common.data.ability::AbilityPowerValueCalculateMethod':['<ctor>','$LevelScale'],
 'haxe.ds::Option':['<ctor>','$Some'],
 'pinball.error::ClientError':['<ctor>'],
 'Std':['$parseFloat','$parseInt'],
 'pinball.common.math._Decimal::Decimal_Impl_':['$_new','$fromInt','$raw'],
 'pinball.common.math._Decimal100::Decimal100_Impl_':['$clamp','$max','$fromFloat','$fromInt','$fromRaw','$raw','$_new'],
 'pinball.common.math._FloatInt::FloatInt_Impl_':['$toFloat','$ceil','$fromInt','$_new'],
 'pinball.common.math::Decimal100ClosedInterval':['<ctor>','set','add','subtract','isMinimum','setRatio','setMaximum'],
 'pinball.scene.battle.battle::HealthPointGaugeImpl':['getValue','getMaxHealthPoint','subtract','add','setRatio','set','setMaxHealthPoint','changeMaxHp','addMaxStatModifier','wfxObserveHpLoss'],
 'pinball.scene.battle.battle.ability::InstantAbility':['wfxAccumulateHpLoss','get_cooltime','get_triggerLimit','get_precontent','invokePrecontent'],
 'pinball.scene.battle.battle.ability._InstantAbility::AbilityTriggerHandler':['countHandler','update'],
 'pinball.scene.battle.battle.ability._AbilityPrecondition::AbilityPrecondition_Impl_':['$isActive'],
 'pinball.scene.battle.battle.squad.member::MemberImpl':['isDead','isDisposed','getRealMaximumHealthPoint'],
 'pinball.scene.battle.battle.squad.member::MemberState':['<ctor>'],
 standard:['<ctor>','isActive','resolve'],
 }
 if op.lifecycle:
  groups.update({'jp.sipo.gipo.core::Gear':['disposeTop','enterRemove','isDisposed','checkPhaseBeforeDispose'],'jp.sipo.gipo.core::GearPhase':['<ctor>'],'jp.sipo.gipo.core::Diffuser':['dispose'],'jp.sipo.gipo.core.handler::GenericGearDispatcher':['get_executing','clear']})
 labels=[];decls={};names=set(groups);specs=[];field_qnames=[]
 names.update({'pinball.scene.battle.battle.squad.member::Member','pinball.scene.battle.battle.action::ActionExecutor','pinball.scene.battle.battle.ability::PrecontentMagnification','pinball.scene.battle.battle.barrier::BarrierHpGaugeImpl'})
 body_by_mid={z[0]:i for i,z in enumerate(abc.bodies)}
 def qtype(i):return abc.mn_name(i) if i else '*'
 def tcode(s):return s.replace('::','.').lstrip('.')
 def pick(q,spec):
  stat=spec.startswith('$');method=spec.lstrip('$');prefix=q+('$' if stat else '')+'/'
  hits=[x for x in v.by_label if x.startswith(prefix) and x.rsplit('/',1)[-1].split('|')[0].rsplit('::',1)[-1]==method]
  assert len(hits)==1,(q,spec,hits);return hits[0]
 for q,ms in groups.items():
  decls[q]=[]
  for spec in ms:
   l=pick(q,spec);labels.append(l);bi,=v.by_label[l];body=abc.bodies[bi];info=abc.methods[body[0]];stat=spec.startswith('$');method=spec.lstrip('$')
   decls[q].append((stat,method,qtype(info[0]),[qtype(n) for n in info[1]],l))
   target=q+('$' if stat else '')+'/'+method+('' if method=='<ctor>' else '|1')
   specs.append(l if target==l else {'source':l,'target':target})
   for n in [info[0]]+info[1]:
    if '::' in qtype(n):names.add(qtype(n))
   pending=[body[0]];seen=set()
   while pending:
    mid=pending.pop()
    if mid in seen:continue
    seen.add(mid)
    nested_info=abc.methods[mid]
    for n in [nested_info[0]]+nested_info[1]:
     if '::' in qtype(n):names.add(qtype(n))
    for ins in b.asm.decode(abc.bodies[body_by_mid[mid]][5]):
     if ins.name in ('getlex','coerce','astype','constructprop','findpropstrict') and abc.multinames[ins.args[0]][0]==7:
      n=qtype(ins.args[0]);
      if '::' in n:names.add(n)
     if ins.op in (0x40,0x44) and ins.args[0] in body_by_mid:pending.append(ins.args[0])
 names={n for n in names if not n.startswith('flash.') or n=='flash::Boot'}
 imports=''.join('import '+tcode(n)+';' for n in sorted(names))
 seeds={
 ('haxe.ds::Option','None'):'new Option("None",1,[])',
 ('pinball.common.data.ability.instant::InstantAbilityTriggerMasterValue','Initial'):'new InstantAbilityTriggerMasterValue("Initial",0,[])',
 ('pinball.common.data.ability.instant::InstantAbilityTriggerMasterValue','InstantWithoutConditionString'):'new InstantAbilityTriggerMasterValue("InstantWithoutConditionString",1,[])',
 ('pinball.common.data.ability.instant::InstantAbilityTriggerPullerMasterValue','Myself'):'new InstantAbilityTriggerPullerMasterValue("Myself",0,[])',
 ('pinball.common.math._Decimal::Decimal_Impl_','RESOLTION'):'100000',
 ('pinball.common.math._Decimal100::Decimal100_Impl_','RESOLTION'):'100',
 ('jp.sipo.gipo.core::GearPhase','Dispose'):'new GearPhase("Dispose",4,[])',
 }
 special={
 'Boot':'public static var skip_constructor:Boolean=false;public static var lastError:*;',
 'MemberImpl':'''public namespace Action="pinball.scene.battle.battle.action:ActionExecutor";Action function isDead():Boolean{return this.isDead();}Action function isDisposed():Boolean{return this.isDisposed();}''',
 'InstantAbility':'''public var fixtureApplies:Array=[];public var fixtureReenter:Function;public var fixtureMarks:int=0;public var fixtureLimitNotices:int=0;public namespace Prec="pinball.scene.battle.battle.ability:PrecontentMagnification";public function apply(enemy:Enemy,puller:Member,byUnison:Boolean,pre:PrecontentMagnification):void{var h:AbilityTriggerHandler=handlerForDebug;fixtureApplies.push({rest:h.restTriggerLimit,cooltime:h.cooltimeRest,called:h.calledCount,frame:h.frameSinceLastInvoked,ledger:wfxHpLossLedger[this],pre:Object(pre).Prec::resolve(puller),byUnison:byUnison});if(fixtureReenter!=null){var f:Function=fixtureReenter;fixtureReenter=null;f();}}public function markAsReachingLimit():void{fixtureMarks++;}public function addReachingLimitCount(m:Member):void{fixtureLimitNotices++;}''',
 'BarrierHpGaugeImpl':'public var barrierHp:Decimal100ClosedInterval;',
 }
 files={}
 for q in sorted(names):
  pkg,cls=q.split('::') if '::' in q else ('',q);ci,row=rows.get(q,(None,None))
  if row is not None and row[2]&4:
   # The actual interface QNames are used by typed implementations/aliases.
   text='package '+pkg+' {public interface '+cls+' {}}'
   files[q.replace('::','/').replace('.','/').lstrip('/')+'.as']=text;continue
  fields={};methods='';ctor=None
  if q in groups:
   for static,ts in [(False,row[6]),(True,abc.classes[ci][1])]:
    for trait in ts:
     if trait.data[0]!='slot':continue
     n=abc.mn_name(trait.name).rsplit('::',1)[-1];ft=qtype(trait.data[2]);ft=tcode(ft) if '::' not in ft or ft in names else '*'
     mn=abc.multinames[trait.name]
     if not static and mn[0]==7:
      ns=abc.namespaces[mn[1]]
      if ns[0]!=22 or abc.s(ns[1])!='':field_qnames.append({'owner':q,'name':n,'source_name':abc.mn_name(trait.name)})
     fields[(static,n)]=ft
   for static,method,ret,args,l in decls[q]:
    params=','.join('p'+str(i)+':'+tcode(t)+('=false' if t=='Boolean' else '=0' if t in ('int','uint','Number') else '=null') for i,t in enumerate(args))
    if method=='<ctor>':ctor='public function '+cls+'('+params+'){'+('super();' if cls=='ClientError' else '')+'throw new Error("ungrafted ctor");}'
    else:methods+='public '+('static ' if static else '')+'function '+method+'('+params+'):'+tcode(ret)+'{throw new Error("ungrafted native");}'
  extra=special.get(cls,'')
  if cls=='MemberImpl' and (False,'gear') not in fields:fields[(False,'gear')]='*'
  if q==standard:
   # Retain real ctor/isActive/resolve. Extra interface forwarding declarations
   # are separate compiled MethodInfos, never a second trait sharing one MID.
   extra+='public namespace Prec="pinball.scene.battle.battle.ability:PrecontentMagnification";'
   for method in ('isActive','resolve'):
    l=pick(q,method);bi,=v.by_label[l];mid=abc.bodies[bi][0];trait=next(t for t in row[6] if t.data[0]=='method' and t.data[2]==mid)
    if abc.mn_name(trait.name)==method:
     extra+=('Prec function isActive():Boolean{return this.isActive();}' if method=='isActive' else 'Prec function resolve(m:Member):int{return this.resolve(m);}')
  declared=''
  for (static,n),ft in fields.items():
   init=seeds.get((q,n));declared+='public '+('static ' if static else '')+'var '+n+':'+ft+('='+init if init else '')+';'
  if ctor is None:ctor='public function '+cls+'(...args){}'
  parent=' extends Error' if cls=='ClientError' else ''
  impl=(' implements Member,ActionExecutor'+(',GearHolder' if op.lifecycle else '')) if cls=='MemberImpl' else ' implements PrecontentMagnification' if q==standard else ''
  files[q.replace('::','/').replace('.','/').lstrip('/')+'.as']='package '+pkg+' {'+imports+'public class '+cls+parent+impl+' {'+declared+ctor+methods+extra+'}}'
 for n in ('Harness.as','Launcher.as','NativeCases.as','HPNativeCase.as','HPState.as','HPPort.as','HPTeam.as','HPGear.as'):files[n]=(ROOT/n).read_text('utf-8')
 if op.lifecycle:
  files['Harness.as']=(ROOT/'LifeHarness.as').read_text('utf-8');files['LifecycleCase.as']=(ROOT/'LifecycleCase.as').read_text('utf-8')
 files['NativeErrorContract.as']='package {import pinball.error.ClientError;public class NativeErrorContract{public static function isClientError(e:Error):Boolean{return e is ClientError;}public static function code(e:Error):int{return ClientError(e).code;}}}'
 l=pick('pinball.common.data.ability.instant::InstantAbilityTriggerMasterValueTools','$resolve');bi,=v.by_label[l];info=abc.methods[abc.bodies[bi][0]];args=[]
 for n in info[1]:
  qt=qtype(n);args.append('value' if qt.endswith('::InstantAbilityTriggerMasterValue') else 'power' if qt.endswith('::AbilityPowerValue') else 'false' if qt=='Boolean' else '0' if qt in ('int','uint','Number') else 'null')
 files['NativeAPI.as']='package {'+imports+'public class NativeAPI{public static function resolve(value:InstantAbilityTriggerMasterValue):Object{var power:AbilityPowerValue=new AbilityPowerValue(AbilityPowerValueCalculateMethod.LevelScale(1,1));return InstantAbilityTriggerMasterValueTools.resolve('+','.join(args)+');}public static function pre(n:int):PrecontentMagnification{return new '+tcode(standard)+'(n);}public static function describe(trigger:InstantBattleAbilityTriggerKind,limit:Option):String{if(limit.index!=1)throw new Error("this description case requires original None limit");var ctx:CommonAbilityDescriptionContext=new CommonAbilityDescriptionContext();ctx.env={};ctx.env["get"]=function(key:String):String{if(key!="ability_description_instant_conjunction_trigger_limit_no_limit")throw new Error("unexpected locale key:"+key);return "|LIMIT_NONE|";};var g:InstantAbilityDescriptionGenerator=new InstantAbilityDescriptionGenerator();var f:Function=g.stringfyInstantTriggerBattle(trigger);return f(ctx);}}}'
 fixture_raw=input_path('leader169980_fixture').read_bytes()
 if a.sha(fixture_raw)!='f61d6a5f292d75e18a59bf81759dce452b0d81a2bd1a58e3d38684edb064c24c':raise ValueError('actual348 fixture changed')
 fixture=json.loads(fixture_raw)
 work.mkdir(parents=True);src=work/'src';src.mkdir();write_sources(src,files)
 plan={'after':{'path':str(AFTER),'sha256':SHA},'donor':{'path':str(donor),'sha256':DONOR_SHA,'scope_proof':str(ROOT.parent/'targets.json')},'before':{'path':str(input_path('tutorial_swf')),'sha256':'215860d0f3933b352c377309c68943a3978a80ab5c5beb209c9b94382191e325'},'includes':[tcode(q) for q in sorted(names)],'actual_methods':specs,'field_qnames':field_qnames,'before_parsers':[pick('pinball.master.generated::LeaderAbilityValues','$parseAt25'),pick('pinball.master.generated::AbilityValues','$parseAt27')],'case':{'row':fixture['row'],'fixture_sha256':a.sha(fixture_raw)},'boundaries':['Complete native counter/countdown/precondition/parent getters, original invokePrecontent, native StandardPrecontentMagnification, native Member death/disposed/max getters and actual15HP bodies imported/readback.','Parent.apply is final content output only; it observes original native writes and may request one actual reentrant subtraction. It contains no counter/cooldown/ledger math.','Slot precontent supply is a typed external-content port returning native StandardPrecontentMagnification(1/0); real precontent effect execution is not tested.','Gear disposal flag and squad membership are finite state; native Member.isDisposed/isDead/getRealMaximumHealthPoint bodies execute. Full Gear.dispose/Member registration teardown/GC retirement is not tested.','Enum static Initial/InstantWithoutConditionString/Option.None/Myself are finite bootstrap state using actual native enum constructors; full owning boot initializer is not executed. Decimal resolution100/100000 matches prior actual carry fixture constants.','Limit mission/passive notification calls are recorded after real count consumes the final limit; side effects are not claimed.']}
 if op.lifecycle:
  plan['modes']=['after'];plan['boundaries']=[x for x in plan['boundaries'] if not x.startswith('Gear disposal flag')];plan['boundaries']+=['Lifecycle increment executes actual empty Gear.disposeTop/enterRemove/Diffuser.dispose/isDisposed/checkPhaseBeforeDispose. Empty callback stack/0 children/null diffuser dictionaries are explicit; full Member callback registrations/children teardown is not tested.','Weak-key retirement is observed only after a short ephemeral function returns and later Timer/System.gc phases, with two retained strong-reference controls.']
 (work/'fixture-plan.json').write_text(json.dumps(plan,indent=2)+'\n','utf-8')
 target_contract=json.loads((ROOT.parent/'targets.json').read_text());report={'donor':{'selected':[r['qname'].rsplit('::',1)[-1].split('|')[0] for r in target_contract['methods']]}};targets=[]
 for short in report['donor']['selected']:
  hit=[l for l in v.by_label if l.rsplit('::',1)[-1].split('|')[0]==short];assert len(hit)==1,(short,hit);bi,=v.by_label[hit[0]];body=abc.bodies[bi]
  targets.append({'qname':hit[0],'methodInfo':body[0],'bodyIndex':bi,'codeSha256':a.sha(body[5]),'header':body[1:5]})
 (work/'15-TARGET-METHODS-83fc.json').write_text(json.dumps({'swfSha256':SHA,'totalMethods':len(abc.methods),'methods':targets},indent=2)+'\n','utf-8')
 print(json.dumps({'attempt':str(work),'methods':len(labels),'classes':len(names),'standardPrecontent':standard,'identity':identity}))
if __name__=='__main__':main()
