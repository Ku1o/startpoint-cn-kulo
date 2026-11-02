package fixture {
import pinball.scene.battle.battle.ObtainableInstantItemManagerImpl;
import pinball.common.data.battle.restore.BattleContinuationData;
import pinball.common.data.quest.battle.BattleClearParameter;
import pinball.common.data.quest.battle.BattleQuestClearParameter;
import pinball.common.data.quest.common.QuestLogic;
import pinball.remote.quest.finish.BattleQuestFinishRemoteUtil;
import pinball.common.data.player.PlayerLogic;

public class BattleNative {
 private static function check(row:Object,id:String,actual:*,expected:*):void {
  row.checks.push({name:id,pass:actual===expected,actual:actual,expected:expected});
  if(actual!==expected)throw new Error(id+": "+actual+" != "+expected);
 }
 private static function party():Object {return {characters:[{id:111001},null,null],unison_characters:[null,null,null],equipments:[null,null,null],ability_soul_ids:[null,null,null]};}
 private static function request(mana:int,restored:Boolean):Object {
  var own:BattleClearParameter=new BattleClearParameter();own.obtainedMana=mana;own.party={equipments:[]};
  own.statistics={party:party(),clear_phase:1,max_combo_count:17,zones:[]};
  var clear:BattleQuestClearParameter=new BattleQuestClearParameter();clear.myBattle=own;clear.isRestored=restored;
  return BattleQuestFinishRemoteUtil.createRequest(new QuestFixture(),clear,null);
 }
 public static function cases():Array {
  var rows:Array=[],row:Object={id:"native-field-mana-request",steps:[],checks:[],payloads:[]};
  try {
   var continuation:BattleContinuationData=new BattleContinuationData();
   var manager:ObtainableInstantItemManagerImpl=new ObtainableInstantItemManagerImpl(continuation);
   manager.addChild(new InstantSource(0,1200),0);manager.addChild(new InstantSource(1,999999),0);
   check(row,"only-mana-kind-counted",manager.count(0),1200);
   check(row,"zone-sum-includes-other-kinds",manager.sumUp(0),1001199);
   check(row,"non-mana-count-query-does-not-return-mana",manager.count(1),0);
   var first:Object=request(manager.count(0),false);
   check(row,"native-request-first-mana",first.add_mana,1200);check(row,"native-request-mana-is-int",first.add_mana is int,true);
   row.payloads.push({id:"first-zone",request:first});
   manager.addChild(new InstantSource(0,70000),1);
   check(row,"second-zone-sum",manager.sumUp(1),70000);
   var resumed:ObtainableInstantItemManagerImpl=new ObtainableInstantItemManagerImpl(continuation);
   check(row,"continuation-retains-acquired-array",resumed.obtainedInstantItems===manager.obtainedInstantItems,true);
   check(row,"multi-zone-restored-total",resumed.count(0),71200);
   resumed.addChild(new InstantSource(0,19000000),2);
   var cumulative:Object=request(resumed.count(0),true);
   check(row,"large-restored-native-request",cumulative.add_mana,19071200);
   check(row,"large-native-request-mana-is-int",cumulative.add_mana is int,true);
   check(row,"native-restored-flag",cumulative.is_restored,true);
   row.payloads.push({id:"large-restored",request:cumulative});
   row.status="passed";
  } catch(error:*) {row.status="failed";row.error=String(error);row.stack=error is Error?error.getStackTrace():null;}
  rows.push(row);row={id:"native-boost-availability",steps:[],checks:[]};
  try {
   for each(var value:int in [1,0,-1]) {
    var player:PlayerLogic=CommonHarness.createPlayer({userInfo:{boost_point:value,boss_boost_point:value}});
    check(row,"boost-getter-"+value,player.get_boostPoint(),value);
    check(row,"boss-boost-getter-"+value,player.get_bossBoostPoint(),value);
    check(row,"can-boost-"+value,player.canUseBoostPoint(),value>0);
    check(row,"can-boss-boost-"+value,player.canUseBossBoostPoint(),value>0);
   }
   row.status="passed";
  } catch(e:*) {row.status="failed";row.error=String(e);row.stack=e is Error?e.getStackTrace():null;}
  rows.push(row);return rows;
 }
 public static function checkResponse(player:PlayerLogic,step:Object,checks:Array):void {
  var row:Object={checks:checks};
  if(!step.expectedUserInfoSubset)throw new Error("battle step must declare expected user-info values");
  for(var key:String in step.expectedUserInfoSubset)check(row,"native-common-"+key,player.saveData.userInfo[key],step.expectedUserInfoSubset[key]);
  check(row,"native-can-use-boost-after-response",player.canUseBoostPoint(),Boolean(step.expectedCanBoost));
  check(row,"native-can-use-boss-boost-after-response",player.canUseBossBoostPoint(),Boolean(step.expectedCanBossBoost));
 }
}
}
