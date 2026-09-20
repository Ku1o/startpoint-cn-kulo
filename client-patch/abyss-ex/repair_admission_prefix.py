"""Repair the pinned EX candidates' folded HMAC prefix without changing gameplay code."""
import argparse, hashlib, importlib.util, json, struct, sys, uuid, zipfile, zlib
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = Path('F:/codex/work/admission-prefix-fix-20260918')
OUT = Path('F:/codex/outputs/abyss-ex-admission-fix-20260918')
INPUT = Path('F:/codex/outputs/abyss-ex-clients-20260917')
INFO = 104549248

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj); return obj
lan = module('prefix_fix_lan', HERE.parent/'r10-public-release/build_lan.py')
layout = module('prefix_fix_layout', HERE.parent/'ios-cumulative-login/macho_signing_layout.py')
sha = lambda b: hashlib.sha256(b).hexdigest()
read = lambda p: json.loads(p.read_text('utf-8-sig'))
def dump(p, value): p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', 'utf8')
IDS = {'android': ('android-181-r10-20260915', 'android-181-abyss-ex-20260917'),
       'ios': ('ios-184-admission-20260915', 'ios-184-abyss-ex-20260917')}

def patch_abc(raw, platform):
    abc = lan.s.m.abcfmt.ABC(raw)
    old, new = [('SP-ADMISSION-1\n'+s+'\n').encode() for s in IDS[platform]]
    indexes = [i for i, value in enumerate(abc.strings) if value == old]
    assert len(indexes) == 1, 'Expected one pinned folded proof prefix'
    index = indexes[0]
    result = lan.patch_strings(raw, {index: (old, new)})
    assert lan.patch_strings(result, {index: (new, old)}) == raw
    patched = lan.s.m.abcfmt.ABC(result)
    assert not any(IDS[platform][0].encode() in value for value in patched.strings)
    assert patched.strings[index] == new
    return result, index

def plain(swf):
    assert swf[:3] in [b'CWS', b'FWS']
    return swf[:8] + zlib.decompress(swf[8:]) if swf[:3] == b'CWS' else swf

def swf_tags(swf):
    data = plain(swf); at = 8 + (5 + 4*(data[8] >> 3) + 7)//8 + 4
    prefix = data[8:at]; tags = []
    while at < len(data):
        start = at; tag = struct.unpack_from('<H', data, at)[0]; at += 2
        kind, size = tag >> 6, tag & 63
        if size == 63: size = struct.unpack_from('<I', data, at)[0]; at += 4
        content = data[at:at+size]; at += size
        tags.append((kind, content, data[start:at]))
    assert at == len(data)
    return prefix, tags

def compress_swf(original, body):
    return b'CWS' + original[3:4] + struct.pack('<I', len(body)+8) + zlib.compress(body)

