"""Narrow actual-body regression. Every invocation requires run_bounded.
Compile/ADL phases additionally require the existing client-background wrapper.
"""
from pathlib import Path
import argparse,copy,json,subprocess,sys
ROOT=Path(__file__).resolve().parent
TASK=ROOT.parents[1]
sys.dont_write_bytecode=True
import bootstrap
from input_config import input_path,runtime,work_path,repo_path,tool_root
import abc_tools as a
BEFORE=input_path('settings_swf')
AFTER=input_path('tutorial_swf')
HASHES={'before':'3c56f08c8b30ae75ae71908a699e703764dcfca0bc64d1fb91d866e2c61bfaef','after':'215860d0f3933b352c377309c68943a3978a80ab5c5beb209c9b94382191e325'}
WORK=work_path('tutorial/attempt01')
CFG=runtime()
def setup():
 a.configure({**CFG,'repo':str(repo_path()),'swf':str(BEFORE),'swf_sha256':HASHES['before'],'tool_root':str(tool_root()),'run_root':str(work_path('tutorial'))})
 return a.load_current(('pinball.scene.gacha.top.common::GachaSceneViewBase',))
def typ(abc,n):return abc.mn_name(n).replace('::','.').lstrip('.') if n else '*'
def put(root,key,text):
 path=(root/key).resolve()
 if not path.is_relative_to(root.resolve()):raise ValueError('source escaped fixture')
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,'utf-8')
def label(v,p):
 hits=[x for x in v.by_label if x==p or x.startswith(p+'|')]
 assert len(hits)==1,(p,hits)
 return hits[0]
