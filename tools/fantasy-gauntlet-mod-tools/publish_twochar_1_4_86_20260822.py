#!/usr/bin/env python3
"""Build the reviewed two-character graft as the local 1.4.85 -> 1.4.86 edge.

The received archive belongs to another CDN chain.  Treat its scripts and
notes as untrusted documentation, consume only the audited row/asset payloads,
rebase its declared rows onto the current active terminal state, and use the
client gacha row as the authority for every server exchange flag.
"""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
TOOL_ROOT = Path(__file__).resolve().parent
SHARE_ARCHIVE = Path(r"F:\wfshare-twochar0822-graft-1.4.350-to-1.4.351.zip")
SHARE_SHA256 = "cc20b327521961e82d1a2b10cf326f34b131fe352116f949f3cbcf683b973ca0"
SHARE_PREFIX = "wfshare-1.4.350-to-1.4.351-graft"

BASE_VERSION = "1.4.85"
PATCH_VERSION = "1.4.86"
PATCH_ID = "twochar-stella-abyss-1.4.86"
ARCHIVE_NAME = "pinball-1.4.85-1.4.86-1-0822-twochar-stella-abyss-ios.zip"

CLIENT_PAYLOAD_NAME = f"{SHARE_PREFIX}/client-tables/client_tables_payload.json"
CLIENT_MANIFEST_NAME = f"{SHARE_PREFIX}/client-tables/client_tables_manifest.json"
SERVER_ROWS_NAME = f"{SHARE_PREFIX}/server-data/twochar0822_rows.json"
SERVER_POOL_NAME = f"{SHARE_PREFIX}/server-data/twochar0822_abyss_pool_rows.json"
REPORT_NAME = f"{SHARE_PREFIX}/report.json"

GACHA_LOGICAL = "master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap"
GACHA_KEY = "cnmod_abyss_limited_gacha_character_5"
ABYSS_GACHA_ID = "990001"
CHARACTER_IDS = ("119997", "149996")
EXPECTED_REPLACED_ASSETS = {
    "production/medium_upload/b2/9213c9e0ecb970f8cab60654815030c948d72c",
    "production/medium_upload/d2/219e1fce07dddc6023c2ca40119ee63819dca0",
}
CUTIN_LOGICALS = tuple(
    f"character/{code}/ui/skill_cutin_{slot}.atf.deflate"
    for code in ("xiaketi", "wind_spgirl_swim")
    for slot in (0, 1)
)
DOC_ROWS = (
    {
        "id": 119997,
        "name": "夏可缇",
        "title": "焚身之誓",
        "rarity": "5★",
        "element": "火",
        "gender": "女性",
        "race": "Human",
    },
    {
        "id": 149996,
        "name": "希尔媞（泳装）",
        "title": "苍蓝疾光",
        "rarity": "5★",
        "element": "风",
        "gender": "女性",
        "race": "Human",
    },
)


