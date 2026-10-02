"""Package the cumulative author-content SWF as an Android LAN candidate."""
from __future__ import annotations
import argparse, copy, hashlib, json, os, struct, subprocess, sys, uuid, zipfile, zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'independent-formations'))
from set_edit_common import s
from package_set_edit_public_android import serialize

BASE_APK=Path('F:/codex/outputs/set-edit-c8601-public-20260924/StarPoint-CN-1.8.1-independent-formations-set-edit-c8601-public-20260924-0fcf027e.apk')
BASE_SHA='f24f469c1be0cb3d2d16520a739ace52b58055ce65621f5243404026beba6066'
BASE_SWF='1785d16b430ea7008e7d70cf1bca106f3f5410bbf86566063e83ad856d9a0a49'
INPUT_SWF='fce5aabaea98ffa84381de91e936a5adfd5991e955ed0c62fb804b7551c5a10c'
OLD_UUID='0fcf027e-c219-4d6c-9221-7e10db70b513'
OLD_HOST='175.178.160.158'
LAN_HOST=os.environ.get('STARPOINT_LAN_HOST')
ADMISSION_ID='android-181-independent-party-20260923'
SIGNER_SHA='569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894'
SWF_MEMBER='assets/worldflipper_android_release.swf'
SIGNATURES={'META-INF/MANIFEST.MF','META-INF/WF.SF','META-INF/WF.RSA'}
JAVA=Path('D:/java/bin/java.exe')
BT=Path('F:/StartPointCN/wf_full_patch/build-tools')
LIBS=Path('F:/codex/ios-rush-leaderboard-port-20260830/AIRSDK_51.2.1.5/lib/android/lib')
sha=lambda b:hashlib.sha256(b).hexdigest()

