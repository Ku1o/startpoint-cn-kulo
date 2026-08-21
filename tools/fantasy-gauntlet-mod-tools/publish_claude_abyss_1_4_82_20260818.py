#!/usr/bin/env python3
"""Publish Claude, abyss-pool v4, Gerald recrops and the official flipper as 1.4.82.

The incoming share archive is anchored to another CDN version.  This builder never
copies that version edge directly.  It reconstructs the current 1.4.81 terminal
state from assets/asset-patch/active, grafts the approved rows, and emits one clean
1.4.81 -> 1.4.82 edge.  The eleven global ui_string shortening rows are deliberately
excluded.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

import wf_mod_tool as core


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
DEPLOY_ROOT = Path(r"F:\startpoint-cn-main")
SHARE_ARCHIVE = Path(r"F:\wfshare-claude0818-graft-1.4.348-to-1.4.349.zip")
SHARE_SHA256 = "00403b3126b7ca053bf7b8760953ad70d5a79324dc1719ec1f6826acd9d5e831"
SHARE_PREFIX = "wfshare-1.4.348-to-1.4.349-graft"
BACKUP_ROOT = Path(r"F:\codex\local-deploy-backups")

BASE_VERSION = "1.4.81"
PATCH_VERSION = "1.4.82"
PATCH_ID = "claude-abyss-gerald-flipper-1.4.82"
ARCHIVE_NAME = "pinball-1.4.81-1.4.82-1-0818-claude-abyss-gerald-flipper.zip"
CLAUDE_ID = "129997"
ABYSS_GACHA_ID = "990001"

CLIENT_PAYLOAD_NAME = f"{SHARE_PREFIX}/client-tables/client_tables_payload.json"
CLIENT_MANIFEST_NAME = f"{SHARE_PREFIX}/client-tables/client_tables_manifest.json"
SERVER_ROWS_NAME = f"{SHARE_PREFIX}/server-data/claude0818_rows.json"
SERVER_POOL_NAME = f"{SHARE_PREFIX}/server-data/claude0818_abyss_pool_v4_rows.json"
REPORT_NAME = f"{SHARE_PREFIX}/report.json"

UI_LOGICAL = "master/string/ui_string.orderedmap"
FLIPPER_LOGICAL = "master/equipment_enhancement/equipment_flipper_skin/flipper_skin.orderedmap"
GACHA_ODDS_LOGICAL = "master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap"
CHARACTER_TEXT_LOGICAL = "master/character/character_text.orderedmap"
RICH_TEXT_LOGICAL = "rich_text/cnmod_abyss_limited_gacha_note.html.deflate"
FLIPPER_LAYER_LOGICAL = "battle/common/layer0.png"

EXPECTED_UI_KEYS = {
    "ability_description_separated_term_character_slayer",
    "ability_description_separated_term_condition_slayer",
    "ability_description_separated_term_stun_wince_slayer",
    "ability_description_separated_term_adversity",
    "ability_description_separated_term_powerflip_lv",
    "ability_description_separated_term_direct_damage",
    "ability_description_separated_term_skill_damage",
    "ability_description_separated_term_ability_damage",
    "ability_description_instant_max_accumulation",
    "ability_description_instant_max_accumulation_count",
    "ability_description_separated_term_damage",
}

GERALD_CHANGED_LOGICALS = {
    "character/white_wolf_gerald/ui/square_0.png",
    "character/white_wolf_gerald/ui/square_1.png",
    "character/white_wolf_gerald/ui/square_132_132_0.png",
    "character/white_wolf_gerald/ui/square_132_132_1.png",
    "character/white_wolf_gerald/ui/square_round_136_136_0.png",
    "character/white_wolf_gerald/ui/square_round_136_136_1.png",
    "character/white_wolf_gerald/ui/square_round_95_95_0.png",
    "character/white_wolf_gerald/ui/square_round_95_95_1.png",
    "character/white_wolf_gerald/ui/battle_member_status_0.png",
    "character/white_wolf_gerald/ui/battle_member_status_1.png",
}


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


def normalize_member(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def member_name(logical: str, root: str = "upload") -> str:
    digest = core.sha1_path(logical)
    return f"production/{root}/{digest[:2]}/{digest[2:]}"


def table_member(logical: str) -> str:
    return member_name(logical, "upload")


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


def terminal_members(
    root: Path,
    manifest: dict[str, Any],
    wanted: set[str],
) -> tuple[dict[str, bytes], dict[str, str]]:
    values: dict[str, bytes] = {}
    sources: dict[str, str] = {}
    for archive_path in active_archives(root, manifest):
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = normalize_member(info.filename)
                if name in wanted:
                    values[name] = archive.read(info)
                    sources[name] = archive_path.name
    return values, sources


def read_manifest(root: Path) -> tuple[dict[str, Any], bytes]:
    path = root / "assets/asset-patch/manifest.json"
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if value.get("cdn_version") != BASE_VERSION:
        raise PublishError(f"manifest is not at {BASE_VERSION}: {path}")
    if any(entry.get("id") == PATCH_ID for entry in value.get("patches", [])):
        raise PublishError(f"patch is already present: {path}")
    if (root / "assets/asset-patch/active" / ARCHIVE_NAME).exists():
        raise PublishError(f"target archive already exists: {root}")
    return value, raw


def read_share() -> dict[str, Any]:
    if not SHARE_ARCHIVE.is_file():
        raise PublishError(f"share archive is missing: {SHARE_ARCHIVE}")
    if sha256_file(SHARE_ARCHIVE) != SHARE_SHA256:
        raise PublishError("share archive hash drifted")
    with zipfile.ZipFile(SHARE_ARCHIVE) as outer:
        required = {
            CLIENT_PAYLOAD_NAME,
            CLIENT_MANIFEST_NAME,
            SERVER_ROWS_NAME,
            SERVER_POOL_NAME,
            REPORT_NAME,
        }
        missing = required - set(outer.namelist())
        if missing:
            raise PublishError(f"share archive lacks required files: {sorted(missing)}")
        payload = json.loads(outer.read(CLIENT_PAYLOAD_NAME))
        payload_manifest = json.loads(outer.read(CLIENT_MANIFEST_NAME))
        server_rows = json.loads(outer.read(SERVER_ROWS_NAME))
        server_pool = json.loads(outer.read(SERVER_POOL_NAME))
        report = json.loads(outer.read(REPORT_NAME))
        asset_members: dict[str, bytes] = {}
        for output in report.get("outputs", []):
            inner_name = f"{SHARE_PREFIX}/{output['path']}"
            raw = outer.read(inner_name)
            if sha256_bytes(raw) != output["sha256"]:
                raise PublishError(f"nested share archive hash drifted: {inner_name}")
            with zipfile.ZipFile(io.BytesIO(raw)) as inner:
                for info in inner.infolist():
                    if info.is_dir():
                        continue
                    name = normalize_member(info.filename)
                    value = inner.read(info)
                    if name in asset_members and asset_members[name] != value:
                        raise PublishError(f"nested share archives disagree: {name}")
                    asset_members[name] = value
    if len(asset_members) != 93:
        raise PublishError(f"share asset member count drifted: {len(asset_members)}")
    if set(payload.get(UI_LOGICAL, {})) != EXPECTED_UI_KEYS:
        raise PublishError("share ui_string exclusion set drifted")
    return {
        "payload": payload,
        "payload_manifest": payload_manifest,
        "server_rows": server_rows,
        "server_pool": server_pool,
        "report": report,
        "asset_members": asset_members,
    }


def upsert_table_rows(
    raw: bytes,
    logical: str,
    incoming: dict[str, str],
) -> tuple[bytes, list[str], list[str]]:
    current = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    keys = list(current.keys)
    rows = list(current.rows)
    positions = {key: index for index, key in enumerate(keys)}
    added: list[str] = []
    changed: list[str] = []
    for key, encoded in incoming.items():
        value = base64.b64decode(encoded)
        if key in positions:
            index = positions[key]
            if rows[index] != value:
                rows[index] = value
                changed.append(key)
        else:
            positions[key] = len(keys)
            keys.append(key)
            rows.append(value)
            added.append(key)
    if not (added or changed):
        return raw, added, changed
    current.keys = keys
    current.rows = rows
    output = core.build_orderedmap_raw_rows(current)
    check = core.read_orderedmap_raw_rows_from_bytes(output, logical)
    check_positions = {key: index for index, key in enumerate(check.keys)}
    for key, encoded in incoming.items():
        if check.rows[check_positions[key]] != base64.b64decode(encoded):
            raise PublishError(f"table graft readback failed: {logical}/{key}")
    return output, added, changed


def raw_deflate(text: str) -> bytes:
    compressor = zlib.compressobj(level=9, wbits=-15)
    raw = compressor.compress(text.encode("utf-8")) + compressor.flush()
    if zlib.decompress(raw, -15).decode("utf-8") != text:
        raise PublishError("rich-text raw-deflate round trip failed")
    return raw


def abyss_note() -> str:
    return """<!DOCTYPE html/>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>深渊限定扭蛋注意事项</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body class="body" style_id="1">
  <div class="container">
    <p>・本扭蛋长期开放，仅可使用深渊单抽券或深渊十连券抽取。</p><br/>
    <p>・本扭蛋不接受星导石或付费星导石抽取。</p><br/>
    <p>・本扭蛋不接受通用角色扭蛋券。</p><br/>
    <p>・★5角色总出现概率为15%，★4角色为35%，★3角色为50%。</p><br/>
    <p>・9名既有深渊限定角色合计出现概率为1%，单人均为1/9%（约0.111%）；克劳德（毒狼EX）单独为0.38%，其余13.62%由其他★5角色均分。</p><br/>
    <p>・使用1张深渊单抽券可抽取1次；使用1张深渊十连券可连续抽取10次。</p><br/>
    <p>・每次抽取累计1点兑换点数；池内除克劳德（毒狼EX）外，其余245名★5角色均可使用250点兑换。</p><br/>
    <p>・克劳德（毒狼EX）不可用兑换点数兑换，仅能通过抽取获得。</p><br/>
    <p>・重复获得已有角色时，按游戏现有角色重复获得规则处理。</p>
  </div>
