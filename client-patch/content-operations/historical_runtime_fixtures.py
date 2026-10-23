"""Execute catalog IDs through instruction/CFG-exact production predicates.

The catalog supplies identities, not synthetic player entitlements or UI routes.
Storage ports close external dependencies; every tested predicate is imported
from the selected production SWF by offline_runtime_test.py.
"""
import json
import native_runtime_fixtures as native


def prepare(stubs, cases, abc, builder):
    stubs = dict(stubs)
    additions = {
        'pinball.common.data.event::EventFolderLogic': ['getViewableEvents'],
        'pinball.common.data.event::SideStoryEventListLogic': ['getAllEventIds', 'getViewableEvents'],
        'pinball.common.data.gacha::GachaLogic': [
            'isAvailable', 'get_pageKind', 'get_onceTicketItemId',
            'get_tenTimesTicketItemId', 'get_crazyTenTimesTicketItemId'],
        'pinball.common.data.boxGacha::BoxGachaLogic': ['isWithinPeriod', 'getPeriod'],
        'pinball.common.data.mission.activeMission::ActiveMissionEventLogic': ['isWithinPeriod', 'getPeriod'],
        'pinball.common.data.collectItem::CollectItemEventLogic': ['isWithinPeriod', 'getPeriod'],
        'pinball.common.data.mission.repository::PassCardEventRepository': ['getCurrentPassId', 'getCurrentPassEvent'],
        'pinball.common.data.campaign.specialExchange::SpecialExchangeCampaignLogic': ['isWithinExchangePeriod', 'isWithinCampaignPeriod'],
        'pinball.common.data.campaign.multiSpecialExchange::MultiSpecialExchangeCampaignLogic': ['isWithinExchangePeriod', 'isWithinCampaignPeriod'],
        'pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic': ['isWithinPeriod', 'isWithinCampaignPeriod'],
    }
    for qn, methods in additions.items():
        native.NATIVE_METHODS.setdefault(qn, []).extend(methods)
    native.STORAGE.update({
        'pinball.common.data.event::EventFolderLogic': 'public var folderEvents:Array=[];',
        'pinball.common.data.event::SideStoryEventListLogic': 'public var allEventsCache:Array=[];public var questRepository:Object;',
        'pinball.common.data.boxGacha::BoxGachaLogic': 'public var id:int=1;public var startTime:Number=0;public var endTime:haxe.ds.Option=haxe.ds.Option.Some(500);',
        'pinball.common.data.mission.repository::PassCardEventRepository': 'public var logicAssets:Object;public var globalLogic:Object;',
    })
    stubs['pinball/common/data/gacha/GachaPageKind.as'] = 'package pinball.common.data.gacha {public class GachaPageKind {public var index:int=0;}}'
    stubs['pinball/master/generated/PassCardEventValues.as'] = 'package pinball.master.generated {public class PassCardEventValues {}}'
    stubs['pinball/common/data/quest/event/common/EventLogic.as'] = 'package pinball.common.data.quest.event.common {public interface EventLogic {}}'
    # Production EventLogic consumers use the interface namespace. The sealed
    # fixture base exposes the same names, forwarding to imported public bodies.
    key = 'pinball/common/data/quest/event/common/EventLogicBase.as'
    text = stubs[key].replace('public class EventLogicBase {',
        'public class EventLogicBase implements EventLogic {'
        'public function EventLogicBase(v:Object=null,a:Object=null,r:Object=null,g:Object=null){if(v!=null)commonValues=v;}'
        'public function getFlashFrameReference():Option{return Option.Some(12);}'
        'public namespace NativeBrowsable="pinball.common.data.quest.event.common:EventLogic";'
        'NativeBrowsable function isWithinBrowsablePeriod(t:Number):Boolean{return Object(this)["isWithinBrowsablePeriod"](t);}')
    text = text.replace('public function get_playableEndTime()',
        'public function isWithinBrowsablePeriod(t:Number):Boolean{return false;}'
        'public function isWithinExchangeablePeriod(t:Number):Boolean{return false;}'
        'public function getBrowsableTimeRange():TimeRange{return null;}'
        'public function getExchangeableTimeRange():TimeRange{return null;}'
        'public function getBrowsableEndTime():Option{return Option.None;}'
        'public function get_exchangeableEndTime():Option{return Option.None;}'
        'public function get_playableEndTime()')
    stubs[key] = text
    # Native.prepare normally declares this class itself; preserve explicit
    # player qualification ports after its declaration below.
    fixture, labels, includes = native.prepare(stubs, cases, abc, builder)
    includes.append('pinball.master.generated.PassCardEventValues')
    source = builder.view(abc)
    for method in ['isWithinBrowsablePeriod', 'isWithinExchangeablePeriod',
                   'getBrowsableTimeRange', 'getExchangeableTimeRange',
                   'getBrowsableEndTime', 'get_exchangeableEndTime']:
        matches = [label for label in source.by_label
                   if label.startswith('pinball.common.data.quest.event.common::EventLogicBase/')
                   and label.rsplit('/', 1)[-1].split('|')[0] == method]
        assert len(matches) == 1, (method, matches)
        labels.extend(matches)
    player = 'pinball/common/data/player/PlayerLogic.as'
    fixture[player] = fixture[player].replace('public class PlayerLogic {',
        'public class PlayerLogic {public var tickets:Object={};public var accountTen:Boolean=false;'
        'public function hasItem(id:int):Boolean{return tickets.hasOwnProperty(id)&&tickets[id]===true;}'
        'public function getGachaDrawableTenTimesPerAccount(id:int):Boolean{return accountTen;}')
    return fixture, labels, includes


