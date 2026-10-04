#!/usr/bin/env python3
"""Hash a candidate asset-patch ZIP and its members for the manifest entry and PR.

Read-only: prints an ``archive_integrity`` object (ZIP size/SHA-256, member list
and per-member SHA-256). It refuses archives that are outside the candidates
directory, contain unsafe member paths or duplicate names.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
CANDIDATES = ROOT / "assets" / "asset-patch" / "active" / "candidates"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def report(path: Path, *, allow_outside: bool = False) -> dict:
    path = path.resolve()
    if not allow_outside and path.parent != CANDIDATES:
        raise ValueError(f"candidate ZIP must live directly in {CANDIDATES.relative_to(ROOT)}: {path}")
    with zipfile.ZipFile(path) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP members")
        members = {}
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts or "\\" in name:
                raise ValueError(f"unsafe member path: {name}")
            members[name] = sha256(archive.read(name))
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": sha256(path.read_bytes()),
        "members": len(members),
        "files": sorted(members),
        "member_sha256": dict(sorted(members.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    parser.add_argument("--allow-outside", action="store_true",
                        help="hash a ZIP that is not yet in active/candidates (for drafts only)")
    args = parser.parse_args()
    try:
        print(json.dumps(report(args.zip, allow_outside=args.allow_outside), ensure_ascii=False, indent=2))
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
