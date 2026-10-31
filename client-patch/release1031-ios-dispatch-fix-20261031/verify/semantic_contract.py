"""Independent instruction/CFG comparison for instance-to-static relocation.

The expected stream is reconstructed from original bytecode. Production
transformation functions and their claimed inverse checks are never called.
"""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()

import dispatch_contract as dispatch


def local_token(op, args, shift):
    args = list(args)
    if 0xD0 <= op <= 0xD3:
        return 0x62, [op - 0xD0 + shift]
    if 0xD4 <= op <= 0xD7:
        return 0x63, [op - 0xD4 + shift]
    if op in (0x08, 0x62, 0x63, 0x92, 0x94, 0xC2, 0xC3):
        args[0] += shift
    elif op == 0x32:
        args = [x + shift for x in args]
    elif op == 0xEF and args[0] == 1:
        args[2] += shift
    return op, args


def expected_stream(before, replacements, helper_owner, shift, closure_map, owner_scope=False):
    p = dispatch.framework()
    original = p.asm.decode(before[5])
    temp = before[2] + shift
    expected = [(0x62, [0], None, None, None), (0x30, [], None, None, None)] if owner_scope else []
    mapping, expanded = {}, []
    for ordinal, row in enumerate(original):
        mapping[ordinal] = len(expected)
        op, args = local_token(row.op, row.args, shift)
        if owner_scope and op == 0x65:
            args[0] += 1
        if op in (0x40, 0x44) and args[0] in closure_map:
            args[0] = closure_map[args[0]]
        if op in p.MULTINAME_OPS and args[0] in replacements:
            dispatch.require(op in (0x46, 0x4F), 'Unsupported live helper reference opcode')
            record, argc = replacements[args[0]], args[1]
            # Use generic local tokens independently of compact wire encodings.
            block = [(0x63, [temp + n]) for n in range(argc, -1, -1)]
            block += [(0x62, [temp]), (0x77, []), (0x63, [temp]),
                      (0x60, [helper_owner])]
            block += [(0x62, [temp + n]) for n in range(argc + 1)]
            block += [(op, [record['new_qname'], argc + 1])]
            expected += [(code, operands, None, None, None) for code, operands in block]
            expanded.append(dict(original_instruction=ordinal, old_method=record['old_mid'],
                                 new_method=record['new_mid'], arguments=argc,
                                 spill_base=temp, expected_instructions=len(block)))
        else:
            expected.append((op, args, row.target, row.default, row.cases))
    mapping[len(original)] = len(expected)
    remapped = []
    for op, args, target, default, cases in expected:
        remapped.append((op, args, mapping[target] if target is not None else None,
                         mapping[default] if default is not None else None,
                         [mapping[x] for x in cases] if cases is not None else None))
    _, offsets = p.asm.encode(original)
    offsets.append(len(before[5]))
    old_index = {at: n for n, at in enumerate(offsets)}
    exceptions = [(mapping[old_index[a]], mapping[old_index[b]], mapping[old_index[c]], d, e)
                  for a, b, c, d, e in before[6]]
    return remapped, exceptions, expanded


def actual_stream(body):
    p = dispatch.framework()
    rows = p.asm.decode(body[5])
    encoded, offsets = p.asm.encode(rows)
    dispatch.require(encoded == body[5], 'Noncanonical final method encoding')
    offsets.append(len(encoded))
    index = {at: n for n, at in enumerate(offsets)}
    tokens = []
    for row in rows:
        op, args = local_token(row.op, row.args, 0)
        tokens.append((op, args, row.target, row.default, row.cases))
    exceptions = [(index[a], index[b], index[c], d, e) for a, b, c, d, e in body[6]]
    return tokens, exceptions


def one_body(before, after, replacements, helper_owner, shift=0, closure_map=None,
             rebase_scope=False, owner_scope=False):
    expected, exceptions, calls = expected_stream(before, replacements, helper_owner, shift, closure_map or {}, owner_scope)
    actual, actual_exceptions = actual_stream(after)
    dispatch.require(expected == actual,
                     'Independent relocated instruction/CFG mismatch: ' + str(after[0]))
    dispatch.require(exceptions == actual_exceptions,
                     'Independent relocated exception boundary mismatch: ' + str(after[0]))
    expected_scope = [0, before[4] - before[3] + int(owner_scope)] if rebase_scope else list(before[3:5])
    dispatch.require(list(after[3:5]) == expected_scope,
                     'Relocated initial/max scope depth differs from compiler-owner contract')
    p = dispatch.framework()
    dispatch.require(p.freeze(before[7]) == p.freeze(after[7]),
                     'Relocated activation traits changed without separate proof')
    max_args = max((x['arguments'] for x in calls), default=-1)
    dispatch.require(after[2] == before[2] + shift + max_args + 1,
                     'Relocated local count differs from explicit receiver/spill contract')
    dispatch.require(after[1] == max(before[1], int(owner_scope)) + bool(calls), 'Relocated max stack differs')
    return dict(original_method=before[0], final_method=after[0],
                instruction_count=len(actual), local_shift=shift, added_static_owner_scope=owner_scope,
                reconstructed_calls=calls, exception_regions=len(exceptions),
                instruction_cfg_exception_inverse_exact=True)