def body(catalog, fixture_path):
    rows = [dict(key=r['key'], type=r['type'], id=r['id']) for r in catalog['rows']
            if r['type'] not in ('mission_regular', 'mission_daily', 'mission_event',
                                 'general_shop', 'treasure_shop', 'star_grain_shop',
                                 'boss_coin_shop', 'event_item_shop')]
    if len(rows) != 1020:
        raise ValueError('Expected the audited 1020 parent identities; review changed catalog')
    fixture_path.write_text(json.dumps(rows, separators=(',', ':')), encoding='utf-8')
    return BODY.replace('HISTORICAL_PATH', json.dumps(str(fixture_path.resolve())))


BODY = r'''
var historicalFile:File=new File(HISTORICAL_PATH),historicalStream:FileStream=new FileStream();historicalStream.open(historicalFile,FileMode.READ);
var historicalRows:Array=JSON.parse(historicalStream.readUTFBytes(historicalStream.bytesAvailable)) as Array;historicalStream.close();
var make:Function=function(n:String):Object {var c:Class=getDefinitionByName(n.replace("::",".")) as Class;return new c();};
var bootClass:Class=getDefinitionByName("flash.Boot") as Class;bootClass.skip_constructor=true;
var cases:Array=NATIVE_EVENT_CASES,eventByType:Object={};for each(var nc:Object in cases)eventByType[nc.key]=nc;
var allRows:Array=[],allCatalog:Array=[],instances:Array=[],nativeEvents:Array=[],nativeIds:Array=[];
var player:Object=make("pinball.common.data.player.PlayerLogic");
var ordinal:int=1;
for each(var identity:Object in historicalRows){
 var qkey:String="3:"+(100000+ordinal++),row:Object=row2(identity.key,{visible:action(true,null,[qkey]),enter:action(true,null,[qkey]),exchange:action(true),claim:action(true)});
 // A pass is selected independently below because its native return contract
 // is one Option, not a list. Other families may open simultaneously.
 if(identity.type=="pass_card_event")row.actions.visible.enabled=false;
 allRows.push(row);allCatalog.push({key:identity.key,quest_keys:[qkey]});
 var instance:Object=null;
 if(eventByType.hasOwnProperty(identity.type)){
  nc=eventByType[identity.type];instance=make(nc.name);if("id" in instance)instance.id=identity.id;else instance.eventId=identity.id;
  instance.commonValues={start_time:0,playable_end_time:Option.Some(500),exchangeable_end_time:Option.Some(500)};
  nativeEvents.push(instance);nativeIds.push({values:{event:instance.getEventId()}});
 }else if(identity.type=="gacha"){
  instance=make("pinball.common.data.gacha.GachaLogic");instance.id=identity.id;
  var page:Object=make("pinball.common.data.gacha.GachaPageKind");page.index=0;
  instance.values={is_comeback:false,is_stars_gacha:false,page_kind:page,once_ticket_item_id:Option.Some(7),ten_times_ticket_item_id:Option.Some(8),crazy_ten_times_ticket_item_id:Option.Some(9)};
  instance.period=new TimeRange(0,Option.Some(500));
 }else if(identity.type=="box_gacha"){
  instance=make("pinball.common.data.boxGacha.BoxGachaLogic");instance.id=identity.id;
 }else if(identity.type=="active_mission_event"){
  instance=make("pinball.common.data.mission.activeMission.ActiveMissionEventLogic");instance.id=identity.id;instance.values={start_time:0,end_time:Option.Some(500),playable_end_time:500};
 }else if(identity.type=="collect_item_event"){
  instance=make("pinball.common.data.collectItem.CollectItemEventLogic");instance.id=identity.id;var kind:Object=make("pinball.common.data.mission.collectItemEvent.CollectItemEventKind");kind.index=1;
  instance.values={kind:kind,start_time:0,end_time:500,exchangeable_end_time:Option.Some(500)};instance.exchangablePeriod=new TimeRange(0,Option.Some(500));
 }else if(identity.type.indexOf("_campaign")>=0){
  var campaignTypes:Object={special_exchange_campaign:"specialExchange.SpecialExchangeCampaignLogic",multi_special_exchange_campaign:"multiSpecialExchange.MultiSpecialExchangeCampaignLogic",start_dash_exchange_campaign:"startDashExchange.StartDashExchangeCampaignLogic"};
  instance=make("pinball.common.data.campaign."+campaignTypes[identity.type]);instance.id=identity.id;
  instance.values={campaign_start_time:0,campaign_end_time:500,exchange_start_time:0,exchange_end_time:500};
  if("startDashExchangeCampaignData" in instance)instance.startDashExchangeCampaignData=Option.Some({period_start_time:0,period_end_time:0.5});
 }
 instances.push({identity:identity,value:instance,qkey:qkey});
}
snap2(10000,allRows,allCatalog);
var list:Object=make("pinball.common.data.event.EventListLogic");list.eventListValuesArray=nativeIds;
check(list.getAllEventIds().length==nativeIds.length,"actual native list accepts every event identity already owned by its table");
var folder:Object=make("pinball.common.data.event.EventFolderLogic");folder.folderEvents=nativeEvents;
check(folder.getViewableEvents(1000).length==nativeEvents.length,"actual native folder consumer accepts simultaneous historical events");
var side:Object=make("pinball.common.data.event.SideStoryEventListLogic");side.allEventsCache=[];var lookup:Object={};
for each(var ev:Object in nativeEvents){var eid:Object=ev.getEventId();side.allEventsCache.push(eid);lookup[eid.tag+":"+eid.params[0]]=ev;}
side.questRepository={getEvent:function(id:Object):Object{return lookup[id.tag+":"+id.params[0]];}};
check(side.getViewableEvents(1000).length==nativeEvents.length,"actual native side-story consumer accepts simultaneous owned historical events");
for each(var item:Object in instances){
 identity=item.identity;instance=item.value;
 if(instance==null)continue;
 if(eventByType.hasOwnProperty(identity.type)){
  check(ContentOperationsState.towerKey(instance)==identity.key && instance.isWithinPeriod(1000)&&instance.isWithinBrowsablePeriod(1000),"actual native event identity/participation/browse "+identity.key);
  nc=eventByType[identity.type];var quest:Object=make("pinball.common.data.quest.fixture."+nc.name.split("::")[1].replace("Logic","ScopedQuest"));quest.id=int(item.qkey.split(":")[1]);quest[nc.field]=instance;
  check(quest.isWithinPeriod(1000)&&quest.isWithinViewablePeriod(1000),"actual native quest scope "+identity.key);
  quest.id+=1000000;check(!quest.isWithinPeriod(1000)&&!quest.isWithinViewablePeriod(1000),"actual native sibling scope denied "+identity.key);
 }else if(identity.type=="gacha")check(instance.isWithinPeriod(player,1000,false)&&instance.isAvailable(player,1000,false),"actual native ordinary eligibility "+identity.key);
 else if(identity.type.indexOf("_campaign")>=0)check(!instance.isOverExchangePeriod(1000)&&(identity.type=="start_dash_exchange_campaign"?instance.isWithinPeriod(1000):instance.isWithinExchangePeriod(1000)),"actual native campaign exchange period "+identity.key);
 else check(instance.isWithinPeriod(1000),"actual native parent period "+identity.key);
}
// One changed ID cannot leak through an unrelated row's state or scope.
for each(row in allRows)for each(var setting:Object in row.actions)setting.enabled=false;
snap2(10001,allRows,allCatalog);
check(list.getAllEventIds().length==0&&folder.getViewableEvents(1000).length==0&&side.getViewableEvents(1000).length==0,"actual native lists remove all closed historical events");
for each(item in instances){identity=item.identity;instance=item.value;if(instance==null)continue;
 if(identity.type=="gacha")check(!instance.isWithinPeriod(player,1000,false)&&!instance.isAvailable(player,1000,false),"actual native pool closure "+identity.key);
 else if(identity.type.indexOf("_campaign")>=0)check(instance.isOverExchangePeriod(1000)&&!(identity.type=="start_dash_exchange_campaign"?instance.isWithinPeriod(1000):instance.isWithinExchangePeriod(1000)),"actual native campaign exchange closure "+identity.key);
 else check(!instance.isWithinPeriod(1000),"actual native parent closure "+identity.key);
}
// Execute native gacha's complete eligibility switch, including unsupported
// original page kinds. The helper may override calendar, never ticket rights.
var pool:Object=make("pinball.common.data.gacha.GachaLogic");pool.id=990099;pool.period=new TimeRange(0,Option.Some(500));
page=make("pinball.common.data.gacha.GachaPageKind");pool.values={is_comeback:false,is_stars_gacha:false,page_kind:page,once_ticket_item_id:Option.Some(7),ten_times_ticket_item_id:Option.Some(8),crazy_ten_times_ticket_item_id:Option.Some(9)};
snap2(10002,[row2("gacha:990099",{visible:action(true),enter:action(true)})]);
var eligibility:Function=function(g:Object,p:Object):Object{try{return {available:g.isAvailable(p,1000,false),code:0};}catch(nativeError:Error){return {available:false,code:nativeError.errorID};}};
for(var pk:int=0;pk<=8;pk++){
 page.index=pk;player.tickets={};player.accountTen=false;var outcome:Object=eligibility(pool,player);
 check(pk==6||pk==7?outcome.code==9100:outcome.code==0&&outcome.available==(pk==0||pk==8),"actual native gacha no-right eligibility pageKind "+pk);
 if(pk==1){player.accountTen=true;check(pool.isAvailable(player,1000,false),"actual native account ten-draw entitlement retained");}
 if(pk>=2&&pk<=5){player.tickets[pk==4?8:pk==5?9:7]=true;check(pool.isAvailable(player,1000,false),"actual native ticket entitlement retained pageKind "+pk);}
}
var passIds:Array=[];for each(identity in historicalRows)if(identity.type=="pass_card_event")passIds.push(identity.id);
var passData:Object={};for each(var pid:int in passIds)passData[pid]={id:pid,start_time:0,end_time:500};
var passMap:Object={keys:function():Array{return passIds;},exists:function(id:int):Boolean{return passData.hasOwnProperty(id);},"get":function(id:int):Object{return passData[id];}};
var passRepository:Object=make("pinball.common.data.mission.repository.PassCardEventRepository");passRepository.globalLogic={getTime:function():Number{return 1000;}};passRepository.logicAssets={getMasterTable:function(c:Class):Object{return {get_data:function():Object{return passMap;}};}};
var passRevision:int=10003;for each(pid in passIds){snap2(passRevision++,[row2("pass_card_event:"+pid,{visible:action(true),enter:action(true)})]);check(passRepository.getCurrentPassId().params[0]==pid&&passRepository.getCurrentPassEvent().params[0]===passData[pid],"actual native single-pass selection "+pid);}
snap2(passRevision++,[row2("pass_card_event:"+passIds[0],{visible:action(true)}),row2("pass_card_event:"+passIds[1],{visible:action(true)})]);
check(passRepository.getCurrentPassId()===Option.None&&passRepository.getCurrentPassEvent()===Option.None,"actual native single-pass contract rejects simultaneous visible periods");
bootClass.skip_constructor=false;
'''
