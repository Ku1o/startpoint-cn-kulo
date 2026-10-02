#!/usr/bin/env python3
"""Build the first resource-only Orochi native-mitigation test copy.

The builder reads the client-visible 1.4.119 terminal through ``wf_live_cdn``
and writes a single 1.4.119 -> 1.4.120 active patch.  It deliberately keeps
the existing Orochi EX rows immutable and clones the already-capacity-safe
``mod_rogue_orochi_ex24`` family into a new boss identity.

The test copy uses only client-native values:

* four BossBattleQuest initial damage resistances (ability/direct/PF/skill),
  each at 80%, plus native debuff immunity;
* the cloned Orochi EX phase-2 element resistances and native trial removal;
* existing six-head, phase, action and weak-point data.

No independent HP ledger, new ActionScript event, or new network field is
introduced by this first pass.  ``--apply`` changes only the source checkout;
runtime-mirror synchronization is intentionally a separate operation.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[2]
BASE_VERSION = "1.4.119"
PATCH_VERSION = "1.4.120"
PATCH_ID = "orochi-native-trial-1.4.120"
ARCHIVE_NAME = "pinball-1.4.119-1.4.120-1-orochi-native-trial.zip"
QUEST_ID = "1020004"
FIELD_ID = "multi_normal_1_20_5"
PARENT_ID = "mod_rogue_orochi_ex_native_v1"
HEAD_IDS = tuple(f"{PARENT_ID}_head{i}" for i in range(1, 7))
SOURCE_PARENT_ID = "mod_rogue_orochi_ex24"
SOURCE_HEAD_IDS = tuple(f"{SOURCE_PARENT_ID}_head{i}" for i in range(1, 7))

QUEST_LOGICAL = "master/quest/boss_battle_quest.orderedmap"
FIELD_LOGICAL = "master/battle/field_data.orderedmap"
ZONE_LOGICAL = "master/battle/zone.orderedmap"
PARENT_LOGICAL = "master/battle/boss/orochi_ex.orderedmap"
HEAD_LOGICAL = "master/battle/boss/orochi_ex_head.orderedmap"
LEVEL_LOGICAL = "master/battle/boss/boss_level.orderedmap"
LOGICALS = (
    QUEST_LOGICAL,
    FIELD_LOGICAL,
    ZONE_LOGICAL,
    PARENT_LOGICAL,
    HEAD_LOGICAL,
    LEVEL_LOGICAL,
)


class BuildError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha1_member(logical: str) -> str:
    import wf_mod_tool as core

    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def csv_row(value: str, *, logical: str, key: str, size: int) -> list[str]:
    rows = list(csv.reader([value]))
    if len(rows) != 1 or len(rows[0]) != size:
        raise BuildError(
            f"unexpected CSV shape for {logical}/{key}: "
            f"rows={len(rows)} columns={len(rows[0]) if rows else 0}"
        )
    return rows[0]


def csv_text(row: list[str]) -> str:
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\r\n").writerow(row)
    return output.getvalue()


def load_current() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    # The canonical .cdn lives in the runtime mirror, but the active overlay
    # must come from the Git source checkout.  This prevents a stale or local
    # runtime-only ZIP from becoming the input to a new source patch.
    os.environ["WF_SERVER_DIR"] = str(SOURCE_ROOT)
    sys.path.insert(0, str(SOURCE_ROOT / "tools/fantasy-gauntlet-mod-tools"))
    import wf_live_cdn
    import wf_quest_lib

    wf_live_cdn.clear_cache()
    provenance: dict[str, dict[str, Any]] = {}
    trees: dict[str, Any] = {}
    for logical in LOGICALS:
        result = wf_live_cdn.read_logical(logical)
        trees[logical] = wf_quest_lib.parse_node(result.data)
        provenance[logical] = {
            "sha256": sha256(result.data),
            "size": len(result.data),
            "tail": result.tail,
            "root": result.root,
            "archive": str(result.archive),
            "member": result.member,
        }
    meta = {
        "tail": wf_live_cdn.describe()["tail"],
        "source_active_dir": str(SOURCE_ROOT / "assets/asset-patch/active"),
        "cdn_root": wf_live_cdn.describe()["cdn_root"],
    }
    return meta, {"trees": trees, "provenance": provenance}


def build_quest(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    levels = output["1"]["20"]
    if list(levels) != ["1", "2", "3"]:
        raise BuildError(f"boss battle quest keys drifted: {list(levels)}")
    row = csv_row(levels["3"], logical=QUEST_LOGICAL, key="1/20/3", size=124)
    expected = {0: "1020003", 10: "2", 109: "multi_normal_1_20_4"}
    if any(row[index] != value for index, value in expected.items()):
        raise BuildError("1020003 client quest baseline drifted")

    row[0] = QUEST_ID
    row[1] = "4"
    row[10] = "3"
    row[11] = "1020003"
    row[106] = "90"
    row[107] = "6"
    row[108] = "2200"
    row[109] = FIELD_ID
    row[111] = "165000"

    # BossBattleQuestValues parses these five slots into native initial enemy
    # conditions.  The first four are 80% resistance for the ordinary damage
    # classes; the fifth is native debuff immunity and has no strength cell.
    row[74], row[75] = "0", "0.8"  # ability
    row[76], row[77] = "1", "0.8"  # direct attack
    row[78], row[79] = "2", "0.8"  # power flip
    row[80], row[81] = "3", "0.8"  # skill / unison skill
    row[82] = "4"                   # debuff resistance
    row[83] = ""
    levels["4"] = csv_text(row)
    return output


def build_field(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    if FIELD_ID in output:
        raise BuildError(f"field already exists: {FIELD_ID}")
    row = csv_row(output["multi_normal_1_20_4"], logical=FIELD_LOGICAL,
                  key="multi_normal_1_20_4", size=3)
    if row[2] != "multi_normal_1_20_4":
        raise BuildError("Orochi field baseline drifted")
    row[2] = FIELD_ID
    output[FIELD_ID] = csv_text(row)
    return output


def build_zone(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    if FIELD_ID in output:
        raise BuildError(f"zone already exists: {FIELD_ID}")
    source = output["multi_normal_1_20_4"]
    if list(source) != ["0"]:
        raise BuildError("Orochi zone baseline shape drifted")
    row = csv_row(source["0"], logical=ZONE_LOGICAL,
                  key="multi_normal_1_20_4/0", size=41)
    if (row[23], row[24], row[25], row[26]) != ("4", "orochi_ex", "4", "orochi_ex"):
        raise BuildError("Orochi zone boss binding drifted")
    row[24] = PARENT_ID
    row[26] = PARENT_ID
    output[FIELD_ID] = {"0": csv_text(row)}
    return output


def build_parent(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    if PARENT_ID in output:
        raise BuildError(f"parent already exists: {PARENT_ID}")
    source = output.get(SOURCE_PARENT_ID)
    if not isinstance(source, dict) or list(source) != ["100"]:
        raise BuildError(f"capacity-safe source parent missing: {SOURCE_PARENT_ID}")
    row = csv_row(source["100"], logical=PARENT_LOGICAL,
                  key=f"{SOURCE_PARENT_ID}/100", size=128)
    # Keep the existing int32-safe P1/P3 values, tested six-head mapping and
    # native P2 resistance/trial values.  Only the six IDs change.
    row[34:37] = list(HEAD_IDS[:3])
    row[105:108] = list(HEAD_IDS[3:])
    output[PARENT_ID] = {"100": csv_text(row)}
    return output


def build_heads(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    for source_id, target_id in zip(SOURCE_HEAD_IDS, HEAD_IDS):
        if target_id in output:
            raise BuildError(f"head already exists: {target_id}")
        source = output.get(source_id)
        if not isinstance(source, dict) or list(source) != ["100"]:
            raise BuildError(f"capacity-safe source head missing: {source_id}")
        output[target_id] = copy.deepcopy(source)
    return output


def build_levels(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    for source_id, target_id in zip((SOURCE_PARENT_ID, *SOURCE_HEAD_IDS),
                                    (PARENT_ID, *HEAD_IDS)):
        if target_id in output:
            raise BuildError(f"boss level row already exists: {target_id}")
        row = output.get(source_id)
        if not isinstance(row, str):
            raise BuildError(f"source boss level row missing: {source_id}")
        parsed = csv_row(row, logical=LEVEL_LOGICAL, key=source_id, size=13)
        output[target_id] = csv_text(parsed)
    return output


def phase2_hp_evidence(boss_level: dict[str, Any], quest: list[str]) -> dict[str, Any]:
    """Read the central parent P2 HP through the current native Hit formula.

    The fixed P1/P3 bars are stored on ``orochi_ex`` itself.  P2 remains the
    parent ``boss_level`` Hit row, so a reusable builder must expose the curve,
    event-level K and quest boss correction instead of presenting c2 as HP.
    """
    import wf_rogue_build

    raw = boss_level.get(PARENT_ID)
    if not isinstance(raw, str):
        raise BuildError(f"boss level parent row missing: {PARENT_ID}")
    row = csv_row(raw, logical=LEVEL_LOGICAL, key=PARENT_ID, size=13)
    if row[0] != "0":
        raise BuildError(f"boss level parent is not a Hit row: {PARENT_ID}")
    try:
        c2 = float(row[2])
        c3 = float(row[3])
        enemy_level = int(quest[106])
        boss_correction = float(quest[99])
    except (TypeError, ValueError) as exc:
        raise BuildError("native P2 HP formula contains a non-numeric field") from exc
    curve_name = row[4]
    curve_value = wf_rogue_build.curve_value("hp", curve_name, enemy_level)
    level_scale = wf_rogue_build.GENERAL_HP_LEVEL_SCALE.get(enemy_level)
    if curve_value is None or level_scale is None:
        raise BuildError(
            f"native P2 HP curve is not proven at enemy level {enemy_level}: "
            f"{curve_name}"
        )
    estimated = c2 * c3 * float(curve_value) * float(level_scale) * boss_correction
    if estimated <= 0:
        raise BuildError("native P2 HP estimate is not positive")
    return {
        "formula": "boss_level.c2 * c3 * hp_curve(level) * general_hp_level_scale(level) * quest.boss_hp_correction",
        "boss_level_c2": c2,
        "boss_level_c3": c3,
        "hp_curve": curve_name,
        "hp_curve_value": float(curve_value),
        "enemy_level": enemy_level,
        "general_hp_level_scale": float(level_scale),
        "quest_boss_hp_correction": boss_correction,
        "estimated_middle_hp": round(estimated, 6),
        "static_verified": True,
        "runtime_simulated": False,
    }


def build_payloads() -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    import wf_quest_lib

    meta, loaded = load_current()
    trees = loaded["trees"]
    built = {
        QUEST_LOGICAL: build_quest(trees[QUEST_LOGICAL]),
        FIELD_LOGICAL: build_field(trees[FIELD_LOGICAL]),
        ZONE_LOGICAL: build_zone(trees[ZONE_LOGICAL]),
        PARENT_LOGICAL: build_parent(trees[PARENT_LOGICAL]),
        HEAD_LOGICAL: build_heads(trees[HEAD_LOGICAL]),
        LEVEL_LOGICAL: build_levels(trees[LEVEL_LOGICAL]),
    }
    payloads: dict[str, bytes] = {}
    for logical in LOGICALS:
        raw = wf_quest_lib.build_node(built[logical])
        if wf_quest_lib.parse_node(raw) != built[logical]:
            raise BuildError(f"build/readback mismatch: {logical}")
        payloads[sha1_member(logical)] = raw
    parent = csv_row(built[PARENT_LOGICAL][PARENT_ID]["100"],
                     logical=PARENT_LOGICAL, key=f"{PARENT_ID}/100", size=128)
    quest = csv_row(built[QUEST_LOGICAL]["1"]["20"]["4"],
                    logical=QUEST_LOGICAL, key="1/20/4", size=124)
    phase2 = phase2_hp_evidence(built[LEVEL_LOGICAL], quest)
    phase1_hp = int(parent[24])
    phase3_hp = int(parent[25])
    design = {
        "base": meta,
        "source_provenance": loaded["provenance"],
        "quest": {
            "id": int(QUEST_ID), "rank": int(quest[107]),
            "enemy_level": int(quest[106]), "field": FIELD_ID,
            "time_limit_frames": int(quest[111]),
            "reward_group_reused": 200071,
        },
        "native_initial_conditions": {
            "ability_resistance": 0.8,
            "direct_attack_resistance": 0.8,
            "power_flip_resistance": 0.8,
            "skill_resistance": 0.8,
            "debuff_immunity": True,
            "formula_source": "BossBattleQuestValues + NormalAttackCalculator",
        },
        "orochi_native_phase2": {
            "parent": PARENT_ID,
            "heads": list(HEAD_IDS),
            "phase1_hp": phase1_hp,
            "phase3_hp": phase3_hp,
            "phase2_hp": phase2,
            "central_parent_total_static_estimate": round(
                phase1_hp + phase2["estimated_middle_hp"] + phase3_hp, 6
            ),
            "element_resistances": [float(value) for value in parent[45:49]],
            "trial_kinds": [parent[70], parent[82], parent[94]],
            "trial_targets": [int(parent[71]), int(parent[83]), int(parent[95])],
            "independent_hp_ledger": False,
        },
        "members": sorted(payloads),
    }
    return payloads, design, meta


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for member in sorted(payloads):
            info = zipfile.ZipInfo(member, (2026, 9, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    return output.getvalue()


def read_manifest() -> dict[str, Any]:
    value = json.loads((SOURCE_ROOT / "assets/asset-patch/manifest.json")
                       .read_text(encoding="utf-8-sig"))
    if value.get("cdn_version") != BASE_VERSION:
        raise BuildError(f"source manifest tail is not {BASE_VERSION}: {value.get('cdn_version')}")
    if any(item.get("id") == PATCH_ID for item in value.get("patches", [])):
        raise BuildError(f"patch is already registered: {PATCH_ID}")
    return value


def updated_manifest(manifest: dict[str, Any], archive: bytes,
                     payloads: dict[str, bytes]) -> bytes:
    value = copy.deepcopy(manifest)
    files = sorted(payloads)
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "八岐大蛇·原生减伤试炼首版",
        "description": (
            "新增独立领主战1020004，克隆已验证六蛇头容量并使用游戏原生伤害类型减免、"
            "减益免疫及八岐P2属性耐性/试炼破防；不改变原八岐和深渊Boss。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "files": files,
        "changes": [
            "新增领主战1020004（敌人等级90、超级+），奖励组首版沿用1020003。",
            "新增独立mod_rogue_orochi_ex_native_v1父体及六个蛇头，不改原1020001至1020003。",
            "全阶段使用BossBattleQuest原生能力/直击/PF/技能80%减免及减益免疫。",
            "保留八岐P2原生属性耐性与三类试炼，试炼成功按原生逻辑逐层撤除耐性。",
            "首版不新增独立HP账本、网络字段或ActionScript机制。",
        ],
        "created_at": str(date(2026, 9, 25)),
        "archive_integrity": [{
            "name": ARCHIVE_NAME,
            "size": len(archive),
            "sha256": sha256(archive),
            "members": len(payloads),
        }],
    })
    value["cdn_version"] = PATCH_VERSION
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def server_row() -> dict[str, Any]:
    rows = json.loads((SOURCE_ROOT / "assets/boss_battle_quest.json")
                      .read_text(encoding="utf-8-sig"))
    if QUEST_ID in rows:
        raise BuildError(f"server quest already exists: {QUEST_ID}")
    rows[QUEST_ID] = copy.deepcopy(rows["1020003"])
    return rows


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".orochi-native.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def prepare_output(output_dir: Path, payloads: dict[str, bytes],
                   design: dict[str, Any], archive: bytes,
                   manifest_raw: bytes, server_raw: bytes) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / ARCHIVE_NAME
    archive_path.write_bytes(archive)
    (output_dir / "manifest-1.4.120.json").write_bytes(manifest_raw)
    (output_dir / "boss_battle_quest-1.4.120.json").write_bytes(server_raw)
    (output_dir / "design.json").write_text(
        json.dumps(design, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "payload-sha256.json").write_text(
        json.dumps({member: sha256(raw) for member, raw in sorted(payloads.items())},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"output_dir": str(output_dir), "archive": str(archive_path),
            "archive_sha256": sha256(archive)}


def apply_source(payloads: dict[str, bytes], manifest_raw: bytes,
                 server_raw: bytes, output_dir: Path) -> dict[str, Any]:
    targets: list[tuple[str, Path, bytes]] = [
        ("manifest", SOURCE_ROOT / "assets/asset-patch/manifest.json", manifest_raw),
        ("server-boss-quest", SOURCE_ROOT / "assets/boss_battle_quest.json", server_raw),
        ("archive", SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME,
         zip_payloads(payloads)),
    ]
    for member, raw in payloads.items():
        targets.append((f"production/{member}", SOURCE_ROOT / "assets/asset-patch" / member, raw))
    backup = output_dir / "source-backup"
    backup.mkdir(parents=True, exist_ok=True)
    for label, path, _raw in targets:
        if path.is_file():
            safe = label.replace("/", "__")
            shutil.copy2(path, backup / safe)
    for _label, path, raw in targets:
        atomic_write(path, raw)
    for label, path, expected in targets:
        if not path.is_file() or path.read_bytes() != expected:
            raise BuildError(f"source readback failed: {label}")
    return {"source_applied": True, "backup": str(backup),
            "targets": [label for label, _path, _raw in targets]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(r"F:\codex\outputs\orochi-native-trial-1.4.120-20260925"))
    parser.add_argument("--apply", action="store_true",
                        help="write the verified patch, manifest and server row into the source checkout")
    args = parser.parse_args()

    payloads, design, meta = build_payloads()
    archive = zip_payloads(payloads)
    manifest_raw = updated_manifest(read_manifest(), archive, payloads)
    server = server_row()
    server_raw = (json.dumps(server, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output = prepare_output(args.output_dir, payloads, design, archive,
                            manifest_raw, server_raw)
    report: dict[str, Any] = {
        "apply": args.apply,
        "source_only_before_apply": True,
        "runtime_mirror_touched": False,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "patch_id": PATCH_ID,
        "archive": output["archive"],
        "archive_sha256": output["archive_sha256"],
        "members": len(payloads),
        "design": design,
        "output": output,
        "server_quest": {"id": int(QUEST_ID), "reward_policy": "clone 1020003"},
    }
    if args.apply:
        report.update(apply_source(payloads, manifest_raw, server_raw, args.output_dir))
    (args.output_dir / "build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
