"""Execute selected production PlayerHistory consumers, plus mature period suite.

UI storage and asset loading are bounded fixtures; this is native method proof,
not a complete page, GPU, sharing platform, or device acceptance.
"""
import json, hashlib, sys, re
from pathlib import Path
import period_runtime_fixtures as period
import native_runtime_fixtures as native
import assistant_runtime_fixtures as assistant
import offline_runtime_test as runtime
import build_player_history as profile

DRAW = ['start_game','total_login','clear_chapter_1_to_6','clear_chapter_7_to_12',
 'complete_mana_board_2','lv_100_character','bond_token','get_100_characters','player_rank_100',
 'complete_regular_mission','complete_event_mission','multi_first_place','multi_host_guest',
 'owned_equipment','complete_equipment','complete_equipment_enhancement','guild_girl_equipment_enhancement',
 'defeat_expert_single_boss','rush_endless_battle_record','haniwa_carnival_record','solo_time_attack_degree',
 'score_attack_border','clear_expert_single_quest','complete_side_story','clear_tower_dungeon_floor',
 'total_mana_paid','encyclopedia_read']
KINDS = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,26,17,18,19,20,21,22,23,24,25]
EXTRA=[]

def prepare(stubs,cases,abc,builder):
    stubs,labels,includes=period.prepare(stubs,cases,abc,builder)
    source=builder.view(abc)
    def put(owner,body,base=''):
        ns,name=owner.split('::');stubs[ns.replace('.','/')+'/'+name+'.as']='package '+ns+' {public class '+name+base+' {'+body+'}}'
        includes.append(ns+'.'+name)
    def actual(owner,names,storage='',base=''):
        body=storage
        for method in names:
            label=owner+'/'+method+'|1';index,=source.by_label[label];m=abc.methods[abc.bodies[index][0]]
            typ=lambda i:abc.mn_name(i).replace('::','.') if i else '*'
            ret=typ(m[0]);args=','.join('p'+str(i)+':'+typ(t)+'=null' for i,t in enumerate(m[1]))
            val='' if ret=='void' else 'return false;' if ret=='Boolean' else 'return 0;' if ret in ['int','uint','Number'] else 'return null;'
            body+='public function '+method+'('+args+'):'+ret+'{'+val+'}'
            labels.append(label)
        put(owner,body,base)
    # Caller/storage fixtures have the namespaces used by actual sealed receivers.
    put('pinball.common.data.player_history::PlayerHistoryLogic',
        'public var id:int=1;public var values:Object;public function isWithinPeriod(t:Number):Boolean{return false;}public function getPeriod():pinball.common.time.TimeRange{return null;}public function get_startTime():Number{return 0;}public function get_endTime():Number{return 0;}')
    for name in ['isWithinPeriod','getPeriod','get_startTime','get_endTime']:
        labels.append('pinball.common.data.player_history::PlayerHistoryLogic/'+name+'|1')
    actual('pinball.scene.playerHistory.card::PlayerHistoryCardTopicLogic',['getDateValues','getValues','getKind'],
        'public var sourceKind:Object;')
    put('pinball.scene.playerHistory.card::PlayerHistoryCardTopicKind','public static var PlayerInfo:PlayerHistoryCardTopicKind=new PlayerHistoryCardTopicKind();public static function Aggregation(v:Object):PlayerHistoryCardTopicKind{return new PlayerHistoryCardTopicKind();}')
    put('pinball.common.data.player_history::PlayerHistoryAggregationKind','public var index:int=0;public var params:Array=[];')
    # SourceKind is concrete in native getValues/getKind.
    put('pinball.scene.playerHistory.card::PlayerHistoryCardTopicSourceKind','public var index:int=1;public var params:Array=[];')
    key='pinball/scene/playerHistory/card/PlayerHistoryCardTopicLogic.as'
    stubs[key]=stubs[key].replace('sourceKind:Object','sourceKind:PlayerHistoryCardTopicSourceKind')
    renderer_storage='''public var peek:Object;public var view:Object;public var globalLogic:Object;public var dateFormat:String="%Y/%m/%d";
public var flaHolder:Object={gear:{addChild:function(a:Object,b:Object=null):void{}}};
public function showImage(a:Object,b:String,c:Boolean):void{}public function showCharacters(a:Array,b:Array,c:Boolean):void{}
public function showDegree(a:Object,b:int):void{}public function showMerchant(a:Object):void{}
'''
    actual('pinball.scene.playerHistory.card::PlayerHistoryCardTopicView',DRAW+['getDateString','showTexts'],renderer_storage)
    actual('pinball.scene.playerHistory.card::PlayerHistoryCardLogic',['createShareText'],'public var id:int=1;public var logic:Object;')
    put('pinball.context.share::SharedItem','public var text:String;public static function Text(s:String):SharedItem{var v:SharedItem=new SharedItem();v.text=s;return v;}')
    put('cn.fixture::ProfilePeriodProbe','public var periodContent:pinball.ui.display.UiDisplayObjectContainer=new pinball.ui.display.UiDisplayObjectContainer();public var view:Object;public function run(provider:Object):void{}')
    put('pinball.common.time._JapanStandardTimeString::JapanStandardTimeString_Impl_',
        'public static function toAppTime(v:String):Number{return Date.parse(v.replace(/-/g,"/")+" GMT+0900");}')
    put('cn.fixture::ProfileAsset','public function getUiString(k:String):String{return k;}public function getUiStringWithContext(k:String,c:Object):String{return k+":"+JSON.stringify(c);}')
    put('pinball.common.math._FloatInt::FloatInt_Impl_','public static function fromInt(v:int):Number{return v;}')
    put('pinball.common.tools::StringExtended','public static function commaSeparate(v:Number):String{return String(v);}')
    put('starling.text::TextFieldAutoSize','public static const HORIZONTAL:String="horizontal";')
    put('pinball.common.tools._FunctionTools::BindImpl2_1','public var fn:Function;public var receiver:Object;public function BindImpl2_1(f:Function,r:Object){fn=f;receiver=r;}public function execute(v:Object):void{fn(receiver,v);}')
    put('pinball.ui.display.image::UiImage','public var visible:Boolean=true;public var x:Number=0;public var width:Number=100;')
    put('pinball.ui.component.equipment::EquipmentAwakeningLevelView','public function EquipmentAwakeningLevelView(a:Object,b:int,c:int){}')
    # Native text formatting is retained; text/containers only store observed writes.
    key='pinball/ui/display/text/UiText.as'
    stubs[key]=stubs[key].replace('public var text:String="";','public var width:Number=80;public var text:String="";public function enableHtmlText():void{}')
    put('pinball.ui.display::UiDisplayObjectContainer','''public var profileMode:Boolean=false;public var x:Number=0;public var y:Number=0;public var visible:Boolean=true;public var frame:int=1;public var texts:Object={};public var groups:Object={};
public function UiDisplayObjectContainer(){this["goto"]=function(n:int):void{frame=n;};}
public function getText(k:String,m:Object=null):pinball.ui.display.text.UiText{if(!profileMode&&(k=="label"||k=="date_text"))return dateText;if(!texts[k]){texts[k]=new pinball.ui.display.text.UiText();if(!profileMode){texts[k].rawTextField.width=595;texts[k].rawTextField.height=40;texts[k].rawTextField.format.size=26;}}return texts[k];}
public function getTexts(k:String):Array{if(!groups[k]){groups[k]=[];for(var i:int=0;i<6;i++)groups[k].push(getText(k+i));}return groups[k];}
public function getContainer(k:String,m:Object=null):UiDisplayObjectContainer{return this;}
public function getContainers(k:String):Array{var a:Array=[];for(var i:int=0;i<6;i++)a.push(new UiDisplayObjectContainer());return a;}
public function getImage(k:String,m:Object=null):pinball.ui.display.image.UiImage{return new pinball.ui.display.image.UiImage();}
public function getGuideRectangle(k:String,m:Object=null):flash.geom.Rectangle{return new flash.geom.Rectangle(0,0,800,600);}
public function show():void{}public function hide():void{}
public var dateText:pinball.ui.display.text.UiText=new pinball.ui.display.text.UiText();public var width:Number=800;public var height:Number=600;public var mask:Object;
''')
    key='pinball/ui/display/UiDisplayObjectContainer.as';stubs[key]=stubs[key].replace('public class UiDisplayObjectContainer','public dynamic class UiDisplayObjectContainer extends starling.display.Sprite')
    stubs['pinball/common/data/character/GeneralCharacterPeek.as']='package pinball.common.data.character {public interface GeneralCharacterPeek {function get_name():String;}}'
    put('cn.fixture::ProfileCharacter','public function get_name():String{return "Known character";}',' implements pinball.common.data.character.GeneralCharacterPeek')
    put('cn.fixture::ProfileGlobal','public namespace N="pinball.context.global:GlobalLogicForSection";N function getGeneralCharacter(id:int):pinball.common.data.character.GeneralCharacterPeek{return new ProfileCharacter();}')
    ns='pinball.scene.playerHistory.card:PlayerHistoryCardTopicPeek'
    methods='''public var topic:pinball.scene.playerHistory.card.PlayerHistoryCardTopicLogic;public var ints:Array;public var chars:Array;public var equips:Array;public var bosses:Array;
public namespace N="'''+ns+'''";
N function getDateValues():Array{return topic.getDateValues();}N function getIntValues():Array{return ints;}
N function getCharacterIdValues():Array{return chars;}N function getEquipmentIdValues():Array{return equips;}N function getBossIdValues():Array{return bosses;}
N function getRushEventStartTime(n:int):String{return "2025-07-17 12:00:00";}N function getCarnivalEventStartTime(n:int):String{return "2025-07-17 12:00:00";}
N function getChapterImage(n:int):String{return "known_chapter";}N function getCompleteManaboardDegree(n:int):haxe.ds.Option{return haxe.ds.Option.None;}
N function getEquipmentData(n:int,lv:int):Object{return {thumbnail:"known_equipment",maxLevel:5};}N function getBossData(n:int):Object{return {thumbnail:"known_boss",name:"Known boss"};}
'''
    put('cn.fixture::ProfilePeek',methods)
    # The exact profile helper is imported after compile, just like old full helper.
    stubs['cn/profile/PlayerHistoryState.as']=profile.HELPER
    includes.append('cn.profile.PlayerHistoryState')
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

