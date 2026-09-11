"""Preserve the original arm64 HUD slot layout while retaining ready voices.

AIR allocates 32-bit scalar slots before reference slots and Number slots after
them. Appending three int traits moved every existing HUD reference by 8 bytes,
invalidating the retained native constructor/run/accessors. Store the three
small counters as zero-initialized Numbers, converting reads to int explicitly.
Only update() accesses these counters. No persistence or save IDs are involved.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from prepare import abcfmt, asm, dump, sha, view

OWNER = 'pinball.scene.battle.battle.hud::HudMemberStatus'
COUNTERS = ('wtsReadyNormalNext', 'wtsReadyFeverNext', 'geraldReadyNext')
METHOD = 63979
R3 = Path(r'F:\codex\ios-artifacts\StarPoint-iOS-1.8.4-login-abyss-lens-public-fix-r3-20260911-unsigned.ipa')
R3_SHA = '61a545ea867e97837fee2204c1649e362d6e3be2d98aa80abd3931111354a9af'
NATIVE_SHA = 'ee2ac750c1a8ab1ea40a4a970a842ab9f29162cce5b6530c807ce61f590a17cb'
FULL = Path(r'F:\codex\ios-artifacts\login-abyss-lens-public-fix-r3-20260911\cumulative-full-r3.abc')
FULL_SHA = '5c08c74334c5a76c22870d9608e67c1bbaa1067cd8442be33982e08bc2a2cd4d'
WORK = Path(r'F:\codex\work\ios-hud-f1009-r4-20260911')
OUTPUT = Path(r'F:\codex\ios-artifacts\StarPoint-iOS-1.8.4-login-abyss-hud-public-fix-r4-20260911-unsigned.ipa')


def hud_traits(abc):
    return next(i[6] for i in abc.instances if abc.mn_name(i[0]) == OWNER)


def slot_offsets(abc):
    """This specific sealed HUD class starts after GearHolderImpl at 0x28.

    The baseline native constructor, run and accessors independently confirm
    the old offsets. Reject subclasses or unrecognized scalar types rather
    than applying this model to arbitrary ABC classes.
    """
    assert not any(abc.mn_name(i[1]) == OWNER for i in abc.instances)
    slots = [t for t in hud_traits(abc) if t.kind in (0, 6)]
    small = [t for t in slots if abc.mn_name(t.data[2]) in ('int', 'uint', 'Boolean')]
    doubles = [t for t in slots if abc.mn_name(t.data[2]) == 'Number']
    pointers = [t for t in slots if t not in small and t not in doubles]
    assert all(abc.mn_name(t.data[2]).startswith(('pinball.', 'flatomo.')) for t in pointers)
    offsets = {}; pos = 0x28
    for group, size in ((small, 4), (pointers, 8), (doubles, 8)):
        if group: pos = (pos + size - 1) & -size
        for t in group:
            offsets[abc.mn_name(t.name)] = pos; pos += size
    return offsets


def correct_traits(abc):
    number, = [i for i in range(len(abc.multinames)) if abc.mn_name(i) == 'Number']
    zero = next(i for i in range(1, len(abc.doubles)) if abc.doubles[i] == 0.0)
    changed = []
    for trait in hud_traits(abc):
        name = abc.mn_name(trait.name)
        if name not in COUNTERS: continue
        assert trait.kind == 0 and abc.mn_name(trait.data[2]) == 'int'
        assert trait.data[3:] == (0, None) or trait.data[3:] == [0, None]
        data = list(trait.data); data[2:] = [number, zero, 6]
        trait.data = tuple(data); changed.append(name)
    assert tuple(changed) == COUNTERS


def correct_body(abc):
    names = {i for i in range(len(abc.multinames)) if abc.mn_name(i) in COUNTERS}
    body, = [b for b in abc.bodies if b[0] == METHOD]
    assert not body[6], 'HUD update unexpectedly contains an exception table'
    old = asm.decode(body[5]); new = []; mapping = {}; reads = []
    for i, ins in enumerate(old):
        mapping[i] = len(new); new.append(copy.deepcopy(ins))
        if ins.op == 0x66 and ins.args[0] in names:
            reads.append(i); new.append(asm.Instruction(0x73))  # convert_i
    assert len(reads) == 5
    mapping[len(old)] = len(new)
    for ins in new:
        if ins.target is not None: ins.target = mapping[ins.target]
        if ins.default is not None: ins.default = mapping[ins.default]
        if ins.cases is not None: ins.cases = [mapping[t] for t in ins.cases]
    body[5] = asm.encode(new)[0]
    return reads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=WORK)
    args = parser.parse_args(); args.work.mkdir(parents=True, exist_ok=True)
    raw = FULL.read_bytes(); assert sha(raw) == FULL_SHA
    abc = abcfmt.ABC(raw); before = slot_offsets(abc)
    correct_traits(abc); reads = correct_body(abc)
    target = args.work / 'cumulative-full-r4.abc'; assert not target.exists()
    target.write_bytes(abc.serialize())
    after = slot_offsets(abc)
    expected = {'prevSkillPointCycle': 0x28, 'viewOrder': 0x30,
                'playheadHealthPointGaugeGlowAnimation': 0x38, 'member': 0x40,
                'featuresPermit': 0x48, 'features': 0x50,
                'effectManager': 0x58, 'character': 0x60}
    assert {k: after[k] for k in expected} == expected
    dump(args.work / 'port.json', dict(full_abc_file=target.name,
         full_abc_sha256=sha(target.read_bytes()), before_offsets=before,
         after_offsets=after, integer_read_conversions=reads))
    print(json.dumps({'full_abc': str(target), 'slot_offsets': after}))


if __name__ == '__main__':
    main()
