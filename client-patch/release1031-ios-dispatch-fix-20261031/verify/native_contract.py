"""Independent ARM64 wrapper-chain and preserved-native checks."""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()

import struct

from dispatch_contract import require

INFO = 104549248
LEGACY = 0x62C0780
SPECIALS = {18392, 66181}
TAIL = 0x106207AF4
DRAW_CALL = 0x103D69208
ALLOWED_CODE_VA = [(TAIL, TAIL + 4), (DRAW_CALL, DRAW_CALL + 8)]


def branch(word, pc):
    require(word & 0xFC000000 in (0x14000000, 0x94000000), 'Expected B/BL instruction')
    value = word & 0x3FFFFFF
    return pc + (value - (1 << 26) if value & (1 << 25) else value) * 4


def draw_target(raw, pc):
    adrp, add, blr = struct.unpack_from('<III', raw)
    require(adrp & 0x9F00001F == 0x90000010
            and add & 0xFFC003FF == 0x91000210
            and blr == 0xD63F0200, 'Draw typed bridge is not ADRP/ADD/BLR x16')
    immediate = (adrp >> 29 & 3) | ((adrp >> 5 & 0x7FFFF) << 2)
    if immediate & (1 << 20):
        immediate -= 1 << 21
    return (pc & ~4095) + immediate * 4096 + (add >> 10 & 0xFFF)


def masked_range(old, new, va, size):
    before, after = old.read(va, size), bytearray(new.read(va, size))
    for lo, hi in ALLOWED_CODE_VA:
        left, right = max(va, lo), min(va + size, hi)
        if left < right:
            after[left-va:right-va] = before[left-va:right-va]
    require(after == before, 'Protected native chain changed outside exact 12-byte binding: ' + hex(va))


