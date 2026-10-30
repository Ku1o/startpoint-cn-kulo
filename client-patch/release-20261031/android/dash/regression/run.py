"""Small actual-caller/callee AVM2 regression; all phases require bounded Jobs."""
from pathlib import Path
import argparse,copy,json,subprocess,sys
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
import bootstrap
from input_config import input_path,input_sha,runtime,repo_path,work_path,tool_root
import abc_tools as a
CFG=runtime()
def typ(n):return n.replace('::','.').lstrip('.')
def write(src,key,value):
 p=(src/key).resolve()
 if not p.is_relative_to(src.resolve()):raise ValueError('source root escape')
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,'utf-8')
def configure(swf,sha):
 a.configure({**CFG,'repo':str(repo_path()),'swf':str(swf),'swf_sha256':sha,'tool_root':str(tool_root()),'run_root':str(work_path('dash'))})
 return a.load_current(('pinball.scene.battle.battle.squad.member::MemberImpl',))
def prepare(work,swf,sha):
 if work.exists():raise FileExistsError('fresh attempt required')
 work.mkdir(parents=True);src=work/'src';src.mkdir();b,abc,v,identity=configure(swf,sha)
 groups={
 'pinball.scene.battle.battle.squad.ball::BallImpl':['wfxTryDashReplacement'],
 'pinball.scene.battle.battle.squad.member::MemberImpl':['wfxRunDashAction','getElement'],
 'pinball.online.battle.address::InstantAbilityAddress':['<ctor>','$Instant'],
 'pinball.common.data.ability.instant::InstantAbilityInstantCharacterContent':['<ctor>','$InvokeSkill'],
 'pinball.common.data.ability::AbilityPowerValue':['<ctor>','$fromSlv'],
 'pinball.common.data.ability::AbilityPowerValueCalculateMethod':['<ctor>','$LevelScale'],
 'pinball.scene.battle.battle._SLv::SLv_Impl_':['$toInt'],
 'pinball.common.data.general._ElementKind::ElementKind_Impl_':['$toColorlessable'],
 'pinball.scene.battle.battle.squad.ball::BallState':['<ctor>','$Escaping'],
 'haxe.ds::Option':['<ctor>','$Some'],
 }
 def label(q,spec):
  static=spec.startswith('$');p=q+('$' if static else '')+'/'+spec.lstrip('$')
  hit=[x for x in v.by_label if x==p or x.startswith(p+'|')];assert len(hit)==1,(p,hit);return hit[0]
 # Address argument is a real native enum object, not a dynamic fake address.
 instant=label('pinball.online.battle.address::InstantAbilityAddress','$Instant');bi,=v.by_label[instant]
 addr=abc.mn_name(abc.methods[abc.bodies[bi][0]][1][1]);groups[addr]=['<ctor>']
 labels=[];methods={};names=set(groups);rows={abc.mn_name(r[0]):(i,r) for i,r in enumerate(abc.instances)}
 for q,ms in groups.items():
  methods[q]=[]
  for m in ms:
   l=label(q,m);labels.append(l);bi,=v.by_label[l];info=abc.methods[abc.bodies[bi][0]]
   methods[q].append((m.startswith('$'),m.lstrip('$'),abc.mn_name(info[0]) if info[0] else '*',[abc.mn_name(n) if n else '*' for n in info[1]]))
   for t in [info[0]]+info[1]:
    n=abc.mn_name(t) if t else '*'
    if '::' in n:names.add(n)
   for ins in b.asm.decode(abc.bodies[bi][5]):
    if ins.name in ('coerce','astype','getlex','constructprop','findpropstrict') and abc.multinames[ins.args[0]][0]==7:
     n=abc.mn_name(ins.args[0]);
     if '::' in n:names.add(n)
 imports=''.join('import '+typ(n)+';' for n in sorted(names))
 extras={
 'Boot':'public static var skip_constructor:Boolean=false;public static var lastError:*;',
 'MemberImpl':'public var calls:int=0;public var received:Array;public function isDead():Boolean{return false;}public function applyInstantAbility(...args):void{calls++;received=args;}',
 'BallImpl':'''public static var wfxDashPending:flash.utils.Dictionary;public static var config:Array=["wfx_dash_v2","fixture_skill",0,7];public static function wfxParseDashLeaderTags(t:Object):Array{return config;}public static function wfxFilterLeaderDash(c:Array,m:MemberImpl):Array{return c;}public function wfxFindDashEnemy():Object{return {present:true};}public function wfxDashV2Landing(c:Array):Object{return {x:8,y:9};}public function get_vx():Number{return 12;}public function get_vy():Number{return -4;}public var changed:Object;public function changeState(s:Object):void{changed=s;}''',
 'SLv_Impl_':'public static var MAX_SLV:int=17;',
 }
 for q in sorted(names):
  pkg,cls=q.split('::');fields={};decl='';ctor=None
  if q in groups:
   ci,row=rows[q]
   for t in row[6]:
    if t.data[0]=='slot':fields[abc.mn_name(t.name).split('::')[-1]]='*'
   # All native enum storage names are retained, but unused runtime graph types
   # are finite declaration ports. Only selected complete actual bodies execute.
   for static,method,ret,args in methods[q]:
    params=','.join('p'+str(i)+':'+typ(t)+('=false' if t=='Boolean' else '=0' if t in ('int','uint','Number') else '=null') for i,t in enumerate(args))
    if method=='<ctor>':ctor='public function '+cls+'('+params+'){throw new Error("ungrafted ctor");}'
    else:decl+='public '+('static ' if static else '')+'function '+method+'('+params+'):'+typ(ret)+'{throw new Error("ungrafted");}'
  if cls=='BallImpl':fields.update({x:'*' for x in ('squad','zoneManager','escapePoint','body','x','y')})
  if cls=='Boot':fields={}
  if ctor is None:ctor='public function '+cls+'(...args){}'
  if q not in groups and cls not in ('Boot',):fields.update(index='int',params='Array',tag='String')
  if cls=='MemberImpl':fields.update(address='*',originMemberIndex='int',source='*')
  text='package '+pkg+' {'+imports+'public class '+cls+' {'+''.join('public var '+n+':'+t+';' for n,t in fields.items())+ctor+decl+extras.get(cls,'')+'}}'
  write(src,q.replace('::','/').replace('.','/').lstrip('/')+'.as',text)
 caller=next(x for x in labels if '/wfxTryDashReplacement|' in x);bi,=v.by_label[caller];escape=abc.mn_name(abc.methods[abc.bodies[bi][0]][1][0])
 write(src,'NativeInput.as','package {'+imports+'public class NativeInput{public static function state():'+typ(escape)+'{var s:'+typ(escape)+'=new '+typ(escape)+'();s.index=1;return s;}public static function address():'+typ(addr)+'{return new '+typ(addr)+'("fixture-member",77,[]);}}}')
 for f in ('Harness.as','Launcher.as','Ports.as'):write(src,f,(ROOT/f).read_text('utf-8'))
 (work/'plan.json').write_text(json.dumps({'identity':identity,'swf':str(swf),'sha':sha,'labels':labels,'includes':[typ(n) for n in sorted(names)],'caller':caller,'helper':next(x for x in labels if '/wfxRunDashAction|' in x),'slot_boundary':'SLv.MAX_SLV seeded17 sentinel; actual toInt/fromSlv/LevelScale/constructor must propagate it. Owning global boot initializer not executed.'},indent=2)+'\n','utf-8')
 print(json.dumps({'methods':len(labels),'classes':len(names),'caller':caller,'helper':next(x for x in labels if '/wfxRunDashAction|' in x)}))
