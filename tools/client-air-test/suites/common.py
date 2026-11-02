"""Compile a typed test carrier and graft registered production consumer methods."""
from __future__ import annotations
import json,subprocess,sys,time,copy,re
from pathlib import Path
import abc_tools as abc
from abc_tools import load_current,sha,raw_units,replace_abc,graft,verify_grafts

def save(path,value):
 Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

BATTLE_CASE_IDS=['native-field-mana-request','native-boost-availability']

def battle_mode(ctx):
 if ctx.get('battle_mode'):return True
 return bool(ctx.get('fixtures') and any(c.get('group')=='battle' for c in json.loads(Path(ctx['fixtures']).read_text(encoding='utf-8-sig'))['cases']))

def purchases_mode(ctx):
 return bool(ctx.get('fixtures') and any(c.get('group')=='purchases' for c in json.loads(Path(ctx['fixtures']).read_text(encoding='utf-8-sig'))['cases']))

def purchase_type_contract(source,view):
 """Verify this donor's public mutation fields; do not synthesize a scene consumer."""
 def names(method):
  label,=[s for s in view.by_label if s.startswith('pinball.common.data.player::PlayerLogic/'+method+'|')]
  return {source.mn_name(i.args[0]) for i in abc.builder.asm.decode(source.bodies[view.by_label[label][0]][5]) if i.op in abc.builder.MULTINAME_OPS}
 user=names('applyCommonResponseUserInfo');common=names('applyCommonResponse')
 if not {'free_mana','paid_mana','free_vmoney','vmoney','stamina','exp_pool','pooled_exp'}<=user:
  raise ValueError('Selected donor lacks required native purchase user-info assignments')
 if not {'applyCommonResponseUserInfo','applyCommonResponseItemList','applyCommonResponseCharacterList'}<=common:
  raise ValueError('Selected donor lacks the required native common purchase consumers')
 if 'user_character_mana_node_list' in common:
  raise ValueError('Donor mana-node common contract changed; inspect before claiming scene coverage')
 return {'source_checked_directly':True,'native_user_fields':['free_mana','paid_mana','free_vmoney','vmoney','stamina','exp_pool -> pooled_exp'],
  'mana_nodes_via_common':False,'unexecuted_scene_consumers':['CharacterLearnManaNodeProcessingFlow.run','CharacterAwakeManaNodeProcessingFlow.run'],
  'dedicated_remote_callbacks_executed':False}

def battle_type_contract(source,view):
 owner='pinball.common.data.quest.battle::BattleClearParameter'
 row,=[r for r in source.instances if source.mn_name(r[0])==owner]
 field,=[t for t in row[6] if source.mn_name(t.name)=='obtainedMana']
 if field.data[0]!='slot' or source.mn_name(field.data[2])!='int':raise ValueError('Selected SWF obtainedMana must be a signed int slot')
 label,=[s for s in view.by_label if s.startswith('pinball.scene.battle.battle::ObtainableInstantItemManagerImpl/count|')]
 body=source.bodies[view.by_label[label][0]];info=source.methods[body[0]]
 if source.mn_name(info[0])!='int' or [source.mn_name(t) for t in info[1]]!=['int']:raise ValueError('Selected SWF pickup count must accept/return signed int')
 return {'obtainedMana_owner':owner,'obtainedMana_type':'int','pickup_count_parameter_types':['int'],'pickup_count_return_type':'int','source_checked_directly':True}
