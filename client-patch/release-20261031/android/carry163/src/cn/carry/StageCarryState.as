package cn.carry {
import flash.utils.Dictionary;
import flash.utils.getQualifiedClassName;
import flash.utils.getDefinitionByName;
/** Stage-local value snapshots. No old owner/member/battle/slot/playhead is retained. */
public final class StageCarryState {
 private static var states:Dictionary=new Dictionary(true);
 private static var applied:Dictionary=new Dictionary(true);
 public static function cloneValue(v:*, seen:Dictionary=null):* {
  if(v==null || typeof v=="number" || typeof v=="boolean" || typeof v=="string" || typeof v=="undefined")return v;
  if(seen==null)seen=new Dictionary();
  if(seen[v]!==undefined)return seen[v];
  var out:*;var i:int;var key:String;
  if(v is Array){out=[];seen[v]=out;for(i=0;i<v.length;i++)out[i]=cloneValue(v[i],seen);return out;}
  if(getQualifiedClassName(v).indexOf("__AS3__.vec::Vector.")==0){var vectorClass:Class=getDefinitionByName(getQualifiedClassName(v)) as Class;out=new vectorClass(v.length,false);seen[v]=out;for(i=0;i<v.length;i++)out[i]=cloneValue(v[i],seen);out.fixed=v.fixed;return out;}
  if(getQualifiedClassName(v)=="Object"){out={};seen[v]=out;for(key in v)out[key]=cloneValue(v[key],seen);return out;}
  // The one typed payload used by ConditionChangeContent (variant 25).
  if(getQualifiedClassName(v)=="pinball.common.data.ability::AdditionalDirectAttackContent"){
   var directClass:Class=getDefinitionByName("pinball.common.data.ability::AdditionalDirectAttackContent") as Class;
   out=new directClass(int(v.directAttackTimes),Number(v.directAttackDamage));seen[v]=out;return out;
  }
  // Haxe enum constructors only assign tag/index/params. They are value trees.
  if(("__enum__" in v) && v.__enum__===true && ("params" in v) && ("tag" in v) && ("index" in v)){
   var enumClass:Class=v.constructor as Class;out=new enumClass(String(v.tag),int(v.index),null);seen[v]=out;out.params=cloneValue(v.params,seen);return out;
  }
  throw new Error("stage carry unsupported value: "+getQualifiedClassName(v));
 }
 public static function cloneCondition(c:Object,shift:int):Object {
  var klass:Class=c.constructor as Class;
  var out:Object=new klass(c.id,c._originalTimeLimit,int(c.addedTime)+shift,c.timeLimit,c.restFlipLimit,c.restPowerFlipLimit,c.restEndPowerFlipLimit,cloneValue(c.endPowerFlipAcceptedLevels),c.maxAccumulation,cloneValue(c.content),c.cancelable,c.isEternal,c.statsBattleId,c.originMemberIndex,c.shouldCountForMission,c.isFromHostile,c.extensionId,c.magnificationFromPrimary,c.magnificationFromOther,null,null,c.discriminationKey,c.isQuestInitial);
  out.consumedCount=c.consumedCount;
  // This is an elapsed animation phase counter, not an absolute stage timestamp.
  out.blinkFrameCount=cloneValue(c.blinkFrameCount);
  return out;
 }
 public static function snapshotSlot(slot:Object):Object {
  if(slot==null)return null;
  var conditions:Array=[];var applications:Array=[];var i:int;var c:Object;
  for(i=0;i<slot.conditions._keys.length;i++){
   c=slot.getConditionByIndex(i);
   if(c.isQuestInitial || c.linkedTrialId!=null || c.hitCountCheck!=null || c.hasExpired(slot.frameCount))continue;
   conditions.push(cloneCondition(c,-int(slot.frameCount)));
  }
  var iter:Object=slot.applicationResolver.keys();var keys:Array=[];
  while(iter.hasNext())keys.push(iter.next());keys.sort();
  for each(var key:String in keys)applications.push([key,cloneValue(slot.applicationResolver.get(key))]);
  return {conditions:conditions,applications:applications,invisible:snapshotSlot(slot.invisibleSlot)};
 }
 public static function restoreSlot(slot:Object,data:Object):void {
  if(slot==null || data==null)return;
  for each(var source:Object in data.conditions){
   var c:Object=cloneCondition(source,int(slot.frameCount));
   slot.conditions.set(c.id,c);
   // Recreate only the neutral HUD carrier. Never replay obtain/link/combo hooks.
   if(!slot.get_isInvisibleSlot() && !slot.iconEffectPlayheads.exists(c.id)){
    var icon:Object=slot.asset.getPlayhead("battle/common/layer1/hud_condition_icon_effect");
    icon.gotoAndPlay("none");slot.iconEffectPlayheads.set(c.id,icon);
   }
  }
  for each(var row:Array in data.applications)slot.applicationResolver.set(row[0],cloneValue(row[1]));
  slot.refreshIndex=int(slot.refreshIndex)+1;
  restoreSlot(slot.invisibleSlot,data.invisible);
 }
 public static function quietBaseline(slot:Object):void {
  if(slot==null)return;
  slot.prevTotalDebuffCounts=slot.getTotalDebuffCounts(false);
  slot.prevRefreshIndex=slot.refreshIndex;
  quietBaseline(slot.invisibleSlot);
 }
 public static function snapshotHp(member:Object):Object {
  var gauge:Object=member.healthPointGauge;var hp:Object=gauge.healthPoint;var shield:Object=gauge.barrierHp;
  return {min:hp.min,max:hp.max,value:hp.value,modifier:gauge.maxStatsModifier,lower:gauge.lowerLimitValue,
    shield:shield==null?null:{min:shield.barrierHp.min,max:shield.barrierHp.max,value:shield.barrierHp.value,frameCount:shield.frameCount}};
 }
 public static function restoreHp(member:Object,data:Object):void {
  var gauge:Object=member.healthPointGauge;
  // Native Member.setContinuationData has already restored maximum then ratio.
  // Keep the exact captured interval/value rather than applying an HP modifier twice.
  gauge.setMaxHealthPoint(data.max,data.modifier);gauge.healthPoint.min=data.min;gauge.healthPoint.set(data.value);gauge.lowerLimitValue=data.lower;
  if(data.shield!=null && Number(data.shield.value)>Number(data.shield.min)){
   if(gauge.barrierHp!=null)gauge.barrierHp.disposePlayhead();
   var barrierClass:Class=getDefinitionByName("pinball.scene.battle.battle.barrier::BarrierHpGaugeImpl") as Class;
   var decimalClass:Class=getDefinitionByName("pinball.common.math._Decimal100::Decimal100_Impl_") as Class;
   var shield:Object=new barrierClass(gauge.owner,Number(data.shield.max)/Number(decimalClass.RESOLTION),gauge.isBoss,gauge.viewOrder,gauge.logicAssets);
   shield.barrierHp.min=data.shield.min;shield.barrierHp.max=data.shield.max;shield.barrierHp.set(data.shield.value);shield.frameCount=int(data.shield.frameCount);
   gauge.barrierHp=shield;
  }
 }
 public static function capture(continuation:Object,squad:Object):void {
  if(continuation==null || squad==null)return;
  var members:Array=[];
  for each(var option:Object in squad.members){if(option.index!=0)continue;var member:Object=option.params[0];members.push({index:member.index,slot:snapshotSlot(member.conditionSlot),hp:snapshotHp(member)});}
  states[continuation]={shared:snapshotSlot(squad.conditionSlot),members:members};
 }
 public static function apply(squad:Object,continuation:Object):void {
  if(squad==null || continuation==null || applied[squad]===continuation)return;
  var state:Object=states[continuation];if(state==null)return;
  restoreSlot(squad.conditionSlot,state.shared);
  for each(var option:Object in squad.members){if(option.index!=0)continue;var member:Object=option.params[0];
   for each(var row:Object in state.members){if(row.index!=member.index)continue;restoreSlot(member.conditionSlot,row.slot);restoreHp(member,row.hp);break;}
  }
  quietBaseline(squad.conditionSlot);
  for each(option in squad.members){if(option.index==0)quietBaseline(option.params[0].conditionSlot);}
  applied[squad]=continuation;
 }
}}
