"""Bounded, read-only current-vs-R11 instance dispatch audit.

No compiler or linker is invoked. Only this script's selected JSON/report is written.
"""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from collections import defaultdict, deque
import argparse
import json
from pathlib import Path
import sys
import types

sys.dont_write_bytecode = True
SOURCE = Path(str(fc.REPO / 'client-patch'))
sys.path[:0] = [str(SOURCE / 'lens0907-0908'), str(fc.private('libraries'))]
import build_swf as p

OLD = Path(str(fc.private('outputs_ios_r11_cumulative_compact_20261025_ios_full_equipment_r11_compact_20261025_abc')))
CURRENT = Path(str(fc.client() / 'revision-public-admission-20261031/ios/build01/full.abc'))

def load(path):
    return p.View(types.SimpleNamespace(abc=p.abcfmt.ABC(path.read_bytes())), p.asm)

def name_key(view, trait, owner, family=False):
    mn = view.mn(trait.name)
    assert mn[0] in (7, 13), ('non-QName trait', owner, mn)
    namespace = mn[1]
    if family and namespace[0] in (24, 26):
        return ('protected', mn[-1])
    # A private namespace must never alias a same-named base/derived binding.
    if namespace[0] == 5:
        return ('private', owner, namespace, mn[-1])
    return mn

def methods(view, owner, inst):
    rows = []
    for tr in inst[6]:
        if tr.kind not in (1, 2, 3):
            continue
        mid = tr.data[2]
        info = view.a.methods[mid]
        rows.append(dict(name=view.a.mn_name(tr.name), kind=tr.kind,
            namespace=view.ns(view.a.multinames[tr.name][1]), method=mid,
            disp_id=tr.data[1], attributes=tr.attr,
            parameter_count=len(info[1]), parameters=[view.a.mn_name(x) for x in info[1]],
            returns=view.a.mn_name(info[0]),
            key=name_key(view, tr, owner)))
    return rows

def model(view, byname, owner):
    chain = []
    external = owner
    while external in byname:
        inst = byname[external]
        chain.append((external, inst))
        external = view.a.mn_name(inst[1])
    chain.reverse()
    slots, bindings, classes = [], {}, []
    for cname, inst in chain:
        start = len(slots)
        for tr in inst[6]:
            if tr.kind not in (1, 2, 3):
                continue
            assert tr.data[1] == 0, ('explicit disp_id requires separate model', cname)
            key = name_key(view, tr, cname, family=True)
            if key not in bindings:
                bindings[key] = (len(slots), tr.kind)
                slots.extend([None] * (1 if tr.kind == 1 else 2))
            at, initial_kind = bindings[key]
            assert (tr.kind == 1) == (initial_kind == 1), ('incompatible binding kinds', cname)
            if tr.kind == 3:
                at += 1
            slots[at] = dict(method=tr.data[2], owner=cname,
                name=view.a.mn_name(tr.name), kind=tr.kind,
                slot_relative_to_external=at,
                identity=(cname, name_key(view, tr, cname), tr.kind))
        classes.append(dict(owner=cname, start=start, end=len(slots)))
    return dict(external=external, classes=classes, slots=slots)

def descendants(root, children):
    out, pending = [], deque(children.get(root, []))
    while pending:
        name = pending.popleft()
        out.append(name)
        pending.extend(children.get(name, []))
    return out

