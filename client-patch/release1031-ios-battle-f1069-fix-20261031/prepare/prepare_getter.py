"""Append the missing real dash getter to an unchanged leaf iOS class.

No AOT, linking, packaging, admission changes, registry updates or device work
is performed here. Every old body and MethodInfo remains immutable.
"""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse,copy,hashlib,importlib.util,json,sys,types
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
CLIENT=HERE.parents[1]
sys.path.insert(0,str(CLIENT/'lens0907-0908'))
import build_swf as p

TASK=Path(str(fc.client() / 'revision-ios-battle-f1069-fix-20261031'))
PREVIOUS=TASK.parent/'revision-ios-dispatch-fix-20261031'
BASE_ABC=PREVIOUS/'prepare-review/all25-run02/full.abc'
BASE_SHA='7568bf806d123809c89a0d1ad7882135299f229778887bfd300b24c8d165a530'
ANDROID=TASK.parent/'lite195/input/r11.swf'
OWNER='pinball.scene.battle.battle.ability::BattleAbilityTotalizerImpl'
LABEL=OWNER+'/getTotalDashParameter|1'
BODY_SHA='debd69bf68464eaa104cb8d87d96d18a7773385bcd1f0fae1ac98d11137c4070'
OLD_COUNT=101872
POOL=('ints','uints','doubles','strings','namespaces','ns_sets','multinames')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def view(a):return p.View(types.SimpleNamespace(abc=a),p.asm)
def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def bounded_job():
    path=fc.tool('support/process/job_guard.py')
    spec=importlib.util.spec_from_file_location('battle_getter_bounded_guard',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.require_bounded_job(180)

def signature(a,mid):
    ret,params,name,flags,options,names=a.methods[mid]
    return dict(returns=a.mn_name(ret),parameters=[a.mn_name(x) for x in params],flags=flags,options=options)

def class_layout(a,owner):
    ci,=[i for i,r in enumerate(a.instances) if a.mn_name(r[0])==owner]
    r=a.instances[ci]
    subclasses=[dict(class_index=i,name=a.mn_name(x[0])) for i,x in enumerate(a.instances) if x[1]==r[0]]
    return ci,r,subclasses

def append_real_getter(target,source):
    """Append exactly one source body/MethodInfo/instance trait; return proof."""
    a=target.a;old=copy.deepcopy(a)
    assert len(a.methods)==OLD_COUNT,'current cumulative method count changed'
    ci,inst,children=class_layout(a,OWNER)
    assert inst[2]&1 and a.mn_name(inst[1])=='Object' and not children,'reviewed sealed leaf owner required'
    assert LABEL not in target.by_label,'getter is already present'
    old_methods=[(a.mn_name(t.name),t.kind,t.data[2]) for t in inst[6] if t.kind in (1,2,3)]
    assert not any(name=='getTotalDashParameter' for name,_,_ in old_methods)
    fields=[t for t in inst[6] if t.kind in (0,6) and a.mn_name(t.name)=='duringDashParameters']
    field,=fields;assert a.mn_name(field.data[2])=='Array','existing real Array storage contract required'
    source_ci,source_inst,source_children=class_layout(source.a,OWNER)
    source_bi,=source.by_label[LABEL];sb=source.a.bodies[source_bi];smid=sb[0]
    assert smid==100913 and len(sb[5])==44 and sha(sb[5])==BODY_SHA,'frozen real Android getter differs'
    assert signature(source.a,smid)==dict(returns='Number',parameters=['int'],flags=0,options=None)
    assert sb[6]==[] and sb[7]==[]
    instructions=p.asm.decode(sb[5])
    assert len(instructions)==24 and not any(x.op in (0x40,0x44,0x57,0x58,0x65,0x67,0x45,0x4e) for x in instructions)
    original_trait,=[t for t in source_inst[6] if t.kind==1 and t.data[2]==smid]
    assert not original_trait.attr and not original_trait.metadata and original_trait.data[1]==0
    importer=p.Importer(target,source);mid=len(a.methods);importer.methods[smid]=mid
    a.methods.append(importer.info(smid));body=importer.body(source_bi,mid)
    a.bodies.append(body);new_trait=importer.trait(original_trait);inst[6].append(new_trait)
    proof=p.check_body(body,a)
    fresh=view(a);bi,=fresh.by_label[LABEL]
    assert p.freeze(fresh.normalized(bi))==p.freeze(source.normalized(source_bi)),'imported production body semantics differ'
    assert signature(a,mid)==signature(source.a,smid)
    for key in POOL:
        assert p.freeze(getattr(a,key)[:len(getattr(old,key))])==p.freeze(getattr(old,key)),key
    for key in ('methods','bodies','classes','scripts','metadata'):
        before=getattr(old,key)
        assert p.freeze(getattr(a,key)[:len(before)])==p.freeze(before),key
    assert len(a.instances)==len(old.instances)
    for index,(before,after) in enumerate(zip(old.instances,a.instances)):
        if index!=ci:assert p.freeze(before)==p.freeze(after),('unrelated class changed',index)
        else:
            assert p.freeze(before[:6])==p.freeze(after[:6])
            assert p.freeze(before[6])==p.freeze(after[6][:-1]) and len(after[6])==len(before[6])+1
            assert p.freeze(after[6][-1])==p.freeze(new_trait)
    assert class_layout(a,OWNER)[2]==[]
    return dict(method_id=mid,label=LABEL,strategy='replace',source_method=smid,
        source_body_sha256=BODY_SHA,after_code_sha256=sha(body[5]),signature=signature(a,mid),
        source_owner_class=source_ci,target_owner_class=ci,trait_name=new_trait.name,
        source_body_bytes=44,target_body_bytes=len(body[5]),validation=proof,
        exact_normalized_production_body_preserved=True,old_instances_and_fields_preserved=True,
        old_method_info_and_body_prefix_preserved=True,old_activation_and_script_prefix_preserved=True,
        target_owner_has_no_subclasses=True,existing_caller_methods_unchanged=[65305,65306],
        existing_native_runtime_lookup_required=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();job=bounded_job();out=args.output.resolve()
    assert out.is_relative_to(TASK.resolve()) and not out.exists(),'fresh task output required'
    raw=BASE_ABC.read_bytes();assert sha(raw)==BASE_SHA,'cumulative full ABC identity changed'
    a=p.abcfmt.ABC(raw);assert a.serialize()==raw
    target=view(a);source=p.View(p.SwfAbc(ANDROID),p.asm)
    change=append_real_getter(target,source);result=a.serialize()
    assert p.abcfmt.ABC(result).serialize()==result
    receipt_path=PREVIOUS/'RESULT.json';previous=json.loads(receipt_path.read_text('utf-8-sig'))['candidate']
    assert previous['sha256']=='8e6845291b3b83a41844c241c562961dc097cf2297599f2940cacffec220011c'
    assert previous['full_abc_sha256']==BASE_SHA and previous['native_sha256']=='2eb568827e72c89b7ae0f60582d6c32523468cc61286ce1b262d9cae8be54caa'
    prior_link=json.loads((PREVIOUS/'linked01/link-report.json').read_text('utf-8-sig'))
    package_receipt=PREVIOUS/'StarPoint-iOS-1.8.4-release1031-dispatch-fix-r1-unsigned.json'
    package=json.loads(package_receipt.read_text('utf-8-sig'))
    assert package['ipa_sha256']==previous['sha256'] and package['total_methods']==OLD_COUNT
    source_ipa=copy.deepcopy(prior_link['source_ipa'])
    source_ipa.update(ipa=previous['path'],ipa_sha256=previous['sha256'],size_bytes=previous['bytes'],
        native_member='Payload/worldflipper.app/worldflipper',native_sha256=previous['native_sha256'],
        swf_member='Payload/worldflipper.app/worldflipper_ios_release.swf',swf_sha256=previous['swf_sha256'],
        bundle_id=previous['bundle_id'],version=previous['version'],build=previous['build'],signing=previous['signing'],
        full_abc=str(BASE_ABC),full_abc_sha256=BASE_SHA,full_abc_sha1=hashlib.sha1(raw).hexdigest(),
        admission_id=previous['admission_id'],acceptance_status='local_candidate',
        aot_info_file_offset=104549248,aot_method_count=OLD_COUNT,architecture='arm64',
        device_acceptance='not_device_accepted; exact installed or re-signed IPA identity unknown',
        identity_evidence_reused_from=[str(receipt_path),str(package_receipt)],not_rehashed_or_registered=True)
    manifest=dict(status='one_leaf_instance_method_appended',owner=OWNER,class_index=change['target_owner_class'],
        method=change['method_id'],trait_name=change['trait_name'],trait_kind=1,disp_id=0,
        old_method_count=OLD_COUNT,new_method_count=len(a.methods),subclasses=[],
        changed_existing_method_bodies=[],changed_existing_fields=[],changed_runtime_scripts=[],
        unchanged_dynamic_callers=[65305,65306],change=change)
    report=dict(status='prepared_requires_native_compile_link_and_air_validation',
        source_ipa=source_ipa,full_abc_file='full.abc',full_abc_sha256=sha(result),
        full_abc_sha1=hashlib.sha1(result).hexdigest(),base_full_abc_sha256=BASE_SHA,
        old_methods=OLD_COUNT,total_methods=len(a.methods),methods=[change],new_method_ids=[change['method_id']],
        compiled_helpers=[change['method_id']],permitted_native_entry_aliases={},
        baseline_native_file=previous['native_path'],baseline_swf_file=previous['swf_path'],
        append_manifest='append-manifest.json',input_android_swf=str(ANDROID),
        source_body_sha256=BODY_SHA,bounded_job=job,native_compiled=False,native_executed=False,
        device_tested=False,endpoint_and_admission_unchanged=True)
    out.mkdir(parents=True);(out/'full.abc').write_bytes(result)
    save(out/'append-manifest.json',manifest);save(out/'port.json',report)
    source_files=[dict(path=str(path),sha256=sha(path.read_bytes())) for path in sorted(HERE.glob('*')) if path.is_file()]
    save(out/'source-manifest.json',dict(files=source_files,python=sys.executable,
        dependencies=[str(CLIENT/'lens0907-0908/build_swf.py'),str(CLIENT/'lens0907-0908/vendor/abcasm'),
            str(fc.tool('support/process/job_guard.py'))]))
    print(json.dumps(dict(status=report['status'],output=str(out),method=change['method_id'],
        total_methods=len(a.methods),full_abc_sha256=sha(result),full_abc_sha1=report['full_abc_sha1'])))

if __name__=='__main__':main()
