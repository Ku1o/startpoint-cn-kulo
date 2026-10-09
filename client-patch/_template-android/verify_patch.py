#!/usr/bin/env python3
"""Skeleton verifier for a new Android client-patch topic.

``--self-test`` needs no APK: it checks that ``baseline.json`` still matches the
public entry of ``android-accepted.json``. With ``--out-dir`` it re-reads the
builder's report and patched SWF and checks lineage, hashes and the new UUID.
Add the topic's own method-level assertions in ``check_patch``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import build_swf


def check_patch(swf: bytes, report: dict) -> None:
    """Topic-specific assertions on the patched SWF (method diffs, constants...)."""
    raise NotImplementedError("add the topic's SWF assertions here")


def verify(out_dir: Path) -> dict:
    baseline = build_swf.load_baseline()
    report = json.loads((out_dir / "build-report.json").read_text(encoding="utf-8"))
    swf = (out_dir / report["output"]["swf"]).read_bytes()
    pinned = report["baseline"]
    for key in ("variant", "build_id", "apk_sha256", "swf_sha256", "uniqueappversionid"):
        if pinned.get(key) != baseline[key]:
            raise ValueError(f"build report baseline differs from baseline.json: {key}")
    if hashlib.sha256(swf).hexdigest() != report["output"]["swf_sha256"]:
        raise ValueError("patched SWF hash differs from the build report")
    if report["output"]["swf_sha256"] == baseline["swf_sha256"]:
        raise ValueError("patched SWF is identical to the baseline")
    uuid = report["output"]["uniqueappversionid"]
    if not build_swf.UUID_RE.fullmatch(uuid) or uuid == baseline["uniqueappversionid"]:
        raise ValueError("patched SWF needs a new, well-formed AIR uniqueappversionid")
    check_patch(swf, report)
    return {"status": "patch_verified_offline", "topic": report["topic"], "swf_sha256": report["output"]["swf_sha256"],
            "uniqueappversionid": uuid, "device_tested_by_this_check": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true", help="check the baseline pin only")
    group.add_argument("--out-dir", type=Path, help="directory written by build_swf.py")
    args = parser.parse_args()
    try:
        if args.self_test:
            baseline = build_swf.load_baseline()
            result = {"status": "baseline_pin_matches_registry", "build_id": baseline["build_id"]}
        else:
            result = verify(args.out_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, NotImplementedError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
