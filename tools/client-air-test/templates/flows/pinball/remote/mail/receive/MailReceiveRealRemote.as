package pinball.remote.mail.receive {
import haxe.IMap;
import pinball.context.input.HookEntrance;
import pinball.context.remote.real.RealRemoteService;
import pinball.remote.common.ResponseData;
public dynamic class MailReceiveRealRemote extends RealRemoteService {
public var mailId:int;
public var dispatcher:HookEntrance;
public var beforeExBoostItemList:IMap;
public var beforeCharacterList:IMap;
public function MailReceiveRealRemote(){super();}
public function successHandler(p0:ResponseData):void{}
}}