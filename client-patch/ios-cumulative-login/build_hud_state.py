"""Apply the HUD slot repair onto the exact R3 public IPA, unsigned."""
import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path

import hud_state_layout as h
from prepare import INFO_OFFSET, LEGACY, abcfmt, dump, sha
from public_endpoint import NATIVE_MEMBER, SWF_MEMBER, require_public_endpoint, runtime_abc
from build_native import (aot, common, commands, segments, segment_command,
                          file_offset, lief, constant, read_rebase)
from macho_signing_layout import assert_signable_layout


def add_code_segment(native, payload_size):
    """Insert RX storage immediately before LINKEDIT; retain its byte stream."""
    old = segments(native); link = old[-1]
    assert link['name'] == '__LINKEDIT' and len(old) == 8
    assert all(s < len(old) - 1 for s, _, _ in read_rebase(native)['entries'])
    growth = aot.align(payload_size, 0x4000)
    offset_fields = {2: [8, 16], 0xb: [32, 40, 48, 56, 64, 72],
                     0x22: [8, 16, 24, 32, 40], 0x80000022: [8, 16, 24, 32, 40]}
    blob_commands = {0x1d, 0x1e, 0x26, 0x29, 0x2b, 0x2e, 0x80000033}
    rebuilt = []
    for _, cmd, raw in commands(native):
        b = bytearray(raw)
        assert cmd != 0x80000034, 'chained fixups need a separate audit'
        if cmd == 0x19 and raw[8:24].rstrip(b'\0') == b'__LINKEDIT':
            rebuilt.append(segment_command('__HUDSTATE', link['vm'], link['off'],
                                           growth, payload_size, 5))
            struct.pack_into('<Q', b, 24, link['vm'] + growth)
            struct.pack_into('<Q', b, 40, link['off'] + growth)
        for at in offset_fields.get(cmd, [8] if cmd in blob_commands else []):
            value = struct.unpack_from('<I', b, at)[0]
            if value:
                assert value >= link['off']
                struct.pack_into('<I', b, at, value + growth)
        rebuilt.append(bytes(b))
    header = b''.join(rebuilt); old_end = 32 + sum(len(b) for _, _, b in commands(native))
    new_end = 32 + len(header)
    assert not any(native[old_end:new_end]), 'no free load command padding'
    result = bytearray(native[:link['off']] + bytes(growth) + native[link['off']:])
    struct.pack_into('<II', result, 16, len(rebuilt), len(header)); result[32:new_end] = header
    return result, dict(vm=link['vm'], off=link['off'], size=growth,
                        header_end=new_end, payload_size=payload_size)


