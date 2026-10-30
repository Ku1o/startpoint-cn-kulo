"""Freeze the actual 17 source bodies/closures before any iOS semantic graft.

Future bounded stage only. Uses the actual cumulative SWF, not a model or the
1008094 whole package. Does not open an APK/IPA or modify any source carrier.
"""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,copy,json,struct,zlib
import repair_common as c
import storage_adapter

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-swf',type=Path,required=True)
    ap.add_argument('--targets',type=Path,required=True)
    ap.add_argument('--before-swf',type=Path,default=Path(cfg.path('before_swf')))
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();job=c.bounded_job();out=c.fresh(args.output)
    c.require(args.source_swf.resolve().is_relative_to(c.CLIENT.resolve()),'Source SWF must be the task client carrier')
    c.require(args.source_swf.stat().st_size<=32*1024**2,'Compressed source SWF bound')
    raw=args.source_swf.read_bytes();c.require(c.sha(raw)==c.SOURCE_SHA,'Frozen final Android SWF changed')
    c.require(raw[:3] in (b'CWS',b'FWS'),'Unsupported source compression')
    if raw[:3]==b'CWS':
        decoder=zlib.decompressobj();data=decoder.decompress(raw[8:],64*1024**2+1)
        c.require(len(data)<=64*1024**2 and decoder.eof and not decoder.unconsumed_tail,'SWF inflation bound')
    else:data=raw[8:]
    c.require(len(data)+8==struct.unpack_from('<I',raw,4)[0],'SWF declared length differs')
    p=c.framework();swftags=p.asm.load_abc_module('swftags');units={}
    for kind,at,header,size in swftags.iter_tags(data):
        if kind!=82:continue
        payload=data[at+header:at+header+size];end=payload.index(b'\0',4)
        name=payload[4:end].decode('utf-8')
        if name not in ('boot_ffc6','content_operations'):continue
        c.require(name not in units,'Duplicate selected DoABC name: '+name)
        c.require(len(payload)-end-1<=24*1024**2,'Selected ABC size bound')
        unit=payload[end+1:];units[name]=dict(raw=unit,view=c.view(p,p.abcfmt.ABC(unit)))
    c.require(set(units)=={'boot_ffc6','content_operations'},'Two exact source units required')
    plan=c.read(args.targets,128*1024)
    c.require(len(plan['methods'])==17,'Business plan changed')
    records=[];unit_jobs={name:set() for name in units}
    for row in plan['methods']:
        label=c.semantic_label(row);name='content_operations' if row['group']=='tutorial' else 'boot_ffc6'
        v=units[name]['view'];bi=c.body_for(v,label);body=v.a.bodies[bi];unit_jobs[name].add(body[0])
        records.append(dict(**row,label=label,source_unit=name,source_method=body[0],source_body=bi,
            source_code_sha256=c.sha(body[5]),signature=c.signature(v,body[0]),header=body[:5],
            activation=p.activation_traits(v,body),normalized_body_sha256=c.sha(repr(p.freeze(v.normalized(bi))).encode())))
    closures=[];ledger_audits=[];hard_slots=[];dispatch=[];static_references=[]
    for name,roots in unit_jobs.items():
        v=units[name]['view'];by_mid={b[0]:i for i,b in enumerate(v.a.bodies)}
        pending=list(roots);seen=set();total_instructions=0
        while pending:
            mid=pending.pop()
            if mid in seen:continue
            seen.add(mid);c.require(len(seen)<=128,'Source closure bound exceeded')
            c.require(mid in by_mid,'Referenced source method has no actual body')
            bi=by_mid[mid];body=v.a.bodies[bi];instructions=p.asm.decode(body[5]);total_instructions+=len(instructions)
            c.require(total_instructions<=100000,'Source instruction bound exceeded')
            if mid not in roots:
                closures.append(dict(source_unit=name,source_method=mid,source_body=bi,
                    label=v.labels.get(mid),signature=c.signature(v,mid),header=body[:5],
                    source_code_sha256=c.sha(body[5]),activation=p.activation_traits(v,body)))
            for trait in body[7]:
                if trait.data[0] in ('method','function'):pending.append(trait.data[2])
            for at,ins in enumerate(instructions):
                if ins.op==0x40:pending.append(ins.args[0])
                elif ins.op==0x44:
                    label=v.labels.get(ins.args[0])
                    static_references.append(dict(unit=name,method=mid,at=at,target=ins.args[0],label=label))
                    # Existing named static callees retain their current iOS
                    # implementation. Only anonymous source dependencies are
                    # cloned; the preparer rejects any unresolved named callee.
                    if label is None or '/closure:' in label:pending.append(ins.args[0])
                if ins.op in (0x6c,0x6d,0x6e,0x6f):hard_slots.append(dict(unit=name,method=mid,at=at,opcode=ins.op,slot=ins.args[0]))
                if ins.op in (0x43,0x4b,0x4d):dispatch.append(dict(unit=name,method=mid,at=at,opcode=ins.op,args=ins.args))
        if name=='boot_ffc6':
            owner_ci,=[i for i,r in enumerate(v.a.instances) if v.a.mn_name(r[0])==storage_adapter.OWNER]
            owner_mid=v.a.classes[owner_ci][0]
            script_mids={mid for mid,traits in v.a.scripts if any(t.kind==4 and t.data[2]==owner_ci for t in traits)}
            ledger_trait,=[t for t in v.a.classes[owner_ci][1] if v.a.mn_name(t.name).split('::')[-1]==storage_adapter.NAME]
            c.require(ledger_trait.kind==0 and ledger_trait.data[2:]==[0,0,None],'Source ledger wildcard/default changed')
            ledger_rows=[dict(source_multiname=ledger_trait.name,name=storage_adapter.NAME,qname=v.a.mn_name(ledger_trait.name))]
            ledger_initializers=[];initializer_seen=set();initializer_pending=list({owner_mid}|script_mids)
            initializer_instructions=0
            while initializer_pending:
                mid=initializer_pending.pop()
                if mid in initializer_seen:continue
                initializer_seen.add(mid);c.require(len(initializer_seen)<=128,'Ledger initializer closure bound exceeded')
                c.require(mid in by_mid,'Ledger initializer graph references a method without ABC body')
                body=v.a.bodies[by_mid[mid]];instructions=p.asm.decode(body[5]);initializer_instructions+=len(instructions)
                c.require(initializer_instructions<=100000,'Ledger initializer instruction bound exceeded')
                children=[]
                for trait in body[7]:
                    if trait.data[0] in ('method','function'):
                        initializer_pending.append(trait.data[2]);children.append(dict(activation_trait=True,method=trait.data[2]))
                for ins in instructions:
                    if ins.op in (0x40,0x44):
                        initializer_pending.append(ins.args[0]);children.append(dict(opcode=ins.op,method=ins.args[0]))
                ledger_initializers.append(dict(source_method=mid,label=v.labels.get(mid),code_sha256=c.sha(body[5]),children=children,
                                                included_as_new_compile_target=False))
                for at,ins in enumerate(instructions):
                    if ins.op in (0x6c,0x6d,0x6e,0x6f):
                        hard_slots.append(dict(unit=name,method=mid,at=at,opcode=ins.op,slot=ins.args[0],initializer=True))
                    if ins.op in (0x43,0x4b,0x4d):
                        dispatch.append(dict(unit=name,method=mid,at=at,opcode=ins.op,args=ins.args,initializer=True))
            ledger_audits=storage_adapter.audit_accesses(p,v,ledger_rows,seen|initializer_seen)
    c.require(not hard_slots,'Source has hard slot operations requiring explicit review: '+str(hard_slots[:5]))
    c.require(not dispatch,'Source contains unaudited raw dispatch: '+str(dispatch[:5]))
    out.mkdir(parents=True)
    unit_rows=[]
    for name,row in units.items():
        path=out/(name+'.abc');path.write_bytes(row['raw'])
        unit_rows.append(dict(key=name,file=str(path),sha256=c.sha(row['raw']),bytes=len(row['raw'])))
    before=c.swf_units(p,args.before_swf,c.BEFORE_SWF_SHA,{'boot_ffc6'})['boot_ffc6']
    before_path=out/'before-boot_ffc6.abc';before_path.write_bytes(before)
    report=dict(status='actual17_source_bodies_and_required_source_method_closure_frozen_not_ios_AOT_verified',
        source_swf=str(args.source_swf.resolve()),source_swf_sha256=c.sha(raw),targets_plan_sha256=c.sha(args.targets.read_bytes()),
        business_methods=records,closure_methods=closures,units=unit_rows,ledger_accesses=ledger_audits,
        direct_static_references=static_references,
        before_main=dict(file=str(before_path),sha256=c.sha(before),source_swf=str(args.before_swf.resolve()),source_swf_sha256=c.BEFORE_SWF_SHA),
        ledger_initializer_audit=ledger_initializers,hard_slot_operations=hard_slots,raw_dispatch_operations=dispatch,
        business_method_count=17,actual_ios_aot_count=None,sidecar_lifecycles_not_yet_added=True,
        jobAtEntry=job,old_carriers_modified=False,native_executed=False)
    c.dump(out/'source-contract.json',report)
    print(json.dumps(dict(status=report['status'],business_methods=17,source_closures=len(closures),ledger_accesses=len(ledger_audits['accesses']))))

if __name__=='__main__':main()
