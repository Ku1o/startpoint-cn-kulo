#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fold the five reviewed MOD character balances into the existing 1.4.92 edge.

The first two 1.4.92 members contain the ranking/content tables and the third
contains the abyss reroll.  This publisher appends one terminal overlay member
to the same 1.4.91 -> 1.4.92 patch.  Only reviewed orderedmap rows and seven
skill DSL payloads are taken from the local pending client store.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import wf_mod_tool as core
from wf_gerald_balance import ABILITY_EDITS as GERALD_ABILITY_EDITS
from wf_gerald_balance import SKILL_DSL_LOGICALS as GERALD_SKILL_DSL_LOGICALS
from wf_lion_balance import ABILITY_EDITS as LION_ABILITY_EDITS
from wf_siete_balance import ACTION_SKILL_KEY as SIETE_ACTION_SKILL_KEY
from wf_siete_balance import CHARACTER_ID as SIETE_CHARACTER_ID
from wf_siete_balance import SKILL_DSL_LOGICALS as SIETE_SKILL_DSL_LOGICALS
from wf_simoun_balance import ABILITY_EDITS as SIMOUN_ABILITY_EDITS
from wf_simoun_balance import ACTION_SKILL_KEY as SIMOUN_ACTION_SKILL_KEY
from wf_simoun_balance import CHARACTER_ID as SIMOUN_CHARACTER_ID
from wf_simoun_balance import LEADER_EDITS as SIMOUN_LEADER_EDITS
from wf_simoun_balance import SKILL_DSL_LOGICALS as SIMOUN_SKILL_DSL_LOGICALS
from wf_vaseraga_balance import CHARACTER_ID as VASERAGA_CHARACTER_ID


TOOL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TOOL_ROOT.parents[1]
ACTIVE_DIR = REPO_ROOT / "assets/asset-patch/active"
PENDING_STORE = REPO_ROOT / "assets/asset-patch/production/upload"
MANIFEST_PATH = REPO_ROOT / "assets/asset-patch/manifest.json"
AUDIT_PATH = (
    REPO_ROOT
    / "assets/asset-patch/audit/home-load-rank-p5b-1.4.92/mod-character-balance-fold.json"
)

PATCH_ID = "home-load-rank-p5b-1.4.92"
BASE_ARCHIVE_NAME = "pinball-1.4.91-1.4.92-2-0829-home-load-rank-p5b.zip"
OUTPUT_ARCHIVE_NAME = "pinball-1.4.91-1.4.92-4-0829-mod-balance-fold.zip"

ABILITY_LOGICAL = "master/ability/ability.orderedmap"
LEADER_ABILITY_LOGICAL = "master/ability/leader_ability.orderedmap"
CHARACTER_TEXT_LOGICAL = "master/character/character_text.orderedmap"
ACTION_SKILL_LOGICAL = "master/skill/action_skill.orderedmap"

TABLE_TARGETS = {
    ABILITY_LOGICAL: tuple(sorted(
        set(SIMOUN_ABILITY_EDITS) | set(LION_ABILITY_EDITS) | set(GERALD_ABILITY_EDITS)
    )),
    LEADER_ABILITY_LOGICAL: tuple(sorted(
        set(SIMOUN_LEADER_EDITS) | {VASERAGA_CHARACTER_ID}
    )),
    CHARACTER_TEXT_LOGICAL: (
        SIETE_CHARACTER_ID,
        SIMOUN_CHARACTER_ID,
        VASERAGA_CHARACTER_ID,
    ),
    ACTION_SKILL_LOGICAL: (
        SIETE_ACTION_SKILL_KEY,
        SIMOUN_ACTION_SKILL_KEY,
    ),
}
SKILL_DSL_LOGICALS = tuple(
    list(SIETE_SKILL_DSL_LOGICALS.values())
    + list(SIMOUN_SKILL_DSL_LOGICALS.values())
    + list(GERALD_SKILL_DSL_LOGICALS.values())
)


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    relative = core.table_path(Path("."), logical).as_posix()
    if relative.startswith("./"):
        relative = relative[2:]
    return "production/upload/" + relative


