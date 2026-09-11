"""Add one native auto-start method after the intact Lens segment.

The new segment precedes LINKEDIT. Existing TEXT/DATA addresses, section
ordinals, dyld segment indexes and every previous patch remain unchanged.
"""
from prepare import *
import struct, time
sys.path[:0]=[str(LEGACY),r'F:\codex\tools\ios-re-libs',r'F:\codex\ios-rush-navigation-port-20260907']
import lief
import build_ios_rush_leaderboard_ipa as aot
import build_incremental_ipa as common
from stitch_ios_stripped_abc import body_records

def ensure(ok,msg):
    if not ok:raise RuntimeError(msg)

def commands(data):
    cursor=32;result=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,n=struct.unpack_from('<II',data,cursor)
        result.append((cursor,cmd,bytes(data[cursor:cursor+n])));cursor+=n
    ensure(cursor==32+struct.unpack_from('<I',data,20)[0],'load-command length')
    return result

def extend_segment(native,payload_size):
    cmds=commands(native)
    segments=[b for _,c,b in cmds if c==0x19]
    ensure([b[8:24].rstrip(b'\0') for b in segments]==[b'__PAGEZERO',b'__TEXT',b'__DATA',b'__LENS',b'__LINKEDIT'],'unexpected segment order')
    link=segments[-1];vm,vs,off,fs=struct.unpack_from('<QQQQ',link,24)
    ensure(off+fs==len(native),'LINKEDIT is not final file payload')
    size=aot.align(payload_size,0x4000)
    ensure(vm%0x4000==off%0x4000==0,'segment alignment')
    new=struct.pack('<II16sQQQQiiII',0x19,152,b'__ABYAUTO',vm,size,off,size,5,5,1,0)
    new+=struct.pack('<16s16sQQIIIIIIII',b'__payload',b'__ABYAUTO',vm,payload_size,off,4,0,0,0,0,0,0)
    rebuilt=[];edits=[]
    # Load commands whose offset members point into LINKEDIT.
    fields={2:[8,16],0xb:[32,40,48,56,64,72],0x22:[8,16,24,32,40],0x80000022:[8,16,24,32,40]}
    data_cmds={0x1d,0x1e,0x26,0x29,0x2b,0x2e,0x80000033}
    for oldpos,cmd,raw in cmds:
        b=bytearray(raw)
        ensure(cmd!=0x80000034,'chained fixups require a different relocation implementation')
        if cmd==0x19 and raw[8:24].rstrip(b'\0')==b'__LINKEDIT':
            rebuilt.append(new)
            struct.pack_into('<Q',b,24,vm+size);struct.pack_into('<Q',b,40,off+size)
        for p in fields.get(cmd,[8] if cmd in data_cmds else []):
            value=struct.unpack_from('<I',b,p)[0]
            if value:
                ensure(value>=off,(hex(cmd),p,'offset outside LINKEDIT'))
                struct.pack_into('<I',b,p,value+size)
        if cmd==0x21:ensure(struct.unpack_from('<I',b,16)[0]==0,'encrypted native input')
        if cmd==0x2c:ensure(struct.unpack_from('<I',b,16)[0]==0,'encrypted native input')
        if bytes(b)!=raw:edits.append(dict(command=hex(cmd),old_offset=oldpos,source=raw.hex(),target=bytes(b).hex()))
        rebuilt.append(bytes(b))
    header=b''.join(rebuilt);old_end=32+sum(len(b) for _,_,b in cmds);new_end=32+len(header)
    ensure(not any(native[old_end:new_end]),'new load command exceeds header padding')
    result=bytearray(native[:off]+bytes(size)+native[off:])
    struct.pack_into('<II',result,16,len(rebuilt),len(header));result[32:new_end]=header
    return result,dict(name='__ABYAUTO',file_offset=off,virtual_address=vm,size=size,payload_size=payload_size,old_linkedit_size=fs,header_end=new_end,command_edits=edits)

def runtime_abc_offset(native):
    va=aot.read_u64(native,aot.MAIN_AOT_INFO_OFFSET+24)
    size=aot.read_u64(native,aot.MAIN_AOT_INFO_OFFSET+32)
    matches=[]
    for _,cmd,raw in commands(native):
        if cmd!=0x19:continue
        start,_,offset,length=struct.unpack_from('<QQQQ',raw,24)
        if start<=va and va+size<=start+length:
            matches.append(offset+va-start)
    ensure(len(matches)==1,'runtime ABC pointer is not contained in one mapped segment')
    return matches[0]

