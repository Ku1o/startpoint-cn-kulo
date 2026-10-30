"""Prepare the reviewed actual source delta on settings-r1, not on R11.

Future bounded stage. This draft must first consume a real Stage1 report and
source freeze; unresolved stub/platform/activation differences fail closed.
"""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,copy,gc,json,types
import repair_common as c
import storage_adapter as storage

POOL=('ints','uints','doubles','strings','namespaces','ns_sets','multinames')

def normalized(p,v,bi,platform):
    original=v.a.bodies[bi]
    canonical=copy.deepcopy(original)
    platform.constant_casts(canonical,v.a,p)
    v.a.bodies[bi]=canonical
    try:return p.freeze(v.normalized(bi))
    finally:v.a.bodies[bi]=original

def tutorial_guard(p,v,body):
    instructions=p.asm.decode(body[5]);rows=v.normalized(c.body_for(v,'cn.content::ContentOperationsState$/gachaDateText|1'))[0]
    c.require([x.op for x in instructions[7:20]]==[0x5d,0xd2,0x46,0x11,0x27,0x48,0x09,0xd2,0x46,0x11,0x27,0x48,0x09],
              'Current tutorial body guard shape differs')
    c.require('gachaSharedDates' in str(rows[7]) and 'gachaSharedDates' in str(rows[9]) and
              'get_showPeriod' in str(rows[15]),'Tutorial guard semantic names differ')
    c.require(instructions[10].target==13 and instructions[16].target==19 and not body[6],
              'Tutorial guard branch/exception shape differs')
    order=list(range(7))+list(range(14,20))+list(range(7,14))+list(range(20,len(instructions)))
    mapping={old:new for new,old in enumerate(order)}
    result=[copy.deepcopy(instructions[i]) for i in order]
    for ins in result:
        c.require(ins.cases is None and ins.default is None,'Unexpected tutorial switch')
        if ins.target is not None:ins.target=mapping[ins.target]
    reverse=[copy.deepcopy(result[mapping[i]]) for i in range(len(order))]
    inverse={new:old for old,new in mapping.items()}
    for ins in reverse:
        if ins.target is not None:ins.target=inverse[ins.target]
    c.require(p.asm.encode(reverse)[0]==body[5],'Tutorial permutation reverse failed')
    changed=copy.deepcopy(body);changed[5]=p.asm.encode(result)[0];p.check_body(changed,v.a)
    return changed,dict(strategy='current_iOS_body_only_reversible_guard_permutation',old_to_new_instruction=mapping)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--inspection',type=Path,required=True)
    ap.add_argument('--source-contract',type=Path,required=True);ap.add_argument('--sidecar-report',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    job=c.bounded_job();out=c.fresh(args.output);inspection=c.read(args.inspection)
    source_contract=c.read(args.source_contract);sidecar=c.read(args.sidecar_report,128*1024)
    c.require(inspection['previousIdentityEvidenceReused']['fullAbcSha256']==c.ABC_SHA,'Wrong inspected ABC')
    c.require(inspection['previousIdentityEvidenceReused']['nativeSha256']==c.NATIVE_SHA,'Wrong inspected native evidence')
    c.require(sidecar['inspection_sha256']==c.sha(args.inspection.read_bytes()),'Sidecar/inspection lineage differs')
    c.require(source_contract['source_swf_sha256']==c.SOURCE_SHA and source_contract['business_method_count']==17,
              'Wrong frozen17 source contract')
    c.require(not source_contract['hard_slot_operations'] and not source_contract['raw_dispatch_operations'],
              'Unreviewed raw source slot/dispatch operations')
    c.require(not inspection['ledger']['currentTraits'] and not inspection['ledger']['proposedNewSidecarExists'],
              'Ledger/sidecar already exists')
    current_by_label={c.semantic_label(row):row for row in inspection['targets']}
    for row in inspection['targets']:
        c.require(row['status']!='missing_old_target_blocked','Required old QName not found by Stage1')
        c.require(not row.get('protectedDispatchOverlap'),'Business target overlaps platform wrapper; dedicated adapter required')
    p=c.framework();raw=(c.BASE_FULL).read_bytes();c.require(c.sha(raw)==c.ABC_SHA,'Frozen ABC changed')
    target=c.view(p,p.abcfmt.ABC(raw));old=copy.deepcopy(target.a);old_count=len(old.methods)
    platform=c.module('acceptance_platform_methods',Path(cfg.local('settings/recipe/platform_methods.py')))
    sources={}
    for unit in source_contract['units']:
        path=Path(unit['file']);c.require(path.resolve().is_relative_to(c.TASK.resolve()),'Frozen source path outside task')
        data=path.read_bytes();c.require(c.sha(data)==unit['sha256'],'Source ABC changed')
        sources[unit['key']]=c.view(p,p.abcfmt.ABC(data))
    main_source=sources['boot_ffc6'];ledger_rows=storage.definitions(target,main_source)
    helper_raw=Path(sidecar['abc']).read_bytes();c.require(c.sha(helper_raw)==sidecar['abc_sha256'],'Sidecar ABC changed')
    helper=c.view(p,p.abcfmt.ABC(helper_raw))
    storage_proof=storage.import_and_install(p,target,main_source,helper,c.SOURCE.parent,ledger_rows)
    target=c.view(p,target.a)
    jobs_by_unit={key:[] for key in sources}
    for row in source_contract['business_methods']:
        jobs_by_unit[row['source_unit']].append(dict(row,closure=False))
    for row in source_contract['closure_methods']:
        jobs_by_unit[row['source_unit']].append(dict(row,closure=True))
    records=[];changed_existing=set();static_proofs=[];before_view=None;new_named=set()
    for unit,jobs in jobs_by_unit.items():
        source=sources[unit];target=c.view(p,target.a);importer=p.Importer(target,source)
        for row in jobs:
            sb=source.a.bodies[row['source_body']]
            c.require(sb[0]==row['source_method'] and c.sha(sb[5])==row['source_code_sha256'],'Source method/body mismatch')
            label=row['label'];hits=target.by_label.get(label,[])
            if hits and not row['closure']:
                c.require(len(hits)==1,'Current QName is ambiguous: '+label)
                ti,=hits;mid=target.a.bodies[ti][0]
                c.require(c.signature(target,mid)==c.signature(source,sb[0]),'Existing MethodInfo ABI/signature differs: '+label)
                c.require(current_by_label[label]['actualMethodInfo']==mid,'Actual MID differs from Stage1')
                c.require(c.sha(target.a.bodies[ti][5])==current_by_label[label]['abcBody']['codeSha256'],
                          'Current target body differs from Stage1')
                row['target_body']=ti
            else:
                mid=len(target.a.methods);target.a.methods.append(importer.info(sb[0]))
                row['target_body']=None
                if not row['closure']:new_named.add(mid)
            importer.methods[sb[0]]=mid;row['target_method']=mid
        # Append only selected new method traits. No Android storage slot is copied.
        owner_index={target.a.mn_name(r[0]):i for i,r in enumerate(target.a.instances)}
        selected={row['source_method']:row for row in jobs if not row['closure'] and row['target_body'] is None}
        for si,(inst,cls) in enumerate(zip(source.a.instances,source.a.classes)):
            owner=source.a.mn_name(inst[0])
            for static,traits in ((False,inst[6]),(True,cls[1])):
                for trait in traits:
                    if trait.kind not in (1,2,3) or trait.data[2] not in selected:continue
                    c.require(owner in owner_index,'New owner class requires an explicit class adapter')
                    ci=owner_index[owner];after=target.a.classes[ci][1] if static else target.a.instances[ci][6]
                    copied=importer.trait(trait)
                    c.require(not any(t.name==copied.name and t.kind==copied.kind for t in after),'New method trait collision')
                    after.append(copied)
        for reference in source_contract['direct_static_references']:
            if reference['unit']!=unit:continue
            sm=reference['target'];tm=importer.methods.get(sm)
            c.require(tm is not None,'Unmapped named callstatic dependency: '+str(reference))
            c.require(c.signature(source,sm)==c.signature(target,tm),'Retained native callstatic signature differs')
            static_proofs.append(dict(source_unit=unit,source_method=sm,target_method=tm,label=reference['label'],
                                      signature=c.signature(target,tm),existing_native_retained=tm<old_count))
        for row in jobs:
            label=row['label'];si=row['source_body'];mid=row['target_method'];ti=row['target_body']
            before=copy.deepcopy(target.a.bodies[ti]) if ti is not None else None
            adaptation=None
            if row.get('group')=='tutorial':
                c.require(before is not None,'Tutorial must patch the existing iOS body')
                body,adaptation=tutorial_guard(p,target,before)
                platform_proof=dict(changed=False,equipment_dispatch=[],constant_casts={})
            else:
                if before is not None and current_by_label[label]['abcBody']['classification']=='nontrivial_ABC_body':
                    if before_view is None:
                        entry=source_contract['before_main'];data=Path(entry['file']).read_bytes()
                        c.require(c.sha(data)==entry['sha256'],'Frozen pre-repair Android ABC changed')
                        before_view=c.view(p,p.abcfmt.ABC(data))
                    bi=c.body_for(before_view,label)
                    c.require(normalized(p,target,ti,platform)==normalized(p,before_view,bi,platform),
                              'Current nonstub iOS semantics differ from before-repair source; local platform delta needed: '+label)
                scope=before[3] if before is not None else source.a.bodies[si][3]
                body=importer.body(si,mid,scope=scope)
                body,platform_proof=platform.adapt(body,target.a,p)
            if before is not None:
                c.require(p.activation_traits(target,before)==p.activation_traits(target,body),
                          'Existing activation ABI changed: '+label)
                target.a.bodies[ti]=body;changed_existing.add(mid)
            else:target.a.bodies.append(body)
            check=p.check_body(body,target.a)
            records.append(dict(method_id=mid,strategy='replace',label=label,source_tag=unit,source_body=si,
                source_method=row['source_method'],source_code_sha256=row['source_code_sha256'],
                before_code_sha256=c.sha(before[5]) if before is not None else None,
                after_code_sha256=c.sha(body[5]),adaptation=adaptation,platform_adaptation=platform_proof,
                validation=check,source_body_was_complete=True,native_runtime_equivalence_proven=False))
    target=c.view(p,target.a)
    # Local tutorial permutation must equal the complete final source semantics.
    tutorial,=[r for r in source_contract['business_methods'] if r['group']=='tutorial']
    c.require(normalized(p,target,c.body_for(target,tutorial['label']),platform)==
              normalized(p,sources[tutorial['source_unit']],tutorial['source_body'],platform),
              'Current iOS tutorial delta differs from frozen final helper semantics')
    target_ledger_rows=[dict(ledger_rows[0],source_multiname=p.Importer(target,main_source).pool('multinames',ledger_rows[0]['source_multiname']))]
    ledger_target_ids={r['method_id'] for r in records}
    target_accesses=storage.audit_accesses(p,target,target_ledger_rows,ledger_target_ids)
    for field in ('methods','metadata','scripts',*POOL):
        c.require(p.freeze(getattr(old,field))==p.freeze(getattr(target.a,field)[:len(getattr(old,field))]),'Old prefix changed: '+field)
    for before,after in zip(old.instances,target.a.instances):
        c.require(p.freeze(before[:-1])==p.freeze(after[:-1]) and p.freeze(before[-1])==p.freeze(after[-1][:len(before[-1])]),'Old instance layout changed')
        c.require(all(t.kind in (1,2,3) for t in after[-1][len(before[-1]):]),'Storage appended to old instance')
    for before,after in zip(old.classes,target.a.classes):
        c.require(before[0]==after[0] and p.freeze(before[1])==p.freeze(after[1][:len(before[1])]),'Old static layout changed')
        c.require(all(t.kind in (1,2,3) for t in after[1][len(before[1]):]),'Storage appended to old class')
    for before,after in zip(old.bodies,target.a.bodies):
        if before[0] not in changed_existing:c.require(p.freeze(before)==p.freeze(after),'Unselected old ABC body changed')
    # All source/old-prefix proofs are complete. Drop parsed Android units and
    # their Importer/View references before allocating the roundtrip ABC copy.
    sources.clear();before_view=None;main_source=None;helper=None;importer=None;source=None
    old=None;gc.collect()
    result=target.a.serialize();c.require(p.abcfmt.ABC(result).serialize()==result,'Prepared ABC does not roundtrip')
    previous=c.read(c.PREVIOUS_LINK);package=c.read(c.PREVIOUS_PACKAGE,128*1024)
    c.require(previous['native_sha256']==package['native_sha256']==c.NATIVE_SHA and package['ipa_sha256']==c.IPA_SHA,'Previous report lineage changed')
    source_ipa=copy.deepcopy(previous['source_ipa'])
    source_ipa.update(ipa=package['ipa'],ipa_sha256=c.IPA_SHA,native_sha256=c.NATIVE_SHA,swf_sha256=package['swf_sha256'],
                      size_bytes=package['size_bytes'],acceptance_status='offline_candidate')
    out.mkdir(parents=True);(out/'full.abc').write_bytes(result)
    total=len(target.a.methods)
    report=dict(status='prepared_actual_repair_delta_requires_AOT_and_native_ABI_verification',
        old_methods=old_count,total_methods=total,base_full_abc_sha256=c.ABC_SHA,full_abc_file='full.abc',
        full_abc_sha256=c.sha(result),full_abc_sha1=__import__('hashlib').sha1(result).hexdigest(),source_ipa=source_ipa,
        baseline_native_file=previous['native_file'],baseline_swf_file=previous['swf_file'],
        baseline_runtime_abc_sha256=previous['runtime_abc_sha256'],methods=records,
        new_method_ids=list(range(old_count,total)),compiled_helpers=list(range(old_count,total)),
        native_aliases=[],method_redirects=[],business_methods=17,
        source_contract=str(args.source_contract.resolve()),source_contract_sha256=c.sha(args.source_contract.read_bytes()),
        inspection=str(args.inspection.resolve()),inspection_sha256=c.sha(args.inspection.read_bytes()),
        storage=storage_proof,source_ledger_accesses=source_contract['ledger_accesses'],target_ledger_accesses=target_accesses,
        retained_callstatic=static_proofs,old_slots_unchanged=True,all_unselected_old_ABC_bodies_unchanged=True,
        old_platform_wrappers_modified=False,complete_source_bodies_imported_without_stub_prefix=True,
        native_semantic_equivalence_executed=False,jobAtEntry=job)
    c.dump(out/'port.json',report)
    print(json.dumps(dict(status=report['status'],business_methods=17,replaced=len(changed_existing),new_methods=total-old_count,
                          source_closures=len(source_contract['closure_methods']),actual_aot_targets=len(changed_existing)+total-old_count)))

if __name__=='__main__':main()
