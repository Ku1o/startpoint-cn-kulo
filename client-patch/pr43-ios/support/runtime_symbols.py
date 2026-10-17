"""Native symbol derivation without invoking the historical build entry point."""
import struct, hashlib
import lief
import aot_helpers as aot
def sha(data): return hashlib.sha256(data).hexdigest()

def function(obj,name):
    syms=list(obj.symbols);s=next(s for s in syms if aot.text(s.name)==name and s.numberof_sections)
    sec=aot.find_section(obj,s)
    starts=sorted(set(x.value for x in syms if x.numberof_sections==s.numberof_sections and not aot.text(x.name).startswith(('ltmp','lCPI')) and x.value>s.value))
    end=starts[0] if starts else sec.virtual_address+sec.size
    return sec,s.value,end

def relocs(path,obj,sec,start,end):
    raw=path.read_bytes();syms=list(obj.symbols);result=[]
    for i in range(sec.numberof_relocations):
        off,word=struct.unpack_from('<iI',raw,sec.relocation_offset+i*8);va=sec.virtual_address+off
        if start<=va<end:result.append(dict(offset=va-start,type=word>>28,external=(word>>27)&1,symbol=aot.text(syms[word&0xffffff].name) if (word>>27)&1 else None))
    return result

def derive(path,name,native):
    obj=lief.parse(str(path));sec,start,end=function(obj,name);code=bytes(sec.content)[start-sec.virtual_address:end-sec.virtual_address]
    rows=relocs(path,obj,sec,start,end);skip={r['offset'] for r in rows};words=[code[i:i+4] for i in range(0,len(code),4)]
    runs=[];run=[]
    for i,word in enumerate(words):
        if i*4 in skip:
            if run:runs.append(run)
            run=[]
        else:run.append(i)
    if run:runs.append(run)
    best=max(runs,key=len);anchor=code[best[0]*4:(best[-1]+1)*4]
    assert len(anchor)>=8,(name,'insufficient anchor')
    at=0;matches=[]
    while True:
        at=native.find(anchor,at)
        if at<0:break
        base=at-best[0]*4;at+=1
        if base>=0 and base%4==0 and all(i*4 in skip or native[base+i*4:base+i*4+4]==word for i,word in enumerate(words)):matches.append(base)
    assert len(matches)==1,(name,'matches',matches,'size',len(code))
    offset=matches[0]
    return dict(address=aot.IMAGE_BASE+offset,file_offset=offset,size=len(code),object=str(path),object_sha256=sha(path.read_bytes()),
        native_bytes=native[offset:offset+32].hex(),relocations=rows,unrelocated_bytes_verified=len(code)-len(skip)*4)
