"""深渊连战第3、4关原生地形回退规则。

只修改 ``field_data`` 中两个 ``mod_rogue`` 行的场景与地形路径，保留各自
克隆后的 zone ID、Boss、等级、HP、诅咒和排行榜结算配置。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import zlib

import wf_mod_tool as core


FIELD_DATA_LOGICAL = "master/battle/field_data.orderedmap"

FIELD_FIXES = {
    "mod_rogue_f3": {
        "before": (
            "water_sphere",
            "battle/terrain/event_quest/time_attack_event/water_sphere",
            "mod_rogue_z3",
        ),
        "after": (
            "tree_worldtree",
            "battle/terrain/event_quest/challenge_dungeon_event/chapter_boss/treant_single",
            "mod_rogue_z3",
        ),
        "source_field": "treant_single",
        "required_positions": ("p0",),
    },
    "mod_rogue_f4": {
        "before": (
            "light_dragon_area",
            "battle/terrain/event_quest/tower_dungeon/area_10_08/tower_dungeon_area_10_8_3",
            "mod_rogue_z4",
        ),
        "after": (
            "sea_ruins_around_boss",
            "battle/terrain/event_quest/challenge_dungeon_event/another_boss/hermit_crab_another_light_single",
            "mod_rogue_z4",
        ),
        "source_field": "hermit_crab_another_light_single",
        "required_positions": ("p0", "p1", "p2"),
    },
}


def _decode_row(raw: bytes, key: str) -> list[str]:
    try:
        text = zlib.decompress(raw).decode("utf-8")
    except (zlib.error, UnicodeDecodeError) as exc:
        raise ValueError(f"{FIELD_DATA_LOGICAL}:{key} 行无法解码") from exc
    rows = core.read_csv_lines(text)
    if len(rows) != 1 or len(rows[0]) != 3:
        raise ValueError(f"{FIELD_DATA_LOGICAL}:{key} 行形状漂移")
    return list(rows[0])


def _encode_row(row: list[str]) -> bytes:
    return zlib.compress(core.write_csv_lines([row]).encode("utf-8"))


def patch_field_data(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    table = core.read_orderedmap_raw_rows_from_bytes(raw, FIELD_DATA_LOGICAL)
    if len(table.keys) != len(table.rows):
        raise ValueError("field_data 键值数量不一致")
    indexes = {key: index for index, key in enumerate(table.keys)}
    missing = sorted(set(FIELD_FIXES) - set(indexes))
    if missing:
        raise ValueError(f"field_data 缺少深渊目标行: {missing}")

    output_rows = list(table.rows)
    reports = []
    changed = False
    for key, spec in FIELD_FIXES.items():
        index = indexes[key]
        row = _decode_row(output_rows[index], key)
        before = list(spec["before"])
        after = list(spec["after"])
        if row not in (before, after):
            raise ValueError(f"{FIELD_DATA_LOGICAL}:{key} 出现未审核内容: {row!r}")
        if row != after:
            output_rows[index] = _encode_row(after)
            changed = True
        reports.append({
            "field": key,
            "source_field": spec["source_field"],
            "before": before,
            "after": after,
            "required_positions": list(spec["required_positions"]),
        })

    if not changed:
        return raw, {"logical": FIELD_DATA_LOGICAL, "fields": reports, "changed": False}

    output = core.build_orderedmap_raw_rows(core.OrderedMap(
        FIELD_DATA_LOGICAL,
        list(table.keys),
        output_rows,
        Path("<abyss-custom-position-fix>"),
    ))
    readback = core.read_orderedmap_raw_rows_from_bytes(output, FIELD_DATA_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("field_data 键顺序发生变化")
    for key, before_raw, after_raw in zip(table.keys, table.rows, readback.rows):
        if key not in FIELD_FIXES and after_raw != before_raw:
            raise AssertionError(f"field_data 非目标行被改动: {key}")
        if key in FIELD_FIXES:
            row = _decode_row(after_raw, key)
            if row != list(FIELD_FIXES[key]["after"]):
                raise AssertionError(f"field_data 目标行回读失败: {key}")
    return output, {"logical": FIELD_DATA_LOGICAL, "fields": reports, "changed": True}


__all__ = ["FIELD_DATA_LOGICAL", "FIELD_FIXES", "patch_field_data"]
