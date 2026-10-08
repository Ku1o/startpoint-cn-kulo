#!/usr/bin/env python3
"""Re-publish the current ability table on a new asset-version edge.

Some clients already reported an old terminal version before the awakened
ability table was finalized and therefore keep stale ability 4/5/6 rows for
151159 and 261089. This patch does not alter balance data: it re-emits the
current terminal table after the 1.4.134 content chain as 1.4.135.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TOOL_ROOT.parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_mod_tool as core  # noqa: E402


BASE_VERSION = "1.4.134"
TARGET_VERSION = "1.4.135"
PATCH_ID = "dragon-awake-ability-refresh-1.4.135"
ARCHIVE_NAME = "pinball-1.4.134-1.4.135-1-dragon-awake-ability-refresh-20261008.zip"
ACTIVE_DIR = REPO_ROOT / "assets/asset-patch/active"
MANIFEST_PATH = REPO_ROOT / "assets/asset-patch/manifest.json"
AUDIT_DIR = REPO_ROOT / "assets/asset-patch/audit/dragon-awake-ability-refresh-1.4.135"

ABILITY_LOGICAL = "master/ability/ability.orderedmap"
TERMINAL_ARCHIVE = (
    ACTIVE_DIR
    / "pinball-1.4.130-1.4.131-1-liangyue-character-final-merged.zip"
)
AWAKENED_ARCHIVE = (
    ACTIVE_DIR
    / "pinball-1.4.93-1.4.94-1-0830-awakened-balance-migration.zip"
)
EXPECTED_TABLE_SHA256 = (
    "413129be259ad4c3686489649ed6c4bbc143c722f595e126b9cbccec9dcfca74"
)
TARGET_KEYS = tuple(
    f"{character_id}{slot}"
    for character_id in ("151159", "261089")
    for slot in (4, 5, 6)
)


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def read_member(archive_path: Path, member: str) -> bytes:
    if not zipfile.is_zipfile(archive_path):
        raise PublishError(f"invalid source ZIP: {archive_path}")
    with zipfile.ZipFile(archive_path) as archive:
        try:
            return archive.read(member)
        except KeyError as error:
            raise PublishError(f"{archive_path.name} is missing {member}") from error


def validate_target_rows(terminal_raw: bytes, awakened_raw: bytes) -> dict[str, dict]:
    terminal = core.read_orderedmap_file_from_bytes(terminal_raw)
    awakened = core.read_orderedmap_file_from_bytes(awakened_raw)
    rows = {}
    for key in TARGET_KEYS:
        if key not in terminal or key not in awakened:
            raise PublishError(f"missing target ability key: {key}")
        if terminal[key] != awakened[key]:
            raise PublishError(f"terminal target ability drifted from approved 1.4.94: {key}")
        parsed = core.read_csv_lines(terminal[key])
        official = [row for row in parsed if len(row) == 126 and row[3] == "1" and row[4] == "0"]
        replacement = [row for row in parsed if len(row) == 126 and row[3] == "1" and row[4] == "1"]
        if len(official) != 1 or not replacement:
            raise PublishError(
                f"{key} must contain one awake-0 row and at least one awake-1 row"
            )
        rows[key] = {
            "row_count": len(parsed),
            "official_rows": len(official),
            "awakened_rows": len(replacement),
            "row_sha256": sha256(terminal[key].encode("utf-8")),
        }
    return rows


def deterministic_zip(member: str, payload: bytes) -> bytes:
    output = io.BytesIO()
    info = zipfile.ZipInfo(member, date_time=(2026, 10, 8, 12, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(info, payload)
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.testzip() is not None or archive.namelist() != [member]:
            raise PublishError("generated archive readback failed")
        if archive.read(member) != payload:
            raise PublishError("generated ability payload differs after ZIP readback")
    return raw


def build() -> tuple[bytes, dict, dict]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("cdn_version") not in (BASE_VERSION, TARGET_VERSION):
        raise PublishError(
            f"manifest tail must be {BASE_VERSION} or {TARGET_VERSION}, "
            f"got {manifest.get('cdn_version')}"
        )

    member = member_name(ABILITY_LOGICAL)
    terminal_raw = read_member(TERMINAL_ARCHIVE, member)
    if sha256(terminal_raw) != EXPECTED_TABLE_SHA256:
        raise PublishError("registered terminal ability table SHA-256 changed")
    awakened_raw = read_member(AWAKENED_ARCHIVE, member)
    target_rows = validate_target_rows(terminal_raw, awakened_raw)
    archive_raw = deterministic_zip(member, terminal_raw)
    report = {
        "schema": "wf-dragon-awake-ability-refresh/v1",
        "status": "prepared_local_resource_update",
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "patch_id": PATCH_ID,
        "archive": {
            "name": ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": 1,
            "files": [member],
        },
        "resource": {
            "logical": ABILITY_LOGICAL,
            "member": member,
            "payload_sha256": sha256(terminal_raw),
            "payload_bytes": len(terminal_raw),
            "source_archive": str(TERMINAL_ARCHIVE.relative_to(REPO_ROOT)).replace("\\", "/"),
            "approved_awakened_source": str(
                AWAKENED_ARCHIVE.relative_to(REPO_ROOT)
            ).replace("\\", "/"),
        },
        "target_rows": target_rows,
        "verification": {
            "target_rows_equal_approved_1_4_94": True,
            "whole_table_is_current_terminal_bytes": True,
            "balance_values_changed": False,
            "save_or_schema_changed": False,
            "zip_crc_and_readback": True,
        },
        "runtime_deployed": False,
        "device_tested": False,
    }
    entry = {
        "id": PATCH_ID,
        "type": "patch",
        "name": "光暗龙觉醒能力表缓存刷新",
        "description": (
            "在新资源版本中重新下发当前终态 ability.orderedmap，"
            "修复部分客户端仍显示拉夫马诺与阿鲁玛德乌斯旧版觉醒能力4至6。"
        ),
        "version": TARGET_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive_raw),
        "files": [member],
        "chain": [ARCHIVE_NAME],
        "archive_integrity": [report["archive"]],
        "created_at": "2026-10-08",
        "audit": {
            "directory": str(AUDIT_DIR.relative_to(REPO_ROOT)).replace("\\", "/"),
            "report": "report.json",
        },
        "changes": [
            "重发当前终态 ability.orderedmap，不改变任一角色能力数值。",
            "验证151159与261089的能力4、5、6均保留未觉醒行和觉醒1级替换行。",
            "Android与iOS共用common能力表；1.4.134客户端通过新版本边自动重新下载。",
        ],
    }
    return archive_raw, report, entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    archive_raw, report, entry = build()
    print(json.dumps({
        "ok": True,
        "dry_run": not args.apply,
        "archive": report["archive"],
        "resource": report["resource"],
        "target_rows": report["target_rows"],
    }, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["patches"] = [
        item for item in manifest["patches"] if item.get("id") != PATCH_ID
    ]
    manifest["patches"].append(entry)
    manifest["cdn_version"] = TARGET_VERSION
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    (ACTIVE_DIR / ARCHIVE_NAME).write_bytes(archive_raw)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (AUDIT_DIR / "manifest-entry.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
