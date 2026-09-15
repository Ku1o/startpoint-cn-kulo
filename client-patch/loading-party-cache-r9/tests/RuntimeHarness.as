package
{
   import cn.loading.PartyDerivedCache;
   import flash.desktop.NativeApplication;
   import flash.display.Sprite;

   public class RuntimeHarness extends Sprite
   {
      public function RuntimeHarness()
      {
         var values:Object = {};
         var assets:Object = {};
         var partyA:FakeParty = new FakeParty(values,assets);
         var partyB:FakeParty = new FakeParty(values,assets);
         var group:Object = {};
         var debug:Array = [8000101];
         var first:Array = PartyDerivedCache.get(partyA,group,debug,true);
         var second:Array = PartyDerivedCache.get(partyB,group,debug,true);
         var third:Array = PartyDerivedCache.get(partyA,group,debug,true);
         var fourth:Array = PartyDerivedCache.get(partyB,group,debug,true);
         var miss:Array = PartyDerivedCache.get(partyA,group,[8000101],true);
         var result:Object = {
            "passed": partyA.buildCalls + partyB.buildCalls == 3 &&
               partyA.createCalls + partyB.createCalls == 9 &&
               first === second && second === third && third !== fourth && fourth !== miss,
            "buildCalls": partyA.buildCalls + partyB.buildCalls,
            "createCalls": partyA.createCalls + partyB.createCalls,
            "firstReuse": first === second && second === third,
            "evictionAfterThreeUses": third !== fourth,
            "differentDebugListMisses": fourth !== miss
         };
         trace("PARTY_CACHE_RESULT " + JSON.stringify(result));
         NativeApplication.nativeApplication.exit(0);
      }
   }
}

internal class FakeParty
{
   public var values:Object;
   public var logicAssets:Object;
   public var buildCalls:int = 0;
   public var createCalls:int = 0;

   public function FakeParty(param1:Object,param2:Object)
   {
      values = param1;
      logicAssets = param2;
   }

   public function _getUnitedCharactersWithQuestId(param1:Function,param2:Object,param3:Array,param4:Boolean) : Array
   {
      buildCalls++;
      return [param1({},0,param2,param3,param4),param1({},1,param2,param3,param4),param1({},2,param2,param3,param4)];
   }

   public function _createCalculatedBattleCharacterLogic(param1:Object,param2:int,param3:Object,param4:Array,param5:Boolean) : Object
   {
      createCalls++;
      return {"slot":param2};
   }
}