def _load_previous_builder():
    path = TOOL_ROOT / "publish_mosiyike_balance_1_4_85_20260821.py"
    spec = importlib.util.spec_from_file_location("publish_mosiyike_1_4_85", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper builder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = _load_previous_builder()
core = base.core
wf_assets = base.wf_assets
wf_atf = base.wf_atf


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


def table_member(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def platform_member(logical: str, root: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/{root}/{digest[:2]}/{digest[2:]}"


def normalize_member(value: str) -> str:
    normalized = value.replace("\\", "/").lstrip("./")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 4:
        raise PublishError(f"unsafe package member: {value}")
    return normalized


def read_manifest() -> dict[str, Any]:
    path = SOURCE_ROOT / "assets/asset-patch/manifest.json"
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if value.get("cdn_version") != BASE_VERSION:
        raise PublishError(f"manifest is not at {BASE_VERSION}: {path}")
    if any(entry.get("id") == PATCH_ID for entry in value.get("patches", [])):
        raise PublishError(f"patch is already registered: {PATCH_ID}")
    target = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
    if target.exists():
        raise PublishError(f"target archive already exists: {target}")
    base.active_archives(SOURCE_ROOT, value)
    return value


def read_share() -> dict[str, Any]:
    if not SHARE_ARCHIVE.is_file() or sha256_file(SHARE_ARCHIVE) != SHARE_SHA256:
        raise PublishError("reviewed share archive is missing or its SHA-256 drifted")
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
            raise PublishError(f"share archive lacks required payloads: {sorted(missing)}")
        payload = json.loads(outer.read(CLIENT_PAYLOAD_NAME))
        payload_manifest = json.loads(outer.read(CLIENT_MANIFEST_NAME))
        server_rows = json.loads(outer.read(SERVER_ROWS_NAME))
        server_pool = json.loads(outer.read(SERVER_POOL_NAME))
        report = json.loads(outer.read(REPORT_NAME))
        assets: dict[str, bytes] = {}
        for output in report.get("outputs", []):
            nested_name = f"{SHARE_PREFIX}/{output['path']}"
            raw = outer.read(nested_name)
            if len(raw) != int(output["size"]) or sha256_bytes(raw) != output["sha256"]:
                raise PublishError(f"nested share archive drifted: {nested_name}")
            with zipfile.ZipFile(io.BytesIO(raw)) as nested:
                for info in nested.infolist():
                    if info.is_dir():
                        continue
                    member = normalize_member(info.filename)
                    if not member.startswith((
                        "production/upload/",
                        "production/medium_upload/",
                        "production/android_upload/",
                    )):
                        raise PublishError(f"unsupported asset root: {member}")
                    value = nested.read(info)
                    if member in assets and assets[member] != value:
                        raise PublishError(f"share archives disagree on member: {member}")
                    assets[member] = value
    if len(payload) != 20 or sum(len(rows) for rows in payload.values()) != 57:
        raise PublishError("client row payload shape drifted")
    if set(payload) != set(payload_manifest):
        raise PublishError("client payload and row manifest table sets disagree")
    for logical, rows in payload.items():
        if set(rows) != set(payload_manifest[logical]["keys"]):
            raise PublishError(f"client row manifest disagrees: {logical}")
    if report.get("asset_entries") != 444 or len(assets) != 444:
        raise PublishError(f"share asset count drifted: {len(assets)}")
    if set(server_rows) != {
        "character.json",
        "cdndata/character.json",
        "cdndata/character_text.json",
        "mana_node.json",
    }:
        raise PublishError("server character payload file set drifted")
    return {
        "payload": payload,
        "payload_manifest": payload_manifest,
        "server_rows": server_rows,
        "server_pool": server_pool,
        "assets": assets,
        "report": report,
    }


def build_ios_cutins(assets: dict[str, bytes]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for logical in CUTIN_LOGICALS:
        android_member = platform_member(logical, "android_upload")
        ios_member = platform_member(logical, "ios_upload")
        png_logical = logical.removesuffix(".atf.deflate") + ".png"
        png_member = platform_member(png_logical, "medium_upload")
        if android_member not in assets or png_member not in assets:
            raise PublishError(f"cut-in platform pair is incomplete: {logical}")
        android_plain = wf_atf.inflate(assets[android_member])
        android_info = wf_atf.parse_atf(android_plain)
        if (android_info["slot"], android_info["layout"]) != (2, "etc1"):
            raise PublishError(f"Android cut-in is not ETC1 slot 2: {logical}")
        png = wf_assets.png_decode(assets[png_member])
        if png[:8] != wf_assets.PNG_REAL:
            raise PublishError(f"cut-in source is not a PNG: {png_logical}")
        ios_plain = wf_atf.build_cutin_atf_ios(png, android_plain)
        wf_atf.validate_cutin_platform_pair(android_plain, ios_plain, png)
        ios_info = wf_atf.parse_atf(ios_plain)
        if (ios_info["slot"], ios_info["layout"]) != (3, "etc2-rgba"):
            raise PublishError(f"iOS cut-in is not ETC2 RGBA slot 3: {logical}")
        assets[ios_member] = wf_atf.deflate(ios_plain)
        report[logical] = {
            "android": "ETC1 slot 2",
            "ios": "ETC2 RGBA slot 3",
            "size": [ios_info["w"], ios_info["h"]],
            "mips": ios_info["mips"],
        }
    return report


def build_client_payloads(
    manifest: dict[str, Any], share: dict[str, Any]
) -> tuple[dict[str, bytes], dict[str, Any], bytes]:
    package_assets = copy.deepcopy(share["assets"])
    wanted = set(package_assets)
    wanted.update(table_member(logical) for logical in share["payload"])
    terminal, sources = base.terminal_members(SOURCE_ROOT, manifest, wanted)
    missing_tables = [
        logical for logical in share["payload"] if table_member(logical) not in terminal
    ]
    if missing_tables:
        raise PublishError(f"active terminal lacks client tables: {missing_tables}")

    classification = {"new": [], "same": [], "different": []}
    for member, value in package_assets.items():
        state = "new" if member not in terminal else (
            "same" if terminal[member] == value else "different"
        )
        classification[state].append(member)
    for values in classification.values():
        values.sort()
    counts = {key: len(value) for key, value in classification.items()}
    if counts != {"new": 442, "same": 0, "different": 2}:
        raise PublishError(f"package/current asset classification drifted: {counts}")
    if set(classification["different"]) != EXPECTED_REPLACED_ASSETS:
        raise PublishError("unexpected same-path asset replacement remains")

    table_payloads: dict[str, bytes] = {}
    table_report: dict[str, Any] = {}
    client_gacha_row = b""
    for logical, encoded_rows in share["payload"].items():
        member = table_member(logical)
        incoming = {key: base64.b64decode(raw) for key, raw in encoded_rows.items()}
        candidate, added, changed = base.upsert_table_rows(
            terminal[member], logical, incoming
        )
        if candidate == terminal[member]:
            raise PublishError(f"approved client table produced no change: {logical}")
        table_payloads[member] = candidate
        table_report[logical] = {"added": added, "changed": changed}
        if logical == GACHA_LOGICAL:
            client_gacha_row = incoming[GACHA_KEY]
    if len(table_payloads) != 20 or not client_gacha_row:
        raise PublishError("final client table set drifted")

    output = dict(package_assets)
    if set(output) & set(table_payloads):
        raise PublishError("share assets unexpectedly contain a stripped table")
    output.update(table_payloads)
    ios_report = build_ios_cutins(output)
    root_counts = {
        root: sum(member.startswith(prefix) for member in output)
        for root, prefix in {
            "common": "production/upload/",
            "medium": "production/medium_upload/",
            "android": "production/android_upload/",
            "ios": "production/ios_upload/",
        }.items()
    }
    if root_counts != {"common": 408, "medium": 52, "android": 4, "ios": 4}:
        raise PublishError(f"final client root counts drifted: {root_counts}")
    if len(output) != 468:
        raise PublishError(f"final active member count drifted: {len(output)}")
    return output, {
        "terminal_sources": sources,
        "package_assets": classification,
        "tables": table_report,
        "ios": ios_report,
        "root_counts": root_counts,
    }, client_gacha_row


def client_gacha_rows(raw_inner: bytes) -> list[dict[str, Any]]:
    values = core.read_orderedmap_file_from_bytes(raw_inner)
    rows: list[dict[str, Any]] = []
    for key in values:
        lines = core.read_csv_lines(values[key])
        if len(lines) != 1 or len(lines[0]) != 7:
            raise PublishError(f"abyss client row shape drifted: {key}")
        row = lines[0]
        rows.append({
            "id": int(row[0]),
            "rank": int(row[1]),
            "odds": int(row[2]),
            "isRateUp": row[3] == "true",
            "isLimited": row[4] == "true",
            "isExchangeable": row[5] == "true",
            "trialReadingForced": row[6] == "true",
        })
    if len(rows) != 249 or len({row["id"] for row in rows}) != 249:
        raise PublishError("abyss client gacha does not contain 249 unique characters")
    return rows


def json_output(current_raw: bytes, value: Any) -> bytes:
    newline = b"\n" if current_raw.endswith(b"\n") else b""
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + newline


def build_character_csv(current_raw: bytes) -> bytes:
    has_utf8_bom = current_raw.startswith(b"\xef\xbb\xbf")
    text = current_raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames
    if not fieldnames:
        raise PublishError("generated character CSV has no header")
    rows = list(reader)
    existing = {int(row["id"]) for row in rows}
    if any(row["id"] in existing for row in DOC_ROWS):
        raise PublishError("new characters already exist in generated character CSV")
    rows.extend({key: str(value) for key, value in row.items()} for row in DOC_ROWS)
    rows.sort(key=lambda row: int(row["id"]))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator=newline)
    writer.writeheader()
    writer.writerows(rows)
    encoded = output.getvalue().encode("utf-8")
    return (b"\xef\xbb\xbf" if has_utf8_bom else b"") + encoded


def build_server_outputs(
    share: dict[str, Any], client_gacha_inner: bytes
) -> tuple[dict[Path, bytes], dict[str, Any]]:
    outputs: dict[Path, bytes] = {}
    server_rows = share["server_rows"]
    for relative, incoming in server_rows.items():
        if set(incoming) != set(CHARACTER_IDS):
            raise PublishError(f"server character key set drifted: {relative}")
        path = SOURCE_ROOT / "assets" / relative
        raw = path.read_bytes()
        current = json.loads(raw.decode("utf-8-sig"))
        if any(character_id in current for character_id in CHARACTER_IDS):
            raise PublishError(f"new character already exists in server table: {relative}")
        for character_id in CHARACTER_IDS:
            current[character_id] = incoming[character_id]
        outputs[path] = json_output(raw, current)

    client_rows = client_gacha_rows(client_gacha_inner)
    client_by_id = {row["id"]: row for row in client_rows}
    package_pool = copy.deepcopy(
        share["server_pool"]["gacha.json"][ABYSS_GACHA_ID]
    )
    server_five = package_pool["pool"]["1"]
    if len(server_five) != 249 or {row["id"] for row in server_five} != set(client_by_id):
        raise PublishError("client/server abyss pool membership disagrees")
    authoritative_fields = (
        "rank", "odds", "isRateUp", "isLimited", "isExchangeable",
        "trialReadingForced",
    )
    mismatches: list[tuple[int, str]] = []
    for row in server_five:
        approved = client_by_id[row["id"]]
        for field in authoritative_fields:
            if row.get(field) != approved[field]:
                mismatches.append((row["id"], field))
            row[field] = approved[field]
    if len(mismatches) != 217 or {field for _id, field in mismatches} != {"isExchangeable"}:
        raise PublishError(f"package client/server mismatch set drifted: {mismatches[:10]}")
    if sum(row["odds"] for row in server_five) != 1_593_000:
        raise PublishError("abyss five-star odds total drifted")
    if sum(bool(row["isExchangeable"]) for row in server_five) != 30:
        raise PublishError("client-authoritative exchangeable count drifted")
    if not all(row["isRateUp"] for row in server_five[:13]) or any(
        row["isRateUp"] for row in server_five[13:]
    ):
        raise PublishError("the 13 abyss rate-up rows are not a contiguous prefix")
    featured = {row["id"]: row for row in server_five[:13]}
    new_ids = {119997, 149996}
    old_featured = {
        129997, 129999, 139997, 139998, 139999, 149997,
        149998, 149999, 169998, 169999, 179999,
    }
    if set(featured) != new_ids | old_featured:
        raise PublishError("abyss featured membership drifted")
    for character_id in new_ids:
        row = featured[character_id]
        if row["odds"] != 40356 or row["isExchangeable"]:
            raise PublishError(f"new-character abyss settings drifted: {character_id}")
    for character_id in old_featured:
        row = featured[character_id]
        if row["odds"] != 10620 or not row["isExchangeable"]:
            raise PublishError(f"existing featured abyss settings drifted: {character_id}")

    for relative in ("gacha.json", "gacha_cnmod.json"):
        path = SOURCE_ROOT / "assets" / relative
        raw = path.read_bytes()
        current = json.loads(raw.decode("utf-8-sig"))
        if ABYSS_GACHA_ID not in current:
            raise PublishError(f"current abyss pool is missing: {path}")
        current[ABYSS_GACHA_ID] = package_pool
        outputs[path] = json_output(raw, current)
    for relative in ("cdndata/gacha.json", "cdndata/gacha_feature_content.json"):
        path = SOURCE_ROOT / "assets" / relative
        current = json.loads(path.read_text(encoding="utf-8-sig"))
        incoming = share["server_pool"][relative][ABYSS_GACHA_ID]
        if current.get(ABYSS_GACHA_ID) != incoming:
            raise PublishError(f"unreviewed CDN gacha metadata difference remains: {relative}")

    json_path = SOURCE_ROOT / "docs/generated/character_table.json"
    json_raw = json_path.read_bytes()
    lookup = json.loads(json_raw.decode("utf-8-sig"))
    existing = {int(row["id"]) for row in lookup}
    if any(row["id"] in existing for row in DOC_ROWS):
        raise PublishError("new characters already exist in generated character JSON")
    lookup.extend(copy.deepcopy(DOC_ROWS))
    lookup.sort(key=lambda row: int(row["id"]))
    outputs[json_path] = json_output(json_raw, lookup)
    csv_path = SOURCE_ROOT / "docs/generated/character_table.csv"
    outputs[csv_path] = build_character_csv(csv_path.read_bytes())

    return outputs, {
        "characters_added": [119997, 149996],
        "gacha_five_star_count": len(server_five),
        "gacha_odds_sum": sum(row["odds"] for row in server_five),
        "gacha_exchangeable_count": sum(
            bool(row["isExchangeable"]) for row in server_five
        ),
        "client_authoritative_exchange_repairs": len(mismatches),
        "gacha_files": ["assets/gacha.json", "assets/gacha_cnmod.json"],
    }


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for member in sorted(payloads):
            info = zipfile.ZipInfo(member, (2026, 8, 22, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(payloads):
            raise PublishError("active archive member order mismatch")
        for member, expected in payloads.items():
            if archive.read(member) != expected:
                raise PublishError(f"active archive readback failed: {member}")
    return raw


def updated_manifest(
    manifest: dict[str, Any], archive: bytes, payloads: dict[str, bytes]
) -> bytes:
    value = copy.deepcopy(manifest)
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "夏可缇、泳装希尔媞、史黛拉觉醒立绘与深渊池 1.4.86",
        "description": (
            "新增夏可缇与泳装希尔媞的完整角色数据和双端资源，更新史黛拉觉醒立绘，"
            "并按客户端权威字段统一深渊限定池概率与兑换政策。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "files": sorted(payloads),
        "changes": [
            "新增火属性★5夏可缇（119997）与风属性★5泳装希尔媞（149996）的角色表、六条能力、队长技、主动技、玛纳板、立绘、像素演出、语音及特效资源。",
            "保留泳装希尔媞能力3的包内终态：主位50连击触发独立技能伤害+5%与独立直接攻击伤害+5%，表内无显式次数、冷却、持续时间或叠加上限。",
            "更新夏日史黛拉（139999）的觉醒槽立绘、插画切换页图集及相应图像几何。",
            "深渊限定池扩为249名五星；两个新角色各0.38%且不可兑换，墨斯伊克与原有10名UP各0.1%且可兑换，五星权重总量保持1593000。",
            "服务端249名五星的概率、UP、限定及兑换字段全部由客户端gacha_odds行回写，修复作者服务端负载中217项兑换标志冲突。",
            "为两个新角色的4张技能切入补齐Android ETC1与iOS ETC2 RGBA平台纹理。",
        ],
        "created_at": "2026-08-22",
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
        f"| 2026-08-22 | character/ability/skill | 119997/149996 | 新增夏可缇与泳装希尔媞完整角色数据及Android/iOS资源 | 1.4.86 | active统一增量包 |{newline}"
        f"| 2026-08-22 | character_image/trimmed_image | 139999 | 更新夏日史黛拉觉醒立绘与插画切换页图集 | 1.4.86 | active统一增量包 |{newline}"
        f"| 2026-08-22 | gacha | 990001 | 按客户端249行权威规则统一深渊池概率与全池兑换字段 | 1.4.86 | active统一增量包 |{newline}"
    )
    return text.replace(marker, marker + rows, 1).encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".twochar-1.4.86.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def assert_target(path: Path) -> None:
    path.resolve(strict=False).relative_to(SOURCE_ROOT.resolve(strict=True))


def build_targets(
    manifest_raw: bytes,
    archive_raw: bytes,
    payloads: dict[str, bytes],
    server_outputs: dict[Path, bytes],
    changelog_raw: bytes,
) -> dict[str, tuple[Path, bytes]]:
    targets: dict[str, tuple[Path, bytes]] = {}

    def add(label: str, path: Path, raw: bytes) -> None:
        assert_target(path)
        if label in targets or path in (entry[0] for entry in targets.values()):
            raise PublishError(f"duplicate publication target: {path}")
        targets[label] = (path, raw)

    add("active-archive", SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME, archive_raw)
    for member, raw in payloads.items():
        add(f"production-{member}", SOURCE_ROOT / "assets/asset-patch" / member, raw)
    for path, raw in server_outputs.items():
        add(f"source-{path.relative_to(SOURCE_ROOT).as_posix()}", path, raw)
    add("changelog", SOURCE_ROOT / "assets/asset-patch/changelog.md", changelog_raw)
    add("manifest", SOURCE_ROOT / "assets/asset-patch/manifest.json", manifest_raw)
    return targets


def apply_targets(
    targets: dict[str, tuple[Path, bytes]], report: dict[str, Any]
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TOOL_ROOT / "work" / f"twochar-1.4.86-backup-{stamp}"
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
        for label, (path, raw) in targets.items():
            if label != "manifest":
                atomic_write(raw, path)
        atomic_write(targets["manifest"][1], targets["manifest"][0])
        for label, (path, expected) in targets.items():
            if not path.is_file() or path.read_bytes() != expected:
                raise PublishError(f"publication readback failed: {label}")
        manifest = json.loads(
            (SOURCE_ROOT / "assets/asset-patch/manifest.json").read_text(
                encoding="utf-8-sig"
            )
        )
        matches = [entry for entry in manifest["patches"] if entry.get("id") == PATCH_ID]
        if manifest.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
            raise PublishError("manifest readback registration failed")
        archive_path = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
        with zipfile.ZipFile(archive_path) as archive:
            if archive.namelist() != matches[0]["files"]:
                raise PublishError("archive and manifest file lists disagree")
        if sha256_file(archive_path) != matches[0]["archive_integrity"][0]["sha256"]:
            raise PublishError("active archive SHA-256 readback failed")
    except Exception:
        for label, (path, _raw) in reversed(list(targets.items())):
            assert_target(path)
            if existence[label]:
                atomic_write((backup / label).read_bytes(), path)
            elif path.exists():
                path.unlink()
        raise
    report["backup"] = str(backup)
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write verified source-repository outputs")
    args = parser.parse_args()

    manifest = read_manifest()
    share = read_share()
    payloads, client_report, client_gacha_inner = build_client_payloads(manifest, share)
    archive_raw = zip_payloads(payloads)
    manifest_raw = updated_manifest(manifest, archive_raw, payloads)
    server_outputs, server_report = build_server_outputs(share, client_gacha_inner)
    changelog_path = SOURCE_ROOT / "assets/asset-patch/changelog.md"
    changelog_raw = updated_changelog(changelog_path.read_bytes())
    report: dict[str, Any] = {
        "apply": args.apply,
        "source_only": True,
        "runtime_mirror_touched": False,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "patch_id": PATCH_ID,
        "share_sha256": SHARE_SHA256,
        "archive": str(SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME),
        "archive_size": len(archive_raw),
        "archive_sha256": sha256_bytes(archive_raw),
        "members": len(payloads),
        "client": client_report,
        "server": server_report,
        "source_files": sorted(
            path.relative_to(SOURCE_ROOT).as_posix() for path in server_outputs
        ),
        "excluded": {
            "share_scripts_executed": False,
            "share_server_exchange_flags_accepted": False,
            "unrelated_worktree_changes_touched": False,
        },
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    targets = build_targets(
        manifest_raw, archive_raw, payloads, server_outputs, changelog_raw
    )
    backup = apply_targets(targets, report)
    report["backup"] = str(backup)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
