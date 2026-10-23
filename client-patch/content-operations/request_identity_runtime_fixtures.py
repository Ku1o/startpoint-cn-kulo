"""Bounded I/O dependencies; tested RequestQueue bodies come from the selected SWF."""
import re
METHODS = ['startRequest', 'reset', 'requestErrorHandler', 'requestSuccessHandler', 'update', 'clearQueue', 'requestSuccessHandlerWithDelay', 'addRequest']


def prepare(stubs, cases, abc, builder):
    stubs = dict(stubs)
    includes, labels = [], []

    def put(qn, body, base=''):
        package, name = qn.split('::')
        imports = ''.join('import ' + ref + ';' for ref in sorted(set(re.findall(r'\b(?:[a-z][A-Za-z0-9_]*\.)+[A-Z][A-Za-z0-9_]*', body + base))))
        stubs[package.replace('.', '/') + '/' + name + '.as'] = 'package ' + package + ' {' + imports + 'public class ' + name + base + ' {' + body + '}}'
        includes.append(package + '.' + name)

    source = builder.view(abc)
    queue = ('public var accessCount:int=0;public var timeLeft:int=100000;public var screenSize:Object=new cn.fixture.IdentityScreenSize();'
             'public var requestState:RequestState=RequestState.None;public var remote:Object;public var refusesResponse:haxe.ds.Option=haxe.ds.Option.None;'
             'public var queue:Array=[];public var note:Object={};public var localStore:Object=new cn.fixture.IdentityLocalStore();'
             'public var fakeApiErrors:Array=[];public var failsRequest:Boolean=false;public var devConfig:pinball.config.core.DevConfig=new pinball.config.core.DevConfig();'
             'public var delaysRequest:Boolean=false;public var clock:Object=new cn.fixture.IdentityClock();'
             'public var assetDownloader:Object=new cn.fixture.IdentityDownloader();public var RETRY_LIMIT:int=5;public var RETRY_INTERVAL:int=0;')
    for method in METHODS:
        label = 'pinball.context.remote::RequestQueue/' + method + '|1'
        labels.append(label)
        index, = source.by_label[label]
        info = abc.methods[abc.bodies[index][0]]
        typ = lambda i: abc.mn_name(i).replace('::', '.') if i else '*'
        args = ','.join('p' + str(i) + ':' + typ(t) for i, t in enumerate(info[1]))
        queue += 'public function ' + method + '(' + args + '):' + typ(info[0]) + '{}'
    put('pinball.context.remote::RequestQueue', queue)
    put('pinball.context.remote::RequestSetting', 'public var basePath:String;public var endPoint:String;public var body:*;public var accessCountMode:int;public var headers:Array;public var playerIdMode:PlayerIdMode;public var successHandler:Function;public var errorHandler:Function;public var cancelHandler:Function;public function RequestSetting(base:String=null,path:String=null,data:*=null,success:Function=null,error:Function=null,cancel:Function=null,player:PlayerIdMode=null,mode:int=0){}')
    labels.append('pinball.context.remote::RequestSetting/<ctor>')
    put('pinball.context.remote::RequestState', 'public var index:int;public var params:Array;public function RequestState(i:int,p:Array){index=i;params=p;}public static var Requesting:RequestState=new RequestState(0,[]);public static var None:RequestState=new RequestState(2,[]);public static function WaitForRetry(s:RequestSetting,n:int,r:int,t:int):RequestState{return new RequestState(1,[s,n,r,t]);}')
    put('pinball.context.remote::PlayerIdMode', 'public var index:int;public var params:Array;public static var LocalStore:PlayerIdMode=new PlayerIdMode(2,[]);public function PlayerIdMode(i:int,p:Array){index=i;params=p;}')
    put('pinball.config.core::DevConfig', 'public static var loginToken:String;public var remoteFormatKind:int=0;public var assetReadKind:int=2;public var connectionTotalTimeout:int=100000;public function getServerApiPath():String{return "https://offline.invalid";}')
    put('cn.account::PlayerLogin', 'public static function attach(s:Object):void{}')
    put('cn.admission::ClientAdmission', 'public static function beforeQueue(q:Object,s:Object,r:int,t:int):Boolean{return true;}public static function inspect(q:Object,s:Object,v:Object):Boolean{return true;}')
    put('pinball.context.remote::RemoteUtil', '''public static var captures:Array=[];
public static function getURLRequest(url:String,kind:Object):flash.net.URLRequest{var r:flash.net.URLRequest=new flash.net.URLRequest(url);r.method="POST";r.requestHeaders=[new flash.net.URLRequestHeader("DEVICE","test-device"),new flash.net.URLRequestHeader("APP_VER","1.8.1"),new flash.net.URLRequestHeader("CHANNEL","offline")];return r;}
public static function startRequest(r:flash.net.URLRequest,success:Function,error:Function,n:Object,k:Object,t:int):void{var headers:Array=[];for each(var h:flash.net.URLRequestHeader in r.requestHeaders)headers.push({name:h.name,value:h.value});captures.push({url:r.url,method:r.method,headers:headers,body:JSON.parse(JSON.stringify(r.data)),success:success,error:error,format:k,timeLeft:t});}''')
    put('pinball.context.remote::RemoteError', 'public var kind:RemoteErrorKind;public var causeUrl:String;public var retryable:Boolean=true;public var displayMessage:String="ordinary";public var internalMessage:String="ordinary";public function RemoteError(k:RemoteErrorKind,u:String=""){kind=k;causeUrl=u;}public function shouldRetry():Boolean{return retryable;}')
    errors = ['Debug', 'FailureResult', 'WholeMaintenanceError', 'TaskMaintenanceError', 'ApplicationVersionError', 'ResourceVersionError', 'PreparationMaintenanceError', 'TaskMaintenanceToDefineIndividualProcessError', 'UserDataEraseError', 'ApplicationCommonError']
    put('pinball.context.remote::RemoteErrorKind', 'public var index:int=0;public var tag:String;public var params:Array;public function RemoteErrorKind(t:String,i:int,p:Array){tag=t;index=i;params=p;}public static var Timeout:RemoteErrorKind=new RemoteErrorKind("Timeout",99,[]);' + ''.join('public static function ' + n + '(...p):RemoteErrorKind{return new RemoteErrorKind("' + n + '",0,p);}' for n in errors))
    put('pinball.context.remote::UserDataEraseRequestStatusKind', 'public static var RequestPeriodExpired:Object={};public static var Executed:Object={};public static function Requesting(v:Object):Object{return v;}')
    put('pinball.context.activity::ActivityUtil', 'public static function runInActive(f:Function):void{f();}')
    put('pinball.common.task::Delay', 'public static var scheduled:Array=[];public static function delay(f:Function,frames:int):void{scheduled.push(f);}')
    put('pinball.remote.attention::AttentionRemoteUtil', 'public static function isIgnorableEndPointAndError(e:String,r:Object):Boolean{return false;}')
    put('pinball.remote.common::ResponseData', 'public var header:Object={servertime:haxe.ds.Option.None};public var raw:Object;public function ResponseData(v:Object){raw=v;}')
    put('pinball.context.localStore::LocalStore', '')
    put('pinball.context.screenSize::ImageScale', 'public var index:int=1;')
    put('cn.fixture::IdentityScreenSize', 'public namespace NativeSize="pinball.context.screenSize:ScreenSizeForSection";NativeSize function get_imageScale():pinball.context.screenSize.ImageScale{return new pinball.context.screenSize.ImageScale();}')
    put('cn.fixture::IdentityLocalStore', 'public namespace NativeStore="pinball.context.localStore:LocalStoreForSection";NativeStore function get_account():pinball.context.localStore.LocalStore{return new pinball.context.localStore.LocalStore();}')
    put('cn.fixture::IdentityDownloader', 'public namespace NativeDownloader="pinball.context.assetDownloader:AssetDownloaderForSection";NativeDownloader function getResourceVersion():haxe.ds.Option{return haxe.ds.Option.Some("9.9");}')
    put('cn.fixture::IdentityClock', 'public namespace NativeClock="pinball.context.clock:ClockForRemote";NativeClock function applyServerTime(v:Number):void{}')
    put('pinball.context.localStore._AccountLocalStore::AccountLocalStore_Impl_', 'public static function get(v:Object):haxe.ds.Option{return haxe.ds.Option.Some({viewerId:123,udid:"device-id",shortUdid:"short-id"});}')
    for name, args, call in [('BindImpl2_1', 1, 'v:Object'), ('BindImpl3_1', 2, 'v:Object'), ('BindImpl4_1', 3, 'v:Object'), ('BindImpl1_0', 1, ''), ('BindImpl3_0', 3, ''), ('BindImpl6_0', 6, '')]:
        params = ','.join('p' + str(i) + ':*' for i in range(args))
        values = ','.join('p' + str(i) for i in range(args))
        put('pinball.common.tools._FunctionTools::' + name, 'public var fn:Function;public var args:Array;public function ' + name + '(f:Function,' + params + '){fn=f;args=[' + values + '];}public function execute(' + call + '):void{fn.apply(null,args' + ('.concat([v])' if call else '') + ');}')
    factory = ('public var remote:Object;public function earlySuccessHandler(f:Function,v:pinball.remote.common.ResponseData):void{f(v);}'
               'public function defaultErrorHandler(v:pinball.context.remote.RemoteError):void{}public function defaultCancelHandler():void{}')
    for method in ['startUserRequest', 'startUserRequestDetail', 'resolveAccessCountMode']:
        label = 'pinball.context.remote.real::RealRemoteService/' + method + '|1'
        labels.append(label)
        index, = source.by_label[label]
        info = abc.methods[abc.bodies[index][0]]
        args = ','.join('p' + str(i) + ':' + typ(t) for i, t in enumerate(info[1]))
        factory += 'public function ' + method + '(' + args + '):' + typ(info[0]) + '{' + ('return 0;' if typ(info[0]) == 'int' else '') + '}'
    put('pinball.context.remote.real::RealRemoteService', factory)
    stubs['pinball/common/data/config/ConfigProvider.as'] = 'package pinball.common.data.config {public interface ConfigProvider {function getConfig():ConfigLogic;}}'
    stubs['pinball/context/global/GlobalLogicForRemote.as'] = 'package pinball.context.global {import pinball.common.data.config.ConfigProvider;public interface GlobalLogicForRemote extends ConfigProvider {}}'
    put('cn.fixture::IdentityGlobal', 'public function getConfig():pinball.common.data.config.ConfigLogic{return new pinball.common.data.config.ConfigLogic();}', ' implements pinball.context.global.GlobalLogicForRemote')
    put('pinball.common.data.config::ConfigLogic', 'public var accessCountModeTable:Object=new cn.fixture.IdentityModeMap();public function getAccessCountMode(p:String):int{return 0;}')
    labels.append('pinball.common.data.config::ConfigLogic/getAccessCountMode|1')
    stubs['pinball/master/runtime/MasterMap.as'] = 'package pinball.master.runtime {public interface MasterMap {function exists(k:Object):Boolean;function get(k:Object):Object;}}'
    put('cn.fixture::IdentityModeMap', 'public function exists(k:Object):Boolean{return false;}public function get(k:Object):Object{return new pinball.master.generated.AccessCountModeValues();}', ' implements pinball.master.runtime.MasterMap')
    put('pinball.master.generated::AccessCountModeValues', 'public var mode:int=2;')
    stubs['flash/Boot.as'] = stubs['flash/Boot.as'].replace('public static var lastError:Error;', 'public static var lastError:Error;public static var skip_constructor:Boolean=false;')
    return stubs, labels, includes


BODY = r'''
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
function stablePayload(c:Object):String{var b:Object=JSON.parse(JSON.stringify(c.body));delete b.api_count;delete b.retry_count;var hs:Array=[];for each(var h:Object in c.headers)if(h.name!="LOGIN_TOKEN")hs.push(h);return JSON.stringify({url:c.url,method:c.method,body:b,headers:hs,format:c.format});}
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
'''
