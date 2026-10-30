"""Resource proof inputs only; never chooses a registry or writes a carrier."""
from pathlib import Path
import hashlib, json, re, sys
sys.dont_write_bytecode = True
if not __debug__:
    raise RuntimeError('Assertions are required; do not use Python -O')
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))
import release_config as cfg

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 12 * 1024 * 1024:
        raise ValueError('Resource metadata must be a small explicit file')
    return json.loads(path.read_text('utf-8-sig'))

def input_sha(role):
    value = cfg.input_value('android.resources.' + role + '.sha256').lower()
    if re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Full private SHA-256 required: ' + role)
    return value

def input_path(role):
    path = cfg.input_path('android.resources.' + role + '.path')
    return cfg.require_sha(path, input_sha(role))

def input_directory(role):
    path = cfg.input_path('android.resources.' + role + '.path')
    if not path.is_dir():
        raise ValueError('Explicit archive directory required: ' + role)
    return path

def output_path(path):
    path = Path(path).resolve()
    root = cfg.work_path('android/resources')
    if not path.is_relative_to(root) or path == root or path.exists():
        raise ValueError('Fresh work_dir/android/resources report required')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def source_contract(name):
    pins = read(ROOT / 'contract-hashes.json')
    path = ROOT / name
    if sha(path.read_bytes()) != pins[name]:
        raise ValueError('Source resource contract digest differs: ' + name)
    return read(path)

def repository_tools():
    pins = read(ROOT / 'REPOSITORY-DEPENDENCIES.json')
    for row in pins:
        cfg.require_sha(cfg.repo_path(row['repository_path']), row['sha256'])
    sys.path.insert(0, str(cfg.repo_path('tools/fantasy-gauntlet-mod-tools')))

def carrier(path, expected, role):
    if path is None:
        if expected is not None:
            raise ValueError('Carrier path missing for explicit digest')
        return input_path(role), input_sha(role)
    if expected is None or re.fullmatch('[0-9a-f]{64}', expected.lower()) is None:
        raise ValueError('Explicit carrier needs its full SHA-256')
    return cfg.require_sha(Path(path), expected.lower()), expected.lower()
