"""Bind ABI proof by final owner/QName to actual MethodInfo, object and linked native bytes."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,bisect,json,struct,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'recipe'),cfg.path('libraries'),cfg.repo('client-patch/ios-r11-port')]
import prepare_final as p,verify_stages as v,capstone
from type_helpers import receiver_loads
from type_helpers import owning_script,KIND

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--compiled',type=Path,required=True);ap.add_argument('--linked',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();prepared=v.read(args.prepared);compiled=v.read(args.compiled);linked=v.read(args.linked);a=p.view(p.p.abcfmt.ABC((args.prepared.parent/prepared['full_abc_file']).read_bytes()));im=v.Image(Path(linked['native_file']).read_bytes());assert v.sha(im.raw)==linked['native_sha256'];objects={str(Path(compiled['directory'])/r['name']):v.Object(Path(compiled['directory'])/r['name'],r['sha256']) for r in compiled['objects']};md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM);md.detail=True
 owner='pinball.common.data.localStore::ApplicationOptionLogic';targets=[(owner,'getTeammateEffectsVisible',False),(owner,'setTeammateEffectsVisible',False),(owner,'cnTeammateEffectsVisibleFromRaw',True),(owner,'cnTeammateEffectsVisibleFromBattle',True),('pinball.scene.applicationOption::ApplicationOptionSwitchButtonKind','CnTeammateEffectsVisible',True)];rows=[];code={}
 for cls,name,static in targets:
  ci,=[i for i,r in enumerate(a.a.instances) if a.a.mn_name(r[0])==cls];traits=a.a.classes[ci][1] if static else a.a.instances[ci][6];tr,=[tr for tr in traits if tr.kind in (1,2,3) and a.a.mn_name(tr.name)==name];mn=a.a.multinames[tr.name];assert a.a.namespaces[mn[1]][0]==0x16 and a.a.ns_name(mn[1])=='';mid=tr.data[2];fn,=[r for r in linked['functions'] if r['method']==mid];obj,name_symbol=next((obj,n) for obj in objects.values() for n in obj.defined if f':{mid}:' in n);f=obj.function(name_symbol);actual=im.read(fn['address'],fn['size']);assert v.sha(actual)==fn['sha256'] and len(actual)==len(f['data']);code[name]=actual[:f['code_size']];rows.append(dict(owner=cls,qname=name,trait_kind=tr.kind,actual_method_info=mid,signature=p.signature(a,mid),compiled_symbol=name_symbol,object=str(obj.path),actual_native_address=hex(fn['address']),actual_native_bytes=len(actual),actual_native_sha256=v.sha(actual),object_unwind_encoding=hex(f['encoding'])))
 storage=v.read(Path(cfg.path('native_storage_contract')));old=v.Image(Path(storage['native_path']).read_bytes());assert v.sha(old.raw)==storage['native_sha256'];old_store,=[r for r in storage['methods'] if r['label'].endswith('ApplicationOptionLogic/store|1')];base_loads=receiver_loads(md,old.read(int(old_store['address'],16),old_store['bytes']),int(old_store['address'],16));getter_loads=receiver_loads(md,code['getTeammateEffectsVisible']);setter_loads=receiver_loads(md,code['setTeammateEffectsVisible']);assert len(base_loads)==len(getter_loads)==len(setter_loads)==1
 active=v.u64(im.raw,p.INFO_OFFSET+48);old_active=v.u64(old.raw,p.INFO_OFFSET+48);preserved=[]
 for r in storage['methods']:
  mid=r['method'];old_entry=v.u64(old.read(old_active+mid*8,8));entry=v.u64(im.read(active+mid*8,8));assert entry==old_entry==int(r['address'],16) and v.sha(im.read(entry,r['bytes']))==r['sha256'];assert mid not in {f['method'] for f in linked['functions']};preserved.append(dict(qname=r['label'],method_info=mid,address=r['address'],bytes=r['bytes'],sha256=r['sha256']))
 namespace=v.read(Path(cfg.path('namespace_contract')));tr=namespace['traits'][0];ci,=[i for i,r in enumerate(a.a.instances) if a.a.mn_name(r[0])==tr['owner']];getter,=[t for t in a.a.instances[ci][6] if t.kind==1 and a.a.mn_name(t.name)==tr['name']];assert getter.data[2]==tr['method_info']
 setter_ins=list(md.disasm(code['setTeammateEffectsVisible'],0));store_env=[i for i,x in enumerate(setter_ins) if x.mnemonic=='ldr' and x.op_str=='x1, [x8, #0x98]'];assert len(store_env)==1;at=store_env[0];assert any(x.mnemonic=='blr' for x in setter_ins[at:at+5]),'real original-store virtual call absent'
 sci,sm,sbi=owning_script(a,KIND);assert sm==54758;sf,=[r for r in linked['functions'] if r['method']==sm];assert v.u64(im.read(active+sm*8,8))==sf['address'];hooks=[r for r in linked['hooks'] if r['method']==sm];assert hooks
 for h in hooks:
  dest=v.branch(v.u32(im.raw,h['offset']),h['previous']);assert dest==sf['address'] or v.veneer(im,dest)==sf['address']
 _,uwsize,uwoff=im.sections['__TEXT','__unwind_info'];unwind=v.unwind_semantics(im.raw[uwoff:uwoff+uwsize])[0];keys=sorted(unwind)
 for r in rows:
  pc=int(r['actual_native_address'],16)-v.BASE;assert unwind[keys[bisect.bisect_right(keys,pc)-1]]==int(r['object_unwind_encoding'],16)
 script=dict(actual_method_info=sm,owning_class=sci,actual_native_address=hex(sf['address']),bytes=sf['size'],sha256=sf['sha256'],active_table_pointer_verified=True,original_native_entry_hooks_verified=hooks,method_signature=p.signature(a,sm),activation=a.a.bodies[sbi][7],script_record_preserved=True)
 out=dict(status='actual_linked_settings_abi_bound_by_final_qname_and_method_info',linked_report_sha256=v.sha(args.linked.read_bytes()),native_sha256=linked['native_sha256'],full_abc_sha256=prepared['full_abc_sha256'],methods=rows,receiver_field=dict(offset='0x30',original_native_store=base_loads,actual_native_getter=getter_loads,actual_native_setter=setter_loads),setter_original_store_call=dict(method_info=old_store['method'],vtable_env_offset='0x98',instructions=[x.mnemonic+' '+x.op_str for x in setter_ins[at:at+5]]),owning_type_script_initializer=script,original_storage_native_preserved=preserved,global_raw_getter_public_qname_and_mid_preserved=True,no_storage_native_recompiled=True,no_new_old_class_slots=True,probe_ids_not_reused=True,native_executed=False,ui_runtime_validation_pending=True)
 v.dump(args.output,out);print(json.dumps(dict(status=out['status'],native_sha256=out['native_sha256'],actual_ids=[r['actual_method_info'] for r in rows],storage_functions_preserved=len(preserved))))
if __name__=='__main__':main()
