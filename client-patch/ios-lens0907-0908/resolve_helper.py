"""Prove the additional String conversion helper against the AIR runtime object."""
from prepare import *
import struct
sys.path[:0]=[str(LEGACY),r'F:\codex\tools\ios-re-libs']
import lief
import build_ios_rush_leaderboard_ipa as aot

name='__ZN8halfmoon5Stubs16do_abc_convert_sEPN7avmplus11MethodFrameEx'
path=LEGACY/'runtime-archive-members/hm-stubs.o'
obj=lief.parse(str(path));symbols={aot.text(s.name):s for s in obj.symbols}
sym=symbols[name];sec=next(s for s in obj.sections if s.virtual_address<=sym.value<s.virtual_address+s.size)
code=bytes(sec.content)[sym.value-sec.virtual_address:sym.value-sec.virtual_address+32]
assert len(code)==32 and struct.unpack_from('<I',code,28)[0]==0x14000000
old=json.loads((LEGACY/'runtime-helper-map.json').read_text(encoding='utf-8'))['symbols']
old[aot.STRICT_EQUALS_SYMBOL]={'address':hex(aot.STRICT_EQUALS_VA)}
anchors=[]
for n,s in symbols.items():
    if abs(s.value-sym.value)<=0x100 and n in old:
        anchors.append(dict(symbol=n,object_address=s.value,native_address=int(old[n]['address'],0),delta=int(old[n]['address'],0)-s.value))
before=[a for a in anchors if a['object_address']<sym.value]
after=sorted((a for a in anchors if a['object_address']>sym.value),key=lambda a:a['object_address'])
assert len(before)>=3 and len({a['delta'] for a in before})==1,anchors
va=before[0]['delta']+sym.value;native=(WORK/'baseline-native').read_bytes();off=va-aot.IMAGE_BASE
assert native[off:off+28]==code[:28]
assert struct.unpack_from('<I',native,off+28)[0]&0xfc000000==0x14000000
assert after and after[0]['native_address']==va+32,after
report={'symbol':name,'address':va,'native_bytes':native[off:off+32].hex(),'object':str(path),'object_sha256':sha(path.read_bytes()),'anchors':anchors,'unrelocated_bytes_verified':28,'tail_branch_opcode_verified':True}
dump(WORK/'additional-helper.json',report)
print(name,hex(va),'anchors',len(anchors))
