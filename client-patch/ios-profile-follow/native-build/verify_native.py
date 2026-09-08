"""Decode final ARM64 instructions and audit IPA preservation independently."""
from pathlib import Path
import json, struct, hashlib, sys, zipfile, plistlib, argparse
from prepare import ROOT,LEGACY
sys.path.insert(0,str(LEGACY));sys.path.insert(0,r'F:\codex\tools\ios-re-libs')
import lief
import build_ios_rush_leaderboard_ipa as aot
from stitch_ios_stripped_abc import body_records

TARGETS=[78115,87249,87420]
TABLE=0x62c0780;AOT=0x63b4b80;BASE=0x100000000
def check(b,msg):
    if not b:raise RuntimeError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def sx(n,bits):return n-(1<<bits) if n&(1<<(bits-1)) else n
def word(b,o):return struct.unpack_from('<I',b,o)[0]
def branch(w,pc):
    check(w&0x7c000000==0x14000000,'expected B/BL')
    return pc+(sx(w&0x3ffffff,26)<<2)
def page(w,pc):
    check(w&0x9f000000==0x90000000,'expected ADRP')
    return (pc&~4095)+(sx(((w>>5)&0x7ffff)<<2|((w>>29)&3),21)<<12)
def low(w):
    immediate=(w>>10)&4095
    if w&0x7f000000==0x11000000:return immediate
    if w&0x3b000000==0x39000000:return immediate*(1<<((w>>30)&3))
    raise RuntimeError('expected ADD/load/store')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ipa',type=Path,help='verify the exact candidate after moving it to the delivery directory')
    args=parser.parse_args()
    report=json.loads((ROOT/'output/build-report.json').read_text('utf-8'))
    src=Path(report['baseline_ipa']);dst=args.ipa or Path(report['output_ipa'])
    check(sha(src.read_bytes())=='f44710abcbb6c657f25a205b8d72ca597be551f19e2f7b02a9591605339dcc40','wrong accepted base')
    check(sha(dst.read_bytes())==report['output_ipa_sha256'],'IPA hash mismatch')
    changed=[]
    with zipfile.ZipFile(src) as x,zipfile.ZipFile(dst) as y:
        check(x.namelist()==y.namelist() and len(y.namelist())==3568,'ZIP inventory changed')
        check(y.testzip() is None,'ZIP CRC failed')
        for a,b in zip(x.infolist(),y.infolist()):
            for k in ['filename','date_time','compress_type','comment','extra','create_system','create_version','extract_version','flag_bits','volume','internal_attr','external_attr']:
                check(getattr(a,k)==getattr(b,k),f'ZIP metadata changed: {a.filename}:{k}')
            if x.read(a.filename)!=y.read(b.filename):changed.append(a.filename)
        check(set(changed)=={'Payload/worldflipper.app/worldflipper','Payload/worldflipper.app/worldflipper_ios_release.swf'},'non-target IPA member changed')
        check(not any('/_CodeSignature/' in n or n.endswith('/embedded.mobileprovision') for n in y.namelist()),'unexpected signing artifacts')
        old=x.read('Payload/worldflipper.app/worldflipper');new=y.read('Payload/worldflipper.app/worldflipper')
        oswf=x.read('Payload/worldflipper.app/worldflipper_ios_release.swf');nswf=y.read('Payload/worldflipper.app/worldflipper_ios_release.swf')
        plist=plistlib.loads(y.read('Payload/worldflipper.app/Info.plist'))
    check(len(old)==len(new)==108757200,'native size changed')
    full=(ROOT/'profile-full.abc').read_bytes();base_full=(ROOT/'baseline-full.abc').read_bytes()
    old_hash=hashlib.sha1(base_full).digest();new_hash=hashlib.sha1(full).digest()
    check(old[AOT:AOT+20]==old_hash and new[AOT:AOT+20]==new_hash,'AOT hashes inconsistent')
    _,op=aot.decompress_swf(oswf);_,np=aot.decompress_swf(nswf)
    check(op.count(old_hash)==1 and op.replace(old_hash,new_hash)==np,'SWF changed beyond AOT hash; title/assets not preserved')
    a,_,ar=body_records(base_full);b,_,br=body_records(full)
    check(base_full[:a]==full[:b],'compiler pools/definitions drift')
    check([l[0] for l,r in zip(ar,br) if l!=r]==[78115,87249,87260,87420,87421],'compiler methods changed beyond targets/lifecycle context')
    oldtab=struct.unpack_from('<101071Q',old,TABLE);newtab=struct.unpack_from('<101071Q',new,TABLE)
    check([i for i,(l,r) in enumerate(zip(oldtab,newtab)) if l!=r]==TARGETS,'unexpected native table changes')
    info=json.loads((ROOT/'compile-inspection.json').read_text('utf-8'))
    objpath=ROOT/'compile'/info['78115']['object'];obj=lief.parse(str(objpath))
    sect,symbols,records=aot.parse_object_functions(obj,TARGETS)
    functions={f['method_id']:f for f in report['functions']}
    check(set(functions)==set(TARGETS),'unexpected report methods')
    destinations={r.symbol:newtab[r.method_id] for r in records}
    literals={l['symbol']:BASE+int(l['offset'],0) for l in report['literals']}
    helpers={name:int(row['address'],0) for name,row in json.loads((LEGACY/'runtime-helper-map.json').read_text('utf-8'))['symbols'].items()}
    helpers[aot.STRICT_EQUALS_SYMBOL]=aot.STRICT_EQUALS_VA
    count=0
    for r in records:
        fn=functions[r.method_id];off=newtab[r.method_id]-BASE
        check(off==int(fn['destination_offset'],0) and r.size==fn['size'],'function geometry mismatch')
        original=bytes(sect.content)[r.source_start-sect.virtual_address:r.source_end-sect.virtual_address]
        embedded=new[off:off+r.size];mask=bytearray(embedded)
        rows=aot.parse_relocations(objpath,sect,symbols,r)
        addends={x['source_address']:sx(x['raw']&0xffffff,24) for x in rows if x['type']==10}
        for row in rows:
            typ=row['type'];name=row['symbol'];offset=row['offset'];pc=BASE+off+offset
            if typ==10:continue
            w=word(embedded,offset)
            if typ==2:
                check(branch(w,pc)==helpers[name],f'bad branch: {name}')
                check((w&0xfc000000)==(word(original,offset)&0xfc000000),'B/BL semantics changed')
            else:
                target=(literals.get(name) or destinations.get(name) or aot.DEPENDENCY_AOT_INFOS.get(name))
                check(target is not None,f'unmapped symbol {name}')
                target+=addends.get(row['source_address'],0)
                check((page(w,pc)==target&~4095) if typ in [3,5] else (low(w)==target&4095),f'bad page relocation {name}')
            mask[offset:offset+4]=original[offset:offset+4];count+=1
        check(bytes(mask)==original,f'non-relocation instructions changed in {r.method_id}')
        check(sha(embedded)==fn['code_sha256'],'native function hash mismatch')
    for l in report['literals']:
        off=int(l['offset'],0)
        check(new[off:off+8]==aot.extract_symbol_bytes(obj,l['symbol'],8),'constant literal differs')
    expected_hooks={0x311f308:78115,0x5f207e0:78115,0x361f198:87249,0x362b81c:87420}
    for off,mid in expected_hooks.items():
        check(word(new,off)&0xfc000000==0x14000000 and branch(word(new,off),BASE+off)==newtab[mid],'entry trampoline mismatch')
    start=0x5f28f40;end=int(report['code_end'],0)
    check(start<=end<0x5f7f300 and not any(old[start:end]),'code overwrote existing data')
    allowed=[(start,end),(AOT,AOT+20)]+[(o,o+4) for o in expected_hooks]+[(TABLE+m*8,TABLE+m*8+8) for m in TARGETS]
    restored=bytearray(new)
    for start,end in allowed:restored[start:end]=old[start:end]
    check(bytes(restored)==old,'unexpected modified bytes, including protected previous fixes/title')
    ob=lief.parse(str(ROOT/'baseline-worldflipper'));nb=lief.parse(str(ROOT/'output/worldflipper'))
    check({r.address for r in ob.relocations}=={r.address for r in nb.relocations},'dyld rebases changed')
    rebases={r.address for r in nb.relocations}
    check({BASE+TABLE+m*8 for m in TARGETS}<=rebases,'native method pointers missing ASLR rebases')
    check([(s.name,s.virtual_address,s.virtual_size,s.file_offset,s.file_size) for s in ob.segments]==[(s.name,s.virtual_address,s.virtual_size,s.file_offset,s.file_size) for s in nb.segments],'segment geometry changed')
    final=dict(status='offline_verified_unsigned_candidate',acceptance='awaiting_user_device_acceptance',ipa_sha256=sha(dst.read_bytes()),native_sha256=sha(new),swf_sha256=sha(nswf),changed_members=changed,zip_members_verified=3568,method_table_changed_ids=TARGETS,decoded_relocations_verified=count,native_changes_outside_allowed_windows=0,all_previous_non_target_native_bytes_preserved=True,all_runtime_abc_bytes_preserved=True,title_cntips_b_unchanged=True,dyld_rebases_preserved=True,info_plist_preserved=True,bundle_identifier=plist['CFBundleIdentifier'],app_version=plist['CFBundleShortVersionString'],build_version=plist['CFBundleVersion'])
    (ROOT/'output/verification-report.json').write_text(json.dumps(final,indent=2)+'\n','utf-8')
    print(json.dumps(final,indent=2))

if __name__=='__main__':main()
