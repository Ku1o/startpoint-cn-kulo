package {
 import pinball.scene.battle.battle.ability.InstantAbility;
 import pinball.scene.battle.battle.barrier.BarrierHpGaugeImpl;
 import pinball.common.math.Decimal100ClosedInterval;
 import pinball.scene.battle.battle.squad.member.MemberState;
 public class HPNativeCase {
  private static function same(a:Number,b:Number):Boolean{return Math.abs(a-b)<0.000001;}
  public static function run(resolved:Object,check:Function,observe:Function):void {
   var s:HPState=new HPState(resolved),initialLimit:int=s.handler.restTriggerLimit;
   check(resolved.tag=="Battle" && resolved.params[0].tag=="Count" && resolved.params[0].params[0]==9000 && resolved.params[0].params[3]==30000 && resolved.params[0].params[4]==5 && resolved.params[2]==1800,"actual frozen row resolves9000/scope5/threshold30000/cooldown1800");
   check(initialLimit==2147483647 && s.member.getRealMaximumHealthPoint()==100000 && s.other.getRealMaximumHealthPoint()==200000,"actual native limit None getter and distinct native maxHP getters");
   s.gauge.subtract(10000,false);check(s.credit()==10000 && s.applies()==0,"first actual HP loss accumulates");
   s.gauge.add(5000);check(s.credit()==10000 && s.gauge.getValue()==95000,"actual healing neither adds nor subtracts prior bank");
   s.gauge.subtract(79999,false);check(s.credit()==89999 && s.applies()==0,"bank just below actual team threshold does not fire");
   s.gauge.subtract(1,false);var entered:Object=s.ability.fixtureApplies[0];
   check(s.credit()==0 && s.applies()==1 && s.handler.calledCount==1 && s.handler.restTriggerLimit==initialLimit-1,"threshold equality clears ledger and native counter consumes one");
   check(entered.ledger==0 && entered.rest==initialLimit-1 && entered.cooltime==1800 && entered.called==1 && entered.frame==77 && entered.pre==1 && !entered.byUnison,"content outlet observes native scheduling writes before apply and old frame value");
   check(s.handler.frameSinceLastInvoked==0 && s.handler.cooltimeRest==1800,"native count finishes frame reset after apply");

   var re:HPState=new HPState(resolved);re.ability.fixtureReenter=function():void{re.gauge.subtract(1000,false);};
   re.gauge.subtract(90000,false);check(re.applies()==1 && re.handler.calledCount==1 && re.credit()==0 && re.gauge.getValue()==9000,"real in-content HP reentry is rejected by already-assigned native cooldown");
   re.gauge.subtract(1000,false);check(re.applies()==1 && re.handler.calledCount==1 && re.credit()==0,"second same-frame real subtraction does not bypass cooldown or accrue credit");
   re.ticks(1799);check(re.handler.cooltimeRest==1 && re.handler.frameSinceLastInvoked==1799,"actual update decrements1799 ticks without manual reset");
   re.gauge.subtract(1,false);check(re.credit()==0 && re.applies()==1,"last positive cooldown tick still blocks");
   re.handler.update();check(re.handler.cooltimeRest==0 && re.handler.frameSinceLastInvoked==1800,"actual final update reaches cooldown0");
   re.gauge.add(100000);re.gauge.subtract(90000,false);check(re.applies()==2 && re.handler.restTriggerLimit==initialLimit-2 && re.handler.cooltimeRest==1800,"next threshold after actual cooldown is admitted and consumed natively");

   var over:HPState=new HPState(resolved);over.gauge.subtract(100000,false);check(over.applies()==1 && over.credit()==0,"overshoot resets to0 instead of carrying the excess");
   over.ticks(1800);over.gauge.add(100000);over.gauge.subtract(89999,false);check(over.applies()==1 && over.credit()==89999,"discarded overshoot cannot cause an early next trigger");

   var own:HPState=new HPState(resolved,0);own.otherGauge.subtract(30000,false);check(own.applies()==0 && own.credit()==0,"scope0 rejects another member loss");
   own.gauge.subtract(29999,false);check(own.credit()==29999 && own.applies()==0,"scope0 uses owner's real100000 max denominator");own.gauge.subtract(1,false);check(own.applies()==1 && own.credit()==0,"scope0 exact own threshold fires");
   var split:HPState=new HPState(resolved);split.otherGauge.subtract(30000,false);split.gauge.subtract(59999,false);check(split.credit()==89999 && split.applies()==0,"scope5 aggregates both real members with summed max denominator");split.gauge.subtract(1,false);check(split.applies()==1,"scope5 split exact threshold fires once");

   var shield:HPState=new HPState(resolved);var barrier:BarrierHpGaugeImpl=new BarrierHpGaugeImpl();barrier.barrierHp=new Decimal100ClosedInterval(0,90000,90000);shield.gauge.barrierHp=barrier;
   shield.gauge.subtract(10000,true);check(shield.gauge.getValue()==100000 && barrier.barrierHp.value==80000 && shield.credit()==0 && shield.applies()==0,"actual shield absorption does not count as real HP loss");

   var no:HPState=new HPState(resolved);no.handler.precondition=[[]];no.gauge.subtract(90000,false);check(no.applies()==0 && no.credit()==0 && no.handler.calledCount==0,"real precondition array evaluator rejects before ledger/count changes");
   var inactive:HPState=new HPState(resolved);inactive.ability.slot.preActive=0;inactive.gauge.subtract(90000,false);check(inactive.applies()==0 && inactive.handler.calledCount==1 && inactive.handler.restTriggerLimit==initialLimit && inactive.handler.cooltimeRest==0 && inactive.credit()==0,"native inactive typed precontent advances attempts but consumes no limit or cooldown");
   var limit:HPState=new HPState(resolved,5,1);limit.gauge.subtract(90000,false);check(limit.applies()==1 && limit.handler.restTriggerLimit==0 && limit.ability.fixtureMarks==1 && limit.ability.fixtureLimitNotices==1,"native last count consumes0 then emits post-content limit notifications");
   limit.gauge.add(100000);limit.ticks(1800);limit.gauge.subtract(90000,false);check(limit.applies()==1 && limit.credit()==0 && limit.handler.calledCount==1,"HP exhausted-limit gate prevents new credit and handler entry");
   var attempted:Number=limit.ability.stats.invokeCountWithoutLimit;limit.handler.countHandler(null,1);check(limit.applies()==1 && limit.handler.calledCount==2 && limit.ability.stats.invokeCountWithoutLimit==attempted+1,"direct native exhausted counter still records attempt statistics but no content");

   var dead:HPState=new HPState(resolved);dead.member.state=new MemberState("fixture-dead",1,[]);dead.handler.countHandler(null,1);check(dead.applies()==0 && dead.handler.calledCount==0,"native ActionExecutor alias enters actual Member death getter and rejects direct dead owner");
   dead.gauge.subtract(90000,false);check(dead.applies()==1 && dead.handler.activeEvenIfOwnerIsDead,"actual HP helper intentionally enables death-even triggering");
   var disposed:HPState=new HPState(resolved);disposed.gauge.subtract(10000,false);disposed.member.gear.disposed=true;disposed.gauge.subtract(5000,false);check(disposed.credit()==10000 && disposed.applies()==0 && disposed.member.isDisposed(),"native disposed getter and helper preserve bank without adding new loss");
   disposed.handler.countHandler(null,1);check(disposed.handler.calledCount==0,"native handler disposed interface path rejects before attempt count");
   var old:InstantAbility=disposed.ability;disposed.member.gear.disposed=false;
   var rebuilt:HPState=new HPState(resolved);check(rebuilt.credit()==0 && InstantAbility.wfxHpLossLedger[old]==10000,"new ability/member construction has no old weak-key bank; retained old object keeps its own value");
   rebuilt.gauge.subtract(20000,false);check(rebuilt.credit()==20000 && InstantAbility.wfxHpLossLedger[old]==10000,"native weak Dictionary keys isolate reconstructed ability state");

   var secondary:HPState=new HPState(resolved);secondary.team.primary=false;secondary.gauge.subtract(90000,false);check(secondary.credit()==0 && secondary.applies()==0,"nonprimary squad observer gives no dispatch");
   var zero:HPState=new HPState(resolved);zero.ability.wfxAccumulateHpLoss(zero.member,10000,0);check(zero.credit()==0,"nonpositive team denominator returns before credit");

   // All three max-HP paths execute their complete original method and actual
   // decimal interval operations. Tests distinguish net HP loss from max change.
   var max1:HPState=new HPState(resolved);max1.gauge.healthPoint.set(90000);max1.gauge.setMaxHealthPoint(80000,0);check(max1.gauge.getValue()==80000 && max1.credit()==10000 && max1.member.getRealMaximumHealthPoint()==80000,"setMaxHealthPoint counts only actual clamped10000 HP loss");
   var max1n:HPState=new HPState(resolved);max1n.gauge.healthPoint.set(60000);max1n.gauge.setMaxHealthPoint(80000,0);check(max1n.gauge.getValue()==60000 && max1n.credit()==0,"setMaxHealthPoint lower max without HP drop adds no loss");
   var max2:HPState=new HPState(resolved);max2.gauge.healthPoint.set(90000);max2.gauge.changeMaxHp(700);check(max2.gauge.getValue()==70000 && max2.credit()==20000 && max2.member.getRealMaximumHealthPoint()==70000,"changeMaxHp executes actual conversions and counts20000 net loss");
   var max2n:HPState=new HPState(resolved);max2n.gauge.healthPoint.set(60000);max2n.gauge.changeMaxHp(700);check(max2n.gauge.getValue()==70000 && max2n.credit()==0,"changeMaxHp lower max but positive HP change does not count");
   var max3:HPState=new HPState(resolved);max3.gauge.healthPoint.set(90000);max3.gauge.addMaxStatModifier(1000,-20000);check(max3.gauge.getValue()==70000 && max3.credit()==20000 && max3.member.getRealMaximumHealthPoint()==80000,"addMaxStatModifier actual decimal formula counts net20000 loss");
   var ratio:HPState=new HPState(resolved);ratio.gauge.setRatio(0.5);check(ratio.gauge.getValue()==50000 && ratio.credit()==50000,"actual native fractional0.5 ratio loss enters ledger");ratio.gauge.set(40000);check(ratio.gauge.getValue()==40000 && ratio.credit()==60000,"actual set loss enters same ledger");ratio.gauge.set(70000);check(ratio.credit()==60000,"actual set healing does not deduct existing ledger");
   check(NativeAPI.describe(resolved.params[0],resolved.params[1])=="全队累计损失的HP达到全队最大HP总和的30%|LIMIT_NONE|","actual description consumer/helper/bind/context getter/limit-None closure selects locale port and real scope5 threshold");
   var ownDescription:Object=new HPState(resolved,0);check(NativeAPI.describe(ownDescription.ability.source.trigger,resolved.params[1])=="自身累计损失的HP达到自身最大HP的30%|LIMIT_NONE|","actual description scope0 uses own denominator wording");
   observe({nativeCounter:true,nativeCooldownTicks:1800,maxHpPathsExecuted:["setMaxHealthPoint","changeMaxHp","addMaxStatModifier"],ownerDisposalBoundary:"real Member.isDisposed and interface path; finite Gear disposed state, no full Gear.dispose/registration teardown/forced GC",contentBoundary:"parent.apply records post-native-counter state and optional real HP reentry only; passive business content not executed"});
  }
 }
}
