"""Run only through client-background. Complete production bodies, typed recording boundary shells."""
from pathlib import Path
import argparse,copy,json,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
import bootstrap
from input_config import runtime,tool_root,repo_path,work_path
sys.path.insert(0,str(tool_root()/'lib'))
import abc_tools as a

def main():
 p=argparse.ArgumentParser();p.add_argument("--out",required=True);p.add_argument("--swf",required=True);p.add_argument("--sha",required=True);opt=p.parse_args();out=Path(opt.out).resolve()
 if out.exists() or not out.is_relative_to(work_path()):raise ValueError("fresh local output required")
 out.mkdir();src=out/"src";src.mkdir()
 cfg=runtime();ctx={**cfg,"repo":str(repo_path('.')),"swf":opt.swf,"swf_sha256":opt.sha,"tool_root":str(tool_root()),"run_root":str(out)}
 a.configure(ctx);builder,source,sv,identity=a.load_current(("pinball.scene.battle.view::BattleView",))
 owners={
 "pinball.scene.battle.viewInput::BattleViewInputSettings":{"isOtherBattleActionVisible":"public function isOtherBattleActionVisible():Boolean{throw new Error(\"ungrafted\");}"},
 "pinball.scene.battle.battle::Battle":{
 "preparation":"public function preparation(p0:GearPreparationTool):void{throw new Error(\"ungrafted\");}",
 "isRichMode":"public function isRichMode(p0:SkippableLogicKind):Boolean{throw new Error(\"ungrafted\");}",
 "__isRichMode__":"public function __isRichMode__(p0:SkippableLogicKind):Boolean{throw new Error(\"ungrafted\");}"},
 "pinball.scene.battle.battle::SkippableLogicKindTools":{"getLevel":"public static function getLevel(p0:SkippableLogicKind):int{throw new Error(\"ungrafted\");}"},
 "pinball.scene.battle.view::BattleView":{"show":"public function show(p0:int,p1:BattleViewKind,p2:int):int{throw new Error(\"ungrafted\");}"},
 "pinball.scene.battle.battle.effect::EffectManagerImpl":{"canPlayEffect":"public function canPlayEffect(p0:Boolean,p1:pinball.scene.battle.battle.effect.EffectKind):Boolean{throw new Error(\"ungrafted\");}","show":"public function show(p0:pinball.scene.battle.battle.effect.EffectKind):void{throw new Error(\"ungrafted\");}"},
 "jp.sipo.gipo.core::Gear":{"absorb":"public function absorb(p0:Class,p1:Object=null):Object{throw new Error(\"ungrafted\");}"},
 "pinball.context.global::GlobalLogic":{"_getApplicationOption":"public function _getApplicationOption():Object{throw new Error(\"ungrafted\");}","getApplicationOption":"public function getApplicationOption():ApplicationOptionPeek{throw new Error(\"ungrafted\");}"},
 "pinball.common.data.localStore::ApplicationOptionLogic":{
 "<ctor>":"", "store":"public function store():void{throw new Error(\"ungrafted\");}",
 "getWeightSavingModeOptionData":"public function getWeightSavingModeOptionData():Object{throw new Error(\"ungrafted\");}",
 "getTeammateEffectsVisible":"public function getTeammateEffectsVisible():Boolean{throw new Error(\"ungrafted\");}",
 "setTeammateEffectsVisible":"public function setTeammateEffectsVisible(p0:Boolean):void{throw new Error(\"ungrafted\");}",
 "cnTeammateEffectsVisibleFromRaw":"public static function cnTeammateEffectsVisibleFromRaw(p0:Object):Boolean{throw new Error(\"ungrafted\");}",
 "cnTeammateEffectsVisibleFromBattle":"public static function cnTeammateEffectsVisibleFromBattle(p0:Battle):Boolean{throw new Error(\"ungrafted\");}"}}

 selections=[]
 for owner,methods in owners.items():
  for name in methods:
   static=name in ("getLevel","cnTeammateEffectsVisibleFromRaw","cnTeammateEffectsVisibleFromBattle");prefix=owner+("$" if static else "")+"/"+name;hits=[l for l in sv.by_label if l==prefix or l.startswith(prefix+"|")];assert len(hits)==1;selections+=hits
 names=set(owners)|{"pinball.scene.battle.view::BattleViewKind","jp.sipo.gipo.core::GearPreparationTool","pinball.scene.battle.battle.effect::EffectKind","pinball.common.data.localStore::ApplicationOptionPeek","haxe.ds::Option","jp.sipo.gipo.core::GearPhase","::Std"}
 for label in selections:
  bi,=sv.by_label[label]
  info=source.methods[source.bodies[bi][0]]
  for t in [info[0]]+info[1]:
   n=source.mn_name(t) if t else '*'
   if '::' in n:names.add(n)
  for x in builder.asm.decode(source.bodies[bi][5]):
   if x.name in ("coerce","astype","getlex","findpropstrict","constructprop") and source.multinames[x.args[0]][0]==7:
    n=source.mn_name(x.args[0]);
    if "::" in n:names.add(n)
 for n in sorted(names):
  pkg,cls=n.split("::");extra="".join(owners.get(n,{}).values())
  if n in owners:
   fields=set()
   for label in selections:
    if label.startswith(n+"/") or label.startswith(n+"$/"):
     bi,=sv.by_label[label]
     for x in builder.asm.decode(source.bodies[bi][5]):
      if x.name=="findproperty":
       field=source.mn_name(x.args[0])
       if "::" not in field and field not in owners[n] and field not in ("index","params"):fields.add(field)
   extra+=''.join('public var '+f+':*;' for f in sorted(fields))
  if cls=="Boot":extra+='public static var skip_constructor:Boolean=false;public static var lastError:*;'
  if cls=="Std":extra+='public static function string(v:*):String{return String(v);}'
  if cls=="MemberPeek":extra+='public var kind:SquadKind;public function getSquadKind():SquadKind{return kind;}'
  if cls=="ActionEffectPeek":extra+='public var hostile:Boolean=false;public function isHostile():Boolean{return hostile;}'
  if cls=="BallPeek":extra+='public var primary:Boolean;public function isPrimary():Boolean{return primary;}'
  if cls=="BattleSceneDiffuseKey":extra+='public static var PlayerMode:Object={};'
  if cls=="SkippableLogicKind":extra+='public static var Action:SkippableLogicKind=new SkippableLogicKind();'

  if cls=='LocalStoreForLogic':extra+='public var saves:int=0;public var last:Object;public function saveApplicationOption(v:Object):void{saves++;last=v;}'
  imports=''.join('import '+n.replace('::','.').lstrip('.')+';' for n in sorted(names))
  if cls=='Gear':extra=extra.replace('public var phase:*;','public var phase:GearPhase;')
  if cls=='ApplicationOptionPeek':text='package '+pkg+' {public interface '+cls+' {}}'
  else:
   parent=' extends Error' if cls in ('SipoError','ClientError') else ' implements ApplicationOptionPeek' if cls=='ApplicationOptionLogic' else ''
   ctor='public function '+cls+'(...args){'+('super(String(args[0]));' if cls in ('SipoError','ClientError') else '')+'}'
   text='package '+pkg+' {'+imports+'public dynamic class '+cls+parent+' {public var index:int;public var params:Array;'+ctor+extra+'}}'
  path=(src/(n.replace("::","/").replace(".","/").lstrip("/")+".as")).resolve()
  if not path.is_relative_to(src.resolve()):raise ValueError("fixture path outside source root")
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding="utf-8")
 (src/"air_harness.as").write_bytes((ROOT/"air_harness.as").read_bytes())
 sdk=Path(cfg['sdk']);cmd=[cfg['java'],'-Xmx1g','-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-swf-version=44','-target-player=32.0','-debug=true','-compress=false','-compiler.source-path='+str(src),'-includes='+','.join(n.replace('::','.').lstrip('.') for n in sorted(names)),'-output='+str(out/'template.swf'),str(src/'air_harness.as')]
 run=subprocess.run(cmd,cwd=out,capture_output=True,timeout=120);(out/'compile.log').write_bytes(run.stdout+run.stderr);(out/'compile-receipt.json').write_text(json.dumps({'command':cmd,'exit_code':run.returncode,'sources':{str(p.relative_to(src)):a.sha(p.read_bytes()) for p in src.rglob('*.as')}},indent=2),encoding='utf-8')
 if run.returncode:raise RuntimeError('compile failed')
 template=(out/'template.swf').read_bytes();target=builder.abcfmt.ABC(list(a.raw_units(template))[0][1]);tv=a.view(target);aliases=[]
 for label in selections:
  ti,=tv.by_label[label]
  mid=target.bodies[ti][0]
  for row in target.instances:
   for t in row[6]:
    if t.data[0]=='method' and t.data[2]==mid:aliases.append((row,copy.deepcopy(t)))
 if __import__('os').environ.get('LITE195_ONLY_P1'):selections=[l for l in selections if 'isOtherBattleActionVisible' in l]
 mapping=a.graft(target,source,selections)
 # Preserve the compiled public call alias; actual target body/info is still the donor's exact method.
 for row,trait in aliases:
  if not any(target.mn_name(t.name)==target.mn_name(trait.name) for t in row[6]):row[6].append(trait)
 # BallPeek's real interface QName is used by production P2b; add a recording-shell alias.
 imp=builder.Importer(a.view(target),sv)
 for row in target.instances:
  if target.mn_name(row[0])=='pinball.scene.battle.battle.squad.ball::BallPeek':
   t=next(t for t in row[6] if t.data[0]=='method' and target.mn_name(t.name)=='isPrimary')
   for i,mn in enumerate(source.multinames):
    if mn and mn[0]==7 and source.mn_name(i)=='pinball.scene.battle.battle.squad.ball:BallPeek::isPrimary':
     t.name=imp.pool('multinames',i)
 for owner,method,match in [('pinball.scene.battle.battle.squad.member::MemberPeek','getSquadKind','MemberPeek::getSquadKind'),('pinball.scene.battle.battle.action::ActionEffectPeek','isHostile','ActionEffectPeek::isHostile')]:
  row,=[r for r in target.instances if target.mn_name(r[0])==owner]
  trait=next(t for t in row[6] if t.data[0]=='method' and target.mn_name(t.name)==method)
  qn,=[i for i,mn in enumerate(source.multinames) if mn and mn[0]==7 and source.mn_name(i).endswith(match)]
  trait.name=imp.pool('multinames',qn)
 # Exact interface QName aliases for native option getter and store boundary.
 for owner,method,match in [('pinball.common.data.localStore::LocalStoreForLogic','saveApplicationOption','LocalStoreForLogic::saveApplicationOption')]:
  row,=[r for r in target.instances if target.mn_name(r[0])==owner]
  trait=next(t for t in row[6] if t.data[0]=='method' and target.mn_name(t.name)==method)
  qn,=[i for i,mn in enumerate(source.multinames) if mn and mn[0]==7 and source.mn_name(i).endswith(match)]
  trait.name=imp.pool('multinames',qn)
 final=a.replace_abc(template,target);(out/'Harness.swf').write_bytes(final);parsed=builder.abcfmt.ABC(list(a.raw_units(final))[0][1]);proof=a.verify_grafts(parsed,source,mapping)
 (out/'proof.json').write_text(json.dumps({'identity':identity,'real_methods':proof,'harness_sha256':a.sha(final),'shell_classes':len(names),'limits':['Complete actual production render, new preference/reader and native Gear/GlobalLogic/weight getter bodies imported and read back; only recorded branches execute.','External diffuser lookup, local-store persistence sink, GPU/view constructors and errors are typed recording boundaries; no empty original option getter.','Battle.preparation executes actual prologue and flags then stops at explicit getBattleDebugSettings sentinel; full initialization is not exercised.','No GPU/device/real multiplayer or performance measurement.']},indent=2),encoding='utf-8')
 launcher=out/'Launcher.as';launcher.write_text("""package {import flash.display.*;import flash.events.*;import flash.net.URLRequest;import flash.filesystem.*;import flash.desktop.NativeApplication;public class Launcher extends Sprite {public function Launcher(){var l:Loader=new Loader();l.uncaughtErrorEvents.addEventListener(UncaughtErrorEvent.UNCAUGHT_ERROR,function(e:UncaughtErrorEvent):void{e.preventDefault();var f:File=new File(File.applicationDirectory.nativePath).resolvePath(\"result.json\");var fs:FileStream=new FileStream();fs.open(f,FileMode.WRITE);fs.writeUTFBytes(JSON.stringify({passed:false,launcher:true,error:String(e.error),stack:e.error is Error?Error(e.error).getStackTrace():null}));fs.close();NativeApplication.nativeApplication.exit(1);});addChild(l);l.load(new URLRequest(\"Harness.swf\"));}}}""",encoding='utf-8')
 cmd=[cfg['java'],'-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-debug=true','-output='+str(out/'Launcher.swf'),str(launcher)]
 run=subprocess.run(cmd,cwd=out,capture_output=True,timeout=60);(out/'launcher-compile.log').write_bytes(run.stdout+run.stderr);assert run.returncode==0
 app=out/'application.xml';app.write_text(('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.lite195.RANDOM_PLACEHOLDER</id><versionNumber>1.0.0</versionNumber><filename>lite195</filename><initialWindow><content>Launcher.swf</content><visible>false</visible></initialWindow></application>').replace('RANDOM_PLACEHOLDER',__import__('re').sub('[^A-Za-z0-9]','',out.name)),encoding='utf-8')
 cmd=[str(sdk/'bin/adl.exe'),'-cmd',str(app)];
 try:run=subprocess.run(cmd,cwd=out,capture_output=True,timeout=25)
 except subprocess.TimeoutExpired as e:
  (out/'adl.log').write_bytes((e.stdout or b'')+(e.stderr or b''));raise
 (out/'adl.log').write_bytes(run.stdout+run.stderr)
 result=json.loads((out/'result.json').read_text(encoding='utf-8'));print(json.dumps(result,ensure_ascii=False));assert run.returncode==0 and result['passed'] and result['assertions']>=100
if __name__=='__main__':main()
