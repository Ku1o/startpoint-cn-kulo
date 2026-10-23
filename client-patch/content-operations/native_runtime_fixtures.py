"""Closed dependencies for executing production native bodies in desktop AIR.

These classes supply state/storage only. The methods named in NATIVE_METHODS
are replaced with instruction/CFG-exact bodies from the selected production SWF.
They are not a replacement client and do not establish device/resource readiness.
"""
import re
import campaign_ui_runtime_fixtures as campaign_ui
import assistant_runtime_fixtures as assistant

NATIVE_METHODS = {
 'pinball.common.data.gacha::GachaRepository': ['resolveAssetPathCollection'],
 'pinball.common.data.gacha::GachaLogic': ['get_startTime','get_endTime','isComeback','isStarsGacha','isWithinPeriod','get_oddsRarityStringId','get_noteAsset','resolveAssetPathCollection','isFreemiumGuaranteeAvailable','get_prizeKind'],
 'pinball.common.data.gacha::GachaOddsTools$': ['getRarityOddsPath','getCharacterOddsPath','getEquipmentOddsPath'],
 'pinball.asset.logic::LogicAssetContainer': ['getMasterTableWithPath'],
 'pinball.common.data.collectItem::CollectItemEventLogic': ['get_kind','get_exchangableEndTime','isExchangingAvailable','getRemainingTimeLabel','get_startTime','get_endTime'],
 'pinball.common.data.collectItem::CollectItemEventRepository': ['collectItemEventExchangingAvailable'],
 'pinball.common.data.campaign.specialExchange::SpecialExchangeCampaignLogic': ['get_exchangeEndTime','isOverExchangePeriod'],
 'pinball.common.data.campaign.multiSpecialExchange::MultiSpecialExchangeCampaignLogic': ['get_exchangeEndTime','isOverExchangePeriod'],
 'pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic': ['get_periodEndTime','isOverExchangePeriod','get_hasCampaignData'],
 'pinball.common.data.mission.activeMission::ActiveMissionEventLogic': ['getPlayablePeriod','getLotteryPeriod','getRewardReceivePeriod','getRealIncentiveMissionEventTimeKind'],
 'pinball.common.data.quest.common::CommonQuestBase': ['isWithinPeriod','isWithinViewablePeriod','isEarlierThanPeriodEnd','isViewable'],
 'pinball.common.data.quest.event.advent::AdventEventQuestLogic': ['isViewable'],
 'pinball.common.data.quest.event.ranking::RankingEventLogic': ['<ctor>','getNowRankingEventTimeKind'],
 'pinball.common.data.event::EventListLogic': ['getAllEventIds'],
}
DATE_SCENES = [
 'pinball.scene.event.base::EventQuestSelectBaseScene',
 'pinball.scene.event.carnival::CarnivalEventFolderSelectScene',
 'pinball.scene.event.carnival.questSelect::CarnivalEventQuestSelectScene',
 'pinball.scene.event.expert.bossSelect::ExpertSingleEventBossSelectScene',
 'pinball.scene.event.expert.questSelect::ExpertSingleEventQuestSelectScene',
 'pinball.scene.event.scoreAttack.questSelect::ScoreAttackEventQuestSelectScene',
 'pinball.scene.event.soloTimeAttack.questSelect::SoloTimeAttackEventQuestSelectScene',
]
for _scene in DATE_SCENES:NATIVE_METHODS[_scene]=['getDate']
NATIVE_METHODS['pinball.scene.event.ranking.questSelect::RankingEventQuestSelectScene']=['getEventPeriodInfo']
NATIVE_METHODS['pinball.common.data.quest.event.scoreAttack::ScoreAttackEventLogic']=['getRemainingTimeUntilNextEvent']
NATIVE_METHODS.update(campaign_ui.METHODS)
for _family in ['specialExchange::SpecialExchangeCampaignLogic','multiSpecialExchange::MultiSpecialExchangeCampaignLogic']:
 NATIVE_METHODS['pinball.common.data.campaign.'+_family]+=['get_exchangeStartTime','get_campaignStartTime','get_campaignEndTime']
NATIVE_METHODS['pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic']+=['get_periodStartTime','get_buyEndTime']
NATIVE_METHODS['pinball.common.data.gacha::GachaLogic']+=['get_showPeriod']

