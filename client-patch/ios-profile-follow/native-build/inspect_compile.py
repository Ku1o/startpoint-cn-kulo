from prepare import ROOT, LEGACY
import sys, json, struct, hashlib
sys.path.insert(0,str(LEGACY));sys.path.insert(0,r'F:\codex\tools\ios-re-libs')
import lief
import build_ios_rush_leaderboard_ipa as aot
from stitch_ios_stripped_abc import body_records
from restore_ios_method_infos import constant_pool_end, method_info_end

targets=[78115,87249,87420]
helper_map=json.loads((LEGACY/'runtime-helper-map.json').read_text('utf-8'))['symbols']
helper_map[aot.STRICT_EQUALS_SYMBOL]={}
result={}
for obj in sorted((ROOT/'compile').glob('profile-follow*.o')):
    b=lief.parse(str(obj))
    if any(aot.text(s.name).endswith('_284_aotInfo') and s.numberof_sections>0 for s in b.symbols):
        metadata_path=obj
    sect=next((s for s in b.sections if s.name=='__text'),None)
    ids=[m for m in targets if sect and any(f':{m}:' in aot.text(s.name) and s.numberof_sections>0 and sect.virtual_address <= s.value < sect.virtual_address+sect.size for s in b.symbols)]
    if not ids: continue
    section,symbols,records=aot.parse_object_functions(b,ids)
    for r in records:
        rows=aot.parse_relocations(obj,section,symbols,r)
        result[str(r.method_id)]={'object':obj.name,'symbol':r.symbol,'size':r.size,'missing_branches':sorted(set(row['symbol'] for row in rows if row['type']==2 and row['symbol'] not in helper_map)),'page_symbols':sorted(set(row['symbol'] for row in rows if row['type'] in [3,4,5,6]))}
meta=lief.parse(str(metadata_path))
result['metadata_object']=metadata_path.name
info=next(s for s in meta.symbols if aot.text(s.name).endswith('_284_aotInfo'))
infob=aot.extract_symbol_bytes(meta,aot.text(info.name),168)
assert infob[:20]==hashlib.sha1((ROOT/'profile-full.abc').read_bytes()).digest()
abc_sym=next(s for s in meta.symbols if aot.text(s.name).endswith('_abcBytes'))
compiled=aot.extract_symbol_bytes(meta,aot.text(abc_sym.name),struct.unpack_from('<Q',infob,32)[0])
(ROOT/'compiler-stripped.abc').write_bytes(compiled)
base=(ROOT/'baseline-stripped.abc').read_bytes()
be,_,bs=body_records(base);ce,_,cs=body_records(compiled)
result['stripped_prefix_identical']=base[:be]==compiled[:ce]
result['target_stripped_records']={str(a[0]):dict(baseline=a[1].hex(),compiled=b[1].hex()) for a,b in zip(bs,cs) if a[0] in targets}
native=(ROOT/'baseline-worldflipper').read_bytes()
result['original_entries']={str(m):hex(aot.read_u64(native,aot.MAIN_METHOD_TABLE_OFFSET+m*8)) for m in targets}
result['available_space_zero']=set(native[0x5f28f40:0x5f7f300])=={0}
result['space_nonzero_bytes']=sum(x!=0 for x in native[0x5f28f40:0x5f7f300])
(ROOT/'compile-inspection.json').write_text(json.dumps(result,indent=2),'utf-8')
print(json.dumps(result,indent=2))
