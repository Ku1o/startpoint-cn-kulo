package cn.loading
{
   /**
    * Reuses the calculated character array while one multi-battle preparation
    * pass is constructing the same party for several battle worlds.
    *
    * The cache is deliberately bounded and short lived: an entry is consumed
    * at most three times (the normal three-world preparation) and the table is
    * capped so a failed or abandoned scene cannot retain an unbounded graph.
    * The key includes the source party data, logic-asset container, quest
    * group, debug ability list, and ability flag.  No player or cross-scene
    * result is reused when any of those inputs differ.
    */
   public final class PartyDerivedCache
   {
      private static var entries:Array = [];
      private static const MAX_ENTRIES:int = 12;
      private static const MAX_USES:int = 3;

      public static function get(param1:Object, param2:Object, param3:Array, param4:Boolean) : Array
      {
         var _loc7_:Object;
         var _loc8_:int;
         var _loc5_:Object = param1.values;
         var _loc6_:int = 0;
         while(_loc6_ < int(entries.length))
         {
            _loc7_ = entries[_loc6_];
            if(_loc7_.values === _loc5_ && _loc7_.assets === param1.logicAssets && _loc7_.group === param2 && _loc7_.debug === param3 && _loc7_.enable === param4)
            {
               _loc8_ = int(_loc7_.uses) + 1;
               _loc7_.uses = _loc8_;
               var _loc9_:Array = _loc7_.result;
               if(_loc8_ >= MAX_USES)
               {
                  entries.splice(_loc6_,1);
               }
               return _loc9_;
            }
            _loc6_++;
         }

         var _loc10_:Object = param1;
         var _loc11_:Function = function(param5:Object, param6:int, param7:Object, param8:Array, param9:Boolean) : Object
         {
            return _loc10_._createCalculatedBattleCharacterLogic(param5,param6,param7,param8,param9);
         };
         var _loc14_:Array = _loc10_._getUnitedCharactersWithQuestId(_loc11_,param2,param3,param4);
         if(int(entries.length) >= MAX_ENTRIES)
         {
            entries.shift();
         }
         entries.push({"values":_loc5_,"assets":_loc10_.logicAssets,"group":param2,"debug":param3,"enable":param4,"result":_loc14_,"uses":1});
         return _loc14_;
      }
   }
}
