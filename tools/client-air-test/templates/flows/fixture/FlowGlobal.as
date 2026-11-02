package fixture {
import pinball.common.data.exBoost.ExBoostRepository;
import pinball.common.data.player.PlayerLogic;
import pinball.common.data.player.PlayerPeek;
import pinball.context.global.GlobalLogicForSection;
public class FlowGlobal implements GlobalLogicForSection {public var player:PlayerLogic;public var ex:ExBoostRepository=new ExBoostRepository();public function FlowGlobal(p:PlayerLogic){player=p;}public function getPlayer():PlayerPeek{return player;}public function getExBoostRepository():ExBoostRepository{return ex;}}}