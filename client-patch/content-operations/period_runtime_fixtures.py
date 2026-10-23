"""Execute exact candidate date consumers and complete helper in isolated AIR.

External UI storage is bounded to real resource dimensions. The production helper
calendar uses AIR Date UTC fields directly, never an AppTime timestamp substitute.
"""
import sys
import copy, hashlib
sys.dont_write_bytecode = True
import native_runtime_fixtures as native
import assistant_runtime_fixtures as assistant
import offline_runtime_test as runtime

BODY = r'''
var make:Function=function(n:String):Object {var type:Class=getDefinitionByName(n) as Class;return new type();};
Object(Date)["fromTime"]=function(v:Number):Date{return new Date(v);};
Object(Math)["isNaN"]=function(v:Number):Boolean{return isNaN(v);};
var end:Number=Date.UTC(2030,0,2,16,30,0), rev:int=100;
check(ContentOperationsState.formatDeadline(end)=="2030.01/03 00:30","actual production UTC+8 formatter crosses the UTC calendar day");
check(ContentOperationsState.formatDeadline(Date.UTC(2029,11,31,16,0,0))=="2030.01/01 00:00","actual production UTC+8 formatter crosses the calendar year");
check(ContentOperationsState.formatDeadline(Date.UTC(2030,0,3,0,30,0))=="2030.01/03 08:30","actual production UTC+8 formatter preserves the eight-hour offset");
var actualCalendar:Class=getDefinitionByName("pinball.common.time._AppTime.AppTime_Impl_") as Class;
check(actualCalendar.toStandardDateFormatString(end)==ContentOperationsState.formatDeadline(end),"actual imported production AppTime and DateTools formatter chain agrees at the UTC+8 day boundary");
var textType:Class=getDefinitionByName("pinball.ui.display.text.UiText") as Class;
var text:Object=new textType();
var pass:Object=make("pinball.scene.passCard.PassCardView");pass.peek={passCardId:14};pass.templateView={timeRangeText:Option.Some({texts:[text]})};
snap2(rev++,[row2("pass_card_event:14",{visible:action(true),enter:action(true)})]);pass.draw(1);
check(text.text=="常驻开放","actual PassCardView.draw writes permanent to its existing date text");
check(text.get_textWidth()==640 && text.get_textHeight()==43 && text.rawTextField.format.size==40 && text.rawTextField.format.horizontalAlign=="center","Pass date field keeps its native width/font and fits the actual black strip established by embedded-font pixel proof");
check(text.rawTextField.autoSize=="none" && text.rawTextField.autoScale && !text.rawTextField.wordWrap,"Pass text stays inside the original bounds with autoscale and no wrapping");
snap2(rev++,[row2("pass_card_event:14",{visible:action(true,end),enter:action(true,end)})]);pass.draw(1);
check(text.text=="开放至 2030.01/03 00:30","actual Pass date displays the exact operator cutoff rather than remaining minutes");
var config:Object={date:Option.Some({frame:1,timeRanges:[{start:123,end:456}],remaining:Option.None})};
ContentOperationsState.preparePeriodConfig(pass,config);
check(config.date.params[0].timeRanges[0].start==123 && config.date.params[0].timeRanges[0].end==456,"display annotation does not rewrite original range values");
var rangeType:Class=getDefinitionByName("pinball.ui.component.template._QuestLikeSceneTemplateView.TimeRangeText") as Class;
var assetType:Class=getDefinitionByName("pinball.asset.view.ViewAssetContainer") as Class;
var nativeText:Object=new textType(), nativeAsset:Object=new assetType();
var rangeView:Object=new rangeType(nativeText,config.date.params[0].timeRanges,nativeAsset);
check(nativeText.text=="开放至 2030.01/03 00:30" && nativeAsset.calls==0,"actual TimeRangeText constructor bypasses numeric calendar formatting for explicit controlled text");
var oldText:Object=new textType();new rangeType(oldText,[{uiStringKey:"original",start:123,end:456}],nativeAsset);
check(nativeAsset.calls==1 && oldText.text.indexOf("original")>=0,"actual TimeRangeText constructor preserves original formatter path when no display annotation exists");
var gc:Object=make("pinball.common.data.gacha.GachaLogic");gc.id=990001;gc.values={show_period:true};gc.period=new TimeRange(100,Option.Some(500));
var gacha:Object=make("pinball.scene.gacha.top.common.GachaSceneViewBase"), base:Object=make("cn.fixture.GachaBasePeek");base.gacha=gc;gacha.basePeek=base;gacha.view={asset:{getUiStringWithContext:function(k:String,c:Object):String{return "legacy";}}};
gacha.periodLayout.dateText.rawTextField.width=740;gacha.periodLayout.dateText.rawTextField.height=46;gacha.periodLayout.dateText.rawTextField.format.size=25;
snap2(rev++,[row2("gacha:990001",{visible:action(true),enter:action(true)})]);gacha.setupText();
check(gacha.periodLayout.dateText.text=="常驻开放","actual gacha setupText renders permanent");
snap2(rev++,[row2("gacha:990001",{visible:action(true,end),enter:action(true,end)})]);gacha.setupText();
check(gacha.periodLayout.dateText.text=="开放至 2030.01/03 00:30","actual gacha setupText renders authoritative cutoff");
check(gacha.periodLayout.dateText.get_textWidth()==740 && gacha.periodLayout.dateText.get_textHeight()==46 && gacha.periodLayout.dateText.rawTextField.format.size==25 && gacha.periodLayout.dateText.rawTextField.autoScale && !gacha.periodLayout.dateText.rawTextField.wordWrap,"actual gacha keeps effective Flatomo 740x46 font25 and enables native text autoscale for a finite deadline");
gc.values.show_period=false;gacha.setupText();check(!gacha.periodLayout.visible,"actual gacha showPeriod false remains hidden");
var box:Object=make("pinball.scene.boxGacha.BoxGachaView"), boxPeek:Object=make("cn.fixture.BoxPeek");box.peek=boxPeek;
box.layout.dateText.rawTextField.height=49;box.layout.dateText.rawTextField.format.size=32;
snap2(rev++,[row2("box_gacha:1",{visible:action(true),enter:action(true)})]);box.setupPeriod();
check(box.layout.dateText.text=="","actual Box with original None date does not gain a new label");
boxPeek.originalEnd=Option.Some(500);box.setupPeriod();check(box.layout.dateText.text=="常驻开放","actual Box with original date UI renders permanent");
snap2(rev++,[row2("pass_card_event:14",{claim:action(true)})]);pass.draw(1);check(text.text=="仅可领奖","actual helper preserves claim-only unlimited rights without claiming permanent participation");
snap2(rev++,[row2("pass_card_event:14",{claim:action(true,end)})]);pass.draw(1);check(text.text=="仅可领奖（至 2030.01/03 00:30）","actual helper preserves claim-only finite rights and exact cutoff");
snap2(rev++,[row2("box_gacha:1",{visible:action(true),enter:action(false),exchange:action(true)})]);box.setupPeriod();check(box.layout.dateText.text=="仅可兑换","actual helper preserves exchange-only unlimited rights");
snap2(rev++,[row2("box_gacha:1",{visible:action(true,end),enter:action(false),exchange:action(true,end)})]);box.setupPeriod();check(box.layout.dateText.text=="仅可兑换（至 2030.01/03 00:30）" && box.layout.dateText.get_textWidth()==640 && box.layout.dateText.get_textHeight()==49 && box.layout.dateText.rawTextField.format.size==32 && box.layout.dateText.rawTextField.autoScale && !box.layout.dateText.rawTextField.wordWrap,"actual Box fits finite exchange-only text within its effective Flatomo 640x49 font32");
var tower:Object=make("pinball.common.data.quest.event.towerDungeon.TowerDungeonEventLogic");
check(tower.getRemainingTimeLabel(1000,false)===Option.None,"actual original Tower None label is preserved");
for each(var className:String in ["pinball.common.data.quest.event.expertSingleEvent.ExpertSingleEventLogic","pinball.common.data.quest.event.soloTimeAttack.SoloTimeAttackEventLogic"]) {
 var countLogic:Object=make(className);countLogic.dailyPoints=7;countLogic.logicAssets=make("cn.fixture.CountAssets");
 check(countLogic.getRemainingTimeLabel(1000,false).params[0].indexOf(":7")>=0,"actual original daily challenge count remains: "+className);
 check(countLogic.getRemainingTimeLabel(1000,true)===Option.None,"actual original exchange None label remains: "+className);
}
var event:Object=make("pinball.common.data.quest.event.advent.AdventEventLogic");event.commonValues={start_time:123,playable_end_time:Option.Some(456)};
var scene:Object=make("pinball.scene.event.base.EventQuestSelectBaseScene");scene.eventPeek=event;
snap2(rev++,[row2("advent_event:1",{visible:action(true),enter:action(true)})]);var date:Object=scene.getDate();
check(date.index==0 && date.params[0].timeRanges[0].contentDisplayText=="常驻开放","actual event getDate keeps existing date panel for permanent");
snap2(rev++,[row2("advent_event:1",{visible:action(true,end),enter:action(true,end)})]);date=scene.getDate();
check(date.params[0].timeRanges[0].contentDisplayText=="开放至 2030.01/03 00:30" && !date.params[0].timeRanges[0].hasOwnProperty("start"),"actual event display has no invented start/server epoch");
event.commonValues.playable_end_time=Option.None;
check(scene.getDate()===Option.None,"actual event native getDate with a frame but original None end does not gain a date panel");
for each(var sceneFamily:String in ["raid","rush"]) {
 var familyTitle:String=sceneFamily=="raid"?"Raid":"Rush",familyLogic:Object=make("pinball.common.data.quest.event."+sceneFamily+"."+familyTitle+"EventLogic");
 var tools:Class=getDefinitionByName("pinball.scene.event."+sceneFamily+"."+familyTitle+"EventSceneTools") as Class;
 familyLogic.commonValues={start_time:123,playable_end_time:Option.Some(456)};
 snap2(rev++,[row2(sceneFamily+"_event:1",{visible:action(true),enter:action(true)})]);
 var familyDate:Object=tools.getDate(familyLogic,1000);
 check(familyDate.index==0 && familyDate.params[0].timeRanges[0].contentDisplayText=="常驻开放","actual static "+familyTitle+" date tool retains an existing time UI for permanent participation");
 snap2(rev++,[row2(sceneFamily+"_event:1",{visible:action(true,end),enter:action(true,end)})]);familyDate=tools.getDate(familyLogic,1000);
 check(familyDate.params[0].timeRanges[0].contentDisplayText=="开放至 2030.01/03 00:30","actual static "+familyTitle+" date tool displays the operator cutoff");
 familyLogic.commonValues.playable_end_time=Option.None;
 check(tools.getDate(familyLogic,1000)===Option.None,"actual static "+familyTitle+" original None date does not gain a time UI");
}
var active:Object=make("pinball.common.data.mission.activeMission.ActiveMissionEventLogic");active.id=2;active.values={start_time:123,end_time:Option.Some(456),flash_frame_reference:Option.Some(1)};
var activePeek:Object=make("cn.fixture.ActivePeek");activePeek.event=active;var probe:Object=make("cn.fixture.ActiveRunProbe");probe.peek=activePeek;
snap2(rev++,[row2("active_mission_event:2",{visible:action(true),enter:action(true)})]);probe.run();
check(probe.templateView.config.date.index==0 && probe.templateView.config.date.params[0].timeRanges[0].contentDisplayText=="常驻开放","actual ActiveMissionView.run date-construction prefix preserves an originally existing time UI for permanence");
active.values.end_time=Option.None;snap2(rev++,[row2("active_mission_event:2",{visible:action(true,end),enter:action(true,end)})]);probe.run();
check(probe.templateView.config.date===Option.None,"actual ActiveMissionView.run prefix with original None end does not create a time UI under a finite override");
var rankClass:Class=getDefinitionByName("pinball.common.data.quest.event.ranking.RankingEventLogic") as Class;
var rank:Object=new rankClass(1,make("pinball.asset.logic.LogicAssetContainer"),null,null);
var rankScene:Object=make("pinball.scene.event.ranking.questSelect.RankingEventQuestSelectScene");rankScene.event=rank;
var rankPeek:Object=make("cn.fixture.RankingPeek");rankPeek.event=rank;rankPeek.scene=rankScene;
var rankProbe:Object=make("cn.fixture.RankingRunProbe");rankProbe.peek=rankPeek;
snap2(rev++,[row2("ranking_event:1",{visible:action(true,end),enter:action(true,end)})]);rankProbe.run();
var rankText:Object=new textType();new rangeType(rankText,rankProbe.templateView.config.date.params[0].timeRanges,nativeAsset);
check(rankText.text=="开放至 2030.01/03 00:30","actual Ranking scene + view run construction prefix + TimeRangeText renders the new cutoff rather than original master dates");
snap2(rev++,[row2("ranking_event:1",{visible:action(true),enter:action(false),claim:action(true,end)})]);rankProbe.run();
rankText=new textType();new rangeType(rankText,rankProbe.templateView.config.date.params[0].timeRanges,nativeAsset);
check(rankText.text=="仅可领奖（至 2030.01/03 00:30）","actual Ranking final text preserves finite claim-only semantics");
var real:Object=make("cn.fixture.RealPeriodProbe");real.view={asset:nativeAsset};
active.values={start_time:123,playable_end_time:Option.Some(Date.UTC(2029,11,1)),lottery_end_time:Option.Some(Date.UTC(2029,11,2)),end_time:Option.Some(456)};
snap2(rev++,[row2("active_mission_event:2",{visible:action(true),enter:action(true),claim:action(true)})]);real.run(active);
check(real.periodBackLayout.texts.playable_period_date.text=="常驻开放" && real.periodBackLayout.texts.receive_period_date.text=="仅可领奖","actual RealIncentive native date fragment safely renders unlimited participation and earned claims without unwrapping None");
check(real.periodBackLayout.texts.lottery_period_date.text.indexOf("2029.12/01 08:00")>=0 && real.periodBackLayout.texts.lottery_period_date.text.indexOf("2029.12/02 08:00")>=0,"actual RealIncentive keeps reliable original lottery dates through the native localized template");
active.values.playable_end_time=Option.Some(Date.UTC(2030,0,2,20,59,59));real.run(active);
check(ContentOperationsState.realIncentiveLotteryDate(active,false)=="2030.01/03 05:00" && real.periodBackLayout.texts.lottery_period_date.text.indexOf("2030.01/03 05:00")>=0 && real.periodBackLayout.texts.lottery_period_date.text.indexOf("04:59")<0,"actual RealIncentive preserves native lottery start playable-end plus 1000ms across a minute boundary");
check(real.periodBackLayout.texts.playable_period_date.get_textWidth()==595 && real.periodBackLayout.texts.playable_period_date.get_textHeight()==40 && real.periodBackLayout.texts.playable_period_date.rawTextField.format.size==26,"actual RealIncentive keeps effective Flatomo date bounds 595x40 and font26");
active.values.lottery_end_time=Option.None;real.run(active);
check(real.periodBackLayout.texts.lottery_period_date.text=="","actual RealIncentive original lottery None safely stays empty with no fabricated calendar or new message");
snap2(rev++,[row2("active_mission_event:2",{visible:action(true,end),enter:action(true,end),claim:action(true,end)})]);real.run(active);
check(real.periodBackLayout.texts.playable_period_date.text=="开放至 2030.01/03 00:30" && real.periodBackLayout.texts.receive_period_date.text=="仅可领奖（至 2030.01/03 00:30）","actual RealIncentive native date fragment uses both authoritative finite cutoffs");
'''

