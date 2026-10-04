"""Independent read-back verification of a migrated public iOS candidate."""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO / "client-patch/ios-cumulative-login"),
                r"F:/codex/tools/ios-re-libs"]
import build_native as link  # type: ignore
import public_endpoint  # type: ignore
from macho_signing_layout import assert_signable_layout  # type: ignore

NATIVE_MEMBER = "Payload/worldflipper.app/worldflipper"
SWF_MEMBER = "Payload/worldflipper.app/worldflipper_ios_release.swf"
INFO_OFFSET = 104549248


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def constructor_origin(native: bytes, host: str) -> str:
    saved = (public_endpoint.PUBLIC_HOST, public_endpoint.PUBLIC_ORIGIN)
    public_endpoint.PUBLIC_HOST = host
    public_endpoint.PUBLIC_ORIGIN = "http://" + host
    try:
        return public_endpoint.require_public_endpoint(native)
    finally:
        public_endpoint.PUBLIC_HOST, public_endpoint.PUBLIC_ORIGIN = saved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--input-ipa", type=Path, required=True)
    parser.add_argument("--old-ip", required=True)
    parser.add_argument("--new-ip", required=True)
    parser.add_argument("--expected-native-hits", type=int, default=354)
    parser.add_argument("--expected-full-abc-hits", type=int, default=17)
    parser.add_argument("--report-out", type=Path, default=None)
    args = parser.parse_args()

    report = json.loads(args.build_report.read_text("utf-8"))
    ipa = Path(report["ipa"])
    checks = {}
    with zipfile.ZipFile(ipa) as new, zipfile.ZipFile(args.input_ipa) as old:
        checks["member_order_equal"] = new.namelist() == old.namelist()
        changed = [name for name in new.namelist() if new.read(name) != old.read(name)]
        checks["changed_members"] = changed
        checks["changed_members_expected"] = set(changed) == {NATIVE_MEMBER, SWF_MEMBER}
        checks["comment_equal"] = new.comment == old.comment
        new_native = new.read(NATIVE_MEMBER)
        old_native = old.read(NATIVE_MEMBER)
        new_swf = new.read(SWF_MEMBER)
        old_swf = old.read(SWF_MEMBER)
        checks["old_ip_left_in_members"] = [
            info.filename for info in new.infolist()
            if args.old_ip.encode() in new.read(info.filename)]
    checks["ipa_sha256"] = sha(ipa.read_bytes())
    checks["ipa_matches_report"] = checks["ipa_sha256"] == report["ipa_sha256"]
    checks["native_matches_report"] = sha(new_native) == report["native_sha256"]
    checks["swf_matches_report"] = sha(new_swf) == report["swf_sha256"]

    full = Path(report["full_abc"]).read_bytes()
    checks["full_abc_sha256"] = sha(full)
    checks["full_abc_matches_report"] = checks["full_abc_sha256"] == report["full_abc_sha256"]
    digest = hashlib.sha1(full).digest()
    checks["native_digest_ok"] = new_native[INFO_OFFSET:INFO_OFFSET + 20] == digest
    checks["full_abc_new_hits"] = full.count(args.new_ip.encode())
    checks["full_abc_new_hits_expected"] = checks["full_abc_new_hits"] == args.expected_full_abc_hits
    checks["full_abc_no_old"] = full.count(args.old_ip.encode()) == 0

    abc_va = struct.unpack_from("<Q", new_native, INFO_OFFSET + 24)[0]
    abc_len = struct.unpack_from("<Q", new_native, INFO_OFFSET + 32)[0]
    abc_off = link.file_offset(new_native, abc_va)
    runtime = new_native[abc_off:abc_off + abc_len]
    checks["runtime_abc_sha256"] = sha(runtime)
    checks["runtime_no_old_ip"] = runtime.count(args.old_ip.encode()) == 0
    checks["runtime_new_ip_hits"] = runtime.count(args.new_ip.encode())

    origin = constructor_origin(new_native, args.new_ip)
    checks["constructor_origin"] = origin
    checks["constructor_origin_ok"] = origin == "http://" + args.new_ip
    checks["signing_layout_equal"] = (assert_signable_layout(new_native)
                                      == assert_signable_layout(old_native))

    expected_diffs = set(range(INFO_OFFSET, INFO_OFFSET + 20))
    old_sites = []
    start = 0
    while True:
        at = old_native.find(args.old_ip.encode(), start)
        if at < 0:
            break
        old_sites.append(at)
        expected_diffs.update(range(at, at + len(args.old_ip)))
        start = at + 1
    diffs = {i for i, (x, y) in enumerate(zip(new_native, old_native)) if x != y}
    checks["native_site_count"] = len(old_sites)
    checks["native_site_count_expected"] = len(old_sites) == args.expected_native_hits
    checks["native_change_count"] = len(diffs)
    checks["native_changes_confined"] = not (diffs - expected_diffs)
    checks["native_new_ip_at_all_sites"] = all(
        new_native[at:at + len(args.new_ip)] == args.new_ip.encode() for at in old_sites)
    checks["native_new_ip_hits"] = new_native.count(args.new_ip.encode())
    checks["native_no_old_ip"] = new_native.count(args.old_ip.encode()) == 0

    tag, old_plain = link.aot.decompress_swf(old_swf)
    tag2, new_plain = link.aot.decompress_swf(new_swf)
    checks["swf_signature_equal"] = tag == tag2
    checks["swf_uncompressed_same_length"] = len(old_plain) == len(new_plain)
    old_at = old_plain.find(b"\0\0\0\0" + old_native[INFO_OFFSET:INFO_OFFSET + 20])
    checks["swf_digest_slot_found"] = old_at >= 0
    plain_diffs = {i for i, (x, y) in enumerate(zip(new_plain, old_plain)) if x != y}
    checks["swf_changes_confined_to_digest"] = (
        old_at >= 0 and plain_diffs == set(range(old_at + 4, old_at + 24)))

    failures = {k: v for k, v in checks.items() if v is False}
    result = {"status": "verified" if not failures else "failed",
              "ipa": str(ipa), "ipa_sha256": checks["ipa_sha256"],
              "source_ipa": str(args.input_ipa), "checks": checks, "failures": failures}
    report_out = args.report_out or (Path(report["ipa"]).parent / "ios-public-verification.json")
    report_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    print(json.dumps({"status": result["status"], "ipa": result["ipa"],
                      "ipa_sha256": result["ipa_sha256"],
                      "constructor_origin": checks["constructor_origin"],
                      "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
