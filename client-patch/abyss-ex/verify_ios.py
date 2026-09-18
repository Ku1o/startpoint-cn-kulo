"""Independent EX IPA layout, ABI, package, native and admission verification."""
from release_common import *
import struct, zipfile, zlib, plistlib
sys.modules['prepare']=p
import build_native as link
from macho_signing_layout import assert_signable_layout,linkedit_ranges
from test_signing_layout import replace_signature_tail,BROKEN_IPA,FIRST_FIX_IPA
from public_endpoint import require_public_endpoint
from hud_state_layout import slot_offsets

def u64(d,at):return struct.unpack_from('<Q',d,at)[0]

def main():
    report=read(OUT/'ios-build-report.json');port=read(WORK/'port.json');reg=report['source_ipa']
    assert sha(Path(report['ipa']).read_bytes())==report['ipa_sha256']
    assert report['total_methods']==report['original_methods']==OLD_COUNT
    assert not (WORK/'compile-final.log').read_text('utf8').strip()
    with zipfile.ZipFile(reg['ipa']) as before,zipfile.ZipFile(report['ipa']) as after:
        assert before.namelist()==after.namelist() and before.comment==after.comment
        assert len(after.namelist())==len(set(after.namelist())) and after.testzip() is None
        changed=[n for n in before.namelist() if before.read(n)!=after.read(n)]
        assert set(changed)=={reg['native_member'],reg['swf_member']}
        old=before.read(reg['native_member']);new=after.read(reg['native_member'])
        oldswf=before.read(reg['swf_member']);newswf=after.read(reg['swf_member'])
        plist=plistlib.loads(after.read('Payload/worldflipper.app/Info.plist'))
        assert plist['CFBundleIdentifier']==reg['bundle_id'] and plist['CFBundleVersion']==reg['build']
        assert plist['CFBundleShortVersionString']==reg['version']
        members=len(after.namelist())
    assert sha(old)==reg['native_sha256'] and sha(new)==report['native_sha256']
    assert new==(OUT/'ios-r2/worldflipper').read_bytes() and sha(newswf)==report['swf_sha256']
    assert require_public_endpoint(new)=='http://175.178.160.158'
    oldsegments=link.segments(old);segs=link.segments(new);rx=report['executable_extension']
    assert [s['name'] for s in segs]==[s['name'] for s in oldsegments]
    assert segs[:-2]==oldsegments[:-2]
    for seg in segs[1:]:
        assert seg['vm']%0x4000==seg['off']%0x4000==0 and seg['vs']>=seg['fs'] and seg['off']+seg['fs']<=len(new)
    for a,b in zip(segs[1:],segs[2:]): assert a['vm']+a['vs']<=b['vm']
    assert segs[-2]['vm']==oldsegments[-2]['vm'] and segs[-2]['off']==oldsegments[-2]['off']
    assert segs[-2]['vs']-oldsegments[-2]['vs']==segs[-2]['fs']-oldsegments[-2]['fs']==rx['size']
    assert segs[-1]['vm']-oldsegments[-1]['vm']==segs[-1]['off']-oldsegments[-1]['off']==rx['size']
    assert new[segs[-1]['off']:]==old[oldsegments[-1]['off']:]
    full=(WORK/port['full_abc_file']).read_bytes();assert sha(full)==port['full_abc_sha256']
    digest=hashlib.sha1(full).digest();assert new[INFO_OFFSET:INFO_OFFSET+20]==digest
    plain=lambda b:b[:8]+zlib.decompress(b[8:]) if b[:3]==b'CWS' else b
    oswf,nswf=plain(oldswf),plain(newswf);oldhash=old[INFO_OFFSET:INFO_OFFSET+20]
    assert oswf.count(b'\0'*4+oldhash)==1 and oswf.replace(b'\0'*4+oldhash,b'\0'*4+digest)==nswf
    def runtime(data):
        va,size=u64(data,INFO_OFFSET+24),u64(data,INFO_OFFSET+32);at=link.file_offset(data,va,size)
        return abcfmt.ABC(data[at:at+size])
    oa,na=runtime(old),runtime(new);fa=abcfmt.ABC(full)
    assert len(na.methods)==len(oa.methods)==OLD_COUNT
    for field in ('methods','metadata','instances','classes','scripts','ints','uints','doubles','namespaces','ns_sets','multinames'):
        rows=getattr(oa,field);assert freeze(rows)==freeze(getattr(na,field)[:len(rows)]),field
    replacements_=replacements('ios')
    for index,value in enumerate(oa.strings): assert na.strings[index]==replacements_.get(value,value),index
    assert not any(value in replacements_ for value in na.strings)
    keys=read(PAIR/'config/client-admission.keys.json')
    assert lan.constants([[82,None,None,na]])==dict(ID=IDS['ios'],KEY=keys[IDS['ios']],ORIGIN='http://175.178.160.158')
    del replacements_,keys
    assert slot_offsets(oa)==slot_offsets(na)
    expected={101077,101194,26363};assert {r['method_id'] for r in port['methods']}==expected
    nb={body[0]:body for body in na.bodies};ov,nv=view(oa),view(na)
    for body in oa.bodies:
        if body[0] not in expected:assert freeze(body)==freeze(nb[body[0]]),body[0]
        else: assert p.activation_traits(ov,body)==p.activation_traits(nv,nb[body[0]])
    # Compiler-only lexical initializers must not replace their native functions.
    context={r['method_id'] for r in port['compiler_only_lifecycles']}
    assert not context.intersection(expected)
    # Recover the compiler's actual function bytes independently of the link
    # report. Outside relocation words every emitted instruction must match.
    compile_report=json.loads((WORK/'compile-final-report.json').read_text())
    wanted=expected|set(range(OLD_COUNT,report['total_methods']));native_functions_checked=set()
    for item in compile_report['objects']:
        objpath=Path(compile_report['directory'])/item['name'];assert sha(objpath.read_bytes())==item['sha256']
        obj=link.lief.parse(str(objpath));symbols=list(obj.symbols)
        ids=[mid for mid in wanted if any(f':{mid}:' in link.aot.text(t.name) and t.numberof_sections for t in symbols)]
        if not ids:continue
        sec,syms,functions=link.aot.parse_object_functions(obj,ids)
        for function in functions:
            placed,=[r for r in report['functions'] if r['method']==function.method_id]
            assert function.size==placed['size']
            original_code=bytes(sec.content)[function.source_start-sec.virtual_address:function.source_start-sec.virtual_address+function.size]
            emitted=new[placed['file_offset']:placed['file_offset']+placed['size']]
            assert sha(emitted)==placed['sha256']
            relocations=link.aot.parse_relocations(objpath,sec,syms,function)
            relocated={r['offset'] for r in relocations if r['type']!=10}
            for off in range(0,function.size,4):
                if off not in relocated:assert original_code[off:off+4]==emitted[off:off+4],(function.method_id,off)
            native_functions_checked.add(function.method_id)
    assert native_functions_checked==wanted
    count=report['total_methods'];oldtable=link.file_offset(old,u64(old,INFO_OFFSET+48),OLD_COUNT*8);newtable=link.file_offset(new,u64(new,INFO_OFFSET+48),count*8)
    changed_ids={mid for mid in range(OLD_COUNT) if u64(old,oldtable+mid*8)!=u64(new,newtable+mid*8)}
    assert changed_ids==expected
    sites={oldtable+mid*8 for mid in expected}|{0x62c0780+mid*8 for mid in expected if mid<101071};assert set(report['table_sites'])==sites
    for mid in range(OLD_COUNT):assert u64(new,oldtable+mid*8)==u64(new,newtable+mid*8)
    for mid in expected:
        function=next(r for r in report['functions'] if r['method']==mid)
        target=function['address']
        assert u64(new,newtable+mid*8)==target
    for mid in range(OLD_COUNT,count):assert u64(new,newtable+mid*8)==next(r['address'] for r in report['functions'] if r['method']==mid)
    for info,width in ((64,4),(88,16)):
        before=link.file_offset(old,u64(old,INFO_OFFSET+info),OLD_COUNT*width);after=link.file_offset(new,u64(new,INFO_OFFSET+info),count*width)
        assert old[before:before+OLD_COUNT*width]==new[after:after+OLD_COUNT*width]
    def branch(pc):
        word=struct.unpack_from('<I',new,link.file_offset(new,pc,4))[0];assert word&0x7c000000==0x14000000
        imm=word&0x3ffffff
        if imm&(1<<25):imm-=1<<26
        return pc+4*imm
    for r in report['hooks']:assert branch(r['previous'])==r['target']
    # Independent Capstone decoding checks the emitted IP0-only veneer rather
    # than using the encoder to assert its own output.
    import capstone
    md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN);md.detail=True
    veneer_targets={}
    for v in report['veneers']:
        at=link.file_offset(new,v['address'],16);assert at==v['file_offset']
        assert rx['off']<=at and at+16<=rx['off']+report['abc_position']
        data=new[at:at+16];assert sha(data)==v['sha256']
        instructions=list(md.disasm(data,v['address']));assert len(instructions)==4
        assert [i.mnemonic for i in instructions]==['adrp','add','br','nop']
        assert instructions[0].reg_name(instructions[0].operands[0].reg)=='x16'
        assert [instructions[1].reg_name(o.reg) for o in instructions[1].operands[:2]]==['x16','x16']
        assert instructions[2].op_str=='x16'
        assert instructions[0].operands[1].imm+instructions[1].operands[2].imm==v['target']
        assert v['address'] not in veneer_targets
        veneer_targets[v['address']]=v['target']
    used_veneers=set()
    for r in report['relocations']:
        pc,target,typ=r['pc'],r['target'],r['type'];word=struct.unpack_from('<I',new,link.file_offset(new,pc,4))[0]
        if typ==2:
            destination=branch(pc);assert destination==r['branch_target']
            if destination!=target:
                assert veneer_targets[destination]==target
                used_veneers.add(destination)
        elif typ in (3,5):
            assert word&0x9f000000==0x90000000
            imm=((word>>29)&3)|(((word>>5)&0x7ffff)<<2)
            if imm&(1<<20):imm-=1<<21
            assert (pc&~0xfff)+(imm<<12)==target&~0xfff
        else:
            value=(word>>10)&0xfff
            if word&0x7f000000==0x11000000:assert value==target&0xfff
            else:assert word&0x3b000000==0x39000000 and value<<(word>>30)==target&0xfff
    assert used_veneers==set(veneer_targets)

    assert link.read_rebase(old)['entries']==link.read_rebase(new)['entries']
    for si,offset,typ in link.read_rebase(old)['entries']:
        assert si<=15 and offset+8<=segs[si]['fs']
        if typ==1:
            pointer=u64(old,oldsegments[si]['off']+offset)
            assert not oldsegments[-1]['vm']<=pointer<oldsegments[-1]['vm']+oldsegments[-1]['vs']
    equipment=port['equipment'];gate_at=equipment['offset'];gate_end=gate_at+equipment['new_size']
    assert equipment['old_size']==equipment['new_size']==548
    assert sha(old[gate_at:gate_end])==equipment['source_sha256']
    assert sha(new[gate_at:gate_end])==equipment['sha256']
    gate_changes=[i for i in range(gate_at,gate_end,4) if old[i:i+4]!=new[i:i+4]]
    assert gate_changes==list(range(gate_changes[0],gate_changes[0]+16,4))
    instructions=list(md.disasm(new[gate_changes[0]:gate_changes[0]+16],0x100000000+gate_changes[0]))
    assert [i.mnemonic for i in instructions]==['sub','sub','cmp','b.ls']
    assert instructions[0].op_str=='w9, w0, #0xaa, lsl #12' and instructions[1].op_str=='w9, w9, #0xec3'
    assert instructions[2].op_str=='w9, #1'
    ranges=[(0,32+struct.unpack_from('<I',new,20)[0]),(INFO_OFFSET,INFO_OFFSET+20),
            (INFO_OFFSET+24,INFO_OFFSET+40),(gate_changes[0],gate_changes[-1]+4)]
    expected_entries={(mid,u64(old,oldtable+mid*8)) for mid in expected}
    expected_entries|={(mid,u64(old,0x62c0780+mid*8)) for mid in expected if mid<101071}
    assert {(r['method'],r['previous']) for r in report['hooks']}==expected_entries
    ranges += [(r['offset'],r['offset']+4) for r in report['hooks']]+[(at,at+8) for at in sites]
    prefix=bytearray(new[:oldsegments[-1]['off']])
    for start,end in ranges: prefix[start:end]=old[start:end]
    assert prefix==old[:oldsegments[-1]['off']]
    signing=assert_signable_layout(new)
    for size in (0x80000,0x200000,0x400000):
        replacement=replace_signature_tail(new,size,use_ldid=True);assert_signable_layout(replacement)
        assert link.read_rebase(replacement)['entries']==link.read_rebase(new)['entries']
        for row in linkedit_ranges(new):
            at,end=row['offset'],row['offset']+row['size'];assert new[at:end]==replacement[at:end]
    rejected=0
    for path,expected_sha in ((BROKEN_IPA,'54a305686a8cf0ae9ad6f1ea3158d34009a7eb0a7221e807de334570d56ebe2a'),
                              (FIRST_FIX_IPA,'77757cb88ed43593d1df3ab48b7d4fc0601476362163a013c20159f3e3832499')):
        # Negative artifacts are only layout evidence, never build inputs.
        assert sha(path.read_bytes())==expected_sha
        with zipfile.ZipFile(path) as z: negative=z.read(reg['native_member'])
        try:assert_signable_layout(negative)
        except AssertionError:rejected+=1
        else:raise AssertionError('Invalid legacy layout accepted')
    result=dict(status='offline_verified_unsigned_candidate',ipa=report['ipa'],ipa_sha256=report['ipa_sha256'],
         zip_members=members,changed_members=changed,total_methods=OLD_COUNT,patched_methods=sorted(expected),
         native_relocations_checked=len(report['relocations']),veneers_checked=len(used_veneers),
         preserved_other_method_pointers=OLD_COUNT-len(expected),same_size_equipment_gate=True,
         unchanged_activation_layout=True,unchanged_rebases=True,ldid_models=3,rejected_legacy_layouts=rejected,
         cumulative_native_bytes_preserved=True,build_id=IDS['ios'],new_id_and_pair_verified=True,
         device_tested=False,registry_promoted=False)
    dump(OUT/'ios-verification-report.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
