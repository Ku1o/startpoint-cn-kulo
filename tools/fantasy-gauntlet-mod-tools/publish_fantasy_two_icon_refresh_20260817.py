#!/usr/bin/env python3
"""Publish the two approved Fantasy equipment icons as ResVer 1.4.81."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

from PIL import Image

import wf_assets
import wf_mod_tool as core


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
DEPLOY_ROOT = Path(r"F:\startpoint-cn-main")
BACKUP_ROOT = Path(r"F:\codex\local-deploy-backups")
BASE_VERSION = "1.4.80"
PATCH_VERSION = "1.4.81"
PATCH_ID = "fantasy-two-icon-refresh-1.4.81"
ARCHIVE_NAME = "pinball-1.4.80-1.4.81-1-0817-fantasy-two-icon-refresh.zip"
IMAGE_PREFIX = "item/equipment/mod/fantasy"
TRIMMED_LOGICAL = "master/generated/trimmed_image.orderedmap"
TRIMMED_KEY_ROW = b"0,0,20,20"

ICONS = (
    {
        "id": "100021",
        "name": "冥灯返魂杖",
        "slug": "revival_staff",
        "input": Path(r"F:\冥灯返魂杖.png"),
        "input_sha256": "3188f3c9c834b77b21b8a5981fee9ecd51a5a675f37d6af503e2ba1345250349",
        "old_sha256": "1b2922d0f48bcc6664984b3ee697ac0a6be51b73df4d72ffbaa8924d86235753",
    },
    {
        "id": "100022",
        "name": "无界贯星枪",
        "slug": "piercing_lance",
        "input": Path(r"F:\无界贯星枪.png"),
        "input_sha256": "cbedb421db1c196beaa9a14bd2e319890792491d21af3a7a77fa4ab8da853d6a",
        "old_sha256": "44287417e574ef6817684b2f39963cdaa840a02109a5107576fffb870efcb478",
    },
)


class PublishError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def logical_path(icon: dict) -> str:
    return f"{IMAGE_PREFIX}/{icon['slug']}.png"


def member_name(icon: dict) -> str:
    digest = core.sha1_path(logical_path(icon))
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def live_path(root: Path, icon: dict) -> Path:
    digest = core.sha1_path(logical_path(icon))
    return root / "assets/asset-patch/production/upload" / digest[:2] / digest[2:]


def canonical_path(root: Path, icon: dict) -> Path:
    return (
        root
        / "tools/fantasy-gauntlet-mod-tools/assets/fantasy-equipment"
        / f"{icon['slug']}.png"
    )


def validate_png(icon: dict) -> bytes:
    path = icon["input"]
    raw = path.read_bytes()
    if sha256_bytes(raw) != icon["input_sha256"]:
        raise PublishError(f"input icon changed after approval: {path}")
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if image.format != "PNG" or image.size != (20, 20) or image.mode != "RGBA":
            raise PublishError(
                f"{path} must be a native 20x20 RGBA PNG, got "
                f"{image.format} {image.size} {image.mode}"
            )
        if image.getchannel("A").getextrema() != (0, 255):
            raise PublishError(f"{path} must contain transparent and opaque pixels")
    encoded = wf_assets.png_encode(raw)
    if wf_assets.png_decode(encoded) != raw:
        raise PublishError(f"client PNG codec round-trip failed: {path}")
    return raw


def validate_current_state(root: Path) -> tuple[dict, bytes]:
    manifest_path = root / "assets/asset-patch/manifest.json"
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8-sig"))
    if manifest.get("cdn_version") != "1.4.79":
        raise PublishError(f"unexpected base manifest version: {manifest_path}")
    if any(patch.get("id") == PATCH_ID for patch in manifest.get("patches", [])):
        raise PublishError(f"patch already exists: {manifest_path}")
    if any(patch.get("version") == PATCH_VERSION for patch in manifest.get("patches", [])):
        raise PublishError(f"another {PATCH_VERSION} patch already exists: {manifest_path}")

    active_path = root / ".cdn/cn/character-releases/active.json"
    active = json.loads(active_path.read_text(encoding="utf-8-sig"))
    releases = active.get("releases")
    if not isinstance(releases, list) or len(releases) != 1:
        raise PublishError(f"unexpected active character release: {active_path}")
    release = releases[0]
    if release.get("version") != BASE_VERSION or release.get("from_version") != "1.4.79":
        raise PublishError(f"active release is not the expected 1.4.80 edge: {active_path}")

    common = [item for item in release.get("archives", []) if item.get("root") == "common"]
    if len(common) != 1:
        raise PublishError(f"active release has no unique common archive: {active_path}")
    archive = root / ".cdn/cn" / common[0]["relative_path"]
    trim_digest = core.sha1_path(TRIMMED_LOGICAL)
    trim_member = f"production/upload/{trim_digest[:2]}/{trim_digest[2:]}"
    with zipfile.ZipFile(archive) as bundle:
        if trim_member not in bundle.namelist():
            raise PublishError(f"active 1.4.80 archive lacks trimmed_image: {archive}")
        trim_payload = bundle.read(trim_member)
    trim = core.read_orderedmap_raw_rows_from_bytes(trim_payload, TRIMMED_LOGICAL)
    rows = dict(zip(trim.keys, trim.rows))
    for icon in ICONS:
        key = f"{IMAGE_PREFIX}/{icon['slug']}"
        row = rows.get(key)
        if row is None or zlib.decompress(row) != TRIMMED_KEY_ROW:
            raise PublishError(f"trimmed_image is missing the full-frame row: {key}")

    for icon in ICONS:
        canonical = canonical_path(root, icon)
        if not canonical.is_file() or sha256_bytes(canonical.read_bytes()) != icon["old_sha256"]:
            raise PublishError(f"canonical old icon drifted: {canonical}")
    return manifest, trim_payload


def validate_candidate_icon_set(root: Path, inputs: dict[str, bytes]) -> None:
    icon_root = root / "tools/fantasy-gauntlet-mod-tools/assets/fantasy-equipment"
    expected = {
        "skill_core", "direct_blade", "powerflip_hammer", "multiball_hangar",
        "ability_terminal", "fever_ring", "adversity_sword", "flying_wing",
        "revival_staff", "piercing_lance", "six_element_wheel",
    }
    actual = {path.stem for path in icon_root.glob("*.png")}
    if actual != expected:
        raise PublishError("canonical Fantasy icon set is not the expected 11 files")
    hashes: dict[str, str] = {}
    for slug in sorted(expected):
        raw = inputs.get(slug, (icon_root / f"{slug}.png").read_bytes())
        digest = sha256_bytes(raw)
        if digest in hashes:
            raise PublishError(f"duplicate candidate icons: {hashes[digest]} and {slug}")
        hashes[digest] = slug


def build_archive(encoded: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for member in sorted(encoded):
            info = zipfile.ZipInfo(member, (2026, 8, 17, 16, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, encoded[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(encoded):
            raise PublishError("icon archive member order mismatch")
        for member, payload in encoded.items():
            if archive.read(member) != payload:
                raise PublishError(f"icon archive readback mismatch: {member}")
    return raw


def updated_manifest(manifest: dict, archive: bytes, encoded: dict[str, bytes]) -> bytes:
    value = json.loads(json.dumps(manifest))
    members = sorted(encoded)
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "幻想连战两件装备图标更新 1.4.81",
        "description": (
            "替换冥灯返魂杖与无界贯星枪的20×20像素图标；"
            "沿用现有完整画布裁剪记录，不修改装备数值、词条、商店或其他素材。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "files": members,
        "changes": [
            "冥灯返魂杖（100021）替换为用户提供的新图标。",
            "无界贯星枪（100022）替换为用户提供的新图标。",
            "复核 trimmed_image 两键均为 0,0,20,20；裁剪表无需改写。",
        ],
        "created_at": "2026-08-17",
        "archive_integrity": [{
            "name": ARCHIVE_NAME,
            "size": len(archive),
            "sha256": sha256_bytes(archive),
            "members": len(members),
        }],
    })
    value["cdn_version"] = PATCH_VERSION
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".fantasy-icon-refresh.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def safe_unlink(path: Path, allowed_root: Path) -> None:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(allowed_root.resolve(strict=True))
    except ValueError as exc:
        raise PublishError(f"refusing to delete outside allowed root: {resolved}") from exc
    if path.exists():
        if not path.is_file():
            raise PublishError(f"refusing to delete non-file path: {path}")
        path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    inputs = {icon["slug"]: validate_png(icon) for icon in ICONS}
    for root in (SOURCE_ROOT, DEPLOY_ROOT):
        validate_candidate_icon_set(root, inputs)
    source_manifest, source_trim = validate_current_state(SOURCE_ROOT)
    deploy_manifest, deploy_trim = validate_current_state(DEPLOY_ROOT)
    if source_manifest != deploy_manifest or source_trim != deploy_trim:
        raise PublishError("source and deployed base states differ")

    encoded = {
        member_name(icon): wf_assets.png_encode(inputs[icon["slug"]])
        for icon in ICONS
    }
    archive = build_archive(encoded)
    manifest_raw = updated_manifest(source_manifest, archive, encoded)
    report = {
        "apply": args.apply,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "archive_sha256": sha256_bytes(archive),
        "trimmed_image_sha256_unchanged": sha256_bytes(source_trim),
        "icons": [
            {
                "id": icon["id"],
                "name": icon["name"],
                "logical_path": logical_path(icon),
                "member": member_name(icon),
                "source_sha256": sha256_bytes(inputs[icon["slug"]]),
                "encoded_sha256": sha256_bytes(encoded[member_name(icon)]),
                "trim": TRIMMED_KEY_ROW.decode("ascii"),
            }
            for icon in ICONS
        ],
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_ROOT / f"fantasy-two-icon-refresh-1.4.81-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    targets: dict[str, Path] = {}
    for label, root in (("source", SOURCE_ROOT), ("deploy", DEPLOY_ROOT)):
        targets[f"{label}-manifest.json"] = root / "assets/asset-patch/manifest.json"
        targets[f"{label}-archive.zip"] = root / "assets/asset-patch/active" / ARCHIVE_NAME
        for icon in ICONS:
            slug = icon["slug"]
            targets[f"{label}-canonical-{slug}.png"] = canonical_path(root, icon)
            targets[f"{label}-live-{slug}"] = live_path(root, icon)
    existed: dict[str, bool] = {}
    for name, path in targets.items():
        existed[name] = path.is_file()
        if existed[name]:
            shutil.copy2(path, backup / name)
    (backup / "existence.json").write_text(
        json.dumps(existed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    try:
        for root in (SOURCE_ROOT, DEPLOY_ROOT):
            atomic_write(archive, root / "assets/asset-patch/active" / ARCHIVE_NAME)
            for icon in ICONS:
                raw = inputs[icon["slug"]]
                atomic_write(raw, canonical_path(root, icon))
                atomic_write(encoded[member_name(icon)], live_path(root, icon))
        atomic_write(manifest_raw, SOURCE_ROOT / "assets/asset-patch/manifest.json")
        atomic_write(manifest_raw, DEPLOY_ROOT / "assets/asset-patch/manifest.json")

        for root in (SOURCE_ROOT, DEPLOY_ROOT):
            written = json.loads(
                (root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
            )
            if written.get("cdn_version") != PATCH_VERSION:
                raise PublishError("manifest version readback failed")
            matches = [patch for patch in written["patches"] if patch.get("id") == PATCH_ID]
            if len(matches) != 1:
                raise PublishError("manifest patch readback failed")
            archive_path = root / "assets/asset-patch/active" / ARCHIVE_NAME
            if archive_path.read_bytes() != archive:
                raise PublishError("archive readback failed")
            for icon in ICONS:
                if canonical_path(root, icon).read_bytes() != inputs[icon["slug"]]:
                    raise PublishError("canonical icon readback failed")
                stored = live_path(root, icon).read_bytes()
                if wf_assets.png_decode(stored) != inputs[icon["slug"]]:
                    raise PublishError("live icon readback failed")
    except Exception:
        for name, path in targets.items():
            if existed[name]:
                atomic_write((backup / name).read_bytes(), path)
            elif path.exists():
                safe_unlink(path, path.parent)
        raise

    report["backup"] = str(backup)
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
