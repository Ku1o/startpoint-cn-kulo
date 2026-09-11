"""Pin iOS's pre-version-query API to the public server, preserving R2 code.

The title login panel captures DevConfig before the asynchronous version query
can replace it. R2 retained the official constructor's HTTPS/host defaults.
Change only that constructor's protocol selection and its host pool entry.
No AIR runtime, compiler, installer, signing tool, or account request is run.
"""
import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path

from prepare import abcfmt, INFO_OFFSET
from build_native import file_offset, aot, common
from macho_signing_layout import assert_signable_layout

R2 = Path(r'F:\codex\ios-artifacts\StarPoint-iOS-1.8.4-login-abyss-lens-trollstore-fix-r2-20260911-unsigned.ipa')
R2_SHA = '171f0eb1d1671c9684c1ee9829af4b7f29a9ccc7481ec42144743c51cc2e6d7c'
R2_NATIVE_SHA = 'ae47dc3f1bcdf419476cc7e54ddf24aa5819f055b9892d33e8ede3965c2f5824'
FULL = Path(r'F:\codex\ios-artifacts\login-abyss-lens-20260911\cumulative-full-r8.abc')
FULL_SHA = 'b3d4c1e7aea35df9f50bf080d201f7f84de1a0ecd0943359de25d399b7dbef40'
DEFAULT_OUTPUT = Path(r'F:\codex\ios-artifacts\StarPoint-iOS-1.8.4-login-abyss-lens-public-fix-r3-20260911-unsigned.ipa')
DEFAULT_REPORT = Path(r'F:\codex\work\ios-public-endpoint-fix-r3-20260911\output')
NATIVE_MEMBER = 'Payload/worldflipper.app/worldflipper'
SWF_MEMBER = 'Payload/worldflipper.app/worldflipper_ios_release.swf'
SCHEME_SITE = 0x33d08a0
HOST_SITE = 0x33d08b0
HTTPS_INDEX = 0x39ad
HOST_INDEX = 0x39ae
HTTP_INDEX = 33074
OFFICIAL_HOST = 'shijtswygamegf.leiting.com'
# No explicit :80: exactly match the cloud version response, so the remembered
# account namespace and header matching do not change after the query finishes.
PUBLIC_HOST = '175.178.160.158'
PUBLIC_ORIGIN = 'http://' + PUBLIC_HOST


def sha(data):
    return hashlib.sha256(data).hexdigest()


def runtime_abc(native):
    pointer, size = struct.unpack_from('<QQ', native, INFO_OFFSET + 24)
    offset = file_offset(native, pointer, size)
    return offset, size, abcfmt.ABC(native[offset:offset + size])


def mov_w1(index):
    assert 0 <= index <= 0xffff
    return struct.pack('<I', 0x52800001 | (index << 5))


def constructor_origin(native):
    _, _, abc = runtime_abc(native)
    values = []
    for site in (SCHEME_SITE, HOST_SITE):
        word = struct.unpack_from('<I', native, site)[0]
        assert word & 0xffe0001f == 0x52800001, 'expected MOVZ W1, imm16'
        values.append(abc.s((word >> 5) & 0xffff))
    return values[0] + '://' + values[1]


def require_public_endpoint(native):
    origin = constructor_origin(native)
    assert origin == PUBLIC_ORIGIN, ('pre-query API still targets another server', origin)
    return origin


