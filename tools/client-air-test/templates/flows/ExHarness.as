package {
import fixture.CommonHarness;
import fixture.FlowHook;
import fixture.FlowRestore;
import flash.desktop.NativeApplication;
import flash.display.Sprite;
import flash.events.InvokeEvent;
import flash.filesystem.File;
import flash.filesystem.FileMode;
import flash.filesystem.FileStream;
import haxe.IMap;
import haxe.ds.IntMap;
import haxe.ds.Option;
import pinball.common.data.player.PlayerLogic;
import pinball.context.HookForSection;
import pinball.context.remote.NewsInterruptFlagSender;
import pinball.remote.common.ResponseData;
import pinball.remote.initialize.InitializeRealRemote;






















































































































































































public class ExHarness extends Sprite {

 public function ExHarness(){NativeApplication.nativeApplication.addEventListener(InvokeEvent.INVOKE,start);}
 private function serial(v:*):* {if(v is IMap)return serial(CommonHarness.objectMap(v));if(v is Option)return {tag:v.tag,index:v.index,params:serial(v.params)};if(v is Array){var a:Array=[];for each(var i:* in v)a.push(serial(i));return a;}if(v!==null&&typeof v=="object"){var o:Object={};for(var k:String in v)o[k]=serial(v[k]);return o;}return v;}
 private function subset(actual:*,expected:*,path:String="root"):void {if(expected is Array){if(!(actual is Array)||actual.length!=expected.length)throw new Error(path+" array mismatch");for(var i:int=0;i<expected.length;i++)subset(actual[i],expected[i],path+"["+i+"]");}else if(expected!==null&&typeof expected=="object"){for(var k:String in expected){if(actual===null||actual===undefined||!actual.hasOwnProperty(k))throw new Error(path+" missing "+k);subset(actual[k],expected[k],path+"."+k);}}else if(actual!==expected)throw new Error(path+" "+actual+" != "+expected);}
 private function start(e:InvokeEvent):void {
  var rows:Array=[];var failed:int=0;CommonHarness.installHaxeArrayContract();Object(Math)["isNaN"]=function(v:Number):Boolean{return isNaN(v);};Object(Math)["isFinite"]=function(v:Number):Boolean{return isFinite(v);};var fs:FileStream=new FileStream();fs.open(new File(String(e.arguments[0])),FileMode.READ);var input:Object=JSON.parse(fs.readUTFBytes(fs.bytesAvailable));fs.close();if(input.schemaVersion!==2)throw new Error("Expected fixtures schemaVersion 2");
  for each(var c:Object in input.cases)if(c.group=="ex")for each(var s:Object in c.steps)if(String(s.route).indexOf("/load")>=0){
   var row:Object={id:s.id,caseId:c.id,sourceNewProcess:s.newProcess};
   try {
    var probe:IMap=new IntMap();probe.set(1,{x:1});row.interfaceSetProbe=true;var method:InitializeRealRemote=new InitializeRealRemote();var h:FlowHook=new FlowHook();method.hook=new HookForSection();method.hook.dispatcher=h;method.newsInterruptFlagSender=new NewsInterruptFlagSender();method.fixtureStoredData={viewerId:s.request.body.viewer_id};var restore:FlowRestore=new FlowRestore();method.restore=restore;
    var calls:int=0;var complete:Object;method.completeHandler=function(value:Object):void{calls++;complete=value;};
    CommonHarness.events=[];var response:ResponseData=new ResponseData(s.response,true);method.loadSuccessHandler("fixture-input",response);
    if(calls!=1)throw new Error("completeHandler count "+calls);
    var pending:Option=complete.exBoostDrawResult;var expected:Object=s.response.data.ex_boost_draw_result;
    if(expected===null){if(pending.index!=1)throw new Error("pending EX not cleared");}else{if(pending.index!=0)throw new Error("pending EX not restored");subset(pending.params[0],expected,"pending EX");}
    var player:PlayerLogic=CommonHarness.createPlayer(s.before);player.saveData=complete.player;var state:Object=CommonHarness.snapshot(player);
    row.state=state;row.pending=serial(pending);row.completeCalled=calls;row.restoreState=serial(complete.restoreState);
    // Full load retains explicit zero entries from the wire; incremental common
    // updates remove them. Preserve raw state and prove both wire fidelity and
    // server positive-stock projection without mutating the target state.
    if(!CommonHarness.same(state.items,s.response.data.item_list))throw new Error("full load item map differs from actual wire");
    var nonzero:Object={};for(var itemId:String in state.items)if(state.items[itemId]!==0)nonzero[itemId]=state.items[itemId];
    if(!CommonHarness.same(nonzero,s.expectedAfter.items))throw new Error("full load nonzero item projection differs from server state");
    row.nonzeroItemProjection=nonzero;row.depletedMaterialQuantity=player.getItemNumber(10001);if(row.depletedMaterialQuantity!==0)throw new Error("last EX material was not depleted");
    for each(var key:String in ["equipments","characters","crazyGachaResultList"])if(!CommonHarness.same(state[key],s.expectedAfter[key]))throw new Error("restored state mismatch "+key);
    subset(state.userInfo,s.expectedAfter.userInfo,"restored userInfo");
    var restored:Object=complete.restoreState;
    row.restoreState={tag:restored.tag,index:restored.index,params:serial(restored.params)};
    var expectedBranch:String=s.expectedRestoreState?String(s.expectedRestoreState):(s.response.data.user_tutorial!==null?"Tutorial":"None");if(restored.tag!=expectedBranch)throw new Error("restore branch "+restored.tag+" != "+expectedBranch);row.expectedRestoreState=expectedBranch;
    row.checks=[{id:"complete-handler-exactly-once",pass:calls===1},{id:"pending-wire-and-confirmed-player-separate",pass:true},{id:"raw-wire-item-map-and-nonzero-server-state",pass:true},{id:"requested-restore-branch",pass:restored.tag===expectedBranch}];row.steps=[];row.status="passed";row.state=state;row.pending=serial(pending);row.restoreExternalCalls=restore.calls;row.events=serial(h.events);row.completeCalled=calls;
   } catch(err:*){failed++;row.status="failed";row.error=String(err);row.externalEvents=serial(CommonHarness.events);row.hookEvents=h?serial(h.events):null;row.stack=err is Error?err.getStackTrace():null;}
   rows.push(row);
  }
  fs.open(new File(String(e.arguments[1])),FileMode.WRITE);fs.writeUTFBytes(JSON.stringify({status:failed?"failed":"passed",failed:failed,stage_is_null:stage===null,cases:rows,limits:"Complete actual InitializeRealRemote.loadSuccessHandler and restoreFinishedHandler; recorded external config/store/restore boundaries; only supplied load paths, no live game or iOS."}));fs.close();NativeApplication.nativeApplication.exit(failed?1:0);
 }
}
}
