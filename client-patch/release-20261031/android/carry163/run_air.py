"""Full compiled helper plus actual native condition/update/HP methods; recording UI/owner boundaries."""
from pathlib import Path
import json,sys,subprocess,struct,zlib,argparse
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
import bootstrap
from input_config import runtime,input_path,input_sha,work_path,repo_path,helper_path
import abc_tools as a

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--swf',default=str(input_path('carry_swf')));p.add_argument('--sha',required=True);op=p.parse_args();out=Path(op.out).resolve()
 if out.exists() or not out.is_relative_to(work_path()):raise ValueError('fresh carry directory required')
 out.mkdir();src=out/'src';src.mkdir();cfg=runtime();swf=Path(op.swf).resolve();digest=a.sha(swf.read_bytes());
 if op.sha is not None and digest!=op.sha:raise ValueError('explicit source SWF SHA mismatch')
 ctx={**cfg,'repo':str(repo_path()),'swf':str(swf),'swf_sha256':digest,'tool_root':str(ROOT.parent/'test-support'),'run_root':str(out)};a.configure(ctx);builder,source,sv,identity=a.load_current(('pinball.scene.battle.battle.condition::ConditionSlot',))
 groups={
 'pinball.common.data.ability::AdditionalDirectAttackContent':['<ctor>'],
 'pinball.common.data.character.condition::Condition':['<ctor>','hasExpired','hasConsumed','getRemainingTime','updateBlinkFrameCount','updateLinkedHitCountCheck','consume','countUpBallFlip','countUpPowerFlip','countUpEndPowerFlip','get_accumulatable','get_magnification'],
 'pinball.common.data.character.condition::ConditionChangeContent':['<ctor>'],
 'pinball.common.data.character.condition::ConditionChangeContentTools':['$getDirection','$isConsumable','$getConsumableCount'],
 'pinball.common.data.character.condition::ConditionTools':['$getDirection'],
 'pinball.scene.battle.battle.condition::ConditionSlot':['getConditionByIndex','get_isInvisibleSlot','getTotalDebuffCounts','update','addRefreshCount','removeCondition'],
 'pinball.scene.battle.battle::HealthPointGaugeImpl':['setMaxHealthPoint','getRatio','setRatio','getMaxHealthPoint','addMaxStatModifier'],
 'pinball.common.math::Decimal100ClosedInterval':['<ctor>','set','setMaximum','setRatio','getRatio','isMinimum'],
 'pinball.scene.battle.battle.barrier::BarrierHpGaugeImpl':['update'],
 'pinball.common.math._Decimal100::Decimal100_Impl_':['$clamp','$fromInt','$fromRaw','$fromFloat','$raw','$_new'],
 'pinball.common.math._Decimal::Decimal_Impl_':['$fromInt','$raw','$_new'],
 'pinball.common.math._FloatInt::FloatInt_Impl_':['$fromInt','$toFloat','$ceil','$_new'],
 }
 # Close all direct references among current core wfx helpers starting at removeCondition.
 # Non-wfx combat services stay external; the ordinary expiry must return before them.
 core_closure=[]
 method_index={}
 for label in sv.by_label:
  name=label.split('/')[-1].split('|')[0]
  if name.startswith('wfx'):method_index.setdefault(name,[]).append(label)
 pending=['pinball.scene.battle.battle.condition::ConditionSlot/removeCondition|1'];seen=set()
 while pending:
  label=pending.pop()
  if label in seen:continue
  seen.add(label);bi,=sv.by_label[label]
  for ins in builder.asm.decode(source.bodies[bi][5]):
   if ins.name not in ('callproperty','callpropvoid'):continue
   name=source.mn_name(ins.args[0]).split('::')[-1]
   if not name.startswith('wfx'):continue
   choices=method_index.get(name,[])
   if not choices:raise ValueError('missing core helper '+name)
   if len(choices)>1:
    owner=label.split('/')[0].rstrip('$');same=[x for x in choices if x.split('/')[0].rstrip('$')==owner]
    if len(same)!=1:raise ValueError('ambiguous core helper '+name)
    choices=same
   dep=choices[0];pending.append(dep)
   owner,method=dep.rsplit('/',1);static=owner.endswith('$');owner=owner.rstrip('$');method=method.split('|')[0];decl=('$' if static else '')+method
   if decl not in groups.setdefault(owner,[]):groups[owner].append(decl);core_closure.append(dep)
 if core_closure:
  groups.setdefault('pinball.scene.battle.battle::Battle',[]).append('__isMyBattle__')
  groups.setdefault('pinball.scene.battle.battle.squad.member::MemberImpl',[]).extend(['isInPrimarySquad','isMultiball','isLeader'])
 labels=[];defs={};names=set(groups)|{'::Type','::ValueType','fixture::Recorder','haxe.ds::StringMap','pinball.common.ds::OrderedMap','flatomo.timeline::Playhead','pinball.scene.battle.battle.squad.member::Member','pinball.common.data.character.condition::ConditionDirection'}
 for owner,ms in groups.items():
  defs[owner]=[]
  for name in ms:
   static=name.startswith('$');name=name.lstrip('$');prefix=owner+('$' if static else '')+'/'+name;hits=[l for l in sv.by_label if l==prefix or l.startswith(prefix+'|')];assert len(hits)==1,(owner,name,hits);label=hits[0];labels.append(label);bi,=sv.by_label[label];body=source.bodies[bi];info=source.methods[body[0]]
   typ=lambda i:source.mn_name(i) if i else '*'
   for t in [info[0]]+info[1]:
    n=typ(t)
    if '::' in n:names.add(n)
   if name!='<ctor>':defs[owner].append((static,name,typ(info[0]),[typ(t) for t in info[1]]))
   for x in builder.asm.decode(body[5]):
    if x.name in ('coerce','astype','getlex','findpropstrict','constructprop') and source.multinames[x.args[0]][0]==7:
     n=source.mn_name(x.args[0]);
     if '::' in n:names.add(n)
 def put(n,text):
  text=text.replace('.const.','.constantx.');path=src/(n.replace('.const.','.constantx.').replace('::','/').replace('.','/').lstrip('/')+'.as');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
 def short(n):return n.split('::')[-1]
 def typecode(n):return n.replace('::','.') if n!='*' else '*'
 special={
 'Recorder':'public static var effects:int=0;public static var expired:int=0;public static var icons:int=0;public static var combo:int=0;public static var missions:int=0;public static var disposed:int=0;public static function wfxStageClone(c:Condition,shift:int):Condition{throw new Error("ungrafted old clone");}public static function installArrayExtensions():void{Array.prototype["remove"]=function(v:Object):Boolean{return false;};Array.prototype.setPropertyIsEnumerable("remove",false);}',
 'Boot':'public static var skip_constructor:Boolean=false;public static var lastError:*;',
 'BattleConstants':'public static var HUD_CONDITION_ICON_BLINKING_TIME:int=180;',
 'ConditionDirection':'public static var Good:ConditionDirection=new ConditionDirection(0);public static var Bad:ConditionDirection=new ConditionDirection(1);',
 'StringMap':"public static var reserved:Object={};public var h:Object={};public var rh:Object={};public function set(k:*,v:*):void{h[k]=v;}public function get(k:*):*{return h[k];}public function exists(k:*):Boolean{return k in h;}public function remove(k:*):Boolean{return delete h[k];}public function getReserved(k:*):*{return h[k];}public function setReserved(k:*,v:*):void{h[k]=v;}public function existsReserved(k:*):Boolean{return k in h;}public function keys():Object{var a:Array=[];for(var k:String in h)a.push(k);var i:int=0;return {hasNext:function():Boolean{return i<a.length;},next:function():*{return a[i++];}};}",
 'OrderedMap':"public var _keys:Array=[];public var map:haxe.ds.StringMap=new haxe.ds.StringMap();public function set(k:*,v:*):*{if(!map.exists(k))_keys.push(k);map.set(k,v);return v;}",
 'Playhead':'public var frames:int=0;public function gotoAndPlay(v:String):void{if(v!="none")fixture.Recorder.effects++;}public function advanceFrame():void{frames++;}public function isSequenceBeginFrame(v:String):Boolean{return false;}',
 'Squad':'public var kind:*;public function isPrimary():Boolean{throw new Error("ungrafted squad guard");}',
 'Member':'public function countUpExpiredCondition(v:*):void{fixture.Recorder.expired++;}',
 'BarrierHpGaugeImpl':'public function disposePlayhead():void{fixture.Recorder.disposed++;}',
 'Type':'public static function typeOf(v:*):ValueType{var t:ValueType=new ValueType();t.index=1;return t;}public static function enumEq(a:*,b:*):Boolean{return a===b;}',
 'ImpactHitEffectPosition':'public static function CenterOfTarget(v:Boolean):ImpactHitEffectPosition{return new ImpactHitEffectPosition();}',
 'GearDispatcherHandler':'public var func:Function;',
 'GenericGearDispatcher':'public var handlers:Array=[new GearDispatcherHandler()];public var once:Boolean=false;public var executingHandlers:Array;public var executingIndex:int=-1;public function get_executing():Boolean{return false;}public function clear():void{}',
 }
 names={n for n in names if not n.startswith('flash.') or n=='flash::Boot'}
 for n in sorted(names):
  pkg,cls=n.split('::');methods=defs.get(n,[]);fields=set();fieldtypes={};extra=special.get(cls,'');ctor='public function '+cls+'(...a){}'
  row=next((row for row in source.instances if source.mn_name(row[0])==n),None)
  if n in groups and row is not None:
   fields={source.mn_name(t.name) for t in row[6] if t.data[0]=='slot' and '::' not in source.mn_name(t.name)}
   fieldtypes={source.mn_name(t.name):source.mn_name(t.data[2]) if t.data[2] else '*' for t in row[6] if t.data[0]=='slot'}
  for label in labels:
   if label.startswith(n+'/'):
    bi,=sv.by_label[label]
    for x in builder.asm.decode(source.bodies[bi][5]):
     if x.name=='findproperty' and '::' not in source.mn_name(x.args[0]):fields.add(source.mn_name(x.args[0]))
  fields-=set(m[1] for m in methods)
  if cls in ('ConditionChangeContent','ConditionDirection','Option','ValueType'):fields|={'tag','index','params','__enum__'};fieldtypes.update({'tag':'String','index':'int','params':'Array','__enum__':'Boolean'})
  if cls=='ConditionChangeContent':fields.discard('__enum__');extra+='public const __enum__:Boolean=true;'
  if cls=='GearDispatcherHandler':ctor='public function GearDispatcherHandler(...a){func=function(v:*):void{Recorder.effects++;};}'
  if cls=='ConditionDirection':ctor='public function ConditionDirection(i:int=0){index=i;}'
  if cls=='BarrierHpGaugeImpl':ctor='public function BarrierHpGaugeImpl(...a){owner=a.length>0?a[0]:null;barrierHp=new pinball.common.math.Decimal100ClosedInterval(0,0,0);frameCount=0;playhead=new flatomo.timeline.Playhead();}'
  if cls=='Decimal100_Impl_':extra+='public static var RESOLTION:Number=100;'
  if cls=='Decimal_Impl_':extra+='public static var RESOLTION:Number=100000;'
  if n in groups and row is not None:
   ci=source.instances.index(row)
   for trait in source.classes[ci][1]:
    if trait.data[0]=='slot' and '::' not in source.mn_name(trait.name) and source.mn_name(trait.name) not in ('RESOLTION',):extra+='public static var '+source.mn_name(trait.name)+':*;'
  for static,name,returns,args in methods:
   extra+='public '+('static ' if static else '')+'function '+name+'('+','.join('p'+str(i)+':'+typecode(t) for i,t in enumerate(args))+'):'+typecode(returns)+'{throw new Error("ungrafted '+name+'");}'
  text='package '+pkg+' {'+''.join('import '+full.replace('::','.').lstrip('.')+';' for full in sorted(names))+'public class '+cls+(' extends Member' if cls=='MemberImpl' else '')+' {'+''.join('public var '+f+':'+(typecode(fieldtypes[f]) if f in fieldtypes and (fieldtypes[f] in ('int','uint','Number','Boolean','String','Array','haxe.ds::Option','pinball.common.ds::OrderedMap') or fieldtypes[f] in groups) else '*')+';' for f in sorted(fields))+ctor+extra+'}}'
  # Imports make short names usable for nested construction in generated fixture code.
  for full in sorted(names,key=len,reverse=True):
   text=text.replace(':'+full.replace('::','.'),':'+short(full)).replace('new '+full.replace('::','.')+'(','new '+short(full)+'(').replace(full.replace('::','.')+'.',short(full)+'.')
  put(n,text)
 put('air_harness',(ROOT/'air_harness.as').read_text(encoding='utf-8'))
 sdk=Path(cfg['sdk']);cmd=[cfg['java'],'-Xmx1g','-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-debug=true','-compress=false','-compiler.source-path='+str(src),'-external-library-path+='+str(helper_path('swc')),'-includes='+','.join(n.replace('::','.').replace('.const.','.constantx.').lstrip('.') for n in sorted(names)),'-output='+str(out/'template.swf'),str(src/'air_harness.as')];run=subprocess.run(cmd,cwd=out,capture_output=True,timeout=90);(out/'compile.log').write_bytes(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError('fixture compilation failed')
 template=(out/'template.swf').read_bytes();target=builder.abcfmt.ABC(list(a.raw_units(template))[0][1]);target.strings=[x.replace(b'.constantx.',b'.const.') for x in target.strings];tv=a.view(target);extra_target,=[l for l in tv.by_label if l.startswith('fixture::Recorder$/installArrayExtensions|1/closure:')];extra={'source':'script:flash::Boot/<init>/closure:6','target':extra_target};core_guard_mapping=[]
 if core_closure:
  real_is_primary,=[l for l in sv.by_label if l.startswith('pinball.scene.battle.battle.squad::SquadImpl/isPrimary|')];core_guard_mapping=a.graft(target,source,[{'source':real_is_primary,'target':'pinball.scene.battle.battle.squad::Squad/isPrimary|1'}])
 mapping=a.graft(target,source,labels+[extra]);old_path=input_path('old163_swf');old_raw=old_path.read_bytes();assert a.sha(old_raw)=='463ae455765f31be5e2d782bda9ab024d7b2f1bb344c6ada36db038fab30c302';old_source=builder.SwfAbc(old_path).abc;old_label,=[l for l in a.view(old_source).by_label if l.startswith('pinball.common.data.battle.restore::BattleContinuationData$/wfxStageClone|')];old_mapping=a.graft(target,old_source,[{'source':old_label,'target':'fixture::Recorder$/wfxStageClone|1'}])
 # Rename the reserved Type keyword alias for the native removeCondition consumer.
 for row in target.instances:
  if target.mn_name(row[0])=='Type':
   for t in row[6]+target.classes[target.instances.index(row)][1]:
    if target.mn_name(t.name)=='typeOf':target.multinames[t.name]=(7,target.multinames[t.name][1],target.strings.index(b'typeof') if b'typeof' in target.strings else len(target.strings));target.strings.append(b'typeof') if b'typeof' not in target.strings else None
 # Native MemberImpl guards call the actual Squad interface QName.
 if core_closure:
  imp=builder.Importer(a.view(target),sv)
  for row in target.instances:
   if target.mn_name(row[0])=='pinball.scene.battle.battle.squad::Squad':
    trait=next(t for t in row[6] if t.data[0]=='method' and target.mn_name(t.name)=='isPrimary')
    q,=[i for i,m in enumerate(source.multinames) if m and m[0]==7 and source.mn_name(i)=='pinball.scene.battle.battle.squad:Squad::isPrimary'];trait.name=imp.pool('multinames',q)
 # Member's external counter interface method must use the exact native QName.
 imp=builder.Importer(a.view(target),sv)
 for row in target.instances:
  if target.mn_name(row[0])=='pinball.scene.battle.battle.squad.member::Member':
   t=next(t for t in row[6] if t.data[0]=='method' and target.mn_name(t.name)=='countUpExpiredCondition')
   for i,mn in enumerate(source.multinames):
    if mn and mn[0]==7 and source.mn_name(i)=='pinball.scene.battle.battle.squad.member:Member::countUpExpiredCondition':t.name=imp.pool('multinames',i)
 carrier=a.replace_abc(template,target);parsed=builder.abcfmt.ABC(list(a.raw_units(carrier))[0][1]);proof=a.verify_grafts(parsed,source,mapping);old_proof=a.verify_grafts(parsed,old_source,old_mapping);core_guard_proof=a.verify_grafts(parsed,source,core_guard_mapping)
 helper=helper_path('abc').read_bytes();
 if sum(unit==helper for _,unit in a.raw_units(swf.read_bytes()))!=1:raise ValueError('selected production SWF must contain exact current helper ABC once')
 body=zlib.decompress(carrier[8:]) if carrier[:3]==b'CWS' else carrier[8:];at=next(at for c,at,h,z in a.swftags.iter_tags(body) if c==82);payload=struct.pack('<I',1)+b'actual_carry_helper\0'+helper;tag=struct.pack('<HI',(82<<6)|63,len(payload))+payload;body=body[:at]+tag+body[at:];final=b'FWS'+carrier[3:4]+struct.pack('<I',len(body)+8)+body;(out/'Harness.swf').write_bytes(final);(out/'proof.json').write_text(json.dumps({'identity':identity,'actual_helper_abc_sha256':a.sha(helper),'actual_helper_bytes_exact':True,'real_methods':proof,'old_original163_clone_sha256':a.sha(old_raw),'old_clone_method':old_proof,'core_wfx_helper_closure':core_closure,'core_native_guard_methods':core_guard_proof,'harness_sha256':a.sha(final),'recording_boundaries':['StringMap/OrderedMap, graphical playheads, owner expiry counter and Boot/constants are typed fixture boundaries.','Native condition/update/HP/interval methods are grafted unchanged and executed; helper ABC injected unchanged.','Native bothbossNext and SquadImpl.setContinuationData hooks are statically reversible; complete native battle assembly not executed here.']},indent=2),encoding='utf-8')
 app=out/'application.xml';app.write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.carry.'+out.name+'</id><versionNumber>1.0.0</versionNumber><filename>carry</filename><initialWindow><content>Harness.swf</content><visible>false</visible></initialWindow></application>',encoding='utf-8');cmd=[str(sdk/'bin/adl.exe'),'-cmd',str(app)]
 try:run=subprocess.run(cmd,cwd=out,capture_output=True,timeout=30)
 except subprocess.TimeoutExpired as e:(out/'adl.log').write_bytes((e.stdout or b'')+(e.stderr or b''));raise
 (out/'adl.log').write_bytes(run.stdout+run.stderr);result=json.loads((out/'result.json').read_text(encoding='utf-8'));print(json.dumps(result,ensure_ascii=False));assert run.returncode==0 and result['passed']
if __name__=='__main__':main()
