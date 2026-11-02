package fixture {
import haxe.ds.Option;
import pinball.common.data.save.restore.RestoreState;
import pinball.context.restore.RestoreForRemote;
public class FlowRestore implements RestoreForRemote {public var calls:Array=[];public function getRoomData():Option{calls.push("getRoomData");return Option.None;}public function deleteRoomData():void{calls.push("deleteRoomData");}public function getLoungeData():Option{calls.push("getLoungeData");return Option.None;}public function deleteLoungeData():void{calls.push("deleteLoungeData");}public function readBattleHead(v:Object,f:Function):void{calls.push({readBattleHead:v});throw new Error("fixture has no saved battle header");}}}