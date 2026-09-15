"""Build a phone-export diagnostic candidate from the pinned accepted public APK."""
import json, shutil, sys, uuid, zipfile
from common import *
import manifest

def main():
    WORK.mkdir(parents=True,exist_ok=True)
    identity=baseline();dump(WORK/'baseline-identity.json',identity)
    base=Path(identity['apk']);jar=WORK/'android-30.jar'
    assert jar.is_file(),'Obtain Android platform-30_r03.zip from the official SDK repository and verify its recorded checksum first.'
    assert sha(jar.read_bytes())=='96ccfdc84d15fad4e22d76cbb8ef38b150a4b56327957067875ca7e18113a424','Android platform class stubs changed'
    with zipfile.ZipFile(base) as z:
        for target,name in [('input.swf','assets/worldflipper_android_release.swf'),('original.dex','classes.dex'),('AndroidManifest.xml','AndroidManifest.xml')]:
            data=z.read(name);p=WORK/target
            if p.exists():assert p.read_bytes()==data
            else:p.write_bytes(data)
    run=b.run;java=b.JAVA;sdk=b.SDK;libs=b.ALIB
    compiler=[java,'-Dflexlib='+str(sdk/'frameworks'),'-Xmx512m','-jar',sdk/'lib/compc-cli.jar',
              '+configname=air','-swf-version=44','-target-player=32.0','-debug=false']
    run([*compiler,'-compiler.source-path='+str(HERE/'src'),'-include-classes=cn.diagnostics.LoadingTrace',
         '-output='+str(WORK/'loading-trace.swc')],WORK,'compile-helper')
    run([sys.executable,'-B','-X','utf8',HERE/'patch_swf.py'],WORK,'patch-swf')
    print('Loading checkpoints compiled and verified',flush=True)
    uid=str(uuid.uuid4())
    with (WORK/'allocated-identities.jsonl').open('a',encoding='utf8') as f:
        f.write(json.dumps({'uuid':uid,'swf_sha256':sha((WORK/'diagnostic.swf').read_bytes())})+'\n')
    (WORK/'uuid.txt').write_text(uid,encoding='ascii')
    generated=WORK/'generated/cn/startpoint/diagnostics/BuildInfo.java';generated.parent.mkdir(parents=True,exist_ok=True)
    generated.write_text('package cn.startpoint.diagnostics; public final class BuildInfo { public static final String BUILD="'+BUILD+'", AIR_UUID="'+uid+'", BASE_APK_SHA256="'+BASE_SHA+'"; }\n',encoding='utf8')
    classes=WORK/('native-classes-'+uid);classes.mkdir()
    sources=sorted((HERE/'native').rglob('*.java'))
    run([java.with_name('javac.exe'),'--release','8','-encoding','UTF-8','-cp',jar,'-d',classes,*sources,generated],WORK,'compile-native')
    run([java.with_name('javac.exe'),'--release','8','-encoding','UTF-8','-cp',classes,'-d',classes,HERE/'tests/LogStoreTest.java'],WORK,'compile-storage-test')
    result=run([java,'-cp',classes,'LogStoreTest',WORK/('storage-test-'+uid)],WORK,'storage-test')
    assert 'LOG_STORE_TESTS_PASSED 17' in result,result
    with zipfile.ZipFile(WORK/'native-helper.jar','w') as z:
        for p in sorted((classes/'cn').rglob('*.class')):z.write(p,p.relative_to(classes).as_posix())
    dex=WORK/('helper-dex-'+uid);dex.mkdir()
    run([java,'-cp',sdk/'lib/android/bin/d8.jar','com.android.tools.r8.D8','--lib',jar,'--min-api','19','--output',dex,WORK/'native-helper.jar'],WORK,'d8')
    run([java,'-jar',libs/'baksmali.jar','d','-o',WORK/'base-smali',WORK/'original.dex'],WORK,'base-dex-decode')
    run([java,'-jar',libs/'baksmali.jar','d','-o',WORK/('helper-smali-'+uid),dex/'classes.dex'],WORK,'helper-dex-decode')
    smali=WORK/('merged-smali-'+uid);smali.mkdir()
    originals={p.relative_to(WORK/'base-smali'):p.read_text(encoding='utf8') for p in (WORK/'base-smali').rglob('*.smali')}
    assert len(originals)==6
    replacements=0
    for name,text in originals.items():
        hits=text.count(BASE_UUID)
        if hits:assert name.as_posix() in ('cn/startpoint/StartupCache.smali','cn/startpoint/BuildIdentity.smali')
        replacements+=hits;p=smali/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text.replace(BASE_UUID,uid),encoding='utf8')
    assert replacements==2
    helper_names=[]
    for p in (WORK/('helper-smali-'+uid)).rglob('*.smali'):
        name=p.relative_to(WORK/('helper-smali-'+uid));assert name not in originals
        helper_names.append(name.as_posix());target=smali/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    run([java,'-jar',libs/'smali.jar','a','-a','19','-o',WORK/'classes.dex',smali],WORK,'dex-assemble')
    run([java,'-jar',libs/'baksmali.jar','d','-o',WORK/('readback-smali-'+uid),WORK/'classes.dex'],WORK,'dex-readback')
    for name,old in originals.items():
        assert native.canonical((WORK/('readback-smali-'+uid)/name).read_text(encoding='utf8').replace(uid,BASE_UUID))==native.canonical(old),name
    assert len(list((WORK/('readback-smali-'+uid)).rglob('*.smali')))==len(originals)+len(helper_names)
    # Compile only the new component nodes, then append them to the original binary manifest.
    component_manifest=WORK/'components/AndroidManifest.xml';component_manifest.parent.mkdir(exist_ok=True)
    shutil.copyfile(HERE/'components.xml',component_manifest)
    run([sdk/'lib/android/bin/aapt.exe','package','-f','-M',component_manifest,'-I',jar,'-F',WORK/'components.apk'],WORK,'compile-components')
    with zipfile.ZipFile(WORK/'components.apk') as z:template=z.read('AndroidManifest.xml')
    new_manifest,manifest_report=manifest.merge((WORK/'AndroidManifest.xml').read_bytes(),template,BASE_UUID,uid)
    (WORK/'patched-manifest.xml').write_bytes(new_manifest)
    excluded={'META-INF/MANIFEST.MF','META-INF/WF.SF','META-INF/WF.RSA'}
    payloads={'AndroidManifest.xml':new_manifest,'classes.dex':(WORK/'classes.dex').read_bytes(),
              'assets/worldflipper_android_release.swf':(WORK/'diagnostic.swf').read_bytes()}
    out=ROOT/'outputs/loading-diagnostic-public-test-20260913';out.mkdir(parents=True,exist_ok=True)
    apk=out/('StarPoint-CN-1.8.1-loading-diagnostic-public-20260913-'+REVISION+'.apk')
    assert not apk.exists(),'Never overwrite a delivered diagnostic artifact; allocate a new revision.'
    with zipfile.ZipFile(base) as z,zipfile.ZipFile(WORK/'unsigned.apk','w') as dest:
        for item in z.infolist():
            if item.filename not in excluded:dest.writestr(item,payloads.get(item.filename,z.read(item.filename)))
    align=Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    run([align,'-p','4',WORK/'unsigned.apk',WORK/'aligned.apk'],WORK,'align')
    run(['powershell','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1',
         '-InputApk',WORK/'aligned.apk','-OutputApk',apk,'-ApkSigner',libs/'apksigner.jar','-Java',java],WORK,'sign')
    signature=run([java,'-jar',libs/'apksigner.jar','verify','--verbose','--print-certs',apk],WORK,'signature-check')
    assert b.CERT in signature.lower()
    for version in ['v1 scheme (JAR signing)','v2 scheme (APK Signature Scheme v2)']:assert 'Verified using '+version+': true' in signature
    run([align,'-c','-p','4',apk],WORK,'zipalign-check')
    with zipfile.ZipFile(base) as old,zipfile.ZipFile(apk) as final:
        assert set(old.namelist())-excluded==set(final.namelist())-excluded
        for name in set(old.namelist())-excluded:assert final.read(name)==payloads.get(name,old.read(name)),name
    report={'status':'built_pending_independent_verification','build':BUILD,'apk':str(apk),'apk_sha256':sha(apk.read_bytes()),
        'size_bytes':apk.stat().st_size,'baseline':identity,'swf_sha256':sha(payloads['assets/worldflipper_android_release.swf']),
        'dex_sha256':sha(payloads['classes.dex']),'uniqueappversionid':uid,'native_build_identity':uid,
        'changed_apk_members':list(payloads),'manifest':manifest_report,'old_native_classes_preserved':6,'new_native_classes':helper_names,
        'signature_v1_v2':True,'signer_certificate_sha256':b.CERT,'zipalign':True,
        'android_platform_archive_sha1':'e7c6280901dcfa511af098d67dd88c4dfcbc6ea2',
        'storage_tests':17,'new_permissions':[],'gameplay_logic_changed':False,'save_schema_changed':False,
        'runtime_mirror_changed':False,'server_changed':False,'registry_promoted':False,'device_tested':False}
    dump(out/('build-report-'+REVISION+'.json'),report);dump(WORK/'build-report.json',report)
    (out/('SHA256-'+REVISION+'.txt')).write_text(report['apk_sha256']+'  '+apk.name+'\n',encoding='ascii')
    # These two exact, task-owned signing intermediates are regenerated on each build.
    for name in ['unsigned.apk','aligned.apk']:
        p=(WORK/name).resolve();assert p.parent==WORK and p.suffix=='.apk';p.unlink()
    print(json.dumps({'apk':str(apk),'sha256':report['apk_sha256'],'uuid':uid},ensure_ascii=False))

if __name__=='__main__':main()
