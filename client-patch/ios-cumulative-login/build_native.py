"""Link only the new native methods onto the exact accepted cumulative IPA."""
from prepare import *
import struct,re
sys.path[:0]=[str(LEGACY),r'F:\codex\tools\ios-re-libs',r'F:\codex\ios-rush-navigation-port-20260907']
import lief,build_ios_rush_leaderboard_ipa as aot,build_incremental_ipa as common
from map_runtime import relocs
from macho_signing_layout import insert_before_string_table,assert_signable_layout

def commands(data):
    pos=32;out=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        c,n=struct.unpack_from('<II',data,pos);out.append((pos,c,bytes(data[pos:pos+n])));pos+=n
    assert pos==32+struct.unpack_from('<I',data,20)[0]
    return out

def segments(data):
    result=[]
    for pos,c,b in commands(data):
        if c==0x19:
            vm,vs,off,fs=struct.unpack_from('<QQQQ',b,24)
            result.append(dict(name=b[8:24].rstrip(b'\0').decode(),vm=vm,vs=vs,off=off,fs=fs,command=pos))
    return result

def file_offset(data,va,size=1):
    hits=[s['off']+va-s['vm'] for s in segments(data) if s['vm']<=va and va+size<=s['vm']+s['fs']]
    assert len(hits)==1,('unmapped file address',hex(va),size)
    return hits[0]

def segment_command(name,vm,off,size,payload,prot):
    return struct.pack('<II16sQQQQiiII',0x19,152,name.encode(),vm,size,off,size,prot,prot,1,0)+struct.pack('<16s16sQQIIIIIIII',b'__payload',name.encode(),vm,payload,off,4,0,0,0,0,0,0)

def extend(native,code_size,data_size):
    old=segments(native)
    assert [s['name'] for s in old]==['__PAGEZERO','__TEXT','__DATA','__LENS','__ABYAUTO','__LINKEDIT']
    link=old[-1];assert link['off']+link['fs']==len(native)
    rx=aot.align(code_size,0x4000);rw=aot.align(data_size,0x4000);growth=rx+rw
    added=[dict(name='__CNUPDATE',vm=link['vm'],off=link['off'],size=rx,payload=code_size,index=5,prot=5),
        dict(name='__CNACCT',vm=link['vm']+rx,off=link['off']+rx,size=rw,payload=data_size,index=6,prot=3)]
    fields={2:[8,16],0xb:[32,40,48,56,64,72],0x22:[8,16,24,32,40],0x80000022:[8,16,24,32,40]}
    data_cmds={0x1d,0x1e,0x26,0x29,0x2b,0x2e,0x80000033};rebuilt=[]
    for pos,c,raw in commands(native):
        b=bytearray(raw);assert c!=0x80000034,'chained fixups need another linker'
        if c==0x19 and raw[8:24].rstrip(b'\0')==b'__LINKEDIT':
            for s in added:rebuilt.append(segment_command(s['name'],s['vm'],s['off'],s['size'],s['payload'],s['prot']))
            struct.pack_into('<Q',b,24,link['vm']+growth);struct.pack_into('<Q',b,40,link['off']+growth)
        for at in fields.get(c,[8] if c in data_cmds else []):
            v=struct.unpack_from('<I',b,at)[0]
            if v:assert v>=link['off'];struct.pack_into('<I',b,at,v+growth)
        if c in (0x21,0x2c):assert struct.unpack_from('<I',b,16)[0]==0
        rebuilt.append(bytes(b))
    header=b''.join(rebuilt);old_end=32+sum(len(b) for _,_,b in commands(native));end=32+len(header)
    assert not any(native[old_end:end]),'load-command padding exhausted'
    result=bytearray(native[:link['off']]+bytes(growth)+native[link['off']:])
    struct.pack_into('<II',result,16,len(rebuilt),len(header));result[32:end]=header
    return result,added,end

def uleb(n):
    out=bytearray()
    while n>=128:out.append((n&127)|128);n>>=7
    out.append(n);return out

