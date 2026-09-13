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
    assert report['original_methods']==OLD_COUNT and report['total_methods']==OLD_COUNT+9
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
    assert [s['name'] for s in segs]==[s['name'] for s in baseline_segs[:-1]]+['__CNCACHE','__CNCTAB','__LINKEDIT']
    for seg in segs[1:]:
        assert seg['vm']%0x4000==seg['off']%0x4000==0 and seg['vs']>=seg['fs'] and seg['off']+seg['fs']<=len(new)
    for a,b in zip(segs[1:],segs[2:]):assert a['vm']+a['vs']<=b['vm']
    rx,rw=segs[-3:-1]
    for n in ('__LENS','__ABYAUTO','__HUDSTATE'):
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
    assert [na.mn_name(i[0]) for i in na.instances[len(oa.instances):]]==['cn.asset::EmptyUpdate','cn.ui::RoundedButton']
    ov,nv,fv=view(oa),view(na),view(fa)
    expected={51820,101083,101091};assert {r['method_id'] for r in port['methods']}==expected
    # All existing function signatures and activation fields remain unchanged.
    ob={b[0]:b for b in oa.bodies};nb={b[0]:b for b in na.bodies}
    for mid,b in ob.items():
        if mid not in {101083,101091}:assert freeze(b)==freeze(nb[mid]),mid
        else:assert p.activation_traits(ov,b)==p.activation_traits(nv,nb[mid]),mid
    label='cn.ui::AbyssDetails$/attach|1';fi,=fv.by_label[label]
    oldfull=view(abcfmt.ABC((WORK/'baseline-full.abc').read_bytes()));oi,=oldfull.by_label[label]
    before=p.asm.decode(oldfull.a.bodies[oi][5]);after=p.asm.decode(fa.bodies[fi][5])
    assert len(before)==len(after)
    for i,(x,y) in enumerate(zip(before,after)):
        if i not in (164,168):assert repr(x)==repr(y),(i,'attach unexpected instruction')
    assert fv.mn(after[164].args[0])==(7,(22,'cn.ui'),'RoundedButton') and after[168].op==0x46 and after[168].args[1]==3
    # Independently compare all new helper behavior with actual compiled donor ABCs.
    donors=[view(t[3]) for t in s.parts(WORK/'android.swf')[2] if t[0]==82]
    donors=[v for v in donors if 'cn.asset::EmptyUpdate$/normalize|1' in v.by_label]+[view(s.helper_abc(WORK/'rounded.swc'))]
    matched=0
    for dv in donors:
        for label,indices in dv.by_label.items():
            if not label.startswith(('cn.asset::EmptyUpdate','cn.ui::RoundedButton','script:cn.asset::EmptyUpdate','script:cn.ui::RoundedButton')):continue
            if label not in fv.by_label:continue
            assert [dv.normalized(i) for i in indices]==[fv.normalized(i) for i in fv.by_label[label]],label
            matched+=len(indices)
    assert matched==9,matched
    login='cn.account::PlayerLogin$/title|1/closure:0'
    donor,=[view(t[3]) for t in s.parts(WORK/'android.swf')[2] if t[0]==82 and login in view(t[3]).by_label]
    assert donor.normalized(donor.by_label[login][0])==fv.normalized(fv.by_label[login][0])
    count=report['total_methods'];oldtable=link.file_offset(old,u64(old,INFO_OFFSET+48),OLD_COUNT*8);newtable=link.file_offset(new,u64(new,INFO_OFFSET+48),count*8)
    changed_ids={mid for mid in range(OLD_COUNT) if u64(old,oldtable+mid*8)!=u64(new,newtable+mid*8)}
    assert changed_ids==expected
    sites={oldtable+mid*8 for mid in expected}|{0x62c0780+51820*8};assert set(report['table_sites'])==sites
    for mid in range(OLD_COUNT):assert u64(new,oldtable+mid*8)==u64(new,newtable+mid*8)
    for mid in expected:
        function=next(r for r in report['functions'] if r['method']==mid)
        target=report['asset_wrapper']['address'] if mid==51820 else function['address']
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
    for r in report['relocations']:
        pc,target,typ=r['pc'],r['target'],r['type'];word=struct.unpack_from('<I',new,link.file_offset(new,pc,4))[0]
        if typ==2:assert branch(pc)==target
        elif typ in (3,5):
            assert word&0x9f000000==0x90000000
            imm=((word>>29)&3)|(((word>>5)&0x7ffff)<<2)
            if imm&(1<<20):imm-=1<<21
            assert (pc&~0xfff)+(imm<<12)==target&~0xfff
        else:
            value=(word>>10)&0xfff
            if word&0x7f000000==0x11000000:assert value==target&0xfff
            else:assert word&0x3b000000==0x39000000 and value<<(word>>30)==target&0xfff
    for item in ('main_wrapper','asset_wrapper'):
        w=report[item];code=bytes.fromhex(w['bytes']);assert new[w['file_offset']:w['file_offset']+len(code)]==code
        assert branch(w['address']+24)==w['extension'] and branch(w['address']+52)==w['original']+4
        assert code[48:52]==old[link.file_offset(old,w['original'],4):link.file_offset(old,w['original'],4)+4]
    oldrebases=link.read_rebase(old)['entries'];newrebases=link.read_rebase(new)['entries'];assert newrebases[:len(oldrebases)]==oldrebases
    newset={(seg,at) for seg,at,typ in newrebases[len(oldrebases):] if typ==1}
    expected_rebases={(9,i*8) for i in range(count) if u64(new,newtable+i*8)}
    oldact=u64(old,INFO_OFFSET+88)
    for seg,at,typ in oldrebases:
        va=baseline_segs[seg]['vm']+at
        if oldact<=va<oldact+OLD_COUNT*16:expected_rebases.add((9,report['activation_position']+va-oldact))
    assert newset==expected_rebases and len(newset)==report['new_rebases']
    # Reconstruct the original prefix, permitting only derived pointers/hooks.
    ranges=[(0,32+struct.unpack_from('<I',new,20)[0]),(INFO_OFFSET,INFO_OFFSET+20),(INFO_OFFSET+24,INFO_OFFSET+40),(INFO_OFFSET+48,INFO_OFFSET+72),(INFO_OFFSET+88,INFO_OFFSET+96)]
    assert {r['method'] for r in report['hooks']}==expected|{'main'} and len(report['hooks'])==4
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
        zip_members=members,changed_zip_members=changed,existing_methods_preserved=OLD_COUNT-3,
        old_class_and_activation_layouts_preserved=True,patched_existing_methods=sorted(expected),new_helper_methods=matched,
        native_relocations_checked=len(report['relocations']),new_rebases=len(newset),ldid_signature_models_passed=3,
        public_origin=origin,signing_layout=signing,ios_carousel_unchanged=True,save_schema_changed=False,
        device_tested=False,server_changed=False,cleanup_scope='NSURLCache responses only; no downloaded game files or accounts')
    dump(out/'verification-report.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
