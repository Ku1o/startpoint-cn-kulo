"""Sparse source-overlay audit: AST/JSON, source identities and loader contracts only."""
from pathlib import Path
import argparse, ast, hashlib, json, os, re, sys
sys.dont_write_bytecode = True
from test_release_config import external_output, release_root, run_suite

FORBIDDEN = {'.apk', '.ipa', '.swf', '.abc', '.aot', '.o', '.obj', '.a', '.so', '.dll',
             '.dylib', '.exe', '.swc', '.zip', '.p12', '.pfx', '.pem', '.key', '.p8',
             '.jks', '.keystore', '.mobileprovision', '.cer', '.der', '.crt', '.db', '.sqlite'}
TEXT = {'.py', '.ps1', '.md', '.json', '.as', '.txt', '.toml', '.yaml', '.yml', '.xml'}
MACHINE = re.compile(r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]|/(?:Users|home)/[^/\s]+')
CHAT = re.compile(r'https?://(?:chatgpt\.com|chat\.openai\.com)/(?:c|share)/|codex://(?:chat|thread)|plugin[:][/][/][^\s]*thread', re.I)
PRIVATE_KEY = re.compile(r'-{5}BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-{5}')
CREDENTIAL = re.compile(r'''(?im)^\s*['\"']?(?:password|passphrase|private_key|client_secret|access_token|refresh_token|signing_password|store_password|key_password)['\"']?\s*[:=]\s*['\"']([^'\"'\r\n]{8,})['\"']''')
HEX = re.compile(r'[0-9a-f]{64}')


