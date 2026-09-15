"""Append admission only to the registered, accepted iOS AOT payload."""
from pathlib import Path
import copy, hashlib, importlib.util, json, os, struct, sys, zipfile

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
WORK=Path(os.environ.get('STARPOINT_IOS_ADMISSION_WORK','F:/codex/work/ios-admission-public-20260915'))
sys.path[:0]=[str(HERE.parent/'ios-cumulative-login'),str(HERE.parent)]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
p=module('ios_admission_previous_prepare',HERE.parent/'ios-cumulative-login/prepare.py')
s=module('ios_admission_swf_support',HERE.parent/'startup-cache/build_swf.py')
build=module('ios_admission_compile_support',HERE.parent/'startup-cache/build.py')
LEGACY,SDK=p.LEGACY,p.SDK
abcfmt,asm,view,freeze,dump,sha=p.abcfmt,p.asm,p.view,p.freeze,p.dump,p.sha
OLD_COUNT=101214;INFO_OFFSET=104549248
BUILD_ID='ios-184-admission-20260915';ORIGIN='http://175.178.160.158'
PRIVATE=REPO/'outputs/ios-admission-release-private-20260915/config/client-admission.keys.json'
SOURCE_IPA_SHA='544ec90332845ff6c6b06e98aad691c0d9f10c725470eceeb4237c8bdbd65361'

