"""Pinned cumulative iOS inputs for the one-method battle F1069 repair."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from pathlib import Path
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
TASK=Path(str(fc.client() / 'revision-ios-battle-f1069-fix-20261031'))
CLIENT=TASK.parent
PREVIOUS=CLIENT/'revision-ios-dispatch-fix-20261031'
SOURCE=Path(str(fc.REPO / 'client-patch'))
LIBRARIES=Path(str(fc.private('libraries')))
SDK=Path(str(fc.private('sdk')))
DEPENDENCIES=fc.private('dependencies')
BACKGROUND=Path(str(fc.tool('support/process/run_background.py')))
STUBS=fc.private('runtime_stubs')
REPAIRS=CLIENT/'revision-ios-acceptance-repairs'
SETTINGS=CLIENT/'revision-settings/ios'
ABC_SHA='7568bf806d123809c89a0d1ad7882135299f229778887bfd300b24c8d165a530'
NATIVE_SHA='2eb568827e72c89b7ae0f60582d6c32523468cc61286ce1b262d9cae8be54caa'
IPA_SHA='8e6845291b3b83a41844c241c562961dc097cf2297599f2940cacffec220011c'
METHODS=101872
NEW_METHOD=101872

def require(ok,message):
    if not ok:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def read(path,maximum=24*1024**2):
    path=Path(path)
    require(path.is_file() and path.stat().st_size<=maximum,'JSON path/size refused')
    return json.loads(path.read_text('utf-8-sig'))

def fresh(path):
    path=Path(path).resolve()
    require(path.is_relative_to(TASK.resolve()) and path!=TASK.resolve(),'Output outside battle repair task')
    require(not path.exists(),'Fresh output required: '+str(path))
    return path

def dump(path,data):
    path=fresh(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(data,stream,ensure_ascii=False,indent=2,default=str);stream.write('\n')

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def framework():
    sys.path[:0]=[str(LIBRARIES),str(SOURCE/'lens0907-0908'),str(SOURCE/'pr43-ios'),
                  str(SOURCE/'ios-r11-port'),str(fc.tool('repairs/scripts'))]
    import build_swf as p
    return p

def bounded_job(max_seconds=180):
    return module('battle_job_guard',fc.tool('support/process/job_guard.py')).require_bounded_job(max_seconds)