def prepare():
 if WORK.exists():raise FileExistsError('fresh attempt required')
 WORK.mkdir(parents=True);src=WORK/'src';src.mkdir()
 b,abc,v,identity=setup()
 owners={
 'pinball.common.data.gacha::TutorialGachaLogic':None,
 'pinball.common.data.gacha::TutorialGachaFeatureContentLogic':['<ctor>'],
 'pinball.common.data.gacha::GachaFeatureContentAssetKind':['<ctor>','Image'],
 'haxe.ds::Option':['<ctor>'],
 'pinball.common.data.gacha::GachaLogic':['get_showPeriod','isComeback','isStarsGacha'],
 'pinball.scene.gacha.top.common::GachaSceneViewBase':['setupText']}
 selections=[];files={};allnames=set(owners)
 for owner,names in owners.items():
  for l in v.by_label:
   if (l.startswith(owner+'/') or l.startswith(owner+'$/')) and (names is None or any(l.split('/')[-1].split('|')[0]==x for x in names)):
    selections.append(l)
 for l in selections:
  bi,=v.by_label[l];info=abc.methods[abc.bodies[bi][0]]
  for t in [info[0]]+info[1]:
   if t and '::' in abc.mn_name(t):allnames.add(abc.mn_name(t))
  for ins in b.asm.decode(abc.bodies[bi][5]):
   if ins.name in ('getlex','findpropstrict','coerce','astype','constructprop') and abc.multinames[ins.args[0]][0]==7:
    q=abc.mn_name(ins.args[0]);
    if '::' in q:allnames.add(q)
 for owner in owners:
  row=next(x for x in abc.instances if abc.mn_name(x[0])==owner)
  for t in row[6]:
   if t.data[0]=='slot' and '::' in abc.mn_name(t.data[2]):allnames.add(abc.mn_name(t.data[2]))
 allnames.update(['pinball.scene.gacha.top.common::GachaSceneBasePeek','pinball.common.data.gacha::GachaPeekForGachaTopScene','pinball.ui.display::UiDisplayObjectContainer','pinball.ui.display.text::UiText','pinball.common.time._AppTime::AppTime_Impl_'])
 imports=''.join('import '+q.replace('::','.').lstrip('.')+';' for q in sorted(allnames))
 def decl(owner):
  pkg,cls=owner.split('::');row=next(x for x in abc.instances if abc.mn_name(x[0])==owner)
  fields=''
  # All actual Tutorial slots retained, no id or dynamic prototype added.
  if 'Tutorial' in cls or cls in ('Option','GachaFeatureContentAssetKind'):
   fields=''.join('public var '+abc.mn_name(t.name)+':'+typ(abc,t.data[2])+';' for t in row[6] if t.data[0]=='slot')
  if cls=='GachaLogic':fields='public var id:int;public var values:Object;'
  if cls=='GachaSceneViewBase':fields='public var basePeek:GachaSceneBasePeek;public var periodLayout:UiDisplayObjectContainer;public var view:Object;'
  methods='';hasctor=False
  for l in selections:
   if not (l.startswith(owner+'/') or l.startswith(owner+'$/')):continue
   name=l.split('/')[-1].split('|')[0];bi,=v.by_label[l];info=abc.methods[abc.bodies[bi][0]]
   if name=='<cinit>':continue
   args=','.join('p'+str(i)+':'+typ(abc,t)+('=null' if typ(abc,t) not in ('int','uint','Number','Boolean') else '=0') for i,t in enumerate(info[1]))
   if name=='<ctor>':methods+='public function '+cls+'('+args+'){throw new Error("ungrafted ctor");}';hasctor=True
   else:methods+='public '+('static ' if '$/' in l else '')+'function '+name+'('+args+'):'+typ(abc,info[0])+'{throw new Error("ungrafted method");}'
  if not hasctor:methods+='public function '+cls+'(){}'
  if cls=='Option':fields+='public static var None:Option=new Option("None",1,[]);'
  return 'package '+pkg+' {'+imports+'public class '+cls+' {'+fields+methods+'}}'
 for q in sorted(allnames):
  pkg,cls=q.split('::')
  if q in owners:text=decl(q)
  elif cls in ('GachaSceneBasePeek','GachaPeekForGachaTopScene'):text='package '+pkg+' {public interface '+cls+' {}}'
  elif cls=='Boot':text='package flash {public class Boot{public static var skip_constructor:Boolean=false;public static var lastError:*;}}'
  elif cls=='TutorialGachaValues':
   text='package '+pkg+' {public class '+cls+'{public var title:String="tutorial";public var banner_image:String="banner";public var once_cost:int=1;public var ten_times_cost:int=10;public var daily_payment_cost:int=0;public var odds_rarity_string_id:String="odds";public var movie_id:String="movie";public var feature_image:String="feature";public var start_time:Number=100;public var end_time:Number=500;}}'
  elif cls=='UiText':text='package '+pkg+' {public class UiText{public var text:String="sentinel";public var rawTextField:Object={wordWrap:true};public function set_text(s:String):String{text=s;return s;}public function get_textWidth():Number{return 740;}public function get_textHeight():Number{return 46;}public function set_autoSize(s:String):String{return s;}public function set_textWidth(v:Number):Number{return v;}public function set_textHeight(v:Number):Number{return v;}public function set_autoScale(v:Boolean):Boolean{return v;}}}'
  elif cls=='UiDisplayObjectContainer':text='package '+pkg+' {import pinball.ui.display.text.UiText;public class UiDisplayObjectContainer{public var visible:Boolean=true;public var text:UiText=new UiText();public var calls:int=0;public function getText(k:String,p:Object):UiText{calls++;return text;}}}'
  elif cls=='AppTime_Impl_':text='package '+pkg+' {public class AppTime_Impl_{public static var calls:int=0;public static function toStandardDateFormatString(v:Number):String{calls++;return "DATE("+v+")";}}}'
  else:text='package '+pkg+' {public class '+cls+' {public function '+cls+'(...args){}}}'
  put(src,q.replace('::','/').replace('.','/').lstrip('/')+'.as',text)
 # Exact interface QNames used by setupText; public names serve helper's Object dispatch.
 put(src,'fixture/BasePeek.as','package fixture {import pinball.scene.gacha.top.common.GachaSceneBasePeek;import pinball.common.data.gacha.GachaPeekForGachaTopScene;public class BasePeek implements GachaSceneBasePeek{public var gacha:GachaPeekForGachaTopScene;public var startCalls:int=0;public var endCalls:int=0;public function getGacha():GachaPeekForGachaTopScene{return gacha;}public function getGachaStartTime():Number{startCalls++;return 100;}public function getGachaEndTime():Number{endCalls++;return 500;}public namespace Holder="pinball.scene.gacha:GachaHolder";Holder function getGacha():GachaPeekForGachaTopScene{return gacha;}public namespace Peek="pinball.scene.gacha.top.common:GachaSceneBasePeek";Peek function getGachaStartTime():Number{return getGachaStartTime();}Peek function getGachaEndTime():Number{return getGachaEndTime();}}}')
 for cls in ('TutorialGachaLogic','GachaLogic'):
  path=src/('pinball/common/data/gacha/'+cls+'.as');text=path.read_text();text=text.replace('public class '+cls+' {','public class '+cls+' implements GachaPeekForGachaTopScene {')
  text=text[:-2]+'public namespace NativePeek="pinball.common.data.gacha:GachaPeekForGachaTopScene";NativePeek function get_showPeriod():Boolean{return get_showPeriod();}}}'
  path.write_text(text,'utf-8')
 put(src,'cn/content/ContentOperationsState.as',repo_path('client-patch/content-operations/src/cn/content/ContentOperationsState.as').read_text('utf-8'))
 put(src,'Harness.as',(ROOT/'Harness.as').read_text('utf-8'))
 (WORK/'plan.json').write_text(json.dumps({'identity':identity,'selections':selections,'includes':[q.replace('::','.').lstrip('.') for q in sorted(allnames)],'helperSource':str(repo_path('client-patch/content-operations/src/cn/content/ContentOperationsState.as'))},indent=2),'utf-8')
 print('prepared',len(selections),'main methods; exact helper follows')
