"""Explicit private inputs and task-local outputs; no machine-specific defaults."""
from pathlib import Path
import hashlib, json, os, sys, zipfile
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]

# Shared release configuration resolves paths relative to the private JSON.
sys.path.insert(0, str(ROOT.parent))
import release_config as _release

def configuration():
    value = _release.configuration()
    if not isinstance(value.get('settings'), dict):
        raise ValueError('SP_CLIENT_INPUTS.settings must be an object')
    return value

def require_sha(path, expected):
    if len(expected) != 64:
        raise ValueError('Full SHA-256 is required')
    return _release.require_sha(Path(path).resolve(), expected.lower())

def input_path(name):
    row = configuration()['settings'][name]
    pins = json.loads((ROOT / 'contracts/private-input-hashes.json').read_text())
    if name in pins and row['sha256'].lower() != pins[name]:
        raise ValueError('Adopted private input identity differs: ' + name)
    return require_sha(_release.input_path('settings.' + name + '.path'), row['sha256'])
def input_sha(name):
    return configuration()['settings'][name]['sha256'].lower()

def repo_path(relative):
    return _release.repo_path(relative)

def work_path(relative=''):
    return _release.work_path('settings/' + relative)
def require_output(path):
    path = Path(path).resolve()
    if not path.is_relative_to(work_path()) or path.exists():
        raise ValueError('Fresh output under private work_dir/settings required')
    return path

def runtime():
    return json.loads(input_path('air_config').read_text(encoding='utf-8-sig'))

def tool_root():
    row = configuration()['settings']['air_tools']
    root = _release.input_path('settings.air_tools.path')
    if not row.get('files') or 'lib/abc_tools.py' not in row['files']:
        raise ValueError('air_tools must pin lib/abc_tools.py and its private helper files')
    for relative, digest in row['files'].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Tool file escapes pinned root')
        require_sha(path, digest)
    return root

def configure_support():
    sys.dont_write_bytecode = True
    support = repo_path('client-patch/pr43-port/support')
    contract = json.loads((ROOT / 'contracts/repository-support.json').read_text())
    for name, digest in contract.items():
        require_sha(support / name, digest)
    sys.path[:0] = [str(ROOT / 'support'), str(support)]

def original_text(name):
    rows = json.loads((ROOT / 'contracts/original-entries.json').read_text())
    if name not in rows:
        raise ValueError('Original source member is outside narrow whitelist: ' + name)
    with zipfile.ZipFile(input_path('original_zip')) as archive:
        raw = archive.read('wf-cn-client-as3-20261014/scripts/' + name)
    if hashlib.sha256(raw).hexdigest() != rows[name]:
        raise ValueError('Original source member hash differs: ' + name)
    return raw.decode('utf-8-sig')
