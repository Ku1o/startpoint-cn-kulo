"""Build an unsigned IPA from the accepted iOS package with the startup gate repair."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
CLIENT_PATCH = HERE.parent
sys.path.insert(0, str(CLIENT_PATCH / "ios-cumulative-login"))
import build_native as link  # noqa: E402
from macho_signing_layout import assert_signable_layout  # noqa: E402

NATIVE_MEMBER = "Payload/worldflipper.app/worldflipper"
SWF_MEMBER = "Payload/worldflipper.app/worldflipper_ios_release.swf"
INFO_OFFSET = 104549248
METHOD_COUNT = 101436
METHOD_ID = 41998
SITE_BYTES = ((0x105376F68, "a0180034"), (0x105377300, "20050034"))
NOP = bytes.fromhex("1f2003d5")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ipa", type=Path, required=True)
    parser.add_argument("--baseline-full-abc-sha1", required=True)
    parser.add_argument("--full-abc", type=Path, required=True)
    parser.add_argument("--output-ipa", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    full = args.full_abc.read_bytes()
    new_digest = hashlib.sha1(full).digest()
    old_digest = bytes.fromhex(args.baseline_full_abc_sha1)
    if new_digest == old_digest:
        raise AssertionError("complete ABC digest did not change")
    with zipfile.ZipFile(args.baseline_ipa) as source:
        native = bytearray(source.read(NATIVE_MEMBER))
        swf = source.read(SWF_MEMBER)
        source_members = source.namelist()
        if len(source_members) != len(set(source_members)):
            raise AssertionError("duplicate IPA members")
    if native[INFO_OFFSET : INFO_OFFSET + 20] != old_digest:
        raise AssertionError("baseline AOT digest does not match the supplied full ABC")
    if struct.unpack_from("<Q", native, INFO_OFFSET + 56)[0] != METHOD_COUNT:
        raise AssertionError("baseline AOT method count differs")
    old_native = bytes(native)
    assert_signable_layout(old_native)
    aot = link.aot
    entry = aot.read_u64(native, aot.MAIN_METHOD_TABLE_OFFSET + METHOD_ID * 8)
    if entry != 0x105376DF8:
        raise AssertionError(("unexpected applyLoad entry", hex(entry)))
    changes = []
    for address, old_hex in SITE_BYTES:
        offset = link.file_offset(native, address, 4)
        if native[offset : offset + 4].hex() != old_hex:
            raise AssertionError(("unexpected branch", hex(address), native[offset : offset + 4].hex()))
        native[offset : offset + 4] = NOP
        changes.append({"address": hex(address), "file_offset": offset, "old": old_hex, "new": NOP.hex()})
    native[INFO_OFFSET : INFO_OFFSET + 20] = new_digest
    signing = assert_signable_layout(native)
    allowed = set(range(INFO_OFFSET, INFO_OFFSET + 20))
    for change in changes:
        allowed.update(range(change["file_offset"], change["file_offset"] + 4))
    actual = {i for i, (before, after) in enumerate(zip(old_native, native)) if before != after}
    if actual != allowed:
        raise AssertionError("native patch escaped the two branches and AOT identity")
    new_swf = aot.replace_main_swf_hash(swf, old_digest, new_digest)

    args.output_ipa.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.baseline_ipa) as source, zipfile.ZipFile(args.output_ipa, "w", allowZip64=True) as dest:
        for item in source.infolist():
            data = bytes(native) if item.filename == NATIVE_MEMBER else new_swf if item.filename == SWF_MEMBER else source.read(item)
            dest.writestr(link.common.clone_zipinfo(item), data)
        dest.comment = source.comment
    report = {
        "status": "candidate_built_pending_independent_verification",
        "ipa": str(args.output_ipa),
        "ipa_sha256": sha(args.output_ipa.read_bytes()),
        "source_ipa": str(args.baseline_ipa),
        "native_sha256": sha(native),
        "swf_sha256": sha(new_swf),
        "full_abc": str(args.full_abc),
        "full_abc_sha256": sha(full),
        "full_abc_sha1": new_digest.hex(),
        "aot_info_file_offset": INFO_OFFSET,
        "aot_method_count": METHOD_COUNT,
        "method_id": METHOD_ID,
        "apply_load_entry": hex(entry),
        "native_patch": changes,
        "native_changed_byte_count": len(actual),
        "runtime_abc_unchanged": True,
        "aot_method_table_unchanged": True,
        "signing_layout": signing,
        "device_tested": False,
        "cloud_deployed": False,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
