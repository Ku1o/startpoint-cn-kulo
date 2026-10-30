"""Bounded targeted metadata for actual ratio units and native Gear teardown."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
import bootstrap
from input_config import input_path,input_sha,runtime,repo_path,work_path,tool_root
import abc_tools as a
cfg=runtime()
a.configure({**cfg,'repo':str(repo_path()),'swf':str(input_path('final_swf')),'swf_sha256':'83fc92d70d7457bb5e4b58d25d97663eeb80367ee366a947f4779a12075ff172','tool_root':str(tool_root()),'run_root':str(work_path('trigger9000'))})
b,abc,v,identity=a.load_current(('pinball.master.generated::LeaderAbilityValues',))
selections={'Decimal100ClosedInterval':['setRatio'],'Gear':['disposeTop','enterRemove','isDisposed','checkPhaseBeforeDispose'],'Diffuser':['dispose'],'GearPhase':['<ctor>'],'GearHolderImpl':['<ctor>']}
result={'identity':identity,'classes':{}}
for ci,row in enumerate(abc.instances):
 q=abc.mn_name(row[0]);short=q.rsplit('::',1)[-1]
 if short not in selections:continue
 methods=[]
 for label,indices in v.by_label.items():
  if not (label.startswith(q+'/') or label.startswith(q+'$/')):continue
  method=label.rsplit('/',1)[-1].split('|')[0].rsplit('::',1)[-1]
  if method not in selections[short]:continue
  bi,=indices;body=abc.bodies[bi];info=abc.methods[body[0]]
  methods.append({'label':label,'body':bi,'mid':body[0],'header':body[1:5],'codeSha256':a.sha(body[5]),'signature':{'return':abc.mn_name(info[0]),'args':[abc.mn_name(n) for n in info[1]],'flags':info[3]},'rows':v.normalized(bi)})
 result['classes'][q]={'super':abc.mn_name(row[1]),'flags':row[2],'slots':[{'name':abc.mn_name(t.name),'type':abc.mn_name(t.data[2]),'data':str(t.data)} for t in row[6] if t.data[0]=='slot'],'staticSlots':[{'name':abc.mn_name(t.name),'type':abc.mn_name(t.data[2]),'data':str(t.data)} for t in abc.classes[ci][1] if t.data[0]=='slot'],'methods':methods}
out=work_path('trigger9000/metadata-lifecycle83fc.json');out.parent.mkdir(parents=True,exist_ok=True);assert not out.exists()
if out.exists():raise FileExistsError(out)
out.write_text(json.dumps(result,indent=2)+'\n','utf-8');print(json.dumps({'out':str(out),'classes':list(result['classes'])}))
