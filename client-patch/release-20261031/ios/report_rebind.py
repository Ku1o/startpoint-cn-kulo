"""Rebind an explicit private report DAG; never copy or change payloads.

Only existing allowed JSON path fields and report-file SHA links may change.
Unknown paths fail closed. Input metadata is bounded and processed one node at a
time. This module has no compiler, package, SDK or business-module imports.
"""
from pathlib import Path, PureWindowsPath
import argparse, copy, hashlib, json, os, re, tempfile
HERE = Path(__file__).resolve().parent
IDENT = re.compile(r'[a-z][a-z0-9_]{0,63}')
DIGEST = re.compile(r'[0-9a-f]{64}')
READ_KEYS = {'native_file', 'swf_file', 'runtime_abc_file', 'full_abc_file', 'ipa',
             'apk', 'compiled_report', 'source_prepare_report', 'previous_link_report',
             'previous_package_report', 'link_report', 'prepared_report', 'plan_file',
             'source_contract', 'directory', 'object', 'abc_file', 'runtime_stubs',
             'dependencies', 'baseline_native_file', 'baseline_swf_file', 'input_file',
             'allocation_contract', 'detail_report', 'proof_file', 'evidence_file'}
ZIP_KEYS = {'native_member', 'swf_member', 'manifest_member', 'dex_member', 'androidMember',
            'iosMember', 'member', 'asset_member', 'zip_member'}
PROVENANCE_KEYS = {'source_linker', 'source_linker_file', 'compiler_source', 'adapter_source',
                   'verifier_source', 'packaging_source', 'compiler_path'}
REPORT_HASH_KEYS = {'previous_link_sha256', 'previous_link_report_sha256',
                    'previous_package_sha256', 'previous_package_report_sha256',
                    'prepared_report_sha256', 'compiled_report_sha256',
                    'source_prepare_report_sha256', 'source_contract_sha256',
                    'link_report_sha256', 'allocation_contract_sha256',
                    'detail_report_sha256', 'proof_report_sha256', 'report_sha256'}
PAYLOAD_KEYS = {'native_file', 'swf_file', 'runtime_abc_file', 'full_abc_file', 'ipa',
                'apk', 'abc_file', 'baseline_native_file', 'baseline_swf_file'}


