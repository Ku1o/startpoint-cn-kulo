package pinball.remote.exBoost

{
import flash.Boot;






   public final class ExBoostSelectRemoteInput

   {



      public static const __isenum:Boolean = true;



      public static var __constructs__:Array = ["FinishedOverride","FinishedDiscard"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function ExBoostSelectRemoteInput(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }



      public static function FinishedDiscard(param1:int) : ExBoostSelectRemoteInput

      {

         return new ExBoostSelectRemoteInput("FinishedDiscard",1,[param1]);

      }



      public static function FinishedOverride(param1:int, param2:Object) : ExBoostSelectRemoteInput

      {

         return new ExBoostSelectRemoteInput("FinishedOverride",0,[param1,param2]);

      }

   }

}