def build_sources(ctx):
 abc.configure(ctx)
 templates=Path(ctx['tool_root'])/'templates/common'
 b,a,v,identity=load_current();sources={};selections=[]
 if battle_mode(ctx):battle_type_contract(a,v)
 if purchases_mode(ctx):purchase_type_contract(a,v)
 def put(owner,body,extra='',imports=''):
  package,sep,name=owner.rpartition('::')
  if not sep:package='';name=owner
  references=sorted(set(re.findall(r'(?<![\w.])(?:[a-z]\w*\.)+[A-Z]\w*',body+extra)),key=len,reverse=True)
  imported=''
  for full in references:
   if full!=((package+'.') if package else '')+name:imported+='import '+full+';'
   body=re.sub(r'(?<![\w.])'+re.escape(full)+r'\b',full.rsplit('.',1)[-1],body)
   extra=re.sub(r'(?<![\w.])'+re.escape(full)+r'\b',full.rsplit('.',1)[-1],extra)
  sources[(package.replace('.','/')+'/' if package else '')+name+'.as']='package '+package+' {'+imports+imported+' public dynamic class '+name+extra+' {'+body+'}}'
 def method(owner,name,static=False,alias=None):
  prefix=owner+('$/' if static else '/')
  matches=[label for label in v.by_label if label.startswith(prefix) and label[len(prefix):].split('|')[0].rsplit('::',1)[-1]==name]
  assert len(matches)==1,(owner,name,matches)
  source=matches[0];bi,=v.by_label[source];mid=a.bodies[bi][0];info=a.methods[mid]
  def typ(t):return a.mn_name(t).replace('::','.') if t else '*'
  opts=len(info[4] or []);params=[]
  for i,t in enumerate(info[1]):params.append('p'+str(i)+':'+typ(t)+('=undefined' if i>=len(info[1])-opts else ''))
  alias=alias or name
  if name=='<ctor>':actual_name=owner.rsplit('::',1)[-1];decl='public function '+actual_name+'('+','.join(params)+'){}';target=prefix+'<ctor>'
  else:
   decl='public '+('static ' if static else '')+'function '+alias+'('+','.join(params)+'):'+typ(info[0])+'{throw new Error("ungrafted '+owner+'.'+name+'");}'
   target=prefix+alias+'|1'
  selections.append(source if source==target else {'source':source,'target':target})
  return decl
 def methods(owner,names,static=False):return ''.join(method(owner,n,static) for n in names)

 put('Dynamic','')
 put('cn.town::TownThemeState','public static function captureResponse(v:Object):void{fixture.CommonHarness.events.push({kind:"town-capture-dependency"});}')
 put('cn.content::ContentOperationsState','public static function captureResponse(v:Object):void{fixture.CommonHarness.events.push({kind:"content-capture-dependency"});}')
 put('flash::Boot','public static var skip_constructor:Boolean=false;public static var lastError:Error;'+method('flash::Boot','__instanceof',True)+'''public static function __string_rec(v:*,indent:String,depth:int=5):String {if(v===null)return "null";if(v===undefined)return "null";if(typeof v!="object")return String(v);try{return JSON.stringify(v);}catch(e:*){return String(v);}}public static function enum_to_string(v:Object):String{return v.tag;}''')
 put('ValueType','public var tag:String;public var index:int;public var params:Array;public function ValueType(t:String,i:int,p:Array){tag=t;index=i;params=p;}'+''.join('public static var '+n+':ValueType=new ValueType("'+n+'",'+str(i)+',null);' for i,n in enumerate(['TNull','TInt','TFloat','TBool','TObject','TFunction','TUnknown']))+'public static function TClass(v:Class):ValueType{return new ValueType("TClass",6,[v]);}public static function TEnum(v:Class):ValueType{return new ValueType("TEnum",7,[v]);}')
 put('Type',method('Type','typeof',True,'typeof_'))
 put('Std',method('Std','is',True,'is_')+methods('Std',['parseInt','string'],True))
 put('Reflect',methods('Reflect',['field','fields','compare'],True))
 sources['haxe/IMap.as']=(templates/'types/haxe/IMap.as').read_text(encoding='utf-8')
 sources['haxe/ds/Option.as']=(templates/'types/haxe/ds/Option.as').read_text(encoding='utf-8')
 map_methods={'toString':('','String'),'set':('p0:Object,p1:Object','void'),'remove':('p0:Object','Boolean'),'keys':('','Object'),'keyValueIterator':('','Object'),'iterator':('','Object'),'get':('p0:Object','Object'),'exists':('p0:Object','Boolean'),'copy':('','haxe.IMap'),'clear':('','void')}
 body='public var h:flash.utils.Dictionary;'+method('haxe.ds::IntMap','<ctor>')
 for n,(args,ret) in map_methods.items():
  if n in ['set','remove','keys','get','exists','copy','clear']:body+=method('haxe.ds::IntMap',n)
  else:body+='public function '+n+'('+args+'):'+ret+'{throw new Error("unused IntMap.'+n+'");}'
 put('haxe.ds::IntMap',body,' implements haxe.IMap')
 body='public var h:Object={};public static var reserved:Object={};public function setReserved(k:String,v:Object):void{h[k]=v;}public function getReserved(k:String):Object{return h[k];}'
 for n,(args,ret) in map_methods.items():
  impl={'toString':'return "[record-map]";','set':'h[String(p0)]=p1;','remove':'return delete h[String(p0)];','get':'return h[String(p0)];','exists':'return String(p0) in h;','clear':'h={};'}.get(n,'throw new Error("unused StringMap.'+n+'");')
  body+='public function '+n+'('+args+'):'+ret+'{'+impl+'}'
 put('haxe.ds::StringMap',body,' implements haxe.IMap')
 put('haxe.ds._IntMap::IntMapKeysIterator','public var h:flash.utils.Dictionary;public var index:int;public var nextIndex:int;'+methods('haxe.ds._IntMap::IntMapKeysIterator',['<ctor>','next','hasNext']))
 put('pinball.error::ClientError','public var internalMessage:String;public var code:int;'+methods('pinball.error::ClientError',['<ctor>','toString']),' extends Error')
 put('jp.sipo.util::Note','public function Note(v:Array=null){}')
 put('jp.sipo.util::CommonTag','public static var Debug:Object={tag:"Debug"};')
 put('haxe::Log','public static function trace(v:*,p:Object=null):void{fixture.CommonHarness.events.push({kind:"log",value:String(v)});}')
 put('pinball.remote.common::ResponseData','public var rawData:*;public var note:jp.sipo.util.Note;public var header:Object;'+method('pinball.remote.common::ResponseData','<ctor>'))
 sources['pinball/context/input/HookEntrance.as']=(templates/'types/pinball/context/input/HookEntrance.as').read_text(encoding='utf-8')
 put('pinball.context::HookForSection','public var dispatcher:pinball.context.input.HookEntrance;')
 put('pinball.context::SectionCommand','public var tag:String;public var index:int;public var params:Array;public function SectionCommand(t:String,i:int,p:Array){tag=t;index=i;params=p;}public static function ReceiveCommonResponse(v:Object):SectionCommand{return new SectionCommand("ReceiveCommonResponse",0,[v]);}public static function ApplyCommonConfig(v:Object):SectionCommand{return new SectionCommand("ApplyCommonConfig",1,[v]);}')
 put('pinball.context.remote::NewsInterruptFlagSender','public function send(v:haxe.ds.Option):void{fixture.CommonHarness.events.push({kind:"header",forceNews:v.index==0?v.params[0]:null});}')
 put('pinball.context.remote.real::RealRemote','public var globalLogic:Object;public var localStore:Object;public var hook:pinball.context.HookForSection;')
 put('pinball.context.remote.real::RealRemoteService','public var remote:Object;public var hook:pinball.context.HookForSection;public var globalLogic:Object;public var newsInterruptFlagSender:pinball.context.remote.NewsInterruptFlagSender;public function RealRemoteService(r:pinball.context.remote.real.RealRemote=null){if(r){remote=r;globalLogic=r.globalLogic;hook=r.hook;}}'+methods('pinball.context.remote.real::RealRemoteService',['processResponseHeader','earlySuccessHandler']))
 put('fixture::RecordingDispatcher','public var player:pinball.common.data.player.PlayerLogic;public function instant(v:Object,pos:Object=undefined):void{if(v.tag!="ReceiveCommonResponse")throw new Error("unexpected command "+v.tag);fixture.CommonHarness.events.push({kind:"common-before"});var applied:Boolean=player.applyCommonResponse(v.params[0]);fixture.CommonHarness.events.push({kind:"common-after",applied:applied});}public function ready(v:Object,pos:Object=undefined):void{instant(v,pos);}public function instantWithHandler(v:Object,f:Function,pos:Object=undefined):void{instant(v,pos);f();}public function readyWithHandler(v:Object,f:Function,pos:Object=undefined):void{instantWithHandler(v,f,pos);}',' implements pinball.context.input.HookEntrance')
 sources['pinball/common/data/player/PlayerPeek.as']='package pinball.common.data.player {public interface PlayerPeek {}}'
 # These fields are typed test setup; actual public consumers and getters are grafted.
 body='''public var saveData:Object;public var currentRank:haxe.ds.Option=haxe.ds.Option.None;public var logicStatus:pinball.common.data.player.LogicStatusForPlayerLogic=new fixture.RecordingLogicStatus();public var itemRepository:pinball.common.data.item.repository.OwnedItemRepository;public var timeProvider:Object={getTime:function():Number{return 0;}};
public function searchRank(v:int):int{throw new Error("rank lookup not part of economic fixture");}public function get_rankPoint():int{return int(saveData.userInfo.rank_point);}public function get_viewerId():Number{return 1;}public function get_name():String{return "offline-fixture";}
public function applyCommonResponseMonthlyChargeBonusInfo(v:Object):void{throw new Error("unexpected monthly bonus");}
public function getOwnedCharacter(id:int):pinball.common.data.character.OwnedCharacterPeek{var c:pinball.common.data.character.OwnedCharacterLogic=new pinball.common.data.character.OwnedCharacterLogic();c.characterSaveData=saveData.characters.h[id];c.applyCharacterSaveData();return c;}
'''
 body+=methods('pinball.common.data.player::PlayerLogic',['applyCommonResponse','applyCommonResponseItemList','applyCommonResponseEquipmentList','applyCommonResponseUserInfo','applyCommonResponseCharacterList','applyCommonResponseCrazyGachaResultList','applyCommonResponseLastCrazyGachaResultList','applyCommonResponseFundBonusList','hasCharacter','getItemNumber','getEquipmentNumber','get_mana','get_paidMana','get_freeMana','get_virtualMoney','get_starCrumb','getItemRepository'])
 if battle_mode(ctx):
  body=body.replace('throw new Error("rank lookup not part of economic fixture");','return 1; /* explicit rank-master boundary, not a rank acceptance */')
  body+=methods('pinball.common.data.player::PlayerLogic',['get_boostPoint','get_bossBoostPoint','canUseBoostPoint','canUseBossBoostPoint'])
 put('pinball.common.data.player::PlayerLogic',body,' implements pinball.common.data.player.PlayerPeek')
 sources['pinball/common/data/player/LogicStatusForPlayerLogic.as']='package pinball.common.data.player {public interface LogicStatusForPlayerLogic {function applyMailArrived(v:Boolean):void;function applyDailyChallengePointList(v:Array):void;}}'
 put('fixture::RecordingLogicStatus','public function applyMailArrived(v:Boolean):void{fixture.CommonHarness.events.push({kind:"mail-arrived",value:v});}public function applyDailyChallengePointList(v:Array):void{fixture.CommonHarness.events.push({kind:"daily",value:v});}',' implements pinball.common.data.player.LogicStatusForPlayerLogic')
 put('pinball.common.data.item.repository::OwnedItemRepository','public var player:pinball.common.data.player.PlayerLogic;'+methods('pinball.common.data.item.repository::OwnedItemRepository',['getNumber','getAllIds']))
 put('com.gibits.leitingaar::LeitingSDKExtension','public static function getInstance():LeitingSDKExtension{return new LeitingSDKExtension();}public function levelUpReport(v:String):void{fixture.CommonHarness.events.push({kind:"ANE-level-report",value:v});}')
 put('pinball.common.time._AppTime::AppTime_Impl_','public static function now():Number{return 0;}public static function getTime(v:Number):Number{return v;}public static function _new(v:Number):Number{return v;}')
 # Date parsing is a setup dependency; economic scalar/character mutation algorithms stay production.
 put('pinball.common.time._JapanStandardTimeString::JapanStandardTimeString_Impl_','public static function toAppTime(v:String):Number{if(v=="0000-00-00 00:00:00")return 0;return Date.parse(v.split("-").join("/"));}')
 sources['pinball/common/data/character/OwnedCharacterPeek.as']='package pinball.common.data.character {public interface OwnedCharacterPeek {}}'
 body='public var characterSaveData:Object;public var abilities:haxe.IMap;public var evolutionLevel:int;public var experience:int;public var overLimitStep:int;public var exBoost:haxe.ds.Option;'
 body+=methods('pinball.common.data.character::OwnedCharacterLogic',['applyUseDate','applyStack','applyProtection','applyOverLimitStep','applyOpenedManaBoardIndex','applyJoinDate','applyExperience','applyExBoost','applyEvolutionLevel','applyEntryCount','applyCharacterSaveData','applyBondTokenList','get_stack'])
 # This uncommon branch is explicit instead of silently pretending to load board state.
 body+='public function applyManaBoardAwake(v:haxe.IMap):void{throw new Error("mana board awake needs an explicit fixture");}'
 put('pinball.common.data.character::OwnedCharacterLogic',body,' implements pinball.common.data.character.OwnedCharacterPeek')
 put('pinball.common.data.save::PlayerSaveDataTools',method('pinball.common.data.save::PlayerSaveDataTools','addCharacter',True))
 sources['fixture/CommonHarness.as']=(templates/'CommonHarness.as').read_text(encoding='utf-8')
 if battle_mode(ctx):
  sources['fixture/BattleNative.as']=(templates/'BattleNative.as').read_text(encoding='utf-8')
  sources['pinball/common/data/item/ObtainableInstantItemSource.as']='package pinball.common.data.item {public interface ObtainableInstantItemSource {function get_kind():int;function get_num_items():int;}}'
  put('fixture::InstantSource','public var kind:int;public var count:int;public function InstantSource(k:int,n:int){kind=k;count=n;}public function get_kind():int{return kind;}public function get_num_items():int{return count;}',' implements pinball.common.data.item.ObtainableInstantItemSource')
  put('pinball.common.data.battle.restore::BattleContinuationData','public var obtainedInstantItems:Array=[];')
  put('pinball.scene.battle.battle::ObtainableInstantItemManagerImpl','public var obtainedInstantItems:Array;'+methods('pinball.scene.battle.battle::ObtainableInstantItemManagerImpl',['<ctor>','addChild','count','sumUp']))
  put('pinball.common.data.quest.battle::BattleClearParameter','public var obtainedMana:int;public var continueCount:int=0;public var party:Object;public var statistics:Object;public var accomplished:Boolean=true;public var isLoseEventBattle:Boolean=false;public var isLose:Boolean=false;public function get_isAccomplished():Boolean{return accomplished;}')
  put('pinball.common.data.quest.battle::BattleQuestClearParameter','public var myBattle:pinball.common.data.quest.battle.BattleClearParameter;public var multiParamter:Object=null;public var playId:String="native-field-mana";public var isRestored:Boolean=false;public function getMyFinalScore(v:pinball.common.data.quest.score.ScoreSource):pinball.common.data.quest.score.FinalScore{return new pinball.common.data.quest.score.FinalScore();}public function get_clearTime():Number{return 1000;}public function getStatistics():Object{return myBattle.statistics;}public function getOtherStatistics():haxe.ds.Option{return haxe.ds.Option.None;}public function getMyContributionScoreResult():Object{return {contributionScore:0};}')
  put('pinball.common.data.quest.score::ScoreSource','')
  put('pinball.common.data.quest.score::FinalScore','public var total:Number=100;')
  put('pinball.common.data.quest.id::QuestIdGroupKind','public var category:int=1;public var questId:int=1001001;')
  sources['pinball/common/data/quest/common/QuestLogic.as']='package pinball.common.data.quest.common {import pinball.common.data.quest.id.QuestIdGroupKind;import pinball.common.data.quest.battle.BattleQuestLogic;import haxe.ds.Option;public interface QuestLogic {function get_idGroup():QuestIdGroupKind;function getBattleDetail():BattleQuestLogic;function getFixedParty():Option;}}'
  sources['pinball/common/data/quest/battle/BattleQuestPeek.as']='package pinball.common.data.quest.battle {import pinball.common.data.quest.score.ScoreSource;public interface BattleQuestPeek {function getScoreSource():ScoreSource;}}'
  sources['pinball/common/data/quest/battle/BattleQuestLogic.as']='package pinball.common.data.quest.battle {public interface BattleQuestLogic extends BattleQuestPeek {}}'
  put('fixture::QuestFixture','public function get_idGroup():pinball.common.data.quest.id.QuestIdGroupKind{return new pinball.common.data.quest.id.QuestIdGroupKind();}public function getBattleDetail():pinball.common.data.quest.battle.BattleQuestLogic{return new fixture.BattleQuestFixture();}public function getFixedParty():haxe.ds.Option{return haxe.ds.Option.None;}',' implements pinball.common.data.quest.common.QuestLogic')
  put('fixture::BattleQuestFixture','public function getScoreSource():pinball.common.data.quest.score.ScoreSource{return new pinball.common.data.quest.score.ScoreSource();}',' implements pinball.common.data.quest.battle.BattleQuestLogic')
  put('pinball.common.data.quest.common._QuestCategory::QuestCategory_Impl_','public static function fromQuestIdGroupKind(v:pinball.common.data.quest.id.QuestIdGroupKind):int{return v.category;}')
  put('pinball.common.data.quest.id::QuestIdGroupKindTools','public static function toAnyQuestId(v:pinball.common.data.quest.id.QuestIdGroupKind):int{return v.questId;}')
  put('pinball.common.time._TimeSpan::TimeSpan_Impl_','public static function getSeconds(v:Number):Number{return v/1000;}')
  put('pinball.common.data.item::OwnedEquipmentLogic','')
  put('pinball.common.data.player._ViewerId::ViewerId_Impl_','public static var MAX_SAFE_INTEGER:Number=9007199254740991;')
  put('pinball.context.attention.data::AttentionScoreActionKind','public static var Parasite:AttentionScoreActionKind=new AttentionScoreActionKind();')
  put('haxe.ds._StringMap::StringMapKeysIterator','public function StringMapKeysIterator(h:Object,r:Object){}public function hasNext():Boolean{return false;}public function next():String{return "";}')
  put('pinball.common.math._FloatInt::FloatInt_Impl_','public static function toFloat(v:Number):Number{return v;}')
  put('pinball.remote.quest.finish::BattleQuestFinishRemoteUtil','public static function createLogData(v:Boolean):Object{return {}; }public static function compareSubStatistics(a:Object,b:Object):int{return int(a.sub_id)-int(b.sub_id);}'+method('pinball.remote.quest.finish::BattleQuestFinishRemoteUtil','createRequest',True))
 return sources,selections,identity

