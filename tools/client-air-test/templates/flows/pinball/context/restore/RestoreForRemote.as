package pinball.context.restore {
import haxe.ds.Option;
public interface RestoreForRemote {function getRoomData():Option;function deleteRoomData():void;function getLoungeData():Option;function deleteLoungeData():void;function readBattleHead(v:Object,f:Function):void;}}