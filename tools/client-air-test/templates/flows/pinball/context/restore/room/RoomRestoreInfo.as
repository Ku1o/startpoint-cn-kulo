package pinball.context.restore.room

{
import flash.Boot;
import pinball.online.room.CooperationRoomConnectionConfig;








   public class RoomRestoreInfo

   {



      public var version:int;



      public var time:Number;



      public var continuationData:Object;



      public var config:CooperationRoomConnectionConfig;



      public function RoomRestoreInfo(param1:Number = 0, param2:CooperationRoomConnectionConfig = undefined, param3:Object = undefined)

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
