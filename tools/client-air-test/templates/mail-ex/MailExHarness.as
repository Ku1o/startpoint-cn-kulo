package {
import fixture.CommonHarness;
import fixture.MailExAssets;
import fixture.MailExGlobal;
import fixture.MailExHook;
import fixture.MailExMailList;
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
import pinball.common.data.character.joinMovie.JoinMovieKind;
import pinball.common.data.exBoost.ExBoostItemAcquisitionRepository;
import pinball.common.data.exBoost.ExBoostRepository;
import pinball.common.data.player.PlayerLogic;
import pinball.common.ds.OrderedMap;
import pinball.remote.common.ResponseData;
import pinball.remote.mail.MailRemoteInput;
import pinball.remote.mail.MailReceiveRemoteUtil;
import pinball.remote.mail.receive.MailReceiveRealRemote;
import pinball.remote.mail.receiveAll.MailReceiveAllRealRemote;
import pinball.scene.characterGet.CharacterGetCharacterInfoTools;
import pinball.scene.mailList.MailListScene;
public class MailExHarness extends Sprite {
 private var master:Object=JSON.parse(__CLIENT_MASTER_JSON__);
 private var checks:Array=[];
 public function MailExHarness(){NativeApplication.nativeApplication.addEventListener(InvokeEvent.INVOKE,start);}
 private function read(path:String):Object{var fs:FileStream=new FileStream();fs.open(new File(path),FileMode.READ);var data:Object=JSON.parse(fs.readUTFBytes(fs.bytesAvailable));fs.close();return data;}
 private function write(path:String,data:Object):void{var fs:FileStream=new FileStream();fs.open(new File(path),FileMode.WRITE);fs.writeUTFBytes(JSON.stringify(data));fs.close();}
 private function serial(v:*):*{if(v is IMap)return serial(CommonHarness.objectMap(v as IMap));if(v is Option||v is MailRemoteInput||v is JoinMovieKind)return {tag:v.tag,index:v.index,params:serial(v.params)};if(v is Array){var a:Array=[];for each(var x:* in v)a.push(serial(x));return a;}if(v!==null&&typeof v=="object"){var o:Object={};for(var key:String in v)o[key]=serial(v[key]);return o;}return v;}
 private function check(pass:Boolean,id:String,actual:*=null,expected:*=null):void{checks.push({id:id,pass:pass,actual:serial(actual),expected:serial(expected)});}
 private function eq(actual:*,expected:*,id:String):void{check(CommonHarness.same(serial(actual),serial(expected)),id,actual,expected);}
 private function failures():int{var total:int=0;for each(var row:Object in checks)if(row.pass!==true)total++;return total;}
 private function state(actual:Object,expected:Object):void{if(expected===null)throw new Error("Expected complete economic projection");for each(var name:String in ["items","equipments","characters","crazyGachaResultList"])eq(actual[name],expected[name],"state."+name);for(var key:String in expected.userInfo)eq(actual.userInfo[key],expected.userInfo[key],"state.userInfo."+key);}
 private function raw(s:Object):Object{if(!s.hasOwnProperty("response"))throw new Error("Missing complete response");var r:Object=s.response;if(r&&r.data&&r.data.data_headers)return r.data;return r;}
 private function request(s:Object):Object{return s.request?(s.request.body||s.request):{};}
 private function chars(p:PlayerLogic):OrderedMap{var map:OrderedMap=new OrderedMap();for(var key:String in p.saveData.characters.h){var c:OwnedCharacterLogic=new OwnedCharacterLogic();c.characterSaveData=p.saveData.characters.h[key];map._keys.push(int(key));map.map.h[int(key)]=c;}return map;}
 private function player(before:Object):PlayerLogic{var p:PlayerLogic=CommonHarness.createPlayer(before);p["getOwnedCharacters"]=function():OrderedMap{return chars(p);};return p;}
 private function expectedJoined(before:Object,after:Object):Array{var a:Array=[];for(var key:String in after.characters){var n:int=before.characters.hasOwnProperty(key)?int(after.characters[key].stack)-int(before.characters[key].stack):int(after.characters[key].stack)+1;for(var i:int=0;i<n;i++)a.push(int(key));}a.sort(Array.NUMERIC);return a;}
 private function totals(items:Array,idField:String,countField:String):Object{var total:Object={};for each(var item:Object in items){var id:String=String(item[idField]);total[id]=int(total[id]||0)+int(item[countField]);}return total;}
 private function displayTotals(info:Array):Object{var items:Array=[];for each(var row:Object in info){var kind:JoinMovieKind=row.entryKind as JoinMovieKind;if(kind.index==1){var optional:Option=kind.params[0] as Option;if(optional.index==0)items.push(optional.params[0]);}}return totals(items,"id","count");}
 private function expectedBatchGroups(items:Array,mails:Array):Object{var input:Object={};for each(var mail:Object in mails)input[String(mail.mail_id)]=mail;var grouped:Object={};for each(var row:Object in items){if(!input.hasOwnProperty(String(row.mail_id)))throw new Error("Expected metadata references unknown mail");var id:String=String(input[String(row.mail_id)].character_id);if(!grouped.hasOwnProperty(id))grouped[id]=[];grouped[id].push({id:row.item_id,count:row.item_count});}return grouped;}
 private function nativeItemIds(acquisition:ExBoostItemAcquisitionRepository):Array{var ids:Array=acquisition.getExBoostItemIds();ids.sort(Array.NUMERIC);return ids;}
 private function mapKeys(map:IMap):Array{var a:Array=[];for(var key:* in Object(map).h)a.push(int(key));a.sort(Array.NUMERIC);return a;}
 private function masterDiagnostics(c:Object,acquisition:ExBoostItemAcquisitionRepository):Array{var rows:Array=[];if(!(c.setup.characters is Array))throw new Error("Missing character metadata");for each(var ch:Object in c.setup.characters){if(!master.characters.hasOwnProperty(String(ch.character_id)))throw new Error("No captured native character row for "+ch.character_id);var nativeRow:Object=master.characters[String(ch.character_id)];eq(ch.rarity,nativeRow.rarity,"master.character.rarity."+ch.character_id);eq(ch.element,nativeRow.element,"master.character.element."+ch.character_id);var acquired:Option=acquisition.getExBoostItem(int(ch.character_id));if(acquired.index!=0)throw new Error("Captured native acquisition is missing");var grant:Object=acquired.params[0];eq(ch.duplicate_item_id,grant.id,"master.compensation.itemId."+ch.character_id);eq(ch.duplicate_item_count,grant.count,"master.compensation.perDuplicateCount."+ch.character_id);rows.push({characterId:ch.character_id,native:serial(grant),serverPerDuplicate:ch.duplicate_item_count,countMatches:grant.count===ch.duplicate_item_count,note:"Independent server expectation must equal the verified native acquisition count; actual inventory increments are checked separately."});}return rows;}
 private function business(c:Object,acquisition:ExBoostItemAcquisitionRepository,assets:MailExAssets):Object{
  var row:Object={id:c.id,group:c.group,clientScenario:c.clientScenario,steps:[]};var caseFailed:Boolean=false;checks=[];
  try{
   if(!(c.steps is Array)||!c.steps.length||!c.setup||!(c.setup.mails is Array)||c.setup.captureAllExItemIdsIncludingZero!==true)throw new Error("Incomplete mail-ex fixture contract");
   var p:PlayerLogic=player(c.before);var snapshots:Object={};var stepIds:Object={};row.masterDiagnostics=masterDiagnostics(c,acquisition);row.masterChecks=checks;checks=[];
   for each(var s:Object in c.steps){
    var step:Object={id:s.id,route:s.route,requestSnapshotStepId:s.requestSnapshotStepId};checks=[];
    try{
     if(!s.id||stepIds.hasOwnProperty(s.id))throw new Error("Missing or duplicate step ID");stepIds[s.id]=true;
     if(s.httpStatus!==200)throw new Error("mail-ex requires successful application response");
     var bulk:Boolean=String(s.route).indexOf("mail/receive_all")>=0;if(!bulk&&String(s.route).indexOf("mail/receive")<0)throw new Error("Unsupported mail-ex route");
     var ref:String=s.requestSnapshotStepId;if(!ref||ref=="undefined")throw new Error("Missing request snapshot identity");
     if(ref===s.id){if(snapshots.hasOwnProperty(ref))throw new Error("Duplicate snapshot identity");snapshots[ref]={characters:MailReceiveRemoteUtil.getCharacterIdAndCount(p),items:acquisition.getOwnedExBoostItemMap(p),state:CommonHarness.snapshot(p)};}
     if(!snapshots.hasOwnProperty(ref))throw new Error("Retry references uncaptured request snapshot "+ref);
     var captured:Object=snapshots[ref];eq(mapKeys(captured.items),nativeItemIds(acquisition),"snapshot.all-native-EX-IDs-including-zero");step.beforeExSnapshot=serial(captured.items);
     var hook:MailExHook=new MailExHook();var global:MailExGlobal=new MailExGlobal(p,acquisition);var req:Object=request(s);var actor:Object;
     if(bulk){var all:MailReceiveAllRealRemote=new MailReceiveAllRealRemote();all.mailIds=req.mail_ids;all.beforeCharacterList=captured.characters;all.dispatcher=hook;all.globalLogic=global;actor=all;}
     else{var single:MailReceiveRealRemote=new MailReceiveRealRemote();single.mailId=int(req.mail_id);single.beforeCharacterList=captured.characters;single.beforeExBoostItemList=captured.items;single.dispatcher=hook;single.globalLogic=global;actor=single;}
     var begin:int=CommonHarness.events.length;
     hook.beforeInstant=function(event:Object):void{var order:Array=[];for each(var e:Object in CommonHarness.events.slice(begin))if(e.kind=="common-before"||e.kind=="common-after"||e.kind=="callback"||e.kind=="mail-finished")order.push(e.kind);eq(order,["common-before","common-after","callback"],"common-update-before-mail-Finished");state(CommonHarness.snapshot(p),s.expectedAfter);CommonHarness.events.push({kind:"mail-finished"});};
     var response:ResponseData=CommonHarness.consume(raw(s),p);actor.successHandler(response);
     eq(hook.events.length,1,"exactly-one-native-mail-event");if(hook.events.length!=1)throw new Error("Expected native mail event");var event:MailRemoteInput=hook.events[0] as MailRemoteInput;if(event===null)throw new Error("Wrong event QName");step.event=serial(event);
     eq(event.tag,bulk?"ReceiveAllFinished":"ReceiveFinished","native-mail-event-tag");eq(event.index,bulk?2:1,"native-mail-event-index");eq(event.params[0],bulk?req.mail_ids:req.mail_id,"requested-mail-IDs");
     var joined:Array=event.params[1].concat();joined.sort(Array.NUMERIC);eq(joined,expectedJoined(captured.state,s.expectedAfter),"joined-copies-from-request-snapshot");
     var display:Array;var expectedItems:Array;var scene:MailListScene=new MailListScene();scene.mailList=new MailExMailList(c.setup.mails);
     if(bulk){
      if(!(s.expectedBatchExItems is Array))throw new Error("Missing expectedBatchExItems");expectedItems=s.expectedBatchExItems;
      var optional:Option=event.params[2].ex_boost_item_list as Option;if(optional===null)throw new Error("Missing native optional EX list");
      step.rawExBoostItemList=serial(raw(s).data.ex_boost_item_list);step.nativeExBoostItemList=serial(optional);
      eq(optional.index,0,"batch-native-list-is-Some");var list:Array=optional.index==0?optional.params[0]:[];eq(list,expectedItems,"batch-native-wire-items-exact");
      var grouped:IMap=scene.getExBoostItemMap(optional);step.groupedExItems=serial(grouped);eq(serial(grouped),expectedBatchGroups(expectedItems,c.setup.mails),"native-mail-ID-to-character-grouping");
      display=CharacterGetCharacterInfoTools.from(event.params[1],grouped,p);
     }else{
      if(!(s.expectedSingleExItems is Array))throw new Error("Missing expectedSingleExItems");expectedItems=s.expectedSingleExItems;eq(event.params[3],expectedItems,"single-native-inventory-difference");
      display=CharacterGetCharacterInfoTools.fromSingleCharacters(event.params[1],event.params[3],p,assets);
     }
     step.displayInfo=serial(display);step.displayRewardTotals=displayTotals(display);eq(display.length,event.params[1].length,"native-display-one-row-per-joined-copy");eq(step.displayRewardTotals,totals(expectedItems,bulk?"item_id":"id",bulk?"item_count":"count"),"native-display-preserves-actual-granted-total");
     state(CommonHarness.snapshot(p),s.expectedAfter);step.state=CommonHarness.snapshot(p);
    }catch(error:*){check(false,"execution-error",String(error),null);step.error=String(error);step.stack=error is Error?error.getStackTrace():null;}
    step.checks=checks;step.failed=failures();step.status=step.failed?"failed":"passed";if(step.failed)caseFailed=true;row.steps.push(step);
   }
   checks=[];state(CommonHarness.snapshot(p),c.expectedAfter);row.finalChecks=checks;if(failures())caseFailed=true;row.state=CommonHarness.snapshot(p);
   eq(row.steps.length,c.steps.length,"all-declared-steps-observed");row.declaredStepCount=c.steps.length;
  }catch(error2:*){caseFailed=true;row.error=String(error2);row.stack=error2 is Error?error2.getStackTrace():null;}
  if(row.masterChecks)for each(var mc:Object in row.masterChecks)if(mc.pass!==true)caseFailed=true;
  row.status=caseFailed?"failed":"passed";return row;
 }
 private function contracts(acquisition:ExBoostItemAcquisitionRepository):Object{
  var row:Object={id:"mail-ex-difference-contract",group:"synthetic",steps:[]};var failed:Boolean=false;
  var before:IntMap=new IntMap();before.h[14003]=0;before.h[14006]=3;
  var cases:Array=[{id:"mail-ex-diff-zero-positive",value:Option.Some(CommonHarness.map({"14003":1})),expected:[{id:14003,count:1}]},{id:"mail-ex-diff-existing-positive",value:Option.Some(CommonHarness.map({"14006":6})),expected:[{id:14006,count:3}]},{id:"mail-ex-diff-unchanged",value:Option.Some(CommonHarness.map({"14006":3})),expected:[]},{id:"mail-ex-diff-decreased",value:Option.Some(CommonHarness.map({"14006":0})),expected:[]},{id:"mail-ex-diff-omitted",value:Option.None,expected:[]},{id:"mail-ex-diff-unrelated",value:Option.Some(CommonHarness.map({"999":8})),expected:[]},{id:"mail-ex-diff-invalid-map",value:Option.Some("wrong map"),expectedErrorId:1034}];
  var repository:ExBoostRepository=new ExBoostRepository();
  for each(var c:Object in cases){checks=[];var step:Object={id:c.id};try{var actual:Array=repository.getIncreasedExBoostItems({item_list:c.value},before);step.observed=serial(actual);if(c.hasOwnProperty("expectedErrorId"))check(false,"strict-map-type-rejected",actual,c.expectedErrorId);else eq(actual,c.expected,"actual-native-difference");}catch(error:*){step.error=String(error);if(c.hasOwnProperty("expectedErrorId")&&error is Error){step.nativeErrorID=Error(error).errorID;check(error is TypeError,"strict-map-error-type",String(error),"TypeError");eq(String(error),"TypeError: Error #"+c.expectedErrorId,"strict-map-type-rejected");}else check(false,"unexpected-native-error",String(error),null);}step.checks=checks;step.failed=failures();step.status=step.failed?"failed":"passed";if(step.failed)failed=true;row.steps.push(step);}
  row.status=failed?"failed":"passed";return row;
 }
 private function start(e:InvokeEvent):void{
  var rows:Array=[];var excluded:Array=[];var failed:int=0;var fatal:Object=null;var observedStepCount:int=0;
  try{CommonHarness.installHaxeArrayContract();var input:Object=read(String(e.arguments[0]));if(input.schemaVersion!==2||!(input.cases is Array))throw new Error("Expected schemaVersion 2 fixtures");var assets:MailExAssets=new MailExAssets(master);var acquisition:ExBoostItemAcquisitionRepository=new ExBoostItemAcquisitionRepository(assets);var ids:Object={};
   for each(var c:Object in input.cases){if(c.clientScenario!=="mail-ex"){excluded.push({id:c.id,reason:"not mail-ex scenario"});continue;}if(c.group!=="mail"||!c.id||ids.hasOwnProperty(c.id))throw new Error("Invalid or duplicate mail-ex case");ids[c.id]=true;var row:Object=business(c,acquisition,assets);rows.push(row);observedStepCount+=row.steps.length;if(row.status!=="passed")failed++;}
   if(!rows.length)throw new Error("No mail-ex business cases");var contract:Object=contracts(acquisition);rows.push(contract);observedStepCount+=contract.steps.length;if(contract.status!=="passed")failed++;
  }catch(error:*){failed++;fatal={error:String(error),stack:error is Error?error.getStackTrace():null};}
  write(String(e.arguments[1]),{schemaVersion:2,suite:"mail-ex",stage_is_null:stage===null,status:failed?"failed":"passed",failed:failed,cases:rows,caseCount:rows.length,stepCount:observedStepCount,excludedCases:excluded,fatal:fatal,nativeMasterSource:master.source,limits:["Complete selected AVM2 algorithms; post-MessagePack full responses, no HTTP/Flash decode.","Actual captured client acquisition rows; server per-duplicate expectations and granted totals must match the verified rarity rule.","Typed master/list storage and heavy character construction are external fixture boundaries.","Presentation data is checked; actual game scene, rendering, platform runtime and final animation are not executed."]});NativeApplication.nativeApplication.exit(failed?1:0);
 }
}}
