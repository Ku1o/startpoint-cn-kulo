#!/usr/bin/env python3
"""Publish the ability-5/6 mana-node awakening lookup fix as 1.4.95.

The official client table only defines awakening material rows for ability
slots 1-3 and action-skill slot 4.  StarPoint CN also awakens ability slots
4-6 on the extension board, so a fully awakened board can make the client
look up missing keys 5 and 6 and terminate with C8601.  This sparse patch
adds only those two keys while preserving every existing row byte.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import zipfile


TOOL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TOOL_ROOT.parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_store_materialize as materialize  # noqa: E402


BASE_VERSION = "1.4.94"
TARGET_VERSION = "1.4.95"
PATCH_ID = "mana-node-awake-board2-1.4.95"
ARCHIVE_NAME = "pinball-1.4.94-1.4.95-1-0831-mana-node-awake-board2.zip"
LOGICAL_PATH = "master/mana_board/mana_node_awake.orderedmap"
ACTIVE_DIR = REPO_ROOT / "assets/asset-patch/active"
MANIFEST_PATH = REPO_ROOT / "assets/asset-patch/manifest.json"
SERVER_JSON_PATH = REPO_ROOT / "assets/mana_node_awake.json"
AUDIT_DIR = REPO_ROOT / "assets/asset-patch/audit/mana-node-awake-board2-1.4.95"


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def read_plan_logical(plan: object, logical: str) -> bytes:
    digest = core.sha1_path(logical)
    entry = plan.entries.get(("common", f"{digest[:2]}/{digest[2:]}"))
    if entry is None:
        raise PublishError(f"{logical} 不存在于 {plan.tail}")
    with zipfile.ZipFile(entry.zip_path) as archive:
        return archive.read(entry.name)


def deterministic_zip(payloads: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,
    ) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 8, 31, 13, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])
    raw = output.getvalue()
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        if archive.testzip() is not None:
            raise PublishError("增量 ZIP CRC 校验失败")
    return raw


def decode_table(raw: bytes) -> dict[str, dict[str, dict[str, list[list[str]]]]]:
    result: dict[str, dict[str, dict[str, list[list[str]]]]] = {}
    outer = core.read_orderedmap_raw_rows_from_bytes(raw, LOGICAL_PATH)
    for rarity, slot_map_raw in zip(outer.keys, outer.rows):
        slots = core.read_orderedmap_raw_rows_from_bytes(
            slot_map_raw, f"{LOGICAL_PATH}#{rarity}",
        )
        rarity_rows: dict[str, dict[str, list[list[str]]]] = {}
        for slot, pedestal_map_raw in zip(slots.keys, slots.rows):
            pedestal_map = core.read_orderedmap_file_from_bytes(pedestal_map_raw)
            rarity_rows[slot] = {
                pedestal: core.read_csv_lines(text)
                for pedestal, text in pedestal_map.items()
            }
        result[rarity] = rarity_rows
    return result


def add_board2_slots(source_raw: bytes) -> tuple[bytes, dict[str, object]]:
    outer = core.read_orderedmap_raw_rows_from_bytes(source_raw, LOGICAL_PATH)
    if outer.keys != ["1", "2", "3", "4", "5"]:
        raise PublishError(f"mana_node_awake稀有度键漂移: {outer.keys}")

    source_outer_rows = dict(zip(outer.keys, outer.rows))
    mapping: dict[str, dict[str, str]] = {}
    rebuilt_outer_rows: list[bytes] = []
    for rarity, slot_map_raw in zip(outer.keys, outer.rows):
        slots = core.read_orderedmap_raw_rows_from_bytes(
            slot_map_raw, f"{LOGICAL_PATH}#{rarity}",
        )
        source_slots = dict(zip(slots.keys, slots.rows))
        if "5" in source_slots or "6" in source_slots:
            raise PublishError(f"稀有度{rarity}已存在能力5/6键，拒绝重复发布")
        if "2" not in source_slots:
            raise PublishError(f"稀有度{rarity}缺少能力2模板")

        slot6_source = "3" if "3" in source_slots else "2"
        slots.keys.extend(["5", "6"])
        slots.rows.extend([source_slots["2"], source_slots[slot6_source]])
        rebuilt = core.build_orderedmap_raw_rows(slots)
        rebuilt_outer_rows.append(rebuilt)
        mapping[rarity] = {"5": "2", "6": slot6_source}

        verified = core.read_orderedmap_raw_rows_from_bytes(
            rebuilt, f"{LOGICAL_PATH}#{rarity}:rebuilt",
        )
        verified_rows = dict(zip(verified.keys, verified.rows))
        if verified.keys != slots.keys:
            raise PublishError(f"稀有度{rarity}槽位键回读不一致")
        for slot, original_row in source_slots.items():
            if verified_rows.get(slot) != original_row:
                raise PublishError(f"稀有度{rarity}既有槽位{slot}字节发生变化")
        if verified_rows["5"] != source_slots["2"]:
            raise PublishError(f"稀有度{rarity}能力5模板回读不一致")
        if verified_rows["6"] != source_slots[slot6_source]:
            raise PublishError(f"稀有度{rarity}能力6模板回读不一致")

    patched_outer = copy.copy(outer)
    patched_outer.rows = rebuilt_outer_rows
    patched_raw = core.build_orderedmap_raw_rows(patched_outer)
    decoded = decode_table(patched_raw)
    source_decoded = decode_table(source_raw)
    for rarity in outer.keys:
        for slot, value in source_decoded[rarity].items():
            if decoded[rarity].get(slot) != value:
                raise PublishError(f"稀有度{rarity}既有槽位{slot}语义发生变化")
        if decoded[rarity]["5"] != source_decoded[rarity]["2"]:
            raise PublishError(f"稀有度{rarity}能力5素材语义不一致")
        slot6_source = mapping[rarity]["6"]
        if decoded[rarity]["6"] != source_decoded[rarity][slot6_source]:
            raise PublishError(f"稀有度{rarity}能力6素材语义不一致")

    # Reconfirm that every untouched outer row was the exact source supplied to
    # its inner rebuild. This makes the sparse-edit boundary explicit in audit.
    if set(source_outer_rows) != set(decoded):
        raise PublishError("稀有度外层键集合发生变化")
    return patched_raw, {
        "rarity_keys": outer.keys,
        "slot_template_mapping": mapping,
        "existing_slots_preserved": True,
        "added_slots": [5, 6],
    }


def source_plan() -> object:
    cdn_root, _runtime_root = wf_live_cdn._resolve_locations()
    plan = materialize.build_read_only_plan(
        cdn_root, REPO_ROOT, BASE_VERSION, False,
    )
    if plan.tail != BASE_VERSION:
        raise PublishError(f"资源链尾不符: {plan.tail}")
    return plan


def build() -> tuple[bytes, dict[str, object], dict[str, object], dict[str, object]]:
    plan = source_plan()
    source_raw = read_plan_logical(plan, LOGICAL_PATH)
    patched_raw, table_report = add_board2_slots(source_raw)
    member = member_name(LOGICAL_PATH)
    archive_raw = deterministic_zip({member: patched_raw})
    with zipfile.ZipFile(BytesIO(archive_raw)) as archive:
        info = archive.getinfo(member)
        if archive.read(info) != patched_raw:
            raise PublishError("增量 ZIP 内容回读不一致")

    decoded = decode_table(patched_raw)
    report = {
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "logical_path": LOGICAL_PATH,
        "member": member,
        "source": {
            "tail": plan.tail,
            "size": len(source_raw),
            "sha256": sha256(source_raw),
        },
        "patched": {
            "size": len(patched_raw),
            "sha256": sha256(patched_raw),
        },
        "table": table_report,
        "archive": {
            "name": ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": 1,
        },
        "verification": {
            "archive_crc_ok": True,
            "archive_readback_equal": True,
            "all_rarities_have_slot_5_and_6": all(
                "5" in slots and "6" in slots for slots in decoded.values()
            ),
            "existing_slot_semantics_preserved": True,
        },
    }
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return archive_raw, report, decoded, manifest


def update_manifest(manifest: dict[str, object], report: dict[str, object]) -> dict[str, object]:
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        raise PublishError("manifest.patches不是数组")
    enabled = [item for item in patches if item.get("enabled")]
    if not enabled:
        raise PublishError("manifest没有启用补丁")
    valid_tail_ids = {"awakened-balance-migration-1.4.94", PATCH_ID}
    if enabled[-1].get("id") not in valid_tail_ids:
        raise PublishError(f"manifest链尾不是已知1.4.94/1.4.95: {enabled[-1].get('id')}")

    updated = copy.deepcopy(manifest)
    updated["patches"] = [item for item in patches if item.get("id") != PATCH_ID]
    archive = report["archive"]
    updated["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "玛纳板2能力5/6觉醒查询修复",
        "description": (
            "为能力4至6随角色觉醒的扩展玛纳板补齐客户端能力5、6素材查询键，"
            "修复整板觉醒后进入玛纳板时因Key=5/6缺失触发的C8601。"
        ),
        "version": TARGET_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": archive["size"],
        "files": [report["member"]],
        "changes": [
            "mana_node_awake仅新增能力槽5、6；稀有度1至5的既有槽1至4行保持不变。",
            "能力5沿用能力2的素材档；能力6沿用能力3的素材档，稀有度1、2因无能力3而沿用能力2。",
            "该表仅补齐客户端觉醒态展示所需查询，不改角色星级、能力数值、玛纳板节点或既有存档。",
        ],
        "created_at": "2026-08-31",
        "audit": {
            "directory": str(AUDIT_DIR.relative_to(REPO_ROOT)).replace("\\", "/"),
            "report": "report.json",
        },
        "archive_integrity": [archive],
        "chain": [ARCHIVE_NAME],
    })
    updated["cdn_version"] = TARGET_VERSION
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    archive_raw, report, server_json, manifest = build()
    print(json.dumps({
        "ok": True,
        "dry_run": not args.apply,
        "patch_id": PATCH_ID,
        "archive": report["archive"],
        "table": report["table"],
        "verification": report["verification"],
    }, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0

    updated_manifest = update_manifest(manifest, report)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    (ACTIVE_DIR / ARCHIVE_NAME).write_bytes(archive_raw)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    SERVER_JSON_PATH.write_text(
        json.dumps(server_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    MANIFEST_PATH.write_text(
        json.dumps(updated_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"wrote {ACTIVE_DIR / ARCHIVE_NAME}")
    print(f"wrote {AUDIT_DIR / 'report.json'}")
    print(f"wrote {SERVER_JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
