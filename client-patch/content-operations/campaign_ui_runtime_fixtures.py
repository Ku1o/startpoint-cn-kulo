"""Narrow UI storage for executing the three production campaign consumers.

No helper formatter is mocked. Native getDateText/refresh bodies execute; the
external layout, text sink and calendar formatter are deterministic test ports.
"""
METHODS={
 'pinball.scene.campaign.specialExchange::SpecialExchangeCampaignScene':['getDateText'],
 'pinball.scene.campaign.startDashExchange::StartDashExchangeCampaignView':['refresh'],
 'pinball.scene.campaign.multiSpecialExchange.exchange::MultiSpecialExchangeCampaignExchangeView':['refresh'],
 'pinball.scene.gacha.top.common::GachaSceneViewBase':['setupText'],
}
SCENE_STORAGE={
 'SpecialExchangeCampaignScene':'public var campaignLogic:pinball.common.data.campaign.specialExchange.SpecialExchangeCampaignLogic;public var logic:Object;public function isTicketOnSale():Boolean{return false;}',
 'StartDashExchangeCampaignView':'public var peek:pinball.scene.campaign.startDashExchange.StartDashExchangeCampaignScenePeek;',
 'MultiSpecialExchangeCampaignExchangeView':'public var peek:pinball.scene.campaign.multiSpecialExchange.exchange.MultiSpecialExchangeCampaignExchangeScenePeek;public function loadAndAddBackground(a:Object,b:Object):void{}',
 'GachaSceneViewBase':'public var basePeek:pinball.scene.gacha.top.common.GachaSceneBasePeek;public var periodLayout:pinball.ui.display.UiDisplayObjectContainer=new pinball.ui.display.UiDisplayObjectContainer();public var view:Object;',
}
VIEW_STORAGE='''public var mainUi:pinball.ui.display.UiDisplayObjectContainer=new pinball.ui.display.UiDisplayObjectContainer();public var view:Object;public var safeArea:flash.geom.Rectangle=new flash.geom.Rectangle(0,0,800,600);public var listLayerHeightMax:Number=400;public var listLayerHeightOrigin:Number=400;public var listLayerYOrigin:Number=0;public var gear:Object={addChild:function(a:Object,b:Object):void{}};public var panelList:Object={setListRegion:function(a:Object,b:Object):void{},replaceTouchBeginningDisabledRegions:function(a:Object):void{},resetTouchBeginningDisabledRegions:function():void{}};public var selectPanel:Object={cullingAll:function():void{}};public var buttonGroupView:Object={add:function(a:Object,b:Object):void{}};public var itemDetailButton:haxe.ds.Option=haxe.ds.Option.Some({});'''

def receiver(name):
 """Alias native interface namespaces to the real public getter bodies."""
 body='public var fixtureStatus:haxe.ds.Option=haxe.ds.Option.Some(2);public function get_status():haxe.ds.Option{return fixtureStatus;}'
 if name=='SpecialExchangeCampaignLogic':return body,''
 stem='startDashExchange' if name=='StartDashExchangeCampaignLogic' else 'multiSpecialExchange'
 kind='StartDashExchangeCampaignPeek' if stem=='startDashExchange' else 'MultiSpecialExchangeCampaignPeek'
 body+='public namespace NativeCampaignPeek="pinball.common.data.campaign.'+stem+':'+kind+'";'
 methods={'get_status':'haxe.ds.Option'}
 if stem=='startDashExchange':methods.update(get_periodStartTime='Number',get_periodEndTime='Number')
 else:methods.update(get_campaignStartTime='Number',get_campaignEndTime='Number',get_exchangeStartTime='Number',get_exchangeEndTime='Number')
 for method,returns in methods.items():body+='NativeCampaignPeek function '+method+'():'+returns+'{return Object(this)["'+method+'"]();}'
 if stem=='startDashExchange':body+='public namespace NativeExchangePeek="pinball.common.data.campaign.exchange:ExchangeCampaignPeek";NativeExchangePeek function get_status():haxe.ds.Option{return fixtureStatus;}'
 else:body+='NativeCampaignPeek function get_headerBackgroundImage():String{return "fixture_background";}NativeCampaignPeek function get_type():Object{return {};}'
 return body,' implements pinball.common.data.campaign.'+stem+'.'+kind

