package pinball.remote.exBoost {
import pinball.context.input.HookEntrance;
import pinball.context.remote.real.RealRemoteService;
import pinball.remote.common.ResponseData;
public dynamic class ExBoostSelectRealRemote extends RealRemoteService {
public var isConfirm:Boolean;
public var dispatcher:HookEntrance;
public var characterId:int;
public function ExBoostSelectRealRemote(){super();}
public function successHandler(p0:ResponseData):void{}
}}