def patch(native, full_bytes, swf):
    assert sha(native) == R2_NATIVE_SHA, 'exact R2 native required'
    assert sha(full_bytes) == FULL_SHA, 'exact cumulative full ABC required'
    assert native[INFO_OFFSET:INFO_OFFSET + 20] == hashlib.sha1(full_bytes).digest()
    assert constructor_origin(native) == 'https://' + OFFICIAL_HOST
    assert native[SCHEME_SITE:SCHEME_SITE + 4] == mov_w1(HTTPS_INDEX)
    assert native[HOST_SITE:HOST_SITE + 4] == mov_w1(HOST_INDEX)
    assert_signable_layout(native)
    offset, old_size, runtime = runtime_abc(native)
    full = abcfmt.ABC(full_bytes)
    assert full.serialize() == full_bytes, 'full ABC must round-trip exactly'
    assert runtime.serialize() == native[offset:offset + old_size]
    for abc in (full, runtime):
        assert abc.s(HTTP_INDEX) == 'http'
        assert abc.s(HTTPS_INDEX) == 'https'
        assert abc.s(HOST_INDEX) == OFFICIAL_HOST
        assert sum(s == OFFICIAL_HOST.encode() for s in abc.strings) == 1
        abc.strings[HOST_INDEX] = PUBLIC_HOST.encode()
    new_full, new_runtime = full.serialize(), runtime.serialize()
    assert len(new_runtime) <= old_size, 'this patch cannot grow the runtime allocation'
    result = bytearray(native)
    result[SCHEME_SITE:SCHEME_SITE + 4] = mov_w1(HTTP_INDEX)
    result[offset:offset + old_size] = new_runtime + bytes(old_size - len(new_runtime))
    digest = hashlib.sha1(new_full).digest()
    result[INFO_OFFSET:INFO_OFFSET + 20] = digest
    struct.pack_into('<Q', result, INFO_OFFSET + 32, len(new_runtime))
    new_swf = aot.replace_main_swf_hash(swf, native[INFO_OFFSET:INFO_OFFSET + 20], digest)
    require_public_endpoint(result)
    assert assert_signable_layout(result) == assert_signable_layout(native)
    changes = [(SCHEME_SITE, SCHEME_SITE + 4), (offset, offset + old_size),
               (INFO_OFFSET, INFO_OFFSET + 20), (INFO_OFFSET + 32, INFO_OFFSET + 40)]
    restored = bytearray(result)
    for start, end in changes:
        restored[start:end] = native[start:end]
    assert restored == native, 'unexpected native code or metadata change'
    return bytes(result), new_swf, new_full, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-ipa', type=Path, default=R2)
    parser.add_argument('--full-abc', type=Path, default=FULL)
    parser.add_argument('--output-ipa', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--report-dir', type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    assert not args.output_ipa.exists() and not args.report_dir.exists(), 'fresh outputs required'
    assert sha(args.input_ipa.read_bytes()) == R2_SHA
    with zipfile.ZipFile(args.input_ipa) as z:
        native, swf = z.read(NATIVE_MEMBER), z.read(SWF_MEMBER)
    new_native, new_swf, full, ranges = patch(native, args.full_abc.read_bytes(), swf)
    args.report_dir.mkdir(parents=True)
    full_path = args.report_dir / 'cumulative-full-r3.abc'
    full_path.write_bytes(full)
    args.output_ipa.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.input_ipa) as left, zipfile.ZipFile(args.output_ipa, 'w', allowZip64=True) as right:
        for item in left.infolist():
            data = new_native if item.filename == NATIVE_MEMBER else new_swf if item.filename == SWF_MEMBER else left.read(item.filename)
            right.writestr(common.clone_zipinfo(item), data)
        right.comment = left.comment
    report = dict(status='unsigned_pending_independent_verification',
                  input_ipa=str(args.input_ipa.resolve()), input_ipa_sha256=R2_SHA,
                  input_full_abc=str(args.full_abc.resolve()), input_full_abc_sha256=FULL_SHA,
                  ipa=str(args.output_ipa.resolve()), ipa_sha256=sha(args.output_ipa.read_bytes()),
                  native_sha256=sha(new_native), swf_sha256=sha(new_swf),
                  full_abc=str(full_path.resolve()), full_abc_sha256=sha(full),
                  full_abc_sha1=hashlib.sha1(full).hexdigest(),
                  old_constructor_origin=constructor_origin(native), constructor_origin=constructor_origin(new_native),
                  effective_port=80, scheme_instruction_offset=SCHEME_SITE, host_pool_index=HOST_INDEX,
                  allowed_native_ranges=ranges, signing_layout=assert_signable_layout(new_native),
                  code_compilation=False, desktop_air_run=False, signed=False, device_tested=False,
                  account_storage_code_unchanged=True, server_changes=False)
    (args.report_dir / 'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf8')
    args.output_ipa.with_suffix('.ipa.sha256').write_text(report['ipa_sha256'] + '  ' + args.output_ipa.name + '\n', 'utf8')
    print(json.dumps({key: report[key] for key in ('status', 'ipa', 'ipa_sha256', 'constructor_origin')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
