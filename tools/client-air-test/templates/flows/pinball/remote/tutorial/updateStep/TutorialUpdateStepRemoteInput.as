package pinball.remote.tutorial.updateStep

{
import flash.Boot;






   public final class TutorialUpdateStepRemoteInput

   {



      public static const __isenum:Boolean = true;



      public static var NgWordError:TutorialUpdateStepRemoteInput = new TutorialUpdateStepRemoteInput("NgWordError",1,null);



      public static var Present:TutorialUpdateStepRemoteInput = new TutorialUpdateStepRemoteInput("Present",3,null);



      public static var __constructs__:Array = ["NameChangeComplete","NgWordError","GachaDrawn","Present","End"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function TutorialUpdateStepRemoteInput(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }



      public static function End(param1:Object) : TutorialUpdateStepRemoteInput

      {

         return new TutorialUpdateStepRemoteInput("End",4,[param1]);

      }



      public static function GachaDrawn(param1:Object) : TutorialUpdateStepRemoteInput

      {

         return new TutorialUpdateStepRemoteInput("GachaDrawn",2,[param1]);

      }



      public static function NameChangeComplete(param1:String) : TutorialUpdateStepRemoteInput

      {

         return new TutorialUpdateStepRemoteInput("NameChangeComplete",0,[param1]);

      }

   }

}
