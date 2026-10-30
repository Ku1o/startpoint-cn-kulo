package {
 import jp.sipo.gipo.core.Gear;import jp.sipo.gipo.core.GearPhase;import jp.sipo.gipo.core.Diffuser;
 import flash.utils.Dictionary;import flash.utils.setTimeout;import flash.system.System;
 import pinball.scene.battle.battle.ability.InstantAbility;
 public class LifecycleCase {
  private static var retained:HPState;private static var rebuilt:HPState;private static var ledger:Dictionary;
  private static var verify:Function;private static var record:Function;private static var done:Function;
  private static function makeGear(s:HPState):Gear {
   var g:Gear=new Gear();g.phase=new GearPhase("fixture-live",3,[]);g.disposeTaskStack=null;g.numChildren=0;g.gearChildren=null;
   g.parent=new Gear();g.holder=s.member;var d:Diffuser=new Diffuser();d.parent=new Diffuser();d.holder=s.member;d.instanceClassDictionary=null;d.instanceEnumDictionary=null;g.diffuser=d;s.member.gear=g;return g;
  }
  private static function dispose(s:HPState,g:Gear):void {
   var d:Diffuser=g.diffuser;verify(!g.isDisposed() && !s.member.isDisposed(),"actual native Gear/Member disposed getters initially false");
   g.disposeTop();verify(g.phase===GearPhase.Dispose && g.parent===null && g.holder===null && g.diffuser===null && d.parent===null,"actual Gear.disposeTop/enterRemove/Diffuser.dispose clear empty native graph");
   verify(g.isDisposed() && s.member.isDisposed(),"actual Gear phase change reaches native Member disposed getter");
   var bank:Number=s.credit();s.gauge.subtract(1000,false);verify(s.credit()==bank && s.applies()==0,"actual disposed Gear blocks original HP accumulator without clearing its retained key value");
  }
  private static function ephemeral(resolved:Object):void {
   var s:HPState=new HPState(resolved);var g:Gear=makeGear(s);s.gauge.subtract(22222,false);verify(s.credit()==22222,"ephemeral object gets real nonzero weak-ledger entry");dispose(s,g);
   // No object/key is returned or captured by a Timer callback.
  }
  private static function values(value:Number):int{var n:int=0;for(var key:Object in ledger)if(ledger[key]===value)n++;return n;}
  private static function size():int{var n:int=0;for(var key:Object in ledger)n++;return n;}
  public static function start(resolved:Object,check:Function,observe:Function,complete:Function):void {
   verify=check;record=observe;done=complete;InstantAbility.wfxHpLossLedger=null;
   retained=new HPState(resolved);var g:Gear=makeGear(retained);retained.gauge.subtract(11111,false);verify(retained.credit()==11111,"retained control starts with actual nonzero HP bank");dispose(retained,g);
   rebuilt=new HPState(resolved);makeGear(rebuilt);verify(rebuilt.credit()==0,"reconstructed actual ability starts with no old-instance ledger credit");rebuilt.gauge.subtract(33333,false);verify(rebuilt.credit()==33333 && retained.credit()==11111,"recreated ability records a separate native weak-key amount");
   ephemeral(resolved);ledger=InstantAbility.wfxHpLossLedger;verify(ledger is Dictionary && values(11111)==1 && values(33333)==1 && values(22222)==1 && size()==3,"actual static ledger contains two strong controls and one released key before GC");
   setTimeout(collect,1);
  }
  private static function collect():void {try{System.gc();System.gc();setTimeout(afterGC,20);}catch(e:Error){done(e);}}
  private static function afterGC():void {
   try{verify(InstantAbility.wfxHpLossLedger===ledger,"GC observations use the same actual native static Dictionary");verify(values(22222)==0 && values(11111)==1 && values(33333)==1 && size()==2,"later Timer GC retires released weak key while both strong-reference controls survive");record({actualGearEmptyTeardown:true,weakGc:true,remainingEntries:size(),retainedBank:retained.credit(),rebuiltBank:rebuilt.credit(),boundary:"No registered Member disposal tasks/children/diffuser dictionary contents; native empty graph teardown and weak-key cycle collection only"});done();}catch(e:Error){done(e);}
  }
 }
}