def native_method(work):
    found = []
    report = json.loads((work / 'compile-r4-report.json').read_text('utf8'))
    for p in Path(report['directory']).glob('cumulative*.o'):
        obj = lief.parse(str(p))
        if not any(f':{h.METHOD}:' in aot.text(s.name) and s.numberof_sections for s in obj.symbols): continue
        assert sha(p.read_bytes()) == next(r['sha256'] for r in report['objects'] if r['name'] == p.name)
        sec, syms, records = aot.parse_object_functions(obj, [h.METHOD]); record, = records
        rows = aot.parse_relocations(p, sec, syms, record)
        found.append((p, obj, sec, record, rows))
    assert len(found) == 1
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=h.WORK)
    parser.add_argument('--output-ipa', type=Path, default=h.OUTPUT)
    args = parser.parse_args(); work = args.work
    assert not args.output_ipa.exists() and not (work / 'build-report.json').exists()
    assert sha(h.R3.read_bytes()) == h.R3_SHA
    assert sha(h.FULL.read_bytes()) == h.FULL_SHA
    with zipfile.ZipFile(h.R3) as z: native, swf = z.read(NATIVE_MEMBER), z.read(SWF_MEMBER)
    assert sha(native) == h.NATIVE_SHA
    require_public_endpoint(native); assert_signable_layout(native)
    full = (work / 'cumulative-full-r4.abc').read_bytes()
    assert sha(full) == json.loads((work / 'port.json').read_text('utf8'))['full_abc_sha256']
    path, obj, sec, record, rows = native_method(work)
    start = record.source_start - sec.virtual_address
    code = bytearray(bytes(sec.content)[start:start + record.size])
    constants = {}; cursor = aot.align(len(code), 16)
    for row in rows:
        name = row['symbol']
        if name and name.startswith(('lCPI', '_exceptionDesc')) and name not in constants:
            raw = constant(obj, name, path); constants[name] = (cursor, raw)
            cursor = aot.align(cursor + len(raw), 16)
    result, added = add_code_segment(native, cursor)
    helpers = {name: int(v['address'], 0) for name, v in json.loads((LEGACY / 'runtime-helper-map.json').read_text('utf8'))['symbols'].items()}
    addends = {r['source_address']: aot.sign_extend_24(r['raw'] & 0xffffff) for r in rows if r['type'] == 10}
    resolved = []
    for row in rows:
        typ, name, at = row['type'], row['symbol'], row['offset']
        if typ == 10: continue
        target = added['vm'] + constants[name][0] if name in constants else helpers[name]
        target += addends.get(row['source_address'], 0); pc = added['vm'] + at
        if typ == 2: aot.patch_branch26(code, at, pc, target)
        elif typ in (3, 5): aot.patch_adrp(code, at, pc, target)
        elif typ in (4, 6): aot.patch_pageoff12(code, at, target, relax_got_load=typ == 6)
        else: raise AssertionError(('unsupported relocation', typ, name))
        resolved.append(dict(offset=at, type=typ, symbol=name, pc=pc, target=target))
    result[added['off']:added['off'] + len(code)] = code
    for at, data in constants.values(): result[added['off'] + at:added['off'] + at + len(data)] = data
    abc_off, old_size, runtime = runtime_abc(native)
    h.correct_traits(runtime); new_runtime = runtime.serialize()
    # R3 has 58 bytes of verified zero alignment padding after its runtime ABC.
    end = abc_off + len(new_runtime)
    rx = next(s for s in segments(native) if s['name'] == '__CNUPDATE')
    assert end <= rx['off'] + rx['fs']
    assert not any(native[abc_off + old_size:end])
    result[abc_off:end] = new_runtime
    digest = hashlib.sha1(full).digest()
    result[INFO_OFFSET:INFO_OFFSET + 20] = digest
    struct.pack_into('<Q', result, INFO_OFFSET + 32, len(new_runtime))
    table = struct.unpack_from('<Q', native, INFO_OFFSET + 48)[0]
    sites = [0x62c0780 + h.METHOD * 8, file_offset(native, table) + h.METHOD * 8]
    old_target = struct.unpack_from('<Q', native, sites[0])[0]
    assert all(struct.unpack_from('<Q', native, at)[0] == old_target for at in sites)
    assert old_target == 0x107353230
    for at in sites: struct.pack_into('<Q', result, at, added['vm'])
    # Both historical direct entry routes must reach the corrected update.
    hooks = [0x102acac84, old_target]
    for address in hooks:
        at = file_offset(native, address, 4)
        # Relocation patching preserves the opcode; a function prologue must
        # first become B, otherwise its STP high bits would survive.
        struct.pack_into('<I', result, at, 0x14000000)
        aot.patch_branch26(result, at, address, added['vm'])
    new_swf = aot.replace_main_swf_hash(swf, native[INFO_OFFSET:INFO_OFFSET + 20], digest)
    assert read_rebase(result)['entries'] == read_rebase(native)['entries']
    require_public_endpoint(result); signing = assert_signable_layout(result)
    assert result[added['off'] + added['size']:] == native[added['off']:]
    changes = [(0, added['header_end']), (abc_off, end), (INFO_OFFSET, INFO_OFFSET + 20),
               (INFO_OFFSET + 32, INFO_OFFSET + 40)] + [(at, at + 8) for at in sites]
    changes += [(file_offset(native, address, 4), file_offset(native, address, 4) + 4) for address in hooks]
    restored = bytearray(result[:added['off']] + result[added['off'] + added['size']:])
    for begin, end in changes: restored[begin:end] = native[begin:end]
    assert restored == native, 'unexpected cumulative native byte change'
    args.output_ipa.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(h.R3) as left, zipfile.ZipFile(args.output_ipa, 'w', allowZip64=True) as right:
        for item in left.infolist():
            data = result if item.filename == NATIVE_MEMBER else new_swf if item.filename == SWF_MEMBER else left.read(item)
            right.writestr(common.clone_zipinfo(item), data)
        right.comment = left.comment
    report = dict(status='unsigned_pending_independent_verification', input_ipa=str(h.R3),
                  input_ipa_sha256=h.R3_SHA, ipa=str(args.output_ipa), ipa_sha256=sha(args.output_ipa.read_bytes()),
                  native_sha256=sha(result), swf_sha256=sha(new_swf), full_abc=str(work / 'cumulative-full-r4.abc'),
                  full_abc_sha256=sha(full), full_abc_sha1=digest.hex(), segment=added,
                  method=h.METHOD, function_size=len(code), function_sha256=sha(code),
                  object=str(path), object_sha256=sha(path.read_bytes()), relocations=resolved,
                  constants={name: dict(offset=at, hex=data.hex()) for name, (at, data) in constants.items()},
                  native_change_ranges=changes, table_sites=sites, hooks=hooks,
                  runtime_abc_offset=abc_off, old_runtime_size=old_size, runtime_abc_size=len(new_runtime),
                  signing_layout=signing, origin=require_public_endpoint(result),
                  save_impact='none; transient per-battle voice counters only',
                  desktop_air_run=False, actual_signing_performed=False, device_tested=False)
    dump(work / 'build-report.json', report)
    args.output_ipa.with_suffix('.ipa.sha256').write_text(report['ipa_sha256'] + '  ' + args.output_ipa.name + '\n', 'utf8')
    print(json.dumps({k: report[k] for k in ('status', 'ipa', 'ipa_sha256', 'function_size', 'origin')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
