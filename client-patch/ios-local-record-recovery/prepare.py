"""Recover empty account records on the current iOS admission release."""
import copy,hashlib,importlib.util,json,os,struct,sys,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
WORK=Path(os.environ.get('STARPOINT_IOS_RECORD_WORK','F:/codex/work/r10-public-ios-reopen-fix-20260915/ios'))
sys.path[:0]=[str(HERE.parent/'ios-cumulative-login'),str(HERE.parent)]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
p=module('ios_record_previous_prepare',HERE.parent/'ios-cumulative-login/prepare.py')
s=module('ios_record_swf_support',HERE.parent/'startup-cache/build_swf.py')
LEGACY,SDK=p.LEGACY,p.SDK
abcfmt,asm,view,freeze,dump,sha=p.abcfmt,p.asm,p.view,p.freeze,p.dump,p.sha
OLD_COUNT=101283
INFO_OFFSET=104549248
BUILD_ID='ios-184-admission-20260915'
ORIGIN='http://175.178.160.158'
PRIVATE=Path('F:/codex/.codex/secrets/starpoint-client-admission/config/client-admission.keys.json')
REG={
    'ipa':str(REPO/'outputs/ios-admission-public-20260915/StarPoint-iOS-1.8.4-admission-public-20260915-unsigned.ipa'),
    'ipa_sha256':'764a7c5183a8605f58364e786a08a59f65333403bded9918dd3b544a85112f09',
    'native_member':'Payload/worldflipper.app/worldflipper',
    'native_sha256':'ad35c8894e5c883798e9d2ff305ada8562fdc26361d550e2affb5f5456ccf211',
    'swf_member':'Payload/worldflipper.app/worldflipper_ios_release.swf',
    'swf_sha256':'addf3ee62d783fff828c1811ee4b6461cb1323146871d78ee2107bff8e439c2e',
    'full_abc':'F:/codex/work/ios-admission-public-20260915/admission-full.abc',
    'full_abc_sha256':'86e787a8d169cabfee94e8420d56ff1bf8ed928afdb04e367d9967cf91844ae3',
    'aot_method_count':OLD_COUNT,'bundle_id':'com.kulo.wf','version':'1.8.4','build':'1.8.46','signing':'unsigned'}
ANDROID=REPO/'outputs/r10-public-reopen-fix-20260915/StarPoint-CN-1.8.1-r10-public-reopen-fix-20260915.apk'
ANDROID_SHA='3c365e51762ad115366731fa1fa2bd1ffbdac54cbce4c3e2626010deffc91fd2'
LABELS=['pinball.context.localStore._AccountLocalStore::AccountLocalStore_Impl_$/get|1',
        'pinball.context.localStore._AccountLocalStore::AccountLocalStore_Impl_$/saveAccountData|1']

