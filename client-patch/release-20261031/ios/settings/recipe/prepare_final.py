"""Prepare a frozen selective Android delta on the registered iOS full/native prefix.

New mutable static fields are implemented as accessors and sidecar slots.
Preview preparation deliberately excludes MemberView.draw pending its explicit
platform adapter; a preview port must not be used as the final release.
"""
from __future__ import annotations
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
cfg.bind_tools()
import argparse,copy,hashlib,importlib.util,json,shutil,struct,subprocess,sys,types,zipfile,zlib
sys.dont_write_bytecode=True
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=Path(str(cfg.REPO))
CLIENT=SOURCE/'client-patch'
SDK=Path(cfg.path('sdk'))
sys.path[:0]=[str(CLIENT/'lens0907-0908'),str(CLIENT/'pr43-ios'),cfg.path('libraries'),str(HERE),cfg.local('capabilities')]
import build_swf as p
from native_support import backend,INFO_OFFSET,read64
from donor_mapping import signature
from hud_adapter import adapt_hud_body,COUNTERS
import static_proxies as storage

DRAW='pinball.scene.battle.battle.squad.member::MemberView/draw|1'
HUD='pinball.scene.battle.battle.hud::HudMemberStatus/update|1'
PATHS='pinball.common.data.character::BattleCharacterLogic/resolvePathCollection|1'
POOL=('ints','uints','doubles','strings','namespaces','ns_sets','multinames')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save(path,doc):Path(path).write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def view(abc):return p.View(types.SimpleNamespace(abc=abc),p.asm)

def units(path):
 raw=Path(path).read_bytes()
 body=zlib.decompress(raw[8:]) if raw[:3]==b'CWS' else raw[8:]
 from swfabc import swftags
 result={}
 for kind,at,header,length in swftags.iter_tags(body):
  if kind!=82:continue
  d=body[at+header:at+header+length];end=d.index(b'\0',4);name=d[4:end].decode('utf-8');result.setdefault(name,[]).append(d[end+1:])
 return result

