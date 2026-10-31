"""Read-only conservative recompile closure for the 25-helper layout repair."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from collections import defaultdict
import bisect
import json
import mmap
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
from audit_instance_dispatch import load, model, methods, name_key, OLD, CURRENT, SOURCE, p
sys.path.insert(0, str(SOURCE / 'pr43-ios'))
from native_support import INFO_OFFSET

ROOT = Path(str(fc.client() / 'revision-ios-dispatch-fix-20261031/audit'))
OUT = ROOT / 'recompile-closure-run01'
NATIVE = CURRENT.with_name('worldflipper')
LINK_REPORTS = [
    Path(str(fc.client() / 'revision-settings/ios/linked01/link-report.json')),
    Path(str(fc.client() / 'revision-ios-acceptance-repairs/runs/link03/link-report.json')),
]
REMOVE = {101732, 101820, 101821, 101665, 101666, 101667, 101668, 101669, 101670,
    101685, 101686, 101687, 101688, 101689, 101690, 101691, 101692,
    101697, 101698, 101702, 101725, 101729, 101730, 101812, 101711}
DISPATCH_OPS = {4, 5, 0x45, 0x46, 0x4c, 0x4e, 0x4f, 0x59, 0x5d, 0x5e, 0x61, 0x66, 0x68, 0x6a}

def local_name(view, mi):
    mn = view.a.multinames[mi]
    if mn[0] in (7, 13):
        return view.a.strings[mn[2]].decode('utf8', 'replace')
    if mn[0] in (9, 14, 15, 16):
        return view.a.strings[mn[1]].decode('utf8', 'replace')
    return None

def native_tables(raw):
    off, segments, starts, start_payload = 32, [], [], None
    for _ in range(struct.unpack_from('<I', raw, 16)[0]):
        cmd, size = struct.unpack_from('<II', raw, off)
        if cmd == 0x19:
            label = raw[off + 8:off + 24].rstrip(b'\0').decode()
            vm, vs, fo, fs = struct.unpack_from('<4Q', raw, off + 24)
            segments.append((label, vm, vs, fo, fs))
        if cmd == 0x26:
            start_payload = struct.unpack_from('<II', raw, off + 8)
        off += size
    def fileoff(va, size=1):
        for _, vm, _, fo, fs in segments:
            if vm <= va and va + size <= vm + fs:
                return fo + va - vm
        raise ValueError(('unmapped', hex(va), size))
    va = next(r[1] for r in segments if r[0] == '__TEXT')
    at, size = start_payload
    end = at + size
    while at < end:
        delta, shift = 0, 0
        while True:
            b = raw[at]
            at += 1
            delta |= (b & 127) << shift
            shift += 7
            if not b & 128:
                break
        if not delta:
            break
        va += delta
        starts.append(va)
    count = struct.unpack_from('<Q', raw, INFO_OFFSET + 56)[0]
    table_va = struct.unpack_from('<Q', raw, INFO_OFFSET + 48)[0]
    table_at = fileoff(table_va, count * 8)
    table = struct.unpack_from('<' + 'Q' * count, raw, table_at)
    return fileoff, starts, table

def main():
    assert not OUT.exists()
    old, cur = load(OLD), load(CURRENT)
    om, cm = [{v.a.mn_name(i[0]): i for i in v.a.instances} for v in (old, cur)]
    filtered = {n: [*i[:6], [t for t in i[6] if t.kind not in (1, 2, 3) or t.data[2] not in REMOVE]] for n, i in cm.items()}
    initial = json.loads((ROOT / 'instance-dispatch-run01/instance-dispatch-audit.json').read_text('utf8'))
    relevant = [r['owner'] for r in initial['affected_old_class_models']]
    affected_types, targets, restored = set(), set(), []
    for owner in relevant:
        original = model(old, om, owner)
        before = model(cur, cm, owner)
        after = model(cur, filtered, owner)
        before_map = {r['identity']: r for r in before['slots'] if r}
        after_map = {r['identity']: r for r in after['slots'] if r}
        original_map = {r['identity']: r for r in original['slots'] if r}
        moves = []
        for identity, before_row in before_map.items():
            after_row = after_map.get(identity)
            if after_row is None or before_row['slot_relative_to_external'] != after_row['slot_relative_to_external']:
                local = before_row['name'].split('::')[-1]
                targets.add(local)
                moves.append(dict(method=before_row['method'], name=local,
                    old_current_slot=before_row['slot_relative_to_external'],
                    repaired_slot=None if after_row is None else after_row['slot_relative_to_external']))
        if moves:
            affected_types.add(owner)
        for identity, old_row in original_map.items():
            repaired = after_map.get(identity)
            assert repaired is not None, ('old binding lost', owner, old_row['method'])
            assert old_row['slot_relative_to_external'] == repaired['slot_relative_to_external'], ('old slot not restored', owner, old_row['method'])
        restored.append(dict(owner=owner, all_original_effective_slots_restored=True,
            old_effective_slots=len(original['slots']), current_effective_slots=len(before['slots']),
            repaired_effective_slots=len(after['slots']), changes=moves))
    functions = {}
    for report_path in LINK_REPORTS:
        report = json.loads(report_path.read_text('utf8'))
        for row in report['functions']:
            mid = int(row['method'])
            assert mid not in functions, ('reports overlap', mid)
            functions[mid] = dict(row, source_report=str(report_path))
    assert len(functions) == 356
    bodies = {r[0]: r for r in cur.a.bodies}
    selected, unselected, dynamic, direct_calls = [], [], [], defaultdict(list)
    for mid in sorted(functions):
        body = bodies[mid]
        hits, dynamic_ops = [], []
        for index, (op, operands) in enumerate(p.asm.opwalk.walk(body[5])):
            if op in DISPATCH_OPS:
                name = local_name(cur, operands[0])
                if name in targets:
                    hits.append(dict(instruction=index, opcode=hex(op), name=name, multiname=cur.mn(operands[0])))
                elif name is None:
                    dynamic_ops.append(dict(instruction=index, opcode=hex(op), multiname=cur.mn(operands[0])))
            if op == 0x43:
                dynamic_ops.append(dict(instruction=index, opcode=hex(op), reason='callmethod with explicit dispatch id', operands=operands))
            if op == 0x44:
                direct_calls[operands[0]].append(mid)
        row = dict(method=mid, label=cur.labels.get(mid, 'UNMAPPED'),
            body_bytes=len(body[5]), property_hits=hits, dynamic_property_ops=dynamic_ops,
            is_migrated_helper=mid in REMOVE)
        if hits or mid in REMOVE:
            selected.append(row)
        else:
            unselected.append(row)
        if dynamic_ops:
            dynamic.append(mid)
    # AOT native check of explicit VTable-dispatch-shaped instruction windows.
    # This is a second conservative screen; it cannot determine receiver type.
    import capstone
    cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    opcode_native_hits, wrapped_entries = [], []
    target_offsets = {152 + r['old_current_slot'] * 8 for row in restored for r in row['changes']}
    with NATIVE.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as raw:
        fileoff, starts, table = native_tables(raw)
        rtva, rtsize = struct.unpack_from('<QQ', raw, INFO_OFFSET + 24)
        rt = p.View(type('ABCOnly', (), dict(abc=p.abcfmt.ABC(raw[fileoff(rtva, rtsize):fileoff(rtva, rtsize) + rtsize])))(), p.asm)
        rm = {rt.a.mn_name(i[0]): i for i in rt.a.instances}
        runtime_checks = []
        for owner in relevant:
            equal = methods(cur, owner, cm[owner]) == methods(rt, owner, rm[owner])
            assert equal, ('runtime declarations differ', owner)
            runtime_checks.append(dict(owner=owner, actual_runtime_method_traits_equal_full=True))
        for mid, row in sorted(functions.items()):
            if table[mid] != row['address']:
                # Active table entries can intentionally point at cumulative
                # wrappers. The compiled function remains a downstream target.
                wrapped_entries.append(dict(method=mid, compiled_function_address=hex(row['address']),
                    active_table_address=hex(table[mid]),
                    reason='Compiled function is not active table entry; preserve and verify wrapper route separately'))
            at = fileoff(row['address'], row['size'])
            assert at == row['file_offset'], ('function file offset mismatch', mid)
            instructions = list(cs.disasm(raw[at:at + row['size']], row['address']))
            hits = []
            for index, ins in enumerate(instructions):
                # ldr MethodEnv,[VTable,#slot] followed nearby by a blr is a
                # possible static dispatch. String parsing is only a screen.
                if ins.mnemonic != 'ldr' or ', #' not in ins.op_str:
                    continue
                try:
                    offset = int(ins.op_str.rsplit(', #', 1)[1].rstrip(']'), 0)
                except ValueError:
                    continue
                if offset not in target_offsets:
                    continue
                tail = instructions[index + 1:index + 9]
                if any(x.mnemonic == 'blr' for x in tail):
                    hits.append(dict(address=hex(ins.address), slot_offset=hex(offset),
                        instruction=ins.mnemonic + ' ' + ins.op_str))
            if hits:
                opcode_native_hits.append(dict(method=mid, label=cur.labels.get(mid, 'UNMAPPED'), hits=hits))
        # Retained original methods from moved descendants remain unchanged
        # in current native. Compare sparse methods, never entire binaries.
        examples = [18631, 18632, 18633]
        examples += [r['method'] for r in initial['affected_old_class_models']
            if r['owner'].endswith('::Conductor') for r in r['moved'] if r['owner'].endswith('::Conductor')][:3]
        oldnative = OLD.parent / 'linked/worldflipper'
        retained = []
        with oldnative.open('rb') as oldstream, mmap.mmap(oldstream.fileno(), 0, access=mmap.ACCESS_READ) as oldraw:
            oldoff, oldstarts, oldtable = native_tables(oldraw)
            for mid in examples:
                va = oldtable[mid]
                index = bisect.bisect_left(oldstarts, va)
                assert oldstarts[index] == va
                size = oldstarts[index + 1] - va
                start_old, start_current = oldoff(va, size), fileoff(table[mid], size)
                equal = oldraw[start_old:start_old + size] == raw[start_current:start_current + size]
                assert equal, ('sparse old native was modified', mid)
                retained.append(dict(method=mid, label=cur.labels.get(mid, 'UNMAPPED'),
                    bytes=size, native_entry_unchanged=va == table[mid], native_bytes_unchanged=True))
    selected_ids = {r['method'] for r in selected}
    native_ids = {r['method'] for r in opcode_native_hits}
    conservative = sorted(selected_ids | native_ids)
    result = dict(scope='Read-only current356 conservative recompile-closure screen',
        remove_instance_method_ids=sorted(REMOVE), existing_effective_function_count=356,
        link_reports=[str(p) for p in LINK_REPORTS],
        affected_receiver_classes=sorted(affected_types), affected_method_local_names=sorted(targets),
        simulated_repair=restored, actual_runtime_trait_checks=runtime_checks,
        bytecode_selected=selected, bytecode_unselected=unselected,
        dynamic_property_functions=dynamic, native_dispatch_pattern_hits=opcode_native_hits,
        conservative_recompile_method_ids=conservative,
        extra_native_screen_method_ids=sorted(native_ids - selected_ids),
        compiled_functions_with_wrapped_table_entries=wrapped_entries,
        direct_callstatic_consumers={str(k): v for k, v in direct_calls.items() if k in REMOVE},
        sparse_unchanged_old_native_examples=retained,
        special_routes=['18392 typed bridge to 101665 must be rebuilt for explicit static receiver, while preserving equipment/five-in-one/resolver active wrappers',
            'Recompile from current full ABC and then remap static-helper consumers; compiled receiver slots must match repaired full/runtime declarations'],
        limitations=['The property-name screen intentionally includes ambiguous namespaces and receivers',
            'The native screen is a pattern screen, not full typed dataflow or indirect target proof',
            'Dynamic runtime property lookup has no fixed receiver slot in ABC but native lowering still requires final object inspection',
            'Use all356 if compile filtering cannot independently prove no changed fixed-slot access; do not claim this conservative screen is a mathematically minimal set'])
    OUT.mkdir()
    (OUT / 'recompile-closure.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps(dict(effective_functions=356, remove_helpers=len(REMOVE),
        original_class_layout_models_restored=len(restored), affected_receiver_classes=len(affected_types),
        affected_names=len(targets), bytecode_selected=len(selected), native_screen=len(native_ids),
        conservative_recompile=len(conservative), dynamic_property_functions=len(dynamic),
        output=str(OUT / 'recompile-closure.json')), ensure_ascii=False))

if __name__ == '__main__':
    main()
