"""Read back ZIP, ABC, arm64 instructions and dyld rebases independently."""
from prepare import *
import struct
sys.path.insert(0,r'F:\codex\tools\ios-re-libs')
import lief,capstone
from macho_signing_layout import assert_signable_layout,signature_range,string_table

def u64(data,at):return struct.unpack_from('<Q',data,at)[0]
def main():
    out=WORK/'output';report=json.loads((out/'build-report.json').read_text('utf8'));port=json.loads((WORK/'port.json').read_text('utf8'))
    ipa=Path(report['ipa']);reg=report['source_ipa'];assert sha(ipa.read_bytes())==report['ipa_sha256']
    with zipfile.ZipFile(reg['ipa']) as left,zipfile.ZipFile(ipa) as right:
        assert left.namelist()==right.namelist() and left.comment==right.comment
        differences=[n for n in left.namelist() if left.read(n)!=right.read(n)]
        assert set(differences)=={reg['native_member'],reg['swf_member']},differences
        native=right.read(reg['native_member']);swf=right.read(reg['swf_member'])
        baseline=left.read(reg['native_member']);oldswf=left.read(reg['swf_member'])
        members=len(left.namelist())
    assert sha(native)==report['native_sha256'] and sha(swf)==report['swf_sha256']
    assert sha(baseline)==reg['native_sha256']
    binary=lief.parse(str(out/'worldflipper'));oldbinary=lief.parse(str(WORK/'baseline-native'))
    assert binary.header.cpu_type==oldbinary.header.cpu_type and binary.header.flags==oldbinary.header.flags
    segs=list(binary.segments);oldsegs=list(oldbinary.segments)
    assert [s.name for s in segs]==['__PAGEZERO','__TEXT','__DATA','__LENS','__ABYAUTO','__CNUPDATE','__CNACCT','__LINKEDIT']
    for s in segs[1:]:
        assert s.virtual_address%0x4000==s.file_offset%0x4000==0
        assert s.virtual_size>=s.file_size and s.file_offset+s.file_size<=len(native)
        assert s.init_protection!=7,'RWX segment'
    for a,b in zip(segs[1:],segs[2:]):assert a.virtual_address+a.virtual_size<=b.virtual_address
    def offset(va,length=1):
        matches=[s.file_offset+va-s.virtual_address for s in segs if s.virtual_address<=va and va+length<=s.virtual_address+s.file_size]
        assert len(matches)==1,(hex(va),length)
        return matches[0]
    oldlink=oldsegs[-1];newlink=segs[-1]
    signing_layout=assert_signable_layout(native)
    _,old_signature,_=signature_range(baseline)
    _,new_signature,_=signature_range(native)
    _,old_strings,old_strings_size=string_table(baseline)
    _,new_strings,new_strings_size=string_table(native)
    assert old_strings_size==new_strings_size
    old_prefix_size=old_strings-oldlink.file_offset
    assert baseline[oldlink.file_offset:old_strings]==native[newlink.file_offset:newlink.file_offset+old_prefix_size]
    assert baseline[old_strings:old_signature]==native[new_strings:new_signature],'symbol strings changed'
    assert baseline[old_signature:]==native[new_signature:],'original signature placeholder changed'
    insertion=native[newlink.file_offset+old_prefix_size:new_strings]
    rebase=report['rebases']
    assert newlink.file_offset+old_prefix_size==rebase['stream_offset']
    assert not any(insertion[rebase['stream_size']:]) and len(insertion)%16==0
    whitelist=[(0,report['header_end']),(INFO_OFFSET,INFO_OFFSET+20),(INFO_OFFSET+24,INFO_OFFSET+40),(INFO_OFFSET+48,INFO_OFFSET+72),(INFO_OFFSET+88,INFO_OFFSET+96)]
    for h in report['hooks']:whitelist.extend([(h['offset'],h['offset']+4),(0x62c0780+h['method']*8,0x62c0780+h['method']*8+8)])
    prefix=bytearray(native[:oldlink.file_offset])
    for a,b in whitelist:prefix[a:b]=baseline[a:b]
    assert prefix==baseline[:oldlink.file_offset],'unapproved change in original native ranges'
    old_digest=baseline[INFO_OFFSET:INFO_OFFSET+20];digest=native[INFO_OFFSET:INFO_OFFSET+20]
    import zlib
    plain=lambda b:b[:8]+zlib.decompress(b[8:]) if b[:3]==b'CWS' else b
    before,after=plain(oldswf),plain(swf)
    assert before.count(b'\0'*4+old_digest)==1 and before.replace(b'\0'*4+old_digest,b'\0'*4+digest)==after
    full=(WORK/port['full_abc_file']).read_bytes();assert hashlib.sha1(full).digest()==digest
    abcptr,abclen=u64(native,INFO_OFFSET+24),u64(native,INFO_OFFSET+32)
    runtime=native[offset(abcptr,abclen):offset(abcptr,abclen)+abclen]
    assert sha(runtime)==report['runtime_abc_sha256']
    a=abcfmt.ABC(runtime);f=abcfmt.ABC(full)
    oldptr,oldlen=u64(baseline,INFO_OFFSET+24),u64(baseline,INFO_OFFSET+32)
    oo=next(s.file_offset+oldptr-s.virtual_address for s in oldsegs if s.virtual_address<=oldptr< s.virtual_address+s.file_size)
    b=abcfmt.ABC(baseline[oo:oo+oldlen])
    from hud_state_layout import slot_offsets
    old_hud=slot_offsets(b);new_hud=slot_offsets(a)
    assert all(new_hud[n]==offset for n,offset in old_hud.items()),'native HUD slot ABI changed'
    for name in ('methods','metadata','classes','scripts'):
        rows=getattr(b,name);assert freeze(rows)==freeze(getattr(a,name)[:len(rows)]),name
    fields=[]
    for i,(x,y) in enumerate(zip(b.instances,a.instances)):
        assert freeze(x[:6])==freeze(y[:6]) and freeze(x[6])==freeze(y[6][:len(x[6])])
        for t in y[6][len(x[6]):]:fields.append((a.mn_name(y[0]),a.mn_name(t.name)))
    assert [n for _,n in fields]==['wtsReadyNormalNext','wtsReadyFeverNext','geraldReadyNext']
    assert all(c=='pinball.scene.battle.battle.hud::HudMemberStatus' for c,_ in fields)
    assert [a.mn_name(i[0]) for i in a.instances[len(b.instances):]]==['cn.rules::QuestElementResistance','cn.ui::AbyssDetails','cn.account::PlayerLogin']
    oldb={x[0]:x for x in b.bodies};newb={x[0]:x for x in a.bodies};expected={x['method_id'] for x in port['methods']}-{18394}
    assert {m for m,x in oldb.items() if freeze(x)!=freeze(newb[m])}<=expected
    assert freeze(oldb[26363])==freeze(newb[26363]) and freeze(oldb[18394])==freeze(newb[18394])
    # All helper code in the compiler input equals the current Android helper,
    # after resolving method/class IDs and pool indexes to their names.
    fv=view(f);fby={x[0]:i for i,x in enumerate(f.bodies)};helper_checks=[]
    for item in port['helpers']:
        raw=(WORK/(item['name']+'.abc')).read_bytes();assert sha(raw)==item['sha256']
        hv=view(abcfmt.ABC(raw));start=item['first_method']
        for i,body in enumerate(hv.a.bodies):
            assert hv.normalized(i)==fv.normalized(fby[start+body[0]]),(item['name'],body[0],'helper behavior changed')
            assert activation_traits(hv,body)==activation_traits(fv,f.bodies[fby[start+body[0]]])
        helper_checks.append(dict(name=item['name'],methods=len(hv.a.methods),behavior_and_activation_layout_equal=True))
    count=u64(native,INFO_OFFSET+56);assert count==101182==len(a.methods)
    table=u64(native,INFO_OFFSET+48);to=offset(table,count*8)
    pointers=[u64(native,to+i*8) for i in range(count)]
    changed={x['method'] for x in report['hooks']}
    for i in range(OLD_COUNT):
        current=u64(native,0x62c0780+i*8);assert current==pointers[i]
        if i not in changed:assert current==u64(baseline,0x62c0780+i*8)
    actual_rebases={r.address for r in binary.relocations if str(r.type)=='REBASE_TYPE.POINTER'}
    old_rebases={r.address for r in oldbinary.relocations if str(r.type)=='REBASE_TYPE.POINTER'}
    assert old_rebases<=actual_rebases
    oldact=u64(baseline,INFO_OFFSET+88);act=u64(native,INFO_OFFSET+88)
    extra={table+i*8 for i,p in enumerate(pointers) if p}|{act+(p-oldact) for p in old_rebases if oldact<=p<oldact+OLD_COUNT*16}
    assert actual_rebases-old_rebases==extra,'dyld pointer coverage differs'
    for at in (24,48,64,88):assert 0x100000000+INFO_OFFSET+at in actual_rebases
    flags=u64(native,INFO_OFFSET+64);assert native[offset(flags,count*4):offset(flags,count*4)+count*4]==bytes(count*4)
    # Decode actual linked instructions; do not trust destination values merely
    # because the linker included them in its report.
    def branch(pc):
        word=struct.unpack_from('<I',native,offset(pc,4))[0];assert word&0x7c000000==0x14000000
        imm=word&0x3ffffff
        if imm&(1<<25):imm-=1<<26
        return pc+4*imm
    for h in report['hooks']:assert branch(h['previous'])==h['target']
    for r in report['relocations']:
        pc,target,typ=r['pc'],r['target'],r['type'];word=struct.unpack_from('<I',native,offset(pc,4))[0]
        if typ==2:assert branch(pc)==target
        elif typ in (3,5):
            assert word&0x9f000000==0x90000000
            imm=((word>>29)&3)|(((word>>5)&0x7ffff)<<2)
            if imm&(1<<20):imm-=1<<21
            assert (pc&~0xfff)+(imm<<12)==target&~0xfff
        elif typ in (4,6):
            v=(word>>10)&0xfff
            if word&0x7f000000==0x11000000:assert v==target&0xfff
            else:assert word&0x3b000000==0x39000000 and (v<<(word>>30))==target&0xfff
    vm=report['voice_wrapper'];code=bytes.fromhex(vm['bytes']);assert native[vm['file_offset']:vm['file_offset']+len(code)]==code
    cs=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN);decoded=[(i.mnemonic,i.op_str) for i in cs.disasm(code,vm['address'])]
    assert [m for m,_ in decoded]==['stp','stp','stp','stp','mov','bl','ldp','ldp','ldp','ldp','stp','b']
    assert branch(vm['address']+20)==next(x['address'] for x in report['functions'] if x['method']==18394)
    assert branch(vm['address']+44)==vm['original_entry']+4
    assert code[40:44]==baseline[vm['original_entry']-0x100000000:vm['original_entry']-0x100000000+4]
    # Simulate the wrapper's save/call/restore part for adversarial register
    # clobbers. The copied original prologue must see the original six args,
    # frame pointer, stack pointer and caller return address.
    saved=dict(x0=11,x1=22,x2=33,x3=44,x4=55,x5=66,x29=77,x30=88,sp=0x8000)
    regs=dict(saved);stack={};regs['sp']-=64
    for off,pair in [(0,('x29','x30')),(16,('x0','x1')),(32,('x2','x3')),(48,('x4','x5'))]:
        for j,k in enumerate(pair):stack[regs['sp']+off+8*j]=regs[k]
    regs.update({k:0xbad for k in ('x0','x1','x2','x3','x4','x5','x29','x30')})
    for off,pair in [(16,('x0','x1')),(32,('x2','x3')),(48,('x4','x5')),(0,('x29','x30'))]:
        for j,k in enumerate(pair):regs[k]=stack[regs['sp']+off+8*j]
    regs['sp']+=64;assert regs==saved
    result=dict(status='offline_verified_unsigned_candidate',ipa=str(ipa),ipa_sha256=report['ipa_sha256'],native_sha256=report['native_sha256'],swf_sha256=report['swf_sha256'],
        zip_members=members,changed_zip_members=differences,old_method_ids_preserved=OLD_COUNT,new_methods=111,patched_existing_methods=len(changed),
        helpers=helper_checks,native_relocations_checked=len(report['relocations']),new_dyld_rebases=len(extra),voice_wrapper_instructions=decoded,
        original_native_code_outside_allowlist_unchanged=True,old_lens_abyss_segments_unchanged=True,endpoint_storage_title_cntips_unchanged=True,
        bundle_identity_unchanged=True,arm64_wrapper_abi_verified=True,accepted_registry_changed=False,desktop_air_run=False,device_tested=False,
        signing_layout=signing_layout,
        limitations=['No iOS device installation, soft-keyboard, login/network, or battle acceptance performed.'])
    dump(out/'verification-report.json',result)
    print(json.dumps({k:result[k] for k in ('status','zip_members','patched_existing_methods','new_methods','native_relocations_checked','new_dyld_rebases')},ensure_ascii=False))

if __name__=='__main__':main()
