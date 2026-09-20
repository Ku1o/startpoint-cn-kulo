"""Exact-input, native-only Fantasy Gauntlet navigation repair."""
from pathlib import Path
from types import SimpleNamespace
import hashlib, importlib.util, json, os, struct, sys, zipfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = Path(os.environ.get('STARPOINT_IOS_FANTASY_RETURN_WORK', 'F:/codex/work/ios-fantasy-return-20260916-r2'))
OUT = Path(os.environ.get('STARPOINT_IOS_FANTASY_RETURN_OUT',
           str(REPO / 'outputs/ios-fantasy-return-fix-20260916-r2')))
LEGACY = Path('F:/codex/ios-rush-leaderboard-port-20260830')
SDK = LEGACY / 'AIRSDK_51.2.1.5'
sys.path[:0] = [str(HERE.parent/'lens0907-0908'), str(HERE.parent), str(LEGACY),
                'F:/codex/tools/ios-re-libs', str(HERE.parent/'ios-cumulative-login')]
import build_swf as model
import build_ios_rush_leaderboard_ipa as aot
import lief
from macho_signing_layout import assert_signable_layout

INPUT_SHA = '90d6757bc45c8562926f7ea53b0455c219b9867bf91cbab4314237cab4ffb3f6'
NATIVE_SHA = 'abfbfad2949dfaf26cb9440a63c1cbb8893559078b91a32e868c5c843165b0fa'
METHOD = 31064
ROUTE = 0x103d51830
HOOK = 0x103d51888
ORIGINAL_TARGET = 0x10380b4a4
BUILD_ID = 'ios-184-admission-20260915'

def sha(data): return hashlib.sha256(data).hexdigest()
def dump(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def registry(): return json.loads((HERE/'source-artifact.json').read_text('utf-8'))
def view(abc): return model.View(SimpleNamespace(abc=abc), model.asm)
def commands(data):
    at = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, at)
        yield at, cmd, data[at:at+size]
        at += size
def segments(data):
    return [dict(name=raw[8:24].rstrip(b'\0').decode(), command=at,
                 **dict(zip(('vm','vs','off','fs'), struct.unpack_from('<QQQQ', raw,24))),
                 section_size=struct.unpack_from('<Q',raw,112)[0] if len(raw)>=152 else 0)
            for at,cmd,raw in commands(data) if cmd==0x19]
def offset(data, va, size=1):
    return next(s['off']+va-s['vm'] for s in segments(data) if s['vm']<=va and va+size<=s['vm']+s['fs'])
def native():
    reg=registry(); path=REPO/reg['ipa']
    assert sha(path.read_bytes())==INPUT_SHA
    with zipfile.ZipFile(path) as z: data=z.read(reg['native_member'])
    assert sha(data)==NATIVE_SHA
    return data
def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
