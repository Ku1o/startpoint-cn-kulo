"""Prepare a narrow AOT delta on the accepted R4, retaining its native ABI."""
from pathlib import Path
import copy, hashlib, importlib.util, json, os, sys, types, zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
WORK=Path(os.environ.get('STARPOINT_IOS_CACHE_WORK','F:/codex/work/ios-cache-rounded-r2-20260912'))
sys.path[:0]=[str(HERE.parent/'ios-cumulative-login'),str(HERE.parent)]
spec=importlib.util.spec_from_file_location('previous_prepare',HERE.parent/'ios-cumulative-login/prepare.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
spec=importlib.util.spec_from_file_location('android_model',HERE.parent/'startup-cache/build_swf.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
LEGACY,SDK=p.LEGACY,p.SDK
abcfmt,asm,view,freeze,dump,sha=p.abcfmt,p.asm,p.view,p.freeze,p.dump,p.sha
OLD_COUNT=101182
INFO_OFFSET=104549248
from verify_ios_baseline import verify

def main():
    # Historical reproduction of this accepted delta, always from its exact R4 parent.
    record=HERE.parent/'accepted-history/ios-login-abyss-hud-r4-20260911.json'
    verify(record_path=record)
    reg=json.loads(record.read_text('utf8'))['artifact']
    assert reg['ipa_sha256']=='560d5787411dfa1b603a9c8f0b4fba46f045e02531256e476df5b6474d822fae'
    assert not (WORK/'port.json').exists();WORK.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(reg['ipa']) as z:
        native=z.read(reg['native_member']);swf=z.read(reg['swf_member'])
    full=Path(reg['full_abc']).read_bytes();assert sha(full)==reg['full_abc_sha256']
    for name,data in [('baseline-native',native),('baseline.swf',swf),('baseline-full.abc',full)]:p.put(WORK/name,data)
    # This donor is the tested three-feature Android candidate, before the
    # Android-only carousel repair. The endpoint and all other game methods stay iOS.
    apk=REPO/'outputs/client-cache-rounded-public-20260912/StarPoint-CN-1.8.1-cache-rounded-public-20260912.apk'
    assert sha(apk.read_bytes())=='32006941eff3a0294e9895aafba4668c8a4691bce1459740cb46afc258492f56'
    with zipfile.ZipFile(apk) as z:p.put(WORK/'android.swf',z.read('assets/worldflipper_android_release.swf'))
    sources=[view(t[3]) for t in s.parts(WORK/'android.swf')[2] if t[0]==82]
    a=abcfmt.ABC(full);target=view(a);old=copy.deepcopy(a)
    assert len(a.methods)==OLD_COUNT
    hv,=[v for v in sources if 'cn.asset::EmptyUpdate$/normalize|1' in v.by_label]
    p.ClassImporter(target,hv).merge()
    assert len(a.methods)==OLD_COUNT+5
    spec=importlib.util.spec_from_file_location('android_build',HERE.parent/'startup-cache/build.py')
    build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
    build.run([build.JAVA,'-Dflexlib='+str(SDK/'frameworks'),'-Xmx512m','-jar',SDK/'lib/compc-cli.jar',
        '+configname=air','-swf-version=44','-target-player=32.0','-debug=false',
        '-compiler.source-path='+str(HERE/'src'),'-include-classes=cn.ui.RoundedButton',
        '-output='+str(WORK/'rounded.swc')],WORK,'compile-rounded')
    rounded=view(s.helper_abc(WORK/'rounded.swc'))
    p.ClassImporter(target,rounded).merge()
    def q(ns,name):
        hits=[i for i in range(1,len(a.multinames)) if target.mn(i)==(7,(22,ns),name)]
        assert hits,(ns,name);return hits[0]
    records=[]
    # Preserve the exact activation layout used by the retained click closure.
    label='cn.ui::AbyssDetails$/attach|1';ti,=target.by_label[label];body=copy.deepcopy(old.bodies[ti])
    rows=asm.decode(body[5]);assert not body[6]
    assert rows[164].op==0x5d and target.mn(rows[164].args[0])==(7,(23,'cn.ui'),'QuadClass')
    assert rows[168].op==0x4a and list(rows[168].args)==[rows[164].args[0],3]
    rows[164]=asm.Instruction(0x60,[q('cn.ui','RoundedButton')])
    rows[168]=asm.Instruction(0x46,[q('','create'),3]);body[5]=asm.encode(rows)[0];a.bodies[ti]=body
    assert p.activation_traits(target,old.bodies[ti])==p.activation_traits(target,body)
    records.append(dict(label=label,method_id=body[0],body_index=ti,check=p.check_body(body,a),strategy='replace',
        activation_layout_preserved=True,replaced_instructions=[164,168]))
    for label in ('cn.account::PlayerLogin$/title|1/closure:0',):
        donor,=[v for v in sources if label in v.by_label]
        si,=donor.by_label[label];ti,=target.by_label[label];original=old.bodies[ti]
        importer=p.Importer(target,donor)
        body=importer.body(si,original[0],scope=original[3])
        assert p.activation_traits(target,original)==p.activation_traits(target,body),(label,'activation layout')
        assert target.mn(a.methods[original[0]][0])==donor.mn(donor.a.methods[donor.a.bodies[si][0]][0])
        a.bodies[ti]=body
        assert view(a).normalized(ti)==donor.normalized(si),label
        records.append(dict(label=label,method_id=body[0],body_index=ti,check=p.check_body(body,a),strategy='replace'))
    label='pinball.protocol.api.logic.real::AssetGetPathRealRemote/successHandler|1'
    matches=[k for k in target.by_label if k.endswith('::AssetGetPathRealRemote/successHandler|1')]
    assert len(matches)==1,matches;label=matches[0]
    ti,=target.by_label[label];original=old.bodies[ti]
    rows=asm.assemble([('getlocal_0',),('pushscope',),('getlex',q('cn.asset','EmptyUpdate')),('getlocal_1',),
        ('callpropvoid',q('','normalize'),1),('returnvoid',)])
    body=copy.deepcopy(original);body[1]=2;body[4]=body[3]+1;body[5]=asm.encode(rows)[0];body[6]=[];body[7]=[]
    a.bodies[ti]=body
    assert a.mn_name(a.methods[body[0]][0])=='void'
    records.append(dict(label=label,method_id=body[0],body_index=ti,check=p.check_body(body,a),strategy='extension_then_original'))
    # Compiler-only class initializers establish lexical scopes; the linker
    # preserves their existing native functions and runtime declarations.
    lifecycles=[]
    for owner in ('cn.ui::AbyssDetails','cn.account::PlayerLogin',label.split('/')[0]):
        init='script:'+owner+'/<init>'
        donor,=[v for v in sources if init in v.by_label]
        si,=donor.by_label[init];ti,=target.by_label[init];original=old.bodies[ti]
        a.bodies[ti]=p.Importer(target,donor).body(si,original[0],scope=original[3])
        lifecycles.append(dict(label=init,method_id=original[0],body_index=ti))
    changes={r['method_id'] for r in records+lifecycles}
    # The AOT compiler discovers closures via their real enclosing method and
    # needs helper class initializers to establish static constants. Compile
    # their retained context, but link only the three selected native methods.
    context_ids=set()
    for label,indices in target.by_label.items():
        if label.startswith(('cn.ui::AbyssDetails/','cn.ui::AbyssDetails$/','cn.account::PlayerLogin/','cn.account::PlayerLogin$/')):
            context_ids.update(old.bodies[i][0] for i in indices)
    for i,b in enumerate(old.bodies):
        if b[0] not in changes:assert freeze(b)==freeze(a.bodies[i])
    for field in ('methods','metadata','instances','classes','scripts','ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        before=getattr(old,field);assert freeze(before)==freeze(getattr(a,field)[:len(before)]),field
    import struct
    abcva,abclen=struct.unpack_from('<QQ',native,INFO_OFFSET+24)
    pos=32;at=None
    for _ in range(struct.unpack_from('<I',native,16)[0]):
        cmd,size=struct.unpack_from('<II',native,pos)
        if cmd==0x19:
            vm,_,off,fs=struct.unpack_from('<QQQQ',native,pos+24)
            if vm<=abcva and abcva+abclen<=vm+fs:at=off+abcva-vm
        pos+=size
    assert at is not None
    runtime=abcfmt.ABC(native[at:at+abclen]);by_mid={b[0]:b for b in runtime.bodies}
    sys.path.insert(0,str(LEGACY))
    from fill_ios_aot_stub_bodies import return_stub
    for i,b in enumerate(a.bodies):
        if b[0]<OLD_COUNT and b[0] not in changes|context_ids:
            stub=copy.deepcopy(by_mid[b[0]]);stub[5]=return_stub(a.mn_name(a.methods[b[0]][0]));stub[6]=[];a.bodies[i]=stub
    payload=a.serialize();p.put(WORK/'cache-rounded-full.abc',payload)
    dump(WORK/'port.json',dict(source_ipa=reg,old_methods=OLD_COUNT,total_methods=len(a.methods),methods=records,
        compiler_only_lifecycles=lifecycles,full_abc_file='cache-rounded-full.abc',full_abc_sha256=sha(payload),
        compiler_only_context=sorted(context_ids-{r['method_id'] for r in records}),
        full_abc_sha1=hashlib.sha1(payload).hexdigest(),baseline_runtime_abc_sha256=sha(native[at:at+abclen]),
        new_classes=['cn.asset::EmptyUpdate','cn.ui::RoundedButton'],new_method_count=len(a.methods)-OLD_COUNT,
        ios_carousel_unchanged=True,save_schema_changed=False))
    print(json.dumps(records,ensure_ascii=False))

if __name__=='__main__':main()