def compile_sidecar(out,rows):
 source_file=out/'storage-source/cn/release/ReleaseState20261031.as';source_file.parent.mkdir(parents=True)
 source_file.write_text(storage.source_text(rows),encoding='utf-8')
 swc=out/'ReleaseState20261031.swc'
 command=[shutil.which('java'),'-Dflexlib='+str(SDK/'frameworks'),'-jar',str(SDK/'lib/compc-cli.jar'),
  '+configname=air','-swf-version=44','-target-player=32.0','-compiler.float=false','-debug=false',
  '-compiler.source-path='+str(out/'storage-source'),'-include-classes=cn.release.ReleaseState20261031','-output='+str(swc)]
 if any(row['type']=='haxe.ds::WeakMap' for row in rows):
  # Only a type declaration is needed by compc. It is external to the helper
  # SWC and never enters runtime; the full iOS ABC retains the real WeakMap.
  stub=out/'external-type-source/haxe/ds/WeakMap.as';stub.parent.mkdir(parents=True)
  stub.write_text('package haxe.ds { public class WeakMap {} }\n',encoding='utf-8')
  external=out/'external-weakmap-type.swc'
  cmd=command[:4]+['+configname=air','-compiler.float=false','-compiler.source-path='+str(out/'external-type-source'),'-include-classes=haxe.ds.WeakMap','-output='+str(external)]
  with (out/'external-type-compc.log').open('wb') as log:result=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=120)
  assert result.returncode==0,'external WeakMap type declaration compilation failed'
  command.append('-external-library-path+='+str(external))
 with (out/'sidecar-compc.log').open('wb') as log:result=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=120)
 assert result.returncode==0,'sidecar compc failed'
 with zipfile.ZipFile(swc) as z:raw=z.read('library.swf')
 (out/'sidecar-library.swf').write_bytes(raw);parts=units(out/'sidecar-library.swf');data,=[d for values in parts.values() for d in values]
 (out/'sidecar-compiler-original.abc').write_bytes(data)
 helper=view(p.abcfmt.ABC(data))
 assert [helper.a.mn_name(i[0]) for i in helper.a.instances]==[storage.STATE],'external type stub leaked into runtime helper'
 return helper

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--preview',action='store_true');ap.add_argument('--draw-gated-extension',action='store_true');args=ap.parse_args()
 contract=read(args.contract);out=args.output.resolve();assert out.is_relative_to(cfg.work('settings')) and not out.exists(),'fresh private settings work directory required'
 basefile=Path(contract['android_base_swf']);donorfile=Path(contract['donor_swf'])
 assert sha(basefile.read_bytes())==contract['android_base_sha256']=='9c672e56e5911679848047daece874e139255b2d128f67ab11e605c5db2bb951'
 assert sha(donorfile.read_bytes())==contract['donor_sha256'],'donor must be frozen'
 registry=read(cfg.path('r11_baseline_record'))['artifact']
 assert registry['ipa_sha256']=='339e19ca373284ed778dd3fcda5ee2aa2e93915f550add733629de5bd989c33b'
 original=Path(registry['full_abc']).read_bytes();assert sha(original)==registry['full_abc_sha256']
 target=view(p.abcfmt.ABC(original));old=copy.deepcopy(target.a)
 base_units,donor_units=units(basefile),units(donorfile)
 changed_tags=[name for name in donor_units if name not in base_units or donor_units[name]!=base_units[name]]
 assert set(base_units)<=set(donor_units),'donor deleted ABC units'
 assert set(changed_tags)<=set(contract['allowed_modified_abc_tags']),('undeclared modified ABC unit',changed_tags)
 out.mkdir(parents=True)
 wanted=[];sources=[];blocked=[];all_sources=[]
 # New independent helper ABCs are imported intact before main method mapping.
 for name in changed_tags:
  assert len(donor_units[name])==1 and (name not in base_units or len(base_units[name])==1)
  source=view(p.abcfmt.ABC(donor_units[name][0]));all_sources.append((name,source))
  existing={target.a.mn_name(i[0]) for i in target.a.instances}
  names={source.a.mn_name(i[0]) for i in source.a.instances}
  if not (names&existing):
   ids=storage.import_sidecar(p,target,source,SOURCE);wanted+=ids
   sources.append(dict(tag=name,strategy='new_helper_unit',methods=ids,abc_sha256=sha(donor_units[name][0])))
  # Existing main units contain platform-specific unselected classes. They
  # remain outside the iOS import; selected new class owners are gated below.
 # Each unit gets its own mapping; ordinary helper units can refer to main
 # game methods by QName without importing declarations from Android wholesale.
 jobs=[];main_source=None;main_base=None
 for name,source in all_sources:
  if name not in base_units:continue
  base=view(p.abcfmt.ABC(base_units[name][0]));selected=[]
  for label,indices in source.by_label.items():
   assert len(indices)==1,('ambiguous donor method',label)
   si=indices[0];body=source.a.bodies[si]
   if label in base.by_label:
    bi,=base.by_label[label]
    if base.a.bodies[bi][5]==body[5] or p.freeze(base.normalized(bi))==p.freeze(source.normalized(si)):continue
   selected.append(label)
  if name=='boot_ffc6':main_source,main_base=source,base
  jobs.append((name,source,selected))
 assert main_source is not None,'main ABC not selected'
 fields=storage.definitions(main_base,main_source)
 for row in fields:assert row['type'] in ('Object','flash.utils::Dictionary','*','Array','Boolean','int','haxe.ds::WeakMap'),('unreviewed new static storage type',row)
 accesses=storage.audit_accesses(p,main_source,fields,{main_source.a.bodies[main_source.by_label[l][0]][0] for name,s,labels in jobs if s is main_source for l in labels})
 proxy_records=[]
 if fields:
  helper=compile_sidecar(out,fields);wanted+=storage.import_sidecar(p,target,helper,SOURCE)
  target=view(target.a);proxy_importer=p.Importer(target,main_source)
  proxy_records=storage.install_accessors(p,target,main_source,proxy_importer,fields)
  wanted += [r['method_id'] for row in proxy_records for r in row['accessors']]
 records=[];new_ids=set(wanted);changed_existing=set()
 for name,source,selected in jobs:
  target=view(target.a);importer=p.Importer(target,source)
  # Explicitly reserve every new named method and recursively referenced
  # closure before importing any body. Old stripped parents do not reveal
  # nested iOS labels; append those closures instead of guessing old IDs.
  queue=list(selected);seen=set();extra=[];cloned={}
  while queue:
   label=queue.pop(0)
   if label in seen:continue
   seen.add(label)
   si,=source.by_label[label];sb=source.a.bodies[si]
   if label==DRAW:
    if args.preview and not args.draw_gated_extension:blocked.append(dict(label=label,reason='requires verified iOS wrapper/typed draw adapter'));continue
    assert args.draw_gated_extension,'final MemberView.draw platform adapter is not selected'
   if label==PATHS:
    from swfabc import PoolEditor
    ti,=target.by_label[label];original_body=target.a.bodies[ti]
    assert signature(target,original_body[0])==signature(source,sb[0])
    mid=len(target.a.methods);importer.methods[sb[0]]=mid;target.a.methods.append(importer.info(sb[0]));new_ids.add(mid);wanted.append(mid)
    owner=label.split('/')[0];ci,=[i for i,r in enumerate(target.a.instances) if target.a.mn_name(r[0])==owner]
    oldtrait,=[t for t in target.a.instances[ci][6] if t.kind==1 and t.data[2]==original_body[0]]
    q=PoolEditor(target.a).public_qname('cnReleaseResolvePathCollection',oldtrait.name)
    trait=p.abcfmt.Trait();trait.name=q;trait.kind=1;trait.attr=0;trait.data=['method',0,mid];trait.metadata=[];target.a.instances[ci][6].append(trait)
    code=[('getlocal_0',),('pushscope',),('getlocal_0',)]+[('getlocal',n) for n in range(1,6)]+[('callpropvoid',q,5),('returnvoid',)]
    bridge=copy.deepcopy(original_body);bridge[1]=max(bridge[1],6);bridge[5]=p.asm.encode(p.asm.assemble(code))[0];bridge[6]=[]
    p.check_body(bridge,target.a);target.a.bodies[ti]=bridge;changed_existing.add(original_body[0]);wanted.append(original_body[0])
    records.append(dict(method_id=original_body[0],strategy='replace',label=label,source_tag=name,source_body=si,
        before_code_sha256=sha(original_body[5]),after_code_sha256=sha(bridge[5]),
        adaptation=dict(strategy='typed_call_to_new_method_with_independent_activation',clone_method=mid,clone_name='cnReleaseResolvePathCollection',old_activation_preserved=True),validation=p.check_body(bridge,target.a)))
    cloned[label]=mid
   elif label in target.by_label:
    ti,=target.by_label[label];mid=target.a.bodies[ti][0]
    assert signature(target,mid)==signature(source,sb[0]),('signature differs',label,signature(target,mid),signature(source,sb[0]))
    importer.methods[sb[0]]=mid
   else:
    mid=len(target.a.methods);importer.methods[sb[0]]=mid;target.a.methods.append(importer.info(sb[0]));new_ids.add(mid);wanted.append(mid)
   extra.append((label,si,mid))
   for x in p.asm.decode(sb[5]):
    if x.op not in (0x40,0x44):continue
    child=source.labels.get(x.args[0]);assert child in source.by_label,('anonymous method needs explicit source body',label,x.args[0]);queue.append(child)
  # Add only method/accessor traits. Source storage slots never reach old classes.
  target_owners={target.a.mn_name(i[0]):ci for ci,i in enumerate(target.a.instances)}
  for inst,cls in zip(source.a.instances,source.a.classes):
   owner=source.a.mn_name(inst[0])
   relevant=any(t.kind in (1,2,3) and t.data[2] in importer.methods and importer.methods[t.data[2]] in new_ids for t in inst[6]+cls[1])
   if owner not in target_owners:
    assert not relevant,('selected method has new class owner; explicit class import required',owner)
    continue
   ci=target_owners[owner]
   for before,after in [(inst[6],target.a.instances[ci][6]),(cls[1],target.a.classes[ci][1])]:
    for trait in before:
     if trait.kind not in (1,2,3) or trait.data[2] not in importer.methods or importer.methods[trait.data[2]] not in new_ids:continue
     # The paths clone has its explicitly renamed trait above; replacing its
     # original declaration would alias the new activation onto the old ID.
     if source.labels.get(trait.data[2]) in cloned:continue
     copied=importer.trait(trait)
     if any(t.kind==copied.kind and t.name==copied.name for t in after):continue
     after.append(copied)
  for label,si,mid in extra:
   sb=source.a.bodies[si];is_existing=mid<len(old.methods)
   if is_existing:
    ti,=target.by_label[label];before=target.a.bodies[ti];scope=before[3]
   else:before=None;scope=sb[3]
   activation_adaptation=None
   try:body=importer.body(si,mid,scope=scope)
   except Exception as error:raise ValueError(('body import failed',label,'source scope',sb[3],'target scope',scope)) from error
   adaptation=None
   if label==DRAW:
    from draw_extension import build as draw_extension
    body,adaptation=draw_extension(p,target.a,body)
   import platform_methods
   body,platform_adaptation=platform_methods.adapt(body,target.a,p)
   if label==HUD:
    count=sum(x.op==0x66 and target.a.mn_name(x.args[0]) in COUNTERS for x in p.asm.decode(body[5]))
    assert count>0
    body,adaptation=adapt_hud_body(target.a,body,p.asm,expected_reads=count)
   if before is not None:
    # Existing activation descriptors are an immutable ABI prefix.
    assert p.activation_traits(target,before)==p.activation_traits(target,body),('activation layout differs',label)
    target.a.bodies[ti]=body;changed_existing.add(mid)
   else:target.a.bodies.append(body)
   check=p.check_body(body,target.a)
   wanted.append(mid)
   row=dict(method_id=mid,strategy='replace',label=label if label not in cloned else label.replace('/resolvePathCollection|','/cnReleaseResolvePathCollection|'),source_tag=name,source_body=si,after_code_sha256=sha(body[5]),adaptation=adaptation,platform_adaptation=platform_adaptation,activation_adaptation=activation_adaptation,validation=check)
   if before is not None:row['before_code_sha256']=sha(before[5])
   records.append(row)
 for field in ('methods','metadata','scripts',*POOL):assert p.freeze(getattr(old,field))==p.freeze(getattr(target.a,field)[:len(getattr(old,field))]),field
 for before,after in zip(old.instances,target.a.instances):
  assert p.freeze(before[:-1])==p.freeze(after[:-1]);assert p.freeze(before[-1])==p.freeze(after[-1][:len(before[-1])]);assert all(t.kind in (1,2,3) for t in after[-1][len(before[-1]):])
 for before,after in zip(old.classes,target.a.classes):
  assert before[0]==after[0] and p.freeze(before[1])==p.freeze(after[1][:len(before[1])]);assert all(t.kind in (1,2,3) for t in after[1][len(before[1]):])
 for before,after in zip(old.bodies,target.a.bodies):
  if before[0] not in changed_existing:assert p.freeze(before)==p.freeze(after),before[0]
 result=target.a.serialize();assert p.abcfmt.ABC(result).serialize()==result
 (out/'full.abc').write_bytes(result)
 native_file=Path(cfg.path('outputs_ios_r11_cumulative_compact_20261025_linked_worldflipper'));swf_file=native_file.with_name('worldflipper_ios_release.swf');native=native_file.read_bytes();link=backend()
 assert sha(native)==registry['native_sha256'] and sha(swf_file.read_bytes())==registry['swf_sha256']
 at=link.file_offset(native,read64(native,INFO_OFFSET+24));size=read64(native,INFO_OFFSET+32)
 report=dict(status='preview_not_final_requires_draw_adapter' if args.preview else 'prepared_requires_aot_compile_and_link',source_ipa=registry,
  full_abc_file='full.abc',full_abc_sha256=sha(result),full_abc_sha1=hashlib.sha1(result).hexdigest(),base_full_abc_sha256=sha(original),
  old_methods=len(old.methods),total_methods=len(target.a.methods),baseline_native_file=str(native_file),baseline_swf_file=str(swf_file),
  baseline_runtime_abc_sha256=sha(native[at:at+size]),methods=records,new_method_ids=sorted(new_ids),compiled_helpers=sorted(new_ids),
  permitted_native_entry_aliases=read(cfg.path('shared_alias_review'))['permitted_aliases'],source_contract=str(args.contract.resolve()),source_contract_sha256=sha(args.contract.read_bytes()),
  donor_android_swf_file=str(donorfile),donor_android_swf_sha256=contract['donor_sha256'],changed_tags=changed_tags,
  storage=proxy_records,source_storage_accesses=accesses,new_helper_sources=sources,blocked_platform_methods=blocked,
  old_declarations_and_pool_prefix_preserved=True,unrelated_existing_bodies_preserved=len(old.bodies)-len(changed_existing),native_executed=False,device_tested=False)
 save(out/'port.json',report)
 print(json.dumps(dict(status=report['status'],existing=len(changed_existing),new=len(new_ids),total=report['total_methods'],storage=len(fields),blocked=blocked)))

if __name__=='__main__':main()
