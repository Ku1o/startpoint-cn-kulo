"""Standalone composable carry163 build. Input must omit the rejected old PR163 group."""
from pathlib import Path
import json,argparse,struct,copy
import bootstrap
from bootstrap import ROOT,sha
from input_config import input_path,input_sha,work_path,helper_path
import asm,bodies
from swfabc import SwfAbc,swftags,abcfmt
from framework import Editor
import patch

# Original adopted bytes; the current source differs only by LF/EOF normalization.
ORIGINAL_SOURCE_SHA256='6ac6ff8f5eead3984f932c9d7a4cfb58b058452c0311d058ebd00a6a7d30b856'

def inject(raw,helper):
 import zlib
 body=zlib.decompress(raw[8:]) if raw[:3]==b'CWS' else raw[8:]
 main=next(at for code,at,head,size in swftags.iter_tags(body) if code==82 and body[at+head+4:at+head+13]==b'boot_ffc6')
 payload=struct.pack('<I',1)+b'cn.carry.StageCarryState\0'+helper;tag=struct.pack('<HI',(82<<6)|63,len(payload))+payload;final=body[:main]+tag+body[main:]
 return b'CWS'+raw[3:4]+struct.pack('<I',len(final)+8)+zlib.compress(final)

def build(source,expected,dest):
 source=Path(source).resolve();dest=Path(dest).resolve()
 if not dest.is_relative_to(work_path('carry163')) or dest.exists() or dest==source or dest.suffix.lower()!='.swf':raise ValueError('output must be a SWF in carry163/build or output')
 raw=source.read_bytes()
 if sha(raw)!=expected:raise ValueError('input SHA mismatch')
 helper=helper_path('abc').read_bytes();receipt={'abc_sha256':'6849f52ea234769bb73fadad08604e9f8009b4e4fc0a0c01c22a7d9284c507a5','source_sha256':'2e4141d743ce2aff36b4b649fe350c4a644b90938af2f7a2b65eef2152a86443','original_source_sha256':ORIGINAL_SOURCE_SHA256}
 if sha(helper)!=receipt['abc_sha256'] or sha((ROOT/'src/cn/carry/StageCarryState.as').read_bytes())!=receipt['source_sha256']:raise ValueError('helper source/compiler identity changed')
 before=SwfAbc(source);locks={l:{'sha':sha(before.abc.bodies[bodies.resolve(before.abc,l)][5]),'header':before.abc.bodies[bodies.resolve(before.abc,l)][1:5]} for l in patch.TARGETS};e=Editor(source,locks);detail=patch.build(e);e.apply();changed={bodies.resolve(before.abc,l) for l in patch.TARGETS}
 for i,body in enumerate(before.abc.bodies):
  if i not in changed:
   a,b=body,e.abc.bodies[i]
   if a[:7]!=b[:7]:raise ValueError('non-target method changed')
 for l in patch.TARGETS:
  if asm.unsplice_many(e.body(l)[5],e.report[l]['insertions'])!=before.abc.bodies[bodies.resolve(before.abc,l)][5]:raise ValueError('native hook not reversible')
 check=copy.deepcopy(e.abc)
 for name in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
  old=getattr(before.abc,name);new=getattr(e.abc,name)
  if name=='doubles':
   if b''.join(struct.pack('<d',v) for v in new[:len(old)])!=b''.join(struct.pack('<d',v) for v in old):raise ValueError('original double pool changed')
  elif new[:len(old)]!=old:raise ValueError('original pool changed: '+name)
  setattr(check,name,copy.deepcopy(old))
 for i in changed:check.bodies[i]=copy.deepcopy(before.abc.bodies[i])
 if check.serialize()!=before.abc.serialize():raise ValueError('non-target main ABC bytes changed')
 dest.parent.mkdir(parents=True,exist_ok=True);main_raw=e.swf.serialize();dest.write_bytes(inject(main_raw,helper));after=SwfAbc(dest)
 import zlib
 found=[]
 for code,at,head,size in swftags.iter_tags(after.body):
  if code==82:
   data=after.body[at+head:at+head+size];end=data.index(b'\0',4)
   if data[4:end]==b'cn.carry.StageCarryState':found.append((at,head+size,data[end+1:]))
 if len(found)!=1 or found[0][2]!=helper:raise ValueError('helper injection not byte exact')
 at,size,_=found[0]
 expected_body=zlib.decompress(main_raw[8:]) if main_raw[:3]==b'CWS' else main_raw[8:]
 if after.body[:at]+after.body[at+size:]!=expected_body:raise ValueError('other SWF tags changed during helper injection')
 if after.abc.serialize()!=e.abc.serialize():raise ValueError('final main ABC mismatch')
 report={'status':'built_pending_runtime_acceptance','input':str(source),'input_sha256':expected,'output':str(dest),'output_sha256':sha(dest.read_bytes()),'helper':receipt,'detail':detail,'changed_methods':e.report,'pool_additions':e.pool.report(),'original_methods_reversible':True,'non_target_method_records_exact':True,'existing_traits_unchanged':True,'all_non_target_main_ABC_bytes_exact_after_removing_appended_pools':True,'new_ABC_classes':1,'helper_ABC_byte_exact':True,'all_other_SWF_tags_exact':True,'new_existing_class_slots':0,'device_tested':False};dest.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return report

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',default=str(input_path('r11_swf')));p.add_argument('--sha',default='9c672e56e5911679848047daece874e139255b2d128f67ab11e605c5db2bb951');p.add_argument('--output',default=str(work_path('carry163/build/carry163-r11.swf')));a=p.parse_args();r=build(a.input,a.sha,a.output);print(json.dumps({k:r[k] for k in ('status','output','output_sha256')}))
if __name__=='__main__':main()