def verify_wrappers(old, new, linked, prior_functions, targets):
    wanted = {int(r['method']): r for r in linked['functions']}
    require(SPECIALS <= wanted.keys() and SPECIALS <= set(targets), 'Both wrapper extension methods must compile')
    require(all(not any(f':{mid}:' in r['symbol'] for r in linked['relocations']) for mid in SPECIALS),
            'Direct compiled cross-call bypasses preserved equipment/draw wrapper')
    active = struct.unpack_from('<Q', old.raw, INFO + 48)[0]
    pointer_rows = []
    for mid in sorted(SPECIALS):
        for kind, at in (('active', old.offset(active + mid * 8)), ('legacy', LEGACY + mid * 8)):
            require(new.raw[at:at + 8] == old.raw[at:at + 8], 'Protected wrapper table pointer changed')
            pointer_rows.append(dict(method=mid, table=kind, offset=at,
                                     target=struct.unpack_from('<Q', new.raw, at)[0]))
    require(struct.unpack_from('<Q', new.read(active + 18392 * 8, 8))[0] == 0x10D9D9030,
            'Resolver active table bypasses equipment wrapper')
    require(struct.unpack_from('<Q', new.raw, LEGACY + 18392 * 8)[0] == 0x106207AA0,
            'Resolver legacy table bypasses five-in-one wrapper')
    require(struct.unpack_from('<Q', new.read(active + 66181 * 8, 8))[0] == 0x103D69180,
            'Draw active table bypasses retained wrapper')
    require(struct.unpack_from('<Q', new.raw, LEGACY + 66181 * 8)[0] == 0x103D69180,
            'Draw legacy table bypasses retained wrapper')
    # Verify semantic wrapper binding from actual words, not report booleans.
    old_resolver = branch(struct.unpack_from('<I', old.read(TAIL, 4))[0], TAIL)
    tail_word = struct.unpack_from('<I', new.read(TAIL, 4))[0]
    require(tail_word & 0xFC000000 == 0x94000000, 'Resolver postprocessing tail no longer BL')
    via = branch(tail_word, TAIL)
    target = wanted[18392]['address']
    if via != target:
        words = struct.unpack('<4I', new.read(via, 16))
        require(words[2:] == (0xD61F0200, 0xD503201F), 'Resolver veneer register/BR/NOP changed')
        # Reuse the independent ADRP/ADD decoder with its required BLR word;
        # this veneer ends in BR, which was just checked above.
        decoded = draw_target(struct.pack('<III', words[0], words[1], 0xD63F0200), via)
        require(decoded == target, 'Resolver tail veneer reaches wrong compiled function')
    old_draw = draw_target(old.read(DRAW_CALL, 12), DRAW_CALL)
    prior_by_method = {int(r['method']): r for r in prior_functions}
    require(old_resolver == prior_by_method[18392]['address']
            and old_draw == prior_by_method[66181]['address'],
            'Original wrapper extension target differs from cumulative method identity')
    require(draw_target(new.read(DRAW_CALL, 12), DRAW_CALL) == wanted[66181]['address'],
            'Draw typed bridge reaches wrong compiled function')
    declared_resolver, declared_draw = linked['dispatch_resolver_wrapper'], linked['dispatch_draw_wrapper']
    require((declared_resolver['method'], declared_resolver['tail'], declared_resolver['compiled_function'])
            == (18392, TAIL, target), 'Resolver report differs from actual chain')
    require(declared_resolver['previous_target'] == old_resolver
            and declared_draw['previous_target'] == old_draw,
            'Wrapper report previous target differs from actual original chain')
    require((declared_draw['method'], declared_draw['call_address'], declared_draw['compiled_function'])
            == (66181, DRAW_CALL, wanted[66181]['address']), 'Draw report differs from actual chain')
    ranges = [
        ('draw-wrapper-and-live-frame', 0x103D69180, 0x103D694C4 - 0x103D69180),
        ('draw-stock', 0x102B990D4, 5224),
        ('draw-scale-bl', 0x103A4561C, 4),
        ('draw-scale-trampoline', 0x103D694D0, 396),
        ('equipment-wrapper', 0x10D9D9030, 52),
        ('five-in-one-wrapper', 0x106207AA0, 208),
        ('resolver-stock', 0x104963A08, 4372),
    ]
    for _, va, size in ranges:
        masked_range(old, new, va, size)
    # Bind the precise original caller that triggered the actual crash.
    callsite = 0x103421BDC
    expected = (0xF9400B28, 0xAA1903E0, 0xF9435101,
                0xF9400828, 0xF9402908, 0xD63F0100)
    require(struct.unpack('<6I', new.read(callsite, 24)) == expected
            and new.read(callsite, 24) == old.read(callsite, 24),
            'HomeCarousel retained native zero-argument +0x6a0 callsite changed')
    preserved = []
    for row in prior_functions:
        mid = int(row['method'])
        if mid in targets:
            continue
        require(old.read(row['address'], row['size']) == new.read(row['address'], row['size']),
                'Prior non-target compiled native changed: ' + str(mid))
        preserved.append(mid)
    return dict(wrapper_extension_methods=sorted(SPECIALS), pointer_sites=pointer_rows,
                resolver_previous_target=old_resolver, resolver_compiled_target=target, resolver_via=via,
                draw_previous_target=old_draw, draw_compiled_target=wanted[66181]['address'],
                preserved_ranges=[dict(name=n, address=v, bytes=s) for n, v, s in ranges],
                exact_code_binding_exception_bytes=12, original_crash_callsite_preserved=True,
                prior_non_target_compiled_methods_exact=sorted(preserved),
                direct_compiled_wrapper_bypasses=0,
                inherited_draw_wrapper_cfi_limitation=True)


def prefix_ranges(image):
    return [(image.offset(lo), image.offset(lo) + hi - lo) for lo, hi in ALLOWED_CODE_VA]


