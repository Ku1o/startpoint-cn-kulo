from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zipfile
from pathlib import Path


SCHEMA_VERSION = 1
DEFAULT_MERGE_GAP = 16


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def changed_ranges(source: bytes, target: bytes, merge_gap: int) -> list[tuple[int, int]]:
    if len(source) != len(target):
        raise ValueError("range patches require equal-sized members")

    changed = [index for index, pair in enumerate(zip(source, target)) if pair[0] != pair[1]]
    if not changed:
        return []

    ranges: list[tuple[int, int]] = []
    start = previous = changed[0]
    for index in changed[1:]:
        if index > previous + 1 + merge_gap:
            ranges.append((start, previous + 1))
            start = index
        previous = index
    ranges.append((start, previous + 1))
    return ranges


def build_member_patch(
    name: str,
    source: bytes,
    target: bytes,
    merge_gap: int,
) -> dict[str, object]:
    common = {
        "path": name,
        "sourceSize": len(source),
        "targetSize": len(target),
        "sourceSha256": sha256_bytes(source),
        "targetSha256": sha256_bytes(target),
    }

    if len(source) == len(target):
        ranges = changed_ranges(source, target, merge_gap)
        range_payload = sum((end - start) * 2 for start, end in ranges)
        if range_payload < len(target):
            return {
                **common,
                "mode": "ranges",
                "ranges": [
                    {
                        "offset": start,
                        "source": encode(source[start:end]),
                        "target": encode(target[start:end]),
                    }
                    for start, end in ranges
                ],
            }

    return {**common, "mode": "replace", "target": encode(target)}


def generate(source_path: Path, target_path: Path, merge_gap: int) -> dict[str, object]:
    with zipfile.ZipFile(source_path, "r") as source_zip, zipfile.ZipFile(
        target_path, "r"
    ) as target_zip:
        source_names = [info.filename for info in source_zip.infolist()]
        target_names = [info.filename for info in target_zip.infolist()]
        if source_names != target_names:
            raise RuntimeError("source and target IPA member order differs")

        member_patches: list[dict[str, object]] = []
        for name in source_names:
            source = source_zip.read(name)
            target = target_zip.read(name)
            if source != target:
                member_patches.append(
                    build_member_patch(name, source, target, merge_gap)
                )

        return {
            "schemaVersion": SCHEMA_VERSION,
            "description": (
                "World Flipper CN iOS 1.8.4 private-server five-in-one, "
                "account takeover, Fantasy Gauntlet, and asynchronous Fantasy "
                "soul texture client patch"
            ),
            "source": {
                "sha256": sha256_file(source_path),
                "memberCount": len(source_names),
            },
            "target": {
                "sha256": sha256_file(target_path),
                "memberCount": len(target_names),
                "bundleIdentifier": "com.kulo.wf",
                "signed": False,
            },
            "zipComment": encode(target_zip.comment),
            "mergeGap": merge_gap,
            "members": member_patches,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a hash-locked IPA patch manifest from vetted binaries."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--merge-gap", type=int, default=DEFAULT_MERGE_GAP)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.merge_gap < 0:
        raise SystemExit("--merge-gap must be non-negative")
    manifest = generate(args.source, args.target, args.merge_gap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output}")
    print(f"source sha256: {manifest['source']['sha256']}")
    print(f"target sha256: {manifest['target']['sha256']}")
    print(f"changed members: {len(manifest['members'])}")


if __name__ == "__main__":
    main()
