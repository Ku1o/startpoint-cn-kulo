"""Execute the candidate helper and complete native town selection methods in AVM2.

Resource maps are bounded fixtures; this does not execute the game, GPU or downloads.
The response probe executes the exact native constructor prologue only.
"""
import argparse,copy,hashlib,json,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'content-operations'))
import build_bridge as b
from build_exchange_repair import physical_labels
from build_town_theme import RESPONSE,SELECT,sha
STUBS={
'haxe/ds/Option.as':'''package haxe.ds {public class Option {public var index:int;public var params:Array;public static var None:Option=new Option(1,[]);public function Option(i:int,p:Array){index=i;params=p;}public static function Some(v:Object):Option{return new Option(0,[v]);}}}''',
'flash/Boot.as':'''package flash {public class Boot {public static var lastError:Error;public static var skip_constructor:Boolean=false;}}''',
'Std.as':'''package {public class Std {public static function string(o:Object):String{return String(o);}}}''',
'pinball/error/ClientError.as':'''package pinball.error {public class ClientError extends Error {public var code:int;public function ClientError(c:int,s:String){code=c;super(s);}}}''',
'pinball/common/data/town/TownContentKind.as':'''package pinball.common.data.town {public class TownContentKind {public var index:int;public var params:Array;public static var Normal:TownContentKind=new TownContentKind(0,[]);public function TownContentKind(i:int,p:Array){index=i;params=p;}}}''',
'pinball/common/data/town/TownContentPeek.as':'''package pinball.common.data.town {public interface TownContentPeek {function get_bgm():String;}}''',
'pinball/common/data/town/TownContentLogic.as':'''package pinball.common.data.town {import haxe.ds.Option;public class TownContentLogic implements TownContentPeek {public var id:int;public var values:Object;public function TownContentLogic(i:int=0,v:Object=null){id=i;values=v;}
public function isWithinPeriod(t:Number):Boolean{return false;}public function get_kind():TownContentKind{return null;}public function getDisplayPriority():int{return 0;}
public function get_backgroundImage():String{return null;}public function get_backgroundBluredImage():String{return null;}public function get_bgm():String{return null;}
public function get_maskImage():Option{return null;}}}''',
'pinball/common/data/town/TownContentRepository.as':'''package pinball.common.data.town {public class TownContentRepository {public var townContentTable:Object;public var traceCalls:Array=[];
public function getTownContentByTime(t:Number):TownContentLogic{return null;}
public function sortTownContents(a:TownContentLogic,c:TownContentLogic):int{return 0;}
public function getAllTownContents():Array {traceCalls.push("all");return townContentTable.all();}
public function getTownContentById(i:int):TownContentLogic{traceCalls.push("id:"+i);return new TownContentLogic(i,townContentTable.get(i));}}}''',
'pinball/common/time/TimeRangeWithoutYear.as':'''package pinball.common.time {public class TimeRangeWithoutYear {public var startTime:Number;public var endTime:Number;public function TimeRangeWithoutYear(s:Number=0,e:Number=0){startTime=s;endTime=e;}public function isWithin(t:Number):Boolean{return false;}}}''',
'pinball/common/time/_AppTime/AppTime_Impl_.as':'''package pinball.common.time._AppTime {public class AppTime_Impl_ {public static function toWithoutYear(t:Number):Number {return t;}public static function toSecondsAccuracy(t:Number):Number{return Math.floor(t/1000)*1000;}}}''',
'cn/content/ContentOperationsState.as':'''package cn.content {public class ContentOperationsState {public static var calls:int=0;public static function captureResponse(v:Object):void{calls++;}}}''',
'cn/fixture/LoginProbe.as':'''package cn.fixture {public class LoginProbe {public function capture(raw:Object):void{}}}''',
'cn/fixture/NativeTownBaseline.as':'''package cn.fixture {import pinball.common.data.town.*;public class NativeTownBaseline extends TownContentRepository {override public function getTownContentByTime(t:Number):TownContentLogic{return null;}}}''',
'pinball/common/data/localStore/MiscDataLogic.as':'''package pinball.common.data.localStore {public class MiscDataLogic {public var home:Object={bgmPath:null};public function getHomeData():Object{return home;}}}''',
'pinball/context/global/GlobalLogic.as':'''package pinball.context.global {import pinball.common.data.localStore.MiscDataLogic;import pinball.common.data.town.TownContentPeek;public class GlobalLogic {public var misc:MiscDataLogic=new MiscDataLogic();public var current:TownContentPeek;public function getMiscData():MiscDataLogic{return misc;}public function getTownContent():TownContentPeek{return current;}public function getCustomTownBgm():String{return null;}}}''',
'cn/fixture/TownTable.as':'''package cn.fixture {import pinball.common.data.town.TownContentLogic;public class TownTable {public var rows:Object={};public var order:Array=[];public var fail:Boolean=false;public function exists(i:int):Boolean{if(fail)throw new Error("unavailable");return rows.hasOwnProperty(String(i));}public function get(i:int):Object{return rows[String(i)];}public function all():Array{var a:Array=[];for each(var i:int in order)a.push(new TownContentLogic(i,get(i)));return a;}}}''',
}
BODY=r'''
Array.prototype.copy=function():Array{return this.concat();};Array.prototype.setPropertyIsEnumerable("copy",false);
var table:TownTable=new TownTable();var repo:TownContentRepository=new TownContentRepository();repo.townContentTable=table;
var baseline:NativeTownBaseline=new NativeTownBaseline();baseline.townContentTable=table;
function row(i:int,kind:int,start:Number=0,end:Number=0):void {table.rows[String(i)]={string_id:"fixture_"+i,kind:new TownContentKind(kind,[start,end]),background_image:"town/a"+i,background_blured_image:"town/b"+i,bgm:"bgm/a"+i,mask_image:Option.None,particle:Option.None};table.order.push(i);}
row(1,0);row(2,1,1000,3000);row(3,2,2000,4000);row(9,2,2000,4000);row(42,0);
check(table.order.length==5 && table.get(1)!=null,"fixture table seeded");
check(repo.getAllTownContents()[0].values!=null,"fixture native row receiver seeded");
check(repo.getAllTownContents()[0].get_kind().index===0,"direct native kind getter resolves sealed receiver");
check(repo.getAllTownContents()[0].isWithinPeriod(0),"direct native period resolves sealed receiver");
var probe:LoginProbe=new LoginProbe();
function policy(id:Object=2,mode:String="manual",rev:Object=1):Object{return {schema_version:1,revision:rev,mode:mode,theme_id:mode=="auto"?null:"future_sixth_theme",town_content_id:mode=="auto"?null:id,catalog_digest:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"};}
function login(p:Object,marker:Object=true,code:Object=1):Object{return {data_headers:{result_code:code},data:{town_presentation_load:marker,town_presentation:p}};}
function autoCheck(t:Number,expected:int,label:String):void {repo.traceCalls=[];var actual:TownContentLogic=repo.getTownContentByTime(t);var nativeResult:TownContentLogic=baseline.getTownContentByTime(t);check(actual.id==nativeResult.id && (actual.id==expected || expected==3 && actual.id==9),label+"; exact R10 selector result="+nativeResult.id);check(repo.traceCalls.join(",")=="all","native auto calls whole enumeration once: "+label);}
probe.capture(login(policy(null,"auto")));autoCheck(0,1,"auto normal");autoCheck(1000,2,"event start inclusive");autoCheck(1999,2,"before annual start");autoCheck(2000,3,"annual wins event and original stable row order");autoCheck(3000,3,"annual remains over inclusive event end");autoCheck(4000,3,"annual end inclusive");autoCheck(5000,1,"expired event and annual fall back normal");
probe.capture(login(policy(42)));repo.traceCalls=[];var selected:TownContentLogic=repo.getTownContentByTime(2000);check(selected.id==42,"future sixth ID outside built-in five accepted without SWF rebuild");check(repo.traceCalls.join(",")=="id:42","manual bypasses native enumeration only after validated row");check(selected.get_backgroundImage()=="town/a42" && selected.get_backgroundBluredImage()=="town/b42" && selected.get_bgm()=="bgm/a42" && selected.get_maskImage().index==1,"native row getters retain matching background blur music and mask");
var snapshot:Object=login(policy(2));probe.capture(snapshot);snapshot.data.town_presentation.town_content_id=42;check(repo.getTownContentByTime(0).id==2,"capture copies scalar; mutable raw response cannot change async load selection");
for each(var ordinary:Object in [{data_headers:{result_code:1},data:{}},{data_headers:{result_code:1},data:{town_presentation:policy(42)}},login(policy(42),false),login(policy(42),true,500),{data_headers:{result_code:1},data:{user_info:{}}},{data_headers:{result_code:1},data:{user_info:{},user_option:{},user_party_group_list:{}}},null,"bad",[],{data_headers:7,data:{}},{data_headers:{result_code:1},data:[]},{data_headers:{result_code:1},data:"bad"}]) {probe.capture(ordinary);check(repo.getTownContentByTime(0).id==2,"ordinary partial malformed or error responses leave active theme unchanged");}
probe.capture(login(null));autoCheck(0,1,"new successful login missing field resets auto");
var bad:Array=[null,{},[],"bad",7,policy(0),policy(-1),policy(1.2),policy("2"),policy(2147483648),policy(9999),policy(2,"unknown"),policy(2,"manual",-1),policy(2,"manual",1.5),policy(2,"manual","1"),policy(2,"manual",Number.NaN),policy(2,"manual",Number.POSITIVE_INFINITY)];
var p:Object=policy();p.schema_version=2;bad.push(p);p=policy();p.catalog_digest="bad";bad.push(p);p=policy();p.theme_id="";bad.push(p);p=policy();delete p.theme_id;bad.push(p);p=policy();delete p.town_content_id;bad.push(p);
for each(p in bad){probe.capture(login(policy(2)));probe.capture(login(p));autoCheck(0,1,"invalid new login resets auto: "+JSON.stringify(p));}
probe.capture(login(policy(42)));probe.capture({data_headers:{result_code:1},data:{user_info:{},user_option:{},user_character_list:{},user_party_group_list:{}}});autoCheck(0,1,"old server full login without marker clears stale session theme");
probe.capture(login(policy(42)));probe.capture({data_headers:{result_code:1},data:{user_info:{},user_option:{},user_character_list:[],user_party_group_list:{}}});check(repo.getTownContentByTime(0).id==42,"array list impostor cannot reset legacy login");
probe.capture(login(policy(2,"manual",99)));probe.capture(login(policy(42,"manual",1)));check(repo.getTownContentByTime(0).id==42,"new account load accepts its own lower revision");probe.capture(login(policy(2,"manual",1)));check(repo.getTownContentByTime(0).id==2,"same revision successful login can establish a new session");
var saved:Object=table.rows["42"];for each(var field:String in ["string_id","background_image","background_blured_image","bgm","mask_image","particle"]){table.rows["42"]=JSON.parse(JSON.stringify(saved));table.rows["42"].kind=saved.kind;delete table.rows["42"][field];probe.capture(login(policy(42)));autoCheck(0,1,"missing native resource field falls back: "+field);}table.rows["42"]=saved;
for each(var malformed:Object in [{index:7},{index:0,params:[]},{index:0,params:[null]}]) {table.rows["42"].particle=malformed;probe.capture(login(policy(42)));autoCheck(0,1,"invalid native particle schema falls back");}table.rows["42"].particle=Option.None;
table.rows["42"].mask_image=Option.Some("../bad");probe.capture(login(policy(42)));autoCheck(0,1,"unsafe native mask path falls back");table.rows["42"].mask_image=Option.None;
table.fail=true;probe.capture(login(policy(42)));autoCheck(0,1,"unavailable table manual guard catches failure then original runs");table.fail=false;
probe.capture(login(policy(null,"auto")));var oldOrder:Array=table.order;table.order=[];var missing:Boolean=false;try {repo.getTownContentByTime(0);}catch(err:ClientError){missing=err.code==7233;}check(missing,"original no-candidate ClientError7233 preserved");table.order=oldOrder;
// Year-wrapping annual semantics use the complete native TimeRangeWithoutYear.isWithin body.
table.rows["3"].kind=new TownContentKind(2,[4000,1000]);table.order=[1,2,3];autoCheck(0,3,"native annual year wrap includes before end");autoCheck(1000,3,"native annual wrapped end inclusive");autoCheck(2000,2,"native annual middle gap retains event");autoCheck(4000,3,"native annual wrapped start inclusive");
check(ContentOperationsState.calls>0,"exact constructor prologue retains previous content capture invocation");
var global:GlobalLogic=new GlobalLogic();probe.capture(login(policy(42)));global.current=repo.getTownContentByTime(0);check(global.getCustomTownBgm()=="bgm/a42","complete native custom BGM getter uses selected theme when no preference");global.misc.home.bgmPath="bgm/player/custom";check(global.getCustomTownBgm()=="bgm/player/custom","complete native getter preserves existing player custom music");probe.capture(login(policy(2)));global.current=repo.getTownContentByTime(0);check(global.getCustomTownBgm()=="bgm/player/custom" && global.misc.home.bgmPath=="bgm/player/custom","next login theme never writes local BGM preference");global.misc.home.bgmPath="";check(global.getCustomTownBgm()=="bgm/a2","empty preference uses new native theme default");
'''
MAIN='''package {import flash.display.Sprite;import flash.desktop.NativeApplication;import flash.filesystem.*;import flash.utils.Timer;import flash.events.TimerEvent;import haxe.ds.Option;import pinball.common.data.town.*;import pinball.context.global.GlobalLogic;import pinball.error.ClientError;import cn.fixture.*;import cn.content.ContentOperationsState;import cn.town.TownThemeState;
public class TownTest extends Sprite {public function TownTest(){var assertions:int=0;var checks:Array=[];function check(v:Boolean,s:String):void{assertions++;if(!v)throw new Error(s);checks.push(s);}function finish(result:Object):void{var fs:FileStream=new FileStream();fs.open(new File(OUTPUT),FileMode.WRITE);fs.writeUTFBytes(JSON.stringify(result));fs.close();NativeApplication.nativeApplication.exit(result.passed?0:1);}try {BODY
var asyncRaw:Object=login(policy(42));probe.capture(asyncRaw);var preloadId:int=repo.getTownContentByTime(0).id;var timer:Timer=new Timer(10,1);timer.addEventListener(TimerEvent.TIMER_COMPLETE,function(e:TimerEvent):void{try {asyncRaw.data.town_presentation.town_content_id=2;probe.capture({data_headers:{result_code:1},data:{town_presentation:policy(2)}});var later:TownContentLogic=repo.getTownContentByTime(0);check(preloadId==42 && later.id==preloadId && later.get_bgm()=="bgm/a42","actual Timer boundary keeps preload background and BGM ID despite ordinary update or raw mutation");finish({passed:true,assertions:assertions,checks:checks,asyncTickExecuted:true});}catch(error:Error){finish({passed:false,assertions:assertions,error:error.toString(),stack:error.getStackTrace()});}});timer.start();
}catch(e:Error){finish({passed:false,assertions:assertions,error:e.toString(),stack:e.getStackTrace()});}}}}'''
def run(a):
 root=a.work;root.mkdir(parents=True,exist_ok=True)
 prodtags=b.sc.parts(a.candidate)[2];main=next(t[3] for t in prodtags if t[3] and any(t[3].mn_name(i[0])=='pinball.context.global::GlobalLogic' for i in t[3].instances))
 baseline_tags=b.sc.parts(a.baseline)[2];baseline_main=next(t[3] for t in baseline_tags if t[3] and any(t[3].mn_name(i[0])=='pinball.context.global::GlobalLogic' for i in t[3].instances))
 helper=next(t[3] for t in prodtags if t[3] and any(t[3].mn_name(i[0])=='cn.town::TownThemeState' for i in t[3].instances))
 if a.expect_r10_missing_hooks:main=baseline_main
 for path,value in STUBS.items():
  f=root/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(value,encoding='utf8')
 output=(root/'air-town-result.json').resolve();(root/'TownTest.as').write_text(MAIN.replace('BODY',BODY).replace('OUTPUT',json.dumps(str(output))),encoding='utf8')
 includes=[p[:-3].replace('/','.') for p in STUBS]+['cn.town.TownThemeState']
 cmd=[str(a.java),'-Dflexlib='+str(a.sdk/'frameworks'),'-jar',str(a.sdk/'lib/mxmlc-cli.jar'),'+configname=air','-swf-version=44','-target-player=32.0','-compiler.float=false','-debug=true','-compiler.source-path='+str(root),'-compiler.library-path+='+str(a.candidate.parent/'town-theme-state.swc'),'-includes='+','.join(includes),'-output='+str(root/'test.swf'),str(root/'TownTest.as')]
 r=subprocess.run(cmd,capture_output=True,timeout=120);(root/'compile.log').write_bytes(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError((r.stdout+r.stderr).decode('utf8','replace'))
 version,header,tags=b.sc.parts(root/'test.swf');tag,=[t for t in tags if t[3]];target=b.view(tag[3]);receipts=[]
 labels=[SELECT,'pinball.common.data.town::TownContentRepository/sortTownContents|1']+['pinball.common.data.town::TownContentLogic/'+n+'|1' for n in ['isWithinPeriod','get_kind','getDisplayPriority','get_backgroundImage','get_backgroundBluredImage','get_bgm','get_maskImage']]+['pinball.common.time::TimeRangeWithoutYear/isWithin|1','pinball.context.global::GlobalLogic/getCustomTownBgm|1']
 for donor,ls in [(helper,list(b.view(helper).by_label)),(main,labels)]:
  source=b.view(donor);imp=b.p.Importer(target,source)
  for label in ls:
   di,=source.by_label[label];ti,=target.by_label[label];prior=target.a.bodies[ti]
   target.a.methods[prior[0]][3]=(target.a.methods[prior[0]][3]&~2)|(donor.methods[donor.bodies[di][0]][3]&2)
   target.a.bodies[ti]=imp.body(di,prior[0]);assert target.normalized(ti)==source.normalized(di),label
   b.p.check_body(target.a.bodies[ti],target.a);receipts.append({'label':label,'sourceCodeSha256':sha(donor.bodies[di][5]),'normalizedInstructionsCfgExact':True})
 # Exact eight-instruction native constructor prologue: scope, town capture, existing operations capture.
 source=b.view(baseline_main);di,=source.by_label[SELECT];ti,=target.by_label['cn.fixture::NativeTownBaseline/getTownContentByTime|1'];prior=target.a.bodies[ti];target.a.bodies[ti]=b.p.Importer(target,source).body(di,prior[0]);assert target.normalized(ti)==source.normalized(di)
 receipts.append({'label':SELECT,'kind':'complete-exact-R10-baseline-selector','sourceCodeSha256':sha(baseline_main.bodies[di][5]),'normalizedInstructionsCfgExact':True})
 donor=copy.deepcopy(main);source=b.view(donor);di,=source.by_label[RESPONSE];body=donor.bodies[di];rows=b.p.asm.decode(body[5]);prologue_length=5 if a.expect_r10_missing_hooks else 8;prefix=rows[:prologue_length]
 assert [donor.mn_name(x.args[0]) for x in prefix if x.op==0x60]==(['cn.content::ContentOperationsState'] if a.expect_r10_missing_hooks else ['cn.town::TownThemeState','cn.content::ContentOperationsState'])
 body[5]=b.p.asm.encode(prefix+b.p.asm.assemble([('returnvoid',)]))[0];body[6]=[]
 ti,=target.by_label['cn.fixture::LoginProbe/capture|1'];prior=target.a.bodies[ti];target.a.bodies[ti]=b.p.Importer(target,b.view(donor)).body(di,prior[0]);b.p.check_body(target.a.bodies[ti],target.a)
 receipts.append({'label':RESPONSE,'kind':'exact-native-constructor-prologue','instructionRange':[0,prologue_length],'wholeConstructorExecuted':False})
 payload=tag[2]+target.a.serialize();tag[1]=struct.pack('<HI',(82<<6)|63,len(payload))+payload;raw=header+b''.join(t[1] for t in tags);(root/'test.swf').write_bytes(b'FWS'+bytes([version])+struct.pack('<I',len(raw)+8)+raw)
 (root/'production-method-import.json').write_text(json.dumps({'candidateSwfSha256':sha(a.candidate.read_bytes()),'methods':receipts},indent=2)+'\n',encoding='utf8')
 (root/'application.xml').write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>cn.town.offline</id><versionNumber>1.0.0</versionNumber><filename>test</filename><initialWindow><content>test.swf</content><visible>false</visible></initialWindow></application>',encoding='utf8')
 output.unlink(missing_ok=True);r=subprocess.run([str(a.sdk/'bin/adl64.exe'),str(root/'application.xml')],capture_output=True,timeout=45);(root/'run.log').write_bytes(r.stdout+r.stderr)
 if not output.exists():raise RuntimeError('AIR result missing: '+str(r.returncode)+' '+(r.stdout+r.stderr).decode('utf8','replace'))
 result=json.loads(output.read_text(encoding='utf8'));result.update(candidateSwfSha256=sha(a.candidate.read_bytes()),gameExecuted=False,deviceTested=False,resourceDownloadExecuted=False,actualNativeBodies=len(labels),actualHelperBodies=len(helper.bodies),constructorPrologueOnly=True,tableAndAssetFixture=True,annualClockConversionFixture=True)
 if a.expect_r10_missing_hooks:
  result.update(observedPassed=result['passed'],expectedMissingHooksDetected=not result['passed'] and result.get('error')=='Error: future sixth ID outside built-in five accepted without SWF rebuild',nativeBodiesFromR10Baseline=True)
  result['passed']=result['expectedMissingHooksDetected'];r.returncode=0 if result['passed'] else r.returncode or 1
 output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
 if r.returncode or not result['passed']:raise RuntimeError('actual AVM2 town fixture failed')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['work','candidate','baseline','sdk','java']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--expect-r10-missing-hooks',action='store_true')
 run(p.parse_args())
if __name__=='__main__':main()
