"""Independent inherited-dispatch and recompile-closure checks.

No build entry point is imported or executed. Models use application-relative
slots so external/native ancestors do not need to be guessed. The focused
BattleCharacterLogic proof additionally binds the local SDK's Object ABI.
"""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import sys

sys.dont_write_bytecode = True
SOURCE = Path(str(fc.REPO))
SDK = Path(str(fc.private('sdk')))


def require(value, message):
    if not value:
        raise ValueError(message)


def framework():
    sys.path[:0] = [str(SOURCE / 'client-patch/lens0907-0908')]
    import build_swf
    return build_swf


def binding(abc, multiname):
    """Trait binding identity, including private namespace identity.

    Protected methods share their binding through a class's inheritance family;
    private namespaces with equal strings must still remain separate.
    """
    mn = abc.multinames[multiname]
    require(mn[0] in (7, 13), 'Non-QName instance method trait')
    ns_kind, name = abc.namespaces[mn[1]]
    local = abc.strings[mn[2]].decode('utf-8', 'strict')
    if ns_kind in (24, 26):
        return ('protected', local)
    ns = abc.strings[name].decode('utf-8', 'strict')
    return (mn[0], ns_kind, ns, mn[1] if ns_kind == 5 else None, local)


@dataclass(frozen=True)
class Slot:
    owner: str
    method: int
    kind: int
    key: tuple


class Dispatch:
    """AVM method/getter/setter allocation, excluding external ancestor slots."""
    def __init__(self, abc):
        self.abc = abc
        self.classes = {abc.mn_name(i[0]): i for i in abc.instances}
        require(len(self.classes) == len(abc.instances), 'Duplicate instance class QName')
        self.cache = {}
        self.active = set()

    def model(self, name):
        if name in self.cache:
            return self.cache[name]
        require(name not in self.active, 'Cyclic class inheritance: ' + name)
        self.active.add(name)
        inst = self.classes[name]
        parent = self.abc.mn_name(inst[1])
        if parent in self.classes:
            root, old_slots, old_bindings = self.model(parent)
            slots, bindings = list(old_slots), dict(old_bindings)
        else:
            root, slots, bindings = parent, [], {}
        for trait in inst[6]:
            if trait.kind not in (1, 2, 3):
                continue
            require(trait.data[1] == 0,
                    'Explicit dispatch ID requires SDK-specific proof: ' + name)
            key = binding(self.abc, trait.name)
            if key not in bindings:
                bindings[key] = (len(slots), trait.kind)
                slots.extend([None] * (1 if trait.kind == 1 else 2))
            at, first_kind = bindings[key]
            require((first_kind == 1) == (trait.kind == 1),
                    'Method/accessor binding kind changed: ' + name)
            if trait.kind == 3:
                at += 1
            slots[at] = Slot(name, int(trait.data[2]), trait.kind, key)
        self.active.remove(name)
        result = root, tuple(slots), bindings
        self.cache[name] = result
        return result


def preserved_old_dispatch(old_abc, final_abc, permitted_override_methods=()):
    """Check every original class and every inherited old slot, not prefixes."""
    old, final = Dispatch(old_abc), Dispatch(final_abc)
    count = 0
    affected_tails = []
    replacements = set(map(int, permitted_override_methods))
    observed = set()
    for name in old.classes:
        require(name in final.classes, 'Old class removed: ' + name)
        root, before, _ = old.model(name)
        after_root, after, _ = final.model(name)
        require(root == after_root, 'External superclass changed: ' + name)
        require(len(after) >= len(before), 'Old dispatch shortened: ' + name)
        for slot, (a, b) in enumerate(zip(before, after)):
            same_binding_override = (a and b and b.method in replacements
                                     and a.key == b.key and a.kind == b.kind)
            require(a == b or same_binding_override,
                    'Old inherited dispatch changed: ' + name + ':' + str(slot))
            if a != b:
                observed.add(b.method)
            count += a is not None
        if len(after) != len(before):
            affected_tails.append(dict(owner=name, original_slots=len(before), final_slots=len(after)))
    # A tail on an ancestor would already have shifted a child's old methods.
    # Explicitly report surviving tails; callers can review leaf additions.
    return dict(old_classes=len(old.classes), inherited_method_slots_checked=count,
                classes_with_appended_tail=affected_tails,
                permitted_overrides_observed=sorted(observed),
                original_inherited_binding_slots_exact=True,
                original_slot_method_ids_exact_except_listed_overrides=True)


def changed_bindings(before_abc, after_abc):
    """Return conservative QName/local names whose inherited slot moved."""
    before, after = Dispatch(before_abc), Dispatch(after_abc)
    names, rows = set(), []
    for name in before.classes:
        require(name in after.classes, 'Current input class removed: ' + name)
        _, left, _ = before.model(name)
        _, right, _ = after.model(name)
        left_methods = {(x.method, x.kind, x.key): at for at, x in enumerate(left) if x}
        right_methods = {(x.method, x.kind, x.key): at for at, x in enumerate(right) if x}
        moved = []
        for key, at in left_methods.items():
            destination = right_methods.get(key)
            if destination != at:
                names.add(key[2][-1])
                moved.append((key[0], at, destination))
        if moved:
            rows.append(dict(owner=name, moved=moved))
    return names, rows


# Methods taking a multiname that can resolve through a method/getter/setter.
# Include super access: parent table restoration can also change these targets.
DISPATCH_OPS = {0x04, 0x05, 0x45, 0x46, 0x4C, 0x4E, 0x4F,
                0x59, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x61,
                0x66, 0x68, 0x6A}


