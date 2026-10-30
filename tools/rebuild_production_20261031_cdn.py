#!/usr/bin/env python3
"""Inspect or rebuild one adopted CDN recipe into a new external directory.

This source-preservation entry does not create version edges, ZIPs, manifests,
server data or deployment/acceptance records. No network or child processes.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from production_20261031_cdn.common import Context, SparseChain, file_sha, member, read_json, sha

MODULES = {'release344', 'town345', 'art346347', 'ticket348', 'lich349', 'town350'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--check-spec', action='store_true', help='Parse source/spec and check bundled inputs; never generate resources')
    parser.add_argument('--verify-external-inputs', action='store_true', help='Also require and verify every declared external input')
    parser.add_argument('--external-inputs', type=Path, help='Local alias-to-path JSON; keep actual locations outside Git')
    parser.add_argument('--phase', choices=('346', '347'))
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--active', action='append', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--baseline-version', default='1.4.54')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resource', action='append', help='Optional root:logical output filter; generation cost depends on the selected recipe')
    parser.add_argument('--output-limit-mib', type=int, default=32)
    args = parser.parse_args()
    spec = read_json(args.spec)
    name = spec['module'].replace('\\', '/').split('/')[-1].removesuffix('.py').split('.')[-1]
    if name not in MODULES:
        parser.error('Unknown adopted recipe module')
    module_path = Path(__file__).parent / 'production_20261031_cdn' / (name + '.py')
    ast.parse(module_path.read_text('utf-8-sig'), filename=module_path.name)
    if args.phase:
        spec['phase'] = args.phase
    if name == 'art346347' and not args.phase:
        parser.error('Art recipes require an explicit --phase 346 or 347')
    locations = read_json(args.external_inputs) if args.external_inputs else {}
    context = Context(args.repo, args.spec, spec, locations)
    inputs = spec.get('inputs', [])
    if isinstance(inputs, dict):
        inputs = list(inputs.values())
    if isinstance(spec.get('input'), dict):
        inputs = [*inputs, spec['input']]
    checked = []
    for entry in inputs:
        relative = entry.get('path', entry.get('relative'))
        if relative is None:
            raise ValueError('Bundled input needs path/relative')
        path = context.input(relative)
        if file_sha(path) != entry['sha256']:
            raise ValueError('Bundled input identity mismatch: ' + relative)
        checked.append(relative)
    for entry in spec.get('externalInputs', []):
        if entry.get('kind') != 'directory' and re.fullmatch('[0-9a-f]{64}', entry.get('sha256', '')) is None:
            raise ValueError('External input needs an exact SHA-256')
        if args.verify_external_inputs:
            context.external(entry['alias'])
    if args.check_spec:
        print(json.dumps({'status': 'source_and_spec_parse_passed', 'module': name,
                          'bundledInputsChecked': checked,
                          'externalInputsDeclared': list(context.external_specs),
                          'externalInputsVerified': sorted(context._checked_external),
                          'resourceGenerationRun': False, 'sourceClosureRequiresDeclaredExternalInputs': True}, ensure_ascii=False))
        return
    if not all((args.manifest, args.active, args.baseline, args.output)):
        parser.error('Build requires --manifest, --active, --baseline and a fresh --output')
    phase = spec.get('phases', {}).get(spec.get('phase'), {})
    base = phase.get('baseVersion', spec.get('baseVersion'))
    if not base:
        parser.error('Recipe must declare its baseline version')
    if not 1 <= args.output_limit_mib <= 128:
        parser.error('Output limit must be between1 and128 MiB')
    out = args.output.resolve()
    protected = [args.repo.resolve(), args.spec.resolve().parent, args.baseline.resolve(), *[x.resolve() for x in args.active]]
    protected.extend(Path(locations[alias]).resolve() for alias in context.external_specs if alias in locations)
    if out.exists() or any(out.is_relative_to(x) or x.is_relative_to(out) for x in protected):
        parser.error('Output must be a new directory outside the repository and all input roots')
    context.chain = SparseChain(args.manifest, args.active, args.baseline, base, args.baseline_version)
    module = importlib.import_module('production_20261031_cdn.' + name)
    payloads = module.build(context, spec)
    if not isinstance(payloads, dict) or not payloads:
        raise ValueError('Recipe produced no resource dictionary')
    selected = set(args.resource or [])
    if selected:
        missing = selected - {root + ':' + logical for root, logical in payloads}
        if missing:
            raise ValueError('Requested resource not produced: ' + ','.join(sorted(missing)))
        payloads = {key: raw for key, raw in payloads.items() if key[0] + ':' + key[1] in selected}
    if sum(map(len, payloads.values())) > args.output_limit_mib * 1024 * 1024:
        raise ValueError('Recipe output exceeds explicit output limit; split work instead of raising process limits')
    outputs = {}
    for (root, logical), raw in payloads.items():
        if not isinstance(raw, bytes):
            raise TypeError('Resource payload must be bytes')
        path = member(root, logical)
        if path in outputs:
            raise ValueError('Two logical resources map to one output member')
        outputs[path] = raw
    proof = {'schemaVersion': 1, 'recipe': args.spec.name, 'recipeSha256': file_sha(args.spec),
             'module': name, 'baselineVersion': base, 'suppliedManifestSha256': sha(context.chain.raw),
             'recipeHistoricalBaselineManifestSha256': spec.get('baselineManifestSha256'),
             'resources': [{'member': key, 'bytes': len(raw), 'sha256': sha(raw)} for key, raw in sorted(outputs.items())],
             'baselineReads': context.chain.reads, 'externalInputAliasesVerified': sorted(context._checked_external),
             'archiveManifestOrSourceWritten': False, 'deviceVerified': False}
    out.mkdir(parents=True)
    for relative, raw in outputs.items():
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        if path.read_bytes() != raw:
            raise OSError('Output readback mismatch')
    (out / 'recipe-proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({'status': 'isolated_resource_recipe_output_written', 'resources': len(outputs), 'output': str(out),
                      'archivesGenerated': False, 'manifestWritten': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
