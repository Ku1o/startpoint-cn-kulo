"""Add exactly three native profile methods to the hash-locked accepted IPA."""
from pathlib import Path
import hashlib, json, struct, sys, zipfile, re
from prepare import ROOT, LEGACY
sys.path.insert(0,str(LEGACY))
sys.path.insert(0,r'F:\codex\tools\ios-re-libs')
sys.path.insert(0,r'F:\codex\ios-rush-navigation-port-20260907')
import lief
import build_ios_rush_leaderboard_ipa as aot
import build_incremental_ipa as common
from stitch_ios_stripped_abc import body_records

TARGETS=[78115,87249,87420]
COMPILER_ONLY=[87260,87421]
START=0x5f28f40
LIMIT=0x5f7f300
IPA=Path(r'F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-r12b-navigation-abyss-multibothboss-level120-test-unsigned.ipa')

def sha(x): return hashlib.sha256(x).hexdigest()
def ensure(ok,msg):
    if not ok: raise RuntimeError(msg)

def main():
    ensure(sha(IPA.read_bytes())=='f44710abcbb6c657f25a205b8d72ca597be551f19e2f7b02a9591605339dcc40','IPA base mismatch')
    with zipfile.ZipFile(IPA) as z:
        native=z.read(common.MACHO_MEMBER);swf=z.read(common.SWF_MEMBER)
    ensure(sha(native)=='530db20daa356162b617c5d853335d5c4d2a09965fd89c2151a1dca03bccc1e8','native base mismatch')
    ensure(sha(swf)=='2b6d7d9c4420872245053bc4150a913a208a589fc282ec0f65a43957618de6f9','SWF base mismatch')
    full=(ROOT/'profile-full.abc').read_bytes()
    old_full=(ROOT/'baseline-full.abc').read_bytes()
    old_hash=native[aot.MAIN_AOT_INFO_OFFSET:aot.MAIN_AOT_INFO_OFFSET+20]
    ensure(hashlib.sha1(old_full).digest()==old_hash,'baseline full ABC does not match native AOT hash')
    old_pos,_,old_records=body_records(old_full);pos,_,records_new=body_records(full)
    ensure(old_full[:old_pos]==full[:pos], 'constant pools or definitions changed')
    changes=[a[0] for a,b in zip(old_records,records_new) if a!=b]
    ensure(changes==sorted(TARGETS+COMPILER_ONLY),'unexpected compiler method changes')
    old_abc=(ROOT/'baseline-stripped.abc').read_bytes()
    ensure(native[aot.MAIN_ABC_OFFSET:aot.MAIN_ABC_OFFSET+len(old_abc)]==old_abc,'stripped ABC base mismatch')

    inspection=json.loads((ROOT/'compile-inspection.json').read_text('utf-8'))
    objects={}
    records=[]
    relocation_rows={}
    for mid in TARGETS:
        objpath=ROOT/'compile'/inspection[str(mid)]['object']
        if objpath not in objects: objects[objpath]=lief.parse(str(objpath))
        obj=objects[objpath]
        sect,syms,rs=aot.parse_object_functions(obj,[mid])
        r=rs[0]
        records.append((r,objpath,sect,syms))
        relocation_rows[mid]=aot.parse_relocations(objpath,sect,syms,r)
        ensure(r.size>100, f'method {mid} is a stub')
    meta=lief.parse(str(ROOT/'compile'/inspection['metadata_object']))
    info=next(s for s in meta.symbols if aot.text(s.name).endswith('_284_aotInfo'))
    infob=aot.extract_symbol_bytes(meta,aot.text(info.name),168)
    ensure(infob[:20]==hashlib.sha1(full).digest(),'compiled AOT hash mismatch')
    flags=next(s for s in meta.symbols if aot.text(s.name).endswith('_methodFlagsArr'))
    ensure(not any(aot.extract_symbol_bytes(meta,aot.text(flags.name),aot.MAIN_METHOD_COUNT*4)),'unexpected compiler flags')
    ensure(inspection['stripped_prefix_identical'],'compiled metadata definitions changed')
    for mid in TARGETS+COMPILER_ONLY:
        compiled=dict(body_records((ROOT/'compiler-stripped.abc').read_bytes())[2])[mid]
        ensure(compiled==dict(body_records(old_abc)[2])[mid],f'AIR body metadata differs for {mid}')

    cursor=START
    for r,_,_,_ in records:
        r.destination_offset=cursor
        cursor=aot.align(cursor+r.size,16)
    literals={}
    for r,objpath,_,_ in records:
        for row in relocation_rows[r.method_id]:
            name=row['symbol']
            if name and name.startswith('lCPI'):
                key=(objpath,name)
                if key not in literals: literals[key]=cursor;cursor+=8
    end=aot.align(cursor,16)
    ensure(end<=LIMIT,'patch overlaps activation metadata')
    ensure(not any(native[START:end]),'patch would overwrite existing code')
    helper_json=json.loads((LEGACY/'runtime-helper-map.json').read_text('utf-8'))['symbols']
    helpers={n:int(v['address'],0) for n,v in helper_json.items()}
    helpers[aot.STRICT_EQUALS_SYMBOL]=aot.STRICT_EQUALS_VA
    name_records={r.symbol:r for r,_,_,_ in records}
    patched=bytearray(native)
    report_funcs=[];relocation_audit=[]
    prior=json.loads(Path(r'F:\codex\ios-rush-navigation-port-20260907\output\build-report.json').read_text('utf-8'))
    prior_funcs={row['method_id']:row for row in prior['aot_functions']}
    hooks=[]
    for r,objpath,sect,syms in records:
        source_offset=r.source_start-sect.virtual_address
        code=bytearray(bytes(sect.content)[source_offset:source_offset+r.size])
        rows=relocation_rows[r.method_id]
        addends={row['source_address']:aot.sign_extend_24(row['raw']&0xffffff) for row in rows if row['type']==10}
        for row in rows:
            typ=row['type'];name=row['symbol'];off=row['offset'];pc=r.destination_va+off
            if typ==10:continue
            if typ==2:
                ensure(name in helpers,f'unmapped helper {name}')
                target=helpers[name]
                aot.patch_branch26(code,off,pc,target)
            elif typ in (3,4,5,6):
                if (objpath,name) in literals: target=aot.IMAGE_BASE+literals[(objpath,name)]
                elif name in aot.DEPENDENCY_AOT_INFOS:target=aot.DEPENDENCY_AOT_INFOS[name]
                elif name in name_records:target=name_records[name].destination_va
                else:raise RuntimeError(f'unmapped page symbol {name}')
                target+=addends.get(row['source_address'],0)
                if typ in (3,5):aot.patch_adrp(code,off,pc,target)
                else:aot.patch_pageoff12(code,off,target,relax_got_load=typ==6)
            else:raise RuntimeError(f'unsupported relocation type {typ}')
            relocation_audit.append(dict(method_id=r.method_id,offset=off,pc=hex(pc),type=typ,symbol=name,target=hex(target)))
        patched[r.destination_offset:r.destination_offset+r.size]=code
        table_offset=aot.MAIN_METHOD_TABLE_OFFSET+r.method_id*8
        old_entry=aot.read_u64(native,table_offset)
        entry_offsets=[old_entry-aot.IMAGE_BASE]
        if r.method_id in prior_funcs:
            old=prior_funcs[r.method_id]
            ensure(old_entry==int(old['destination_va'],0),'prior Rush entry drifted')
            entry_offsets.append(int(old['canonical_offset'],0))
        for off in sorted(set(entry_offsets)):
            aot.write_unconditional_branch(patched,off,aot.IMAGE_BASE+off,r.destination_va)
            hooks.append(dict(method_id=r.method_id,offset=hex(off),old_bytes=native[off:off+4].hex(),target=hex(r.destination_va)))
        aot.write_u64(patched,table_offset,r.destination_va)
        report_funcs.append(dict(method_id=r.method_id,symbol=r.symbol,object=str(objpath),object_sha256=sha(objpath.read_bytes()),size=r.size,destination_offset=hex(r.destination_offset),destination_va=hex(r.destination_va),old_entry_va=hex(old_entry),code_sha256=sha(code)))
    for (p,name),offset in literals.items():
        patched[offset:offset+8]=aot.extract_symbol_bytes(objects[p],name,8)
    patched[aot.MAIN_AOT_INFO_OFFSET:aot.MAIN_AOT_INFO_OFFSET+20]=hashlib.sha1(full).digest()
    patched=bytes(patched)
    new_swf=aot.replace_main_swf_hash(swf,old_hash,hashlib.sha1(full).digest())
    ensure(common.macho_layout(native)==common.macho_layout(patched),'Mach-O layout changed')
    changed_table=[m for m in range(aot.MAIN_METHOD_COUNT) if native[aot.MAIN_METHOD_TABLE_OFFSET+m*8:aot.MAIN_METHOD_TABLE_OFFSET+m*8+8]!=patched[aot.MAIN_METHOD_TABLE_OFFSET+m*8:aot.MAIN_METHOD_TABLE_OFFSET+m*8+8]]
    ensure(changed_table==TARGETS,'unexpected method-table changes')
    windows=[(START,end),(aot.MAIN_AOT_INFO_OFFSET,aot.MAIN_AOT_INFO_OFFSET+20)]
    windows += [(int(h['offset'],0),int(h['offset'],0)+4) for h in hooks]
    windows += [(aot.MAIN_METHOD_TABLE_OFFSET+m*8,aot.MAIN_METHOD_TABLE_OFFSET+m*8+8) for m in TARGETS]
    restored=bytearray(patched)
    for start,stop in windows:restored[start:stop]=native[start:stop]
    ensure(bytes(restored)==native,'native changes outside three methods/hash/allocated code')
    for name,(start,stop) in common.PROTECTED_RANGES.items():
        ensure(native[start:stop]==patched[start:stop],f'protected range changed: {name}')
    ensure(native[aot.MAIN_ABC_OFFSET:aot.MAIN_ABC_OFFSET+len(old_abc)]==patched[aot.MAIN_ABC_OFFSET:aot.MAIN_ABC_OFFSET+len(old_abc)],'runtime ABC changed')
    output=ROOT/'output';output.mkdir(exist_ok=True)
    out_ipa=output/'StarPoint-iOS-1.8.4-profile-follow-self-20260908-unsigned.ipa'
    ensure(not out_ipa.exists(),'output already exists')
    (output/'worldflipper').write_bytes(patched)
    (output/'worldflipper_ios_release.swf').write_bytes(new_swf)
    with zipfile.ZipFile(IPA) as source,zipfile.ZipFile(out_ipa,'w',allowZip64=True) as z:
        for info in source.infolist():
            data=patched if info.filename==common.MACHO_MEMBER else new_swf if info.filename==common.SWF_MEMBER else source.read(info.filename)
            z.writestr(common.clone_zipinfo(info),data)
        z.comment=source.comment
    report=dict(status='built_unsigned_candidate_pending_independent_verification',baseline_ipa=str(IPA),baseline_ipa_sha256=sha(IPA.read_bytes()),output_ipa=str(out_ipa),output_ipa_sha256=sha(out_ipa.read_bytes()),native_sha256=sha(patched),swf_sha256=sha(new_swf),native_method_changes=TARGETS,compiler_only_lifecycles=COMPILER_ONLY,full_abc_sha256=sha(full),full_abc_sha1=hashlib.sha1(full).hexdigest(),runtime_stripped_abc_unchanged=True,code_start=hex(START),code_end=hex(end),functions=report_funcs,hooks=hooks,relocations=relocation_audit,literals=[dict(object=str(p),symbol=n,offset=hex(o),bytes=patched[o:o+8].hex()) for (p,n),o in literals.items()],allowed_windows=windows,title_cntips_b_unchanged=True)
    (output/'build-report.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['relocations','functions','allowed_windows']},indent=2))

if __name__=='__main__':main()
