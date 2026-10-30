from pathlib import Path
import json,subprocess,sys
import bootstrap
from bootstrap import ROOT,sha
from input_config import input_path,input_sha,work_path,require_output
import asm,bodies
from swfabc import SwfAbc

def call(src,digest,out):return subprocess.run([sys.executable,'-B',str(ROOT/'build.py'),'--input',str(src),'--input-sha256',digest,'--output',str(out)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=80)
def main():
 out=require_output(work_path('render/composition'));out.mkdir(parents=True);base=input_path('ui_partial');basehash=input_sha('ui_partial');candidate=input_path('final_swf');rows=[]
 for name,src,digest,error in [('wrong-full-sha',base,'0'*64,'explicit input SHA mismatch'),('missing-ui',input_path('corecarry'),input_sha('corecarry'),'required exact method'),('repeat',candidate,sha(candidate.read_bytes()),'method lock mismatch')]:
  target=out/(name+'.swf');p=call(src,digest,target);caught=p.returncode!=0 and error in p.stderr and not target.exists();rows.append({'case':name,'rejected':caught,'error_match':error});assert caught,(name,p.stdout,p.stderr)
 tamper=SwfAbc(base);b=tamper.abc.bodies[bodies.resolve(tamper.abc,'GlobalLogic/_getApplicationOption')];b[5]=asm.encode(asm.assemble([('getlocal_0',),('pushscope',),('pushnull',),('returnvalue',)]))[0];path=out/'tampered-input.swf';path.write_bytes(tamper.serialize());target=out/'tampered-output.swf';p=call(path,sha(path.read_bytes()),target);caught=p.returncode!=0 and 'native dependency body differs' in p.stderr and not target.exists();rows.append({'case':'changed-native-getter','rejected':caught});assert caught
 target=out/'deterministic-rebuild.swf';p=call(base,basehash,target);assert p.returncode==0,(p.stdout,p.stderr);same=target.read_bytes()==candidate.read_bytes();rows.append({'case':'deterministic-current-module-rebuild','byte_exact':same,'sha256':sha(target.read_bytes())});assert same
 (out/'report.json').write_text(json.dumps({'passed':True,'cases':rows},indent=2),encoding='utf-8');print(json.dumps(rows))
if __name__=='__main__':main()
