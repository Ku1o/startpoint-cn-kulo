package pinball.remote.tutorial.updateStep

{
import flash.Boot;
import haxe.ds.Option;
import pinball.common.data.tutorial.StartTutorialProgressKind;










   public final class TutorialUpdateStepKind

   {



      public static const __isenum:Boolean = true;



      public static var BeginFullTutorial:TutorialUpdateStepKind = new TutorialUpdateStepKind("BeginFullTutorial",0,null);



      public static var BeginShortenedTutorial:TutorialUpdateStepKind = new TutorialUpdateStepKind("BeginShortenedTutorial",1,null);



      public static var __constructs__:Array = ["BeginFullTutorial","BeginShortenedTutorial","CompleteStep","CompleteStepWithChangingName","CompleteStepWithGachaDraw","CompleteStepWithPresent","CompleteStepToEnd"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function TutorialUpdateStepKind(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }



      public static function CompleteStep(param1:StartTutorialProgressKind, param2:Option) : TutorialUpdateStepKind

      {

         return new TutorialUpdateStepKind("CompleteStep",2,[param1,param2]);

      }



      public static function CompleteStepToEnd(param1:StartTutorialProgressKind) : TutorialUpdateStepKind

      {

         return new TutorialUpdateStepKind("CompleteStepToEnd",6,[param1]);

      }



      public static function CompleteStepWithChangingName(param1:StartTutorialProgressKind, param2:String) : TutorialUpdateStepKind

      {

         return new TutorialUpdateStepKind("CompleteStepWithChangingName",3,[param1,param2]);

      }



      public static function CompleteStepWithGachaDraw(param1:StartTutorialProgressKind, param2:int) : TutorialUpdateStepKind

      {

         return new TutorialUpdateStepKind("CompleteStepWithGachaDraw",4,[param1,param2]);

      }



      public static function CompleteStepWithPresent(param1:StartTutorialProgressKind) : TutorialUpdateStepKind

      {

         return new TutorialUpdateStepKind("CompleteStepWithPresent",5,[param1]);

      }

   }

}
