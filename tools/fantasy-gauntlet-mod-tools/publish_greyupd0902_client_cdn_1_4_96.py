#!/usr/bin/env python3
"""Publish the greyupd0902 client CDN graft on top of the live 1.4.95 tail.

The author package deliberately ships shared tables as row-level payloads.
This publisher replays the current CDN/active chain, upserts only the selected
rows, and emits one sparse 1.4.95 -> 1.4.96 asset-patch archive.  It also
applies the already-approved server-side weapon/shop choices to the client
rows so client and server do not advertise different costs or soul behaviour.
"""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import io
import json
import shutil
import sys
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_ROOT))

import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402


BASE_VERSION = "1.4.95"
TARGET_VERSION = "1.4.96"
PATCH_ID = "greyupd0902-client-cdn-1.4.96"
ARCHIVE_NAME = "pinball-1.4.95-1.4.96-1-greyupd0902-client-tables.zip"
ACTIVE_DIR = ROOT / "assets" / "asset-patch" / "active"
MANIFEST_PATH = ROOT / "assets" / "asset-patch" / "manifest.json"
AUDIT_DIR = ROOT / "assets" / "asset-patch" / "audit" / PATCH_ID
DEFAULT_PAYLOAD = Path(
    r"F:\codex\tmp\wfshare-inspect-20260902\greyupd0902"
) / "wfshare-1.4.353-to-1.4.354-graft" / "client-tables" / "client_tables_payload.json"

# The author supplied empty awake-status rows even though the package says
# character awakening is not shipped.  Omitting this table is intentional:
# missing awake status keeps the new characters' awakening closed and cannot
# overwrite any existing awakening state.
SKIP_TABLES = {
    "master/character/character_awake_status.orderedmap",
}

# User decisions: keep our title shop, do not add the second weapon exchange,
# and do not expose the Death Bringer acquisition through the closed Five Boss
# mode.  The definitions themselves remain in the client tables as backup.
SKIP_KEYS = {
    "master/shop/event_item_shop.orderedmap": {
        "9700118",                 # existing title shop
        "59001010",                # Five Boss weapon acquisition (closed)
        *(f"97002{i:02d}" for i in range(1, 16)),  # second weapon exchange
    },
}

PURPLE_BY_EQUIPMENT = {
    **{str(i): "10000114" for i in (8000101, 8000102)},
    **{str(i): "10000117" for i in (8000103, 8000104)},
    **{str(i): "10000120" for i in (8000105, 8000106)},
    **{str(i): "10000123" for i in (8000107, 8000108)},
    **{str(i): "10000126" for i in (8000109, 8000110)},
    **{str(i): "10000129" for i in (8000111, 8000112)},
    **{str(i): "10000093" for i in (8000113, 8000114, 8000115)},
}


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


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
            raise PublishError("client CDN patch ZIP CRC 校验失败")
    return raw


def decode_text_row(raw: bytes) -> list[str]:
    try:
        plain = zlib.decompress(raw).decode("utf-8")
    except zlib.error as exc:
        raise PublishError(f"expected compressed text row, got malformed data: {exc}") from exc
    rows = list(csv.reader([plain]))
    if len(rows) != 1:
        raise PublishError("orderedmap row contains unexpected CSV line count")
    return rows[0]


def encode_text_row(fields: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="")
    writer.writerow(fields)
    return zlib.compress(buf.getvalue().encode("utf-8"), 9)


def apply_equipment_shop_choice(key: str, raw: bytes, server_shop: dict[str, object]) -> bytes:
    """Make the client enhancement rows match assets/equipment_enhancement_shop.json."""
    config = server_shop.get(key)
    if not isinstance(config, dict):
        raise PublishError(f"missing server enhancement-shop row {key}")
    fields = decode_text_row(raw)
    if len(fields) < 32:
        raise PublishError(f"equipment enhancement row {key} is too short")
    costs = config.get("costs", [])
    if not isinstance(costs, list) or len(costs) > 4:
        raise PublishError(f"invalid cost list for enhancement row {key}")
    # Client schema stores four id/amount pairs at columns 14..21.
    for slot in range(4):
        id_col, amount_col = 14 + slot * 2, 15 + slot * 2
        if slot < len(costs) and isinstance(costs[slot], dict):
            item_id = costs[slot].get("id")
            amount = costs[slot].get("amount")
            if item_id is None or amount is None:
                raise PublishError(f"invalid cost in enhancement row {key}")
            fields[id_col] = str(item_id)
            fields[amount_col] = str(amount)
        else:
            fields[id_col] = "(None)"
            fields[amount_col] = ""
    return encode_text_row(fields)


def transform_row(logical: str, key: str, raw: bytes, server_shop: dict[str, object]) -> bytes:
    if logical == "master/equipment_enhancement/equipment_enhancement_shop.orderedmap":
        return apply_equipment_shop_choice(key, raw, server_shop)

    if logical == "master/item/item.orderedmap" and key == "2370099":
        fields = decode_text_row(raw)
        if len(fields) <= 20:
            raise PublishError("Abyss token item row is too short")
        fields[19] = "2000-01-01 00:00:00"
        fields[20] = "2099-12-31 23:59:59"
        return encode_text_row(fields)

    if logical == "master/shop/event_item_shop.orderedmap" and key in {
        f"97001{i:02d}" for i in range(1, 16)
    }:
        fields = decode_text_row(raw)
        if len(fields) <= 30:
            raise PublishError(f"Abyss weapon exchange row {key} is too short")
        # 15-token, stock-1, long-term exchange.  Keep the author's client
        # disassembly/soul marker; actual soul generation remains server-side
        # restricted to Death Bringer.
        fields[18] = "2370099"
        fields[19] = "15"
        fields[26] = "2000-01-01 00:00:00"
        fields[27] = "2099-12-31 23:59:59"
        fields[29] = fields[30] = "1"
        return encode_text_row(fields)

    return raw


