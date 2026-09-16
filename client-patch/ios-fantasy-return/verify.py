"""Independently verify IPA scope, linked instructions and TrollStore layout."""
from common import *
from macho_signing_layout import signature_range,ldid_code_limit,linkedit_ranges
import plistlib

def branch(word,pc):
    assert word&0xfc000000==0x94000000
    value=word&0x3ffffff
    if value&(1<<25):value-=1<<26
    return pc+value*4

def main():
    report=json.loads((OUT/'build-report.json').read_text('utf-8'));reg=registry()
    assert sha(Path(report['ipa']).read_bytes())==report['ipa_sha256']
    with zipfile.ZipFile(REPO/reg['ipa']) as before,zipfile.ZipFile(report['ipa']) as after:
        assert before.namelist()==after.namelist() and len(after.namelist())==len(set(after.namelist()))
        assert after.testzip() is None
        changed=[name for name in before.namelist() if before.read(name)!=after.read(name)]
        assert changed==[reg['native_member']]
        old=before.read(reg['native_member']);new=after.read(reg['native_member'])
        assert sha(old)==NATIVE_SHA and sha(new)==report['native_sha256']
        assert sha(after.read(reg['swf_member']))==reg['swf_sha256']
        plist=plistlib.loads(after.read('Payload/worldflipper.app/Info.plist'))
        assert plist['CFBundleIdentifier']==reg['bundle_id'] and plist['CFBundleVersion']==reg['build']
        count=len(after.namelist())
    h=report['helper'];segment=next(s for s in segments(old) if s['name']=='__CNCACHE')
    assert h['file_offset']==segment['off']+((segment['section_size']+15)&~15)
    assert h['address']==segment['vm']+h['file_offset']-segment['off']
    assert h['size']==468 and h['file_offset']+h['size']<=segment['off']+segment['fs']
    assert not any(old[h['file_offset']:h['file_offset']+h['size']])
    ranges=sorted([(segment['command']+112,segment['command']+120),(offset(old,HOOK),offset(old,HOOK)+4),
                   (h['file_offset'],h['file_offset']+h['size'])])
    assert ranges==[tuple(x) for x in report['allowed_ranges']]
    cursor=0
    for start,end in ranges:
        assert old[cursor:start]==new[cursor:start]
        cursor=end
    assert old[cursor:]==new[cursor:] and len(old)==len(new)
    assert branch(struct.unpack_from('<I',old,offset(old,HOOK))[0],HOOK)==ORIGINAL_TARGET
    assert branch(struct.unpack_from('<I',new,offset(new,HOOK))[0],HOOK)==h['address']
    # Re-read the compiler object while retaining its LIEF owner.
    objpath=Path(h['object']);assert sha(objpath.read_bytes())==h['object_sha256']
    obj=lief.parse(str(objpath));sec,syms,recs=aot.parse_object_functions(obj,[METHOD]);record,=recs
    raw=bytes(sec.content)[record.source_start-sec.virtual_address:record.source_end-sec.virtual_address]
    actual=new[h['file_offset']:h['file_offset']+h['size']];assert len(raw)==len(actual)
    relocs=aot.parse_relocations(objpath,sec,syms,record);assert len(relocs)==6
    helpers={k:int(v['address'],0) for k,v in json.loads((LEGACY/'runtime-helper-map.json').read_text())['symbols'].items()}
    restored=bytearray(actual)
    for row in relocs:
        idx=row['offset'];assert row['type']==2
        assert branch(struct.unpack_from('<I',actual,idx)[0],h['address']+idx)==helpers[row['symbol']]
        restored[idx:idx+4]=raw[idx:idx+4]
    assert bytes(restored)==raw and sha(actual)==h['sha256']
    signing=assert_signable_layout(new)
    for size in (0x80000,0x200000,0x400000):
        command,_,_=signature_range(new);limit=ldid_code_limit(new)
        replacement=bytearray(new[:limit]+struct.pack('>III',0xfade0cc0,size,0)+b'\xa5'*(size-12))
        struct.pack_into('<II',replacement,command+8,limit,size)
        link=segments(replacement)[-1];length=len(replacement)-link['off']
        struct.pack_into('<Q',replacement,link['command']+48,length)
        struct.pack_into('<Q',replacement,link['command']+32,(length+0x3fff)&~0x3fff)
        assert_signable_layout(replacement)
        for row in linkedit_ranges(new):
            start=row['offset'];end=start+row['size'];assert new[start:end]==replacement[start:end]
        assert actual==replacement[h['file_offset']:h['file_offset']+h['size']]
    result=dict(status='offline_structure_verified',ipa=report['ipa'],ipa_sha256=report['ipa_sha256'],
        zip_members=count,changed_members=changed,linked_relocations_checked=6,native_helper_bytes=h['size'],
        all_other_native_bytes_preserved=True,swf_and_runtime_abc_unchanged=True,
        all_101287_method_table_entries_unchanged=True,class_and_activation_abi_unchanged=True,
        admission_build_id=BUILD_ID,admission_id_key_and_protocol_unchanged=True,
        public_endpoint_unchanged=True,signature_layout=signing,ldid_replacement_models=3,
        save_schema_changed=False,device_tested=False)
    dump(OUT/'verification-report.json',result)
    print('Verified',count,'IPA members; one native member changed; six relocations; three ldid models.')

if __name__=='__main__':main()