def read_rebase(data):
    pos,c,b=next(x for x in commands(data) if x[1] in (0x22,0x80000022))
    off,size=struct.unpack_from('<II',b,8);raw=data[off:off+size];i=0;typ=0;seg=0;where=0;result=[]
    def read():
        nonlocal i
        n=0;shift=0
        while True:
            v=raw[i];i+=1;n|=(v&127)<<shift
            if v<128:return n
            shift+=7
    def emit(n,skip=0):
        nonlocal where
        assert typ in (1,2,3)
        for _ in range(n):result.append((seg,where,typ));where+=8+skip
    while i<len(raw):
        op=raw[i]>>4;imm=raw[i]&15;i+=1
        if op==0:return dict(command=pos,offset=off,size=size,prefix=bytes(raw[:i-1]),entries=result)
        if op==1:typ=imm
        elif op==2:seg=imm;where=read()
        elif op==3:where+=read()
        elif op==4:where+=imm*8
        elif op==5:emit(imm)
        elif op==6:emit(read())
        elif op==7:emit(1,read())
        elif op==8:n=read();skip=read();emit(n,skip)
        else:raise ValueError(('rebase opcode',op))
    raise ValueError('rebase stream has no DONE')

def add_rebases(data,new_entries):
    info=read_rebase(data);stream=bytearray(info['prefix']);stream.append(0x11)
    # Existing streams must not refer to the moved LINKEDIT segment index.
    assert all(s<5 for s,_,_ in info['entries'])
    for seg in sorted(set(s for s,_ in new_entries)):
        offsets=sorted({o for s,o in new_entries if s==seg});i=0
        while i<len(offsets):
            start=offsets[i];end=i+1
            while end<len(offsets) and offsets[end]==offsets[end-1]+8:end+=1
            stream.append(0x20|seg);stream+=uleb(start);stream.append(0x60);stream+=uleb(end-i);i=end
    stream.append(0)
    # TrollStore's ldid truncates at the symbol string table end, even if the
    # signature load command points farther out. Keep all loader data before it.
    at=insert_before_string_table(data,stream)
    struct.pack_into('<II',data,info['command']+8,at,len(stream))
    signing_layout=assert_signable_layout(data)
    actual=read_rebase(data)['entries']
    assert actual==info['entries']+[(s,o,1) for s,o in sorted(set(new_entries))]
    return dict(old_count=len(info['entries']),new_count=len(new_entries),stream_offset=at,stream_size=len(stream),signing_layout=signing_layout)

def load_objects(port):
    directory=Path(json.loads((WORK/'compile-r8-report.json').read_text('utf8'))['directory'])
    wanted={r['method_id'] for r in port['methods']}|set(range(OLD_COUNT,port['total_methods']))
    objects={};functions={};meta=None
    for path in sorted(directory.glob('cumulative*.o')):
        obj=lief.parse(str(path));objects[path]=obj;symbols=list(obj.symbols)
        if any(aot.text(s.name).endswith('_284_aotInfo') and s.numberof_sections for s in symbols):meta=(path,obj)
        ids=[m for m in wanted if any(f':{m}:' in aot.text(s.name) and s.numberof_sections for s in symbols)]
        if not ids:continue
        sec,syms,records=aot.parse_object_functions(obj,ids)
        for r in records:functions[r.method_id]=(r,path,sec,syms,aot.parse_relocations(path,sec,syms,r))
    assert set(functions)==wanted and meta
    assert all(functions[mid][0].size>100 for mid in wanted if mid<OLD_COUNT)
    return objects,functions,meta

def constant(obj,name,path):
    sym=next(s for s in obj.symbols if aot.text(s.name)==name and s.numberof_sections)
    sec=aot.find_section(obj,sym)
    assert sec.name in ('__const','__literal8','__literal16'),('not a constant',name,sec.name)
    ends=[s.value for s in obj.symbols if s.numberof_sections==sym.numberof_sections and s.value>sym.value]
    end=min(ends,default=sec.virtual_address+sec.size)
    assert not relocs(path,obj,sec,sym.value,end),('constant pointer relocations require registration',name)
    return bytes(sec.content)[sym.value-sec.virtual_address:end-sec.virtual_address]

