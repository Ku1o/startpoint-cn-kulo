"""Phase runner; use exclusive run_bounded and background wrappers, never directly.

The fixture plan is written only after actual native metadata is inspected. No
parser, enum factory or cumulative-loss implementation is supplied by this file.
"""
from pathlib import Path
import argparse,copy,json,subprocess,sys
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
import bootstrap
from input_config import input_path,input_sha,runtime,repo_path,work_path,tool_root
import abc_tools as a
from fixture_utils import write_sources
CFG=runtime()

def configure(plan):
 a.configure({**CFG,'repo':str(repo_path()),'swf':plan['after']['path'],'swf_sha256':plan['after']['sha256'],'tool_root':str(tool_root()),'run_root':str(work_path('trigger9000'))})
 return a.load_current(('pinball.master.generated::LeaderAbilityValues',))

def compile_template(work,plan):
 sdk=Path(CFG['sdk'])
 for source,output in [(work/'src/Harness.as',work/'template.swf'),(work/'src/Launcher.as',work/'Launcher.swf')]:
  if output.exists():raise FileExistsError('fresh compile output required')
  command=[CFG['java'],'-Xmx768m','-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-swf-version=44','-target-player=32.0','-debug=true','-compress=false','-compiler.source-path='+str(work/'src'),'-output='+str(output)]
  if output.name=='template.swf':command+=['-includes='+','.join(plan['includes'])]
  command+=[str(source)]
  result=subprocess.run(command,cwd=work,capture_output=True,timeout=65)
  output.with_suffix('.log').write_bytes(result.stdout+result.stderr)
  if result.returncode:raise RuntimeError('narrow compile failed: '+output.name)

def graft(work,plan):
 builder,after,view,identity=configure(plan)
 template=(work/'template.swf').read_bytes()
 target=builder.abcfmt.ABC(list(a.raw_units(template))[0][1])
 mapping=a.graft(target,after,plan['actual_methods'])
 # Native private/interface field QNames can be rebound explicitly by the
 # generated plan; no second slot or alternate state copy is introduced.
 importer=builder.Importer(a.view(target),view)
 for contract in plan.get('field_qnames',[]):
  source_row=next(r for r in after.instances if after.mn_name(r[0])==contract['owner'])
  target_row=next(r for r in target.instances if target.mn_name(r[0])==contract['owner'])
  st=next(t for t in source_row[6] if after.mn_name(t.name).split('::')[-1]==contract['name'])
  tt=next(t for t in target_row[6] if target.mn_name(t.name).split('::')[-1]==contract['name'])
  tt.name=importer.pool('multinames',st.name)
 for mode in plan.get('modes',('before','after')):
  output=work/mode
  if output.exists():raise FileExistsError('fresh run output required')
  output.mkdir();candidate=copy.deepcopy(target)
  old_mapping=[];old=None
  if mode=='before':
   raw=Path(plan['before']['path']).read_bytes()
   if a.sha(raw)!=plan['before']['sha256']:raise ValueError('before carrier changed')
   unit,=[u for n,u in a.raw_units(raw) if n=='boot_ffc6']
   old=builder.abcfmt.ABC(unit)
   old_mapping=a.graft(candidate,old,plan['before_parsers'])
  final=a.replace_abc(template,candidate);(output/'Harness.swf').write_bytes(final)
  parsed=builder.abcfmt.ABC(list(a.raw_units(final))[0][1])
  kept=[x for x in mapping if mode=='after' or x['source_label'] not in plan['before_parsers']]
  proof={'mode':mode,'after_identity':identity,'harness_sha256':a.sha(final),'actual_methods':a.verify_grafts(parsed,after,kept),'actual_before_parsers':a.verify_grafts(parsed,old,old_mapping) if old is not None else [],'boundaries':plan['boundaries']}
  (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n','utf-8')
  (output/'Launcher.swf').write_bytes((work/'Launcher.swf').read_bytes())
  (output/'case.json').write_text(json.dumps({**plan['case'],'mode':mode},ensure_ascii=False)+'\n','utf-8')
  (output/'application.xml').write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.trigger9000.'+work.name+'.'+mode+'</id><versionNumber>1.0.0</versionNumber><filename>trigger9000</filename><initialWindow><content>Launcher.swf</content><visible>false</visible></initialWindow></application>','utf-8')

def run(work,mode):
 output=work/mode
 if (output/'result.json').exists():raise FileExistsError('each run requires fresh result path')
 command=[str(Path(CFG['sdk'])/'bin/adl.exe'),'-cmd',str(output/'application.xml')]
 try:result=subprocess.run(command,cwd=output,capture_output=True,timeout=15)
 except subprocess.TimeoutExpired as error:
  (output/'adl.log').write_bytes((error.stdout or b'')+(error.stderr or b''));raise
 (output/'adl.log').write_bytes(result.stdout+result.stderr)
 data=json.loads((output/'result.json').read_text());print(json.dumps(data,ensure_ascii=False))
 if result.returncode or not data['passed']:raise RuntimeError('actual-body regression failed')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('phase',choices=('compile','graft','before','after'));parser.add_argument('--attempt',required=True);args=parser.parse_args()
 work=(work_path('trigger9000')/args.attempt).resolve()
 if work.parent!=work_path('trigger9000'):raise ValueError('direct owned attempt required')
 plan=json.loads((work/'fixture-plan.json').read_text())
 if args.phase=='compile':compile_template(work,plan)
 elif args.phase=='graft':graft(work,plan)
 else:run(work,args.phase)
if __name__=='__main__':main()
