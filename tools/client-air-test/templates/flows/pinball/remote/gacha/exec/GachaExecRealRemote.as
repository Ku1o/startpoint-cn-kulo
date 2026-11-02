package pinball.remote.gacha.exec {
import fixture.CommonHarness;
import haxe.IMap;
import pinball.common.data.player.PlayerLogic;
import pinball.context.input.HookEntrance;
import pinball.context.remote.real.RealRemote;
import pinball.context.remote.real.RealRemoteService;
import pinball.remote.common.ResponseData;
public dynamic class GachaExecRealRemote extends RealRemoteService {
public var dispatcher:HookEntrance;
public var beforeStarCrumb:int;
public var beforeItemMap:IMap;
public var beforeEquipmentIds:Array;
public var beforeCharacterIds:Array;
public function GachaExecRealRemote(r:RealRemote=null,h:HookEntrance=null,g:int=0,t:int=0,p:int=0,n:int=0){super(r);}
public function startUserRequest(route:String,body:Object,callback:Function):void{CommonHarness.events.push({kind:"recorded-gacha-request",route:route,body:body});}
public function successHandler(p0:ResponseData):void{}
public function getItemDiff(p0:PlayerLogic):IMap{return null;}
public function isNew(p0:Array,p1:Object):Boolean{return false;}
}}