def add_support(stubs,put):
 for package,name in [('pinball.common.data.campaign.startDashExchange','StartDashExchangeCampaignPeek'),('pinball.common.data.campaign.multiSpecialExchange','MultiSpecialExchangeCampaignPeek'),('pinball.scene.campaign.startDashExchange','StartDashExchangeCampaignScenePeek'),('pinball.scene.campaign.multiSpecialExchange.exchange','MultiSpecialExchangeCampaignExchangeScenePeek'),('pinball.common.data.gacha','GachaPeekForGachaTopScene'),('pinball.scene.gacha.top.common','GachaSceneBasePeek')]:
  stubs[package.replace('.','/')+'/'+name+'.as']='package '+package+' {public interface '+name+' {}}'
 put('pinball.ui.display.text::UiText','public var text:String="";public function set_text(s:String):String{text=s;return s;}')
 put('pinball.ui.display::UiDisplayObjectContainer','public var x:Number=0;public var y:Number=0;public var width:Number=800;public var height:Number=600;public var visible:Boolean=true;public var mask:Object;public var maxRect:flash.geom.Rectangle=new flash.geom.Rectangle(0,0,800,600);public var dateText:pinball.ui.display.text.UiText=new pinball.ui.display.text.UiText();public function UiDisplayObjectContainer(){this["goto"]=function(i:Object):void{};}public function getContainer(k:String,m:Object=null):UiDisplayObjectContainer{return this;}public function getText(k:String,m:Object=null):pinball.ui.display.text.UiText{return dateText;}public function getGuideRectangle(k:String,m:Object=null):flash.geom.Rectangle{return maxRect;}public function show():void{}public function hide():void{}')
 key='pinball/ui/display/UiDisplayObjectContainer.as';stubs[key]=stubs[key].replace('public class UiDisplayObjectContainer','public dynamic class UiDisplayObjectContainer')
 put('pinball.ui.component.wheel::WheelViewColor','public static var Dark:WheelViewColor=new WheelViewColor();public static var Light:WheelViewColor=new WheelViewColor();')
 put('pinball.ui.component.wheel::WheelView','public function WheelView(a:Object,b:Object){}')
 put('starling.display::Quad','public function Quad(a:Number,b:Number,c:uint=0){}')
 put('pinball.scene.campaign.exchange::ExchangeCampaignItemDetailButtonView','public function ExchangeCampaignItemDetailButtonView(a:Object,b:Object,c:Object){}public function apply(o:Object):void{}')
 put('pinball.scene.campaign.exchange.list::ExchangeCampaignListConfigBuilder','public static var overExchangePeriod:Function=function():Object{return {};};public static var boughtTicket:Function=function():Object{return {};};public static var notBuyTicket:Function=function():Object{return {};};')
 put('pinball.asset::AssetGroupKind','public static var MultiSpecialExchangeCampaignExchange:Object={};')
 put('cn.fixture::StartDashScenePeek','public var campaign:pinball.common.data.campaign.startDashExchange.StartDashExchangeCampaignPeek;public var isOverExchangePeriod:Boolean=false;public function getStartDashExchangeCampaign():pinball.common.data.campaign.startDashExchange.StartDashExchangeCampaignPeek{return campaign;}public namespace NativeScenePeek="pinball.scene.campaign.startDashExchange:StartDashExchangeCampaignScenePeek";NativeScenePeek function getStartDashExchangeCampaign():pinball.common.data.campaign.startDashExchange.StartDashExchangeCampaignPeek{return campaign;}',' implements pinball.scene.campaign.startDashExchange.StartDashExchangeCampaignScenePeek')
 put('cn.fixture::MultiScenePeek','public var campaign:pinball.common.data.campaign.multiSpecialExchange.MultiSpecialExchangeCampaignPeek;public var hasTicket:Boolean=false;public var campaignTime:Boolean=false;public function getMultiSpecialExchangeCampaign():pinball.common.data.campaign.multiSpecialExchange.MultiSpecialExchangeCampaignPeek{return campaign;}public function showCampaignTime():Boolean{return campaignTime;}public function isDrew():Boolean{return true;}public function showTabs():Boolean{return false;}public namespace NativeScenePeek="pinball.scene.campaign.multiSpecialExchange.exchange:MultiSpecialExchangeCampaignExchangeScenePeek";NativeScenePeek function getMultiSpecialExchangeCampaign():pinball.common.data.campaign.multiSpecialExchange.MultiSpecialExchangeCampaignPeek{return campaign;}NativeScenePeek function showCampaignTime():Boolean{return campaignTime;}NativeScenePeek function isDrew():Boolean{return true;}NativeScenePeek function showTabs():Boolean{return false;}',' implements pinball.scene.campaign.multiSpecialExchange.exchange.MultiSpecialExchangeCampaignExchangeScenePeek')
 put('cn.fixture::GachaBasePeek','public var gacha:pinball.common.data.gacha.GachaLogic;public function getGacha():pinball.common.data.gacha.GachaPeekForGachaTopScene{return gacha;}public function getGachaStartTime():Number{return gacha.get_startTime().params[0];}public function getGachaEndTime():Number{return gacha.get_endTime().params[0];}public namespace NativeGachaHolder="pinball.scene.gacha:GachaHolder";NativeGachaHolder function getGacha():pinball.common.data.gacha.GachaPeekForGachaTopScene{return gacha;}public namespace NativeGachaBasePeek="pinball.scene.gacha.top.common:GachaSceneBasePeek";NativeGachaBasePeek function getGachaStartTime():Number{return Object(this)["getGachaStartTime"]();}NativeGachaBasePeek function getGachaEndTime():Number{return Object(this)["getGachaEndTime"]();}',' implements pinball.scene.gacha.top.common.GachaSceneBasePeek')
 key='pinball/common/time/_AppTime/AppTime_Impl_.as'
 stubs[key]=stubs[key].replace('public class AppTime_Impl_ {','public class AppTime_Impl_ {public static var formattedDates:Array=[];public static function toStandardDateFormatString(v:Number):String{formattedDates.push(v);return "DATE("+v+")";}')

