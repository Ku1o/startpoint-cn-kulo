from pathlib import Path
import json,base64
import bootstrap
from bootstrap import ROOT,sha
from input_config import input_path,work_path,require_output
import asm,bodies,patch
from swfabc import SwfAbc,abcfmt

def main():
 path=input_path('final_swf');src=SwfAbc(path).abc;labels=list(patch.TARGETS)+['ApplicationOptionLogic$/'+patch.READER];methods=[]
 for label in labels:
  bi=bodies.resolve(src,label);body=src.bodies[bi];info=src.methods[body[0]];ins=asm.decode(body[5]);ops=[]
  for i,x in enumerate(ins):
   args=list(x.args)
   for j,v in enumerate(x.args):
    kind=asm.opwalk.KIND.get((x.op,j))
    if kind=='multiname':args[j]=src.mn_name(v)
    elif kind=='string':args[j]=src.s(v)
    elif kind in ('int','uint','double'):args[j]=getattr(src,kind+'s')[v]
   row={'instruction':i,'op':x.name,'args':args}
   if x.target is not None:row['target']=x.target
   if x.cases is not None:row.update(default=x.default,cases=x.cases)
   ops.append(row)
  w=abcfmt.W()
  for v in body[:5]:w.u30(v)
  w.u30(len(body[5]));w.raw(body[5]);w.u30(len(body[6]))
  for ex in body[6]:
   for v in ex:w.u30(v)
  w.u30(len(body[7]))
  for t in body[7]:abcfmt.write_trait(w,t)
  methods.append({'label':label,'body_index':bi,'method_info':body[0],'header':body[1:5],'code_bytes':len(body[5]),'code_sha256':sha(body[5]),'complete_body_record_sha256':sha(w.out()),'complete_body_record_base64':base64.b64encode(w.out()).decode(),'signature':{'return':src.mn_name(info[0]),'args':[src.mn_name(t) if t else '*' for t in info[1]],'flags':info[3],'defaults':info[4]},'instructions':ops})
 report={'swf':str(path),'swf_sha256':sha(path.read_bytes()),'main_abc_sha256':sha(src.serialize()),'methods':methods,'preparation_body_sha256':sha(src.bodies[bodies.resolve(src,'Battle/preparation')][5]),'build_module':'patch.py::build(editor); caller then editor.apply()','no_existing_instance_or_static_slots_added':True,'added_static_method_only':True}
 require_output(work_path('render/METHODS.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({m['label']:m['code_sha256'] for m in methods}))
if __name__=='__main__':main()
