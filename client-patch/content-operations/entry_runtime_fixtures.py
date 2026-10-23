"""Native entry consumers, with bounded master/UI/IoC dependencies only."""
import re

METHODS = {
 'pinball.common.data.event::EventListLogic': ['<ctor>', 'sortByDisplayOrder', 'getId', 'getDisplayOrder', 'getAllEventIds'],
 'pinball.master.generated::EventListValues': ['<ctor>'],
 'pinball.common.data.bossBattle::BossBattleHeaderBannerResolver$': ['resolve'],
 'pinball.common.data.banner::EventBannerImageLogic': ['<ctor>', 'getHeaderMiniBannerPathAt', 'getBannerScheduleRangeIndex'],
 'pinball.scene.boxGacha::BoxGachaScene': ['buttonClicked'],
 'pinball.scene.event::EventSelectFlow': ['<ctor>', 'run', 'resolveTransitionRouterResult'],
 'pinball.common.data.quest.event::EventQuestSelectSceneResolver$': ['resolveSingleQuestSelectScene', 'resolveMultiQuestSelectScene'],
 'pinball.common.data.quest.event.common::EventLogicKind$': ['WorldStoryEvent', 'AdventEvent', 'RushEvent'],
 'pinball.common.data.scene::SceneKind$': ['Mission', 'WorldStoryEventQuestSelect', 'AdventEventQuestSelect', 'RushEventLoading', 'RushEventTop'],
 'pinball.common.data.scene::ChangeSceneOrLoading$': ['Scene'],
 'pinball.common.data.scene::ChangeSceneBackKind$': ['FromHome'],
 'pinball.common.data.scene::TransitionKind$': ['BlackOut'],
 'pinball.common.data.scene::TransitionRouterResult': ['<ctor>'],
 '::Std$': ['parseInt'], '::Reflect$': ['compare'], '::Type$': ['enumEq'],
}

