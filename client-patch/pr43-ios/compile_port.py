"""Compile a prepared iOS AOT delta without invoking historical build mains."""
from __future__ import annotations

import argparse
import copy
import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path

from native_support import (backend, dump, input_path,
                            read_report, sha, verify_warnings, wanted_methods)


def verify_symbols(directory, objects, wanted):
    link = backend()
    found = set()
    for row in objects:
        obj = link.lief.parse(str(Path(directory) / row['name']))
        for symbol in obj.symbols:
            match = re.search(r':(\d+):', link.aot.text(symbol.name))
            if symbol.numberof_sections and match and int(match.group(1)) in wanted:
                found.add(int(match.group(1)))
    return dict(expected=sorted(wanted), found=sorted(found), missing=sorted(wanted - found))


def compile_input(full, wanted):
    link = backend()
    from fill_ios_aot_stub_bodies import return_stub
    abc = link.abcfmt.ABC(full)
    # Stripped native carriers retain declaration traits but no newclass code
    # in their global initializers. AOT discovers class methods by visiting
    # those declarations; a real body alone does not make a method reachable.
    owners = set()
    for ci, (instance, cls) in enumerate(zip(abc.instances, abc.classes)):
        declared = {instance[5], cls[0]}
        for trait in instance[6] + cls[1]:
            if trait.kind in (1, 2, 3):
                declared.add(trait.data[2])
        if declared & wanted:
            owners.add(ci)
    declarations = {}
    for script_mid, traits in abc.scripts:
        classes = [t.data[2] for t in traits if t.kind == 4 and t.data[2] in owners]
        if classes:
            declarations[script_mid] = classes
    contexts = []
    replaced = []
    for index, body in enumerate(abc.bodies):
        if body[0] in wanted:
            continue
        if body[0] in declarations:
            stub = copy.deepcopy(body)
            rows = [('getlocal_0',), ('pushscope',)]
            for ci in declarations[body[0]]:
                name, superclass = abc.instances[ci][:2]
                assert superclass, ('compiler class has no base', ci)
                rows.extend([('getglobalscope',), ('getlex', superclass), ('pushscope',),
                             ('getlex', superclass), ('newclass', ci), ('popscope',),
                             ('initproperty', name)])
            rows.append(('returnvoid',))
            stub[1] = 2
            stub[4] = stub[3] + 2
            stub[5] = link.asm.encode(link.asm.assemble(rows))[0]
            stub[6] = []
            abc.bodies[index] = stub
            contexts.append(dict(method_id=body[0], classes=declarations[body[0]],
                                 code_sha256=sha(stub[5]), runtime_linked=False))
            continue
        stub = copy.deepcopy(body)
        stub[1] = max(stub[1], 1)
        stub[5] = return_stub(abc.mn_name(abc.methods[body[0]][0]))
        stub[6] = []
        # Keep body traits and NEED_ACTIVATION flags. Only code is discarded;
        # those traits still define compiler-visible old activation layouts.
        abc.bodies[index] = stub
        replaced.append(body[0])
    return abc.serialize(), replaced, contexts


def run(prepared, directory, *, sdk, dependencies, background, optimization='1', timeout=600, delta_stubs=True):
    sdk, dependencies, background = Path(sdk), Path(dependencies), Path(background)
    assert background.is_file(), 'Background wrapper is required'
    prepared, port = read_report(prepared)
    directory = Path(directory).resolve()
    assert not directory.exists(), ('fresh compile directory required', str(directory))
    source = input_path(prepared, port['full_abc_file']).read_bytes()
    assert sha(source) == port['full_abc_sha256']
    wanted = wanted_methods(port)
    compiler_source, replaced, contexts = compile_input(source, wanted) if delta_stubs else (source, [], [])
    compiler = sdk / 'lib/aot/bin/compile-abc/compile-abc-64.exe'
    from fixed_inputs import check_dependencies
    deps = check_dependencies(dependencies)
    assert sha(compiler.read_bytes()) == '4d37897f71d7cec73c5e9fc108fc130678dab33d711616fcfc35f42119112943', 'Compiler identity mismatch'
    assert len(deps) == 284 and compiler.is_file()
    directory.mkdir(parents=True)
    cumulative = directory / 'cumulative.abc'
    cumulative.write_bytes(compiler_source)
    args = [str(compiler), '-mtriple=arm64-apple-ios',
            '-fields=' + str(sdk / 'lib/aot/lib/air-fields.arm64-air.txt'),
            '-sdk=' + str(sdk / 'lib/aot/lib/avmglue.abc'),
            '-O=' + optimization, '-verify-warnings', *map(str, deps), str(cumulative)]
    log_path = directory / 'compiler.log'
    started = time.monotonic()
    # compile-abc may spawn windowed child tools. All compilation runs through
    # the existing private desktop wrapper, including command-line invocations.
    command = [sys.executable, str(background), '--timeout', str(timeout),
               '--cwd', str(directory), '--', *args]
    with log_path.open('wb') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                timeout=timeout + 30, check=False)
    assert result.returncode == 0, ('compiler failed', result.returncode, str(log_path))
    warnings = verify_warnings(log_path, wanted)
    objects = [dict(name=p.name, bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
               for p in sorted(directory.glob('cumulative*.o'))]
    assert objects, ('no AOT objects', str(log_path))
    coverage = verify_symbols(directory, objects, wanted)
    report = dict(status='missing_target_symbols' if coverage['missing'] else 'compiled_native_not_executed', directory=str(directory),
                  prepared_report=str(prepared), prepared_report_sha256=sha(prepared.read_bytes()),
                  full_abc_sha256=sha(source), full_abc_sha1=hashlib.sha1(source).hexdigest(),
                  compile_input_sha256=sha(compiler_source),
                  compile_input_sha1=hashlib.sha1(compiler_source).hexdigest(),
                  delta_stubs=delta_stubs, stubbed_methods=len(replaced),
                  compiler_only_lifecycles=contexts,
                  tracked_methods=sorted(wanted), objects=objects, verifier_warnings=warnings,
                  target_symbol_coverage=coverage,
                  elapsed_seconds=round(time.monotonic() - started, 2), optimization=optimization,
                  compiler=str(compiler), compiler_sha256=sha(compiler.read_bytes()),
                  native_executed=False, device_tested=False)
    dump(directory / 'compile-report.json', report)
    assert not coverage['missing'], ('missing compiled methods', coverage['missing'])
    print('Compiled', len(objects), 'objects;', len(wanted), 'target methods;',
          sum(x['bytes'] for x in objects), 'object bytes')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--background', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--optimization', choices=['0', '1'], default='1')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--no-delta-stubs', action='store_true')
    args = parser.parse_args()
    run(args.prepared, args.out, sdk=args.sdk, dependencies=args.dependencies, background=args.background,
        optimization=args.optimization, timeout=args.timeout,
        delta_stubs=not args.no_delta_stubs)


if __name__ == '__main__':
    main()