def main():
    arg = argparse.ArgumentParser()
    arg.add_argument('--out', type=Path, required=True)
    args = arg.parse_args()
    assert not args.out.exists(), 'Use fresh audit output directory'
    old, cur = load(OLD), load(CURRENT)
    maps = [{v.a.mn_name(i[0]): i for i in v.a.instances} for v in (old, cur)]
    oldmap, curmap = maps
    children = defaultdict(list)
    for name, inst in curmap.items():
        children[cur.a.mn_name(inst[1])].append(name)
    additions, changed_prefixes = [], []
    for name in sorted(oldmap.keys() & curmap.keys()):
        before, after = methods(old, name, oldmap[name]), methods(cur, name, curmap[name])
        # Compare semantic trait prefix and method identities, never large objects.
        prefix_equal = len(after) >= len(before) and all(a == b for a, b in zip(before, after))
        if not prefix_equal:
            changed_prefixes.append(dict(owner=name, old_count=len(before), current_count=len(after)))
        before_keys = {(r['key'], r['kind']) for r in before}
        added = [r for r in after if (r['key'], r['kind']) not in before_keys]
        if not added:
            continue
        desc = descendants(name, children)
        additions.append(dict(owner=name, old_local_method_traits=len(before),
            current_local_method_traits=len(after), old_method_prefix_equal=prefix_equal,
            added=added, direct_subclasses=children.get(name, []),
            all_subclasses=desc, old_subclasses=[n for n in desc if n in oldmap]))
    affected = sorted({n for r in additions for n in [r['owner'], *r['old_subclasses']]})
    shifts = []
    for owner in affected:
        a, b = model(old, oldmap, owner), model(cur, curmap, owner)
        assert a['external'] == b['external'], ('external root changed', owner)
        am = {r['identity']: r for r in a['slots'] if r}
        bm = {r['identity']: r for r in b['slots'] if r}
        moved = []
        for identity, r in am.items():
            new = bm.get(identity)
            if new and new['slot_relative_to_external'] != r['slot_relative_to_external']:
                moved.append(dict(owner=r['owner'], method=r['method'], name=r['name'], kind=r['kind'],
                    old_slot=r['slot_relative_to_external'], current_slot=new['slot_relative_to_external'],
                    delta=new['slot_relative_to_external'] - r['slot_relative_to_external']))
        shifts.append(dict(owner=owner, external=a['external'],
            old_slots=len(a['slots']), current_slots=len(b['slots']),
            moved_old_methods=len(moved), moved=moved))
    # Bytecode consumers of added names. Retained AOT bodies are placeholders:
    # lack of a bytecode match is not evidence that native code has no callsite.
    target_names = {r['name'].split('::')[-1] for a in additions for r in a['added']}
    multinames = {}
    for i, mn in enumerate(cur.a.multinames):
        if mn[0] in (7, 13) and cur.a.strings[mn[2]].decode('utf8', 'replace') in target_names:
            multinames[i] = cur.a.mn_name(i)
        elif mn[0] in (9, 14) and cur.a.strings[mn[1]].decode('utf8', 'replace') in target_names:
            multinames[i] = cur.a.mn_name(i)
    calls = []
    for body in cur.a.bodies:
        mid = body[0]
        for offset, (op, operands) in enumerate(p.asm.opwalk.walk(body[5])):
            if op in p.MULTINAME_OPS and operands[0] in multinames:
                calls.append(dict(caller_method=mid, caller=cur.labels.get(mid, 'UNMAPPED'),
                    instruction_index=offset, opcode=hex(op), name=multinames[operands[0]],
                    operands=operands[1:]))
    result = dict(scope='Read-only structural instance-dispatch audit; no AOT or device execution',
        current=str(CURRENT), layout_reference=str(OLD),
        class_counts=dict(old=len(oldmap), current=len(curmap)),
        existing_classes_with_added_method_traits=len(additions),
        added_instance_method_traits=sum(len(r['added']) for r in additions),
        changed_old_method_prefixes=changed_prefixes, additions=additions,
        affected_old_class_models=shifts, bytecode_consumers=calls,
        model_rules=['method consumes one slot', 'getter/setter property reserves two slots',
            'override replaces inherited slot', 'protected namespace is an inheritance family',
            'private namespace is scoped to declaring owner', 'external SDK root omitted equally in both models'],
        limitations=['Full ABC retained AOT placeholders do not expose every native callsite',
            'Leaf appends do not shift existing slots but their own AOT signatures still require final verification',
            'No live iOS VTable read or device fix validation'])
    args.out.mkdir(parents=True)
    (args.out / 'instance-dispatch-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    summary = dict(existing_classes_with_additions=len(additions),
        added_method_traits=result['added_instance_method_traits'], changed_prefixes=len(changed_prefixes),
        old_classes_with_moved_slots=[dict(owner=r['owner'], moved=r['moved_old_methods']) for r in shifts if r['moved_old_methods']],
        additions=[dict(owner=r['owner'], added=len(r['added']), old_subclasses=len(r['old_subclasses'])) for r in additions],
        bytecode_consumer_count=len(calls), output=str(args.out / 'instance-dispatch-audit.json'))
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    main()
