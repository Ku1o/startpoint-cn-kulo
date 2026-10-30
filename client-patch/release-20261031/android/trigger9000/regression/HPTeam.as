package {import pinball.scene.battle.battle.squad.member.MemberImpl;import haxe.ds.Option;public class HPTeam {
 public var primary:Boolean=true;public var members:Array;
 public function HPTeam(m:MemberImpl,o:MemberImpl){members=[Option.Some(m),Option.Some(o)];}
 public function isPrimary():Boolean{return primary;}
}}