def prepare(stubs, cases, abc, builder):
    original_prepare = _prepare
    methods = {
      'pinball.scene.passCard::PassCardView':['draw'],
      'pinball.scene.boxGacha::BoxGachaView':['setupPeriod'],
      'pinball.common.data.quest.event.towerDungeon::TowerDungeonEventLogic':['getRemainingTimeLabel'],
      'pinball.common.data.quest.event.expertSingleEvent::ExpertSingleEventLogic':['getRemainingTimeLabel'],
      'pinball.common.data.quest.event.soloTimeAttack::SoloTimeAttackEventLogic':['getRemainingTimeLabel'],
      'pinball.scene.event.raid::RaidEventSceneTools$':['getDate'],
      'pinball.scene.event.rush::RushEventSceneTools$':['getDate'],
    }
    native.NATIVE_METHODS.update(methods)
    native.NATIVE_METHODS['pinball.common.data.mission.activeMission::ActiveMissionEventLogic'] += ['get_endTime','get_startTime','getFlashFrameReference']
    native.campaign_ui.SCENE_STORAGE['PassCardView']='public var peek:Object;public var templateView:Object;public var featuredReward:Object={draw:function(n:int):void{}};'
    native.campaign_ui.SCENE_STORAGE['BoxGachaView']='public var peek:Object;public var layout:pinball.ui.display.UiDisplayObjectContainer=new pinball.ui.display.UiDisplayObjectContainer();public var view:Object;'
    for owner in ['expertSingleEvent::ExpertSingleEventLogic','soloTimeAttack::SoloTimeAttackEventLogic']:
        field='eventId' if owner.startswith('soloTimeAttack') else 'id'
        native.STORAGE['pinball.common.data.quest.event.'+owner]='public var '+field+':int=1;public var dailyPoints:int=7;public var logicAssets:Object;public function getDailyChallengePoint():int{return dailyPoints;}public function getEventId():pinball.common.data.quest.event.EventIdKind{return null;}'
    native.STORAGE['pinball.common.data.quest.event.towerDungeon::TowerDungeonEventLogic']='public var id:int=1;public function getEventId():pinball.common.data.quest.event.EventIdKind{return null;}'
    stubs,labels,includes=original_prepare(stubs,cases,abc,builder)
    def put(owner, body):
        namespace,name=owner.split('::');stubs[namespace.replace('.','/')+'/'+name+'.as']='package '+namespace+' {public class '+name+' {'+body+'}}';includes.append(namespace+'.'+name)
    ui='public var text:String="";public var visible:Boolean=true;public var x:Number=0;public var y:Number=0;public var parent:Object={addChild:function(o:Object):void{}};public var rawTextField:Object={width:640,height:61,format:{size:40},autoScale:false,autoSize:"bothDirections",wordWrap:true};public function set_text(s:String):String{text=s;return s;}public function clone():UiText{return new UiText();}'
    for method,signature,returns in [('get_textWidth','','Number'),('get_textHeight','','Number'),('set_textWidth','v:Number','Number'),('set_textHeight','v:Number','Number'),('set_autoScale','v:Boolean','Boolean'),('set_autoSize','v:String','String')]:
        ui+='public function '+method+'('+signature+'):'+returns+'{return '+('false' if returns=='Boolean' else 'null' if returns=='String' else '0')+';}'
        labels.append('pinball.ui.display.text::UiText/'+method+'|1')
    put('pinball.ui.display.text::UiText',ui)
    put('pinball.asset.view::ViewAssetContainer','public var calls:int=0;public function getUiString(k:String):String{return k;}public function getUiStringWithContext(k:String,c:Object):String{calls++;return k+":"+JSON.stringify(c);}')
    put('cn.fixture::CountAssets','public namespace NativeAssets="pinball.asset.logic:ILogicAssetContainer";NativeAssets function getUiStringWithContext(k:String,c:Object):String{return k+":"+c.current;}')
    put('starling.display::Sprite','')
    put('pinball.ui.component.template::CharacterImageKind','public static var None:CharacterImageKind=new CharacterImageKind();')
    for family,title in [('raid','Raid'),('rush','Rush')]:
        put('pinball.common.data.quest.event.'+family+'::'+title+'EventTimeKind','public var index:int=0;')
        key='pinball/common/data/quest/event/'+family+'/'+title+'EventLogic.as'
        stubs[key]=stubs[key].replace('public class '+title+'EventLogic {','public class '+title+'EventLogic {public function getNow'+title+'EventTimeKind(t:Number):pinball.common.data.quest.event.'+family+'.'+title+'EventTimeKind{return null;}') if 'public class '+title+'EventLogic {' in stubs[key] else stubs[key].replace('extends EventLogicBase {','extends EventLogicBase {public function getNow'+title+'EventTimeKind(t:Number):pinball.common.data.quest.event.'+family+'.'+title+'EventTimeKind{return null;}')
    stubs['pinball/common/data/mission/activeMission/ActiveMissionEventPeek.as']='package pinball.common.data.mission.activeMission {public interface ActiveMissionEventPeek {}}'
    stubs['pinball/scene/activeMission/ActiveMissionScenePeek.as']='package pinball.scene.activeMission {public interface ActiveMissionScenePeek {}}'
    key='pinball/common/data/mission/activeMission/ActiveMissionEventLogic.as'
    stubs[key]=stubs[key].replace('public class ActiveMissionEventLogic','public class ActiveMissionEventLogic implements ActiveMissionEventPeek').replace('{','{import pinball.common.data.mission.activeMission.ActiveMissionEventPeek;',1)
    aliases='public namespace NativeActivePeek="pinball.common.data.mission.activeMission:ActiveMissionEventPeek";'
    for method,typ in [('get_endTime','haxe.ds.Option'),('get_startTime','Number'),('getFlashFrameReference','haxe.ds.Option'),('getPlayablePeriod','pinball.common.time.TimeRange'),('getLotteryPeriod','pinball.common.time.TimeRange'),('getRewardReceivePeriod','pinball.common.time.TimeRange')]:aliases+='NativeActivePeek function '+method+'():'+typ+'{return Object(this)["'+method+'"]();}'
    stubs[key]=stubs[key].rsplit('}',2)[0]+aliases+'}}'
    put('cn.fixture::ActivePeek','public var event:pinball.common.data.mission.activeMission.ActiveMissionEventLogic;public function getActiveMissionEvent():pinball.common.data.mission.activeMission.ActiveMissionEventPeek{return event;}public namespace NativeActiveScenePeek="pinball.scene.activeMission:ActiveMissionScenePeek";NativeActiveScenePeek function getActiveMissionEvent():pinball.common.data.mission.activeMission.ActiveMissionEventPeek{return event;}')
    key='cn/fixture/ActivePeek.as';stubs[key]=stubs[key].replace('public class ActivePeek','public class ActivePeek implements pinball.scene.activeMission.ActiveMissionScenePeek')
    put('pinball.ui.component.template::QuestLikeSceneTemplateView','public var config:Object;public function QuestLikeSceneTemplateView(layer:starling.display.Sprite=null,c:Object=null){config=c;}')
    put('cn.fixture::ActiveRunProbe','public var peek:pinball.scene.activeMission.ActiveMissionScenePeek;public var starlingLocalLayer:starling.display.Sprite=new starling.display.Sprite();public var templateView:pinball.ui.component.template.QuestLikeSceneTemplateView;public function run():void{}')
    stubs['pinball/scene/event/ranking/questSelect/RankingEventQuestSelectPeek.as']='package pinball.scene.event.ranking.questSelect {public interface RankingEventQuestSelectPeek {}}'
    put('cn.fixture::RankingPeek','public var event:Object;public var scene:pinball.scene.event.ranking.questSelect.RankingEventQuestSelectScene;public namespace NativeRankPeek="pinball.scene.event.ranking.questSelect:RankingEventQuestSelectPeek";NativeRankPeek function getEventPeriodInfo():haxe.ds.Option{return scene.getEventPeriodInfo();}NativeRankPeek function getLayoutReferenceFrame():int{return 12;}')
    key='cn/fixture/RankingPeek.as';stubs[key]=stubs[key].replace('public class RankingPeek','public class RankingPeek implements pinball.scene.event.ranking.questSelect.RankingEventQuestSelectPeek')
    put('cn.fixture::RankingRunProbe','public var peek:pinball.scene.event.ranking.questSelect.RankingEventQuestSelectPeek;public var starlingLocalLayer:starling.display.Sprite=new starling.display.Sprite();public var templateView:pinball.ui.component.template.QuestLikeSceneTemplateView;public function run():void{}')
    stubs['pinball/ui/provider/UiProvider.as']='package pinball.ui.provider {public interface UiProvider {}}'
    put('cn.fixture::PeriodUiProvider','public namespace NativeProvider="pinball.ui.provider:UiProvider";NativeProvider function build(c:Object):pinball.ui.display.UiDisplayObjectContainer{return new pinball.ui.display.UiDisplayObjectContainer();}')
    key='cn/fixture/PeriodUiProvider.as';stubs[key]=stubs[key].replace('public class PeriodUiProvider','public class PeriodUiProvider implements pinball.ui.provider.UiProvider')
    put('cn.fixture::RealPeriodProbe','public var view:Object;public var periodBackLayout:pinball.ui.display.UiDisplayObjectContainer;public var uiProvider:pinball.ui.provider.UiProvider=new cn.fixture.PeriodUiProvider();public var templateView:Object={backgroundOverlayLayer:{addChild:function(o:Object):void{}}};public function run(logic:Object):void{}')
    stubs['pinball/scene/boxGacha/BoxGachaScenePeek.as']='package pinball.scene.boxGacha {public interface BoxGachaScenePeek {}}'
    put('cn.fixture::BoxPeek','public var boxGachaId:int=1;public var originalEnd:haxe.ds.Option=haxe.ds.Option.None;public function getEndDate():haxe.ds.Option{return originalEnd;}public namespace NativeBoxPeek="pinball.scene.boxGacha:BoxGachaScenePeek";NativeBoxPeek function getEndDate():haxe.ds.Option{return originalEnd;}NativeBoxPeek function getStartDate():Number{return 123;}')
    key='cn/fixture/BoxPeek.as';stubs[key]=stubs[key].replace('public class BoxPeek','public class BoxPeek implements pinball.scene.boxGacha.BoxGachaScenePeek').replace('{','{import haxe.ds.Option;import pinball.scene.boxGacha.BoxGachaScenePeek;',1).replace('implements pinball.scene.boxGacha.BoxGachaScenePeek','implements BoxGachaScenePeek').replace('haxe.ds.Option','Option').replace('import Option;','import haxe.ds.Option;')
    put('pinball.ui.component.template._QuestLikeSceneTemplateView::TimeRangeText','public var texts:Array=[];public var elapsedFrame:int=0;public var timeRangeIndex:int=0;public function TimeRangeText(t:pinball.ui.display.text.UiText=null,r:Array=null,a:pinball.asset.view.ViewAssetContainer=null){}')
    key='pinball/ui/component/template/_QuestLikeSceneTemplateView/TimeRangeText.as'
    stubs[key]=stubs[key].replace('{','{import pinball.ui.display.text.UiText;import pinball.asset.view.ViewAssetContainer;',1).replace('t:pinball.ui.display.text.UiText','t:UiText').replace('a:pinball.asset.view.ViewAssetContainer','a:ViewAssetContainer')
    labels.append('pinball.ui.component.template._QuestLikeSceneTemplateView::TimeRangeText/<ctor>')
    key='pinball/common/time/_AppTime/AppTime_Impl_.as'
    stubs[key]=stubs[key].replace('public class AppTime_Impl_ {','public class AppTime_Impl_ {public static var JAPAN_STANDARD_OFFSET_MILLISECONDS:Number=28800000;public static function japanStandardFormat(v:Number,f:String):String{return "";}public static function toJapanStandardDate(v:Number):Date{return null;}')
    for method in ['toStandardDateFormatString','japanStandardFormat','toJapanStandardDate']:labels.append('pinball.common.time._AppTime::AppTime_Impl_$/'+method+'|1')
    stubs['DateTools.as']='package {public class DateTools {public static var DAY_NAMES:Array=[];public static var MONTH_NAMES:Array=[];public static var DAYS_OF_MONTH:Array=[];public static function __format_get(d:Date,f:String):String{return "";}public static function __format(d:Date,f:String):String{return "";}public static function format(d:Date,f:String):String{return "";}}}'
    includes.append('DateTools')
    for method in ['format','__format','__format_get']:labels.append('DateTools$/'+method+'|1')
    stubs['StringTools.as']='package {public class StringTools {public static function lpad(s:String,p:String,n:int):String{return "";}}}'
    includes.append('StringTools');labels.append('StringTools$/lpad|1')
    put('pinball.ui.display.image::UiImage','public var visible:Boolean=true;public var x:Number=0;public var width:Number=100;')
    key='pinball/ui/display/UiDisplayObjectContainer.as';stubs[key]=stubs[key].replace('public function getContainer','public function getImage(k:String,m:Object=null):pinball.ui.display.image.UiImage{return new pinball.ui.display.image.UiImage();}public function getContainer').replace('{','{import pinball.ui.display.image.UiImage;',1).replace('pinball.ui.display.image.UiImage','UiImage')
    stubs[key]=stubs[key].replace('import UiImage;','import pinball.ui.display.image.UiImage;')
    stubs[key]=stubs[key].replace('public var dateText:','public var texts:Object={};public var dateText:').replace('return dateText;','if(k=="label" || k=="date_text")return dateText;if(!texts.hasOwnProperty(k)){texts[k]=new pinball.ui.display.text.UiText();texts[k].rawTextField.width=595;texts[k].rawTextField.height=40;texts[k].rawTextField.format.size=26;}return texts[k];')
    # These extra sealed receiver declarations need explicit ASC imports too.
    import re
    names=[path[:-3].replace('/','.') for path in stubs if path.endswith('.as') and '/' in path]
    for key,text in list(stubs.items()):
        imports=re.findall(r'\bimport\s+([\w.]+);',text);text=re.sub(r'\bimport\s+[\w.]+;','',text)
        for full in sorted(names,key=len,reverse=True):
            if full in text:imports.append(full);text=text.replace(full,full.rsplit('.',1)[-1])
        if imports:text=text.replace('{','{'+''.join('import '+name+';' for name in dict.fromkeys(imports)),1)
        stubs[key]=text
    return stubs,labels,includes