def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def read_report(path, expected):
    require(DIGEST.fullmatch(expected) is not None, 'Full original report SHA required')
    require(path.is_file() and path.stat().st_size <= 12 * 1024 * 1024, 'Report exceeds 12 MiB bound')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'Original report identity differs')
    result = json.loads(raw.decode('utf-8-sig'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite report JSON')))
    require(isinstance(result, dict), 'Report root must be an object')
    return result

def parts(pointer):
    require(isinstance(pointer, str) and pointer.startswith('/') and pointer != '/', 'Existing non-root JSON pointer required')
    result = pointer[1:].split('/')
    require(all('~' not in re.sub(r'~[01]', '', x) for x in result), 'Invalid JSON pointer escape')
    return [x.replace('~1', '/').replace('~0', '~') for x in result]

def get(document, pointer):
    current = document
    for key in parts(pointer):
        if isinstance(current, list):
            require(key.isdecimal() and str(int(key)) == key and int(key) < len(current), 'Invalid array pointer')
            current = current[int(key)]
        else:
            require(isinstance(current, dict) and key in current, 'JSON pointer missing: ' + pointer)
            current = current[key]
    return current

def put(document, pointer, value):
    path = parts(pointer)
    parent = document
    for key in path[:-1]:
        parent = parent[int(key)] if isinstance(parent, list) else parent[key]
    key = int(path[-1]) if isinstance(parent, list) else path[-1]
    parent[key] = value  # existing pointers were validated before any write

def walk(value, pointer=''):
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace('~', '~0').replace('/', '~1')
            yield from walk(child, pointer + '/' + escaped)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, pointer + '/' + str(index))
    else:
        yield pointer, value

def is_path(pointer, value):
    if not isinstance(value, str) or not value:
        return False
    key = parts(pointer)[-1]
    if key in ZIP_KEYS:
        require(not PureWindowsPath(value).is_absolute() and not value.startswith('/') and '..' not in value.replace(chr(92), '/').split('/'), 'ZIP member is not an internal relative name')
        return False
    if value.startswith(('http://', 'https://')):
        return False
    absolute = PureWindowsPath(value).is_absolute() or value.startswith('/')
    return absolute or key in READ_KEYS or key.endswith(('_file', '_path', '_report', '_directory')) or (
        ('/' in value or chr(92) in value) and value.lower().endswith(('.json', '.abc', '.swf', '.ipa', '.apk', '.o', '.swc')))

def protected_digest(document, excluded):
    digest = hashlib.sha256()
    def visit(value, pointer=''):
        if pointer in excluded:
            digest.update(b'<explicit-path-or-report-hash>')
        elif isinstance(value, dict):
            digest.update(b'{')
            for key in sorted(value):
                digest.update(json.dumps(key, ensure_ascii=False).encode())
                visit(value[key], pointer + '/' + key.replace('~', '~0').replace('/', '~1'))
            digest.update(b'}')
        elif isinstance(value, list):
            digest.update(b'[')
            for index, child in enumerate(value):
                visit(child, pointer + '/' + str(index))
            digest.update(b']')
        else:
            digest.update(json.dumps(value, ensure_ascii=False, allow_nan=False).encode())
            digest.update(b';')
    visit(document)
    return digest.hexdigest()

def resolved(value, base):
    path = Path(value)
    return (path if path.is_absolute() else base / path).resolve()

def rebind(profile, output, *, base, allowed_work, repository):
    """No file-tree copy. Every node and artifact role must be explicitly supplied."""
    output, base = Path(output).resolve(), Path(base).resolve()
    allowed_work, repository = Path(allowed_work).resolve(), Path(repository).resolve()
    require(output != allowed_work and output.is_relative_to(allowed_work) and not output.is_relative_to(repository), 'Fresh output directory must stay in private rebind work root')
    require(not output.exists(), 'Existing report output refused')
    nodes, artifacts = profile['reports'], profile['artifacts']
    require(isinstance(nodes, dict) and 0 < len(nodes) <= 64 and isinstance(artifacts, dict) and len(artifacts) <= 4096, 'Report/role count bound')
    require(all(IDENT.fullmatch(x) for x in [*nodes, *artifacts]), 'Simple explicit role IDs required')
    inputs, outputs, dependencies = {}, {}, {}
    for name, row in nodes.items():
        inputs[name] = resolved(row['path'], base)
        target = (output / row['output']).resolve()
        require(target != output and target.is_relative_to(output) and target.suffix == '.json', 'Report output traversal/type rejected')
        require(target not in outputs.values(), 'Two nodes share an output')
        require(target.name != 'REBIND-RECEIPT.json', 'Reserved receipt filename')
        outputs[name] = target
        dependencies[name] = set()
        pointers = set()
        for binding in row.get('bindings', []):
            pointer = binding['pointer']
            require(pointer not in pointers, 'Duplicate path pointer')
            pointers.add(pointer)
            require(('report' in binding) != ('artifact' in binding), 'Binding must name one report or artifact')
            if 'report' in binding:
                require(binding['report'] in nodes, 'Unknown report role')
                dependencies[name].add(binding['report'])
                if binding.get('sha_pointer'):
                    key = parts(binding['sha_pointer'])[-1]
                    require(key in REPORT_HASH_KEYS and binding['sha_pointer'] not in pointers, 'Unapproved/duplicate report SHA association')
                    pointers.add(binding['sha_pointer'])
            else:
                require(binding['artifact'] in artifacts, 'Unknown artifact role')
    order, active, done = [], set(), set()
    def visit(name):
        require(name not in active, 'Report DAG cycle rejected')
        if name in done:
            return
        active.add(name)
        for child in sorted(dependencies[name]):
            visit(child)
        active.remove(name)
        done.add(name)
        order.append(name)
    for name in sorted(nodes):
        visit(name)
    checked_roles = set()
    projections = {}
    def validate(name, document):
        row = nodes[name]
        excluded, covered = set(), set()
        for binding in row.get('bindings', []):
            pointer = binding['pointer']
            original = get(document, pointer)
            require(isinstance(original, str) and original == binding['old'], 'Expected old path differs: ' + name + pointer)
            require(is_path(pointer, original), 'Only actual path fields may be rebound')
            excluded.add(pointer)
            covered.add(pointer)
            if parts(pointer)[-1] in PAYLOAD_KEYS:
                require('artifact' in binding, 'Native/ABC/package path cannot bind to a JSON report node')
                payload_role = artifacts[binding['artifact']]
                require(payload_role.get('kind', 'file') == 'file' and 'guard_pointer' in binding, 'Native/ABC/package path requires file role and original payload SHA pointer')
            if 'report' in binding:
                child = binding['report']
                path_parts = parts(pointer)
                parent = get(document, '/' + '/'.join(pointer[1:].split('/')[:-1])) if len(path_parts) > 1 else document
                names = [path_parts[-1] + '_sha256']
                if path_parts[-1] in ('previous_link_report', 'previous_package_report'):
                    names.append(path_parts[-1].replace('_report', '') + '_sha256')
                companions = [key for key in names if isinstance(parent, dict) and key in parent]
                require(len(companions) <= 1, 'Ambiguous sibling report SHA fields; explicit schema adapter required')
                if companions:
                    prefix = pointer.rsplit('/', 1)[0]
                    expected_pointer = prefix + '/' + companions[0].replace('~', '~0').replace('/', '~1')
                    require(binding.get('sha_pointer') == expected_pointer, 'Existing sibling report SHA requires explicit correct sha_pointer')
                if binding.get('sha_pointer'):
                    guard = binding['sha_pointer']
                    require(get(document, guard) == nodes[child]['sha256'], 'Original report SHA association differs')
                    excluded.add(guard)
            else:
                role_name = binding['artifact']
                role = artifacts[role_name]
                path = resolved(role['path'], base)
                if path.suffix.lower() in ('.py', '.ps1'):
                    require(path.is_relative_to(repository), 'Handwritten build/tool source must be repository-owned, not private external data')
                if role.get('kind', 'file') == 'directory':
                    require(path.is_dir() and 'members' in binding, 'Directory role needs exact member hash contract')
                    spec = binding['members']
                    members = get(document, spec['pointer'])
                    require(isinstance(members, list) and len(members) <= 4096, 'Bounded member list required')
                    for member in members:
                        filename, expected = member[spec['name']], member[spec['sha256']]
                        require(Path(filename).name == filename and DIGEST.fullmatch(expected), 'Member basename/SHA invalid')
                        require(sha_file(path / filename) == expected, 'Compiled/data member identity changed')
                else:
                    require(role.get('kind', 'file') == 'file' and DIGEST.fullmatch(role['sha256']), 'Pinned file role required')
                    if role_name not in checked_roles:
                        require(path.is_file() and sha_file(path) == role['sha256'], 'Mapped artifact identity differs')
                        if path.suffix.lower() == '.json':
                            require(path.stat().st_size <= 12 * 1024 * 1024, 'JSON artifact bound')
                            opaque = json.loads(path.read_text('utf-8-sig'))
                            require(isinstance(opaque, (dict, list)), 'JSON data artifact must be structured')
                            require(not any(is_path(p, v) for p, v in walk(opaque)), 'JSON artifact contains read paths; declare it as a report node')
                        checked_roles.add(role_name)
                    if binding.get('guard_pointer'):
                        require(get(document, binding['guard_pointer']) == role['sha256'], 'Original payload protection SHA differs')
        for preserved in row.get('preserve_provenance', []):
            pointer = preserved['pointer']
            require(parts(pointer)[-1] in PROVENANCE_KEYS and preserved.get('reason'), 'Only reviewed non-reading provenance fields can remain opaque')
            require(get(document, pointer) == preserved['old'], 'Provenance preimage differs')
            require(pointer not in covered, 'Path cannot be rebound and opaque')
            covered.add(pointer)
        for pointer, value in walk(document):
            if is_path(pointer, value):
                require(pointer in covered, 'Unknown/unmapped actual path: ' + name + pointer)
        return excluded
    # Complete bounded preflight before creating the new output tree.
    for name in order:
        document = read_report(inputs[name], nodes[name]['sha256'])
        excluded = validate(name, document)
        projections[name] = protected_digest(document, excluded)
        del document
    output.mkdir(parents=True, exist_ok=False)
    receipts = {}
    for name in order:
        row = nodes[name]
        document = read_report(inputs[name], row['sha256'])
        excluded = validate(name, document)
        for binding in row.get('bindings', []):
            if 'report' in binding:
                child = binding['report']
                put(document, binding['pointer'], str(outputs[child]))
                if binding.get('sha_pointer'):
                    put(document, binding['sha_pointer'], receipts[child]['sha256'])
            else:
                put(document, binding['pointer'], str(resolved(artifacts[binding['artifact']]['path'], base)))
        require(protected_digest(document, excluded) == projections[name], 'Protected payload/ABI/MethodInfo/slot/function values changed')
        path = outputs[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        receipts[name] = {'path': str(path), 'sha256': sha_file(path), 'original_sha256': row['sha256'],
                          'protected_projection_sha256': projections[name], 'allowed_fields': sorted(excluded)}
        del document
    receipt = {'status': 'explicit_report_dag_rebound_protected_values_preserved', 'reports': receipts,
               'order': order, 'copied_payloads': False, 'compiled_or_executed_native': False,
               'opaque_provenance_is_not_an_input': True}
    with (output / 'REBIND-RECEIPT.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
    return receipt

def self_test(parent):
    """Tiny synthetic files only; no real IPA/native/AOT/SDK is opened."""
    results = []
    with tempfile.TemporaryDirectory(prefix='sp-report-rebind-', dir=parent) as temporary:
        temp = Path(temporary)
        inputs = temp / 'inputs'
        inputs.mkdir()
        payload = inputs / 'small.dat'
        payload.write_bytes(b'synthetic-payload-only')
        plan = inputs / 'plan.json'
        plan.write_text('{"synthetic":true}', encoding='utf-8')
        objects = inputs / 'objects'
        objects.mkdir()
        (objects / 'unit.dat').write_bytes(payload.read_bytes())
        child = {'native_file': 'legacy/native.bin', 'native_sha256': sha_file(payload),
                 'directory': 'legacy/objects', 'objects': [{'name': 'unit.dat', 'sha256': sha_file(payload)}],
                 'method_info': 12, 'flags': 128, 'slots': [0, 4], 'activation': {'fields': 2}}
        child_path = inputs / 'child.json'
        child_path.write_text(json.dumps(child), encoding='utf-8')
        root = {'previous_link_report': 'legacy/child.json', 'previous_link_report_sha256': sha_file(child_path),
                'source_ipa': {'ipa': 'legacy/app.ipa', 'ipa_sha256': sha_file(payload)},
                'nested': {'plan_file': 'legacy/plan.json', 'plan_sha256': sha_file(plan), 'abi': {'args': 5}}}
        root_path = inputs / 'root.json'
        root_path.write_text(json.dumps(root), encoding='utf-8')
        profile = {'reports': {
            'child': {'path': str(child_path), 'sha256': sha_file(child_path), 'output': 'nested/child.json', 'bindings': [
                {'pointer': '/native_file', 'old': 'legacy/native.bin', 'artifact': 'native', 'guard_pointer': '/native_sha256'},
                {'pointer': '/directory', 'old': 'legacy/objects', 'artifact': 'objects',
                 'members': {'pointer': '/objects', 'name': 'name', 'sha256': 'sha256'}}]},
            'root': {'path': str(root_path), 'sha256': sha_file(root_path), 'output': 'root.json', 'bindings': [
                {'pointer': '/previous_link_report', 'old': 'legacy/child.json', 'report': 'child', 'sha_pointer': '/previous_link_report_sha256'},
                {'pointer': '/source_ipa/ipa', 'old': 'legacy/app.ipa', 'artifact': 'native', 'guard_pointer': '/source_ipa/ipa_sha256'},
                {'pointer': '/nested/plan_file', 'old': 'legacy/plan.json', 'artifact': 'plan', 'guard_pointer': '/nested/plan_sha256'}]}},
            'artifacts': {'native': {'path': str(payload), 'sha256': sha_file(payload)},
                          'plan': {'path': str(plan), 'sha256': sha_file(plan)},
                          'objects': {'path': str(objects), 'kind': 'directory'}}}
        work = temp / 'work'
        fake_repository = temp / 'repository'
        def run(value, target):
            return rebind(value, target, base=inputs, allowed_work=work, repository=fake_repository)
        receipt = run(profile, work / 'success')
        mapped_child = json.loads(Path(receipt['reports']['child']['path']).read_text())
        mapped_root = json.loads(Path(receipt['reports']['root']['path']).read_text())
        require(mapped_root['previous_link_report_sha256'] == receipt['reports']['child']['sha256'], 'Nested report SHA link not rebound')
        require(mapped_root['source_ipa']['ipa_sha256'] == root['source_ipa']['ipa_sha256'] and mapped_child['slots'] == child['slots'] and mapped_child['method_info'] == 12 and mapped_child['flags'] == 128, 'Protected fixture fields changed')
        require(sha_file(child_path) == profile['reports']['child']['sha256'] and sha_file(root_path) == profile['reports']['root']['sha256'], 'Original reports changed')
        results.append({'case': 'two_node_nested_paths_hash_links_directory_members_and_protected_values', 'passed': True})
        def negative(name, change=None, target=None):
            value = copy.deepcopy(profile)
            if change:
                change(value)
            try:
                run(value, target or work / name)
            except ValueError:
                results.append({'case': name, 'rejected': True})
                return
            raise AssertionError('Negative control accepted: ' + name)
        negative('unknown_role', lambda x: x['reports']['child']['bindings'][0].update(artifact='missing'))
        negative('cycle', lambda x: x['reports']['child']['bindings'][0].update(report='root') or x['reports']['child']['bindings'][0].pop('artifact'))
        negative('report_output_traversal', lambda x: x['reports']['child'].update(output='../outside.json'))
        negative('output_root_traversal', target=temp / 'outside')
        negative('existing_output', target=work / 'success')
        negative('original_report_digest', lambda x: x['reports']['child'].update(sha256='0' * 64))
        negative('payload_hash_changed', lambda x: x['artifacts']['native'].update(sha256='0' * 64))
        def directory_as_payload(value):
            value['reports']['child']['bindings'][0].update(artifact='objects', members={'pointer': '/empty_members', 'name': 'name', 'sha256': 'sha256'})
            document = copy.deepcopy(child)
            document['empty_members'] = []
            file = inputs / 'directory-payload.json'
            file.write_text(json.dumps(document), encoding='utf-8')
            value['reports']['child'].update(path=str(file), sha256=sha_file(file))
            parent = copy.deepcopy(root)
            parent['previous_link_report_sha256'] = sha_file(file)
            parent_file = inputs / 'directory-payload-root.json'
            parent_file.write_text(json.dumps(parent), encoding='utf-8')
            value['reports']['root'].update(path=str(parent_file), sha256=sha_file(parent_file))
        negative('directory_cannot_replace_payload_even_with_empty_members', directory_as_payload)
        def report_as_payload(value):
            file = inputs / 'leaf.json'
            file.write_text('{"plain":true}', encoding='utf-8')
            value['reports']['leaf'] = {'path': str(file), 'sha256': sha_file(file), 'output': 'leaf.json', 'bindings': []}
            binding = value['reports']['child']['bindings'][0]
            binding.pop('artifact')
            binding['report'] = 'leaf'
        negative('report_node_cannot_replace_payload', report_as_payload)
        negative('existing_report_sha_cannot_be_omitted', lambda x: x['reports']['root']['bindings'][0].pop('sha_pointer'))
        def altered_report(case, mutate):
            document = copy.deepcopy(root)
            mutate(document)
            file = inputs / (case + '.json')
            file.write_text(json.dumps(document), encoding='utf-8')
            def change(value):
                value['reports']['root'].update(path=str(file), sha256=sha_file(file))
            negative(case, change)
        altered_report('unknown_actual_path', lambda x: x.update(mystery_path='legacy/unmapped.bin'))
        altered_report('wrong_report_hash_association', lambda x: x.update(previous_link_report_sha256='0' * 64))
        negative('payload_guard_mismatch', lambda x: x['reports']['root']['bindings'][1].update(guard_pointer='/previous_link_report_sha256'))
    return {'status': 'passed_synthetic_report_rebind_contracts', 'checks': results,
            'assertions': len(results), 'temporary_fixtures_removed': True,
            'real_carrier_sdk_native_aot_read': False, 'full_real_report_dag_executed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--repository', type=Path, help='Read-only actual checkout required for self-test output boundary')
    parser.add_argument('--output', type=Path, required=True,
                        help='Self-test JSON report, or fresh external DAG directory')
    args = parser.parse_args()
    if args.self_test:
        output = args.output.resolve()
        require(args.repository is not None, 'Self-test needs explicit read-only repository root')
        require(not output.exists() and output.parent.is_dir() and not output.is_relative_to(HERE.parents[2]) and not output.is_relative_to(args.repository.resolve()), 'Fresh external self-test report required')
        result = self_test(output.parent)
        with output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
        print(json.dumps({'status': result['status'], 'assertions': result['assertions']}))
        return
    # CLI always starts a fresh process, with explicit private configuration.
    import sys
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(HERE))
    import input_config as cfg
    private_file = Path(os.environ['SP_CLIENT_INPUTS']).resolve()
    profile = cfg.configuration()['ios']['report_rebind']
    result = rebind(profile, args.output, base=private_file.parent,
                    allowed_work=cfg.work('report-rebind'), repository=cfg.REPO)
    print(json.dumps({'status': result['status'], 'reports': len(result['reports'])}))


if __name__ == '__main__':
    main()
