"""Independent artifact regression for the R3 public iOS bootstrap endpoint."""
import argparse
import copy
import hashlib
import json
import plistlib
import struct
import zlib
import zipfile
from pathlib import Path

import public_endpoint as p
from prepare import abcfmt, INFO_OFFSET
from build_native import commands, read_rebase
from macho_signing_layout import assert_signable_layout, linkedit_ranges
from test_signing_layout import replace_signature_tail


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', type=Path, default=p.DEFAULT_REPORT)
    args = parser.parse_args()
    report = json.loads((args.report_dir / 'build-report.json').read_text('utf8'))
    assert p.sha(Path(report['input_ipa']).read_bytes()) == p.R2_SHA
    assert p.sha(Path(report['ipa']).read_bytes()) == report['ipa_sha256']
    with zipfile.ZipFile(report['input_ipa']) as old, zipfile.ZipFile(report['ipa']) as new:
        assert old.namelist() == new.namelist() and old.comment == new.comment
        differences = []
        for a, b in zip(old.infolist(), new.infolist()):
            for key in ('filename', 'date_time', 'compress_type', 'comment', 'extra', 'create_system', 'external_attr'):
                assert getattr(a, key) == getattr(b, key), (a.filename, key)
            if old.read(a) != new.read(b): differences.append(a.filename)
        assert set(differences) == {p.NATIVE_MEMBER, p.SWF_MEMBER}
        assert new.testzip() is None
        before, after = old.read(p.NATIVE_MEMBER), new.read(p.NATIVE_MEMBER)
        oldswf, newswf = old.read(p.SWF_MEMBER), new.read(p.SWF_MEMBER)
        identity = plistlib.loads(new.read('Payload/worldflipper.app/Info.plist'))
        assert identity['CFBundleIdentifier'] == 'com.kulo.wf'
        assert identity['NSAppTransportSecurity']['NSAllowsArbitraryLoads'] is True
        count = len(new.namelist())
    assert p.sha(before) == p.R2_NATIVE_SHA and p.sha(after) == report['native_sha256']
    assert len(before) == len(after) and commands(before) == commands(after)
    # Decode the two real ARM64 constant loads independently of the builder.
    import capstone
    dis = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    _, _, r = p.runtime_abc(after)
    loads = []
    for site in (p.SCHEME_SITE, p.HOST_SITE):
        inst, = list(dis.disasm(after[site:site + 4], 0x100000000 + site))
        assert inst.mnemonic == 'mov' and inst.op_str.startswith('w1, #')
        loads.append(r.s(int(inst.op_str.split('#')[1], 0)))
    assert loads == ['http', '175.178.160.158']
    # This guard must reject the actual faulty artifact, not just a mock string.
    try:
        p.require_public_endpoint(before)
    except AssertionError as error:
        assert 'pre-query API' in str(error)
    else:
        raise AssertionError('R2 default-official endpoint was not detected')
    assert p.require_public_endpoint(after) == report['constructor_origin']
    offset, old_size, a = p.runtime_abc(before)
    new_offset, new_size, b = p.runtime_abc(after)
    assert offset == new_offset and new_size < old_size
    assert not any(after[offset + new_size:offset + old_size])
    full_before = Path(report['input_full_abc']).read_bytes()
    full_after = Path(report['full_abc']).read_bytes()
    assert p.sha(full_before) == p.FULL_SHA and p.sha(full_after) == report['full_abc_sha256']
    f, g = abcfmt.ABC(full_before), abcfmt.ABC(full_after)
    for left, right in ((a, b), (f, g)):
        assert len(left.methods) == len(right.methods) == 101182
        assert [i for i, (x, y) in enumerate(zip(left.strings, right.strings)) if x != y] == [p.HOST_INDEX]
        restored = copy.deepcopy(right)
        restored.strings[p.HOST_INDEX] = left.strings[p.HOST_INDEX]
        assert restored.serialize() == left.serialize(), 'only the host pool entry may change'
    old_digest, digest = before[INFO_OFFSET:INFO_OFFSET + 20], after[INFO_OFFSET:INFO_OFFSET + 20]
    assert digest == hashlib.sha1(full_after).digest()
    plain = lambda data: data[:8] + zlib.decompress(data[8:]) if data[:3] == b'CWS' else data
    left, right = plain(oldswf), plain(newswf)
    assert left.count(b'\0' * 4 + old_digest) == 1
    assert left.replace(b'\0' * 4 + old_digest, b'\0' * 4 + digest) == right
    # Reconstruct the allowed ranges ourselves; protect every unrelated byte,
    # including storage, all native methods, method tables, and old segments.
    ranges = [(p.SCHEME_SITE, p.SCHEME_SITE + 4), (offset, offset + old_size),
              (INFO_OFFSET, INFO_OFFSET + 20), (INFO_OFFSET + 32, INFO_OFFSET + 40)]
    restored_native = bytearray(after)
    for start, end in ranges: restored_native[start:end] = before[start:end]
    assert restored_native == before
    assert assert_signable_layout(before) == assert_signable_layout(after)
    expected = read_rebase(before)['entries']
    assert read_rebase(after)['entries'] == expected
    for size in (0x80000, 0x200000, 0x400000):
        signed_model = replace_signature_tail(after, size, use_ldid=True)
        assert_signable_layout(signed_model)
        assert read_rebase(signed_model)['entries'] == expected
        for row in linkedit_ranges(after):
            start, end = row['offset'], row['offset'] + row['size']
            assert signed_model[start:end] == after[start:end]
    result = dict(status='offline_verified_pending_device_test', ipa=report['ipa'],
                  ipa_sha256=report['ipa_sha256'], constructor_origin='http://175.178.160.158',
                  zip_members_checked=count, only_native_and_swf_changed=True,
                  r2_endpoint_regression_detected=True, arm64_constant_loads_verified=True,
                  all_other_101182_method_bodies_and_native_code_preserved=True,
                  storage_and_account_protocol_preserved=True, all_macho_headers_unchanged=True,
                  r2_rebases_preserved=True, ldid_signature_models_passed=3,
                  full_abc_identity_verified=True, actual_signing_performed=False, device_tested=False)
    (args.report_dir / 'verification-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
