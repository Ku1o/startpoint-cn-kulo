"""Build the acquisition folder fix on the exact cumulative Abyss-records LAN candidate."""
import argparse,importlib.util,json,uuid,zipfile
from pathlib import Path
from patch_swf import patch

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
base=module('startup_build',HERE.parent/'startup-cache/build.py')
native=module('startup_verify',HERE.parent/'startup-cache/verify_native.py')
checker=module('accepted_check',HERE.parent/'verify_android_baseline.py')
VARIANTS=('lan',)

def main(args):
    w=args.work.resolve();out=args.out.resolve();variant=args.variant
    assert not w.exists() and not out.exists() and '.cdn' not in w.parts and '.cdn' not in out.parts
    accepted=checker.verify(variant, record_path=HERE.parent/'accepted-history/android-cache-party-20260912.json')
    parent=ROOT/'outputs/abyss-records-lan-test-20260912/StarPoint-CN-1.8.1-abyss-records-lan-test-20260912.apk'
    digest='db802e5e01e8d2f5e02aa0e5e92b58eb4d979e503605a5594a4b19ead90208e2'
    assert base.sha(parent.read_bytes())==digest
    previous=json.loads((parent.parent/'verification.json').read_text('utf-8'))
    assert previous['parent_apk_sha256']==accepted['apk_sha256']
    old_uid=previous['uniqueappversionid']
    w.mkdir(parents=True);out.mkdir(parents=True);uid=str(uuid.uuid4())
    with zipfile.ZipFile(parent) as z:
        (w/'input.swf').write_bytes(z.read('assets/worldflipper_android_release.swf'))
        (w/'original.dex').write_bytes(z.read('classes.dex'))
    compiler=[base.JAVA,'-Dflexlib='+str(base.SDK/'frameworks'),'-Xmx512m','-jar',base.SDK/'lib/compc-cli.jar',
              '+configname=air','-swf-version=44','-target-player=32.0','-debug=false']
    for name,src,cls in [('folder-gate',HERE/'src','cn.ui.ItemSourceFolderGate')]:
        base.run([*compiler,'-compiler.source-path='+str(src),'-include-classes='+cls,'-output='+str(w/(name+'.swc'))],w,'compile-'+name)
    swf=w/'item-source-folders.swf';swf_report=patch(w/'input.swf',swf)
    java,libs,run=base.JAVA,base.ALIB,base.run
    ffdec=Path('F:/codex/tools/ffdec_26.2.1/ffdec.jar');classes=w/'java';classes.mkdir()
    run([java.with_name('javac.exe'),'-cp',ffdec,'-d',classes,HERE/'CompareBodies.java'],w,'compile-verifier')
    checks=run([java,'-Xmx2g','-cp',str(classes)+';'+str(ffdec),'CompareBodies',w/'input.swf',swf,swf_report['changed_method'],str(swf_report['added_bodies'])],w,'method-verify')
    assert 'PASS original_bodies=96531' in checks
    print('Acquisition folder gate independently verified',flush=True)
    run([java,'-jar',libs/'baksmali.jar','d','-o',w/'smali',w/'original.dex'],w,'dex-decode')
    original={p.relative_to(w/'smali'):p.read_text() for p in (w/'smali').rglob('*.smali')}
    hits=0
    for name,text in original.items():
        count=text.count(old_uid)
        if count:
            assert name.as_posix() in ('cn/startpoint/StartupCache.smali','cn/startpoint/BuildIdentity.smali')
            (w/'smali'/name).write_text(text.replace(old_uid,uid));hits+=count
    assert hits==2
    run([java,'-jar',libs/'smali.jar','a','-a','21','-o',w/'classes.dex',w/'smali'],w,'dex-assemble')
    run([java,'-jar',libs/'baksmali.jar','d','-o',w/'readback',w/'classes.dex'],w,'dex-readback')
    assert len(list((w/'readback').rglob('*.smali')))==len(original)==6
    for name,text in original.items():
        assert native.canonical((w/'readback'/name).read_text().replace(uid,old_uid))==native.canonical(text),name
    excluded={'META-INF/MANIFEST.MF','META-INF/WF.SF','META-INF/WF.RSA'}
    payloads={'assets/worldflipper_android_release.swf':swf.read_bytes(),'classes.dex':(w/'classes.dex').read_bytes()}
    with zipfile.ZipFile(parent) as source,zipfile.ZipFile(w/'unsigned.apk','w') as dest:
        manifest=source.read('AndroidManifest.xml');assert manifest.count(old_uid.encode('utf-16le'))==1
        payloads['AndroidManifest.xml']=manifest.replace(old_uid.encode('utf-16le'),uid.encode('utf-16le'))
        for item in source.infolist():
            if item.filename not in excluded:dest.writestr(item,payloads.get(item.filename,source.read(item.filename)))
    align=Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    run([align,'-p','4',w/'unsigned.apk',w/'aligned.apk'],w,'align')
    apk=out/f'StarPoint-CN-1.8.1-item-source-folders-{variant}-test-20260912.apk'
    run(['powershell','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1',
         '-InputApk',w/'aligned.apk','-OutputApk',apk,'-ApkSigner',libs/'apksigner.jar','-Java',java],w,'sign')
    signature=run([java,'-jar',libs/'apksigner.jar','verify','--verbose','--print-certs',apk],w,'verify-signature')
    assert base.CERT in signature.lower()
    assert all('Verified using '+s+': true' in signature for s in ('v1 scheme (JAR signing)','v2 scheme (APK Signature Scheme v2)'))
    run([align,'-c','-p','4',apk],w,'verify-alignment')
    with zipfile.ZipFile(parent) as source,zipfile.ZipFile(apk) as dest:
        assert set(source.namelist())-excluded==set(dest.namelist())-excluded
        for name in set(source.namelist())-excluded:assert dest.read(name)==payloads.get(name,source.read(name)),name
        manifest=dest.read('AndroidManifest.xml')
        assert manifest.count(uid.encode('utf-16le'))==1 and old_uid.encode('utf-16le') not in manifest
    report={'variant':variant,'apk':str(apk),'apk_sha256':base.sha(apk.read_bytes()),'parent_apk_sha256':digest,
        'uniqueappversionid':uid,'native_build_identity':uid,'swf':swf_report,'signer_sha256':base.CERT,
        'zipalign':True,'v1_v2_signatures':True,'native_behavior_unchanged':True,'all_other_apk_members_unchanged':True,
        'previous_three_features_preserved':True,'device_tested_at_build':False,'server_changed':False,'abyss_records_preserved':True,'resource_version':'1.4.106','registry_promoted':False}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'SHA256.txt').write_text(report['apk_sha256']+'  '+apk.name+'\n',encoding='ascii')
    for name in ('unsigned.apk','aligned.apk'):
        p=(w/name).resolve();assert p.parent==w;p.unlink()
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--variant',choices=VARIANTS,required=True)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
