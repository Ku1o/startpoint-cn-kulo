"""Adapt imported ready-voice reads to the accepted arm64 Number tail slots.

The three existing HUD traits are immutable.  Only the copied method body is
changed: missing convert_i instructions are inserted, and every instruction
target and exception byte boundary is relocated.  No compiler/linker is run.
"""
from __future__ import annotations

import copy
from collections import Counter

OWNER = 'pinball.scene.battle.battle.hud::HudMemberStatus'
COUNTERS = ('wtsReadyNormalNext', 'wtsReadyFeverNext', 'geraldReadyNext')


def _validate_traits(abc):
    owners = [row for row in abc.instances if abc.mn_name(row[0]) == OWNER]
    if len(owners) != 1:
        raise ValueError('Exactly one native HUD class is required')
    traits = owners[0][6]
    for name in COUNTERS:
        matches = [t for t in traits if abc.mn_name(t.name) == name]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous HUD counter trait: ' + name)
        trait = matches[0]
        if trait.kind != 0 or trait.data[0] != 'slot' or abc.mn_name(trait.data[2]) != 'Number':
            raise ValueError('HUD counter must retain its Number tail slot: ' + name)
        value, kind = trait.data[3:5]
        if kind != 6 or not 0 < value < len(abc.doubles) or abc.doubles[value] != 0.0:
            raise ValueError('HUD counter must retain its zero Number default: ' + name)


def adapt_hud_body(abc, body, asm, *, expected_reads=16):
    """Return ``(copied_body, report)`` without modifying ``abc`` or ``body``.

    ``body`` uses the existing eight-item ABC body representation.  It must
    already have been imported into ``abc``'s pools.  The default locks this
    adapter to the final sixteen-read HUD body; a small explicit read count is
    supported for focused bytecode boundary tests.  Already-adapted reads are
    recognized, making a repeated application a byte-exact no-op.
    """
    _validate_traits(abc)
    if len(body) != 8 or not isinstance(expected_reads, int) or expected_reads < 1:
        raise ValueError('Invalid HUD body or expected read count')
    old = asm.decode(body[5])
    encoded, offsets = asm.encode(old)
    if encoded != body[5]:
        raise ValueError('HUD instruction decoding must roundtrip byte-exactly')
    offsets.append(len(body[5]))
    old_at = dict((offset, index) for index, offset in enumerate(offsets))
    reads, inserted, already, instructions, positions = [], [], [], [], {}
    for index, ins in enumerate(old):
        positions[index] = len(instructions)
        instructions.append(copy.deepcopy(ins))
        if ins.op != 0x66 or abc.mn_name(ins.args[0]) not in COUNTERS:
            continue
        name = abc.mn_name(ins.args[0])
        reads.append({'instruction': index, 'field': name})
        if index + 1 < len(old) and old[index + 1].op == 0x73:
            already.append(index)
        else:
            inserted.append(index)
            instructions.append(asm.Instruction(0x73))
    if len(reads) != expected_reads:
        raise ValueError('Unexpected HUD counter read count: expected %d, found %d' %
                         (expected_reads, len(reads)))
    positions[len(old)] = len(instructions)
    for ins in instructions:
        try:
            if ins.target is not None:
                ins.target = positions[ins.target]
            if ins.default is not None:
                ins.default = positions[ins.default]
            if ins.cases is not None:
                ins.cases = [positions[target] for target in ins.cases]
        except KeyError as error:
            raise ValueError('HUD branch target is not an original instruction boundary') from error
    code, new_offsets = asm.encode(instructions)
    new_offsets.append(len(code))
    exception_rows = []
    for start, end, target, type_index, variable_index in body[6]:
        if not (0 <= start < end <= len(body[5])) or target >= len(body[5]):
            raise ValueError('Invalid HUD exception range or handler')
        try:
            boundaries = [new_offsets[positions[old_at[x]]] for x in (start, end, target)]
        except KeyError as error:
            raise ValueError('HUD exception boundary is not an instruction boundary') from error
        exception_rows.append((*boundaries, type_index, variable_index))
    result = copy.deepcopy(body)
    result[5], result[6] = code, exception_rows
    # convert_i consumes/produces one value; max stack, local count, scopes and
    # activation traits are unchanged, including the compiler-visible ABI.
    report = dict(reads=len(reads), inserted=len(inserted), already_converted=len(already),
                  counter_reads=dict(Counter(row['field'] for row in reads)),
                  inserted_after_instructions=inserted,
                  already_converted_after_instructions=already,
                  instruction_count_before=len(old), instruction_count_after=len(instructions),
                  exception_count=len(body[6]), traits_preserved=True,
                  old_to_new_instruction=positions,
                  old_to_new_byte_offset=dict((offset, new_offsets[positions[index]])
                                              for index, offset in enumerate(offsets)))
    return result, report