def android():
    source = INPUT/'StarPoint-CN-1.8.1-abyss-ex-20260917.apk'
    assert sha(source.read_bytes()) == '4fbc354fa93942b65c28d0ecdc1f14fb39851117068b9d5a7c0cb252c87761ea'
    work = WORK/'android'; work.mkdir(exist_ok=False)
    target = OUT/'StarPoint-CN-1.8.1-abyss-ex-admission-fix-20260918.apk'
    assert not target.exists()
    b = lan.b; run = lambda args, label: b.run(args, work, label)
    sig = run([b.JAVA, '-jar', b.ALIB/'apksigner.jar', 'verify', '--verbose', '--print-certs', source], 'input-signature')
    assert b.CERT in sig.lower()
    with zipfile.ZipFile(source) as z:
        swf = z.read(lan.SWF_MEMBER); prefix, tags = swf_tags(swf); fixed_tags=[]; changed=[]
        for i, (kind, content, raw) in enumerate(tags):
            if kind == 82:
                end = content.index(b'\0', 4)
                if content[4:end] == b'cn/admission/ClientAdmission':
                    abc, index = patch_abc(content[end+1:], 'android')
                    updated = content[:end+1]+abc
                    raw = struct.pack('<HI', (82 << 6)|63, len(updated))+updated
                    changed.append({'tag':i, 'string_index':index})
            fixed_tags.append(raw)
        assert len(changed) == 1
        fixed = compress_swf(swf, prefix+b''.join(fixed_tags))
        (work/'fixed.swf').write_bytes(fixed)
        old_uuid='9e963096-e486-4e2d-938b-0ffa1c52d439'; new_uuid=str(uuid.uuid4())
        manifest=z.read('AndroidManifest.xml'); assert manifest.count(old_uuid.encode('utf-16le'))==1
        manifest=manifest.replace(old_uuid.encode('utf-16le'),new_uuid.encode('utf-16le'))
        (work/'original.dex').write_bytes(z.read('classes.dex'))
    run([b.JAVA,'-jar',b.ALIB/'baksmali.jar','d','-o',work/'smali',work/'original.dex'],'decode-dex')
    originals={p.relative_to(work/'smali'):p.read_text('utf8') for p in (work/'smali').rglob('*.smali')}
    changes={}
    for name,text in originals.items():
        if old_uuid in text:
            assert name.as_posix() in {'cn/startpoint/StartupCache.smali','cn/startpoint/BuildIdentity.smali'}
            changes[name.as_posix()]=text.count(old_uuid)
            (work/'smali'/name).write_text(text.replace(old_uuid,new_uuid),'utf8')
    assert len(changes)==2 and sum(changes.values())==2
    run([b.JAVA,'-jar',b.ALIB/'smali.jar','a','-a','21','-o',work/'classes.dex',work/'smali'],'encode-dex')
    run([b.JAVA,'-jar',b.ALIB/'baksmali.jar','d','-o',work/'readback',work/'classes.dex'],'readback-dex')
    assert set(originals)=={p.relative_to(work/'readback') for p in (work/'readback').rglob('*.smali')}
    for name,text in originals.items(): assert lan.native.canonical((work/'readback'/name).read_text('utf8').replace(new_uuid,old_uuid))==lan.native.canonical(text)
    payloads={lan.SWF_MEMBER:fixed,'AndroidManifest.xml':manifest,'classes.dex':(work/'classes.dex').read_bytes()}
    with zipfile.ZipFile(source) as z, zipfile.ZipFile(work/'unsigned.apk','w') as out:
        for info in z.infolist():
            if info.filename not in lan.SIGNATURES:out.writestr(info,payloads.get(info.filename,z.read(info)))
    align=Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    run([align,'-p','4',work/'unsigned.apk',work/'aligned.apk'],'align')
    run(['powershell','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1','-InputApk',work/'aligned.apk','-OutputApk',target,'-ApkSigner',b.ALIB/'apksigner.jar','-Java',b.JAVA],'sign')
    sig=run([b.JAVA,'-jar',b.ALIB/'apksigner.jar','verify','--verbose','--print-certs',target],'verify-signature')
    assert b.CERT in sig.lower() and all('Verified using '+x+': true' in sig for x in ['v1 scheme (JAR signing)','v2 scheme (APK Signature Scheme v2)'])
    run([align,'-c','-p','4',target],'verify-align')
    with zipfile.ZipFile(source) as z,zipfile.ZipFile(target) as out:
        assert out.testzip() is None and len(out.namelist())==len(set(out.namelist()))
        assert set(z.namelist())-lan.SIGNATURES==set(out.namelist())-lan.SIGNATURES
        for n in set(out.namelist())-lan.SIGNATURES:assert out.read(n)==payloads.get(n,z.read(n)),n
        assert out.read('AndroidManifest.xml').count(new_uuid.encode('utf-16le'))==1
        assert old_uuid.encode('utf-16le') not in out.read('AndroidManifest.xml')
    report={'apk':str(target),'sha256':sha(target.read_bytes()),'swf_sha256':sha(fixed),'dex_sha256':sha(payloads['classes.dex']),'uniqueappversionid':new_uuid,'signer_sha256':b.CERT,'v1_v2':True,'zipalign':True,'build_id':IDS['android'][1],'proof_prefix_fixed':changed,'all_other_swf_tags_unchanged':True,'method_bodies_unchanged':True,'dex_changes_only_uuid':changes,'source':str(source),'device_tested':False}
    dump(OUT/'android-repair.json',report); print(json.dumps({k:report[k] for k in ['apk','sha256','build_id','uniqueappversionid']}),flush=True)

def abc_range(native):
    va,size=struct.unpack_from('<QQ',native,INFO+24)
    for _,cmd,raw in layout.load_commands(native):
        if cmd==0x19:
            vm,vs,off,fs=struct.unpack_from('<QQQQ',raw,24)
            if vm<=va and va+size<=vm+fs:return off+va-vm,size
    raise AssertionError('Runtime ABC range missing')

