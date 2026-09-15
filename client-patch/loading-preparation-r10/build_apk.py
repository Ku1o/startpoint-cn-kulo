"""Pinned cumulative R9 diagnostic input; R10 SWF plus fresh, matching AIR/native UUID."""
import argparse
import importlib.util
import json
import re
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'outputs/party-cache-r9-public-diagnostic-fixed3-20260914/StarPoint-CN-1.8.1-party-cache-r9-public-diagnostic-test-20260914.apk'
SOURCE_SHA = 'ab01f3ac983b1b47ee10d7fc17a41f57464e2cd3f546cc9ac4a64144cce740b2'
OLD_UUID = 'af7b51c4-b7be-4ea5-836a-31032d3578da'
SIGNATURES = {'META-INF/MANIFEST.MF','META-INF/WF.SF','META-INF/WF.RSA'}

def module(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result

b = module('r10_native_build', HERE.parent/'startup-cache/build.py')
native = module('r10_native_verify', HERE.parent/'startup-cache/verify_native.py')
endpoint = module('r10_endpoint', HERE.parent/'loading-party-cache-r9/build_public.py')
checker = module('r10_baseline', HERE.parent/'verify_android_baseline.py')

def main(args):
    work, out = args.work.resolve(), args.out.resolve()
    assert not work.exists() and not out.exists()
    assert '.cdn' not in work.parts and '.cdn' not in out.parts
    assert b.sha(SOURCE.read_bytes()) == SOURCE_SHA
    accepted = checker.verify(args.variant)
    patch_report = json.loads(args.swf.with_suffix('.json').read_text('utf-8'))
    assert patch_report['input_swf_sha256'] == '119560545b87cf7cfc36b53a0354fa211cbc7eb05f2bdb6872661d62ee82ed4f'
    assert b.sha(args.swf.read_bytes()) == patch_report['output_swf_sha256']
    runtime = json.loads(args.tests.read_text('utf-8'))
    assert runtime['passed'] and runtime['assertions'] >= 40
    work.mkdir(parents=True); out.mkdir(parents=True)
    uid = str(uuid.uuid4()); (work/'uuid.txt').write_text(uid,encoding='ascii')
    target_endpoint = accepted['endpoint']
    swf = args.swf
    conversion = None
    if args.variant == 'lan':
        swf = work/'lan.swf'
        conversion = endpoint.convert_endpoint(args.swf,swf,'175.178.160.158:8001',target_endpoint.split('://',1)[1])
        conversion.pop('changed_original_bodies')  # historical R9 report field is not an endpoint change
        conversion['changed_method_bodies'] = 0
    with zipfile.ZipFile(SOURCE) as src:
        (work/'original.dex').write_bytes(src.read('classes.dex'))
        assert b.sha(src.read('assets/worldflipper_android_release.swf')) == patch_report['input_swf_sha256']
    run, java, libs = b.run,b.JAVA,b.ALIB
    run([java,'-jar',libs/'baksmali.jar','d','-o',work/'smali',work/'original.dex'],work,'decode')
    original = {p.relative_to(work/'smali'):p.read_text('utf-8') for p in (work/'smali').rglob('*.smali')}
    assert len(original) == 21
    allowed = {'cn/startpoint/StartupCache.smali','cn/startpoint/BuildIdentity.smali',
               'cn/startpoint/diagnostics/BuildInfo.smali','cn/startpoint/diagnostics/DiagnosticsActivity$6.smali'}
    hits = {}
    for name, text in original.items():
        count = text.count(OLD_UUID)
        if count:
            assert name.as_posix() in allowed
            (work/'smali'/name).write_text(text.replace(OLD_UUID,uid),encoding='utf-8')
            hits[name.as_posix()] = count
    assert set(hits) == allowed
    run([java,'-jar',libs/'smali.jar','a','-a','21','-o',work/'classes.dex',work/'smali'],work,'assemble')
    run([java,'-jar',libs/'baksmali.jar','d','-o',work/'readback',work/'classes.dex'],work,'readback')
    assert len(list((work/'readback').rglob('*.smali'))) == len(original)
    for name,text in original.items():
        assert native.canonical((work/'readback'/name).read_text('utf-8').replace(uid,OLD_UUID)) == native.canonical(text)
    payloads = {'classes.dex':(work/'classes.dex').read_bytes(),'assets/worldflipper_android_release.swf':swf.read_bytes()}
    with zipfile.ZipFile(SOURCE) as src:
        manifest = src.read('AndroidManifest.xml')
        assert manifest.count(OLD_UUID.encode('utf-16le')) == 1
        payloads['AndroidManifest.xml'] = manifest.replace(OLD_UUID.encode('utf-16le'),uid.encode('utf-16le'))
        with zipfile.ZipFile(work/'unsigned.apk','w') as dest:
            for item in src.infolist():
                if item.filename not in SIGNATURES: dest.writestr(item,payloads.get(item.filename,src.read(item.filename)))
    align = Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    run([align,'-p','4',work/'unsigned.apk',work/'aligned.apk'],work,'align')
    apk = out/('StarPoint-CN-1.8.1-loading-r10-'+args.variant+'-diagnostic-test-20260915.apk')
    run(['powershell','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1',
         '-InputApk',work/'aligned.apk','-OutputApk',apk,'-ApkSigner',libs/'apksigner.jar','-Java',java],work,'sign')
    signature = run([java,'-jar',libs/'apksigner.jar','verify','--verbose','--print-certs',apk],work,'verify-signature')
    assert b.CERT in signature.lower()
    assert all('Verified using '+scheme+': true' in signature for scheme in ('v1 scheme (JAR signing)','v2 scheme (APK Signature Scheme v2)'))
    run([align,'-c','-p','4',apk],work,'verify-alignment')
    with zipfile.ZipFile(SOURCE) as src,zipfile.ZipFile(apk) as dest:
        assert dest.testzip() is None
        assert len(dest.namelist()) == len(set(dest.namelist()))
        members = set(src.namelist()) - SIGNATURES
        assert members == set(dest.namelist()) - SIGNATURES
        for name in members: assert dest.read(name) == payloads.get(name,src.read(name)),name
        manifest = dest.read('AndroidManifest.xml')
        assert manifest.count(uid.encode('utf-16le')) == 1 and OLD_UUID.encode('utf-16le') not in manifest
    report = {'variant':args.variant,'apk':str(apk),'apk_sha256':b.sha(apk.read_bytes()),'size_bytes':apk.stat().st_size,
              'source_apk_sha256':SOURCE_SHA,'source_swf_sha256':patch_report['input_swf_sha256'],
              'swf_sha256':b.sha(payloads['assets/worldflipper_android_release.swf']),
              'endpoint':target_endpoint,'endpoint_conversion':conversion,'uniqueappversionid':uid,
              'native_identity_sites':hits,'native_classes_preserved':21,'diagnostic_export_preserved':True,
              'changed_apk_members':list(payloads),'all_other_apk_members_preserved':True,'swf_changes':patch_report,
              'runtime_helper_tests':runtime,'v1_v2_signatures':True,'zipalign':True,'signer_sha256':b.CERT,
              'device_tested_at_build':False,'registry_promoted':False,'server_or_runtime_changed':False,
              'persistence_impact':'No saved IDs, database, progress, or save import/export changes.'}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'SHA256.txt').write_text(report['apk_sha256']+'  '+apk.name+'\n',encoding='ascii')
    for name in ('unsigned.apk','aligned.apk'):
        path = (work/name).resolve(); assert path.parent == work; path.unlink()
    print(json.dumps({'apk':str(apk),'sha256':report['apk_sha256'],'uuid':uid},ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant',choices=('lan','public'),required=True)
    for name in ('swf','work','out','tests'): parser.add_argument('--'+name,type=Path,required=True)
    main(parser.parse_args())
