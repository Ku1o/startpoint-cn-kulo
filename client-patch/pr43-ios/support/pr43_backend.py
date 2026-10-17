"""Selected unchanged Mach-O parsing helpers from ios-cumulative-login/build_native.py."""
import struct
import lief
import aot_helpers as aot
from build_swf import abcfmt, asm, freeze
from runtime_symbols import relocs

def commands(data):
    pos=32;out=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        c,n=struct.unpack_from('<II',data,pos);out.append((pos,c,bytes(data[pos:pos+n])));pos+=n
    assert pos==32+struct.unpack_from('<I',data,20)[0]
    return out

def segments(data):
    result=[]
    for pos,c,b in commands(data):
        if c==0x19:
            vm,vs,off,fs=struct.unpack_from('<QQQQ',b,24)
            result.append(dict(name=b[8:24].rstrip(b'\0').decode(),vm=vm,vs=vs,off=off,fs=fs,command=pos))
    return result

def file_offset(data,va,size=1):
    hits=[s['off']+va-s['vm'] for s in segments(data) if s['vm']<=va and va+size<=s['vm']+s['fs']]
    assert len(hits)==1,('unmapped file address',hex(va),size)
    return hits[0]

def uleb(n):
    out=bytearray()
    while n>=128:out.append((n&127)|128);n>>=7
    out.append(n);return out

def read_rebase(data):
    pos,c,b=next(x for x in commands(data) if x[1] in (0x22,0x80000022))
    off,size=struct.unpack_from('<II',b,8);raw=data[off:off+size];i=0;typ=0;seg=0;where=0;result=[]
    def read():
        nonlocal i
        n=0;shift=0
        while True:
            v=raw[i];i+=1;n|=(v&127)<<shift
            if v<128:return n
            shift+=7
    def emit(n,skip=0):
        nonlocal where
        assert typ in (1,2,3)
        for _ in range(n):result.append((seg,where,typ));where+=8+skip
    while i<len(raw):
        op=raw[i]>>4;imm=raw[i]&15;i+=1
        if op==0:return dict(command=pos,offset=off,size=size,prefix=bytes(raw[:i-1]),entries=result)
        if op==1:typ=imm
        elif op==2:seg=imm;where=read()
        elif op==3:where+=read()
        elif op==4:where+=imm*8
        elif op==5:emit(imm)
        elif op==6:emit(read())
        elif op==7:emit(1,read())
        elif op==8:n=read();skip=read();emit(n,skip)
        else:raise ValueError(('rebase opcode',op))
    raise ValueError('rebase stream has no DONE')

def constant(obj,name,path):
    sym=next(s for s in obj.symbols if aot.text(s.name)==name and s.numberof_sections)
    sec=aot.find_section(obj,sym)
    assert sec.name in ('__const','__literal8','__literal16'),('not a constant',name,sec.name)
    ends=[s.value for s in obj.symbols if s.numberof_sections==sym.numberof_sections and s.value>sym.value]
    end=min(ends,default=sec.virtual_address+sec.size)
    assert not relocs(path,obj,sec,sym.value,end),('constant pointer relocations require registration',name)
    return bytes(sec.content)[sym.value-sec.virtual_address:end-sec.virtual_address]