def multiname_local(abc, index):
    row = abc.multinames[index]
    if row[0] in (7, 13):
        return abc.strings[row[2]].decode('utf-8', 'strict')
    if row[0] in (9, 14, 15, 16):
        return abc.strings[row[1]].decode('utf-8', 'strict')
    return None


def conservative_recompile_closure(before_abc, after_abc, prior_native_methods,
                                   recompiled, exempt=()):
    """Independently require prior AOT member references that may have moved.

    This deliberately errs toward recompiling a same-name reference. It is a
    necessary coverage check, not a whole-program receiver type proof. Unknown
    runtime multinames and direct dispatch IDs are rejected for separate review.
    """
    p = framework()
    names, owners = changed_bindings(before_abc, after_abc)
    bodies = {b[0]: b for b in before_abc.bodies}
    required, ambiguous = {}, {}
    prior = set(map(int, prior_native_methods))
    for mid in sorted(prior):
        require(mid in bodies, 'Prior native method lacks semantic body: ' + str(mid))
        refs, uncertain = [], []
        for ordinal, (op, args) in enumerate(p.asm.opwalk.walk(bodies[mid][5])):
            if op == 0x43:  # callmethod encodes a dispatch ID, not a QName.
                uncertain.append((ordinal, 'callmethod', int(args[0])))
            elif op in DISPATCH_OPS:
                local = multiname_local(before_abc, args[0])
                if local is None:
                    uncertain.append((ordinal, 'runtime_multiname', int(args[0])))
                elif local in names:
                    refs.append((ordinal, op, local))
        if refs:
            required[mid] = refs
        if uncertain:
            ambiguous[mid] = uncertain
    covered = set(map(int, recompiled))
    exceptions = set(map(int, exempt))
    require(not (set(required) - covered - exceptions),
            'Incomplete restored-dispatch AOT closure: ' + str(sorted(set(required) - covered - exceptions)))
    require(not (set(ambiguous) - covered - exceptions),
            'Unreviewed dynamic/direct prior AOT dispatch: ' + str(sorted(set(ambiguous) - covered - exceptions)))
    return dict(prior_native_methods=len(prior), changed_binding_names=sorted(names),
                changed_classes=len(owners), conservative_required_methods=sorted(required),
                dynamic_or_direct_methods=sorted(ambiguous), explicitly_reviewed_exemptions=sorted(exceptions),
                all_required_recompiled=True,
                scope='conservative member-name closure; receiver type and wrapper reviews remain separate')


def focus_getter(abc):
    model = Dispatch(abc)
    owner = 'pinball.common.data.character::BattleCharacterLogic'
    root, slots, _ = model.model(owner)
    require(root == 'Object', 'Focused dispatch root is not builtin Object')
    builtin = framework().abcfmt.ABC((SDK / 'lib/aot/lib/builtin.abc').read_bytes())
    obj, = [i for i in builtin.instances if builtin.mn_name(i[0]) == 'Object']
    inherited = sum(1 if t.kind == 1 else 2 for t in obj[6] if t.kind in (1, 2, 3))
    require(inherited == 3, 'SDK builtin Object method slots changed')
    fields = (SDK / 'lib/aot/lib/air-fields.arm64-air.txt').read_text()
    require("field 128 *'avmplus::MethodEnv' methods" in fields, 'SDK VTable methods offset changed')
    at = (0x6A0 - 0x80) // 8 - inherited
    hit = slots[at]
    require(hit and hit.method == 18471,
            'HomeCarousel +0x6a0 still selects wrong method: ' + repr(hit))
    require(len(abc.methods[18471][1]) == 0, '18471 is not zero-explicit-argument getter')
    require(abc.mn_name(next(t.name for t in model.classes[owner][6]
                             if t.kind in (1, 2, 3) and t.data[2] == 18471))
            == 'getFullShotImagePathWithAttribute', '18471 semantic identity changed')
    return dict(method=18471, explicit_arguments=0, vtable_offset=0x6A0,
                application_relative_slot=at, builtin_object_slots=inherited)


def selftest():
    """Small independent controls; never read large application/native inputs."""
    from types import SimpleNamespace as NS
    def fake(with_parent_helper=False, leaf_helper=False):
        # Zero/unused namespace and QName entries retain real ABC indexing.
        strings = [b'', b'Object', b'Base', b'Leaf', b'old', b'extra', b'get']
        mn = [(0,), (7, 1, 2), (7, 1, 1), (7, 1, 3), (7, 1, 4), (7, 1, 5), (7, 1, 6)]
        t = lambda n, m, k=1: NS(name=n, kind=k, data=('method', 0, m))
        base = (1, 2, 0, 0, [], 0, [t(4, 10)] + ([t(5, 12)] if with_parent_helper else []))
        leaf = (3, 1, 0, 0, [], 0, [t(6, 11, 2)] + ([t(5, 13)] if leaf_helper else []))
        names = {1:'Base', 2:'Object', 3:'Leaf'}
        return NS(instances=[base, leaf], multinames=mn, namespaces=[(0, 0), (22, 0)],
                  strings=strings, mn_name=lambda i: names[i])
    good = preserved_old_dispatch(fake(), fake(leaf_helper=True))
    require(good['old_classes'] == 2 and good['inherited_method_slots_checked'] == 3,
            'Dispatch self-test count')
    try:
        preserved_old_dispatch(fake(), fake(with_parent_helper=True))
    except ValueError as error:
        require('Old inherited dispatch changed' in str(error), 'Wrong negative-control rejection')
    else:
        raise ValueError('Ancestor-helper regression was not detected')
    return dict(passed=2, scope='small synthetic inheritance fixtures')


if __name__ == '__main__':
    require(sys.argv[1:] == ['--self-test'], 'Use --self-test, or import from the final verifier')
    print(json.dumps(selftest()))
