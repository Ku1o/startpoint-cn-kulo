"""Run the independent state class in desktop AIR with isolated stubs, never the game."""
import argparse,copy,hashlib,importlib.util,json,struct,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
EVENT_CASES=[
 ('advent','AdventEvent','advent_event','id',False),('carnival','CarnivalEvent','carnival_event','id',False),
 ('challengeDungeon','ChallengeDungeonEvent','challenge_dungeon_event','id',True),('dailyExpMana','DailyExpManaEvent','daily_exp_mana_event','id',True),
 ('dailyWeek','DailyWeekEvent','daily_week_event','id',True),('expertSingleEvent','ExpertSingleEvent','expert_single_event','id',False),
 ('hardMulti','HardMultiEvent','hard_multi_event','id',False),('raid','RaidEvent','raid_event','id',False),
 ('ranking','RankingEvent','ranking_event','id',False),('rush','RushEvent','rush_event','id',False),
 ('scoreAttack','ScoreAttackEvent','score_attack_event','eventId',False),('soloTimeAttack','SoloTimeAttackEvent','solo_time_attack_event','eventId',False),
 ('story','StoryEvent','story_event','id',True),('towerDungeon','TowerDungeonEvent','tower_dungeon_event','id',True),
 ('worldStory','WorldStoryEvent','world_story_event','id',False),
]
STUBS={
'haxe/ds/Option.as': 'package haxe.ds { public class Option { public var index:int; public var params:Array; public static var None:Option=new Option(1,[]); public function Option(i:int,p:Array){index=i;params=p;} public static function Some(v:Object):Option{return new Option(0,[v]);}}}',
'haxe/ds/IntMap.as':'package haxe.ds { public class IntMap { public var h:Object={}; }}',
'pinball/common/data/quest/event/EventIdKind.as':'package pinball.common.data.quest.event { public class EventIdKind { public var tag:String;public var params:Array; public function EventIdKind(t:String,id:int){tag=t;params=[id];} public static function TowerDungeonEvent(id:int):EventIdKind{return new EventIdKind("TowerDungeonEvent",id);} }}',
'pinball/common/data/quest/event/challengeDungeon/ChallengeDungeonEventLogic.as':'package pinball.common.data.quest.event.challengeDungeon {public class ChallengeDungeonEventLogic {public var id:int=1;}}',
'pinball/master/generated/PassCardEventTable.as':'package pinball.master.generated {public class PassCardEventTable {}}',
'pinball/common/time/TimeRange.as':'package pinball.common.time {public class TimeRange {public var startTime:Number;public var endTime:Object;public function TimeRange(s:Number,e:Object){startTime=s;endTime=e;}public function isWithin(t:Number):Boolean{return t>=startTime && (endTime.index==1 || t<=Number(endTime.params[0]));}}}',
'pinball/common/data/boxGacha/BoxGachaLogic.as':'package pinball.common.data.boxGacha {public class BoxGachaLogic {public var id:int=48;}}',
'pinball/common/data/shop/EventItemShopProductLogic.as':'package pinball.common.data.shop {public class EventItemShopProductLogic {public var id:Object={tag:"EventItem",params:[9]};public var eventItemValues:Object={event:{tag:"CarnivalEvent",params:[1]}};}}',
'pinball/common/data/player/ShopProductBuyableState.as':'package pinball.common.data.player {public class ShopProductBuyableState {public static var OutOfStock:Object={tag:"OutOfStock"};}}',
'pinball/common/tools/DateUtil.as':'package pinball.common.tools {public class DateUtil {public static function getTomorrowStartDateTime(now:Number):Number{return now+86400000;}public static function getNextWeekStartDateTime(now:Number):Number{return now+604800000;}}}',
}

STUBS.update({
 'pinball/common/data/quest/event/common/EventLogicBase.as': 'package pinball.common.data.quest.event.common {import haxe.ds.Option;import pinball.common.time.TimeRange;public class EventLogicBase {public var commonValues:Object={start_time:0,playable_end_time:Option.Some(500)};public function isWithinPeriod(now:Number):Boolean{return false;}public function getPlayableTimeRange():TimeRange{return null;}public function get_startTime():Number{return 0;}public function get_playableEndTime():Option{return Option.None;}}}',
 'pinball/common/data/quest/event/common/EventWithFixedHeaderLogicBase.as': 'package pinball.common.data.quest.event.common {public class EventWithFixedHeaderLogicBase extends EventLogicBase {}}',
 'pinball/common/error/DisplayableError.as': 'package pinball.common.error {public class DisplayableError {public var displayMessage:String;public var internalMessage:String;public function DisplayableError(display:String,internalText:String=""){displayMessage=display;internalMessage=internalText;}}}',
 'pinball/common/time/_AppTime/AppTime_Impl_.as': 'package pinball.common.time._AppTime {public class AppTime_Impl_ {public static function toJapanStandardTimeString(v:Number):String{return String(v);}}}',
 'pinball/context/remote/RemoteErrorKind.as': 'package pinball.context.remote {public class RemoteErrorKind {public var tag:String;public var index:int;public var params:Array;public function RemoteErrorKind(t:String,i:int,p:Array){tag=t;index=i;params=p;}}}',
 'pinball/context/remote/RemoteError.as': 'package pinball.context.remote {import pinball.common.error.DisplayableError;public class RemoteError extends DisplayableError {public var kind:RemoteErrorKind;public function RemoteError(k:RemoteErrorKind){super(k.params.length?String(k.params[0]):"ordinary");kind=k;}}}',
 'pinball/context/remote/RemoteCommonInput.as': 'package pinball.context.remote {public class RemoteCommonInput {public var params:Array;public function RemoteCommonInput(error:RemoteError){params=[error];}}}',
 'pinball/debug/CrashUtil.as': 'package pinball.debug {public class CrashUtil {public static var errors:Array=[];public static function saveServerError(error:Object):void{errors.push(error);}}}',
 'pinball/context/scene/ILogicScene.as': 'package pinball.context.scene {public interface ILogicScene {function openErrorDialog(error:Object,callback:Function):void;function gotoTitleScene():void;function openApplicationVersionErrorDialog(v:Object):void;function openApplicationCommonErrorDialog(v:Object):void;function openPreparationMaintenanceErrorDialog(v:Object):void;function openTakeOverOldAccessErrorDialog(v:Object):void;function wordFilterImpl():void;}}',
 'pinball/context/scene/ReloadTestScene.as': 'package pinball.context.scene {public class ReloadTestScene implements ILogicScene {public var dialogs:Array=[];public var titleCalls:int=0;public function openErrorDialog(error:Object,callback:Function):void{dialogs.push({error:error,callback:callback});}public function gotoTitleScene():void{titleCalls++;}public function openApplicationVersionErrorDialog(v:Object):void{}public function openApplicationCommonErrorDialog(v:Object):void{}public function openPreparationMaintenanceErrorDialog(v:Object):void{}public function openTakeOverOldAccessErrorDialog(v:Object):void{}public function wordFilterImpl():void{}}}',
 'pinball/context/Logic.as': 'package pinball.context {import pinball.context.remote.RemoteCommonInput;import pinball.context.scene.ILogicScene;public class Logic {public var asset:Object;public var state:ILogicScene;public var attention:Object;public var globalLogic:Object;public function remoteCommonInput(input:RemoteCommonInput):void{}public function openDateChangedDialog(before:Number,after:Number):void{}}}',
 'pinball/context/global/GlobalLogic.as': 'package pinball.context.global {import haxe.ds.Option;public class GlobalLogic {public var logicStatus:Object;public function getTime():Number{return -999;}public function getOptionTime():Option{return Option.None;}}}',
 'pinball/context/clock/ComplexTime.as': 'package pinball.context.clock {public class ComplexTime {public var serverTime:Number;public var elapsedTime:Number;public function ComplexTime(s:Number=0,e:Number=0){serverTime=s;elapsedTime=e;}public function getAppTime():Number{return serverTime+elapsedTime;}}}',
 'pinball/error/ClientError.as': 'package pinball.error {public class ClientError extends Error {public function ClientError(code:int,message:String){super(message);}}}',
 'flash/Boot.as': 'package flash {public class Boot {public static var lastError:Error;}}',
})
STUBS['pinball/common/data/quest/event/EventIdKind.as']='package pinball.common.data.quest.event {public class EventIdKind {public var tag:String;public var index:int;public var params:Array;public function EventIdKind(t:String,i:int,p:Array){tag=t;index=i;params=p;}' + ''.join('public static function '+kind+'(id:int):EventIdKind{return null;}' for _,kind,_,_,_ in EVENT_CASES) + '}}'
for package,kind,_,field,fixed in EVENT_CASES:
 base='EventWithFixedHeaderLogicBase' if fixed else 'EventLogicBase'
 STUBS['pinball/common/data/quest/event/'+package+'/'+kind+'Logic.as']='package pinball.common.data.quest.event.'+package+' {import pinball.common.data.quest.event.common.'+base+';import pinball.common.data.quest.event.EventIdKind;public class '+kind+'Logic extends '+base+' {public var '+field+':int=1;public function getEventId():EventIdKind{return null;}}}'
