"""Link three EX methods and the equipment gate onto the accepted cumulative IPA.

Existing method and activation tables stay at their original addresses. Extend
the last executable segment to avoid the four-bit classic-dyld segment limit.
"""
from release_common import *
import copy, struct, zipfile
sys.modules['prepare'] = p
import build_native as link
from macho_signing_layout import assert_signable_layout
from public_endpoint import require_public_endpoint
import veneers

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
    port=json.loads((WORK/'port.json').read_text());reg=port['source_ipa'];out=OUT/'ios-r2'; assert port['total_methods']==OLD_COUNT
    assert not out.exists()
    native=(WORK/'baseline-native').read_bytes();swf=(WORK/'baseline.swf').read_bytes()
    assert sha(native)==reg['native_sha256'];assert sha(Path(reg['ipa']).read_bytes())==reg['ipa_sha256']
    require_public_endpoint(native);assert_signable_layout(native)
    full=(WORK/port['full_abc_file']).read_bytes();assert sha(full)==port['full_abc_sha256']
    count=port['total_methods'];wanted={r['method_id'] for r in port['methods']}|set(range(OLD_COUNT,count))
    compiled_report=json.loads((WORK/'compile-final-report.json').read_text());objects={};funcs={};meta=None
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
    for field in ('methods','metadata','instances','classes','scripts','ints','uints','doubles','namespaces','ns_sets','multinames'):
        rows=getattr(old,field);assert freeze(rows)==freeze(getattr(fresh,field)[:len(rows)]),field
    allowed_strings=replacements('ios')
    for index,value in enumerate(old.strings):
        assert fresh.strings[index]==allowed_strings.get(value,value),('string index',index)
    assert not any(value in allowed_strings for value in fresh.strings)
    constants=lan.constants([[82,None,None,fresh]])
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
    abc_position=cursor;code_size=cursor+len(runtime)
    patched,rx,header_end=extend(native,code_size)
    helpers={n:int(v['address'],0) for n,v in json.loads((LEGACY/'runtime-helper-map.json').read_text())['symbols'].items()}
    helpers.update(link.aot.DEPENDENCY_AOT_INFOS);helpers[link.aot.STRICT_EQUALS_SYMBOL]=link.aot.STRICT_EQUALS_VA
    extra=json.loads(Path('F:/codex/work/lens-ios-20260908/additional-helper.json').read_text())
    assert native[link.file_offset(native,extra['address'],32):link.file_offset(native,extra['address'],32)+32].hex()==extra['native_bytes']
    helpers[extra['symbol']]=extra['address']
    for name,r in json.loads(Path('F:/codex/work/ios-cumulative-launch-fix-r2-20260911/runtime-extra-map.json').read_text()).items():helpers[name]=r['address']
    named={r.symbol:rx['vm']+positions[mid] for mid,(r,*_) in funcs.items()};named[infoname]=link.aot.IMAGE_BASE+INFO_OFFSET
    unknown={row['symbol'] for r,path,sec,syms,rows in funcs.values() for row in rows
             if row['type']!=10 and (path,row['symbol']) not in cpos and row['symbol'] not in named and row['symbol'] not in helpers}
    from map_runtime import derive
    runtime_member=LEGACY/'runtime-archive-members/hm-stubs.o'
    assert sha(runtime_member.read_bytes())=='952f0c9ffe34f2e35eb434fdf0dd641d7ecd8baa6bf9d260e258d59e4ca1ecb8'
    runtime_proofs={name:derive(runtime_member,name,native) for name in sorted(unknown)}
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
    flags_offset=link.file_offset(native,read64(native,INFO_OFFSET+64),count*4)
    compiler_flags=link.aot.extract_symbol_bytes(mo,sym('_methodFlagsArr'),count*4)
    for mid in wanted:
        assert native[flags_offset+mid*4:flags_offset+mid*4+4]==compiler_flags[mid*4:mid*4+4],('method flags',mid)
    # Existing pointer slots already occur in the dyld rebase stream. No new
    # absolute pointer locations or activation-layout changes are introduced.
    segments=link.segments(native)
    rebased={segments[si]['vm']+off for si,off,typ in link.read_rebase(native)['entries'] if typ==1}
    for location in sites+[INFO_OFFSET+24]:
        segment,=[s for s in segments if s['off']<=location<s['off']+s['fs']]
        assert segment['vm']+location-segment['off'] in rebased,('missing rebase',location)
    patched[rx['off']+abc_position:rx['off']+abc_position+len(runtime)]=runtime
    equipment=port['equipment']; at=equipment['offset']; old_size=equipment['old_size']
    assert sha(native[at:at+old_size])==equipment['source_sha256']
    new_gate=(PREP/'abyss-ex-ios-equipment.bin').read_bytes()
    assert sha(new_gate)==equipment['sha256'] and len(new_gate)==equipment['new_size']
    assert not any(native[at+old_size:at+len(new_gate)])
    patched[at:at+len(new_gate)]=new_gate
    patched[INFO_OFFSET:INFO_OFFSET+20]=digest
    for at,v in ((24,rx['vm']+abc_position),(32,len(runtime))):write64(patched,INFO_OFFSET+at,v)
    newswf=link.aot.replace_main_swf_hash(swf,native[INFO_OFFSET:INFO_OFFSET+20],digest)
    signing=assert_signable_layout(patched);origin=require_public_endpoint(patched)
    allowed=[(0,header_end),(INFO_OFFSET,INFO_OFFSET+20),(INFO_OFFSET+24,INFO_OFFSET+40),(equipment['offset'],equipment['offset']+len(new_gate))]
    allowed += [(h['offset'],h['offset']+4) for h in hooks]+[(at,at+8) for at in sites]
    old_prefix_end=link.segments(native)[-1]['off']
    prefix=bytearray(patched[:old_prefix_end])
    for begin,end in allowed:prefix[begin:end]=native[begin:end]
    assert prefix==native[:old_prefix_end],'unexpected preexisting native change'
    out.mkdir();ipa=OUT/'StarPoint-iOS-1.8.4-abyss-ex-20260917-r2-unsigned.ipa'
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
        abc_position=abc_position,new_rebases=0,signing_layout=signing,origin=origin,runtime_helper_proofs=runtime_proofs,
        ios_carousel_unchanged=True,ios_device_store_unchanged=True,device_tested=False,save_schema_changed=False,
        record_encoding_unchanged=True,game_file_cleanup=False,server_endpoint_required=False,old_startup_cache_preserved=True,
        admission_protocol_unchanged=True,build_id=IDS['ios'],previous_build_id=reg['build_id'])
    dump(OUT/'ios-build-report.json',report)
    print(json.dumps({k:report[k] for k in ('status','ipa','ipa_sha256','new_methods','origin')},ensure_ascii=False))

if __name__=='__main__':main()
