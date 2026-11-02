package pinball.remote.mail.receiveAll {
import haxe.IMap;
import pinball.context.input.HookEntrance;
import pinball.context.remote.real.RealRemoteService;
import pinball.remote.common.ResponseData;
public dynamic class MailReceiveAllRealRemote extends RealRemoteService {
public var mailIds:Array;
public var dispatcher:HookEntrance;
public var beforeCharacterList:IMap;
public function MailReceiveAllRealRemote(){super();}
public function successHandler(p0:ResponseData):void{}
}}