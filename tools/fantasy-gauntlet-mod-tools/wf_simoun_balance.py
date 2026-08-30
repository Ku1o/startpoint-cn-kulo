"""西蒙（169996）主动技能与能力数值的本地平衡规则。

本模块只转换调用方传入的 master-data / ActionDsl 字节，不写 CDN、
不生成补丁包，也不接触运行镜像。能力1～3与队长技中的团队向增益保留50%，
自身专属增益保留75%；能力4～6、伤害、回复、敌方减益与「羊群」获取规则
保持不变。主动技能的全队技能槽由20%调整为15%，不再清空「羊群」。
``AddSkillPoint`` 的第一个参数是作用对象 ID，必须保留为 20；只有第二个
参数中的固定比例由 0.20 调整为 0.15。
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Iterable, Mapping
import zlib

import wf_dsl
import wf_dsl_sig
import wf_mod_tool as core


CHARACTER_ID = "169996"
CHARACTER_NAME = "西蒙"
UNIQUE_CONDITION_ID = 169996

ABILITY_LOGICAL = core.ABILITY_LOGICAL
LEADER_ABILITY_LOGICAL = "master/ability/leader_ability.orderedmap"
ACTION_SKILL_LOGICAL = "master/skill/action_skill.orderedmap"
CHARACTER_TEXT_LOGICAL = "master/character/character_text.orderedmap"
ACTION_SKILL_KEY = "simoun_dark"

SKILL_DSL_LOGICALS = {
    level: (
        "battle/action/skill/action/rare5/simoun_dark$"
        f"simoun_dark_{level}.action.dsl.amf3.deflate"
    )
    for level in (1, 2, 3)
}

SKILL_DESCRIPTION = (
    "使全场敌人攻击力降低30%与暗属性抗性降低20%（20秒），全体队员技能槽增加15%；"
    "根据发动技能时自身「羊群」等级，对全场敌人造成暗属性伤害，并恢复全体队员生命值："
    "0／1／2／3／4级时，伤害倍率为20／40／60／80／100倍，"
    "生命回复量为各自最大生命值的0%／3%／6%／9%／12%。"
)

UNSAFE_RESET_SKILL_DESCRIPTION = (
    SKILL_DESCRIPTION + "上述效果结算后，将自身「羊群」等级清零。"
)

OLD_SKILL_DESCRIPTIONS = {
    (
        "使全场敌人攻击力降低30%与暗属性抗性降低20%（20秒），全体队员技能槽增加20%；"
        "根据自身「羊群」等级对全场敌人造成暗属性伤害并恢复全体队员生命值："
        "0／1／2／3／4级时，伤害倍率为20／40／60／80／100倍，"
        "回复量为最大生命值的0%／3%／6%／9%／12%。"
    ),
    SKILL_DESCRIPTION,
    UNSAFE_RESET_SKILL_DESCRIPTION,
}

# (行号, 数值列, 当前值, 目标值, 说明)
# ability 表：瞬发效果强度位于 c51/c52，持续效果强度位于 c113/c114。
ABILITY_EDITS: Mapping[str, tuple[tuple[int, int, str, str, str], ...]] = {
    "1699961": (
        (2, 113, "4000", "2000", "每级羊群·暗角色技能充能速度"),
        (2, 114, "4000", "2000", "每级羊群·暗角色技能充能速度"),
        (3, 51, "5000", "3750", "队友发动技能·自身技能槽"),
        (3, 52, "5000", "3750", "队友发动技能·自身技能槽"),
        (4, 51, "50000", "37500", "队友发动技能·自身攻击力"),
        (4, 52, "50000", "37500", "队友发动技能·自身攻击力"),
        (5, 51, "50000", "37500", "队友发动技能·自身技能伤害"),
        (5, 52, "50000", "37500", "队友发动技能·自身技能伤害"),
    ),
    "1699962": (
        (1, 113, "100000", "50000", "每级羊群·暗角色攻击力"),
        (1, 114, "100000", "50000", "每级羊群·暗角色攻击力"),
        (2, 113, "100000", "50000", "每级羊群·暗角色技能伤害"),
        (2, 114, "100000", "50000", "每级羊群·暗角色技能伤害"),
        (3, 113, "20000", "10000", "每个协力球·暗角色独立技能伤害"),
        (3, 114, "20000", "10000", "每个协力球·暗角色独立技能伤害"),
    ),
    "1699963": (
        (1, 51, "50000", "37500", "战斗开始·自身技能槽"),
        (1, 52, "50000", "37500", "战斗开始·自身技能槽"),
        (2, 113, "10000", "7500", "每级羊群·自身减益特攻"),
        (2, 114, "10000", "7500", "每级羊群·自身减益特攻"),
        (3, 113, "10000", "5000", "每级羊群·暗角色减益特攻"),
        (3, 114, "10000", "5000", "每级羊群·暗角色减益特攻"),
        (4, 113, "10000", "5000", "每级羊群·暗角色六属性敌人伤害"),
        (4, 114, "10000", "5000", "每级羊群·暗角色六属性敌人伤害"),
    ),
}

# leader_ability 比 ability 少两个表头列，强度位于 c49/c50 或 c111/c112。
LEADER_EDITS: Mapping[str, tuple[tuple[int, int, str, str, str], ...]] = {
    CHARACTER_ID: (
        (1, 49, "50000", "25000", "暗角色满编·暗角色技能槽"),
        (1, 50, "50000", "25000", "暗角色满编·暗角色技能槽"),
        (2, 111, "50000", "37500", "每级羊群·自身攻击力"),
        (2, 112, "50000", "37500", "每级羊群·自身攻击力"),
        (3, 111, "50000", "37500", "每级羊群·自身技能伤害"),
        (3, 112, "50000", "37500", "每级羊群·自身技能伤害"),
        (4, 111, "100000", "50000", "每级羊群·暗角色攻击力"),
        (4, 112, "100000", "50000", "每级羊群·暗角色攻击力"),
        (5, 111, "100000", "50000", "每级羊群·暗角色技能伤害"),
        (5, 112, "100000", "50000", "每级羊群·暗角色技能伤害"),
        (6, 111, "8000", "4000", "每级羊群·暗角色技能充能速度"),
        (6, 112, "8000", "4000", "每级羊群·暗角色技能充能速度"),
    ),
}

_EXPECTED_ABILITY_ROW_COUNTS = {
    "1699961": 5,
    "1699962": 3,
    "1699963": 4,
}
_EXPECTED_LEADER_ROW_COUNTS = {CHARACTER_ID: 6}


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _raw_deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(data) + compressor.flush()


def _decode_skill(raw: bytes, logical: str) -> list[Any]:
    try:
        tree = wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
    except Exception as error:
        raise ValueError(f"无法解析西蒙主动技能 DSL: {logical}: {error}") from error
    if not isinstance(tree, list) or len(tree) != 12 or tree[0] != "ActionDsl":
        raise ValueError(f"{logical}: ActionDsl 根节点形状漂移")
    if tree[10] != 0 or tree[11][0] != "Block":
        raise ValueError(f"{logical}: ActionDsl 根 Block 漂移")
    return tree


def _fixed_range(node: Any, label: str) -> float:
    if (
        not isinstance(node, list)
        or len(node) != 1
        or not isinstance(node[0], dict)
        or set(node[0]) != {"min", "max"}
    ):
        raise ValueError(f"{label}数值范围形状漂移: {node!r}")
    minimum = float(node[0]["min"])
    maximum = float(node[0]["max"])
    if not math.isclose(minimum, maximum, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{label}不是固定值: {minimum}/{maximum}")
    return minimum


def _skill_facts(tree: list[Any], logical: str) -> dict[str, Any]:
    gauge_commands: list[list[Any]] = []
    attacks: list[float] = []
    heals: list[float] = []
    flock_branches: list[int] = []
    resets: list[list[Any]] = []
    for node in _walk(tree):
        if not isinstance(node, list) or not node:
            continue
        if node[0] == "AddSkillPoint":
            gauge_commands.append(node)
        elif node[0] == "CreateNormalAttack":
            if len(node) <= 6:
                raise ValueError(f"{logical}: CreateNormalAttack 形状漂移")
            attacks.append(_fixed_range(node[6], "伤害倍率"))
        elif node[0] == "CreateRatioHeal":
            if len(node) <= 3:
                raise ValueError(f"{logical}: CreateRatioHeal 形状漂移")
            heals.append(_fixed_range(node[3], "生命回复比例"))
        elif (
            node[0] == "ConditionalsConditionAccumulationNumber"
            and len(node) >= 3
            and node[1] == ["DCUnique", UNIQUE_CONDITION_ID]
        ):
            flock_branches.append(int(node[2]))
        elif node[0] == "ConsumeUniqueCondition":
            resets.append(node)

    if len(gauge_commands) != 1:
        raise ValueError(f"{logical}: 全队技能槽命令数量漂移: {len(gauge_commands)}")
    if sorted(attacks) != [20.0, 40.0, 60.0, 80.0, 100.0]:
        raise ValueError(f"{logical}: 羊群伤害档位漂移: {sorted(attacks)}")
    if sorted(heals) != [0.03, 0.03, 0.06, 0.06, 0.09, 0.09, 0.12, 0.12]:
        raise ValueError(f"{logical}: 羊群生命回复档位漂移: {sorted(heals)}")
    if sorted(flock_branches) != [1, 2, 3, 4]:
        raise ValueError(f"{logical}: 羊群条件分支漂移: {sorted(flock_branches)}")
    if len(resets) > 1:
        raise ValueError(f"{logical}: 羊群清零命令重复")
    return {
        "gauge": gauge_commands[0],
        "attacks": attacks,
        "heals": heals,
        "resets": resets,
    }


UNSAFE_RESET_COMMAND = [
    "Event",
    [
        "Wait",
        3,
        "*",
        [
            "Block",
            [["Command", ["ConsumeUniqueCondition", -17, UNIQUE_CONDITION_ID, ["None"]]]],
        ],
    ],
]


def patch_skill_dsl(raw: bytes, logical: str) -> tuple[bytes, dict[str, Any]]:
    """保留技能槽作用对象 ID 20，将比例改为15%，并移除羊群清零。"""
    if logical not in SKILL_DSL_LOGICALS.values():
        raise ValueError(f"不是受支持的西蒙主动技能路径: {logical}")
    tree = _decode_skill(raw, logical)
    facts = _skill_facts(tree, logical)
    before = copy.deepcopy(tree)

    gauge = facts["gauge"]
    if len(gauge) != 3:
        raise ValueError(f"{logical}: AddSkillPoint 形状漂移")
    target_id = int(gauge[1])
    ratio = _fixed_range(gauge[2], "全队技能槽")
    if (target_id, ratio) not in ((20, 0.2), (20, 0.15), (15, 0.15)):
        raise ValueError(
            f"{logical}: 技能槽对象ID/数值未审核: {target_id}/{ratio}"
        )
    # AddSkillPoint 参数1是作用对象 ID，不是百分比。历史错误把 20 改成了
    # 15，会让运行器解析到无效对象并报 C16103。
    gauge[1] = 20
    gauge[2][0]["min"] = 0.15
    gauge[2][0]["max"] = 0.15

    if facts["resets"]:
        if UNSAFE_RESET_COMMAND not in tree[11][1]:
            raise ValueError(f"{logical}: 羊群清零命令位置或延迟未审核")
        expected = UNSAFE_RESET_COMMAND[1][3][1][0][1]
        if facts["resets"][0] != expected:
            raise ValueError(f"{logical}: 羊群清零命令参数漂移")
        tree[11][1].remove(UNSAFE_RESET_COMMAND)

    # 先按官方签名验证完整树，再声明本次只允许修改 AddSkillPoint 的“数值”
    # 参数 p2。历史错误包的 p1=15 只允许在已识别的修复分支恢复为对象 ID 20；
    # 干净基线若再次误改 p1，会在编码前直接失败。
    mutable_gauge_parameters = {1, 2} if target_id == 15 else {2}
    wf_dsl_sig.assert_command_parameter_edits(
        before, tree, {"AddSkillPoint": mutable_gauge_parameters})

    changed = tree != before
    output = _raw_deflate(wf_dsl.encode_amf3(tree)) if changed else raw
    readback = _decode_skill(output, logical)
    wf_dsl_sig.validate_action_dsl(readback)
    final = _skill_facts(readback, logical)
    if (final["gauge"][1], _fixed_range(final["gauge"][2], "全队技能槽")) != (20, 0.15):
        raise AssertionError(f"{logical}: 全队技能槽回读不一致")
    if final["resets"]:
        raise AssertionError(f"{logical}: 羊群清零命令仍然存在")
    return output, {
        "logical": logical,
        "skill_point_target_id": 20,
        "party_skill_gauge_percent": 15,
        "damage_multipliers": [20, 40, 60, 80, 100],
        "party_heal_max_hp_percent": [0, 3, 6, 9, 12],
        "flock_reset": "已撤销；主动技能不再清空羊群",
        "changed": changed,
    }


def patch_skill_dsls(payloads: Mapping[str, bytes]) -> tuple[dict[str, bytes], dict[str, Any]]:
    missing = sorted(set(SKILL_DSL_LOGICALS.values()) - set(payloads))
    if missing:
        raise ValueError(f"缺少西蒙主动技能 payload: {missing}")
    output: dict[str, bytes] = {}
    report: dict[str, Any] = {}
    for level, logical in SKILL_DSL_LOGICALS.items():
        output[logical], report[f"skill_lv{level}"] = patch_skill_dsl(
            payloads[logical], logical
        )
    return output, report


def _patch_csv_table(
    raw: bytes,
    logical: str,
    edits: Mapping[str, tuple[tuple[int, int, str, str, str], ...]],
    expected_counts: Mapping[str, int],
    expected_width: int,
) -> tuple[bytes, dict[str, Any]]:
    table = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    if len(table.keys) != len(set(table.keys)):
        raise ValueError(f"{logical}: 存在重复键")
    missing = sorted(set(edits) - set(table.keys))
    if missing:
        raise ValueError(f"{logical}: 缺少西蒙能力键: {missing}")

    before_outer = list(table.rows)
    details: list[dict[str, Any]] = []
    for key, key_edits in edits.items():
        position = table.keys.index(key)
        try:
            text = zlib.decompress(table.rows[position]).decode("utf-8")
        except Exception as error:
            raise ValueError(f"{logical}#{key}: 无法解码 CSV") from error
        rows = core.read_csv_lines(text)
        if len(rows) != expected_counts[key]:
            raise ValueError(
                f"{logical}#{key}: 行数漂移 {len(rows)} != {expected_counts[key]}"
            )
        if any(len(row) != expected_width for row in rows):
            raise ValueError(f"{logical}#{key}: 列数漂移")
        expected_string_id = "simoun_dark" + (f"_{key[-1]}" if key != CHARACTER_ID else "")
        if any(row[0] != expected_string_id for row in rows):
            raise ValueError(f"{logical}#{key}: string_id 漂移")

        changed_key = False
        for line, column, current, target, label in key_edits:
            value = rows[line - 1][column]
            if value not in (current, target):
                raise ValueError(
                    f"{logical}#{key} line{line} c{column} {label}未审核: {value!r}"
                )
            if value != target:
                rows[line - 1][column] = target
                changed_key = True
            details.append(
                {
                    "key": key,
                    "line": line,
                    "column": column,
                    "label": label,
                    "before": value,
                    "after": target,
                }
            )
        if changed_key:
            table.rows[position] = zlib.compress(core.write_csv_lines(rows).encode("utf-8"))

    if table.rows == before_outer:
        return raw, {"logical": logical, "edits": details, "changed": False}
    output = core.build_orderedmap_raw_rows(table)
    readback = core.read_orderedmap_raw_rows_from_bytes(output, logical)
    if readback.keys != table.keys:
        raise AssertionError(f"{logical}: 键顺序漂移")
    target_keys = set(edits)
    for index, (before, after) in enumerate(zip(before_outer, readback.rows)):
        if table.keys[index] not in target_keys and before != after:
            raise AssertionError(f"{logical}: 非目标键被改动: {table.keys[index]}")
    return output, {"logical": logical, "edits": details, "changed": True}


def patch_ability_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    return _patch_csv_table(
        raw,
        ABILITY_LOGICAL,
        ABILITY_EDITS,
        _EXPECTED_ABILITY_ROW_COUNTS,
        126,
    )


def patch_leader_ability_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    return _patch_csv_table(
        raw,
        LEADER_ABILITY_LOGICAL,
        LEADER_EDITS,
        _EXPECTED_LEADER_ROW_COUNTS,
        124,
    )


def patch_action_skill_entries(
    entries: list[tuple[str, list[str]]],
) -> tuple[list[tuple[str, list[str]]], dict[str, Any]]:
    if [level for level, _row in entries] != ["1", "2", "3"]:
        raise ValueError("西蒙主动技能级别集合漂移")
    output: list[tuple[str, list[str]]] = []
    for level, row in entries:
        patched = list(row)
        if len(patched) != 24:
            raise ValueError(f"西蒙主动技能{level}列数漂移: {len(patched)}")
        expected_program = (
            "battle/action/skill/action/rare5/simoun_dark$"
            f"simoun_dark_{level}"
        )
        if patched[core.ACTION_SKILL_COLUMNS["program_path"]] != expected_program:
            raise ValueError(f"西蒙主动技能{level}程序路径漂移")
        column = core.ACTION_SKILL_COLUMNS["description"]
        if patched[column] not in OLD_SKILL_DESCRIPTIONS:
            raise ValueError(f"西蒙主动技能{level}文案出现未审核内容")
        patched[column] = SKILL_DESCRIPTION
        output.append((level, patched))
    return output, {"character_id": CHARACTER_ID, "description": SKILL_DESCRIPTION}


def patch_action_skill_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    table = core.read_orderedmap_raw_rows_from_bytes(raw, ACTION_SKILL_LOGICAL)
    try:
        position = table.keys.index(ACTION_SKILL_KEY)
    except ValueError as error:
        raise ValueError("action_skill.orderedmap 缺少 simoun_dark") from error
    before = list(table.rows)
    entries, report = patch_action_skill_entries(
        core.decode_action_skill_row(table.rows[position])
    )
    replacement = core.encode_action_skill_row(entries)
    if replacement == table.rows[position]:
        report["changed"] = False
        return raw, report
    table.rows[position] = replacement
    output = core.build_orderedmap_raw_rows(table)
    readback = core.read_orderedmap_raw_rows_from_bytes(output, ACTION_SKILL_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("action_skill.orderedmap 键顺序漂移")
    for index, (old, new) in enumerate(zip(before, readback.rows)):
        if index != position and old != new:
            raise AssertionError(f"非西蒙主动技能被改动: {table.keys[index]}")
    report["changed"] = True
    return output, report


def patch_character_text_rows(rows: list[list[str]]) -> tuple[list[list[str]], dict[str, Any]]:
    if len(rows) != 1 or len(rows[0]) != 12:
        raise ValueError("西蒙 character_text 行列形状漂移")
    row = list(rows[0])
    if row[0] != CHARACTER_NAME:
        raise ValueError(f"西蒙 character_text 角色名漂移: {row[0]!r}")
    for column in (5, 7, 9):
        if row[column] not in OLD_SKILL_DESCRIPTIONS:
            raise ValueError(f"西蒙 character_text c{column}出现未审核文案")
        row[column] = SKILL_DESCRIPTION
    return [row], {"character_id": CHARACTER_ID, "description": SKILL_DESCRIPTION}


def patch_character_text_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    table = core.read_orderedmap_raw_rows_from_bytes(raw, CHARACTER_TEXT_LOGICAL)
    try:
        position = table.keys.index(CHARACTER_ID)
    except ValueError as error:
        raise ValueError("character_text.orderedmap 缺少 169996") from error
    before = list(table.rows)
    rows = core.read_csv_lines(zlib.decompress(table.rows[position]).decode("utf-8"))
    patched, report = patch_character_text_rows(rows)
    replacement = zlib.compress(core.write_csv_lines(patched).encode("utf-8"))
    if replacement == table.rows[position]:
        report["changed"] = False
        return raw, report
    table.rows[position] = replacement
    output = core.build_orderedmap_raw_rows(table)
    readback = core.read_orderedmap_raw_rows_from_bytes(output, CHARACTER_TEXT_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("character_text.orderedmap 键顺序漂移")
    for index, (old, new) in enumerate(zip(before, readback.rows)):
        if index != position and old != new:
            raise AssertionError(f"非西蒙角色文案被改动: {table.keys[index]}")
    report["changed"] = True
    return output, report


__all__ = [
    "ABILITY_EDITS",
    "ABILITY_LOGICAL",
    "ACTION_SKILL_KEY",
    "ACTION_SKILL_LOGICAL",
    "CHARACTER_ID",
    "CHARACTER_NAME",
    "CHARACTER_TEXT_LOGICAL",
    "LEADER_EDITS",
    "LEADER_ABILITY_LOGICAL",
    "UNSAFE_RESET_COMMAND",
    "SKILL_DESCRIPTION",
    "SKILL_DSL_LOGICALS",
    "patch_ability_table",
    "patch_action_skill_table",
    "patch_character_text_table",
    "patch_leader_ability_table",
    "patch_skill_dsl",
    "patch_skill_dsls",
]
