#!/usr/bin/env python3
"""Publish the approved Siete active-skill balance and UI restoration.

The source repository's 1.4.97 recovery edge accidentally wins over the
previous Siete balance and UI resources.  This publisher creates a sparse
1.4.98 -> 1.4.99 edge containing only Siete's two active-skill DSLs and the
two affected orderedmap rows.  The visual archive is produced separately from
the audited 1.4.90 UI archive and is chained in the same version edge.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
from pathlib import Path
import zipfile
import zlib

import wf_mod_tool as core
import wf_siete_balance as balance
import wf_store_materialize as materialize


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_DIR = ROOT / "assets" / "asset-patch" / "active"
MANIFEST_PATH = ROOT / "assets" / "asset-patch" / "manifest.json"
AUDIT_DIR = ROOT / "assets" / "asset-patch" / "audit" / "siete-active-balance-1.4.99"
# The source repository's .cdn is a junction; the actual archive roots live
# below its ``cn`` child.  Resolve the junction before any read and never
# write through this path.
CDN_ROOT = (ROOT / ".cdn" / "cn").resolve()

BASE_VERSION = "1.4.98"
TARGET_VERSION = "1.4.99"
PATCH_ID = "siete-balance-visual-restore-1.4.99"
BALANCE_ARCHIVE_NAME = "pinball-1.4.98-1.4.99-2-siete-active-balance.zip"
UI_ARCHIVE_NAME = "pinball-1.4.98-1.4.99-1-siete-ui-restore.zip"
UI_AUDIT = "assets/asset-patch/audit/siete-ui-restore-1.4.99/report.json"

TABLE_LOGICALS = (
    balance.ACTION_SKILL_LOGICAL,
    balance.CHARACTER_TEXT_LOGICAL,
)
DSL_LOGICALS = tuple(balance.SKILL_DSL_LOGICALS.values())


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def read_plan_member(plan: materialize.MaterializePlan, logical: str) -> bytes:
    digest = core.sha1_path(logical)
    relative = f"{digest[:2]}/{digest[2:]}"
    key = ("common", relative)
    try:
        entry = plan.entries[key]
    except KeyError as error:
        raise PublishError(f"source plan lacks common member: {logical}") from error
    try:
        with zipfile.ZipFile(entry.zip_path) as archive:
            raw = archive.read(entry.name)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise PublishError(f"cannot read source member {logical}: {error}") from error
    if len(raw) != entry.size or (zlib.crc32(raw) & 0xFFFFFFFF) != entry.crc:
        raise PublishError(f"source member changed after planning: {logical}")
    return raw


def decode_csv_row(raw: bytes) -> list[str]:
    try:
        return core.read_csv_lines(zlib.decompress(raw).decode("utf-8"))[0]
    except (ValueError, zlib.error, UnicodeDecodeError, IndexError) as error:
        raise PublishError(f"malformed character_text row: {error}") from error


def deterministic_zip(payloads: dict[str, bytes]) -> bytes:
    out = BytesIO()
    with zipfile.ZipFile(
        out,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 4, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])
    raw = out.getvalue()
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        if archive.testzip() is not None:
            raise PublishError("Siete balance archive CRC 校验失败")
        if len(archive.infolist()) != len(payloads):
            raise PublishError("Siete balance archive member count mismatch")
        if len({info.filename for info in archive.infolist()}) != len(payloads):
            raise PublishError("Siete balance archive contains duplicate members")
    return raw


def verify_action_skill_scope(before: bytes, after: bytes) -> dict[str, object]:
    base = core.read_orderedmap_raw_rows_from_bytes(before, balance.ACTION_SKILL_LOGICAL)
    patched = core.read_orderedmap_raw_rows_from_bytes(after, balance.ACTION_SKILL_LOGICAL)
    if patched.keys != base.keys:
        raise PublishError("action_skill outer key order changed")
    before_rows = dict(zip(base.keys, base.rows))
    after_rows = dict(zip(patched.keys, patched.rows))
    for key in base.keys:
        if key != balance.ACTION_SKILL_KEY and after_rows[key] != before_rows[key]:
            raise PublishError(f"non-target action_skill row changed: {key}")
    before_entries = core.decode_action_skill_row(before_rows[balance.ACTION_SKILL_KEY])
    after_entries = core.decode_action_skill_row(after_rows[balance.ACTION_SKILL_KEY])
    if [key for key, _row in after_entries] != ["1", "2"]:
        raise PublishError("Siete action_skill levels drifted")
    for (before_level, before_row), (after_level, after_row) in zip(before_entries, after_entries):
        if before_level != after_level or len(before_row) != len(after_row):
            raise PublishError(f"Siete action_skill row shape changed: {after_level}")
        for index, (old, new) in enumerate(zip(before_row, after_row)):
            if index != core.ACTION_SKILL_COLUMNS["description"] and old != new:
                raise PublishError(f"Siete action_skill c{index} changed outside description")
    expected = [balance.SKILL_DESCRIPTION_BY_LEVEL[1], balance.SKILL_DESCRIPTION_BY_LEVEL[2]]
    descriptions = [row[core.ACTION_SKILL_COLUMNS["description"]] for _level, row in after_entries]
    if descriptions != expected:
        raise PublishError("Siete action_skill descriptions do not match the two forms")
    return {
        "logical": balance.ACTION_SKILL_LOGICAL,
        "target_key": balance.ACTION_SKILL_KEY,
        "changed_fields": ["description"],
        "before_sha256": sha256(before),
        "after_sha256": sha256(after),
    }


def verify_character_text_scope(before: bytes, after: bytes) -> dict[str, object]:
    base = core.read_orderedmap_raw_rows_from_bytes(before, balance.CHARACTER_TEXT_LOGICAL)
    patched = core.read_orderedmap_raw_rows_from_bytes(after, balance.CHARACTER_TEXT_LOGICAL)
    if patched.keys != base.keys:
        raise PublishError("character_text outer key order changed")
    before_rows = dict(zip(base.keys, base.rows))
    after_rows = dict(zip(patched.keys, patched.rows))
    for key in base.keys:
        if key != balance.CHARACTER_ID and after_rows[key] != before_rows[key]:
            raise PublishError(f"non-target character_text row changed: {key}")
    old_fields = decode_csv_row(before_rows[balance.CHARACTER_ID])
    new_fields = decode_csv_row(after_rows[balance.CHARACTER_ID])
    if len(old_fields) != 12 or len(new_fields) != 12:
        raise PublishError("Siete character_text row shape drifted")
    for index, (old, new) in enumerate(zip(old_fields, new_fields)):
        if index not in (5, 7, 9) and old != new:
            raise PublishError(f"Siete character_text c{index} changed outside skill descriptions")
    if [new_fields[index] for index in (5, 7, 9)] != [balance.SKILL_DESCRIPTION] * 3:
        raise PublishError("Siete character_text description readback mismatch")
    return {
        "logical": balance.CHARACTER_TEXT_LOGICAL,
        "target_key": balance.CHARACTER_ID,
        "changed_fields": ["skill_desc", "skill_plus_desc", "skill_plusplus_desc"],
        "before_sha256": sha256(before),
        "after_sha256": sha256(after),
    }


def build() -> tuple[bytes, dict[str, object]]:
    if not CDN_ROOT.is_dir():
        raise PublishError(f"pristine CDN root is unavailable: {CDN_ROOT}")
    plan = materialize.build_read_only_plan(CDN_ROOT, ROOT, BASE_VERSION, False)
    if plan.tail != BASE_VERSION:
        raise PublishError(f"source plan tail drifted: {plan.tail} != {BASE_VERSION}")

    source = {logical: read_plan_member(plan, logical) for logical in (*TABLE_LOGICALS, *DSL_LOGICALS)}
    patched_dsls, dsl_report = balance.patch_skill_dsls(
        {logical: source[logical] for logical in DSL_LOGICALS}
    )
    patched_action_skill, action_report = balance.patch_action_skill_table(
        source[balance.ACTION_SKILL_LOGICAL]
    )
    patched_character_text, text_report = balance.patch_character_text_table(
        source[balance.CHARACTER_TEXT_LOGICAL]
    )

    table_reports = [
        verify_action_skill_scope(source[balance.ACTION_SKILL_LOGICAL], patched_action_skill),
        verify_character_text_scope(source[balance.CHARACTER_TEXT_LOGICAL], patched_character_text),
    ]
    payloads = {
        member_name(balance.ACTION_SKILL_LOGICAL): patched_action_skill,
        member_name(balance.CHARACTER_TEXT_LOGICAL): patched_character_text,
    }
    for logical, raw in patched_dsls.items():
        payloads[member_name(logical)] = raw

    dsl_reports = []
    for logical in DSL_LOGICALS:
        dsl_reports.append({
            "logical": logical,
            "before_sha256": sha256(source[logical]),
            "after_sha256": sha256(patched_dsls[logical]),
            "before_size": len(source[logical]),
            "after_size": len(patched_dsls[logical]),
            "report": dsl_report["skill_lv1" if logical.endswith("seofon_wind_1.action.dsl.amf3.deflate") else "skill_lv2"],
        })

    archive_raw = deterministic_zip(payloads)
    report = {
        "schema": "siete-balance-visual-restore/v1",
        "patch_id": PATCH_ID,
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "source_tail": plan.tail,
        "archive": {
            "name": BALANCE_ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": len(payloads),
            "files": sorted(payloads),
        },
        "tables": table_reports,
        "skill_dsl": dsl_reports,
        "description_reports": {
            "action_skill": action_report,
            "character_text": text_report,
        },
        "verification": {
            "only_siete_targets_changed": True,
            "hit_topology_preserved": True,
            "active_skill_form1_tiers": [25, 30, 40, 50, 70],
            "active_skill_form2_tiers": [30, 35, 45, 55, 80],
            "ios_visual_pairing": "in separate audited UI archive",
        },
    }
    return archive_raw, report


def update_manifest(manifest: dict[str, object], report: dict[str, object]) -> dict[str, object]:
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        raise PublishError("manifest.patches is not an array")
    if any(item.get("id") == PATCH_ID for item in patches):
        raise PublishError(f"manifest already contains {PATCH_ID}")
    enabled = [item for item in patches if item.get("enabled")]
    if not enabled or enabled[-1].get("version") != BASE_VERSION:
        raise PublishError(f"manifest enabled tail is not {BASE_VERSION}")
    ui_path = ACTIVE_DIR / UI_ARCHIVE_NAME
    if not ui_path.is_file():
        raise PublishError(f"missing audited UI archive: {ui_path}")
    ui_raw = ui_path.read_bytes()
    with zipfile.ZipFile(BytesIO(ui_raw)) as archive:
        if archive.testzip() is not None or len(archive.infolist()) != 29:
            raise PublishError("audited Siete UI archive failed readback")
        ui_files = sorted(info.filename for info in archive.infolist())
    updated = json.loads(json.dumps(manifest))
    updated["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "希耶提主动技能平衡与视觉资源恢复",
        "description": "恢复此前确认的希耶提两形态主动技能平衡，并把被1.4.97 recovery覆盖的29个视觉/切入资源恢复到1.4.90修正版；不修改白虎或希耶提队长技。",
        "version": TARGET_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": report["archive"]["name"],
        "archive_size": report["archive"]["size"],
        "files": sorted(set(report["archive"]["files"]) | set(ui_files)),
        "changes": [
            "进化前剑神层数1～2/3～5/6～8/9～11/12的每段倍率为25/30/40/50/70倍。",
            "进化后同区间每段倍率为30/35/45/55/80倍；两形态均保持N+1段命中拓扑。",
            "同步 action_skill 与 character_text 的技能说明，避免显示值与执行 DSL 分离。",
            "同一1.4.99边串接1.4.90审计的希耶提25张PNG与2组Android/iOS技能切入纹理。",
            "白虎灰更与希耶提149995队长技触发枚举不在本补丁范围内。",
        ],
        "created_at": "2026-09-04",
        "audit": {
            "directory": str(AUDIT_DIR.relative_to(ROOT)).replace("\\", "/"),
            "report": "report.json",
            "ui_restore": UI_AUDIT,
        },
        "archive_integrity": [
            {
                "name": UI_ARCHIVE_NAME,
                "size": len(ui_raw),
                "sha256": sha256(ui_raw),
                "members": 29,
            },
            report["archive"],
        ],
        "chain": [UI_ARCHIVE_NAME, report["archive"]["name"]],
    })
    updated["cdn_version"] = TARGET_VERSION
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    archive_raw, report = build()
    print(json.dumps({
        "ok": True,
        "dry_run": not args.apply,
        "archive": report["archive"],
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "tiers": report["verification"],
    }, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0

    archive_path = ACTIVE_DIR / BALANCE_ARCHIVE_NAME
    if archive_path.exists():
        raise PublishError(f"refusing to overwrite existing archive: {archive_path}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    updated = update_manifest(manifest, report)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive_raw)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    MANIFEST_PATH.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {archive_path}")
    print(f"wrote {AUDIT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