def unwind_page_bounds(image):
    """Check official 4KiB/entry-count limits while allowing exact page aliases."""
    _, size, offset = image.sections['__TEXT', '__unwind_info']
    raw = image.raw[offset:offset + size]
    require(len(raw) == size and size >= 28, 'Unwind section extent')
    version, co, nc, po, np, io, ni = struct.unpack_from('<7I', raw)
    require(version == 1 and 0 < nc <= 256 and ni >= 2, 'Unwind header/count range')
    require(co + nc * 4 <= size and po + np * 4 <= size and io + ni * 12 <= size,
            'Unwind header metadata leaves section')
    index = [struct.unpack_from('<III', raw, io + n * 12) for n in range(ni)]
    require(index[-1][1] == 0 and all(a[0] < b[0] for a, b in zip(index, index[1:])),
            'Unwind top-level function ranges not strictly increasing/sentinel missing')
    require(all(a[2] <= b[2] for a, b in zip(index, index[1:]))
            and all(x[2] <= size for x in index), 'Unwind per-range LSDA spans invalid')
    metadata_end = max(28, co + nc * 4, po + np * 4, io + ni * 12, index[-1][2])
    unique, aliases, max_bytes, max_entries = {}, 0, 0, 0
    for start, page, _ in index[:-1]:
        require(metadata_end <= page <= size - 8, 'Unwind page overlaps metadata or leaves section')
        kind, entries, count = struct.unpack_from('<IHH', raw, page)
        if kind == 3:
            require(page + 12 <= size, 'Compressed page header extent')
            encodings, enc_count = struct.unpack_from('<HH', raw, page + 8)
            require(entries >= 12 and 0 < count <= 1021, 'Compressed page exceeds 1021-entry format bound')
            end = entries + count * 4
            if enc_count:
                require(encodings >= end and enc_count + nc <= 256, 'Compressed local encoding table invalid')
                end = encodings + enc_count * 4
            require(page + end <= size, 'Compressed page payload leaves unwind section')
            first = struct.unpack_from('<I', raw, page + entries)[0] & 0xFFFFFF
            require(first == 0, 'Compressed page first offset does not match selected top-level base')
        elif kind == 2:
            require(entries >= 8 and 0 < count <= 511, 'Regular page exceeds 511-entry format bound')
            end = entries + count * 8
        else:
            raise ValueError('Unknown compact-unwind page kind')
        require(end <= 4096 and page + end <= size, 'Unwind page exceeds 4096-byte format bound')
        if page in unique:
            require(kind == 3 and unique[page] == end, 'Only exact compressed page payloads may alias')
            aliases += 1
        else:
            unique[page] = end
        max_bytes, max_entries = max(max_bytes, end), max(max_entries, count)
    extents = sorted((at, at + length) for at, length in unique.items())
    require(all(a[1] <= b[0] for a, b in zip(extents, extents[1:])), 'Different unwind payloads partially overlap')
    return dict(index_ranges=ni - 1, unique_page_payloads=len(unique), shared_page_aliases=aliases,
                max_page_bytes=max_bytes, max_page_entries=max_entries,
                official_4096_byte_page_limit=True, compressed_1021_entry_limit=True,
                lsda_range_offsets_independently_retained=True,
                source='https://github.com/apple-oss-distributions/libunwind/blob/main/libunwind/include/mach-o/compact_unwind_encoding.h#L375-L439')


def equipment_preservation(old, new, equipment, read):
    """Preserve current equipment-chain bytes, with only reviewed target binds."""
    plan = read(equipment['plan_file'])
    for row in plan['chunks']:
        masked_range(old, new, row['va'], row['bytes'])
    for row in plan['patches']:
        length, at = len(bytes.fromhex(row['after'])), row['file_offset']
        before, after = old.raw[at:at + length], bytearray(new.raw[at:at + length])
        for lo, hi in prefix_ranges(old):
            left, right = max(at, lo), min(at + length, hi)
            if left < right:
                after[left-at:right-at] = before[left-at:right-at]
        require(after == before, 'Current equipment patch changed')
    for row in plan['preserved_native_ranges']:
        masked_range(old, new, row['va'], row['bytes'])
    return plan
