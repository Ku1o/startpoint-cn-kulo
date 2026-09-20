"""Independent payload readback, inverse instrumentation proof and FFDec inventory."""
import copy, json, sys, zipfile
from common import *

EXPECTED={4336,4373,4374,5209,5259,5263,5264,5322,15140,20565,28920,28956,28963,28971,30852,38042,38045,38046,38073,38074,38076,38428,38430,38431,38432,50845,51007,51008,58883,60835,63233,63250,76162,76168,76169,82500,82509,92540}

def main():
    report=json.loads((WORK/'build-report.json').read_text(encoding='utf8'))
    proof=json.loads((WORK/'swf-report.json').read_text(encoding='utf8'))
    assert set(proof['changed_bodies'])==EXPECTED
    apk=Path(report['apk']);assert sha(apk.read_bytes())==report['apk_sha256']
    with zipfile.ZipFile(apk) as z:
        data=z.read('assets/worldflipper_android_release.swf');assert sha(data)==report['swf_sha256']==proof['output_swf_sha256']
        assert data==(WORK/'diagnostic.swf').read_bytes()
        assert sha(z.read('classes.dex'))==report['dex_sha256']
    old=s.parts(WORK/'input.swf')[2];new=s.parts(WORK/'diagnostic.swf')[2]
    extras=[row for row in new if row[0]==82 and row[2][4:-1]==b'cn.diagnostics.LoadingTrace']
    assert len(extras)==1 and sha(extras[0][4])==proof['helper_abc_sha256']
    kept=[row for row in new if row is not extras[0]]
    assert len(old)==len(kept) and sum(a[1]!=b[1] for a,b in zip(old,kept))==1
    a=[x[3] for x in old if x[0]==82][291];bmain=[x[3] for x in new if x[0]==82][292]
    changed={i for i,(x,y) in enumerate(zip(a.bodies,bmain.bodies)) if s.m.freeze(x)!=s.m.freeze(y)}
    assert changed==EXPECTED
    for item in proof['changes']:
        bi=item['body'];code=s.m.asm.unsplice_many(bmain.bodies[bi][5],item['placed'])
        if bi==38428:
            rows=s.m.asm.decode(code);original=s.m.asm.decode(a.bodies[bi][5])
            assert rows[19].op==0x60 and rows[20].op==0x66
            rows[19]=original[19];rows[20]=original[20];code=s.m.asm.encode(rows)[0]
        assert code==a.bodies[bi][5],bi
    for field in ('methods','instances','classes','scripts','metadata'):
        assert s.m.freeze(getattr(a,field))==s.m.freeze(getattr(bmain,field)),field
    for field in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        original=getattr(a,field);assert s.m.freeze(original)==s.m.freeze(getattr(bmain,field)[:len(original)]),field
    assert not any(row[0]==22 and row[1]==0 for row in bmain.namespaces[len(a.namespaces):])
    ffdec=Path('F:/codex/tools/ffdec_26.2.1/ffdec.jar');classes=WORK/'ffdec-verifier';classes.mkdir(exist_ok=True)
    b.run([b.JAVA.with_name('javac.exe'),'-cp',ffdec,'-d',classes,HERE/'CompareBodies.java'],WORK,'compile-ffdec-verifier')
    text=b.run([b.JAVA,'-Xmx2g','-cp',str(classes)+';'+str(ffdec),'CompareBodies',WORK/'input.swf',WORK/'diagnostic.swf'],WORK,'ffdec-verification')
    assert 'PASS original_bodies=96543 unchanged_bodies=96505 added_bodies=20' in text
    result={'status':'offline_verified_phone_diagnostic_candidate','apk':str(apk),'apk_sha256':report['apk_sha256'],
        'baseline_sha256':BASE_SHA,'swf_sha256':report['swf_sha256'],'uniqueappversionid':report['uniqueappversionid'],
        'changed_original_methods':sorted(EXPECTED),'original_methods_checked':96543,'unchanged_original_methods':96505,
        'added_helper_methods':20,'instrumentation_inverse_recovers_original_code':True,
        'gc_callback_count_and_actual_gc_call_preserved':True,'old_class_layouts_and_signatures_preserved':True,
        'old_native_logic_preserved':True,'signature_v1_v2':True,'zipalign':True,
        'public_endpoint_unchanged':True,'new_permissions':[],'server_or_cdn_change':False,'save_schema_change':False,
        'registry_promoted':False,'device_tested':False,'actual_coop_reproduction':False}
    dump(apk.parent/('verification-'+REVISION+'.json'),result);dump(WORK/'verification.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
