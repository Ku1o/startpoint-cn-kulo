"""玛格诺斯（119996）能力3与能力6的本地平衡规则。

本模块只转换调用方传入的 ``ability.orderedmap`` 字节，不写 CDN、
不生成补丁包，也不接触运行镜像。调整范围严格限定为：

* 能力3的冲刺与强化弹射全体追击由10倍降为5倍；
* 能力3的FEVER攻击力／能力伤害加成由火属性全队改为自身；
* 能力6的自身技能发动全体追击由50倍降为30倍。
"""

from __future__ import annotations

from collections.abc import Mapping
import zlib

import wf_mod_tool as core


CHARACTER_ID = "119996"
CHARACTER_NAME = "玛格诺斯"
ABILITY_LOGICAL = core.ABILITY_LOGICAL

# (行号, 列号, 原值, 目标值, 说明)
# ability 表：瞬发伤害倍率位于 c51/c52；持续效果种类、目标、角色组
# 分别位于 c109/c110/c111。
ABILITY_EDITS: Mapping[str, tuple[tuple[int, int, str, str, str], ...]] = {
    "1199963": (
        (4, 110, "5", "0", "FEVER期间能力伤害加成目标·火属性全队→自身"),
        (4, 111, "Red", "", "FEVER期间能力伤害加成目标组·清除火属性限制"),
        (5, 110, "5", "0", "FEVER期间攻击力加成目标·火属性全队→自身"),
        (5, 111, "Red", "", "FEVER期间攻击力加成目标组·清除火属性限制"),
        (6, 51, "1000000", "500000", "FEVER冲刺全体能力伤害·10倍→5倍"),
        (6, 52, "1000000", "500000", "FEVER冲刺全体能力伤害·10倍→5倍"),
        (7, 51, "1000000", "500000", "永恒之火强化弹射全体能力伤害·10倍→5倍"),
        (7, 52, "1000000", "500000", "永恒之火强化弹射全体能力伤害·10倍→5倍"),
    ),
    "1199966": (
        (1, 51, "5000000", "3000000", "自身技能发动全体能力伤害·50倍→30倍"),
        (1, 52, "5000000", "3000000", "自身技能发动全体能力伤害·50倍→30倍"),
    ),
}

_EXPECTED_ROW_COUNTS = {"1199963": 7, "1199966": 4}
_EXPECTED_STRING_IDS = {
    "1199963": "lion_swordman_reborn_3",
    "1199966": "lion_swordman_reborn_6",
}
_ABILITY_ROW_WIDTH = 126


def patch_ability_table(raw: bytes) -> tuple[bytes, dict]:
    """只修改玛格诺斯能力3、6，保留整表其他键的原始字节。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, ABILITY_LOGICAL)
    if len(table.keys) != len(set(table.keys)):
        raise ValueError("ability.orderedmap 存在重复键")
    missing = sorted(set(ABILITY_EDITS) - set(table.keys))
    if missing:
        raise ValueError(f"ability.orderedmap 缺少玛格诺斯能力键: {missing}")

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
        if any(row[0] != _EXPECTED_STRING_IDS[key] for row in rows):
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
        raise AssertionError("ability.orderedmap 键顺序漂移")
    target_keys = set(ABILITY_EDITS)
    for index, (before, after) in enumerate(zip(before_outer, readback.rows)):
        if table.keys[index] not in target_keys and before != after:
            raise AssertionError(f"非玛格诺斯能力被改动: {table.keys[index]}")

    for key, edits in ABILITY_EDITS.items():
        position = readback.keys.index(key)
        rows = core.read_csv_lines(
            zlib.decompress(readback.rows[position]).decode("utf-8")
        )
        for line, column, _current, target, label in edits:
            if rows[line - 1][column] != target:
                raise AssertionError(
                    f"ability.orderedmap#{key} line{line} c{column} "
                    f"{label}回读不一致"
                )

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
    "patch_ability_table",
]