STUBS['pinball/common/data/quest/event/challengeDungeon/CampaignAppliedChallengeDungeonEventLogic.as']='package pinball.common.data.quest.event.challengeDungeon {public class CampaignAppliedChallengeDungeonEventLogic extends ChallengeDungeonEventLogic {}}'

MAIN=r"""package {
import flash.display.Sprite; import flash.filesystem.File; import flash.filesystem.FileStream; import flash.filesystem.FileMode;
import flash.utils.getDefinitionByName;import flash.desktop.NativeApplication; import cn.content.ContentOperationsState;
import haxe.ds.Option; import haxe.ds.IntMap; import pinball.common.data.quest.event.EventIdKind;
import pinball.common.data.quest.event.challengeDungeon.ChallengeDungeonEventLogic;
import pinball.master.generated.PassCardEventTable;
import pinball.common.time.TimeRange;import pinball.common.data.boxGacha.BoxGachaLogic;import pinball.common.data.shop.EventItemShopProductLogic;
import pinball.common.data.player.ShopProductBuyableState;import pinball.common.tools.DateUtil;
import pinball.context.Logic;import pinball.context.remote.RemoteError;import pinball.context.remote.RemoteErrorKind;import pinball.context.remote.RemoteCommonInput;
import pinball.context.scene.ReloadTestScene;import pinball.debug.CrashUtil;
public class StateTest extends Sprite {
private var assertions:int=0;
private var checks:Array=[];
private var nativeObservations:Array=[];
private function check(v:Boolean,n:String):void {if(!v)throw new Error(n);assertions++;checks.push(n);}
private function row(key:String,open:Boolean,q:Array=null,end:Object=null):Object{return {key:key,instance_id:key+":original",visible:open,enter:open,claim:false,exchange:open,permanent:end===null,ends_at_ms:end,quest_keys:q};}
private function snap(rev:int,rows:Array,catalog:Array=null):void {ContentOperationsState.applySnapshot({schema_version:1,full_snapshot:true,revision:rev,catalog_digest:new Array(65).join("a"),server_time_ms:1000,states:rows,catalog:catalog});}
private function action(open:Boolean,end:Object=null,q:Array=null,m:Array=null):Object{return {enabled:open,ends_at_ms:end,quest_keys:q,mission_keys:m};}
private function row2(key:String,actions:Object):Object{return {key:key,instance_id:key+":original",actions:actions};}
private function snap2(rev:int,rows:Array,entries:Array=null):void {ContentOperationsState.applySnapshot({schema_version:2,full_snapshot:true,revision:rev,catalog_digest:new Array(65).join("a"),server_time_ms:1000,states:rows,catalog:entries});}
public function StateTest() {
var force:Array=[Option,IntMap,EventIdKind,ChallengeDungeonEventLogic,PassCardEventTable,TimeRange,BoxGachaLogic,EventItemShopProductLogic,ShopProductBuyableState,DateUtil];
var result:Object;
try {
snap2(0,[row2("pass_card_event:17",{claim:action(false)})]);
check(ContentOperationsState.selectPass({globalLogic:{getTime:function():Number{return 1000;}},logicAssets:{getMasterTable:function(c:Class):Object{return {get_data:function():Object{return {keys:function():Array{return [];}};}};}}},"id")===Option.None,"claim-only snapshot does not create a current pass");
var untouchedLabels:Array=[];
ContentOperationsState.updatePassView({peek:{passCardId:17},templateView:{timeRangeText:Option.Some({texts:[{set_text:function(v:String):void{untouchedLabels.push(v);}}]})}});
check(untouchedLabels.length==0,"v2 disabling only claim preserves original visible label");
check(ContentOperationsState.contentLabel({idKind:{tag:"PassCardEvent",params:[1]},missionValues:{event_id:17}})===null,"v2 disabling only claim does not label whole content closed");
snap(1,[row("gacha:1",true),row("tower_dungeon_event:1",true)]);
check(ContentOperationsState.decision("gacha:1","enter")==1,"open");
snap(2,[row("gacha:1",false)]);check(ContentOperationsState.decision("gacha:1","visible")==0,"closed");
check(ContentOperationsState.decision("tower_dungeon_event:1","visible")==0,"missing controlled closes");
snap(3,[row("gacha:1",true),row("tower_dungeon_event:2",true)], [{key:"tower_dungeon_event:2",entry:{kind:"TowerDungeonEvent",id:2}}]);
check(ContentOperationsState.decision("gacha:1","visible")==1,"reopen");
var list:Object={eventListValuesArray:[{values:{event:EventIdKind.TowerDungeonEvent(1)}}]};
var ids:Array=ContentOperationsState.eventIds(list);check(ids.length==0,"catalog-only event cannot be injected into another native folder");
snap(4,[row("gacha:1",false)]);check(ContentOperationsState.eventIds(list).length==0,"catalog deletion removes old entry");
snap(5,[row("challenge_dungeon_event:1",true,["13:1017"])]);
var event:Object=new ChallengeDungeonEventLogic();
var quest:Object={id:1017,challengeDungeonEvent:event,get_category:function():Object{return {id:13};}};
check(ContentOperationsState.questDecision(quest,"enter")==1,"verified exact quest");quest.id=1018;
check(ContentOperationsState.questDecision(quest,"enter")==0,"unverified exact quest");
var global:Object={};ContentOperationsState.invalidateGlobal(global);
check(global.gachaRepositoryCache===Option.None && global.questRepositoryCache===Option.None && global.specialExchangeCampaignRepositoryCache===Option.None,"actual cache slots cleared");
var repo:Object={gachaLoicTable:{old:1},gachaCombebackPeriod:{old:1},gachaStarskPeriod:{old:1}};
ContentOperationsState.gachaCache(repo);check(repo.gachaLoicTable is IntMap && !repo.gachaLoicTable.h.hasOwnProperty("old"),"stale Some to Some cache removed");
snap(6,[row("gacha:1",true,null,1)]);check(ContentOperationsState.decision("gacha:1","enter")==0,"real expiry");
snap(7,[row("gacha:1",true)]);ContentOperationsState.applySnapshot({});check(ContentOperationsState.decision("gacha:1","enter")==0,"malformed snapshot fails closed");
snap(8,[row("gacha:1",true)]);snap(7,[row("gacha:1",false)]);check(ContentOperationsState.decision("gacha:1","enter")==1,"old revision rejected");
var calls:Array=[],requests:Array=[];
var remote:Object={requestQueue:{addRequest:function(r:Object):void{requests.push(r);}}};
var scene:Object={globalLogic:global,logic:{remote:remote},logicStatus:{isDuringChangingScene:false},sceneKind:{index:0,params:[{tag:"EventTop"}]},changeSceneSimply:function(t:Object):void{calls.push(t);}};
ContentOperationsState.tick(scene);
snap(9,[row("gacha:1",false)]);ContentOperationsState.tick(scene);
check(requests.length==0 && calls.length==0,"local maintenance never polls or dispatches scene transitions");
scene.sceneKind.params[0]={tag:"Battle"};snap(10,[row("gacha:1",true)]);ContentOperationsState.tick(scene);
check(requests.length==0 && calls.length==0,"snapshot changes never interrupt battle or request refresh");
var pass:Object=row("pass_card_event:15",true);pass.mission_keys=["8:101"];
snap(11,[pass,row("box_gacha:48",true),row("carnival_event:1",true),row("event_item_shop:9",true)]);
var table:Object={keys:function():Array{return [15];},exists:function(id:int):Boolean{return id==15;},"get":function(id:int):Object{return {id:id,start_time:0,end_time:500};}};
var passRepo:Object={globalLogic:{getTime:function():Number{return 1000;}},logicAssets:{getMasterTable:function(c:Class):Object{return {get_data:function():Object{return table;}};}}};
check(ContentOperationsState.selectPass(passRepo,"id").params[0]==15,"operator-visible pass becomes the native current pass");
var mission:Object={idKind:{tag:"PassCardEvent",params:[101]},missionValues:{event_id:15}};
check(ContentOperationsState.contentDecision(mission,"enter")==1,"exact pass mission enabled");mission.idKind.params[0]=102;
check(ContentOperationsState.contentDecision(mission,"enter")==0,"unverified pass mission excluded");
check(ContentOperationsState.contentPeriod(new BoxGachaLogic(),"enter").endTime===Option.None,"box generic native period keeps original open-ended Option contract");
var product:EventItemShopProductLogic=new EventItemShopProductLogic();check(ContentOperationsState.contentDecision(product,"exchange")==1,"item and parent open");
snap(12,[pass,row("box_gacha:48",true),row("carnival_event:1",false),row("event_item_shop:9",true)]);
check(ContentOperationsState.contentDecision(product,"exchange")==0,"closed parent defeats individual open");
snap(13,[pass,row("carnival_event:1",true),row("event_item_shop:9",false)]);
check(ContentOperationsState.contentDecision(product,"exchange")==0,"closed individual defeats parent open");
check(ContentOperationsState.shopBuyGate(product)===ShopProductBuyableState.OutOfStock,"closed stale product disabled before buy");
var labels:Array=[];var text:Object={set_text:function(v:String):void{labels.push(v);},visible:true};
ContentOperationsState.updatePassView({peek:{passCardId:15},templateView:{timeRangeText:Option.Some({texts:[text]})}});
check(labels[0]=="常驻开放","pass date rendered from state");
snap(14,[pass,row("pass_card_event:16",true)]);check(ContentOperationsState.selectPass(passRepo,"id")===Option.None,"multiple pass conflict fails closed");
snap(15,[]);check(ContentOperationsState.selectPass(passRepo,"id")===Option.None,"closed pass does not revive old master");
snap(16,[pass]);mission.idKind.params[0]=101;
check(ContentOperationsState.missionRemaining(mission,"event")===Option.None,"permanent mission has no false deadline");
check(ContentOperationsState.missionRemaining(mission,"daily").params[0]<=86400000,"daily mission retains recurrence limit");
ContentOperationsState.tick(scene);
check(requests.length==0,"later local updates remain network free");
var scoped:Object=row("active_mission_event:1",true);scoped.mission_keys=["0:101"];
snap(17,[scoped,row("challenge_dungeon_event:1",true,["13:1017"])],[
 {key:"active_mission_event:1",mission_keys:["0:101","0:102"]},
 {key:"challenge_dungeon_event:1",quest_keys:["13:1017","13:1018"]}]);
var excluded:Object={missionId:102,eventId:1};
check(ContentOperationsState.contentDecision(excluded,"enter")==0,"catalog excluded mission cannot fall back");
var excludedQuest:Object={id:1018,get_category:function():Object{return {id:13};}};
check(ContentOperationsState.questDecision(excludedQuest,"enter")==0,"catalog excluded quest cannot fall back");
snap(18,[row("gacha:1",false)]);check(ContentOperationsState.gachaExchangeProducts({gachaId:1}).length==0,"closed gacha exchange list removed");
var directMission:Object={idKind:{tag:"Regular",params:[1]},missionValues:{}};
snap(19,[row("mission_regular:1",false)]);check(ContentOperationsState.contentDecision(directMission,"enter")==0,"direct regular mission null scope remains closed");
var unverifiedProduct:EventItemShopProductLogic=new EventItemShopProductLogic();unverifiedProduct.id.params[0]=10;
snap(20,[row("carnival_event:1",true)]);
check(ContentOperationsState.contentDecision(unverifiedProduct,"exchange")==-1,"open parent does not authorize unverified product");
check(ContentOperationsState.shopBuyGate(unverifiedProduct)===null,"unverified product retains original purchase rules");
snap(21,[row("carnival_event:1",false)]);
check(ContentOperationsState.contentDecision(unverifiedProduct,"exchange")==0,"closed parent blocks unverified product");
var browseOnly:Object=row("box_gacha:48",false);browseOnly.visible=true;snap(22,[browseOnly]);
check(ContentOperationsState.contentDecision(new BoxGachaLogic(),"visible")==1,"read only box remains visible");
check(ContentOperationsState.contentDecision(new BoxGachaLogic(),"enter")==0,"read only box remains nonparticipating");
snap2(100,[row2("gacha:900",{visible:action(true),enter:action(true,1)})]);
check(ContentOperationsState.decision("gacha:900","visible")==1,"v2 independently visible");
check(ContentOperationsState.decision("gacha:900","enter")==0,"v2 independent enter expiry");
check(ContentOperationsState.decision("gacha:900","exchange")==-1 && ContentOperationsState.gachaExchangeProducts({gachaId:900})===null,"v2 missing exchange preserves original policy");
snap2(101,[row2("gacha:900",{enter:action(true)})]);
check(ContentOperationsState.decision("gacha:900","visible")==0,"v2 missing previously controlled action closes");
check(ContentOperationsState.decision("gacha:900","exchange")==-1,"v2 never controlled action still falls back");
snap2(102,[row2("challenge_dungeon_event:9",{visible:action(true)}),row2("active_mission_event:9",{visible:action(true)})],[{key:"active_mission_event:9",mission_keys:["0:901"]}]);
var freshEvent:ChallengeDungeonEventLogic=new ChallengeDungeonEventLogic();freshEvent.id=9;
check(ContentOperationsState.contentEnd(freshEvent,"enter")===null && ContentOperationsState.contentEnd(freshEvent,"exchange")===null,"v2 visible only retains original event action end getters");
var originalEventEnd:Object=ContentOperationsState.contentEnd(freshEvent,"enter");
if(originalEventEnd===null) originalEventEnd=Option.Some(500);
check(!new TimeRange(0,originalEventEnd).isWithin(1000),"v2 visible only cannot reopen expired event fallback range");
var visibleMission:Object={missionId:901,eventId:9};
check(ContentOperationsState.missionRemaining(visibleMission,"event")===null,"v2 visible only retains original remaining time");
var allowedEnter:Array=["0:901"],allowedClaim:Array=["0:901","0:902"];
snap2(103,[row2("active_mission_event:9",{enter:action(true,61000,null,allowedEnter),claim:action(true,null,null,allowedClaim)})],[{key:"active_mission_event:9",mission_keys:["0:901","0:902","0:903"]}]);
check(ContentOperationsState.missionRemaining(visibleMission,"event").params[0]>0,"v2 enter deadline independent of visible");
var claimMission:Object={missionId:902,eventId:9};
check(ContentOperationsState.contentDecision(claimMission,"enter")==0 && ContentOperationsState.contentDecision(claimMission,"claim")==1,"v2 enter and claim scopes independent");
claimMission.missionId=903;allowedEnter.push("0:903");
check(ContentOperationsState.contentDecision(claimMission,"enter")==0 && ContentOperationsState.contentDecision(claimMission,"claim")==0,"v2 excluded catalog member closed and input cloned");
check(ContentOperationsState.contentDecision(claimMission,"exchange")==-1,"v2 mission unmanaged action retains original policy");
var enter12:Array=["6:57","6:58","6:59","6:60","7:57","7:58","8:86","8:87","8:88","8:89","8:90","8:91"];
var claim14:Array=enter12.concat(["7:59","7:60"]);
snap2(104,[row2("pass_card_event:15",{visible:action(true),enter:action(true,null,null,enter12),claim:action(true,null,null,claim14)})],[{key:"pass_card_event:15",mission_keys:claim14}]);
var weekly:Object={idKind:{tag:"PassCardWeek",params:[59]},missionValues:{event_id:15}};
check(ContentOperationsState.contentDecision(weekly,"enter")==0 && ContentOperationsState.contentDecision(weekly,"claim")==1,"v2 pass12 enter14 claim excludes unsupported fact writer");
weekly.idKind.params[0]=57;
check(ContentOperationsState.contentDecision(weekly,"enter")==1 && ContentOperationsState.contentDecision(weekly,"claim")==1,"v2 verified pass mission shares both permissions");
snap2(105,[row2("pass_card_event:15",{visible:action(false),claim:action(true,null,null,claim14)}),row2("pass_card_event:16",{visible:action(true)})],[{key:"pass_card_event:15",mission_keys:claim14}]);
var table16:Object={keys:function():Array{return [15,16];},exists:function(id:int):Boolean{return id==15 || id==16;},"get":function(id:int):Object{return {id:id,start_time:0,end_time:500};}};
var repo16:Object={globalLogic:{getTime:function():Number{return 1000;}},logicAssets:{getMasterTable:function(c:Class):Object{return {get_data:function():Object{return table16;}};}}};
check(ContentOperationsState.selectPass(repo16,"id").params[0]==16,"v2 current visible pass precedes old claim pass");
snap2(106,[row2("pass_card_event:15",{claim:action(true,null,null,claim14)})],[{key:"pass_card_event:15",mission_keys:claim14}]);
labels=[];ContentOperationsState.updatePassView({peek:{passCardId:15},templateView:{timeRangeText:Option.Some({texts:[text]})}});
check(labels[0]=="仅可领奖","v2 claim only pass label does not imply participation");
var originalTable:Object={keys:function():Array{return [15,18];},exists:function(id:int):Boolean{return id==15 || id==18;},"get":function(id:int):Object{return {id:id,start_time:0,end_time:id==18?2000:500};}};
var originalRepo:Object={globalLogic:{getTime:function():Number{return 1000;}},logicAssets:{getMasterTable:function(c:Class):Object{return {get_data:function():Object{return originalTable;}};}}};
check(ContentOperationsState.selectPass(originalRepo,"id")===Option.None,"claim rights cannot select an old or unreviewed master period");
snap2(107,[row2("active_mission_event:9",{enter:action(true,null,null,["0:999"])})],[{key:"active_mission_event:9",mission_keys:["0:901"]}]);
check(ContentOperationsState.contentDecision(visibleMission,"enter")==0,"v2 foreign scope fails closed");
snap2(108,[row2("active_mission_event:9",{enter:action(true,null,null,["0:901"])})]);
check(ContentOperationsState.contentDecision(visibleMission,"enter")==0,"v2 missing scope catalog fails closed");
snap2(109,[row2("active_mission_event:9",{enter:action(true,null,null,["0:901"])})],[{key:"active_mission_event:9",mission_keys:["0:901"]},{key:"active_mission_event:9",mission_keys:["0:901"]}]);
check(ContentOperationsState.contentDecision(visibleMission,"enter")==0,"v2 duplicate catalog fails closed");
snap2(110,[row2("gacha:900",{visible:action(true)})]);snap2(109,[row2("gacha:900",{visible:action(false)})]);
check(ContentOperationsState.decision("gacha:900","visible")==1,"v2 stale revision rejected");
ContentOperationsState.applySnapshot({});
check(ContentOperationsState.decision("gacha:999","enter")==-1,"v2 malformed snapshot preserves never controlled content");
snap2(111,[row2("gacha:905",{visible:action(true)}),row2("gacha:906",{enter:action(true)}),row2("gacha:907",{visible:action(true,0)}),row2("event_item_shop:900",{exchange:action(true)}),row2("event_item_shop:901",{visible:action(true)})]);
var oldGacha:Object={id:905,period:new TimeRange(0,Option.Some(500)),isComeback:function():Boolean{return false;},isStarsGacha:function():Boolean{return false;},get_onceTicketItemId:function():Object{return Option.Some(7);},get_tenTimesTicketItemId:function():Object{return Option.None;},get_ticketExpiryTime:function():Object{return Option.Some(2000);}};
check(ContentOperationsState.gachaEnterGate(oldGacha,{},1000,false)==0,"v2 visible only cannot reopen expired gacha availability");
check(ContentOperationsState.gachaEnterGate(oldGacha,{hasItem:function(id:int):Boolean{return id==7;}},1000,true)==-1,"v2 original ticket extension and caller time preserved");
check(ContentOperationsState.gachaEnterGate(oldGacha,{},400,false)==-1,"v2 original active gacha preserves later eligibility rules");
check(ContentOperationsState.gachaStart(oldGacha).params[0]==0 && ContentOperationsState.gachaEnd(oldGacha).params[0]==ContentOperationsState.OPEN_END_MS && ContentOperationsState.gachaPeriod(oldGacha).params[0].endTime===Option.None && ContentOperationsState.gachaHasEnd(oldGacha)==0,"v2 visible-only pool provides concrete preload end while generic period retains native None");
oldGacha.id=906;
check(ContentOperationsState.gachaDecision(oldGacha,"visible")==-1 && ContentOperationsState.gachaStart(oldGacha)===null && ContentOperationsState.gachaEnd(oldGacha)===null && ContentOperationsState.gachaPeriod(oldGacha)===null,"v2 enter only cannot override original visible gacha dates");
check(ContentOperationsState.decision("gacha:907","visible")==0 && ContentOperationsState.decision("gacha:905","visible")==1,"v2 zero expiry closes only its action");
var partialShop:EventItemShopProductLogic=new EventItemShopProductLogic();partialShop.id.params[0]=900;partialShop.eventItemValues={event:{tag:"CarnivalEvent",params:[999]}};
check(ContentOperationsState.shopSharedEnd(partialShop)===null && ContentOperationsState.contentDecision(partialShop,"visible")==-1,"v2 exchange only cannot override original visible shop dates");
partialShop.id.params[0]=901;
check(ContentOperationsState.shopSharedEnd(partialShop)===null,"v2 visible only retains original shared shop end");

var defaults:Object={version:1,explicit_actions_override_defaults:true,actions:{visible:{closed_keys:["gacha:940","pass_card_event:15"],qualified_rights_keys:[]},enter:{closed_keys:["gacha:940","pass_card_event:15"],qualified_rights_keys:[]},claim:{closed_keys:[],qualified_rights_keys:["pass_card_event:15"]},exchange:{closed_keys:["event_item_shop:900"],qualified_rights_keys:["gacha:940"]}}};
for each(var legacyAction:String in ["visible","enter","claim","exchange"]) defaults.actions[legacyAction].legacy_keys=["general_shop:100001","mission_regular:901"];
ContentOperationsState.applySnapshot({schema_version:2,full_snapshot:true,revision:112,catalog_digest:new Array(65).join("a"),server_time_ms:100000,states:[row2("gacha:940",{visible:action(true),enter:action(true)}),row2("pass_card_event:14",{visible:action(true),enter:action(true),claim:action(true)})],catalog:[],default_policy:defaults});
check(ContentOperationsState.decision("gacha:940","enter")==1,"default closed list is overridden by explicit scoped permission");
check(ContentOperationsState.decision("event_item_shop:900","exchange")==0,"default unapproved timed product fails closed");
check(ContentOperationsState.decision("gacha:940","exchange")==1,"earned exchange rights retained separately from participation");
check(ContentOperationsState.decision("gacha:999999","enter")==0,"unknown new gacha cannot silently borrow dates");
check(ContentOperationsState.decision("general_shop:100001","visible")==-1 && ContentOperationsState.decision("general_shop:100001","exchange")==-1,"known permanent core shop retains original visibility and purchase rules");
check(ContentOperationsState.decision("general_shop:999999","exchange")==0,"unknown new core-family product remains denied");
check(ContentOperationsState.decision("mission_regular:901","enter")==-1 && ContentOperationsState.decision("mission_regular:99999","enter")==0,"known core mission retains original policy while unknown new mission is denied");
check(ContentOperationsState.questDecision({id:2080001,get_category:function():Object{return {id:26};},hardMultiEvent:new ChallengeDungeonEventLogic()},"enter")==-1,"explicit ordinary hard boss bypasses seasonal unknown fallback");
var clock:Object={serverTime:9000000,elapsedTime:456,getAppTime:function():Number{return this.serverTime+this.elapsedTime;}};
var cg:Object={logicStatus:{currentTime:Option.Some(clock)}};ContentOperationsState.syncGlobalTime(cg);
check(clock.elapsedTime==456 && clock.getAppTime()>=100000 && clock.getAppTime()<100100,"GlobalLogic currentTime epoch rebased while elapsed duration preserved");
var globalType:Class=getDefinitionByName("pinball.context.global::GlobalLogic") as Class;
var clockType:Class=getDefinitionByName("pinball.context.clock::ComplexTime") as Class;
var actualGlobal:Object=new globalType();var actualClock:Object=new clockType(9000000,321);actualGlobal.logicStatus={currentTime:Option.Some(actualClock)};
check(actualGlobal.getTime()>=100000 && actualGlobal.getTime()<100100 && actualClock.elapsedTime==321,"actual grafted production GlobalLogic.getTime executes rebasing and original getter");
check(actualGlobal.getOptionTime().index==0 && actualGlobal.getOptionTime().params[0]>=100000,"actual grafted production GlobalLogic.getOptionTime returns actual synchronized epoch");
actualGlobal.logicStatus.currentTime=Option.None;check(actualGlobal.getOptionTime()===Option.None,"actual production Option.None fallback preserved");
var helperType:Class=getDefinitionByName("cn.content::ContentOperationsState") as Class;
for each(var removed:String in ["attachHomeHistory","initHistoricalPass","historicalPassButtonGate","historicalBoxList","resumeRefresh","refreshSuccess","refreshError","refreshCancelled","replaceExchangeList"])
    check(!(removed in helperType),"removed player selector or refresh API: "+removed);
var loginTable:Object={keys:function():Array{return [14,15,18];},exists:function(id:int):Boolean{return id==14||id==15||id==18;},"get":function(id:int):Object{return {id:id,start_time:0,end_time:999999999};}};
var loginRepo:Object={globalLogic:{getTime:function():Number{return 100000;}},logicAssets:{getMasterTable:function(c:Class):Object{return {get_data:function():Object{return loginTable;}};}}};
var loginList:Object={eventListValuesArray:[{values:{event:EventIdKind.TowerDungeonEvent(2)}},{values:{event:EventIdKind.TowerDungeonEvent(3)}}]};
var loginGacha:Object={id:941,isComeback:function():Boolean{return false;},isStarsGacha:function():Boolean{return false;}};
ContentOperationsState.captureResponse({data:{content_operations:{schema_version:2,full_snapshot:true,revision:113,catalog_digest:new Array(65).join("a"),server_time_ms:100001,
 states:[row2("gacha:941",{visible:action(true),enter:action(true)}),row2("gacha:942",{visible:action(false),enter:action(false)}),row2("tower_dungeon_event:2",{visible:action(true)}),row2("tower_dungeon_event:3",{visible:action(false)}),row2("pass_card_event:14",{visible:action(true),claim:action(true)}),row2("pass_card_event:15",{visible:action(false),claim:action(true)})],
 catalog:[{key:"tower_dungeon_event:2",entry:{kind:"TowerDungeonEvent",id:2}},{key:"tower_dungeon_event:3",entry:{kind:"TowerDungeonEvent",id:3}}],default_policy:defaults}}});
check(ContentOperationsState.eventIds(loginList).length==1 && ContentOperationsState.eventIds(loginList)[0].params[0]==2,"login snapshot A publishes only native event A");
check(ContentOperationsState.gachaDecision(loginGacha,"visible")==1 && ContentOperationsState.decision("gacha:942","visible")==0,"login snapshot A opens gacha A and closes B");
check(ContentOperationsState.selectPass(loginRepo,"id").params[0]==14,"login snapshot A selects only visible native pass A");
global.gachaRepositoryCache={stale:true};ContentOperationsState.tick(scene);
check(global.gachaRepositoryCache===Option.None,"new login snapshot invalidates native repositories");
ContentOperationsState.captureResponse({data:{content_operations:{schema_version:2,full_snapshot:true,revision:114,catalog_digest:new Array(65).join("a"),server_time_ms:100002,
 states:[row2("gacha:941",{visible:action(false),enter:action(false)}),row2("gacha:942",{visible:action(true),enter:action(true)}),row2("tower_dungeon_event:2",{visible:action(false)}),row2("tower_dungeon_event:3",{visible:action(true)}),row2("pass_card_event:14",{visible:action(false),claim:action(true)}),row2("pass_card_event:15",{visible:action(true),claim:action(true)})],
 catalog:[{key:"tower_dungeon_event:2",entry:{kind:"TowerDungeonEvent",id:2}},{key:"tower_dungeon_event:3",entry:{kind:"TowerDungeonEvent",id:3}}],default_policy:defaults}}});
check(ContentOperationsState.eventIds(loginList).length==1 && ContentOperationsState.eventIds(loginList)[0].params[0]==3,"relogin snapshot B removes native event A and publishes B");
check(ContentOperationsState.gachaDecision(loginGacha,"visible")==0 && ContentOperationsState.decision("gacha:942","enter")==1,"relogin snapshot B closes gacha A and opens B");
check(ContentOperationsState.selectPass(loginRepo,"id").params[0]==15,"relogin snapshot B replaces native current pass A with B");
ContentOperationsState.captureResponse({data:{content_operations:{schema_version:2,full_snapshot:true,revision:115,catalog_digest:new Array(65).join("a"),server_time_ms:100003,
 states:[row2("pass_card_event:14",{visible:action(false),claim:action(true)}),row2("pass_card_event:15",{visible:action(false),claim:action(true)})],catalog:[],default_policy:defaults}}});
check(ContentOperationsState.selectPass(loginRepo,"id")===Option.None,"all passes closed despite retained claim rights and still-current master dates");
check(ContentOperationsState.decision("pass_card_event:14","claim")==1 && ContentOperationsState.decision("pass_card_event:15","claim")==1,"closing native pass entrance preserves snapshot claim entitlements");
var legacyDefaults:Object=JSON.parse(JSON.stringify(defaults));legacyDefaults.actions.visible.legacy_keys.push("pass_card_event:18");
ContentOperationsState.captureResponse({data:{content_operations:{schema_version:2,full_snapshot:true,revision:116,catalog_digest:new Array(65).join("a"),server_time_ms:100004,
 states:[row2("pass_card_event:14",{visible:action(false),claim:action(true)})],catalog:[],default_policy:legacyDefaults}}});
check(ContentOperationsState.selectPass(loginRepo,"id").params[0]==18 && ContentOperationsState.selectPass(loginRepo,"event").params[0].id==18,"only explicit reviewed legacy pass may retain native calendar selection");
ContentOperationsState.tick(scene);check(requests.length==0 && calls.length==0,"all login and closure changes stay passive without network or BlackOut");
snap2(117,[row2("box_gacha:1001",{visible:action(false),enter:action(false),claim:action(false)})]);
check(ContentOperationsState.boxActionGate({boxGachaId:1001},"enter")==0 && ContentOperationsState.boxActionGate({boxGachaId:1001},"claim")==0,"native box actions obey operator closure without historical state");
snap2(118,[row2("box_gacha:1001",{visible:action(true),enter:action(true),claim:action(true)})]);
check(ContentOperationsState.boxActionGate({boxGachaId:1001},"enter")==-1 && ContentOperationsState.boxActionGate({boxGachaId:1001},"claim")==-1,"open native box actions preserve original execution path");
var boxLabels:Array=[];
check(ContentOperationsState.updateBoxPeriod({peek:{boxGachaId:1001},layout:{getImage:function(key:String,meta:Object):Object{return {};},getText:function(key:String,meta:Object):Object{return {set_text:function(value:String):void{boxLabels.push(value);}};}}}) && boxLabels[0]=="常驻开放","native box period uses operator state without custom text widgets");
snap2(119,[row2("special_exchange_campaign:1",{visible:action(false),exchange:action(true)}),row2("start_dash_exchange_campaign:1",{visible:action(false),exchange:action(true)})]);
check(ContentOperationsState.decision("special_exchange_campaign:1","exchange")==1 && ContentOperationsState.decision("start_dash_exchange_campaign:1","exchange")==1,"original self-select exchange entitlements remain independent of visibility");
ContentOperationsState.applySnapshot({schema_version:2,full_snapshot:true,revision:120,catalog_digest:new Array(65).join("a"),server_time_ms:100001,states:[],catalog:[],default_policy:{version:1,explicit_actions_override_defaults:true,actions:{}}});
check(ContentOperationsState.decision("gacha:940","enter")==0,"malformed default policy cannot reopen previously managed content");

var nativeEventCases:Array=NATIVE_EVENT_CASES;
var nativeEventRows:Array=[];
for each(var nativeCase:Object in nativeEventCases) nativeEventRows.push(row2(nativeCase.key+":1",{visible:action(true),enter:action(true),exchange:action(true)}));
snap2(121,nativeEventRows);
for each(nativeCase in nativeEventCases) {
 var nativeType:Class=getDefinitionByName(nativeCase.name) as Class;
 var nativeEvent:Object=new nativeType();
 check(ContentOperationsState.towerKey(nativeEvent)==nativeCase.key+":1","actual native sealed event getter key: "+nativeCase.name);
 check(nativeEvent.isWithinPeriod(1000),"actual native EventLogicBase period opens controlled expired event: "+nativeCase.name);
 check(ContentOperationsState.contentDecision(nativeEvent,"enter")==1 && ContentOperationsState.contentPeriod(nativeEvent,"enter").endTime===Option.None,"shared content periods preserve native None and event identity: "+nativeCase.name);
}
var scoreType:Class=getDefinitionByName("pinball.common.data.quest.event.scoreAttack::ScoreAttackEventLogic") as Class;
var scoreEvent:Object=new scoreType();check(!("id" in scoreEvent) && ("eventId" in scoreEvent),"ScoreAttack fixture is sealed with actual eventId and no fictitious id slot");
var soloType:Class=getDefinitionByName("pinball.common.data.quest.event.soloTimeAttack::SoloTimeAttackEventLogic") as Class;
var soloEvent:Object=new soloType();check(!("id" in soloEvent) && ("eventId" in soloEvent),"SoloTimeAttack fixture is sealed with actual eventId and no fictitious id slot");
var campaignType:Class=getDefinitionByName("pinball.common.data.quest.event.challengeDungeon::CampaignAppliedChallengeDungeonEventLogic") as Class;
var inheritedEvent:Object=new campaignType();check(ContentOperationsState.towerKey(inheritedEvent)=="challenge_dungeon_event:1" && inheritedEvent.isWithinPeriod(1000),"campaign subclass inherits actual native event getter and base period method");
snap2(122,[row2("score_attack_event:1",{visible:action(false),enter:action(false)})]);
check(!scoreEvent.isWithinPeriod(1000) && ContentOperationsState.towerDecision(scoreEvent,"enter")==0,"closed native ScoreAttack uses operator decision without property exception");
snap2(123,[]);scoreEvent.eventId=99;
check(ContentOperationsState.towerDecision(scoreEvent,"enter")==-1 && !scoreEvent.isWithinPeriod(1000),"unmanaged native event keeps actual original expired calendar path");
check(ContentOperationsState.towerKey(null)=="" && ContentOperationsState.towerKey({})=="","non-event inputs preserve original unsupported fallback without fabricated keys");

var reloadMessage:String=ContentOperationsState.CONTENT_CLIENT_RELOAD_MESSAGE;
var routeLogic:Logic=new Logic(),routeScene:ReloadTestScene=new ReloadTestScene();
var notificationErrors:Array=[],uiKeys:Array=[],clockReadCount:int=0,unalteredClock:Object={serverTime:777777,elapsedTime:123};
routeLogic.state=routeScene;routeLogic.asset={getUiString:function(key:String):String{uiKeys.push(key);return "native date-change message";}};
routeLogic.attention={notifyRemoteError:function(error:Object):void{notificationErrors.push(error);}};
routeLogic.globalLogic={getTime:function():Number{clockReadCount++;return unalteredClock.serverTime+unalteredClock.elapsedTime;}};
var markedError:RemoteError=new RemoteError(new RemoteErrorKind("WholeMaintenanceError",9,[reloadMessage]));
check(ContentOperationsState.isContentReload(markedError),"reserved exact maintenance-kind message recognized");
check(!ContentOperationsState.isContentReload(null) && !ContentOperationsState.isContentReload(new RemoteError(new RemoteErrorKind("WholeMaintenanceError",9,[reloadMessage+" "]))) && !ContentOperationsState.isContentReload(new RemoteError(new RemoteErrorKind("LoginTokenNotMatch",19,[reloadMessage]))),"null near-match and other error kinds cannot request operations reload");
check(!ContentOperationsState.isContentReload(new RemoteError(new RemoteErrorKind("WholeMaintenanceError",9,[reloadMessage,1]))) && !ContentOperationsState.isContentReload({kind:{tag:"WholeMaintenanceError",index:8,params:[reloadMessage]}}),"reserved reload contract requires exact enum identity and one unchanged message");
routeLogic.remoteCommonInput(new RemoteCommonInput(markedError));
check(CrashUtil.errors.length==1 && CrashUtil.errors[0]===markedError && notificationErrors.length==1 && notificationErrors[0]===markedError,"actual native route preserves crash recording and attention error notification before reload");
check(uiKeys.length==1 && uiKeys[0]=="change_date_dialog_message" && routeScene.dialogs.length==1 && routeScene.dialogs[0].error!==markedError && routeScene.dialogs[0].error.displayMessage=="native date-change message","actual production date-change dialog replaces marked maintenance error using original native UI key");
check(clockReadCount==1 && unalteredClock.serverTime==777777 && unalteredClock.elapsedTime==123 && routeScene.dialogs[0].error.internalMessage.indexOf("777900")>=0,"native reload samples actual time once without clock or elapsed-time mutation");
check(routeScene.titleCalls==0,"native date-change route waits for dialog confirmation");
routeScene.dialogs[0].callback();check(routeScene.titleCalls==1,"native date-change dialog keeps its original title-scene callback");
var ordinaryMaintenance:RemoteError=new RemoteError(new RemoteErrorKind("WholeMaintenanceError",9,["ordinary maintenance"]));
routeLogic.remoteCommonInput(new RemoteCommonInput(ordinaryMaintenance));
check(routeScene.dialogs.length==2 && routeScene.dialogs[1].error===ordinaryMaintenance && uiKeys.length==1 && clockReadCount==1,"ordinary maintenance retains original error object and native switch without date dialog");
var ordinaryTakeover:RemoteError=new RemoteError(new RemoteErrorKind("LoginTokenNotMatch",19,[]));routeLogic.remoteCommonInput(new RemoteCommonInput(ordinaryTakeover));
check(routeScene.dialogs.length==3 && routeScene.dialogs[2].error===ordinaryTakeover && CrashUtil.errors.length==3 && notificationErrors.length==3,"unrelated native remote errors keep original switch and notifications");
routeScene.dialogs[1].callback();routeScene.dialogs[2].callback();check(routeScene.titleCalls==3,"ordinary maintenance and takeover callbacks keep their native title action");

result={passed:true,assertions:assertions,checks:checks,gameExecuted:false,deviceTested:false};
} catch(e:Error) {result={passed:false,assertions:assertions,error:e.toString(),stack:e.getStackTrace(),nativeObservations:nativeObservations};}
var file:File=new File(OUTPUT_PATH);var stream:FileStream=new FileStream();stream.open(file,FileMode.WRITE);stream.writeUTFBytes(JSON.stringify(result));stream.close();NativeApplication.nativeApplication.exit(result.passed?0:1);
}}
}"""
def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--production-work',type=Path);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--java',type=Path,required=True);mode=p.add_mutually_exclusive_group();mode.add_argument('--policy-fixture',type=Path);mode.add_argument('--expect-f1069',action='store_true');mode.add_argument('--native-regression',action='store_true');mode.add_argument('--history-catalog',type=Path);mode.add_argument('--request-identity',action='store_true');mode.add_argument('--native-entry',action='store_true');p.add_argument('--expect-native-baseline',action='store_true');p.add_argument('--expect-campaign-date-regressions',action='store_true');a=p.parse_args()
 if a.expect_native_baseline and not a.native_regression:p.error('--expect-native-baseline requires --native-regression')
 if a.expect_campaign_date_regressions and (not a.native_regression or a.expect_native_baseline):p.error('--expect-campaign-date-regressions requires candidate native suite without --expect-native-baseline')
 production=a.production_work or a.work
 production_files=[production/'content-operations-android.swf',production/'production-helper.abc']
 if (production/'content-state.swc').exists():production_files.append(production/'content-state.swc')
 production_identity={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in production_files}
 root=a.work/('runtime-entry-test' if a.native_entry else 'runtime-identity-test' if a.request_identity else 'runtime-policy-test' if a.policy_fixture else 'runtime-f1069-test' if a.expect_f1069 else 'runtime-history-test' if a.history_catalog else 'runtime-native-test' if a.native_regression else 'runtime-test');root.mkdir(parents=True,exist_ok=True)
 spec=importlib.util.spec_from_file_location('content_runtime_graft',HERE/'build_bridge.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
 prod_tags=builder.sc.parts(production/'content-operations-android.swf')[2]
 production_main=next(row[3] for row in prod_tags if row[3] and any(row[3].mn_name(i[0])=='pinball.context.global::GlobalLogic' for i in row[3].instances))
 fixture_stubs=STUBS;native_labels=[];native_includes=[]
 if a.history_catalog:
  from historical_runtime_fixtures import prepare
  fixture_stubs,native_labels,native_includes=prepare(STUBS,EVENT_CASES,production_main,builder)
 if a.native_regression:
  from native_runtime_fixtures import prepare,BODY,DATE_SCENES,import_date_prologue
  fixture_stubs,native_labels,native_includes=prepare(STUBS,EVENT_CASES,production_main,builder)
 if a.native_entry:
  from entry_runtime_fixtures import prepare
  fixture_stubs,native_labels,native_includes=prepare(STUBS,EVENT_CASES,production_main,builder)
 if a.request_identity:
  from request_identity_runtime_fixtures import prepare
  fixture_stubs,native_labels,native_includes=prepare(STUBS,EVENT_CASES,production_main,builder)
 for name,content in fixture_stubs.items():
  f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(content,encoding='utf8')
 output=a.work.resolve()/('air-entry-result.json' if a.native_entry else 'air-identity-result.json' if a.request_identity else 'air-policy-result.json' if a.policy_fixture else 'air-f1069-result.json' if a.expect_f1069 else 'air-history-result.json' if a.history_catalog else 'air-native-result.json' if a.native_regression else 'air-runtime-result.json')
 main=MAIN
 if a.policy_fixture:
  policy_path=json.dumps(str(a.policy_fixture.resolve()))
  policy_body='''
var policyFile:File=new File(POLICY_PATH);var policyStream:FileStream=new FileStream();
policyStream.open(policyFile,FileMode.READ);var policy:Object=JSON.parse(policyStream.readUTFBytes(policyStream.bytesAvailable));policyStream.close();
check(policy.snapshot.schema_version===2 && policy.snapshot.full_snapshot===true,"actual server full snapshot schema");
check(policy.expected is Array && policy.expected.length>=79000,"all catalog rows and four actions exported");
ContentOperationsState.applySnapshot(policy.snapshot);
for each(var expectation:Object in policy.expected) {
 var actual:int=ContentOperationsState.decision(expectation.key,expectation.action);
 if(actual!=int(expectation.decision))throw new Error("Server/client decision differs: "+expectation.key+"/"+expectation.action+" expected "+expectation.decision+" got "+actual);
 assertions++;
}
checks.push("every catalog action matches the authoritative server decision");
'''.replace('POLICY_PATH',policy_path)
  prefix,body=MAIN.split('try {',1)
  _,suffix=body.split('result={passed:true,assertions:assertions,checks:checks,gameExecuted:false,deviceTested:false};',1)
  main=prefix+'try {'+policy_body+'result={passed:true,assertions:assertions,checks:checks,expectedDecisions:policy.expected.length,controls:policy.snapshot.states.length,catalogDigest:policy.snapshot.catalog_digest,gameExecuted:false,deviceTested:false};'+suffix
 if a.expect_f1069:
  prefix,body=MAIN.split('try {',1)
  _,suffix=body.split('result={passed:true,assertions:assertions,checks:checks,gameExecuted:false,deviceTested:false};',1)
  regression_body='''
snap2(1,[row2("score_attack_event:1",{enter:action(true)}),row2("solo_time_attack_event:1",{enter:action(true)})]);
var regressions:Array=[];
for each(var eventName:String in ["pinball.common.data.quest.event.scoreAttack::ScoreAttackEventLogic","pinball.common.data.quest.event.soloTimeAttack::SoloTimeAttackEventLogic"]) {
 var eventType:Class=getDefinitionByName(eventName) as Class;var instance:Object=new eventType();
 check(!("id" in instance) && ("eventId" in instance),"actual sealed event fields: "+eventName);
 var reproduced:Boolean=false;
 try {instance.isWithinPeriod(1000);} catch(expected:ReferenceError) {
  reproduced=expected.errorID==1069 && expected.getStackTrace().indexOf("towerKey")>=0
    && expected.getStackTrace().indexOf("towerDecision")>=0 && expected.getStackTrace().indexOf("EventLogicBase/isWithinPeriod")>=0;
  regressions.push({name:eventName,error:expected.toString(),stack:expected.getStackTrace()});
 }
 check(reproduced,"R4 native period chain reproduces F1069: "+eventName);
}
'''
  main=prefix+'try {'+regression_body+'result={passed:true,expectedRegressionReproduced:true,assertions:assertions,checks:checks,regressions:regressions,gameExecuted:false,deviceTested:false};'+suffix
 if a.native_regression:
  prefix,body=MAIN.split('try {',1)
  _,suffix=body.split('result={passed:true,assertions:assertions,checks:checks,gameExecuted:false,deviceTested:false};',1)
  import assistant_runtime_fixtures as assistant
  native_body=(BODY+assistant.BODY).replace('EXPECT_NATIVE_BASELINE',str(a.expect_native_baseline).lower()).replace('EXPECT_CAMPAIGN_DATE_REGRESSIONS',str(a.expect_campaign_date_regressions).lower()).replace('NATIVE_DATE_SCENES',json.dumps(DATE_SCENES))
  main=prefix+'try {'+native_body+'result={passed:true,assertions:assertions,checks:checks,nativeObservations:nativeObservations,nativeRegressionBaseline:'+str(a.expect_native_baseline).lower()+',expectedCampaignDateRegressions:'+str(a.expect_campaign_date_regressions).lower()+',gameExecuted:false,deviceTested:false};'+suffix
 if a.history_catalog:
  from historical_runtime_fixtures import body as historical_body
  catalog=json.loads(a.history_catalog.read_text(encoding='utf-8-sig'))
  prefix,body=MAIN.split('try {',1)
  _,suffix=body.split('result={passed:true,assertions:assertions,checks:checks,gameExecuted:false,deviceTested:false};',1)
  main=prefix+'try {'+historical_body(catalog,root/'historical-parents.json')+'result={passed:true,assertions:assertions,checks:checks,historicalParentCount:1020,gameExecuted:false,deviceTested:false};'+suffix
 if a.request_identity:
  from request_identity_runtime_fixtures import BODY as identity_body
  prefix,body=MAIN.split('try {',1)
  _,suffix=body.split('result={passed:true,assertions:assertions,checks:checks,gameExecuted:false,deviceTested:false};',1)
  main=prefix+'try {'+identity_body+'result={passed:true,assertions:assertions,checks:checks,actualRequestQueueMethods:8,actualFactoryAndConstructorMethods:5,gameExecuted:false,deviceTested:false};'+suffix
  main=main.replace('import flash.display.Sprite;', 'import flash.display.Sprite;import flash.utils.getTimer;import flash.net.URLRequestHeader;')
 if a.native_entry:
  from entry_runtime_fixtures import BODY as entry_body
  prefix,body=MAIN.split('try {',1)
  _,suffix=body.split('result={passed:true,assertions:assertions,checks:checks,gameExecuted:false,deviceTested:false};',1)
  main=prefix+'try {'+entry_body+'result={passed:true,assertions:assertions,checks:checks,gameExecuted:false,deviceTested:false};'+suffix
  main=main.replace('import flash.display.Sprite;', 'import flash.display.Sprite;import flash.Boot;import pinball.context.global.GlobalLogic;')
 cases=[{'name':'pinball.common.data.quest.event.'+package+'::'+kind+'Logic','key':key,'field':package if package=='expertSingleEvent' else package+'Event'} for package,kind,key,_,_ in EVENT_CASES]
 (root/'StateTest.as').write_text(main.replace('[Option,None,IntMap','[Option,IntMap').replace('OUTPUT_PATH',json.dumps(str(output))).replace('NATIVE_EVENT_CASES',json.dumps(cases)),encoding='utf8')
 includes=['pinball.context.global.GlobalLogic','pinball.context.clock.ComplexTime','pinball.error.ClientError','flash.Boot','pinball.context.Logic','pinball.context.scene.ReloadTestScene','pinball.common.time._AppTime.AppTime_Impl_','pinball.debug.CrashUtil']+['pinball.common.data.quest.event.'+package+'.'+kind+'Logic' for package,kind,_,_,_ in EVENT_CASES]+['pinball.common.data.quest.event.challengeDungeon.CampaignAppliedChallengeDungeonEventLogic']+native_includes
 # Link the helper that actually produced the selected candidate, so concurrent
 # source editing cannot turn a historical negative fixture into a mixed build.
 library=production/'content-state.swc'
 helper_source=['-compiler.library-path+='+str(library)] if library.exists() else ['-compiler.source-path+='+str(HERE/'src')]
 command=[str(a.java),'-Dflexlib='+str(a.sdk/'frameworks'),'-jar',str(a.sdk/'lib/mxmlc-cli.jar'),'+configname=air','-swf-version=44','-target-player=32.0','-compiler.float=false','-includes='+','.join(includes),'-debug=true','-compiler.source-path='+str(root)]+helper_source+['-output='+str(root/'test.swf'),str(root/'StateTest.as')]
 r=subprocess.run(command,capture_output=True,timeout=120);(root/'compile.log').write_bytes(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError((r.stdout+r.stderr).decode('utf8','replace'))

 version,header,tags=builder.sc.parts(root/'test.swf');rows=[row for row in tags if row[0]==82];assert len(rows)==1;tag=rows[0]
 target=builder.view(tag[3]);receipts=[]
 main=production_main
 helper=builder.p.abcfmt.ABC((production/'production-helper.abc').read_bytes())
 event_labels=['pinball.common.data.quest.event.'+package+'::'+kind+'Logic/getEventId|1' for package,kind,_,_,_ in EVENT_CASES]+['pinball.common.data.quest.event::EventIdKind$/'+kind+'|1' for _,kind,_,_,_ in EVENT_CASES]+['pinball.common.data.quest.event.common::EventLogicBase/'+method+'|1' for method in ['isWithinPeriod','getPlayableTimeRange','get_startTime','get_playableEndTime']]
 for donor,labels in [(helper,None),(main,['pinball.context.global::GlobalLogic/getTime|1','pinball.context.global::GlobalLogic/getOptionTime|1','pinball.context::Logic/remoteCommonInput|1','pinball.context::Logic/openDateChangedDialog|1']+event_labels+native_labels)]:
  source=builder.view(donor);importer=builder.p.Importer(target,source)
  for label in labels or source.by_label:
   assert label in target.by_label,(label,'fixture missing production method')
   di,=source.by_label[label];ti,=target.by_label[label];prior=target.a.bodies[ti]
   if a.native_entry:
    # Production catch scopes (notably Type.enumEq) require their activation
    # flag as well as the exact method body. Keep fixture optional-argument ABI.
    target.a.methods[prior[0]][3]=(target.a.methods[prior[0]][3]&~2)|(donor.methods[donor.bodies[di][0]][3]&2)
   target.a.bodies[ti]=importer.body(di,prior[0])
   assert target.normalized(ti)==source.normalized(di),(label,'actual instructions/CFG differ')
   builder.p.check_body(target.a.bodies[ti],target.a)
   receipts.append({'label':label,'sourceCodeSha256':hashlib.sha256(donor.bodies[di][5]).hexdigest(),'normalizedInstructionsCfgExact':True})
 if a.native_regression:
  has_date_prologue=import_date_prologue(builder,target,main,receipts)
  if not a.expect_native_baseline:assert has_date_prologue,'candidate lacks native date constructor sanitizer prologue'
  import assistant_runtime_fixtures as assistant
  has_assistant_consumers=assistant.import_comparisons(builder,target,main,receipts)
  if not a.expect_native_baseline and not a.expect_campaign_date_regressions:assert has_assistant_consumers,'candidate lacks seven native assistant Some-consumer adapters'
 payload=tag[2]+target.a.serialize();tag[1]=struct.pack('<HI',(82<<6)|63,len(payload))+payload
 raw=header+b''.join(row[1] for row in tags);(root/'test.swf').write_bytes(b'FWS'+bytes([version])+struct.pack('<I',len(raw)+8)+raw)
 (a.work/('production-entry-import.json' if a.native_entry else 'production-identity-import.json' if a.request_identity else 'production-policy-import.json' if a.policy_fixture else 'production-f1069-import.json' if a.expect_f1069 else 'production-history-import.json' if a.history_catalog else 'production-native-import.json' if a.native_regression else 'production-runtime-import.json')).write_text(json.dumps({'sourceSwfSha256':hashlib.sha256((production/'content-operations-android.swf').read_bytes()).hexdigest(),'actualHelperBodies':len(helper.bodies),'methods':receipts,'deviceTested':False},indent=2),encoding='utf-8')
 (root/'application.xml').write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>cn.content.operations.offline</id><versionNumber>1.0.0</versionNumber><filename>test</filename><initialWindow><content>test.swf</content><visible>false</visible></initialWindow></application>',encoding='utf8')
 output.unlink(missing_ok=True)
 r=subprocess.run([str(a.sdk/'bin/adl64.exe'),str(root/'application.xml'),'--',str(output)],capture_output=True,timeout=30)
 (root/'run.log').write_bytes(r.stdout+r.stderr)
 if r.returncode or not output.exists():raise RuntimeError('AIR state test failed: '+str(r.returncode)+': '+(output.read_text(encoding='utf8') if output.exists() else (r.stdout+r.stderr).decode('utf8','replace')))
 if any(hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest for path,digest in production_identity.items()):raise RuntimeError('Production inputs changed during AIR check; result is not a frozen candidate verification')
 result=json.loads(output.read_text(encoding='utf8'))
 result.update(sourceSha256=hashlib.sha256((HERE/'src/cn/content/ContentOperationsState.as').read_bytes()).hexdigest(),sourceSwfSha256=hashlib.sha256((production/'content-operations-android.swf').read_bytes()).hexdigest(),
  testSwfSha256=hashlib.sha256((root/'test.swf').read_bytes()).hexdigest(),packaged=False)
 result['productionHelperAbcSha256']=hashlib.sha256((production/'production-helper.abc').read_bytes()).hexdigest()
 result['helperCompileInput']='production-swc' if library.exists() else 'workspace-source'
 result['productionInputsStable']=True
 result['sourceSha256Meaning']='workspace source observation; executed code is bound by production SWF/ABC/SWC hashes'
 if library.exists():result['productionHelperSwcSha256']=hashlib.sha256(library.read_bytes()).hexdigest()
 if a.policy_fixture:result['policyFixtureSha256']=hashlib.sha256(a.policy_fixture.read_bytes()).hexdigest()
 output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
if __name__=='__main__':main()