def import_prefixes(builder,target,main,receipts):
    result=_date_prologue(builder,target,main,receipts)
    source=builder.view(main)
    for label,probe_name in [('pinball.scene.activeMission::ActiveMissionView/run|1','ActiveRunProbe'),('pinball.scene.event.ranking.questSelect::RankingEventQuestSelectView/run|1','RankingRunProbe')]:
        index,=source.by_label[label];original=main.bodies[index];instructions=builder.p.asm.decode(original[5])
        constructor,=[i for i,row in enumerate(instructions) if row.op==0x4a and main.mn_name(row.args[0])=='pinball.ui.component.template::QuestLikeSceneTemplateView']
        stop=next(i+1 for i in range(constructor+1,len(instructions)) if instructions[i].op==0x68 and main.mn_name(instructions[i].args[0])=='templateView')
        sliced=copy.deepcopy(original);sliced[5]=builder.p.asm.encode(instructions[:stop]+[builder.p.asm.Instruction(0x47)])[0];sliced[6]=[]
        expected=source.normalized(index)[0][:stop]
        main.bodies[index]=sliced
        probe,=target.by_label['cn.fixture::'+probe_name+'/run|1'];prior=target.a.bodies[probe]
        try:target.a.bodies[probe]=builder.p.Importer(target,builder.view(main)).body(index,prior[0])
        finally:main.bodies[index]=original
        assert target.normalized(probe)[0][:-1]==expected,'actual native run prefix differs: '+label
        receipts.append({'label':label,'kind':'actual-native-date-construction-prefix','sourceCodeSha256':hashlib.sha256(original[5]).hexdigest(),'sourceInstructionRange':[0,stop],'normalizedPrefixExact':True,'wholeViewRunExecuted':False})
    label='pinball.scene.activeMission::RealIncentiveActiveMissionView/run|1';index,=source.by_label[label]
    original=main.bodies[index];instructions=builder.p.asm.decode(original[5])
    start=next(i-2 for i,row in enumerate(instructions) if row.op==0x46 and main.mn_name(row.args[0])=='realIncentiveManaged')
    last=max(i for i,row in enumerate(instructions) if row.op==0x46 and main.mn_name(row.args[0])=='realIncentiveText')
    stop=next(i+1 for i in range(last,len(instructions)) if instructions[i].op==0x4f and main.mn_name(instructions[i].args[0])=='set_text')
    prefix=builder.p.asm.assemble([('getlocal_0',),('pushscope',),('getlocal_1',),('setlocal_2',)])
    fragment=copy.deepcopy(instructions[start:stop])
    for row in fragment:
        if row.target is not None:
            assert start<=row.target<=stop,('native fragment leaves bounded UI',row.target)
            row.target=row.target-start+len(prefix)
        if row.cases is not None:
            assert all(start<=v<=stop for v in row.cases+[row.default])
            row.cases=[v-start+len(prefix) for v in row.cases];row.default=row.default-start+len(prefix)
    sliced=copy.deepcopy(original);sliced[5]=builder.p.asm.encode(prefix+fragment+[builder.p.asm.Instruction(0x47)])[0];sliced[6]=[]
    main.bodies[index]=sliced;expected=builder.view(main).normalized(index)
    probe,=target.by_label['cn.fixture::RealPeriodProbe/run|1'];prior=target.a.bodies[probe]
    try:target.a.bodies[probe]=builder.p.Importer(target,builder.view(main)).body(index,prior[0])
    finally:main.bodies[index]=original
    assert target.normalized(probe)==expected,'actual native RealIncentive display fragment differs'
    receipts.append({'label':label,'kind':'actual-native-date-display-fragment','sourceCodeSha256':hashlib.sha256(original[5]).hexdigest(),'sourceInstructionRange':[start,stop],'normalizedFragmentExact':True,'receiverAdapterPrefixInstructions':len(prefix),'wholeViewRunExecuted':False})
    return result

_prepare=native.prepare
_date_prologue=native.import_date_prologue
if __name__=='__main__':
    native.prepare=prepare;native.import_date_prologue=import_prefixes;native.BODY=BODY;assistant.BODY=''
    runtime.main()
