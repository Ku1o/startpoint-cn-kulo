"""Pinned cumulative inputs and private admission material for the EX release."""
import hashlib, importlib.util, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = Path(os.environ.get('STARPOINT_EX_RELEASE_WORK', 'F:/codex/work/abyss-ex-clients-20260917'))
OUT = Path(os.environ.get('STARPOINT_EX_RELEASE_OUT', 'F:/codex/outputs/abyss-ex-clients-20260917'))
PREP = Path('F:/codex/work/abyss-normal-ex-20260917/client')
PRIVATE = Path('F:/codex/.codex/secrets/starpoint-client-admission')
PAIR = PRIVATE/'releases/abyss-ex-20260917'
IDS = {'android': 'android-181-abyss-ex-20260917', 'ios': 'ios-184-abyss-ex-20260917'}
INFO_OFFSET = 104549248
OLD_COUNT = 101287
LEGACY = Path('F:/codex/ios-rush-leaderboard-port-20260830')
SDK = LEGACY/'AIRSDK_51.2.1.5'

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def sha(data): return hashlib.sha256(data).hexdigest()
def dump(path, obj): path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', 'utf8')
def read(path): return json.loads(path.read_text('utf-8-sig'))

lan = module('ex_release_android_helpers', HERE.parent/'r10-public-release/build_lan.py')
s, b = lan.s, lan.b
abcfmt = s.m.abcfmt
freeze = s.m.freeze
sys.path[:0] = [str(HERE.parent/'ios-cumulative-login'), str(HERE.parent), str(HERE.parent/'ios-shop-first-open')]
p = module('ex_release_ios_helpers', HERE.parent/'ios-cumulative-login/prepare.py')
view = p.view

def registries():
    android = read(HERE.parent/'android-accepted.json')['variants']['public']
    ios = read(HERE.parent/'ios-accepted.json')['artifact']
    assert android['apk_sha256'] == '3c365e51762ad115366731fa1fa2bd1ffbdac54cbce4c3e2626010deffc91fd2'
    assert ios['ipa_sha256'] == 'f1d9f41f0b9c16ec79efa5664833fe5dea13038bc844a25f22dbafda367316dc'
    return android, ios

def replacements(platform):
    a, i = registries()
    old = (a if platform == 'android' else i)['build_id']
    keys = read(PAIR/'config/client-admission.keys.json')
    assert keys[old] != keys[IDS[platform]]
    return {old.encode(): IDS[platform].encode(), keys[old].encode(): keys[IDS[platform]].encode()}

def replace_abc(raw, platform):
    abc = abcfmt.ABC(raw)
    values = replacements(platform)
    changes = {i: (value, values[value]) for i, value in enumerate(abc.strings)
               if value in values}
    result = lan.patch_strings(raw, changes)
    assert lan.patch_strings(result, {i:(new,old) for i,(old,new) in changes.items()}) == raw
    return result, sorted(changes)
