"""Independent final full/runtime/compiled ABC preservation contract."""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()

import hashlib
from pathlib import Path
import struct

import dispatch_contract as dispatch

REMOVED = {
    'pinball.common.data.battle.squadMember::CharacterBaseImpl': {101732},
    'pinball.common.data.character::GeneralCharacterLogic': {101820, 101821},
    'pinball.common.data.character::BattleCharacterLogic': {
        101665, 101666, 101667, 101668, 101669, 101670, 101685,
        101686, 101687, 101688, 101689, 101690, 101691, 101692,
        101697, 101698, 101702, 101725, 101729, 101730, 101812},
    'pinball.scene.battle.battle.enemy::EnemyImpl': {101711},
}
REMOVED_IDS = set().union(*REMOVED.values())
ORPHAN_IDS = REMOVED_IDS | {101832}
INFO = 104549248


def require(ok, message):
    dispatch.require(ok, message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def u64(raw, offset):
    return struct.unpack_from('<Q', raw, offset)[0]


def old_class_declarations(old_abc, after_abc, deleted_helpers):
    """Permit precisely the reviewed removals; freeze every other old trait."""
    p = dispatch.framework()
    actual = {}
    for owner, methods in deleted_helpers.items():
        require(owner in {old_abc.mn_name(i[0]) for i in old_abc.instances},
                'Unknown removed-helper owner: ' + owner)
        actual[owner] = set(map(int, methods))
    require(set().union(*actual.values()) == REMOVED_IDS,
            'Removed instance-helper method set differs from reviewed 25')
    require(actual == REMOVED, 'Removed instance-helper ownership differs')
    count = 0
    for index, before in enumerate(old_abc.instances):
        after = after_abc.instances[index]
        owner = old_abc.mn_name(before[0])
        require(p.freeze(before[:-1]) == p.freeze(after[:-1]),
                'Old instance header/storage metadata changed: ' + owner)
        removed = actual.get(owner, set())
        hits = [t for t in before[6] if t.kind in (1, 2, 3) and t.data[2] in removed]
        require({t.data[2] for t in hits} == removed and len(hits) == len(removed),
                'Removed helper is missing or duplicated: ' + owner)
        require(all(t.kind == 1 and t.attr == 0 for t in hits),
                'Only reviewed ordinary instance methods may move: ' + owner)
        expected = [t for t in before[6] if t not in hits]
        require(p.freeze(expected) == p.freeze(after[6]),
                'Non-target old instance trait/storage changed: ' + owner)
        require(p.freeze(old_abc.classes[index]) == p.freeze(after_abc.classes[index]),
                'Old class-side declaration changed: ' + owner)
        count += len(hits)
    return dict(old_classes=len(old_abc.instances), removed_instance_traits=count,
                all_old_instance_fields_exact=True, all_old_class_side_traits_exact=True,
                all_other_old_instance_traits_exact=True)


def check(old, new, previous, linked, prepared, meta, contract):
    """Drop-in replacement for verify_stages.abc_checks with narrower changes."""
    p = dispatch.framework()
    full = Path(linked['full_abc_file']).read_bytes()
    old_full = Path(previous['full_abc_file']).read_bytes()
    require(sha(full) == linked['full_abc_sha256'] == prepared['full_abc_sha256'],
            'Final full ABC identity mismatch')
    require(sha(old_full) == previous['full_abc_sha256'], 'Current input full ABC identity mismatch')
    require(prepared.get('base_full_abc_sha256', prepared.get('input_full_abc_sha256')) == sha(old_full),
            'Preparation did not use current public full ABC')
    digest = hashlib.sha1(full).digest()
    require(new.raw[INFO:INFO + 20] == digest and digest.hex() == linked['full_abc_sha1'],
            'AOTInfo full ABC digest mismatch')
    count, old_count = u64(new.raw, INFO + 56), u64(old.raw, INFO + 56)
    require(count == linked['total_methods'] == prepared['total_methods']
            and old_count == prepared['old_methods'], 'Final AOT MethodInfo count mismatch')
    runtime = new.read(u64(new.raw, INFO + 24), u64(new.raw, INFO + 32))
    old_runtime = old.read(u64(old.raw, INFO + 24), u64(old.raw, INFO + 32))
    require(sha(runtime) == linked['runtime_abc_sha256']
            and runtime == Path(linked['runtime_abc_file']).read_bytes(),
            'Actual native runtime ABC differs from linked/runtime file')
    a, b, c, d = map(p.abcfmt.ABC, (old_full, full, old_runtime, runtime))
    require(len(a.methods) == old_count and len(b.methods) == count, 'Full ABC MethodInfo count mismatch')
    for field in ('methods', 'metadata', 'scripts', 'ints', 'uints', 'doubles',
                  'strings', 'namespaces', 'ns_sets', 'multinames'):
        before, after = getattr(a, field), getattr(b, field)
        require(p.freeze(before) == p.freeze(after[:len(before)]), 'Old full ABC pool/info prefix changed: ' + field)
        require(p.freeze(after) == p.freeze(getattr(d, field)), 'Final full/runtime declaration mismatch: ' + field)
    for field in ('instances', 'classes'):
        require(p.freeze(getattr(b, field)) == p.freeze(getattr(d, field)),
                'Final full/runtime class layout mismatch')
        require(len(getattr(b, field)) >= len(getattr(a, field)), 'Old classes removed')
    declarations = old_class_declarations(a, b, contract['removed_instance_helpers'])
    require(len(b.instances) == len(a.instances) + 1 and len(b.classes) == len(a.classes) + 1,
            'Only one independent helper class may be appended')
    require(count - old_count == 29, 'Expected 25 static helpers, one copied closure, three lifecycle methods')
    targets = {int(r['method_id']): r for r in prepared['methods'] if r.get('strategy', 'replace') == 'replace'}
    old_targets = set(targets) & set(range(old_count))
    require(not ORPHAN_IDS & targets.keys(), 'Orphan helper/closure MethodInfo/body must remain preserved')
    old_bodies, new_bodies = ({x[0]: x for x in abc.bodies} for abc in (a, b))
    require(old_bodies.keys() <= new_bodies.keys(), 'Old method body removed')
    changed = []
    for mid, before in old_bodies.items():
        after = new_bodies[mid]
        if p.freeze(before) != p.freeze(after):
            changed.append(mid)
            require(mid in targets, 'Unlisted changed old full ABC body: ' + str(mid))
        require(p.freeze(before[7]) == p.freeze(after[7]), 'Old activation traits changed: ' + str(mid))
        if mid in targets:
            row = targets[mid]
            require(row['body_changed'] == (p.freeze(before) != p.freeze(after)),
                    'Target body-change declaration mismatch: ' + str(mid))
            if 'before_code_sha256' in row or 'after_code_sha256' in row:
                require(sha(before[5]) == row['before_code_sha256']
                        and sha(after[5]) == row['after_code_sha256'], 'Target body hash mismatch: ' + str(mid))
    require(set(changed) == set(map(int, contract['changed_body_ids'])), 'Changed full ABC body allowlist mismatch')
    for mid in ORPHAN_IDS:
        require(p.freeze(old_bodies[mid]) == p.freeze(new_bodies[mid]), 'Old orphan helper body changed')
    meta_info = meta.extract(next(n for n in meta.defined if n.endswith('_284_aotInfo')), 168)
    compiled_raw = meta.extract(next(n for n in meta.defined if n.endswith('_abcBytes')), u64(meta_info, 32))
    compiled_abc = p.abcfmt.ABC(compiled_raw)
    compiled_bodies = {x[0]: x for x in compiled_abc.bodies}
    old_runtime_bodies = {x[0]: x for x in c.bodies}
    require({x[0] for x in d.bodies} == compiled_bodies.keys()
            and len({x[0] for x in d.bodies}) == len(d.bodies), 'Runtime method-body set differs from compiler')
    for body in d.bodies:
        mid = body[0]
        expected = compiled_bodies[mid] if mid in targets or mid >= old_count else old_runtime_bodies[mid]
        require(p.freeze(body) == p.freeze(expected), 'Runtime body differs from compiler/preserved body: ' + str(mid))
    flags = new.read(u64(new.raw, INFO + 64), count * 4)
    compiler_flags = meta.extract(next(n for n in meta.defined if n.endswith('_methodFlagsArr')), count * 4)
    require(flags == compiler_flags
            and flags[:old_count * 4] == old.read(u64(old.raw, INFO + 64), old_count * 4),
            'Compiler/final flags or old flags prefix mismatch')
    require(u64(new.raw, INFO + 48) == u64(old.raw, INFO + 48)
            and u64(new.raw, INFO + 88) == u64(old.raw, INFO + 88), 'AOT pointer/activation table moved')
    mutable = set(range(20)) | set(range(24, 40)) | set(range(56, 72))
    require(all(new.raw[INFO + n] == old.raw[INFO + n] for n in range(168) if n not in mutable),
            'Unrelated AOTInfo fields changed')
    evidence_path = Path(contract['semantic_evidence'])
    require(sha(evidence_path.read_bytes()) == contract['semantic_evidence_sha256'], 'Semantic receipt identity mismatch')
    evidence = __import__('json').loads(evidence_path.read_text('utf-8-sig'))
    require(evidence['status'] == 'independent_prepared_semantics_and_original_dispatch_checked'
            and evidence['full_abc_sha256'] == sha(full)
            and evidence['base_full_abc_sha256'] == sha(old_full)
            and evidence['relocation_sha256'] == contract['relocation_sha256'],
            'Semantic receipt does not cover this actual final ABC/input/relocation')
    for filename in ('abc_contract.py', 'dispatch_contract.py', 'semantic_contract.py'):
        require(sha(Path(__file__).with_name(filename).read_bytes()) == evidence['source_sha256'][filename],
                'Semantic algorithm changed after its bounded verification: ' + filename)
    slots = evidence['original_dispatch']
    focus = dispatch.focus_getter(b)
    require(dispatch.focus_getter(d) == focus, 'Actual runtime focused getter dispatch differs from full ABC')
    prior_reports = [__import__('json').loads(Path(f).read_text('utf-8-sig'))
                     for f in contract['prior_aot_link_reports']]
    prior_native = {int(r['method']) for report in prior_reports for r in report['functions'] if int(r['method']) >= 0}
    require(len(prior_native) == 356, 'Expected fixed current 334+22 prior native method union')
    require(old_targets == prior_native - ORPHAN_IDS and len(old_targets) == 330,
            'Every retained current AOT method must be recompiled: fixed 356 minus 26 orphan methods')
    closure = evidence['recompile_closure']
    semantics = evidence['semantics']
    for mid in set(old_targets) | {int(r['new_mid']) for r in contract['relocation']['helpers']} \
            | {int(r['new_mid']) for r in contract['relocation']['closures']}:
        p.check_body(new_bodies[mid], b)
    return dict(old_methods=old_count, total_methods=count, targets=sorted(targets),
                changed_existing_bodies=sorted(changed), new_method_ids=list(range(old_count, count)),
                full_abc_sha256=sha(full), runtime_abc_sha256=sha(runtime),
                declaration_pool_prefix_preserved=True, unrelated_runtime_bodies_preserved=True,
                flags_prefix_exact=True, old_declarations=declarations, original_dispatch=slots,
                focused_getter=focus, recompile_closure=closure, relocated_semantics=semantics)
