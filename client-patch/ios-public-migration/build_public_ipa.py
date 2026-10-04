"""Convert an accepted iOS IPA to the current public endpoint.

Endpoint conversion is a mechanical step: keep the accepted game content and
the admission pairing, replace the embedded server address everywhere in the
native executable and the full ABC, refresh the AOT digest in the native image
and in the main SWF, then repack.  Only the native executable and the main SWF
may change; the input must be a carrier whose pre-query constructor origin is
the previous public endpoint.

The full ABC (the AOT compiler input paired with the IPA) is required so the
digest can be recomputed.  Nothing here installs, signs, deploys or tests the
package; the result is an offline public candidate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
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
DEFAULT_OLD_IP = "175.178.160.158"
DEFAULT_NEW_IP = "124.222.203.221"


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


def admission_id(full: bytes) -> str:
    match = re.search(rb"SP-ADMISSION-1\n([0-9A-Za-z\-]+)\n", full)
    if not match:
        raise AssertionError("full ABC has no admission id")
    return match.group(1).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-ipa", type=Path, required=True)
    parser.add_argument("--input-ipa-sha256", required=True)
    parser.add_argument("--input-full-abc", type=Path, required=True)
    parser.add_argument("--input-full-abc-sha256", required=True)
    parser.add_argument("--old-ip", default=DEFAULT_OLD_IP)
    parser.add_argument("--new-ip", default=DEFAULT_NEW_IP)
    parser.add_argument("--expected-native-hits", type=int, default=354)
    parser.add_argument("--expected-full-abc-hits", type=int, default=17)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--abc-name", required=True)
    args = parser.parse_args()

    if sha(args.input_ipa.read_bytes()) != args.input_ipa_sha256:
        raise AssertionError("input IPA hash changed")
    full = args.input_full_abc.read_bytes()
    if sha(full) != args.input_full_abc_sha256:
        raise AssertionError("input full ABC hash changed")
    with zipfile.ZipFile(args.input_ipa) as archive:
        native = archive.read(NATIVE_MEMBER)
        swf = archive.read(SWF_MEMBER)
        entries = [(archive.getinfo(name), archive.read(name)) for name in archive.namelist()]
        comment = archive.comment

    if constructor_origin(native, args.old_ip) != "http://" + args.old_ip:
        raise AssertionError("input native does not carry the previous public endpoint")
    assert_signable_layout(native)
    old_digest = native[INFO_OFFSET:INFO_OFFSET + 20]
    if old_digest != hashlib.sha1(full).digest():
        raise AssertionError("input AOT digest does not match the supplied full ABC")
    old = args.old_ip.encode()
    new = args.new_ip.encode()
    if len(old) != len(new):
        raise AssertionError("endpoint replacement must keep the byte length")
    native_hits = native.count(old)
    full_hits = full.count(old)
    if native_hits != args.expected_native_hits:
        raise AssertionError(("unexpected native endpoint count", native_hits))
    if full_hits != args.expected_full_abc_hits:
        raise AssertionError(("unexpected full ABC endpoint count", full_hits))
    if native.count(new) or full.count(new) or swf.count(old) or swf.count(new):
        raise AssertionError("input already carries the new endpoint or SWF carries an endpoint")

    new_native = native.replace(old, new)
    new_full = full.replace(old, new)
    if len(new_full) != len(full):
        raise AssertionError("endpoint replacement changed the full ABC size")
    if new_native.count(old) or new_native.count(new) != native_hits:
        raise AssertionError("native endpoint replacement incomplete")
    if new_full.count(old) or new_full.count(new) != full_hits:
        raise AssertionError("full ABC endpoint replacement incomplete")
    digest = hashlib.sha1(new_full).digest()
    new_native = bytearray(new_native)
    new_native[INFO_OFFSET:INFO_OFFSET + 20] = digest
    new_native = bytes(new_native)
    new_swf = link.aot.replace_main_swf_hash(swf, old_digest, digest)
    origin = constructor_origin(new_native, args.new_ip)
    if origin != "http://" + args.new_ip:
        raise AssertionError(("constructor origin not migrated", origin))
    signing = assert_signable_layout(new_native)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    abc_path = args.out_dir / args.abc_name
    abc_path.write_bytes(new_full)
    ipa = args.out_dir / args.output_name
    if ipa.exists():
        raise FileExistsError(ipa)
    with zipfile.ZipFile(ipa, "w", allowZip64=True) as destination:
        for info, data in entries:
            if info.filename == NATIVE_MEMBER:
                data = new_native
            elif info.filename == SWF_MEMBER:
                data = new_swf
            destination.writestr(link.common.clone_zipinfo(info), data)
        destination.comment = comment
    report = {
        "status": "offline_public_candidate",
        "input_ipa": str(args.input_ipa), "input_ipa_sha256": args.input_ipa_sha256,
        "input_full_abc_sha256": args.input_full_abc_sha256,
        "ipa": str(ipa), "ipa_sha256": sha(ipa.read_bytes()),
        "native_sha256": sha(new_native), "swf_sha256": sha(new_swf),
        "full_abc": str(abc_path), "full_abc_sha256": sha(new_full),
        "full_abc_sha1": hashlib.sha1(new_full).hexdigest(),
        "endpoint_before": "http://" + args.old_ip,
        "endpoint_after": "http://" + args.new_ip,
        "native_endpoint_replacements": native_hits,
        "full_abc_endpoint_replacements": full_hits,
        "constructor_origin": origin,
        "admission_id": admission_id(new_full),
        "admission_pair_unchanged": True,
        "signing_layout": signing,
        "device_tested": False, "cloud_deployed": False,
    }
    (args.out_dir / "ios-public-build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ipa.with_suffix(".ipa.sha256")).write_text(
        report["ipa_sha256"] + "  " + ipa.name + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "status", "ipa", "ipa_sha256", "native_sha256", "swf_sha256",
        "full_abc_sha256", "constructor_origin", "admission_id",
        "native_endpoint_replacements", "full_abc_endpoint_replacements")},
        ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
