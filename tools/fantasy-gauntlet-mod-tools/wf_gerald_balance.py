"""杰拉德（149999）主动技能与能力2～5的本地平衡规则。

本模块只转换调用方传入的 master-data / ActionDsl 字节，不写 CDN、
不生成补丁包，也不接触运行镜像。调整范围严格限定为：

* 两档主动技能的能力伤害抗性与光属性抗性降低统一为15%；
* 能力2每5次冲刺的四项永久增益各限制为整场只触发1次；
* 能力3的FEVER中PF3追击由10倍降为3倍；
* 能力4改为主位限定，最近敌人追击由10倍降为1倍；
* 能力5改为主位限定，六属性全体追击各由5倍降为3倍。
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
import math
from typing import Any
import zlib

import wf_dsl
import wf_mod_tool as core


CHARACTER_ID = "149999"
CHARACTER_NAME = "杰拉德"
ABILITY_LOGICAL = core.ABILITY_LOGICAL

SKILL_DSL_LOGICALS = {
    level: (
        "battle/action/skill/action/rare5/white_wolf_gerald$"
        f"white_wolf_gerald_{level}.action.dsl.amf3.deflate"
    )
    for level in (1, 2)
}

TARGET_RESISTANCE = -0.15
CURRENT_RESISTANCES = {
    1: {"ability": -2.0, "light": -0.5},
    2: {"ability": -2.0, "light": -0.1},
}

# (行号, 列号, 原值, 目标值, 说明)
# ability 表：c1=false为主位限定，c34为瞬发触发次数上限，c51/c52为
# 瞬发效果的满级／SLv1强度。
ABILITY_EDITS: Mapping[str, tuple[tuple[int, int, str, str, str], ...]] = {
    "1499992": tuple(
        (line, 34, "(None)", "1", "每5次冲刺增益·整场只触发1次")
        for line in range(1, 5)
    ),
    "1499993": (
        (1, 51, "1000000", "300000", "FEVER中PF3全体能力伤害·10倍→3倍"),
        (1, 52, "1000000", "300000", "FEVER中PF3全体能力伤害·10倍→3倍"),
    ),
    "1499994": (
        (1, 1, "true", "false", "冲刺追击·改为主位限定"),
        (1, 51, "1000000", "100000", "最近敌人能力伤害·10倍→1倍"),
        (1, 52, "1000000", "100000", "最近敌人能力伤害·10倍→1倍"),
        (2, 1, "true", "false", "冲刺追加连击·改为主位限定"),
    ),
    "1499995": tuple(
        edit
        for line in range(1, 7)
        for edit in (
            (line, 1, "true", "false", "六属性全体追击·改为主位限定"),
            (line, 51, "500000", "300000", "六属性全体追击·5倍→3倍"),
            (line, 52, "500000", "300000", "六属性全体追击·5倍→3倍"),
        )
    ),
}

_EXPECTED_ROW_COUNTS = {
    "1499992": 5,
    "1499993": 6,
    "1499994": 2,
    "1499995": 6,
}
_EXPECTED_STRING_IDS = {
    "1499992": ["black_wolf_knight_2"] * 5,
    "1499993": ["black_wolf_knight_3"] * 4 + ["black_wolf_knight_5"] * 2,
    "1499994": ["black_wolf_knight_4"] * 2,
    "1499995": ["black_wolf_knight_3"] * 6,
}
_ABILITY_ROW_WIDTH = 126


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
        raise ValueError(f"无法解析杰拉德主动技能DSL: {logical}: {error}") from error
    if not isinstance(tree, list) or not tree or tree[0] != "ActionDsl":
        raise ValueError(f"{logical}: ActionDsl根节点形状漂移")
    return tree


def _fixed_range(value: Any, label: str) -> float:
    if (
        not isinstance(value, list)
        or len(value) != 1
        or not isinstance(value[0], dict)
        or set(value[0]) != {"min", "max"}
    ):
        raise ValueError(f"{label}范围形状漂移: {value!r}")
    minimum = float(value[0]["min"])
    maximum = float(value[0]["max"])
    if not math.isclose(minimum, maximum, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{label}不是固定值: {minimum}/{maximum}")
    return minimum


def _set_fixed_range(value: list[dict[str, float]], target: float) -> None:
    value[0]["min"] = target
    value[0]["max"] = target


def _skill_conditions(
    tree: list[Any], logical: str
) -> tuple[list[Any], list[Any]]:
    ability_conditions: list[list[Any]] = []
    light_conditions: list[list[Any]] = []
    for node in _walk(tree):
        if not isinstance(node, list) or not node:
            continue
        if node[0] == "ACAbilityDamageResistance":
            ability_conditions.append(node)
        elif node[0] == "ACToleranceOfElement" and len(node) > 2 and node[2] == 5:
            light_conditions.append(node)
    if len(ability_conditions) != 1:
        raise ValueError(
            f"{logical}: 能力伤害抗性降低词条数量漂移: {len(ability_conditions)}"
        )
    if len(light_conditions) != 1:
        raise ValueError(
            f"{logical}: 光属性抗性降低词条数量漂移: {len(light_conditions)}"
        )
    ability = ability_conditions[0]
    light = light_conditions[0]
    if len(ability) != 4 or len(light) != 5:
        raise ValueError(f"{logical}: 抗性降低词条结构漂移")
    if _fixed_range(ability[1], "能力伤害抗性持续时间") != 1800:
        raise ValueError(f"{logical}: 能力伤害抗性持续时间漂移")
    if _fixed_range(light[1], "光属性抗性持续时间") != 1800:
        raise ValueError(f"{logical}: 光属性抗性持续时间漂移")
    return ability, light


def patch_skill_dsl(raw: bytes, logical: str) -> tuple[bytes, dict]:
    """将一档主动技能的两项抗性降低固定为15%。"""
    try:
        level = next(
            level
            for level, expected in SKILL_DSL_LOGICALS.items()
            if logical == expected
        )
    except StopIteration as error:
        raise ValueError(f"不是受支持的杰拉德主动技能路径: {logical}") from error

    tree = _decode_skill(raw, logical)
    before = copy.deepcopy(tree)
    ability, light = _skill_conditions(tree, logical)
    current = CURRENT_RESISTANCES[level]
    ability_value = _fixed_range(ability[2], "能力伤害抗性降低")
    light_value = _fixed_range(light[3], "光属性抗性降低")
    if not any(
        math.isclose(ability_value, accepted, rel_tol=0.0, abs_tol=1e-12)
        for accepted in (current["ability"], TARGET_RESISTANCE)
    ):
        raise ValueError(f"{logical}: 能力伤害抗性降低未审核: {ability_value}")
    if not any(
        math.isclose(light_value, accepted, rel_tol=0.0, abs_tol=1e-12)
        for accepted in (current["light"], TARGET_RESISTANCE)
    ):
        raise ValueError(f"{logical}: 光属性抗性降低未审核: {light_value}")

    _set_fixed_range(ability[2], TARGET_RESISTANCE)
    _set_fixed_range(light[3], TARGET_RESISTANCE)
    changed = tree != before
    output = _raw_deflate(wf_dsl.encode_amf3(tree)) if changed else raw

    readback = _decode_skill(output, logical)
    final_ability, final_light = _skill_conditions(readback, logical)
    if not math.isclose(
        _fixed_range(final_ability[2], "能力伤害抗性降低"),
        TARGET_RESISTANCE,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise AssertionError(f"{logical}: 能力伤害抗性降低回读不一致")
    if not math.isclose(
        _fixed_range(final_light[3], "光属性抗性降低"),
        TARGET_RESISTANCE,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise AssertionError(f"{logical}: 光属性抗性降低回读不一致")
    return output, {
        "character_id": CHARACTER_ID,
        "logical": logical,
        "skill_level": level,
        "ability_damage_resistance_down_percent": 15,
        "light_resistance_down_percent": 15,
        "duration_seconds": 30,
        "changed": changed,
    }


def patch_skill_dsls(
    payloads: Mapping[str, bytes],
) -> tuple[dict[str, bytes], dict[str, dict]]:
    missing = sorted(set(SKILL_DSL_LOGICALS.values()) - set(payloads))
    if missing:
        raise ValueError(f"缺少杰拉德主动技能payload: {missing}")
    output: dict[str, bytes] = {}
    report: dict[str, dict] = {}
    for level, logical in SKILL_DSL_LOGICALS.items():
        output[logical], report[f"skill_lv{level}"] = patch_skill_dsl(
            payloads[logical], logical
        )
    return output, report


def patch_ability_table(raw: bytes) -> tuple[bytes, dict]:
    """只修改杰拉德能力2～5，保留整表其他键的原始字节。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, ABILITY_LOGICAL)
    if len(table.keys) != len(set(table.keys)):
        raise ValueError("ability.orderedmap存在重复键")
    missing = sorted(set(ABILITY_EDITS) - set(table.keys))
    if missing:
        raise ValueError(f"ability.orderedmap缺少杰拉德能力键: {missing}")

    before_outer = list(table.rows)
    details: list[dict] = []
    for key, edits in ABILITY_EDITS.items():
        position = table.keys.index(key)
        try:
            rows = core.read_csv_lines(
                zlib.decompress(table.rows[position]).decode("utf-8")
            )
        except Exception as error:
            raise ValueError(f"ability.orderedmap#{key}: 无法解码CSV") from error
        if len(rows) != _EXPECTED_ROW_COUNTS[key]:
            raise ValueError(
                f"ability.orderedmap#{key}: 行数漂移 "
                f"{len(rows)} != {_EXPECTED_ROW_COUNTS[key]}"
            )
        if any(len(row) != _ABILITY_ROW_WIDTH for row in rows):
            raise ValueError(f"ability.orderedmap#{key}: 列数漂移")
        if [row[0] for row in rows] != _EXPECTED_STRING_IDS[key]:
            raise ValueError(f"ability.orderedmap#{key}: string_id漂移")

        changed_key = False
        for line, column, current, target, label in edits:
            value = rows[line - 1][column]
            if value not in (current, target):
                raise ValueError(
                    f"ability.orderedmap#{key} line{line} c{column} "
                    f"{label}未审核: {value!r}"
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
            table.rows[position] = zlib.compress(
                core.write_csv_lines(rows).encode("utf-8")
            )

    if table.rows == before_outer:
        return raw, {
            "character_id": CHARACTER_ID,
            "logical": ABILITY_LOGICAL,
            "edits": details,
            "changed": False,
        }

    output = core.build_orderedmap_raw_rows(table)
    readback = core.read_orderedmap_raw_rows_from_bytes(output, ABILITY_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("ability.orderedmap键顺序漂移")
    target_keys = set(ABILITY_EDITS)
    for index, (before, after) in enumerate(zip(before_outer, readback.rows)):
        if table.keys[index] not in target_keys and before != after:
            raise AssertionError(f"非杰拉德能力被改动: {table.keys[index]}")
    return output, {
        "character_id": CHARACTER_ID,
        "logical": ABILITY_LOGICAL,
        "edits": details,
        "changed": True,
    }


__all__ = [
    "ABILITY_EDITS",
    "ABILITY_LOGICAL",
    "CHARACTER_ID",
    "CHARACTER_NAME",
    "CURRENT_RESISTANCES",
    "SKILL_DSL_LOGICALS",
    "TARGET_RESISTANCE",
    "patch_ability_table",
    "patch_skill_dsl",
    "patch_skill_dsls",
]
