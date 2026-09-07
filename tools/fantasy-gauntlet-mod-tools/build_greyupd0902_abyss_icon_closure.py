#!/usr/bin/env python3
"""Build a .97 -> .98 common-atlas repair without changing any game table.

The three abyss materials currently use the same logical name for their
thumbnail and small icon.  Their standalone PNGs exist in .97, but synchronous
small-icon readers cannot load them on demand.  Add the exact existing pixels
to the already preloaded item/sprite_sheet pair, retaining every old frame.
The common PNG/atlas pair is consumed by both Android and iOS.

This builder writes only its new archive and audit report.  Register the
reported entry in manifest.json separately; never rewrite the .96/.97 edges.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
import zlib
from pathlib import Path

from PIL import Image

import wf_battle_atlas_repack as atlas_codec
import wf_mod_tool as core


REPO_ROOT = Path(__file__).resolve().parents[2]
PATCH_ID = "greyupd0902-abyss-item-icon-closure-1.4.98"
BASE_VERSION = "1.4.97"
PATCH_VERSION = "1.4.98"
SOURCE_ARCHIVE = "pinball-1.4.96-1.4.97-1-greyupd0902-cdn-resource-recovery.zip"
SOURCE_ARCHIVE_SHA256 = "3150894f71aff238a4190730569edfa6e1a5a0c062b92e9fa8aa4b3e34073d4c"
TABLE_ARCHIVE = "pinball-1.4.95-1.4.96-1-cdn-consolidated-gerald0903.zip"
OUTPUT_ARCHIVE = "pinball-1.4.97-1.4.98-1-greyupd0902-abyss-item-icon-closure.zip"
SHEET_LOGICAL = "item/sprite_sheet.png"
ATLAS_LOGICAL = "item/sprite_sheet.atlas.amf3.deflate"
ITEM_LOGICAL = "master/item/item.orderedmap"
SOURCE_PAYLOAD_SHA256 = {
    SHEET_LOGICAL: "0f3c6d7c356196c688cb914eb7e8a85cd32506f72a86a361e5dffc25d2852b92",
    ATLAS_LOGICAL: "c9ede674ccbf3da1f4403734e909a3407afbf7f10dc4f2c35f631f2c89ea1b01",
    "item/materials/mod/abyss/abyss_coin.png": "114961cf0a62ac609b51d32e004ea0e6da186de974c21b63fdd86fb8e62af1b3",
    "item/materials/mod/abyss/abyss_core.png": "cc6722d3652a6409fbc09b947b56c9ca214e4ace255f07f7f5de2e1ba7b88e21",
    "item/materials/mod/abyss/abyss_seal.png": "0b392b057079b4f1997fd5debddefe6e945758f3cd5f611deb482f9c0ef18f0c",
}
ICON_ITEMS = (
    (2370099, "深渊代币", "item/materials/mod/abyss/abyss_coin"),
    (2370100, "深渊觉醒核", "item/materials/mod/abyss/abyss_core"),
    (2370101, "深渊王印", "item/materials/mod/abyss/abyss_seal"),
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def read_payload(archive: Path, logical: str) -> bytes:
    with zipfile.ZipFile(archive) as source:
        return source.read(member_name(logical))


def build_payloads(source: dict[str, bytes], item_table: bytes) -> tuple[dict[str, bytes], dict]:
    for logical, expected in SOURCE_PAYLOAD_SHA256.items():
        if sha256_bytes(source[logical]) != expected:
            raise ValueError(f"source payload drift: {logical}")

    item_rows = core.read_orderedmap_raw_rows_from_bytes(item_table, ITEM_LOGICAL)
    item_rows_by_id = dict(zip(item_rows.keys, item_rows.rows))
    for item_id, _, icon_name in ICON_ITEMS:
        rows = list(csv.reader(io.StringIO(zlib.decompress(
            item_rows_by_id[str(item_id)]
        ).decode("utf-8"))))
        if len(rows) != 1 or rows[0][3:5] != [icon_name, icon_name]:
            raise ValueError(f"item thumbnail/small-icon reference drift: {item_id}")

    baseline_sheet = atlas_codec.decode_png(source[SHEET_LOGICAL])
    baseline_atlas = atlas_codec.decode_atlas(source[ATLAS_LOGICAL])
    if baseline_sheet.size != (505, 1704) or len(baseline_atlas) != 1514:
        raise ValueError("unexpected .97 terminal item atlas dimensions/frame count")
    baseline_names = {row["n"] for row in baseline_atlas}
    if len(baseline_names) != len(baseline_atlas):
        raise ValueError("baseline item atlas has duplicate frame names")

    output_sheet = Image.new("RGBA", (baseline_sheet.width, baseline_sheet.height + 22))
    output_sheet.paste(baseline_sheet, (0, 0))
    output_atlas = list(baseline_atlas)
    frame_reports = []
    for index, (item_id, item_name, icon_name) in enumerate(ICON_ITEMS):
        if icon_name in baseline_names:
            raise ValueError(f"custom icon already exists in source atlas: {icon_name}")
        icon = atlas_codec.decode_png(source[icon_name + ".png"])
        if icon.size != (20, 20) or icon.getbbox() is None:
            raise ValueError(f"invalid source icon: {icon_name}")
        frame = {
            "n": icon_name,
            "w": 20,
            "h": 20,
            "x": 1 + index * 21,
            "y": baseline_sheet.height + 1,
        }
        output_sheet.paste(icon, (frame["x"], frame["y"]))
        output_atlas.append(frame)
        frame_reports.append({
            "item_id": item_id,
            "item_name": item_name,
            "logical_name": icon_name,
            "frame": frame,
            "source_png_sha256": sha256_bytes(source[icon_name + ".png"]),
            "rgba_sha256": sha256_bytes(icon.tobytes()),
        })

    sheet_payload = atlas_codec.encode_png(output_sheet)
    atlas_payload = atlas_codec.encode_atlas(output_atlas)
    decoded_sheet = atlas_codec.decode_png(sheet_payload)
    decoded_atlas = atlas_codec.decode_atlas(atlas_payload)
    if decoded_sheet.crop((0, 0, baseline_sheet.width, baseline_sheet.height)).tobytes() != baseline_sheet.tobytes():
        raise ValueError("encoding changed baseline item pixels")
    if decoded_atlas[:len(baseline_atlas)] != baseline_atlas:
        raise ValueError("encoding changed baseline item frame metadata")
    if decoded_atlas[len(baseline_atlas):] != [entry["frame"] for entry in frame_reports]:
        raise ValueError("encoded custom frame metadata differs")
    if decoded_sheet.size != output_sheet.size or decoded_sheet.tobytes() != output_sheet.tobytes():
        raise ValueError("encoded output sheet differs from the appended-pixels construction")
    for report in frame_reports:
        frame = report["frame"]
        crop = decoded_sheet.crop((frame["x"], frame["y"], frame["x"] + 20, frame["y"] + 20))
        if sha256_bytes(crop.tobytes()) != report["rgba_sha256"]:
            raise ValueError(f"source icon pixels changed: {report['logical_name']}")

    payloads = {
        member_name(SHEET_LOGICAL): sheet_payload,
        member_name(ATLAS_LOGICAL): atlas_payload,
    }
    report = {
        "baseline_dimensions": list(baseline_sheet.size),
        "output_dimensions": list(decoded_sheet.size),
        "baseline_frame_count": len(baseline_atlas),
        "output_frame_count": len(decoded_atlas),
        "baseline_pixels_preserved": True,
        "baseline_frame_metadata_preserved": True,
        "source_icon_pixels_preserved": True,
        "added_frames": frame_reports,
        "item_table_reference_closure_verified": True,
        "item_table_changed": False,
        "common_android_ios_pair": True,
        "platform_atf_required": False,
        "output_members": [
            {"logical": logical, "member": member_name(logical), "sha256": sha256_bytes(payloads[member_name(logical)])}
            for logical in (SHEET_LOGICAL, ATLAS_LOGICAL)
        ],
    }
    return payloads, report


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 3, 23, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, payloads[name])
    result = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        if set(archive.namelist()) != set(payloads):
            raise ValueError("output archive member set differs")
        for name, expected in payloads.items():
            if archive.read(name) != expected:
                raise ValueError(f"output archive payload differs: {name}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the new .98 archive and static audit")
    args = parser.parse_args()

    active = REPO_ROOT / "assets" / "asset-patch" / "active"
    source_archive = active / SOURCE_ARCHIVE
    table_archive = active / TABLE_ARCHIVE
    before_hashes = {path.name: sha256_file(path) for path in (table_archive, source_archive)}
    if before_hashes[SOURCE_ARCHIVE] != SOURCE_ARCHIVE_SHA256:
        raise ValueError("the reviewed .97 source archive changed")
    manifest = json.loads((active.parent / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("cdn_version") not in (BASE_VERSION, PATCH_VERSION):
        raise ValueError("refusing to build against a different CDN terminal version")

    source = {logical: read_payload(source_archive, logical) for logical in SOURCE_PAYLOAD_SHA256}
    item_table = read_payload(table_archive, ITEM_LOGICAL)
    payloads, content_report = build_payloads(source, item_table)
    archive_bytes = zip_payloads(payloads)
    archive_sha256 = sha256_bytes(archive_bytes)
    audit_directory = f"assets/asset-patch/audit/{PATCH_ID}"
    manifest_entry = {
        "id": PATCH_ID,
        "type": "patch",
        "name": "深渊物品图标预加载配套修复",
        "description": "将 .97 已有的深渊代币、觉醒核和王印原图补入常驻物品图集，修复同步小图标读取；安卓与 iOS 共用，不修改玩法主表。",
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": OUTPUT_ARCHIVE,
        "archive_size": len(archive_bytes),
        "files": sorted(payloads),
        "changes": [
            "保留当前 1514 个物品图集帧及全部原始像素，仅追加深渊代币、深渊觉醒核、深渊王印三个同名图标帧。",
            "三个图标直接复用 .97 的作者 PNG 像素，补齐同步小图标所需的常驻图集加载链。",
            "common PNG 与 atlas 同时供 Android 和 iOS 使用，不增加或复制平台专属 ATF。",
            "仅顺接 1.4.97 -> 1.4.98，不改写 .96/.97 旧包及称号、代币消耗、卡池、商店或连战塔主表。",
        ],
        "created_at": "2026-09-03",
        "audit": {"directory": audit_directory, "report": "report.json"},
        "archive_integrity": [{"name": OUTPUT_ARCHIVE, "size": len(archive_bytes), "sha256": archive_sha256, "members": len(payloads)}],
        "chain": [OUTPUT_ARCHIVE],
    }
    after_hashes = {path.name: sha256_file(path) for path in (table_archive, source_archive)}
    if after_hashes != before_hashes:
        raise ValueError("an earlier archive changed during the build")
    report = {
        "patch_id": PATCH_ID,
        "base_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "source_archives_sha256": before_hashes,
        "prior_archives_unchanged": True,
        "item_table_source_sha256": sha256_bytes(item_table),
        "content": content_report,
        "manifest_entry": manifest_entry,
        "validation": "static payload decoding and archive readback only; no application/runtime tests",
    }
    if args.write:
        output_path = active / OUTPUT_ARCHIVE
        if output_path.exists() and sha256_file(output_path) != archive_sha256:
            raise ValueError("refusing to replace a different existing .98 archive")
        if not output_path.exists():
            output_path.write_bytes(archive_bytes)
        audit_path = REPO_ROOT / audit_directory / "report.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "archive": str(active / OUTPUT_ARCHIVE),
        "archive_size": len(archive_bytes),
        "archive_sha256": archive_sha256,
        "members": len(payloads),
        "added_icons": [name for _, name, _ in ICON_ITEMS],
        "old_frames_preserved": content_report["baseline_frame_count"],
        "android_ios": "shared common PNG/atlas",
        "written": args.write,
        "manifest_updated": False,
        "manifest_entry": manifest_entry,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
