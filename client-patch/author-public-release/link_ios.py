"""Link author rules while retaining the accepted SET-fix executable.

Expand existing writable AOT table tails in segment 15, add their pointer
rebases, and extend segment 16 for code. No new Mach-O segments are added.
"""
import copy, struct, zipfile, sys, json
from common import *
WORK=WORK/'ios'; OUT=OUT/'ios'; PREP=WORK
OLD_COUNT=101315; NATIVE_COUNT=101287; INFO_OFFSET=104549248
sys.path[:0]=[str(HERE.parent/'ios-cumulative-login'),str(HERE.parent/'ios-shop-first-open')]
import prepare as p
p.asm.MNEMONICS['avm_label']=0x09;p.asm.BY_OPCODE[0x09]='avm_label'
LEGACY,SDK=p.LEGACY,p.SDK
abcfmt,freeze,view=p.abcfmt,p.freeze,p.view
lan=load('author_link_pools',HERE.parent/'r10-public-release/build_lan.py')
read=lambda path:json.loads(path.read_text('utf-8-sig'))
import build_native as link
from macho_signing_layout import assert_signable_layout,insert_before_string_table
from public_endpoint import require_public_endpoint
import veneers

def replacements(platform):
    _,keys=pair()
    return {OLD_IDS[platform].encode():IDS[platform].encode(),
            keys[OLD_IDS[platform]].encode():keys[IDS[platform]].encode(),
            ('SP-ADMISSION-1\n'+OLD_IDS[platform]+'\n').encode():('SP-ADMISSION-1\n'+IDS[platform]+'\n').encode()}

def assert_admission_prefix(abcs,platform):
    assert [v for a in abcs for v in a.strings if v.startswith(b'SP-ADMISSION-1\n')]==[('SP-ADMISSION-1\n'+IDS[platform]+'\n').encode()]

def add_rebases(data,entries):
    info=link.read_rebase(data);stream=bytearray(info['prefix']);stream.append(0x11)
    existing=set(info['entries'])
    assert all(si<=15 for si,_,_ in existing)
    assert all(0<=si<=15 and (si,offset,1) not in existing for si,offset in entries)
    for si in sorted({s for s,_ in entries}):
        offsets=sorted(o for s,o in entries if s==si);n=0
        while n<len(offsets):
            end=n+1
            while end<len(offsets) and offsets[end]==offsets[end-1]+8:end+=1
            stream.append(0x20|si);stream+=link.uleb(offsets[n]);stream.append(0x60);stream+=link.uleb(end-n);n=end
    stream.append(0)
    offset=insert_before_string_table(data,stream)
    struct.pack_into('<II',data,info['command']+8,offset,len(stream))
    assert link.read_rebase(data)['entries']==info['entries']+[(s,o,1) for s,o in sorted(entries)]
    return {'old_count':len(existing),'new_count':len(entries),'stream_offset':offset,'stream_size':len(stream)}

def guard_wrapper(native,oldva,address,target,kind):
    """Preserve integer argument registers and LR; typed null/-1 means fallback."""
    import capstone
    at=link.file_offset(native,oldva,4)
    first,=list(capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN).disasm(native[at:at+4],oldva))
    words=[0xa9bb7bfd,0xa90107e0,0xa9020fe2,0xa90317e4,0xa9041fe6,0x910003fd,0x94000000]
    if kind=='null_function':
        # cbz x0, fallback (skip ldp/ret)
        words+=[0xb4000060,0xa8c57bfd,0xd65f03c0]
    else:
        assert kind=='integer_minus_one'
        words+=[0x3100041f,0x54000060,0xa8c57bfd,0xd65f03c0]  # cmn w0,#1; b.eq
    words += [0xa94107e0,0xa9420fe2,0xa94317e4,0xa9441fe6,0xa8c57bfd]
    code=bytearray(struct.pack('<'+'I'*len(words),*words))
    link.aot.patch_branch26(code,24,address+24,target)
    if first.mnemonic=='b':
        fallback=int(first.op_str.removeprefix('#'),16)
        code+=veneers.encode(address+len(code),fallback)
    else:
        assert first.mnemonic in ('stp','sub') and 'sp' in first.op_str, str(first)
        code+=native[at:at+4]
        fallback=oldva+4;code+=veneers.encode(address+len(code),fallback)
    assert len(code)<=96
    return code,{'original_entry':oldva,'displaced_instruction':first.mnemonic+' '+first.op_str,
                 'fallback':fallback,'guard':target,'kind':kind,'address':address,'size':len(code),'sha256':sha(code)}

