#!/usr/bin/env python3
"""Publish the final Gauntlet hub banner and Fantasy/Abyss equipment art.

This client-only patch gives EventFolder 2 its own banner asset, replaces all
Fantasy and Deep-Abyss equipment icons, introduces dedicated Deep-Abyss soul
icon paths, and registers every standalone 20x20 icon as a full-frame texture.

The active archive and live payloads are written only below asset-patch/active
and asset-patch/production.  The base .cdn tree is intentionally out of scope.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import shutil
import struct
import sys
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

MOD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOD_DIR))
import wf_assets  # noqa: E402
import wf_mod_tool as core  # noqa: E402


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
RUNTIME_ROOT = Path(r"F:\startpoint-cn-main")
RUNTIME_BACKUP_ROOT = RUNTIME_ROOT / ".codex-backups"

BANNER_INPUT = Path(r"F:\image\终始之战_1000x184.png")
FANTASY_INPUT = Path(r"F:\image\幻想终版")
FANTASY_SOUL_INPUT = FANTASY_INPUT / "魂珠图标输出"
ABYSS_INPUT = Path(r"F:\image\深渊终版")
ABYSS_SOUL_INPUT = ABYSS_INPUT / "魂珠图标输出"

BASE_VERSION = "1.4.83"
PATCH_VERSION = "1.4.84"
PATCH_ID = "gauntlet-final-art-1.4.84"
ARCHIVE_NAME = "pinball-1.4.83-1.4.84-1-0818-gauntlet-final-art.zip"

EVENT_FOLDER_LOGICAL = "master/quest/event/event_folder.orderedmap"
ITEM_LOGICAL = "master/item/item.orderedmap"
EQUIPMENT_LOGICAL = "master/item/equipment.orderedmap"
TRIM_LOGICAL = "master/generated/trimmed_image.orderedmap"
TABLE_LOGICALS = (
    EVENT_FOLDER_LOGICAL,
    ITEM_LOGICAL,
    EQUIPMENT_LOGICAL,
    TRIM_LOGICAL,
)

FOLDER_ID = "2"
OLD_FOLDER_BANNER = "quest/event/banner/rush_event/mod_fifteen_stage_banner_001"
FOLDER_BANNER = "quest/event/banner/rush_event/mod_gauntlet_hub_banner_001"
FOLDER_BANNER_LOGICAL = f"{FOLDER_BANNER}.png"

FANTASY_PREFIX = "item/equipment/mod/fantasy"
FANTASY_SOUL_PREFIX = f"{FANTASY_PREFIX}/soul"
ABYSS_PREFIX = "item/equipment/mod/abyss"
ABYSS_SOUL_PREFIX = f"{ABYSS_PREFIX}/soul"

FANTASY_WEAPONS = (
    ("100013", "幻星术式核心", "幻星术式核心.png", "幻星术式核心_魂珠.png", "skill_core"),
    ("100014", "双星追迹刃", "双星追踪刃.png", "双星追踪刃_魂珠.png", "direct_blade"),
    ("100015", "坠星破界锤", "坠星破界锤.png", "坠星破界锤_魂珠.png", "powerflip_hammer"),
    ("100016", "群星自律机库", "群星自律机库.png", "群星自律机库_魂珠.png", "multiball_hangar"),
    ("100017", "因果演算终端", "因果演算终端.png", "因果演算终端_魂珠.png", "ability_terminal"),
    ("100018", "热寂共鸣环", "热寂共鸣环.png", "热寂共鸣环_魂珠.png", "fever_ring"),
    ("100019", "半月蚀心剑", "半月蚀心剑.png", "半月蚀心剑_魂珠.png", "adversity_sword"),
    ("100020", "天穹无坠之翼", "天穹无坠之翼.png", "天穹无坠之翼_魂珠.png", "flying_wing"),
    ("100021", "冥灯返魂杖", "冥灯返魂杖.png", "冥灯返魂杖_魂珠.png", "revival_staff"),
    ("100022", "无界贯星枪", "无界贯星枪.png", "无界贯星枪_魂珠.png", "piercing_lance"),
    ("100023", "六相万华轮", "六相万华轮.png", "六相万华轮_魂珠.png", "six_element_wheel"),
)

# Two author filenames differ from the existing server display names.  They map
# to the established IDs/slugs rather than creating duplicate equipment rows.
ABYSS_WEAPONS = (
    ("8000101", "深渊·灰烬巨剑", "深渊·灰烬巨剑.png", "深渊·灰烬巨剑_魂珠.png", "fire_01"),
    ("8000102", "深渊·熔核法杖", "深渊·熔核法杖.png", "深渊·熔核法杖_魂珠.png", "fire_02"),
    ("8000103", "深渊·深潮长枪", "深渊·深潮长枪.png", "深渊·深潮长枪_魂珠.png", "water_01"),
    ("8000104", "深渊·冻海战锚", "深渊·冰海战锚.png", "深渊·冰海战锚_魂珠.png", "water_02"),
    ("8000105", "深渊·雷鸣双刃", "深渊·雷鸣双刃.png", "深渊·雷鸣双刃_魂珠.png", "thunder_01"),
    ("8000106", "深渊·轰电战锤", "深渊·轰雷战锤.png", "深渊·轰雷战锤_魂珠.png", "thunder_02"),
    ("8000107", "深渊·裂空战镰", "深渊·裂空战镰.png", "深渊·裂空战镰_魂珠.png", "wind_01"),
    ("8000108", "深渊·苍岚长弓", "深渊·苍岚长弓.png", "深渊·苍岚长弓_魂珠.png", "wind_02"),
    ("8000109", "深渊·晨星圣剑", "深渊·晨星圣剑.png", "深渊·晨星圣剑_魂珠.png", "light_01"),
    ("8000110", "深渊·辉环法器", "深渊·辉环法器.png", "深渊·辉环法器_魂珠.png", "light_02"),
    ("8000111", "深渊·蚀月大剑", "深渊·蚀月大剑.png", "深渊·蚀月大剑_魂珠.png", "dark_01"),
    ("8000112", "深渊·冥灯魔杖", "深渊·冥灯魔杖.png", "深渊·冥灯魔杖_魂珠.png", "dark_02"),
    ("8000113", "深渊·征服者", "深渊·征服者.png", "深渊·征服者_魂珠.png", "universal_01"),
    ("8000114", "深渊·轮转核", "深渊·轮转核.png", "深渊·轮转核_魂珠.png", "universal_02"),
    ("8000115", "深渊·万象铳", "深渊·万象铳.png", "深渊·万象铳_魂珠.png", "universal_03"),
)


class PublishError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def live_path(root: Path, logical: str) -> Path:
    digest = core.sha1_path(logical)
    return root / "assets/asset-patch/production/upload" / digest[:2] / digest[2:]


def read_manifest(root: Path, repair_existing: bool) -> tuple[dict[str, Any], bytes]:
    path = root / "assets/asset-patch/manifest.json"
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    expected_version = PATCH_VERSION if repair_existing else BASE_VERSION
    if value.get("cdn_version") != expected_version:
        raise PublishError(f"manifest is not at {expected_version}: {path}")
    matches = [entry for entry in value.get("patches", []) if entry.get("id") == PATCH_ID]
    archive = root / "assets/asset-patch/active" / ARCHIVE_NAME
    if repair_existing:
        if len(matches) != 1 or matches[0].get("archive") != ARCHIVE_NAME:
            raise PublishError(f"existing {PATCH_ID} manifest entry drifted: {path}")
        if not archive.is_file():
            raise PublishError(f"existing archive is missing: {archive}")
    else:
        if matches:
            raise PublishError(f"patch is already present: {path}")
        if archive.exists():
            raise PublishError(f"target archive already exists: {archive}")
    return value, raw


def manifest_before_current_patch(manifest: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(manifest)
    matches = [index for index, entry in enumerate(value.get("patches", [])) if entry.get("id") == PATCH_ID]
    if len(matches) != 1:
        raise PublishError(f"cannot derive {BASE_VERSION} baseline for {PATCH_ID}")
    del value["patches"][matches[0]]
    value["cdn_version"] = BASE_VERSION
    return value


def active_archives(root: Path, manifest: dict[str, Any]) -> list[Path]:
    result: list[Path] = []
    for patch in manifest.get("patches", []):
        if not patch.get("enabled", True):
            continue
        names: list[str] = []
        if patch.get("archive"):
            names.append(str(patch["archive"]))
        names.extend(str(value) for value in patch.get("chain", []))
        seen: set[str] = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            path = root / "assets/asset-patch/active" / name
            if not path.is_file():
                raise PublishError(f"active manifest archive is missing: {path}")
            result.append(path)
    return result


def terminal_tables(
    root: Path,
    manifest: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, str]]:
    wanted = {member_name(logical): logical for logical in TABLE_LOGICALS}
    values: dict[str, bytes] = {}
    sources: dict[str, str] = {}
    for archive_path in active_archives(root, manifest):
        with zipfile.ZipFile(archive_path) as archive:
            available = set(archive.namelist())
            for member, logical in wanted.items():
                if member in available:
                    values[logical] = archive.read(member)
                    sources[logical] = archive_path.name
    missing = set(TABLE_LOGICALS) - set(values)
    if missing:
        raise PublishError(f"active terminal lacks required tables: {sorted(missing)}")
    return values, sources


def split_flat_chunks(raw: bytes) -> tuple[list[str], list[bytes]]:
    keys, pairs, index_len = core.parse_index(raw)
    blob = raw[4 + index_len:]
    chunks: list[bytes] = []
    previous = 0
    for _, row_end in pairs:
        chunks.append(blob[previous:row_end])
        previous = row_end
    return keys, chunks


def build_flat_chunks(keys: list[str], chunks: list[bytes]) -> bytes:
    if len(keys) != len(chunks):
        raise PublishError("orderedmap key/chunk count mismatch")
    key_blob = bytearray()
    row_blob = bytearray()
    pairs: list[tuple[int, int]] = []
    for key, chunk in zip(keys, chunks):
        key_blob.extend(key.encode("utf-8"))
        row_blob.extend(chunk)
        pairs.append((len(key_blob), len(row_blob)))
    index = bytearray(struct.pack("<I", len(keys)))
    for key_end, row_end in pairs:
        index.extend(struct.pack("<II", key_end, row_end))
    index.extend(key_blob)
    packed_index = zlib.compress(bytes(index))
    return struct.pack("<I", len(packed_index)) + packed_index + bytes(row_blob)


def patch_flat_rows(
    raw: bytes,
    replacements: dict[str, str],
    additions: dict[str, str] | None = None,
) -> bytes:
    keys, chunks = split_flat_chunks(raw)
    positions = {key: index for index, key in enumerate(keys)}
    for key, text in replacements.items():
        if key not in positions:
            raise PublishError(f"orderedmap key is missing: {key}")
        chunks[positions[key]] = zlib.compress(text.encode("utf-8")) if text else b""
    for key, text in (additions or {}).items():
        if key in positions:
            raise PublishError(f"orderedmap addition already exists: {key}")
        positions[key] = len(keys)
        keys.append(key)
        chunks.append(zlib.compress(text.encode("utf-8")) if text else b"")
    return build_flat_chunks(keys, chunks)


def flat_rows(raw: bytes) -> dict[str, str]:
    return core.read_orderedmap_file_from_bytes(raw)


def validate_png(path: Path, expected_size: tuple[int, int], require_rgba: bool) -> dict[str, Any]:
    if not path.is_file():
        raise PublishError(f"input PNG is missing: {path}")
    raw = path.read_bytes()
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if image.format != "PNG" or image.size != expected_size:
            raise PublishError(f"input must be a native {expected_size[0]}x{expected_size[1]} PNG: {path}")
        if require_rgba and image.mode != "RGBA":
            raise PublishError(f"equipment/soul input must be RGBA: {path}")
        trim: str | None = None
        if require_rgba:
            alpha = image.getchannel("A")
            if alpha.getextrema() != (0, 255):
                raise PublishError(f"icon must contain transparent and opaque pixels: {path}")
            bbox = alpha.getbbox()
            if bbox is None:
                raise PublishError(f"icon has no visible pixels: {path}")
            # trimmed_image is a texture-frame declaration, not an alpha-bounds
            # table.  Standalone 20x20 icons must keep the complete canvas or
            # ViewAssetCache applies a negative frame offset in real UI cells.
            trim = f"0,0,{expected_size[0]},{expected_size[1]}"
    encoded = wf_assets.png_encode(raw)
    if wf_assets.png_decode(encoded) != raw:
        raise PublishError(f"client PNG codec round-trip failed: {path}")
    return {
        "raw": raw,
        "encoded": encoded,
        "trim": trim,
        "sha256": sha256_bytes(raw),
    }


def validate_exact_png_set(root: Path, expected: set[str], label: str) -> None:
    if not root.is_dir():
        raise PublishError(f"input directory is missing: {root}")
    actual = {
        path.name for path in root.iterdir()
        if path.is_file() and path.suffix.lower() == ".png"
    }
    if actual != expected:
        raise PublishError(
            f"{label} PNG set drifted: missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def load_images() -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    validate_exact_png_set(FANTASY_INPUT, {row[2] for row in FANTASY_WEAPONS}, "Fantasy equipment")
    validate_exact_png_set(FANTASY_SOUL_INPUT, {row[3] for row in FANTASY_WEAPONS}, "Fantasy soul")
    validate_exact_png_set(ABYSS_INPUT, {row[2] for row in ABYSS_WEAPONS}, "Abyss equipment")
    validate_exact_png_set(ABYSS_SOUL_INPUT, {row[3] for row in ABYSS_WEAPONS}, "Abyss soul")

    banner = validate_png(BANNER_INPUT, (1000, 184), False)
    fantasy: dict[str, dict[str, Any]] = {}
    abyss: dict[str, dict[str, Any]] = {}
    for item_id, name, icon_name, soul_name, slug in FANTASY_WEAPONS:
        fantasy[slug] = {
            "id": item_id,
            "name": name,
            "equipment": validate_png(FANTASY_INPUT / icon_name, (20, 20), True),
            "soul": validate_png(FANTASY_SOUL_INPUT / soul_name, (20, 20), True),
        }
    for item_id, name, icon_name, soul_name, slug in ABYSS_WEAPONS:
        abyss[slug] = {
            "id": item_id,
            "name": name,
            "equipment": validate_png(ABYSS_INPUT / icon_name, (20, 20), True),
            "soul": validate_png(ABYSS_SOUL_INPUT / soul_name, (20, 20), True),
        }
    return banner, fantasy, abyss


def patch_event_folder(raw: bytes) -> bytes:
    rows = flat_rows(raw)
    value = rows.get(FOLDER_ID)
    if value is None:
        raise PublishError(f"EventFolder {FOLDER_ID} is missing")
    lines = core.read_csv_lines(value)
    if len(lines) != 1 or len(lines[0]) != 7:
        raise PublishError(f"EventFolder {FOLDER_ID} row shape drifted")
    if lines[0][1] != OLD_FOLDER_BANNER:
        raise PublishError(f"EventFolder {FOLDER_ID} banner path drifted: {lines[0][1]}")
    lines[0][1] = FOLDER_BANNER
    return patch_flat_rows(raw, {FOLDER_ID: core.write_csv_lines(lines)})


def verify_equipment_paths(raw: bytes) -> None:
    rows = flat_rows(raw)
    for item_id, _name, _icon_name, _soul_name, slug in FANTASY_WEAPONS:
        value = rows.get(item_id)
        lines = core.read_csv_lines(value) if value is not None else []
        expected = f"{FANTASY_PREFIX}/{slug}"
        if len(lines) != 1 or len(lines[0]) < 7 or lines[0][6] != expected:
            raise PublishError(f"Fantasy equipment image path drifted: {item_id}")
    for item_id, _name, _icon_name, _soul_name, slug in ABYSS_WEAPONS:
        value = rows.get(item_id)
        lines = core.read_csv_lines(value) if value is not None else []
        expected = f"{ABYSS_PREFIX}/{slug}"
        if len(lines) != 1 or len(lines[0]) < 7 or lines[0][6] != expected:
            raise PublishError(f"Abyss equipment image path drifted: {item_id}")


def patch_item(raw: bytes) -> bytes:
    rows = flat_rows(raw)
    replacements: dict[str, str] = {}
    for item_id, _name, _icon_name, _soul_name, slug in FANTASY_WEAPONS:
        value = rows.get(item_id)
        lines = core.read_csv_lines(value) if value is not None else []
        expected = f"{FANTASY_SOUL_PREFIX}/{slug}"
        if len(lines) != 1 or len(lines[0]) < 4 or lines[0][3] != expected:
            raise PublishError(f"Fantasy soul path drifted: {item_id}")
    for item_id, _name, _icon_name, _soul_name, slug in ABYSS_WEAPONS:
        value = rows.get(item_id)
        lines = core.read_csv_lines(value) if value is not None else []
        expected = f"{ABYSS_PREFIX}/{slug}"
        if len(lines) != 1 or len(lines[0]) < 4 or lines[0][3] != expected:
            raise PublishError(f"Abyss soul source path drifted: {item_id}")
        lines[0][3] = f"{ABYSS_SOUL_PREFIX}/{slug}"
        replacements[item_id] = core.write_csv_lines(lines)
    return patch_flat_rows(raw, replacements)


def patch_trim(
    raw: bytes,
    fantasy: dict[str, dict[str, Any]],
    abyss: dict[str, dict[str, Any]],
) -> bytes:
    rows = flat_rows(raw)
    replacements: dict[str, str] = {}
    additions: dict[str, str] = {}
    for _item_id, _name, _icon_name, _soul_name, slug in FANTASY_WEAPONS:
        equipment_key = f"{FANTASY_PREFIX}/{slug}"
        soul_key = f"{FANTASY_SOUL_PREFIX}/{slug}"
        if equipment_key not in rows or soul_key not in rows:
            raise PublishError(f"Fantasy trim key is missing: {slug}")
        replacements[equipment_key] = str(fantasy[slug]["equipment"]["trim"])
        replacements[soul_key] = str(fantasy[slug]["soul"]["trim"])
    for _item_id, _name, _icon_name, _soul_name, slug in ABYSS_WEAPONS:
        equipment_key = f"{ABYSS_PREFIX}/{slug}"
        soul_key = f"{ABYSS_SOUL_PREFIX}/{slug}"
        if equipment_key in rows or soul_key in rows:
            raise PublishError(f"Abyss trim key unexpectedly already exists: {slug}")
        additions[equipment_key] = str(abyss[slug]["equipment"]["trim"])
        additions[soul_key] = str(abyss[slug]["soul"]["trim"])
    return patch_flat_rows(raw, replacements, additions)


def build_payloads(
    terminal: dict[str, bytes],
    banner: dict[str, Any],
    fantasy: dict[str, dict[str, Any]],
    abyss: dict[str, dict[str, Any]],
) -> dict[str, bytes]:
    verify_equipment_paths(terminal[EQUIPMENT_LOGICAL])
    payloads = {
        EVENT_FOLDER_LOGICAL: patch_event_folder(terminal[EVENT_FOLDER_LOGICAL]),
        ITEM_LOGICAL: patch_item(terminal[ITEM_LOGICAL]),
        TRIM_LOGICAL: patch_trim(terminal[TRIM_LOGICAL], fantasy, abyss),
        FOLDER_BANNER_LOGICAL: banner["encoded"],
    }
    for _item_id, _name, _icon_name, _soul_name, slug in FANTASY_WEAPONS:
        payloads[f"{FANTASY_PREFIX}/{slug}.png"] = fantasy[slug]["equipment"]["encoded"]
        payloads[f"{FANTASY_SOUL_PREFIX}/{slug}.png"] = fantasy[slug]["soul"]["encoded"]
    for _item_id, _name, _icon_name, _soul_name, slug in ABYSS_WEAPONS:
        payloads[f"{ABYSS_PREFIX}/{slug}.png"] = abyss[slug]["equipment"]["encoded"]
        payloads[f"{ABYSS_SOUL_PREFIX}/{slug}.png"] = abyss[slug]["soul"]["encoded"]
    verify_payloads(payloads, banner, fantasy, abyss)
    return payloads


def verify_payloads(
    payloads: dict[str, bytes],
    banner: dict[str, Any],
    fantasy: dict[str, dict[str, Any]],
    abyss: dict[str, dict[str, Any]],
) -> None:
    folders = flat_rows(payloads[EVENT_FOLDER_LOGICAL])
    if core.read_csv_lines(folders[FOLDER_ID])[0][1] != FOLDER_BANNER:
        raise PublishError("EventFolder banner readback failed")
    items = flat_rows(payloads[ITEM_LOGICAL])
    trims = flat_rows(payloads[TRIM_LOGICAL])
    for item_id, _name, _icon_name, _soul_name, slug in FANTASY_WEAPONS:
        if core.read_csv_lines(items[item_id])[0][3] != f"{FANTASY_SOUL_PREFIX}/{slug}":
            raise PublishError(f"Fantasy soul item readback failed: {item_id}")
        for kind, prefix in (("equipment", FANTASY_PREFIX), ("soul", FANTASY_SOUL_PREFIX)):
            logical = f"{prefix}/{slug}.png"
            trim_key = f"{prefix}/{slug}"
            if trims[trim_key] != fantasy[slug][kind]["trim"]:
                raise PublishError(f"Fantasy trim readback failed: {logical}")
            if wf_assets.png_decode(payloads[logical]) != fantasy[slug][kind]["raw"]:
                raise PublishError(f"Fantasy PNG readback failed: {logical}")
    for item_id, _name, _icon_name, _soul_name, slug in ABYSS_WEAPONS:
        if core.read_csv_lines(items[item_id])[0][3] != f"{ABYSS_SOUL_PREFIX}/{slug}":
            raise PublishError(f"Abyss soul item readback failed: {item_id}")
        for kind, prefix in (("equipment", ABYSS_PREFIX), ("soul", ABYSS_SOUL_PREFIX)):
            logical = f"{prefix}/{slug}.png"
            trim_key = f"{prefix}/{slug}"
            if trims[trim_key] != abyss[slug][kind]["trim"]:
                raise PublishError(f"Abyss trim readback failed: {logical}")
            if wf_assets.png_decode(payloads[logical]) != abyss[slug][kind]["raw"]:
                raise PublishError(f"Abyss PNG readback failed: {logical}")
    if wf_assets.png_decode(payloads[FOLDER_BANNER_LOGICAL]) != banner["raw"]:
        raise PublishError("EventFolder banner PNG readback failed")


def build_archive(payloads: dict[str, bytes]) -> tuple[bytes, dict[str, bytes]]:
    members = {member_name(logical): raw for logical, raw in payloads.items()}
    if len(members) != len(payloads):
        raise PublishError("logical path hash collision detected")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for member in sorted(members):
            if not member.startswith("production/upload/") or ".." in member:
                raise PublishError(f"unsafe/non-active archive member: {member}")
            info = zipfile.ZipInfo(member, (2026, 8, 18, 23, 30, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, members[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(members):
            raise PublishError("archive member order/readback failed")
        for member, expected in members.items():
            if archive.read(member) != expected:
                raise PublishError(f"archive payload readback failed: {member}")
    return raw, members


def updated_manifest(
    manifest: dict[str, Any],
    archive_raw: bytes,
    members: dict[str, bytes],
    repair_existing: bool,
) -> bytes:
    value = copy.deepcopy(manifest)
    entry = {
        "id": PATCH_ID,
        "type": "patch",
        "name": "终始之战入口与连战终版图标 1.4.84",
        "description": (
            "为幻想/深渊连战共用文件夹启用独立的终始之战横幅；替换两套连战全部装备与魂珠图标，"
            "并为深渊15件魂珠建立独立图片映射。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive_raw),
        "files": sorted(members),
        "changes": [
            "活动文件夹（2）改用独立的“终始之战”1000×184入口横幅，不覆盖幻想连战自身横幅。",
            "替换幻想连战11件装备图标及11张专属魂珠图标。",
            "替换深渊连战15件装备图标，并将15件魂珠从装备图标路径切换为独立专属魂珠图标路径。",
            "52张20×20独立纹理统一使用0,0,20,20完整画布frame，避免客户端应用负偏移造成图标错位。",
        ],
        "created_at": "2026-08-18",
        "archive_integrity": [{
            "name": ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256_bytes(archive_raw),
            "members": len(members),
        }],
    }
    if repair_existing:
        matches = [index for index, current in enumerate(value["patches"]) if current.get("id") == PATCH_ID]
        if len(matches) != 1:
            raise PublishError(f"cannot replace existing {PATCH_ID} manifest entry")
        value["patches"][matches[0]] = entry
    else:
        value["patches"].append(entry)
    value["cdn_version"] = PATCH_VERSION
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def updated_changelog(raw: bytes, repair_existing: bool) -> bytes:
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    marker = f"|---|---|---|---|---|---|{newline}"
    if marker not in text:
        raise PublishError("asset patch changelog table header drifted")
    old_rows = (
        f"| 2026-08-18 | event_folder/image | 2 | 文件夹入口改用独立“终始之战”横幅 | 1.4.84 | active增量包 |{newline}"
        f"| 2026-08-18 | image/trimmed_image | 100013-100023 | 幻想连战11件装备与11张魂珠终版图标 | 1.4.84 | active增量包 |{newline}"
        f"| 2026-08-18 | item/image/trimmed_image | 8000101-8000115 | 深渊连战15件装备及15张独立魂珠终版图标 | 1.4.84 | active增量包 |{newline}"
    )
    rows = (
        f"| 2026-08-18 | event_folder/image | 2 | 文件夹入口改用独立“终始之战”横幅 | 1.4.84 | active增量包 |{newline}"
        f"| 2026-08-18 | image/trimmed_image | 100013-100023 | 幻想连战11件装备与11张魂珠终版图标；完整20×20 frame | 1.4.84 | active增量包 |{newline}"
        f"| 2026-08-18 | item/image/trimmed_image | 8000101-8000115 | 深渊连战15件装备及15张独立魂珠终版图标；完整20×20 frame | 1.4.84 | active增量包 |{newline}"
    )
    if repair_existing:
        if text.count(old_rows) != 1:
            raise PublishError("existing 1.4.84 changelog rows drifted")
        return text.replace(old_rows, rows, 1).encode("utf-8")
    return text.replace(marker, marker + rows, 1).encode("utf-8")


def canonical_path(root: Path, family: str, slug: str, soul: bool) -> Path:
    if family == "fantasy":
        directory = "fantasy-equipment-souls" if soul else "fantasy-equipment"
    elif family == "abyss":
        directory = "abyss-equipment-souls" if soul else "abyss-equipment"
    else:
        raise PublishError(f"unknown canonical asset family: {family}")
    return root / "tools/fantasy-gauntlet-mod-tools/assets" / directory / f"{slug}.png"


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".gauntlet-final-art-1.4.84.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def assert_target(root: Path, target: Path) -> None:
    target.resolve(strict=False).relative_to(root.resolve(strict=True))
    if ".cdn" in target.parts:
        raise PublishError(f"base .cdn write is forbidden: {target}")


def add_target(
    targets: dict[str, tuple[Path, bytes, Path]],
    label: str,
    root: Path,
    target: Path,
    raw: bytes,
) -> None:
    assert_target(root, target)
    if label in targets or target in (entry[0] for entry in targets.values()):
        raise PublishError(f"duplicate publication target: {target}")
    targets[label] = (target, raw, root)


def build_targets(
    manifest_raw: bytes,
    changelog_raw: bytes,
    archive_raw: bytes,
    payloads: dict[str, bytes],
    banner: dict[str, Any],
    fantasy: dict[str, dict[str, Any]],
    abyss: dict[str, dict[str, Any]],
) -> dict[str, tuple[Path, bytes, Path]]:
    targets: dict[str, tuple[Path, bytes, Path]] = {}
    for root, label in ((SOURCE_ROOT, "source"), (RUNTIME_ROOT, "runtime")):
        add_target(
            targets, f"{label}-active-archive", root,
            root / "assets/asset-patch/active" / ARCHIVE_NAME, archive_raw,
        )
        for logical, raw in payloads.items():
            add_target(
                targets, f"{label}-live-{core.sha1_path(logical)}", root,
                live_path(root, logical), raw,
            )
        add_target(
            targets, f"{label}-changelog", root,
            root / "assets/asset-patch/changelog.md", changelog_raw,
        )
        add_target(
            targets, f"{label}-manifest", root,
            root / "assets/asset-patch/manifest.json", manifest_raw,
        )

    add_target(
        targets, "source-canonical-banner", SOURCE_ROOT,
        SOURCE_ROOT / "tools/fantasy-gauntlet-mod-tools/assets/gauntlet-hub-banner/gauntlet_hub_banner_1000x184.png",
        banner["raw"],
    )
    for _item_id, _name, _icon_name, _soul_name, slug in FANTASY_WEAPONS:
        add_target(
            targets, f"source-canonical-fantasy-equipment-{slug}", SOURCE_ROOT,
            canonical_path(SOURCE_ROOT, "fantasy", slug, False), fantasy[slug]["equipment"]["raw"],
        )
        add_target(
            targets, f"source-canonical-fantasy-soul-{slug}", SOURCE_ROOT,
            canonical_path(SOURCE_ROOT, "fantasy", slug, True), fantasy[slug]["soul"]["raw"],
        )
    for _item_id, _name, _icon_name, _soul_name, slug in ABYSS_WEAPONS:
        add_target(
            targets, f"source-canonical-abyss-equipment-{slug}", SOURCE_ROOT,
            canonical_path(SOURCE_ROOT, "abyss", slug, False), abyss[slug]["equipment"]["raw"],
        )
        add_target(
            targets, f"source-canonical-abyss-soul-{slug}", SOURCE_ROOT,
            canonical_path(SOURCE_ROOT, "abyss", slug, True), abyss[slug]["soul"]["raw"],
        )
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--repair-existing", action="store_true")
    args = parser.parse_args()

    source_manifest, source_manifest_current = read_manifest(SOURCE_ROOT, args.repair_existing)
    runtime_manifest, runtime_manifest_current = read_manifest(RUNTIME_ROOT, args.repair_existing)
    if source_manifest != runtime_manifest or source_manifest_current != runtime_manifest_current:
        raise PublishError("source and runtime manifests differ")

    source_changelog_path = SOURCE_ROOT / "assets/asset-patch/changelog.md"
    runtime_changelog_path = RUNTIME_ROOT / "assets/asset-patch/changelog.md"
    if source_changelog_path.read_bytes() != runtime_changelog_path.read_bytes():
        raise PublishError("source and runtime changelogs differ")

    source_baseline = manifest_before_current_patch(source_manifest) if args.repair_existing else source_manifest
    runtime_baseline = manifest_before_current_patch(runtime_manifest) if args.repair_existing else runtime_manifest
    source_terminal, source_sources = terminal_tables(SOURCE_ROOT, source_baseline)
    runtime_terminal, runtime_sources = terminal_tables(RUNTIME_ROOT, runtime_baseline)
    if source_terminal != runtime_terminal:
        raise PublishError("source and runtime terminal client tables differ")

    banner, fantasy, abyss = load_images()
    payloads = build_payloads(source_terminal, banner, fantasy, abyss)
    archive_raw, members = build_archive(payloads)
    manifest_raw = updated_manifest(source_manifest, archive_raw, members, args.repair_existing)
    changelog_raw = updated_changelog(source_changelog_path.read_bytes(), args.repair_existing)

    report: dict[str, Any] = {
        "apply": args.apply,
        "repair_existing": args.repair_existing,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "patch_id": PATCH_ID,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive_raw),
        "archive_sha256": sha256_bytes(archive_raw),
        "members": sorted(members),
        "member_count": len(members),
        "effects": {
            "event_folder": int(FOLDER_ID),
            "folder_banner_logical": FOLDER_BANNER_LOGICAL,
            "fantasy_equipment_icons": len(FANTASY_WEAPONS),
            "fantasy_soul_icons": len(FANTASY_WEAPONS),
            "abyss_equipment_icons": len(ABYSS_WEAPONS),
            "abyss_soul_icons": len(ABYSS_WEAPONS),
            "trimmed_image_rows": 2 * (len(FANTASY_WEAPONS) + len(ABYSS_WEAPONS)),
            "trimmed_image_frame": "0,0,20,20",
            "abyss_soul_item_paths_changed": len(ABYSS_WEAPONS),
        },
        "terminal_sources": source_sources,
        "runtime_terminal_sources": runtime_sources,
        "cdn_archive_directory": "assets/asset-patch/active",
        "live_asset_directory": "assets/asset-patch/production/upload",
        "wrote_dot_cdn": False,
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    targets = build_targets(
        manifest_raw, changelog_raw, archive_raw, payloads, banner, fantasy, abyss,
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "gauntlet-final-art-1.4.84-repair" if args.repair_existing else "gauntlet-final-art-1.4.84"
    backup = RUNTIME_BACKUP_ROOT / f"{stamp}-{suffix}"
    backup.mkdir(parents=True, exist_ok=False)
    existence: dict[str, dict[str, Any]] = {}
    for label, (path, _raw, root) in targets.items():
        group = "source" if root == SOURCE_ROOT else "runtime"
        relative = path.relative_to(root)
        backup_path = backup / group / relative
        existed = path.is_file()
        existence[label] = {
            "target": str(path),
            "existed": existed,
            "backup": str(backup_path) if existed else None,
        }
        if existed:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_path)
    (backup / "existence.json").write_text(
        json.dumps(existence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        for label, (path, raw, _root) in targets.items():
            if label.endswith("-manifest"):
                continue
            atomic_write(raw, path)
        for label, (path, raw, _root) in targets.items():
            if label.endswith("-manifest"):
                atomic_write(raw, path)

        for label, (path, expected, _root) in targets.items():
            if not path.is_file() or path.read_bytes() != expected:
                raise PublishError(f"publication readback failed: {label}")
        for root in (SOURCE_ROOT, RUNTIME_ROOT):
            written = json.loads(
                (root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
            )
            matches = [entry for entry in written["patches"] if entry.get("id") == PATCH_ID]
            if written.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
                raise PublishError(f"manifest readback failed: {root}")
            with zipfile.ZipFile(root / "assets/asset-patch/active" / ARCHIVE_NAME) as archive:
                if archive.namelist() != sorted(members):
                    raise PublishError(f"archive member readback failed: {root}")
                for member, expected in members.items():
                    if archive.read(member) != expected:
                        raise PublishError(f"archive payload readback failed: {root}/{member}")
    except Exception:
        for label, (path, _raw, root) in reversed(list(targets.items())):
            assert_target(root, path)
            record = existence[label]
            if record["existed"]:
                atomic_write(Path(record["backup"]).read_bytes(), path)
            elif path.exists():
                path.unlink()
        raise

    report["backup"] = str(backup)
    report["source_targets"] = sum(1 for _path, _raw, root in targets.values() if root == SOURCE_ROOT)
    report["runtime_targets"] = sum(1 for _path, _raw, root in targets.values() if root == RUNTIME_ROOT)
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
