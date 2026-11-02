package pinball.common.data.quest.id

{
import flash.Boot;






   public final class BattleGroupKind

   {



      public static const __isenum:Boolean = true;



      public static var Multi:BattleGroupKind = new BattleGroupKind("Multi",1,null);



      public static var SingleOrRaid:BattleGroupKind = new BattleGroupKind("SingleOrRaid",0,null);



      public static var __constructs__:Array = ["SingleOrRaid","Multi"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function BattleGroupKind(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }

   }

}