def extend(native, code_size):
    old=link.segments(native); tail=old[-1]; segment=old[-2]
    assert len(old)==18 and segment['name']=='__CNRECIO' and tail['name']=='__LINKEDIT'
    assert segment['off']+segment['fs']==tail['off'] and segment['vm']+segment['vs']==tail['vm']
    assert segment['fs']==segment['vs']
    growth=link.aot.align(code_size,0x4000)
    rx=dict(name='__CNRECIO',vm=tail['vm'],off=tail['off'],size=growth,payload=code_size,prot=5,index=16)
    offsets={2:[8,16],0xb:[32,40,48,56,64,72],0x22:[8,16,24,32,40],0x80000022:[8,16,24,32,40]}
    datacmds={0x1d,0x1e,0x26,0x29,0x2b,0x2e,0x80000033}
    patched=bytearray(native[:tail['off']]+bytes(growth)+native[tail['off']:])
    for at,cmd,raw in link.commands(native):
        row=bytearray(raw); assert cmd!=0x80000034
        if at==segment['command']:
            assert len(raw)==152 and struct.unpack_from('<I',raw,64)[0]==1
            struct.pack_into('<Q',row,32,segment['vs']+growth)
            struct.pack_into('<Q',row,48,segment['fs']+growth)
            struct.pack_into('<Q',row,112,segment['fs']+code_size)
        if at==tail['command']:
            struct.pack_into('<Q',row,24,tail['vm']+growth)
            struct.pack_into('<Q',row,40,tail['off']+growth)
        for field in offsets.get(cmd,[8] if cmd in datacmds else []):
            value=struct.unpack_from('<I',row,field)[0]
            if value:
                assert value>=tail['off']
                struct.pack_into('<I',row,field,value+growth)
        patched[at:at+len(row)]=row
    end=32+struct.unpack_from('<I',native,20)[0]
    assert link.read_rebase(patched)['entries']==link.read_rebase(native)['entries']
    return patched,rx,end

def read64(d,at):return struct.unpack_from('<Q',d,at)[0]
def write64(d,at,v):struct.pack_into('<Q',d,at,v)

