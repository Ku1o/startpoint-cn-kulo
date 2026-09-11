"""Independent archive, ARM64 relocation, AOT and loader preservation checks."""
from prepare import *
import struct, plistlib
sys.path[:0]=[str(LEGACY),r'F:\codex\tools\ios-re-libs']
import lief
import build_ios_rush_leaderboard_ipa as aot

def check(ok,msg):
    if not ok:raise AssertionError(msg)
def word(b,o):return struct.unpack_from('<I',b,o)[0]
def sx(n,bits):return n-(1<<bits) if n&(1<<(bits-1)) else n
def branch(w,pc):
    check(w&0x7c000000==0x14000000,'expected ARM64 branch')
    return pc+(sx(w&0x3ffffff,26)<<2)
def page(w,pc):
    check(w&0x9f000000==0x90000000,'expected ADRP')
    return (pc&~4095)+(sx(((w>>5)&0x7ffff)<<2|((w>>29)&3),21)<<12)
def low(w):
    n=(w>>10)&4095
    if w&0x7f000000==0x11000000:return n
    if w&0x3b000000==0x39000000:return n*(1<<((w>>30)&3))
    raise AssertionError('expected ADD/load/store')

def main():
    report=json.loads((WORK/'output/build-report.json').read_text(encoding='utf-8'))
    src=Path(report['source_ipa']['ipa']);dst=Path(report['output_ipa'])
    check(sha(src.read_bytes())==IPA_HASH,'accepted source IPA drift')
    check(sha(dst.read_bytes())==report['ipa_sha256'],'candidate IPA drift')
    changed=[]
    with zipfile.ZipFile(src) as a,zipfile.ZipFile(dst) as b:
        check(a.namelist()==b.namelist() and len(b.namelist())==3568,'IPA member inventory')
        check(b.testzip() is None,'ZIP CRC')
        for x,y in zip(a.infolist(),b.infolist()):
            for key in ('filename','date_time','compress_type','comment','extra','create_system','create_version','extract_version','flag_bits','volume','internal_attr','external_attr'):
                check(getattr(x,key)==getattr(y,key),f'ZIP metadata {x.filename}:{key}')
            if a.read(x.filename)!=b.read(y.filename):changed.append(x.filename)
        check(set(changed)=={report['source_ipa']['native_member'],report['source_ipa']['swf_member']},'unrelated IPA member changed')
        old=a.read(report['source_ipa']['native_member']);new=b.read(report['source_ipa']['native_member'])
        oswf=a.read(report['source_ipa']['swf_member']);nswf=b.read(report['source_ipa']['swf_member'])
        plist=plistlib.loads(b.read('Payload/worldflipper.app/Info.plist'))
    check(sha(new)==report['native_sha256'] and sha(nswf)==report['swf_sha256'],'payload hashes')
    check(plist['CFBundleIdentifier']=='com.kulo.wf' and plist['CFBundleShortVersionString']=='1.8.4' and plist['CFBundleVersion']=='1.8.46','application identity')
    _,op=aot.decompress_swf(oswf);_,np=aot.decompress_swf(nswf)
    old_hash=old[aot.MAIN_AOT_INFO_OFFSET:aot.MAIN_AOT_INFO_OFFSET+20];new_hash=bytes.fromhex(report['full_abc_sha1'])
    check(op.count(old_hash)==1 and op.replace(old_hash,new_hash)==np,'SWF changed beyond AOT identity')
    check(new[aot.MAIN_AOT_INFO_OFFSET:aot.MAIN_AOT_INFO_OFFSET+20]==new_hash,'native AOT identity')
    seg=report['segment'];start=seg['file_offset'];end=start+seg['size'];va=seg['virtual_address']
    check(len(new)==len(old)+seg['size'],'native file size')
    check(new[end:]==old[start:],'original LINKEDIT payload changed')
    check(aot.read_u64(new,aot.MAIN_AOT_INFO_OFFSET+24)==va,'runtime ABC pointer')
    check(aot.read_u64(new,aot.MAIN_AOT_INFO_OFFSET+32)==report['runtime_abc_size'],'runtime ABC length')
    check(sha(new[start:start+report['runtime_abc_size']])==report['runtime_abc_sha256'],'runtime ABC bytes')
    old_binary=lief.parse(str(WORK/'baseline-native'));new_binary=lief.parse(str(WORK/'output/worldflipper'))
    check(len(new_binary.segments)==len(old_binary.segments)+1,'segment inventory')
    before={s.name:s for s in old_binary.segments};after={s.name:s for s in new_binary.segments}
    geometry=lambda s:(s.virtual_address,s.virtual_size,s.file_offset,s.file_size,s.max_protection,s.init_protection)
    for name in ('__PAGEZERO','__TEXT','__DATA'):check(geometry(before[name])==geometry(after[name]),'existing segment moved: '+name)
    check(geometry(after['__LENS'])==(va,seg['size'],start,seg['size'],5,5),'new RX segment geometry')
    check(after['__LINKEDIT'].file_offset==before['__LINKEDIT'].file_offset+seg['size'] and after['__LINKEDIT'].virtual_address==before['__LINKEDIT'].virtual_address+seg['size'],'LINKEDIT geometry')
    check(after['__LINKEDIT'].file_size==before['__LINKEDIT'].file_size,'LINKEDIT length')
    ordered=sorted((s.virtual_address,s.virtual_address+s.virtual_size) for s in new_binary.segments)
    check(all(a[1]<=b[0] for a,b in zip(ordered,ordered[1:])),'overlapping mapped segments')
    check({r.address for r in old_binary.relocations}=={r.address for r in new_binary.relocations},'dyld rebases changed')
    rebases={r.address for r in new_binary.relocations}
    ids={x['method_id'] for x in report['functions']};check(len(ids)==33,'expected 33 native methods')
    required={aot.IMAGE_BASE+aot.MAIN_METHOD_TABLE_OFFSET+i*8 for i in ids}|{aot.IMAGE_BASE+aot.MAIN_AOT_INFO_OFFSET+24}
    check(required<=rebases,'ASLR rebases missing for updated pointers')
    table=aot.MAIN_METHOD_TABLE_OFFSET
    check({i for i in range(aot.MAIN_METHOD_COUNT) if old[table+i*8:table+i*8+8]!=new[table+i*8:table+i*8+8]}==ids,'unrelated method pointer changed')
    # Independent disassembly of every relocated instruction, plus byte equality
    # for every instruction that was not relocated.
    objects={};helper_map={n:int(v['address'],0) for n,v in json.loads((LEGACY/'runtime-helper-map.json').read_text(encoding='utf-8'))['symbols'].items()}
    helper_map[aot.STRICT_EQUALS_SYMBOL]=aot.STRICT_EQUALS_VA
    extra=json.loads((WORK/'additional-helper.json').read_text(encoding='utf-8'));helper_map[extra['symbol']]=extra['address']
    literals={(l['object'],l['symbol']):l['virtual_address'] for l in report['literals']}
    names={f['symbol']:f['virtual_address'] for f in report['functions']}
    verified=0
    for f in report['functions']:
        p=Path(f['object']);check(sha(p.read_bytes())==f['object_sha256'],'compiled object drift')
        if p not in objects:objects[p]=lief.parse(str(p))
        sec,syms,rs=aot.parse_object_functions(objects[p],[f['method_id']]);r=rs[0]
        rows=aot.parse_relocations(p,sec,syms,r)
        original=bytes(sec.content)[r.source_start-sec.virtual_address:r.source_end-sec.virtual_address]
        embedded=new[f['file_offset']:f['file_offset']+f['size']];restored=bytearray(embedded)
        check(r.size==f['size'] and sha(embedded)==f['code_sha256'],'native function size/hash')
        check(aot.read_u64(new,table+f['method_id']*8)==f['virtual_address'],'method pointer')
        addends={x['source_address']:sx(x['raw']&0xffffff,24) for x in rows if x['type']==10}
        for row in rows:
            typ=row['type'];name=row['symbol'];o=row['offset'];pc=f['virtual_address']+o
            if typ==10:continue
            instruction=word(embedded,o)
            if typ==2:
                check(branch(instruction,pc)==helper_map[name],'branch target '+name)
                check(instruction&0xfc000000==word(original,o)&0xfc000000,'B/BL behavior')
            else:
                target=literals.get((str(p),name)) or names.get(name) or aot.DEPENDENCY_AOT_INFOS.get(name)
                if target is None and name.endswith('_284_aotInfo'):target=aot.IMAGE_BASE+aot.MAIN_AOT_INFO_OFFSET
                check(target is not None,'unknown relocation symbol '+name)
                target+=addends.get(row['source_address'],0)
                check(page(instruction,pc)==target&~4095 if typ in (3,5) else low(instruction)==target&4095,'page relocation '+name)
            restored[o:o+4]=original[o:o+4];verified+=1
        check(bytes(restored)==original,'non-relocation machine instruction changed')
    check(verified==len(report['relocations']),'relocation receipt count')
    for l in report['literals']:
        p=Path(l['object']);check(new[l['file_offset']:l['file_offset']+8]==aot.extract_symbol_bytes(objects[p],l['symbol'],8),'numeric literal changed')
    for h in report['hooks']:
        o=h['offset'];check(word(new,o)&0xfc000000==0x14000000 and branch(word(new,o),aot.IMAGE_BASE+o)==h['target'],'entry trampoline')
    # Reconstruct the exact accepted bytes by removing the additional segment
    # and undoing only the declared header, AOT identity/pointer and 33 entries.
    reconstructed=bytearray(new[:start]+new[end:])
    allowed=[(16,24),(32,seg['header_end']),(aot.MAIN_AOT_INFO_OFFSET,aot.MAIN_AOT_INFO_OFFSET+40)]
    allowed += [(table+i*8,table+i*8+8) for i in ids]
    allowed += [(h['offset'],h['offset']+4) for h in report['hooks']]
    for a,b in allowed:reconstructed[a:b]=old[a:b]
    check(bytes(reconstructed)==old,'unrelated native bytes changed')
    # Compare runtime metadata, including all old anonymous closure definitions.
    oldabc=abcfmt.ABC(old[aot.MAIN_ABC_OFFSET:aot.MAIN_ABC_OFFSET+aot.read_u64(old,aot.MAIN_AOT_INFO_OFFSET+32)])
    newabc=abcfmt.ABC(new[start:start+report['runtime_abc_size']]); ov=view(oldabc);nv=view(newabc)
    port=json.loads((WORK/'port.json').read_text(encoding='utf-8'));field_owners=port['fields']
    for a,b in zip(oldabc.instances,newabc.instances):
        check(a[:6]==b[:6],'class identity changed')
        check(freeze(a[6])==freeze(b[6][:len(a[6])]),'old instance slots changed')
        names=[newabc.mn_name(t.name) for t in b[6][len(a[6]):]]
        check(names==field_owners.get(oldabc.mn_name(a[0]),[]),'unexpected instance field')
    check(freeze(oldabc.classes)==freeze(newabc.classes) and freeze(oldabc.scripts)==freeze(newabc.scripts),'class/script definitions changed')
    check(len(oldabc.methods)==len(newabc.methods)==101071,'method inventory changed')
    signature_ids={r['method_id'] for r in port['methods'] if 'BothBossTool$/' in r['label']}
    for i,(a,b) in enumerate(zip(oldabc.methods,newabc.methods)):
        if i not in signature_ids:check(a==b,'unrelated method info changed')
    for a,b in zip(oldabc.bodies,newabc.bodies):
        if a[0] not in ids:check(freeze(a)==freeze(b),'non-target activation/body metadata changed')
        else:check(activation_traits(ov,a)==activation_traits(nv,b),'target closure activation layout changed')
    result=dict(status='offline_verified_unsigned_candidate',device_acceptance='pending',ipa=str(dst),ipa_sha256=sha(dst.read_bytes()),native_sha256=sha(new),swf_sha256=sha(nswf),zip_members_verified=3568,changed_members=changed,native_methods=33,relocations_verified=verified,new_segment_size=seg['size'],all_prior_non_target_native_bytes_preserved=True,existing_method_ids_and_dyld_rebases_preserved=True,old_constant_pool_indexes_preserved=True,closure_layouts_preserved=True,title_cntips_b_unchanged=True,identity={k:plist[k] for k in ('CFBundleIdentifier','CFBundleShortVersionString','CFBundleVersion')})
    dump(WORK/'output/verification-report.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
