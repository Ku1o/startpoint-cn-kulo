"""Selective cumulative APK composition using repository tools and private signing paths.
Does not install, rotate admission, update registry, upload or deploy anything.
Run only after explicit packaging authorization inside the bounded Job wrapper.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,uuid,zipfile
import bootstrap
from input_config import input_path,input_sha,repo_path,require_output
sys.path.insert(0,str(repo_path('client-patch/pr43-port')))
import package_android as pkg
SHA=lambda raw:hashlib.sha256(raw).hexdigest()
SIGNER='569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894'
RECIPES={
 'tutorial':('settings_apk','tutorial_swf','1a0bddfa-d986-416c-9f77-7f22257a01c9'),
 'trigger9000':('tutorial_apk','trigger9000_swf','3a71ee78-245d-4f71-8304-f47035f10472'),
 'dash':('trigger9000_apk','final_swf','3c3474db-a831-4174-a434-cf922839a4f7')}

def run(command,log):
    result=subprocess.run([str(x) for x in command],capture_output=True,text=True,
                          encoding='utf-8',errors='replace',timeout=120)
    log.write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError('Packaging tool failed; see '+str(log))
    return result.stdout+result.stderr

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',choices=RECIPES,required=True)
    ap.add_argument('--out',required=True);args=ap.parse_args();out=require_output(args.out)
    base_role,swf_role,old_uuid=RECIPES[args.revision]
    base=input_path(base_role);swf=input_path(swf_role);expected=input_sha(base_role)
    signer=json.loads(input_path('signer_config').read_text(encoding='utf-8-sig'))
    # Only file locations, never password/key/credential bytes, enter this process.
    for key in ('java','powershell','build_tools','keystore','credential_path'):
        if not Path(signer[key]).is_absolute():raise ValueError('Private signer path must be absolute: '+key)
    if signer['expected_signer_sha256']!=SIGNER:raise ValueError('Signer identity differs')
    with zipfile.ZipFile(base) as archive:dex=archive.read('classes.dex')
    for _ in range(100):
        new_uuid=str(uuid.uuid4())
        try:pkg.patch_dex(dex,old_uuid,new_uuid);break
        except pkg.PortError as error:
            if 'order/duplicates' not in str(error):raise
    else:raise RuntimeError('Cannot allocate ordered fresh AIR UUID')
    out.mkdir(parents=True)
    report=pkg.package(base,swf,None,new_uuid,out/'unsigned',base_sha256=expected,
                       swf_sha256=input_sha(swf_role),old_uuid=old_uuid,output_root=out)
    tools=Path(signer['build_tools']);java=Path(signer['java'])
    aligned=out/'candidate.aligned.apk';signed=out/('StarPoint-CN-1.8.1-release1031-'+args.revision+'-lan.apk')
    run([tools/'zipalign.exe','-p','4',report['apk'],aligned],out/'zipalign-build.log')
    run([signer['powershell'],'-NoProfile','-ExecutionPolicy','Bypass','-File',
         repo_path('client-patch/abyss-autostart/sign_apk.ps1'),'-Java',java,
         '-ApkSigner',tools/'lib/apksigner.jar','-Keystore',signer['keystore'],
         '-CredentialPath',signer['credential_path'],'-InputApk',aligned,'-OutputApk',signed],out/'sign.log')
    check=run([java,'-Xmx512m','-jar',tools/'lib/apksigner.jar','verify','--verbose','--print-certs',signed],out/'signature-verify.log')
    assert SIGNER in check.lower()
    for scheme in ('v1 scheme (JAR signing)','v2 scheme (APK Signature Scheme v2)'):
        assert f'Verified using {scheme}: true' in check
    run([tools/'zipalign.exe','-c','-p','4',signed],out/'zipalign-final.log')
    with zipfile.ZipFile(base) as old,zipfile.ZipFile(signed) as final:
        assert final.testzip() is None and len(final.namelist())==len(set(final.namelist()))
        names={n for n in old.namelist() if not pkg.signature(n)}
        assert names=={n for n in final.namelist() if not pkg.signature(n)}
        changed=set(report['changed_members'])
        assert changed=={pkg.SWF,'AndroidManifest.xml','classes.dex'}
        for name in sorted(names-changed):assert old.read(name)==final.read(name),name
        assert final.read(pkg.SWF)==swf.read_bytes()
        manifest,identity=pkg.patch_manifest(final.read('AndroidManifest.xml'),new_uuid,old_uuid)
        assert manifest==old.read('AndroidManifest.xml')
        assert pkg.patch_dex(final.read('classes.dex'),new_uuid,old_uuid)[0]==old.read('classes.dex')
        assert SHA(final.read(pkg.SWF))==input_sha(swf_role)
    result={'status':'packaged_offline_runtime_acceptance_separate','revision':args.revision,
            'apk':str(signed),'apkSha256':SHA(signed.read_bytes()),'swfSha256':input_sha(swf_role),
            'baseApkSha256':expected,'uuid':new_uuid,'previousUuid':old_uuid,'identity':identity,
            'signerSha256':SIGNER,'signatureV1V2':True,'zipalign':True,'crc':True,
            'nonTargetMembersPreserved':len(names-changed),'manifestAndDexUuidInverseExact':True,
            'bundleChanged':False,'admissionAdvanced':False,'acceptedRegistryChanged':False,
            'deviceInstalled':False,'cloudChanged':False}
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