BODY=r'''
if(!nativeBaseline) {
 var campaignDateOld:Boolean=EXPECT_CAMPAIGN_DATE_REGRESSIONS;
 var calendar:Class=getDefinitionByName("pinball.common.time._AppTime.AppTime_Impl_") as Class;
 var uiAsset:Object={getUiStringWithContext:function(k:String,c:Object):String{return k+":"+JSON.stringify(c);}};
 var dateCases:Array=[{key:"special_exchange_campaign",logic:"specialExchange.SpecialExchangeCampaignLogic",consumer:"pinball.scene.campaign.specialExchange.SpecialExchangeCampaignScene"},{key:"start_dash_exchange_campaign",logic:"startDashExchange.StartDashExchangeCampaignLogic",consumer:"pinball.scene.campaign.startDashExchange.StartDashExchangeCampaignView"},{key:"multi_special_exchange_campaign",logic:"multiSpecialExchange.MultiSpecialExchangeCampaignLogic",consumer:"pinball.scene.campaign.multiSpecialExchange.exchange.MultiSpecialExchangeCampaignExchangeView"}];
 var uiRevision:int=300;
 for each(var dateCase:Object in dateCases) {
  var dateLogic:Object=make("pinball.common.data.campaign."+dateCase.logic);dateLogic.id=8;dateLogic.values={campaign_start_time:0,campaign_end_time:50000,exchange_start_time:0,exchange_end_time:500};
  if("startDashExchangeCampaignData" in dateLogic)dateLogic.startDashExchangeCampaignData=Option.Some({period_start_time:0,period_end_time:0.5});
  var consumer:Object=make(dateCase.consumer),datePeek:Object;
  if(dateCase.key=="special_exchange_campaign"){consumer.campaignLogic=dateLogic;consumer.logic={asset:uiAsset};}
  else {datePeek=make(dateCase.key=="start_dash_exchange_campaign"?"cn.fixture.StartDashScenePeek":"cn.fixture.MultiScenePeek");datePeek.campaign=dateLogic;consumer.peek=datePeek;consumer.view={asset:uiAsset};}
  snap2(uiRevision++,[row2(dateCase.key+":8",{visible:action(true),enter:action(false),exchange:action(true)})]);
  calendar.formattedDates=[];var rendered:String;
  if(dateCase.key=="special_exchange_campaign")rendered=consumer.getDateText();else{consumer.refresh();rendered=consumer.mainUi.dateText.text;}
  nativeObservations.push({key:dateCase.key,rendered:rendered,calendarInputs:calendar.formattedDates.concat(),expectedOldRegression:campaignDateOld});
  check((calendar.formattedDates.indexOf(8640000000000000)>=0)==campaignDateOld,"actual native campaign date consumer does not calendar-format numeric open bound: "+dateCase.key);
  check(campaignDateOld ? rendered.indexOf("8640000000000000")>=0 : rendered.indexOf("仅可兑换")>=0,"actual native campaign date output distinguishes retained old sentinel regression from operator label: "+dateCase.key);
  if(dateCase.key=="start_dash_exchange_campaign")check(dateLogic.get_buyEndTime()==(campaignDateOld?8640000000000000:500),"actual native StartDash buy deadline retains personal data instead of inheriting exchange open bound");
  snap2(uiRevision++,[row2(dateCase.key+":8",{visible:action(true),enter:action(false),exchange:action(true,61000)})]);calendar.formattedDates=[];
  if(dateCase.key=="special_exchange_campaign")rendered=consumer.getDateText();else{consumer.refresh();rendered=consumer.mainUi.dateText.text;}
  check(calendar.formattedDates.indexOf(61000)>=0 && rendered.indexOf("DATE(61000)")>=0,"actual native campaign finite exchange date keeps original calendar formatter: "+dateCase.key);
  if(!campaignDateOld){snap2(uiRevision++,[row2(dateCase.key+":8",{visible:action(true),enter:action(false),exchange:action(false)})]);calendar.formattedDates=[];if(dateCase.key=="special_exchange_campaign")rendered=consumer.getDateText();else{consumer.refresh();rendered=consumer.mainUi.dateText.text;}check(rendered=="已关闭" && calendar.formattedDates.length==0,"actual native campaign closed date avoids formatting zero as a calendar date: "+dateCase.key);}
  snap2(uiRevision++,[row2(dateCase.key+":8",{visible:action(true),enter:action(false),exchange:action(true)})]);dateLogic.fixtureStatus=Option.Some(1);if(dateCase.key=="multi_special_exchange_campaign")datePeek.campaignTime=true;calendar.formattedDates=[];
  if(dateCase.key=="special_exchange_campaign")rendered=consumer.getDateText();else{consumer.refresh();rendered=consumer.mainUi.dateText.text;}
  nativeObservations.push({key:dateCase.key,phase:"sale",rendered:rendered,calendarInputs:calendar.formattedDates.concat(),expectedOldRegression:campaignDateOld});
  check(dateCase.key=="start_dash_exchange_campaign" && campaignDateOld ? calendar.formattedDates.indexOf(8640000000000000)>=0 : calendar.formattedDates.indexOf(dateCase.key=="start_dash_exchange_campaign"?500:50000)>=0 && calendar.formattedDates.indexOf(8640000000000000)<0,"actual native campaign sale dates preserve purchase qualification deadline: "+dateCase.key);
 }
 var gachaView:Object=make("pinball.scene.gacha.top.common.GachaSceneViewBase"),gachaBase:Object=make("cn.fixture.GachaBasePeek");gc.values.show_period=true;gachaBase.gacha=gc;gachaView.basePeek=gachaBase;gachaView.view={asset:uiAsset};
 snap2(330,[row2("gacha:990001",{visible:action(true),enter:action(true)})]);calendar.formattedDates=[];gachaView.setupText();rendered=gachaView.periodLayout.dateText.text;
 nativeObservations.push({key:"gacha:990001",rendered:rendered,calendarInputs:calendar.formattedDates.concat(),expectedOldRegression:campaignDateOld});
 check((calendar.formattedDates.indexOf(8640000000000000)>=0)==campaignDateOld,"actual native gacha setupText does not calendar-format permanent concrete end bound");
 check(campaignDateOld?rendered.indexOf("8640000000000000")>=0:rendered.indexOf("常驻开放")>=0,"actual native gacha setupText renders permanent operation label");
 if(!campaignDateOld){snap2(331,[row2("gacha:990001",{visible:action(true,61000),enter:action(true,61000)})]);calendar.formattedDates=[];gachaView.setupText();check(gachaView.periodLayout.dateText.text.indexOf("剩余")>=0 && calendar.formattedDates.length==0,"actual native controlled gacha finite date uses operation deadline");snap2(332,[row2("gacha:990001",{visible:action(false),enter:action(false)})]);gachaView.setupText();check(gachaView.periodLayout.dateText.text=="已关闭","actual native closed gacha date does not show epoch zero");}
 gc.values.show_period=false;calendar.formattedDates=[];gachaView.setupText();check(!gachaView.periodLayout.visible && calendar.formattedDates.length==0,"actual native gacha showPeriod false keeps original hidden date behavior");
 var personalUiRevision:int=334;
 for each(var uiPersonalKind:String in ["stars","comeback"]){var uiPersonal:Object=makePool(uiPersonalKind=="stars"?80000:700000,false,uiPersonalKind);uiPersonal.values.show_period=true;uiPersonal[uiPersonalKind=="stars"?"starsGachaPeriod":"comebackGachaPeriod"]=Option.Some(new TimeRange(900,Option.Some(1100)));gachaBase.gacha=uiPersonal;snap2(personalUiRevision++,[row2("gacha:"+uiPersonal.id,{visible:action(true),enter:action(true)})]);calendar.formattedDates=[];gachaView.setupText();check(calendar.formattedDates.indexOf(1100)>=0 && calendar.formattedDates.indexOf(8640000000000000)<0 && gachaView.periodLayout.dateText.text.indexOf("DATE(1100)")>=0,"actual native personal gacha date keeps original personal window: "+uiPersonalKind);}
}
'''
