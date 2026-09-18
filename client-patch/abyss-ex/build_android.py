"""Package the verified EX SWF with a fresh AIR identity and independent admission ID."""
from release_common import *
import argparse, ipaddress, struct, uuid, zipfile, zlib
from urllib.parse import urlsplit

def main(lan_origin=None):
    reg, _ = registries(); apk = ROOT/reg['apk']; work = WORK/('android-lan' if lan_origin else 'android')
    origin=lan_origin or reg['endpoint']
    if lan_origin:
        parsed=urlsplit(origin)
        assert parsed.scheme=='http' and not parsed.path and not parsed.query and not parsed.fragment
        assert parsed.username is None and parsed.password is None
        address=ipaddress.ip_address(parsed.hostname)
        assert address.version==4 and address.is_private and not address.is_unspecified
        assert origin=='http://'+str(address)+(':'+str(parsed.port) if parsed.port else '')
    build_id=reg['build_id'] if lan_origin else IDS['android']
    WORK.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    assert not work.exists(); work.mkdir()
    assert sha(apk.read_bytes()) == reg['apk_sha256']
    prepared = PREP/'abyss-ex-android.swf'
    assert sha(prepared.read_bytes()) == read(PREP/'preparation.json')['android']['swf_sha256']
    version, header, tags = s.parts(prepared)
    before = [t for t in tags if t[0] == 82]
    originals = [t[4] for t in before]
    const = lan.constants(before)
    assert const['ID'] == reg['build_id'] and const['ORIGIN'] == reg['endpoint']
    keys = read(PAIR/'config/client-admission.keys.json')
    assert const['KEY'] == keys[reg['build_id']]
    changes = []; patches_by_abc={}
    for index, tag in enumerate(before):
        if lan_origin:
            replacements_={i:(value,value.replace(reg['endpoint'].encode(),origin.encode())
                             if reg['endpoint'].encode() in value else origin.split('://',1)[1].encode())
                           for i,value in enumerate(tag[3].strings) if b'175.178.160.158' in value}
            assert all(reg['endpoint'].encode() in old or old==reg['endpoint'].split('://',1)[1].encode()
                       for old,new in replacements_.values())
        else:
            values=replacements('android')
            replacements_={i:(value,values[value]) for i,value in enumerate(tag[3].strings) if value in values}
        raw=lan.patch_strings(tag[4],replacements_);indices=sorted(replacements_)
        patches_by_abc[index]=replacements_
        if indices:
            data = tag[2]+raw
            tag[1] = struct.pack('<HI', (82<<6)|63, len(data))+data
            changes.append(dict(abc=index, string_indices=indices))
    assert len(changes) == (3 if lan_origin else 2)
    if lan_origin:assert sum(len(r['string_indices']) for r in changes)==9
    raw = header+b''.join(t[1] for t in tags)
    swf = work/'worldflipper_android_release.swf'
    swf.write_bytes(b'CWS'+bytes([version])+struct.pack('<I', len(raw)+8)+zlib.compress(raw))
    final_tags = s.parts(swf)[2]; final_abcs = [t for t in final_tags if t[0] == 82]
    newconst = lan.constants(final_abcs)
    assert newconst == dict(ID=build_id, KEY=keys[build_id], ORIGIN=origin)
    proof_prefixes = [value for tag in final_abcs for value in tag[3].strings if value.startswith(b'SP-ADMISSION-1\n')]
    assert proof_prefixes == [('SP-ADMISSION-1\n'+build_id+'\n').encode()], 'Admission proof literal differs from actual build ID'
    forbidden=set() if lan_origin else set(replacements('android'))
    for index,(original, tag) in enumerate(zip(originals, final_abcs)):
        patches = {i:(new,old) for i,(old,new) in patches_by_abc[index].items()}
        assert lan.patch_strings(tag[4], patches) == original
        if lan_origin:assert not any(b'175.178.160.158' in value for value in tag[3].strings)
        else:assert not any(value in forbidden for value in tag[3].strings)
    if lan_origin:
        main=final_abcs[-1][3];code=s.m.asm.decode(main.bodies[92013][5])
        assert code[11].op==0x2c and main.s(code[11].args[0])==origin.split('://',1)[1]
    assert sum(len(t[3].bodies) for t in final_abcs) == 96635
    del keys, const, newconst, patches_by_abc
    with zipfile.ZipFile(apk) as source: (work/'original.dex').write_bytes(source.read('classes.dex'))
    uid = str(uuid.uuid4()); old_uuid = reg['uniqueappversionid']
    b.run([b.JAVA,'-jar',b.ALIB/'baksmali.jar','d','-o',work/'smali',work/'original.dex'],work,'decode-dex')
    originals = {p.relative_to(work/'smali'):p.read_text('utf8') for p in (work/'smali').rglob('*.smali')}
    assert len(originals) == 6
    changed = {}
    for name, text in originals.items():
        if old_uuid in text:
            assert name.as_posix() in {'cn/startpoint/StartupCache.smali','cn/startpoint/BuildIdentity.smali'}
            changed[name.as_posix()] = text.count(old_uuid)
            (work/'smali'/name).write_text(text.replace(old_uuid,uid),'utf8')
    assert len(changed) == 2 and sum(changed.values()) == 2
    b.run([b.JAVA,'-jar',b.ALIB/'smali.jar','a','-a','21','-o',work/'classes.dex',work/'smali'],work,'encode-dex')
    b.run([b.JAVA,'-jar',b.ALIB/'baksmali.jar','d','-o',work/'readback',work/'classes.dex'],work,'readback-dex')
    assert {p.relative_to(work/'readback') for p in (work/'readback').rglob('*.smali')} == set(originals)
    for name, text in originals.items():
        assert lan.native.canonical((work/'readback'/name).read_text('utf8').replace(uid,old_uuid)) == lan.native.canonical(text)
    payloads = {lan.SWF_MEMBER:swf.read_bytes(), 'classes.dex':(work/'classes.dex').read_bytes()}
    with zipfile.ZipFile(apk) as source, zipfile.ZipFile(work/'unsigned.apk','w') as dest:
        manifest = source.read('AndroidManifest.xml')
        assert manifest.count(old_uuid.encode('utf-16le')) == 1
        payloads['AndroidManifest.xml'] = manifest.replace(old_uuid.encode('utf-16le'),uid.encode('utf-16le'))
        for item in source.infolist():
            if item.filename not in lan.SIGNATURES: dest.writestr(item,payloads.get(item.filename,source.read(item)))
    align = Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    b.run([align,'-p','4',work/'unsigned.apk',work/'aligned.apk'],work,'align')
    result = OUT/('StarPoint-CN-1.8.1-abyss-ex-20260917-lan.apk' if lan_origin else 'StarPoint-CN-1.8.1-abyss-ex-20260917.apk')
    assert not result.exists()
    b.run(['powershell','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1',
           '-InputApk',work/'aligned.apk','-OutputApk',result,'-ApkSigner',b.ALIB/'apksigner.jar','-Java',b.JAVA],work,'sign')
    sig = b.run([b.JAVA,'-jar',b.ALIB/'apksigner.jar','verify','--verbose','--print-certs',result],work,'verify-signature')
    assert b.CERT in sig.lower()
    assert all('Verified using '+x+': true' in sig for x in ['v1 scheme (JAR signing)','v2 scheme (APK Signature Scheme v2)'])
    b.run([align,'-c','-p','4',result],work,'verify-align')
    with zipfile.ZipFile(apk) as left, zipfile.ZipFile(result) as right:
        assert right.testzip() is None and len(right.namelist()) == len(set(right.namelist()))
        assert set(left.namelist())-lan.SIGNATURES == set(right.namelist())-lan.SIGNATURES
        for name in set(right.namelist())-lan.SIGNATURES: assert right.read(name) == payloads.get(name,left.read(name)),name
        manifest = right.read('AndroidManifest.xml')
        assert manifest.count(uid.encode('utf-16le')) == 1 and old_uuid.encode('utf-16le') not in manifest
        members = len(right.namelist())
    report = dict(status='offline_verified',apk=str(result),sha256=sha(result.read_bytes()),size_bytes=result.stat().st_size,
         build_id=build_id, previous_build_id=reg['build_id'], origin=origin, input=reg,
         variant='lan' if lan_origin else 'public', admission_pair_reused=bool(lan_origin),
         swf_sha256=sha(swf.read_bytes()), dex_sha256=sha(payloads['classes.dex']), uniqueappversionid=uid,
         package_name=reg['package_name'],version_name=reg['version_name'],version_code=reg['version_code'],
         admission_changes=changes, method_bodies_checked=96635, ex_methods=read(PREP/'preparation.json')['android']['methods'],
         signer_sha256=b.CERT, v1_v2=True, zipalign=True, native_changes_only_uuid=changed,
         members_read_back=members,device_tested=False,registry_promoted=False)
    dump(OUT/('android-lan-build-report.json' if lan_origin else 'android-build-report.json'),report)
    if lan_origin:(OUT/'SHA256.txt').write_text(report['sha256']+'  '+result.name+'\n','utf8')
    print(json.dumps({k:report[k] for k in ('apk','sha256','build_id','uniqueappversionid')}))

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lan-origin')
    main(parser.parse_args().lan_origin)