def synthetic_cases():
 """Seven small schema-2 contract cases, embedded once in the common carrier."""
 base={'items':{'101':7,'999':4},'equipments':{},'userInfo':{'free_vmoney':8,'vmoney':2,'free_mana':5,'paid_mana':3,'pooled_exp':0},'characters':{},'crazyGachaResultList':{}}
 def response(data):return {'data_headers':{'result_code':1},'data':data}
 good=response({'item_list':{'101':0,'102':3},'equipment_list':[{'equipment_id':100013,'level':2,'enhancement_level':1,'stack':0,'protection':False}],'user_info':{'free_vmoney':0,'free_mana':99},'crazy_gacha_result_list':{'100':[111015,111016]}})
 final=copy.deepcopy(base);final['items']={'999':4,'102':3};final['equipments']={'100013':{'equipmentId':100013,'level':2,'enhancementLevel':1,'stack':0,'protection':False}};final['userInfo'].update(free_vmoney=0,free_mana=99);final['crazyGachaResultList']={'100':[111015,111016]}
 cases=[]
 def add(name,responses,expected,code=None):
  steps=[]
  for i,raw in enumerate(responses):
   step={'id':name+'/'+str(i+1),'response':copy.deepcopy(raw),'expectedAfter':copy.deepcopy(expected)}
   if code is not None:step['expectedErrorId']=code
   steps.append(step)
  cases.append({'id':name,'group':'synthetic','before':copy.deepcopy(base),'steps':steps,'expectedAfter':copy.deepcopy(expected)})
 add('synthetic-absolute-updates-repeat-zero-preserve',[good,good],final)
 add('synthetic-omitted-fields-preserve',[response({})],base)
 for name,raw,code in [('item-string',response({'item_list':{'101':'7'}}),8700),('item-float',response({'item_list':{'101':1.5}}),8700),('equipment-bool',response({'equipment_list':[{'equipment_id':100013,'level':1,'enhancement_level':0,'stack':0,'protection':'false'}]}),8703),('bad-data',response('wrong'),8707),('bad-header',{'data_headers':{'result_code':'1'},'data':{}},8700)]:
  add('synthetic-invalid-'+name,[raw],base,code)
 return cases

