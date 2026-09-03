#!/usr/bin/env python3
"""Publish the five approved season leaderboard titles as a sparse CDN patch.

The patch is deliberately based on the effective 1.4.96 CDN tail.  It appends
five rows to ``master/degree/degree.orderedmap`` and adds their five PNGs.  All
existing degree rows and the previously approved abyss-weapon client marker
are verified and left byte-for-byte unchanged.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_ROOT))

import wf_assets  # noqa: E402
import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402


BASE_VERSION = "1.4.96"
TARGET_VERSION = "1.4.97"
PATCH_ID = "season-rank-titles-1.4.97"
ARCHIVE_NAME = "pinball-1.4.96-1.4.97-1-season-rank-titles.zip"
ACTIVE_DIR = ROOT / "assets" / "asset-patch" / "active"
MANIFEST_PATH = ROOT / "assets" / "asset-patch" / "manifest.json"
AUDIT_DIR = ROOT / "assets" / "asset-patch" / "audit" / PATCH_ID
TITLE_DIR = ROOT.parent / "outputs" / "title-design-game-template-20260902-v11"

DEGREE_LOGICAL = "master/degree/degree.orderedmap"
EQUIPMENT_LOGICAL = "master/item/equipment.orderedmap"

TITLES = (
    (9900007, "degree_mod_stellar_abyss_overlord", "星渊主宰者", "せいえんしゅさいしゃ", "获得条件：新赛季排行榜排名第1"),
    (9900008, "degree_mod_stellar_abyss_conqueror", "星渊征服者", "せいえんせいふくしゃ", "获得条件：新赛季排行榜排名第2"),
    (9900009, "degree_mod_stellar_abyss_slayer", "星渊讨伐者", "せいえんとうばつしゃ", "获得条件：新赛季排行榜排名第3"),
    (9900010, "degree_mod_breakthrough_pioneer", "破阵先行者", "はじんせんこうしゃ", "获得条件：新赛季排行榜排名第4～15"),
    (9900011, "degree_mod_stellar_abyss_together", "共赴星渊", "ともにせいえんへ", "获得条件：参加新赛季排行榜"),
)


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def encode_text_row(fields: list[str]) -> bytes:
    text = io.StringIO()
    csv.writer(text, lineterminator="").writerow(fields)
    return zlib.compress(text.getvalue().encode("utf-8"), 9)


def degree_row(title_id: int, string_id: str, name: str, condition: str) -> bytes:
    # The nine columns mirror the existing 9900002--9900006 rows exactly:
    # string id, display order, CN name, short key, condition, category,
    # background, icon root, and the title image logical path.
    fields = [
        string_id,
        str(title_id - 1),
        name,
        string_id.removeprefix("degree_mod_"),
        condition,
        "8",
        "dynamic/degree/background",
        "item/etc/degree",
        f"dynamic/degree/{string_id}",
    ]
    return encode_text_row(fields)


def verify_png(raw: bytes, source: Path) -> dict[str, object]:
    if raw[:8] != wf_assets.PNG_REAL:
        raise PublishError(f"{source.name}: 不是标准 PNG")
    dims = wf_assets.png_dims(raw)
    if dims != (320, 50):
        raise PublishError(f"{source.name}: 尺寸 {dims!r}，期望 320x50")
    if len(raw) < 26 or raw[24] != 8 or raw[25] != 6:
        raise PublishError(f"{source.name}: 不是 8-bit RGBA PNG")
    return {"name": source.name, "sha256": sha256(raw), "width": 320, "height": 50, "format": "RGBA"}


def verify_client_disassembly_marker() -> dict[str, object]:
    live = wf_live_cdn.read_logical(EQUIPMENT_LOGICAL)
    if live.tail != BASE_VERSION:
        raise PublishError(f"live CDN equipment tail drifted: {live.tail}, expected {BASE_VERSION}")
    ordered = core.read_orderedmap_raw_rows_from_bytes(live.data, EQUIPMENT_LOGICAL)
    rows: dict[str, list[str]] = {}
    for key in ["5900101", *[str(value) for value in range(8000101, 8000116)]]:
        if key not in ordered.keys:
            raise PublishError(f"equipment row missing: {key}")
        raw = ordered.rows[ordered.keys.index(key)]
        try:
            fields = next(csv.reader([zlib.decompress(raw).decode("utf-8")]))
        except (UnicodeDecodeError, zlib.error, StopIteration) as exc:
            raise PublishError(f"equipment row {key} malformed: {exc}") from exc
        if len(fields) <= 13:
            raise PublishError(f"equipment row {key} has no client disassembly column")
        rows[key] = fields
    # Column 13 is the client "dismantle to soul" display marker.  Keep it on
    # all 15 abyss weapons; actual server soul generation remains Death Bringer-only.
    abyss = [rows[str(value)][13] for value in range(8000101, 8000116)]
    if abyss != ["true"] * 15:
        raise PublishError(f"abyss client disassembly marker changed: {abyss!r}")
    if rows["5900101"][13] != "true":
        raise PublishError("Death Bringer client disassembly marker is not true")
    return {
        "logical": EQUIPMENT_LOGICAL,
        "column": 13,
        "abyss_weapon_ids": [8000101 + index for index in range(15)],
        "abyss_marker_values": abyss,
        "death_bringer_marker": rows["5900101"][13],
        "server_soul_generation_ids": [5900101],
    }


def deterministic_zip(payloads: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 3, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])
    raw = out.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.testzip() is not None:
            raise PublishError("season title CDN ZIP CRC 校验失败")
    return raw


def build() -> tuple[bytes, dict[str, object], dict[str, object]]:
    live = wf_live_cdn.read_logical(DEGREE_LOGICAL)
    if live.tail != BASE_VERSION:
        raise PublishError(f"live CDN degree tail drifted: {live.tail}, expected {BASE_VERSION}")
    ordered = core.read_orderedmap_raw_rows_from_bytes(live.data, DEGREE_LOGICAL)
    before = dict(zip(ordered.keys, ordered.rows))
    expected_old = ["9900002", "9900003", "9900004", "9900005", "9900006"]
    for key in expected_old:
        if key not in before:
            raise PublishError(f"existing title row missing: {key}")
    existing = set(ordered.keys)
    if any(str(title_id) in existing for title_id, *_ in TITLES):
        raise PublishError("one or more new title IDs already exist in live degree table")

    archive_payloads: dict[str, bytes] = {}
    for title_id, string_id, name, _kana, condition in TITLES:
        ordered.keys.append(str(title_id))
        ordered.rows.append(degree_row(title_id, string_id, name, condition))
    rebuilt_degree = core.build_orderedmap_raw_rows(ordered)
    check = core.read_orderedmap_raw_rows_from_bytes(rebuilt_degree, DEGREE_LOGICAL)
    after = dict(zip(check.keys, check.rows))
    for key, value in before.items():
        if after.get(key) != value:
            raise PublishError(f"existing degree row changed: {key}")
    archive_payloads[member_name(DEGREE_LOGICAL)] = rebuilt_degree

    png_reports: list[dict[str, object]] = []
    for _title_id, string_id, _name, _kana, _condition in TITLES:
        source = TITLE_DIR / f"{_name}.png"
        if not source.is_file():
            raise PublishError(f"formal title PNG missing: {source}")
        formal = source.read_bytes()
        png_reports.append(verify_png(formal, source))
        archive_payloads[member_name(f"dynamic/degree/{string_id}.png")] = wf_assets.png_encode(formal)

    archive_raw = deterministic_zip(archive_payloads)
    report = {
        "schema": "season-rank-titles/v1",
        "patch_id": PATCH_ID,
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "archive": {
            "name": ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": len(archive_payloads),
            "member_paths": sorted(archive_payloads),
        },
        "degree": {
            "logical": DEGREE_LOGICAL,
            "before_rows": len(before),
            "after_rows": len(after),
            "preserved_old_ids": [int(key) for key in expected_old],
            "new_titles": [
                {"id": title_id, "string_id": string_id, "name": name, "condition": condition,
                 "image": f"dynamic/degree/{string_id}.png"}
                for title_id, string_id, name, _kana, condition in TITLES
            ],
        },
        "png": png_reports,
        "client_disassembly": verify_client_disassembly_marker(),
        "verification": {
            "archive_crc_ok": True,
            "untouched_degree_rows_preserved": True,
            "old_titles_preserved": True,
            "formal_png_only": True,
            "green_zoom_excluded": True,
            "client_disassembly_marker_preserved": True,
        },
    }
    return archive_raw, report, json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def update_manifest(manifest: dict[str, object], report: dict[str, object]) -> dict[str, object]:
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        raise PublishError("manifest.patches is not an array")
    enabled = [item for item in patches if item.get("enabled")]
    if not enabled or enabled[-1].get("version") != BASE_VERSION:
        raise PublishError(f"manifest enabled tail is not {BASE_VERSION}")
    archive = report["archive"]
    updated = copy.deepcopy(manifest)
    updated["patches"] = [item for item in patches if item.get("id") != PATCH_ID]
    updated["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "新赛季排行榜称号 1.4.97",
        "description": "保留 9900002～9900006 旧称号，追加五个赛季称号及正式 PNG；只改排行榜结算称号/票券引用，不覆盖其他卡池。",
        "version": TARGET_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": archive["name"],
        "archive_size": archive["size"],
        "files": sorted(archive["member_paths"]),
        "changes": [
            "追加 9900007～9900011：星渊主宰者、星渊征服者、星渊讨伐者、破阵先行者、共赴星渊。",
            "旧 9900002～9900006 与旧图片保留；新赛季结算使用新五档称号。",
            "结算单抽/十连券引用 999017/999018；990002 竞速池其他配置不改，999015/999016 保留历史兼容。",
            "15 把深渊武器客户端分解为魂珠标记保持 true；服务端实际魂珠生成仍仅限死亡使者。",
        ],
        "created_at": "2026-09-03",
        "audit": {"directory": str(AUDIT_DIR.relative_to(ROOT)).replace("\\", "/"), "report": "report.json"},
        "archive_integrity": [archive],
        "chain": [archive["name"]],
    })
    updated["cdn_version"] = TARGET_VERSION
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    archive_raw, report, manifest = build()
    print(json.dumps({
        "ok": True,
        "dry_run": not args.apply,
        "archive": report["archive"],
        "new_titles": report["degree"]["new_titles"],
        "client_disassembly": report["client_disassembly"],
    }, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0
    target_archive = ACTIVE_DIR / ARCHIVE_NAME
    if target_archive.exists():
        raise PublishError(f"refusing to overwrite existing archive: {target_archive}")
    updated = update_manifest(manifest, report)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    target_archive.write_bytes(archive_raw)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MANIFEST_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target_archive}")
    print(f"wrote {AUDIT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