def compile_(work):
 p=json.loads((work/'plan.json').read_text());sdk=Path(CFG['sdk'])
 for name in ('Harness','Launcher'):
  output=work/('template.swf' if name=='Harness' else 'Launcher.swf')
  if output.exists():raise FileExistsError(output)
  cmd=[CFG['java'],'-Xmx768m','-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-debug=true','-swf-version=44','-compress=false','-compiler.source-path='+str(work/'src'),'-output='+str(output)]
  if name=='Harness':cmd+=['-includes='+','.join(p['includes'])]
  cmd+=[str(work/'src'/(''+name+'.as'))];r=subprocess.run(cmd,cwd=work,capture_output=True,timeout=50);output.with_suffix('.log').write_bytes(r.stdout+r.stderr)
  if r.returncode:raise RuntimeError('compile failed '+name)
def graft(work):
 p=json.loads((work/'plan.json').read_text());b,source,sv,identity=configure(p['swf'],p['sha']);template=(work/'template.swf').read_bytes();target=b.abcfmt.ABC(list(a.raw_units(template))[0][1]);mapping=a.graft(target,source,p['labels'])
 for mode in ('before','after'):
  out=work/mode
  if out.exists():raise FileExistsError(out)
  out.mkdir();candidate=copy.deepcopy(target);member=next(r for r in candidate.instances if candidate.mn_name(r[0])=='pinball.scene.battle.battle.squad.member::MemberImpl');assert member[2]&1
  if mode=='before':member[6]=[t for t in member[6] if candidate.mn_name(t.name)!='wfxRunDashAction']
  assert any(candidate.mn_name(t.name)=='wfxRunDashAction' for t in member[6])==(mode=='after')
  final=a.replace_abc(template,candidate);(out/'Harness.swf').write_bytes(final);parsed=b.abcfmt.ABC(list(a.raw_units(final))[0][1]);kept=[m for m in mapping if mode=='after' or m['source_label']!=p['helper']]
  proof={'production':identity,'mode':mode,'sealedMember':True,'helperTraitPresent':mode=='after','actual_methods':a.verify_grafts(parsed,source,kept),'harness_sha256':a.sha(final),'boundaries':['Before uses same sealed finite Member declaration with only the absent helper trait removed, matching actual old trait absence; full Member ctor not executed.','Complete actual TryDash caller and33instr helper execute; tag filter, landing, zone, squad, physical body and applyInstantAbility are explicit recording ports.','Native Instant/InvokeSkill/fromSlv/LevelScale/constructors/toInt/getElement/toColorlessable/Escaping bodies imported/readback.','MAX_SLV=17 controlled sentinel; full native boot initializer and actual skill effects/physics are not executed.']}
  (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n','utf-8');(out/'Launcher.swf').write_bytes((work/'Launcher.swf').read_bytes());(out/'mode.txt').write_text(mode,'utf-8')
  (out/'application.xml').write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.dash.'+work.name+'.'+mode+'</id><versionNumber>1.0.0</versionNumber><filename>dash</filename><initialWindow><content>Launcher.swf</content><visible>false</visible></initialWindow></application>','utf-8')
 print('grafted and fully readback')
def run(work,mode):
 out=work/mode
 if (out/'result.json').exists():raise FileExistsError('fresh result required')
 try:r=subprocess.run([str(Path(CFG['sdk'])/'bin/adl.exe'),'-cmd',str(out/'application.xml')],cwd=out,capture_output=True,timeout=15)
 except subprocess.TimeoutExpired as e:(out/'adl.log').write_bytes((e.stdout or b'')+(e.stderr or b''));raise
 (out/'adl.log').write_bytes(r.stdout+r.stderr);result=json.loads((out/'result.json').read_text());print(json.dumps(result,ensure_ascii=False));assert r.returncode==0 and result['passed']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','compile','graft','before','after'));p.add_argument('--attempt',default='air01');p.add_argument('--swf');p.add_argument('--sha');args=p.parse_args();work=(work_path('dash')/args.attempt).resolve()
 if work.parent!=work_path('dash'):raise ValueError('owned direct attempt required')
 {'prepare':lambda:prepare(work,args.swf or input_path('final_swf'),args.sha or input_sha('final_swf')),'compile':lambda:compile_(work),'graft':lambda:graft(work),'before':lambda:run(work,'before'),'after':lambda:run(work,'after')}[args.phase]()