def prepare_sources(ctx,out):
 out=abc.output_directory(ctx,out);out.mkdir(parents=True,exist_ok=True)
 sources,selections,identity=build_sources(ctx);src=out/'src';src.mkdir(exist_ok=False)
 for name,text in sources.items():
  p=src/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
 runner=(Path(ctx['tool_root'])/'templates/common/CommonRunner.as').read_text(encoding='utf-8')
 marker='__SYNTHETIC_CASES_JSON__'
 if runner.count(marker)!=1:raise ValueError('CommonRunner synthetic marker must be unique')
 runner=runner.replace(marker,json.dumps(json.dumps(synthetic_cases(),ensure_ascii=False,separators=(',',':')),ensure_ascii=True))
 for marker,replacement in {
  '__BATTLE_NATIVE_RUN__':'for each(var nativeRow:Object in fixture.BattleNative.cases()){rows.push(nativeRow);if(nativeRow.status!="passed")failed++;}' if battle_mode(ctx) else '',
  '__BATTLE_NATIVE_RESPONSE__':'if(spec.group=="battle")fixture.BattleNative.checkResponse(player,step,stepChecks);' if battle_mode(ctx) else '',
  '__BATTLE_NATIVE_LIMIT__':',"Battle count is manually assigned to obtainedMana before native createRequest; battle/clear constructors, complete restore, rank master, score/quest conversion and finish-specific UI/parser are not executed."' if battle_mode(ctx) else '',
  '__PURCHASE_NATIVE_LIMIT__':',"Purchases validates native common wallet/stamina/EXP/item/character updates only. Dedicated shop/box/EXP/mana remote callbacks, mana-board scene appendManaNodes, node persistence and result UI are not executed. expectedManaNodes is a server fixture assertion, not AIR node-consumption evidence."' if purchases_mode(ctx) else '',
 }.items():
  if runner.count(marker)!=1:raise ValueError('Missing or duplicate battle carrier marker '+marker)
  runner=runner.replace(marker,replacement)
 (src/'CommonRunner.as').write_text(runner,encoding='utf-8')
 includes=sorted(n[:-3].replace('/','.') for n in sources)
 save(out/'source-manifest.json',{'identity':identity,'selections':selections,'includes':includes,'sources':{str(p.relative_to(src)):sha(p.read_bytes()) for p in src.rglob('*.as')}})
 return {'source_dir':src,'selections':selections,'includes':includes}

