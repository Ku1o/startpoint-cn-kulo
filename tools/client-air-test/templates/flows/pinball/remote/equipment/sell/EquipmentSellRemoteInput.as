package pinball.remote.equipment.sell

{
import flash.Boot;






   public final class EquipmentSellRemoteInput

   {



      public static const __isenum:Boolean = true;



      public static var StackSold:EquipmentSellRemoteInput = new EquipmentSellRemoteInput("StackSold",1,null);



      public static var __constructs__:Array = ["EquipmentSold","StackSold"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function EquipmentSellRemoteInput(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }



      public static function EquipmentSold(param1:int) : EquipmentSellRemoteInput

      {

         return new EquipmentSellRemoteInput("EquipmentSold",0,[param1]);

      }

   }

}
