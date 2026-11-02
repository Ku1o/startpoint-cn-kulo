package pinball.common.data.tutorial

{
import flash.Boot;






   public final class StartTutorialProgressKind

   {



      public static const __isenum:Boolean = true;



      public static var __constructs__:Array = ["Shortened","Full"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function StartTutorialProgressKind(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }



      public static function Full(param1:int) : StartTutorialProgressKind

      {

         return new StartTutorialProgressKind("Full",1,[param1]);

      }



      public static function Shortened(param1:int) : StartTutorialProgressKind

      {

         return new StartTutorialProgressKind("Shortened",0,[param1]);

      }

   }

}
