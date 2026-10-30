"""Actual native storage code, native Flash JSON/ByteArray/FileStream; cold separate processes."""
from pathlib import Path
import argparse,json,subprocess,sys,hashlib,copy
from inventory import ROOT,source,selections,a
from input_config import work_path
import fixture_api

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--compile-only',action='store_true');args=ap.parse_args();out=Path(args.out).resolve()
 if not out.is_relative_to(work_path()) or out.exists():raise ValueError('fresh storage-validation output required')
 out.mkdir();src=out/'src';src.mkdir();cfg,(b,donor,sv,identity)=source();files=fixture_api.sources(donor,sv);files['air_harness.as']=(ROOT/'air_harness.as').read_text(encoding='utf-8');fixture_api.write_sources(src,files)
 sdk=Path(cfg['sdk']);cmd=[cfg['java'],'-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-swf-version=44','-debug=true','-compress=false','-compiler.source-path='+str(src),'-includes='+','.join(n[:-3].replace('/','.') for n in files if n!='air_harness.as'),'-output='+str(out/'template.swf'),str(src/'air_harness.as')];p=subprocess.run(cmd,cwd=out,capture_output=True,timeout=90);(out/'compile.log').write_bytes(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError('compile failed '+str(out/'compile.log'))
 template=(out/'template.swf').read_bytes();target=b.abcfmt.ABC(list(a.raw_units(template))[0][1]);mapping=fixture_api.graft(target,donor,b,a);final=a.replace_abc(template,target);(out/'Harness.swf').write_bytes(final);parsed=b.abcfmt.ABC(list(a.raw_units(final))[0][1]);proof=a.verify_grafts(parsed,donor,mapping);(out/'proof.json').write_text(json.dumps({'identity':identity,'actual_methods':proof,'harness_sha256':a.sha(final),'boundaries':['DevConfig.getStorageDirectory is restricted to dedicated storage-validation/data prefix.','StorageHook is notification capture only; original enum construction/startLoad/apply/JSON/read/write/compress/FileStream execute.','GenericGearDispatcher/AddBehaviorPreset and error/Std diagnostic formatting are finite typed boundaries; actual WaitImpl/WaitInOrder/stream methods run.'],'source_files_sha256':{n:a.sha(s.encode()) for n,s in files.items()}},ensure_ascii=False,indent=2),encoding='utf-8')
 launcher=(ROOT/'Launcher.as').read_text(encoding='utf-8');(out/'Launcher.as').write_text(launcher,encoding='utf-8');p=subprocess.run([cfg['java'],'-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-debug=true','-output='+str(out/'Launcher.swf'),str(out/'Launcher.as')],cwd=out,capture_output=True,timeout=60);(out/'launcher-compile.log').write_bytes(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError('launcher compile failed')
 appid='local.starpoint.cn.storagevalidation.'+''.join(c for c in out.name if c.isalnum());(out/'application.xml').write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>'+appid+'</id><versionNumber>1.0.0</versionNumber><filename>storagevalidation</filename><initialWindow><content>Launcher.swf</content><visible>false</visible></initialWindow></application>',encoding='utf-8')
 if args.compile_only:
  print(json.dumps({'status':'compiled_exact_storage_harness','out':str(out),'harness_sha256':a.sha(final)}));return
 root=work_path('storage-validation/data')/out.name
 if root.exists():raise ValueError('fresh dedicated data directory required')
 rows=[]
 for phase in ['seed-old13','missing-writefalse','false-writetrue','true-readonly']:
  (out/'control.json').write_text(json.dumps({'phase':phase,'root':str(root)}),encoding='utf-8');resultpath=out/'result.json'
  if resultpath.exists():resultpath.rename(out/(rows[-1]['phase']+'.result.json'))
  child=subprocess.Popen([str(sdk/'bin/adl.exe'),'-cmd',str(out/'application.xml')],cwd=out,stdout=subprocess.PIPE,stderr=subprocess.PIPE);pid=child.pid
  try:stdout,stderr=child.communicate(timeout=30)
  except subprocess.TimeoutExpired:
   child.kill();stdout,stderr=child.communicate();(out/(phase+'.adl.log')).write_bytes(stdout+stderr);raise
  (out/(phase+'.adl.log')).write_bytes(stdout+stderr);result=json.loads(resultpath.read_text(encoding='utf-8'));datafile=root/'application_option';row={'phase':phase,'pid':pid,'exit_code':child.returncode,'result':result,'settings_file':str(datafile),'settings_sha256':a.sha(datafile.read_bytes()) if datafile.exists() else None};rows.append(row);print(json.dumps({'phase':phase,'pid':pid,'passed':result['passed'],'assertions':result['assertions'],'settings_sha256':row['settings_sha256']},ensure_ascii=False),flush=True)
  if child.returncode!=0 or not result['passed']:raise AssertionError('phase failed '+phase)
 (out/'true-readonly.result.json').write_bytes(resultpath.read_bytes());report={'passed':True,'app_id_same_all_processes':appid,'separate_process_pids':[r['pid'] for r in rows],'production_swf_sha256':identity['swf_sha256'],'harness_sha256':a.sha(final),'phases':rows,'actual_methods':len(proof),'real_game_settings_touched':False};(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