STORAGE = {
 'pinball.common.data.gacha::GachaLogic': 'public var id:int=1;public var values:Object={};public var period:pinball.common.time.TimeRange;public var comebackGachaPeriod:haxe.ds.Option=haxe.ds.Option.None;public var starsGachaPeriod:haxe.ds.Option=haxe.ds.Option.None;public function getExtendedEndTime(p:Object):haxe.ds.Option{return get_endTime();}',
 'pinball.common.data.gacha::GachaRepository': 'public var characters:Array=[];public var equipments:Array=[];public var gachaLoicTable:Object;public var gachaCombebackPeriod:Object;public var gachaStarskPeriod:Object;public function getCharacterGachas(p:Object):Array{return characters;}public function getEquipmentGachas(p:Object):Array{return equipments;}public function getGachaIdsFromBackScenes(a:Array):Array{return [];}public function getGacha(p:Object,id:int):pinball.common.data.gacha.GachaLogic{return null;}',
 'pinball.asset.logic::LogicAssetContainer': 'public var loaded:Object={};public var ignorePeriods:Boolean=false;public function _getMasterTableWithPath(p:Object):pinball.master.runtime.MasterTable{return loaded[p.path] as pinball.master.runtime.MasterTable;}public function getIgnoreQuestPeriod():Boolean{return ignorePeriods;}public function getMasterTable(c:Class):pinball.master.runtime.MasterTable{return new c();}',
 'pinball.common.data.collectItem::CollectItemEventLogic': 'public var id:int=1;public var values:Object={};public var logicAssets:Object={};public var exchangablePeriod:pinball.common.time.TimeRange;',
 'pinball.common.data.campaign.specialExchange::SpecialExchangeCampaignLogic': 'public var id:int=1;public var values:Object={};',
 'pinball.common.data.campaign.multiSpecialExchange::MultiSpecialExchangeCampaignLogic': 'public var id:int=1;public var values:Object={};',
 'pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic': 'public var id:int=1;public var values:Object={};public var startDashExchangeCampaignData:haxe.ds.Option=haxe.ds.Option.Some({period_end_time:0});',
 'pinball.common.data.mission.activeMission::ActiveMissionEventLogic': 'public var id:int=1;public var values:Object={};',
 'pinball.common.data.quest.common::CommonQuestBase': 'public var id:int=101;public var categoryId:int=3;public var annualPeriod:haxe.ds.Option=haxe.ds.Option.None;public var period:pinball.common.time.TimeRange=new pinball.common.time.TimeRange(0,haxe.ds.Option.Some(500));public var logicAssets:pinball.asset.logic.ILogicAssetContainer=new pinball.asset.logic.LogicAssetContainer();public var questViewableConditionByQuestClear:pinball.common.data.quest.condition.viewable.QuestViewableConditionByQuestClear;public var questViewableConditionByOwnedCharacter:pinball.common.data.quest.condition.viewable.QuestViewableConditionByOwnedCharacter;public var questViewableConditionByGameSystemUnlock:pinball.common.data.quest.condition.viewable.QuestViewableConditionByGameSystemUnlock;public function get_category():Object{return {id:categoryId};}',
 'pinball.common.data.quest.event.advent::AdventEventQuestLogic': 'public var adventEvent:pinball.common.data.quest.event.advent.AdventEventLogic;public var questRepository:Object;',
 'pinball.common.data.event::EventListLogic': 'public var eventListValuesArray:Array=[];',
}