def merge_reviewed_rows(base_raw: bytes, source_raw: bytes, logical: str) -> tuple[bytes, dict]:
    targets = TABLE_TARGETS[logical]
    base = core.read_orderedmap_raw_rows_from_bytes(base_raw, logical)
    source = core.read_orderedmap_raw_rows_from_bytes(source_raw, logical)
    base_rows = dict(zip(base.keys, base.rows))
    source_rows = dict(zip(source.keys, source.rows))
    missing = [key for key in targets if key not in base_rows or key not in source_rows]
    if missing:
        raise PublishError(f"{logical}: reviewed target rows missing: {missing}")

    output_rows = [source_rows[key] if key in targets else row for key, row in zip(base.keys, base.rows)]
    output = core.build_orderedmap_raw_rows(core.OrderedMap(
        logical,
        list(base.keys),
        output_rows,
        Path("<fold-five-mod-balances-into-1.4.92>"),
    ))
    readback = core.read_orderedmap_raw_rows_from_bytes(output, logical)
    if readback.keys != base.keys:
        raise PublishError(f"{logical}: key order changed")
    readback_rows = dict(zip(readback.keys, readback.rows))
    for key in base.keys:
        expected = source_rows[key] if key in targets else base_rows[key]
        if readback_rows[key] != expected:
            raise PublishError(f"{logical}: row verification failed: {key}")
    return output, {
        "logical": logical,
        "target_keys": list(targets),
        "base_sha256": sha256(base_raw),
        "source_sha256": sha256(source_raw),
        "output_sha256": sha256(output),
        "non_target_rows_preserved": len(base.keys) - len(targets),
    }


def deterministic_zip(payloads: dict[str, bytes]) -> bytes:
    from io import BytesIO

    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 8, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])
    return output.getvalue()


def build() -> tuple[bytes, dict]:
    base_path = ACTIVE_DIR / BASE_ARCHIVE_NAME
    if not base_path.is_file():
        raise PublishError(f"missing base archive: {base_path}")
    payloads: dict[str, bytes] = {}
    table_reports: list[dict] = []
    with zipfile.ZipFile(base_path) as base_archive:
        for logical in TABLE_TARGETS:
            member = member_name(logical)
            try:
                base_raw = base_archive.read(member)
            except KeyError as error:
                raise PublishError(f"base archive lacks {logical}") from error
            source_path = core.table_path(PENDING_STORE, logical)
            if not source_path.is_file():
                raise PublishError(f"pending store lacks {logical}: {source_path}")
            merged, report = merge_reviewed_rows(
                base_raw,
                source_path.read_bytes(),
                logical,
            )
            payloads[member] = merged
            table_reports.append(report)

    dsl_reports: list[dict] = []
    for logical in SKILL_DSL_LOGICALS:
        source_path = core.table_path(PENDING_STORE, logical)
        if not source_path.is_file():
            raise PublishError(f"pending store lacks skill DSL: {logical}")
        raw = source_path.read_bytes()
        payloads[member_name(logical)] = raw
        dsl_reports.append({
            "logical": logical,
            "sha256": sha256(raw),
            "size": len(raw),
        })

    archive_raw = deterministic_zip(payloads)
    report = {
        "schema": "wf-mod-character-balance-fold/v1",
        "patch_id": PATCH_ID,
        "base_version": "1.4.91",
        "target_version": "1.4.92",
        "characters": [119996, 149995, 149999, 169996, 169997],
        "archive": {
            "name": OUTPUT_ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": len(payloads),
        },
        "tables": table_reports,
        "skill_dsl": dsl_reports,
    }
    return archive_raw, report


def update_manifest(manifest: dict, report: dict) -> dict:
    patches = manifest.get("patches", [])
    entry = next((item for item in patches if item.get("id") == PATCH_ID), None)
    if entry is None:
        raise PublishError(f"manifest lacks patch {PATCH_ID}")
    expected_prefix = [
        "pinball-1.4.91-1.4.92-1-0829-home-load-rank-p5b.zip",
        BASE_ARCHIVE_NAME,
        "pinball-1.4.91-1.4.92-3-58f49db214d9.zip",
    ]
    chain = [name for name in entry.get("chain", []) if name != OUTPUT_ARCHIVE_NAME]
    if chain != expected_prefix:
        raise PublishError(f"unexpected 1.4.92 chain before MOD fold: {chain}")
    integrity = [
        item for item in entry.get("archive_integrity", [])
        if item.get("name") != OUTPUT_ARCHIVE_NAME
    ]
    if [item.get("name") for item in integrity] != expected_prefix:
        raise PublishError("unexpected 1.4.92 archive integrity order")
    entry["archive_integrity"] = integrity + [report["archive"]]
    entry["chain"] = expected_prefix + [OUTPUT_ARCHIVE_NAME]
    change = (
        "同一1.4.92末端覆盖五名MOD角色终态：希耶提、西蒙、巴萨拉卡、"
        "玛格诺斯、杰拉德；仅移植审核白名单行与7份技能DSL。"
    )
    if change not in entry["changes"]:
        entry["changes"].append(change)
    entry.setdefault("audit", {})["mod_character_balance_fold"] = {
        "report": str(AUDIT_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "characters": report["characters"],
        "table_rows": sum(len(item["target_keys"]) for item in report["tables"]),
        "skill_dsl": len(report["skill_dsl"]),
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write archive, audit and manifest")
    args = parser.parse_args()
    archive_raw, report = build()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.apply:
        print("dry-run complete")
        return 0

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = update_manifest(manifest, report)
    (ACTIVE_DIR / OUTPUT_ARCHIVE_NAME).write_bytes(archive_raw)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_ARCHIVE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