def ios():
    source=INPUT/'StarPoint-iOS-1.8.4-abyss-ex-20260917-r2-unsigned.ipa'
    assert sha(source.read_bytes())=='ce14b180816a6023c2c2bd51e231055bdf7c6083405583b7d58e75396a85c763'
    target=OUT/'StarPoint-iOS-1.8.4-abyss-ex-admission-fix-20260918-unsigned.ipa';assert not target.exists()
    full=(INPUT/'abyss-ex-ios-full.abc').read_bytes();assert sha(full)=='fc9309a462d6739af2e7cdd6299434eb71251d6ad3f78a4da14581ab4db49f5c'
    fixed_full,full_index=patch_abc(full,'ios');digest=hashlib.sha1(fixed_full).digest()
    with zipfile.ZipFile(source) as z:
        native=z.read('Payload/worldflipper.app/worldflipper');swf=z.read('Payload/worldflipper.app/worldflipper_ios_release.swf')
    assert sha(native)=='1d14111267e0c20c87aaa2cd90cd948c779f23ba2f41ab6892ff2d1de2e75bc1'
    assert native[INFO:INFO+20]==hashlib.sha1(full).digest()
    off,size=abc_range(native);runtime=native[off:off+size];fixed_runtime,index=patch_abc(runtime,'ios')
    assert index==full_index and len(fixed_runtime)==size-1
    patched=bytearray(native);patched[off:off+size]=fixed_runtime+b'\0';patched[INFO:INFO+20]=digest
    struct.pack_into('<Q',patched,INFO+32,len(fixed_runtime))
    # In-place string metadata repair; no code, pointer, relocation or segment moves.
    reverse=bytearray(patched);reverse[off:off+size]=runtime;reverse[INFO:INFO+20]=native[INFO:INFO+20];reverse[INFO+32:INFO+40]=native[INFO+32:INFO+40];assert reverse==native
    assert abc_range(patched)==(off,len(fixed_runtime))
    body=plain(swf)[8:];oldhash=b'\0'*4+hashlib.sha1(full).digest();assert body.count(oldhash)==1
    newbody=body.replace(oldhash,b'\0'*4+digest);fixed_swf=compress_swf(swf,newbody)
    assert plain(fixed_swf)[8:].replace(b'\0'*4+digest,oldhash)==body
    signing=layout.assert_signable_layout(patched);assert signing==layout.assert_signable_layout(native)
    # Model TrollStore/ldid replacing differently sized signatures at the unchanged code limit.
    for sigsize in [0x80000,0x200000,0x400000]:
        command,sigoff,_=layout.signature_range(patched);assert sigoff==layout.ldid_code_limit(patched)
        simulated=bytearray(patched[:sigoff]+struct.pack('>III',0xfade0cc0,sigsize,0)+b'\xa5'*(sigsize-12))
        struct.pack_into('<II',simulated,command+8,sigoff,sigsize)
        pos,_,raw=next(x for x in layout.load_commands(simulated) if x[1]==0x19 and x[2][8:24].rstrip(b'\0')==b'__LINKEDIT')
        lo=struct.unpack_from('<Q',raw,40)[0];fs=len(simulated)-lo;struct.pack_into('<Q',simulated,pos+48,fs);struct.pack_into('<Q',simulated,pos+32,(fs+0x3fff)&~0x3fff)
        layout.assert_signable_layout(simulated)
        for row in layout.linkedit_ranges(patched):at=row['offset'];end=at+row['size'];assert simulated[at:end]==patched[at:end]
        assert simulated[off:off+len(fixed_runtime)]==fixed_runtime
    payloads={'Payload/worldflipper.app/worldflipper':patched,'Payload/worldflipper.app/worldflipper_ios_release.swf':fixed_swf}
    with zipfile.ZipFile(source) as z,zipfile.ZipFile(target,'w') as out:
        for info in z.infolist():out.writestr(info,payloads.get(info.filename,z.read(info)))
        out.comment=z.comment
    with zipfile.ZipFile(source) as z,zipfile.ZipFile(target) as out:
        assert out.testzip() is None and out.namelist()==z.namelist()
        for n in out.namelist():assert out.read(n)==payloads.get(n,z.read(n)),n
    fullpath=OUT/'abyss-ex-ios-admission-fixed-full.abc';fullpath.write_bytes(fixed_full)
    report={'ipa':str(target),'ipa_sha256':sha(target.read_bytes()),'native_sha256':sha(patched),'swf_sha256':sha(fixed_swf),'full_abc':str(fullpath),'full_abc_sha256':sha(fixed_full),'full_abc_sha1':digest.hex(),'runtime_abc_sha256':sha(fixed_runtime),'runtime_abc_offset':off,'runtime_abc_size':len(fixed_runtime),'proof_prefix_string_index':index,'build_id':IDS['ios'][1],'native_code_pointers_and_relocations_unchanged':True,'ldid_models':3,'signing_layout':signing,'source':str(source),'device_tested':False,'unsigned':True}
    dump(OUT/'ios-repair.json',report);print(json.dumps({k:report[k] for k in ['ipa','ipa_sha256','build_id']}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('platform',choices=['android','ios']);args=parser.parse_args()
    WORK.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True)
    (android if args.platform=='android' else ios)()
