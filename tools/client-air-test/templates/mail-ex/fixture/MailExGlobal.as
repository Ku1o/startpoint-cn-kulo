package fixture {
import pinball.common.data.player.PlayerLogic;
import pinball.common.data.player.PlayerPeek;
import pinball.common.data.exBoost.ExBoostRepository;
import pinball.common.data.exBoost.ExBoostItemAcquisitionRepository;
import pinball.context.global.GlobalLogicForSection;
public class MailExGlobal implements GlobalLogicForSection {public var player:PlayerLogic;public var acquisition:ExBoostItemAcquisitionRepository;public var ex:ExBoostRepository=new ExBoostRepository();public function MailExGlobal(p:PlayerLogic,a:ExBoostItemAcquisitionRepository){player=p;acquisition=a;}public function getPlayer():PlayerPeek{return player;}public function getExBoostRepository():ExBoostRepository{return ex;}public function getExBoostItemAcquisitionRepository():ExBoostItemAcquisitionRepository{return acquisition;}}}
