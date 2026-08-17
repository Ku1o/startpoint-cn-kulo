#!/usr/bin/env python3
"""Fold the approved Fantasy equipment icon refresh into ResVer 1.4.80.

This supersedes the temporary 1.4.80 -> 1.4.81 icon-only edge.  The two
payloads are published as a parallel 1.4.79 -> 1.4.80 common patch while the
existing swim-EX character release and trimmed_image table remain untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
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
BASE_VERSION = "1.4.79"
PATCH_VERSION = "1.4.80"
OLD_PATCH_ID = "fantasy-two-icon-refresh-1.4.81"
OLD_ARCHIVE_NAME = "pinball-1.4.80-1.4.81-1-0817-fantasy-two-icon-refresh.zip"
PATCH_ID = "fantasy-two-icon-refresh-1.4.80"
ARCHIVE_NAME = "pinball-1.4.79-1.4.80-2-0817-fantasy-two-icon-refresh.zip"
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
    },
    {
        "id": "100022",
        "name": "无界贯星枪",
        "slug": "piercing_lance",
        "input": Path(r"F:\无界贯星枪.png"),
        "input_sha256": "cbedb421db1c196beaa9a14bd2e319890792491d21af3a7a77fa4ab8da853d6a",
    },
)


class PublishError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    raw = icon["input"].read_bytes()
    if sha256_bytes(raw) != icon["input_sha256"]:
        raise PublishError(f"approved input changed: {icon['input']}")
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if image.format != "PNG" or image.size != (20, 20) or image.mode != "RGBA":
            raise PublishError(f"icon must be a native 20x20 RGBA PNG: {icon['input']}")
        if image.getchannel("A").getextrema() != (0, 255):
            raise PublishError(f"icon transparency is invalid: {icon['input']}")
    encoded = wf_assets.png_encode(raw)
    if wf_assets.png_decode(encoded) != raw:
        raise PublishError(f"client PNG codec round-trip failed: {icon['input']}")
    return raw


def active_trim_payload(root: Path) -> tuple[bytes, bytes]:
    active_path = root / ".cdn/cn/character-releases/active.json"
    active_raw = active_path.read_bytes()
    active = json.loads(active_raw.decode("utf-8-sig"))
    releases = active.get("releases")
    if active.get("base_version") != BASE_VERSION or not isinstance(releases, list) or len(releases) != 1:
        raise PublishError(f"unexpected active character release: {active_path}")
    release = releases[0]
    if release.get("from_version") != BASE_VERSION or release.get("version") != PATCH_VERSION:
        raise PublishError(f"active release is not the expected 1.4.80 edge: {active_path}")
    common = [item for item in release.get("archives", []) if item.get("root") == "common"]
    if len(common) != 1:
        raise PublishError(f"active release has no unique common archive: {active_path}")
    archive = root / ".cdn/cn" / str(common[0]["relative_path"])
    if archive.stat().st_size != common[0].get("size") or sha256_file(archive) != common[0].get("sha256"):
        raise PublishError(f"active common archive receipt drifted: {archive}")
    digest = core.sha1_path(TRIMMED_LOGICAL)
    member = f"production/upload/{digest[:2]}/{digest[2:]}"
    with zipfile.ZipFile(archive) as bundle:
        trim_payload = bundle.read(member)
    trim = core.read_orderedmap_raw_rows_from_bytes(trim_payload, TRIMMED_LOGICAL)
    rows = dict(zip(trim.keys, trim.rows))
    for icon in ICONS:
        key = f"{IMAGE_PREFIX}/{icon['slug']}"
        if key not in rows or zlib.decompress(rows[key]) != TRIMMED_KEY_ROW:
            raise PublishError(f"trimmed_image row is missing or wrong: {key}")
    return active_raw, trim_payload


def validate_current_state(root: Path, inputs: dict[str, bytes]) -> tuple[dict, bytes, bytes]:
    manifest_path = root / "assets/asset-patch/manifest.json"
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8-sig"))
    if manifest.get("cdn_version") != "1.4.81":
        raise PublishError(f"expected the temporary 1.4.81 publication: {manifest_path}")
    old = [patch for patch in manifest.get("patches", []) if patch.get("id") == OLD_PATCH_ID]
    if len(old) != 1 or old[0].get("archive") != OLD_ARCHIVE_NAME:
        raise PublishError(f"temporary 1.4.81 patch entry drifted: {manifest_path}")
    if any(patch.get("id") == PATCH_ID for patch in manifest.get("patches", [])):
        raise PublishError(f"1.4.80 icon patch already exists: {manifest_path}")
    old_archive = root / "assets/asset-patch/active" / OLD_ARCHIVE_NAME
    if not old_archive.is_file() or sha256_file(old_archive) != "6b296d8a9194ab3d81c65e393fbf268e43005facac8e3d0dd28455cafdcc4527":
        raise PublishError(f"temporary 1.4.81 archive drifted: {old_archive}")
    new_archive = root / "assets/asset-patch/active" / ARCHIVE_NAME
    if new_archive.exists():
        raise PublishError(f"target 1.4.80 archive already exists: {new_archive}")
    for icon in ICONS:
        expected = inputs[icon["slug"]]
        if canonical_path(root, icon).read_bytes() != expected:
            raise PublishError(f"canonical icon is not the approved payload: {icon['slug']}")
        if wf_assets.png_decode(live_path(root, icon).read_bytes()) != expected:
            raise PublishError(f"live icon is not the approved payload: {icon['slug']}")
    active_raw, trim_payload = active_trim_payload(root)
    return manifest, active_raw, trim_payload


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
            raise PublishError("archive member order mismatch")
        for member, payload in encoded.items():
            if archive.read(member) != payload:
                raise PublishError(f"archive payload mismatch: {member}")
    return raw


def updated_manifest(manifest: dict, archive: bytes, encoded: dict[str, bytes]) -> bytes:
    value = json.loads(json.dumps(manifest))
    value["patches"] = [patch for patch in value["patches"] if patch.get("id") != OLD_PATCH_ID]
    members = sorted(encoded)
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "幻想连战两件装备图标更新 1.4.80",
        "description": (
            "替换冥灯返魂杖与无界贯星枪的20×20像素图标；"
            "与现有泳皇女EX更新共同发布在1.4.80，沿用其裁剪表。"
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
            "trimmed_image 两键继续使用 0,0,20,20，本补丁不改写裁剪表。",
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
    temporary = target.with_name(target.name + ".fantasy-icon-1.4.80.tmp")
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
    source_manifest, source_active, source_trim = validate_current_state(SOURCE_ROOT, inputs)
    deploy_manifest, deploy_active, deploy_trim = validate_current_state(DEPLOY_ROOT, inputs)
    if source_manifest != deploy_manifest:
        raise PublishError("source and deployed manifests differ")
    if source_active != deploy_active or source_trim != deploy_trim:
        raise PublishError("source and deployed active 1.4.80 releases differ")

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
        "removed_temporary_archive": OLD_ARCHIVE_NAME,
        "active_character_release_sha256_unchanged": sha256_bytes(source_active),
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
    backup = BACKUP_ROOT / f"fantasy-two-icon-refresh-fold-into-1.4.80-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    targets: dict[str, Path] = {}
    for label, root in (("source", SOURCE_ROOT), ("deploy", DEPLOY_ROOT)):
        targets[f"{label}-manifest.json"] = root / "assets/asset-patch/manifest.json"
        targets[f"{label}-old-1.4.81.zip"] = root / "assets/asset-patch/active" / OLD_ARCHIVE_NAME
        targets[f"{label}-new-1.4.80.zip"] = root / "assets/asset-patch/active" / ARCHIVE_NAME
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
        atomic_write(manifest_raw, SOURCE_ROOT / "assets/asset-patch/manifest.json")
        atomic_write(manifest_raw, DEPLOY_ROOT / "assets/asset-patch/manifest.json")
        for root in (SOURCE_ROOT, DEPLOY_ROOT):
            safe_unlink(root / "assets/asset-patch/active" / OLD_ARCHIVE_NAME, root)

        for root in (SOURCE_ROOT, DEPLOY_ROOT):
            written = json.loads(
                (root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
            )
            if written.get("cdn_version") != PATCH_VERSION:
                raise PublishError("manifest version readback failed")
            if len([patch for patch in written["patches"] if patch.get("id") == PATCH_ID]) != 1:
                raise PublishError("1.4.80 manifest patch readback failed")
            if any(patch.get("id") == OLD_PATCH_ID for patch in written["patches"]):
                raise PublishError("temporary 1.4.81 manifest entry remains")
            new_archive = root / "assets/asset-patch/active" / ARCHIVE_NAME
            if new_archive.read_bytes() != archive:
                raise PublishError("1.4.80 archive readback failed")
            if (root / "assets/asset-patch/active" / OLD_ARCHIVE_NAME).exists():
                raise PublishError("temporary 1.4.81 archive remains")
            active_raw, trim_payload = active_trim_payload(root)
            if active_raw != source_active or trim_payload != source_trim:
                raise PublishError("active 1.4.80 character release changed")
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
