"""Port the accepted Android record/name and folder gate onto accepted iOS AOT."""
from pathlib import Path
import copy,hashlib,importlib.util,json,os,struct,sys,zipfile
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
WORK=Path(os.environ.get('STARPOINT_IOS_RECORD_WORK','F:/codex/work/ios-record-holder-20260912'))
sys.path[:0]=[str(HERE.parent/'ios-cumulative-login'),str(HERE.parent)]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
p=module('previous_prepare',HERE.parent/'ios-cumulative-login/prepare.py')
s=module('android_model',HERE.parent/'startup-cache/build_swf.py')
LEGACY,SDK=p.LEGACY,p.SDK
abcfmt,asm,view,freeze,dump,sha=p.abcfmt,p.asm,p.view,p.freeze,p.dump,p.sha
OLD_COUNT=101191;INFO_OFFSET=104549248

def main():
    from verify_ios_baseline import verify
    from verify_android_baseline import verify as verify_android
    verify();android=verify_android('lan')
    assert android['apk_sha256']=='e04b9e4f367be0ee447f1cfc8f45ff314fafc4a2df7efcef03db120347278f32'
    reg=json.loads((HERE.parent/'ios-accepted.json').read_text('utf-8'))['artifact']
    assert reg['ipa_sha256']=='11ccd92b75e00484e57d124b52a02aedc4cecfb9c0012387288fd69e58af42d9'
    assert not (WORK/'port.json').exists();WORK.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(reg['ipa']) as z:native=z.read(reg['native_member']);swf=z.read(reg['swf_member'])
    full=Path(reg['full_abc']).read_bytes();assert sha(full)==reg['full_abc_sha256']
    for name,data in [('baseline-native',native),('baseline.swf',swf),('baseline-full.abc',full)]:p.put(WORK/name,data)
    with zipfile.ZipFile(android['apk']) as z:p.put(WORK/'android.swf',z.read('assets/worldflipper_android_release.swf'))
    sources=[view(t[3]) for t in s.parts(WORK/'android.swf')[2] if t[0]==82]
    a=abcfmt.ABC(full);old=copy.deepcopy(a);target=view(a);assert len(a.methods)==OLD_COUNT
    helper_names=['cn.ui::AbyssRecordDetails','cn.ui::ItemSourceFolderGate'];helper_records=[]
    for name in helper_names:
        dv,=[v for v in sources if any(v.a.mn_name(i[0])==name for i in v.a.instances)]
        assert len(dv.a.instances)==1
        first=len(a.methods);p.ClassImporter(target,dv).merge()
        helper_records.append(dict(name=name,first_method=first,methods=len(dv.a.methods)))
    records=[]
    labels=['cn.ui::AbyssDetails$/openDetails|1','pinball.scene.itemHowToGet.questSearch::ItemHowToGetQuestSearcher/getAvailableQuestLogic|1']
    for label in labels:
        dv,=[v for v in sources if label in v.by_label];si,=dv.by_label[label];ti,=target.by_label[label];original=old.bodies[ti]
        sig=lambda v,m:(v.mn(v.a.methods[m][0]),tuple(v.mn(x) for x in v.a.methods[m][1]),v.a.methods[m][3])
        assert sig(target,original[0])==sig(dv,dv.a.bodies[si][0]),label
        body=p.Importer(target,dv).body(si,original[0],scope=original[3])
        if label=='cn.ui::AbyssDetails$/openDetails|1':
            # Retained old closures/native activation descriptors can still
            # describe these slots. The new delegate does not read any of them.
            assert not body[7]
            body[7]=copy.deepcopy(original[7])
        assert p.activation_traits(target,original)==p.activation_traits(target,body),(label,'activation ABI')
        a.bodies[ti]=body
        assert view(a).normalized(ti)==dv.normalized(si),label
        records.append(dict(label=label,method_id=body[0],body_index=ti,check=p.check_body(body,a),strategy='replace'))
    # Compile lexical context without linking any additional old native methods.
    lifecycles=[]
    for owner in ('cn.ui::AbyssDetails','pinball.scene.itemHowToGet.questSearch::ItemHowToGetQuestSearcher'):
        label='script:'+owner+'/<init>';dv,=[v for v in sources if label in v.by_label]
        si,=dv.by_label[label];ti,=target.by_label[label];original=old.bodies[ti]
        a.bodies[ti]=p.Importer(target,dv).body(si,original[0],scope=original[3])
        lifecycles.append(dict(label=label,method_id=original[0],body_index=ti))
    context=set()
    for label,indices in target.by_label.items():
        if label.startswith(('cn.ui::AbyssDetails/','cn.ui::AbyssDetails$/')):context.update(old.bodies[i][0] for i in indices)
    changes={r['method_id'] for r in records+lifecycles}
    for i,b in enumerate(old.bodies):
        if b[0] not in changes:assert freeze(b)==freeze(a.bodies[i]),b[0]
    fields=('methods','metadata','instances','classes','scripts','ints','uints','doubles','strings','namespaces','ns_sets','multinames')
    for field in fields:
        rows=getattr(old,field);assert freeze(rows)==freeze(getattr(a,field)[:len(rows)]),field
    import build_native as link
    abcva,abclen=struct.unpack_from('<QQ',native,INFO_OFFSET+24);at=link.file_offset(native,abcva,abclen)
    runtime=abcfmt.ABC(native[at:at+abclen]);by_mid={b[0]:b for b in runtime.bodies}
    sys.path.insert(0,str(LEGACY));from fill_ios_aot_stub_bodies import return_stub
    for i,b in enumerate(a.bodies):
        if b[0]<OLD_COUNT and b[0] not in changes|context:
            stub=copy.deepcopy(by_mid[b[0]]);stub[5]=return_stub(a.mn_name(a.methods[b[0]][0]));stub[6]=[];a.bodies[i]=stub
    payload=a.serialize();p.put(WORK/'record-holder-full.abc',payload)
    dump(WORK/'port.json',dict(source_ipa=reg,android_reference=android,old_methods=OLD_COUNT,total_methods=len(a.methods),methods=records,compiler_only_lifecycles=lifecycles,compiler_only_context=sorted(context-{r['method_id'] for r in records}),full_abc_file='record-holder-full.abc',full_abc_sha256=sha(payload),full_abc_sha1=hashlib.sha1(payload).hexdigest(),baseline_runtime_abc_sha256=sha(native[at:at+abclen]),new_classes=helper_names,new_method_count=len(a.methods)-OLD_COUNT,helpers=helper_records,ios_carousel_unchanged=True,save_schema_changed=False))
    print(json.dumps(dict(methods=records,helpers=helper_records),ensure_ascii=False))
if __name__=='__main__':main()
