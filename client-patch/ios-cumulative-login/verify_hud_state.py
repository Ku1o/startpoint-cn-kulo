"""Read back the R4 IPA, including native field loads and old-R3 regression."""
import argparse
import copy
import hashlib
import json
import plistlib
import struct
import zlib
import zipfile

import hud_state_layout as h
from prepare import INFO_OFFSET, abcfmt, asm, dump, sha, freeze
from public_endpoint import NATIVE_MEMBER, SWF_MEMBER, runtime_abc, require_public_endpoint
from build_native import commands, segments, file_offset
from macho_signing_layout import assert_signable_layout, linkedit_ranges
from test_signing_layout import replace_signature_tail
from build_native import read_rebase
import capstone


def inspect_traits(old, new):
    restored = copy.deepcopy(new)
    left = h.hud_traits(old); right = h.hud_traits(restored)
    names = []
    for before, after in zip(left, right):
        if old.mn_name(before.name) not in h.COUNTERS:
            assert freeze(before) == freeze(after); continue
        assert new.mn_name(after.data[2]) == 'Number'
        assert after.data[4] == 6 and new.doubles[after.data[3]] == 0.0
        after.data = copy.deepcopy(before.data); names.append(old.mn_name(before.name))
    assert tuple(names) == h.COUNTERS
    return restored


