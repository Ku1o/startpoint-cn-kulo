"""Link a prepared arm64 AOT delta into the accepted carrier, preserving ABI.

Only new native/SWF/runtime payloads and an auditable receipt are emitted.
Package creation, signing, device execution and acceptance registration are
separate operations.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import struct
from pathlib import Path
from native_support import (INFO_OFFSET, backend, check_definitions,
                            current_origin, dependency_info, dump, read_report,
                            read64, sha, source_inputs, symbol_record,
                            activation_tail, activation_relocations,
                            verify_entry_aliases, verify_signing_models, wanted_methods, write64)
link = backend()
from fixed_inputs import fixed_json
import prepare as p
from macho_signing_layout import assert_signable_layout, insert_before_string_table
import veneers
abcfmt, view = p.abcfmt, p.view
SYMBOL_STRICT_EQUALS = link.aot.STRICT_EQUALS_SYMBOL


def add_rebases(data, entries):
    info = link.read_rebase(data)
    stream = bytearray(info['prefix'])
    stream.append(0x11)
    existing = set(info['entries'])
    assert all(si <= 15 for si, _, _ in existing)
    assert all(0 <= si <= 15 and (si, offset, 1) not in existing for si, offset in entries)
    for si in sorted({s for s, _ in entries}):
        offsets = sorted(o for s, o in entries if s == si)
        n = 0
        while n < len(offsets):
            end = n + 1
            while end < len(offsets) and offsets[end] == offsets[end - 1] + 8:
                end += 1
            stream.append(0x20 | si)
            stream += link.uleb(offsets[n])
            stream.append(0x60)
            stream += link.uleb(end - n)
            n = end
    stream.append(0)
    offset = insert_before_string_table(data, stream)
    struct.pack_into('<II', data, info['command'] + 8, offset, len(stream))
    assert link.read_rebase(data)['entries'] == info['entries'] + [(s, o, 1) for s, o in sorted(entries)]
    return {'old_count': len(existing), 'new_count': len(entries),
            'stream_offset': offset, 'stream_size': len(stream)}


def extend(native, code_size):
    old = link.segments(native)
    tail = old[-1]
    segment = old[-2]
    assert len(old) == 18 and segment['name'] == '__CNRECIO' and tail['name'] == '__LINKEDIT'
    assert segment['off'] + segment['fs'] == tail['off']
    assert segment['vm'] + segment['vs'] == tail['vm']
    assert segment['fs'] == segment['vs']
    growth = link.aot.align(code_size, 0x4000)
    rx = dict(name='__CNRECIO', vm=tail['vm'], off=tail['off'], size=growth,
              payload=code_size, prot=5, index=16)
    offsets = {2: [8, 16], 0xb: [32, 40, 48, 56, 64, 72],
               0x22: [8, 16, 24, 32, 40], 0x80000022: [8, 16, 24, 32, 40]}
    datacmds = {0x1d, 0x1e, 0x26, 0x29, 0x2b, 0x2e, 0x80000033}
    patched = bytearray(native[:tail['off']] + bytes(growth) + native[tail['off']:])
    for at, cmd, raw in link.commands(native):
        row = bytearray(raw)
        assert cmd != 0x80000034
        if at == segment['command']:
            assert len(raw) == 152 and struct.unpack_from('<I', raw, 64)[0] == 1
            struct.pack_into('<Q', row, 32, segment['vs'] + growth)
            struct.pack_into('<Q', row, 48, segment['fs'] + growth)
            struct.pack_into('<Q', row, 112, segment['fs'] + code_size)
        if at == tail['command']:
            struct.pack_into('<Q', row, 24, tail['vm'] + growth)
            struct.pack_into('<Q', row, 40, tail['off'] + growth)
        for field in offsets.get(cmd, [8] if cmd in datacmds else []):
            value = struct.unpack_from('<I', row, field)[0]
            if value:
                assert value >= tail['off']
                struct.pack_into('<I', row, field, value + growth)
        patched[at:at + len(row)] = row
    end = 32 + struct.unpack_from('<I', native, 20)[0]
    assert link.read_rebase(patched)['entries'] == link.read_rebase(native)['entries']
    return patched, rx, end


def run(prepared_report, compiled_report, output, *, runtime_stubs, dependencies):
    prepared_report, port = read_report(prepared_report)
    OLD_COUNT = NATIVE_COUNT = int(port['old_methods'])
    reg = port['source_ipa']
    out = Path(output).resolve()
    native, swf, full = source_inputs(prepared_report, port)
    assert port['old_methods'] == OLD_COUNT and port['total_methods'] >= OLD_COUNT
    assert not out.exists()
    current_origin(native)
    assert_signable_layout(native)
    count = port['total_methods']
    redirects = {int(row['original']): int(row['compiled']) for row in port.get('method_redirects', [])}
    assert not port.get('native_start_wrapper'), 'wrappers must be prepared explicitly'
    assert not any(r.get('strategy') == 'guard_then_original' for r in port.get('method_redirects', []))
    aliases = {row['original']: row['compiled'] for row in port.get('native_aliases', [])}
    wanted = wanted_methods(port) - set(aliases)
    shared_entries = verify_entry_aliases(native, port, wanted)
    compiled_report = json.loads(Path(compiled_report).read_text('utf8'))
    assert compiled_report['prepared_report_sha256'] == sha(prepared_report.read_bytes())
    assert compiled_report['full_abc_sha256'] == sha(full)
    objects, funcs, meta = {}, {}, None
    for row in compiled_report['objects']:
        path = Path(compiled_report['directory']) / row['name']
        assert sha(path.read_bytes()) == row['sha256']
        obj = link.lief.parse(str(path))
        objects[path] = obj
        symbols = list(obj.symbols)
        if any(link.aot.text(s.name).endswith('_284_aotInfo') and s.numberof_sections for s in symbols):
            meta = (path, obj)
        ids = [i for i in wanted
               if any(f':{i}:' in link.aot.text(s.name) and s.numberof_sections for s in symbols)]
        if ids:
            for mid in ids:
                names = [link.aot.text(s.name) for s in symbols
                         if s.numberof_sections and re.search(rf':{mid}:', link.aot.text(s.name))]
                assert len(names) == 1, (mid, names)
                funcs[mid] = symbol_record(obj, path, names[0], mid)
    assert set(funcs) == wanted and meta, ('missing compiled methods', sorted(wanted - set(funcs)))
    mp, mo = meta

    def sym(suffix):
        return next(link.aot.text(s.name) for s in mo.symbols
                    if link.aot.text(s.name).endswith(suffix) and s.numberof_sections)

    infoname = sym('_284_aotInfo')
    info = link.aot.extract_symbol_bytes(mo, infoname, 168)
    digest = hashlib.sha1(full).digest()
    assert info[:20].hex() == compiled_report['compile_input_sha1'] and read64(info, 56) == count
    compiled = link.aot.extract_symbol_bytes(mo, sym('_abcBytes'), read64(info, 32))
    fresh = abcfmt.ABC(compiled)
    oldabcoff = link.file_offset(native, read64(native, INFO_OFFSET + 24))
    oldabclen = read64(native, INFO_OFFSET + 32)
    oldraw = native[oldabcoff:oldabcoff + oldabclen]
    assert sha(oldraw) == port['baseline_runtime_abc_sha256']
    old = abcfmt.ABC(oldraw)
    prepared = abcfmt.ABC(full)
    check_definitions(old, fresh, prepared)
    bymid = {b[0]: b for b in old.bodies}
    replace = {r['method_id'] for r in port['methods'] if r['strategy'] == 'replace'}
    for i, b in enumerate(fresh.bodies):
        if b[0] < OLD_COUNT:
            if b[0] not in replace:
                fresh.bodies[i] = copy.deepcopy(bymid[b[0]])
            else:
                assert (p.activation_traits(view(old), bymid[b[0]]) ==
                        p.activation_traits(view(fresh), b))
    runtime = fresh.serialize()
    # Runtime ABC is emitted with the linked carrier only.
    act_tail, act_section, act_start = activation_tail(mo, sym('_activationInfo'), NATIVE_COUNT, count)
    act_relocs = activation_relocations(mp, mo, act_section, act_start, len(act_tail))
    # Generated initHandlers are real executable functions with their own
    # relocations. Resolve them (and direct generated callees) before layout.
    generated = {row['symbol'] for row in act_relocs}
    all_defs = {link.aot.text(symbol.name): (path, obj)
                for path, obj in objects.items() for symbol in obj.symbols
                if symbol.numberof_sections}
    generated_names = {}
    pending = list(sorted(generated))
    while pending:
        name = pending.pop()
        if name in generated_names or any(row[0].symbol == name for row in funcs.values()):
            continue
        assert name in all_defs, ('missing generated initializer', name)
        path, obj = all_defs[name]
        key = -len(generated_names) - 1
        record = symbol_record(obj, path, name, key)
        generated_names[name] = key
        funcs[key] = record
        for row in record[-1]:
            target = row['symbol']
            if target in all_defs and target not in generated_names:
                method_match = re.search(r':(\d+):', target)
                if method_match and int(method_match.group(1)) < OLD_COUNT:
                    # Never recursively import an old method's temporary
                    # return stub. Its accepted native implementation stays.
                    continue
                target_path, target_obj = all_defs[target]
                symbol = next(s for s in target_obj.symbols if link.aot.text(s.name) == target and s.numberof_sections)
                if link.aot.find_section(target_obj, symbol).name == '__text':
                    pending.append(target)
    cursor = 0
    positions, constants2, cpos = {}, {}, {}
    for mid, (record, *_) in sorted(funcs.items()):
        positions[mid] = cursor
        cursor = link.aot.align(cursor + record.size, 16)
    for mid, (r, path, sec, syms, rows) in funcs.items():
        for row in rows:
            name = row['symbol']
            if name and name.startswith(('lCPI', '_exceptionDesc')) and (path, name) not in constants2:
                data = link.constant(objects[path], name, path)
                constants2[path, name] = data
                cpos[path, name] = cursor
                cursor = link.aot.align(cursor + len(data), 16)
    branch_keys = set()
    for mid, (r, path, sec, syms, rows) in funcs.items():
        addends = {x['source_address']: link.aot.sign_extend_24(x['raw'] & 0xffffff)
                   for x in rows if x['type'] == 10}
        branch_keys.update((row['symbol'], addends.get(row['source_address'], 0))
                           for row in rows if row['type'] == 2)
    veneer_positions = {}
    for key in sorted(branch_keys):
        veneer_positions[key] = cursor
        cursor += 16
    compiler_flags = link.aot.extract_symbol_bytes(mo, sym('_methodFlagsArr'), count * 4)
    abc_position = cursor
    flags_position = link.aot.align(abc_position + len(runtime), 16)
    code_size = flags_position + len(compiler_flags)
    patched, rx, header_end = extend(native, code_size)
    entry_bridges = []
    padding = {}
    for segment in link.segments(native)[3:-2]:
        at = segment['command']
        if struct.unpack_from('<ii', native, at + 56) != (5, 5):
            continue
        if struct.unpack_from('<I', native, at + 64)[0] != 1:
            continue
        used = struct.unpack_from('<Q', native, at + 112)[0]
        start = link.aot.align(used, 16)
        if start + 16 <= segment['fs']:
            assert not any(native[segment['off'] + start:segment['off'] + segment['fs']]), segment['name']
            padding[segment['name']] = [segment, start]

    def hook_entry(offset, address, target):
        via = target
        if not veneers.reachable(address, target):
            candidates = [r for r in entry_bridges
                          if r['target'] == target and veneers.reachable(address, r['address'])]
            if candidates:
                via = candidates[0]['address']
            else:
                for name, (segment, used) in padding.items():
                    va = segment['vm'] + used
                    if used + 16 <= segment['fs'] and veneers.reachable(address, va):
                        break
                else:
                    raise AssertionError(('No verified executable padding for entry bridge',
                                          hex(address)))
                bridge_offset = segment['off'] + used
                code = veneers.encode(va, target)
                assert not any(native[bridge_offset:bridge_offset + 16])
                patched[bridge_offset:bridge_offset + 16] = code
                padding[name][1] = used + 16
                struct.pack_into('<Q', patched, segment['command'] + 112, used + 16)
                entry_bridges.append({'segment': name, 'address': va,
                                      'file_offset': bridge_offset, 'target': target,
                                      'size': 16, 'sha256': sha(code)})
                via = va
        link.aot.write_unconditional_branch(patched, offset, address, via)
        return via

    helpers = {n: int(v['address'], 0) for n, v in
               fixed_json('runtime-helper-map.json')['symbols'].items()}
    helpers.update(link.aot.DEPENDENCY_AOT_INFOS)
    helpers[SYMBOL_STRICT_EQUALS] = link.aot.STRICT_EQUALS_VA
    extra = fixed_json('additional-helper.json')
    extra_off = link.file_offset(native, extra['address'], 32)
    assert native[extra_off:extra_off + 32].hex() == extra['native_bytes']
    helpers[extra['symbol']] = extra['address']
    for name, row in fixed_json('runtime-extra-map.json').items():
        helpers[name] = row['address']
    named = {r.symbol: rx['vm'] + positions[mid] for mid, (r, *_) in funcs.items()}
    named[infoname] = link.aot.IMAGE_BASE + INFO_OFFSET
    native_table = link.file_offset(native, read64(native, INFO_OFFSET + 48), OLD_COUNT * 8)
    retained_method_symbols = {}
    for obj in objects.values():
        for symbol in obj.symbols:
            name = link.aot.text(symbol.name)
            match = re.search(r':(\d+):', name)
            if match and int(match.group(1)) < OLD_COUNT and name not in named:
                retained_method_symbols[name] = read64(native, native_table + int(match.group(1)) * 8)
    named.update(retained_method_symbols)
    unknown = {row['symbol'] for r, path, sec, syms, rows in funcs.values() for row in rows
               if row['type'] != 10 and (path, row['symbol']) not in cpos
               and row['symbol'] not in named and row['symbol'] not in helpers}
    dump(out.parent / (out.name + '-symbol-analysis.json'), dict(
        unknown_symbols={str(name): sorted(mid for mid, value in funcs.items()
                                          if any(row['symbol'] == name for row in value[-1]))
                         for name in sorted(unknown, key=str)},
        new_activation_pointer_relocations=act_relocs,
        generated_initializers=generated_names))
    from runtime_symbols import derive, function as runtime_function, relocs as runtime_relocs  # type: ignore
    runtime_member = Path(runtime_stubs)
    assert sha(runtime_member.read_bytes()) == \
        '952f0c9ffe34f2e35eb434fdf0dd641d7ecd8baa6bf9d260e258d59e4ca1ecb8'

    def proof_at(name, offset):
        obj = link.lief.parse(str(runtime_member))
        sec, start, end = runtime_function(obj, name)
        code = bytes(sec.content)[start - sec.virtual_address:end - sec.virtual_address]
        rows = runtime_relocs(runtime_member, obj, sec, start, end)
        reloc = {row['offset'] for row in rows}
        assert offset >= 0 and offset + len(code) <= len(native)
        for at in range(0, len(code), 4):
            if at not in reloc:
                assert native[offset + at:offset + at + 4] == code[at:at + 4], (name, offset, at)
        return dict(address=link.aot.IMAGE_BASE + offset, file_offset=offset, size=len(code),
                    object=str(runtime_member), object_sha256=sha(runtime_member.read_bytes()),
                    native_bytes=native[offset:offset + 32].hex(), relocations=rows,
                    unrelocated_bytes_verified=len(code) - len(reloc) * 4,
                    fixed_offset_proof=True)

    runtime_proofs = {}
    for name in sorted(unknown):
        if re.fullmatch(r'_\d+-.+_\d+_aotInfo', name):
            runtime_proofs[name] = dependency_info(native, name, dependencies)
            continue
        try:
            runtime_proofs[name] = derive(runtime_member, name, native)
        except (AssertionError, StopIteration):
            if name == '__ZN8halfmoon5Stubs16do_abc_convert_sEPN7avmplus11MethodFrameEx':
                runtime_proofs[name] = proof_at(name, 0xA273CC)
            else:
                raise RuntimeError(('unresolved native runtime symbol', name,
                                    sorted(mid for mid, value in funcs.items()
                                           if any(row['symbol'] == name for row in value[-1])))) from None
    helpers.update({name: row['address'] for name, row in runtime_proofs.items()})
    functions, relocations, used_veneers = [], [], {}
    for mid, (r, path, sec, syms, rows) in sorted(funcs.items()):
        address = rx['vm'] + positions[mid]
        offset = rx['off'] + positions[mid]
        start = r.source_start - sec.virtual_address
        code = bytearray(bytes(sec.content)[start:start + r.size])
        addends = {x['source_address']: link.aot.sign_extend_24(x['raw'] & 0xffffff)
                   for x in rows if x['type'] == 10}
        for row in rows:
            typ, name, at = row['type'], row['symbol'], row['offset']
            pc = address + at
            if typ == 10:
                continue
            if (path, name) in cpos:
                target = rx['vm'] + cpos[path, name]
            elif name in named:
                target = named[name]
            elif name in helpers:
                target = helpers[name]
            else:
                raise RuntimeError(('unmapped native symbol', mid, name, typ))
            target += addends.get(row['source_address'], 0)
            branch_target = None
            if typ == 2:
                branch_target = target
                if not veneers.reachable(pc, target):
                    key = (name, addends.get(row['source_address'], 0))
                    branch_target = rx['vm'] + veneer_positions[key]
                    veneer_offset = rx['off'] + veneer_positions[key]
                    veneer_code = veneers.encode(branch_target, target)
                    patched[veneer_offset:veneer_offset + 16] = veneer_code
                    used_veneers[key] = dict(symbol=name, address=branch_target, target=target,
                                             file_offset=veneer_offset, size=16,
                                             sha256=sha(veneer_code))
                link.aot.patch_branch26(code, at, pc, branch_target)
            elif typ in (3, 5):
                link.aot.patch_adrp(code, at, pc, target)
            elif typ in (4, 6):
                link.aot.patch_pageoff12(code, at, target, relax_got_load=typ == 6)
            else:
                raise AssertionError((typ, name))
            relocations.append(dict(method=mid, offset=at, type=typ, symbol=name, pc=pc,
                                    target=target, branch_target=branch_target))
        patched[offset:offset + len(code)] = code
        functions.append(dict(method=mid, address=address, file_offset=offset,
                              size=len(code), sha256=sha(code)))
    for key, data in constants2.items():
        at = rx['off'] + cpos[key]
        patched[at:at + len(data)] = data
    activeva = read64(native, INFO_OFFSET + 48)
    activeoff = link.file_offset(native, activeva, NATIVE_COUNT * 8)
    assert read64(native, INFO_OFFSET + 56) == NATIVE_COUNT
    table = bytearray(native[activeoff:activeoff + NATIVE_COUNT * 8] +
                      bytes((count - NATIVE_COUNT) * 8))
    assert NATIVE_COUNT == OLD_COUNT
    activationva = read64(native, INFO_OFFSET + 88)
    activationoff = link.file_offset(native, activationva, NATIVE_COUNT * 16)
    activation_tail_bytes = act_tail
    for row in act_relocs:
        key = generated_names.get(row['symbol'])
        if key is None:
            key = next(mid for mid, value in funcs.items() if value[0].symbol == row['symbol'])
        assert read64(act_tail, row['offset']) == 0, 'activation pointer addend requires explicit handling'
        write64(activation_tail_bytes, row['offset'], rx['vm'] + positions[key])
    for at in range(8, len(activation_tail_bytes), 16):
        assert bool(read64(activation_tail_bytes, at)) == any(r['offset'] == at for r in act_relocs), \
            ('activation pointer missing relocation', at)
    segments = link.segments(native)
    writable = segments[15]
    assert writable['name'] == '__CNADTAB'
    assert writable['off'] <= activeoff and activeoff + count * 8 < activationoff
    assert activationoff + count * 16 <= writable['off'] + writable['fs']
    struct.pack_into('<Q', patched, writable['command'] + 112,
                     activationoff + count * 16 - writable['off'])
    assert not any(native[activeoff + NATIVE_COUNT * 8:activeoff + count * 8]), 'method tail is occupied'
    assert not any(native[activationoff + NATIVE_COUNT * 16:activationoff + count * 16]), \
        'activation tail is occupied'
    # The original table predates appended helpers. Its tail is unrelated
    # native data; only the active table contains IDs added by earlier ports.
    original_count = link.aot.MAIN_METHOD_COUNT
    legacy = link.aot.MAIN_METHOD_TABLE_OFFSET
    hooks, sites = [], []
    for mid in sorted(wanted):
        target = rx['vm'] + positions[mid]
        if mid < OLD_COUNT:
            oldva = read64(table, mid * 8)
            at = link.file_offset(native, oldva, 4)
            hook_entry(at, oldva, target)
            hooks.append(dict(method=mid, previous=oldva, target=target, offset=at))
            write64(patched, activeoff + mid * 8, target)
            sites.append(activeoff + mid * 8)
            if mid < original_count:
                legacyva = read64(native, legacy + mid * 8)
                if legacyva != oldva:
                    la = link.file_offset(native, legacyva, 4)
                    hook_entry(la, legacyva, target)
                    hooks.append(dict(method=mid, previous=legacyva, target=target, offset=la))
                write64(patched, legacy + mid * 8, target)
                sites.append(legacy + mid * 8)
        write64(table, mid * 8, target)
    for original_mid, compiled_mid in aliases.items():
        write64(table, original_mid * 8, rx['vm'] + positions[compiled_mid])
    for original, compiled_mid in sorted(redirects.items()):
        target = rx['vm'] + positions[compiled_mid]
        oldva = read64(table, original * 8)
        at = link.file_offset(native, oldva, 4)
        hook_entry(at, oldva, target)
        hooks.append(dict(method=original, compiled_method=compiled_mid, previous=oldva,
                          target=target, offset=at))
        write64(patched, activeoff + original * 8, target)
        sites.append(activeoff + original * 8)
        if original < original_count:
            legacyva = read64(native, legacy + original * 8)
            if legacyva != oldva:
                la = link.file_offset(native, legacyva, 4)
                hook_entry(la, legacyva, target)
                hooks.append(dict(method=original, compiled_method=compiled_mid,
                                  previous=legacyva, target=target, offset=la))
            write64(patched, legacy + original * 8, target)
            sites.append(legacy + original * 8)
    flags_offset = link.file_offset(native, read64(native, INFO_OFFSET + 64), OLD_COUNT * 4)
    for mid in wanted:
        if mid >= OLD_COUNT:
            continue
        assert native[flags_offset + mid * 4:flags_offset + mid * 4 + 4] == \
            compiler_flags[mid * 4:mid * 4 + 4], ('method flags', mid)
    rebased = {segments[si]['vm'] + off for si, off, typ in link.read_rebase(native)['entries'] if typ == 1}
    for location in sites + [INFO_OFFSET + 24, INFO_OFFSET + 64]:
        segment, = [s for s in segments if s['off'] <= location < s['off'] + s['fs']]
        assert segment['vm'] + location - segment['off'] in rebased, ('missing rebase', location)
    patched[rx['off'] + abc_position:rx['off'] + abc_position + len(runtime)] = runtime
    patched[rx['off'] + flags_position:rx['off'] + flags_position + len(compiler_flags)] = compiler_flags
    patched[INFO_OFFSET:INFO_OFFSET + 20] = digest
    for at, value in ((24, rx['vm'] + abc_position), (32, len(runtime)),
                      (56, count), (64, rx['vm'] + flags_position)):
        write64(patched, INFO_OFFSET + at, value)
    table_tail = bytes(table[NATIVE_COUNT * 8:])
    assert all(read64(table, mid * 8) for mid in range(NATIVE_COUNT, count))
    patched[activeoff + NATIVE_COUNT * 8:activeoff + count * 8] = table_tail
    patched[activationoff + NATIVE_COUNT * 16:activationoff + count * 16] = activation_tail_bytes
    new_entries = {(15, activeoff + mid * 8 - writable['off']) for mid in range(NATIVE_COUNT, count)}
    new_entries.update((15, activationoff + NATIVE_COUNT * 16 + row['offset'] - writable['off']) for row in act_relocs)
    rebases = add_rebases(patched, new_entries)
    newswf = link.aot.replace_main_swf_hash(swf, native[INFO_OFFSET:INFO_OFFSET + 20], digest)
    signing = assert_signable_layout(patched)
    signing_models = verify_signing_models(patched)
    origin = current_origin(patched)
    allowed = [(0, header_end), (INFO_OFFSET, INFO_OFFSET + 20),
               (INFO_OFFSET + 24, INFO_OFFSET + 40), (INFO_OFFSET + 56, INFO_OFFSET + 72),
               (activeoff + NATIVE_COUNT * 8, activeoff + count * 8),
               (activationoff + NATIVE_COUNT * 16, activationoff + count * 16)]
    allowed += [(h['offset'], h['offset'] + 4) for h in hooks]
    allowed += [(at, at + 8) for at in sites]
    allowed += [(r['file_offset'], r['file_offset'] + 16) for r in entry_bridges]
    old_prefix_end = link.segments(native)[-1]['off']
    prefix = bytearray(patched[:old_prefix_end])
    for begin, end in allowed:
        end = min(end, old_prefix_end)
        if begin >= end:
            continue
        prefix[begin:end] = native[begin:end]
    if prefix != native[:old_prefix_end]:
        diffs = [i for i, (x, y) in enumerate(zip(prefix, native[:old_prefix_end])) if x != y]
        ranges = []
        for at in diffs:
            if ranges and at == ranges[-1][1]:
                ranges[-1][1] = at + 1
            else:
                ranges.append([at, at + 1])
        raise AssertionError(('unexpected preexisting native change', len(diffs), ranges[:12]))

    out.mkdir(parents=True)
    (out / 'worldflipper').write_bytes(patched)
    (out / 'worldflipper_ios_release.swf').write_bytes(newswf)
    (out / 'runtime-stripped.abc').write_bytes(runtime)
    report = dict(status='linked_native_not_executed', source_ipa=reg,
                  prepared_report=str(prepared_report), prepared_report_sha256=sha(prepared_report.read_bytes()),
                  native_file=str(out / 'worldflipper'), swf_file=str(out / 'worldflipper_ios_release.swf'),
                  native_sha256=sha(patched), swf_sha256=sha(newswf),
                  runtime_abc_sha256=sha(runtime), full_abc_sha256=sha(full), full_abc_sha1=digest.hex(),
                  executable_extension=rx, functions=functions, relocations=relocations,
                  hooks=hooks, table_sites=sites, native_change_ranges=allowed,
                  old_active_table_offset=activeoff, veneers=list(used_veneers.values()),
                  total_methods=count, original_methods=OLD_COUNT, new_methods=count - OLD_COUNT,
                  abc_position=abc_position, flags_position=flags_position,
                  rebases=rebases, signing_layout=signing, signing_models=signing_models, origin=origin,
                  runtime_helper_proofs=runtime_proofs, old_native_count=NATIVE_COUNT,
                  activation_offset=activationoff, activation_pointer_relocations=act_relocs,
                  generated_initializers=generated_names, entry_bridges=entry_bridges,
                  retained_native_method_symbols=len(retained_method_symbols),
                  native_aliases=aliases, native_executed=False, device_tested=False)
    report['retained_entry_aliases'] = shared_entries
    dump(out / 'link-report.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'native_sha256', 'new_methods', 'origin')}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--runtime-stubs', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--compiled', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.prepared, args.compiled, args.out, runtime_stubs=args.runtime_stubs, dependencies=args.dependencies)


if __name__ == '__main__':
    main()
