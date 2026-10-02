"""Convert the accepted LAN APK to public, rotating its actual admission material.

All ABC bytes outside the selected string constants are proven reversible.
The existing packager verifies persistent signing, UUID/Dex sites and ZIP members.
"""
import json, struct, zipfile, zlib
from urllib.parse import urlsplit
from common import *

def main():
    assert sha(APK.read_bytes()) == APK_SHA
    work = WORK/'android'; work.mkdir(parents=True, exist_ok=True)
    out = OUT/'android'; out.mkdir(parents=True, exist_ok=True)
    assert not (out/'package-report.json').exists(), 'Use the completed batch, do not rebuild silently.'
    legacy = load('author_public_packager', HERE.parent/'author-content-1043/package_android.py')
    lan = load('author_public_pool', HERE.parent/'r10-public-release/build_lan.py')
    with zipfile.ZipFile(APK) as archive:
        original = archive.read(legacy.SWF_MEMBER)
    assert sha(original) == ANDROID_SWF_SHA
    source = work/'accepted-lan.swf'; source.write_bytes(original)
    version, header, tags = legacy.s.parts(source)
    _, keys = pair()
    values = lan.constants([t for t in tags if t[0] == 82])
    assert values['ID'] == OLD_IDS['android'] and values['KEY'] == keys[OLD_IDS['android']]
    # The pinned input hash identifies the accepted LAN payload.
    source_origin = urlsplit(values['ORIGIN'])
    assert source_origin.scheme == 'http' and source_origin.hostname and source_origin.port == 8001
    assert source_origin.path in ('', '/') and not source_origin.query and not source_origin.fragment
    assert source_origin.username is None and source_origin.password is None
    replacements = {OLD_IDS['android'].encode(): IDS['android'].encode(),
                    keys[OLD_IDS['android']].encode(): keys[IDS['android']].encode(),
                    ('SP-ADMISSION-1\n'+OLD_IDS['android']+'\n').encode():
                    ('SP-ADMISSION-1\n'+IDS['android']+'\n').encode()}
    counts = {k:0 for k in replacements}; records = []
    for ti, tag in enumerate(tags):
        if tag[0] != 82: continue
        patches = {i:(s,replacements[s]) for i,s in enumerate(tag[3].strings) if s in replacements}
        if not patches: continue
        patched = lan.patch_strings(tag[4], patches)
        assert lan.patch_strings(patched, {i:(b,a) for i,(a,b) in patches.items()}) == tag[4]
        for old, _ in patches.values(): counts[old] += 1
        data = tag[2]+patched
        tag[1] = struct.pack('<HI', (82<<6)|63, len(data))+data
        records.append({'tag':ti, 'pool_indexes':sorted(patches)})
    assert all(n > 0 for n in counts.values())
    assert counts[('SP-ADMISSION-1\n'+OLD_IDS['android']+'\n').encode()] == 1
    raw = header+b''.join(t[1] for t in tags)
    candidate = work/'admission-lan.swf'
    candidate.write_bytes(b'CWS'+bytes([version])+struct.pack('<I',len(raw)+8)+zlib.compress(raw))
    for old in replacements: assert old not in raw
    legacy.BASE_APK, legacy.BASE_SHA, legacy.BASE_SWF = APK, APK_SHA, ANDROID_SWF_SHA
    legacy.OLD_UUID, legacy.OLD_HOST, legacy.LAN_HOST = ANDROID_UUID, source_origin.hostname, '175.178.160.158'
    legacy.ADMISSION_ID = IDS['android']
    legacy.main(candidate, work, out, expected_swf=sha(candidate.read_bytes()), label='author-unified-damage-public')
    report = json.loads((out/'package-report.json').read_text('utf-8'))
    intermediate = Path(report['apk'])
    final = intermediate.with_name(intermediate.name.replace('-public-lan-', '-public-'))
    assert not final.exists(); intermediate.rename(final)
    old_sidecar = out/(intermediate.name+'.sha256')
    old_sidecar.unlink()
    with zipfile.ZipFile(final) as archive:
        check = work/'public-readback.swf'; check.write_bytes(archive.read(legacy.SWF_MEMBER))
    _, _, checked = legacy.s.parts(check)
    actual = lan.constants([t for t in checked if t[0] == 82])
    assert actual == {'ID':IDS['android'], 'KEY':keys[IDS['android']], 'ORIGIN':'http://175.178.160.158:8001'}
    assert sum(len(t[3].bodies) for t in checked if t[0]==82) == sum(len(t[3].bodies) for t in tags if t[0]==82)
    report.update(apk=str(final), admission_pair_unchanged=False, admission_pool_rewrites=records,
                  admission_pool_inverse_verified=True, previous_admission_id=OLD_IDS['android'],
                  all_gameplay_bodies_and_traits_preserved=True,
                  method_bodies_checked=sum(len(t[3].bodies) for t in checked if t[0]==82),
                  device_tested=False, status='offline_verified_public_candidate',
                  resource_version='1.4.117', accepted_lan_source=True)
    dump(out/'package-report.json', report)
    (out/(final.name+'.sha256')).write_text(report['apk_sha256']+'  '+final.name+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','apk','apk_sha256','swf_sha256','uniqueappversionid','admission_id')}))

if __name__ == '__main__':
    main()