def prepare(stubs, cases, abc, builder):
 """Declare selected native ABI, while keeping state fixtures sealed."""
 stubs = dict(stubs)
 labels=[]; includes=[]
 source=builder.view(abc)
 def put(qn,body,base='',extra=''):
  package,name=qn.split('::');path=package.replace('.','/')+'/'+name+'.as'
  stubs[path]='package '+package+' {public class '+name+base+' {'+body+'}}'
  includes.append(package+'.'+name)
 for qn,methods in NATIVE_METHODS.items():
  static=qn.endswith('$');qn_type=qn.rstrip('$');package,name=qn_type.split('::')
  body=STORAGE.get(qn_type,'');base=''
  if name=='AdventEventQuestLogic':base=' extends pinball.common.data.quest.common.OrdinaryQuestBase'
  if name=='LogicAssetContainer':base=' implements ILogicAssetContainer'
  if qn_type.startswith('pinball.scene.'):
   body='public var event:Object;public var eventPeek:Object;public var eventShopSelectItemCampaignLogic:haxe.ds.Option=haxe.ds.Option.None;'
  if name in campaign_ui.SCENE_STORAGE:
   body=campaign_ui.SCENE_STORAGE[name]+(campaign_ui.VIEW_STORAGE if name in ['StartDashExchangeCampaignView','MultiSpecialExchangeCampaignExchangeView'] else '')
  if name in ['SpecialExchangeCampaignLogic','StartDashExchangeCampaignLogic','MultiSpecialExchangeCampaignLogic']:
   extra,base=campaign_ui.receiver(name);body+=extra
  if name=='GachaLogic':
   base=' implements pinball.common.data.gacha.GachaPeekForGachaTopScene'
   body+='public namespace NativeGachaPeek="pinball.common.data.gacha:GachaPeekForGachaTopScene";NativeGachaPeek function get_showPeriod():Boolean{return Object(this)["get_showPeriod"]();}'
  if name=='ScoreAttackEventLogic':
   body='public var eventId:int=1;public var quests:Array=[];public function getEventId():pinball.common.data.quest.event.EventIdKind{return null;}public function getQuests():Array{return quests;}'
   base=' extends pinball.common.data.quest.event.common.EventLogicBase'
  if name=='RankingEventLogic':
   body='public var id:int=1;public var values:Object;public var singleQuestTable:pinball.master.runtime.MasterMap;public var rewardTable:pinball.master.runtime.MasterMap;public var aggregationTimeRange:pinball.common.time.TimeRange;public var rewardReceiveTimeRange:pinball.common.time.TimeRange;public function getEventId():pinball.common.data.quest.event.EventIdKind{return null;}'
   base=' extends pinball.common.data.quest.event.common.EventLogicBase'
  for method in methods:
   matches=[label for label in source.by_label if label.startswith(qn+'/') and label.rsplit('/',1)[-1].split('|')[0]==method]
   assert len(matches)==1,(qn,method,matches)
   label=matches[0];labels.append(label);bi,=source.by_label[label];m=abc.methods[abc.bodies[bi][0]]
   def typ(i):return abc.mn_name(i).replace('::','.') if i else '*'
   args=','.join('p'+str(i)+':'+typ(t)+('=null' if typ(t) not in ['int','uint','Number','Boolean'] else '=0' if typ(t)!='Boolean' else '=false') for i,t in enumerate(m[1]))
   returns=typ(m[0]);name_method=name if method=='<ctor>' else method
   override='override ' if name=='AdventEventQuestLogic' else ''
   value='' if returns=='void' else 'return false;' if returns=='Boolean' else 'return 0;' if returns in ['Number','int','uint'] else 'return null;'
   body+='public '+override+('static ' if static else '')+'function '+name_method+'('+args+')'+(':'+returns if method!='<ctor>' else '')+'{'+('super();' if method=='<ctor>' else value)+'}'
  put(qn_type,body,base)
 # Native base receives four arguments from the actual Ranking constructor.
 key='pinball/common/data/quest/event/common/EventLogicBase.as'
 stubs[key]=stubs[key].replace('public class EventLogicBase {','public class EventLogicBase {public function EventLogicBase(v:Object=null,a:Object=null,r:Object=null,g:Object=null){if(v!=null)commonValues=v;}')
 stubs[key]=stubs[key].replace('public class EventLogicBase {','public class EventLogicBase {public function getFlashFrameReference():haxe.ds.Option{return haxe.ds.Option.Some(12);}')
 put('pinball.common.data.quest.common::OrdinaryQuestBase','',' extends CommonQuestBase')
 put('cn.fixture::NativeDateCtorProbe','public function run(scene:Object,config:Object):void{}')
 put('pinball.common.time::TimeRangeWithoutYear','public function isWithin(t:Number):Boolean{return false;}')
 put('pinball.common.data.quest.event.scoreAttack::ScoreAttackEventQuestLogic','public var scoreAttackEvent:pinball.common.data.quest.event.scoreAttack.ScoreAttackEventLogic;',' extends pinball.common.data.quest.common.CommonQuestBase')
 for package,kind,_,_,_ in cases:
  field=package if package=='expertSingleEvent' else package+'Event'
  put('pinball.common.data.quest.fixture::'+kind+'ScopedQuest','public var '+field+':pinball.common.data.quest.event.'+package+'.'+kind+'Logic;',' extends pinball.common.data.quest.common.CommonQuestBase')
 put('pinball.common.data.player::PlayerLogic','')
 put('pinball.common.data.player::PlayerPeek','')
 put('pinball.asset.logic::AssetPathCollectionBuilder','public var master:FixtureAssetSet=new FixtureAssetSet();public var html:FixtureAssetSet=new FixtureAssetSet();')
 put('pinball.asset.logic::FixtureAssetSet','public var paths:Array=[];public function add(p:Object):void{paths.push(p);}public function addAll(a:Array):void{for each(var p:Object in a)add(p);}')
 put('pinball.asset.logic::MasterGroupAssetPath','public var path:String;public var clazz:Class;public function MasterGroupAssetPath(p:Object){path=p.path;clazz=p.clazz;}public static function createFromMasterAssetPath(p:Object):MasterGroupAssetPath{return new MasterGroupAssetPath(p);}')
 stubs['pinball/asset/logic/ILogicAssetContainer.as']='package pinball.asset.logic {public interface ILogicAssetContainer {function getIgnoreQuestPeriod():Boolean;function getMasterTable(c:Class):pinball.master.runtime.MasterTable;}}'
 put('pinball.master.runtime::MasterTable','')
 stubs['pinball/master/runtime/MasterMap.as']='package pinball.master.runtime {public interface MasterMap {function get(id:int):Object;}}'
 put('pinball.master.runtime::FixtureMasterMap','public var value:Object;public function FixtureMasterMap(v:Object=null){value=v;}public function get(id:int):Object{return value;}',' implements MasterMap')
 put('pinball.master.generated::RankingEventValues','public var start_time:Number=0;public var playable_end_time:haxe.ds.Option=haxe.ds.Option.Some(500);public var aggregation_end_time:Number=2000;public var reward_receive_end_time:Number=10000;')
 for name in ['RankingEventTable','RankingEventSingleQuestTable','RankingEventRankingRewardTable']:
  value='new RankingEventValues()' if name=='RankingEventTable' else 'new pinball.master.runtime.FixtureMasterMap()'
  put('pinball.master.generated::'+name,'public function get_data():pinball.master.runtime.MasterMap{return new pinball.master.runtime.FixtureMasterMap('+value+');}',' extends pinball.master.runtime.MasterTable')
 put('pinball.common.data.quest.repository::QuestRepository','')
 put('pinball.context.global::GlobalLogicForQuest','')
 for name in ['GachaRarityOddsTable','GachaOddsTable','EquipmentGachaOddsTable']:
  put('pinball.master.generated::'+name,'',' extends pinball.master.runtime.MasterTable')
 for qn in ['pinball.common.data.gacha::GachaPrizeKind','pinball.common.data.mission.collectItemEvent::CollectItemEventKind']:
  put(qn,'public var index:int=0;public var params:Array=[];')
 for qn,names in [('pinball.common.data.quest.event.ranking::RankingEventTimeKind',['Playable','Aggregation','RewardReceive','OutOfPeriod']),('pinball.common.data.mission.activeMission::RealIncentiveMissionEventTimeKind',['Playable','Lottery','RewardReceive','OutOfPeriod'])]:
  put(qn,'public var tag:String;public var index:int;public function '+qn.split('::')[1]+'(t:String){tag=t;index='+str(names).replace("'",'"')+'.indexOf(t);}'+''.join('public static var '+n+':'+qn.split('::')[1]+'=new '+qn.split('::')[1]+'("'+n+'");' for n in names))
 for kind in ['QuestClear','OwnedCharacter','GameSystemUnlock']:
  put('pinball.common.data.quest.condition.viewable::QuestViewableConditionBy'+kind,'public var allowed:Boolean=true;public var calls:int=0;public function satisfied(p:Object,t:Number):Boolean{calls++;return allowed;}')
 put('pinball.common.data.quest.event.rush::RushEventQuestLogic','public function isClearedFromProgress(p:Object):Boolean{return false;}')
 put('pinball.common.ds._Maybe::Maybe_Impl_','public static var tmp:Object;')
 stubs['Std.as']='package {public class Std {public static function string(v:Object):String{return String(v);}}}'
 includes.append('Std')
 stubs['flash/Boot.as']=stubs['flash/Boot.as'].replace('public static var lastError:Error;','public static var lastError:Error;public static var skip_constructor:Boolean=false;')
 stubs['pinball/error/ClientError.as']='package pinball.error {public class ClientError extends Error {public var code:int;public function ClientError(c:int,m:String){super(m,c);code=c;}}}'
 stubs['pinball/common/time/_AppTime/AppTime_Impl_.as']=stubs['pinball/common/time/_AppTime/AppTime_Impl_.as'].replace('public class AppTime_Impl_ {','public class AppTime_Impl_ {public static function _new(v:Number):Number{return v;}public static function toSecondsAccuracy(v:Number):Number{return Math.floor(v/1000)*1000;}')
 stubs['pinball/common/time/TimeRange.as']=stubs['pinball/common/time/TimeRange.as'].replace('endTime:Object','endTime:haxe.ds.Option').replace('e:Object','e:haxe.ds.Option').replace('public function isWithin','public function isEarlierThanEnd(t:Number):Boolean{return endTime.index==1||t<=Number(endTime.params[0]);}public function isWithin')
 stubs['pinball/common/tools/DateUtil.as']=stubs['pinball/common/tools/DateUtil.as'].replace('public class DateUtil {','public class DateUtil {public static function formatRemainingTime(a:Object,t:Number):String{return String(t);}')
 campaign_ui.add_support(stubs,put)
 # Untaken original scene branches still name concrete types during AVM2
 # verification. Declare only those bounded type dependencies, never their UI.
 for label in labels:
  if not label.startswith('pinball.scene.') and '/getRemainingTimeUntilNextEvent|' not in label:continue
  bi,=source.by_label[label]
  for op,args,_,_,_ in source.normalized(bi)[0]:
   if op not in (0x60,0x80,0x86):continue
   for mn in args:
    if not isinstance(mn,tuple) or mn[0]!=7 or not mn[1][1].startswith('pinball.'):continue
    qn=mn[1][1]+'::'+mn[2];path=mn[1][1].replace('.','/')+'/'+mn[2]+'.as'
    if path not in stubs:put(qn,'')
 assistant.prepare(stubs,includes)
 # ASC's qualified-expression lookup still needs explicit imports. Keep these
 # support declarations independent of compiler wildcard/source-path behavior.
 names=[path[:-3].replace('/','.') for path in stubs if path.endswith('.as') and '/' in path]+['flash.geom.Rectangle']
 for path,text in list(stubs.items()):
  imports=['import '+full+';' for full in re.findall(r'\bimport\s+([\w.]+);',text)]
  text=re.sub(r'\bimport\s+[\w.]+;','',text)
  for full in sorted(names,key=len,reverse=True):
   if full in text:
    imports.append('import '+full+';');text=text.replace(full,full.rsplit('.',1)[-1])
  if imports:text=text.replace('{','{'+''.join(dict.fromkeys(imports)),1)
  stubs[path]=text
 return stubs,labels,includes

