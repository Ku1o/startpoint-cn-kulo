"""UI-first input -> selective revision render SWF; explicit hashes and reversible preservation."""
from pathlib import Path
import argparse,copy,json
import bootstrap
from bootstrap import ROOT,sha
from input_config import work_path
import asm,bodies
from framework import Editor
from swfabc import SwfAbc
import patch

def build(source,expected,dest):
 source=Path(source).resolve();dest=Path(dest).resolve()
 if not dest.is_relative_to(work_path()) or dest==source or dest.exists() or dest.suffix.lower()!='.swf':raise ValueError('fresh render output SWF required')
 raw=source.read_bytes()
 if sha(raw)!=expected:raise ValueError('explicit input SHA mismatch')
 before=SwfAbc(source);locks={k:{'sha':sha(before.abc.bodies[bodies.resolve(before.abc,k)][5]),'header':list(before.abc.bodies[bodies.resolve(before.abc,k)][1:5])} for k in patch.TARGETS}
 e=Editor(source,locks);contract=patch.build(e);e.apply();dest.parent.mkdir(parents=True,exist_ok=True);data=e.swf.serialize();after=SwfAbc.__new__(SwfAbc)
 # Persist candidate only after editor's static checks; reopen and verify complete preservation.
 dest.write_bytes(data);after=SwfAbc(dest);records=[]
 for label in patch.TARGETS:
  i=bodies.resolve(before.abc,label);old=before.abc.bodies[i];new=after.abc.bodies[i]
  if asm.unsplice_many(new[5],e.report[label]['insertions'])!=old[5]:raise ValueError('not reversible '+label)
  if new[0]!=old[0] or new[3:5]!=old[3:5] or len(new[6])!=len(old[6]) or len(new[7])!=len(old[7]):raise ValueError('method contract changed '+label)
  records.append({'label':label,'body_index':i,'method_info':old[0],'before_sha256':sha(old[5]),'after_sha256':sha(new[5]),'before_header':old[1:5],'after_header':new[1:5],**e.report[label]})
 check=copy.deepcopy(after.abc)
 if len(check.bodies)!=len(before.abc.bodies)+1 or len(check.methods)!=len(before.abc.methods)+1:raise ValueError('exact one method addition required')
 for label in patch.TARGETS:
  i=bodies.resolve(before.abc,label);check.bodies[i]=copy.deepcopy(before.abc.bodies[i])
 check.bodies.pop();check.methods.pop()
 ci,= [i for i,r in enumerate(before.abc.instances) if before.abc.mn_name(r[0])==patch.APP]
 added=check.classes[ci][1].pop()
 if check.mn_name(added.name)!=patch.READER:raise ValueError('wrong added static trait')
 for name in ('strings','ints','uints','doubles','namespaces','ns_sets','multinames'):
  setattr(check,name,getattr(check,name)[:len(getattr(before.abc,name))])
 if check.serialize()!=before.abc.serialize():raise ValueError('unexpected ABC changes outside four reversible bodies and one appended public static method/pools')
 if before.body[:before._offset]!=after.body[:after._offset] or before.body[before._offset+before._length:]!=after.body[after._offset+after._length:]:raise ValueError('non-main SWF changed')
 p=bodies.resolve(before.abc,'Battle/preparation')
 report={'status':'static_verified','input':str(source),'input_sha256':expected,'output':str(dest),'output_sha256':sha(data),'contract':contract,'methods':records,'new_methods':e.new_methods,'original_code_reversible':True,'unrelated_method_records_exact':True,'pool_prefixes_exact':True,'non_main_swf_bytes_exact':True,'preparation_exact':before.abc.bodies[p][0:6]==after.abc.bodies[p][0:6],'air_verified':False,'device_tested':False}
 dest.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--input-sha256',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=build(a.input,a.input_sha256,a.output);print(json.dumps({k:r[k] for k in ('status','output','output_sha256')}))
if __name__=='__main__':main()
