"""Shared task-local bounded-stage utilities; no build main runs at import."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import hashlib, importlib.util, json, os, struct, sys, types, zlib
sys.dont_write_bytecode=True
TASK=cfg.work('repairs')
CLIENT=Path(cfg.path('input_root'))
BASE_FULL=Path(cfg.path('settings_full_abc'))
PREVIOUS_LINK=Path(cfg.path('settings_link_report'))
PREVIOUS_PACKAGE=Path(cfg.path('settings_package_report'))
SOURCE=Path(cfg.repo('client-patch'))
LIBRARIES=Path(cfg.path('libraries'))
SDK=Path(cfg.path('sdk'))
DEPENDENCIES=Path(cfg.path('dependencies'))
BACKGROUND=Path(cfg.local('support/process/run_background.py'))
STUBS=Path(cfg.path('runtime_stubs'))
ABC_SHA='672757b40180eb960dde989b8f659b37cc32229a03a5c903b0bbdc3be6bc814e'
NATIVE_SHA='7d803626d4cd5debc00cb17b633bbfeec3a9d04ef6b7beed4f068d2e17b6215f'
IPA_SHA='b38629f65e8506720cc27200b4c87fd51613b78593899c0248a46ffc2e3a9d24'
SOURCE_SHA='83fc92d70d7457bb5e4b58d25d97663eeb80367ee366a947f4779a12075ff172'
BEFORE_SWF_SHA='215860d0f3933b352c377309c68943a3978a80ab5c5beb209c9b94382191e325'

def require(ok,message):
    if not ok:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def read(path,maximum=16*1024**2):
    path=Path(path)
    require(path.is_file() and path.stat().st_size<=maximum,'Input JSON size/path refused: '+str(path))
    return json.loads(path.read_text('utf-8-sig'))

def fresh(path):
    path=Path(path).resolve()
    require(path.is_relative_to(TASK.resolve()) and path!=TASK.resolve(),'Output must stay inside new repair task')
    require(not path.exists(),'Fresh output required: '+str(path))
    return path

def dump(path,value):
    path=Path(path).resolve()
    require(path.is_relative_to(TASK.resolve()),'Write outside this task refused')
    require(not path.exists(),'Existing report refused: '+str(path))
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,default=str)
        stream.write('\n')

def bounded_job(max_seconds=180):
    from inspect_stage1 import require_bounded_job
    return require_bounded_job(max_seconds)

def framework():
    cfg.bind_tools()
    sys.path[:0]=[str(LIBRARIES),str(SOURCE/'lens0907-0908'),str(SOURCE/'pr43-ios'),str(SOURCE/'ios-r11-port')]
    import build_swf as p
    return p

def view(p,abc):return p.View(types.SimpleNamespace(abc=abc),p.asm)

def signature(v,mid):
    ret,params,name,flags,options,pnames=v.a.methods[mid]
    def const(index,kind):
        pools={1:'strings',3:'ints',4:'uints',6:'doubles'}
        if kind in pools:
            value=getattr(v.a,pools[kind])[index]
            return kind,value.hex() if isinstance(value,bytes) else value
        if kind in (5,8,22,23,24,25,26):return kind,v.ns(index)
        return kind,index
    return dict(returns=v.mn(ret),parameters=[v.mn(x) for x in params],flags=flags,
                optional=[const(x,k) for x,k in options] if options is not None else None)

def semantic_label(row):
    return row['owner']+('$' if row['static'] else '')+'/'+row['name']+'|1'

def body_for(v,label):
    hits=v.by_label.get(label,[])
    require(len(hits)==1,'Missing/ambiguous source method: '+label)
    return hits[0]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def swf_units(p,path,expected_sha,names):
    path=Path(path);require(path.resolve().is_relative_to(CLIENT.resolve()),'Source SWF outside client task')
    require(path.stat().st_size<=32*1024**2,'Source SWF input bound')
    raw=path.read_bytes();require(sha(raw)==expected_sha,'Source SWF digest differs')
    require(raw[:3] in (b'CWS',b'FWS'),'Unsupported SWF compression')
    if raw[:3]==b'CWS':
        decoder=zlib.decompressobj();data=decoder.decompress(raw[8:],64*1024**2+1)
        require(len(data)<=64*1024**2 and decoder.eof and not decoder.unconsumed_tail,'SWF inflation bound')
    else:data=raw[8:]
    require(len(data)+8==struct.unpack_from('<I',raw,4)[0],'SWF declared length differs')
    tags=p.asm.load_abc_module('swftags');result={}
    for kind,at,header,size in tags.iter_tags(data):
        if kind!=82:continue
        payload=data[at+header:at+header+size];end=payload.index(b'\0',4);name=payload[4:end].decode('utf-8')
        if name not in names:continue
        require(name not in result,'Duplicate selected source DoABC: '+name)
        result[name]=payload[end+1:]
    require(set(result)==set(names),'Source DoABC set differs')
    return result
