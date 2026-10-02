#!/usr/bin/env python3
"""Read-only identity check for the registered iOS IPA, native executable and SWF."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RECORD = Path(__file__).with_name("ios-accepted.json")


def verify(ipa: Path | None = None, *, record_path: Path | None = None) -> dict:
    record_file = record_path if record_path is not None else RECORD
    record = json.loads(record_file.read_text(encoding="utf-8"))
    identity = (record["schema_version"], record["status"])
    if identity not in ((1, "user_accepted"), (2, "accepted_offline"), (3, "user_accepted"),
                        (4, "accepted_offline"), (4, "user_accepted"), (5, "user_accepted"),
                        (6, "accepted_offline"), (6, "user_accepted")):
        raise ValueError("baseline record must explicitly identify an accepted release and scope")
    if identity in ((2, "accepted_offline"), (4, "accepted_offline")):
        if not record["acceptance"]["user_statement"] or record["acceptance"]["scope"] != "offline_artifact_and_lineage":
            raise ValueError("offline acceptance must record user authorization and its limited scope")
    if identity in ((3, "user_accepted"), (4, "user_accepted")):
        acceptance = record["acceptance"]
        if not acceptance["user_statement"] or acceptance["scope"] != "user_confirmed_acceptance_and_offline_identity":
            raise ValueError("user acceptance must record the user's confirmation and audit scope")
    if identity == (5, "user_accepted"):
        acceptance = record["acceptance"]
        if acceptance.get("result") != "accepted" or acceptance.get("scope") != "public_release_and_offline_identity" or not acceptance.get("audit"):
            raise ValueError("acceptance must record an explicit result, release scope and audit")
    entry = record["artifact"]
    if identity == (6, "accepted_offline"):
        acceptance = record["acceptance"]
        if acceptance.get("result") != "accepted_offline" or acceptance.get("scope") != "offline_artifact_lineage_and_public_admission" or not acceptance.get("audit"):
            raise ValueError("offline acceptance must state its evidence scope and audit")
    if identity == (6, "user_accepted"):
        acceptance = record["acceptance"]
        if acceptance.get("result") != "user_accepted" or acceptance.get("scope") != "ios_real_device_acceptance_and_offline_artifact_lineage" or not acceptance.get("audit"):
            raise ValueError("user acceptance must state its device acceptance scope and audit")
    path = ipa.resolve() if ipa else ROOT / entry["ipa"]
    if not path.is_file():
        raise ValueError(f"accepted IPA is missing; do not substitute an older package: {path}")
    if path.stat().st_size != entry["size_bytes"]:
        raise ValueError("IPA size differs from the accepted package")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != entry["ipa_sha256"]:
            raise ValueError("IPA SHA-256 differs from the accepted package")
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("duplicate IPA members")
        for part in ("native", "swf"):
            if hashlib.sha256(archive.read(entry[f"{part}_member"])).hexdigest() != entry[f"{part}_sha256"]:
                raise ValueError(f"embedded {part} SHA-256 mismatch")
        plist_path = str(Path(entry["native_member"]).with_name("Info.plist")).replace("\\", "/")
        plist = plistlib.loads(archive.read(plist_path))
        for key, name in (("CFBundleIdentifier", "bundle_id"),
                          ("CFBundleShortVersionString", "version"),
                          ("CFBundleVersion", "build")):
            if plist[key] != entry[name]:
                raise ValueError(f"application identity mismatch: {key}")
        if identity in ((3, "user_accepted"), (4, "accepted_offline"), (4, "user_accepted"), (5, "user_accepted"), (6, "accepted_offline"), (6, "user_accepted")):
            full = ROOT / entry["full_abc"]
            if not full.is_file():
                raise ValueError("accepted full ABC is missing; do not substitute stripped runtime ABC")
            full_bytes = full.read_bytes()
            if hashlib.sha256(full_bytes).hexdigest() != entry["full_abc_sha256"]:
                raise ValueError("accepted full ABC SHA-256 mismatch")
            digest = hashlib.sha1(full_bytes).digest()
            native = archive.read(entry["native_member"])
            at = entry["aot_info_file_offset"]
            if digest.hex() != entry["full_abc_sha1"] or native[at:at + 20] != digest:
                raise ValueError("accepted full ABC and native AOT identity differ")
            if struct.unpack_from("<Q", native, at + 56)[0] != entry["aot_method_count"]:
                raise ValueError("accepted native AOT method count differs")
    return {"status": "accepted_identity_verified", "acceptance_status": record["status"],
            "registry": str(record_file),
            "ipa": str(path), "ipa_sha256": entry["ipa_sha256"],
            "native_sha256": entry["native_sha256"], "swf_sha256": entry["swf_sha256"],
            "signing": entry["signing"], "device_tested_by_this_check": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipa", type=Path, help="explicit alternate location; identity must still match")
    parser.add_argument("--record", type=Path, help="explicit historical acceptance record for reproduction")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.ipa, record_path=args.record), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
