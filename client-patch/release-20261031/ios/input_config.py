"""Private paths only from SP_CLIENT_INPUTS; no package work at import."""
from pathlib import Path
import hashlib, importlib.util, json, os, sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
_DATA = None
_CHECKED = set()

def configuration():
    global _DATA
    if _DATA is None:
        value = os.environ.get('SP_CLIENT_INPUTS')
        if not value:
            raise ValueError('Set SP_CLIENT_INPUTS to a private JSON configuration')
        path = Path(value).resolve()
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError('Private configuration missing or exceeds 1 MiB')
        _DATA = json.loads(path.read_text('utf-8-sig'))
        if not isinstance(_DATA.get('ios'), dict):
            raise ValueError('Configuration requires ios object and work_dir')
    return _DATA

def path(key):
    row = configuration()['ios'][key]
    value = row['path'] if isinstance(row, dict) else row
    if not value or not Path(value).is_absolute():
        raise ValueError('Absolute private path required: ios.' + key)
    resolved = Path(value).resolve()
    pins = json.loads((HERE / 'INPUT-PINS.json').read_text('utf-8-sig'))
    declared = row.get('sha256') if isinstance(row, dict) else None
    if key in ('settings_link_report', 'settings_package_report') and (not isinstance(declared, str) or len(declared) != 64):
        raise ValueError('Rebound report SHA from REBIND-RECEIPT is required: ' + key)
    expected = pins.get(key) or declared
    if key == 'settings_native':
        if declared != pins[key]:
            raise ValueError('Native evidence role must retain frozen identity')
        return str(resolved)  # Stage1 stays sparse; rebind/link/check verify actual payload bytes
    if expected and (key, str(resolved)) not in _CHECKED:
        require_sha(resolved, expected)
        _CHECKED.add((key, str(resolved)))
    return str(resolved)

def require_sha(file, expected):
    digest = hashlib.sha256()
    with Path(file).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError('Private input identity mismatch: ' + str(file))
    return Path(file)

def repo(relative):
    result = (REPO / relative).resolve()
    if not result.is_relative_to(REPO) or not result.exists():
        raise ValueError('Repository dependency missing/escaped: ' + relative)
    return str(result)

def local(relative):
    result = (HERE / relative).resolve()
    if not result.is_relative_to(HERE) or not result.exists():
        raise ValueError('Recipe dependency missing/escaped: ' + relative)
    return str(result)

def work(relative=''):
    root = Path(configuration()['work_dir'])
    if not root.is_absolute():
        raise ValueError('Absolute work_dir required')
    root = root.resolve()
    if not root.is_absolute() or root.is_relative_to(REPO):
        raise ValueError('work_dir must be private and outside repository')
    result = (root / 'ios' / relative).resolve()
    if not result.is_relative_to(root / 'ios') or result.is_relative_to(REPO):
        raise ValueError('Work output escaped ios root')
    return result

def bootstrap():
    sys.path[:0] = [path('libraries'), str(HERE), local('support/recipe-deps/pr43-ios'),
                   local('support/recipe-deps/pr43-ios/support'),
                   repo('client-patch/pr43-ios/support'),
                   repo('client-patch/lens0907-0908'), repo('client-patch/pr43-ios'),
                   repo('client-patch/ios-r11-port'), repo('client-patch/ios-cumulative-login'),
                   repo('client-patch/ios-shop-first-open'), repo('client-patch/equipment-ios-repair')]

def bind_tools():
    # Generic adapters insert their historical directories at index 0.
    # Preload exact adopted tools by absolute repository source identity first.
    bootstrap()
    for name in ('native_support', 'compile_port', 'hud_adapter', 'link_port'):
        expected = Path(local('support/recipe-deps/pr43-ios/' + name + '.py'))
        if name in sys.modules:
            if Path(sys.modules[name].__file__).resolve() != expected:
                raise ValueError('Different tool already imported: ' + name)
            continue
        spec = importlib.util.spec_from_file_location(name, expected)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
