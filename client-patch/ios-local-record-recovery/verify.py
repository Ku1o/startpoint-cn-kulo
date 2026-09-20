"""Independent artifact, pointer, metadata, instruction and signing checks."""
import copy,hashlib,json,struct,sys,zipfile,zlib
from pathlib import Path
from prepare import WORK,HERE,OLD_COUNT,INFO_OFFSET,abcfmt,view,freeze,sha,dump,p,s
import build_native as link
from macho_signing_layout import assert_signable_layout,linkedit_ranges
from test_signing_layout import replace_signature_tail
from public_endpoint import require_public_endpoint
from hud_state_layout import slot_offsets

def u64(d,at):return struct.unpack_from('<Q',d,at)[0]

def main():
    out=WORK/'output';report=json.loads((out/'build-report.json').read_text());port=json.loads((WORK/'port.json').read_text());reg=report['source_ipa']
    assert report['original_methods']==OLD_COUNT and report['total_methods']==OLD_COUNT+4
    assert not (WORK/'compile.log').read_text().strip(),'compiler warning or error'
    with zipfile.ZipFile(reg['ipa']) as before,zipfile.ZipFile(report['ipa']) as after:
        assert before.namelist()==after.namelist() and before.comment==after.comment
        changed=[n for n in before.namelist() if before.read(n)!=after.read(n)]
        assert set(changed)=={reg['native_member'],reg['swf_member']}
        assert after.testzip() is None
        old=before.read(reg['native_member']);new=after.read(reg['native_member']);oldswf=before.read(reg['swf_member']);newswf=after.read(reg['swf_member'])
        members=len(after.namelist())
    assert sha(Path(report['ipa']).read_bytes())==report['ipa_sha256'];assert sha(old)==reg['native_sha256'];assert sha(new)==report['native_sha256']
    assert new==(out/'worldflipper').read_bytes() and sha(newswf)==report['swf_sha256']
    origin=require_public_endpoint(new);assert origin=='http://175.178.160.158'
    baseline_segs=link.segments(old);segs=link.segments(new)
    assert [s['name'] for s in segs]==[s['name'] for s in baseline_segs[:-1]]+['__CNRECIO','__LINKEDIT']
    for seg in segs[1:]:
        assert seg['vm']%0x4000==seg['off']%0x4000==0 and seg['vs']>=seg['fs'] and seg['off']+seg['fs']<=len(new)
    for a,b in zip(segs[1:],segs[2:]):assert a['vm']+a['vs']<=b['vm']
    rx,rw=segs[-2],segs[15]
    extension=report['data_extension'];data_base=baseline_segs[15]['vs']
    assert rw['name']=='__CNADTAB' and extension['base_offset']==data_base
    assert rw['vm']==baseline_segs[15]['vm'] and rw['off']==baseline_segs[15]['off']
    assert rw['vs']==rw['fs']==data_base+extension['size']
    assert extension['off']==rw['off']+data_base and extension['vm']==rw['vm']+data_base
    assert rw['off']+rw['fs']==rx['off'] and rw['vm']+rw['vs']==rx['vm']
    for n in ('__LENS','__ABYAUTO','__HUDSTATE','__CNCACHE','__CNRECORD','__CNSHOP','__CNADMIT'):
        seg=next(x for x in baseline_segs if x['name']==n);assert old[seg['off']:seg['off']+seg['fs']]==new[seg['off']:seg['off']+seg['fs']],n
    full=(WORK/port['full_abc_file']).read_bytes();assert sha(full)==port['full_abc_sha256'];digest=hashlib.sha1(full).digest()
    assert new[INFO_OFFSET:INFO_OFFSET+20]==digest
    plain=lambda b:b[:8]+zlib.decompress(b[8:]) if b[:3]==b'CWS' else b
    oswf,nswf=plain(oldswf),plain(newswf);oldhash=old[INFO_OFFSET:INFO_OFFSET+20]
    assert oswf.count(b'\0'*4+oldhash)==1 and oswf.replace(b'\0'*4+oldhash,b'\0'*4+digest)==nswf
    def runtime(d):
        va,size=u64(d,INFO_OFFSET+24),u64(d,INFO_OFFSET+32);at=link.file_offset(d,va,size)
        return abcfmt.ABC(d[at:at+size])
    oa,na=runtime(old),runtime(new);fa=abcfmt.ABC(full)
    for field in ('methods','metadata','instances','classes','scripts','ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        rows=getattr(oa,field);assert freeze(rows)==freeze(getattr(na,field)[:len(rows)]),field
    assert slot_offsets(oa)==slot_offsets(na)
    assert [na.mn_name(i[0]) for i in na.instances[len(oa.instances):]]==port['new_classes']
    ov,nv,fv=view(oa),view(na),view(fa)
    expected={31752,31756};assert {r['method_id'] for r in port['methods']}==expected
    # All existing function signatures and activation fields remain unchanged.
    ob={b[0]:b for b in oa.bodies};nb={b[0]:b for b in na.bodies}
    for mid,b in ob.items():
        if mid not in expected:assert freeze(b)==freeze(nb[mid]),mid
        else:assert p.activation_traits(ov,b)==p.activation_traits(nv,nb[mid]),mid
    # The same record helper was exercised by the prior Android filesystem
    # harness. Compare every helper method with the fixed public APK.
    donors=[view(t[3]) for t in s.parts(WORK/'android-record-reference.swf')[2]
        if t[0]==82 and any(t[3].mn_name(i[0])=='cn.storage::LocalRecordIO' for i in t[3].instances)]
    assert len(donors)==1
    matched=0
    for dv in donors:
        for label,indices in dv.by_label.items():
            assert label in fv.by_label,label
            assert [dv.normalized(i) for i in indices]==[fv.normalized(i) for i in fv.by_label[label]],label
            matched+=len(indices)
    assert matched==4,matched
    # Cross-check both account methods against the tested Android recovery
    # behavior. The complete current IPA remains the native baseline.
    from prepare import ANDROID,ANDROID_SHA
    reference=ANDROID
    assert sha(reference.read_bytes())==ANDROID_SHA
    with zipfile.ZipFile(reference) as z:reference_swf=z.read('assets/worldflipper_android_release.swf')
    assert reference_swf==(WORK/'android-record-reference.swf').read_bytes()
    network=[view(t[3]) for t in s.parts(WORK/'android-record-reference.swf')[2] if t[0]==82]
    for record in port['methods']:
        label=record['label'];dv,=[v for v in network if label in v.by_label]
        assert dv.normalized(dv.by_label[label][0])==fv.normalized(fv.by_label[label][0]),label
    # Private values are read for comparison, never written to a public report.
    from prepare import PRIVATE,BUILD_ID,ORIGIN
    pair=json.loads(PRIVATE.read_text('utf-8-sig'))
    ci,=[i for i,row in enumerate(na.instances) if na.mn_name(row[0])=='cn.admission::BuildConfig']
    config={na.mn_name(t.name):na.s(t.data[3]) for t in na.classes[ci][1] if t.data[0]=='slot'}
    assert config=={'ID':BUILD_ID,'KEY':pair[BUILD_ID],'ORIGIN':ORIGIN}
    assert config=={na.mn_name(t.name):na.s(t.data[3]) for t in oa.classes[ci][1] if t.data[0]=='slot'}
    helper_text=[dv.a.s(i) for dv in donors for i in range(len(dv.a.strings))]
    assert not any('cn.loading' in x or 'cn.diagnostics' in x or 'cn.probe' in x or ':8001' in x for x in helper_text)
    # iOS uses its existing device-store/extension route, not Android's
    # per-file device writer. Its method bytes and function pointers stay old.
    assert not any('DeviceLocalStore' in r['label'] for r in port['methods'])
    for name,proof in report['runtime_helper_proofs'].items():
        from map_runtime import derive
        assert derive(Path(proof['object']),name,old)==proof
    # Recover the compiler's actual function bytes independently of the link
    # report. Outside relocation words every emitted instruction must match.
    compile_report=json.loads((WORK/'compile-report.json').read_text())
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
    oldrebases=link.read_rebase(old)['entries'];newrebases=link.read_rebase(new)['entries'];assert newrebases[:len(oldrebases)]==oldrebases
    newset={(seg,at) for seg,at,typ in newrebases[len(oldrebases):] if typ==1}
    expected_rebases={(15,data_base+i*8) for i in range(count) if u64(new,newtable+i*8)}
    oldact=u64(old,INFO_OFFSET+88)
    for seg,at,typ in oldrebases:
        va=baseline_segs[seg]['vm']+at
        if oldact<=va<oldact+OLD_COUNT*16:expected_rebases.add((15,data_base+report['activation_position']+va-oldact))
    assert newset==expected_rebases and len(newset)==report['new_rebases']
    assert not newset.intersection((si,off) for si,off,typ in oldrebases)
    assert all(si<=15 for si,off,typ in newrebases)
    assert all(off+8<=segs[si]['fs'] for si,off,typ in newrebases)
    # Reconstruct the original prefix, permitting only derived pointers/hooks.
    ranges=[(0,32+struct.unpack_from('<I',new,20)[0]),(INFO_OFFSET,INFO_OFFSET+20),(INFO_OFFSET+24,INFO_OFFSET+40),(INFO_OFFSET+48,INFO_OFFSET+72),(INFO_OFFSET+88,INFO_OFFSET+96)]
    expected_entries={(mid,u64(old,oldtable+mid*8)) for mid in expected}
    expected_entries|={(mid,u64(old,0x62c0780+mid*8)) for mid in expected if mid<101071}
    assert {(r['method'],r['previous']) for r in report['hooks']}==expected_entries
    assert len(report['hooks'])==len(expected_entries)
    ranges += [(r['offset'],r['offset']+4) for r in report['hooks']]+[(at,at+8) for at in sites]
    prefix=bytearray(new[:baseline_segs[-1]['off']])
    for a,b in ranges:prefix[a:b]=old[a:b]
    assert prefix==old[:baseline_segs[-1]['off']]
    signing=assert_signable_layout(new)
    for size in (0x80000,0x200000,0x400000):
        replacement=replace_signature_tail(new,size,use_ldid=True);assert_signable_layout(replacement)
        assert link.read_rebase(replacement)['entries']==newrebases
        for r in linkedit_ranges(new):assert new[r['offset']:r['offset']+r['size']]==replacement[r['offset']:r['offset']+r['size']]
    result=dict(status='offline_verified_unsigned_candidate',ipa=report['ipa'],ipa_sha256=report['ipa_sha256'],
        zip_members=members,changed_zip_members=changed,existing_methods_preserved=OLD_COUNT-len(expected),
        old_class_and_activation_layouts_preserved=True,patched_existing_methods=sorted(expected),new_helper_methods=matched,
        native_functions_checked=len(native_functions_checked),native_relocations_checked=len(report['relocations']),long_branch_veneers_checked=len(used_veneers),new_rebases=len(newset),ldid_signature_models_passed=3,
        public_origin=origin,signing_layout=signing,ios_carousel_unchanged=True,save_schema_changed=False,
        device_tested=False,server_endpoint_required=False,old_startup_cache_preserved=True,
        account_reference_sha256=port['android_reference']['sha256'],build_id=port['build_id'],platform=port['platform'],
        ios_device_store_unchanged=True,record_encoding_unchanged=True,admission_id_key_and_behavior_unchanged=True,
        android_performance_not_imported=True)
    dump(out/'verification-report.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
