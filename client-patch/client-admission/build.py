"""Build from the accepted registry; only reviewed method hooks and fresh AIR identity."""
import argparse, copy, importlib.util, json, re, secrets, struct, uuid, zipfile, zlib
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
s=module('admission_swf_support',HERE.parent/'startup-cache/build_swf.py')
b=module('admission_apk_support',HERE.parent/'startup-cache/build.py')
native=module('admission_native_support',HERE.parent/'startup-cache/verify_native.py')
checker=module('admission_baseline',HERE.parent/'verify_android_baseline.py')

def main(args):
    identity=checker.verify(args.variant)
    work=args.work.resolve();out=args.out.resolve();keysPath=args.keys.resolve()
    for target in (work,out,keysPath):
        assert '.cdn' not in [part.lower() for part in target.parts], 'read-only CDN boundary'
    assert re.fullmatch(r'[A-Za-z0-9_-]{1,80}',args.build_id), 'invalid build ID'
    assert Path(args.name).name==args.name and args.name.endswith('.apk'), 'invalid APK filename'
    work.mkdir(parents=True,exist_ok=False);out.mkdir(parents=True,exist_ok=True)
    origin=args.origin or identity['endpoint']
    assert origin.startswith('http://') and '/' not in origin[7:] and '"' not in origin
    with zipfile.ZipFile(identity['apk']) as z:
        (work/'input.swf').write_bytes(z.read('assets/worldflipper_android_release.swf'))
        (work/'original.dex').write_bytes(z.read('classes.dex'))
    version,header,tags=s.parts(work/'input.swf');abcs=[t for t in tags if t[0]==82]
    assert sum(len(t[3].bodies) for t in abcs)==identity['method_bodies_checked']
    assert len(abcs)-1==identity['main_abc_index']
    main=abcs[-1];changes=[];originals={id(t):copy.deepcopy(t[3]) for t in abcs}
    def view(t):return s.m.View(SimpleNamespace(abc=t[3]),s.m.asm)
    def q(t,ns,name):
        a=t[3];v=view(t);pool=s.PoolEditor(a)
        match=[i for i in range(1,len(a.multinames)) if v.mn(i)==(7,(22,ns),name)]
        if match:return match[0]
        spaces=[i for i,n in enumerate(a.namespaces) if i and n[0]==22 and a.s(n[1])==ns and n[1]!=0]
        if spaces:space=spaces[0]
        else:
            ix=pool.string(ns)
            if ix==0:a.strings.append(b'');ix=len(a.strings)-1
            a.namespaces.append((22,ix));space=len(a.namespaces)-1
        a.multinames.append((7,space,pool.string(name)));return len(a.multinames)-1
    def insert(t,bi,at,code):
        body=t[3].bodies[bi];old=body[5]
        body[5],body[6],_,placed=s.m.asm.splice_many(body,[(at,s.m.asm.assemble(code),s.m.asm.ENTER)])
        assert s.m.asm.unsplice_many(body[5],placed)==old
        body[1]=max(body[1],8)
        changes.append({'abc':abcs.index(t),'body':bi,'kind':'reversible insertion'})
    if not args.legacy:
        keysPath.parent.mkdir(parents=True,exist_ok=True)
        keys=json.loads(keysPath.read_text('utf-8-sig')) if keysPath.exists() else {}
        assert isinstance(keys,dict) and all(isinstance(v,str) and re.fullmatch(r'[a-f0-9]{64}',v) for v in keys.values()), 'invalid build keys'
        if args.build_id not in keys:
            keys[args.build_id]=secrets.token_hex(32)
            keysPath.write_text(json.dumps(keys,indent=2)+'\n','utf-8')
        generated=work/'generated/cn/admission';generated.mkdir(parents=True)
        (generated/'BuildConfig.as').write_text('package cn.admission { public final class BuildConfig { public static const ID:String='+json.dumps(args.build_id)+'; public static const KEY:String='+json.dumps(keys[args.build_id])+'; public static const ORIGIN:String='+json.dumps(origin)+'; } }','utf-8')
        b.run([b.JAVA,'-Dflexlib='+str(b.SDK/'frameworks'),'-Xmx512m','-jar',b.SDK/'lib/compc-cli.jar',
            '+configname=air','-swf-version=44','-target-player=32.0','-debug=false',
            '-compiler.source-path='+str(HERE/'src')+','+str(work/'generated'),'-include-classes=cn.admission.ClientAdmission',
            '-output='+str(work/'admission.swc')],work,'compile-helper')
        helper=q(main,'cn.admission','ClientAdmission')
        assert view(main).normalized(29670)[0][332][0:2]==(0x62,[16])
        insert(main,29670,332,[('getlex',helper),('getlocal',16),('getlocal_2',),
            ('callproperty',q(main,'','forwardAdmission'),2),('iftrue','END'),('returnvoid',)])
        insert(main,29697,5,[('getlex',helper),('getlocal_0',),('getlocal_1',),('getlocal_2',),('getlocal_3',),
            ('callproperty',q(main,'','beforeQueue'),4),('iftrue','END'),('returnvoid',)])
        insert(main,29701,2,[('getlex',helper),('getlocal_0',),('getlocal_1',),('getlocal_3',),
            ('callproperty',q(main,'','inspect'),3),('iftrue','END'),('returnvoid',)])
        insert(main,31405,5,[('getlex',helper),('getlocal_0',),('callpropvoid',q(main,'','socket'),1)])
        login=next(t for t in abcs if any(t[3].mn_name(i[0])=='cn.account::PlayerLogin' for i in t[3].instances))
        v=view(login);bi=v.by_label['cn.account::PlayerLogin$/cn.account:PlayerLogin::request|1'][0]
        body=login[3].bodies[bi];code=s.m.asm.decode(body[5]);rows=v.normalized(bi)[0]
        hits=[i for i,r in enumerate(rows) if r[0]==0x4f and r[1]==[(7,(22,''),'load'),1]]
        assert len(hits)==1
        # Preserve the original call's stack [loader, request]; two temporary locals
        # let the replacement call our helper with the same objects and callbacks.
        at=hits[0];temp=body[2];body[2]+=2
        block=s.m.asm.assemble([('setlocal',temp+1),('setlocal',temp),('getlex',q(login,'cn.admission','ClientAdmission')),
            ('getlocal',temp),('getlocal',temp+1)])
        body[5],body[6],_,placed=s.m.asm.splice_many(body,[(at,block,s.m.asm.ENTER)])
        code=s.m.asm.decode(body[5]);call=code[at+len(block)];call.args=[q(login,'','load'),2]
        body[5]=s.m.asm.encode(code)[0];body[1]=max(body[1],4)
        changes.append({'abc':abcs.index(login),'body':bi,'kind':'loader wrapper'})
    v=view(main);a=main[3];pool=s.PoolEditor(a)
    if origin!=identity['endpoint']:
        body=a.bodies[92013];code=s.m.asm.decode(body[5]);assert code[11].op==0x2c
        assert a.s(code[11].args[0])==identity['endpoint'].split('://',1)[1]
        code[11].args[0]=pool.string(origin.split('://',1)[1]);body[5]=s.m.asm.encode(code)[0]
        changes.append({'abc':abcs.index(main),'body':92013,'kind':'endpoint'})
    if args.isolate_storage:
        a.bodies[91935][5]=s.m.asm.encode(s.m.asm.assemble([('pushstring',pool.string('client_admission_trial_v1')),('returnvalue',)]))[0]
        changes.append({'abc':abcs.index(main),'body':91935,'kind':'isolated test preferences'})
    changed={(r['abc'],r['body']) for r in changes}
    for ti,t in enumerate(abcs):
        old=originals[id(t)]
        for i,body in enumerate(t[3].bodies):
            if (ti,i) not in changed:assert s.m.freeze(body)==s.m.freeze(old.bodies[i]),(ti,i)
        for field in ('methods','metadata','instances','classes','scripts'):
            assert s.m.freeze(getattr(old,field))==s.m.freeze(getattr(t[3],field)),field
        if any(x[0]==ti for x in changed):
            payload=t[2]+s.serialize(t[3],t[4]);t[1]=struct.pack('<HI',(82<<6)|63,len(payload))+payload
    extra=b'';extra_count=0
    if not args.legacy:
        with zipfile.ZipFile(work/'admission.swc') as library:(work/'helper.swf').write_bytes(library.read('library.swf'))
        helper_tags=[t for t in s.parts(work/'helper.swf')[2] if t[0]==82]
        helper_classes=[t[3].mn_name(i[0]) for t in helper_tags for i in t[3].instances]
        assert set(helper_classes)=={'cn.admission::ClientAdmission','cn.admission::BuildConfig'},helper_classes
        extra=b''.join(t[1] for t in helper_tags);extra_count=len(helper_tags)
    raw=header+b''.join((extra if t is abcs[0] else b'')+t[1] for t in tags)
    swf=work/'client-admission.swf';swf.write_bytes(b'CWS'+bytes([version])+struct.pack('<I',len(raw)+8)+zlib.compress(raw))
    after=[t for t in s.parts(swf)[2] if t[0]==82]
    for i,t in enumerate(abcs):assert s.m.freeze(after[i+extra_count][3].bodies)==s.m.freeze(t[3].bodies)
    uid=str(uuid.uuid4());old_uid=identity['uniqueappversionid']
    b.run([b.JAVA,'-jar',b.ALIB/'baksmali.jar','d','-o',work/'smali',work/'original.dex'],work,'decode-dex')
    nativeOriginal={p.relative_to(work/'smali'):p.read_text('utf8') for p in (work/'smali').rglob('*.smali')};hits={}
    for name,text in nativeOriginal.items():
        if old_uid in text:
            assert name.as_posix() in ('cn/startpoint/StartupCache.smali','cn/startpoint/BuildIdentity.smali')
            hits[str(name)]=text.count(old_uid);(work/'smali'/name).write_text(text.replace(old_uid,uid),'utf8')
    assert sum(hits.values())==2
    b.run([b.JAVA,'-jar',b.ALIB/'smali.jar','a','-a','21','-o',work/'classes.dex',work/'smali'],work,'encode-dex')
    b.run([b.JAVA,'-jar',b.ALIB/'baksmali.jar','d','-o',work/'native-readback',work/'classes.dex'],work,'readback-dex')
    for name,text in nativeOriginal.items():assert native.canonical((work/'native-readback'/name).read_text('utf8').replace(uid,old_uid))==native.canonical(text)
    signatures={'META-INF/MANIFEST.MF','META-INF/WF.SF','META-INF/WF.RSA'}
    payloads={'assets/worldflipper_android_release.swf':swf.read_bytes(),'classes.dex':(work/'classes.dex').read_bytes()}
    with zipfile.ZipFile(identity['apk']) as z,zipfile.ZipFile(work/'unsigned.apk','w') as dest:
        manifest=z.read('AndroidManifest.xml');assert manifest.count(old_uid.encode('utf-16le'))==1
        payloads['AndroidManifest.xml']=manifest.replace(old_uid.encode('utf-16le'),uid.encode('utf-16le'))
        for item in z.infolist():
            if item.filename not in signatures:dest.writestr(item,payloads.get(item.filename,z.read(item.filename)))
    align=Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    b.run([align,'-p','4',work/'unsigned.apk',work/'aligned.apk'],work,'align')
    apk=out/args.name;assert not apk.exists()
    b.run(['powershell','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1',
        '-InputApk',work/'aligned.apk','-OutputApk',apk,'-ApkSigner',b.ALIB/'apksigner.jar','-Java',b.JAVA],work,'sign')
    sig=b.run([b.JAVA,'-jar',b.ALIB/'apksigner.jar','verify','--verbose','--print-certs',apk],work,'verify-signature')
    assert b.CERT in sig.lower() and all('Verified using '+x+': true' in sig for x in ['v1 scheme (JAR signing)','v2 scheme (APK Signature Scheme v2)'])
    b.run([align,'-c','-p','4',apk],work,'verify-align')
    with zipfile.ZipFile(identity['apk']) as original,zipfile.ZipFile(apk) as check:
        assert len(check.namelist())==len(set(check.namelist()))
        assert set(check.namelist())-signatures==set(original.namelist())-signatures
        for name in set(check.namelist())-signatures:assert check.read(name)==payloads.get(name,original.read(name)),name
        assert check.read('AndroidManifest.xml').count(uid.encode('utf-16le'))==1
        assert old_uid.encode('utf-16le') not in check.read('AndroidManifest.xml')
    report={'apk':str(apk),'sha256':b.sha(apk.read_bytes()),'swf_sha256':b.sha(swf.read_bytes()),'baseline':identity,
        'changes':changes,'original_bodies_verified':identity['method_bodies_checked'],'all_other_methods_preserved':True,
        'build_id':None if args.legacy else args.build_id,'uniqueappversionid':uid,'signer_sha256':b.CERT,'zipalign':True,'v1_v2':True,
        'origin':origin,'isolated_preferences':args.isolate_storage,'registry_promoted':False}
    (out/(apk.stem+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    for name in ['unsigned.apk','aligned.apk']:(work/name).unlink()
    print(json.dumps({k:report[k] for k in ['apk','sha256','build_id','original_bodies_verified']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--name',required=True);p.add_argument('--variant',choices=['lan','public'],default='lan');p.add_argument('--origin')
    p.add_argument('--keys',type=Path,required=True);p.add_argument('--build-id',default='android-20260915-admission-01')
    p.add_argument('--legacy',action='store_true');p.add_argument('--isolate-storage',action='store_true');main(p.parse_args())
