package {
import fixture.CommonHarness;
import fixture.FlowGlobal;
import fixture.FlowHook;
import flash.desktop.NativeApplication;
import flash.display.Sprite;
import flash.events.InvokeEvent;
import flash.filesystem.File;
import flash.filesystem.FileMode;
import flash.filesystem.FileStream;
import haxe.IMap;
import haxe.ds.IntMap;
import haxe.ds.Option;
import pinball.common.data.character.OwnedCharacterLogic;
import pinball.common.data.player.PlayerLogic;
import pinball.common.data.player.PlayerPeek;
import pinball.common.ds.OrderedMap;
import pinball.context.remote.real.RealRemote;
import pinball.context.remote.real.RealRemoteService;
import pinball.remote.common.ResponseData;
import pinball.remote.equipment.sell.EquipmentBulkSellStackRealRemote;
import pinball.remote.equipment.sell.EquipmentSellEquipmentRealRemote;
import pinball.remote.equipment.sell.EquipmentSellStackRealRemote;
import pinball.remote.equipment.upgrade.EquipmentUpgradeRealRemote;
import pinball.remote.equipment.upgrade.EquipmentUpgradeRemoteInput;
import pinball.remote.exBoost.ExBoostDrawRealRemote;
import pinball.remote.exBoost.ExBoostFirstDrawRealRemote;
import pinball.remote.exBoost.ExBoostSelectRealRemote;
import pinball.remote.gacha.crazyGachaResult.CrazyGachaResultSaveRealRemote;
import pinball.remote.gacha.crazyGachaResult.CrazyGachaResultSelectRealRemote;
import pinball.remote.gacha.exec.GachaExecRealRemote;
import pinball.remote.mail.MailReceiveRemoteUtil;
import pinball.remote.mail.receive.MailReceiveRealRemote;
import pinball.remote.mail.receiveAll.MailReceiveAllRealRemote;
import pinball.remote.tutorial.updateStep.TutorialUpdateStepKind;
import pinball.remote.tutorial.updateStep.TutorialUpdateStepRealRemote;






















































































































































































































































































































































































































































































































































































































































public class FlowHarness extends Sprite {
 private var exCharacterId:int=0;
 private var upgradeObservation:Object=null;
 private function validateState(actual:Object,expected:Object):void {
  for each(var name:String in ["items","equipments","characters","crazyGachaResultList"])
   if(!CommonHarness.same(actual[name],expected[name]))throw new Error("state mismatch "+name);
  subset(actual.userInfo,expected.userInfo,"state.userInfo");
 }
 private function validateEvents(s:Object,events:Array,p:PlayerLogic):void {
  var route:String=s.route;var data:Object=raw(s).data;var request:Object=s.request?(s.request.body||s.request):{};
  if(route.indexOf("/load")>=0)return;
  if(route.indexOf("equipment/upgrade")>=0){
   if(upgradeObservation===null)throw new Error("upgrade Finished did not pass the common-update observation");
   if(!CommonHarness.same(upgradeObservation.order,["common-before","common-after","callback","equipment-upgrade-finished"]))throw new Error("upgrade common/Finished order mismatch");
  }
  if(events.length!=1)throw new Error("expected one flow event: "+route+" got "+events.length);
  var event:Object=events[0];var expectedTag:String;
  if(route.indexOf("tutorial/")>=0)expectedTag="Present";
  else if(route.indexOf("mail/receive_all")>=0)expectedTag="ReceiveAllFinished";
  else if(route.indexOf("mail/receive")>=0)expectedTag="ReceiveFinished";
  else if(route.indexOf("equipment/upgrade")>=0){expectedTag="Finished";if(event.index!==0||event.params!==null)throw new Error("upgrade Finished enum shape mismatch");}
  else if(route.indexOf("sell_equipment")>=0)expectedTag="EquipmentSold";
  else if(route.indexOf("bulk_sell_stack")>=0)expectedTag="Finished";
  else if(route.indexOf("sell_stack")>=0)expectedTag="StackSold";
  else if(route.indexOf("crazy_gacha_save")>=0){expectedTag="GachaSave";subset(event.params[0],data.crazy_gacha_result_list,"event.savedSlots");}
  else if(route.indexOf("crazy_gacha_select")>=0)expectedTag="GachaSelect";
  else if(route.indexOf("gacha/exec")>=0){expectedTag="GachaExec";var candidates:Array=event.params[1];if(candidates.length!=10)throw new Error("expected ten candidates");for(var i:int=0;i<10;i++){var w:Object=data.draw[i];var d:Object=candidates[i];subset(d.character_id,w.character_id,"candidate.id");subset(d.movie_id,w.movie_id,"candidate.movie");subset(d.seed,w.seed,"candidate.seed");subset(d.entry_count,w.entry_count,"candidate.entryCount");if(w.ex_boost_item===null&&d.ex_boost_item.index!=1)throw new Error("candidate optional EX mismatch");}}
  else if(route.toLowerCase().indexOf("exboost")>=0||route.indexOf("/ex/")>=0){expectedTag=route.indexOf("select")>=0?(request.is_confirm?"FinishedOverride":"FinishedDiscard"):"Finished";if(int(event.params[0])!=exCharacterId)throw new Error("EX event character mismatch");if(route.indexOf("draw")>=0&&route.indexOf("first_draw")<0)subset(event.params[1],data.draw_result,"EX draw event");}
  if(expectedTag&&event.tag!=expectedTag)throw new Error("event tag "+event.tag+" != "+expectedTag);
  if(route.indexOf("sell_equipment")>=0)subset(event.params[0],request.equipment_list[0].equipment_id,"equipment event ID");
  if(route.indexOf("mail/receive")>=0){
   if(route.indexOf("receive_all")>=0)subset(event.params[0],request.mail_ids,"mail batch IDs");else subset(event.params[0],request.mail_id,"mail ID");
   var joined:Array=[];var oldChars:Object=s.before.characters;var newChars:Object=s.expectedAfter.characters;
   for(var key:String in newChars){var count:int=oldChars.hasOwnProperty(key)?int(newChars[key].stack)-int(oldChars[key].stack):int(newChars[key].stack)+1;for(var n:int=0;n<count;n++)joined.push(int(key));}
   var observed:Array=event.params[1].concat();joined.sort(Array.NUMERIC);observed.sort(Array.NUMERIC);subset(observed,joined,"mail joined character copies");
   var receipt:Object=event.params[2];if(data.total_count!==undefined)subset(receipt.total_count,data.total_count,"mail total count");
   for each(var field:String in ["already_mail_count","received_mail_count","unreceived_mail_count"])
    if(data[field]!==undefined)subset(receipt[field],data[field],"mail receipt "+field);
  }
  if((route.toLowerCase().indexOf("exboost")>=0)&&(route.indexOf("first_draw")>=0||expectedTag=="FinishedOverride")){
   for each(var character:Object in data.character_list)if(int(character.character_id)==exCharacterId)subset(event.params[1],character.ex_boost,"EX installed event");
  }
 }
 public function FlowHarness(){NativeApplication.nativeApplication.addEventListener(InvokeEvent.INVOKE,start);}
 private function read(p:String):Object {var s:FileStream=new FileStream();s.open(new File(p),FileMode.READ);var v:Object=JSON.parse(s.readUTFBytes(s.bytesAvailable));s.close();return v;}
 private function write(p:String,v:Object):void {var s:FileStream=new FileStream();s.open(new File(p),FileMode.WRITE);s.writeUTFBytes(JSON.stringify(v));s.close();}
 private function serial(v:*):* {if(v is IntMap)return serial(v.h);if(v is Option)return {tag:v.tag,index:v.index,params:serial(v.params)};if(v is Array){var a:Array=[];for each(var x:* in v)a.push(serial(x));return a;}if(v!==null&&typeof v=="object"){var o:Object={};for(var k:String in v)o[k]=serial(v[k]);return o;}return v;}
 private function subset(actual:*,expected:*,path:String="root"):void {if(expected is Array){if(!(actual is Array)||actual.length!=expected.length)throw new Error(path+" array mismatch");for(var i:int=0;i<expected.length;i++)subset(actual[i],expected[i],path+"["+i+"]");}else if(expected!==null&&typeof expected=="object"){for(var k:String in expected){if(actual===null||actual===undefined||!actual.hasOwnProperty(k))throw new Error(path+" missing "+k);subset(actual[k],expected[k],path+"."+k);}}else if(actual!==expected)throw new Error(path+" "+actual+" != "+expected);}
 private function raw(s:Object):Object {var r:Object=s.response;if(r&&r.data&&r.data.data_headers)return r.data;return r;}
 private function chars(p:PlayerLogic):OrderedMap {var r:OrderedMap=new OrderedMap();for(var k:String in p.saveData.characters.h){var c:OwnedCharacterLogic=new OwnedCharacterLogic();c.characterSaveData=p.saveData.characters.h[k];r._keys.push(int(k));r.map.h[k]=c;}return r;}
 private function characterCounts(p:PlayerLogic):IMap {var r:IntMap=new IntMap();for(var k:String in p.saveData.characters.h)r.h[k]=int(p.saveData.characters.h[k].stack);return r;}
 private function actor(s:Object,p:PlayerLogic,h:FlowHook):Object {var route:String=s.route;var request:Object=s.request?(s.request.body||s.request):{};var a:Object;
  h.beforeInstant=null;upgradeObservation=null;
  if(route.indexOf("equipment/upgrade")>=0){
   a=new EquipmentUpgradeRealRemote();
   var commonStart:int=CommonHarness.events.length;
   h.beforeInstant=function(input:Object):void {
    if(!(input is EquipmentUpgradeRemoteInput)||input!==EquipmentUpgradeRemoteInput.Finished)throw new Error("upgrade dispatched the wrong typed Finished constant");
    var order:Array=[];
    for each(var observed:Object in CommonHarness.events.slice(commonStart)){
     if(observed.kind=="common-before"||observed.kind=="common-after"||observed.kind=="callback"||observed.kind=="equipment-upgrade-finished")order.push(observed.kind);
    }
    if(!CommonHarness.same(order,["common-before","common-after","callback"]))throw new Error("upgrade Finished occurred before exactly one completed common update");
    var state:Object=CommonHarness.snapshot(p);
    if(s.expectedAfter===null||s.expectedAfter===undefined)throw new Error("upgrade requires expectedAfter before Finished");
    validateState(state,s.expectedAfter);
    order.push("equipment-upgrade-finished");
    upgradeObservation={stepId:s.id,order:order,stateBeforeFinished:state,typedFinished:true};
    CommonHarness.events.push({kind:"equipment-upgrade-finished",stepId:s.id});
   };
  }
  else if(route.indexOf("sell_equipment")>=0){a=new EquipmentSellEquipmentRealRemote();a.sellId=request.equipment_list?int(request.equipment_list[0].equipment_id):0;}
  else if(route.indexOf("bulk_sell_stack")>=0)a=new EquipmentBulkSellStackRealRemote();
  else if(route.indexOf("sell_stack")>=0)a=new EquipmentSellStackRealRemote();
  else if(route.indexOf("first_draw")>=0)a=new ExBoostFirstDrawRealRemote();
  else if((route.indexOf("/ex/")>=0||route.toLowerCase().indexOf("exboost")>=0)&&route.indexOf("draw")>=0)a=new ExBoostDrawRealRemote();
  else if((route.indexOf("/ex/")>=0||route.toLowerCase().indexOf("exboost")>=0)&&route.indexOf("select")>=0){a=new ExBoostSelectRealRemote();a.isConfirm=Boolean(request.is_confirm);}
  else if(route.indexOf("crazy_gacha_save")>=0)a=new CrazyGachaResultSaveRealRemote();
  else if(route.indexOf("crazy_gacha_select")>=0)a=new CrazyGachaResultSelectRealRemote();
  else if(route.indexOf("tutorial/update_step")>=0){a=new TutorialUpdateStepRealRemote();a.kind=new TutorialUpdateStepKind("CompleteStepWithPresent",5,[null]);}
  else if(route.indexOf("mail/receive_all")>=0){a=new MailReceiveAllRealRemote();a.mailIds=request.mail_ids||[];a.beforeCharacterList=MailReceiveRemoteUtil.getCharacterIdAndCount(p);}
  else if(route.indexOf("mail/receive")>=0){a=new MailReceiveRealRemote();a.mailId=int(request.mail_id);a.beforeCharacterList=MailReceiveRemoteUtil.getCharacterIdAndCount(p);a.beforeExBoostItemList=new IntMap();}
  else if(route.indexOf("gacha/exec")>=0){var remote:RealRemote=new RealRemote();remote.globalLogic=new FlowGlobal(p);a=new GachaExecRealRemote(remote,h,int(request.gacha_id),int(request.type),int(request.payment_type),int(request.number_of_exec));}
  else return null;
  if(a is TutorialUpdateStepRealRemote)a.dispatcher=Option.Some(h);else a.dispatcher=h;
  a.globalLogic=new FlowGlobal(p);if(request.character_id!==undefined){a.characterId=int(request.character_id);exCharacterId=int(request.character_id);}else if(a is ExBoostSelectRealRemote)a.characterId=exCharacterId;
  return a;
 }
 private function start(e:InvokeEvent):void {var rows:Array=[];var failed:int=0;try {CommonHarness.installHaxeArrayContract();Object(RealRemoteService).prototype.startUserRequest=function(...args):void{CommonHarness.events.push({kind:"flow-recorded-request",route:args[0],request:args[1]});};var input:Object=read(String(e.arguments[0]));if(input.schemaVersion!==2)throw new Error("Expected fixtures schemaVersion 2");for each(var c:Object in input.cases){var row:Object={id:c.id,group:c.group,steps:[]};try{exCharacterId=0;var p:PlayerLogic=CommonHarness.createPlayer(c.before);p["getOwnedCharacters"]=function():OrderedMap{return chars(p);};var hook:FlowHook=new FlowHook();for each(var s:Object in c.steps){var step:Object={id:s.id,route:s.route,httpStatus:s.httpStatus};try{if(int(s.httpStatus)!=200){step.status="not_sent_to_success_consumer";continue;}if(String(s.route).indexOf("/load")>=0){step.status="deferred_to_full_load_carrier";continue;}var a:Object=actor(s,p,hook);if(a===null)throw new Error("Uncovered route: "+s.route);var beforeEvents:int=hook.events.length;var r:ResponseData=CommonHarness.consume(raw(s),p);if(a!==null)a.successHandler(r);step.consumer=a===null?"common_only":String(a);step.events=serial(hook.events.slice(beforeEvents));validateEvents(s,step.events,p);if(a is EquipmentUpgradeRealRemote)step.upgradeObservation=upgradeObservation;step.lastCrazyGachaDrawResult=serial(p.saveData.lastCrazyGachaDrawResult);step.status="passed";step.state=CommonHarness.snapshot(p);if(s.expectedAfter)validateState(step.state,s.expectedAfter);}catch(err:*){step.status="failed";step.error=String(err);step.stack=err is Error?err.getStackTrace():null;throw err;}finally{row.steps.push(step);}}row.state=CommonHarness.snapshot(p);if(c.expectedAfter)validateState(row.state,c.expectedAfter);row.checks=[{id:"all-covered-step-events-and-states",pass:true}];row.status="passed";}catch(err2:*){failed++;row.status="failed";row.error=String(err2);}rows.push(row);}}catch(err3:*){failed++;rows.push({status:"harness_failed",error:String(err3),stack:err3 is Error?err3.getStackTrace():null});}write(String(e.arguments[1]),{stage_is_null:stage===null,status:failed?"failed":"passed",failed:failed,cases:rows,limits:"Real selected Android R11 AVM2 consumers in AIR cmd; external dispatcher/storage/assets recorded; no full game, Android GPU or iOS execution."});NativeApplication.nativeApplication.exit(failed?1:0);}
}
}
