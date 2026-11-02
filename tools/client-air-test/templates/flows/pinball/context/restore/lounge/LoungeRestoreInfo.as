package pinball.context.restore.lounge

{
import flash.Boot;
import pinball.online.lounge.LoungeConnectionConfig;








   public class LoungeRestoreInfo

   {



      public var version:int;



      public var time:Number;



      public var continuationData:Object;



      public var config:LoungeConnectionConfig;



      public function LoungeRestoreInfo(param1:Number = 0, param2:LoungeConnectionConfig = undefined, param3:Object = undefined)

      {

         if(Boot.skip_constructor)

         {

            return;

         }

         time = param1;

         config = param2;

         continuationData = param3;

         version = 1;

      }

   }

}
