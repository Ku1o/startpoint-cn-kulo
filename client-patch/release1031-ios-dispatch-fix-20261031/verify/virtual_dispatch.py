"""Prove migrated instance helpers have no descendant override.

Uses the existing ABC declaration parser, stopping before script/method bodies.
Only the four reviewed inheritance subtrees are materialized as dispatch maps.
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
import inspect
from pathlib import Path
import textwrap

import dispatch_contract as d
import package_contract
import verify_final as v


def declarations_only(raw):
    p = d.framework()
    source = ast.parse(textwrap.dedent(inspect.getsource(p.abcfmt.ABC.__init__)))
    function = source.body[0]
    cut = None
    for index, statement in enumerate(function.body):
        if isinstance(statement, ast.Assign) and any(
                isinstance(target, ast.Attribute) and target.attr == 'scripts'
                for target in statement.targets):
            cut = index
            break
    d.require(cut is not None and cut > 8, 'ABC declaration parser source shape changed')
    function.body = function.body[:cut]
    function.name = '_declarations_only'
    namespace = dict(p.abcfmt.__dict__)
    exec(compile(ast.fix_missing_locations(source), str(Path(p.abcfmt.__file__)), 'exec'), namespace)
    parsed = p.abcfmt.ABC.__new__(p.abcfmt.ABC)
    namespace['_declarations_only'](parsed, raw)
    d.require(hasattr(parsed, 'instances') and hasattr(parsed, 'classes')
              and not hasattr(parsed, 'bodies'), 'Declaration-only parser read method bodies')
    return parsed


def check(abc, helpers):
    model = d.Dispatch(abc)
    children = {}
    for name, instance in model.classes.items():
        children.setdefault(abc.mn_name(instance[1]), []).append(name)
    subtrees = {}
    proof = []
    for helper in helpers:
        owner, mid = helper['owner'], int(helper['old_mid'])
        if owner not in subtrees:
            pending, descendants = [owner], []
            while pending:
                name = pending.pop()
                d.require(name not in descendants, 'Inheritance cycle/duplicate descendant')
                descendants.append(name)
                pending.extend(children.get(name, []))
            subtrees[owner] = sorted(descendants)
        key = d.binding(abc, int(helper['old_qname']))
        rows = []
        for name in subtrees[owner]:
            _, slots, bindings = model.model(name)
            d.require(key in bindings, 'Helper binding disappeared in descendant: ' + name)
            at, kind = bindings[key]
            d.require(kind == 1 and slots[at] and slots[at].method == mid,
                      'Static relocation would bypass descendant helper override: ' + name + '/' + str(mid))
            rows.append(dict(receiver=name, application_relative_slot=at, effective_method=mid))
        proof.append(dict(method=mid, declaring_owner=owner, receivers=rows,
                          all_descendant_effective_methods_equal_original_helper=True))
    return dict(helper_count=len(proof), descendant_binding_checks=sum(len(r['receivers']) for r in proof),
                unique_receiver_classes=len(set(x for rows in subtrees.values() for x in rows)),
                helper_dispatch_overrides=0, helpers=proof)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-port', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    v.require_job()
    contract = v.contract_for(args.prepared_port)
    prepared = v.read(args.prepared_port)
    raw = v.CURRENT_FULL.read_bytes()
    d.require(package_contract.sha(raw) == prepared['base_full_abc_sha256'], 'Input full ABC identity changed')
    abc = declarations_only(raw)
    result = dict(status='independent_helper_virtual_dispatch_equivalence_passed',
        input_full_abc_sha256=prepared['base_full_abc_sha256'],
        final_full_abc_sha256=prepared['full_abc_sha256'],
        relocation_sha256=contract['relocation_sha256'],
        verifier_sha256=package_contract.file_sha(__file__),
        dispatch_model_sha256=package_contract.file_sha(d.__file__),
        parser_mode='existing parser truncated before scripts and all method bodies',
        **check(abc, contract['relocation']['helpers']))
    v.dump(args.output, result)
    print(__import__('json').dumps({k: result[k] for k in
          ('status', 'helper_count', 'descendant_binding_checks', 'unique_receiver_classes', 'helper_dispatch_overrides')}))


if __name__ == '__main__':
    main()
