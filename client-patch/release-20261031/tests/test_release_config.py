"""Small private-loader contracts; no business imports, SDK reads or subprocesses."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, sys, tempfile
sys.dont_write_bytecode = True

def require(ok, message):
    if not ok:
        raise AssertionError(message)

def release_root(candidate):
    candidate = Path(candidate).resolve()
    direct = candidate / 'release_config.py'
    nested = candidate / 'client-patch/release-20261031/release_config.py'
    if direct.is_file():
        return candidate
    if nested.is_file():
        return nested.parent
    raise ValueError('Candidate must be sparse repository overlay or release source root')

def external_output(value, candidate, repository):
    path = Path(value).resolve()
    if path.exists() or path.is_relative_to(Path(candidate).resolve()) or path.is_relative_to(Path(repository).resolve()):
        raise ValueError('Fresh output outside candidate and source repository required')
    if not path.parent.is_dir():
        raise ValueError('Create the external output parent explicitly before running')
    return path

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def run_suite(candidate, repository, scratch_parent, modules=('settings', 'ios')):
    source = release_root(candidate)
    repository = Path(repository).resolve()
    saved_env = os.environ.get('SP_CLIENT_INPUTS')
    saved_path = sys.path[:]
    names = ('release_config', '_sp_settings_contract', '_sp_ios_contract')
    saved_modules = {name: sys.modules.get(name) for name in names}
    checks = []
    def checked(name, condition):
        require(condition, name)
        checks.append({'name': name, 'passed': True})
    def refused(name, call):
        try:
            call()
        except (ValueError, KeyError, FileNotFoundError, TypeError):
            checks.append({'name': name, 'passed': True})
            return
        raise AssertionError('Expected rejection: ' + name)
    try:
        with tempfile.TemporaryDirectory(prefix='sp-config-contract-', dir=scratch_parent) as temporary:
            temp = Path(temporary).resolve()
            payload = temp / 'small-input.txt'
            payload.write_text('private-loader-small-fixture', encoding='utf-8')
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            config = temp / 'inputs.json'
            data = {'work_dir': 'work', 'settings': {
                'probe': {'path': payload.name, 'sha256': digest},
                'air_tools': {'path': 'tools', 'files': {'lib/abc_tools.py': digest}}},
                'ios': {'probe': {'path': str(payload)}}}
            tool = temp / 'tools/lib/abc_tools.py'
            tool.parent.mkdir(parents=True)
            tool.write_bytes(payload.read_bytes())
            def save(value):
                config.write_text(json.dumps(value), encoding='utf-8')
                os.environ['SP_CLIENT_INPUTS'] = str(config)
                for name in names:
                    module = sys.modules.get(name)
                    if module:
                        for field in ('_CONFIG', '_CONFIG_FILE', '_DATA'):
                            if hasattr(module, field):
                                setattr(module, field, None)
                        if hasattr(module, '_CHECKED'):
                            module._CHECKED.clear()
            save(data)
            shared = load('release_config', source / 'release_config.py')
            checked('relative role path resolves from private JSON', shared.input_path('settings.probe.path') == payload)
            checked('relative work_dir resolves from private JSON', shared.work_path('test') == temp / 'work/test')
            checked('source root is release source', shared.source_path() == source)
            checked('repository root is two source parents', shared.repo_path() == source.parents[1])
            checked('full SHA matches small fixture', shared.require_sha(payload, digest) == payload)
            refused('wrong SHA rejected', lambda: shared.require_sha(payload, '0' * 64))
            refused('missing dotted role rejected', lambda: shared.input_path('settings.absent.path'))
            refused('object cannot be passed as a path', lambda: shared.input_path('settings.probe'))
            refused('source traversal rejected', lambda: shared.source_path('../outside'))
            refused('repository traversal rejected', lambda: shared.repo_path('../../outside'))
            refused('work traversal rejected', lambda: shared.work_path('../outside'))
            refused('absolute work child rejected', lambda: shared.work_path(str(payload)))
            data['work_dir'] = str(source)
            save(data)
            refused('work root inside checkout rejected', lambda: shared.work_path('probe'))
            data['work_dir'] = str(shared.repo_path().parent)
            save(data)
            refused('parent work root cannot route child back into checkout',
                    lambda: shared.work_path(shared.repo_path().name + '/source-overwrite'))
            data['work_dir'] = str(temp / 'work')
            save(data)
            if 'settings' in modules and (source / 'settings/input_config.py').is_file():
                settings = load('_sp_settings_contract', source / 'settings/input_config.py')
                checked('settings role object path/sha256 works', settings.input_path('probe') == payload)
                checked('settings input_sha agrees', settings.input_sha('probe') == digest)
                checked('settings work namespace', settings.work_path('probe') == temp / 'work/settings/probe')
                checked('settings air_tools path plus file map works', settings.tool_root() == temp / 'tools')
                fresh = settings.work_path('new.json')
                checked('settings fresh output accepted', settings.require_output(fresh) == fresh)
                refused('settings outside output rejected', lambda: settings.require_output(temp / 'outside.json'))
                existing = temp / 'work/settings/existing.json'
                existing.parent.mkdir(parents=True, exist_ok=True)
                existing.write_text('{}')
                refused('settings existing output rejected', lambda: settings.require_output(existing))
                data['settings']['air_tools']['files']['../escape.py'] = digest
                save(data)
                refused('air_tools file traversal rejected', settings.tool_root)
                del data['settings']['air_tools']['files']['../escape.py']
                data['settings']['probe']['sha256'] = '0' * 64
                save(data)
                refused('settings mismatched private file rejected', lambda: settings.input_path('probe'))
                data['settings']['probe']['sha256'] = digest
                save(data)
            if 'ios' in modules and (source / 'ios/input_config.py').is_file():
                ios = load('_sp_ios_contract', source / 'ios/input_config.py')
                checked('iOS absolute private role works', Path(ios.path('probe')) == payload)
                checked('iOS work namespace', ios.work('probe') == temp / 'work/ios/probe')
                refused('iOS work traversal rejected', lambda: ios.work('../outside'))
                refused('iOS repository traversal rejected', lambda: ios.repo('../../outside'))
                refused('iOS local traversal rejected', lambda: ios.local('../outside'))
                data['ios']['probe']['path'] = payload.name
                save(data)
                refused('iOS explicitly requires absolute role path', lambda: ios.path('probe'))
                data['ios']['probe']['path'] = str(payload)
                save(data)
            os.environ.pop('SP_CLIENT_INPUTS', None)
            shared._CONFIG = None
            refused('missing configuration environment rejected', shared.configuration)
            config.write_text('[]', encoding='utf-8')
            os.environ['SP_CLIENT_INPUTS'] = str(config)
            shared._CONFIG = None
            refused('non-object configuration rejected', shared.configuration)
            config.write_text(' ' * (1024 * 1024 + 1), encoding='ascii')
            shared._CONFIG = None
            refused('configuration over one MiB rejected', shared.configuration)
            result = {'status': 'passed_small_private_loader_contracts', 'checks': checks,
                      'assertions': len(checks), 'temporary_fixtures_removed': True,
                      'business_modules_imported': False, 'repository': str(repository),
                      'limits': ['Only shared/private loader modules imported', 'No generic full checkout imports',
                                 'No SDK/carrier reads, compilers, AIR, AOT or packaging']}
        return result
    finally:
        sys.path[:] = saved_path
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        if saved_env is None:
            os.environ.pop('SP_CLIENT_INPUTS', None)
        else:
            os.environ['SP_CLIENT_INPUTS'] = saved_env

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--modules', nargs='+', choices=('settings', 'ios'), default=('settings', 'ios'))
    args = parser.parse_args()
    output = external_output(args.output, args.candidate, args.repository)
    try:
        result = run_suite(args.candidate, args.repository, output.parent, args.modules)
    except Exception as error:
        with output.open('x', encoding='utf-8') as stream:
            json.dump({'status': 'failed_small_private_loader_contract', 'error': str(error)}, stream, indent=2)
        raise
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'status': result['status'], 'assertions': result['assertions']}))

if __name__ == '__main__':
    main()
