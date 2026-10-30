"""Small Android source/contract/import check; never opens a carrier or builds.

Use a fresh external --output. Repository dependencies are checked in the sparse
candidate overlay when explicitly present there, otherwise in --repository.
Only source text and JSON are read; private inputs are temporary text markers.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

TEXT = {'.py', '.ps1', '.as', '.md', '.json', '.txt', '.xml', '.toml', '.yaml', '.yml'}
HEX = re.compile(r'[0-9a-f]{64}')
HEAD = '5f70aec391c011f8d3066d41021fe06f27c07f84'
LEADER_LABELS = {
    'AbilityDisabledReasonResolver/wfxLeaderResolve',
    'AbilityDisabledReasonResolver/wfxLeaderResolveInitial',
    'AbilityDisabledReasonResolver/wfxLeaderResolveInstant',
    'AbilityDisabledReasonResolver/wfxLeaderResolvePrecondition',
    'TriggerableAbilityDialogAllAbilitiesGenerator/get',
    'TriggerableAbilityDialogAllAbilitiesGenerator/wfxAddLeaderAbility',
    'TriggerableAbilityDialogAllAbilitiesGenerator/wfxAppendUnisonLeader',
    'TriggerableAbilityDialogAllAbilitiesGenerator/wfxLeaderAbilityPeek',
    'TriggerableAbilityDialogAllAbilitiesGenerator/wfxLeaderDescriptions',
    'TriggerableAbilityDialogAllAbilitiesGenerator/wfxLeaderReasonResolver',
}
CT_PROLOGUE = [
    'getlocal_0 []', 'getlocal_1 []', 'getlocal_2 []', 'getlocal_3 []',
    'getlocal [4]', "callproperty ['wfxHealAnyCTRecord', 4]",
    'iffalse [] -> #10', 'returnvoid []',
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def source_root(candidate):
    for root in (candidate, candidate / 'client-patch/release-20261031'):
        if (root / 'release_config.py').is_file():
            return root.resolve()
    raise ValueError('Candidate must be sparse repository or release source root')


def inside(root, relative):
    require(isinstance(relative, str) and '\\' not in relative, 'Relative source path required')
    parts = PurePosixPath(relative)
    require(not parts.is_absolute() and '..' not in parts.parts and bool(parts.parts), 'Source path escapes root')
    path = root
    for part in parts.parts:
        path = path / part
        require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(), 'Source reparse point refused')
    path = path.resolve()
    require(path.is_relative_to(root.resolve()), 'Resolved source leaves root')
    return path


def source_bytes(path, maximum=4 * 1024 * 1024):
    path = Path(path)
    require(path.suffix.lower() in TEXT, 'Binary/non-source input refused: ' + path.name)
    require(path.is_file() and path.stat().st_size <= maximum, 'Missing/oversize source: ' + str(path))
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum and b'\x00' not in raw, 'Non-text/oversize source refused')
    return raw


def digest(path):
    return hashlib.sha256(source_bytes(path)).hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(source_bytes(path).decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=invalid)


def manifest_files(root, manifest, label, checks):
    rows = manifest['files']
    require(isinstance(rows, list) and 0 < len(rows) <= 2048, 'Manifest file bound: ' + label)
    seen = set()
    parsed = {'python': 0, 'json': 0}
    for row in rows:
        relative = row['path']
        require(relative not in seen and HEX.fullmatch(row['sha256']), 'Duplicate/invalid file record: ' + label)
        seen.add(relative)
        path = inside(root, relative)
        raw = source_bytes(path)
        require(hashlib.sha256(raw).hexdigest() == row['sha256'], 'Source hash differs: ' + relative)
        if 'bytes' in row:
            require(len(raw) == row['bytes'], 'Source byte count differs: ' + relative)
        if path.suffix == '.py':
            ast.parse(raw.decode('utf-8-sig'), filename=relative)
            parsed['python'] += 1
        elif path.suffix == '.json':
            read_json(path)
            parsed['json'] += 1
    checks.append({'name': label, 'files': len(rows), 'parsed': parsed, 'passed': True})
    return rows


def dependency_files(rows, candidate, repository, checks, label):
    require(isinstance(rows, list), 'Repository dependency list required')
    result = []
    seen = set()
    for row in rows:
        relative = row.get('path', row.get('repository_path'))
        require(relative not in seen and HEX.fullmatch(row['sha256']), 'Duplicate/invalid repository dependency')
        seen.add(relative)
        overlay = inside(candidate, relative)
        path, origin = (overlay, 'candidate_overlay') if overlay.is_file() else (inside(repository, relative), 'repository')
        require(digest(path) == row['sha256'], 'Dependency hash differs: ' + relative)
        result.append({'path': relative, 'origin': origin, 'sha256': row['sha256']})
    checks.append({'name': label, 'passed': True, 'files': result})


def check_contracts(root, checks):
    contracts = root / 'android/contracts'
    preimages = read_json(contracts / 'semantic-preimages.json')['preimages']
    require(len(preimages) == 21, 'Exactly21 semantic preimages required')
    keys = set()
    for row in preimages:
        key = row['label'], row['historical_code_sha256']
        require(key not in keys, 'Duplicate semantic preimage')
        keys.add(key)
        for field in ('historical_code_sha256', 'source_file_sha256', 'observed_relocation_lock_sha256'):
            require(isinstance(row[field], str) and HEX.fullmatch(row[field]), 'Semantic SHA contract invalid')
        require(len(row['header']) == 4 and all(isinstance(v, int) and v >= 0 for v in row['header']), 'Semantic header invalid')
        require(isinstance(row['instructions'], list) and 0 < len(row['instructions']) <= 20000
                and all(isinstance(v, str) for v in row['instructions']), 'Semantic instruction contract invalid')
    helpers = read_json(contracts / 'helper-instructions.json')['methods']
    require(set(helpers) == {'identity_tags', 'caster_barrier', 'ct_predecessor'}, 'Exactly two custom helpers plus CT proof required')
    texts = {}
    for name, row in helpers.items():
        require(HEX.fullmatch(row['source_file_sha256']) is not None, 'Helper source hash invalid')
        require('header=[' in row['source_header'] and 'code_sha256=' in row['source_header'], 'Helper header missing')
        lines = row['instruction_lines']
        require(isinstance(lines, list) and lines and len(lines) <= 1000, 'Helper instruction count bound')
        matches = [re.fullmatch(r'#\d+ ofs[0-9a-f]+: (.*)', line) for line in lines]
        require(all(matches), 'Helper instruction record malformed')
        texts[name] = [hit.group(1) for hit in matches]
    ct = texts['ct_predecessor']
    require(ct[2:10] == CT_PROLOGUE, 'CT exact eight-instruction prologue differs')
    candidates = [r for r in preimages if r['label'] == 'MemberImpl/wfxHealAnyDamage']
    require(len(candidates) == 1 and candidates[0]['instructions'] == ct, 'CT semantic/archive inputs disagree')
    expected = ct[:2] + ct[10:]
    expected = [re.sub(r'-> #(\d+)', lambda m: '-> #' + str(int(m[1]) - 8 if int(m[1]) >= 10 else int(m[1])), line) for line in expected]
    require(len(expected) == len(ct) - 8 and expected[:2] == ct[:2], 'CT predecessor transformation invalid')
    labels = read_json(contracts / 'leader-display-labels.json')['labels']
    require(len(labels) == 10 and len(set(labels)) == 10 and set(labels) == LEADER_LABELS, 'Exact ten donor labels required')
    order = read_json(contracts / 'capability-order.json')
    groups = order['ordered_groups']
    require(order['source_head'] == HEAD and len(groups) == 46, 'Fixed-head46 profile changed')
    require(len({r['name'] for r in groups}) == 46, 'Profile repeats a group')
    require(all(HEX.fullmatch(r['expected_output_sha256']) for r in groups), 'Profile output hashes malformed')
    require(groups[-1]['expected_output_sha256'] == order['final_partial_sha256'], 'Profile final output hash differs')
    require(order['historical_deferred_dash_helper'] is True, 'Historical profile must explicitly defer the later repaired helper')
    require(not any(r['name'] in {'163-carry', '112-query-fallback'} for r in groups), 'Excluded/fallback group in frozen successful profile')
    checks.append({'name': 'exact_contract_shapes', 'passed': True, 'semantic_preimages': 21,
                   'custom_helpers': 2, 'ct_predecessors': 1, 'donor_labels': 10, 'profile_groups': 46,
                   'ct_normalized_predecessor_sha256': hashlib.sha256('\n'.join(expected).encode('utf-8')).hexdigest()})
    return order


def import_apis(root, scratch_parent, order, checks):
    saved_modules, saved_path = dict(sys.modules), sys.path[:]
    saved_env = dict(os.environ)
    saved_bytecode, saved_profile = sys.dont_write_bytecode, sys.getprofile()
    opened = []
    cap = root / 'android/capabilities'
    aliases = {'bootstrap', 'port_capabilities', 'release_config', 'asm', 'bodies', 'swfabc',
               'framework', 'static_check', 'multiabc', 'common', 'perf2_core',
               'abcasm_opwalk', 'abcasm_abcfmt', 'abcasm_swftags', '_sp_android_port_contract'}
    restored = False
    try:
        sys.dont_write_bytecode = True
        for name in aliases:
            sys.modules.pop(name, None)
        with tempfile.TemporaryDirectory(prefix='sp-android-source-', dir=scratch_parent) as temporary:
            temp = Path(temporary).resolve()
            marker = temp / 'input.txt'
            marker.write_text('unread source-only carrier marker', encoding='utf-8')
            config = temp / 'inputs.json'
            config.write_text(json.dumps({'work_dir': str(temp / 'work'), 'android': {'inputs': {
                'r11_swf': {'path': marker.name}, 'donor_swf': {'path': marker.name}}}}), encoding='utf-8')
            os.environ['SP_CLIENT_INPUTS'] = str(config)
            sys.path[:0] = [str(cap), str(root)]
            original_open, original_io_open = builtins.open, io.open
            def guarded_open(file, mode='r', *args, **kwargs):
                require(isinstance(file, (str, bytes, os.PathLike)), 'Descriptor access refused during source import')
                path = Path(os.fsdecode(file)).resolve()
                require(not any(flag in mode for flag in ('w', 'a', 'x', '+')), 'Import-time write refused')
                require(path != marker, 'Carrier marker must never be read')
                require(path == config or path.suffix == '.py', 'Non-source import read refused: ' + path.name)
                require(path.is_file() and path.stat().st_size <= 4 * 1024 * 1024, 'Import source bound')
                opened.append(path.suffix)
                return original_io_open(file, mode, *args, **kwargs)
            def source_get_code(loader, fullname):
                filename = Path(loader.get_filename(fullname)).resolve()
                with guarded_open(filename, 'r', encoding='utf-8-sig') as stream:
                    text = stream.read(4 * 1024 * 1024 + 1)
                return compile(text, str(filename), 'exec', dont_inherit=True)
            def forbidden_process(*args, **kwargs):
                raise ValueError('Subprocess/OS command execution forbidden in source import check')
            def profile(frame, event, arg):
                if event != 'call':
                    return
                filename = Path(frame.f_code.co_filename)
                if not filename.is_absolute() or not filename.resolve().is_relative_to(root / 'android'):
                    return
                name = frame.f_code.co_name
                qualified = getattr(frame.f_code, 'co_qualname', name)
                require(name not in {'build', 'main', 'graft_donor', 'compose', 'apply'}, 'Recipe/build call forbidden: ' + qualified)
                require(not (name == '__init__' and any(v in qualified for v in ('SwfAbc.', 'R11Editor.', 'PoolEditor.'))),
                        'Carrier/editor construction forbidden: ' + qualified)
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(builtins, 'open', guarded_open))
                stack.enter_context(patch.object(io, 'open', guarded_open))
                stack.enter_context(patch.object(importlib.machinery.SourceFileLoader, 'get_code', source_get_code))
                for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
                    stack.enter_context(patch.object(subprocess, name, forbidden_process))
                stack.enter_context(patch.object(os, 'system', forbidden_process))
                if hasattr(os, 'startfile'):
                    stack.enter_context(patch.object(os, 'startfile', forbidden_process))
                sys.setprofile(profile)
                spec = importlib.util.spec_from_file_location('_sp_android_port_contract', cap / 'port_capabilities.py')
                port = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = port
                spec.loader.exec_module(port)
                require(isinstance(port.R11Editor, type) and issubclass(port.R11Editor, port.framework.Editor), 'R11Editor API missing')
                for name in ('graft_donor', 'load', 'compose', 'envelope', 'body_bytes', 'digest'):
                    require(callable(getattr(port, name, None)), 'Port API missing: ' + name)
                for name in ('decode', 'encode', 'assemble'):
                    require(callable(getattr(port.asm, name, None)), 'Assembler API missing: ' + name)
                require(callable(port.bodies.resolve) and hasattr(port.framework.FMT, 'R') and hasattr(port.framework.FMT, 'W'), 'Parser APIs missing')
                require(port.BASE == marker and port.DONOR_PATH == marker, 'Explicit private fixture roles did not bind')
                require(port.ROOT.is_relative_to(temp / 'work') and port.REFERENCES == root / 'android/upstream', 'Source/output boundary differs')
                available = {row[0] for row in port.GROUPS}
                require(all(row['name'] in available for row in order['ordered_groups']), 'Profile references an absent group')
                require(not (temp / 'work').exists(), 'Import created output directories')
                sys.setprofile(saved_profile)
            checks.append({'name': 'private_fixture_import_only', 'passed': True,
                           'apis': ['R11Editor', 'graft_donor', 'compose', 'envelope', 'body_bytes', 'digest', 'asm', 'bodies', 'framework.FMT'],
                           'source_or_config_reads': len(opened), 'carrier_marker_read': False,
                           'editor_constructed': False, 'business_methods_executed': 0, 'processes_launched': 0})
    finally:
        sys.setprofile(saved_profile)
        sys.path[:] = saved_path
        sys.dont_write_bytecode = saved_bytecode
        os.environ.clear()
        os.environ.update(saved_env)
        for name in list(sys.modules):
            if name not in saved_modules:
                del sys.modules[name]
        sys.modules.update(saved_modules)
        restored = (sys.path == saved_path and dict(os.environ) == saved_env
                    and sys.dont_write_bytecode == saved_bytecode
                    and set(sys.modules) == set(saved_modules)
                    and all(sys.modules[name] is value for name, value in saved_modules.items()))
        require(restored, 'Interpreter environment/modules were not restored')
    checks.append({'name': 'environment_and_sys_modules_restored', 'passed': restored})


def run(candidate, repository, scratch_parent):
    root = source_root(candidate)
    checks = []
    capabilities = read_json(root / 'android/capabilities/SOURCE-MANIFEST.json')
    manifest_files(root, capabilities, 'capabilities_source_manifest', checks)
    require(capabilities['sourceDependencyClosureCount'] == 105 and capabilities['extraInterpreterQaSources'] == 4,
            'Capability source/QA closure counts differ')
    dependency_files(capabilities['repositoryDependencies'], candidate, repository, checks, 'capabilities_repository_dependencies')
    support = read_json(root / 'android/test-support/SOURCE-MANIFEST.json')
    manifest_files(root / 'android', support, 'android_test_support_manifest', checks)
    dependencies = read_json(root / 'android/test-support/DEPENDENCIES.json')
    dependency_files(dependencies['repository_files'], candidate, repository, checks, 'test_support_repository_dependencies')
    manifest_files(root, {'files': dependencies['release_source_files']}, 'test_support_release_dependencies', checks)
    resources = read_json(root / 'android/resources/SOURCE-MANIFEST.json')
    manifest_files(root / 'android/resources', resources, 'resource_source_manifest', checks)
    dependency_files(read_json(root / 'android/resources/REPOSITORY-DEPENDENCIES.json'), candidate, repository,
                     checks, 'resource_repository_dependencies')
    order = check_contracts(root, checks)
    import_apis(root, scratch_parent, order, checks)
    return {'status': 'passed_android_source_contract_and_import_only', 'checks': checks,
            'carrier_reconstruction_run': False, 'binary_payload_read': False, 'sdk_or_java_launched': False,
            'executed_business_methods': 0, 'main_repository_modified': False,
            'boundary': 'Source hashes/AST/JSON and declaration/API imports only; no payload, build, AIR, package or gameplay validation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    candidate, repository, output = args.candidate.resolve(), args.repository.resolve(), args.output.resolve()
    require(not output.exists() and output.parent.is_dir(), 'Fresh output with existing external parent required')
    require(not output.is_relative_to(candidate) and not output.is_relative_to(repository), 'Output must be external to both source trees')
    try:
        report = run(candidate, repository, output.parent)
        code = 0
    except Exception as error:
        report = {'status': 'failed_android_source_contract_or_import', 'error': type(error).__name__ + ': ' + str(error),
                  'carrier_reconstruction_run': False, 'executed_business_methods': 0}
        code = 1
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'output': str(output)}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