def prepare(stubs, cases, abc, builder):
 from native_runtime_fixtures import prepare as base_prepare
 stubs, _, includes = base_prepare(stubs, cases, abc, builder)
 labels=[];source=builder.view(abc)
 def put(qn,body,base=''):
  package,name=qn.split('::');path=(package.replace('.','/')+'/' if package else '')+name+'.as'
  stubs[path]='package '+package+' {public class '+name+base+' {'+body+'}}';includes.append((package+'.' if package else '')+name)
 def append(qn,text):
  package,name=qn.split('::');path=(package.replace('.','/')+'/' if package else '')+name+'.as'
  stubs[path]=re.sub(r'(public class '+re.escape(name)+r'[^\{]*\{)',lambda m:m.group(1)+text,stubs[path],count=1)
 def declaration(qn,method):
  matches=[label for label in source.by_label if label.startswith(qn.removeprefix('::')+'/') and label.rsplit('/',1)[-1].split('|')[0]==method]
  assert len(matches)==1,(qn,method,matches)
  label=matches[0];labels.append(label);bi,=source.by_label[label];m=abc.methods[abc.bodies[bi][0]]
  def typ(i):return abc.mn_name(i).replace('::','.') if i else '*'
  args=','.join('p'+str(i)+':'+typ(t)+('=false' if typ(t)=='Boolean' else '=0' if typ(t) in ['int','uint','Number'] else '=null') for i,t in enumerate(m[1]))
  returns=typ(m[0]);name=qn.rstrip('$').split('::')[1];ctor=method=='<ctor>'
  value='' if returns=='void' or ctor else 'return false;' if returns=='Boolean' else 'return 0;' if returns in ['int','uint','Number'] else 'return null;'
  return 'public '+('static ' if qn.endswith('$') else '')+'function '+(name if ctor else method)+'('+args+')'+('' if ctor else ':'+returns)+'{'+('super();' if ctor and name=='EventSelectFlow' else value)+'}'
 storage={
 'pinball.common.data.event::EventListLogic':'public var logicAssets:pinball.asset.logic.ILogicAssetContainer;public var eventListValuesArray:Array;',
 'pinball.master.generated::EventListValues':'public var event:pinball.common.data.quest.event.EventIdKind;public var display_order:int;',
 'pinball.common.data.banner::EventBannerImageLogic':'public var listBannerPaths:Array;public var headerMiniBannerPaths:Array;public var bannerScheduleRanges:Array;',
 'pinball.scene.boxGacha::BoxGachaScene':'''public var boxGachaId:int=108;public var animationState:int=0;public var carousel:Object;
public var globalLogic:pinball.context.global.GlobalLogic;public var flows:Array=[];public var transitions:Array=[];public var boxes:Array=[];
public var logic:Object;public var boxGacha:Object;public var preparedTime:Number;public var drawnRewardPanel:Object;public var buttonGroup:Object;
public function addFlow(f:Object):void{flows.push(f);f.globalLogic=globalLogic;f.scene=this;}
public function changeSceneWithPushBackScene(v:Object):void{transitions.push(v);}public function drawBoxGacha(v:Object,n:int):void{}
public function resetBox(v:Object):void{}public function openDialog(v:Object):void{}public function closeBox(v:Object):void{}public function showInstantMessage(v:String,p:Object):void{}''',
 'pinball.scene.event::EventSelectFlow':'public var scene:pinball.context.scene.ILogicScene;public var multi:Boolean;public var globalLogic:pinball.context.global.GlobalLogic;public var event:pinball.common.data.quest.event.common.EventLogic;public var backKind:haxe.ds.Option;',
 'pinball.common.data.quest.event.common::EventLogicKind':'public var index:int;public var tag:String;public var params:Array;public function EventLogicKind(t:String,i:int,p:Array){tag=t;index=i;params=p;}',
 'pinball.common.data.scene::TransitionRouterResult':'public var overwritePlayer:haxe.ds.Option;public var nextKind:pinball.common.data.scene.ChangeSceneOrLoading;public var backKind:pinball.common.data.scene.ChangeSceneBackKind;',
 '::Std':'public static function string(v:Object):String{return String(v);}',
 }
 # Enum factories outside the selected route are inert dependencies. Selected
 # Mission/World/Advent/Rush factories below are replaced with production bodies.
 for qn in ['pinball.common.data.scene::SceneKind','pinball.common.data.scene::ChangeSceneOrLoading','pinball.common.data.scene::ChangeSceneBackKind','pinball.common.data.scene::TransitionKind']:
  name=qn.split('::')[1]
  storage[qn]='public var index:int;public var tag:String;public var params:Array;public function '+name+'(t:String,i:int,p:Array){tag=t;index=i;params=p;}'
  if name=='SceneKind':storage[qn]+='public static var EventTop:SceneKind=new SceneKind("EventTop",0,[]);'
 for qn,methods in METHODS.items():
  actual=qn.rstrip('$');body=storage.get(actual,'')
  body+=''.join(declaration(qn,method) for method in methods)
  base=' extends jp.sipo.gipo.core.GearHolderImpl' if actual.endswith('::EventSelectFlow') else ' extends pinball.context.scene.ReloadTestScene' if actual.endswith('::BoxGachaScene') else ''
  put(actual,body,base)
 for qn in ['pinball.common.data.quest.event.advent::AdventEventLogic','pinball.common.data.quest.event.rush::RushEventLogic']:
  append(qn,declaration(qn,'toDetail'))
 stubs['flash/Boot.as']=stubs['flash/Boot.as'].replace('public static var lastError:Error;','public static var lastError:Error;')
 stubs['pinball/master/runtime/MasterMap.as']=stubs['pinball/master/runtime/MasterMap.as'].replace('function get(', 'function rawKeys():Array;function get(')
 append('pinball.master.runtime::FixtureMasterMap','public function rawKeys():Array{return [];}')
 put('cn.fixture::EntryMap','public var records:Array=[];public function rawKeys():Array{var a:Array=[];for each(var r:Object in records)a.push(r.id);return a;}public function get(id:int):Object{for each(var r:Object in records)if(r.id==id)return r.values;return null;}',' implements pinball.master.runtime.MasterMap')
 put('pinball.master.generated::EventListTable','public static var data:cn.fixture.EntryMap=new cn.fixture.EntryMap();public function get_data():pinball.master.runtime.MasterMap{return data;}',' extends pinball.master.runtime.MasterTable')
 put('pinball.common.data.quest.repository::QuestRepository','public var list:pinball.common.data.event.EventListLogic;public var events:Object={};public function getEventList():pinball.common.data.event.EventListLogic{return list;}public function getEvent(e:pinball.common.data.quest.event.EventIdKind):pinball.common.data.quest.event.common.EventLogic{return events[e.tag+":"+e.params[0]];}')
 stubs['pinball/common/data/quest/event/common/EventLogic.as']='''package pinball.common.data.quest.event.common {public interface EventLogic {
function isWithinPeriod(t:Number):Boolean;function isUnlocked():Boolean;function getEventBannerImageLogic():pinball.common.data.banner.EventBannerImageLogic;
function getUnlockedStatus():pinball.common.data.game_system_unlock.GameSystemUnlockStatus;function getUnlockEventIdInEventTop():haxe.ds.Option;
function getAutoPlayQuest(p:pinball.common.data.player.PlayerLogic):haxe.ds.Option;function toDetail():EventLogicKind;function get_availablePlayKind():int;function getEventId():pinball.common.data.quest.event.EventIdKind;}}'''
 put('pinball.common.data.game_system_unlock::GameSystemUnlockStatus','public var index:int;public var params:Array;public function GameSystemUnlockStatus(i:int,p:Array){index=i;params=p;}')
 put('cn.fixture::EntryEvent','''public var id:int;public var inPeriod:Boolean=true;public var unlocked:Boolean=true;public var unlockMovie:haxe.ds.Option=haxe.ds.Option.None;
public var autoQuest:haxe.ds.Option=haxe.ds.Option.None;public var banner:pinball.common.data.banner.EventBannerImageLogic;
public function isWithinPeriod(t:Number):Boolean{return inPeriod;}public function isUnlocked():Boolean{return unlocked;}
public function getEventBannerImageLogic():pinball.common.data.banner.EventBannerImageLogic{return banner;}
public function getUnlockedStatus():pinball.common.data.game_system_unlock.GameSystemUnlockStatus{return new pinball.common.data.game_system_unlock.GameSystemUnlockStatus(unlocked?0:1,[new pinball.common.data.game_system_unlock.GameSystemUnlockConditionMessage()]);}
public function getUnlockEventIdInEventTop():haxe.ds.Option{return unlockMovie;}public function getAutoPlayQuest(p:pinball.common.data.player.PlayerLogic):haxe.ds.Option{return autoQuest;}
public function toDetail():pinball.common.data.quest.event.common.EventLogicKind{var w:pinball.common.data.quest.event.worldStory.WorldStoryEventLogic=new pinball.common.data.quest.event.worldStory.WorldStoryEventLogic();w.id=id;return pinball.common.data.quest.event.common.EventLogicKind.WorldStoryEvent(w);}
public function get_availablePlayKind():int{return 0;}public function getEventId():pinball.common.data.quest.event.EventIdKind{return pinball.common.data.quest.event.EventIdKind.WorldStoryEvent(id);}''',' implements pinball.common.data.quest.event.common.EventLogic')
 put('cn.fixture::EntryGear','public var runHandler:Function;public var children:Array=[];public function addRunHandler(f:Function,p:Object):void{runHandler=f;}public function addChild(v:Object,p:Object):void{children.push(v);}')
 put('jp.sipo.gipo.core::GearHolderImpl','public var gear:cn.fixture.EntryGear;public function GearHolderImpl(){gear=new cn.fixture.EntryGear();}')
 stubs['pinball/context/scene/ILogicScene.as']=stubs['pinball/context/scene/ILogicScene.as'].replace('function openErrorDialog','function showUnlockMessage(v:Object):void;function changeSceneWithRouterResult(v:pinball.common.data.scene.TransitionRouterResult):void;function openErrorDialog')
 append('pinball.context.scene::ReloadTestScene','public var unlockMessages:Array=[];public var routerResults:Array=[];public function showUnlockMessage(v:Object):void{unlockMessages.push(v);}public function changeSceneWithRouterResult(v:pinball.common.data.scene.TransitionRouterResult):void{routerResults.push(v);}')
 stubs['pinball/context/global/GlobalLogicForDataLogic.as']='package pinball.context.global {public interface GlobalLogicForDataLogic {}}'
 stubs['pinball/context/global/GlobalLogic.as']=stubs['pinball/context/global/GlobalLogic.as'].replace('public class GlobalLogic {','public class GlobalLogic implements GlobalLogicForDataLogic {public var eventRepository:pinball.common.data.quest.repository.QuestRepository;public var moviePlayed:Boolean=true;public function getEventRepository():pinball.common.data.quest.repository.QuestRepository{return eventRepository;}public function getMiscData():pinball.common.data.localStore.MiscDataLogic{var v:pinball.common.data.localStore.MiscDataLogic=new pinball.common.data.localStore.MiscDataLogic();v.moviePlayed=moviePlayed;return v;}public function getPlayer():pinball.common.data.player.PlayerLogic{return new pinball.common.data.player.PlayerLogic();}')
 put('pinball.common.data.localStore::MiscDataLogic','public var moviePlayed:Boolean=true;public function getEventUnlockMoviePlayed(v:Object):Boolean{return moviePlayed;}')
 put('pinball.scene.ui::SingleQuestStartFlow','public static var starts:Array=[];public function start(q:Object,a:Object,b:Object,c:Boolean):void{starts.push({quest:q,a:a,b:b,c:c});}')
 put('pinball.common.data.quest.event.worldStory::WorldStoryEventQuestSelectTab','public var tag:String;public var index:int;public var params:Array=[];public function WorldStoryEventQuestSelectTab(t:String,i:int){tag=t;index=i;}public static var NormalSingle:WorldStoryEventQuestSelectTab=new WorldStoryEventQuestSelectTab("NormalSingle",0);')
 put('pinball.common.data.game_system_unlock::GameSystemUnlockConditionMessage','')
 put('pinball.common.data.quest.common::QuestLogic','public var nativeAutoQuest:int=0;')
 for qn in ['pinball.common.data.quest.id::QuestIdGroupKind','pinball.common.data.quest.id::SingleQuestIdKind','pinball.common.data.quest.id::MultiQuestIdKind']:
  put(qn,'public var index:int;public var params:Array=[];')
 stubs['pinball/common/data/quest/event/worldStory/WorldStoryEventQuestLogic.as']='package pinball.common.data.quest.event.worldStory {public interface WorldStoryEventQuestLogic {function getTab():WorldStoryEventQuestSelectTab;}}'
 includes.append('pinball.common.data.quest.event.worldStory.WorldStoryEventQuestLogic')
 put('pinball.scene.boxGacha.carousel::BoxGachaCarouselPageLogic','public var touchable:Boolean=true;public var sliderCount:int=0;public function getTouchable():Boolean{return touchable;}public function increaseSlider():void{sliderCount++;}')
 # Class names in untaken native branches must still resolve during verification.
 for label in labels:
  bi,=source.by_label[label]
  for op,args,_,_,_ in source.normalized(bi)[0]:
   if op not in (0x60,0x80,0x86):continue
   for mn in args:
    if not isinstance(mn,tuple) or mn[0]!=7 or not mn[1][1].startswith('pinball.'):continue
    qn=mn[1][1]+'::'+mn[2];path=mn[1][1].replace('.','/')+'/'+mn[2]+'.as'
    if path not in stubs:put(qn,'')
 # Resolve all typed package expressions exactly as in the existing fixtures.
 names=[path[:-3].replace('/','.') for path in stubs if path.endswith('.as') and '/' in path]
 for path,text in list(stubs.items()):
  imports=['import '+full+';' for full in re.findall(r'\bimport\s+([\w.]+);',text)];text=re.sub(r'\bimport\s+[\w.]+;','',text)
  for full in sorted(names,key=len,reverse=True):
   if full in text:imports.append('import '+full+';');text=text.replace(full,full.rsplit('.',1)[-1])
  if imports:text=text.replace('{','{'+''.join(dict.fromkeys(imports)),1)
  stubs[path]=text
 return stubs,labels,list(dict.fromkeys(includes))

