"""Bind actual-package bytes to compiled wildcard accessor/callsite ABI.

Uses exact arm64 instruction contracts observed in this compiler's real output,
and small destructive in-memory controls. Does not execute iOS native methods.
The whole-native identity is reused only from the actual-IPA independent check.
"""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,copy,json,struct
import repair_common as c
import storage_adapter as storage

def words(raw):
    c.require(len(raw)%4==0,'Arm64 function alignment')
    return list(struct.unpack('<'+'I'*(len(raw)//4),raw))

def one_sequence(rows,pattern,label):
    hits=[i for i in range(len(rows)-len(pattern)+1) if rows[i:i+len(pattern)]==pattern]
    c.require(len(hits)==1,'Actual compiled ABI pattern differs: '+label)
    return hits[0]*4

def patterns(getter,setter,caller,barrier_offset):
    g,s,a=map(words,(getter,setter,caller))
    gp=one_sequence(g,[0xaa0103f3],'getter preserves own Env x1 in x19')
    load=one_sequence(g,[0xf9401900],'getter LDR x0,[sidecar x8,#0x30] full Atom64')
    getter_ret=one_sequence(g,[0xd65f03c0],'getter normal return')
    tail=[0xf9401900,0xf94007e8,0xf9003288,0xd10043bf,0xa9417bfd,0xa8c24ff4,0xd65f03c0]
    c.require(g[load//4:getter_ret//4+1]==tail,'Getter Atom return is rewritten between slot load and RET')
    se=one_sequence(s,[0xaa0203f3],'setter preserves own Env x2 in x19')
    sv=one_sequence(s,[0xaa0103f4],'setter preserves full Atom x1 in x20')
    field=one_sequence(s,[0x9100c022,0xaa1403e3],'setter field address x2=x1+0x30, Atom x3=x20')
    c.require(field+8==barrier_offset and barrier_offset<one_sequence(s,[0xd65f03c0],'setter normal return'),
              'Setter Atom barrier sequence does not precede normal RET')
    c.require((s[barrier_offset//4]&0xfc000000)==0x94000000,'Setter Atom barrier is not BL')
    getter_call=one_sequence(a,[0xf9400808,0xf9405501,0xf9400828,0xf9402908,0xd63f0100],
        'caller getter loads own MethodEnv from VTable+0xa8 into x1 then MethodInfo.native.handler')
    setter_call=one_sequence(a,[0xf9400808,0x9100075a,0xaa1a03e1,0xf9405902,0xf9400848,0xf9402908,0xd63f0100],
        'caller setter boxes dictionary full Atom into x1 and loads own MethodEnv VTable+0xb0 into x2')
    return dict(getter_env_save_offset=gp,getter_atom_load_offset=load,getter_atom_load_bytes='001940f9',
        setter_env_save_offset=se,setter_atom_save_offset=sv,setter_slot_address_offset=field,
        setter_barrier_offset=barrier_offset,storage_offset=0x30,
        getter_caller_sequence_offset=getter_call,getter_caller_blr_offset=getter_call+16,
        setter_caller_sequence_offset=setter_call,setter_caller_blr_offset=setter_call+24,
        getter_env_vtable_offset=0xa8,setter_env_vtable_offset=0xb0,
        getter_fixed_load_to_ret_words=[f'{word:08x}' for word in tail],
        getter_load_to_ret_writes_x0_only_at_initial_64bit_load=True,
        getter_return='64-bit Atom in x0',setter_value='64-bit Atom x1 -> x20 -> atomWriteBarrier x3',
        method_env='getter receives own x1; setter receives own x2; caller loads each from class VTable',
        sidecar_storage_receiver='new sidecar ClassClosure from getlex; not old InstantAbility static storage')

def negative_controls(g,s,a,offset):
    base=patterns(g,s,a,offset);cases=[]
    def mutate(raw,at,word):
        changed=bytearray(raw);struct.pack_into('<I',changed,at,word);return bytes(changed)
    mutations=[
        ('getter_narrowed_to_32bit',mutate(g,base['getter_atom_load_offset'],0xb9403100),s,a),
        ('getter_return_narrowed_after_load',mutate(g,base['getter_atom_load_offset']+4,0x2a0003e0),s,a),
        ('setter_value_narrowed_to_32bit',g,mutate(s,base['setter_atom_save_offset'],0x2a0103f4),a),
        ('setter_wrong_env_argument',g,mutate(s,base['setter_env_save_offset'],0xaa0103f3),a),
        ('setter_wrong_storage_slot',g,mutate(s,base['setter_slot_address_offset'],0x9100e022),a),
        ('getter_caller_wrong_env',g,s,mutate(a,base['getter_caller_sequence_offset']+4,0xaa1403e1)),
        ('setter_caller_wrong_env_slot',g,s,mutate(a,base['setter_caller_sequence_offset']+12,0xf9405502))]
    for name,gg,ss,aa in mutations:
        try:patterns(gg,ss,aa,offset)
        except ValueError:cases.append(name)
        else:raise ValueError('Atom ABI negative control accepted: '+name)
    return dict(passed=len(cases),rejected=cases,scope='actual compiled function copies in memory only')

def branch_target(word,pc):
    c.require(word&0xfc000000==0x94000000,'Expected linked BL')
    value=word&0x3ffffff
    if value&(1<<25):value-=1<<26
    return pc+value*4

def native_segments(stream):
    stream.seek(0);header=stream.read(32);count,size=struct.unpack_from('<II',header,16)
    c.require(count<=128 and size<=65536,'Native command bound')
    raw=stream.read(size);at=0;result=[]
    for _ in range(count):
        kind,length=struct.unpack_from('<II',raw,at);row=raw[at:at+length]
        if kind==0x19:
            vm,vs,off,fs=struct.unpack_from('<QQQQ',row,24);result.append(dict(vm=vm,off=off,fs=fs))
        at+=length
    return result

def sdk_layout():
    path=c.SDK/'lib/aot/lib/air-fields.arm64-air.txt'
    c.require(path.stat().st_size<=1024*1024,'SDK fields text bound')
    with path.open('rb') as stream:raw=stream.read(1024*1024+1)
    c.require(len(raw)<=1024*1024,'SDK fields text grew beyond bound')
    expected={('avmplus::ScriptObject','vtable'):16,('avmplus::VTable','methods'):128,
              ('avmplus::MethodEnv','method'):16,('avmplus::MethodInfo','native'):72,
              ('avmplus::MethodInfo::NativeInfo','handler'):8,('avmplus::ClassClosure',''):48}
    found={};evidence=[];owner=None
    for number,line in enumerate(raw.decode('utf-8').splitlines(),1):
        tokens=line.split()
        if not tokens:continue
        if tokens[0]=='struct':
            owner=tokens[2]
            if (owner,'') in expected:
                found[(owner,'')]=int(tokens[1]);evidence.append(dict(line=number,text=line))
        elif tokens[0]=='field' and owner is not None:
            key=(owner,tokens[-1])
            if key in expected:found[key]=int(tokens[1]);evidence.append(dict(line=number,text=line))
    c.require(found==expected,'Actual SDK AOT layout fields differ')
    return dict(path=str(path),sha256=c.sha(raw),fields={owner+'/'+field:value for (owner,field),value in found.items()},
                actual_lines=evidence)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--package-report',type=Path,required=True)
    ap.add_argument('--verification',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();job=c.bounded_job();out=c.fresh(args.output)
    package=c.read(args.package_report,128*1024);verification=c.read(args.verification)
    linked=c.read(package['link_report']);port=c.read(linked['source_prepare_report'])
    c.require(package['native_sha256']==verification['native_sha256']==linked['native_sha256'],'Actual package/native binding differs')
    c.require(package['ipa_sha256']==verification['ipa_sha256'],'Actual IPA identity differs')
    c.require(verification['status']=='independent_actual_stage_package_readback_passed','Actual independent package check required first')
    detail=c.read(verification['detail_report'],32*1024**2)
    records=port['storage']['proxy_records'];c.require(len(records)==1,'Exactly one ledger proxy pair required')
    pair=records[0];getter,=[r['method_id'] for r in pair['accessors'] if r['kind']=='getter']
    setter,=[r['method_id'] for r in pair['accessors'] if r['kind']=='setter']
    caller,=[r['method_id'] for r in port['methods'] if r['label'].endswith('InstantAbility/wfxAccumulateHpLoss|1')]
    p=c.framework();full=Path(linked['full_abc_file']).read_bytes();c.require(c.sha(full)==package['full_abc_sha256'],'Final full ABC differs')
    view=c.view(p,p.abcfmt.ABC(full));a=view.a
    c.require(a.methods[getter][0]==0 and a.methods[getter][1]==[],'Getter MethodInfo is not return*()')
    c.require(a.mn_name(a.methods[setter][0])=='void' and a.methods[setter][1]==[0],'Setter MethodInfo is not void(*)')
    ci,=[i for i,r in enumerate(a.instances) if a.mn_name(r[0])==storage.OWNER]
    traits=[t for t in a.classes[ci][1] if a.mn_name(t.name).split('::')[-1]==storage.NAME]
    c.require({(t.kind,t.data[2]) for t in traits}=={(2,getter),(3,setter)},'Original owner accessors differ')
    c.require(not any(t.kind in (0,6) for t in traits),'Ledger storage was added to old owner')
    state_ci,=[i for i,r in enumerate(a.instances) if a.mn_name(r[0])==storage.STATE]
    field,=[t for t in a.classes[state_ci][1] if t.kind==0]
    c.require(a.mn_name(field.name)=='hpLossLedger' and field.data[2:]==[0,0,None],'Sidecar wildcard/undefined field differs')
    scripts=[mid for mid,ts in a.scripts if any(t.kind==4 and t.data[2]==state_ci for t in ts)]
    c.require(len(scripts)==1,'Unique sidecar owning initializer required')
    lifecycle={a.instances[state_ci][5],a.classes[state_ci][0],scripts[0]}
    c.require(lifecycle==set(port['storage']['source_lifecycle_method_ids']),'Sidecar lifecycle set incomplete')
    bodies={b[0]:b for b in a.bodies}
    for mid in (getter,setter):
        accesses=p.asm.decode(bodies[mid][5]);states=[i.args[0] for i in accesses if i.op==0x60]
        c.require([a.mn_name(i) for i in states]==[storage.STATE],'Accessor reads an old owner instead of new storage class')
    c.require(all(i.op not in (0x61,0x68,0x42,0x4a) for i in p.asm.decode(bodies[a.classes[state_ci][0]][5])),
              'Sidecar cinit eagerly writes/allocates state')
    fn_rows={r['method']:r for r in linked['functions']};proof_rows={r['method']:r for r in detail['functions']}
    wanted={getter,setter,caller}|lifecycle
    actual={};proofs=[]
    with Path(linked['native_file']).open('rb') as stream:
        segments=native_segments(stream)
        def read_at(va,size):
            hits=[r['off']+va-r['vm'] for r in segments if r['vm']<=va and va+size<=r['vm']+r['fs']]
            c.require(len(hits)==1 and size<=1024*1024,'Sparse Atom ABI native range refused')
            stream.seek(hits[0]);raw=stream.read(size);c.require(len(raw)==size,'Short native ABI read');return raw
        stream.seek(104549248);info=stream.read(168);active=struct.unpack_from('<Q',info,48)[0];activation=struct.unpack_from('<Q',info,88)[0]
        for mid in sorted(wanted):
            row=fn_rows[mid];proof=proof_rows[mid];data=read_at(row['address'],row['size'])
            c.require(c.sha(data)==row['sha256']==proof['sha256'],'Function differs from actual IPA/object relocation proof')
            c.require(struct.unpack('<Q',read_at(active+mid*8,8))[0]==row['address'],'Actual active table does not reach compiled function')
            descriptor=read_at(activation+mid*16,16)
            c.require(a.methods[mid][3]&2==0 and bodies[mid][7]==[],'Unexpected activation needs another ABI proof')
            c.require(struct.unpack_from('<i',descriptor)[0]==-1 and struct.unpack_from('<Q',descriptor,8)[0]==0,
                      'Unexpected native activation initializer/handler')
            actual[mid]=data;proofs.append(dict(method=mid,address=row['address'],bytes=row['size'],sha256=c.sha(data),
                symbol=proof['symbol'],object=proof['object'],activation_hex=descriptor.hex(),code_hex=data.hex()))
    barriers=[r for r in linked['relocations'] if r['method']==setter and r['type']==2 and 'atomWriteBarrier' in r['symbol']]
    c.require(len(barriers)==1,'Actual setter must call Atom write barrier exactly once')
    barrier,=barriers;offset=barrier['offset'];word=struct.unpack_from('<I',actual[setter],offset)[0]
    c.require(branch_target(word,fn_rows[setter]['address']+offset)==barrier['branch_target'],'Actual Atom barrier BL target differs')
    actual_sdk=sdk_layout()
    machine=patterns(actual[getter],actual[setter],actual[caller],offset)
    negatives=negative_controls(actual[getter],actual[setter],actual[caller],offset)
    report=dict(status='actual_ipa_compiled_atom_accessor_callsite_and_lifecycle_abi_verified_offline',
        ipa=package['ipa'],ipa_sha256=package['ipa_sha256'],native_sha256=package['native_sha256'],
        full_abc_sha256=package['full_abc_sha256'],actual_full_native_sha_reused_from_independent_package_check=True,
        independent_verification=str(args.verification.resolve()),independent_verification_sha256=c.sha(args.verification.read_bytes()),
        getter_method=getter,setter_method=setter,caller_method=caller,type_index=0,declared_default='undefined',
        getter_signature=c.signature(view,getter),setter_signature=c.signature(view,setter),sidecar=storage.STATE,
        sidecar_lifecycle_methods=sorted(lifecycle),old_owner_new_storage_slots=0,
        machine_abi=machine,atom_write_barrier=barrier,functions=proofs,negative_controls=negatives,
        sdk_layout_contract=actual_sdk,
        initializer_declaration_default_verified=True,runtime_initialized_atom_value_observed=False,
        native_executed=False,device_tested=False,jobAtEntry=job,
        scope='actual compiled bytes and metadata/ABI only; no iOS native execution or gameplay acceptance')
    out.mkdir(parents=True);c.dump(out/'atom-abi.json',report)
    print(json.dumps(dict(status=report['status'],getter=getter,setter=setter,slot=0x30,negative_controls=len(negatives['rejected']),ipa_sha256=package['ipa_sha256'])))

if __name__=='__main__':main()
