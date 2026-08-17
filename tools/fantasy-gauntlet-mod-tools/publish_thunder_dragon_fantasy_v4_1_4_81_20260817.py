#!/usr/bin/env python3
"""Publish the approved thunder-dragon balance and Fantasy V4 icons as 1.4.81."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import struct
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
INPUT_ROOT = Path(r"F:\image\V4")
SOUL_INPUT_ROOT = INPUT_ROOT / "魂珠图标输出"

BASE_VERSION = "1.4.80"
PATCH_VERSION = "1.4.81"
PATCH_ID = "thunder-dragon-fantasy-v4-1.4.81"
ARCHIVE_NAME = "pinball-1.4.80-1.4.81-1-0817-thunder-dragon-fantasy-v4.zip"

CHARACTER_ID = "139998"
CHARACTER_CODE = "cnmod_thunder_dragon_ascendant"
SWIM_EX_ID = "139997"
EQUIPMENT_PREFIX = "item/equipment/mod/fantasy"
SOUL_PREFIX = "item/equipment/mod/fantasy/soul"

ABILITY_LOGICAL = "master/ability/ability.orderedmap"
LEADER_LOGICAL = "master/ability/leader_ability.orderedmap"
UNIQUE_LOGICAL = "master/character/unique_condition.orderedmap"
ACTION_SKILL_LOGICAL = "master/skill/action_skill.orderedmap"
CHARACTER_TEXT_LOGICAL = "master/character/character_text.orderedmap"
ITEM_LOGICAL = "master/item/item.orderedmap"
TRIM_LOGICAL = "master/generated/trimmed_image.orderedmap"

ACTIVE_COMMON_SHA256 = "552ea55716662a701afbeee06e9520823a9ab46b5fb60c0b9bd782ee43778ba0"
ITEM_BASE_ARCHIVE = "pinball-1.4.77-1.4.78-2-0816-thunder-abyss-fantasy.zip"
ITEM_BASE_SHA256 = "4252a66b39ede2140e88be5cc005c386eb56863b27135ac15b95d16e4b19f7c6"

WEAPONS = (
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


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def live_path(root: Path, logical: str) -> Path:
    digest = core.sha1_path(logical)
    return root / "assets/asset-patch/production/upload" / digest[:2] / digest[2:]


def active_common_archive(root: Path) -> Path:
    active_path = root / ".cdn/cn/character-releases/active.json"
    active = json.loads(active_path.read_text(encoding="utf-8-sig"))
    if active.get("base_version") != "1.4.79":
        raise PublishError(f"unexpected active character-release base: {active_path}")
    releases = active.get("releases")
    if not isinstance(releases, list) or len(releases) != 1:
        raise PublishError(f"unexpected active character-release count: {active_path}")
    release = releases[0]
    if release.get("from_version") != "1.4.79" or release.get("version") != BASE_VERSION:
        raise PublishError(f"active character release is not the 1.4.80 edge: {active_path}")
    common = [entry for entry in release.get("archives", []) if entry.get("root") == "common"]
    if len(common) != 1:
        raise PublishError(f"active release has no unique common archive: {active_path}")
    receipt = common[0]
    archive = root / ".cdn/cn" / str(receipt["relative_path"])
    if not archive.is_file():
        raise PublishError(f"active common archive is missing: {archive}")
    if archive.stat().st_size != receipt.get("size"):
        raise PublishError(f"active common archive size drifted: {archive}")
    digest = sha256_file(archive)
    if digest != receipt.get("sha256") or digest != ACTIVE_COMMON_SHA256:
        raise PublishError(f"active common archive hash drifted: {archive}")
    return archive


def read_member(archive: Path, logical: str) -> bytes:
    member = member_name(logical)
    with zipfile.ZipFile(archive) as bundle:
        try:
            return bundle.read(member)
        except KeyError as exc:
            raise PublishError(f"baseline archive lacks {logical}: {archive}") from exc


def item_baseline(root: Path) -> bytes:
    archive = root / "assets/asset-patch/active" / ITEM_BASE_ARCHIVE
    raw = read_member(archive, ITEM_LOGICAL)
    if sha256_bytes(raw) != ITEM_BASE_SHA256:
        raise PublishError(f"terminal item baseline drifted: {archive}")
    return raw


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


def patch_flat_rows(raw: bytes, replacements: dict[str, str], additions: dict[str, str] | None = None) -> bytes:
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


def patch_ability(raw: bytes) -> bytes:
    rows = flat_rows(raw)
    value = rows.get("1399983")
    if value is None:
        raise PublishError("ability 1399983 is missing")
    lines = core.read_csv_lines(value)
    if len(lines) != 3 or any(len(row) != 126 for row in lines):
        raise PublishError("ability 1399983 shape drifted")
    expected = (("25000", "25000"), ("25000", "25000"))
    for index, pair in enumerate(expected):
        if (lines[index][51], lines[index][52]) != pair:
            raise PublishError(f"ability 1399983 line {index + 1} gauge values drifted")
    lines[0][51] = lines[0][52] = "5000"
    lines[1][51] = lines[1][52] = "10000"
    return patch_flat_rows(raw, {"1399983": core.write_csv_lines(lines)})


def patch_leader(raw: bytes) -> bytes:
    rows = flat_rows(raw)
    value = rows.get(CHARACTER_ID)
    if value is None:
        raise PublishError("leader ability 139998 is missing")
    lines = core.read_csv_lines(value)
    if len(lines) != 5 or len(lines[4]) != 124:
        raise PublishError("leader ability 139998 shape drifted")
    if (lines[4][55], lines[4][56]) != ("18000000", "18000000"):
        raise PublishError("leader ability 雷电增幅 is not already 18 seconds")
    swim_value = rows.get(SWIM_EX_ID)
    if swim_value is None:
        raise PublishError("leader ability 139997 is missing")
    swim_lines = core.read_csv_lines(swim_value)
    if len(swim_lines) != 9 or len(swim_lines[6]) != 124:
        raise PublishError("leader ability 139997 shape drifted")
    swim_trigger = swim_lines[6]
    expected_trigger = {
        4: "2", 7: "600000", 8: "600000", 9: "Yellow",
        25: "23", 26: "5", 27: "Yellow", 28: "100000", 29: "100000",
        45: "211", 46: "5", 47: "Yellow", 49: "10000", 50: "10000",
    }
    if any(swim_trigger[index] != expected for index, expected in expected_trigger.items()):
        raise PublishError("leader ability 139997 resonance gauge row drifted")
    swim_trigger[49] = swim_trigger[50] = "8000"
    return patch_flat_rows(raw, {SWIM_EX_ID: core.write_csv_lines(swim_lines)})


def patch_unique_condition(raw: bytes) -> bytes:
    rows = flat_rows(raw)
    value = rows.get(CHARACTER_ID)
    if value is None:
        raise PublishError("unique condition 139998 is missing")
    lines = core.read_csv_lines(value)
    if len(lines) != 1 or len(lines[0]) < 4 or lines[0][3] != "600":
        raise PublishError("unique condition 139998 duration drifted")
    lines[0][3] = "1080"
    return patch_flat_rows(raw, {CHARACTER_ID: core.write_csv_lines(lines)})


def patch_action_skill(raw: bytes) -> bytes:
    outer = core.read_orderedmap_raw_rows_from_bytes(raw, ACTION_SKILL_LOGICAL)
    try:
        index = outer.keys.index(CHARACTER_CODE)
    except ValueError as exc:
        raise PublishError(f"action skill {CHARACTER_CODE} is missing") from exc
    entries = core.decode_action_skill_row(outer.rows[index])
    if [key for key, _ in entries] != ["1", "2"]:
        raise PublishError("thunder-dragon action-skill forms drifted")
    for key, row in entries:
        if len(row) != 24 or row[1].count("10秒") != 1 or "18秒" in row[1]:
            raise PublishError(f"action-skill description drifted: form {key}")
        row[1] = row[1].replace("10秒", "18秒")
    outer.rows[index] = core.encode_action_skill_row(entries)
    return core.build_orderedmap_raw_rows(outer)


def patch_character_text(raw: bytes) -> bytes:
    rows = flat_rows(raw)
    value = rows.get(CHARACTER_ID)
    if value is None or value.count("10秒") != 2 or "18秒" in value:
        raise PublishError("character_text 139998 duration text drifted")
    return patch_flat_rows(raw, {CHARACTER_ID: value.replace("10秒", "18秒")})


def patch_item(raw: bytes) -> bytes:
    rows = flat_rows(raw)
    replacements: dict[str, str] = {}
    for item_id, _name, _icon_file, _soul_file, slug in WEAPONS:
        value = rows.get(item_id)
        if value is None:
            raise PublishError(f"Fantasy soul item is missing: {item_id}")
        lines = core.read_csv_lines(value)
        expected = f"{EQUIPMENT_PREFIX}/{slug}"
        if len(lines) != 1 or len(lines[0]) < 4 or lines[0][3] != expected:
            raise PublishError(f"Fantasy soul item image path drifted: {item_id}")
        lines[0][3] = f"{SOUL_PREFIX}/{slug}"
        replacements[item_id] = core.write_csv_lines(lines)
    return patch_flat_rows(raw, replacements)


def validate_png(path: Path) -> tuple[bytes, str]:
    if not path.is_file():
        raise PublishError(f"input PNG is missing: {path}")
    raw = path.read_bytes()
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if image.format != "PNG" or image.size != (20, 20) or image.mode != "RGBA":
            raise PublishError(f"input must be a native 20x20 RGBA PNG: {path}")
        alpha = image.getchannel("A")
        if alpha.getextrema() != (0, 255):
            raise PublishError(f"input must contain transparent and opaque pixels: {path}")
        bbox = alpha.getbbox()
        if bbox is None:
            raise PublishError(f"input has no visible pixels: {path}")
        left, top, right, bottom = bbox
        trim = f"{left},{top},{right - left},{bottom - top}"
    encoded = wf_assets.png_encode(raw)
    if wf_assets.png_decode(encoded) != raw:
        raise PublishError(f"client PNG codec round-trip failed: {path}")
    return raw, trim


def load_images() -> dict[str, dict]:
    expected_equipment = {entry[2] for entry in WEAPONS}
    expected_souls = {entry[3] for entry in WEAPONS}
    actual_equipment = {
        path.name for path in INPUT_ROOT.iterdir()
        if path.is_file() and path.suffix.lower() == ".png"
    }
    actual_souls = {
        path.name for path in SOUL_INPUT_ROOT.iterdir()
        if path.is_file() and path.suffix.lower() == ".png"
    }
    if actual_equipment != expected_equipment:
        raise PublishError(
            f"V4 equipment PNG set drifted: missing={sorted(expected_equipment - actual_equipment)}, "
            f"unexpected={sorted(actual_equipment - expected_equipment)}"
        )
    if actual_souls != expected_souls:
        raise PublishError(
            f"V4 soul PNG set drifted: missing={sorted(expected_souls - actual_souls)}, "
            f"unexpected={sorted(actual_souls - expected_souls)}"
        )
    images: dict[str, dict] = {}
    for item_id, name, icon_file, soul_file, slug in WEAPONS:
        equipment_raw, equipment_trim = validate_png(INPUT_ROOT / icon_file)
        soul_raw, soul_trim = validate_png(SOUL_INPUT_ROOT / soul_file)
        images[slug] = {
            "id": item_id,
            "name": name,
            "equipment": equipment_raw,
            "equipment_trim": equipment_trim,
            "soul": soul_raw,
            "soul_trim": soul_trim,
        }
    return images


def patch_trim(raw: bytes, images: dict[str, dict]) -> bytes:
    rows = flat_rows(raw)
    replacements: dict[str, str] = {}
    additions: dict[str, str] = {}
    for _item_id, _name, _icon_file, _soul_file, slug in WEAPONS:
        equipment_key = f"{EQUIPMENT_PREFIX}/{slug}"
        soul_key = f"{SOUL_PREFIX}/{slug}"
        if equipment_key not in rows:
            raise PublishError(f"trimmed_image equipment key is missing: {equipment_key}")
        replacements[equipment_key] = images[slug]["equipment_trim"]
        if soul_key in rows:
            raise PublishError(f"dedicated soul trim key already exists: {soul_key}")
        additions[soul_key] = images[slug]["soul_trim"]
    return patch_flat_rows(raw, replacements, additions)


def build_payloads(common_archive: Path, item_raw: bytes, images: dict[str, dict]) -> dict[str, bytes]:
    baseline = {
        logical: read_member(common_archive, logical)
        for logical in (
            ABILITY_LOGICAL,
            LEADER_LOGICAL,
            UNIQUE_LOGICAL,
            ACTION_SKILL_LOGICAL,
            CHARACTER_TEXT_LOGICAL,
            TRIM_LOGICAL,
        )
    }
    payloads = {
        ABILITY_LOGICAL: patch_ability(baseline[ABILITY_LOGICAL]),
        LEADER_LOGICAL: patch_leader(baseline[LEADER_LOGICAL]),
        UNIQUE_LOGICAL: patch_unique_condition(baseline[UNIQUE_LOGICAL]),
        ACTION_SKILL_LOGICAL: patch_action_skill(baseline[ACTION_SKILL_LOGICAL]),
        CHARACTER_TEXT_LOGICAL: patch_character_text(baseline[CHARACTER_TEXT_LOGICAL]),
        ITEM_LOGICAL: patch_item(item_raw),
        TRIM_LOGICAL: patch_trim(baseline[TRIM_LOGICAL], images),
    }
    for _item_id, _name, _icon_file, _soul_file, slug in WEAPONS:
        payloads[f"{EQUIPMENT_PREFIX}/{slug}.png"] = wf_assets.png_encode(images[slug]["equipment"])
        payloads[f"{SOUL_PREFIX}/{slug}.png"] = wf_assets.png_encode(images[slug]["soul"])
    return payloads


def build_archive(payloads: dict[str, bytes]) -> tuple[bytes, dict[str, bytes]]:
    members = {member_name(logical): raw for logical, raw in payloads.items()}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for member in sorted(members):
            info = zipfile.ZipInfo(member, (2026, 8, 17, 20, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, members[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(members):
            raise PublishError("archive member order mismatch")
        for member, payload in members.items():
            if archive.read(member) != payload:
                raise PublishError(f"archive payload mismatch: {member}")
    return raw, members


def validate_manifest(root: Path) -> tuple[dict, bytes]:
    path = root / "assets/asset-patch/manifest.json"
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if value.get("cdn_version") != BASE_VERSION:
        raise PublishError(f"manifest is not at {BASE_VERSION}: {path}")
    if any(patch.get("id") == PATCH_ID for patch in value.get("patches", [])):
        raise PublishError(f"patch is already present: {path}")
    if (root / "assets/asset-patch/active" / ARCHIVE_NAME).exists():
        raise PublishError(f"target archive already exists under {root}")
    return value, raw


def updated_manifest(manifest: dict, archive: bytes, members: dict[str, bytes]) -> bytes:
    value = json.loads(json.dumps(manifest))
    files = sorted(members)
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "雷龙、泳皇女 EX 平衡与幻想连战 V4 图标 1.4.81",
        "description": (
            "调整响彻碧海的雷龙（139998）的雷电增幅持续时间与能力3充能数值；"
            "调整泳皇女 EX（139997）雷属性共鸣队长技的技能槽回复；"
            "替换幻想连战11件装备图标，并为对应魂珠导入独立图标及精确裁切定义。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "files": files,
        "changes": [
            "响彻碧海的雷龙主动技能赋予的雷电增幅由10秒延长至18秒；队长技实效保持并校验为18秒，相关技能文案统一为18秒。",
            "能力3第一条自身技能槽回复由25%调整为5%，第二条除自身外角色技能槽回复由25%调整为10%。",
            "泳皇女 EX 队长技在雷属性共鸣时，雷角色发动技能后的雷属性全队技能槽回复由10%调整为8%。",
            "替换幻想连战11件装备的V4图标。",
            "为11件装备魂珠新增独立逻辑图标，不再复用装备图标。",
            "trimmed_image 按每张PNG的透明通道可见边界写入22条精确裁切定义。",
        ],
        "created_at": "2026-08-17",
        "archive_integrity": [{
            "name": ARCHIVE_NAME,
            "size": len(archive),
            "sha256": sha256_bytes(archive),
            "members": len(files),
        }],
    })
    value["cdn_version"] = PATCH_VERSION
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def patch_server_character_text(raw: bytes) -> bytes:
    value = json.loads(raw.decode("utf-8-sig"))
    rows = value.get(CHARACTER_ID)
    if (
        not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], list)
        or len(rows[0]) < 8
    ):
        raise PublishError("server character_text 139998 is missing or malformed")
    row = rows[0]
    matches = sum(cell.count("10秒") for cell in row if isinstance(cell, str))
    if matches != 2:
        raise PublishError(f"server character_text 139998 expected two 10-second texts, got {matches}")
    value[CHARACTER_ID] = [[
        cell.replace("10秒", "18秒") if isinstance(cell, str) else cell
        for cell in row
    ]]
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".thunder-fantasy-v4.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def canonical_path(root: Path, slug: str, soul: bool) -> Path:
    directory = "fantasy-equipment-souls" if soul else "fantasy-equipment"
    return root / "tools/fantasy-gauntlet-mod-tools/assets" / directory / f"{slug}.png"


def add_target(targets: dict[str, tuple[Path, bytes]], label: str, path: Path, raw: bytes) -> None:
    if label in targets or path in (entry[0] for entry in targets.values()):
        raise PublishError(f"duplicate publication target: {path}")
    targets[label] = (path, raw)


def verify_payloads(payloads: dict[str, bytes], images: dict[str, dict]) -> None:
    ability = flat_rows(payloads[ABILITY_LOGICAL])["1399983"]
    lines = core.read_csv_lines(ability)
    if (lines[0][51], lines[0][52], lines[1][51], lines[1][52]) != ("5000", "5000", "10000", "10000"):
        raise PublishError("ability readback verification failed")
    unique = core.read_csv_lines(flat_rows(payloads[UNIQUE_LOGICAL])[CHARACTER_ID])
    if unique[0][3] != "1080":
        raise PublishError("active-skill duration readback verification failed")
    leader = core.read_csv_lines(flat_rows(payloads[LEADER_LOGICAL])[CHARACTER_ID])
    if (leader[4][55], leader[4][56]) != ("18000000", "18000000"):
        raise PublishError("leader duration readback verification failed")
    swim_leader = core.read_csv_lines(flat_rows(payloads[LEADER_LOGICAL])[SWIM_EX_ID])
    if (swim_leader[6][49], swim_leader[6][50]) != ("8000", "8000"):
        raise PublishError("swim-EX leader gauge readback verification failed")
    item = flat_rows(payloads[ITEM_LOGICAL])
    trim = flat_rows(payloads[TRIM_LOGICAL])
    for item_id, _name, _icon_file, _soul_file, slug in WEAPONS:
        row = core.read_csv_lines(item[item_id])[0]
        if row[3] != f"{SOUL_PREFIX}/{slug}":
            raise PublishError(f"soul path readback failed: {item_id}")
        if trim[f"{EQUIPMENT_PREFIX}/{slug}"] != images[slug]["equipment_trim"]:
            raise PublishError(f"equipment trim readback failed: {slug}")
        if trim[f"{SOUL_PREFIX}/{slug}"] != images[slug]["soul_trim"]:
            raise PublishError(f"soul trim readback failed: {slug}")
        if wf_assets.png_decode(payloads[f"{EQUIPMENT_PREFIX}/{slug}.png"]) != images[slug]["equipment"]:
            raise PublishError(f"equipment PNG readback failed: {slug}")
        if wf_assets.png_decode(payloads[f"{SOUL_PREFIX}/{slug}.png"]) != images[slug]["soul"]:
            raise PublishError(f"soul PNG readback failed: {slug}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    images = load_images()
    source_manifest, source_manifest_raw = validate_manifest(SOURCE_ROOT)
    deploy_manifest, deploy_manifest_raw = validate_manifest(DEPLOY_ROOT)
    if source_manifest != deploy_manifest or source_manifest_raw != deploy_manifest_raw:
        raise PublishError("source and deployed manifests differ")
    source_common = active_common_archive(SOURCE_ROOT)
    deploy_common = active_common_archive(DEPLOY_ROOT)
    if source_common.read_bytes() != deploy_common.read_bytes():
        raise PublishError("source and deployed active common archives differ")
    source_item = item_baseline(SOURCE_ROOT)
    deploy_item = item_baseline(DEPLOY_ROOT)
    if source_item != deploy_item:
        raise PublishError("source and deployed terminal item baselines differ")

    payloads = build_payloads(source_common, source_item, images)
    verify_payloads(payloads, images)
    archive, members = build_archive(payloads)
    manifest_raw = updated_manifest(source_manifest, archive, members)

    server_texts: dict[Path, bytes] = {}
    for root in (SOURCE_ROOT, DEPLOY_ROOT):
        path = root / "assets/cdndata/character_text.json"
        server_texts[root] = patch_server_character_text(path.read_bytes())

    report = {
        "apply": args.apply,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "patch_id": PATCH_ID,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "archive_sha256": sha256_bytes(archive),
        "members": len(members),
        "thunder_dragon": {
            "id": CHARACTER_ID,
            "active_amp_frames": {"before": 600, "after": 1080},
            "leader_amp_microseconds": {"before_terminal": 18000000, "after": 18000000},
            "ability3_self_gauge": {"before": 25000, "after": 5000},
            "ability3_other_gauge": {"before": 25000, "after": 10000},
        },
        "swim_ex": {
            "id": SWIM_EX_ID,
            "leader_resonance_party_gauge": {"before": 10000, "after": 8000},
        },
        "icons": [
            {
                "id": images[slug]["id"],
                "name": images[slug]["name"],
                "slug": slug,
                "equipment_sha256": sha256_bytes(images[slug]["equipment"]),
                "equipment_trim": images[slug]["equipment_trim"],
                "soul_sha256": sha256_bytes(images[slug]["soul"]),
                "soul_trim": images[slug]["soul_trim"],
            }
            for _item_id, _name, _icon_file, _soul_file, slug in WEAPONS
        ],
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    targets: dict[str, tuple[Path, bytes]] = {}
    for label, root in (("source", SOURCE_ROOT), ("deploy", DEPLOY_ROOT)):
        add_target(targets, f"{label}-manifest", root / "assets/asset-patch/manifest.json", manifest_raw)
        add_target(targets, f"{label}-archive", root / "assets/asset-patch/active" / ARCHIVE_NAME, archive)
        add_target(targets, f"{label}-server-character-text", root / "assets/cdndata/character_text.json", server_texts[root])
        for logical, raw in payloads.items():
            add_target(targets, f"{label}-live-{core.sha1_path(logical)}", live_path(root, logical), raw)
        for _item_id, _name, _icon_file, _soul_file, slug in WEAPONS:
            add_target(targets, f"{label}-canonical-equipment-{slug}", canonical_path(root, slug, False), images[slug]["equipment"])
            add_target(targets, f"{label}-canonical-soul-{slug}", canonical_path(root, slug, True), images[slug]["soul"])

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_ROOT / f"thunder-dragon-fantasy-v4-1.4.81-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    existence: dict[str, bool] = {}
    for label, (path, _raw) in targets.items():
        existence[label] = path.is_file()
        if existence[label]:
            destination = backup / label
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    (backup / "existence.json").write_text(
        json.dumps(existence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    try:
        # Publish data/assets first and switch the manifest version last.
        for label, (path, raw) in targets.items():
            if label.endswith("-manifest"):
                continue
            atomic_write(raw, path)
        for label, (path, raw) in targets.items():
            if label.endswith("-manifest"):
                atomic_write(raw, path)

        for label, (path, expected) in targets.items():
            if not path.is_file() or path.read_bytes() != expected:
                raise PublishError(f"publication readback failed: {label} -> {path}")
        for root in (SOURCE_ROOT, DEPLOY_ROOT):
            written = json.loads((root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig"))
            matches = [patch for patch in written.get("patches", []) if patch.get("id") == PATCH_ID]
            if written.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
                raise PublishError(f"manifest readback failed under {root}")
            with zipfile.ZipFile(root / "assets/asset-patch/active" / ARCHIVE_NAME) as bundle:
                if bundle.namelist() != sorted(members):
                    raise PublishError(f"archive readback member list failed under {root}")
                for member, expected in members.items():
                    if bundle.read(member) != expected:
                        raise PublishError(f"archive readback payload failed: {member}")
    except Exception:
        for label, (path, _raw) in reversed(list(targets.items())):
            if existence[label]:
                atomic_write((backup / label).read_bytes(), path)
            elif path.exists():
                resolved = path.resolve(strict=False)
                resolved.relative_to(path.parent.resolve(strict=True))
                path.unlink()
        raise

    report["backup"] = str(backup)
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
