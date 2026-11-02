package pinball.remote.initialize {
import fixture.CommonHarness;
import haxe.ds.Option;
import pinball.common.data.save.restore.RestoreState;
import pinball.context.remote.PlayerIdMode;
import pinball.context.remote.real.RealRemoteService;
import pinball.context.restore.RestoreForRemote;
import pinball.remote.common.ResponseData;
public dynamic class InitializeRealRemote extends RealRemoteService {
public var userDataEraseRequestingHandler:Function;
public var rightAfterSignUp:Boolean;
public var restore:RestoreForRemote;
public var reloadLoading:Boolean;
public var playerIdMode:PlayerIdMode;
public var isTestMode:Boolean;
public var completeHandler:Function;
public var authUdid:Option;
public var applicationVersionErrorHandler:Function;
public var applicationCommonErrorHandler:Function;
public var agreementVersionErrorHandler:Function;
public var fixtureStoredData:Object;
public function InitializeRealRemote(){super();}
public function loadSuccessHandler(p0:String,p1:ResponseData):void{}
public function restoreFinishedHandler(p0:Object,p1:Object,p2:RestoreState):void{}
public function translateFavoriteParty(p0:Object):Option{return null;}
public static function extractPartyId(p0:Object):int{return 0;}
public function getStoredData():Object{return fixtureStoredData;}
public function loginReport(response:ResponseData):void{CommonHarness.events.push({kind:"recorded-login-analytics"});}
}}