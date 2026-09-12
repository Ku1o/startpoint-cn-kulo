"""Link only the record/name/folder delta, preserving all accepted cache-rounded native code."""
import copy,json,struct,sys,zipfile,uuid
from pathlib import Path
from prepare import WORK,HERE,LEGACY,OLD_COUNT,INFO_OFFSET,abcfmt,view,freeze,sha,dump,p
import build_native as link
from macho_signing_layout import insert_before_string_table,assert_signable_layout
from public_endpoint import require_public_endpoint

def extend(native,code_size,data_size):
    old=link.segments(native);tail=old[-1];assert len(old)==11 and tail['name']=='__LINKEDIT'
    assert all(i<10 for i,_,_ in link.read_rebase(native)['entries'])
    rxsize=link.aot.align(code_size,0x4000);rwsize=link.aot.align(data_size,0x4000);growth=rxsize+rwsize
    segments=[dict(name='__CNRECORD',vm=tail['vm'],off=tail['off'],size=rxsize,index=10,payload=code_size,prot=5),
        dict(name='__CNRCTAB',vm=tail['vm']+rxsize,off=tail['off']+rxsize,size=rwsize,index=11,payload=data_size,prot=3)]
    offsets={2:[8,16],0xb:[32,40,48,56,64,72],0x22:[8,16,24,32,40],0x80000022:[8,16,24,32,40]}
    datacmds={0x1d,0x1e,0x26,0x29,0x2b,0x2e,0x80000033};commands=[]
    for _,cmd,raw in link.commands(native):
        b=bytearray(raw);assert cmd!=0x80000034
        if cmd==0x19 and raw[8:24].rstrip(b'\0')==b'__LINKEDIT':
            for s in segments:commands.append(link.segment_command(s['name'],s['vm'],s['off'],s['size'],s['payload'],s['prot']))
            struct.pack_into('<Q',b,24,tail['vm']+growth);struct.pack_into('<Q',b,40,tail['off']+growth)
        for at in offsets.get(cmd,[8] if cmd in datacmds else []):
            value=struct.unpack_from('<I',b,at)[0]
            if value:assert value>=tail['off'];struct.pack_into('<I',b,at,value+growth)
        commands.append(bytes(b))
    hdr=b''.join(commands);end=32+len(hdr);oldend=32+sum(len(b) for _,_,b in link.commands(native))
    assert not any(native[oldend:end]),'load command padding exhausted'
    out=bytearray(native[:tail['off']]+bytes(growth)+native[tail['off']:]);out[32:end]=hdr
    struct.pack_into('<II',out,16,len(commands),len(hdr))
    return out,segments,end

def read64(d,at):return struct.unpack_from('<Q',d,at)[0]
def write64(d,at,v):struct.pack_into('<Q',d,at,v)

def wrapper(native,oldva,newva,address):
    """Call the extension, then continue the untouched original function."""
    at=link.file_offset(native,oldva,4);word=struct.unpack_from('<I',native,at)[0]
    import capstone
    ins=next(capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN).disasm(native[at:at+4],oldva))
    assert ins.mnemonic=='stp' and '[sp, #-' in ins.op_str and ins.op_str.endswith('!'),(hex(oldva),ins.mnemonic,ins.op_str)
    # Preserve all integer argument registers plus fp/lr. Both wrapped
    # signatures (main and the asset response handler) have no FP arguments.
    words=[0xa9ba7bfd,0xa90107e0,0xa9020fe2,0xa90317e4,0xa9041fe6,0x910003fd,0x94000000,
        0xa94107e0,0xa9420fe2,0xa94317e4,0xa9441fe6,0xa8c67bfd,word,0x14000000]
    code=bytearray(struct.pack('<'+'I'*len(words),*words))
    link.aot.patch_branch26(code,24,address+24,newva);link.aot.patch_branch26(code,52,address+52,oldva+4)
    return code

