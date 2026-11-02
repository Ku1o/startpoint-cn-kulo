package pinball.remote.gacha

{
import flash.Boot;
import haxe.IMap;
import haxe.ds.Option;










   public final class GachaRemoteInput

   {



      public static const __isenum:Boolean = true;



      public static var GachaCampaignInvalidPeriodError:GachaRemoteInput = new GachaRemoteInput("GachaCampaignInvalidPeriodError",4,null);



      public static var GachaCampaignOverDayPeriodError:GachaRemoteInput = new GachaRemoteInput("GachaCampaignOverDayPeriodError",5,null);



      public static var GachaInvalidPeriodError:GachaRemoteInput = new GachaRemoteInput("GachaInvalidPeriodError",3,null);



      public static var GachaSelect:GachaRemoteInput = new GachaRemoteInput("GachaSelect",7,null);



      public static var __constructs__:Array = ["GachaExec","GachaEquipmentExec","InvalidDrawResult","GachaInvalidPeriodError","GachaCampaignInvalidPeriodError","GachaCampaignOverDayPeriodError","GachaSave","GachaSelect"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function GachaRemoteInput(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }



      public static function GachaEquipmentExec(param1:Option, param2:Array, param3:Array, param4:Option, param5:IMap, param6:int) : GachaRemoteInput

      {

         return new GachaRemoteInput("GachaEquipmentExec",1,[param1,param2,param3,param4,param5,param6]);

      }



      public static function GachaExec(param1:Option, param2:Array, param3:Array, param4:IMap, param5:int, param6:Array, param7:Number, param8:Option, param9:Array) : GachaRemoteInput

      {

         return new GachaRemoteInput("GachaExec",0,[param1,param2,param3,param4,param5,param6,param7,param8,param9]);

      }



      public static function GachaSave(param1:IMap) : GachaRemoteInput

      {

         return new GachaRemoteInput("GachaSave",6,[param1]);

      }



      public static function InvalidDrawResult(param1:String) : GachaRemoteInput

      {

         return new GachaRemoteInput("InvalidDrawResult",2,[param1]);

      }

   }

}