def build(ctx,out):
 out=abc.output_directory(ctx,out);prepared=prepare_sources(ctx,out);src=prepared['source_dir']
 sdk=Path(ctx['sdk']);java=Path(ctx['java']);template=out/'template.swf';output=out/'Harness.swf'
 command=[java,'-Xmx1g','-Dflexlib='+str(sdk/'frameworks'),'-jar',sdk/'lib/mxmlc-cli.jar','+configname=air','-swf-version=44','-target-player=32.0','-compiler.float=false','-debug=false','-compress=false','-compiler.source-path='+str(src),'-includes='+','.join(prepared['includes']),'-output='+str(template),src/'CommonRunner.as']
 t=time.perf_counter();process=subprocess.run([str(x) for x in command],cwd=out,capture_output=True,timeout=120)
 (out/'compile.log').write_bytes(process.stdout+process.stderr)
 receipt={'command':[str(x) for x in command],'exit_code':process.returncode,'elapsed_ms':round((time.perf_counter()-t)*1000,3),'source_sha256':{str(p.relative_to(src)):sha(p.read_bytes()) for p in src.rglob('*.as')}}
 save(out/'compile-receipt.json',receipt)
 if process.returncode:raise RuntimeError('compile failed; see compile.log')
 b,source,sv,_=load_current();units=list(raw_units(template.read_bytes()));assert len(units)==1
 target=b.abcfmt.ABC(units[0][1]);mapping=graft(target,source,prepared['selections']);output.write_bytes(replace_abc(template.read_bytes(),target))
 parsed=b.abcfmt.ABC(list(raw_units(output.read_bytes()))[0][1]);proof=verify_grafts(parsed,source,mapping)
 identity=load_current()[3];proof_path=out/'graft-proof.json'
 save(proof_path,{'input':identity,'identity':identity,'methods':proof,'real_methods':proof,'target_swf_sha256':sha(output.read_bytes()),'template_swf_sha256':sha(template.read_bytes()),'battle_input_contract':battle_type_contract(source,sv) if battle_mode(ctx) else None,'purchase_input_contract':purchase_type_contract(source,sv) if purchases_mode(ctx) else None,'adaptations':['Existing importer maps pools and method IDs; code/exception normalization and full MethodInfo flags/defaults retained.','Type.typeof and Std.is placeholder aliases renamed to exact donor QName.','Typed setup/storage/time/ANE/dispatch and captureResponse recording boundaries are explicit; only listed grafted methods are production code claims.']+(['BattleNative executes nine added native methods: pickup manager ctor/addChild/count/sumUp; finish createRequest; PlayerLogic normal/boss boost getters and availability checks. Binding alone is not execution evidence: inspect both required native runtime cases.','The bridge from count to BattleClearParameter.obtainedMana is manual. Battle and clear constructors, complete battle restore, score/quest conversion, rank master, equipment/mate branches and device log creation are explicit shell boundaries. Finish-specific response parser and result UI are not imported.'] if battle_mode(ctx) else [])})
 application=out/'application.xml';application.write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>cn.fixture.common.offline</id><versionNumber>1.0.0</versionNumber><filename>CommonRunner</filename><initialWindow><content>Harness.swf</content><visible>false</visible></initialWindow></application>',encoding='utf-8')
 cases=synthetic_cases()
 return {'application':application,'swf':output,'proof':proof_path,'required_case_ids':[c['id'] for c in cases]+(BATTLE_CASE_IDS if battle_mode(ctx) else []),'required_step_ids':[s['id'] for c in cases for s in c['steps']]}