def main():
    port=json.loads((WORK/'port.json').read_text());reg=port['source_ipa'];out=WORK/'output'
    assert not out.exists()
    native=(WORK/'baseline-native').read_bytes();swf=(WORK/'baseline.swf').read_bytes()
    assert sha(native)==reg['native_sha256'];assert sha(Path(reg['ipa']).read_bytes())==reg['ipa_sha256']
    require_public_endpoint(native);assert_signable_layout(native)
    full=(WORK/port['full_abc_file']).read_bytes();assert sha(full)==port['full_abc_sha256']
    count=port['total_methods'];wanted={r['method_id'] for r in port['methods']}|set(range(OLD_COUNT,count))
    compiled_report=json.loads((WORK/'compile-report.json').read_text());objects={};funcs={};meta=None
    for row in compiled_report['objects']:
        path=Path(compiled_report['directory'])/row['name'];assert sha(path.read_bytes())==row['sha256']
        obj=link.lief.parse(str(path));objects[path]=obj;symbols=list(obj.symbols)
        if any(link.aot.text(s.name).endswith('_284_aotInfo') and s.numberof_sections for s in symbols):meta=(path,obj)
        ids=[i for i in wanted if any(f':{i}:' in link.aot.text(s.name) and s.numberof_sections for s in symbols)]
        if ids:
            sec,syms,records=link.aot.parse_object_functions(obj,ids)
            for r in records:funcs[r.method_id]=(r,path,sec,syms,link.aot.parse_relocations(path,sec,syms,r))
    assert set(funcs)==wanted and meta
    mp,mo=meta
    def sym(suffix):return next(link.aot.text(s.name) for s in mo.symbols if link.aot.text(s.name).endswith(suffix) and s.numberof_sections)
    infoname=sym('_284_aotInfo');info=link.aot.extract_symbol_bytes(mo,infoname,168)
    digest=__import__('hashlib').sha1(full).digest();assert info[:20]==digest and read64(info,56)==count
    compiled=link.aot.extract_symbol_bytes(mo,sym('_abcBytes'),read64(info,32));fresh=abcfmt.ABC(compiled)
    oldabcoff=link.file_offset(native,read64(native,INFO_OFFSET+24));oldabclen=read64(native,INFO_OFFSET+32)
    oldraw=native[oldabcoff:oldabcoff+oldabclen];assert sha(oldraw)==port['baseline_runtime_abc_sha256'];old=abcfmt.ABC(oldraw)
    for field in ('methods','metadata','instances','classes','scripts','ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        rows=getattr(old,field);assert freeze(rows)==freeze(getattr(fresh,field)[:len(rows)]),field
    bymid={b[0]:b for b in old.bodies};replace={r['method_id'] for r in port['methods'] if r['strategy']=='replace'}
    for i,b in enumerate(fresh.bodies):
        if b[0]<OLD_COUNT:
            if b[0] not in replace:fresh.bodies[i]=copy.deepcopy(bymid[b[0]])
            else:assert p.activation_traits(view(old),bymid[b[0]])==p.activation_traits(view(fresh),b)
    runtime=fresh.serialize();(WORK/'runtime-stripped.abc').write_bytes(runtime)
    cursor=0;positions={};constants={};cpos={}
    for mid,(record,*_) in sorted(funcs.items()):positions[mid]=cursor;cursor=link.aot.align(cursor+record.size,16)
    for mid,(r,path,sec,syms,rows) in funcs.items():
        for row in rows:
            name=row['symbol']
            if name and name.startswith(('lCPI','_exceptionDesc')) and (path,name) not in constants:
                data=link.constant(objects[path],name,path);constants[path,name]=data;cpos[path,name]=cursor;cursor=link.aot.align(cursor+len(data),16)
    abc_position=cursor;code_size=cursor+len(runtime)
    flags_position=link.aot.align(count*8,16);act_position=link.aot.align(flags_position+count*4,16)
    patched,(rx,rw),header_end=extend(native,code_size,act_position+count*16)
    helpers={n:int(v['address'],0) for n,v in json.loads((LEGACY/'runtime-helper-map.json').read_text())['symbols'].items()}
    helpers.update(link.aot.DEPENDENCY_AOT_INFOS);helpers[link.aot.STRICT_EQUALS_SYMBOL]=link.aot.STRICT_EQUALS_VA
    extra=json.loads(Path('F:/codex/work/lens-ios-20260908/additional-helper.json').read_text())
    assert native[link.file_offset(native,extra['address'],32):link.file_offset(native,extra['address'],32)+32].hex()==extra['native_bytes']
    helpers[extra['symbol']]=extra['address']
    for name,r in json.loads(Path('F:/codex/work/ios-cumulative-launch-fix-r2-20260911/runtime-extra-map.json').read_text()).items():helpers[name]=r['address']
    named={r.symbol:rx['vm']+positions[mid] for mid,(r,*_) in funcs.items()};named[infoname]=link.aot.IMAGE_BASE+INFO_OFFSET
    functions=[];relocations=[]
    for mid,(r,path,sec,syms,rows) in sorted(funcs.items()):
        address=rx['vm']+positions[mid];offset=rx['off']+positions[mid];start=r.source_start-sec.virtual_address
        code=bytearray(bytes(sec.content)[start:start+r.size]);addends={x['source_address']:link.aot.sign_extend_24(x['raw']&0xffffff) for x in rows if x['type']==10}
        for row in rows:
            typ,name,at=row['type'],row['symbol'],row['offset'];pc=address+at
            if typ==10:continue
            if (path,name) in cpos:target=rx['vm']+cpos[path,name]
            elif name in named:target=named[name]
            elif name in helpers:target=helpers[name]
            else:raise RuntimeError(('unmapped native symbol',mid,name,typ))
            target+=addends.get(row['source_address'],0)
            if typ==2:link.aot.patch_branch26(code,at,pc,target)
            elif typ in (3,5):link.aot.patch_adrp(code,at,pc,target)
            elif typ in (4,6):link.aot.patch_pageoff12(code,at,target,relax_got_load=typ==6)
            else:raise AssertionError((typ,name))
            relocations.append(dict(method=mid,offset=at,type=typ,symbol=name,pc=pc,target=target))
        patched[offset:offset+len(code)]=code
        functions.append(dict(method=mid,address=address,file_offset=offset,size=len(code),sha256=sha(code)))
    for key,data in constants.items():at=rx['off']+cpos[key];patched[at:at+len(data)]=data
    activeva=read64(native,INFO_OFFSET+48);activeoff=link.file_offset(native,activeva,OLD_COUNT*8)
    table=bytearray(native[activeoff:activeoff+OLD_COUNT*8]+bytes((count-OLD_COUNT)*8))
    original_count=101071;legacy=0x62c0780
    hooks=[];sites=[]
    for mid in sorted(wanted):
        target=rx['vm']+positions[mid]
        if mid<OLD_COUNT:
            oldva=read64(table,mid*8);at=link.file_offset(native,oldva,4)
            link.aot.write_unconditional_branch(patched,at,oldva,target)
            hooks.append(dict(method=mid,previous=oldva,target=target,offset=at))
            write64(patched,activeoff+mid*8,target);sites.append(activeoff+mid*8)
            if mid<original_count:
                legacyva=read64(native,legacy+mid*8)
                if legacyva!=oldva:
                    la=link.file_offset(native,legacyva,4);link.aot.write_unconditional_branch(patched,la,legacyva,target)
                    hooks.append(dict(method=mid,previous=legacyva,target=target,offset=la))
                write64(patched,legacy+mid*8,target);sites.append(legacy+mid*8)
        write64(table,mid*8,target)
    oldflagsva=read64(native,INFO_OFFSET+64);oldflags=link.file_offset(native,oldflagsva,OLD_COUNT*4)
    flags=native[oldflags:oldflags+OLD_COUNT*4]+link.aot.extract_symbol_bytes(mo,sym('_methodFlagsArr'),count*4)[OLD_COUNT*4:]
    oldactva=read64(native,INFO_OFFSET+88);oldact=link.file_offset(native,oldactva,OLD_COUNT*16)
    activation=native[oldact:oldact+OLD_COUNT*16]+link.aot.extract_symbol_bytes(mo,sym('_activationInfo'),count*16)[OLD_COUNT*16:]
    assert activation[OLD_COUNT*16:]==bytes.fromhex('ffffffff000000000000000000000000')*(count-OLD_COUNT)
    for off,data in ((rw['off'],table),(rw['off']+flags_position,flags),(rw['off']+act_position,activation),(rx['off']+abc_position,runtime)):
        patched[off:off+len(data)]=data
    rebases=link.read_rebase(patched);oldsegments=link.segments(native)
    new={(rw['index'],i*8) for i in range(count) if read64(table,i*8)}
    for si,off,typ in rebases['entries']:
        va=oldsegments[si]['vm']+off
        if oldactva<=va<oldactva+OLD_COUNT*16:assert typ==1;new.add((rw['index'],act_position+va-oldactva))
    stream=bytearray(rebases['prefix']);stream.append(0x11)
    for seg in sorted({si for si,_ in new}):
        offsets=sorted(o for si,o in new if si==seg);i=0
        while i<len(offsets):
            end=i+1
            while end<len(offsets) and offsets[end]==offsets[end-1]+8:end+=1
            stream.append(0x20|seg);stream+=link.uleb(offsets[i]);stream.append(0x60);stream+=link.uleb(end-i);i=end
    stream.append(0);rebaseat=insert_before_string_table(patched,stream)
    struct.pack_into('<II',patched,rebases['command']+8,rebaseat,len(stream))
    assert link.read_rebase(patched)['entries']==rebases['entries']+[(si,o,1) for si,o in sorted(new)]
    patched[INFO_OFFSET:INFO_OFFSET+20]=digest
    for at,v in ((24,rx['vm']+abc_position),(32,len(runtime)),(48,rw['vm']),(56,count),(64,rw['vm']+flags_position),(88,rw['vm']+act_position)):write64(patched,INFO_OFFSET+at,v)
    newswf=link.aot.replace_main_swf_hash(swf,native[INFO_OFFSET:INFO_OFFSET+20],digest)
    signing=assert_signable_layout(patched);origin=require_public_endpoint(patched)
    allowed=[(0,header_end),(INFO_OFFSET,INFO_OFFSET+20),(INFO_OFFSET+24,INFO_OFFSET+40),(INFO_OFFSET+48,INFO_OFFSET+72),(INFO_OFFSET+88,INFO_OFFSET+96)]
    allowed += [(h['offset'],h['offset']+4) for h in hooks]+[(at,at+8) for at in sites]
    prefix=bytearray(patched[:rx['off']])
    for begin,end in allowed:prefix[begin:end]=native[begin:end]
    assert prefix==native[:rx['off']],'unexpected preexisting native change'
    out.mkdir();ipa=out/'StarPoint-iOS-1.8.4-record-holder-public-20260912-unsigned.ipa'
    (out/'worldflipper').write_bytes(patched);(out/'worldflipper_ios_release.swf').write_bytes(newswf)
    with zipfile.ZipFile(reg['ipa']) as left,zipfile.ZipFile(ipa,'w',allowZip64=True) as right:
        for item in left.infolist():
            data=patched if item.filename==reg['native_member'] else newswf if item.filename==reg['swf_member'] else left.read(item)
            right.writestr(link.common.clone_zipinfo(item),data)
        right.comment=left.comment
    report=dict(status='pending_independent_verification',ipa=str(ipa),ipa_sha256=sha(ipa.read_bytes()),source_ipa=reg,
        native_sha256=sha(patched),swf_sha256=sha(newswf),runtime_abc_sha256=sha(runtime),
        full_abc_sha256=sha(full),full_abc_sha1=digest.hex(),segments_added=[rx,rw],functions=functions,relocations=relocations,
        hooks=hooks,table_sites=sites,native_change_ranges=allowed,old_active_table_offset=activeoff,
        total_methods=count,original_methods=OLD_COUNT,new_methods=count-OLD_COUNT,
        flags_position=flags_position,activation_position=act_position,abc_position=abc_position,
        rebase_offset=rebaseat,rebase_size=len(stream),new_rebases=len(new),signing_layout=signing,origin=origin,
        ios_carousel_unchanged=True,device_tested=False,save_schema_changed=False,game_file_cleanup=False,server_endpoint_required=True,old_startup_cache_preserved=True)
    dump(out/'build-report.json',report)
    print(json.dumps({k:report[k] for k in ('status','ipa','ipa_sha256','new_methods','origin')},ensure_ascii=False))

if __name__=='__main__':main()