def lexical_scope_proof(before_abc, helpers, closure_rows):
    """Pin the actual receiver/local-activation scope used by the one closure."""
    p = dispatch.framework()
    bodies = {b[0]: b for b in before_abc.bodies}
    selected = {int(x['old_mid']) for x in helpers} | {int(x['old_mid']) for x in closure_rows}
    require = dispatch.require
    require({int(x['old_mid']) for x in closure_rows} == {101832}, 'Unexpected closure graph')
    relevant = bodies[101665]
    rows = p.asm.decode(relevant[5])
    require(len(relevant[7]) == 18 and before_abc.methods[101665][3] & 2,
            'Original local activation is not the reviewed 18-slot frame')
    require([x.op for x in rows[:2]] == [0xD0, 0x30]
            and [x.op for x in rows[9:13]] == [0x57, 0x2A, 0x63, 0x30],
            'Original receiver/activation pushscope order changed')
    reads = [x.args[0] for x in rows if x.op == 0x65]
    require(reads and set(reads) == {1}, 'Captured frame is not local scope index 1')
    require({x.args[0] for x in rows if x.op == 0x40} == {101832}, 'Original closure edge changed')
    activation = {before_abc.mn_name(t.name).split('::')[-1]: t for t in relevant[7]}
    for name, slot in (('paths', 15), ('characterOwner', 16), ('featuresPermit', 17), ('_gthis', 18)):
        require(name in activation and activation[name].data[1] == slot,
                'Captured activation slot identity changed: ' + name)
    for mid in selected:
        require(not any(op == 0x67 for op, _ in p.asm.opwalk.walk(bodies[mid][5])),
                'Moved body reads owner-specific outer lexical scope: ' + str(mid))
        local_scopes = [args[0] for op, args in p.asm.opwalk.walk(bodies[mid][5]) if op == 0x65]
        require(not local_scopes or mid == 101665 and set(local_scopes) == {1},
                'Unreviewed local scope read in moved body')
    return dict(method=101665, closure=101832, activation_slots=18,
                receiver_local_scope=0, activation_local_scope=1,
                final_helper_owner_scope=0, final_receiver_scope=1, final_activation_scope=2,
                outer_scope_reads=0, captured_slots=[15, 16, 17, 18],
                scope='actual bytecode frame/slot identity; compiler owner-scope header checked separately')


