package pinball.remote.exBoost

{
import flash.Boot;






   public final class ExBoostFirstDrawRemoteInput

   {



      public static const __isenum:Boolean = true;



      public static var __constructs__:Array = ["Finished"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function ExBoostFirstDrawRemoteInput(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }



      public static function Finished(param1:int, param2:Object) : ExBoostFirstDrawRemoteInput

      {

         return new ExBoostFirstDrawRemoteInput("Finished",0,[param1,param2]);

      }

   }

}
