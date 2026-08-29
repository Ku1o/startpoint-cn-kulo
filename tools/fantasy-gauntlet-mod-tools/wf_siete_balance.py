"""希耶提（149995）主动技能的源级平衡规则。

本模块只修改调用方提供的主动技能表、角色文案表或 Action DSL 字节，
不写 CDN、不生成版本边，也不打包 ZIP。后续整合发布器应显式调用这里的
补丁函数，并把两个技能形态与两张文案表放进同一版本。
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping
import zlib

import wf_dsl
import wf_mod_tool as core


CHARACTER_ID = "149995"
CHARACTER_NAME = "希耶提"
ACTION_SKILL_KEY = "seofon_wind"
ACTION_SKILL_LOGICAL = "master/skill/action_skill.orderedmap"
CHARACTER_TEXT_LOGICAL = "master/character/character_text.orderedmap"
SKILL_DSL_LOGICALS = {
    level: (
        "battle/action/skill/action/rare5/seofon_wind$"
        f"seofon_wind_{level}.action.dsl.amf3.deflate"
    )
    for level in (1, 2)
}

OLD_SKILL_DESCRIPTION = (
    "剑神双奏：无剑神时，原地召唤剑神——全体队员获得15%护盾，自身获得"
    "「剑神」并加速10秒；持有剑神时，剑神化身齐射突进，并向前方推出十二把"
    "灵剑，剑刃倍率随剑神层数成长（1/3/6/9/12层时每刃"
    "25/35/50/70/90倍），并消耗1层剑神。"
)
SKILL_DESCRIPTION = (
    "剑神双奏：无「剑神」时，原地召唤剑神——全体队员获得15%护盾，自身获得"
    "1级「剑神」与30%加速（10秒）；持有N级「剑神」时，剑神化身突进攻击1段，"
    "并向前方推出N把灵剑（每把攻击1段），共N+1段，随后消耗1级「剑神」。"
    "每段倍率：1～7级25倍，8～10级40倍，11～12级55倍。"
)

TARGET_MULTIPLIER_BY_LAYER = {
    **{layer: 25.0 for layer in range(1, 8)},
    **{layer: 40.0 for layer in range(8, 11)},
    **{layer: 55.0 for layer in range(11, 13)},
}
CURRENT_MULTIPLIER_BY_LEVEL = {
    1: {
        1: 25.0,
        2: 25.0,
        3: 35.0,
        4: 35.0,
        5: 35.0,
        6: 50.0,
        7: 50.0,
        8: 50.0,
        9: 70.0,
        10: 70.0,
        11: 70.0,
        12: 90.0,
    },
    2: {
        1: 30.0,
        2: 30.0,
        3: 40.0,
        4: 40.0,
        5: 40.0,
        6: 55.0,
        7: 55.0,
        8: 55.0,
        9: 75.0,
        10: 75.0,
        11: 75.0,
        12: 90.0,
    },
}


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _decode_payload(raw: bytes, logical: str) -> Any:
    try:
        return wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
    except Exception as error:
        raise ValueError(f"无法解析希耶提主动技能 DSL: {logical}: {error}") from error


def _encode_payload(tree: Any) -> bytes:
    encoded = wf_dsl.encode_amf3(tree)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(encoded) + compressor.flush()


def _read_attack_multiplier(node: list[Any], logical: str) -> float:
    if len(node) <= 6 or node[0] != "CreateNormalAttack":
        raise ValueError(f"攻击节点形状异常: {logical}: {node!r}")
    ranges = node[6]
    if (
        not isinstance(ranges, list)
        or len(ranges) != 1
        or not isinstance(ranges[0], dict)
        or "min" not in ranges[0]
        or "max" not in ranges[0]
    ):
        raise ValueError(f"攻击倍率字段形状异常: {logical}: {ranges!r}")
    minimum = float(ranges[0]["min"])
    maximum = float(ranges[0]["max"])
    if not math.isclose(minimum, maximum, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"攻击倍率不是固定值: {logical}: {minimum}/{maximum}")
    return minimum


def _write_attack_multiplier(node: list[Any], value: float) -> None:
    node[6][0]["min"] = value
    node[6][0]["max"] = value


def _layer_attacks(tree: Any, logical: str) -> dict[int, list[list[Any]]]:
    branches: dict[int, list[list[Any]]] = {}
    for node in _walk(tree):
        if not isinstance(node, list) or not node:
            continue
        if node[0] != "ConditionalsConditionAccumulationNumber":
            continue
        if len(node) < 4 or node[1] != ["DCUnique", int(CHARACTER_ID)]:
            continue
        layer = int(node[2])
        if layer in branches:
            raise ValueError(f"{logical}: 剑神{layer}级条件重复")
        attacks = [
            child
            for child in _walk(node[3])
            if isinstance(child, list) and child and child[0] == "CreateNormalAttack"
        ]
        branches[layer] = attacks

    if set(branches) != set(range(1, 13)):
        raise ValueError(
            f"{logical}: 剑神层级条件漂移: {sorted(branches)} != 1～12"
        )

    all_attacks = [
        node
        for node in _walk(tree)
        if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
    ]
    branch_attacks = [attack for attacks in branches.values() for attack in attacks]
    if {id(node) for node in branch_attacks} != {id(node) for node in all_attacks}:
        raise ValueError(f"{logical}: 存在未归属剑神层级的攻击节点")

    for layer, attacks in branches.items():
        expected_hits = layer + 1
        if len(attacks) != expected_hits:
            raise ValueError(
                f"{logical}: 剑神{layer}级命中段数漂移: "
                f"{len(attacks)} != {expected_hits}"
            )
    return branches


def patch_skill_dsl(raw: bytes, logical: str) -> tuple[bytes, dict[str, Any]]:
    """按剑神层级修改一个希耶提主动技能形态的每段倍率。"""
    try:
        level = next(
            level
            for level, expected_logical in SKILL_DSL_LOGICALS.items()
            if logical == expected_logical
        )
    except StopIteration as error:
        raise ValueError(f"不是受支持的希耶提主动技能路径: {logical}") from error

    tree = _decode_payload(raw, logical)
    if not isinstance(tree, list) or len(tree) < 12 or tree[0] != "ActionDsl":
        raise ValueError(f"{logical}: ActionDsl 根节点形状异常")
    if tree[10] != 0:
        raise ValueError(f"{logical}: buffTargetAs 已漂移，拒绝误改伤害类型")

    branches = _layer_attacks(tree, logical)
    report_layers: dict[str, dict[str, Any]] = {}
    changed = False
    for layer in range(1, 13):
        attacks = branches[layer]
        before_values = [_read_attack_multiplier(node, logical) for node in attacks]
        if any(
            not math.isclose(value, before_values[0], rel_tol=0.0, abs_tol=1e-12)
            for value in before_values[1:]
        ):
            raise ValueError(f"{logical}: 剑神{layer}级各段倍率不一致")
        accepted = {
            CURRENT_MULTIPLIER_BY_LEVEL[level][layer],
            TARGET_MULTIPLIER_BY_LAYER[layer],
        }
        if not any(
            math.isclose(before_values[0], value, rel_tol=0.0, abs_tol=1e-12)
            for value in accepted
        ):
            raise ValueError(
                f"{logical}: 剑神{layer}级当前每段倍率{before_values[0]:g}"
                f"不在允许前值{sorted(accepted)}中"
            )

        target = TARGET_MULTIPLIER_BY_LAYER[layer]
        for attack in attacks:
            if not math.isclose(
                _read_attack_multiplier(attack, logical),
                target,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                _write_attack_multiplier(attack, target)
                changed = True
        report_layers[str(layer)] = {
            "sword_avatar_hits": 1,
            "spirit_sword_hits": layer,
            "total_hits": layer + 1,
            "before_per_hit": before_values[0],
            "after_per_hit": target,
            "after_total": (layer + 1) * target,
        }

    output = _encode_payload(tree) if changed else raw
    return output, {
        "character_id": CHARACTER_ID,
        "skill_level": level,
        "logical": logical,
        "damage_type": "skill",
        "hit_rule": "剑神化身1段＋N把灵剑各1段＝N+1段",
        "layers": report_layers,
        "changed": changed,
    }


def patch_skill_dsls(
    payloads: Mapping[str, bytes],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """同时处理两个主动技能形态，缺少任一路径即拒绝。"""
    missing = sorted(set(SKILL_DSL_LOGICALS.values()) - set(payloads))
    if missing:
        raise ValueError(f"缺少希耶提主动技能 payload: {missing}")
    output: dict[str, bytes] = {}
    report: dict[str, Any] = {}
    for level, logical in SKILL_DSL_LOGICALS.items():
        patched, detail = patch_skill_dsl(payloads[logical], logical)
        output[logical] = patched
        report[f"skill_lv{level}"] = detail
    return output, report


def patch_action_skill_entries(
    entries: list[tuple[str, list[str]]],
) -> tuple[list[tuple[str, list[str]]], dict[str, Any]]:
    """同步两个主动技能形态的客户端说明。"""
    if [key for key, _row in entries] != ["1", "2"]:
        raise ValueError("149995 主动技能形态集合漂移")
    output: list[tuple[str, list[str]]] = []
    for level, row in entries:
        patched = list(row)
        if len(patched) != 24:
            raise ValueError(f"149995 主动技能{level}列数漂移: {len(patched)} != 24")
        expected_program = (
            "battle/action/skill/action/rare5/seofon_wind$"
            f"seofon_wind_{level}"
        )
        if patched[core.ACTION_SKILL_COLUMNS["program_path"]] != expected_program:
            raise ValueError(f"149995 主动技能{level}程序路径漂移")
        description_column = core.ACTION_SKILL_COLUMNS["description"]
        if patched[description_column] not in (
            OLD_SKILL_DESCRIPTION,
            SKILL_DESCRIPTION,
        ):
            raise ValueError(f"149995 主动技能{level}文案出现未审核内容")
        patched[description_column] = SKILL_DESCRIPTION
        output.append((level, patched))
    return output, {
        "character_id": CHARACTER_ID,
        "description": SKILL_DESCRIPTION,
        "describes_layer_hit_link": True,
        "describes_new_multiplier_tiers": True,
    }


def patch_action_skill_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """只替换 ``action_skill#seofon_wind`` 的主动技能说明。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, ACTION_SKILL_LOGICAL)
    try:
        index = table.keys.index(ACTION_SKILL_KEY)
    except ValueError as error:
        raise ValueError("action_skill.orderedmap 缺少 seofon_wind") from error
    before_rows = list(table.rows)
    patched, report = patch_action_skill_entries(
        core.decode_action_skill_row(table.rows[index])
    )
    replacement = core.encode_action_skill_row(patched)
    if replacement == table.rows[index]:
        report["changed"] = False
        return raw, report
    table.rows[index] = replacement
    output = core.build_orderedmap_raw_rows(table)

    readback = core.read_orderedmap_raw_rows_from_bytes(output, ACTION_SKILL_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("action_skill.orderedmap 键顺序漂移")
    for position, (before, after) in enumerate(zip(before_rows, readback.rows)):
        if position != index and before != after:
            raise AssertionError(f"非目标主动技能被改动: {table.keys[position]}")
    descriptions = [
        row[core.ACTION_SKILL_COLUMNS["description"]]
        for _level, row in core.decode_action_skill_row(readback.rows[index])
    ]
    if descriptions != [SKILL_DESCRIPTION, SKILL_DESCRIPTION]:
        raise AssertionError("149995 主动技能说明回读不一致")
    report["changed"] = True
    return output, report


def patch_character_text_rows(
    rows: list[list[str]],
) -> tuple[list[list[str]], dict[str, Any]]:
    """同步 ``character_text#149995`` 重复保存的三档主动技能说明。"""
    if len(rows) != 1 or len(rows[0]) != 12:
        raise ValueError("149995 character_text 行列形状漂移")
    row = list(rows[0])
    if row[0] != CHARACTER_NAME:
        raise ValueError(f"149995 character_text 角色名漂移: {row[0]!r}")
    for column in (5, 7, 9):
        if row[column] not in (OLD_SKILL_DESCRIPTION, SKILL_DESCRIPTION):
            raise ValueError(f"149995 character_text c{column}出现未审核文案")
        row[column] = SKILL_DESCRIPTION
    return [row], {"character_id": CHARACTER_ID, "description": SKILL_DESCRIPTION}


def patch_character_text_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """只替换 ``character_text#149995`` 的三档主动技能说明。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, CHARACTER_TEXT_LOGICAL)
    try:
        index = table.keys.index(CHARACTER_ID)
    except ValueError as error:
        raise ValueError("character_text.orderedmap 缺少 149995") from error
    before_rows = list(table.rows)
    text = zlib.decompress(table.rows[index]).decode("utf-8")
    patched, report = patch_character_text_rows(core.read_csv_lines(text))
    replacement = zlib.compress(core.write_csv_lines(patched).encode("utf-8"))
    if replacement == table.rows[index]:
        report["changed"] = False
        return raw, report
    table.rows[index] = replacement
    output = core.build_orderedmap_raw_rows(table)

    readback = core.read_orderedmap_raw_rows_from_bytes(output, CHARACTER_TEXT_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("character_text.orderedmap 键顺序漂移")
    for position, (before, after) in enumerate(zip(before_rows, readback.rows)):
        if position != index and before != after:
            raise AssertionError(f"非目标角色文案被改动: {table.keys[position]}")
    final_rows = core.read_csv_lines(
        zlib.decompress(readback.rows[index]).decode("utf-8")
    )
    if [final_rows[0][column] for column in (5, 7, 9)] != [
        SKILL_DESCRIPTION
    ] * 3:
        raise AssertionError("149995 character_text 主动技能说明回读不一致")
    report["changed"] = True
    return output, report


def patch_server_character_text_document(
    document: dict[str, list[list[str]]],
) -> tuple[dict[str, list[list[str]]], dict[str, Any]]:
    """同步服务端 ``assets/cdndata/character_text.json`` 中的149995行。"""
    try:
        current_rows = document[CHARACTER_ID]
    except KeyError as error:
        raise ValueError("服务端 character_text.json 缺少 149995") from error
    patched_rows, report = patch_character_text_rows(current_rows)
    output = dict(document)
    output[CHARACTER_ID] = patched_rows
    report["changed"] = patched_rows != current_rows
    return output, report


__all__ = [
    "ACTION_SKILL_KEY",
    "ACTION_SKILL_LOGICAL",
    "CHARACTER_ID",
    "CHARACTER_NAME",
    "CHARACTER_TEXT_LOGICAL",
    "CURRENT_MULTIPLIER_BY_LEVEL",
    "OLD_SKILL_DESCRIPTION",
    "SKILL_DESCRIPTION",
    "SKILL_DSL_LOGICALS",
    "TARGET_MULTIPLIER_BY_LAYER",
    "patch_action_skill_entries",
    "patch_action_skill_table",
    "patch_character_text_rows",
    "patch_character_text_table",
    "patch_server_character_text_document",
    "patch_skill_dsl",
    "patch_skill_dsls",
]