def check(before_abc, after_abc, relocation):
    """Expected relocation receipt uses helpers plus optional copied_closures.

    Complex lexical or activation changes intentionally fail until a separate
    reviewed adapter reconstructs their exact intended differences.
    """
    p = dispatch.framework()
    helpers = relocation['helpers']
    replacements = {int(r['old_qname']): r for r in helpers}
    dispatch.require(len(replacements) == len(helpers), 'Duplicate helper QName relocation')
    owner_name = relocation.get('helper_owner') or relocation['helper_class']
    owners = [i[0] for i in after_abc.instances if after_abc.mn_name(i[0]) == owner_name]
    dispatch.require(len(owners) == 1, 'Helper class missing or ambiguous')
    helper_owner = owners[0]
    helper_index, = [n for n, i in enumerate(after_abc.instances) if i[0] == helper_owner]
    helper_instance = after_abc.instances[helper_index]
    helper_class = after_abc.classes[helper_index]
    dispatch.require(after_abc.mn_name(helper_instance[1]) == 'Object'
                     and not helper_instance[6], 'Helper class adds instance bindings')
    dispatch.require(len(helper_class[1]) == 25
                     and all(t.kind == 1 for t in helper_class[1]), 'Helper class adds unrelated static bindings')
    new_static_names = {dispatch.multiname_local(after_abc, t.name) for t in helper_class[1]}
    dispatch.require(new_static_names == {f"m{r['old_mid']}_{r['name']}" for r in helpers},
                     'New owner scope contains unexpected static names')
    old = {b[0]: b for b in before_abc.bodies}
    new = {b[0]: b for b in after_abc.bodies}
    closure_rows = relocation.get('copied_closures', relocation.get('closures', []))
    closure_map = {int(r['old_mid']): int(r['new_mid']) for r in closure_rows}
    scope_proof = lexical_scope_proof(before_abc, helpers, closure_rows)
    proofs = []
    for record in helpers:
        left, right = int(record['old_mid']), int(record['new_mid'])
        require = dispatch.require
        before_info, after_info = before_abc.methods[left], after_abc.methods[right]
        require(after_info[0] == before_info[0]
                and after_info[1] == [record['owner_multiname'], *before_info[1]]
                and after_info[2:5] == before_info[2:5], 'Static helper signature/flags changed')
        expected_names = [0, *before_info[5]] if before_info[5] is not None else None
        require(after_info[5] == expected_names, 'Static helper parameter-name mapping changed')
        proofs.append(one_body(old[left], new[right], replacements, helper_owner, 1, closure_map, True, True))
    for row in closure_rows:
        left, right = int(row['old_mid']), int(row['new_mid'])
        dispatch.require(p.freeze(before_abc.methods[left]) == p.freeze(after_abc.methods[right]),
                         'Copied closure MethodInfo changed')
        proofs.append(one_body(old[left], new[right], replacements, helper_owner,
                               int(row.get('local_shift', 0)), closure_map, True))
    removed = {int(r['old_mid']) for r in helpers}
    helper_names = {dispatch.multiname_local(before_abc, x) for x in replacements}
    changed_callers = []
    for mid, body in old.items():
        if mid in removed or mid in closure_map:
            continue  # Orphaned originals are frozen by abc_contract.
        direct = any(op in p.MULTINAME_OPS and args[0] in replacements
                     for op, args in p.asm.opwalk.walk(body[5]))
        if direct:
            proofs.append(one_body(body, new[mid], replacements, helper_owner, 0, closure_map))
            changed_callers.append(mid)
    # No active body may retain a direct/newfunction call or property access to
    # a removed instance helper. Original unreachable orphan bodies are exempt.
    stale = []
    inactive = removed | set(closure_map)
    for mid, body in new.items():
        if mid in inactive:
            continue
        for ordinal, (op, args) in enumerate(p.asm.opwalk.walk(body[5])):
            if op in (0x40, 0x44) and args[0] in inactive:
                stale.append((mid, ordinal, 'direct_old_helper_or_closure'))
            elif op in p.MULTINAME_OPS and dispatch.multiname_local(after_abc, args[0]) in helper_names:
                stale.append((mid, ordinal, 'removed_instance_helper_name'))
    dispatch.require(not stale, 'Stale live helper reference: ' + repr(stale[:8]))
    # The extra owner frame is below the preserved receiver and activation.
    # It has no name matching any old lexical lookup, so it cannot capture one.
    for record in helpers:
        for op, args in p.asm.opwalk.walk(old[int(record['old_mid'])][5]):
            if op in (0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x60):
                dispatch.require(dispatch.multiname_local(before_abc, args[0]) not in new_static_names,
                                 'Added helper-class scope shadows an original lexical binding')
    return dict(static_helper_count=len(helpers), copied_closures=len(closure_rows),
                changed_original_callers=changed_callers, bodies=proofs,
                lexical_scope=scope_proof,
                added_owner_scope_has_no_original_lexical_name_collisions=True,
                no_live_removed_helper_references=True,
                scope='instruction, signature, locals, CFG, exceptions, activation; native GC/device behavior unexecuted')


def selftest():
    # Every local family gets an independent expected-number control.
    for op, args, wanted_op, wanted_args in (
        (0xD0, [], 0x62, [1]), (0xD3, [], 0x62, [4]),
        (0xD4, [], 0x63, [1]), (0xD7, [], 0x63, [4]),
        (0x08, [2], 0x08, [3]), (0x92, [3], 0x92, [4]),
        (0x94, [0], 0x94, [1]), (0xC2, [5], 0xC2, [6]),
        (0xC3, [6], 0xC3, [7]), (0x32, [0, 3], 0x32, [1, 4]),
        (0xEF, [1, 0, 2, 0], 0xEF, [1, 0, 3, 0])):
        dispatch.require(local_token(op, args, 1) == (wanted_op, wanted_args),
                         'Independent local family self-test failed')
    p = dispatch.framework()
    code = lambda rows: p.asm.encode(p.asm.assemble(rows))[0]
    before = [1, 1, 1, 7, 8, code([('getlocal_0',), ('pushscope',),
                                    ('pushbyte', 1), ('returnvalue',)]), [], []]
    after = [2, 1, 2, 0, 2, code([('getlocal_0',), ('pushscope',),
                                   ('getlocal_1',), ('pushscope',),
                                   ('pushbyte', 1), ('returnvalue',)]), [], []]
    one_body(before, after, {}, 99, 1, {}, True, True)
    bad = list(after)
    bad[5] = code([('getlocal_1',), ('pushscope',), ('pushbyte', 1), ('returnvalue',)])
    try:
        one_body(before, bad, {}, 99, 1, {}, True, True)
    except ValueError:
        pass
    else:
        raise ValueError('Missing static-owner scope escaped independent bytecode check')
    return dict(passed=13, scope='explicit local-number plus static-owner scope positive/negative controls')
