"""Pinned cumulative inputs for the three-entry independent-party repair."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from pathlib import Path
import hashlib, importlib.util, json, sys
sys.dont_write_bytecode = True
SOURCE = Path(str(fc.REPO / 'client-patch'))
TASK = Path(str(fc.client() / 'revision-ios-independent-party-fix-20261031'))
PREVIOUS = TASK.parent / 'revision-ios-battle-f1069-fix-20261031'
REPAIRS = TASK.parent / 'revision-ios-acceptance-repairs'
SETTINGS = TASK.parent / 'revision-settings/ios'
SDK = Path(str(fc.private('sdk')))
DEPENDENCIES = fc.private('dependencies')
STUBS = fc.private('runtime_stubs')
BACKGROUND = Path(str(fc.tool('support/process/run_background.py')))
ABC = PREVIOUS / 'prepared01/full.abc'
ABC_SHA = 'ccb1e564a5650b57219cf7f7354ba1da971f5702a0cbc503ce165ca58bfaee8e'
NATIVE_SHA = 'c5a2072735e3bd62872f4f877d70bcb10e41aa6106e9e9c50ff49896934698b8'
IPA_SHA = '67dcd483aa3f7e500b9d2ed494b2106fe8b30da0f1c5f05415828563e7ac5b78'
METHODS = 101873
TARGETS = {
    42394: 'pinball.loading.rush::RushEventLoadingTask/summaryRemoteInput|1',
    52468: 'pinball.remote.event.rush.party::EventRushPartyRealRemote/<ctor>',
    22164: 'pinball.common.data.party.event.rush::RushEventPartyGroupHolder/getPartyCategory|1',
}
def require(ok, message):
    if not ok: raise ValueError(message)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(path, maximum=32*1024**2):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= maximum, 'JSON input path/size refused')
    return json.loads(path.read_text('utf-8-sig'))
def fresh(path):
    path = Path(path).resolve()
    require(path.is_relative_to(TASK.resolve()) and path != TASK.resolve(), 'Output outside party repair task')
    require(not path.exists(), 'Fresh output required: '+str(path))
    return path
def dump(path, value):
    path = fresh(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str); stream.write('\n')
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
def framework():
    sys.path[:0] = [str(fc.private('libraries')), str(SOURCE/'lens0907-0908'),
                   str(SOURCE/'pr43-ios'), str(SOURCE/'ios-r11-port'), str(fc.tool('repairs/scripts'))]
    import build_swf as p
    return p
def bounded_job():
    return module('party_job_guard', fc.tool('support/process/job_guard.py')).require_bounded_job(180)
