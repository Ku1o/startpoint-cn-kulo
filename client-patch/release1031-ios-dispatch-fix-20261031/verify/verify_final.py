"""Independent inherited-dispatch repair validation.

Run inside the existing bounded Python 3.13 engineering Job. The default mode
reads the final IPA; --semantic-only verifies the prepared ABC before packaging.
All reports stay under this task's verify-review directory. No build runs.
"""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()

import argparse
import ast
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
import abc_contract
import dispatch_contract
import native_contract
import package_contract
import semantic_contract

TASK = Path(str(fc.client() / 'revision-ios-dispatch-fix-20261031'))
VERIFY_OUTPUT = TASK / 'verify-review'
SOURCE = dispatch_contract.SOURCE / 'client-patch'
LIBRARIES = Path(str(fc.private('libraries')))
BASELINE_RECEIPT = Path(str(fc.private('followup_public_verification')))
CURRENT_FULL = TASK.parent / 'revision-public-admission-20261031/ios/build01/full.abc'
ORIGINAL_FULL = Path(str(fc.private('outputs_ios_r11_cumulative_compact_20261025_ios_full_equipment_r11_compact_20261025_abc')))
ORIGINAL_SHA = 'ff1ac16421ed0d394b70612aed23584e30c0aa9ec1de0eebe4336cc1cb396388'
PRIOR_REPORTS = [TASK.parent / 'revision-settings/ios/linked01/link-report.json',
                 TASK.parent / 'revision-ios-acceptance-repairs/runs/link03/link-report.json']
PROOFS = {}


def read(path, maximum=32 * 1024**2):
    path = Path(path)
    dispatch_contract.require(path.is_file() and path.stat().st_size <= maximum, 'JSON input size/path bound')
    return json.loads(path.read_text('utf-8-sig'))


