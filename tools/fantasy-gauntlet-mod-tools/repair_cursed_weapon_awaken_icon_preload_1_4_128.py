#!/usr/bin/env python3
"""Build the 1.4.127 -> 1.4.128 preload closure for the cursed awakening material.

The item row and standalone 20x20 PNG for item 10000311 already exist, but
``DialogVariationTitleView`` reads the thumbnail synchronously from the
preloaded ``item/sprite_sheet`` atlas.  Append the exact existing pixels as a
new atlas frame while preserving every baseline pixel and frame record.

This builder writes only the active archive and its static audit report.  It
does not edit the CDN manifest; registration is a separate, explicit step.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[2]
TOOLS = HERE.parent
sys.path.insert(0, str(TOOLS))
import wf_battle_atlas_repack as atlas_codec  # noqa: E402
import wf_quest_lib as quest  # noqa: E402

PATCH_ID = "cursed-weapon-awakening-icon-preload-1.4.128"
BASE_VERSION = "1.4.127"
PATCH_VERSION = "1.4.128"
SOURCE_ARCHIVE = "pinball-1.4.122-1.4.123-1-author-weapons-fiveboss-20261001.zip"
SOURCE_ARCHIVE_SHA256 = "967dd40c45a9b5c7c6ad0ba164a2a413b82217c33fa0e3f510ac0a760ea02a06"
OUTPUT_ARCHIVE = "pinball-1.4.127-1.4.128-1-cursed-weapon-awakening-icon-preload-20261002.zip"
SHEET_LOGICAL = "item/sprite_sheet.png"
ATLAS_LOGICAL = "item/sprite_sheet.atlas.amf3.deflate"
ICON_LOGICAL = "item/materials/mod/cursed/forbidden_star_steel.png"
ICON_NAME = "item/materials/mod/cursed/forbidden_star_steel"
ITEM_ID = 10000311


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def member_name(logical: str) -> str:
    return "production/upload/" + quest.hashed_rel(logical)


def read_member(archive: Path, logical: str) -> bytes:
    with zipfile.ZipFile(archive) as source:
        return source.read(member_name(logical))


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 2, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, payloads[name])
    result = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        if sorted(archive.namelist()) != sorted(payloads):
            raise ValueError("output archive member set differs")
        for name, expected in payloads.items():
            if archive.read(name) != expected:
                raise ValueError(f"output archive payload differs: {name}")
    return result


def build(source_archive: Path) -> tuple[dict[str, bytes], dict]:
    if sha256(source_archive.read_bytes()) != SOURCE_ARCHIVE_SHA256:
        raise ValueError("the reviewed source archive changed")

    source_sheet_raw = read_member(source_archive, SHEET_LOGICAL)
    source_atlas_raw = read_member(source_archive, ATLAS_LOGICAL)
    source_icon_raw = read_member(source_archive, ICON_LOGICAL)
    source_sheet = atlas_codec.decode_png(source_sheet_raw)
    source_atlas = atlas_codec.decode_atlas(source_atlas_raw)
    icon = atlas_codec.decode_png(source_icon_raw)

    if source_sheet.mode != "RGBA" or source_sheet.size != (505, 1836):
        raise ValueError(f"unexpected source item sheet: {source_sheet.mode} {source_sheet.size}")
    if len(source_atlas) != 1525:
        raise ValueError(f"unexpected source item atlas frame count: {len(source_atlas)}")
    if icon.mode != "RGBA" or icon.size != (20, 20) or icon.getbbox() is None:
        raise ValueError("invalid forbidden star steel source icon")
    if any(row.get("n") == ICON_NAME for row in source_atlas):
        raise ValueError("forbidden star steel is already present in item/sprite_sheet")
    if source_icon_raw[:8] != b"\x89png\r\n\x1a\n":
        raise ValueError("source icon does not use the stored PNG signature")

    frame = {"n": ICON_NAME, "w": 20, "h": 20, "x": 1, "y": source_sheet.height + 1}
    output_sheet = Image.new("RGBA", (source_sheet.width, source_sheet.height + 22))
    output_sheet.paste(source_sheet, (0, 0))
    output_sheet.paste(icon, (frame["x"], frame["y"]))
    output_atlas = source_atlas + [frame]
    sheet_payload = atlas_codec.encode_png(output_sheet)
    atlas_payload = atlas_codec.encode_atlas(output_atlas)

    decoded_sheet = atlas_codec.decode_png(sheet_payload)
    decoded_atlas = atlas_codec.decode_atlas(atlas_payload)
    if decoded_sheet.size != output_sheet.size or decoded_sheet.tobytes() != output_sheet.tobytes():
        raise ValueError("encoded item sheet differs from construction")
    if decoded_sheet.crop((0, 0, source_sheet.width, source_sheet.height)).tobytes() != source_sheet.tobytes():
        raise ValueError("baseline item sheet pixels changed")
    if decoded_atlas[: len(source_atlas)] != source_atlas or decoded_atlas[-1] != frame:
        raise ValueError("baseline item atlas records changed")
    crop = decoded_sheet.crop((frame["x"], frame["y"], frame["x"] + 20, frame["y"] + 20))
    if crop.tobytes() != icon.tobytes():
        raise ValueError("appended forbidden star steel pixels changed")
    if sheet_payload[:8] != b"\x89png\r\n\x1a\n":
        raise ValueError("encoded item sheet does not use the stored PNG signature")

    payloads = {
        member_name(SHEET_LOGICAL): sheet_payload,
        member_name(ATLAS_LOGICAL): atlas_payload,
    }
    report = {
        "patch_id": PATCH_ID,
        "base_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "source_archive": SOURCE_ARCHIVE,
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "item_id": ITEM_ID,
        "thumbnail_logical": ICON_NAME,
        "source_icon_logical": ICON_LOGICAL,
        "source_icon_sha256": sha256(source_icon_raw),
        "source_icon_dimensions": list(icon.size),
        "baseline_sheet_dimensions": list(source_sheet.size),
        "output_sheet_dimensions": list(decoded_sheet.size),
        "baseline_frame_count": len(source_atlas),
        "output_frame_count": len(decoded_atlas),
        "added_frame": frame,
        "baseline_pixels_preserved": True,
        "baseline_frame_metadata_preserved": True,
        "source_icon_pixels_preserved": True,
        "item_table_changed": False,
        "common_android_ios_pair": True,
        "platform_atf_required": False,
        "output_members": [
            {"logical": logical, "member": member_name(logical), "sha256": sha256(payloads[member_name(logical)])}
            for logical in (SHEET_LOGICAL, ATLAS_LOGICAL)
        ],
        "validation": "static atlas decode, PNG signature, pixel preservation and archive readback; no device test",
    }
    return payloads, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the active archive and audit report")
    args = parser.parse_args(argv)

    active = REPO_ROOT / "assets" / "asset-patch" / "active"
    source_archive = active / SOURCE_ARCHIVE
    payloads, content_report = build(source_archive)
    archive_bytes = zip_payloads(payloads)
    archive_sha256 = sha256(archive_bytes)
    archive_path = active / OUTPUT_ARCHIVE
    audit_directory = f"assets/asset-patch/audit/{PATCH_ID}"
    entry = {
        "id": PATCH_ID,
        "type": "patch",
        "name": "诅咒武器觉醒素材缩略图预加载修复",
        "description": "将禁忌星铁已有的 20×20 原图补入常驻 item/sprite_sheet 图集，修复觉醒弹窗同步取图 C8004；不改玩法表或服务端。",
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "candidate_only": True,
        "archive": OUTPUT_ARCHIVE,
        "archive_size": len(archive_bytes),
        "files": sorted(payloads),
        "changes": [
            "保留当前 1525 个物品图集帧及全部原始像素，仅追加 item/materials/mod/cursed/forbidden_star_steel。",
            "复用现有禁忌星铁 PNG 像素，补齐 DialogVariationTitleView 的同步预加载闭包。",
            "common PNG 与 atlas 同时供 Android 和 iOS 使用，不增加平台专属 ATF。",
        ],
        "created_at": "2026-10-02",
        "audit": {"directory": audit_directory, "report": "report.json"},
        "archive_integrity": [{"name": OUTPUT_ARCHIVE, "size": len(archive_bytes), "sha256": archive_sha256, "members": len(payloads)}],
        "chain": [OUTPUT_ARCHIVE],
    }
    report = {**content_report, "archive": entry}
    if args.write:
        if archive_path.exists() and sha256(archive_path.read_bytes()) != archive_sha256:
            raise ValueError("refusing to replace a different existing repair archive")
        if not archive_path.exists():
            archive_path.write_bytes(archive_bytes)
        audit_path = REPO_ROOT / audit_directory / "report.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive_path), "archive_size": len(archive_bytes), "archive_sha256": archive_sha256, "members": len(payloads), "written": args.write, "manifest_entry": entry}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
