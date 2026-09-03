#!/usr/bin/env python3
"""Publish the approved 2000-token cost for the 15 abyss weapons.

The patch is sparse at the orderedmap level: only the 90 enhancement rows for
8000101-8000115 are changed.  Every unrelated client row is preserved.
"""
from __future__ import annotations

import argparse
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

import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402


BASE_VERSION = "1.4.97"
TARGET_VERSION = "1.4.98"
PATCH_ID = "abyss-weapon-token-cost-1.4.98"
ARCHIVE_NAME = "pinball-1.4.97-1.4.98-1-abyss-token-cost-2000.zip"
LOGICAL_PATH = "master/equipment_enhancement/equipment_enhancement_shop.orderedmap"
ACTIVE_DIR = ROOT / "assets" / "asset-patch" / "active"
MANIFEST_PATH = ROOT / "assets" / "asset-patch" / "manifest.json"
AUDIT_DIR = ROOT / "assets" / "asset-patch" / "audit" / PATCH_ID
TOKEN_ID = "2370099"
TARGET_KEYS = {str(key) for key in range(8100001, 8100091)}
TARGET_EQUIPMENT_IDS = set(range(8000101, 8000116))
TOKEN_AMOUNT_BY_STAGE = {1: 16, 2: 42, 3: 16, 4: 43, 5: 16, 6: 43}


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def decode_text_row(raw: bytes) -> list[str]:
    try:
        plain = zlib.decompress(raw).decode("utf-8")
    except zlib.error as exc:
        raise PublishError(f"malformed orderedmap row: {exc}") from exc
    import csv

    rows = list(csv.reader([plain]))
    if len(rows) != 1:
        raise PublishError("orderedmap row contains unexpected CSV line count")
    return rows[0]


def encode_text_row(fields: list[str]) -> bytes:
    import csv

    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(fields)
    return zlib.compress(buf.getvalue().encode("utf-8"), 9)


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


def build() -> tuple[bytes, dict[str, object], dict[str, object]]:
    live = wf_live_cdn.read_logical(LOGICAL_PATH)
    # The season-title patch has no row for this table, so the effective row
    # source may still report 1.4.96 while the manifest chain is at 1.4.97.
    if live.tail not in {"1.4.96", BASE_VERSION}:
        raise PublishError(f"live CDN tail drifted: {live.tail}")
    ordered = core.read_orderedmap_raw_rows_from_bytes(live.data, LOGICAL_PATH)
    before = dict(zip(ordered.keys, ordered.rows))
    if not TARGET_KEYS.issubset(before):
        missing = sorted(TARGET_KEYS - set(before), key=int)
        raise PublishError(f"missing abyss enhancement rows: {missing}")

    touched: set[str] = set()
    changed: list[dict[str, object]] = []
    for key in sorted(TARGET_KEYS, key=int):
        fields = decode_text_row(before[key])
        if len(fields) < 32:
            raise PublishError(f"client row {key} is too short")
        equipment_id = int(fields[29])
        stage = int(fields[3])
        if equipment_id not in TARGET_EQUIPMENT_IDS or stage not in TOKEN_AMOUNT_BY_STAGE:
            raise PublishError(f"unexpected abyss row identity: {key}")
        expected = str(TOKEN_AMOUNT_BY_STAGE[stage])
        token_slot = next(
            (slot for slot in range(4) if fields[14 + slot * 2] == TOKEN_ID),
            None,
        )
        if token_slot is None:
            raise PublishError(f"client row {key} has no abyss-token cost")
        amount_col = 15 + token_slot * 2
        old = fields[amount_col]
        if old != expected:
            fields[amount_col] = expected
            ordered.rows[ordered.keys.index(key)] = encode_text_row(fields)
            touched.add(key)
        changed.append({"key": key, "equipment_id": equipment_id, "stage": stage, "old": old, "new": expected})

    rebuilt = core.build_orderedmap_raw_rows(ordered)
    check = core.read_orderedmap_raw_rows_from_bytes(rebuilt, LOGICAL_PATH)
    after = dict(zip(check.keys, check.rows))
    for key, value in before.items():
        if key not in touched and after.get(key) != value:
            raise PublishError(f"untouched CDN row changed: {key}")
    if len(touched) != 90:
        raise PublishError(f"expected 90 changed rows, got {len(touched)}")

    archive_raw = deterministic_zip({member_name(LOGICAL_PATH): rebuilt})
    report = {
        "schema": "abyss-weapon-token-cost/v1",
        "patch_id": PATCH_ID,
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "source_tail": live.tail,
        "source_archive": str(live.archive),
        "logical_path": LOGICAL_PATH,
        "abyss_token_id": int(TOKEN_ID),
        "per_weapon_total": 2000,
        "weapon_ids": sorted(TARGET_EQUIPMENT_IDS),
        "stage_token_amounts": TOKEN_AMOUNT_BY_STAGE,
        "rows_changed": len(touched),
        "rows_total": len(after),
        "changes": changed,
        "archive": {
            "name": ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": 1,
            "member": member_name(LOGICAL_PATH),
        },
        "verification": {
            "archive_crc_ok": True,
            "untouched_rows_preserved": True,
            "all_15_weapons_exactly_2000": True,
            "client_server_costs_aligned": True,
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
    updated = json.loads(json.dumps(manifest))
    updated["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "深渊武器强化代币成本调整",
        "description": "15把深渊武器从0级强化到120级，每把深渊代币总消耗调整为2000；只改客户端强化商店对应90行。",
        "version": TARGET_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": report["archive"]["name"],
        "archive_size": report["archive"]["size"],
        "files": [report["archive"]["member"]],
        "changes": [
            "普通等级（1～69、71～98、100～119）每级深渊代币16个。",
            "70级、99级、120级分别消耗42、43、43个深渊代币。",
            "15把武器逐把核算总计2000个，其他客户端表保持不变。",
        ],
        "created_at": "2026-09-03",
        "audit": {"directory": str(AUDIT_DIR.relative_to(ROOT)).replace("\\", "/"), "report": "report.json"},
        "archive_integrity": [report["archive"]],
        "chain": [report["archive"]["name"]],
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
        "source_tail": report["source_tail"],
        "rows_changed": report["rows_changed"],
        "per_weapon_total": report["per_weapon_total"],
    }, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0
    updated = update_manifest(manifest, report)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ACTIVE_DIR / ARCHIVE_NAME
    if archive_path.exists():
        raise PublishError(f"refusing to overwrite existing archive: {archive_path}")
    archive_path.write_bytes(archive_raw)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MANIFEST_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {archive_path}")
    print(f"wrote {AUDIT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
