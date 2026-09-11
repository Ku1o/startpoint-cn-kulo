"""Prove the additional native AIR references against the accepted executable."""
from prepare import *
import struct,subprocess
sys.path[:0]=[str(LEGACY),r'F:\codex\tools\ios-re-libs']
import lief,build_ios_rush_leaderboard_ipa as aot

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

def main():
    native=(WORK/'baseline-native').read_bytes()
    member=WORK/'runtime-members/hm-aot-helpers.o'
    if not member.exists():
        subprocess.run([sys.executable,'-X','utf8','-B',str(LEGACY/'inspect_runtime_archive.py'),
            str(SDK/'lib/aot/lib/libRuntimeHMAOT.arm-air.a'),
            '_llLoadCatchTraits','_llNewClass','_builtin_traits_any',
            '--extract-dir',str(member.parent)],check=True,timeout=60,capture_output=True)
    assert sha(member.read_bytes())=='3b5d2834de564a773ed2317a66bea702f0987cc35edf72319ac5c1ff057b7176'
    assert sha((LEGACY/'runtime-archive-members/hm-stubs.o').read_bytes())=='952f0c9ffe34f2e35eb434fdf0dd641d7ecd8baa6bf9d260e258d59e4ca1ecb8'
    wanted={
        '__ZN8halfmoon5Stubs11do_newcatchEPN7avmplus11MethodFrameEPNS1_6TraitsE':LEGACY/'runtime-archive-members/hm-stubs.o',
        '__ZN8halfmoon5Stubs6do_d2bEPN7avmplus11MethodFrameEd':LEGACY/'runtime-archive-members/hm-stubs.o',
        '_llLoadCatchTraits':WORK/'runtime-members/hm-aot-helpers.o',
        '_llNewClass':WORK/'runtime-members/hm-aot-helpers.o',
    }
    result={name:derive(path,name,native) for name,path in wanted.items()}
    path=WORK/'runtime-members/hm-aot-helpers.o';obj=lief.parse(str(path))
    # Reuse AIR's actual builtin-traits slot, deriving its address from the
    # matched native accessor rather than assuming its BSS value stays null.
    sec,start,end=function(obj,'_builtin_traits_any')
    assert sec.name=='__common' and end-start==8
    text_sec=next(s for s in obj.sections if s.name=='__text')
    refs=[r for r in relocs(path,obj,text_sec,0,text_sec.size) if r['symbol']=='_builtin_traits_any']
    assert sorted(r['type'] for r in refs)==[3,4]
    first=min(r['offset'] for r in refs)
    owner=max((s for s in obj.symbols if s.numberof_sections and s.value<=first and not aot.text(s.name).startswith('ltmp')),key=lambda s:s.value)
    proof=derive(path,aot.text(owner.name),native)
    hi=next(r['offset']-owner.value for r in refs if r['type']==3)
    lo=next(r['offset']-owner.value for r in refs if r['type']==4)
    hword=struct.unpack_from('<I',native,proof['file_offset']+hi)[0];lword=struct.unpack_from('<I',native,proof['file_offset']+lo)[0]
    assert hword&0x9f000000==0x90000000 and lword&0x3b000000==0x39000000
    assert hword&31==(lword>>5)&31
    imm=((hword>>29)&3)|(((hword>>5)&0x7ffff)<<2)
    if imm&(1<<20):imm-=1<<21
    address=((proof['address']+hi)&~0xfff)+(imm<<12)+(((lword>>10)&0xfff)<<(lword>>30))
    result['_builtin_traits_any']=dict(address=address,accessor=aot.text(owner.name),accessor_proof=proof,adrp_offset=hi,load_offset=lo)
    sdk=(SDK/'lib/aot/lib/avmglue.abc').read_bytes();digest=hashlib.sha1(sdk).digest()
    offset=native.find(digest);assert offset>=0 and native.find(digest,offset+1)==-1
    assert offset==0x63b7db0
    result['_sdk_aotInfo']=dict(address=aot.IMAGE_BASE+offset,hash=digest.hex(),native_bytes=native[offset:offset+40].hex())
    dump(WORK/'runtime-extra-map.json',result)
    print(json.dumps({n:hex(r['address']) if 'address' in r else r['local_constant'] for n,r in result.items()},indent=2))

if __name__=='__main__':main()