def main():
    output=WORK/'output';assert not output.exists(),'fresh native output required'
    port=json.loads((WORK/'port.json').read_text('utf8'));reg=port['source_ipa']
    native=(WORK/'baseline-native').read_bytes();swf=(WORK/'baseline.swf').read_bytes();full=(WORK/port['full_abc_file']).read_bytes()
    assert sha(Path(reg['ipa']).read_bytes())==IPA_SHA and sha(native)==reg['native_sha256'] and sha(swf)==reg['swf_sha256']
    assert sha(full)==port['full_abc_sha256'];digest=hashlib.sha1(full).digest()
    objects,funcs,(mp,meta)=load_objects(port)
    def symbol(suffix):return next(aot.text(s.name) for s in meta.symbols if aot.text(s.name).endswith(suffix) and s.numberof_sections)
    info_name=symbol('_284_aotInfo');info=aot.extract_symbol_bytes(meta,info_name,168);assert info[:20]==digest
    count=struct.unpack_from('<Q',info,56)[0];assert count==port['total_methods']
    compiled=aot.extract_symbol_bytes(meta,symbol('_abcBytes'),struct.unpack_from('<Q',info,32)[0])
    flags=aot.extract_symbol_bytes(meta,symbol('_methodFlagsArr'),count*4);assert not any(flags)
    fresh=abcfmt.ABC(compiled)
    oldptr,oldlen=struct.unpack_from('<QQ',native,INFO_OFFSET+24);oldraw=native[file_offset(native,oldptr,oldlen):file_offset(native,oldptr,oldlen)+oldlen]
    assert sha(oldraw)==port['baseline_runtime_abc_sha256'];old=abcfmt.ABC(oldraw)
    from hud_state_layout import slot_offsets
    old_hud=slot_offsets(old);new_hud=slot_offsets(fresh)
    assert all(new_hud[n]==offset for n,offset in old_hud.items()),'retained native HUD fields moved; apply the R4 slot repair'
    for pool in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        assert freeze(getattr(old,pool))==freeze(getattr(fresh,pool)[:len(getattr(old,pool))]),pool
    oldb={b[0]:b for b in old.bodies};changed={r['method_id'] for r in port['methods']}
    for i,b in enumerate(fresh.bodies):
        if b[0]<OLD_COUNT:
            if b[0] not in changed or b[0]==18394:fresh.bodies[i]=copy.deepcopy(oldb[b[0]])
            else:assert activation_traits(view(old),oldb[b[0]])==activation_traits(view(fresh),b)
    runtime=fresh.serialize();(WORK/'runtime-stripped.abc').write_bytes(runtime)
    cursor=0;positions={}
    for mid,(r,*_) in sorted(funcs.items()):positions[mid]=cursor;cursor=aot.align(cursor+r.size,16)
    wrapper=cursor;cursor+=80
    constants={};constant_positions={}
    for mid,(r,p,sec,syms,rows) in funcs.items():
        for row in rows:
            n=row['symbol']
            if n and (n.startswith('lCPI') or n.startswith('_exceptionDesc')) and (p,n) not in constants:
                data=constant(objects[p],n,p);constants[p,n]=data;constant_positions[p,n]=cursor;cursor=aot.align(cursor+len(data),16)
    abc_position=cursor;code_size=cursor+len(runtime)
    table_position=0;flags_position=aot.align(count*8,16);activation_position=aot.align(flags_position+count*4,16)
    data_size=activation_position+count*16
    patched,(rx,rw),header_end=extend(native,code_size,data_size)
    helpers={n:int(v['address'],0) for n,v in json.loads((LEGACY/'runtime-helper-map.json').read_text('utf8'))['symbols'].items()}
    helpers.update(aot.DEPENDENCY_AOT_INFOS);helpers[aot.STRICT_EQUALS_SYMBOL]=aot.STRICT_EQUALS_VA
    extra=json.loads(Path(r'F:\codex\work\lens-ios-20260908\additional-helper.json').read_text('utf8'))
    assert native[file_offset(native,extra['address'],32):file_offset(native,extra['address'],32)+32].hex()==extra['native_bytes'];helpers[extra['symbol']]=extra['address']
    for n,r in json.loads((WORK/'runtime-extra-map.json').read_text('utf8')).items():helpers[n]=r['address']
    named={r.symbol:rx['vm']+positions[mid] for mid,(r,*_) in funcs.items()};named[info_name]=aot.IMAGE_BASE+INFO_OFFSET
    function_report=[];relocation_report=[];hooks=[]
    for mid,(r,p,sec,syms,rows) in sorted(funcs.items()):
        va=rx['vm']+positions[mid];off=rx['off']+positions[mid];start=r.source_start-sec.virtual_address
        code=bytearray(bytes(sec.content)[start:start+r.size]);addends={x['source_address']:aot.sign_extend_24(x['raw']&0xffffff) for x in rows if x['type']==10}
        for row in rows:
            typ=row['type'];name=row['symbol'];idx=row['offset'];pc=va+idx
            if typ==10:continue
            if (p,name) in constant_positions:target=rx['vm']+constant_positions[p,name]
            elif name in named:target=named[name]
            elif name in helpers:target=helpers[name]
            else:raise RuntimeError(('unmapped native symbol',mid,name,typ))
            target+=addends.get(row['source_address'],0)
            if typ==2:aot.patch_branch26(code,idx,pc,target)
            elif typ in (3,5):aot.patch_adrp(code,idx,pc,target)
            elif typ in (4,6):aot.patch_pageoff12(code,idx,target,relax_got_load=typ==6)
            else:raise RuntimeError(('unsupported code relocation',typ,name))
            relocation_report.append(dict(method=mid,offset=idx,type=typ,symbol=name,pc=pc,target=target))
        patched[off:off+r.size]=code
        function_report.append(dict(method=mid,name=r.symbol,file_offset=off,address=va,size=r.size,sha256=sha(code),object_sha256=sha(p.read_bytes())))
    # Augment voice collection before the original native implementation. All
    # six integer/pointer arguments and the original return address survive.
    import capstone
    oldva=aot.read_u64(native,aot.MAIN_METHOD_TABLE_OFFSET+18394*8);oldoff=file_offset(native,oldva,4)
    first=next(capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN).disasm(native[oldoff:oldoff+4],oldva))
    assert first.mnemonic=='stp' and '[sp, #-' in first.op_str and first.op_str.endswith('!'),first
    # stp fp/lr, save x0..x5, call extension, restore, then original prologue.
    words=[0xa9bc7bfd,0xa90107e0,0xa9020fe2,0xa90317e4,0x910003fd,0x94000000,
        0xa94107e0,0xa9420fe2,0xa94317e4,0xa8c47bfd,struct.unpack_from('<I',native,oldoff)[0],0x14000000]
    wrapper_code=bytearray(struct.pack('<'+'I'*len(words),*words));wrapper_va=rx['vm']+wrapper
    aot.patch_branch26(wrapper_code,20,wrapper_va+20,rx['vm']+positions[18394]);aot.patch_branch26(wrapper_code,44,wrapper_va+44,oldva+4)
    patched[rx['off']+wrapper:rx['off']+wrapper+len(wrapper_code)]=wrapper_code
    table=bytearray(native[aot.MAIN_METHOD_TABLE_OFFSET:aot.MAIN_METHOD_TABLE_OFFSET+OLD_COUNT*8]+bytes((count-OLD_COUNT)*8))
    for mid,(r,*_) in funcs.items():
        va=wrapper_va if mid==18394 else rx['vm']+positions[mid]
        if mid<OLD_COUNT:
            previous=aot.read_u64(native,aot.MAIN_METHOD_TABLE_OFFSET+mid*8);off=file_offset(native,previous,4)
            assert struct.unpack_from('<I',native,off)[0]&0x7c000000!=0x14000000,('prior method hook needs audit',mid)
            aot.write_unconditional_branch(patched,off,previous,va);aot.write_u64(patched,aot.MAIN_METHOD_TABLE_OFFSET+mid*8,va)
            hooks.append(dict(method=mid,offset=off,previous=previous,target=va,old_bytes=native[off:off+4].hex()))
        aot.write_u64(table,mid*8,va)
    oldactva=aot.read_u64(native,INFO_OFFSET+88);oldact=file_offset(native,oldactva,OLD_COUNT*16)
    activation=native[oldact:oldact+OLD_COUNT*16]+aot.extract_symbol_bytes(meta,symbol('_activationInfo'),count*16)[OLD_COUNT*16:]
    assert activation[OLD_COUNT*16:]==(bytes.fromhex('ffffffff000000000000000000000000')*(count-OLD_COUNT))
    patched[rw['off']:rw['off']+len(table)]=table
    patched[rw['off']+flags_position:rw['off']+flags_position+len(flags)]=flags
    patched[rw['off']+activation_position:rw['off']+activation_position+len(activation)]=activation
    patched[rx['off']+abc_position:rx['off']+abc_position+len(runtime)]=runtime
    for key,data in constants.items():off=rx['off']+constant_positions[key];patched[off:off+len(data)]=data
    before_rebases=read_rebase(native)['entries'];old_segments=segments(native)
    new_rebases={(rw['index'],i*8) for i in range(count) if aot.read_u64(table,i*8)}
    for si,offset,typ in before_rebases:
        va=old_segments[si]['vm']+offset
        if oldactva<=va<oldactva+OLD_COUNT*16:
            assert typ==1;new_rebases.add((rw['index'],activation_position+va-oldactva))
    patched[INFO_OFFSET:INFO_OFFSET+20]=digest
    for offset,value in [(24,rx['vm']+abc_position),(32,len(runtime)),(48,rw['vm']),(56,count),(64,rw['vm']+flags_position),(88,rw['vm']+activation_position)]:aot.write_u64(patched,INFO_OFFSET+offset,value)
    rebases=add_rebases(patched,new_rebases)
    new_swf=aot.replace_main_swf_hash(swf,native[INFO_OFFSET:INFO_OFFSET+20],digest)
    for name,(a,b) in common.PROTECTED_RANGES.items():assert native[a:b]==patched[a:b],('prior feature changed',name)
    for s in segments(native):
        if s['name'] in ('__LENS','__ABYAUTO'):assert native[s['off']:s['off']+s['fs']]==patched[s['off']:s['off']+s['fs']]
    output.mkdir();ipa=output/'StarPoint-iOS-1.8.4-login-abyss-lens-trollstore-fix-r2-20260911-unsigned.ipa'
    (output/'worldflipper').write_bytes(patched);(output/'worldflipper_ios_release.swf').write_bytes(new_swf)
    with zipfile.ZipFile(reg['ipa']) as a,zipfile.ZipFile(ipa,'w',allowZip64=True) as b:
        for zi in a.infolist():
            data=patched if zi.filename==reg['native_member'] else new_swf if zi.filename==reg['swf_member'] else a.read(zi.filename)
            b.writestr(common.clone_zipinfo(zi),data)
        b.comment=a.comment
    report=dict(status='unsigned_candidate_pending_independent_verification',source_ipa=reg,ipa=str(ipa),ipa_sha256=sha(ipa.read_bytes()),
        native_sha256=sha(patched),swf_sha256=sha(new_swf),full_abc_sha256=sha(full),full_abc_sha1=digest.hex(),runtime_abc_sha256=sha(runtime),
        segments_added=[rx,rw],header_end=header_end,functions=function_report,relocations=relocation_report,hooks=hooks,rebases=rebases,
        total_methods=count,original_methods=OLD_COUNT,helpers=port['helpers'],table_position=table_position,flags_position=flags_position,
        activation_position=activation_position,abc_position=abc_position,voice_wrapper=dict(file_offset=rx['off']+wrapper,address=wrapper_va,bytes=wrapper_code.hex(),original_entry=oldva),
        previous_lens_and_abyss_segments_unchanged=True,desktop_air_run=False,device_tested=False)
    dump(output/'build-report.json',report)
    print(json.dumps({k:report[k] for k in ('status','ipa','ipa_sha256','native_sha256','swf_sha256')},ensure_ascii=False))

if __name__=='__main__':main()
