package {import haxe.ds.Option;public class Ports {
 public var member:Object;public var stats:Object;public var escapeCalls:int=0;public var vx:Number=12;public var vy:Number=-4;
 public var statsCalls:int=0;public var lastStat:int;public var lastDelta:int;
 public function Ports(m:Object=null){member=m;stats=this;}
 public namespace Squad="pinball.scene.battle.battle.squad:Squad";
 Squad function getMember(i:int):Option{return i==0?Option.Some(member):null;}
 public namespace Zone="pinball.scene.battle.battle.zone:ZoneManager";
 Zone function getCurrentZone():Object{return this;}
 public namespace Body="pinball.scene.battle.battle.physics:MechanicalBody";
 Body function set_vx(v:Number):Number{vx=v;return v;}
 Body function set_vy(v:Number):Number{vy=v;return v;}
 public function add(k:int,n:int):void{statsCalls++;lastStat=k;lastDelta=n;}
 public function set(v:Number):void{escapeCalls++;}
}}