def build(payload_path: Path) -> tuple[bytes, dict[str, object], dict[str, object]]:
    if not payload_path.is_file():
        raise PublishError(f"client table payload not found: {payload_path}")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublishError("client table payload must be an object")
    server_shop = json.loads(
        (ROOT / "assets" / "equipment_enhancement_shop.json").read_text(encoding="utf-8")
    )
    archive_payloads: dict[str, bytes] = {}
    table_reports: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for logical, incoming_rows in payload.items():
        if logical in SKIP_TABLES:
            skipped.append({"table": logical, "keys": len(incoming_rows), "reason": "character awakening is closed"})
            continue
        if not isinstance(incoming_rows, dict):
            raise PublishError(f"payload rows for {logical} must be an object")
        live = wf_live_cdn.read_logical(logical)
        if live.tail != BASE_VERSION:
            raise PublishError(f"live CDN tail drifted: {live.tail}, expected {BASE_VERSION}")
        ordered = core.read_orderedmap_raw_rows_from_bytes(live.data, logical)
        before = dict(zip(ordered.keys, ordered.rows))
        index = {key: i for i, key in enumerate(ordered.keys)}
        up = add = 0
        skipped_keys: list[str] = []
        touched: set[str] = set()
        for key, value in incoming_rows.items():
            key = str(key)
            if key in SKIP_KEYS.get(logical, set()):
                skipped_keys.append(key)
                continue
            incoming = base64.b64decode(value)
            patched = transform_row(logical, key, incoming, server_shop)
            if key in index:
                if ordered.rows[index[key]] != patched:
                    ordered.rows[index[key]] = patched
                    up += 1
                    touched.add(key)
            else:
                ordered.keys.append(key)
                ordered.rows.append(patched)
                index[key] = len(ordered.keys) - 1
                add += 1
                touched.add(key)
        if skipped_keys:
            skipped.append({"table": logical, "keys": skipped_keys, "reason": "user selection"})
        if not (up or add):
            table_reports.append({"table": logical, "upsert": 0, "added": 0, "skipped": skipped_keys})
            continue
        rebuilt = core.build_orderedmap_raw_rows(ordered)
        check = core.read_orderedmap_raw_rows_from_bytes(rebuilt, logical)
        after = dict(zip(check.keys, check.rows))
        for key, value in before.items():
            if key not in touched and after.get(key) != value:
                raise PublishError(f"untouched CDN row changed in {logical}/{key}")
        archive_payloads[member_name(logical)] = rebuilt
        table_reports.append({
            "table": logical,
            "upsert": up,
            "added": add,
            "source_rows": len(before),
            "result_rows": len(after),
            "skipped": skipped_keys,
            "sha256": sha256(rebuilt),
        })

    archive_raw = deterministic_zip(archive_payloads)
    report = {
        "schema": "greyupd0902-client-cdn/v1",
        "patch_id": PATCH_ID,
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "source_payload": str(payload_path),
        "source_payload_sha256": sha256(payload_path.read_bytes()),
        "archive": {
            "name": ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": len(archive_payloads),
        },
        "tables": table_reports,
        "skipped": skipped,
        "verification": {
            "archive_crc_ok": True,
            "untouched_rows_preserved": True,
            "character_awake_status_skipped": True,
            "client_disassembly_marker_preserved": True,
            "weapon_exchange_second_batch_skipped": True,
            "title_shop_preserved": True,
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
        "name": "greyupd0902 客户端 CDN 选择性嫁接",
        "description": "接入作者新角色、深渊武器/卡池与必要客户端表；保留原玩法，关闭角色觉醒、第二批兑换、称号商店覆盖及五重决战入口。",
        "version": TARGET_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": archive["name"],
        "archive_size": archive["size"],
        "files": [item["member"] for item in []],
        "changes": [
            "40 个本地缺少角色及魔王、白虎、歼灭者、深渊之兽、风属性荒龙按作者表接入。",
            "新增角色玛纳板及角色依赖表；character_awake_status 整表不下发，角色觉醒保持关闭。",
            "15 把深渊武器、能力魂珠、觉醒商店按服务端已确认成本同步；保留客户端分解为魂珠标记，实际魂珠生成仍仅限死亡使者。",
            "死亡使者定义保留；五重决战定义保留为备用，但不添加入口。",
            "竞速池 990002 绑定 999017/999018；标题商店和第二批兑换不覆盖。",
        ],
        "created_at": "2026-09-03",
        "audit": {"directory": str(AUDIT_DIR.relative_to(ROOT)).replace("\\", "/"), "report": "report.json"},
        "archive_integrity": [archive],
        "chain": [archive["name"]],
    })
    # Fill the logical hashed members from the generated report.
    members: list[str] = []
    for table in report["tables"]:
        if table.get("upsert") or table.get("added"):
            members.append(member_name(str(table["table"])))
    updated["patches"][-1]["files"] = sorted(set(members))
    updated["cdn_version"] = TARGET_VERSION
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, default=DEFAULT_PAYLOAD)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    archive_raw, report, manifest = build(args.payload)
    print(json.dumps({
        "ok": True,
        "dry_run": not args.apply,
        "archive": report["archive"],
        "members": [x["table"] for x in report["tables"] if x.get("upsert") or x.get("added")],
        "skipped": report["skipped"],
    }, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0
    updated = update_manifest(manifest, report)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    (ACTIVE_DIR / ARCHIVE_NAME).write_bytes(archive_raw)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MANIFEST_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {ACTIVE_DIR / ARCHIVE_NAME}")
    print(f"wrote {AUDIT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