def main():
    from verify_ios_baseline import verify
    verify()
    reg=json.loads((HERE.parent/'ios-accepted.json').read_text('utf-8'))['artifact']
    assert reg['ipa_sha256']==SOURCE_IPA_SHA and reg['aot_method_count']==OLD_COUNT
    assert not (WORK/'port.json').exists();WORK.mkdir(parents=True,exist_ok=True)
    assert '.cdn' not in [x.lower() for x in WORK.resolve().parts]
    with zipfile.ZipFile(reg['ipa']) as z:native=z.read(reg['native_member']);swf=z.read(reg['swf_member'])
    full=Path(reg['full_abc']).read_bytes();assert sha(full)==reg['full_abc_sha256']
    for name,data in [('baseline-native',native),('baseline.swf',swf),('baseline-full.abc',full)]:p.put(WORK/name,data)
    # The accepted iOS ABC contains compiler stubs for retained native methods.
    # Recover only PlayerLogin's compiler context from its pinned iOS ancestor.
    # All these methods retain their native code except the two explicit hooks.
    context_path=Path('F:/codex/ios-artifacts/cache-rounded-public-20260912/cache-rounded-full.abc')
    context_raw=context_path.read_bytes();assert sha(context_raw)=='d4f9e01de7272d43decfd834e1859c57baf735d8cac4bbe5ddeb5db94d020573'
    context_abc=abcfmt.ABC(context_raw);cv=view(context_abc)
    a=abcfmt.ABC(full);old=copy.deepcopy(a)
    fields=('methods','metadata','instances','classes','scripts','ints','uints','doubles','strings','namespaces','ns_sets','multinames')
    for field in fields:
        before=getattr(context_abc,field);assert freeze(before)==freeze(getattr(a,field)[:len(before)]),field
    bymid={b[0]:i for i,b in enumerate(a.bodies)};context=set()
    for label,indices in cv.by_label.items():
        if label.startswith(('cn.account::PlayerLogin/','cn.account::PlayerLogin$/','script:cn.account::PlayerLogin/')):
            for bi in indices:
                b=context_abc.bodies[bi];a.bodies[bymid[b[0]]]=copy.deepcopy(b);context.add(b[0])
    assert 101122 in context and 101128 in context
    target=view(a)
    keys=json.loads(PRIVATE.read_text('utf-8-sig'))
    assert set(keys)=={'android-181-r10-20260915',BUILD_ID} and len(keys[BUILD_ID])==64
    generated=WORK/'generated/cn/admission';generated.mkdir(parents=True)
    source=HERE.parent/'r10-public-release/src/cn/admission'
    helper_sources={}
    for name in ('AdmissionSession.as','ClientAdmission.as'):
        text=(source/name).read_text('utf-8');helper_sources[name]=sha(text.encode())
        if name=='ClientAdmission.as':
            assert text.count('platform:"android"')==1
            text=text.replace('platform:"android"','platform:"ios"')
        (generated/name).write_text(text,'utf-8')
    (generated/'BuildConfig.as').write_text('package cn.admission { public final class BuildConfig { public static const ID:String='+json.dumps(BUILD_ID)+'; public static const KEY:String='+json.dumps(keys[BUILD_ID])+'; public static const ORIGIN:String='+json.dumps(ORIGIN)+'; } }','utf-8')
    build.run([build.JAVA,'-Dflexlib='+str(SDK/'frameworks'),'-Xmx512m','-jar',SDK/'lib/compc-cli.jar',
        '+configname=air','-swf-version=44','-target-player=32.0','-debug=false',
        '-compiler.source-path='+str(WORK/'generated'),'-include-classes=cn.admission.ClientAdmission',
        '-output='+str(WORK/'admission.swc')],WORK,'compile-helper')
    with zipfile.ZipFile(WORK/'admission.swc') as z:p.put(WORK/'helper.swf',z.read('library.swf'))
    helpers=[]
    for tag in s.parts(WORK/'helper.swf')[2]:
        if tag[0]!=82:continue
        donor=view(tag[3]);names=[donor.a.mn_name(i[0]) for i in donor.a.instances]
        assert len(names)==1 and names[0] in ['cn.admission::BuildConfig','cn.admission::AdmissionSession','cn.admission::ClientAdmission']
        first=len(a.methods);p.ClassImporter(target,donor).merge()
        helpers.append(dict(name=names[0],first_method=first,methods=len(donor.a.methods)))
    assert len(helpers)==3
    target=view(a)
    def q(ns,name):
        found=[i for i in range(1,len(a.multinames)) if target.mn(i)==(7,(22,ns),name)]
        if found:return found[0]
        pool=s.PoolEditor(a);spaces=[i for i,n in enumerate(a.namespaces) if i and n[0]==22 and a.s(n[1])==ns and n[1]!=0]
        if spaces:space=spaces[0]
        else:
            ix=pool.string(ns)
            if ix==0:a.strings.append(b'');ix=len(a.strings)-1
            a.namespaces.append((22,ix));space=len(a.namespaces)-1
        a.multinames.append((7,space,pool.string(name)));return len(a.multinames)-1
    helper=q('cn.admission','ClientAdmission');records=[]
    def insert(body,at,code):
        before=body[5]
        body[5],body[6],_,placed=asm.splice_many(body,[(at,asm.assemble(code),asm.ENTER)])
        assert asm.unsplice_many(body[5],placed)==before
        body[1]=max(body[1],8)
        return placed
    # Android's accepted, non-diagnostic package supplies only seven generic
    # network method bodies, not the iOS baseline or any performance changes.
    donor_apk=REPO/'outputs/shop-first-open-public-20260913/StarPoint-CN-1.8.1-shop-first-open-public-20260913.apk'
    assert sha(donor_apk.read_bytes())=='35e0e7c777798594d68c9bcd74c507c6f0b7d065453e0425c301258c6bc38ac6'
    with zipfile.ZipFile(donor_apk) as z:p.put(WORK/'accepted-network-reference.swf',z.read('assets/worldflipper_android_release.swf'))
    donors=[view(t[3]) for t in s.parts(WORK/'accepted-network-reference.swf')[2] if t[0]==82]
    dv=donors[-1]
    specs=[(29670,332,'forwardAdmission',16),(29697,5,'beforeQueue',None),(29701,2,'inspect',None),
           (31405,5,'socket',None),(31407,2,'beforeSocketConnect',None),(31421,2,'socketClosed',None),(29703,2,'queueCanceled',None)]
    owners=[]
    for bi,at,call,unused in specs:
        label=dv.labels[dv.a.bodies[bi][0]];ti,=target.by_label[label];original=old.bodies[ti]
        sig=lambda v,mid:(v.mn(v.a.methods[mid][0]),tuple(v.mn(x) for x in v.a.methods[mid][1]),v.a.methods[mid][3])
        assert sig(target,original[0])==sig(dv,dv.a.bodies[bi][0]),label
        body=p.Importer(target,dv).body(bi,original[0],scope=original[3])
        assert p.activation_traits(target,original)==p.activation_traits(target,body),(label,'activation ABI')
        before=copy.deepcopy(body)
        args={
          'forwardAdmission':[('getlocal',16),('getlocal_2',)],
          'beforeQueue':[('getlocal_0',),('getlocal_1',),('getlocal_2',),('getlocal_3',)],
          'inspect':[('getlocal_0',),('getlocal_1',),('getlocal_3',)],
        }.get(call,[('getlocal_0',)])
        gate=call in ('forwardAdmission','beforeQueue','inspect','beforeSocketConnect')
        code=[('getlex',helper),*args,('callproperty' if gate else 'callpropvoid',q('',call),len(args))]
        if gate:code += [('iftrue','END'),('returnvoid',)]
        placed=insert(body,at,code);a.bodies[ti]=body
        assert not any(x.op==0x40 for x in asm.decode(before[5])),('existing network closure requires separate context',label)
        records.append(dict(label=label,method_id=original[0],body_index=ti,check=p.check_body(body,a),strategy='replace',
                            source='accepted Android generic network method',android_body=bi,hook=call,insertions=placed))
        owners.append(label.split('/')[0].rstrip('$'))
    target=view(a)
    label='cn.account::PlayerLogin$/cn.account:PlayerLogin::request|1';bi,=target.by_label[label];body=a.bodies[bi]
    before=copy.deepcopy(body);rows=target.normalized(bi)[0]
    hits=[i for i,r in enumerate(rows) if r[0]==0x4f and r[1]==[(7,(22,''),'load'),1]];assert len(hits)==1
    at=hits[0];temp=body[2];body[2]+=2
    block=asm.assemble([('setlocal',temp+1),('setlocal',temp),('getlex',helper),('getlocal',temp),('getlocal',temp+1)])
    body[5],body[6],_,placed=asm.splice_many(body,[(at,block,asm.ENTER)])
    code=asm.decode(body[5]);code[at+len(block)].args=[q('','load'),2];body[5]=asm.encode(code)[0];body[1]=max(body[1],4)
    assert p.activation_traits(target,before)==p.activation_traits(target,body)
    records.append(dict(label=label,method_id=body[0],body_index=bi,check=p.check_body(body,a),strategy='replace',source='pinned iOS PlayerLogin context',hook='loader wrapper'))
    label='cn.account::PlayerLogin$/cn.account:PlayerLogin::cancelNetwork|1';bi,=target.by_label[label];body=a.bodies[bi]
    loader=next(i for i in range(1,len(a.multinames)) if target.mn(i)==(7,(5,'cn.account:PlayerLogin'),'loader'))
    placed=insert(body,2,[('getlex',helper),('getlex',loader),('callpropvoid',q('','cancelLoad'),1)])
    records.append(dict(label=label,method_id=body[0],body_index=bi,check=p.check_body(body,a),strategy='replace',source='pinned iOS PlayerLogin context',hook='cancelLoad',insertions=placed))
    lifecycles=[]
    for owner in sorted(set(owners)):
        label='script:'+owner+'/<init>';ti,=target.by_label[label];si,=dv.by_label[label];original=old.bodies[ti]
        a.bodies[ti]=p.Importer(target,dv).body(si,original[0],scope=original[3])
        lifecycles.append(dict(label=label,method_id=original[0],body_index=ti))
    changes={r['method_id'] for r in records+lifecycles}
    for i,b in enumerate(old.bodies):
        if b[0] not in changes|context:assert freeze(b)==freeze(a.bodies[i]),b[0]
    for field in fields:
        rows=getattr(old,field);assert freeze(rows)==freeze(getattr(a,field)[:len(rows)]),field
    helper_checks=[dict(method=b[0],check=p.check_body(b,a)) for b in a.bodies if b[0]>=OLD_COUNT]
    import build_native as link
    abcva,abclen=struct.unpack_from('<QQ',native,INFO_OFFSET+24);off=link.file_offset(native,abcva,abclen)
    runtime_raw=native[off:off+abclen];runtime=abcfmt.ABC(runtime_raw);runtime_bodies={b[0]:b for b in runtime.bodies}
    sys.path.insert(0,str(LEGACY));from fill_ios_aot_stub_bodies import return_stub
    for i,b in enumerate(a.bodies):
        if b[0]<OLD_COUNT and b[0] not in changes|context:
            stub=copy.deepcopy(runtime_bodies[b[0]]);stub[5]=return_stub(a.mn_name(a.methods[b[0]][0]));stub[6]=[];a.bodies[i]=stub
    payload=a.serialize();assert abcfmt.ABC(payload).serialize()==payload
    p.put(WORK/'admission-full.abc',payload)
    dump(WORK/'port.json',dict(source_ipa=reg,old_methods=OLD_COUNT,total_methods=len(a.methods),methods=records,compiler_only_lifecycles=lifecycles,
        compiler_only_context=sorted(context-{r['method_id'] for r in records}),full_abc_file='admission-full.abc',full_abc_sha256=sha(payload),
        full_abc_sha1=hashlib.sha1(payload).hexdigest(),baseline_runtime_abc_sha256=sha(runtime_raw),new_classes=[r['name'] for r in helpers],
        new_method_count=len(a.methods)-OLD_COUNT,helpers=helpers,helper_body_checks=helper_checks,helper_source_sha256=helper_sources,
        build_id=BUILD_ID,platform='ios',origin=ORIGIN,ios_carousel_unchanged=True,save_schema_changed=False,android_performance_not_imported=True,
        context_source={'path':str(context_path),'sha256':sha(context_raw)},network_reference={'apk':str(donor_apk),'sha256':sha(donor_apk.read_bytes())}))
    print(json.dumps({'build_id':BUILD_ID,'patched_methods':[r['method_id'] for r in records],'helpers':helpers,'full_abc_sha256':sha(payload)},ensure_ascii=False))

if __name__=='__main__':main()
