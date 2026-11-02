"""Prepare isolated native active-FX workspaces and build three-group visual resources.

No art/mechanics copying, preview player, source writes, services or publication.
The pinned toolchain supports caster/field/hit, normal alpha, and empty sounds only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
SKILL = Path(__file__).resolve().parent.parent
CATALOG = Path(os.environ.get('STARPOINT_ACTIVE_CASES', SKILL / 'references/active-skill-cases.json')).resolve()
WORK_ROOT = Path(os.environ.get('STARPOINT_WORK_ROOT', Path.cwd() / 'work')).resolve()
TOOLS = ('compile_parts.py', 'packing_optimized.py', 'readback_native.py')
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
            *(f'LPT{i}' for i in range(1, 10))}


class PipelineError(ValueError):
    pass


def require(value, message):
    if not value:
        raise PipelineError(message)


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def entry_sha(case):
    return hashlib.sha256(json.dumps(case, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def name(value, label):
    require(isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value),
            f'{label} must be one lowercase name, no dots, spaces or path separators')
    require(value.upper() not in RESERVED, f'{label} is a reserved Windows name')
    return value


def namespace_for(code):
    require(isinstance(code, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', code),
            'character-code must be explicit lowercase letters/digits/underscore, beginning with a letter')
    require(code.upper() not in RESERVED, 'character-code is a reserved Windows name')
    return 'battle/effect/skill_unique/' + code


def bounded(path):
    p = Path(path).resolve()
    require(p != WORK_ROOT and p.is_relative_to(WORK_ROOT),
            'Workspace/output must resolve strictly inside STARPOINT_WORK_ROOT')
    require(not p.is_relative_to(SKILL.parents[1]), 'Source-repository output forbidden')
    return p


def catalog_case(case_id):
    catalog = read(CATALOG)
    require(catalog.get('format') == 1, 'Unsupported catalog format')
    matches = [c for c in catalog['cases'] if c['id'] == case_id]
    require(len(matches) == 1, 'Expected one catalog case: ' + case_id)
    case = matches[0]
    for item in [*case['tools'], *case['files'], *case.get('toolchainFiles', [])]:
        item['path'] = str((CATALOG.parent / item['path']).resolve())
    return case


def check_case(case):
    bindings = [*case['tools'], *case['files'], *case.get('toolchainFiles', [])]
    actual = []
    require({x['name'] for x in case['tools']} == set(TOOLS), 'Case must pin exactly three supported tools')
    for item in bindings:
        p = Path(item['path'])
        require(p.is_file(), 'Missing pinned case file: ' + str(p))
        digest = sha(p)
        require(digest == item['sha256'], 'Case file/tool SHA drift: ' + str(p))
        actual.append({'path': str(p), 'sha256': digest})
    return actual


def prepare(args):
    case = catalog_case(args.case)
    prefix = namespace_for(args.character_code)
    out = bounded(args.out)
    require(not out.exists(), 'Preserve existing workspace; choose a new --out')
    require(out.parent.is_dir(), 'Workspace parent must already exist')
    for component in out.relative_to(WORK_ROOT).parts:
        require(component.rstrip(' .') == component and component.split('.')[0].upper() not in RESERVED,
                'Unsafe workspace path component')
    identities = check_case(case)  # Nothing is written until all case identities match.
    if args.budget_pixels is None:
        budget = dict(case['budgetTemplate'])
        budget['source'] = 'case_template_reference_not_an_official_or_new_character_limit'
    else:
        require(args.budget_pixels > 0, 'Budget must be positive')
        budget = {'paddedPixels': args.budget_pixels, 'scope': 'caller-selected active caster/field/hit sheets only',
                  'source': 'explicit --budget-pixels; whole character and battle remain unknown'}
    require(isinstance(budget.get('paddedPixels'), int) and budget['paddedPixels'] > 0 and budget.get('scope'),
            'Case budget needs positive paddedPixels and explicit scope')
    out.mkdir()
    engineering = out / 'engineering'
    engineering.mkdir()
    (out / 'art').mkdir()
    copied = []
    for tool in case['tools']:
        target = engineering / tool['name']
        shutil.copyfile(tool['path'], target)
        require(sha(target) == tool['sha256'], 'Copied tool identity mismatch')
        copied.append({'name': tool['name'], 'path': str(target), 'sha256': tool['sha256']})
    config = {'format': 1, 'kind': 'isolated_native_active_visual_workspace', 'case': case['id'],
              'catalog': str(CATALOG), 'catalogEntrySha256': entry_sha(case),
              'characterCode': args.character_code, 'namespace': prefix, 'budget': budget,
              'tools': copied, 'caseInputsChecked': identities,
              'constraints': {'groups': ['caster', 'field', 'hit'], 'blend': 'normal only',
                              'sounds': 'none; no registration or new dynamic sound support',
                              'previewPlayer': 'not provided; existing V12 player is character-specific'},
              'gameIntegrated': False, 'sourceRepositoryWrites': False, 'releaseReady': False}
    write(out / 'pipeline.json', config)
    draft = {'format': 1, 'pipelineDraft': True, 'version': 'unmade-active-presentation',
             'description': 'Empty scaffold. Author and review art/motion separately; remove pipelineDraft before build.',
             'assets': [], 'groups': [{'id': g, 'durationTicks': None, 'partsScale': None, 'instances': []}
                                     for g in ['caster', 'field', 'hit']]}
    write(out / 'art/composition-spec.json', draft)
    (out / 'README.txt').write_text(
        'This workspace contains only three byte-exact compiler/readback tools and an EMPTY draft.\n'
        'No character PNG, motion, identity, DSL, balance or sound was copied.\n'
        f'Explicit namespace: {prefix}\n'
        'Write new/reviewed RGBA art and caster/field/hit matrices, ticks and origins before building.\n'
        'Normal alpha only; no additive blend, masks or newly registered sounds.\n'
        'Budget is an active-sheet allocation/reference, never whole-character/battle/performance proof.\n'
        'Reference case (read only): ' + case['id'] + '\n'
        + '\n'.join(f"{x['role']}: {x['path']}" for x in case['files']) + '\n'
        + '\n'.join(case['lessons']) + '\n', 'utf-8')
    return {'status': 'prepared_empty_isolated_workspace', 'workspace': str(out), 'namespace': prefix,
            'budget': budget, 'artCopied': False, 'mechanicsCopied': False, 'gameIntegrated': False}


def load_workspace(path):
    workspace = bounded(path)
    config = read(workspace / 'pipeline.json')
    require(config.get('format') == 1 and config.get('kind') == 'isolated_native_active_visual_workspace',
            'Not a prepared pipeline workspace')
    require(config.get('namespace') == namespace_for(config.get('characterCode')), 'Workspace namespace/code drift')
    case = catalog_case(config['case'])
    require(config['catalogEntrySha256'] == entry_sha(case), 'Pinned catalog entry changed; review and prepare a new workspace')
    check_case(case)
    engineering = (workspace / 'engineering').resolve()
    require(engineering.is_relative_to(workspace) and engineering.is_dir(), 'Engineering directory escaped workspace')
    copied = {x['name']: x for x in config['tools']}
    require(set(copied) == set(TOOLS), 'Prepared tool set changed')
    for tool in case['tools']:
        target = engineering / tool['name']
        require(target.resolve().is_relative_to(engineering), 'Copied tool escaped engineering')
        require(copied[tool['name']]['sha256'] == tool['sha256'] and sha(target) == tool['sha256'],
                'Copied tool SHA drift: ' + str(target))
    budget = config['budget']
    require(type(budget.get('paddedPixels')) is int and budget['paddedPixels'] > 0 and budget.get('scope'),
            'Workspace budget needs explicit positive pixels and scope')
    return workspace, config, engineering


def validate_spec(spec):
    require(not spec.get('pipelineDraft'), 'Empty draft is not buildable: author art/motion and remove pipelineDraft')
    require(set(spec) <= {'format', 'version', 'description', 'assets', 'groups', 'assetRoot', 'pipelineDraft'},
            'Unsupported top-level fields; no ignored sound/blend/mechanics declarations')
    require(spec.get('format') == 1 and spec.get('assets'), 'format1 and authored RGBA assets required')
    require(len(spec.get('groups', [])) == 3 and {g['id'] for g in spec['groups']} == {'caster', 'field', 'hit'},
            'Exactly caster/field/hit groups supported')
    for asset in spec['assets']:
        require(set(asset) <= {'id', 'path', 'origin', 'sha256'}, 'Unsupported asset declaration')
    for group in spec['groups']:
        require(set(group) <= {'id', 'durationTicks', 'partsScale', 'layerZDepth', 'instances'},
                'Unsupported group fields: normal blend/empty sounds only')
        for inst in group.get('instances', []):
            for key in inst.get('keys', []):
                require(set(key) <= {'tick', 'matrix', 'alpha', 'interpolation'},
                        'Unsupported key fields; blend/masks/sounds are not implemented')


def load_module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def build(args):
    workspace, config, engineering = load_workspace(args.workspace)
    output = engineering / name(args.name, 'build name')
    require(output.resolve().is_relative_to(engineering) and not output.exists(),
            'Build output must be a new engineering child; existing exports are preserved')
    spec_path = Path(args.spec).resolve()
    require(spec_path.is_file(), '--spec must name an existing authored spec')
    validate_spec(read(spec_path))
    spec_digest = sha(spec_path)
    # The compiler's HERE stays in the prepared engineering directory. Prefix is
    # changed in memory; the copied compiler remains byte-identical to the case.
    sys.path.insert(0, str(engineering))
    compiler = load_module('compile_parts', engineering / 'compile_parts.py')
    load_module('packing_optimized', engineering / 'packing_optimized.py')
    readback = load_module('active_skill_readback', engineering / 'readback_native.py')
    compiler.PREFIX = config['namespace']
    result = {'status': 'failed_isolated_native_visual_build', 'workspace': str(workspace),
              'namespace': config['namespace'], 'spec': str(spec_path), 'specSha256': spec_digest,
              'output': str(output), 'gameIntegrated': False, 'deviceVerified': False,
              'wholeCharacterBudget': 'unknown', 'wholeBattlePacking': 'unknown',
              'runtimePerformance': 'unknown', 'aestheticAcceptance': 'not tested', 'releaseReady': False}
    try:
        compiler.compile_spec(spec_path, output)
        require(sha(spec_path) == spec_digest, 'Spec changed during compile')
        native = read(output / 'render_ops.json')
        require(native['specSha256'] == spec_digest, 'Compiled spec identity mismatch')
        resources = read(output / 'overlay.json')['resources']
        require(all(r['logical'].startswith(config['namespace'] + '/') for r in resources), 'Resource namespace mismatch')
        proof = readback.verify(output)
        rows = [{'id': g['id'], 'sheetSize': g['sheetSize'], 'paddedSheetPixels': g['paddedSheetPixels'],
                 'imageTypes': len(g['images']), 'poolSum': g['poolSum'],
                 'leafCommandPeak': g['maxImageCommandsPerTick']} for g in native['groups']]
        pixels = sum(g['paddedSheetPixels'] for g in native['groups'])
        limit = config['budget']['paddedPixels']
        passed = pixels <= limit
        budget = {'status': 'passed_active_subset_budget' if passed else 'failed_active_subset_budget',
                  'renderOpsSha256': sha(output / 'render_ops.json'), 'groups': rows,
                  'activeSubset': {'paddedSheetPixels': pixels, 'percentageOf4096Squared': pixels/4096**2*100,
                                   'budgetPixels': limit, 'scope': config['budget']['scope']},
                  'automaticResizingPerformed': False, 'wholeCharacterBudget': 'unknown', 'wholeBattlePacking': 'unknown'}
        write(output / 'pipeline-budget.json', budget)
        result.update(nativeReadback=proof, activeSubsetBudget=budget,
                      nativeRenderOpsSha256=sha(output / 'render_ops.json'),
                      nativeResourceIdentities=[{k: r[k] for k in ['logical', 'path', 'sha256']} for r in resources])
        require(passed, f'Actual active sheets {pixels} exceed budget {limit}; no automatic texture reduction')
        result['status'] = 'passed_isolated_native_visual_build'
        result['limits'] = ['Exactly caster/field/hit, normal alpha, no new sounds.',
                            'No gameplay DSL, dependency closure, preview player, art or author acceptance generated.',
                            'Resource-chain integration, source writes and publication were not performed.']
        write(output / 'pipeline-result.json', result)
        return result
    except Exception as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        if output.is_dir():
            write(output / 'pipeline-result.json', result)
        raise


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list', help='List pinned cases; does not build or select a character')
    inspect = sub.add_parser('inspect', help='Check case tools/reference file SHA identities')
    inspect.add_argument('--case', required=True)
    prep = sub.add_parser('prepare', help='New workspace under STARPOINT_WORK_ROOT; tools and empty art draft only')
    prep.add_argument('--case', required=True)
    prep.add_argument('--character-code', required=True)
    prep.add_argument('--out', type=Path, required=True)
    prep.add_argument('--budget-pixels', type=positive)
    compile_cmd = sub.add_parser('build', help='Build named NEW output from explicit authored spec; no preview/integration')
    compile_cmd.add_argument('--workspace', type=Path, required=True)
    compile_cmd.add_argument('--spec', type=Path, required=True)
    compile_cmd.add_argument('--name', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'list':
            output = {'cases': [{k: c[k] for k in ['id', 'title', 'acceptedPreview', 'gameIntegrated']}
                                for c in read(CATALOG)['cases']]}
        elif args.command == 'inspect':
            case = catalog_case(args.case)
            output = {'case': case, 'identities': check_case(case), 'status': 'passed_case_file_identities'}
        elif args.command == 'prepare':
            output = prepare(args)
        else:
            output = build(args)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error': {'type': type(exc).__name__, 'message': str(exc)},
                          'gameIntegrated': False, 'releaseReady': False}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