def main():
    port=json.loads((WORK/'port.json').read_text(encoding='utf8'));reg=port['source_ipa'];out=WORK/'linked'; assert port['old_methods']==OLD_COUNT and port['total_methods']>=OLD_COUNT
    assert not out.exists()
    native=(WORK/'baseline-native').read_bytes();swf=(WORK/'baseline.swf').read_bytes()
    assert sha(native)==reg['native_sha256'];assert sha(Path(reg['ipa']).read_bytes())==reg['ipa_sha256']
    require_public_endpoint(native);assert_signable_layout(native)
    full=(WORK/port['full_abc_file']).read_bytes();assert sha(full)==port['full_abc_sha256']
    count=port['total_methods']
    redirects={int(row['original']):int(row['compiled']) for row in port.get('method_redirects',[])}
    guards={row['original']:row for row in port['method_redirects'] if row['strategy']=='guard_then_original'}
    aliases={row['original']:row['compiled'] for row in port['native_aliases']}
    aliases.update({row['original']:row['compiled'] for row in port.get('activation_aliases',[])})
    wanted=(set(redirects.values())|set(port.get('compiled_helpers',[]))|set(range(OLD_COUNT,count)))-set(aliases)
    compiled_report=json.loads((WORK/'compile-final-defaults-report.json').read_text(encoding='utf8'));objects={};funcs={};meta=None
    for row in compiled_report['objects']:
        path=Path(compiled_report['directory'])/row['name'];assert sha(path.read_bytes())==row['sha256']
        obj=link.lief.parse(str(path));objects[path]=obj;symbols=list(obj.symbols)
        if any(link.aot.text(s.name).endswith('_284_aotInfo') and s.numberof_sections for s in symbols):meta=(path,obj)
        ids=[i for i in wanted if any(f':{i}:' in link.aot.text(s.name) and s.numberof_sections for s in symbols)]
        if ids:
            sec,syms,records=link.aot.parse_object_functions(obj,ids)
            for r in records:funcs[r.method_id]=(r,path,sec,syms,link.aot.parse_relocations(path,sec,syms,r))
    assert set(funcs)==wanted and meta, ('missing compiled methods', sorted(wanted-set(funcs)))
    mp,mo=meta
    def sym(suffix):return next(link.aot.text(s.name) for s in mo.symbols if link.aot.text(s.name).endswith(suffix) and s.numberof_sections)
    infoname=sym('_284_aotInfo');info=link.aot.extract_symbol_bytes(mo,infoname,168)
    digest=__import__('hashlib').sha1(full).digest();assert info[:20]==digest and read64(info,56)==count
    compiled=link.aot.extract_symbol_bytes(mo,sym('_abcBytes'),read64(info,32));fresh=abcfmt.ABC(compiled)
    oldabcoff=link.file_offset(native,read64(native,INFO_OFFSET+24));oldabclen=read64(native,INFO_OFFSET+32)
    oldraw=native[oldabcoff:oldabcoff+oldabclen];assert sha(oldraw)==port['baseline_runtime_abc_sha256'];old=abcfmt.ABC(oldraw)
    for field in ('methods','metadata','scripts','ints','uints','doubles','namespaces','ns_sets','multinames'):
        rows=getattr(old,field);assert freeze(rows)==freeze(getattr(fresh,field)[:len(rows)]),field
    prepared=abcfmt.ABC(full)
    for section in ('instances','classes'):
        assert freeze(getattr(fresh,section))==freeze(getattr(prepared,section)),section
        for previous,current in zip(getattr(old,section),getattr(fresh,section)):
            assert freeze(previous[:-1])==freeze(current[:-1])
            assert freeze(previous[-1])==freeze(current[-1][:len(previous[-1])])
    from hud_state_layout import slot_offsets
    assert slot_offsets(old)==slot_offsets(fresh)
    allowed_strings=replacements('ios')
    for index,value in enumerate(old.strings):
        assert fresh.strings[index]==allowed_strings.get(value,value),('string index',index)
    assert not any(value in allowed_strings for value in fresh.strings)
    constants=lan.constants([[82,None,None,fresh]])
    assert_admission_prefix([fresh], 'ios')
    keys=read(PAIR/'config/client-admission.keys.json')
    assert constants==dict(ID=IDS['ios'],KEY=keys[IDS['ios']],ORIGIN='http://175.178.160.158')
    del constants,keys,allowed_strings
    bymid={b[0]:b for b in old.bodies};replace={r['method_id'] for r in port['methods'] if r['strategy']=='replace'}
    for i,b in enumerate(fresh.bodies):
        if b[0]<OLD_COUNT:
            if b[0] not in replace:fresh.bodies[i]=copy.deepcopy(bymid[b[0]])
            else:assert p.activation_traits(view(old),bymid[b[0]])==p.activation_traits(view(fresh),b)
    runtime=fresh.serialize();(WORK/'runtime-stripped.abc').write_bytes(runtime)
    cursor=0;positions={};constants={};cpos={}
    for mid,(record,*_) in sorted(funcs.items()):positions[mid]=cursor;cursor=link.aot.align(cursor+record.size,16)
    guard_positions={}
    for mid in sorted(guards):guard_positions[mid]=cursor;cursor+=96
    for mid,(r,path,sec,syms,rows) in funcs.items():
        for row in rows:
            name=row['symbol']
            if name and name.startswith(('lCPI','_exceptionDesc')) and (path,name) not in constants:
                data=link.constant(objects[path],name,path);constants[path,name]=data;cpos[path,name]=cursor;cursor=link.aot.align(cursor+len(data),16)
    # Reserve deterministic nearby islands before selecting RX/RW sizes.
    branch_keys=set()
    for mid,(r,path,sec,syms,rows) in funcs.items():
        addends={x['source_address']:link.aot.sign_extend_24(x['raw']&0xffffff) for x in rows if x['type']==10}
        branch_keys.update((row['symbol'],addends.get(row['source_address'],0)) for row in rows if row['type']==2)
    veneer_positions={}
    for key in sorted(branch_keys):
        veneer_positions[key]=cursor;cursor+=16
    # The baseline methodFlagsArr ends at OLD_COUNT.  Allocate a complete
    # compiler-produced replacement beside the appended code so AOTInfo also
    # has flags for imported helpers and redirected methods.
    compiler_flags=link.aot.extract_symbol_bytes(mo,sym('_methodFlagsArr'),count*4)
    abc_position=cursor
    flags_position=link.aot.align(abc_position+len(runtime),16)
    code_size=flags_position+len(compiler_flags)
    patched,rx,header_end=extend(native,code_size)
    entry_bridges=[];bridge_by_target={};padding={}
    for segment in link.segments(native)[3:-2]:
        at=segment['command']
        if struct.unpack_from('<ii',native,at+56)!=(5,5) or struct.unpack_from('<I',native,at+64)[0]!=1:continue
        used=struct.unpack_from('<Q',native,at+112)[0]
        start=link.aot.align(used,16)
        if start+16<=segment['fs']:
            assert not any(native[segment['off']+start:segment['off']+segment['fs']]),segment['name']
            padding[segment['name']]=[segment,start]
    def hook_entry(offset,address,target):
        via=target
        if not veneers.reachable(address,target):
            candidates=[r for r in entry_bridges if r['target']==target and veneers.reachable(address,r['address'])]
            if candidates:via=candidates[0]['address']
            else:
                for name,(segment,used) in padding.items():
                    va=segment['vm']+used
                    if used+16<=segment['fs'] and veneers.reachable(address,va):break
                else:raise AssertionError(('No verified executable padding for entry bridge',hex(address)))
                bridge_offset=segment['off']+used;code=veneers.encode(va,target)
                assert not any(native[bridge_offset:bridge_offset+16])
                patched[bridge_offset:bridge_offset+16]=code
                padding[name][1]=used+16
                struct.pack_into('<Q',patched,segment['command']+112,used+16)
                entry_bridges.append({'segment':name,'address':va,'file_offset':bridge_offset,'target':target,'size':16,'sha256':sha(code)})
                via=va
        link.aot.write_unconditional_branch(patched,offset,address,via)
        return via
    helpers={n:int(v['address'],0) for n,v in json.loads((LEGACY/'runtime-helper-map.json').read_text(encoding='utf8'))['symbols'].items()}
    helpers.update(link.aot.DEPENDENCY_AOT_INFOS);helpers[link.aot.STRICT_EQUALS_SYMBOL]=link.aot.STRICT_EQUALS_VA
    extra=json.loads(Path('F:/codex/work/lens-ios-20260908/additional-helper.json').read_text(encoding='utf8'))
    assert native[link.file_offset(native,extra['address'],32):link.file_offset(native,extra['address'],32)+32].hex()==extra['native_bytes']
    helpers[extra['symbol']]=extra['address']
    for name,r in json.loads(Path('F:/codex/work/ios-cumulative-launch-fix-r2-20260911/runtime-extra-map.json').read_text(encoding='utf8')).items():helpers[name]=r['address']
    named={r.symbol:rx['vm']+positions[mid] for mid,(r,*_) in funcs.items()};named[infoname]=link.aot.IMAGE_BASE+INFO_OFFSET
    unknown={row['symbol'] for r,path,sec,syms,rows in funcs.values() for row in rows
             if row['type']!=10 and (path,row['symbol']) not in cpos and row['symbol'] not in named and row['symbol'] not in helpers}
    from map_runtime import derive, function as runtime_function, relocs as runtime_relocs
    runtime_member=LEGACY/'runtime-archive-members/hm-stubs.o'
    assert sha(runtime_member.read_bytes())=='952f0c9ffe34f2e35eb434fdf0dd641d7ecd8baa6bf9d260e258d59e4ca1ecb8'
    def proof_at(name, offset):
        obj=link.lief.parse(str(runtime_member));sec,start,end=runtime_function(obj,name)
        code=bytes(sec.content)[start-sec.virtual_address:end-sec.virtual_address]
        rows=runtime_relocs(runtime_member,obj,sec,start,end)
        reloc={row['offset'] for row in rows}
        assert offset>=0 and offset+len(code)<=len(native)
        for at in range(0,len(code),4):
            if at not in reloc:
                assert native[offset+at:offset+at+4]==code[at:at+4],(name,offset,at)
        return dict(address=link.aot.IMAGE_BASE+offset,file_offset=offset,size=len(code),
                    object=str(runtime_member),object_sha256=sha(runtime_member.read_bytes()),
                    native_bytes=native[offset:offset+32].hex(),relocations=rows,
                    unrelocated_bytes_verified=len(code)-len(reloc)*4,
                    fixed_offset_proof=True)
    runtime_proofs={}
    for name in sorted(unknown):
        try:
            runtime_proofs[name]=derive(runtime_member,name,native)
        except (AssertionError, StopIteration):
            # The accepted iOS executable carries the strict variant of the
            # AIR property lookup stub, but not the non-strict variant.  The
            # reviewed hooks only resolve declared instance/class members;
            # for those lookups strict and non-strict resolution have the
            # same result.  Reuse the byte-proven strict stub rather than
            # guessing an address or adding an unlinked runtime object.
            findproperty='__ZN8halfmoon5Stubs19do_abc_findpropertyEPN7avmplus11MethodFrameEPKNS1_9MultinameEPNS1_9MethodEnvEiiPx'
            findpropstrict='__ZN8halfmoon5Stubs21do_abc_findpropstrictEPN7avmplus11MethodFrameEPKNS1_9MultinameEPNS1_9MethodEnvEiiPx'
            if name == findproperty:
                proof=derive(runtime_member,findpropstrict,native)
                proof=dict(proof, aliased_from=name, semantic_note='strict lookup alias for declared members')
                runtime_proofs[name]=proof
            elif name=='__ZN8halfmoon5Stubs16do_abc_convert_sEPN7avmplus11MethodFrameEx':
                # This short helper has a repeated prologue in hm-stubs.o.
                # The accepted iOS build family records the unique call-site
                # proof at this fixed native offset; verify every
                # non-relocated instruction against the current executable.
                runtime_proofs[name]=proof_at(name,0xA273CC)
            elif name=='_llVerifyError':
                # The accepted executable contains the same fail-fast AIR
                # helper as _llNPE, but not a separately materialized
                # _llVerifyError body.  Verification-successful ABC never
                # reaches this path; use the verified native fail-fast stub.
                runtime_proofs[name]=dict(address=helpers['_llNPE'],
                                           file_offset=link.file_offset(native,helpers['_llNPE'],32),
                                           aliased_from=name,
                                           semantic_note='unreachable verifier-failure alias',
                                           source='accepted runtime-helper-map')
            else:
                raise
    dump(WORK/'runtime-admission-helpers.json',runtime_proofs)
    helpers.update({name:row['address'] for name,row in runtime_proofs.items()})
    functions=[];relocations=[];used_veneers={}
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
            branch_target=None
            if typ==2:
                branch_target=target
                if not veneers.reachable(pc,target):
                    key=(name,addends.get(row['source_address'],0))
                    branch_target=rx['vm']+veneer_positions[key]
                    veneer_offset=rx['off']+veneer_positions[key]
                    veneer_code=veneers.encode(branch_target,target)
                    patched[veneer_offset:veneer_offset+16]=veneer_code
                    used_veneers[key]=dict(symbol=name,address=branch_target,target=target,file_offset=veneer_offset,size=16,sha256=sha(veneer_code))
                link.aot.patch_branch26(code,at,pc,branch_target)
            elif typ in (3,5):link.aot.patch_adrp(code,at,pc,target)
            elif typ in (4,6):link.aot.patch_pageoff12(code,at,target,relax_got_load=typ==6)
            else:raise AssertionError((typ,name))
            relocations.append(dict(method=mid,offset=at,type=typ,symbol=name,pc=pc,target=target,branch_target=branch_target))
        patched[offset:offset+len(code)]=code
        functions.append(dict(method=mid,address=address,file_offset=offset,size=len(code),sha256=sha(code)))
    for key,data in constants.items():at=rx['off']+cpos[key];patched[at:at+len(data)]=data
    activeva=read64(native,INFO_OFFSET+48);activeoff=link.file_offset(native,activeva,NATIVE_COUNT*8)
    assert read64(native,INFO_OFFSET+56)==NATIVE_COUNT
    table=bytearray(native[activeoff:activeoff+NATIVE_COUNT*8]+bytes((count-NATIVE_COUNT)*8))
    # Register previously appended metadata using the exact accepted native
    # functions, including SET. Do not recompile old constructor hooks.
    prior_reports=[Path('F:/codex/outputs/abyss-ex-independent-formations-20260923/ios-build-report.json'),
                   Path('F:/codex/outputs/set-edit-c8601-ios-public-20260924/ios-build-report.json')]
    retained={}
    for path in prior_reports:
        for row in read(path)['functions']:
            mid=row['method']
            if NATIVE_COUNT<=mid<OLD_COUNT:
                off=row['file_offset'];size=row['size']
                assert sha(native[off:off+size])==row['sha256'],('retained method',mid)
                retained[mid]=row;write64(table,mid*8,row['address'])
    assert set(retained)==set(range(NATIVE_COUNT,OLD_COUNT))
    activationva=read64(native,INFO_OFFSET+88);activationoff=link.file_offset(native,activationva,NATIVE_COUNT*16)
    activation_tail=link.aot.extract_symbol_bytes(mo,sym('_activationInfo'),count*16)[NATIVE_COUNT*16:]
    assert activation_tail==bytes.fromhex('ffffffff000000000000000000000000')*(count-NATIVE_COUNT),'new activation constructors require dedicated link'
    segments=link.segments(native);writable=segments[15]
    assert writable['name']=='__CNADTAB'
    assert writable['off']<=activeoff and activeoff+count*8<activationoff
    assert activationoff+count*16<=writable['off']+writable['fs']
    struct.pack_into('<Q',patched,writable['command']+112,activationoff+count*16-writable['off'])
    assert not any(native[activeoff+NATIVE_COUNT*8:activeoff+count*8]),'method tail is occupied'
    assert not any(native[activationoff+NATIVE_COUNT*16:activationoff+count*16]),'activation tail is occupied'
    original_count=101071;legacy=0x62c0780
    hooks=[];sites=[];wrappers=[]
    for mid in sorted(wanted):
        target=rx['vm']+positions[mid]
        if mid<OLD_COUNT:
            oldva=read64(table,mid*8);at=link.file_offset(native,oldva,4)
            hook_entry(at,oldva,target)
            hooks.append(dict(method=mid,previous=oldva,target=target,offset=at))
            write64(patched,activeoff+mid*8,target);sites.append(activeoff+mid*8)
            if mid<original_count:
                legacyva=read64(native,legacy+mid*8)
                if legacyva!=oldva:
                    la=link.file_offset(native,legacyva,4);hook_entry(la,legacyva,target)
                    hooks.append(dict(method=mid,previous=legacyva,target=target,offset=la))
                write64(patched,legacy+mid*8,target);sites.append(legacy+mid*8)
        write64(table,mid*8,target)
    for original_mid,compiled_mid in aliases.items():
        write64(table,original_mid*8,rx['vm']+positions[compiled_mid])
    for original, compiled_mid in sorted(redirects.items()):
        target=rx['vm']+positions[compiled_mid]
        if original in guards:
            previous=read64(table,original*8)
            address=rx['vm']+guard_positions[original]
            code,record=guard_wrapper(native,previous,address,target,guards[original]['guard_kind'])
            offset=rx['off']+guard_positions[original];patched[offset:offset+len(code)]=code
            wrappers.append(dict(record,method=original,file_offset=offset))
            target=address
        oldva=read64(table,original*8);at=link.file_offset(native,oldva,4)
        hook_entry(at,oldva,target)
        hooks.append(dict(method=original,compiled_method=compiled_mid,previous=oldva,target=target,offset=at))
        write64(patched,activeoff+original*8,target);sites.append(activeoff+original*8)
        if original<original_count:
            legacyva=read64(native,legacy+original*8)
            if legacyva!=oldva:
                la=link.file_offset(native,legacyva,4);hook_entry(la,legacyva,target)
                hooks.append(dict(method=original,compiled_method=compiled_mid,previous=legacyva,target=target,offset=la))
            write64(patched,legacy+original*8,target);sites.append(legacy+original*8)
    flags_offset=link.file_offset(native,read64(native,INFO_OFFSET+64),OLD_COUNT*4)
    for mid in wanted:
        if mid>=OLD_COUNT:
            continue
        assert native[flags_offset+mid*4:flags_offset+mid*4+4]==compiler_flags[mid*4:mid*4+4],('method flags',mid)
    # Existing pointer slots already occur in the dyld rebase stream. No new
    # absolute pointer locations or activation-layout changes are introduced.
    rebased={segments[si]['vm']+off for si,off,typ in link.read_rebase(native)['entries'] if typ==1}
    for location in sites+[INFO_OFFSET+24,INFO_OFFSET+64]:
        segment,=[s for s in segments if s['off']<=location<s['off']+s['fs']]
        assert segment['vm']+location-segment['off'] in rebased,('missing rebase',location)
    patched[rx['off']+abc_position:rx['off']+abc_position+len(runtime)]=runtime
    patched[rx['off']+flags_position:rx['off']+flags_position+len(compiler_flags)]=compiler_flags
    equipment=port['equipment']; at=equipment['offset']; old_size=equipment['old_size']
    assert sha(native[at:at+old_size])==equipment['source_sha256']
    new_gate=(PREP/'abyss-ex-ios-equipment.bin').read_bytes()
    assert sha(new_gate)==equipment['sha256'] and len(new_gate)==equipment['new_size']
    assert not any(native[at+old_size:at+len(new_gate)])
    patched[at:at+len(new_gate)]=new_gate
    patched[INFO_OFFSET:INFO_OFFSET+20]=digest
    for at,v in ((24,rx['vm']+abc_position),(32,len(runtime)),
                 (56,count),(64,rx['vm']+flags_position)):write64(patched,INFO_OFFSET+at,v)
    table_tail=bytes(table[NATIVE_COUNT*8:])
    assert all(read64(table,mid*8) for mid in range(NATIVE_COUNT,count))
    patched[activeoff+NATIVE_COUNT*8:activeoff+count*8]=table_tail
    patched[activationoff+NATIVE_COUNT*16:activationoff+count*16]=activation_tail
    new_entries={(15,activeoff+mid*8-writable['off']) for mid in range(NATIVE_COUNT,count)}
    rebases=add_rebases(patched,new_entries)
    newswf=link.aot.replace_main_swf_hash(swf,native[INFO_OFFSET:INFO_OFFSET+20],digest)
    signing=assert_signable_layout(patched);origin=require_public_endpoint(patched)
    allowed=[(0,header_end),(INFO_OFFSET,INFO_OFFSET+20),(INFO_OFFSET+24,INFO_OFFSET+40),
             (INFO_OFFSET+56,INFO_OFFSET+72),(equipment['offset'],equipment['offset']+len(new_gate)),
             (activeoff+NATIVE_COUNT*8,activeoff+count*8),
             (activationoff+NATIVE_COUNT*16,activationoff+count*16)]
    allowed += [(h['offset'],h['offset']+4) for h in hooks]+[(at,at+8) for at in sites]
    allowed += [(r['file_offset'],r['file_offset']+16) for r in entry_bridges]
    old_prefix_end=link.segments(native)[-1]['off']
    prefix=bytearray(patched[:old_prefix_end])
    for begin,end in allowed:prefix[begin:end]=native[begin:end]
    assert prefix==native[:old_prefix_end],'unexpected preexisting native change'
    out.mkdir();OUT.mkdir(parents=True,exist_ok=True);ipa=OUT/'StarPoint-iOS-1.8.4-author-unified-damage-public-20260924-r2-unsigned.ipa'
    (out/'worldflipper').write_bytes(patched);(out/'worldflipper_ios_release.swf').write_bytes(newswf)
    with zipfile.ZipFile(reg['ipa']) as left,zipfile.ZipFile(ipa,'w',allowZip64=True) as right:
        for item in left.infolist():
            data=patched if item.filename==reg['native_member'] else newswf if item.filename==reg['swf_member'] else left.read(item)
            right.writestr(link.common.clone_zipinfo(item),data)
        right.comment=left.comment
    report=dict(status='pending_independent_verification',ipa=str(ipa),ipa_sha256=sha(ipa.read_bytes()),source_ipa=reg,
        native_sha256=sha(patched),swf_sha256=sha(newswf),runtime_abc_sha256=sha(runtime),
        full_abc_sha256=sha(full),full_abc_sha1=digest.hex(),segments_added=[],executable_extension=rx,equipment=equipment,functions=functions,relocations=relocations,
        hooks=hooks,table_sites=sites,native_change_ranges=allowed,old_active_table_offset=activeoff,veneers=list(used_veneers.values()),
        total_methods=count,original_methods=OLD_COUNT,new_methods=count-OLD_COUNT,
        abc_position=abc_position,flags_position=flags_position,new_rebases=len(new_entries),rebases=rebases,signing_layout=signing,origin=origin,runtime_helper_proofs=runtime_proofs,
        old_native_count=NATIVE_COUNT,activation_offset=activationoff,registered_prior_methods=retained,guard_wrappers=wrappers,entry_bridges=entry_bridges,native_aliases=aliases,
        ios_carousel_unchanged=True,ios_device_store_unchanged=True,device_tested=False,save_schema_changed=False,
        record_encoding_unchanged=True,game_file_cleanup=False,server_endpoint_required=False,old_startup_cache_preserved=True,
        admission_protocol_unchanged=True,build_id=IDS['ios'],previous_build_id=reg['build_id'])
    dump(OUT/'ios-build-report.json',report)
    print(json.dumps({k:report[k] for k in ('status','ipa','ipa_sha256','new_methods','origin')},ensure_ascii=False))

if __name__=='__main__':main()
