package pinball.common.data.save.restore

{
import flash.Boot;
import haxe.ds.Option;
import pinball.common.data.battle.restore.BattleRestoreHeaderValues;
import pinball.common.data.quest.battle.BattleQuestClearParameter;
import pinball.common.data.quest.id.BattleGroupKind;
import pinball.online.lounge.LoungeConnectionConfig;
import pinball.online.room.CooperationRoomConnectionConfig;


















   public final class RestoreState

   {



      public static const __isenum:Boolean = true;



      public static var None:RestoreState = new RestoreState("None",6,null);



      public static var __constructs__:Array = ["Tutorial","Battle","BattleClear","BattleAbort","CooperationRoom","Lounge","None"];



      public var tag:String;



      public var index:int;



      public var params:Array;



      public const __enum__:Boolean = true;



      public function RestoreState(param1:String, param2:int, param3:Array)

      {

         tag = param1;

         index = param2;

         params = param3;

      }



      public static function Battle(param1:BattleRestoreHeaderValues, param2:Option) : RestoreState

      {

         return new RestoreState("Battle",1,[param1,param2]);

      }



      public static function BattleAbort(param1:String, param2:BattleGroupKind) : RestoreState

      {

         return new RestoreState("BattleAbort",3,[param1,param2]);

      }



      public static function BattleClear(param1:BattleRestoreHeaderValues, param2:BattleQuestClearParameter) : RestoreState

      {

         return new RestoreState("BattleClear",2,[param1,param2]);

      }



      public static function CooperationRoom(param1:CooperationRoomConnectionConfig, param2:Object) : RestoreState

      {

         return new RestoreState("CooperationRoom",4,[param1,param2]);

      }



      public static function Lounge(param1:LoungeConnectionConfig, param2:Object) : RestoreState

      {

         return new RestoreState("Lounge",5,[param1,param2]);

      }



      public static function Tutorial(param1:Option) : RestoreState

      {

         return new RestoreState("Tutorial",0,[param1]);

      }

   }

}