def main():
    ensure(not (WORK/'output').exists(),'refusing to overwrite an existing output directory')
    reg=json.loads((WORK/'port.json').read_text(encoding='utf-8'))['source_ipa']
    ipa=Path(reg['ipa']);ensure(sha(ipa.read_bytes())==IPA_HASH,'accepted IPA changed')
    native=(WORK/'baseline-native').read_bytes();swf=(WORK/'baseline.swf').read_bytes()
    ensure(sha(native)==reg['native_sha256'] and sha(swf)==reg['swf_sha256'],'baseline payload mismatch')
    port=json.loads((WORK/'port.json').read_text(encoding='utf-8'))
    wanted={r['method_id'] for r in port['methods']}
    full=(WORK/'abyss-full.abc').read_bytes();full_hash=hashlib.sha1(full).digest()
    objects={};functions={};meta_path=None
    for path in sorted((WORK/'compile').glob('abyss*.o')):
        obj=lief.parse(str(path));objects[path]=obj
        if any(aot.text(s.name).endswith('_284_aotInfo') and s.numberof_sections>0 for s in obj.symbols):meta_path=path
        sect=next((s for s in obj.sections if s.name=='__text'),None)
        ids=[m for m in wanted if sect and any(f':{m}:' in aot.text(s.name) and s.numberof_sections>0 and sect.virtual_address<=s.value<sect.virtual_address+sect.size for s in obj.symbols)]
        if not ids:continue
        sect,syms,rs=aot.parse_object_functions(obj,ids)
        for r in rs:
            ensure(r.size>100,f'compiler emitted stub {r.method_id}')
            functions[r.method_id]=(r,path,sect,syms,aot.parse_relocations(path,sect,syms,r))
    ensure(set(functions)==wanted,('missing methods',wanted-set(functions)))
    meta=objects[meta_path]
    info_name=next(aot.text(s.name) for s in meta.symbols if aot.text(s.name).endswith('_284_aotInfo'))
    info=aot.extract_symbol_bytes(meta,info_name,168);ensure(info[:20]==full_hash,'compiler AOT hash differs')
    abc_name=next(aot.text(s.name) for s in meta.symbols if aot.text(s.name).endswith('_abcBytes'))
    compiled=aot.extract_symbol_bytes(meta,abc_name,struct.unpack_from('<Q',info,32)[0])
    flags=next(aot.text(s.name) for s in meta.symbols if aot.text(s.name).endswith('_methodFlagsArr'))
    ensure(not any(aot.extract_symbol_bytes(meta,flags,aot.MAIN_METHOD_COUNT*4)),'nonzero method flags')
    (WORK/'compiler-stripped.abc').write_bytes(compiled)
    oldlen=aot.read_u64(native,aot.MAIN_AOT_INFO_OFFSET+32)
    oldoff=runtime_abc_offset(native)
    oldabc=native[oldoff:oldoff+oldlen]
    ensure(sha(oldabc)==json.loads((LENS_WORK/'output/build-report.json').read_text(encoding='utf-8'))['runtime_abc_sha256'],'current Lens runtime ABC mismatch')
    baseline=abcfmt.ABC(oldabc);fresh=abcfmt.ABC(compiled)
    ensure(len(fresh.methods)==len(baseline.methods)==aot.MAIN_METHOD_COUNT,'method count drift')
    for pool in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        ensure(freeze(getattr(baseline,pool))==freeze(getattr(fresh,pool)[:len(getattr(baseline,pool))]),'old constant indexes changed: '+pool)
    old_by_mid={b[0]:b for b in baseline.bodies}
    for i,b in enumerate(fresh.bodies):
        if b[0] not in wanted:fresh.bodies[i]=copy.deepcopy(old_by_mid[b[0]])
        else:ensure(activation_traits(view(baseline),old_by_mid[b[0]])==activation_traits(view(fresh),b),'activation metadata changed')
    runtime_abc=fresh.serialize();(WORK/'runtime-stripped.abc').write_bytes(runtime_abc)
    cursor=aot.align(len(runtime_abc),16);positions={};literals={}
    for mid,(r,p,sec,syms,rows) in sorted(functions.items()):
        positions[mid]=cursor;cursor=aot.align(cursor+r.size,16)
    for mid,(r,p,sec,syms,rows) in sorted(functions.items()):
        for row in rows:
            name=row['symbol']
            if name and name.startswith('lCPI') and (p,name) not in literals:
                literals[p,name]=cursor;cursor+=8
    payload_size=aot.align(cursor,16)
    patched,segment=extend_segment(native,payload_size)
    seg_off=segment['file_offset'];seg_va=segment['virtual_address']
    helpers={n:int(v['address'],0) for n,v in json.loads((LEGACY/'runtime-helper-map.json').read_text(encoding='utf-8'))['symbols'].items()}
    helpers[aot.STRICT_EQUALS_SYMBOL]=aot.STRICT_EQUALS_VA
    extra=json.loads((LENS_WORK/'additional-helper.json').read_text(encoding='utf-8'))
    helper_offset=extra['address']-aot.IMAGE_BASE
    ensure(native[helper_offset:helper_offset+32].hex()==extra['native_bytes'],'additional helper proof drift')
    helpers[extra['symbol']]=extra['address']
    named={r.symbol:seg_va+positions[mid] for mid,(r,*_) in functions.items()}
    report_functions=[];audit=[];hooks=[]
    for mid,(r,p,sec,syms,rows) in sorted(functions.items()):
        offset=seg_off+positions[mid];va=seg_va+positions[mid]
        start=r.source_start-sec.virtual_address
        code=bytearray(bytes(sec.content)[start:start+r.size])
        addends={x['source_address']:aot.sign_extend_24(x['raw']&0xffffff) for x in rows if x['type']==10}
        for row in rows:
            typ=row['type'];name=row['symbol'];idx=row['offset'];pc=va+idx
            if typ==10:continue
            if typ==2:
                ensure(name in helpers,('unmapped branch',mid,name))
                target=helpers[name];aot.patch_branch26(code,idx,pc,target)
            elif typ in (3,4,5,6):
                if (p,name) in literals:target=seg_va+literals[p,name]
                elif name in aot.DEPENDENCY_AOT_INFOS:target=aot.DEPENDENCY_AOT_INFOS[name]
                elif name in named:target=named[name]
                elif name==info_name:target=aot.IMAGE_BASE+aot.MAIN_AOT_INFO_OFFSET
                else:raise RuntimeError(('unmapped page symbol',mid,name))
                target+=addends.get(row['source_address'],0)
                if typ in (3,5):aot.patch_adrp(code,idx,pc,target)
                else:aot.patch_pageoff12(code,idx,target,relax_got_load=typ==6)
            else:raise RuntimeError(('unsupported relocation',typ,name))
            audit.append(dict(method_id=mid,offset=idx,pc=pc,type=typ,symbol=name,target=target))
        patched[offset:offset+r.size]=code
        table=aot.MAIN_METHOD_TABLE_OFFSET+mid*8;old_va=aot.read_u64(native,table);canonical=old_va-aot.IMAGE_BASE
        ensure(0<=canonical<seg_off-4,'old entry outside original TEXT/DATA')
        ensure(struct.unpack_from('<I',native,canonical)[0]&0x7c000000!=0x14000000,'target already has entry hook requiring prior-lineage audit')
        aot.write_unconditional_branch(patched,canonical,old_va,va);aot.write_u64(patched,table,va)
        hooks.append(dict(method_id=mid,offset=canonical,old_bytes=native[canonical:canonical+4].hex(),target=va))
        report_functions.append(dict(method_id=mid,symbol=r.symbol,object=str(p),object_sha256=sha(p.read_bytes()),size=r.size,file_offset=offset,virtual_address=va,canonical_offset=canonical,code_sha256=sha(code)))
    literal_report=[]
    for (p,name),rel in literals.items():
        data=aot.extract_symbol_bytes(objects[p],name,8);off=seg_off+rel
        patched[off:off+8]=data;literal_report.append(dict(object=str(p),symbol=name,file_offset=off,virtual_address=seg_va+rel,bytes=data.hex()))
    patched[seg_off:seg_off+len(runtime_abc)]=runtime_abc
    patched[aot.MAIN_AOT_INFO_OFFSET:aot.MAIN_AOT_INFO_OFFSET+20]=full_hash
    aot.write_u64(patched,aot.MAIN_AOT_INFO_OFFSET+24,seg_va)
    aot.write_u64(patched,aot.MAIN_AOT_INFO_OFFSET+32,len(runtime_abc))
    new_swf=aot.replace_main_swf_hash(swf,native[aot.MAIN_AOT_INFO_OFFSET:aot.MAIN_AOT_INFO_OFFSET+20],full_hash)
    for name,(a,b) in common.PROTECTED_RANGES.items():ensure(native[a:b]==patched[a:b],'prior feature changed: '+name)
    output=WORK/'output';output.mkdir(exist_ok=True)
    out=output/'StarPoint-iOS-1.8.4-abyss-autostart-lens-20260909-unsigned.ipa'
    ensure(not out.exists(),'refusing to overwrite IPA')
    (output/'worldflipper').write_bytes(patched);(output/'worldflipper_ios_release.swf').write_bytes(new_swf)
    with zipfile.ZipFile(ipa) as z,zipfile.ZipFile(out,'w',allowZip64=True) as y:
        for zi in z.infolist():
            data=patched if zi.filename==reg['native_member'] else new_swf if zi.filename==reg['swf_member'] else z.read(zi.filename)
            y.writestr(common.clone_zipinfo(zi),data)
        y.comment=z.comment
    report=dict(status='unsigned_candidate_pending_independent_verification',baseline_runtime_abc_offset=oldoff,source_ipa=reg,output_ipa=str(out),ipa_sha256=sha(out.read_bytes()),native_sha256=sha(patched),swf_sha256=sha(new_swf),full_abc_sha256=sha(full),full_abc_sha1=full_hash.hex(),runtime_abc_sha256=sha(runtime_abc),runtime_abc_size=len(runtime_abc),metadata_object=str(meta_path),segment=segment,functions=report_functions,hooks=hooks,literals=literal_report,relocations=audit,methods=port['methods'],title_cntips_b_unchanged=True)
    dump(output/'build-report.json',report)
    print(json.dumps({k:report[k] for k in ('status','output_ipa','ipa_sha256','native_sha256','swf_sha256')},indent=2))
    print('native functions',len(functions),'relocations',len(audit),'new RX bytes',segment['size'])

if __name__=='__main__':main()
