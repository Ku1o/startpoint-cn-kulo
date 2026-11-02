package pinball.remote.mail

{
import flash.Boot;
import pinball.context.remote.RemoteError;








   public final class MailRemoteInput

   {



      public static const __isenum:Boolean = true;



      public static var EpiredDisposeError:MailRemoteInput = new MailRemoteInput("EpiredDisposeError",5,null);



      public static var ExpiredSaleError:MailRemoteInput = new MailRemoteInput("ExpiredSaleError",6,null);



      public static var MaxOverError:MailRemoteInput = new MailRemoteInput("MaxOverError",4,null);



      public static var __constructs__:Array = ["IndexFinished","ReceiveFinished","ReceiveAllFinished","ReceiveError","MaxOverError","EpiredDisposeError","ExpiredSaleError"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function MailRemoteInput(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }



      public static function IndexFinished(param1:Object) : MailRemoteInput

      {

         return new MailRemoteInput("IndexFinished",0,[param1]);

      }



      public static function ReceiveAllFinished(param1:Array, param2:Array, param3:Object) : MailRemoteInput

      {

         return new MailRemoteInput("ReceiveAllFinished",2,[param1,param2,param3]);

      }



      public static function ReceiveError(param1:RemoteError) : MailRemoteInput

      {

         return new MailRemoteInput("ReceiveError",3,[param1]);

      }



      public static function ReceiveFinished(param1:int, param2:Array, param3:Object, param4:Array) : MailRemoteInput

      {

         return new MailRemoteInput("ReceiveFinished",1,[param1,param2,param3,param4]);

      }

   }

}
