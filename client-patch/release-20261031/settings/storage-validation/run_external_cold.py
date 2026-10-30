"""Read exact frozen UI settings file in a new AIR process, same UI app descriptor."""
from pathlib import Path
import argparse,json,subprocess,shutil,hashlib
from inventory import ROOT,a
from input_config import runtime,work_path
UIROOT=work_path('ui/storage-data/air15-linked')
def main():
 p=argparse.ArgumentParser();p.add_argument('--harness',required=True);p.add_argument('--out',required=True);p.add_argument('--app-config',required=True);p.add_argument('--input-sha256',required=True);p.add_argument('--expected-json',required=True);p.add_argument('--visible',choices=['true','false'],required=True);op=p.parse_args();out=Path(op.out).resolve();harness=Path(op.harness).resolve();config=Path(op.app_config).resolve();expected=Path(op.expected_json).resolve()
 if not out.is_relative_to(work_path()) or out.exists() or not harness.is_relative_to(work_path()) or not config.is_relative_to(work_path('ui')):raise ValueError('external cold scope boundary')
 file=UIROOT/'application_option';before=file.read_bytes();digest=hashlib.sha256(before).hexdigest()
 if digest!=op.input_sha256:raise ValueError('frozen UI input SHA mismatch')
 out.mkdir();[shutil.copyfile(harness/n,out/n) for n in ('Harness.swf','Launcher.swf')];shutil.copyfile(config,out/'application.xml');control={'phase':'external-cold','root':str(UIROOT),'expectedVisible':op.visible=='true','expected':json.loads(expected.read_text(encoding='utf-8'))};(out/'control.json').write_text(json.dumps(control,ensure_ascii=False),encoding='utf-8');cfg=runtime();child=subprocess.Popen([str(Path(cfg['sdk'])/'bin/adl.exe'),'-cmd',str(out/'application.xml')],cwd=out,stdout=subprocess.PIPE,stderr=subprocess.PIPE);pid=child.pid
 try:stdout,stderr=child.communicate(timeout=30)
 except subprocess.TimeoutExpired:child.kill();stdout,stderr=child.communicate();(out/'adl.log').write_bytes(stdout+stderr);raise
 (out/'adl.log').write_bytes(stdout+stderr);result=json.loads((out/'result.json').read_text(encoding='utf-8'));after=file.read_bytes();report={'passed':child.returncode==0 and result.get('passed') is True and after==before,'reader_pid':pid,'source_harness':str(harness),'source_harness_sha256':hashlib.sha256((harness/'Harness.swf').read_bytes()).hexdigest(),'copied_harness_sha256':hashlib.sha256((out/'Harness.swf').read_bytes()).hexdigest(),'source_proof':str(harness/'proof.json'),'source_proof_sha256':hashlib.sha256((harness/'proof.json').read_bytes()).hexdigest(),'app_config_copied_byte_exact':(out/'application.xml').read_bytes()==config.read_bytes(),'app_config_source':str(config),'source_ui_file':str(file),'input_sha256':digest,'after_sha256':hashlib.sha256(after).hexdigest(),'readonly_original_file_exact':after==before,'result':result};(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'passed':report['passed'],'reader_pid':pid,'assertions':result.get('assertions'),'ui_file_byte_exact':after==before},ensure_ascii=False));assert report['passed']
if __name__=='__main__':main()
