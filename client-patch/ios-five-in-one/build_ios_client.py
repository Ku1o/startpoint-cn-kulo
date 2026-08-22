from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import BinaryIO


DEFAULT_MANIFEST = Path(__file__).with_name("patch-manifest.json")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def copy_zipinfo(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    clone = zipfile.ZipInfo(info.filename, info.date_time)
    clone.compress_type = info.compress_type
    clone.comment = info.comment
    clone.extra = info.extra
    clone.create_system = info.create_system
    clone.create_version = info.create_version
    clone.extract_version = info.extract_version
    clone.flag_bits = info.flag_bits
    clone.volume = info.volume
    clone.internal_attr = info.internal_attr
    clone.external_attr = info.external_attr
    return clone


def verify_member(data: bytes, patch: dict[str, object], side: str) -> None:
    expected_size = int(patch[f"{side}Size"])
    expected_hash = str(patch[f"{side}Sha256"])
    if len(data) != expected_size:
        raise RuntimeError(
            f"{patch['path']} {side} size mismatch: {len(data)} != {expected_size}"
        )
    actual_hash = sha256_bytes(data)
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"{patch['path']} {side} hash mismatch: {actual_hash} != {expected_hash}"
        )


def apply_member_patch(source: bytes, patch: dict[str, object]) -> bytes:
    verify_member(source, patch, "source")
    mode = patch["mode"]
    if mode == "replace":
        target = decode(str(patch["target"]))
    elif mode == "ranges":
        target_buffer = bytearray(source)
        for range_patch in patch["ranges"]:
            offset = int(range_patch["offset"])
            expected = decode(str(range_patch["source"]))
            replacement = decode(str(range_patch["target"]))
            end = offset + len(expected)
            if len(expected) != len(replacement):
                raise RuntimeError(f"{patch['path']} range size mismatch at {offset:#x}")
            if bytes(target_buffer[offset:end]) != expected:
                raise RuntimeError(
                    f"{patch['path']} source bytes mismatch at {offset:#x}"
                )
            target_buffer[offset:end] = replacement
        target = bytes(target_buffer)
    else:
        raise RuntimeError(f"unsupported patch mode: {mode}")

    verify_member(target, patch, "target")
    return target


def write_patched_ipa(
    source_path: Path,
    destination: str | Path | BinaryIO,
    manifest: dict[str, object],
) -> None:
    patch_by_name = {str(item["path"]): item for item in manifest["members"]}
    expected_count = int(manifest["source"]["memberCount"])

    with zipfile.ZipFile(source_path, "r") as source_zip, zipfile.ZipFile(
        destination, "w"
    ) as output_zip:
        source_infos = source_zip.infolist()
        if len(source_infos) != expected_count:
            raise RuntimeError(
                f"source member count mismatch: {len(source_infos)} != {expected_count}"
            )

        source_names = {info.filename for info in source_infos}
        missing = set(patch_by_name) - source_names
        if missing:
            raise RuntimeError(f"patched members missing from source: {sorted(missing)}")

        output_zip.comment = decode(str(manifest.get("zipComment", "")))
        for info in source_infos:
            source = source_zip.read(info.filename)
            patch = patch_by_name.get(info.filename)
            target = apply_member_patch(source, patch) if patch else source
            output_zip.writestr(copy_zipinfo(info), target)


def load_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1:
        raise RuntimeError(f"unsupported manifest schema: {manifest.get('schemaVersion')}")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the vetted unsigned iOS client from the exact original IPA."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Build in memory and verify the exact target hash without writing an IPA.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.verify_only == (args.output is not None):
        raise SystemExit("choose exactly one of --output or --verify-only")

    manifest = load_manifest(args.manifest)
    expected_source_hash = str(manifest["source"]["sha256"])
    actual_source_hash = sha256_file(args.source)
    if actual_source_hash != expected_source_hash:
        raise SystemExit(
            f"source IPA hash mismatch: {actual_source_hash} != {expected_source_hash}"
        )

    expected_target_hash = str(manifest["target"]["sha256"])
    if args.verify_only:
        memory_output = io.BytesIO()
        write_patched_ipa(args.source, memory_output, manifest)
        actual_target_hash = sha256_bytes(memory_output.getvalue())
    else:
        assert args.output is not None
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_patched_ipa(args.source, args.output, manifest)
        actual_target_hash = sha256_file(args.output)

    if actual_target_hash != expected_target_hash:
        raise SystemExit(
            f"target IPA hash mismatch: {actual_target_hash} != {expected_target_hash}"
        )
    print(f"target sha256 verified: {actual_target_hash}")


if __name__ == "__main__":
    main()
