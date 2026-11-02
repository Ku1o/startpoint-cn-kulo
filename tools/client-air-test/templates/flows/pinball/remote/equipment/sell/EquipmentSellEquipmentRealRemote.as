package pinball.remote.equipment.sell {
import pinball.context.input.HookEntrance;
import pinball.context.remote.real.RealRemoteService;
import pinball.remote.common.ResponseData;
public dynamic class EquipmentSellEquipmentRealRemote extends RealRemoteService {
public var sellId:int;
public var dispatcher:HookEntrance;
public function EquipmentSellEquipmentRealRemote(){super();}
public function successHandler(p0:ResponseData):void{}
}}