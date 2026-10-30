package {import pinball.scene.battle.battle.squad.member.MemberImpl;import pinball.scene.battle.battle.ability.PrecontentMagnification;public class HPPort {
 public var member:MemberImpl;public var instantAbilities:Array=[];public var preActive:int=1;public var preCalls:int=0;
 public function HPPort(m:MemberImpl){member=m;}
 public function invokePrecontent(pre:*,content:*,puller:MemberImpl):PrecontentMagnification{preCalls++;return NativeAPI.pre(preActive);}
}}