def import_date_prologue(builder, target, main, receipts):
 """Run the real constructor's sanitizer prologue, excluding all graphics/UI.

 This is deliberately not evidence that the complete template constructor ran.
 The separate receipt records the exact source instruction range and limitation.
 """
 source=builder.view(main)
 label='pinball.ui.component.template::QuestLikeSceneTemplateView/<ctor>'
 di,=source.by_label[label];original=main.bodies[di]
 decoded=builder.p.asm.decode(original[5]);stop=None
 for i,ins in enumerate(decoded[:10]):
  if ins.op==0x4f and main.mn_name(ins.args[0])=='sanitizeDateConfig':stop=i+1;break
 if stop is None:return False
 assert [i.op for i in decoded[:stop]]==[0xd0,0x30,0x60,0xd2,0x4f]
 ti,=target.by_label['cn.fixture::NativeDateCtorProbe/run|1'];prior=target.a.bodies[ti]
 sliced=list(original);sliced[5]=builder.p.asm.encode(decoded[:stop]+[builder.p.asm.Instruction(0x47)])[0];sliced[6]=[]
 expected=source.normalized(di)[0][:stop]
 try:
  main.bodies[di]=sliced
  importer=builder.p.Importer(target,builder.view(main));target.a.bodies[ti]=importer.body(di,prior[0])
 finally:main.bodies[di]=original
 assert target.normalized(ti)[0][:-1]==expected,'native constructor sanitizer prologue differs'
 builder.p.check_body(target.a.bodies[ti],target.a)
 import hashlib
 receipts.append({'label':label,'kind':'bounded-native-constructor-prologue','sourceCodeSha256':hashlib.sha256(original[5]).hexdigest(),'sourceParameterTypes':[main.mn_name(t) for t in main.methods[original[0]][1]],'configArgumentLocal':2,'sourceInstructionRange':[0,stop],'normalizedPrefixExact':True,'wholeConstructorExecuted':False,'targetHarness':'cn.fixture::NativeDateCtorProbe/run|1'})
 return True