def compile_(launcher_only=False):
 plan=json.loads((WORK/'plan.json').read_text());sdk=Path(CFG['sdk'])
 for source,output in [(WORK/'src/Harness.as',WORK/'template.swf'),(ROOT/'Launcher.as',WORK/'Launcher.swf')]:
  if launcher_only and output.name=='template.swf':continue
  cmd=[CFG['java'],'-Xmx768m','-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-swf-version=44','-target-player=32.0','-debug=true','-compress=false','-compiler.source-path='+str(WORK/'src'),'-output='+str(output)]
  if output.name=='template.swf':cmd+=['-includes='+','.join(plan['includes'])]
  cmd+=[str(source)];r=subprocess.run(cmd,capture_output=True,timeout=65);output.with_suffix('.log').write_bytes(r.stdout+r.stderr)
  if r.returncode:raise RuntimeError('compile failed '+output.name)
 if launcher_only:
  for mode in ('before','after'):(WORK/mode/'Launcher.swf').write_bytes((WORK/'Launcher.swf').read_bytes())
 print('compiled narrow template+launcher')
def graft():
 b,main,v,identity=setup();plan=json.loads((WORK/'plan.json').read_text());template=(WORK/'template.swf').read_bytes()
 target=b.abcfmt.ABC(list(a.raw_units(template))[0][1]);mapping=a.graft(target,main,plan['selections'])
 # Source class is sealed. Keep exactly the native Tutorial slot names/types.
 ti=next(x for x in target.instances if target.mn_name(x[0])=='pinball.common.data.gacha::TutorialGachaLogic')
 si=next(x for x in main.instances if main.mn_name(x[0])=='pinball.common.data.gacha::TutorialGachaLogic')
 assert ti[2]&1 and si[2]&1
 assert sorted((target.mn_name(t.name),target.mn_name(t.data[2])) for t in ti[6] if t.data[0]=='slot')==sorted((main.mn_name(t.name),main.mn_name(t.data[2])) for t in si[6] if t.data[0]=='slot')
 assert not any(target.mn_name(t.name)=='id' for t in ti[6])
 # Empty fixture interface has no auto-vtable map: its explicit QName aliases are retained.
 for mode,path in [('before',BEFORE),('after',AFTER)]:
  raw=path.read_bytes();assert a.sha(raw)==HASHES[mode]
  helperunits=[(n,u) for n,u in a.raw_units(raw) if n=='content_operations'];assert len(helperunits)==1
  helper=b.abcfmt.ABC(helperunits[0][1]);candidate=copy.deepcopy(target)
  hm=a.graft(candidate,helper,list(a.view(helper).by_label))
  final=a.replace_abc(template,candidate);out=WORK/mode;out.mkdir();(out/'Harness.swf').write_bytes(final)
  parsed=b.abcfmt.ABC(list(a.raw_units(final))[0][1]);proof={'input':str(path),'inputSha256':HASHES[mode],'main':a.verify_grafts(parsed,main,mapping),'helper':a.verify_grafts(parsed,helper,hm),'sealedTutorialExactSlotShape':True,'tutorialHasNoId':True,'harnessSha256':a.sha(final)}
  (out/'proof.json').write_text(json.dumps(proof,indent=2),'utf-8');(out/'Launcher.swf').write_bytes((WORK/'Launcher.swf').read_bytes())
  (out/'mode.txt').write_text(mode,'utf-8')
  (out/'application.xml').write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.tutorialgacha.'+mode+'</id><versionNumber>1.0.0</versionNumber><filename>tutorial</filename><initialWindow><content>Launcher.swf</content><visible>false</visible></initialWindow></application>','utf-8')
 print('actual bodies grafted and fully read back')
def run(mode):
 out=WORK/mode;cmd=[str(Path(CFG['sdk'])/'bin/adl.exe'),'-cmd',str(out/'application.xml')]
 try:r=subprocess.run(cmd,cwd=out,capture_output=True,timeout=15)
 except subprocess.TimeoutExpired as e:
  (out/'adl.log').write_bytes((e.stdout or b'')+(e.stderr or b''));raise
 (out/'adl.log').write_bytes(r.stdout+r.stderr)
 result=json.loads((out/'result.json').read_text());print(json.dumps(result,ensure_ascii=False));assert r.returncode==0 and result['passed']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','compile','launcher','graft','before','after']);p.add_argument('--attempt',default='attempt01');opt=p.parse_args()
 WORK=(work_path('tutorial')/opt.attempt).resolve()
 if not WORK.is_relative_to(work_path('tutorial')) or WORK.parent!=work_path('tutorial'):raise ValueError('direct task-local attempt required')
 {'prepare':prepare,'compile':compile_,'launcher':lambda:compile_(True),'graft':graft,'before':lambda:run('before'),'after':lambda:run('after')}[opt.phase]()
