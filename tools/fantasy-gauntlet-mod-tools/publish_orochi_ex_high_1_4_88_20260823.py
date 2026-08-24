#!/usr/bin/env python3
"""Build the standalone Orochi EX high-difficulty 1.4.87 -> 1.4.88 patch.

The patch adds boss-battle quest 1020004 and clones ``orochi_ex`` into an
independent ``orochi_ex_high`` data set.  Existing Orochi rows are treated as
immutable.  Rewards intentionally reuse the 1020003 groups for this first
gameplay test.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
TOOL_ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE_STORE = (
    TOOL_ROOT / "work/orochi-high-effective-1.4.87-20260823/production/upload"
)
sys.path.insert(0, str(TOOL_ROOT))
import wf_mod_tool as core  # noqa: E402
import wf_quest_lib as questlib  # noqa: E402
import wf_orochi_ex  # noqa: E402


BASE_VERSION = "1.4.87"
PATCH_VERSION = "1.4.88"
PATCH_ID = "orochi-ex-high-1.4.88"
ARCHIVE_NAME = "pinball-1.4.87-1.4.88-1-0823-orochi-ex-high.zip"
QUEST_ID = "1020004"
QUEST_FIELD_ID = "multi_normal_1_20_5"
PARENT_ID = "orochi_ex_high"

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

BASELINE_SHA256 = {
    QUEST_LOGICAL: "95fd2dfd266988b067ee09582b7956f978fad70bbc9248c2d44168d2d999a224",
    FIELD_LOGICAL: "3b5e2d2ec5952285cb5b227d452a42214168a820b77e4740c7cf3362b48b09f5",
    ZONE_LOGICAL: "14821e3a3704e78c3ae51a8f9584be039de50e66d3174a5d53b09f469c7385e5",
    PARENT_LOGICAL: "19754b19346d41965b2bc5996b8b54c031ea1e7f2073b962e83f73caa662e917",
    HEAD_LOGICAL: "dccdd041fd41920bb77da19a4673be4f601bcd9ba1a5ba3c6c02f90b16c6a2f8",
    LEVEL_LOGICAL: "152b172155e9a4907ccc55027b2eb4b05ba6778dd0e610f39aa69562b22158b3",
}

OLD_HEAD_IDS = (
    "orochi_ex_phase1_left",
    "orochi_ex_phase1_center",
    "orochi_ex_phase1_right",
    "orochi_ex_phase3_left",
    "orochi_ex_phase3_center",
    "orochi_ex_phase3_right",
)
NEW_HEAD_IDS = tuple(value.replace("orochi_ex_", "orochi_ex_high_") for value in OLD_HEAD_IDS)
HEAD_ID_MAP = dict(zip(OLD_HEAD_IDS, NEW_HEAD_IDS))

ACTION_ROOT = "battle/action/enemy/action/boss_orochi/"
FUNNEL1 = ACTION_ROOT + "boss_orochi_ex_phase2$funnel1"
FUNNEL2 = ACTION_ROOT + "boss_orochi_ex_phase2$funnel2"
FUNNEL3 = ACTION_ROOT + "boss_orochi_ex_phase2$funnel3"
FINAL_SHOT = ACTION_ROOT + "boss_orochi_ex_phase4$final_shot"


class PublishError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def store_path(store: Path, logical: str) -> Path:
    digest = core.sha1_path(logical)
    return store / digest[:2] / digest[2:]


def csv_row(value: str, *, logical: str, key: str, size: int) -> list[str]:
    rows = core.read_csv_lines(value)
    if len(rows) != 1 or len(rows[0]) != size:
        raise PublishError(
            f"unexpected CSV shape for {logical}/{key}: "
            f"rows={len(rows)} columns={len(rows[0]) if rows else 0}"
        )
    return rows[0]


def csv_text(row: list[str]) -> str:
    return core.write_csv_lines([row])


def read_manifest(*, allow_published: bool = False) -> dict[str, Any]:
    path = SOURCE_ROOT / "assets/asset-patch/manifest.json"
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    ids = [entry.get("id") for entry in value.get("patches", [])]
    if allow_published:
        if value.get("cdn_version") != PATCH_VERSION or ids.count(PATCH_ID) != 1:
            raise PublishError("published 1.4.88 manifest registration is missing")
    elif value.get("cdn_version") != BASE_VERSION or PATCH_ID in ids:
        raise PublishError("source manifest is not the clean 1.4.87 baseline")
    return value


def load_baseline(store: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    output: dict[str, bytes] = {}
    trees: dict[str, Any] = {}
    for logical in LOGICALS:
        path = store_path(store, logical)
        if not path.is_file():
            raise PublishError(f"baseline member is missing: {logical}: {path}")
        raw = path.read_bytes()
        actual = sha256_bytes(raw)
        if actual != BASELINE_SHA256[logical]:
            raise PublishError(
                f"1.4.87 baseline drifted for {logical}: "
                f"expected={BASELINE_SHA256[logical]} actual={actual}"
            )
        output[logical] = raw
        tree = questlib.parse_node(raw)
        if not isinstance(tree, dict):
            raise PublishError(f"top level is not an ordered map: {logical}")
        trees[logical] = tree
    return output, trees


def build_quest(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    levels = output["1"]["20"]
    if list(levels) != ["1", "2", "3"]:
        raise PublishError(f"Orochi quest baseline keys drifted: {list(levels)}")
    row = csv_row(levels["3"], logical=QUEST_LOGICAL, key="1/20/3", size=124)
    expected = {
        0: "1020003", 1: "3", 10: "2", 11: "1020002",
        70: "200071", 106: "80", 107: "4", 108: "1800",
        109: "multi_normal_1_20_4", 111: "144000",
    }
    if any(row[index] != value for index, value in expected.items()):
        raise PublishError("1020003 client quest baseline drifted")
    row[0] = QUEST_ID
    row[1] = "4"
    row[10] = "3"
    row[11] = "1020003"
    row[106] = "90"
    row[107] = "6"       # 超级+
    row[108] = "2200"    # fever threshold; harder to trigger than 1020003
    row[109] = QUEST_FIELD_ID
    row[111] = "165000"  # mechanic-focused test: modestly offsets the HP increase
    levels["4"] = csv_text(row)
    return output


def build_field(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    if QUEST_FIELD_ID in output:
        raise PublishError(f"field already exists: {QUEST_FIELD_ID}")
    row = csv_row(
        output["multi_normal_1_20_4"], logical=FIELD_LOGICAL,
        key="multi_normal_1_20_4", size=3,
    )
    if row[2] != "multi_normal_1_20_4":
        raise PublishError("Orochi field baseline drifted")
    row[2] = QUEST_FIELD_ID
    output[QUEST_FIELD_ID] = csv_text(row)
    return output


def build_zone(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    if QUEST_FIELD_ID in output:
        raise PublishError(f"zone already exists: {QUEST_FIELD_ID}")
    source = output["multi_normal_1_20_4"]
    if list(source) != ["0"]:
        raise PublishError("Orochi zone baseline shape drifted")
    row = csv_row(source["0"], logical=ZONE_LOGICAL, key="multi_normal_1_20_4/0", size=41)
    if (row[23], row[24], row[25], row[26]) != ("4", "orochi_ex", "4", "orochi_ex"):
        raise PublishError("Orochi zone boss binding drifted")
    row[24] = PARENT_ID
    row[26] = PARENT_ID
    output[QUEST_FIELD_ID] = {"0": csv_text(row)}
    return output


def build_parent(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    if PARENT_ID in output:
        raise PublishError(f"parent already exists: {PARENT_ID}")
    source = output["orochi_ex"]
    if list(source) != ["100"]:
        raise PublishError("orochi_ex parent baseline shape drifted")
    row = csv_row(source["100"], logical=PARENT_LOGICAL, key="orochi_ex/100", size=128)
    if row[24:26] != ["75000000", "120000000"]:
        raise PublishError("orochi_ex phase HP baseline drifted")

    # Phase HP and the six independent child IDs.
    row[24] = "105000000"
    row[25] = "168000000"
    row[34:37] = [
        HEAD_ID_MAP["orochi_ex_phase1_left"],
        HEAD_ID_MAP["orochi_ex_phase1_center"],
        HEAD_ID_MAP["orochi_ex_phase1_right"],
    ]
    row[105:108] = [
        HEAD_ID_MAP["orochi_ex_phase3_left"],
        HEAD_ID_MAP["orochi_ex_phase3_center"],
        HEAD_ID_MAP["orochi_ex_phase3_right"],
    ]

    # Faster phase cadence and shorter punish windows after successful trials.
    updates = {
        37: "1440", 39: "150", 40: "960", 41: "960", 42: "1440",
        43: "960", 44: "720", 52: "210", 53: "210", 54: "210",
        57: "135", 58: "200", 61: "135", 62: "200", 65: "135",
        66: "200", 69: "180", 71: "120", 81: "180", 83: "55",
        93: "180", 95: "80", 108: "120", 109: "270", 110: "900",
        111: "900", 112: "900", 113: "900", 114: "900", 115: "900",
        116: "1680", 117: "720", 118: "120",
    }
    for index, value in updates.items():
        row[index] = value

    # Phase 2 fires paired legacy funnels.  Phase 4 recomposes all three funnels
    # with the stock full-field finisher; every path is already client-supported.
    row[60] = ",".join((FUNNEL1, FUNNEL2))
    row[64] = ",".join((FUNNEL2, FUNNEL3))
    row[68] = ",".join((FUNNEL3, FUNNEL1))
    row[127] = ",".join((FUNNEL1, FUNNEL2, FUNNEL3, FINAL_SHOT))
    output[PARENT_ID] = {"100": csv_text(row)}
    return output


def scaled_idle(value: str) -> str:
    current = int(value)
    return str(max(30, int(round(current * 0.82 / 10.0)) * 10))


def build_heads(tree: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    output = copy.deepcopy(tree)
    idle_columns = (41, 51, 70, 80, 99, 109, 128, 138)
    thresholds = {
        "orochi_ex_phase1_center": ("40", "45"),
        "orochi_ex_phase1_left": ("50", "45"),
        "orochi_ex_phase1_right": ("20", "22"),
        "orochi_ex_phase3_center": ("45", "50"),
        "orochi_ex_phase3_left": ("45", "50"),
        "orochi_ex_phase3_right": ("22", "25"),
    }
    report: dict[str, Any] = {}
    for old_id in OLD_HEAD_IDS:
        new_id = HEAD_ID_MAP[old_id]
        if new_id in output:
            raise PublishError(f"head already exists: {new_id}")
        source = output[old_id]
        if list(source) != ["100"]:
            raise PublishError(f"head baseline shape drifted: {old_id}")
        row = csv_row(source["100"], logical=HEAD_LOGICAL, key=f"{old_id}/100", size=179)
        before_idle = {str(index): row[index] for index in idle_columns}
        row[28] = "210"
        row[29] = "210"
        for index in idle_columns:
            row[index] = scaled_idle(row[index])
        row[158], row[169] = thresholds[old_id]

        # Bring selected phase-3 mechanics forward without inventing new DSL:
        # moving center shot, left freeze pattern, and side-head self-heal.
        if old_id == "orochi_ex_phase1_center":
            row[60] = ACTION_ROOT + "boss_orochi_ex_phase3$ShotA1_center"
        elif old_id == "orochi_ex_phase1_left":
            row[40] = ACTION_ROOT + "boss_orochi_ex_phase3$CoopShotA1_left"
            row[118] = ACTION_ROOT + "boss_orochi_ex_phase3$ShotC1_side"
        elif old_id == "orochi_ex_phase1_right":
            row[40] = ACTION_ROOT + "boss_orochi_ex_phase3$CoopShotA1_right"
            row[118] = ACTION_ROOT + "boss_orochi_ex_phase3$ShotC1_side"

        output[new_id] = {"100": csv_text(row)}
        report[new_id] = {
            "trial_thresholds": [int(row[158]), int(row[169])],
            "idle_before": before_idle,
            "idle_after": {str(index): row[index] for index in idle_columns},
        }
    return output, report


def build_levels(tree: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(tree)
    if PARENT_ID in output or any(value in output for value in NEW_HEAD_IDS):
        raise PublishError("high-difficulty boss level rows already exist")
    parent = csv_row(output["orochi_ex"], logical=LEVEL_LOGICAL, key="orochi_ex", size=13)
    if (parent[2], parent[8], parent[12]) != ("250", "60", "120"):
        raise PublishError("orochi_ex boss level baseline drifted")
    parent[2], parent[8], parent[12] = "300", "75", "140"
    output[PARENT_ID] = csv_text(parent)

    hp = {
        "orochi_ex_phase1_center": "480",
        "orochi_ex_phase1_left": "190",
        "orochi_ex_phase1_right": "190",
        "orochi_ex_phase3_center": "900",
        "orochi_ex_phase3_left": "360",
        "orochi_ex_phase3_right": "360",
    }
    for old_id in OLD_HEAD_IDS:
        row = csv_row(output[old_id], logical=LEVEL_LOGICAL, key=old_id, size=13)
        if row[8] != "80":
            raise PublishError(f"head attack baseline drifted: {old_id}")
        row[2] = hp[old_id]
        row[8] = "95"
        row[12] = "80" if "phase1" in old_id else "105"
        output[HEAD_ID_MAP[old_id]] = csv_text(row)
    return output


def build_payloads(store: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    baseline, trees = load_baseline(store)
    built: dict[str, Any] = {}
    built[QUEST_LOGICAL] = build_quest(trees[QUEST_LOGICAL])
    built[FIELD_LOGICAL] = build_field(trees[FIELD_LOGICAL])
    built[ZONE_LOGICAL] = build_zone(trees[ZONE_LOGICAL])
    built[PARENT_LOGICAL] = build_parent(trees[PARENT_LOGICAL])
    built[HEAD_LOGICAL], head_report = build_heads(trees[HEAD_LOGICAL])
    built[LEVEL_LOGICAL] = build_levels(trees[LEVEL_LOGICAL])

    # Cross-check the release against the same dedicated read/replace channel
    # used by the general Boss evaluator.  The encounter builder owns timing,
    # head IDs and actions; this adapter owns the three HP bars.
    scaled_parent, scaled_level, hp_channel_report = wf_orochi_ex.build_scaled_hp_rows(
        trees[PARENT_LOGICAL], trees[LEVEL_LOGICAL], "orochi_ex", PARENT_ID,
        fixed_phase_scale=1.4, middle_scale=1.2,
    )
    expected_parent = csv_row(
        scaled_parent["100"], logical=PARENT_LOGICAL,
        key=f"{PARENT_ID}/100 expected HP", size=128,
    )
    actual_parent = csv_row(
        built[PARENT_LOGICAL][PARENT_ID]["100"], logical=PARENT_LOGICAL,
        key=f"{PARENT_ID}/100", size=128,
    )
    expected_level = csv_row(
        scaled_level, logical=LEVEL_LOGICAL,
        key=f"{PARENT_ID} expected HP", size=13,
    )
    actual_level = csv_row(
        built[LEVEL_LOGICAL][PARENT_ID], logical=LEVEL_LOGICAL,
        key=PARENT_ID, size=13,
    )
    if actual_parent[24:26] != expected_parent[24:26] or actual_level[2] != expected_level[2]:
        raise PublishError("orochi_ex_high does not match the dedicated HP replacement channel")

    payloads: dict[str, bytes] = {}
    for logical in LOGICALS:
        raw = questlib.build_node(built[logical])
        if questlib.parse_node(raw) != built[logical]:
            raise PublishError(f"build/readback mismatch: {logical}")
        if raw == baseline[logical]:
            raise PublishError(f"table unexpectedly produced no change: {logical}")
        payloads[member_name(logical)] = raw
    return payloads, {
        "quest": {
            "id": int(QUEST_ID), "rank": "超级+", "enemy_level": 90,
            "fever_limit": 2200, "time_limit_ms": 165000,
            "reward_group_reused": 200071,
        },
        "parent": {
            "id": PARENT_ID, "phase_hp": [105_000_000, 168_000_000],
            "phase2_trial_thresholds": {"direct": 120, "power_flip": 55, "skill": 80},
            "phase2_success_stun_frames": 210,
            "phase4_actions": [FUNNEL1, FUNNEL2, FUNNEL3, FINAL_SHOT],
            "hp_channel": hp_channel_report,
        },
        "heads": head_report,
    }


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for member in sorted(payloads):
            info = zipfile.ZipInfo(member, (2026, 8, 23, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    return output.getvalue()


def updated_manifest(manifest: dict[str, Any], archive: bytes, payloads: dict[str, bytes]) -> bytes:
    value = copy.deepcopy(manifest)
    files = sorted(payloads)
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "八岐大蛇·超级+独立高难度",
        "description": "新增领主战1020004，使用独立orochi_ex_high父体与六蛇头配置强化四阶段机制；首轮测试沿用1020003奖励组。",
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "files": files,
        "changes": [
            "新增领主战八岐大蛇第4项难度1020004（超级+、敌人等级90），通关1020003后开放。",
            "克隆独立orochi_ex_high父体及六个阶段蛇头，不改动原1020001至1020003战斗数据。",
            "阶段一提前引入冻结、移动弹幕与侧头自愈；六蛇头缩短空档并提高三类试炼要求。",
            "阶段二加快轮转、配对复用三种漏斗弹幕，并将成功破试炼后的输出窗口缩短至210帧。",
            "阶段四同时重组三种既有漏斗弹幕与原八股冲击终结技，不新增客户端动作类型。",
            "掉落、分数奖励组、经验和玛纳暂时完全沿用1020003，留待玩法测试后单独设计。",
        ],
        "created_at": "2026-08-23",
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
    row = (
        "| 2026-08-23 | boss_battle/orochi_ex | 1020004 | "
        "新增八岐大蛇超级+独立四阶段高难：强化试炼、节奏、阶段机制与终局组合技；奖励暂沿用1020003 | "
        f"{PATCH_VERSION} | active独立增量包 |{newline}"
    )
    return text.replace(marker, marker + row, 1).encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".orochi-1.4.88.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def assert_target(path: Path) -> None:
    path.resolve(strict=False).relative_to(SOURCE_ROOT.resolve(strict=True))


def build_targets(
    manifest_raw: bytes, changelog_raw: bytes, archive_raw: bytes,
    payloads: dict[str, bytes],
) -> dict[str, tuple[Path, bytes]]:
    targets: dict[str, tuple[Path, bytes]] = {}

    def add(label: str, path: Path, raw: bytes) -> None:
        assert_target(path)
        if label in targets or path in (item[0] for item in targets.values()):
            raise PublishError(f"duplicate publication target: {path}")
        targets[label] = (path, raw)

    add("active-archive", SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME, archive_raw)
    for member, raw in payloads.items():
        add(f"production-{member}", SOURCE_ROOT / "assets/asset-patch" / member, raw)
    add("changelog", SOURCE_ROOT / "assets/asset-patch/changelog.md", changelog_raw)
    add("manifest", SOURCE_ROOT / "assets/asset-patch/manifest.json", manifest_raw)
    return targets


def apply_targets(targets: dict[str, tuple[Path, bytes]]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TOOL_ROOT / "work" / f"orochi-high-1.4.88-backup-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    existence: dict[str, bool] = {}
    for label, (path, _raw) in targets.items():
        existence[label] = path.is_file()
        if path.is_file():
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
    except Exception:
        for label, (path, _raw) in reversed(list(targets.items())):
            assert_target(path)
            if existence[label]:
                atomic_write((backup / label).read_bytes(), path)
            elif path.exists():
                path.unlink()
        raise
    return backup


def verify_tables(payloads: dict[str, bytes]) -> dict[str, Any]:
    by_logical = {logical: questlib.parse_node(payloads[member_name(logical)]) for logical in LOGICALS}
    quest = csv_row(by_logical[QUEST_LOGICAL]["1"]["20"]["4"], logical=QUEST_LOGICAL, key="1/20/4", size=124)
    if (quest[0], quest[10], quest[11], quest[70], quest[106], quest[107], quest[109]) != (
        QUEST_ID, "3", "1020003", "200071", "90", "6", QUEST_FIELD_ID,
    ):
        raise PublishError("1020004 client quest verification failed")
    field = csv_row(by_logical[FIELD_LOGICAL][QUEST_FIELD_ID], logical=FIELD_LOGICAL, key=QUEST_FIELD_ID, size=3)
    zone = csv_row(by_logical[ZONE_LOGICAL][QUEST_FIELD_ID]["0"], logical=ZONE_LOGICAL, key=f"{QUEST_FIELD_ID}/0", size=41)
    if field[2] != QUEST_FIELD_ID or (zone[24], zone[26]) != (PARENT_ID, PARENT_ID):
        raise PublishError("1020004 field/zone verification failed")
    parent = csv_row(by_logical[PARENT_LOGICAL][PARENT_ID]["100"], logical=PARENT_LOGICAL, key=f"{PARENT_ID}/100", size=128)
    if parent[24:26] != ["105000000", "168000000"] or parent[34:37] != list(NEW_HEAD_IDS[:3]):
        raise PublishError("orochi_ex_high parent verification failed")
    if parent[105:108] != list(NEW_HEAD_IDS[3:]) or len(parent[127].split(",")) != 4:
        raise PublishError("orochi_ex_high phase3/4 verification failed")
    if any(value not in by_logical[HEAD_LOGICAL] for value in NEW_HEAD_IDS):
        raise PublishError("orochi_ex_high head rows are incomplete")
    if any(value not in by_logical[LEVEL_LOGICAL] for value in (PARENT_ID, *NEW_HEAD_IDS)):
        raise PublishError("orochi_ex_high boss-level rows are incomplete")
    fixed_profile = wf_orochi_ex.read_fixed_phase_hp(
        by_logical[PARENT_LOGICAL], PARENT_ID, 90,
    )
    if (fixed_profile.phase1_hp, fixed_profile.phase3_hp) != (105_000_000, 168_000_000):
        raise PublishError("dedicated Orochi EX reader disagrees with the release rows")
    return {
        "quest": int(quest[0]), "rank": int(quest[107]), "enemy_level": int(quest[106]),
        "parent": PARENT_ID, "heads": len(NEW_HEAD_IDS),
        "phase_hp": [int(parent[24]), int(parent[25])],
        "dedicated_hp_reader": fixed_profile.evidence(),
        "phase4_action_count": len(parent[127].split(",")),
    }


def verify_server_row() -> dict[str, Any]:
    rows = json.loads((SOURCE_ROOT / "assets/boss_battle_quest.json").read_text(encoding="utf-8-sig"))
    row = rows.get(QUEST_ID)
    expected = {
        "name": "", "clearRewardId": 1, "sPlusRewardId": 1,
        "scoreRewardGroupId": 200071, "bRankTime": 1860000,
        "aRankTime": 1410000, "sRankTime": 960000, "sPlusRankTime": 600000,
        "rankPointReward": 1013, "characterExpReward": 2435,
        "manaReward": 2490, "poolExpReward": 2435, "element": 4,
    }
    if row != expected:
        raise PublishError("server 1020004 row is missing or does not reuse 1020003 rewards")
    return {"quest": int(QUEST_ID), "reward_policy": "reuses 1020003 unchanged"}


def verify_existing_release() -> dict[str, Any]:
    manifest = read_manifest(allow_published=True)
    entry = next(item for item in manifest["patches"] if item.get("id") == PATCH_ID)
    archive_path = SOURCE_ROOT / "assets/asset-patch/active" / entry["archive"]
    integrity = entry["archive_integrity"][0]
    if not archive_path.is_file() or archive_path.stat().st_size != integrity["size"]:
        raise PublishError("published archive is missing or has the wrong size")
    archive_raw = archive_path.read_bytes()
    if sha256_bytes(archive_raw) != integrity["sha256"]:
        raise PublishError("published archive SHA-256 drifted")
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        if archive.namelist() != entry["files"] or len(entry["files"]) != len(LOGICALS):
            raise PublishError("archive and manifest member lists disagree")
        payloads = {name: archive.read(name) for name in archive.namelist()}
    for member, raw in payloads.items():
        direct = SOURCE_ROOT / "assets/asset-patch" / member
        if not direct.is_file() or direct.read_bytes() != raw:
            raise PublishError(f"direct production member drifted: {member}")
    return {
        "cdn_version": PATCH_VERSION,
        "archive": str(archive_path),
        "archive_sha256": sha256_bytes(archive_raw),
        "members": len(payloads),
        "client": verify_tables(payloads),
        "server": verify_server_row(),
        "runtime_mirror_touched": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-store", type=Path, default=DEFAULT_BASELINE_STORE)
    parser.add_argument("--apply", action="store_true", help="write verified source-repository outputs")
    parser.add_argument("--verify-existing", action="store_true", help="verify the published source outputs")
    args = parser.parse_args()
    if args.verify_existing:
        if args.apply:
            raise PublishError("--verify-existing and --apply are mutually exclusive")
        print(json.dumps(verify_existing_release(), ensure_ascii=False, indent=2))
        return 0

    manifest = read_manifest()
    payloads, design = build_payloads(args.baseline_store.resolve())
    archive_raw = zip_payloads(payloads)
    manifest_raw = updated_manifest(manifest, archive_raw, payloads)
    changelog_raw = updated_changelog((SOURCE_ROOT / "assets/asset-patch/changelog.md").read_bytes())
    report: dict[str, Any] = {
        "apply": args.apply,
        "source_only": True,
        "runtime_mirror_touched": False,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "patch_id": PATCH_ID,
        "archive": str(SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME),
        "archive_size": len(archive_raw),
        "archive_sha256": sha256_bytes(archive_raw),
        "members": len(payloads),
        "design": design,
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    backup = apply_targets(build_targets(manifest_raw, changelog_raw, archive_raw, payloads))
    report["backup"] = str(backup)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
