package {
 import pinball.scene.battle.battle.HealthPointGaugeImpl;
 import pinball.scene.battle.battle.squad.member.MemberImpl;
 import pinball.scene.battle.battle.squad.member.MemberState;
 import pinball.scene.battle.battle.ability.InstantAbility;
 import pinball.scene.battle.battle.ability.PrecontentMagnification;
 import pinball.scene.battle.battle.ability._InstantAbility.AbilityTriggerHandler;
 import pinball.common.data.ability.instant.InstantBattleAbilityTriggerKind;
 import pinball.common.math.Decimal100ClosedInterval;
 import haxe.ds.Option;
 public class HPState {
  public var member:MemberImpl=new MemberImpl();public var other:MemberImpl=new MemberImpl();
  public var gauge:HealthPointGaugeImpl;public var otherGauge:HealthPointGaugeImpl;
  public var ability:InstantAbility;public var handler:AbilityTriggerHandler;public var team:HPTeam;
  public function HPState(resolved:Object,scope:int=5,remaining:int=-1) {
   member.state=new MemberState("fixture-alive",0,[]);other.state=new MemberState("fixture-alive",0,[]);member.gear=new HPGear();other.gear=new HPGear();
   team=new HPTeam(member,other);member.squad=team;other.squad=team;
   gauge=makeGauge(member,100000,100000);otherGauge=makeGauge(other,200000,200000);
   var original:Object=resolved.params[0];var trigger:InstantBattleAbilityTriggerKind=new InstantBattleAbilityTriggerKind(original.tag,original.index,original.params.slice());trigger.params[4]=scope;
   ability=new InstantAbility();var slot:HPPort=new HPPort(member);ability.slot=slot;
   ability.source={trigger:trigger,triggerLimit:resolved.params[1],cooltime:resolved.params[2],precontent:null,content:null};
   ability.stats={invokeCountWithoutLimit:0};slot.instantAbilities=[ability];member.abilitySlot=slot;other.abilitySlot=new HPPort(other);
   handler=new AbilityTriggerHandler();handler.parent=ability;handler.owner=member;handler.triggerPuller=member;handler.precondition=[];
   handler.periodCount=1;handler.calledCount=0;handler.restTriggerLimit=remaining<0?ability.get_triggerLimit():remaining;
   handler.cooltimeRest=0;handler.frameSinceLastInvoked=77;handler.activeEvenIfOwnerIsDead=false;ability.handlerForDebug=handler;
  }
  public static function makeGauge(m:MemberImpl,max:Number,value:Number):HealthPointGaugeImpl {
   var g:HealthPointGaugeImpl=new HealthPointGaugeImpl();g.owner=m;g.healthPoint=new Decimal100ClosedInterval(0,max,value);g.changeable=true;g.lowerLimitValue=0;g.maxStatsModifier=0;g.barrierHp=null;m.healthPointGauge=g;return g;
  }
  public function credit():Number {return InstantAbility.wfxHpLossLedger && InstantAbility.wfxHpLossLedger[ability] ? Number(InstantAbility.wfxHpLossLedger[ability]):0;}
  public function applies():int{return ability.fixtureApplies.length;}
  public function ticks(n:int):void{for(var i:int=0;i<n;i++)handler.update();}
 }
}