def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(path, maximum=12 * 1024 * 1024):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= maximum, 'Source/dependency exceeds small-file bound: ' + str(path))
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(256 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            secret_names = {'password', 'passphrase', 'private_key', 'client_secret', 'access_token', 'refresh_token', 'signing_password', 'store_password', 'key_password'}
            if key.lower() in secret_names and isinstance(value, str) and len(value) >= 8:
                require(value.upper().startswith(('REPLACE', 'EXAMPLE', 'PLACEHOLDER')), 'Credential-valued JSON key refused: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)

def files_under(root):
    stack = [Path(root)]
    count = 0
    while stack:
        item = stack.pop()
        require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(), 'Source reparse/link refused: ' + str(item))
        if item.is_dir():
            require(item.name not in ('.git', '__pycache__', 'node_modules'), 'Non-source directory refused: ' + str(item))
            with os.scandir(item) as entries:
                stack.extend(Path(row.path) for row in entries)
        else:
            count += 1
            require(count <= 4096, 'Candidate file count bound exceeded')
            yield item

def selected_files(candidate, source, modules):
    if 'all' in modules:
        return files_under(candidate)
    roots = [source / 'release_config.py', source / 'tests']
    roots.extend(source / name for name in modules if name != 'shared')
    def iterator():
        seen = set()
        for root in roots:
            require(root.exists(), 'Selected source group missing: ' + str(root))
            for file in files_under(root):
                if file not in seen:
                    seen.add(file)
                    yield file
    return iterator()

def candidate_path(candidate, source, manifest, row):
    if 'repository_path' in row:
        value = row['repository_path']
        prefix = 'client-patch/release-20261031/'
        require(value.startswith(prefix), 'Candidate manifest path outside release source')
        path = source / value[len(prefix):]
    elif 'path' in row:
        path = manifest.parent / row['path']
    else:
        raise ValueError('Unknown source-manifest file row')
    path = path.resolve()
    require(path.is_relative_to(candidate), 'Candidate manifest escaped explicit --candidate')
    return path

def run(args, output):
    candidate = args.candidate.resolve()
    source = release_root(candidate)
    repository = args.repository.resolve()
    require(repository.is_dir(), 'Read-only repository path missing')
    require((repository / 'client-patch/lens0907-0908/build_swf.py').is_file(), 'Actual full-checkout importer missing')
    selected = list(selected_files(candidate, source, args.modules))
    require(len(selected) <= 4096, 'Global source-file count bound')
    parsed = {'python_ast': 0, 'json': 0, 'other_text': 0}
    total = 0
    lf_files = 0
    for file in selected:
        relative = file.relative_to(candidate).as_posix()
        suffix = file.suffix.lower()
        require(suffix not in FORBIDDEN and file.name not in ('.env', '.netrc', 'id_rsa', 'id_ed25519'), 'Binary/private payload refused: ' + relative)
        require(suffix in TEXT or file.name in ('LICENSE', 'NOTICE'), 'Unexpected source file type: ' + relative)
        maximum = 2 * 1024 * 1024 if suffix == '.py' else 12 * 1024 * 1024
        require(file.stat().st_size <= maximum, 'Candidate small-file bound: ' + relative)
        total += file.stat().st_size
        require(total <= 128 * 1024 * 1024, 'Candidate total source bound')
        raw = file.read_bytes()
        text = raw.decode('utf-8-sig')
        if relative.startswith('client-patch/release-20261031/'):
            require(b'\r' not in raw, 'LF source bytes required: ' + relative)
            require(raw.endswith(b'\n') and not re.search(rb'\n[\t ]*\n\Z', raw), 'Single final LF required: ' + relative)
            require(not re.search(rb'[\t ]+\n', raw), 'Trailing line whitespace: ' + relative)
            lf_files += 1
        require(not MACHINE.search(text), 'Machine/personal absolute path found: ' + relative)
        require(not CHAT.search(text), 'Chat link found: ' + relative)
        require(not PRIVATE_KEY.search(text), 'Private-key block found: ' + relative)
        secret = CREDENTIAL.search(text)
        require(not secret or secret.group(1).upper().startswith(('REPLACE', 'EXAMPLE', 'PLACEHOLDER')), 'Credential literal found: ' + relative)
        if suffix == '.py':
            ast.parse(text, filename=relative)
            parsed['python_ast'] += 1
        elif suffix == '.json':
            strict_json(text)
            parsed['json'] += 1
        else:
            parsed['other_text'] += 1
    manifests = []
    dependencies = {}
    def dependency(relative, expected):
        require(HEX.fullmatch(expected) is not None, 'Invalid repository source digest')
        path = (repository / relative).resolve()
        require(path.is_relative_to(repository), 'Repository dependency traversal')
        require(path.suffix.lower() in ('.py', '.json', '.md', '.as'), 'Only small source dependencies may be read')
        require(digest(path) == expected, 'Actual repository dependency digest differs: ' + relative)
        dependencies[relative] = expected
    for module in ('settings', 'ios'):
        if 'all' not in args.modules and module not in args.modules:
            continue
        manifest = source / module / 'SOURCE-MANIFEST.json'
        require(manifest.is_file(), 'Selected module source manifest missing: ' + module)
        document = strict_json(manifest.read_text('utf-8-sig'))
        for row in document['files']:
            path = candidate_path(candidate, source, manifest, row)
            require(path in selected, 'Manifest file was not selected for audit: ' + str(path))
            require(HEX.fullmatch(row['sha256']) is not None and digest(path) == row['sha256'], 'Candidate source digest differs: ' + str(path))
        manifests.append({'module': module, 'sha256': digest(manifest), 'files_verified': len(document['files'])})
        for row in document.get('repository_dependencies', []):
            dependency(row['repository_path'], row['sha256'])
        if module == 'settings':
            support = strict_json((source / 'settings/contracts/repository-support.json').read_text('utf-8-sig'))
            for name, expected in support.items():
                dependency('client-patch/pr43-port/support/' + name, expected)
    additional = []
    if 'all' in args.modules or 'android' in args.modules:
        additional.extend((
            ('android/capabilities', source, 'path'),
            ('android/test-support', source / 'android', 'path'),
            ('android/resources', source / 'android/resources', 'path')))
    if 'all' in args.modules:
        additional.append(('contracts', source / 'contracts', 'name'))
    for module, base, key in additional:
        manifest = source / module / ('manifest.json' if module == 'contracts' else 'SOURCE-MANIFEST.json')
        document = strict_json(manifest.read_text('utf-8-sig'))
        for row in document['files']:
            path = (base / row[key]).resolve()
            require(path.is_relative_to(candidate) and path in selected, 'Manifest source is outside selected candidate: ' + str(path))
            require(HEX.fullmatch(row['sha256']) is not None and digest(path) == row['sha256'], 'Current LF source digest differs: ' + str(path))
            if 'bytes' in row:
                require(path.stat().st_size == row['bytes'], 'Current LF source byte count differs: ' + str(path))
        manifests.append({'module': module, 'sha256': digest(manifest), 'files_verified': len(document['files'])})
    contracts = run_suite(candidate, repository, output.parent, tuple(args.modules) if 'all' not in args.modules else ('settings', 'ios'))
    return {'status': 'passed_selected_source_static_and_small_loader_contracts',
            'candidate': str(candidate), 'read_only_repository': str(repository), 'modules': args.modules,
            'files': len(selected), 'source_bytes': total, **parsed,
            'new_source_lf_single_final_newline_files': lf_files,
            'source_manifests': manifests, 'repository_dependencies': len(dependencies),
            'loader_contracts': contracts,
            'validation_scope': {'python_ast_json_and_source_hashes': True, 'small_private_loader_contracts': True,
                                 'generic_repository_modules_imported': False, 'sparse_overlay_is_complete_checkout': False,
                                 'business_behavior_executed': False, 'sdk_or_carriers_read': False,
                                 'compiler_air_aot_link_package': False, 'registration_changed': False}}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--modules', nargs='+', choices=('all', 'settings', 'ios', 'android', 'shared'), default=('all',))
    args = parser.parse_args()
    require('all' not in args.modules or len(args.modules) == 1, 'Use all alone or explicit module names')
    output = external_output(args.output, args.candidate, args.repository)
    try:
        result = run(args, output)
    except Exception as error:
        with output.open('x', encoding='utf-8') as stream:
            json.dump({'status': 'failed_source_static_or_small_loader_contract', 'modules': args.modules,
                       'error': str(error), 'compiler_or_package_executed': False}, stream, ensure_ascii=False, indent=2)
        raise
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'status': result['status'], 'files': result['files'], 'python_ast': result['python_ast'],
                      'loader_assertions': result['loader_contracts']['assertions']}))

if __name__ == '__main__':
    main()
