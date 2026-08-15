#!/usr/bin/env python3
"""Publish the Fantasy equipment icon lifetime fix as a one-table CDN patch.

The 11 custom equipment PNGs are standalone textures.  Without matching rows
in ``trimmed_image`` the client hands UI cells the cached root textures; a cell
that clears its image can then dispose the shared root and later thumbnails
become blank.  A full-frame trim row makes the client return disposable
subtextures instead, while leaving the PNG payloads unchanged.
"""

from __future__ import annotations

import hashlib
import io
import json
import zlib
import zipfile
from dataclasses import dataclass
from pathlib import Path

import wf_mod_tool as core


ROOT = Path(__file__).resolve().parents[2]
PATCH_ROOT = ROOT / "assets" / "asset-patch"
MANIFEST_PATH = PATCH_ROOT / "manifest.json"
ACTIVE_ROOT = PATCH_ROOT / "active"
STORE_ROOT = PATCH_ROOT / "production" / "upload"
ICON_ROOT = Path(__file__).resolve().parent / "assets" / "fantasy-equipment"

TRIMMED_LOGICAL = "master/generated/trimmed_image.orderedmap"
TRIMMED_DIGEST = core.sha1_path(TRIMMED_LOGICAL)
TRIMMED_RELATIVE = Path(TRIMMED_DIGEST[:2]) / TRIMMED_DIGEST[2:]
TRIMMED_MEMBER = f"production/upload/{TRIMMED_RELATIVE.as_posix()}"

