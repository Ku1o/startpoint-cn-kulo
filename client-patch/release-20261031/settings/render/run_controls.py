from pathlib import Path
import sys,json,subprocess,copy
import bootstrap
from bootstrap import ROOT,sha
from input_config import input_path,input_sha,work_path,require_output
import asm,bodies
from swfabc import SwfAbc
BASE=input_path('final_swf');BASE_SHA=input_sha('final_swf')
def main():
 if sha(BASE.read_bytes())!=BASE_SHA:raise ValueError('pinned control donor mismatch')
 root=require_output(work_path('render')/(sys.argv[1] if len(sys.argv)>1 else 'controls'));root.mkdir(parents=True);report=json.loads(input_path('render_report').read_text(encoding='utf-8'));records={m['label']:m for m in report['methods']};results=[]
 for name,label,expected in [('stale_reader_true','ApplicationOptionLogic$/cnTeammateEffectsVisibleFromBattle','same raw immediate false true false'),('P1_force_native_true','BattleViewInputSettings/isOtherBattleActionVisible','P1 complete original rich-mode decision'),('P2_drop_dynamic_reader','BattleView/show','P2 dynamic reader original fallback'),('P5_drop_lightweight','EffectManagerImpl/show','P5 independent creation')]:
  s=SwfAbc(BASE);body=s.abc.bodies[bodies.resolve(s.abc,label)];before=sha(body[5])
  if name=='stale_reader_true':body[5]=asm.encode(asm.assemble([('getlocal_0',),('pushscope',),('pushtrue',),('returnvalue',)]))[0]
  elif name=='P1_force_native_true':
   xs=asm.decode(body[5]);keep=records[label]['insertions'][0][0]+records[label]['insertions'][0][1];xs=xs[:keep]+asm.assemble([('pushtrue',),('returnvalue',)]);body[5]=asm.encode(xs)[0]
  elif name=='P2_drop_dynamic_reader':
   site=records[label]['insertions'][1];body[5]=asm.unsplice(body[5],site[0],site[1])
  else:body[5]=asm.unsplice_many(body[5],records[label]['insertions'])
  donor=root/(name+'.swf');raw=s.serialize();donor.write_bytes(raw);out=root/(name+'-air');cmd=[sys.executable,'-B',str(ROOT/'run_air.py'),'--out',str(out),'--swf',str(donor),'--sha',sha(raw)];p=subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=100);(root/(name+'.log')).write_bytes(p.stdout+p.stderr);result=json.loads((out/'result.json').read_text(encoding='utf-8'))
  caught=p.returncode!=0 and result.get('passed') is False and expected in result.get('error','')
  row={'name':name,'donor_sha256':sha(raw),'method':label,'original_code_sha256':before,'mutated_code_sha256':sha(body[5]),'expected_error':expected,'result':result,'caught':caught};results.append(row);print(json.dumps({'name':name,'caught':caught,'assertions':result.get('assertions'),'error':result.get('error')},ensure_ascii=False),flush=True)
  if not caught:raise AssertionError('negative control not caught '+name)
 (root/'report.json').write_text(json.dumps({'status':'all_expected_failures_caught','production_donor_sha256':BASE_SHA,'controls':results},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
