"""Port the bounded C8601 methods to the registered cumulative iOS carrier."""
from __future__ import annotations
import argparse,copy,hashlib,importlib.util,json,os,sys,types
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'client-patch'
RECIPE=SOURCE/'release-20261031/ios'
sys.path.insert(0,str(RECIPE))
LABELS=['cn.content::ContentOperationsState$/questDecision|1',
 'pinball.scene.equipmentList::EquipmentSellableStatusResolver/reasonToUiString|1',
 'pinball.scene.equipmentList::EquipmentSellableStatusResolver/getPartyCategoryPriority|1']

def require(ok,message):
 if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path,maximum=32*1024**2):
 path=Path(path);require(path.is_file() and path.stat().st_size<=maximum,'JSON input size/path refused')
 return json.loads(path.read_text('utf-8-sig'))
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def fresh(path):
 path=Path(path).resolve();require(path.is_relative_to(TASK) and path!=TASK and not path.exists(),'Fresh task-local output required: '+str(path));return path
def dump(path,value):
 path=fresh(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n','utf8')
def framework():
 import input_config as cfg
 cfg.bind_tools()
 sys.path.insert(0,str(SOURCE/'lens0907-0908'))
 import build_swf as p
 return p
def configure(args):
 global TASK,PREVIOUS,SDK,DEPENDENCIES,STUBS,BACKGROUND,INPUTS
 os.environ['SP_CLIENT_INPUTS']=str(args.inputs.resolve())
 INPUTS=read(args.inputs,1024**2);TASK=Path(INPUTS['task']).resolve();PREVIOUS=Path(INPUTS['previous']).resolve()
 require(TASK.is_absolute() and not TASK.is_relative_to(ROOT) and '.cdn' not in TASK.parts,'Private task output required')
 TASK.mkdir(parents=True,exist_ok=True)
 SDK=Path(INPUTS['ios']['sdk']['path']);DEPENDENCIES=Path(INPUTS['ios']['dependencies']['path']);STUBS=Path(INPUTS['ios']['runtime_stubs']['path'])
 BACKGROUND=RECIPE/'support/process/run_background.py'
 # Bind shared algorithm adapters to this new pinned stage, not an old repair's state.
 sys.modules['repair_common']=sys.modules[__name__]
 sys.modules['common']=sys.modules[__name__]
 job=module('c8601_job_guard',RECIPE/'support/process/job_guard.py').require_bounded_job(180)
 return job

def prepare(args,job):
 out=fresh(args.output);p=framework()
 record=read(INPUTS['baseline_record'])['artifact']
 require(record['ipa_sha256']=='1990178abd4078beb39e26e5c2f985b6cc1af4900c72868f5b79221fcc21e907','Wrong cumulative IPA')
 raw=Path(record['full_abc']).read_bytes();require(sha(raw)==record['full_abc_sha256'],'Full ABC identity changed')
 a=p.abcfmt.ABC(raw);before=copy.deepcopy(a);target=p.View(types.SimpleNamespace(abc=a),p.asm)
 require(len(a.methods)==101873,'Unexpected cumulative method count')
 sc=module('c8601_ios_swf_reader',SOURCE/'startup-cache/build_swf.py')
 android=Path(INPUTS['android_swf']);require(sha(android.read_bytes())==INPUTS['android_swf_sha256'],'Verified Android donor changed')
 tags=sc.parts(android)[2]
 donors={}
 for label in LABELS:
  owner=label.split('/')[0].rstrip('$')
  tag,=[t for t in tags if t[0]==82 and any(t[3].mn_name(i[0])==owner for i in t[3].instances)]
  donors[label]=p.View(types.SimpleNamespace(abc=tag[3]),p.asm)
 changes=[]
 for label in LABELS:
  source=donors[label];di,=source.by_label[label];ti,=target.by_label[label]
  prior=a.bodies[ti];mid=prior[0];smid=source.a.bodies[di][0]
  signature=lambda abc,m:(abc.mn_name(abc.methods[m][0]),[abc.mn_name(t) for t in abc.methods[m][1]],abc.methods[m][3])
  require(signature(a,mid)==signature(source.a,smid),'Method ABI/signature differs: '+label)
  importer=p.Importer(target,source)
  for name,indices in source.by_label.items():
   if len(indices)==1 and name in target.by_label and len(target.by_label[name])==1:
    importer.methods[source.a.bodies[indices[0]][0]]=a.bodies[target.by_label[name][0]][0]
  replacement=importer.body(di,mid,scope=prior[3]);a.bodies[ti]=replacement
  require(p.freeze(target.normalized(ti))==p.freeze(source.normalized(di)),'Transferred instructions/CFG differ')
  changes.append(dict(method_id=mid,label=label,strategy='replace',before_code_sha256=sha(prior[5]),after_code_sha256=sha(replacement[5]),validation=p.check_body(replacement,a),real_owner_recompile=True,exact_android_method_semantics=True,prior_body_bytes=len(prior[5])))
 require(len(a.methods)==len(before.methods),'MethodInfo appended unexpectedly')
 changed={r['method_id'] for r in changes}
 for old,new in zip(before.bodies,a.bodies):
  if old[0] not in changed:require(p.freeze(old)==p.freeze(new),'Unrelated method changed')
 for field in ('instances','classes','methods','scripts','metadata'):require(p.freeze(getattr(a,field))==p.freeze(getattr(before,field)),'Layout changed: '+field)
 for field in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
  prefix=getattr(before,field);require(p.freeze(getattr(a,field)[:len(prefix)])==p.freeze(prefix),'Existing pool changed: '+field)
 result=a.serialize();require(p.abcfmt.ABC(result).serialize()==result,'ABC roundtrip differs')
 out.mkdir(parents=True);(out/'full.abc').write_bytes(result)
 port=dict(status='prepared_c8601_real_owner_replacements',source_ipa=record,full_abc_file='full.abc',full_abc_sha256=sha(result),full_abc_sha1=hashlib.sha1(result).hexdigest(),base_full_abc_sha256=sha(raw),old_methods=len(before.methods),total_methods=len(a.methods),methods=changes,compiled_helpers=[],new_method_ids=[],parent_bounded_job=job,android_swf_sha256=sha(android.read_bytes()),old_layouts_and_non_target_bodies_unchanged=True,admission_materials_unchanged=True,device_tested=False)
 dump(out/'port.json',port)
 return {k:port[k] for k in ('status','full_abc_sha256','methods')}

def unwind_wrapper(original_augment):
 # The repository version externalized historical paths. Pin that reviewed
 # source identity rather than using the old pre-migration file's hash.
 algorithm_path=SOURCE/'release1031-ios-dispatch-fix-20261031/audit/probe_unwind_payload_dedup.py'
 algorithm_sha='b8966b9a3a5ab709e7de77bbc7c47a7a63a7b176161cfceb9b2bbcdbf9f3e1b5'
 require(sha(algorithm_path.read_bytes())==algorithm_sha,'Reviewed shared-page algorithm changed')
 algorithm=module('c8601_standard_unwind_pages',algorithm_path)
 baseline=read(PREVIOUS/'linked01/link-report.json')['unwind_finalization']
 windows=[[31587,31619],[32232,32264],[32989,33021],[33092,33124],[34047,34079],[34890,34922],[35765,35797],[36391,36423]]
 def augment(original,ranges):
  require(sha(original)==baseline['final_unwind_sha256'],'Cumulative unwind identity changed')
  packed,receipt=original_augment(original,ranges)
  if len(packed)<=len(original):return packed,receipt
  before=algorithm.u.parse(packed)
  entries=[r for page in before['pages'] for r in page['entries']]
  lsda=[r for page in before['pages'] for r in page['lsda']]
  require(all(encoding in before['common'] for _,encoding in entries),'New unwind common encoding needs review')
  model=dict(before,pages=algorithm.make_pages(entries,windows,before['sentinel'],lsda))
  result,aliases=algorithm.serialize_reusing_payloads(model)
  actual=algorithm.u.parse(result)
  require(actual==model and [r for page in actual['pages'] for r in page['entries']]==entries and [r for page in actual['pages'] for r in page['lsda']]==lsda,'Unwind boundary/encoding/LSDA changed')
  require(all(actual[k]==before[k] for k in ('common','personalities','sentinel')),'Unwind metadata changed')
  require(len(result)<=len(original),'Standard shared pages exceed existing capacity')
  receipt.update(packed_size=len(result),new_pages=len(model['pages']),exact_page_payload_sharing=dict(before_bytes=len(packed),after_bytes=len(result),capacity=len(original),all_augmented_boundaries_and_encodings_exact=len(entries),aliases=aliases,selected_windows=windows,max_entries=max(len(p['entries']) for p in model['pages']),max_page_bytes=max(12+4*len(p['entries']) for p in model['pages']),algorithm_sha256=algorithm_sha,section_address_size_and_eh_unchanged=True,actual_ios_unwinder_executed=False))
  return result,receipt
 return augment

def native_stage(args):
 p=framework();import compile_port,link_stage,native_support
 signing=module('c8601_signing_models',RECIPE/'repairs/scripts/signing_models.py');signing.c=sys.modules[__name__];sys.modules['signing_models']=signing
 output=Path(args.output).resolve()
 if args.stage=='compile':
  fresh(output);return compile_port.run(args.prepared,output,sdk=SDK,dependencies=DEPENDENCIES,background=BACKGROUND,timeout=165)
 if args.stage=='link':
  fresh(output)
  options=types.SimpleNamespace(prepared=args.prepared,compiled=args.compiled,output=output,previous_link=PREVIOUS/'linked01/link-report.json',previous_package=PREVIOUS/'StarPoint-iOS-1.8.4-release1031-independent-party-fix-r1-unsigned.json',runtime_stubs=STUBS,dependencies=DEPENDENCIES)
  adapter=module('c8601_grouped_link',RECIPE/'repairs/scripts/run_native_stage.py');adapter.c=sys.modules[__name__]
  report=adapter.grouped_link(link_stage,options)
  expected={r['method_id'] for r in read(args.prepared)['methods']}
  # Helpers appended by earlier ports have only an active-table slot. The
  # original game table has slots only below MAIN_METHOD_COUNT.
  legacy_count=link_stage.original.link.aot.MAIN_METHOD_COUNT
  require({r['method'] for r in report['hooks']}==expected and len(report['table_sites'])==sum(1+(mid<legacy_count) for mid in expected),'Original entries/tables not fully rebound')
  return report
 if args.stage=='finalize':
  require(read(output/'link-report.json')['status']=='linked_pending_unwind_finalization','No pending native stage')
  sys.path.insert(0,str(RECIPE/'settings/recipe'))
  finalizer=module('c8601_strict_finalizer',RECIPE/'settings/recipe/finalize_final.py')
  import ios_switch
  def strict_switch(*values):
   try:return finalizer.strict_switch(*values)
   except ValueError as first:
    try:return ios_switch.verify_switch_tables(*values)
    except ValueError as second:raise ValueError(f'All strict switch proofs rejected: {first}; direct-u32: {second}') from second
  with (patch.object(finalizer.finalize_delta,'verify_switch_tables',strict_switch),patch.object(finalizer.finalize_delta,'_augment_model',unwind_wrapper(finalizer.finalize_delta._augment_model)),patch.object(link_stage.support,'verify_signing_models',signing.verify_signing_models)):
   return link_stage.finalize(types.SimpleNamespace(output=output))
 fresh(output);fresh(output.with_suffix('.json'))
 package=module('c8601_ios_package_stage',SOURCE/'ios-r11-port/package_stage.py')
 with patch.object(sys,'argv',[str(package.__file__),'--linked',str(args.linked),'--output',str(output)]):package.main()
 return read(output.with_suffix('.json'))

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('stage',choices=['prepare','compile','link','finalize','package']);ap.add_argument('--inputs',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--prepared',type=Path);ap.add_argument('--compiled',type=Path);ap.add_argument('--linked',type=Path)
 args=ap.parse_args();job=configure(args)
 report=prepare(args,job) if args.stage=='prepare' else native_stage(args)
 print(json.dumps({k:v for k,v in report.items() if k in ('status','full_abc_sha256','native_sha256','ipa_sha256','methods')},ensure_ascii=False))
if __name__=='__main__':main()