BASE_VERSION = "1.4.77"
PATCH_VERSION = "1.4.78"
PATCH_ID = "fantasy-equipment-icon-trim-1.4.78"
ARCHIVE_NAME = (
    "pinball-1.4.77-1.4.78-1-0815-fantasy-equipment-icon-trim.zip"
)
CREATED_AT = "2026-08-15"
CLIENT_ASSET_SIZE = (20, 20)
IMAGE_PREFIX = "item/equipment/mod/fantasy"
ICON_SLUGS = (
    "skill_core",
    "direct_blade",
    "powerflip_hammer",
    "multiball_hangar",
    "ability_terminal",
    "fever_ring",
    "adversity_sword",
    "flying_wing",
    "revival_staff",
    "piercing_lance",
    "six_element_wheel",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TRIM_ROW = f"0,0,{CLIENT_ASSET_SIZE[0]},{CLIENT_ASSET_SIZE[1]}"


@dataclass(frozen=True)
class TrimPatchResult:
    payload: bytes
    original_rows: int
    added_keys: tuple[str, ...]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def icon_trim_keys() -> tuple[str, ...]:
    return tuple(f"{IMAGE_PREFIX}/{slug}" for slug in ICON_SLUGS)


def validate_icon_sources(icon_root: Path) -> None:
    """Verify the canonical source set without requiring an image library."""
    expected = {f"{slug}.png" for slug in ICON_SLUGS}
    if not icon_root.is_dir():
        raise FileNotFoundError(f"missing Fantasy icon directory: {icon_root}")
    actual = {path.name for path in icon_root.iterdir() if path.is_file()}
    missing = sorted(expected.difference(actual))
    unexpected = sorted(actual.difference(expected))
    if missing or unexpected:
        raise ValueError(
            "Fantasy icon directory must contain exactly the canonical 11 PNGs: "
            f"missing={missing}, unexpected={unexpected}"
        )

    digests: dict[str, str] = {}
    for name in sorted(expected):
        payload = (icon_root / name).read_bytes()
        if len(payload) < 33 or payload[:8] != PNG_SIGNATURE:
            raise ValueError(f"{name} is not a standard PNG")
        if int.from_bytes(payload[8:12], "big") != 13 or payload[12:16] != b"IHDR":
            raise ValueError(f"{name} has no canonical PNG IHDR")
        width = int.from_bytes(payload[16:20], "big")
        height = int.from_bytes(payload[20:24], "big")
        if (width, height) != CLIENT_ASSET_SIZE:
            raise ValueError(f"{name} must be 20x20, got {width}x{height}")
        if payload[24] != 8 or payload[25] != 6:
            raise ValueError(f"{name} must be 8-bit RGBA PNG")
        expected_crc = int.from_bytes(payload[29:33], "big")
        actual_crc = zlib.crc32(payload[12:29]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise ValueError(f"{name} has an invalid IHDR CRC")
        digest = sha256_bytes(payload)
        duplicate = digests.get(digest)
        if duplicate is not None:
            raise ValueError(f"duplicate icon content: {duplicate} and {name}")
        digests[digest] = name


def _archive_names(patch: dict) -> list[str]:
    names: list[str] = []
    integrity = patch.get("archive_integrity")
    if isinstance(integrity, list):
        for item in integrity:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name not in names:
                names.append(name)
    archive = patch.get("archive")
    if isinstance(archive, str) and archive not in names:
        names.append(archive)
    return names


def find_latest_trim_payload(
    manifest: dict, active_root: Path
) -> tuple[bytes, str, str]:
    """Resolve the final trim table from manifest order, not filename order."""
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        raise ValueError("manifest patches must be an array")

    found: tuple[bytes, str, str] | None = None
    for patch in patches:
        if not isinstance(patch, dict) or patch.get("enabled") is False:
            continue
        patch_id = str(patch.get("id", "<unnamed>"))
        for archive_name in _archive_names(patch):
            archive_path = active_root / archive_name
            if not archive_path.is_file():
                raise FileNotFoundError(
                    f"manifest archive is missing: {archive_path}"
                )
            with zipfile.ZipFile(archive_path) as archive:
                if TRIMMED_MEMBER in archive.namelist():
                    found = (
                        archive.read(TRIMMED_MEMBER),
                        patch_id,
                        archive_name,
                    )
    if found is None:
        raise ValueError(
            f"active manifest chain does not contain {TRIMMED_MEMBER}"
        )
    return found


def patch_trimmed_image(base_payload: bytes) -> TrimPatchResult:
    """Append the 11 full-frame rows and prove all old raw rows are unchanged."""
    ordered = core.read_orderedmap_raw_rows_from_bytes(
        base_payload, TRIMMED_LOGICAL
    )
    if len(ordered.keys) != len(ordered.rows):
        raise ValueError("trimmed_image key/row count mismatch")
    if len(set(ordered.keys)) != len(ordered.keys):
        raise ValueError("trimmed_image contains duplicate keys")

    original_keys = tuple(ordered.keys)
    # This strict reader intentionally returns the exact compressed row chunks.
    # Reusing those chunks avoids recompressing or otherwise rewriting 11,818
    # unrelated records.
    original_rows = tuple(ordered.rows)
    existing = dict(zip(original_keys, original_rows))
    expected_row = TRIM_ROW.encode("utf-8")
    additions: list[str] = []
    for key in icon_trim_keys():
        current = existing.get(key)
        if current is None:
            additions.append(key)
            continue
        try:
            current_text = zlib.decompress(current) if current else b""
        except zlib.error as exc:
            raise ValueError(f"invalid compressed trim row for {key}") from exc
        if current_text != expected_row:
            raise ValueError(
                f"conflicting trim row for {key}: {current_text!r}, "
                f"expected {expected_row!r}"
            )

    for key in additions:
        ordered.keys.append(key)
        ordered.rows.append(zlib.compress(expected_row))
    payload = core.build_orderedmap_raw_rows(ordered)
    verified = core.read_orderedmap_raw_rows_from_bytes(
        payload, TRIMMED_LOGICAL
    )
    if tuple(verified.keys[: len(original_keys)]) != original_keys:
        raise RuntimeError("existing trimmed_image key order changed")
    if tuple(verified.rows[: len(original_rows)]) != original_rows:
        raise RuntimeError("existing trimmed_image rows changed")
    if tuple(verified.keys[len(original_keys) :]) != tuple(additions):
        raise RuntimeError("new trimmed_image keys were not appended canonically")
    for key in icon_trim_keys():
        index = verified.keys.index(key)
        if zlib.decompress(verified.rows[index]) != expected_row:
            raise RuntimeError(f"trimmed_image readback mismatch: {key}")

    return TrimPatchResult(
        payload=payload,
        original_rows=len(original_keys),
        added_keys=tuple(additions),
    )


def build_archive(payload: bytes) -> bytes:
    """Create a deterministic one-member ZIP for the changed table."""
    output = io.BytesIO()
    info = zipfile.ZipInfo(TRIMMED_MEMBER, (2026, 8, 15, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(info, payload)
    result = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        if archive.namelist() != [TRIMMED_MEMBER]:
            raise RuntimeError("unexpected icon-trim archive members")
        if archive.read(TRIMMED_MEMBER) != payload:
            raise RuntimeError("icon-trim archive readback mismatch")
    return result


def build_patch_entry(archive_payload: bytes, added_keys: tuple[str, ...]) -> dict:
    return {
        "id": PATCH_ID,
        "type": "patch",
        "name": "幻想装备图标生命周期修复 1.4.78",
        "description": (
            "为11张自制幻想装备图标补齐完整画布裁剪记录，使客户端使用可独立释放的子纹理，"
            "避免装备列表反复打开或长时间游玩后图标变空；PNG与APK均不变。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive_payload),
        "files": [TRIMMED_MEMBER],
        "changes": [
            f"为{len(added_keys)}张幻想装备图标补入 {TRIM_ROW} 的 trimmed_image 记录。",
            "保留原裁剪表全部键序与行内容，仅在表尾追加缺失记录。",
            "不重复发布PNG，不修改APK。",
        ],
        "created_at": CREATED_AT,
        "archive_integrity": [
            {
                "name": ARCHIVE_NAME,
                "size": len(archive_payload),
                "sha256": sha256_bytes(archive_payload),
                "members": 1,
            }
        ],
    }


def validate_published_patch(
    manifest: dict, active_root: Path, expected_payload: bytes | None = None
) -> None:
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        raise ValueError("manifest patches must be an array")
    matches = [patch for patch in patches if patch.get("id") == PATCH_ID]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {PATCH_ID} manifest entry")
    patch = matches[0]
    if manifest.get("cdn_version") != PATCH_VERSION:
        raise ValueError("published manifest tail is not 1.4.78")
    if patch.get("version") != PATCH_VERSION or patch.get("depends_on") != BASE_VERSION:
        raise ValueError("published icon-trim edge is invalid")
    archive_path = active_root / ARCHIVE_NAME
    archive_payload = archive_path.read_bytes()
    integrity = patch.get("archive_integrity")
    if not isinstance(integrity, list) or len(integrity) != 1:
        raise ValueError("icon-trim archive integrity is missing")
    receipt = integrity[0]
    if receipt.get("size") != len(archive_payload):
        raise ValueError("icon-trim archive size receipt mismatch")
    if receipt.get("sha256") != sha256_bytes(archive_payload):
        raise ValueError("icon-trim archive hash receipt mismatch")
    with zipfile.ZipFile(io.BytesIO(archive_payload)) as archive:
        if archive.namelist() != [TRIMMED_MEMBER]:
            raise ValueError("icon-trim archive member list mismatch")
        payload = archive.read(TRIMMED_MEMBER)
    if expected_payload is not None and payload != expected_payload:
        raise ValueError("published trim payload differs from generated payload")
    verified = core.read_orderedmap_raw_rows_from_bytes(payload, TRIMMED_LOGICAL)
    rows = dict(zip(verified.keys, verified.rows))
    expected_row = TRIM_ROW.encode("utf-8")
    for key in icon_trim_keys():
        compressed = rows.get(key)
        if compressed is None or zlib.decompress(compressed) != expected_row:
            raise ValueError(f"published trim record is missing or wrong: {key}")


def publish(
    manifest_path: Path = MANIFEST_PATH,
    active_root: Path = ACTIVE_ROOT,
    store_root: Path = STORE_ROOT,
    icon_root: Path = ICON_ROOT,
) -> TrimPatchResult:
    validate_icon_sources(icon_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        raise ValueError("manifest patches must be an array")

    existing = [patch for patch in patches if patch.get("id") == PATCH_ID]
    if existing:
        validate_published_patch(manifest, active_root)
        archive_path = active_root / ARCHIVE_NAME
        with zipfile.ZipFile(archive_path) as archive:
            payload = archive.read(TRIMMED_MEMBER)
        ordered = core.read_orderedmap_raw_rows_from_bytes(payload, TRIMMED_LOGICAL)
        return TrimPatchResult(payload, len(ordered.keys) - len(icon_trim_keys()), ())

    if manifest.get("cdn_version") != BASE_VERSION:
        raise ValueError(
            f"expected manifest tail {BASE_VERSION}, got "
            f"{manifest.get('cdn_version')!r}"
        )
    if any(patch.get("version") == PATCH_VERSION for patch in patches):
        raise ValueError(f"manifest already contains another {PATCH_VERSION} patch")

    base_payload, source_patch, source_archive = find_latest_trim_payload(
        manifest, active_root
    )
    result = patch_trimmed_image(base_payload)
    if len(result.added_keys) != len(icon_trim_keys()):
        raise ValueError(
            "base chain already contains some/all Fantasy trim rows; "
            "refusing an ambiguous publication"
        )
    archive_payload = build_archive(result.payload)
    patches.append(build_patch_entry(archive_payload, result.added_keys))
    manifest["cdn_version"] = PATCH_VERSION

    active_root.mkdir(parents=True, exist_ok=True)
    archive_path = active_root / ARCHIVE_NAME
    archive_tmp = archive_path.with_suffix(".zip.tmp")
    manifest_tmp = manifest_path.with_suffix(".json.tmp")
    if archive_tmp.exists() or manifest_tmp.exists():
        raise FileExistsError("stale publication temporary file exists")
    archive_tmp.write_bytes(archive_payload)
    manifest_tmp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        archive_tmp.replace(archive_path)
        manifest_tmp.replace(manifest_path)
    finally:
        archive_tmp.unlink(missing_ok=True)
        manifest_tmp.unlink(missing_ok=True)

    store_path = store_root / TRIMMED_RELATIVE
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_bytes(result.payload)

    written_manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    validate_published_patch(written_manifest, active_root, result.payload)
    print(f"published: {BASE_VERSION} -> {PATCH_VERSION}")
    print(f"source: {source_patch} / {source_archive}")
    print(f"rows: {result.original_rows} + {len(result.added_keys)}")
    print(f"archive: {archive_path}")
    print(f"archive sha256: {sha256_bytes(archive_payload)}")
    print(f"table sha256: {sha256_bytes(result.payload)}")
    return result


def main() -> int:
    publish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
