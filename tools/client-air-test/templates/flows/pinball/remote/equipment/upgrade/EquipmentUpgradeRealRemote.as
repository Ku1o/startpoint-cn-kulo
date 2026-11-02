package pinball.remote.equipment.upgrade {
import haxe.ds.Option;
import pinball.context.input.HookEntrance;
import pinball.context.remote.real.RealRemote;
import pinball.context.remote.real.RealRemoteService;
import pinball.remote.common.ResponseData;
public dynamic class EquipmentUpgradeRealRemote extends RealRemoteService {
public var dispatcher:HookEntrance;
// Fixture initialization only. This constructor is not an imported test target.
public function EquipmentUpgradeRealRemote(p0:RealRemote=null,p1:HookEntrance=null,p2:int=0,p3:Boolean=false,p4:Option=null,p5:int=0){super(p0);dispatcher=p1;}
public function successHandler(p0:ResponseData):void{}
}}
