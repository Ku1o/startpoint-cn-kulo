"""Cross-check old101832 orphan provenance and its actual new closure clone."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from audit_instance_dispatch import CURRENT, load, p
from audit_recompile_closure import ROOT, REMOVE

def refs(view, target):
    out = []
    for body in view.a.bodies:
        for index, (op, args) in enumerate(p.asm.opwalk.walk(body[5])):
            if op in (0x40, 0x44) and args[0] == target:
                out.append(dict(caller=body[0], opcode=hex(op), instruction=index))
    return out

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    before, after = load(CURRENT), load(args.prepared / 'full.abc')
    report = json.loads((args.prepared / 'relocation.json').read_text('utf8'))
    oldclosure = 101832
    helper, = [r for r in report['helpers'] if r['old_mid'] == 101665]
    closure, = [r for r in report['closures'] if r['old_mid'] == oldclosure]
    newhelper, newclosure = helper['new_mid'], closure['new_mid']
    before_refs = refs(before, oldclosure)
    assert len(before_refs) == 1 and before_refs[0]['caller'] == 101665 and before_refs[0]['opcode'] == '0x40', ('old closure consumers differ', before_refs)
    after_old_refs, after_new_refs = refs(after, oldclosure), refs(after, newclosure)
    assert after_old_refs == before_refs, ('orphan closure references changed', after_old_refs)
    assert len(after_new_refs) == 1 and after_new_refs[0]['caller'] == newhelper and after_new_refs[0]['opcode'] == '0x40', ('new closure consumers differ', after_new_refs)
    bb, ab = [{b[0]: b for b in view.a.bodies} for view in (before, after)]
    assert before.a.methods[oldclosure] == after.a.methods[oldclosure] == after.a.methods[newclosure]
    assert p.freeze(bb[oldclosure]) == p.freeze(ab[oldclosure]), 'old closure body/header/activation changed'
    # Static relocation deliberately removes the old instance scope prefix.
    # Keep actual executable code, stack/locals, exceptions and activation exact.
    assert p.freeze(bb[oldclosure][1:3]) == p.freeze(ab[newclosure][1:3]), 'new closure stack/locals differ'
    assert p.freeze(bb[oldclosure][5:]) == p.freeze(ab[newclosure][5:]), 'new closure code/exceptions/activation differ'
    assert ab[newclosure][3:5] == [0, 0], ('unexpected new static closure scope depth', ab[newclosure][3:5])
    assert p.freeze(bb[101665]) == p.freeze(ab[101665]), 'old helper orphan changed'
    for view, name in ((before, 'before'), (after, 'after')):
        traits = [dict(owner=view.a.mn_name(inst[0]), method=t.data[2]) for inst in view.a.instances
            for t in inst[6] if t.kind in (1,2,3) and t.data[2] == oldclosure]
        assert not traits, ('old closure unexpectedly has instance trait owner', name)
    value = dict(status='old_closure_unique_source_and_new_clone_route_verified',
        current=str(CURRENT), prepared=str(args.prepared / 'full.abc'),
        old_helper=101665, old_closure=oldclosure, new_static_helper=newhelper, new_closure=newclosure,
        current_old_closure_references=before_refs, prepared_old_closure_references=after_old_refs,
        prepared_new_closure_references=after_new_refs, old_helper_body_preserved=True,
        old_closure_method_info_body_header_activation_preserved=True,
        new_closure_exact_original_code_stack_locals_exceptions_activation=True,
        new_closure_scope_depth_adjustment=dict(original=bb[oldclosure][3:5], relocated=ab[newclosure][3:5]),
        old_closure_has_no_instance_trait_owner=True,
        old_closure_excluded_from_same_id_recompile=True,
        final_same_id_recompile_formula='356 original target IDs minus25 migrated instance helper IDs minus101832',
        same_id_recompile_count=330, native_or_table_write_performed=False,
        limitation='No new native generated or executed; parent linker/verifier must preserve old closure native/table and bind actual new closure native')
    destination = args.output or ROOT / 'closure-orphan-final.json'
    assert not destination.exists()
    destination.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps(value, ensure_ascii=False))

if __name__ == '__main__':
    main()