def generate_battle(ctx,out,node):
 """Execute native field-mana serialization first, then the selected source routes."""
 from run_contract import validate_binding,validate_application,validate_result,expectations,write
 root=Path(ctx['run_root']);preflight=root/'client-battle-payload';preflight.mkdir()
 empty=preflight/'empty-fixtures.json';write(empty,{'schemaVersion':2,'cases':[]})
 native_ctx={**ctx,'battle_mode':True};built=build(native_ctx,preflight)
 binding={**validate_binding(built,ctx),**validate_application(built)}
 contract=expectations('common',{'schemaVersion':2,'cases':[]},built);write(preflight/'contract.json',contract)
 command=[str(Path(ctx['sdk'])/'bin/adl.exe'),'-nodebug','-cmd',str(built['application']),'--',str(empty),str(preflight/'result.json')]
 started=time.perf_counter();p=subprocess.run(command,cwd=preflight,capture_output=True,timeout=90);(preflight/'adl.log').write_bytes(p.stdout+p.stderr)
 execution={'command':command,'exit_code':p.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3)};write(preflight/'execution.json',execution)
 result=json.loads((preflight/'result.json').read_text(encoding='utf-8'));coverage=validate_result(result,contract,p.returncode)
 write(preflight/'receipt.json',{'status':'passed',**binding,**coverage})
 command=[node,str(Path(ctx['tool_root'])/'fixtures/battle.cjs'),'--repo',ctx['repo'],'--out',str(out),'--client-result',str(preflight/'result.json')]
 started=time.perf_counter();p=subprocess.run(command,cwd=ctx['repo'],capture_output=True,timeout=180);(root/'generator.log').write_bytes(p.stdout+p.stderr)
 write(root/'generator-execution.json',{'command':command,'exit_code':p.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3)})
 if p.returncode:raise RuntimeError('Battle source fixtures failed; see generator.log')
 return out/'fixtures.json'