def main():
    from verify_ios_baseline import verify
    verify()
    assert not WORK.exists(),'Use a new iOS work directory.'
    assert '.cdn' not in [x.lower() for x in WORK.resolve().parts]
    assert sha(Path(REG['ipa']).read_bytes())==REG['ipa_sha256']
    assert sha(ANDROID.read_bytes())==ANDROID_SHA
    with zipfile.ZipFile(REG['ipa']) as z:
        native=z.read(REG['native_member']);swf=z.read(REG['swf_member'])
    assert sha(native)==REG['native_sha256'] and sha(swf)==REG['swf_sha256']
    full=Path(REG['full_abc']).read_bytes();assert sha(full)==REG['full_abc_sha256']
    assert native[INFO_OFFSET:INFO_OFFSET+20]==hashlib.sha1(full).digest()
    import build_native as link
    oldabcva,oldabclen=struct.unpack_from('<QQ',native,INFO_OFFSET+24)
    oldabcoff=link.file_offset(native,oldabcva,oldabclen)
    runtime_raw=native[oldabcoff:oldabcoff+oldabclen]
    runtime=abcfmt.ABC(runtime_raw)
    assert len(runtime.methods)==OLD_COUNT
    WORK.mkdir(parents=True)
    for name,data in [('baseline-native',native),('baseline.swf',swf),('baseline-full.abc',full)]:p.put(WORK/name,data)
    with zipfile.ZipFile(ANDROID) as z:p.put(WORK/'android-record-reference.swf',z.read('assets/worldflipper_android_release.swf'))
    donors=[view(t[3]) for t in s.parts(WORK/'android-record-reference.swf')[2] if t[0]==82]
    a=abcfmt.ABC(full);old=copy.deepcopy(a);target=view(a)
    helper,=[v for v in donors if any(v.a.mn_name(i[0])=='cn.storage::LocalRecordIO' for i in v.a.instances)]
    assert len(helper.a.instances)==1
    p.ClassImporter(target,helper).merge()
    helpers=[dict(name='cn.storage::LocalRecordIO',first_method=OLD_COUNT,methods=len(helper.a.methods))]
    records=[]
    for label in LABELS:
        donor,=[v for v in donors if label in v.by_label]
        si,=donor.by_label[label];ti,=target.by_label[label];original=old.bodies[ti]
        sig=lambda v,mid:(v.mn(v.a.methods[mid][0]),tuple(v.mn(x) for x in v.a.methods[mid][1]),v.a.methods[mid][3])
        assert sig(target,original[0])==sig(donor,donor.a.bodies[si][0]),label
        body=p.Importer(target,donor).body(si,original[0],scope=original[3])
        assert p.activation_traits(target,original)==p.activation_traits(target,body),(label,'activation ABI')
        a.bodies[ti]=body
        assert view(a).normalized(ti)==donor.normalized(si),label
        records.append(dict(label=label,method_id=body[0],body_index=ti,check=p.check_body(body,a),strategy='replace'))
    assert {r['method_id'] for r in records}=={31752,31756}
    # Compile the owner's lexical initializer as context only; retain its
    # actual native initializer, cinit, fields and all iOS device-store code.
    owner=LABELS[0].split('/')[0].rstrip('$')
    label='script:'+owner+'/<init>'
    donor,=[v for v in donors if label in v.by_label]
    si,=donor.by_label[label];ti,=target.by_label[label];original=old.bodies[ti]
    a.bodies[ti]=p.Importer(target,donor).body(si,original[0],scope=original[3])
    lifecycles=[dict(label=label,method_id=original[0],body_index=ti)]
    changed={r['method_id'] for r in records+lifecycles}
    for i,body in enumerate(old.bodies):
        if body[0] not in changed:assert freeze(body)==freeze(a.bodies[i]),body[0]
    fields=('methods','metadata','instances','classes','scripts','ints','uints','doubles','strings','namespaces','ns_sets','multinames')
    for field in fields:
        before=getattr(old,field);assert freeze(before)==freeze(getattr(a,field)[:len(before)]),field
    checks=[dict(method=body[0],check=p.check_body(body,a)) for body in a.bodies if body[0]>=OLD_COUNT]
    sys.path.insert(0,str(LEGACY));from fill_ios_aot_stub_bodies import return_stub
    bymid={body[0]:body for body in runtime.bodies}
    for i,body in enumerate(a.bodies):
        if body[0]<OLD_COUNT and body[0] not in changed:
            stub=copy.deepcopy(bymid[body[0]])
            stub[5]=return_stub(a.mn_name(a.methods[body[0]][0]));stub[6]=[];a.bodies[i]=stub
    payload=a.serialize();assert abcfmt.ABC(payload).serialize()==payload
    p.put(WORK/'record-recovery-full.abc',payload)
    dump(WORK/'port.json',dict(source_ipa=REG,old_methods=OLD_COUNT,total_methods=len(a.methods),methods=records,
        compiler_only_lifecycles=lifecycles,compiler_only_context=[],full_abc_file='record-recovery-full.abc',
        full_abc_sha256=sha(payload),full_abc_sha1=hashlib.sha1(payload).hexdigest(),
        baseline_runtime_abc_sha256=sha(runtime_raw),new_classes=['cn.storage::LocalRecordIO'],
        new_method_count=len(a.methods)-OLD_COUNT,helpers=helpers,helper_body_checks=checks,
        android_reference={'apk':str(ANDROID),'sha256':ANDROID_SHA},build_id=BUILD_ID,origin=ORIGIN,platform='ios',
        ios_device_store_unchanged=True,save_schema_changed=False,record_encoding_unchanged=True,
        admission_id_key_and_behavior_unchanged=True,android_performance_not_imported=True))
    print(json.dumps({'methods':[r['method_id'] for r in records],'helper_methods':len(a.methods)-OLD_COUNT,
        'full_abc_sha256':sha(payload),'build_id':BUILD_ID,'origin':ORIGIN},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
