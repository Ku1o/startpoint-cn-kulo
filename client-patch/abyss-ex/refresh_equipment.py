"""Refresh the same-size equipment helper in an already reserved release."""
from release_common import *

def main():
    gate=module('ex_same_size_gate',HERE.parent/'ios-abyss-equipment/build_ios_abyss_multibothboss_level120.py')
    assembler,_,_=gate.load_assembler(None)
    old=gate.build_gate_helper()
    needle='mov w9, #0xaec3\nmovk w9, #0xa, lsl #16\ncmp w0, w9\nb.eq allow_deep'
    assert old.count(needle)==1
    replacement='sub w9, w0, #0xaa, lsl #12\nsub w9, w9, #0xec3\ncmp w9, #1\nb.ls allow_deep'
    before=bytes(assembler.asm(old,addr=gate.IMAGE_BASE+gate.HELPER_OFFSET)[0])
    after=bytes(assembler.asm(old.replace(needle,replacement),addr=gate.IMAGE_BASE+gate.HELPER_OFFSET)[0])
    assert len(before)==len(after)==548
    native=(WORK/'baseline-native').read_bytes()
    assert native[gate.HELPER_OFFSET:gate.HELPER_OFFSET+548]==before
    changed=[i for i in range(0,548,4) if before[i:i+4]!=after[i:i+4]]
    assert len(changed)==4 and changed==list(range(changed[0],changed[0]+16,4))
    # Every signed 32-bit event identifier around the boundary, plus wrap cases.
    for value in list(range(699900,700300))+[-2147483648,-1,0,2147483647]:
        assert (((value-0xaa000-0xec3)&0xffffffff)<=1)==(value in (700099,700100))
    (PREP/'abyss-ex-ios-equipment.bin').write_bytes(after)
    report=read(PREP/'preparation.json')
    report['ios']['equipment_helper'].update(new_size=len(after),sha256=sha(after))
    dump(PREP/'preparation.json',report)
    port=read(WORK/'port.json');port['equipment']=report['ios']['equipment_helper'];dump(WORK/'port.json',port)
    print('Same-size 548-byte gate verified; exactly four instructions changed.')

if __name__=='__main__':main()
