#!/usr/bin/env python3
"""Skeleton builder for a new Android client-patch topic.

Copy this directory to ``client-patch/<topic>/`` and implement ``apply_patch``.
The builder pins its input to the public entry of ``android-accepted.json``
(via ``baseline.json``), refuses any other APK, and writes the patched SWF plus
a build report. Packaging, signing, admission and release stay with the owner.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASELINE = HERE / "baseline.json"
SWF_MEMBER = "assets/worldflipper_android_release.swf"
UUID_RE = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
PINNED_KEYS = ("apk_sha256", "swf_sha256", "uniqueappversionid", "build_id", "main_abc_index",
               "package_name", "version_name", "version_code")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_baseline() -> dict:
    """Return baseline.json after checking it still matches the accepted registry."""
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "android-accepted.json").read_text(encoding="utf-8"))
    entry = registry["variants"][baseline["variant"]]
    drift = [key for key in PINNED_KEYS if entry.get(key) != baseline.get(key)]
    if drift:
        raise ValueError(f"baseline.json no longer matches android-accepted.json ({', '.join(drift)}); "
                         "re-pin the topic to the current accepted package before building")
    return baseline


def verify_input(apk: Path, baseline: dict) -> bytes:
    """Run the shared baseline checker, then return the embedded SWF bytes."""
    spec = importlib.util.spec_from_file_location("verify_android_baseline", ROOT / "verify_android_baseline.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    checker.verify(baseline["variant"], apk)
    with zipfile.ZipFile(apk) as archive:
        swf = archive.read(SWF_MEMBER)
    if sha256(swf) != baseline["swf_sha256"]:
        raise ValueError("embedded SWF differs from the pinned baseline")
    return swf


def apply_patch(swf: bytes) -> tuple[bytes, dict]:
    """Return the patched SWF and a summary of what changed.

    The summary should at least list changed/added/removed method bodies, e.g.
    ``{"changed_methods": [...], "added_methods": 0, "removed_methods": 0}``.
    """
    raise NotImplementedError("implement the topic's SWF patch here")


def build(apk: Path, out_dir: Path, new_uuid: str) -> dict:
    baseline = load_baseline()
    new_uuid = new_uuid.lower()
    if not UUID_RE.fullmatch(new_uuid):
        raise ValueError("--uuid must be a lowercase RFC 4122 UUID")
    if new_uuid == baseline["uniqueappversionid"]:
        raise ValueError("a changed SWF needs a new AIR uniqueappversionid; do not reuse the baseline UUID")
    swf = verify_input(apk.resolve(), baseline)
    patched, summary = apply_patch(swf)
    if patched == swf:
        raise ValueError("patch produced an identical SWF")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "patched.swf").write_bytes(patched)
    report = {
        "schema_version": 1,
        "topic": HERE.name,
        "baseline": {key: baseline[key] for key in ("variant", "build_id", "apk_sha256", "swf_sha256", "uniqueappversionid")},
        "output": {"swf": "patched.swf", "swf_sha256": sha256(patched), "uniqueappversionid": new_uuid},
        "patch": summary,
        "packaged": False,
        "device_tested": False,
    }
    (out_dir / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True, help="the accepted public APK (identity is checked)")
    parser.add_argument("--out-dir", type=Path, required=True, help="local output directory, never inside the repo")
    parser.add_argument("--uuid", required=True, help="new AIR uniqueappversionid for the patched SWF")
    args = parser.parse_args()
    if args.out_dir.resolve().is_relative_to(ROOT.parent):
        print("ERROR: --out-dir must be outside the repository", file=sys.stderr)
        return 1
    try:
        print(json.dumps(build(args.apk, args.out_dir, args.uuid), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, NotImplementedError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