BODY=r'''
Boot.skip_constructor=false;
var EntryMap:Class=getDefinitionByName("cn.fixture::EntryMap") as Class;
var EventListTable:Class=getDefinitionByName("pinball.master.generated::EventListTable") as Class;
var EventListValues:Class=getDefinitionByName("pinball.master.generated::EventListValues") as Class;
var EventListLogic:Class=getDefinitionByName("pinball.common.data.event::EventListLogic") as Class;
var Assets:Class=getDefinitionByName("pinball.asset.logic::LogicAssetContainer") as Class;
var QuestRepository:Class=getDefinitionByName("pinball.common.data.quest.repository::QuestRepository") as Class;
var HeaderResolver:Class=getDefinitionByName("pinball.common.data.bossBattle::BossBattleHeaderBannerResolver") as Class;
var Banner:Class=getDefinitionByName("pinball.common.data.banner::EventBannerImageLogic") as Class;
var EntryEvent:Class=getDefinitionByName("cn.fixture::EntryEvent") as Class;
var BoxScene:Class=getDefinitionByName("pinball.scene.boxGacha::BoxGachaScene") as Class;
var CarouselPage:Class=getDefinitionByName("pinball.scene.boxGacha.carousel::BoxGachaCarouselPageLogic") as Class;
var Quest:Class=getDefinitionByName("pinball.common.data.quest.common::QuestLogic") as Class;
var UnlockEvent:Class=getDefinitionByName("pinball.common.data.quest.event::UnlockEventIdKind") as Class;
var Resolver:Class=getDefinitionByName("pinball.common.data.quest.event::EventQuestSelectSceneResolver") as Class;
var AdventLogic:Class=getDefinitionByName("pinball.common.data.quest.event.advent::AdventEventLogic") as Class;
var RushLogic:Class=getDefinitionByName("pinball.common.data.quest.event.rush::RushEventLogic") as Class;
var worldIds:Array=[200100,200101,200102,200103,200104,200106,200107,200108,200109];
var boxIds:Array=[108,120,1000,1001,1003,1004,8002,8003,8004];
var assets:Object=new Assets();var master:Object=new EntryMap();EventListTable.data=master;
master.records=[{id:41,values:new EventListValues(["0","1","99"])},{id:42,values:new EventListValues(["6","200100","90"])}];
snap2(3000,[]);var list:Object=new EventListLogic(assets);
check(list.eventListValuesArray.length==2 && list.getId(EventIdKind.RushEvent(700017))==0,"default-off Rush adds no native family member");
snap2(3001,[row2("rush_event:700017",{visible:action(true),enter:action(false)})]);list=new EventListLogic(assets);
check(list.eventListValuesArray.length==2,"Rush visible-only cannot add entrance");
snap2(3002,[row2("rush_event:700017",{visible:action(true),enter:action(true)})]);list=new EventListLogic(assets);
check(list.eventListValuesArray.length==3 && list.eventListValuesArray[0].id==41 && list.eventListValuesArray[1].id==42,"native EventList constructor preserves existing members and relative order");
check(list.getId(EventIdKind.RushEvent(700017))==700017 && list.getDisplayOrder(EventIdKind.RushEvent(700017))==0,"Rush member uses actual typed native EventListValues and getters");
ContentOperationsState.restoreRushEventList(list);check(list.eventListValuesArray.length==3,"Rush restoration is idempotent");
snap2(3003,[row2("rush_event:700017",{visible:action(false),enter:action(false)})]);list=new EventListLogic(assets);
check(list.eventListValuesArray.length==2,"closed Rush is absent after native list reconstruction");
var repo:Object=new QuestRepository();repo.list=list;
var original:Object=new EntryEvent();original.banner=new Banner([],[],[Option.Some("original.png")]);repo.events["AdventEvent:1"]=original;repo.events["WorldStoryEvent:200100"]=original;
var advent:Object=new EntryEvent();advent.banner=new Banner([],[],[Option.Some("advent.png")]);repo.events["AdventEvent:300098"]=advent;
snap2(3004,[]);check(HeaderResolver.resolve(repo,assets,1000).length==2,"disabled Advent leaves original cooperative carousel intact");
snap2(3005,[row2("advent_event:300098",{visible:action(true),enter:action(true)})]);
check(HeaderResolver.resolve(repo,assets,1000).length==3 && list.eventListValuesArray.length==2,"Advent is restored only in original cooperative carousel without an EventTop member");
advent.inPeriod=false;check(HeaderResolver.resolve(repo,assets,1000).length==2,"restored Advent retains native period filter");advent.inPeriod=true;
advent.unlocked=false;check(HeaderResolver.resolve(repo,assets,1000).length==2,"restored Advent retains native unlock filter");advent.unlocked=true;
advent.banner=new Banner([],[],[]);check(HeaderResolver.resolve(repo,assets,1000).length==2,"restored Advent still requires original mini-banner");advent.banner=new Banner([],[],[Option.Some("advent.png")]);
var beforeIds:Array=list.getAllEventIds();var withAdvent:Array=ContentOperationsState.bossBattleHeaderIds(beforeIds);var twice:Array=ContentOperationsState.bossBattleHeaderIds(withAdvent);
check(beforeIds.length==2 && withAdvent.length==3 && twice.length==3,"cooperative helper does not mutate or duplicate original list");
var nativeAdvent:Object=new AdventLogic();nativeAdvent.id=300098;var adventRoute:Object=Resolver.resolveMultiQuestSelectScene(nativeAdvent.toDetail());
check(adventRoute.params[0].tag=="AdventEventQuestSelect" && adventRoute.params[0].params[0]==300098,"actual native Advent toDetail and cooperative resolver retain its original family page");
var nativeRush:Object=new RushLogic();nativeRush.id=700017;var rushRoute:Object=Resolver.resolveSingleQuestSelectScene(new GlobalLogic(),nativeRush.toDetail(),Option.None);
check(rushRoute.params[0].tag=="RushEventLoading" && rushRoute.params[0].params[0].tag=="RushEventTop" && rushRoute.params[0].params[0].params[0]==700017,"actual native Rush toDetail and resolver retain its original family loading/top scene");
for(var wi:int=0;wi<worldIds.length;wi++) {
 var wkey:String="world_story_event:"+worldIds[wi];var e:Object=new EntryEvent();e.id=worldIds[wi];e.banner=new Banner([],[],[]);repo.events["WorldStoryEvent:"+worldIds[wi]]=e;
 var scene:Object=new BoxScene();scene.boxGachaId=boxIds[wi];scene.globalLogic=new GlobalLogic();scene.globalLogic.eventRepository=repo;
 var page:Object=new CarouselPage();scene.carousel={currentIndex:0,getPageAt:function(n:int):Object{return page;}};
 snap2(3100+wi*10,[row2(wkey,{visible:action(false),enter:action(false)})]);scene.buttonClicked(201326592);
 check(scene.flows.length==0 && scene.transitions.length==1 && scene.transitions[0].params[0].tag=="Mission","closed associated World keeps actual original Mission button: "+wkey);
 snap2(3101+wi*10,[row2(wkey,{visible:action(true),enter:action(false)})]);scene.buttonClicked(201326592);
 check(scene.flows.length==0 && scene.transitions.length==2,"World visible-only retains original Mission: "+wkey);
 snap2(3102+wi*10,[row2(wkey,{visible:action(false),enter:action(true)})]);scene.buttonClicked(201326592);
 check(scene.flows.length==0 && scene.transitions.length==3,"World enter-only retains original Mission: "+wkey);
 snap2(3103+wi*10,[row2(wkey,{visible:action(true),enter:action(true)})]);
 if(wi==0){scene.buttonClicked(67108864);check(page.sliderCount==1 && scene.flows.length==0,"other native Box button still performs its original slider action");page.touchable=false;scene.buttonClicked(67108864);check(page.sliderCount==1 && scene.flows.length==0,"native carousel touch guard still blocks the slider action");page.touchable=true;}
 scene.animationState=1;scene.buttonClicked(201326592);
 check(scene.flows.length==0 && scene.transitions.length==3,"actual native animation guard remains before associated route: "+wkey);
 scene.animationState=0;scene.buttonClicked(201326592);
 check(scene.flows.length==1 && scene.flows[0].event===e && scene.flows[0].backKind===Option.None && scene.transitions.length==3,"existing Box task button maps exact associated World through native EventSelectFlow: "+wkey);
 var flow:Object=scene.flows[0];check(flow.gear.runHandler!=null && flow.multi===false,"actual native flow constructor retains its run registration: "+wkey);
 e.unlocked=false;flow.run();check(scene.unlockMessages.length==1 && scene.routerResults.length==0,"native event unlock gate remains: "+wkey);e.unlocked=true;
 e.unlockMovie=Option.Some(new UnlockEvent());scene.globalLogic.moviePlayed=false;flow.run();check(scene.routerResults.length==1 && scene.routerResults[0].nextKind.params[0].tag=="EventTop","native unplayed-unlock-movie redirect remains: "+wkey);scene.globalLogic.moviePlayed=true;e.unlockMovie=Option.None;
 e.autoQuest=Option.Some(new Quest());flow.run();check(flow.gear.children.length==1,"native automatic-story branch remains: "+wkey);e.autoQuest=Option.None;
 flow.run();var route:Object=scene.routerResults[1];
 check(route.nextKind.params[0].tag=="WorldStoryEventQuestSelect" && route.nextKind.params[0].params[0]==worldIds[wi] && route.nextKind.params[0].params[2].tag=="NormalSingle","actual native World family resolver selects original normal-quest page: "+wkey);
 scene.boxGachaId=999999;scene.buttonClicked(201326592);check(scene.flows.length==1 && scene.transitions.length==4,"unrelated Box retains Mission even while World is open: "+wkey);
}
'''