</body>
</html>
"""


def logical_members(logicals: set[str], root_name: str) -> set[str]:
    return {member_name(logical, root_name) for logical in logicals}


def classify_assets(
    package_assets: dict[str, bytes],
    current: dict[str, bytes],
) -> tuple[list[str], list[str], list[str]]:
    new: list[str] = []
    same: list[str] = []
    different: list[str] = []
    for member, value in package_assets.items():
        if member not in current:
            new.append(member)
        elif current[member] == value:
            same.append(member)
        else:
            different.append(member)
    return sorted(new), sorted(same), sorted(different)


def build_client_payloads(
    manifest: dict[str, Any],
    share: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    payload: dict[str, dict[str, str]] = share["payload"]
    package_assets: dict[str, bytes] = share["asset_members"]
    table_logicals = set(payload)
    wanted = set(package_assets) | {table_member(logical) for logical in table_logicals}
    terminal, sources = terminal_members(SOURCE_ROOT, manifest, wanted)
    missing_tables = {
        logical for logical in table_logicals if table_member(logical) not in terminal
    }
    if missing_tables:
        raise PublishError(f"active terminal lacks tables: {sorted(missing_tables)}")

    new_assets, same_assets, different_assets = classify_assets(package_assets, terminal)
    if (len(new_assets), len(same_assets), len(different_assets)) != (62, 18, 13):
        raise PublishError(
            "share/current asset classification drifted: "
            f"new={len(new_assets)} same={len(same_assets)} different={len(different_assets)}"
        )

    gerald_members = logical_members(GERALD_CHANGED_LOGICALS, "medium_upload")
    flipper_members = {
        member_name(FLIPPER_LAYER_LOGICAL, "upload"),
        member_name(FLIPPER_LAYER_LOGICAL, "android_upload"),
    }
    rich_member = member_name(RICH_TEXT_LOGICAL, "upload")
    expected_different = gerald_members | flipper_members | {rich_member}
    if set(different_assets) != expected_different:
        raise PublishError(
            "same-path/different-byte asset set drifted: "
            f"unexpected={sorted(set(different_assets) - expected_different)}, "
            f"missing={sorted(expected_different - set(different_assets))}"
        )

    output: dict[str, bytes] = {}
    table_report: dict[str, dict[str, list[str]]] = {}
    for logical, incoming in payload.items():
        baseline = terminal[table_member(logical)]
        if logical == UI_LOGICAL:
            continue
        if logical == FLIPPER_LOGICAL:
            candidate, added, changed = upsert_table_rows(baseline, logical, incoming)
            if candidate != baseline or added or changed:
                raise PublishError("flipper table is not already at the approved official rows")
            continue
        candidate, added, changed = upsert_table_rows(baseline, logical, incoming)
        if candidate != baseline:
            output[table_member(logical)] = candidate
            table_report[logical] = {"added": added, "changed": changed}

    if len(table_report) != 20:
        raise PublishError(f"changed client-table count drifted: {len(table_report)}")
    if UI_LOGICAL in table_report or table_member(UI_LOGICAL) in output:
        raise PublishError("global ui_string shortening leaked into output")
    if GACHA_ODDS_LOGICAL not in table_report:
        raise PublishError("abyss client odds row was not changed")

    for member in new_assets:
        output[member] = package_assets[member]
    for member in sorted(gerald_members | flipper_members):
        output[member] = package_assets[member]
    output[rich_member] = raw_deflate(abyss_note())

    if len(output) != 95:
        raise PublishError(f"final active member count drifted: {len(output)}")
    return output, {
        "terminal_sources": sources,
        "asset_classification": {
            "new": new_assets,
            "same_omitted": same_assets,
            "different_included": different_assets,
        },
        "table_effects": table_report,
    }


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for member in sorted(payloads):
            info = zipfile.ZipInfo(member, (2026, 8, 18, 20, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(payloads):
            raise PublishError("active archive member order mismatch")
        for member, value in payloads.items():
            if archive.read(member) != value:
                raise PublishError(f"active archive readback failed: {member}")
    return raw


def json_output(current_raw: bytes, value: Any) -> bytes:
    newline = b"\n" if current_raw.endswith(b"\n") else b""
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + newline


def rebuild_server_character_text(payload: dict[str, dict[str, str]]) -> list[list[str]]:
    compressed = base64.b64decode(payload[CHARACTER_TEXT_LOGICAL][CLAUDE_ID])
    text = zlib.decompress(compressed).decode("utf-8")
    rows = core.read_csv_lines(text)
    if len(rows) != 1 or len(rows[0]) != 12:
        raise PublishError("Claude client character_text row shape drifted")
    row = rows[0]
    if row[0] != "克劳德" or row[3] != "碧牙的狩夜者" or row[4] != "蚀刃终决":
        raise PublishError("Claude client final text drifted")
    return rows


def build_server_outputs(root: Path, share: dict[str, Any]) -> dict[Path, bytes]:
    server_rows: dict[str, dict[str, Any]] = share["server_rows"]
    server_pool: dict[str, dict[str, Any]] = share["server_pool"]
    outputs: dict[Path, bytes] = {}
    text_rows = rebuild_server_character_text(share["payload"])

    for relative in ("character.json", "cdndata/character.json", "mana_node.json"):
        path = root / "assets" / relative
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
        if CLAUDE_ID in data:
            raise PublishError(f"Claude server row already exists: {path}")
        data[CLAUDE_ID] = server_rows[relative][CLAUDE_ID]
        outputs[path] = json_output(raw, data)

    text_path = root / "assets/cdndata/character_text.json"
    text_raw = text_path.read_bytes()
    text_data = json.loads(text_raw.decode("utf-8-sig"))
    if CLAUDE_ID in text_data:
        raise PublishError(f"Claude server text already exists: {text_path}")
    text_data[CLAUDE_ID] = text_rows
    outputs[text_path] = json_output(text_raw, text_data)

    pool_row = server_pool["gacha.json"][ABYSS_GACHA_ID]
    five_stars = pool_row["pool"]["1"]
    if len(five_stars) != 246:
        raise PublishError("abyss package does not contain 246 five-star characters")
    exchangeable = [row for row in five_stars if row.get("isExchangeable")]
    non_exchangeable = [row for row in five_stars if not row.get("isExchangeable")]
    if len(exchangeable) != 245 or [row["id"] for row in non_exchangeable] != [129997]:
        raise PublishError("abyss package exchangeability is not the approved 245/1 split")
    claude = next(row for row in five_stars if row["id"] == 129997)
    swim_ex = next(row for row in five_stars if row["id"] == 139997)
    if claude["odds"] != 40356 or claude["isExchangeable"]:
        raise PublishError("Claude abyss-pool settings drifted")
    if not swim_ex["isExchangeable"]:
        raise PublishError("Swim Princess EX is not exchangeable in the approved pool")

    for relative in ("gacha.json", "gacha_cnmod.json"):
        path = root / "assets" / relative
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
        if ABYSS_GACHA_ID not in data:
            raise PublishError(f"current abyss pool is missing: {path}")
        data[ABYSS_GACHA_ID] = pool_row
        outputs[path] = json_output(raw, data)

    for relative in ("cdndata/gacha.json", "cdndata/gacha_feature_content.json"):
        path = root / "assets" / relative
        current = json.loads(path.read_text(encoding="utf-8-sig"))
        incoming = server_pool[relative][ABYSS_GACHA_ID]
        if current.get(ABYSS_GACHA_ID) != incoming:
            raise PublishError(f"unapproved CDN gacha metadata difference remains: {relative}")

    character_table_path = root / "docs/generated/character_table.json"
    character_table_raw = character_table_path.read_bytes()
    character_table = json.loads(character_table_raw.decode("utf-8-sig"))
    if any(int(row.get("id", 0)) == int(CLAUDE_ID) for row in character_table):
        raise PublishError(f"Claude admin lookup row already exists: {character_table_path}")
    character_table.append({
        "id": int(CLAUDE_ID),
        "name": "克劳德",
        "title": "碧牙的狩夜者",
        "rarity": "5★",
        "element": "水",
        "gender": "男性",
        "race": "Human,Beast",
    })
    character_table.sort(key=lambda row: int(row["id"]))
    outputs[character_table_path] = json_output(character_table_raw, character_table)
    return outputs


def updated_manifest(
    manifest: dict[str, Any],
    archive: bytes,
    payloads: dict[str, bytes],
) -> bytes:
    value = json.loads(json.dumps(manifest))
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "克劳德、深渊池、杰拉德重切与弹板还原 1.4.82",
        "description": (
            "新增水属性★5克劳德（129997）完整角色内容；接收深渊限定池 v4，"
            "使除克劳德外的245名五星均可兑换；纳入杰拉德10张重切图片及官方弹板外观。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "files": sorted(payloads),
        "changes": [
            "新增克劳德（129997）的6条能力、队长技、主动技能、专属强化弹射、淬毒体系、玛纳板、立绘、像素动画、技能特效与19条语音。",
            "克劳德服务端名称、称号与技能文字按客户端终态重建为“碧牙的狩夜者／蚀刃终决”。",
            "深渊限定池新增克劳德0.38%且不可兑换；既有9名深渊角色合计1%，泳皇女EX（139997）改为可兑换。",
            "服务端池内除克劳德外的245名五星均允许使用兑换点数兑换，并重写池说明以匹配实际规则。",
            "替换杰拉德（149999）10张重切头像及战斗状态图片。",
            "common与android两端的战斗弹板layer0恢复为作者提供的官方字节；6条弹板映射已与当前终态一致，不重复改表。",
            "明确排除作者包中的11条全局ui_string能力文字裁短，现有全角色能力说明保持不变。",
        ],
        "created_at": "2026-08-18",
        "archive_integrity": [{
            "name": ARCHIVE_NAME,
            "size": len(archive),
            "sha256": sha256_bytes(archive),
            "members": len(payloads),
        }],
    })
    value["cdn_version"] = PATCH_VERSION
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def updated_changelog(raw: bytes) -> bytes:
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    marker = f"|---|---|---|---|---|---|{newline}"
    if marker not in text:
        raise PublishError("asset patch changelog table header drifted")
    rows = (
        f"| 2026-08-18 | character/ability/skill | 129997 | 新增克劳德完整角色、淬毒体系、PF与语音资源 | 1.4.82 | active增量包 |{newline}"
        f"| 2026-08-18 | gacha | 990001 | 深渊池加入克劳德，139997及其余245名五星可兑换 | 1.4.82 | active增量包 |{newline}"
        f"| 2026-08-18 | image/flipper | 149999/layer0 | 杰拉德10张重切图片与官方弹板外观 | 1.4.82 | active增量包 |{newline}"
    )
    text = text.replace(marker, marker + rows, 1)
    return text.encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".claude-1.4.82.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def assert_target(root: Path, target: Path) -> None:
    target.resolve(strict=False).relative_to(root.resolve(strict=True))


def add_target(
    targets: dict[str, tuple[Path, bytes, Path]],
    label: str,
    root: Path,
    path: Path,
    raw: bytes,
) -> None:
    assert_target(root, path)
    if label in targets or path in (entry[0] for entry in targets.values()):
        raise PublishError(f"duplicate target: {path}")
    targets[label] = (path, raw, root)


def build_root_targets(
    root: Path,
    label: str,
    manifest_raw: bytes,
    archive_raw: bytes,
    payloads: dict[str, bytes],
    server_outputs: dict[Path, bytes],
    changelog_raw: bytes,
) -> dict[str, tuple[Path, bytes, Path]]:
    result: dict[str, tuple[Path, bytes, Path]] = {}
    add_target(
        result, f"{label}-active-archive", root,
        root / "assets/asset-patch/active" / ARCHIVE_NAME, archive_raw,
    )
    for member, raw in payloads.items():
        add_target(
            result, f"{label}-production-{member}", root,
            root / "assets/asset-patch" / member, raw,
        )
    for path, raw in server_outputs.items():
        add_target(result, f"{label}-server-{path.relative_to(root).as_posix()}", root, path, raw)
    add_target(
        result, f"{label}-changelog", root,
        root / "assets/asset-patch/changelog.md", changelog_raw,
    )
    add_target(
        result, f"{label}-manifest", root,
        root / "assets/asset-patch/manifest.json", manifest_raw,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source_manifest, source_manifest_current = read_manifest(SOURCE_ROOT)
    deploy_manifest, deploy_manifest_current = read_manifest(DEPLOY_ROOT)
    if source_manifest_current != deploy_manifest_current or source_manifest != deploy_manifest:
        raise PublishError("source and deployment manifests differ")
    share = read_share()

    payloads, client_report = build_client_payloads(source_manifest, share)
    archive_raw = zip_payloads(payloads)
    manifest_raw = updated_manifest(source_manifest, archive_raw, payloads)

    source_server = build_server_outputs(SOURCE_ROOT, share)
    deploy_server = build_server_outputs(DEPLOY_ROOT, share)
    source_relative = {path.relative_to(SOURCE_ROOT): raw for path, raw in source_server.items()}
    deploy_relative = {path.relative_to(DEPLOY_ROOT): raw for path, raw in deploy_server.items()}
    if source_relative != deploy_relative:
        raise PublishError("source and deployment server baselines differ")

    source_changelog_path = SOURCE_ROOT / "assets/asset-patch/changelog.md"
    deploy_changelog_path = DEPLOY_ROOT / "assets/asset-patch/changelog.md"
    if source_changelog_path.read_bytes() != deploy_changelog_path.read_bytes():
        raise PublishError("source and deployment changelogs differ")
    changelog_raw = updated_changelog(source_changelog_path.read_bytes())

    report = {
        "apply": args.apply,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "patch_id": PATCH_ID,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive_raw),
        "archive_sha256": sha256_bytes(archive_raw),
        "members": len(payloads),
        "client": client_report,
        "server": {
            "claude": int(CLAUDE_ID),
            "abyss_five_stars": 246,
            "exchangeable_five_stars": 245,
            "non_exchangeable_five_stars": [int(CLAUDE_ID)],
            "gacha_files": ["assets/gacha.json", "assets/gacha_cnmod.json"],
            "admin_lookup_added": True,
        },
        "excluded": {
            "ui_string_keys": sorted(EXPECTED_UI_KEYS),
            "identical_gerald_assets": 18,
        },
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    targets: dict[str, tuple[Path, bytes, Path]] = {}
    targets.update(build_root_targets(
        SOURCE_ROOT, "source", manifest_raw, archive_raw, payloads,
        source_server, changelog_raw,
    ))
    targets.update(build_root_targets(
        DEPLOY_ROOT, "deploy", manifest_raw, archive_raw, payloads,
        deploy_server, changelog_raw,
    ))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_ROOT / f"claude-abyss-1.4.82-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    existence: dict[str, bool] = {}
    for label, (path, _raw, _root) in targets.items():
        existence[label] = path.is_file()
        if existence[label]:
            destination = backup / label
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    (backup / "existence.json").write_text(
        json.dumps(existence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    try:
        # Switch manifests last so clients cannot observe a partially written edge.
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
        for root in (SOURCE_ROOT, DEPLOY_ROOT):
            written = json.loads(
                (root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
            )
            matches = [entry for entry in written["patches"] if entry.get("id") == PATCH_ID]
            if written.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
                raise PublishError(f"manifest readback failed: {root}")
            with zipfile.ZipFile(root / "assets/asset-patch/active" / ARCHIVE_NAME) as archive:
                if archive.namelist() != sorted(payloads):
                    raise PublishError(f"archive member readback failed: {root}")
                for member, expected in payloads.items():
                    if archive.read(member) != expected:
                        raise PublishError(f"archive payload readback failed: {root}/{member}")
    except Exception:
        for label, (path, _raw, root) in reversed(list(targets.items())):
            assert_target(root, path)
            if existence[label]:
                atomic_write((backup / label).read_bytes(), path)
            elif path.exists():
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