BODY = r'''
var nativeBaseline:Boolean=EXPECT_NATIVE_BASELINE;
var make:Function=function(n:String):Object {var c:Class=getDefinitionByName(n.replace("::",".")) as Class;return new c();};
var planRepo:Object=make("pinball.common.data.gacha.GachaRepository");
var nativePlayer:Object=make("pinball.common.data.player.PlayerLogic");
Array.prototype.iterator=function():Object {var items:Array=this as Array,pos:int=0;return {hasNext:function():Boolean{return pos<items.length;},next:function():Object{return items[pos++];}};};
Array.prototype.setPropertyIsEnumerable("iterator",false);
var makePool:Function=function(id:int,equipment:Boolean=false,personal:String=""):Object {
 var g:Object=make("pinball.common.data.gacha.GachaLogic"),prize:Object=make("pinball.common.data.gacha.GachaPrizeKind");
 g.id=id;prize.index=equipment?1:0;prize.params=[{character_odds_rarity_3:"fixture_char3",character_odds_rarity_4:"fixture_char4",character_odds_rarity_5:"fixture_char5",equipment_odds_rarity_3:"fixture_equip3",equipment_odds_rarity_4:"fixture_equip4",equipment_odds_rarity_5:"fixture_equip5"}];
 g.values={odds_rarity_string_id:"cnmod_abyss_limited_gacha_rarity",note_asset:"fixture_note",prize_kind:prize,is_comeback:personal=="comeback",is_stars_gacha:personal=="stars",freemium_guarantee_available:true};
 g.period=new TimeRange(0,Option.Some(500));return g;
};
var gc:Object=makePool(990001),ge:Object=makePool(990004,true);
snap2(201,[row2("gacha:990001",{visible:action(true),enter:action(true)}),row2("gacha:990004",{visible:action(true),enter:action(true)})]);
planRepo.characters=[gc];planRepo.equipments=[ge];
var assets:Object=make("pinball.asset.logic.AssetPathCollectionBuilder");planRepo.resolveAssetPathCollection(nativePlayer,assets,1000,[],true);
var paths:Array=[];for each(var mp:Object in assets.master.paths)paths.push(mp.path);
check((paths.indexOf("/gacha_odds/cnmod_abyss_limited_gacha_rarity")>=0)==!nativeBaseline,"actual native global planner registers permanent pool rarity master");
check((paths.indexOf("/gacha_odds/fixture_char3")>=0 && paths.indexOf("/gacha_odds/fixture_char4")>=0 && paths.indexOf("/gacha_odds/fixture_char5")>=0)==!nativeBaseline,"actual native character resolver registers all three odds masters");
check((paths.indexOf("/gacha_odds/fixture_equip3")>=0 && paths.indexOf("/gacha_odds/fixture_equip4")>=0 && paths.indexOf("/gacha_odds/fixture_equip5")>=0)==!nativeBaseline,"actual native equipment resolver registers all three odds masters");
var cache:Object=make("pinball.asset.logic.LogicAssetContainer");for each(mp in assets.master.paths){var masterClass:Class=mp.clazz as Class;cache.loaded[mp.path]=new masterClass();}
var oddsTools:Class=getDefinitionByName("pinball.common.data.gacha.GachaOddsTools") as Class;
var c8013:Boolean=false;try {cache.getMasterTableWithPath(oddsTools.getRarityOddsPath(gc.get_oddsRarityStringId()));}catch(missing:Error){if(missing.errorID!=8013)throw missing;c8013=true;}
check(c8013==nativeBaseline,"actual native master lookup reproduces old C8013 and candidate supplies planner dependency");
if(!nativeBaseline){ge.values.freemium_guarantee_available=false;planRepo.characters=[];assets=make("pinball.asset.logic.AssetPathCollectionBuilder");planRepo.resolveAssetPathCollection(nativePlayer,assets,1000,[],true);check(assets.master.paths.length==0,"actual native equipment preloader retains freemium qualification filter");ge.values.freemium_guarantee_available=true;planRepo.characters=[gc];}
snap2(202,[row2("gacha:990001",{visible:action(false),enter:action(false)}),row2("gacha:990004",{visible:action(false),enter:action(false)})]);
assets=make("pinball.asset.logic.AssetPathCollectionBuilder");planRepo.resolveAssetPathCollection(nativePlayer,assets,1000,[],true);
check(assets.master.paths.length==0,"closed pool does not retain open preload dependency");
if(!nativeBaseline){snap2(203,[row2("gacha:990001",{visible:action(true)})]);assets=make("pinball.asset.logic.AssetPathCollectionBuilder");planRepo.equipments=[];planRepo.resolveAssetPathCollection(nativePlayer,assets,1000,[],true);check(assets.master.paths.length==4 && ContentOperationsState.gachaEnterGate(gc,nativePlayer,1000,false)==0,"actual native visible-only planner loads resources while expired participation remains denied");}
for each(var personalKind:String in ["stars","comeback"]) {
 var personal:Object=makePool(personalKind=="stars"?80000:700000,false,personalKind);
 snap2(personalKind=="stars"?204:205,[row2("gacha:"+personal.id,{visible:action(true),enter:action(true)})]);
 check(!personal.isWithinPeriod(nativePlayer,1000,false),"actual native personal pool without entitlement stays unavailable: "+personalKind);
 var field:String=personalKind=="stars"?"starsGachaPeriod":"comebackGachaPeriod";
 personal[field]=Option.Some(new TimeRange(900,Option.Some(1100)));
 check(personal.isWithinPeriod(nativePlayer,1000,false) && personal.get_endTime().params[0]==1100,"actual native personal Some period retained: "+personalKind);
 check(ContentOperationsState.gachaEnterGate(personal,nativePlayer,1000,false)==-1,"actual personal entry gate preserves native valid personal window despite expired master: "+personalKind);
 personal[field]=Option.Some(new TimeRange(0,Option.Some(500)));
 check(!personal.isWithinPeriod(nativePlayer,1000,false),"actual native personal expired period stays unavailable: "+personalKind);
}
var collectible:Object=make("pinball.common.data.collectItem.CollectItemEventLogic"),collectKind:Object=make("pinball.common.data.mission.collectItemEvent.CollectItemEventKind");collectKind.index=1;
collectible.values={kind:collectKind,start_time:0,end_time:500,exchangeable_end_time:Option.Some(500)};collectible.exchangablePeriod=new TimeRange(0,Option.Some(500));
snap2(206,[row2("collect_item_event:1",{visible:action(true),exchange:action(true)})]);
var cr:Object=make("pinball.common.data.collectItem.CollectItemEventRepository");
check(cr.collectItemEventExchangingAvailable(1000,collectible)==!nativeBaseline,"actual native exchange child filter observes operator permanent exchange");
check(collectible.getRemainingTimeLabel(1000).params[0]==(nativeBaseline?"-500":"仅可兑换"),"actual native collect label uses exchange action instead of obsolete master deadline");
snap2(207,[row2("collect_item_event:1",{visible:action(true),exchange:action(false)})]);collectible.exchangablePeriod=new TimeRange(0,Option.Some(2000));
check(collectible.isExchangingAvailable(1000)==nativeBaseline,"actual native exchange child filter does not resurrect closed exchange by old dates");
var campaignCases:Array=[{name:"specialExchange.SpecialExchangeCampaignLogic",key:"special_exchange_campaign"},{name:"multiSpecialExchange.MultiSpecialExchangeCampaignLogic",key:"multi_special_exchange_campaign"},{name:"startDashExchange.StartDashExchangeCampaignLogic",key:"start_dash_exchange_campaign"}];
var revision:int=208;
for each(var cc:Object in campaignCases) {
 var campaign:Object=make("pinball.common.data.campaign."+cc.name);campaign.values={exchange_end_time:500,period_end_time:500};if("startDashExchangeCampaignData" in campaign)campaign.startDashExchangeCampaignData=Option.Some({period_end_time:0.5});
 snap2(revision++,[row2(cc.key+":1",{visible:action(true),exchange:action(true)})]);
 check(campaign.isOverExchangePeriod(1000)==nativeBaseline,"actual native campaign expiration supports permanent exchange: "+cc.key);
 snap2(revision++,[row2(cc.key+":1",{visible:action(true),exchange:action(false)})]);campaign.values.exchange_end_time=2000;campaign.values.period_end_time=2000;if("startDashExchangeCampaignData" in campaign)campaign.startDashExchangeCampaignData=Option.Some({period_end_time:2});
 check(campaign.isOverExchangePeriod(1000)==!nativeBaseline,"actual native campaign expiration obeys explicit close: "+cc.key);
 if("startDashExchangeCampaignData" in campaign){campaign.startDashExchangeCampaignData=Option.None;snap2(revision++,[row2(cc.key+":1",{visible:action(true),exchange:action(true)})]);var noDataError:Boolean=false;try{campaign.get_periodEndTime();}catch(noData:Error){if(noData.errorID!=2562)throw noData;noDataError=true;}check(noDataError,"actual native StartDash no-data end getter preserves original 2562 contract");var noBuyDataError:Boolean=false;try{campaign.get_buyEndTime();}catch(noBuyData:Error){if(noBuyData.errorID!=2562)throw noBuyData;noBuyDataError=true;}check(noBuyDataError,"actual native StartDash no-data buy getter preserves original 2562 contract");if(!nativeBaseline)check(campaign.isOverExchangePeriod(1000),"operator open cannot create personal StartDash entitlement");}
}
var active:Object=make("pinball.common.data.mission.activeMission.ActiveMissionEventLogic");active.values={start_time:0,playable_end_time:Option.Some(500),lottery_end_time:Option.Some(1500),end_time:Option.Some(2000)};
snap2(220,[row2("active_mission_event:1",{visible:action(true),enter:action(false),claim:action(true)})]);
check(active.getRealIncentiveMissionEventTimeKind(1500).tag==(nativeBaseline?"Lottery":"RewardReceive"),"actual native incentive phase cannot let old lottery dates mask operator claim");
snap2(221,[row2("active_mission_event:1",{visible:action(false),enter:action(false),claim:action(false)})]);
check(active.getRealIncentiveMissionEventTimeKind(1500).tag==(nativeBaseline?"Lottery":"OutOfPeriod"),"actual native incentive phase respects complete closure");
var listNative:Object=make("pinball.common.data.event.EventListLogic");listNative.eventListValuesArray=[{values:{event:EventIdKind.TowerDungeonEvent(1)}}];
snap2(222,[row2("tower_dungeon_event:1",{visible:action(true)}),row2("tower_dungeon_event:2",{visible:action(true)})],[{key:"tower_dungeon_event:2",entry:{kind:"TowerDungeonEvent",id:2}}]);
check(listNative.getAllEventIds().length==(nativeBaseline?2:1),"actual native event-list body filters folder entries without injecting catalog-only events");
var nativeCases:Array=NATIVE_EVENT_CASES,nativeRows:Array=[],nativeCatalog:Array=[],questIndex:int=101;
for each(var nc:Object in nativeCases){nc.questId=questIndex++;nativeRows.push(row2(nc.key+":1",{visible:action(true,null,["3:"+nc.questId]),enter:action(true,null,["3:"+nc.questId])}));nativeCatalog.push({key:nc.key+":1",quest_keys:["3:"+nc.questId,"3:"+(nc.questId+1000)]});}
snap2(223,nativeRows,nativeCatalog);
var bootClass:Class=getDefinitionByName("flash.Boot") as Class;bootClass.skip_constructor=true;
for each(nc in nativeCases) {
 var actual:Object=make(nc.name);if("id" in actual)actual.id=1;else actual.eventId=1;actual.commonValues={start_time:0,playable_end_time:Option.Some(500)};
 check(ContentOperationsState.towerKey(actual)==nc.key+":1" && actual.isWithinPeriod(1000),"actual sealed native receiver and inherited period: "+nc.name);
 var exact:Object=make("pinball.common.data.quest.fixture."+nc.name.split("::")[1].replace("Logic","ScopedQuest"));exact.id=nc.questId;exact[nc.field]=actual;
 check(exact.isWithinPeriod(1000) && exact.isWithinViewablePeriod(1000),"actual native base accepts exact scoped quest on sealed receiver: "+nc.name);exact.id+=1000;
 check(!exact.isWithinPeriod(1000) && !exact.isWithinViewablePeriod(1000),"actual native base rejects sibling quest outside exact scope: "+nc.name);
}
bootClass.skip_constructor=false;
var rankCtorFailed:Boolean=false,rank:Object;
snap2(224,[row2("ranking_event:1",{visible:action(true),enter:action(true),claim:action(true)})]);
var rankClass:Class=getDefinitionByName("pinball.common.data.quest.event.ranking.RankingEventLogic") as Class;
try {rank=new rankClass(1,make("pinball.asset.logic.LogicAssetContainer"),null,null);}catch(rankError:Error){rankCtorFailed=rankError.errorID==2703;}
check(rankCtorFailed==nativeBaseline,"actual native Ranking constructor retains its mandatory Some playable-end contract");
if(!nativeBaseline) {
 check(rank.getNowRankingEventTimeKind(1000).tag=="Playable","actual native Ranking phase remains playable under permanent participation");
 snap2(225,[row2("ranking_event:1",{visible:action(true),enter:action(false),claim:action(true)})]);
 check(rank.getNowRankingEventTimeKind(1000).tag=="RewardReceive","actual native Ranking claim phase follows independent claim action");
 snap2(226,[row2("ranking_event:2",{visible:action(true),enter:action(false)})]);
 var unmanagedRank:Object=new rankClass(2,make("pinball.asset.logic.LogicAssetContainer"),null,null);
 check(unmanagedRank.getNowRankingEventTimeKind(5000).tag=="RewardReceive","actual native Ranking never-managed claim retains earned original reward phase");
 snap2(227,[row2("ranking_event:2",{visible:action(true),enter:action(false),claim:action(false)})]);
 check(unmanagedRank.getNowRankingEventTimeKind(5000).tag=="OutOfPeriod","actual native Ranking explicit claim closure differs from never-managed claim");
 active.values.lottery_end_time=Option.Some(2000);active.values.end_time=Option.Some(10000);
 snap2(228,[row2("active_mission_event:2",{visible:action(true),enter:action(false)})]);
 var unmanagedActive:Object=make("pinball.common.data.mission.activeMission.ActiveMissionEventLogic");unmanagedActive.id=2;unmanagedActive.values=active.values;
 check(unmanagedActive.getRealIncentiveMissionEventTimeKind(5000).tag=="RewardReceive","actual native incentive never-managed claim retains original reward phase");
 snap2(229,[row2("active_mission_event:2",{visible:action(true),enter:action(false),claim:action(false)})]);
 check(unmanagedActive.getRealIncentiveMissionEventTimeKind(5000).tag=="OutOfPeriod","actual native incentive explicit claim closure differs from never-managed claim");
}
var adv:Object=make("pinball.common.data.quest.event.advent.AdventEventQuestLogic");adv.adventEvent=make("pinball.common.data.quest.event.advent.AdventEventLogic");
var pp:Object=make("pinball.common.data.player.PlayerPeek");
snap2(230,[row2("advent_event:1",{visible:action(true,null,["3:101"]),enter:action(true,null,["3:101"])})],[{key:"advent_event:1",quest_keys:["3:101","3:102"]}]);
check(adv.isViewable(pp,1000)==!nativeBaseline,"actual Advent override no longer rejects allowed quest at old calendar end");
var condition:Object=make("pinball.common.data.quest.condition.viewable.QuestViewableConditionByQuestClear");condition.allowed=false;adv.questViewableConditionByQuestClear=condition;
check(!adv.isViewable(pp,1000),"actual Advent override preserves player progress qualification even while operator open");
condition.allowed=true;adv.id=102;
check(!adv.isViewable(pp,1000),"actual Advent override preserves exact visible quest scope");
if(!nativeBaseline) {
 adv.id=101;adv.questViewableConditionByQuestClear=null;
 for each(var conditionKind:String in ["QuestClear","OwnedCharacter","GameSystemUnlock"]){var conditionField:String="questViewableConditionBy"+conditionKind;var typedCondition:Object=make("pinball.common.data.quest.condition.viewable.QuestViewableConditionBy"+conditionKind);typedCondition.allowed=false;adv[conditionField]=typedCondition;check(!adv.isViewable(pp,1000) && typedCondition.calls==1,"actual Advent original player qualification executes under open operator date: "+conditionKind);adv[conditionField]=null;}
 var sceneNames:Array=NATIVE_DATE_SCENES;
 snap2(231,[row2("advent_event:1",{visible:action(true),enter:action(true)})]);
 for each(var dateName:String in sceneNames){var ds:Object=make(dateName);ds.eventPeek=adv.adventEvent;ds.event=adv.adventEvent;check(ds.getDate()===Option.None,"actual native date panel hides permanent numeric bound: "+dateName);}
 snap2(232,[row2("advent_event:1",{visible:action(true),enter:action(true,61000)})]);
 for each(dateName in sceneNames){ds=make(dateName);ds.eventPeek=adv.adventEvent;ds.event=adv.adventEvent;var actualDate:Object=ds.getDate();check(actualDate.index==0 && actualDate.params[0].frame==12 && actualDate.params[0].timeRanges[0].end==61000,"actual native finite date panel keeps original frame/date shape: "+dateName);}
 snap2(233,[row2("advent_event:1",{visible:action(true),enter:action(false)})]);
 check(ds.getDate()===Option.None,"actual native date panel removes participation deadline when entry closes");
 var rankScene:Object=make("pinball.scene.event.ranking.questSelect.RankingEventQuestSelectScene");rankScene.event=rank;
 snap2(234,[row2("ranking_event:1",{visible:action(true),enter:action(false),claim:action(true,61000)})]);
 var periodInfo:Object=rankScene.getEventPeriodInfo();check(periodInfo.index==0 && periodInfo.params[0].uiStringKey=="event_reward_receive_dates" && periodInfo.params[0].timeRange.endTime.params[0]==61000,"actual native ranking date panel chooses claim deadline and UI key");
 snap2(235,[row2("ranking_event:1",{visible:action(true),enter:action(false),claim:action(true)})]);check(rankScene.getEventPeriodInfo()===Option.None,"actual native ranking date panel hides permanent claim bound");
 var score:Object=make("pinball.common.data.quest.event.scoreAttack.ScoreAttackEventLogic"),sq:Object=make("pinball.common.data.quest.event.scoreAttack.ScoreAttackEventQuestLogic");sq.id=301;sq.scoreAttackEvent=score;score.quests=[sq];
 snap2(236,[row2("score_attack_event:1",{visible:action(true),enter:action(true,null,["3:301"])})],[{key:"score_attack_event:1",quest_keys:["3:301","3:302"]}]);
 check(score.getRemainingTimeUntilNextEvent(1000)===Option.None,"actual native score getter does not reuse obsolete quest.period for permanent participation");
 snap2(237,[row2("score_attack_event:1",{visible:action(true),enter:action(true,61000,["3:301"])})],[{key:"score_attack_event:1",quest_keys:["3:301","3:302"]}]);
 check(score.getRemainingTimeUntilNextEvent(1000).params[0]>0,"actual native score getter uses controlled deadline through getQuests");
 sq.id=302;check(score.getRemainingTimeUntilNextEvent(1000)===Option.None,"actual native score getter does not invent an allowed child outside exact scope");
 var probe:Object=make("cn.fixture.NativeDateCtorProbe"),preserved:Object={tag:"other constructor config"};
 snap2(238,[row2("collect_item_event:1",{visible:action(true),enter:action(true)})]);
 var panelDate:Object={frame:12,timeRanges:[{uiStringKey:"event_quest_dates",start:collectible.get_startTime(),end:collectible.get_endTime()}],remaining:Option.None};
 var templateConfig:Object={date:Option.Some(panelDate),other:preserved};
 probe.run(null,templateConfig);check(templateConfig.date===Option.None && templateConfig.other===preserved,"actual constructor sanitizer prologue suppresses Collect native permanent getter date without changing other config");
 snap2(239,[row2("collect_item_event:1",{visible:action(true),enter:action(true,61000)})]);
 panelDate={frame:12,timeRanges:[{uiStringKey:"event_quest_dates",start:collectible.get_startTime(),end:collectible.get_endTime()}],remaining:Option.Some(60000)};var originalDate:Object=Option.Some(panelDate);templateConfig={date:originalDate,other:preserved};
 probe.run(null,templateConfig);check(templateConfig.date===originalDate && panelDate.timeRanges[0].end==61000 && panelDate.frame==12 && panelDate.remaining.params[0]==60000 && templateConfig.other===preserved,"actual constructor sanitizer prologue preserves finite native date payload and other fields");
 snap2(240,[row2("collect_item_event:1",{visible:action(true),enter:action(false)})]);
 templateConfig={date:Option.Some({frame:12,timeRanges:[{uiStringKey:"event_quest_dates",start:collectible.get_startTime(),end:collectible.get_endTime()}],remaining:Option.None}),other:preserved};
 probe.run(null,templateConfig);check(templateConfig.date===Option.None && templateConfig.other===preserved,"actual constructor sanitizer prologue suppresses controlled closed native Some zero date");
 var finiteRow:Object={uiStringKey:"finite",start:0,end:61000},finiteRow2:Object={uiStringKey:"finite2",start:1,end:62000};templateConfig={date:Option.Some({frame:12,timeRanges:[finiteRow,{start:0,end:8640000000000000},finiteRow2],remaining:Option.None})};
 probe.run(null,templateConfig);check(templateConfig.date.index==0 && templateConfig.date.params[0].timeRanges.length==2 && templateConfig.date.params[0].timeRanges[0]===finiteRow && templateConfig.date.params[0].timeRanges[1]===finiteRow2,"actual constructor sanitizer prologue preserves finite row order and references in mixed date panel");
 originalDate=Option.Some({frame:12,timeRanges:[{start:0,end:0}],remaining:Option.None});templateConfig={date:originalDate,other:preserved};probe.run(null,templateConfig);check(templateConfig.date===originalDate,"actual constructor sanitizer prologue retains unmanaged epoch-zero date");
 templateConfig={date:Option.None,other:preserved};probe.run(null,templateConfig);check(templateConfig.date===Option.None && templateConfig.other===preserved,"actual constructor sanitizer prologue preserves native None config");
}
'''
BODY+=campaign_ui.BODY
