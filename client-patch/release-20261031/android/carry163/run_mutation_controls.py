from pathlib import Path
import argparse,json,subprocess,sys,struct,zlib,copy
ROOT=Path(__file__).resolve().parent
import bootstrap
from input_config import runtime,input_path,work_path,repo_path,tool_root,require_output
import abc_tools as a

def replace_unit(raw,helper):
 body=zlib.decompress(raw[8:]) if raw[:3]==b'CWS' else raw[8:]
 for code,at,head,size in a.swftags.iter_tags(body):
  if code==82:
   p=body[at+head:at+head+size];nul=p.index(b'\0',4)
   if p[4:nul]==b'actual_carry_helper':
    payload=p[:nul+1]+helper;tag=struct.pack('<HI',(82<<6)|63,len(payload))+payload;body=body[:at]+tag+body[at+head+size:];return b'FWS'+raw[3:4]+struct.pack('<I',len(body)+8)+body
 raise ValueError('missing helper unit')

def main():
 p=argparse.ArgumentParser();p.add_argument('--carrier',default=str(work_path('carry163/air')));p.add_argument('--out',default=str(work_path('carry163/mutation-controls')));p.add_argument('--only-hp',action='store_true');op=p.parse_args();carrier=Path(op.carrier);out=Path(op.out)
 require_output(out)
 out.mkdir();cfg=runtime();swf=input_path('carry_swf');a.configure({**cfg,'repo':str(repo_path()),'swf':str(swf),'swf_sha256':a.sha(swf.read_bytes()),'tool_root':str(tool_root()),'run_root':str(work_path('carry163'))});raw=(carrier/'Harness.swf').read_bytes();helper=next(b for n,b in a.raw_units(raw) if n=='actual_carry_helper');asm=a.builder.asm
 cases=[('clone-identity','cloneValue','identity','content detached'),('no-shield','restoreHp','returnvoid','shield exists'),('unprimed-baseline','quietBaseline','returnvoid','refresh synchronized'),('no-time-rebase','cloneCondition','no-shift','remaining rebased'),('wrong-shield-age','restoreHp','age-min','shield age')];results=[]
 if op.only_hp:cases=[('skip-hp-restore','restoreHp','returnvoid','maxHP')]
 for name,method,kind,message in cases:
  h=a.builder.abcfmt.ABC(helper);v=a.view(h);label,=[l for l in v.by_label if l.startswith('cn.carry::StageCarryState$/'+method+'|')];i,=v.by_label[label];old=h.bodies[i][5];ins=asm.decode(old)
  if kind=='identity':h.bodies[i][5]=b'\xd1\x48'
  elif kind=='returnvoid':h.bodies[i][5]=b'\x47'
  elif kind=='no-shift':
   indices=[j for j,x in enumerate(ins) if x.name=='getlocal_2'];assert len(indices)==1;ins[indices[0]]=asm.Instruction(asm.MNEMONICS['pushbyte'],[0]);h.bodies[i][5]=asm.encode(ins)[0]
  elif kind=='age-min':
   indices=[j for j,x in enumerate(ins) if x.name=='getproperty' and h.mn_name(x.args[0])=='frameCount'];assert len(indices)==1;mn,=[j for j,m in enumerate(h.multinames) if m and h.mn_name(j)=='min'];ins[indices[0]].args=[mn];h.bodies[i][5]=asm.encode(ins)[0]
  dest=out/name;dest.mkdir();(dest/'Harness.swf').write_bytes(replace_unit(raw,h.serialize()));app=dest/'application.xml';app.write_text((carrier/'application.xml').read_text(encoding='utf-8').replace(carrier.name,'mutation.'+name),encoding='utf-8');cmd=[str(Path(cfg['sdk'])/'bin/adl.exe'),'-cmd',str(app)];run=subprocess.run(cmd,cwd=dest,capture_output=True,timeout=25);(dest/'adl.log').write_bytes(run.stdout+run.stderr);result=json.loads((dest/'result.json').read_text(encoding='utf-8'));assert run.returncode==1 and result['passed']==False and result.get('error')=='Error: '+message,(name,result);results.append({'mutation':name,'actual_helper_method':label,'before_sha256':a.sha(old),'after_sha256':a.sha(h.bodies[i][5]),'caught':True,'assertions_before_failure':result['assertions'],'error':result['error']})
 report={'passed':True,'controls':results,'candidate_swf_unchanged':True};(out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'passed':True,'caught':len(results)}))
if __name__=='__main__':main()
