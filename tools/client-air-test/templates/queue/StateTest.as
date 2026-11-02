package {
import flash.display.Sprite;import flash.utils.getTimer;import flash.net.URLRequestHeader; import flash.filesystem.File; import flash.filesystem.FileStream; import flash.filesystem.FileMode;
import flash.utils.getDefinitionByName;import flash.desktop.NativeApplication; import cn.content.ContentOperationsState;
import flash.events.InvokeEvent;
import haxe.ds.Option; import haxe.ds.IntMap; import pinball.common.data.quest.event.EventIdKind;
import pinball.common.data.quest.event.challengeDungeon.ChallengeDungeonEventLogic;
import pinball.master.generated.PassCardEventTable;
import pinball.common.time.TimeRange;import pinball.common.data.boxGacha.BoxGachaLogic;import pinball.common.data.shop.EventItemShopProductLogic;
import pinball.common.data.player.ShopProductBuyableState;import pinball.common.tools.DateUtil;
import pinball.context.Logic;import pinball.context.remote.RemoteError;import pinball.context.remote.RemoteErrorKind;import pinball.context.remote.RemoteCommonInput;
import pinball.context.scene.ReloadTestScene;import pinball.debug.CrashUtil;
public class StateTest extends Sprite {
private var assertions:int=0;
private var checks:Array=[];
private var nativeObservations:Array=[];
private function check(v:Boolean,n:String):void {if(!v)throw new Error(n);assertions++;checks.push({name:n,pass:true});}
private function row(key:String,open:Boolean,q:Array=null,end:Object=null):Object{return {key:key,instance_id:key+":original",visible:open,enter:open,claim:false,exchange:open,permanent:end===null,ends_at_ms:end,quest_keys:q};}
private function snap(rev:int,rows:Array,catalog:Array=null):void {ContentOperationsState.applySnapshot({schema_version:1,full_snapshot:true,revision:rev,catalog_digest:new Array(65).join("a"),server_time_ms:1000,states:rows,catalog:catalog});}
private function action(open:Boolean,end:Object=null,q:Array=null,m:Array=null):Object{return {enabled:open,ends_at_ms:end,quest_keys:q,mission_keys:m};}
private function row2(key:String,actions:Object):Object{return {key:key,instance_id:key+":original",actions:actions};}
private function snap2(rev:int,rows:Array,entries:Array=null):void {ContentOperationsState.applySnapshot({schema_version:2,full_snapshot:true,revision:rev,catalog_digest:new Array(65).join("a"),server_time_ms:1000,states:rows,catalog:entries});}
public function StateTest() {NativeApplication.nativeApplication.addEventListener(InvokeEvent.INVOKE,run);}
private function run(invocation:InvokeEvent):void {
var force:Array=[Option,IntMap,EventIdKind,ChallengeDungeonEventLogic,PassCardEventTable,TimeRange,BoxGachaLogic,EventItemShopProductLogic,ShopProductBuyableState,DateUtil];
var result:Object;
try {function normalized(v:*):*{if(v is Array){var a:Array=[];for each(var x:* in v)a.push(normalized(x));return a;}if(v!==null && typeof v=="object"){var keys:Array=[];for(var k:String in v)if(v.hasOwnProperty(k))keys.push(k);keys.sort();var pairs:Array=[];for each(k in keys)pairs.push([k,normalized(v[k])]);return {objectPairs:pairs};}return v;}

var Queue:Class=getDefinitionByName("pinball.context.remote::RequestQueue") as Class;
var Setting:Class=getDefinitionByName("pinball.context.remote::RequestSetting") as Class;
var Config:Class=getDefinitionByName("pinball.config.core::DevConfig") as Class;
var RemoteIO:Class=getDefinitionByName("pinball.context.remote::RemoteUtil") as Class;
var RemoteErrorType:Class=getDefinitionByName("pinball.context.remote::RemoteError") as Class;
var ErrorKind:Class=getDefinitionByName("pinball.context.remote::RemoteErrorKind") as Class;
var PlayerMode:Class=getDefinitionByName("pinball.context.remote::PlayerIdMode") as Class;
function setting(mode:int=2):Object{var s:Object=new Setting("https://offline.invalid","gacha/exec",{gacha_id:100,type:14,payment_type:3,number_of_exec:1,nested:{value:"unchanged"}},function(v:Object):void{},function(v:Object):void{},function():void{},PlayerMode.LocalStore,mode);s.headers=[new flash.net.URLRequestHeader("CUSTOM","retained")];return s;}
function headerValue(c:Object,name:String):Object{for each(var h:Object in c.headers)if(h.name==name)return h.value;return null;}
function lastCapture():Object{return RemoteIO.captures[RemoteIO.captures.length-1];}
function stablePayload(c:Object):String{var b:Object=JSON.parse(JSON.stringify(c.body));delete b.api_count;delete b.retry_count;var hs:Array=[];for each(var h:Object in c.headers)if(h.name!="LOGIN_TOKEN")hs.push(h);return JSON.stringify(normalized({url:c.url,method:c.method,body:b,headers:hs,format:c.format}));}
var q:Object=new Queue();q.accessCount=7;Config.loginToken="login-A";
var oldSetting:Object=setting();q.startRequest(oldSetting,0,flash.utils.getTimer());var first:Object=lastCapture();
check(first.body.api_count===7 && headerValue(first,"LOGIN_TOKEN")==="login-A","first send reads current native identity");
check(first.body.viewer_id===123 && first.body.nested.value==="unchanged","original body and viewer injection retained");
check(headerValue(first,"DEVICE")==="test-device" && headerValue(first,"APP_VER")==="1.8.1" && headerValue(first,"CHANNEL")==="offline","original transport base headers retained");
check(headerValue(first,"CUSTOM")==="retained" && headerValue(first,"RES_VER")==="9.9" && headerValue(first,"UDID")==="device-id" && headerValue(first,"SHORT_UDID")==="short-id" && headerValue(first,"RESOLUTION")==="small","original custom/resource/account/resolution headers retained");
var originalPayload:String=stablePayload(first);
q.accessCount=90;Config.loginToken="login-B";q.startRequest(oldSetting,1,flash.utils.getTimer());var retry:Object=lastCapture();
check(retry.body.api_count===7 && headerValue(retry,"LOGIN_TOKEN")==="login-A","same logical RequestSetting retry retains first token and api_count");
check(retry.body.retry_count===1 && stablePayload(retry)===originalPayload,"retry_count changes while other original headers/body remain identical");
var fresh:Object=setting();q.startRequest(fresh,0,flash.utils.getTimer());var newCapture:Object=lastCapture();
check(newCapture.body.api_count===90 && headerValue(newCapture,"LOGIN_TOKEN")==="login-B","new logical RequestSetting reads new signup token and current api_count");
q.reset();check(q.accessCount===0 && q.queue.length===0 && q.requestState.index===2 && q.refusesResponse.index===1,"actual native reset semantics unchanged");
Config.loginToken="login-C";
// Invoke the captured error callback from the old in-flight request after reset.
first.error(new RemoteErrorType(ErrorKind.Timeout,"offline"));
check(q.requestState.index===1 && q.requestState.params[0]===oldSetting,"actual old callback schedules retry with the same RequestSetting");
q.update();var afterReset:Object=lastCapture();
check(afterReset.body.api_count===7 && headerValue(afterReset,"LOGIN_TOKEN")==="login-A","old callback across queue reset cannot relabel request with new login nonce/count");
check(afterReset.body.retry_count===1 && stablePayload(afterReset)===originalPayload,"cross-reset retry preserves every other original header/body field");
var afterResetSetting:Object=setting();q.startRequest(afterResetSetting,0,flash.utils.getTimer());
check(lastCapture().body.api_count===0 && headerValue(lastCapture(),"LOGIN_TOKEN")==="login-C","new setting after reset receives fresh login nonce/current zero counter");
// Both the original null guard and original header value read are frozen.
Config.loginToken=null;q.accessCount=11;var noToken:Object=setting();q.startRequest(noToken,0,flash.utils.getTimer());
check(headerValue(lastCapture(),"LOGIN_TOKEN")===null,"initial null login token emits no login header");
Config.loginToken="login-D";q.accessCount=12;q.startRequest(noToken,2,flash.utils.getTimer());
check(headerValue(lastCapture(),"LOGIN_TOKEN")===null && lastCapture().body.api_count===11,"null first identity stays null on retry after login");
var d:Object=setting();q.startRequest(d,0,flash.utils.getTimer());
check(headerValue(lastCapture(),"LOGIN_TOKEN")==="login-D" && lastCapture().body.api_count===12,"fresh setting after null-token request independently receives new identity");
// Reverse transition is just as important: a retry must keep the original header.
Config.loginToken=null;q.accessCount=13;q.startRequest(d,3,flash.utils.getTimer());
check(headerValue(lastCapture(),"LOGIN_TOKEN")==="login-D" && lastCapture().body.api_count===12,"nonnull first token remains present when current global token becomes null");
// Content snapshot lifecycle must not erase transport identities.
ContentOperationsState.applySnapshot({schema_version:2,revision:999,full_snapshot:true,states:[]});q.startRequest(d,4,flash.utils.getTimer());
check(headerValue(lastCapture(),"LOGIN_TOKEN")==="login-D" && lastCapture().body.api_count===12,"content snapshot replacement cannot clear request identities");
// Exercise original success semantics and signup/load modes, not reconstructed logic.
var successes:int=0;var successSetting:Object=setting();successSetting.successHandler=function(v:Object):void{successes++;};q.accessCount=20;
q.startRequest(successSetting,0,flash.utils.getTimer());lastCapture().success({data:{}});
check(q.accessCount===21 && q.requestState.index===2 && successes===1,"actual mode2 success increments counter and dispatches success once");
q.startRequest(successSetting,1,flash.utils.getTimer());check(lastCapture().body.api_count===20,"same setting stays frozen even after native success counter increment");
for each(var countMode:int in [0,1]){
 var nonCount:Object=setting(countMode);q.accessCount=30;Config.loginToken="mode-"+countMode;q.startRequest(nonCount,0,flash.utils.getTimer());
 check(!lastCapture().body.hasOwnProperty("api_count"),"original mode"+countMode+" request does not gain an api_count field");
 lastCapture().success({data:{}});check(q.accessCount===(countMode==0?30:1),"original mode"+countMode+" success counter semantics unchanged");
}
// Original explicit RES_VER wins; NO_ASSET_UPDATE is also unchanged.
var explicit:Object=setting();explicit.headers.push(new flash.net.URLRequestHeader("RES_VER","explicit"));q.startRequest(explicit,0,flash.utils.getTimer());
check(headerValue(lastCapture(),"RES_VER")==="explicit","explicit resource header retains native precedence");
q.devConfig.assetReadKind=0;var localAsset:Object=setting();q.startRequest(localAsset,0,flash.utils.getTimer());
check(headerValue(lastCapture(),"NO_ASSET_UPDATE")==="" && headerValue(lastCapture(),"RES_VER")===null,"native local-asset header branch unchanged");
var queue2:Object=new Queue();queue2.accessCount=55;Config.loginToken="other-queue";queue2.startRequest(oldSetting,5,flash.utils.getTimer());
check(lastCapture().body.api_count===7 && headerValue(lastCapture(),"LOGIN_TOKEN")==="login-A","identity follows RequestSetting even if queue instance changes");
var signupSetting:Object=setting(0);Config.loginToken="signup-old";q.startRequest(signupSetting,0,flash.utils.getTimer());Config.loginToken="signup-new";
q.startRequest(signupSetting,1,flash.utils.getTimer());check(headerValue(lastCapture(),"LOGIN_TOKEN")==="signup-old","signup-mode setting retry retains old token without introducing api_count");
var loadSetting:Object=setting(1);q.startRequest(loadSetting,0,flash.utils.getTimer());check(headerValue(lastCapture(),"LOGIN_TOKEN")==="signup-new","new load logical setting receives newly returned signup login token");
// Actual factory -> native RequestSetting constructor -> native queue.add/update/start.
var Factory:Class=getDefinitionByName("pinball.context.remote.real::RealRemoteService") as Class;
var GlobalDependency:Class=getDefinitionByName("cn.fixture::IdentityGlobal") as Class;
var factory:Object=new Factory(),factoryQueue:Object=new Queue();factory.remote={requestQueue:factoryQueue,devConfig:new Config(),globalLogic:new GlobalDependency()};
var logicalSuccesses:int=0;var logicalSuccess:Function=function(v:Object):void{logicalSuccesses++;};factoryQueue.accessCount=100;Config.loginToken="factory-login";
factory.startUserRequest("gacha/exec",{gacha_id:100,type:14,payment_type:3,number_of_exec:1},logicalSuccess);var drawOne:Object=lastCapture();
check(drawOne.body.api_count===100 && drawOne.body.type===14 && drawOne.body.payment_type===3 && drawOne.body.number_of_exec===1,"native request factory sends first exact Crazy 14/3/1 request");
var sentBeforeSecond:int=RemoteIO.captures.length;
factory.startUserRequest("gacha/exec",{gacha_id:100,type:14,payment_type:3,number_of_exec:1},logicalSuccess);
check(factoryQueue.queue.length===1 && RemoteIO.captures.length===sentBeforeSecond,"second native factory request queues behind in-flight request without freezing an early count");
var queuedSecond:Object=factoryQueue.queue[0];
drawOne.success({data:{}});check(factoryQueue.accessCount===101 && logicalSuccesses===1,"actual queue success increments counter before a new logical draw");
factoryQueue.update();var drawTwo:Object=lastCapture();
check(drawTwo.body.api_count===101 && headerValue(drawTwo,"LOGIN_TOKEN")==="factory-login","second same-path same-body logical draw receives fresh current api_count");
check(drawOne.error!==drawTwo.error,"native factory produces independent bound callback identities");
// Retry the first factory-created object: it must keep its first identity.
drawOne.error(new RemoteErrorType(ErrorKind.Timeout,"offline"));var settingOne:Object=factoryQueue.requestState.params[0];factoryQueue.update();
check(lastCapture().body.api_count===100,"first factory-created logical request retry keeps first count after second draw starts");
drawTwo.error(new RemoteErrorType(ErrorKind.Timeout,"offline"));var settingTwo:Object=factoryQueue.requestState.params[0];factoryQueue.update();
check(settingOne!==settingTwo && settingTwo===queuedSecond && settingOne.body!==settingTwo.body,"native startUserRequestDetail constructs distinct RequestSetting and body objects for consecutive draws");
check(lastCapture().body.api_count===101,"second factory-created request retry keeps its own count");
lastCapture().success({data:{}});check(factoryQueue.accessCount===102 && logicalSuccesses===2,"second logical draw success retains native monotonic counter semantics");
factory.startUserRequest("gacha/crazy_gacha_save",{index:1},logicalSuccess);var saveRequest:Object=lastCapture();check(saveRequest.body.api_count===102 && saveRequest.body.index===1,"same native factory assigns a fresh identity to save endpoint");saveRequest.success({data:{}});
factory.startUserRequest("gacha/crazy_gacha_select",{index:0,gacha_id:100},logicalSuccess);check(lastCapture().body.api_count===103 && lastCapture().body.index===0,"same native factory assigns next fresh identity to final select endpoint");

// Extra bounded failure-path checks. Transport classification and activity are
// explicit recorders; actual queue retry/control/cancel methods are executed.
var errorsSeen:int=0,cancelSeen:int=0;
var failQ:Object=new Queue();failQ.devConfig.connectionTotalTimeout=100000;
var retrySetting:Object=setting();retrySetting.errorHandler=function(e:Object):void{errorsSeen++;};
failQ.startRequest(retrySetting,0,flash.utils.getTimer());
for(var retryStep:int=0;retryStep<5;retryStep++){
 lastCapture().error(new RemoteErrorType(ErrorKind.Timeout,"offline"));
 check(failQ.requestState.index===1 && failQ.requestState.params[0]===retrySetting && failQ.requestState.params[2]===retryStep+1,"actual retry limit step "+retryStep+" retains setting and count");
 failQ.update();
}
var queuedCancel:Object=setting();queuedCancel.cancelHandler=function():void{cancelSeen++;};failQ.queue.push(queuedCancel);
lastCapture().error(new RemoteErrorType(ErrorKind.Timeout,"offline"));
check(errorsSeen===1 && cancelSeen===1 && failQ.queue.length===0 && failQ.requestState.index===2,"retry exhaustion reports failure once and cancels queued request");
var timeoutQ:Object=new Queue();timeoutQ.devConfig.connectionTotalTimeout=1;var timeoutSetting:Object=setting();
timeoutSetting.errorHandler=function(e:Object):void{errorsSeen++;};
timeoutQ.requestErrorHandler(timeoutSetting,0,flash.utils.getTimer()-100,new RemoteErrorType(ErrorKind.Timeout,"offline"));
check(errorsSeen===2 && timeoutQ.requestState.index===2 && timeoutQ.timeLeft<=0,"actual total timeout refuses another retry");
var nonretry:Object=new RemoteErrorType(ErrorKind.Timeout,"offline");nonretry.retryable=false;
var terminalQ:Object=new Queue();var terminalSetting:Object=setting();terminalSetting.errorHandler=function(e:Object):void{errorsSeen++;};
terminalQ.requestErrorHandler(terminalSetting,0,flash.utils.getTimer(),nonretry);
check(errorsSeen===3 && terminalQ.requestState.index===2,"nonretryable classification follows terminal queue path");
result={passed:true,assertions:assertions,checks:checks,actualRequestQueueMethods:8,actualFactoryAndConstructorMethods:5,gameExecuted:false,deviceTested:false};
} catch(e:Error) {result={passed:false,assertions:assertions,error:e.toString(),stack:e.getStackTrace(),nativeObservations:nativeObservations};}
result.status=result.passed?"passed":"failed";result.failed=result.passed?0:1;result.stage_is_null=stage===null;
result.cases=[{id:"request-identity",status:result.status,assertions:assertions,checks:checks,error:result.error}];
var file:File=new File(String(invocation.arguments[1]));var stream:FileStream=new FileStream();stream.open(file,FileMode.WRITE);stream.writeUTFBytes(JSON.stringify(result));stream.close();NativeApplication.nativeApplication.exit(result.passed?0:1);
}}
}
