"""巴萨拉卡（169997）文案修正与队长技回槽删除规则。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import zlib

import wf_mod_tool as core


CHARACTER_ID = "169997"
CHARACTER_NAME = "巴萨拉卡"
LEADER_ABILITY_LOGICAL = "master/ability/leader_ability.orderedmap"

SKILL_DESCRIPTION = (
    "挥舞大镰，对前方巨大扇形范围内的敌人造成20倍暗属性伤害。"
    "1秒后展开16秒「血月」：每1秒产生一次自身周围1倍伤害判定与一次全场1倍伤害判定"
    "（近身敌人可同时受到两段）；命中敌人时赋予1级「古洛诺斯伤痕」，"
    "全场判定还会赋予持续16秒的流血（强度3000）、防御力降低10%与暗属性抗性降低15%，"
    "并使自身获得1级「古洛诺斯伤痕」（最多10级）。自身进入16秒「超负荷」，"
    "获得能力伤害提升400%（20秒）与无敌（5秒）。"
)
SKILL_DESCRIPTION_FIELDS = {
    "skill_desc": SKILL_DESCRIPTION,
    "skill_plus_desc": SKILL_DESCRIPTION,
    "skill_plusplus_desc": SKILL_DESCRIPTION,
}

# 只用非默认字段锁定“自身发动技能时，自身技能槽＋30%”这一行。
# 这样即使前方能力增删导致行号变化，也不会误删相邻效果。
_REFUND_NONDEFAULT = [
    (0, "vaseraga_dark"),
    (25, "23"),
    (28, "100000"),
    (29, "100000"),
    (45, "211"),
    (49, "30000"),
    (50, "30000"),
]
_DEFAULT_VALUES = {"", "0", "(None)", "false", "true"}


def _nondefault(row: list[str]) -> list[tuple[int, str]]:
    return [(index, value) for index, value in enumerate(row) if value not in _DEFAULT_VALUES]


def refund_line_number(rows: list[list[str]]) -> int | None:
    """返回应删除的1起行号；已删除时返回None，未知漂移则拒绝。"""
    if len(rows) not in (12, 13):
        raise ValueError(f"169997队长技行数漂移: {len(rows)}，预期12或13")
    if any(len(row) != 124 for row in rows):
        raise ValueError("169997队长技列数漂移")
    if any(row[0] != "vaseraga_dark" for row in rows):
        raise ValueError("169997队长技string_id漂移")
    matches = [
        index
        for index, row in enumerate(rows, start=1)
        if _nondefault(row) == _REFUND_NONDEFAULT
    ]
    if len(matches) > 1:
        raise ValueError(f"169997队长技回槽行重复: {matches}")
    if len(rows) == 13:
        if matches != [8]:
            raise ValueError(f"169997队长技第8行出现未审核漂移: 命中{matches}")
        return 8
    if matches:
        raise ValueError(f"169997队长技已是12行但仍有回槽行: {matches}")
    return None


def patch_leader_ability_rows(
    rows: list[list[str]],
) -> tuple[list[list[str]], dict[str, Any]]:
    line = refund_line_number(rows)
    if line is None:
        return [list(row) for row in rows], {
            "character_id": CHARACTER_ID,
            "removed": "自身发动技能时，自身技能槽＋30%",
            "removed_line": None,
            "changed": False,
        }
    output = [list(row) for row in rows]
    output.pop(line - 1)
    if refund_line_number(output) is not None:
        raise AssertionError("169997队长技回槽行删除后仍然存在")
    return output, {
        "character_id": CHARACTER_ID,
        "removed": "自身发动技能时，自身技能槽＋30%",
        "removed_line": line,
        "changed": True,
    }


def patch_leader_ability_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """只改 leader_ability#169997，逐字节保留其他角色队长技。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, LEADER_ABILITY_LOGICAL)
    try:
        position = table.keys.index(CHARACTER_ID)
    except ValueError as error:
        raise ValueError("leader_ability.orderedmap缺少169997") from error
    before = list(table.rows)
    rows = core.read_csv_lines(zlib.decompress(table.rows[position]).decode("utf-8"))
    patched, report = patch_leader_ability_rows(rows)
    if not report["changed"]:
        return raw, report
    table.rows[position] = zlib.compress(core.write_csv_lines(patched).encode("utf-8"))
    output = core.build_orderedmap_raw_rows(table)
    readback = core.read_orderedmap_raw_rows_from_bytes(output, LEADER_ABILITY_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("leader_ability.orderedmap键顺序漂移")
    for index, (old, new) in enumerate(zip(before, readback.rows)):
        if index != position and old != new:
            raise AssertionError(f"非巴萨拉卡队长技被改动: {table.keys[index]}")
    final_rows = core.read_csv_lines(
        zlib.decompress(readback.rows[position]).decode("utf-8")
    )
    if refund_line_number(final_rows) is not None:
        raise AssertionError("leader_ability#169997回读仍含技能回槽行")
    return output, report


__all__ = [
    "CHARACTER_ID",
    "CHARACTER_NAME",
    "LEADER_ABILITY_LOGICAL",
    "SKILL_DESCRIPTION",
    "SKILL_DESCRIPTION_FIELDS",
    "patch_leader_ability_rows",
    "patch_leader_ability_table",
    "refund_line_number",
]