def main(source,work,out,*,expected_swf=INPUT_SWF,label='author-1043'):
    assert LAN_HOST and ':' not in LAN_HOST and '/' not in LAN_HOST, 'Set STARPOINT_LAN_HOST to the LAN host before packaging'
    assert sha(BASE_APK.read_bytes())==BASE_SHA
    assert sha(source.read_bytes())==expected_swf
    work.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    uid=str(uuid.uuid4())
    def run(args,log):
        r=subprocess.run([str(a) for a in args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        (work/log).write_bytes(r.stdout)
        if r.returncode:raise RuntimeError(log+': '+r.stdout.decode('utf-8','replace')[-3000:])
        return r.stdout.decode('utf-8','replace')
    version,header,tags=s.parts(source);replaced=[]
    for idx,t in enumerate(tags):
        if t[0]!=82:continue
        a=t[3];changed=False
        for i,value in enumerate(a.strings):
            if not isinstance(value,bytes):continue
            new=value.replace(OLD_HOST.encode(),LAN_HOST.encode())
            if new!=value:
                assert OLD_HOST.encode()+b':8001' in value
                a.strings[i]=new;changed=True
                replaced.append({'tag':idx,'index':i,'before':value.decode(),'after':new.decode()})
        if changed:
            payload=t[2]+serialize(a,t[4])
            t[1]=struct.pack('<HI',(82<<6)|63,len(payload))+payload
    assert len(replaced)==9,replaced
    raw=header+b''.join(t[1] for t in tags)
    swf=b'CWS'+bytes([version])+struct.pack('<I',len(raw)+8)+zlib.compress(raw)
    final_swf=work/'android-lan.swf';final_swf.write_bytes(swf)
    # Round-trip each changed ABC with restored strings. This proves every
    # method, trait and other pool is preserved during endpoint conversion.
    _,_,back=s.parts(final_swf);_,_,original=s.parts(source)
    by_tag={r['tag'] for r in replaced}
    for i,(a,b) in enumerate(zip(original,back)):
        if i not in by_tag:assert a[1]==b[1];continue
        for row in (r for r in replaced if r['tag']==i):
            assert b[3].strings[row['index']]==row['after'].encode()
            b[3].strings[row['index']]=row['before'].encode()
        assert serialize(b[3],a[4])==a[4],i
    with zipfile.ZipFile(BASE_APK) as z:
        manifest=z.read('AndroidManifest.xml');dex=z.read('classes.dex')
        assert sha(z.read(SWF_MEMBER))==BASE_SWF
        members={n:sha(z.read(n)) for n in z.namelist() if n not in SIGNATURES}
    assert manifest.count(OLD_UUID.encode('utf-16le'))==1
    assert dex.count(OLD_UUID.encode())==1
    original_dex=work/'original.dex';original_dex.write_bytes(dex)
    smali=work/('smali-'+uid);readback=work/('readback-'+uid)
    run([JAVA,'-jar',LIBS/'baksmali.jar','d','-o',smali,original_dex],'dex-decode.log')
    originals={p.relative_to(smali):p.read_text(encoding='utf-8') for p in smali.rglob('*.smali')}
    hits={}
    for name,value in originals.items():
        if OLD_UUID in value:
            hits[name.as_posix()]=value.count(OLD_UUID)
            (smali/name).write_text(value.replace(OLD_UUID,uid),encoding='utf-8')
    assert hits=={'cn/startpoint/StartupCache.smali':1,'cn/startpoint/BuildIdentity.smali':1},hits
    dex_path=work/'classes.dex'
    run([JAVA,'-jar',LIBS/'smali.jar','a','-a','21','-o',dex_path,smali],'dex-assemble.log')
    run([JAVA,'-jar',LIBS/'baksmali.jar','d','-o',readback,dex_path],'dex-readback.log')
    assert {p.relative_to(readback) for p in readback.rglob('*.smali')}==set(originals)
    for name,value in originals.items():
        check=(readback/name).read_text(encoding='utf-8')
        if name.as_posix() in hits:check=check.replace(uid,OLD_UUID)
        assert check==value,str(name)
    payloads={'AndroidManifest.xml':manifest.replace(OLD_UUID.encode('utf-16le'),uid.encode('utf-16le')),
              'classes.dex':dex_path.read_bytes(),SWF_MEMBER:swf}
    unsigned=work/('unsigned-'+uid+'.apk');aligned=work/('aligned-'+uid+'.apk')
    with zipfile.ZipFile(BASE_APK) as src,zipfile.ZipFile(unsigned,'w') as dst:
        for item in src.infolist():
            if item.filename not in SIGNATURES:dst.writestr(item,payloads.get(item.filename,src.read(item.filename)))
    run([BT/'zipalign.exe','-p','4',unsigned,aligned],'zipalign.log')
    apk=out/('StarPoint-CN-1.8.1-'+label+'-lan-20260924-'+uid[:8]+'.apk')
    run(['powershell','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1',
         '-InputApk',aligned,'-OutputApk',apk,'-ApkSigner',BT/'lib/apksigner.jar','-Java',JAVA],'sign.log')
    verify=run([JAVA,'-jar',BT/'lib/apksigner.jar','verify','--verbose','--print-certs',apk],'signature-verify.log')
    assert SIGNER_SHA in verify.lower()
    for mode in ('v1 scheme (JAR signing)','v2 scheme (APK Signature Scheme v2)'):
        assert 'Verified using '+mode+': true' in verify
    run([BT/'zipalign.exe','-c','-p','4',apk],'alignment-verify.log')
    with zipfile.ZipFile(apk) as z:
        assert z.testzip() is None
        assert set(z.namelist())-SIGNATURES==set(members)
        for n,old_hash in members.items():
            data=z.read(n)
            if n in payloads:assert data==payloads[n]
            else:assert sha(data)==old_hash,n
        assert z.read('AndroidManifest.xml').count(uid.encode('utf-16le'))==1
        assert OLD_UUID.encode('utf-16le') not in z.read('AndroidManifest.xml')
        assert uid.encode() in z.read('classes.dex') and OLD_UUID.encode() not in z.read('classes.dex')
    report={'status':'offline_candidate','apk':str(apk),'apk_sha256':sha(apk.read_bytes()),
        'source_apk':str(BASE_APK),'source_apk_sha256':BASE_SHA,'source_swf_sha256':BASE_SWF,
        'integrated_swf_sha256':expected_swf,'swf_sha256':sha(swf),'endpoint':'http://'+LAN_HOST+':8001',
        'endpoint_rewrites':replaced,'endpoint_only_abc_roundtrip_verified':True,
        'uniqueappversionid':uid,'previous_uniqueappversionid':OLD_UUID,
        'package_name':'com.leiting.wf','version_name':'1.8.1','version_code':1008001,
        'admission_id':ADMISSION_ID,'admission_pair_unchanged':True,'native_identity_sites':hits,
        'signer_certificate_sha256':SIGNER_SHA,'v1_signature':True,'v2_signature':True,'zipalign':True,
        'native_classes_verified':len(originals),'unchanged_apk_members':len(members)-3,
        'device_tested':False,'accepted_registry_changed':False,'ios_ipa_built':False}
    (out/'package-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/(apk.name+'.sha256')).write_text(report['apk_sha256']+'  '+apk.name+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('apk','apk_sha256','swf_sha256','uniqueappversionid')},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--swf',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();main(a.swf,a.work,a.out)