_prefixes=period.import_prefixes
def imports(builder,target,main,receipts):
    result=_prefixes(builder,target,main,receipts)
    path=Path(sys.argv[sys.argv.index('--production-work')+1])/'player-history-helper.abc'
    helper=builder.p.abcfmt.ABC(path.read_bytes());source=builder.view(helper);graft=builder.p.Importer(target,source)
    for label,ids in source.by_label.items():
        ti,=target.by_label[label];di,=ids;old=target.a.bodies[ti]
        target.a.bodies[ti]=graft.body(di,old[0])
        assert target.normalized(ti)==source.normalized(di),label
        receipts.append({'label':label,'sourceCodeSha256':hashlib.sha256(helper.bodies[di][5]).hexdigest(),'normalizedInstructionsCfgExact':True,'profileHelper':True})
    # The final original UI setter fragment is run without claiming the entire
    # resource-dependent profile page was executed.
    import copy
    donor=copy.deepcopy(main);dv=builder.view(donor)
    label='pinball.scene.playerProfile::PlayerProfileView/drawPlayerInfoForPlayerHistory|1'
    di,=dv.by_label[label];body=donor.bodies[di];rows=builder.p.asm.decode(body[5]);start=257
    assert rows[start].op==0x62 and rows[start].args==[11]
    assert all(x.target is None and x.cases is None for x in rows[start:])
    prefix=builder.p.asm.assemble([('getlocal_0',),('pushscope',),('getlocal_1',),('setlocal',11)])
    body[5]=builder.p.asm.encode(prefix+rows[start:])[0];body[6]=[]
    probe='cn.fixture::ProfilePeriodProbe/run|1';ti,=target.by_label[probe]
    graft=builder.p.Importer(target,builder.view(donor));old=target.a.bodies[ti]
    target.a.bodies[ti]=graft.body(di,old[0]);builder.p.check_body(target.a.bodies[ti],target.a)
    assert target.normalized(ti)[0][len(prefix):]==builder.view(main).normalized(di)[0][start:]
    receipts.append({'label':label,'kind':'exact-native-period-setter-suffix','sourceInstructionRange':[start,len(rows)],'normalizedFragmentExact':True,'wholeViewExecuted':False})
    return result

