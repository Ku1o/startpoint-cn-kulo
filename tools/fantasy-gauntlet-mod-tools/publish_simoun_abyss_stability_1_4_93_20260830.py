#!/usr/bin/env python3
"""Publish two independent 1.4.92 -> 1.4.93 stability overlays.

Segment 1 removes the incompatible Simoun flock-reset command, restores the
AddSkillPoint object ID to 20 while keeping its ratio at 15%, and updates the
two display tables. Segment 2 restores native terrains for abyss rounds 3 and
4. The existing 1.4.92 archives are read as an immutable base and never
rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import zipfile
import zlib

import wf_abyss_custom_position_fix as abyss_fix
import wf_mod_tool as core
import wf_quest_lib as quest
import wf_rogue_bundle as rogue_bundle
import wf_simoun_balance as simoun


TOOL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TOOL_ROOT.parents[1]
ACTIVE_DIR = REPO_ROOT / "assets/asset-patch/active"
PENDING_STORE = REPO_ROOT / "assets/asset-patch/production/upload"
MANIFEST_PATH = REPO_ROOT / "assets/asset-patch/manifest.json"
AUDIT_DIR = REPO_ROOT / "assets/asset-patch/audit/simoun-abyss-stability-1.4.93"

BASE_PATCH_ID = "home-load-rank-p5b-1.4.92"
PATCH_ID = "simoun-abyss-stability-1.4.93"
BASE_VERSION = "1.4.92"
TARGET_VERSION = "1.4.93"
SIMOUN_ARCHIVE = "pinball-1.4.92-1.4.93-1-0830-simoun-flock-reset-rollback.zip"
ABYSS_ARCHIVE = "pinball-1.4.92-1.4.93-2-0830-abyss-position-fix.zip"

SIMOUN_TABLE_TARGETS = {
    simoun.CHARACTER_TEXT_LOGICAL: (simoun.CHARACTER_ID,),
    simoun.ACTION_SKILL_LOGICAL: (simoun.ACTION_SKILL_KEY,),
}
SIMOUN_DSL_LOGICALS = tuple(simoun.SKILL_DSL_LOGICALS.values())


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    relative = core.table_path(Path("."), logical).as_posix().removeprefix("./")
    return "production/upload/" + relative


def deterministic_zip(payloads: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])
    return output.getvalue()


def base_entry(manifest: dict) -> dict:
    entries = [item for item in manifest.get("patches", [])
               if item.get("id") == BASE_PATCH_ID]
    if len(entries) != 1:
        raise PublishError(f"manifest 中 {BASE_PATCH_ID} 数量不是1")
    entry = entries[0]
    if entry.get("version") != BASE_VERSION or entry.get("depends_on") != "1.4.91":
        raise PublishError("1.4.92 基线版本关系漂移")
    chain = entry.get("chain")
    if not isinstance(chain, list) or len(chain) != 4:
        raise PublishError("1.4.92 基线归档链不是已验收的四段")
    integrity = entry.get("archive_integrity")
    if [item.get("name") for item in integrity or []] != chain:
        raise PublishError("1.4.92 基线归档完整性顺序漂移")
    for expected in integrity:
        path = ACTIVE_DIR / expected["name"]
        raw = path.read_bytes()
        if len(raw) != expected["size"] or sha256(raw) != expected["sha256"]:
            raise PublishError(f"1.4.92 基线归档被改写: {path.name}")
    return entry


def latest_base_payload(entry: dict, logical: str) -> bytes:
    member = member_name(logical)
    for archive_name in reversed(entry["chain"]):
        with zipfile.ZipFile(ACTIVE_DIR / archive_name) as archive:
            if member in archive.namelist():
                return archive.read(member)
    raise PublishError(f"1.4.92 链中找不到资源: {logical}")


def merge_target_rows(base_raw: bytes, source_raw: bytes, logical: str,
                      targets: tuple[str, ...]) -> tuple[bytes, dict]:
    base = core.read_orderedmap_raw_rows_from_bytes(base_raw, logical)
    source = core.read_orderedmap_raw_rows_from_bytes(source_raw, logical)
    if base.keys != source.keys:
        raise PublishError(f"{logical}: 待发布表与1.4.92键顺序不一致")
    base_rows = dict(zip(base.keys, base.rows))
    source_rows = dict(zip(source.keys, source.rows))
    missing = sorted(set(targets) - set(base_rows))
    if missing:
        raise PublishError(f"{logical}: 缺少目标行 {missing}")
    rows = [source_rows[key] if key in targets else row
            for key, row in zip(base.keys, base.rows)]
    output = core.build_orderedmap_raw_rows(core.OrderedMap(
        logical, list(base.keys), rows, Path("<simoun-1.4.93-row-graft>")
    ))
    readback = core.read_orderedmap_raw_rows_from_bytes(output, logical)
    if readback.keys != base.keys:
        raise PublishError(f"{logical}: 输出键顺序变化")
    for key, before, after in zip(base.keys, base.rows, readback.rows):
        expected = source_rows[key] if key in targets else before
        if after != expected:
            raise PublishError(f"{logical}: 行回读不一致 {key}")
    return output, {
        "logical": logical,
        "target_keys": list(targets),
        "base_sha256": sha256(base_raw),
        "source_sha256": sha256(source_raw),
        "output_sha256": sha256(output),
        "non_target_rows_preserved": len(base.keys) - len(targets),
    }


def build_simoun_segment(entry: dict) -> tuple[bytes, dict]:
    payloads: dict[str, bytes] = {}
    table_reports = []
    for logical, targets in SIMOUN_TABLE_TARGETS.items():
        base_raw = latest_base_payload(entry, logical)
        source_path = core.table_path(PENDING_STORE, logical)
        if not source_path.is_file():
            raise PublishError(f"本地待发布资源缺失: {logical}")
        output, report = merge_target_rows(
            base_raw, source_path.read_bytes(), logical, targets
        )
        payloads[member_name(logical)] = output
        table_reports.append(report)

    dsl_reports = []
    for logical in SIMOUN_DSL_LOGICALS:
        source_path = core.table_path(PENDING_STORE, logical)
        if not source_path.is_file():
            raise PublishError(f"本地待发布西蒙DSL缺失: {logical}")
        raw = source_path.read_bytes()
        tree = simoun._decode_skill(raw, logical)
        facts = simoun._skill_facts(tree, logical)
        if facts["resets"]:
            raise PublishError(f"{logical}: 仍含羊群清零命令")
        gauge = facts["gauge"]
        if gauge[1] != 20:
            raise PublishError(f"{logical}: AddSkillPoint 作用对象ID不是20")
        if simoun._fixed_range(gauge[2], "全队技能槽") != 0.15:
            raise PublishError(f"{logical}: 全队技能槽不是15%")
        payloads[member_name(logical)] = raw
        dsl_reports.append({"logical": logical, "sha256": sha256(raw), "size": len(raw)})

    archive_raw = deterministic_zip(payloads)
    return archive_raw, {
        "schema": "wf-simoun-flock-reset-rollback/v1",
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "character_id": int(simoun.CHARACTER_ID),
        "flock_reset": False,
        "skill_point_target_id": 20,
        "party_skill_gauge_percent": 15,
        "archive": {
            "name": SIMOUN_ARCHIVE,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": len(payloads),
        },
        "tables": table_reports,
        "skill_dsl": dsl_reports,
    }


def _field_mapping(raw: bytes) -> dict[str, str]:
    table = core.read_orderedmap_raw_rows_from_bytes(raw, abyss_fix.FIELD_DATA_LOGICAL)
    mapping = {}
    for key, payload in zip(table.keys, table.rows):
        try:
            mapping[key] = zlib.decompress(payload).decode("utf-8").strip()
        except (zlib.error, UnicodeDecodeError) as exc:
            raise PublishError(f"field_data 行解码失败: {key}") from exc
    return mapping


def audit_fixed_terrains(field_raw: bytes) -> list[dict]:
    field_data = _field_mapping(field_raw)
    zone = quest.load_table("master/battle/zone.orderedmap")
    reports = []
    for field, spec in abyss_fix.FIELD_FIXES.items():
        source = str(spec["source_field"])
        target_caps = rogue_bundle.load_terrain_layer_caps(
            field, field_data, zone, rogue_bundle.load_store_terrain
        )
        source_caps = rogue_bundle.load_terrain_layer_caps(
            source, field_data, zone, rogue_bundle.load_store_terrain
        )
        if len(target_caps) != 1 or len(source_caps) != 1:
            raise PublishError(f"{field}: 修复后不是单层原生地形")
        target_positions = dict(target_caps[0].custom_positions)
        source_positions = dict(source_caps[0].custom_positions)
        if target_positions != source_positions:
            raise PublishError(f"{field}: 修复后坐标与原生来源不一致")
        required = tuple(spec["required_positions"])
        missing = [name for name in required if target_positions.get(name) != 1]
        if missing:
            raise PublishError(f"{field}: 修复后仍缺少坐标 {missing}")
        reports.append({
            "field": field,
            "source_field": source,
            "terrain": list(spec["after"])[1],
            "zone_preserved": list(spec["after"])[2],
            "required_positions": list(required),
            "target_positions": sorted(target_positions.items()),
            "source_positions_equal": True,
        })
    return reports


def build_abyss_segment(entry: dict) -> tuple[bytes, dict]:
    base_raw = latest_base_payload(entry, abyss_fix.FIELD_DATA_LOGICAL)
    output, patch_report = abyss_fix.patch_field_data(base_raw)
    if not patch_report["changed"]:
        raise PublishError("1.4.92 field_data 已意外包含1.4.93修复")
    terrain_report = audit_fixed_terrains(output)
    payloads = {member_name(abyss_fix.FIELD_DATA_LOGICAL): output}
    archive_raw = deterministic_zip(payloads)
    return archive_raw, {
        "schema": "wf-abyss-custom-position-fix/v1",
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "event_id": 700099,
        "rounds_fixed": [3, 4],
        "archive": {
            "name": ABYSS_ARCHIVE,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": 1,
        },
        "table": {
            "logical": abyss_fix.FIELD_DATA_LOGICAL,
            "base_sha256": sha256(base_raw),
            "output_sha256": sha256(output),
            "non_target_rows_preserved": True,
        },
        "fields": terrain_report,
    }


def build() -> tuple[bytes, dict, bytes, dict, dict]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entry = base_entry(manifest)
    simoun_raw, simoun_report = build_simoun_segment(entry)
    abyss_raw, abyss_report = build_abyss_segment(entry)
    return simoun_raw, simoun_report, abyss_raw, abyss_report, manifest


def update_manifest(manifest: dict, simoun_report: dict, abyss_report: dict) -> dict:
    enabled = [item for item in manifest.get("patches", []) if item.get("enabled")]
    if not enabled or enabled[-1].get("id") not in (BASE_PATCH_ID, PATCH_ID):
        raise PublishError("manifest 链尾不是1.4.92基线或本1.4.93补丁")
    manifest["patches"] = [
        item for item in manifest["patches"] if item.get("id") != PATCH_ID
    ]
    archives = [simoun_report["archive"], abyss_report["archive"]]
    members = []
    members.extend(member_name(logical) for logical in SIMOUN_TABLE_TARGETS)
    members.extend(member_name(logical) for logical in SIMOUN_DSL_LOGICALS)
    members.append(member_name(abyss_fix.FIELD_DATA_LOGICAL))
    entry = {
        "id": PATCH_ID,
        "type": "patch",
        "name": "西蒙兼容回退与深渊地形修复",
        "description": (
            "在独立1.4.92至1.4.93版本边中撤销西蒙主动技羊群清零、"
            "恢复技能槽作用对象ID 20，"
            "并将深渊连战第3、4关恢复为对应Boss原生地形。"
        ),
        "version": TARGET_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": SIMOUN_ARCHIVE,
        "archive_size": sum(item["size"] for item in archives),
        "files": sorted(set(members)),
        "changes": [
            "西蒙三档主动技能不再清空羊群；技能槽作用对象ID恢复为20，全队技能槽15%保持不变。",
            "深渊连战第3关恢复树妖原生地形，补齐唯一自定义坐标p0。",
            "深渊连战第4关恢复寄居蟹原生地形，补齐自定义坐标p0、p1、p2。",
            "第3、4关仅替换场景与地形路径，保留mod_rogue_z3/z4及既有Boss、等级、HP和结算配置。",
        ],
        "created_at": "2026-08-30",
        "audit": {
            "directory": str(AUDIT_DIR.relative_to(REPO_ROOT)).replace("\\", "/"),
            "simoun": "simoun-flock-reset-rollback.json",
            "abyss": "abyss-custom-position-fix.json",
        },
        "archive_integrity": archives,
        "chain": [SIMOUN_ARCHIVE, ABYSS_ARCHIVE],
    }
    manifest["patches"].append(entry)
    manifest["cdn_version"] = TARGET_VERSION
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write archives, audits and manifest")
    args = parser.parse_args()
    simoun_raw, simoun_report, abyss_raw, abyss_report, manifest = build()
    combined = {
        "schema": "wf-simoun-abyss-stability-release/v1",
        "patch_id": PATCH_ID,
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "segments": [simoun_report, abyss_report],
    }
    print(json.dumps(combined, ensure_ascii=False, indent=2))
    if not args.apply:
        print("dry-run complete")
        return 0

    manifest = update_manifest(manifest, simoun_report, abyss_report)
    (ACTIVE_DIR / SIMOUN_ARCHIVE).write_bytes(simoun_raw)
    (ACTIVE_DIR / ABYSS_ARCHIVE).write_bytes(abyss_raw)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "simoun-flock-reset-rollback.json").write_text(
        json.dumps(simoun_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (AUDIT_DIR / "abyss-custom-position-fix.json").write_text(
        json.dumps(abyss_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (AUDIT_DIR / "report.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {SIMOUN_ARCHIVE}")
    print(f"wrote {ABYSS_ARCHIVE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