def inspect_body(before, after):
    """Undo only the five explicit numeric-read coercions and rebase branches."""
    old = next(b for b in before.bodies if b[0] == h.METHOD)
    new = next(b for b in after.bodies if b[0] == h.METHOD)
    ins = asm.decode(new[5]); stripped = []; mapping = {}; removed = []
    skip = False
    for i, x in enumerate(ins):
        if skip: skip = False; removed.append(i); continue
        mapping[i] = len(stripped); stripped.append(copy.deepcopy(x))
        if x.op == 0x66 and after.mn_name(x.args[0]) in h.COUNTERS:
            assert ins[i + 1].op == 0x73; skip = True
    assert len(removed) == 5
    mapping[len(ins)] = len(stripped)
    for x in stripped:
        if x.target is not None: x.target = mapping[x.target]
        if x.default is not None: x.default = mapping[x.default]
        if x.cases is not None: x.cases = [mapping[t] for t in x.cases]
    new[5] = asm.encode(stripped)[0]
    assert freeze(new) == freeze(old), 'voice behavior or control flow changed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=h.Path, default=h.WORK)
    args = parser.parse_args(); work = args.work
    report = json.loads((work / 'build-report.json').read_text('utf8'))
    assert sha(h.R3.read_bytes()) == h.R3_SHA
    assert sha(h.Path(report['ipa']).read_bytes()) == report['ipa_sha256']
    with zipfile.ZipFile(h.R3) as left, zipfile.ZipFile(report['ipa']) as right:
        assert left.namelist() == right.namelist() and left.comment == right.comment
        changed = []
        for a, b in zip(left.infolist(), right.infolist()):
            for name in ('filename', 'date_time', 'compress_type', 'comment', 'extra', 'create_system', 'external_attr'):
                assert getattr(a, name) == getattr(b, name), (a.filename, name)
            if left.read(a) != right.read(b): changed.append(a.filename)
        assert set(changed) == {NATIVE_MEMBER, SWF_MEMBER} and right.testzip() is None
        before, after = left.read(NATIVE_MEMBER), right.read(NATIVE_MEMBER)
        old_swf, swf = left.read(SWF_MEMBER), right.read(SWF_MEMBER)
        identity = plistlib.loads(right.read('Payload/worldflipper.app/Info.plist'))
        members = len(right.namelist())
    assert sha(before) == h.NATIVE_SHA and sha(after) == report['native_sha256']
    assert identity['CFBundleIdentifier'] == 'com.kulo.wf'
    assert identity['CFBundleShortVersionString'] == '1.8.4' and identity['CFBundleVersion'] == '1.8.46'
    assert identity['NSAppTransportSecurity']['NSAllowsArbitraryLoads']
    assert require_public_endpoint(after) == 'http://175.178.160.158'
    segs, old_segs = segments(after), segments(before)
    assert [s['name'] for s in segs] == [s['name'] for s in old_segs[:-1]] + ['__HUDSTATE', '__LINKEDIT']
    new_seg, new_link, old_link = segs[-2], segs[-1], old_segs[-1]
    growth = new_seg['fs']; assert growth == 0x4000
    assert new_seg['vm'] == old_link['vm'] and new_seg['off'] == old_link['off']
    assert new_link['vm'] == old_link['vm'] + growth and new_link['off'] == old_link['off'] + growth
    assert after[new_link['off']:] == before[old_link['off']:]
    for a, b in zip(old_segs[:-1], segs[:-2]): assert a == b
    for a, b in zip(segs, segs[1:]): assert a['vm'] + a['vs'] <= b['vm']
    for _, cmd, raw in commands(after):
        if cmd == 0x19:
            assert struct.unpack_from('<ii', raw, 56) != (7, 7)
            if raw[8:24].rstrip(b'\0') == b'__HUDSTATE': assert struct.unpack_from('<ii', raw, 56) == (5, 5)
    # Validate every old load command, allowing only its LINKEDIT offset fields.
    actual = [(cmd, raw) for _, cmd, raw in commands(after)
              if not (cmd == 0x19 and raw[8:24].rstrip(b'\0') == b'__HUDSTATE')]
    for (_, cmd, raw), (new_cmd, new_raw) in zip(commands(before), actual):
        assert cmd == new_cmd; restored = bytearray(new_raw)
        fields = {2: [8, 16], 0xb: [32, 40, 48, 56, 64, 72],
                  0x22: [8, 16, 24, 32, 40], 0x80000022: [8, 16, 24, 32, 40]}
        blobs = {0x1d, 0x1e, 0x26, 0x29, 0x2b, 0x2e, 0x80000033}
        for at in fields.get(cmd, [8] if cmd in blobs else []):
            old_value, = struct.unpack_from('<I', raw, at); value, = struct.unpack_from('<I', restored, at)
            assert value == old_value + growth if old_value else value == 0
            struct.pack_into('<I', restored, at, old_value)
        if cmd == 0x19 and raw[8:24].rstrip(b'\0') == b'__LINKEDIT':
            for at in (24, 40): struct.pack_into('<Q', restored, at, struct.unpack_from('<Q', restored, at)[0] - growth)
        assert bytes(restored) == raw
    off, old_size, a = runtime_abc(before); new_off, new_size, b = runtime_abc(after)
    assert off == new_off and new_size == old_size + 3
    restored_abc = inspect_traits(a, b)
    assert restored_abc.serialize() == a.serialize(), 'unexpected runtime metadata/body changes'
    full = h.Path(report['full_abc']).read_bytes()
    f, g = abcfmt.ABC(h.FULL.read_bytes()), abcfmt.ABC(full)
    restored_full = inspect_traits(f, g); inspect_body(f, restored_full)
    assert restored_full.serialize() == f.serialize()
    original = {name: offset for name, offset in h.slot_offsets(g).items() if name not in h.COUNTERS}
    assert original == {'prevSkillPointCycle': 0x28, 'viewOrder': 0x30,
                        'playheadHealthPointGaugeGlowAnimation': 0x38, 'member': 0x40,
                        'featuresPermit': 0x48, 'features': 0x50, 'effectManager': 0x58, 'character': 0x60}
    r3_offsets = h.slot_offsets(f)
    assert all(r3_offsets[n] == offset + (0 if n == 'prevSkillPointCycle' else 8) for n, offset in original.items())
    digest = hashlib.sha1(full).digest(); assert after[INFO_OFFSET:INFO_OFFSET + 20] == digest
    plain = lambda data: data[:8] + zlib.decompress(data[8:]) if data[:3] == b'CWS' else data
    old_digest = before[INFO_OFFSET:INFO_OFFSET + 20]
    assert plain(old_swf).count(b'\0' * 4 + old_digest) == 1
    assert plain(old_swf).replace(b'\0' * 4 + old_digest, b'\0' * 4 + digest) == plain(swf)
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    def decode(pc, size):
        at = file_offset(after, pc, size); return list(md.disasm(after[at:at + size], pc))
    def branch(pc):
        instruction, = decode(pc, 4); assert instruction.mnemonic in ('b', 'bl')
        return int(instruction.op_str.removeprefix('#'), 16)
    assert branch(0x102acac84) == branch(0x107353230) == new_seg['vm']
    fn = decode(new_seg['vm'], report['function_size'])
    assert sum(i.size for i in fn) == report['function_size'] == 2988
    assert any(i.mnemonic == 'ldr' and i.op_str == 'x8, [x21, #0x48]' for i in fn)
    assert {i.op_str for i in fn if i.mnemonic == 'ldr' and i.op_str.startswith('d0, [x21,')} == {'d0, [x21, #0x68]', 'd0, [x21, #0x70]', 'd0, [x21, #0x78]'}
    run, = decode(0x102aca980, 4); assert (run.mnemonic, run.op_str) == ('ldr', 'x8, [x22, #0x48]')
    # A focused heap model of the logged first dereference: old constructor
    # writes member at 0x40; gear injection follows runtime trait locations.
    def run_first_read(layout):
        heap = bytearray(128); struct.pack_into('<Q', heap, 0x40, 0x12340000)
        struct.pack_into('<Q', heap, layout['featuresPermit'], 0x56780000)
        return struct.unpack_from('<Q', heap, 0x48)[0]
    assert run_first_read(r3_offsets) == 0 and run_first_read(h.slot_offsets(g)) == 0x56780000
    for r in report['relocations']:
        pc, target, typ = r['pc'], r['target'], r['type']
        word, = struct.unpack_from('<I', after, file_offset(after, pc, 4))
        if typ == 2: assert branch(pc) == target
        elif typ in (3, 5):
            assert word & 0x9f000000 == 0x90000000
            imm = ((word >> 29) & 3) | (((word >> 5) & 0x7ffff) << 2)
            if imm & (1 << 20): imm -= 1 << 21
            assert (pc & ~0xfff) + (imm << 12) == target & ~0xfff
        elif typ in (4, 6):
            value = (word >> 10) & 0xfff
            if word & 0x7f000000 == 0x11000000: assert value == target & 0xfff
            else: assert word & 0x3b000000 == 0x39000000 and value << (word >> 30) == target & 0xfff
        else: raise AssertionError(('unverified relocation', typ))
    old_table = file_offset(before, struct.unpack_from('<Q', before, INFO_OFFSET + 48)[0])
    table = file_offset(after, struct.unpack_from('<Q', after, INFO_OFFSET + 48)[0])
    count = struct.unpack_from('<Q', after, INFO_OFFSET + 56)[0]; assert count == 101182
    for mid in range(count):
        x, = struct.unpack_from('<Q', before, old_table + mid * 8)
        y, = struct.unpack_from('<Q', after, table + mid * 8)
        assert y == (new_seg['vm'] if mid == h.METHOD else x)
        if mid < 101071: assert struct.unpack_from('<Q', after, 0x62c0780 + mid * 8)[0] == y
    header_end = 32 + struct.unpack_from('<I', after, 20)[0]
    ranges = [(0, header_end), (off, off + new_size), (INFO_OFFSET, INFO_OFFSET + 20),
              (INFO_OFFSET + 32, INFO_OFFSET + 40), (0x2acac84, 0x2acac88),
              (file_offset(before, 0x107353230), file_offset(before, 0x107353230) + 4)]
    ranges += [(t + h.METHOD * 8, t + h.METHOD * 8 + 8) for t in (0x62c0780, old_table)]
    restored_native = bytearray(after[:new_seg['off']] + after[new_seg['off'] + growth:])
    for start, end in ranges: restored_native[start:end] = before[start:end]
    assert restored_native == before, 'unrelated native code or data changed'
    expected = read_rebase(before)['entries']; assert read_rebase(after)['entries'] == expected
    signing = assert_signable_layout(after)
    for size in (0x80000, 0x200000, 0x400000):
        model = replace_signature_tail(after, size, use_ldid=True)
        assert_signable_layout(model); assert read_rebase(model)['entries'] == expected
        for r in linkedit_ranges(after):
            start, end = r['offset'], r['offset'] + r['size']; assert model[start:end] == after[start:end]
    result = dict(status='offline_verified_pending_device_test', ipa=report['ipa'], ipa_sha256=report['ipa_sha256'],
                  zip_members_checked=members, only_native_and_swf_changed=True,
                  r3_hud_slot_regression_detected=True, original_hud_offsets_restored=original,
                  actual_old_run_and_new_update_loads_verified=True, modeled_first_dereference_passed=True,
                  voice_control_flow_and_round_robin_preserved=True, all_other_methods_preserved=count - 1,
                  native_relocations_checked=len(report['relocations']), r2_rebases_preserved=True,
                  ldid_signature_models_passed=3, initial_public_origin=require_public_endpoint(after),
                  save_impact='none', desktop_air_run=False, actual_signing_performed=False, device_tested=False)
    dump(work / 'verification-report.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