BODY=r'''
var profileKinds:Array=PROFILE_KINDS, profileDraw:Array=PROFILE_DRAW;
var history:Object=make("pinball.common.data.player_history.PlayerHistoryLogic");
history.id=1;history.values={string_id:"player_history",start_time:100,end_time:500};
check(history.isWithinPeriod(Date.UTC(2026,9,22)),"actual R9-derived id1 period method is permanent at real 2026 clock");
history.id=2;check(!history.isWithinPeriod(1000) && history.isWithinPeriod(300),"other history id retains actual original period");
history.id=1;history.values.string_id="wrong";check(!history.isWithinPeriod(1000),"unknown row cannot gain permanent entitlement");
var shareCard:Object=make("pinball.scene.playerHistory.card.PlayerHistoryCardLogic");
shareCard.logic={asset:{getUiString:function(k:String):String{return "official4周年";}}};
shareCard.id=1;check(shareCard.createShareText().text.indexOf("周年")<0 && shareCard.createShareText().text.indexOf("资料卡")>=0,"actual card share consumer removes anniversary restriction only for id1");
shareCard.id=2;check(shareCard.createShareText().text=="official4周年","other history share text remains native");
var pp:Object=make("cn.fixture.ProfilePeriodProbe");pp.view={asset:make("cn.fixture.ProfileAsset")};
pp.run({id:1,startTime:100,endTime:500});check(pp.periodContent.dateText.text=="常驻资料","actual profile period setter suffix renders permanent without resource-date mutation");
pp.run({id:2,startTime:100,endTime:500});check(pp.periodContent.dateText.text.indexOf("player_history_period_text")>=0,"other history period text retains original formatter");
var renderer:Object=make("pinball.scene.playerHistory.card.PlayerHistoryCardTopicView");
renderer.view={asset:make("cn.fixture.ProfileAsset")};renderer.globalLogic=make("cn.fixture.ProfileGlobal");
var rendering:Array=[];
for(var mode:int=0;mode<3;mode++)for(var pi:int=0;pi<profileDraw.length;pi++) {
 var k:int=profileKinds[pi], topic:Object=make("pinball.scene.playerHistory.card.PlayerHistoryCardTopicLogic");
 var kind:Object=make("pinball.common.data.player_history.PlayerHistoryAggregationKind");kind.index=k;
 var sourceKind:Object=make("pinball.scene.playerHistory.card.PlayerHistoryCardTopicSourceKind");
 var dates:Array=[], flags:Array=[], ints:Array=[], chars:Array=[], equips:Array=[], bosses:Array=[];
 var dateCount:int=(k==2||k==3)?6:1;
 for(var di:int=0;di<dateCount;di++){dates.push(mode==1?Option.Some("2025-07-17 12:00:00"):Option.None);flags.push(Option.Some(mode==2?1:0));}
 for(var vi:int=0;vi<12;vi++)ints.push(mode==0?Option.None:Option.Some(5));
 for(vi=0;vi<7;vi++)chars.push(mode==0?Option.None:Option.Some(101001));
 for(vi=0;vi<6;vi++)equips.push(Option.Some([5010045,5040020,5100011,5030028,5010032,5010056][vi]));
 bosses=[mode==0?Option.None:Option.Some(1)];
 var rawValues:Object={date_values:Option.Some(dates),int_values:Option.Some(flags)};
 sourceKind.index=1;sourceKind.params=[kind,rawValues];topic.sourceKind=sourceKind;
 var peek:Object=make("cn.fixture.ProfilePeek");peek.topic=topic;peek.ints=ints;peek.chars=chars;peek.equips=equips;peek.bosses=bosses;renderer.peek=peek;
 var panel:Object=make("pinball.ui.display.UiDisplayObjectContainer");panel.profileMode=true;
 renderer[profileDraw[pi]](panel);
 var observed:String=JSON.stringify(panel.texts);
 rendering.push({kind:k,mode:mode,frame:panel.frame,texts:observed});
 check(true,"actual topic native consumer completed "+profileDraw[pi]+" mode "+mode);
 if([2,3,4,7,8,26].indexOf(k)>=0 && mode==2) {
  check(observed.indexOf("日期未知")>=0,"completed-with-unknown-date preserves actual achieved native branch "+profileDraw[pi]);
  check(panel.frame==1,"unknown date cannot turn achievement into unachieved "+profileDraw[pi]);
  check(dates[0]===Option.None,"date adapter never mutates stored raw Option.None "+profileDraw[pi]);
 }
 if(k==0 && mode!=1)check(observed.indexOf("日期未知")>=0,"start game missing date renders unknown without native No Value");
}
nativeObservations.push({profileNativeRendering:rendering,wholePageExecuted:false,externalAssetLoadingExecuted:false});
'''.replace('PROFILE_KINDS',json.dumps(KINDS)).replace('PROFILE_DRAW',json.dumps(DRAW))

if __name__=='__main__':
    native.prepare=prepare;native.import_date_prologue=imports
    native.BODY=period.BODY+BODY;assistant.BODY=''
    runtime.main()