def dump(path, value):
    path = Path(path).resolve()
    dispatch_contract.require(path.is_relative_to(VERIFY_OUTPUT.resolve()), 'Report outside assigned verify-review')
    dispatch_contract.require(not path.exists(), 'Existing verification report refused: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write('\n')


def framework():
    sys.path[:0] = [str(LIBRARIES), str(SOURCE / 'lens0907-0908'),
                    str(SOURCE / 'pr43-ios'), str(SOURCE / 'ios-r11-port')]
    import verify_stages as stage
    return stage


def require_job():
    import importlib.util
    path = SOURCE / 'release1031-ios-dispatch-fix-20261031/native/common.py'
    spec = importlib.util.spec_from_file_location('dispatch_verifier_job_guard', path)
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    return common.bounded_job()


def contract_for(prepared_path):
    prepared_path = Path(prepared_path)
    prepared = read(prepared_path)
    relocation_path = Path(prepared['relocation_manifest'])
    if not relocation_path.is_absolute():
        relocation_path = prepared_path.parent / relocation_path
    relocation = read(relocation_path)
    deleted = {}
    for row in relocation['helpers']:
        deleted.setdefault(row['owner'], []).append(int(row['old_mid']))
    return dict(removed_instance_helpers=deleted,
                changed_body_ids=relocation['changed_existing_method_ids'],
                original_full_abc=str(ORIGINAL_FULL), original_full_abc_sha256=ORIGINAL_SHA,
                permitted_override_methods=[101817], prior_aot_link_reports=list(map(str, PRIOR_REPORTS)),
                relocation=relocation, relocation_path=str(relocation_path),
                relocation_sha256=package_contract.file_sha(relocation_path))


def protected(old, new, previous, prepared, linked):
    targets = {int(r['method_id']) for r in prepared['methods'] if r.get('strategy', 'replace') == 'replace'}
    PROOFS['native_wrappers'] = native_contract.verify_wrappers(
        old, new, linked, previous['functions'], targets)
    PROOFS['unwind_page_bounds'] = native_contract.unwind_page_bounds(new)


def restored_table_slots(changed_slots, old, new, linked):
    dispatch_contract.require(native_contract.SPECIALS <= changed_slots.keys(), 'Special compiled slots missing')
    # Actual wrapper pointers and targets were already independently decoded.
    dispatch_contract.require('native_wrappers' in PROOFS, 'Wrapper proof must precede table exclusions')
    return {mid: target for mid, target in changed_slots.items() if mid not in native_contract.SPECIALS}


def chunked_prefix(old, new, allowed):
    exact = list(allowed) + native_contract.prefix_ranges(old)
    PROOFS['native_prefix'] = package_contract.chunked_prefix(old, new, exact)


def adapt_verify(stage):
    """Retain every original stage check except precisely reviewed contracts.

    Allocation, removed traits, and the two wrapper-binding routes need narrow
    adapters. Source shape counts make upstream verifier changes fail closed.
    """
    tree = ast.parse(inspect.getsource(stage.verify))
    fn = tree.body[0]
    changed = dict(prefix=0, protected=0, wrapper_tables=0, equipment=0)
    for index, node in list(enumerate(fn.body)):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'end' for t in node.targets):
            if ast.unparse(node.value) != "old.segments[-1]['off']":
                continue
            following = fn.body[index:index + 4]
            dispatch_contract.require(len(following) == 4
                and 'Unexpected existing native bytes changed' in ast.unparse(following[-1]),
                'Original native prefix verifier changed')
            fn.body[index:index + 4] = ast.parse('_chunked_prefix(old,new,allowed)').body
            changed['prefix'] += 1
            break
    for index, node in list(enumerate(fn.body)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and any(
                isinstance(a, ast.Constant) and a.value == 'Previous native lineage' for a in node.value.args):
            fn.body[index + 1:index + 1] = ast.parse('_protected(old,new,previous,prepared,linked)').body
            changed['protected'] += 1
            break
    for index, node in list(enumerate(fn.body)):
        if isinstance(node, ast.For) and ast.unparse(node.target) == '(mid, target)' \
                and ast.unparse(node.iter) == 'changed_slots.items()':
            fn.body[index:index] = ast.parse(
                'changed_slots=_restored_table_slots(changed_slots,old,new,linked)').body
            changed['wrapper_tables'] += 1
            break
    start = stop = None
    for index, node in enumerate(fn.body):
        if isinstance(node, ast.Assign):
            assigned = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if 'plan' in assigned:
                start = index
            if start is not None and 'detail' in assigned:
                stop = index
                break
    dispatch_contract.require(start is not None and stop is not None and stop - start == 5,
                              'Original equipment verifier shape changed')
    fn.body[start:stop] = ast.parse('plan=_equipment_preservation(old,new,equipment,read)').body
    changed['equipment'] += 1
    dispatch_contract.require(all(value == 1 for value in changed.values()), 'Independent verifier adapter shape mismatch')
    namespace = stage.__dict__.copy()
    namespace.update(_chunked_prefix=chunked_prefix, _protected=protected,
                     _restored_table_slots=restored_table_slots,
                     _equipment_preservation=native_contract.equipment_preservation)
    exec(compile(ast.fix_missing_locations(tree), str(Path(stage.__file__)), 'exec'), namespace)
    return namespace['verify'], changed


def source_identity():
    return {p.name: package_contract.file_sha(p) for p in Path(__file__).parent.glob('*.py')}


def semantic_only(prepared_path, output):
    p = dispatch_contract.framework()
    contract = contract_for(prepared_path)
    prepared = read(prepared_path)
    final_path = Path(prepared['full_abc_file'])
    if not final_path.is_absolute():
        final_path = Path(prepared_path).parent / final_path
    before_raw, after_raw = CURRENT_FULL.read_bytes(), final_path.read_bytes()
    dispatch_contract.require(package_contract.sha(before_raw) == prepared['base_full_abc_sha256']
        and package_contract.sha(after_raw) == prepared['full_abc_sha256'], 'Prepared source ABC identity')
    before, after = map(p.abcfmt.ABC, (before_raw, after_raw))
    declarations = abc_contract.old_class_declarations(before, after, contract['removed_instance_helpers'])
    semantics = semantic_contract.check(before, after, contract['relocation'])
    prior = {int(row['method']) for path in PRIOR_REPORTS for row in read(path)['functions']}
    targets = {int(row['method_id']) for row in prepared['methods'] if row.get('strategy', 'replace') == 'replace'}
    old_targets = targets & set(range(prepared['old_methods']))
    dispatch_contract.require(len(prior) == 356 and old_targets == prior - abc_contract.ORPHAN_IDS
                              and len(old_targets) == 330, 'Prepared retained-AOT recompile closure differs')
    closure = dispatch_contract.conservative_recompile_closure(
        before, after, prior, targets, abc_contract.ORPHAN_IDS)
    original_raw = ORIGINAL_FULL.read_bytes()
    dispatch_contract.require(package_contract.sha(original_raw) == ORIGINAL_SHA, 'Original R11 ABC identity')
    original = p.abcfmt.ABC(original_raw)
    dispatch_proof = dispatch_contract.preserved_old_dispatch(original, after, [101817])
    focus = dispatch_contract.focus_getter(after)
    result = dict(status='independent_prepared_semantics_and_original_dispatch_checked',
                  prepared_report=str(prepared_path), full_abc_sha256=prepared['full_abc_sha256'],
                  base_full_abc_sha256=prepared['base_full_abc_sha256'],
                  relocation_sha256=contract['relocation_sha256'], recompile_closure=closure,
                  declarations=declarations, semantics=semantics, original_dispatch=dispatch_proof,
                  focused_getter=focus, source_sha256=source_identity(),
                  native_compiled_checked=False, native_executed=False, device_tested=False)
    dump(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-report', type=Path)
    parser.add_argument('--semantic-only', type=Path, metavar='PORT_JSON')
    parser.add_argument('--semantic-evidence', type=Path)
    parser.add_argument('--virtuality-evidence', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    dispatch_contract.require(__debug__, 'Python assertions must remain enabled')
    if args.self_test:
        stage = framework()
        _, shapes = adapt_verify(stage)
        print(json.dumps(dict(dispatch=dispatch_contract.selftest(),
                              prefix=package_contract.prefix_selftest(),
                              locals=semantic_contract.selftest(), adapter_shapes=shapes)))
        return
    dispatch_contract.require(args.output is not None, '--output required')
    dispatch_contract.require(args.output.resolve().is_relative_to(VERIFY_OUTPUT.resolve())
                              and not args.output.exists(), 'Fresh output within assigned verify-review required')
    require_job()
    if args.semantic_only:
        result = semantic_only(args.semantic_only, args.output)
        print(json.dumps(dict(status=result['status'], full_abc_sha256=result['full_abc_sha256'],
                              relocated_helpers=result['semantics']['static_helper_count'],
                              old_classes=result['original_dispatch']['old_classes'])))
        return
    dispatch_contract.require(args.package_report is not None, '--package-report required')
    dispatch_contract.require(args.semantic_evidence is not None, '--semantic-evidence required for final native stage')
    dispatch_contract.require(args.virtuality_evidence is not None, '--virtuality-evidence required for final native stage')
    package = read(args.package_report)
    linked = read(package['link_report'])
    models = linked.get('signing_models', [])
    expected_models = {(mode, size) for mode in ('signature', 'ldid')
                       for size in (0x80000, 0x200000, 0x400000)}
    model_source = fc.tool('repairs/scripts/signing_models.py')
    dispatch_contract.require(len(models) == 6
        and {(x['mode'], x['signature_size']) for x in models} == expected_models
        and all(x['loader_metadata_preserved'] and x['all_loader_range_bytes_compared']
                and x['rebase_entries_equal']
                and x['adapter_sha256'] == package_contract.file_sha(model_source) for x in models),
        'Matching six signing/ldid models are required for this finalized native')
    contract = contract_for(linked['source_prepare_report'])
    contract.update(semantic_evidence=str(args.semantic_evidence.resolve()),
                    semantic_evidence_sha256=package_contract.file_sha(args.semantic_evidence))
    virtuality = read(args.virtuality_evidence)
    dispatch_contract.require(virtuality['status'] == 'independent_helper_virtual_dispatch_equivalence_passed'
        and virtuality['input_full_abc_sha256'] == read(linked['source_prepare_report'])['base_full_abc_sha256']
        and virtuality['final_full_abc_sha256'] == linked['full_abc_sha256']
        and virtuality['relocation_sha256'] == contract['relocation_sha256']
        and virtuality['verifier_sha256'] == package_contract.file_sha(Path(__file__).with_name('virtual_dispatch.py'))
        and virtuality['dispatch_model_sha256'] == package_contract.file_sha(dispatch_contract.__file__)
        and virtuality['helper_dispatch_overrides'] == 0 and virtuality['helper_count'] == 25,
        'Helper virtual-dispatch receipt differs from this final ABC/algorithm')
    stage = framework()
    stage.abc_checks = lambda old, new, previous, linked, prepared, meta: abc_contract.check(
        old, new, previous, linked, prepared, meta, contract)
    stage.package_readback = lambda package, linked, previous_package: package_contract.readback(
        package, linked, previous_package, BASELINE_RECEIPT, stage.Image)
    verifier, shapes = adapt_verify(stage)
    options = SimpleNamespace(package_report=args.package_report,
        equipment_link=Path(str(fc.private('outputs_ios_r11_port_20261025_equipment_link_report_json'))),
        libraries=LIBRARIES, output=args.output,
        detail_output=args.output.with_name(args.output.stem + '-details.json'))
    # The framework emits its result once. Append task-specific evidence in a
    # separate report so no earlier receipt is silently overwritten.
    result = verifier(options)
    summary = dict(result, independent_dispatch_contract=contract,
                   helper_virtual_dispatch_proof=virtuality,
                   native_wrapper_proof=PROOFS['native_wrappers'],
                   actual_unwind_page_storage=PROOFS['unwind_page_bounds'],
                   bounded_native_prefix=PROOFS['native_prefix'], adapter_shapes=shapes,
                   source_sha256=source_identity(), keys_logged=False,
                   current_admission_pair_and_endpoint_bytes_preserved=True,
                   signing_models='reuse finalizer six-model evidence bound to this exact native; actual loader/ldid boundaries rechecked',
                   warning='Offline ABC/AOT/package checks do not establish signed launch or device crash resolution')
    dump(args.output.with_name(args.output.stem + '-dispatch-summary.json'), summary)
    print(json.dumps(dict(status=result['status'], ipa_sha256=result['ipa_sha256'],
                          compiled_functions=result['compiled_functions'],
                          relocations_checked=result['relocations_checked'], device_tested=False)))


if __name__ == '__main__':
    main()
