"""Place a compiled navigation helper in existing RX padding and redirect one BL."""
from common import *
import copy

def main():
    assert not OUT.exists(),'Refusing to overwrite a deliverable.'
    reg=registry(); old=native(); assert_signable_layout(old)
    records=[]
    for path in (WORK/'compile').glob('navigation*.o'):
        obj=lief.parse(str(path))
        if not any(f':{METHOD}:' in aot.text(s.name) and s.numberof_sections for s in obj.symbols):continue
        sec,syms,rows=aot.parse_object_functions(obj,[METHOD])
        for record in rows:records.append((path,obj,sec,syms,record))
    assert len(records)==1
    path,obj,sec,syms,record=records[0]
    assert 100<record.size<8192
    raw=bytes(sec.content)[record.source_start-sec.virtual_address:record.source_end-sec.virtual_address]
    code=bytearray(raw)
    region=next(s for s in segments(old) if s['name']=='__CNCACHE')
    relative=(region['section_size']+15)&~15
    assert relative+len(code)<=region['fs'] and not any(old[region['off']+region['section_size']:region['off']+region['fs']])
    address=region['vm']+relative; at=region['off']+relative
    helpers={k:int(v['address'],0) for k,v in json.loads((LEGACY/'runtime-helper-map.json').read_text())['symbols'].items()}
    relocations=[]
    for row in aot.parse_relocations(path,sec,syms,record):
        assert row['type']==2 and row['symbol'] in helpers,('unexpected relocation',row)
        target=helpers[row['symbol']]
        aot.patch_branch26(code,row['offset'],address+row['offset'],target)
        relocations.append(dict(offset=row['offset'],symbol=row['symbol'],target=target))
    assert len(relocations)==6,'Expected the six compiler-emitted runtime calls.'
    # Confirm the hook is still the exact legacy call. Other return wrappers,
    # room-disband callbacks and global method entries remain untouched.
    hook_at=offset(old,HOOK); original=struct.unpack_from('<I',old,hook_at)[0]
    assert original&0xfc000000==0x94000000
    imm=original&0x3ffffff;imm=imm-(1<<26) if imm&(1<<25) else imm
    assert HOOK+(imm<<2)==ORIGINAL_TARGET
    result=bytearray(old);result[at:at+len(code)]=code
    aot.patch_branch26(result,hook_at,HOOK,address)
    size_at=region['command']+112
    struct.pack_into('<Q',result,size_at,relative+len(code))
    ranges=sorted([(size_at,size_at+8),(hook_at,hook_at+4),(at,at+len(code))])
    cursor=0
    for start,end in ranges:
        assert old[cursor:start]==result[cursor:start]
        cursor=end
    assert old[cursor:]==result[cursor:] and len(result)==len(old)
    assert_signable_layout(result)
    OUT.mkdir(parents=True)
    output=OUT/'StarPoint-iOS-1.8.4-fantasy-return-fix-20260916-unsigned.ipa'
    with zipfile.ZipFile(REPO/reg['ipa']) as src,zipfile.ZipFile(output,'w',allowZip64=True) as dest:
        for info in src.infolist():
            dest.writestr(copy.copy(info),result if info.filename==reg['native_member'] else src.read(info.filename))
        dest.comment=src.comment
    report=dict(status='unsigned_candidate_pending_verification',source_ipa=reg,ipa=str(output),
        ipa_sha256=sha(output.read_bytes()),native_sha256=sha(result),build_id=BUILD_ID,platform='ios',
        helper=dict(address=address,file_offset=at,size=len(code),sha256=sha(code),
                    compiler_method_id=METHOD,object=str(path),object_sha256=sha(path.read_bytes()),
                    object_symbol=record.symbol),
        hook=dict(address=HOOK,file_offset=hook_at,original_target=ORIGINAL_TARGET,target=address),
        section_size_field=size_at,allowed_ranges=ranges,relocations=relocations,
        runtime_abc_unchanged=True,swf_unchanged=True,method_tables_unchanged=True,
        class_layouts_unchanged=True,save_schema_changed=False,server_changes_required=False,
        device_tested=False,history=['Title','Home','EventTop','RushEventTop(700098)'])
    dump(OUT/'build-report.json',report)
    (OUT/'SHA256.txt').write_text(report['ipa_sha256']+'  '+output.name+'\n',encoding='utf-8')
    print('Built',output,'helper bytes',len(code),'relocations',len(relocations))

if __name__=='__main__':main()
