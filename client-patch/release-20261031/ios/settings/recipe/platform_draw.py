"""Retain iOS v3/v6 dispatch/type gate before the newly compiled original draw ID."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import hashlib,struct

BASE=0x100000000
MID=66181
GATE_SITE=0x3d691e0
ISLAND=0x3d69200
ISLAND_SIZE=88
STOCK_DRAW=0x102b990d4
CLEANUP_START=0x3d6948c
CLEANUP_END=0x3d694c0
WRAPPER_START=0x3d69180
WRAPPER_END=0x3d694c4
INFO=104549248
LEGACY_TABLE=0x62c0780
BASE_NATIVE_SHA='bcdf74c7f37aa22e4caa4f0abd1891947c70098467b0756413bd26f12c0a9ee1'

def sha(data):return hashlib.sha256(data).hexdigest()
def require(value,msg):
    if not value:raise ValueError(msg)
def branch(pc,target,link=False):
    delta=target-pc;require(delta%4==0 and -(1<<27)<=delta<(1<<27),'branch range/alignment')
    return struct.pack('<I',(0x94000000 if link else 0x14000000)|((delta//4)&0x3ffffff))
def branch_target(word,pc):
    require(word&0xfc000000 in (0x14000000,0x94000000),'not branch')
    imm=word&0x3ffffff;return pc+((imm-(1<<26)) if imm&(1<<25) else imm)*4
def tailjump(pc,target):
    delta=(target>>12)-(pc>>12);require(-(1<<20)<=delta<(1<<20),'ADRP range')
    imm=delta&0x1fffff
    return struct.pack('<III',0x90000010|((imm&3)<<29)|((imm>>2)<<5),0x91000210|((target&4095)<<10),0xd61f0200)

def plan(baseline,target):
    require(sha(baseline)==BASE_NATIVE_SHA,'current compact native identity required')
    require(baseline[GATE_SITE:GATE_SITE+4]==bytes.fromhex('786740f9'),'verified v6 characterTags load preimage')
    require(baseline[GATE_SITE-8:GATE_SITE-4]==branch(BASE+GATE_SITE-8,0x1030199e0,True),'v6 type-gate BL preimage')
    # The entire 13-instruction cleanup is copied. Its sole relative BL must
    # be rebound at the new address. x0/x1 are restored from saved x19/x20
    # before those callee-saved registers are popped.
    cleanup=bytearray(baseline[CLEANUP_START:CLEANUP_END]);require(len(cleanup)==52,'cleanup extent')
    require(cleanup[16:24]==bytes.fromhex('e00313aae10314aa'),'cleanup receiver/MethodEnv moves')
    word=struct.unpack_from('<I',cleanup,4)[0]
    require(word&0xfc000000==0x94000000,'cleanup BL')
    destination=branch_target(word,BASE+CLEANUP_START+4)
    require(destination==0x100a26814,'unexpected GC-core cleanup call')
    cleanup[4:8]=branch(BASE+ISLAND+4,destination,True)
    # Invoke the extension while the existing wrapper frame/GC MethodFrame
    # remains live. The original cleanup then restores ABI args and LR exactly.
    call=bytearray(tailjump(BASE+ISLAND+8,target));call[8:12]=struct.pack('<I',0xd63f0200)
    cleanup[4:8]=branch(BASE+ISLAND+24,destination,True)
    replacement=bytes.fromhex('e00313aae10314aa')+bytes(call)+bytes(cleanup)+branch(BASE+ISLAND+72,STOCK_DRAW)+bytes.fromhex('1f2003d5')*3
    require(len(replacement)==ISLAND_SIZE,'bridge must be exactly 88 bytes')
    return [dict(offset=GATE_SITE,size=4,before=baseline[GATE_SITE:GATE_SITE+4].hex(),after=branch(BASE+GATE_SITE,BASE+ISLAND).hex()),
            dict(offset=ISLAND,size=ISLAND_SIZE,before=baseline[ISLAND:ISLAND+ISLAND_SIZE].hex(),after=replacement.hex())]

def apply(baseline,linked,report,offset_of):
    functions=[f for f in report['functions'] if f['method']==MID];require(len(functions)==1,'one original-ID draw function required')
    target=functions[0]['address']
    # New direct cross-calls would bypass the retained type gate.
    names={r['symbol'] for r in report['relocations'] if f':{MID}:' in r['symbol']}
    require(not names,'new function directly calls draw and would bypass the gate')
    result=bytearray(linked);restored=[]
    active=struct.unpack_from('<Q',baseline,INFO+48)[0]
    for off in (offset_of(baseline,active+MID*8),LEGACY_TABLE+MID*8):
        result[off:off+8]=baseline[off:off+8];restored.append(off)
    hooks=[r for r in report['hooks'] if r['method']==MID]
    for hook in hooks:
        off=hook['offset'];result[off:off+4]=baseline[off:off+4]
    patches=plan(baseline,target)
    for row in patches:
        off=row['offset'];result[off:off+row['size']]=bytes.fromhex(row['after'])
    report['hooks']=[r for r in report['hooks'] if r['method']!=MID]
    report['table_sites']=[off for off in report['table_sites'] if off not in restored]
    report['platform_draw']=dict(method=MID,compiled_function=target,retained_active_table_entry=struct.unpack_from('<Q',baseline,offset_of(baseline,active+MID*8))[0],
        entry_policy='retain v3 MethodInfo repair and v6 concrete-type gate; successful gate calls only guarded new dual-form prefix inside original live wrapper frame/GC MethodFrame, then original cleanup tailcalls unchanged stock draw',
        bridge_file_range=[ISLAND,ISLAND+ISLAND_SIZE],patches=patches,restored_default_hooks=hooks,restored_table_sites=restored,
        preserved_cleanup_sha256=sha(baseline[CLEANUP_START:CLEANUP_END]),native_executed=False)
    verify(baseline,result,report,offset_of)
    return bytes(result)

def verify(baseline,actual,report,offset_of):
    record=report['platform_draw'];function,=[f for f in report['functions'] if f['method']==MID]
    require(record['compiled_function']==function['address'],'draw target changed')
    patches=plan(baseline,function['address'])
    require(patches==record['patches'],'stale draw patch plan')
    for row in patches:
        require(actual[row['offset']:row['offset']+row['size']]==bytes.fromhex(row['after']),'draw patch payload differs')
    protected=[(WRAPPER_START,WRAPPER_END),(0x30199c0,0x3019a40),(0x2b9c070,0x2b9c088),(0x2b990d4,0x2b9a53c),(0x3d694d0,0x3d6965c),(0x3a4561c,0x3a45620)]
    allowed={(row['offset']+i) for row in patches for i in range(row['size'])}
    require(all(actual[i]==baseline[i] for lo,hi in protected for i in range(lo,hi) if i not in allowed),'v3/v6 constructor, type gate, fallback or original draw changed')
    active=struct.unpack_from('<Q',baseline,INFO+48)[0]
    for off in (offset_of(baseline,active+MID*8),LEGACY_TABLE+MID*8):require(actual[off:off+8]==baseline[off:off+8],'draw table entry no longer retains wrapper')
    require(not any(r['method']==MID for r in report['hooks']),'ordinary draw entry detour remains')
    return dict(status='v3_v6_gated_draw_bridge_verified',bridge_file_start=ISLAND,bridge_file_end=ISLAND+ISLAND_SIZE,
                original_method_id=MID,new_method_env_used=False,retained_receiver_and_method_env=True,stock_native_tail_target=STOCK_DRAW,bridge_stack_alignment=16)
