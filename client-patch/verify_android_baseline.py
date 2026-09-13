#!/usr/bin/env python3
"""Read-only identity check for the registered Android baseline and acceptance scope."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RECORD = Path(__file__).with_name("android-accepted.json")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(variant: str, apk: Path | None = None, *, record_path: Path | None = None) -> dict:
    record_file = record_path if record_path is not None else RECORD
    record = json.loads(record_file.read_text(encoding="utf-8"))
    identity = (record["schema_version"], record["status"])
    if identity not in ((1, "user_accepted"), (2, "accepted_offline"), (3, "user_accepted")):
        raise ValueError("baseline record must explicitly identify an accepted release and scope")
    if identity == (2, "accepted_offline"):
        if not record["acceptance"]["user_statement"] or record["acceptance"]["scope"] != "offline_artifact_and_lineage":
            raise ValueError("offline acceptance must record user authorization and its limited scope")
    if identity == (3, "user_accepted"):
        acceptance = record["acceptance"]
        if not acceptance["user_statement"] or acceptance["scope"] != "user_confirmed_acceptance_and_offline_identity":
            raise ValueError("user acceptance must record the user's confirmation and audit scope")
    entry = record["variants"][variant]
    path = apk.resolve() if apk else ROOT / entry["apk"]
    if not path.is_file():
        raise ValueError(f"accepted APK is missing; do not substitute an older package: {path}")
    if digest(path) != entry["apk_sha256"]:
        raise ValueError(f"APK SHA-256 differs from the accepted {variant} package: {path}")
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("duplicate APK members")
        swf = archive.read("assets/worldflipper_android_release.swf")
        if hashlib.sha256(swf).hexdigest() != entry["swf_sha256"]:
            raise ValueError("embedded SWF SHA-256 mismatch")
        if identity == (3, "user_accepted") or "size_bytes" in entry:
            if path.stat().st_size != entry["size_bytes"]:
                raise ValueError("APK size differs from the accepted package")
        if identity == (3, "user_accepted") or "dex_sha256" in entry:
            if hashlib.sha256(archive.read("classes.dex")).hexdigest() != entry["dex_sha256"]:
                raise ValueError("embedded startup-cache DEX SHA-256 mismatch")
        manifest = archive.read("AndroidManifest.xml").decode("utf-16le", errors="ignore")
        expected_uuid = entry["uniqueappversionid"]
        if manifest.count(expected_uuid) != 1:
            raise ValueError("accepted AIR uniqueappversionid must occur exactly once")
        uuids = re.findall(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", manifest)
        if uuids != [expected_uuid]:
            raise ValueError(f"unexpected manifest UUIDs: {uuids}")
    endpoint = entry["endpoint"]
    if "local_endpoint_config" in entry:
        local = ROOT / entry["local_endpoint_config"]
        if local.is_file():
            endpoint = "http://" + json.loads(local.read_text(encoding="utf-8"))["lan_host"]
            if hashlib.sha256(endpoint.encode()).hexdigest() != entry["endpoint_sha256"]:
                raise ValueError("local LAN endpoint differs from the accepted artifact record")
    return {"status": "accepted_identity_verified", "variant": variant,
            "registry": str(record_file),
            "acceptance_status": entry.get("acceptance_status", record["status"]),
            "accepted_on": entry.get("accepted_on", record["accepted_on"]),
            "acceptance_audit": entry.get("acceptance_audit", record.get("acceptance", {}).get("audit")),
            "main_abc_index": entry.get("main_abc_index", 284),
            "method_bodies_checked": entry["local_build_checks"]["method_bodies_checked"],
            "device_tested_by_this_check": False,
            "apk": str(path), "apk_sha256": entry["apk_sha256"],
            "swf_sha256": entry["swf_sha256"], "uniqueappversionid": expected_uuid,
            "endpoint": endpoint}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True, choices=("public", "lan"))
    parser.add_argument("--apk", type=Path, help="explicit alternate location; identity must still match")
    parser.add_argument("--record", type=Path, help="explicit historical acceptance record for reproduction")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.variant, args.apk, record_path=args.record), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
