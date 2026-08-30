#!/usr/bin/env python3
"""Publish the nine-character balance-to-awakening migration as 1.4.94.

The official 1.4.54 terminal supplies unawakened rows.  The repository's
1.4.93 terminal supplies the already reviewed balance designs.  Dark dragon
rarity and character-status rows deliberately remain at their current 5-star
state; this patch never writes either table.
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
import zlib


TOOL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TOOL_ROOT.parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_describe  # noqa: E402
import wf_dsl  # noqa: E402
import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_store_materialize as materialize  # noqa: E402


BASE_VERSION = "1.4.93"
TARGET_VERSION = "1.4.94"
OFFICIAL_VERSION = "1.4.54"
PATCH_ID = "awakened-balance-migration-1.4.94"
ARCHIVE_NAME = "pinball-1.4.93-1.4.94-1-0830-awakened-balance-migration.zip"
ACTIVE_DIR = REPO_ROOT / "assets/asset-patch/active"
MANIFEST_PATH = REPO_ROOT / "assets/asset-patch/manifest.json"
AUDIT_DIR = REPO_ROOT / "assets/asset-patch/audit/awakened-balance-migration-1.4.94"
EXTENSION_PATH = REPO_ROOT / "assets/character_awake_extension.json"
MISSION_EXTENSION_PATH = REPO_ROOT / "assets/mission_char_awake_cnmod.json"
REWARD_EXTENSION_PATH = REPO_ROOT / "assets/mission_char_awake_reward_cnmod.json"

AWAKE_WINDOW_START = "2020-01-01 00:00:00"
AWAKE_WINDOW_END = "2099-04-13 11:59:59"
TEMPLATE_CHARACTER_ID = "341005"
TEMPLATE_CHARACTER_CODE = "cat_fighter"
TEMPLATE_CHARACTER_NAME = "缪"

CHARACTERS = {
    "151045": {"name": "莉莉丝", "label": "夏日莉莉丝"},
    "151027": {"name": "艾莉亚", "label": "艾莉亚"},
    "151021": {"name": "菲莉亚", "label": "菲莉亚"},
    "151015": {"name": "星川莉莉", "label": "星川莉莉"},
    "251017": {"name": "莉莉丝", "label": "灯火莉莉丝"},
    "251053": {"name": "萨莉哈", "label": "萨莉哈"},
    "151159": {"name": "拉夫马诺", "label": "拉夫马诺"},
    "261089": {"name": "阿鲁玛德乌斯", "label": "阿鲁玛德乌斯"},
    "131020": {"name": "雷吉斯", "label": "雷吉斯（白花机人）"},
}

EXPECTED_CHANGED_ABILITY_SLOTS = {
    "151045": (2, 3, 6),
    "151027": (3, 5),
    "151021": (2, 3, 4, 5),
    "151015": (1, 3),
    "251017": (2, 3, 6),
    "251053": (2, 3, 4, 6),
    "151159": (1, 2, 3, 4, 5, 6),
    "261089": (1, 2, 3, 4, 5, 6),
    "131020": (1, 2, 3),
}
EXPECTED_CHANGED_LEADERS = ("131020", "151045", "151159", "261089")
EXPECTED_BOARD2_LINKS = {
    "151045": (6,),
    "151027": (5,),
    "151021": (4, 5),
    "251017": (6,),
    "251053": (4, 6),
    "151159": (4, 5, 6),
    "261089": (4, 5, 6),
}

ABILITY_LOGICAL = "master/ability/ability.orderedmap"
LEADER_LOGICAL = "master/ability/leader_ability.orderedmap"
ACTION_LOGICAL = "master/skill/action_skill.orderedmap"
CHARACTER_LOGICAL = "master/character/character.orderedmap"
STATUS_LOGICAL = "master/character/character_status.orderedmap"
TEXT_LOGICAL = "master/character/character_text.orderedmap"
AWAKE_EVENT_LOGICAL = "master/mission/character_awake_event.orderedmap"
AWAKE_STATUS_LOGICAL = "master/character/character_awake_status.orderedmap"
AWAKE_MISSION_LOGICAL = "master/mission/character_awake_mission.orderedmap"
AWAKE_REWARD_LOGICAL = "master/mission/character_awake_mission_reward.orderedmap"

TABLE_LOGICALS = (
    ABILITY_LOGICAL,
    LEADER_LOGICAL,
    ACTION_LOGICAL,
    CHARACTER_LOGICAL,
    STATUS_LOGICAL,
    TEXT_LOGICAL,
    AWAKE_EVENT_LOGICAL,
    AWAKE_STATUS_LOGICAL,
    AWAKE_MISSION_LOGICAL,
    AWAKE_REWARD_LOGICAL,
)


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def read_plan_relative(plan: object, relative: str, root: str = "common") -> bytes:
    entry = plan.entries.get((root, relative))
    if entry is None:
        raise PublishError(f"{root}:{relative} 不存在于 {plan.tail}")
    with zipfile.ZipFile(entry.zip_path) as archive:
        return archive.read(entry.name)


def read_plan_logical(plan: object, logical: str) -> bytes:
    digest = core.sha1_path(logical)
    return read_plan_relative(plan, f"{digest[:2]}/{digest[2:]}")


def deterministic_zip(payloads: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,
    ) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 8, 30, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])
    raw = output.getvalue()
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        if archive.testzip() is not None:
            raise PublishError("增量 ZIP CRC 校验失败")
    return raw


def flat_rows(raw: bytes, key: str) -> list[list[str]]:
    table = core.read_orderedmap_file_from_bytes(raw)
    try:
        return core.read_csv_lines(table[key])
    except KeyError as error:
        raise PublishError(f"orderedmap 缺少键 {key}") from error


def replace_flat_rows(raw: bytes, replacements: dict[str, list[list[str]]], logical: str) -> bytes:
    table = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    positions = {key: index for index, key in enumerate(table.keys)}
    for key, rows in replacements.items():
        encoded = zlib.compress(core.write_csv_lines(rows).encode("utf-8"))
        if key in positions:
            table.rows[positions[key]] = encoded
        else:
            positions[key] = len(table.keys)
            table.keys.append(key)
            table.rows.append(encoded)
    return core.build_orderedmap_raw_rows(table)


def raw_changed_keys(before: bytes, after: bytes, logical: str) -> list[str]:
    left = core.read_orderedmap_raw_rows_from_bytes(before, logical)
    right = core.read_orderedmap_raw_rows_from_bytes(after, logical)
    if left.keys != right.keys:
        added = [key for key in right.keys if key not in set(left.keys)]
        removed = [key for key in left.keys if key not in set(right.keys)]
        if removed:
            raise PublishError(f"{logical}: 输出删除了键 {removed}")
        common_changes = [
            key for key, raw in zip(left.keys, left.rows)
            if raw != right.rows[right.keys.index(key)]
        ]
        return common_changes + added
    return [
        key for key, old, new in zip(left.keys, left.rows, right.rows)
        if old != new
    ]


def gate_rows(
    rows: list[list[str]], kind_col: int, level_col: int, level: int,
) -> list[list[str]]:
    result = copy.deepcopy(rows)
    for row in result:
        row[kind_col] = "1"
        row[level_col] = str(level)
    return result


def select_rows(
    rows: list[list[str]], awake_level: int, kind_col: int, level_col: int,
) -> list[list[str]]:
    selected: list[list[str]] = []
    for row in rows:
        kind = int(row[kind_col])
        level = int(row[level_col]) if row[level_col] else 0
        if kind == 0 or (kind == 1 and awake_level == level) or (
            kind == 2 and awake_level >= level
        ):
            selected.append(row)
    return selected


def without_gate(
    rows: list[list[str]], kind_col: int, level_col: int,
) -> list[list[str]]:
    result = copy.deepcopy(rows)
    for row in result:
        row[kind_col] = "0"
        row[level_col] = ""
    return result


def build_ability(
    official_raw: bytes, current_raw: bytes,
) -> tuple[bytes, dict[str, object], dict[str, list[list[str]]]]:
    official = core.read_orderedmap_file_from_bytes(official_raw)
    current = core.read_orderedmap_file_from_bytes(current_raw)
    replacements: dict[str, list[list[str]]] = {}
    awakened_designs: dict[str, list[list[str]]] = {}
    discovered: dict[str, tuple[int, ...]] = {}
    character_reports: dict[str, object] = {}

    for character_id, expected_slots in EXPECTED_CHANGED_ABILITY_SLOTS.items():
        changed_slots: list[int] = []
        descriptions: dict[str, object] = {}
        for slot in range(1, 7):
            key = f"{character_id}{slot}"
            official_rows = core.read_csv_lines(official[key])
            current_rows = core.read_csv_lines(current[key])
            if official_rows == current_rows:
                continue
            changed_slots.append(slot)
            awakened_rows = copy.deepcopy(current_rows)

            if key == "1510453":
                damage_rows = [
                    row for row in awakened_rows
                    if row[47] in {"253", "254", "255", "356", "357", "358"}
                ]
                if len(damage_rows) != 1 or damage_rows[0][35] != "180":
                    raise PublishError("夏日莉莉丝能力3伤害CT前置状态漂移")
                damage_rows[0][35] = "150"

            combined = (
                gate_rows(official_rows, 3, 4, 0)
                + gate_rows(awakened_rows, 3, 4, 1)
            )
            replacements[key] = combined
            awakened_designs[key] = awakened_rows
            descriptions[str(slot)] = {
                "key": key,
                "official": wf_describe.describe_rows(official_rows, "ability"),
                "awakened": wf_describe.describe_rows(awakened_rows, "ability"),
                "official_rows": len(official_rows),
                "awakened_rows": len(awakened_rows),
            }
        discovered[character_id] = tuple(changed_slots)
        character_reports[character_id] = {
            "changed_slots": changed_slots,
            "abilities": descriptions,
        }
        if tuple(changed_slots) != expected_slots:
            raise PublishError(
                f"{character_id}: 能力差异槽漂移，实际 {changed_slots}，预期 {expected_slots}"
            )

    candidate = replace_flat_rows(current_raw, replacements, ABILITY_LOGICAL)
    verify = core.read_orderedmap_file_from_bytes(candidate)
    for key, awakened_rows in awakened_designs.items():
        selected = core.read_csv_lines(verify[key])
        official_rows = core.read_csv_lines(official[key])
        if without_gate(select_rows(selected, 0, 3, 4), 3, 4) != official_rows:
            raise PublishError(f"{key}: 未觉醒能力未精确还原官方行")
        if without_gate(select_rows(selected, 1, 3, 4), 3, 4) != awakened_rows:
            raise PublishError(f"{key}: 觉醒能力未精确还原最终设计")

    changed = raw_changed_keys(current_raw, candidate, ABILITY_LOGICAL)
    if set(changed) != set(replacements):
        raise PublishError(f"ability 输出键漂移: {changed}")
    return candidate, {
        "logical": ABILITY_LOGICAL,
        "changed_keys": changed,
        "characters": character_reports,
        "summer_lilith_damage_ct": {
            "ability_3_frames_before": 180,
            "ability_3_frames_after": 150,
        },
    }, awakened_designs


def build_leader(
    official_raw: bytes, current_raw: bytes,
) -> tuple[bytes, dict[str, object], dict[str, list[list[str]]]]:
    official = core.read_orderedmap_file_from_bytes(official_raw)
    current = core.read_orderedmap_file_from_bytes(current_raw)
    replacements: dict[str, list[list[str]]] = {}
    awakened_designs: dict[str, list[list[str]]] = {}
    discovered: list[str] = []
    descriptions: dict[str, object] = {}

    for character_id in CHARACTERS:
        official_rows = core.read_csv_lines(official[character_id])
        current_rows = core.read_csv_lines(current[character_id])
        if official_rows == current_rows:
            continue
        discovered.append(character_id)
        awakened_rows = copy.deepcopy(current_rows)
        if character_id == "151045":
            damage_rows = [
                row for row in awakened_rows
                if row[45] in {"253", "254", "255", "356", "357", "358"}
            ]
            if len(damage_rows) != 1 or damage_rows[0][33] != "180":
                raise PublishError("夏日莉莉丝队长技伤害CT前置状态漂移")
            damage_rows[0][33] = "150"
        combined = (
            gate_rows(official_rows, 1, 2, 0)
            + gate_rows(awakened_rows, 1, 2, 1)
        )
        replacements[character_id] = combined
        awakened_designs[character_id] = awakened_rows
        descriptions[character_id] = {
            "official": wf_describe.describe_rows(official_rows, "leader_ability"),
            "awakened": wf_describe.describe_rows(awakened_rows, "leader_ability"),
        }

    if tuple(sorted(discovered)) != tuple(sorted(EXPECTED_CHANGED_LEADERS)):
        raise PublishError(
            f"队长技差异角色漂移: {sorted(discovered)}"
        )
    candidate = replace_flat_rows(current_raw, replacements, LEADER_LOGICAL)
    verify = core.read_orderedmap_file_from_bytes(candidate)
    for character_id, awakened_rows in awakened_designs.items():
        selected = core.read_csv_lines(verify[character_id])
        official_rows = core.read_csv_lines(official[character_id])
        if without_gate(select_rows(selected, 0, 1, 2), 1, 2) != official_rows:
            raise PublishError(f"{character_id}: 未觉醒队长技未还原官方行")
        if without_gate(select_rows(selected, 1, 1, 2), 1, 2) != awakened_rows:
            raise PublishError(f"{character_id}: 觉醒队长技未还原最终设计")
    changed = raw_changed_keys(current_raw, candidate, LEADER_LOGICAL)
    if set(changed) != set(replacements):
        raise PublishError(f"leader 输出键漂移: {changed}")
    return candidate, {
        "logical": LEADER_LOGICAL,
        "changed_keys": changed,
        "descriptions": descriptions,
        "summer_lilith_damage_ct": {
            "leader_frames_before": 180,
            "leader_frames_after": 150,
        },
    }, awakened_designs


def parse_dsl(raw: bytes, logical: str) -> object:
    try:
        return wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
    except (zlib.error, ValueError, KeyError, EOFError) as error:
        raise PublishError(f"DSL 无法解析: {logical}") from error


def build_action_skill(
    official_plan: object,
    current_plan: object,
    official_raw: bytes,
    current_raw: bytes,
) -> tuple[bytes, dict[str, bytes], dict[str, object]]:
    official = core.load_nested_table_bytes(official_raw, ACTION_LOGICAL)
    current = core.load_nested_table_bytes(current_raw, ACTION_LOGICAL)
    dsl_payloads: dict[str, bytes] = {}
    character_reports: dict[str, object] = {}
    changed_outer: list[str] = []

    current_character_table = core.read_orderedmap_file_from_bytes(
        read_plan_logical(current_plan, CHARACTER_LOGICAL)
    )
    for character_id, meta in CHARACTERS.items():
        current_character_row = core.read_csv_lines(current_character_table[character_id])[0]
        code = current_character_row[0]
        official_rows = official.rows[code].text_rows()
        current_rows = current.rows[code].text_rows()
        if tuple(official_rows) != ("1", "2") or tuple(current_rows) != ("1", "2"):
            raise PublishError(f"{character_id}/{code}: 主动技进化布局不是1、2")

        official_1 = core.read_csv_lines(official_rows["1"])[0]
        official_2 = core.read_csv_lines(official_rows["2"])[0]
        current_2 = core.read_csv_lines(current_rows["2"])[0]
        awakened = copy.deepcopy(current_2)
        awakened[0] = awakened[0].rstrip("＋") + "＋＋"
        if not awakened[7].endswith("_2"):
            raise PublishError(f"{character_id}: 当前进化主动技路径不以_2结尾")
        awakened[7] = awakened[7][:-2] + "_3"

        inner = core.OrderedMap(
            f"<{character_id}-awake-action>",
            ["1", "2", "3"],
            [
                core.write_csv_lines([official_1]).encode("utf-8"),
                core.write_csv_lines([official_2]).encode("utf-8"),
                core.write_csv_lines([awakened]).encode("utf-8"),
            ],
            Path("<awakened-balance-migration>"),
        )
        current.rows[code] = inner
        changed_outer.append(code)

        official_dsl: dict[str, object] = {}
        for evolution, row in (("1", official_1), ("2", official_2)):
            logical = f"{row[7]}.action.dsl.amf3.deflate"
            raw = read_plan_logical(official_plan, logical)
            parse_dsl(raw, logical)
            dsl_payloads[logical] = raw
            official_dsl[evolution] = {
                "logical": logical,
                "sha256": sha256(raw),
                "size": len(raw),
            }

        current_logical = f"{current_2[7]}.action.dsl.amf3.deflate"
        current_dsl = read_plan_logical(current_plan, current_logical)
        current_tree = parse_dsl(current_dsl, current_logical)
        official_tree = parse_dsl(
            dsl_payloads[f"{official_2[7]}.action.dsl.amf3.deflate"],
            f"{official_2[7]}.action.dsl.amf3.deflate",
        )
        if current_tree == official_tree:
            raise PublishError(f"{character_id}: 当前主动技与官方进化技语义意外相同")
        awakened_logical = f"{awakened[7]}.action.dsl.amf3.deflate"
        if awakened_logical in dsl_payloads:
            raise PublishError(f"觉醒主动技路径冲突: {awakened_logical}")
        dsl_payloads[awakened_logical] = current_dsl

        character_reports[character_id] = {
            "label": meta["label"],
            "code": code,
            "official_evolution_1": {
                "name": official_1[0],
                "description": official_1[1],
                "program": official_1[7],
            },
            "official_evolution_2": {
                "name": official_2[0],
                "description": official_2[1],
                "program": official_2[7],
            },
            "awakened_evolution_3": {
                "name": awakened[0],
                "description": awakened[1],
                "program": awakened[7],
                "copied_from": current_logical,
                "sha256": sha256(current_dsl),
                "size": len(current_dsl),
            },
            "official_dsl": official_dsl,
        }

    candidate = core.build_nested_table(current, ACTION_LOGICAL)
    verify = core.load_nested_table_bytes(candidate, ACTION_LOGICAL)
    for character_id in CHARACTERS:
        character_row = core.read_csv_lines(current_character_table[character_id])[0]
        code = character_row[0]
        rows = verify.rows[code].text_rows()
        if tuple(rows) != ("1", "2", "3"):
            raise PublishError(f"{character_id}: 输出主动技没有1、2、3三档")
        official_rows = official.rows[code].text_rows()
        if rows["1"] != official_rows["1"] or rows["2"] != official_rows["2"]:
            raise PublishError(f"{character_id}: 未觉醒主动技行未精确还原官方")
        expected_program = character_reports[character_id]["awakened_evolution_3"]["program"]
        awakened_row = core.read_csv_lines(rows["3"])[0]
        if awakened_row[7] != expected_program:
            raise PublishError(f"{character_id}: 觉醒主动技路径回读不一致")
    for key in current.original_order:
        if key in changed_outer:
            continue
        if verify.raw_rows[key] != current.raw_rows[key]:
            raise PublishError(f"action_skill 非目标外层键发生变化: {key}")

    changed = raw_changed_keys(current_raw, candidate, ACTION_LOGICAL)
    if set(changed) != set(changed_outer):
        raise PublishError(f"action_skill 输出键漂移: {changed}")
    return candidate, dsl_payloads, {
        "logical": ACTION_LOGICAL,
        "changed_outer_keys": changed,
        "characters": character_reports,
        "dsl_payload_count": len(dsl_payloads),
    }


def build_awake_event(current_raw: bytes) -> tuple[bytes, dict[str, object]]:
    current = core.read_orderedmap_file_from_bytes(current_raw)
    replacements: dict[str, list[list[str]]] = {}
    for character_id in CHARACTERS:
        if character_id in current:
            raise PublishError(f"角色已存在觉醒活动行: {character_id}")
        replacements[character_id] = [[AWAKE_WINDOW_START, "(None)"]]
    candidate = replace_flat_rows(current_raw, replacements, AWAKE_EVENT_LOGICAL)
    changed = raw_changed_keys(current_raw, candidate, AWAKE_EVENT_LOGICAL)
    if changed != list(replacements):
        raise PublishError(f"觉醒活动输出键漂移: {changed}")
    return candidate, {
        "logical": AWAKE_EVENT_LOGICAL,
        "added_keys": changed,
        "start": AWAKE_WINDOW_START,
        "end": None,
    }


def build_awake_status(current_raw: bytes) -> tuple[bytes, dict[str, object]]:
    current = core.read_orderedmap_file_from_bytes(current_raw)
    replacements: dict[str, list[list[str]]] = {}
    for character_id in CHARACTERS:
        if character_id in current:
            raise PublishError(f"角色已存在觉醒状态行: {character_id}")
        replacements[character_id] = [["0", "0"]]
    candidate = replace_flat_rows(current_raw, replacements, AWAKE_STATUS_LOGICAL)
    changed = raw_changed_keys(current_raw, candidate, AWAKE_STATUS_LOGICAL)
    if changed != list(replacements):
        raise PublishError(f"觉醒状态输出键漂移: {changed}")
    return candidate, {
        "logical": AWAKE_STATUS_LOGICAL,
        "added_keys": changed,
        "atk_plus": 0,
        "hp_plus": 0,
    }


def character_codes(current_character_raw: bytes) -> dict[str, str]:
    table = core.read_orderedmap_file_from_bytes(current_character_raw)
    return {
        character_id: core.read_csv_lines(table[character_id])[0][0]
        for character_id in CHARACTERS
    }


def build_awake_missions(
    current_raw: bytes,
    codes: dict[str, str],
) -> tuple[bytes, dict[str, object], dict[str, list[list[str]]]]:
    current = core.read_orderedmap_file_from_bytes(current_raw)
    replacements: dict[str, list[list[str]]] = {}
    for character_id, meta in CHARACTERS.items():
        for suffix in range(1, 5):
            target_key = f"{character_id}{suffix}"
            template_key = f"{TEMPLATE_CHARACTER_ID}{suffix}"
            if target_key in current:
                raise PublishError(f"觉醒任务已存在: {target_key}")
            template_rows = core.read_csv_lines(current[template_key])
            cloned = [
                [
                    cell.replace(TEMPLATE_CHARACTER_ID, character_id)
                    .replace(TEMPLATE_CHARACTER_CODE, codes[character_id])
                    .replace(TEMPLATE_CHARACTER_NAME, meta["name"])
                    .replace("2024-12-19 12:00:00", AWAKE_WINDOW_START)
                    for cell in row
                ]
                for row in template_rows
            ]
            for row in cloned:
                row[27] = AWAKE_WINDOW_START
                row[28] = AWAKE_WINDOW_END
                row[29] = AWAKE_WINDOW_START
                row[30] = AWAKE_WINDOW_END
            replacements[target_key] = cloned
    candidate = replace_flat_rows(current_raw, replacements, AWAKE_MISSION_LOGICAL)
    changed = raw_changed_keys(current_raw, candidate, AWAKE_MISSION_LOGICAL)
    if changed != list(replacements):
        raise PublishError(f"觉醒任务输出键漂移: {changed}")
    return candidate, {
        "logical": AWAKE_MISSION_LOGICAL,
        "added_keys": changed,
        "template_character_id": TEMPLATE_CHARACTER_ID,
        "mission_count": len(changed),
        "window": [AWAKE_WINDOW_START, AWAKE_WINDOW_END],
    }, replacements


def build_awake_rewards(
    current_raw: bytes,
) -> tuple[bytes, dict[str, object], dict[str, dict[str, list[list[str]]]]]:
    outer = core.read_orderedmap_raw_rows_from_bytes(current_raw, AWAKE_REWARD_LOGICAL)
    positions = {key: index for index, key in enumerate(outer.keys)}
    extension: dict[str, dict[str, list[list[str]]]] = {}
    added: list[str] = []
    for character_id in CHARACTERS:
        for suffix in range(1, 5):
            target_key = f"{character_id}{suffix}"
            template_key = f"{TEMPLATE_CHARACTER_ID}{suffix}"
            if target_key in positions:
                raise PublishError(f"觉醒任务奖励已存在: {target_key}")
            entries = core.decode_action_skill_row(outer.rows[positions[template_key]])
            cloned = [
                (
                    inner_key,
                    [cell.replace(TEMPLATE_CHARACTER_ID, character_id) for cell in row],
                )
                for inner_key, row in entries
            ]
            outer.keys.append(target_key)
            outer.rows.append(core.encode_action_skill_row(cloned))
            positions[target_key] = len(outer.keys) - 1
            extension[target_key] = {
                inner_key: [row] for inner_key, row in cloned
            }
            added.append(target_key)
    candidate = core.build_orderedmap_raw_rows(outer)
    changed = raw_changed_keys(current_raw, candidate, AWAKE_REWARD_LOGICAL)
    if changed != added:
        raise PublishError(f"觉醒任务奖励输出键漂移: {changed}")
    return candidate, {
        "logical": AWAKE_REWARD_LOGICAL,
        "added_keys": added,
        "template_character_id": TEMPLATE_CHARACTER_ID,
        "reward_count": len(added),
    }, extension


def build_extension_config() -> dict[str, object]:
    return {
        character_id: {
            "linked_mana_node_slots": [
                {
                    "board_index": 2,
                    "ability_slot": slot,
                    "awake_level": 1,
                }
                for slot in slots
            ]
        }
        for character_id, slots in EXPECTED_BOARD2_LINKS.items()
    }


def audit_boards(extension: dict[str, object]) -> dict[str, object]:
    mana_nodes = json.loads((REPO_ROOT / "assets/mana_node.json").read_text(encoding="utf-8"))
    mana_boards = json.loads((REPO_ROOT / "assets/mana_board.json").read_text(encoding="utf-8"))
    reports: dict[str, object] = {}
    for character_id in CHARACTERS:
        nodes = mana_nodes[character_id]
        layouts = mana_boards[character_id]
        if sorted(nodes) != ["1", "2"] or sorted(layouts) != ["1", "2"]:
            raise PublishError(f"{character_id}: 魔晶板不是两板布局")
        board_slots = {
            board: sorted({
                int(node["field6"]) if node["field6"] else "action_skill"
                for node in board_nodes.values()
            }, key=lambda value: 99 if value == "action_skill" else int(value))
            for board, board_nodes in nodes.items()
        }
        if board_slots["1"] != [1, 2, 3, "action_skill"]:
            raise PublishError(f"{character_id}: 一板槽位布局漂移 {board_slots['1']}")
        if board_slots["2"] != [4, 5, 6]:
            raise PublishError(f"{character_id}: 二板槽位布局漂移 {board_slots['2']}")
        expected_links = list(EXPECTED_BOARD2_LINKS.get(character_id, ()))
        configured = [
            item["ability_slot"]
            for item in extension.get(character_id, {}).get("linked_mana_node_slots", [])
        ]
        if configured != expected_links:
            raise PublishError(f"{character_id}: 二板觉醒联动配置漂移")
        reports[character_id] = {
            "board_slots": board_slots,
            "node_counts": {board: len(board_nodes) for board, board_nodes in nodes.items()},
            "linked_board2_slots": configured,
            "skill_evolution_nodes": [
                int(node_id) for node_id, node in nodes["1"].items()
                if node["field5"] == "2" and node["field6"] == ""
            ],
        }
        if len(reports[character_id]["skill_evolution_nodes"]) != 1:
            raise PublishError(f"{character_id}: 技能进化节点数量不是1")
    return reports


def verify_dark_dragon_exception(
    official_raw: dict[str, bytes], current_raw: dict[str, bytes],
) -> dict[str, object]:
    character_id = "261089"
    official_character = flat_rows(official_raw[CHARACTER_LOGICAL], character_id)[0]
    current_character = flat_rows(current_raw[CHARACTER_LOGICAL], character_id)[0]
    if official_character[2] != "4" or current_character[2] != "5":
        raise PublishError(
            f"暗龙星级前置状态漂移: official={official_character[2]} current={current_character[2]}"
        )
    official_status = core.read_orderedmap_raw_rows_from_bytes(
        official_raw[STATUS_LOGICAL], STATUS_LOGICAL,
    )
    current_status = core.read_orderedmap_raw_rows_from_bytes(
        current_raw[STATUS_LOGICAL], STATUS_LOGICAL,
    )
    official_map = dict(zip(official_status.keys, official_status.rows))
    current_map = dict(zip(current_status.keys, current_status.rows))
    if official_map[character_id] == current_map[character_id]:
        raise PublishError("暗龙五星成长曲线与官方四星曲线意外相同")
    return {
        "character_id": 261089,
        "official_rarity": 4,
        "preserved_rarity": 5,
        "official_status_sha256": sha256(official_map[character_id]),
        "preserved_status_sha256": sha256(current_map[character_id]),
        "character_table_written": False,
        "character_status_table_written": False,
    }


def verify_unrelated_identity_and_status(
    official_raw: dict[str, bytes], current_raw: dict[str, bytes],
) -> None:
    for character_id in CHARACTERS:
        official_character = flat_rows(official_raw[CHARACTER_LOGICAL], character_id)[0]
        current_character = flat_rows(current_raw[CHARACTER_LOGICAL], character_id)[0]
        differing = [
            index for index, (old, new) in enumerate(zip(official_character, current_character))
            if old != new
        ]
        expected = [2] if character_id == "261089" else []
        if differing != expected:
            raise PublishError(f"{character_id}: character差异列漂移 {differing}")


def source_plans() -> tuple[object, object]:
    cdn_root, _runtime_root = wf_live_cdn._resolve_locations()
    official = materialize.build_read_only_plan(
        cdn_root, REPO_ROOT, OFFICIAL_VERSION, False,
    )
    current = materialize.build_read_only_plan(
        cdn_root, REPO_ROOT, BASE_VERSION, False,
    )
    if official.tail != OFFICIAL_VERSION or current.tail != BASE_VERSION:
        raise PublishError(
            f"资源链尾不符: official={official.tail} current={current.tail}"
        )
    return official, current


def build() -> tuple[bytes, dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    official_plan, current_plan = source_plans()
    official_raw = {
        logical: read_plan_logical(official_plan, logical)
        for logical in TABLE_LOGICALS
    }
    current_raw = {
        logical: read_plan_logical(current_plan, logical)
        for logical in TABLE_LOGICALS
    }
    verify_unrelated_identity_and_status(official_raw, current_raw)
    dark_exception = verify_dark_dragon_exception(official_raw, current_raw)

    ability_raw, ability_report, _awakened_abilities = build_ability(
        official_raw[ABILITY_LOGICAL], current_raw[ABILITY_LOGICAL],
    )
    leader_raw, leader_report, _awakened_leaders = build_leader(
        official_raw[LEADER_LOGICAL], current_raw[LEADER_LOGICAL],
    )
    action_raw, dsl_payloads, action_report = build_action_skill(
        official_plan,
        current_plan,
        official_raw[ACTION_LOGICAL],
        current_raw[ACTION_LOGICAL],
    )
    event_raw, event_report = build_awake_event(current_raw[AWAKE_EVENT_LOGICAL])
    status_raw, awake_status_report = build_awake_status(current_raw[AWAKE_STATUS_LOGICAL])
    codes = character_codes(current_raw[CHARACTER_LOGICAL])
    mission_raw, mission_report, mission_extension = build_awake_missions(
        current_raw[AWAKE_MISSION_LOGICAL], codes,
    )
    reward_raw, reward_report, reward_extension = build_awake_rewards(
        current_raw[AWAKE_REWARD_LOGICAL],
    )
    server_extension = build_extension_config()
    board_report = audit_boards(server_extension)

    payloads = {
        member_name(ABILITY_LOGICAL): ability_raw,
        member_name(LEADER_LOGICAL): leader_raw,
        member_name(ACTION_LOGICAL): action_raw,
        member_name(AWAKE_EVENT_LOGICAL): event_raw,
        member_name(AWAKE_STATUS_LOGICAL): status_raw,
        member_name(AWAKE_MISSION_LOGICAL): mission_raw,
        member_name(AWAKE_REWARD_LOGICAL): reward_raw,
        **{member_name(logical): raw for logical, raw in dsl_payloads.items()},
    }
    archive_raw = deterministic_zip(payloads)
    report: dict[str, object] = {
        "schema": "wf-awakened-balance-migration/v1",
        "patch_id": PATCH_ID,
        "official_version": OFFICIAL_VERSION,
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "characters": [int(value) for value in CHARACTERS],
        "tables": [
            ability_report,
            leader_report,
            action_report,
            event_report,
            awake_status_report,
            mission_report,
            reward_report,
        ],
        "dark_dragon_exception": dark_exception,
        "mana_boards": board_report,
        "server_extensions": {
            "linked_board2_abilities": server_extension,
            "mission_definition_keys": list(mission_extension),
            "mission_reward_keys": list(reward_extension),
        },
        "archive": {
            "name": ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": len(payloads),
        },
        "payloads": [
            {
                "member": name,
                "size": len(raw),
                "sha256": sha256(raw),
            }
            for name, raw in sorted(payloads.items())
        ],
        "verification": {
            "unawakened_abilities_equal_official": True,
            "awakened_abilities_equal_reviewed_terminal": True,
            "unawakened_leaders_equal_official": True,
            "awakened_leaders_equal_reviewed_terminal": True,
            "action_evolution_1_2_equal_official": True,
            "action_evolution_3_equal_reviewed_evolution_2": True,
            "summer_lilith_damage_ct_180_to_150": True,
            "dark_dragon_rarity_and_status_preserved": True,
            "unrelated_outer_rows_preserved": True,
            "archive_crc_ok": True,
        },
    }
    server_assets = {
        "character_awake_extension.json": server_extension,
        "mission_char_awake_cnmod.json": mission_extension,
        "mission_char_awake_reward_cnmod.json": reward_extension,
    }
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return archive_raw, report, server_assets, manifest, {
        "source_current_tail": current_plan.tail,
        "source_official_tail": official_plan.tail,
    }


def update_manifest(manifest: dict[str, object], report: dict[str, object]) -> dict[str, object]:
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        raise PublishError("manifest.patches 不是数组")
    enabled = [item for item in patches if item.get("enabled")]
    if not enabled:
        raise PublishError("manifest 没有启用补丁")
    valid_tail_ids = {"simoun-abyss-stability-1.4.93", PATCH_ID}
    if enabled[-1].get("id") not in valid_tail_ids:
        raise PublishError(f"manifest 链尾不是已知1.4.93/1.4.94: {enabled[-1].get('id')}")
    manifest["patches"] = [item for item in patches if item.get("id") != PATCH_ID]
    archive = report["archive"]
    files = [item["member"] for item in report["payloads"]]
    entry = {
        "id": PATCH_ID,
        "type": "patch",
        "name": "九名官方角色上修改为觉醒后生效",
        "description": (
            "能力光六人、光龙、暗龙与白花机人雷吉斯在未觉醒时恢复官方数值，"
            "觉醒后切换至本服最终上修设计；暗龙继续保持五星身份和五星成长。"
        ),
        "version": TARGET_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": archive["size"],
        "files": files,
        "changes": [
            "151045、151027、151021、151015、251017、251053、151159、261089、131020的官方能力作为未觉醒行，既有最终上修能力作为觉醒1级替换行。",
            "有改动的队长技按同样规则切换；九名角色主动技进化1/2恢复官方实装，新增进化3承载现行上修DSL。",
            "暗龙阿鲁玛德乌斯（261089）继续保持五星稀有度与当前五星HP/ATK成长曲线，不写回官方四星角色主表或四星成长。",
            "夏日莉莉丝能力3与队长技中真正造成伤害的追击CT由3秒小幅缩短至2.5秒，纯增益触发CT不变。",
            "为九名角色追加长期有效的觉醒活动、任务、奖励与零额外面板加成状态；二板上发生变化的能力4至6由服务端配置联动觉醒等级。",
        ],
        "created_at": "2026-08-30",
        "audit": {
            "directory": str(AUDIT_DIR.relative_to(REPO_ROOT)).replace("\\", "/"),
            "report": "report.json",
        },
        "archive_integrity": [archive],
        "chain": [ARCHIVE_NAME],
    }
    manifest["patches"].append(entry)
    manifest["cdn_version"] = TARGET_VERSION
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    archive_raw, report, server_assets, manifest, sources = build()
    summary = {
        "ok": True,
        "dry_run": not args.apply,
        "sources": sources,
        "patch_id": PATCH_ID,
        "archive": report["archive"],
        "characters": report["characters"],
        "dark_dragon_exception": report["dark_dragon_exception"],
        "verification": report["verification"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0

    updated_manifest = update_manifest(manifest, report)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    (ACTIVE_DIR / ARCHIVE_NAME).write_bytes(archive_raw)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    for name, data in server_assets.items():
        path = REPO_ROOT / "assets" / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    MANIFEST_PATH.write_text(
        json.dumps(updated_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {ACTIVE_DIR / ARCHIVE_NAME}")
    print(f"wrote {AUDIT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
