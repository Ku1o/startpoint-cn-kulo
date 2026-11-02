package {
import flash.display.Sprite;import flash.desktop.NativeApplication;import flash.events.InvokeEvent;import flash.filesystem.File;import flash.filesystem.FileStream;import flash.filesystem.FileMode;
import fixture.CommonHarness;import fixture.CrazyHook;import fixture.CrazyLoadingScene;import fixture.CrazySaveView;import fixture.FlowHook;import fixture.FlowRestore;
import haxe.IMap;import haxe.ds.IntMap;import haxe.ds.Option;
import pinball.context.global.GlobalLogic;import pinball.context.remote.real.RealRemote;import pinball.context.HookForSection;import pinball.context.remote.NewsInterruptFlagSender;
import pinball.remote.common.ResponseData;import pinball.remote.gacha.GachaRemoteInput;import pinball.remote.gacha.exec.GachaExecRealRemote;import pinball.remote.gacha.crazyGachaResult.CrazyGachaResultSaveRealRemote;import pinball.remote.gacha.crazyGachaResult.CrazyGachaResultSelectRealRemote;
import pinball.remote.initialize.InitializeRealRemote;import pinball.common.data.player.PlayerLogic;import pinball.common.data.scene.SceneKind;
import pinball.loading.gacha.GachaLoadingTask;import pinball.dialog.gacha.GachaResultSaveDialog;import pinball.dialog.gacha.GachaResultSelectDialog;import pinball.dialog.processing.CloseBehavior;import pinball.ui.component.button.ButtonGroupLogic;import pinball.config.core.DevConfig;import pinball.scene.home.HomeScene;
public class CrazyFlowHarness extends Sprite {
 private var assertions:int=0;private var currentChecks:Array;private var negative:Array=[];
 public function CrazyFlowHarness(){NativeApplication.nativeApplication.addEventListener(InvokeEvent.INVOKE,start);}
 private function read(path:String):Object{var fs:FileStream=new FileStream();fs.open(new File(path),FileMode.READ);var v:Object=JSON.parse(fs.readUTFBytes(fs.bytesAvailable));fs.close();return v;}
 private function write(path:String,v:Object):void{var fs:FileStream=new FileStream();fs.open(new File(path),FileMode.WRITE);fs.writeUTFBytes(JSON.stringify(v));fs.close();}
 private function check(id:String,value:Boolean):void{assertions++;currentChecks.push({id:id,pass:value});if(!value)throw new Error(id);}
 private function wire(value:*):*{
  if(value is Option)return value.index==1?null:wire(value.params[0]);
  if(value is IMap)return wire(CommonHarness.objectMap(value));
  if(value is Array){var arr:Array=[];for(var i:int=0;i<value.length;i++)arr.push(wire(value[i]));return arr;}
  if(value!==null&&typeof value=="object"){var obj:Object={};for(var key:String in value)if(value.hasOwnProperty(key))obj[key]=wire(value[key]);return obj;}return value;
 }
 private function state(p:PlayerLogic,expected:Object):void{
  var actual:Object=CommonHarness.snapshot(p);
  for each(var name:String in ["equipments","characters","crazyGachaResultList"])check("state/"+name,CommonHarness.same(actual[name],expected[name]));
  var nonzero:Object={};for(var id:String in actual.items)if(actual.items[id]!==0)nonzero[id]=actual.items[id];check("state/nonzero-items",CommonHarness.same(nonzero,expected.items));
  for(var k:String in expected.userInfo)check("state/userInfo/"+k,actual.userInfo[k]===expected.userInfo[k]);
 }
 private function loading(g:GlobalLogic,event:GachaRemoteInput):Object{
  var task:GachaLoadingTask=new GachaLoadingTask();task.globalLogic=g;var target:CrazyLoadingScene=new CrazyLoadingScene();task.scene=target;task.remoteInput(event);
  return {task:task,target:target};
 }
 private function assertCandidates(result:Object,expected:Array):void{
  if(result.target.scenes.length!=1)throw new Error("candidate scene count");var scene:SceneKind=result.target.scenes[0];
  if(scene.tag!="GachaBallMovie"||int(scene.params[0])!=100||int(scene.params[1])!=14)throw new Error("candidate scene route");
  if(!CommonHarness.same(wire(scene.params[3]),expected))throw new Error("candidate scene payload mismatch");
  var chars:Array=scene.params[2].characters;if(chars.length!=expected.length)throw new Error("candidate result count");
  for(var i:int=0;i<chars.length;i++)if(int(chars[i].characterId)!=int(expected[i].character_id))throw new Error("candidate result ID mismatch");
 }
 private function negativeCandidate(event:GachaRemoteInput,expected:Array,before:Object):void{
  var params:Array=event.params.concat();var candidates:Array=params[1].concat();var first:Object={};for(var key:String in candidates[0])first[key]=candidates[0][key];first.character_id=int(first.character_id)+1;candidates[0]=first;params[1]=candidates;
  var g:GlobalLogic=new GlobalLogic();g.player=CommonHarness.createPlayer(before);g.player.saveData.gachaStatus=new IntMap();
  var outcome:Object=loading(g,new GachaRemoteInput(event.tag,event.index,params));var rejected:Boolean=false;var message:String="";
  try{assertCandidates(outcome,expected);}catch(e:Error){rejected=true;message=e.message;}
  negative.push({id:"mutated-candidate-through-real-loading-consumer",expected_rejection:true,guard_rejected:rejected,error:message,changed_field:"first character_id",production_methods_unchanged:true});check("negative-control/candidate-change-is-detected",rejected&&message=="candidate scene payload mismatch");
 }
 private function load(s:Object):Object{
  var task:InitializeRealRemote=new InitializeRealRemote();task.fixtureStoredData={viewerId:s.request.body.viewer_id};task.newsInterruptFlagSender=new NewsInterruptFlagSender();task.hook=new HookForSection();task.hook.dispatcher=new FlowHook();var restore:FlowRestore=new FlowRestore();task.restore=restore;
  var count:int=0;var result:Object;task.completeHandler=function(v:Object):void{count++;result=v;};task.loadSuccessHandler("fixture-input",new ResponseData(s.response,true));
  check("load/complete-once",count==1);check("load/requested-restore-branch",result.restoreState.tag==s.expectedRestoreState);check("load/normal-home-branch",result.restoreState.tag=="None");
  var p:PlayerLogic=CommonHarness.createPlayer(s.before);p.saveData=result.player;
  check("load/raw-item-map",CommonHarness.same(CommonHarness.snapshot(p).items,s.response.data.item_list));
  check("load/last-candidates-exact-wire",CommonHarness.same(wire(p.get_last_crazy_gacha_result_list()),s.expectedLastCrazyGachaDrawResult));
  return {player:p,loaded:result,restore:restore};
 }
 private function home(g:GlobalLogic,expected:Array):Object{
  var h:HomeScene=new HomeScene();h.globalLogic=g;h.startChangeCrazyGachaResultScene();
  if(expected.length){check("home/recovery-result-route",h.transitions.length==1);var next:Object=h.transitions[0].next;check("home/recovery-scene-kind",next.tag=="Scene"&&next.params[0].tag=="GachaResult");var scene:Object=next.params[0];check("home/recovery-gacha-ID",int(scene.params[0])==100&&int(scene.params[1])==14);var chars:Array=scene.params[2].characters;var ids:Array=[];for each(var c:Object in chars)ids.push(int(c.characterId));var expectedIds:Array=[];for each(var w:Object in expected)expectedIds.push(int(w.character_id));check("home/recovery-candidate-IDs",CommonHarness.same(ids,expectedIds));}
  else{check("home/cleared-no-results-route",h.transitions.length==0);check("home/cleared-next-startup",h.nextStartupCalls==1);}
  return {navigation_count:h.transitions.length,next_startup_calls:h.nextStartupCalls};
 }
 private function start(e:InvokeEvent):void{
  var rows:Array=[];var failed:int=0;try{
   CommonHarness.installHaxeArrayContract();Object(Math)["isNaN"]=function(v:Number):Boolean{return isNaN(v);};Object(Math)["isFinite"]=function(v:Number):Boolean{return isFinite(v);};
   var input:Object=read(String(e.arguments[0]));if(input.schemaVersion!==2)throw new Error("Expected schemaVersion 2");
   for each(var c:Object in input.cases)if(c.group=="crazy"){
    var row:Object={id:c.id,checks:[],steps:[]};try{
     var sequence:Array=["crazy-exec","crazy-exec-retry","crazy-load-after-exec","crazy-save","crazy-save-retry","crazy-load-after-save","crazy-select","crazy-select-retry","crazy-load-after-select"];var position:int=0;currentChecks=row.checks;check("case/exactly-nine-required-steps",c.steps.length==sequence.length);
     var g:GlobalLogic=new GlobalLogic();g.player=CommonHarness.createPlayer(c.before);g.player.saveData.gachaStatus=new IntMap();var didNegative:Boolean=false;
     for each(var s:Object in c.steps){var step:Object={id:s.id,route:s.route,checks:[]};currentChecks=step.checks;try{
      check("step/expected-order",s.id===sequence[position++]);check("response/success",int(s.httpStatus)==200);var route:String=s.route;var expected:Array=s.expectedLastCrazyGachaDrawResult;
      if(route=="/api/index.php/load"){
       var restored:Object=load(s);g.player=restored.player;step.restoreState=restored.loaded.restoreState.tag;step.home=home(g,expected);step.coverage="complete-real-load-and-home-recovery";
      }else{
       var hook:CrazyHook=new CrazyHook();var actor:Object;var request:Object=s.request.body;var beforeLast:*=wire(g.player.get_last_crazy_gacha_result_list());
       if(route.indexOf("/gacha/exec")>=0){var remote:RealRemote=new RealRemote();remote.globalLogic=g;actor=new GachaExecRealRemote(remote,hook,int(request.gacha_id),int(request.type),int(request.payment_type),int(request.number_of_exec));}
       else if(route.indexOf("crazy_gacha_save")>=0){actor=new CrazyGachaResultSaveRealRemote();actor.dispatcher=hook;}
       else if(route.indexOf("crazy_gacha_select")>=0){actor=new CrazyGachaResultSelectRealRemote();actor.dispatcher=hook;}
       else throw new Error("Unexpected crazy route "+route);
       actor.successHandler(CommonHarness.consume(s.response,g.player));check("callback/exactly-one-event",hook.events.length==1);var event:GachaRemoteInput=hook.events[0];step.event=event.tag;
       if(event.tag=="GachaExec"){
        check("draw/event-candidates",CommonHarness.same(wire(event.params[1]),expected));var loaded:Object=loading(g,event);assertCandidates(loaded,expected);check("draw/loading-complete-once",loaded.task.completeCalls==1);check("draw/analytics-boundary-once",loaded.task.analyticsCalls==1);check("draw/no-invented-last-write",CommonHarness.same(wire(g.player.get_last_crazy_gacha_result_list()),beforeLast));step.scene={tag:loaded.target.scenes[0].tag,candidate_count:loaded.target.scenes[0].params[3].length};
        for each(var info:Object in s.response.data.gacha_info_list)if(int(info.gacha_id)==100){var status:Object=g.player.saveData.gachaStatus.h[100];check("draw/actual-player-crazy-count",wire(status.crazyDrawCount)===info.crazy_draw_count);check("draw/actual-player-exchange-point",wire(status.gachaExchangePoint)===info.gacha_exchange_point);}
        if(!didNegative){negativeCandidate(event,expected,s.expectedAfter);didNegative=true;}
       }else if(event.tag=="GachaSave"){
        var dialog:GachaResultSaveDialog=new GachaResultSaveDialog();dialog.globalLogic=g;var view:CrazySaveView=new CrazySaveView();dialog.viewOrder=view;dialog.buttonCharacterGroup=new ButtonGroupLogic();var behavior:CloseBehavior=dialog.remoteInput(event);
        check("save/dialog-closes",behavior===CloseBehavior.Close);check("save/view-refreshed",view.refreshes==1);check("save/two-slot-button-states",dialog.buttonCharacterGroup.changes.length==2);
        for each(var change:Object in dialog.buttonCharacterGroup.changes){var slot:int=int(change.id)==16777216?1:2;var ids:Array=g.player.get_crazy_gacha_result_list().get(slot) as Array;check("save/slot-"+slot+"-enabled",change.enabled===(ids===null||ids.length==0));}
        check("save/last-kept-until-select",CommonHarness.same(wire(g.player.get_last_crazy_gacha_result_list()),beforeLast));step.slot_buttons=dialog.buttonCharacterGroup.changes;
       }else if(event.tag=="GachaSelect"){
        var select:GachaResultSelectDialog=new GachaResultSelectDialog();select.globalLogic=g;DevConfig.isCrazySelect=false;select.remoteInput(event);
        check("select/actual-last-null",g.player.get_last_crazy_gacha_result_list()===null);check("select/index-reset",select.selectIndex==-1);check("select/native-flag",DevConfig.isCrazySelect===true);check("select/navigation-boundary-once",select.navigationCalls==1);check("select/server-recovery-cleared",expected.length==0);
       }else throw new Error("Unexpected callback event "+event.tag);
       step.coverage="actual-callback-and-downstream-consumer";
      }
      state(g.player,s.expectedAfter);step.lastCrazyGachaDrawResult=wire(g.player.get_last_crazy_gacha_result_list());step.status="passed";
     }catch(error:*){step.status="failed";step.error=String(error);step.stack=error is Error?error.getStackTrace():null;throw error;}finally{row.steps.push(step);}}
     row.status="passed";row.checks.push({id:"complete-nine-step-downstream-chain",pass:true});
    }catch(error2:*){failed++;row.status="failed";row.error=String(error2);}rows.push(row);
   }
  }catch(error3:*){failed++;rows.push({id:"harness",status:"failed",error:String(error3)});}
  var output:String=String(e.arguments[1]);write(output,{status:failed?"failed":"passed",failed:failed,stage_is_null:stage===null,assertions:assertions,cases:rows,negative_controls:negative,limits:["Actual callbacks, loading/result construction, save/select dialog consumers, complete Initialize reload and Home recovery routing.","Scene/GPU/asset lookup/view/navigation/analytics boundaries are records; no actual rendering or persistent client file write.","Fresh draw passes event candidates directly; lastCrazy is reconstructed by load and cleared to null by the actual selection dialog."]});write(new File(output).parent.resolvePath("negative-control.json").nativePath,{negative_controls:negative});NativeApplication.nativeApplication.exit(failed?1:0);
 }
}
}
