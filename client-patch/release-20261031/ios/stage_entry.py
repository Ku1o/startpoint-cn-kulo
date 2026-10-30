"""Dispatch repository recipes only inside an explicitly allocated bounded Job."""
from pathlib import Path
import argparse, json, os, runpy, sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import input_config as cfg
sys.path.insert(0, cfg.local('support/process'))
from job_guard import require_bounded_job

ENTRIES = {
    'inspect': 'repairs/scripts/inspect_stage1.py',
    'freeze': 'repairs/scripts/freeze_sources.py',
    'sidecar': 'repairs/scripts/compile_sidecar.py',
    'prepare': 'repairs/scripts/prepare_repairs.py',
    'native': 'repairs/scripts/run_native_stage.py',
    'check': 'repairs/scripts/verify_repairs.py',
    'atom': 'repairs/scripts/verify_atom_abi.py',
    'settings-prepare': 'settings/prepare_revision.py',
    'settings-link': 'settings/recipe/link_grouped.py',
    'settings-platform': 'settings/recipe/apply_draw.py',
    'settings-finalize': 'settings/recipe/finalize_final.py',
    'settings-contract': 'settings/recipe/verify_contract.py',
    'settings-check': 'settings/recipe/verify_final.py',
    'settings-abi': 'settings/verify_actual_abi.py',
    'settings-degree': 'settings/verify_degree_retraction.py',
    'settings-package': '@package',
    'settings-compile': '@compile',
}

def outputs(entry, arguments):
    for option in ('--output', '--detail-output'):
        if option not in arguments:
            continue
        at = arguments.index(option)
        path = Path(arguments[at + 1]).resolve()
        if not path.is_relative_to(cfg.work()) or path == cfg.work():
            raise ValueError('Output must stay in private work_dir/ios')
        updating = entry == 'settings-finalize' or (entry == 'native' and arguments[:1] == ['finalize'])
        if path.exists() and not updating:
            raise ValueError('Fresh output required: ' + str(path))
    for option in ('--inspection', '--source-contract', '--sidecar-report', '--prepared', '--compiled', '--linked', '--package-report', '--verification'):
        if option in arguments:
            artifact = Path(arguments[arguments.index(option) + 1]).resolve()
            if not artifact.is_relative_to(cfg.work()):
                raise ValueError('Generated artifact must stay in private work_dir/ios: ' + option)
    # Existing finalizers intentionally update only the new pending link output;
    # their original pending-state and strict metadata guards remain unchanged.

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('entry', choices=sorted(ENTRIES))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    options = parser.parse_args()
    arguments = options.arguments
    if arguments[:1] == ['--']:
        arguments = arguments[1:]
    require_bounded_job(180)
    manifest = json.loads((HERE / 'SOURCE-MANIFEST.json').read_text('utf-8-sig'))
    for row in manifest['files'] + manifest['repository_dependencies']:
        cfg.require_sha(cfg.repo(row['repository_path']), row['sha256'])
    outputs(options.entry, arguments)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # process-local, inherited children
    cfg.bootstrap()
    if options.entry != 'inspect':
        cfg.bind_tools()
    selected = ENTRIES[options.entry]
    if selected == '@compile':
        import compile_port
        inner = argparse.ArgumentParser()
        inner.add_argument('--prepared', type=Path, required=True)
        inner.add_argument('--output', type=Path, required=True)
        args = inner.parse_args(arguments)
        if args.output.exists():
            raise ValueError('Fresh compile output required')
        compile_port.run(args.prepared, args.output, sdk=Path(cfg.path('sdk')),
                         dependencies=Path(cfg.path('dependencies')),
                         background=Path(cfg.local('support/process/run_background.py')),
                         timeout=165)
        return
    if selected == '@package':
        selected = cfg.repo('client-patch/ios-r11-port/package_stage.py')
    else:
        selected = cfg.local(selected)
    sys.path.insert(0, str(Path(selected).parent))
    sys.argv = [selected, *arguments]
    runpy.run_path(selected, run_name='__main__')

if __name__ == '__main__':
    main()
