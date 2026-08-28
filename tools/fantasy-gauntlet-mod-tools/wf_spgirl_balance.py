"""泳装希尔媞（149996）已确认的源级平衡规则。

本模块只改调用方提供的角色主表或 Action DSL 字节，不写 CDN、不生成版本边，
也不打包 ZIP。后续整合发布器应显式调用这里的补丁函数。
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any
import zlib

import wf_mod_tool as core
import wf_dsl


ABILITY_LOGICAL = "master/ability/ability.orderedmap"
ABILITY1_KEY = "1499961"
ABILITY1_STRING_ID = "wind_spgirl_swim_1"
ABILITY2_KEY = "1499962"
ABILITY2_STRING_ID = "wind_spgirl_swim_2"
ABILITY3_KEY = "1499963"
ABILITY3_STRING_ID = "wind_spgirl_swim_3"
ABILITY6_KEY = "1499966"
ABILITY6_STRING_ID = "wind_spgirl_swim_6"

LEADER_ABILITY_LOGICAL = "master/ability/leader_ability.orderedmap"
LEADER_ABILITY_KEY = "149996"
LEADER_ABILITY_STRING_ID = "wind_spgirl_swim_leader"

ACTION_SKILL_LOGICAL = "master/skill/action_skill.orderedmap"
CHARACTER_TEXT_LOGICAL = "master/character/character_text.orderedmap"
CUSTOM_ABILITY_STRING_LOGICAL = "master/string/custom_ability_string.orderedmap"
ACTION_SKILL_KEY = "wind_spgirl_swim"
CHARACTER_TEXT_KEY = "149996"
SKILL_DSL_LOGICALS = {
    level: (
        "battle/action/skill/action/rare5/wind_spgirl_swim$"
        f"wind_spgirl_swim_{level}.action.dsl.amf3.deflate"
    )
    for level in (1, 2, 3)
}

OLD_SKILL_DESCRIPTION = (
    "向距离最近的敌人使出肉眼无法看清的闪击，对接触到的敌人造成风属性伤害／"
    "连击数 +77／赋予自身「连击」（直接攻击变为 4 次）／赋予自身贯通、"
    "最大速度固定与冲刺间隔缩短"
)
SKILL_DESCRIPTION = (
    "以肉眼无法看清的闪击对前方和后方的敌方造成风属性伤害"
    "【根据连击数提升伤害】／赋予自身贯通、最大速度固定。"
)
PIERCING_DURATION_FRAMES = 720
COMBO_SCALING_PREVIOUS_RAW = 5  # Action DSL原始单位：0.1%/点，即5=0.5%。
COMBO_SCALING_TARGET_RAW = 7  # 7=每1连击提升0.7%。
COMBO_SCALING_PER_COMBO_PERCENT = 0.7

COMBO_STEP = 77
COMBO_RESET = 777
MAX_LAYERS = 10
LAYER_STRENGTH = 20_000  # 20%，千分比单位。

LEADER_TRIGGER_LIMIT = 101
LEADER_SELF_STRENGTH = 12_500  # 12.5%，千分比单位。
LEADER_WIND_MEMBER_COUNT = 6
LEADER_GAUGE_COMBO = 777
LEADER_GAUGE_CHARGE = 150_000  # +150%。
LEADER_GAUGE_MAX = 50_000  # 最大值+50%，即技能槽上限由100%变为150%。
LEADER_PF3_GAUGE_CHARGE = 77_000  # 风共鸣时，每次发动强化弹射3，风角色技能槽+77%。

ABILITY_GAUGE_STRENGTH = 5_000  # A1/A6每层+5%。
ABILITY_TRIGGER_LIMIT = 101

XIWEI_CHARACTER_ID = "141063"
XIWEI_ACTION_SKILL_KEY = "bigwing_shaman_smr21"
XIWEI_ACTION_SKILL_LEVEL = "2"  # 满强化形态“风怒龙卷＋”。
XIWEI_SOURCE_ACTION_PATH = (
    "battle/action/skill/action/rare5/bigwing_shaman_smr21$"
    "bigwing_shaman_smr21_2"
)
XIWEI_SKILL_DSL_LOGICAL = f"{XIWEI_SOURCE_ACTION_PATH}.action.dsl.amf3.deflate"
XIWEI_INVOKE_STRING_ID = "ability_skill_wind_spgirl_swim_whirlwind"
XIWEI_INVOKE_DESCRIPTION = "额外发动「旋风」"
XIWEI_INVOKE_COOLDOWN_FRAMES = 60
XIWEI_INVOKE_COOLDOWN_SECONDS = 1
XIWEI_ACTION_PATH = (
    "battle/action/skill/action/ability_skill/"
    "ability_skill_wind_spgirl_swim_whirlwind$"
    "ability_skill_wind_spgirl_swim_whirlwind"
)
XIWEI_ABILITY_SKILL_DSL_LOGICAL = f"{XIWEI_ACTION_PATH}.action.dsl.amf3.deflate"
XIWEI_SOURCE_DSL_SHA256 = (
    "5dadf28009ca42b2bcf500b6c2f8cdc19181fc2cfdd179d233556027c4eded1d"
)
XIWEI_SOURCE_DSL_BASE64 = (
    "jVNPaxNBFM/sTiZsSylSqpZCpXaL+Adi7aGgaEg2SRU0VVPBW5juTpIxszt1d2PTk+Qg"
    "Inr06DfwA1hU7MGrnvwEilVB8OAXiG92NqmVHpzNTt68fe83v9+bN9YMIlNFN+YyKEc"
    "CI8tExKrJgBl64IyVRWS8JKTbsXJILSYd6fs08KwJRI7UY7lZokLgwWDwC4+p9NXbLIp"
    "lyNZlfZMxr8SasNBbVHrM7SpDxWUrVY1OrElE5qs88GqMhvXuxj3mxpFGRHhJhZx1QkZ"
    "jds2nLR7QcHudhi0Wq5CBxsAwaaxZRKbrbblVaTYBhsx8f/li79Wbb2+f7z1+nUABK5c3"
    "t/X3Mg9hFtukP7VB41iwPEv8+ajDhWh0A36/y/IbvLXFg1YjalNQ3oj88MLSoc4GeDxgB"
    "PJOVUF2xD221nTaNKRuzEK1/6UD+1/nTRZznw154P7RpDbFEs6oxzBUjlWXPgP/2DjK+T"
    "zAZs6nPWymilcQmdX1ucrjIhjEPKM5zP0NMuHw0BUJDDqJ+3kb3uS8JxwWKHJgnkvWdZA"
    "FgZBzOSWbAh/GFqJWHCrcrgAC3p0Icm/QXq3rrzUhK8LHFaRhmMkfRvqwEMIGNrWdS2XA"
    "dKzeph3mUJ+FFKfuBUQWtbqaDH0qinFM3Q42cf8hwCgkrCVlC1+e/r67u/jMzhb27iQDp"
    "WIzNs6gpJ+HoZ91gD2y0PDL10wy7JGl7wS0JzNHHXZCM3Jk4HHVz1jJs8YROV101qUA+"
    "oELB18RzIfapiyenLfh3ee7+27n1s9Hczt2dvf9cjKGfJGN0b82WV5lAQu5O9oUyqubyD"
    "QIQkbCYZRhqINPaq5JTwNpdcWKQoxuGMbzuoT7P0iYKsuajNtwjvp8zP2LdTHhblmILBS"
    "dm3KLhVXBN8vQ/y12UOSomh/U+AjV/KGrOUnFgwb0cLaQatYO2ssWPv1HEa4cqvUP"
)

# 只用于把尚未发布的旧规则输出安全迁移到西微版，不会写入新终态。
_LEGACY_RAM_INVOKE_STRING_ID = "ability_skill_wind_spgirl_swim_ram"
_LEGACY_RAM_ACTION_PATH = "battle/action/skill/action/rare4/ram$ram_2"

INSTANT_COMBO_TRIGGER = "12"
INSTANT_SKILL_TRIGGER = "23"
INSTANT_POWER_FLIP_LV3_TRIGGER = "65"
DURING_COMBO_TRIGGER = "2"
INSTANT_SET_COMBO = "390"
INSTANT_ATTACK_POINT = "32"
INSTANT_DIRECT_DAMAGE = "33"
INSTANT_SKILL_GAUGE = "211"
INSTANT_SKILL_GAUGE_MAX = "245"
INSTANT_ADD_COMBO = "226"
INSTANT_CONDITION_DIRECT_ATTACK3 = "224"
INSTANT_CONDITION_SWIFT = "31"
INSTANT_INVOKE_SKILL = "629"
INSTANT_SEPARATED_DIRECT_DAMAGE = "693"
INSTANT_SEPARATED_SKILL_DAMAGE = "694"
DURING_SEPARATED_DIRECT_DAMAGE = "410"
DURING_SEPARATED_SKILL_DAMAGE = "411"

PRECONDITION_ALWAYS = "0"
PRECONDITION_MEMBER = "2"
INITIAL_TRIGGER = "0"
TARGET_SELF = "0"
TARGET_PARTY = "5"
WIND_GROUP = "Green"

_INSTANT_TO_DURING = {
    INSTANT_SEPARATED_DIRECT_DAMAGE: DURING_SEPARATED_DIRECT_DAMAGE,
    INSTANT_SEPARATED_SKILL_DAMAGE: DURING_SEPARATED_SKILL_DAMAGE,
}
_DURING_CONTENTS = frozenset(_INSTANT_TO_DURING.values())


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def patch_action_skill_entries(
    entries: list[tuple[str, list[str]]],
) -> tuple[list[tuple[str, list[str]]], dict[str, Any]]:
    """修正149996三档主动技文案，不重复描述能力6效果。"""
    if [key for key, _row in entries] != ["1", "2", "3"]:
        raise ValueError("149996 主动技形态集合漂移")

    output: list[tuple[str, list[str]]] = []
    for level, row in entries:
        patched = list(row)
        if len(patched) != 24:
            raise ValueError(f"149996 主动技{level}列数漂移: {len(patched)} != 24")
        expected_program = (
            "battle/action/skill/action/rare5/wind_spgirl_swim$"
            f"wind_spgirl_swim_{level}"
        )
        if patched[7] != expected_program:
            raise ValueError(f"149996 主动技{level}程序路径漂移: {patched[7]!r}")
        if patched[1] not in (OLD_SKILL_DESCRIPTION, SKILL_DESCRIPTION):
            raise ValueError(f"149996 主动技{level}文案出现未审核内容")
        patched[1] = SKILL_DESCRIPTION
        output.append((level, patched))
    return output, {
        "character_id": CHARACTER_TEXT_KEY,
        "description": SKILL_DESCRIPTION,
        "mentions_combo_scaling": True,
        "duplicates_ability6": False,
    }


def patch_action_skill_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """只替换 ``action_skill#wind_spgirl_swim`` 的三档文案。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, ACTION_SKILL_LOGICAL)
    if len(table.keys) != len(set(table.keys)):
        raise ValueError("action_skill.orderedmap 存在重复键")
    try:
        index = table.keys.index(ACTION_SKILL_KEY)
    except ValueError as error:
        raise ValueError("action_skill.orderedmap 缺少 wind_spgirl_swim") from error

    before_rows = list(table.rows)
    entries = core.decode_action_skill_row(table.rows[index])
    patched, report = patch_action_skill_entries(entries)
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
            raise AssertionError(f"非目标主动技被改动: {table.keys[position]}")
    descriptions = [row[1] for _key, row in core.decode_action_skill_row(readback.rows[index])]
    if descriptions != [SKILL_DESCRIPTION] * 3:
        raise AssertionError("149996 主动技文案回读不一致")
    report["changed"] = True
    return output, report


def patch_character_text_rows(rows: list[list[str]]) -> tuple[list[list[str]], dict[str, Any]]:
    """同步 ``character_text#149996`` 中重复保存的三档主动技文案。"""
    if len(rows) != 1 or len(rows[0]) != 12:
        raise ValueError("149996 character_text 行列形状漂移")
    row = list(rows[0])
    if row[0] != "希尔媞":
        raise ValueError(f"149996 character_text 角色名漂移: {row[0]!r}")
    for column in (5, 7, 9):
        if row[column] not in (OLD_SKILL_DESCRIPTION, SKILL_DESCRIPTION):
            raise ValueError(f"149996 character_text c{column}出现未审核文案")
        row[column] = SKILL_DESCRIPTION
    return [row], {"character_id": CHARACTER_TEXT_KEY, "description": SKILL_DESCRIPTION}


def patch_character_text_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """只替换 ``character_text#149996`` 的三档主动技文案。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, CHARACTER_TEXT_LOGICAL)
    if len(table.keys) != len(set(table.keys)):
        raise ValueError("character_text.orderedmap 存在重复键")
    try:
        index = table.keys.index(CHARACTER_TEXT_KEY)
    except ValueError as error:
        raise ValueError("character_text.orderedmap 缺少 149996") from error

    before_rows = list(table.rows)
    text = zlib.decompress(table.rows[index]).decode("utf-8")
    patched, report = patch_character_text_rows(core.read_csv_lines(text))
    replacement_text = core.write_csv_lines(patched)
    if replacement_text == text:
        report["changed"] = False
        return raw, report
    table.rows[index] = zlib.compress(replacement_text.encode("utf-8"))
    output = core.build_orderedmap_raw_rows(table)

    readback = core.read_orderedmap_raw_rows_from_bytes(output, CHARACTER_TEXT_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("character_text.orderedmap 键顺序漂移")
    for position, (before, after) in enumerate(zip(before_rows, readback.rows)):
        if position != index and before != after:
            raise AssertionError(f"非目标角色文案被改动: {table.keys[position]}")
    final_rows = core.read_csv_lines(zlib.decompress(readback.rows[index]).decode("utf-8"))
    if [final_rows[0][column] for column in (5, 7, 9)] != [SKILL_DESCRIPTION] * 3:
        raise AssertionError("149996 character_text 文案回读不一致")
    report["changed"] = True
    return output, report


def patch_custom_ability_string_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """注册A6的“旋风”专用文案键，避免角色详情页查键失败。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, CUSTOM_ABILITY_STRING_LOGICAL)
    if len(table.keys) != len(set(table.keys)):
        raise ValueError("custom_ability_string.orderedmap 存在重复键")

    if XIWEI_INVOKE_STRING_ID in table.keys:
        index = table.keys.index(XIWEI_INVOKE_STRING_ID)
        try:
            existing = zlib.decompress(table.rows[index]).decode("utf-8")
        except Exception as error:
            raise ValueError(
                f"无法解码旋风技能文案键 {XIWEI_INVOKE_STRING_ID}"
            ) from error
        if existing != XIWEI_INVOKE_DESCRIPTION:
            raise ValueError(
                f"旋风技能文案键出现未审核内容: "
                f"{existing!r} != {XIWEI_INVOKE_DESCRIPTION!r}"
            )
        return raw, {
            "string_id": XIWEI_INVOKE_STRING_ID,
            "description": XIWEI_INVOKE_DESCRIPTION,
            "changed": False,
        }

    before_keys = list(table.keys)
    before_rows = list(table.rows)
    table.keys.append(XIWEI_INVOKE_STRING_ID)
    table.rows.append(zlib.compress(XIWEI_INVOKE_DESCRIPTION.encode("utf-8")))
    output = core.build_orderedmap_raw_rows(table)

    readback = core.read_orderedmap_raw_rows_from_bytes(
        output, CUSTOM_ABILITY_STRING_LOGICAL
    )
    if readback.keys != [*before_keys, XIWEI_INVOKE_STRING_ID]:
        raise AssertionError("custom_ability_string.orderedmap 键顺序漂移")
    if readback.rows[:-1] != before_rows:
        raise AssertionError("非目标 custom_ability_string 文案被改动")
    if zlib.decompress(readback.rows[-1]).decode("utf-8") != XIWEI_INVOKE_DESCRIPTION:
        raise AssertionError("A6旋风技能文案回读不一致")
    return output, {
        "string_id": XIWEI_INVOKE_STRING_ID,
        "description": XIWEI_INVOKE_DESCRIPTION,
        "changed": True,
    }


def _decode_dsl(raw: bytes, logical: str) -> Any:
    try:
        return wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
    except Exception as error:
        raise ValueError(f"无法解析149996主动技 DSL: {logical}: {error}") from error


def _encode_dsl(tree: Any) -> bytes:
    encoded = wf_dsl.encode_amf3(tree)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(encoded) + compressor.flush()


def build_xiwei_ability_skill_dsl() -> tuple[bytes, dict[str, Any]]:
    """Build a native ability_skill wrapper from Xiwei's max active-skill body.

    Actor-control ``StopBall`` is deliberately removed because this body runs
    inside 149996's own active skill.  All skill-level and ability-level ranges
    are frozen to Xiwei's max values so ability 6 cannot reinterpret them.
    """
    source = base64.b64decode(XIWEI_SOURCE_DSL_BASE64, validate=True)
    if hashlib.sha256(source).hexdigest() != XIWEI_SOURCE_DSL_SHA256:
        raise ValueError("西微满强化主动技源 DSL 哈希漂移")
    tree = _decode_dsl(source, XIWEI_SKILL_DSL_LOGICAL)
    if (
        not isinstance(tree, list)
        or len(tree) != 12
        or tree[0] != "ActionDsl"
        or not isinstance(tree[11], list)
        or len(tree[11]) != 2
        or tree[11][0] != "Block"
        or not isinstance(tree[11][1], list)
    ):
        raise ValueError("西微满强化主动技根节点形状漂移")
    commands = tree[11][1]
    if [row[1][0] for row in commands] != ["StopBall", "FindNearSubjects", "FindAllSubjects"]:
        raise ValueError("西微满强化主动技顶层命令集合漂移")
    tree[11][1] = commands[1:]

    attacks = [
        node for node in _walk(tree)
        if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
    ]
    if len(attacks) != 1 or attacks[0][6] != [{
        "min": 0.5795833333333333,
        "max": 0.6666666666666666,
    }]:
        raise ValueError("西微满强化主动技攻击倍率字段漂移")
    attacks[0][6][0]["min"] = attacks[0][6][0]["max"]

    tolerances = [
        node for node in _walk(tree)
        if isinstance(node, list) and node and node[0] == "ACToleranceOfElement"
    ]
    if len(tolerances) != 1 or tolerances[0][3] != [{"min": -0.12, "max": -0.15}]:
        raise ValueError("西微满强化主动技风耐性降低字段漂移")
    tolerances[0][3][0]["min"] = tolerances[0][3][0]["max"]

    power_flip = [
        node for node in _walk(tree)
        if isinstance(node, list) and node and node[0] == "ACPowerFlipDamage"
    ]
    expected_pf = [{
        "min": 0.65,
        "max": 0.75,
        "alv_min": 0.15,
        "alv_max": 0.3,
    }]
    if len(power_flip) != 1 or power_flip[0][2] != expected_pf:
        raise ValueError("西微满强化主动技PF增益字段漂移")
    fixed_pf = power_flip[0][2][0]
    fixed_pf["min"] = fixed_pf["max"]
    fixed_pf.pop("alv_min")
    fixed_pf.pop("alv_max")

    output = _encode_dsl(tree)
    readback = _decode_dsl(output, XIWEI_ABILITY_SKILL_DSL_LOGICAL)
    names = [
        node[0] for node in _walk(readback)
        if isinstance(node, list) and node and isinstance(node[0], str)
    ]
    if "StopBall" in names or names.count("FindNearSubjects") != 1 or names.count("FindAllSubjects") != 1:
        raise AssertionError("旋风 ability_skill 命令回读不一致")
    if any(
        isinstance(node, dict) and ("alv_min" in node or "alv_max" in node)
        for node in _walk(readback)
    ):
        raise AssertionError("旋风 ability_skill 仍含能力等级插值字段")
    return output, {
        "source_logical": XIWEI_SKILL_DSL_LOGICAL,
        "output_logical": XIWEI_ABILITY_SKILL_DSL_LOGICAL,
        "source_sha256": XIWEI_SOURCE_DSL_SHA256,
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "actor_control_removed": ["StopBall"],
        "hit_count": 24,
        "damage_per_hit": 2 / 3,
        "total_damage_multiplier": 16,
        "wind_resistance_down_percent": 15,
        "wind_resistance_down_seconds": 20,
        "power_flip_damage_percent": 75,
        "power_flip_damage_seconds": 20,
        "skill_ranges_frozen_to_max": True,
        "ability_level_ranges_removed": True,
    }


def patch_skill_dsl(raw: bytes, logical: str) -> tuple[bytes, dict[str, Any]]:
    """把149996三档连击修正改为0.7%，并统一12秒贯通。"""
    if logical not in SKILL_DSL_LOGICALS.values():
        raise ValueError(f"不是149996主动技 DSL: {logical}")
    level = next(level for level, path in SKILL_DSL_LOGICALS.items() if path == logical)
    tree = _decode_dsl(raw, logical)
    attacks = [
        node
        for node in _walk(tree)
        if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
    ]
    if len(attacks) != 1 or len(attacks[0]) <= 8 or attacks[0][8] is not True:
        raise ValueError(f"149996 主动技{level}连击增伤开关漂移")
    attack = attacks[0]
    if (
        len(attack) <= 14
        or not isinstance(attack[14], list)
        or len(attack[14]) != 1
        or not isinstance(attack[14][0], dict)
        or set(attack[14][0]) != {"min", "max"}
    ):
        raise ValueError(f"149996 主动技{level}连击增伤系数字段漂移")
    combo_scale = attack[14][0]
    combo_before = (combo_scale["min"], combo_scale["max"])
    accepted_combo = {
        (COMBO_SCALING_PREVIOUS_RAW, COMBO_SCALING_PREVIOUS_RAW),
        (COMBO_SCALING_TARGET_RAW, COMBO_SCALING_TARGET_RAW),
    }
    if combo_before not in accepted_combo:
        raise ValueError(
            f"149996 主动技{level}连击增伤系数出现未审核值: {combo_before}"
        )
    combo_scale["min"] = COMBO_SCALING_TARGET_RAW
    combo_scale["max"] = COMBO_SCALING_TARGET_RAW

    piercing = [
        node
        for node in _walk(tree)
        if isinstance(node, list) and node and node[0] == "ACPiercing"
    ]
    if len(piercing) != 1:
        raise ValueError(f"149996 主动技{level}贯通节点数漂移: {len(piercing)}")
    duration = piercing[0][1]
    if (
        not isinstance(duration, list)
        or len(duration) != 1
        or not isinstance(duration[0], dict)
        or set(duration[0]) != {"min", "max"}
    ):
        raise ValueError(f"149996 主动技{level}贯通时长字段漂移")
    before = (duration[0]["min"], duration[0]["max"])
    accepted = {(630, 630), (PIERCING_DURATION_FRAMES, PIERCING_DURATION_FRAMES)}
    if before not in accepted:
        raise ValueError(f"149996 主动技{level}贯通时长出现未审核值: {before}")
    if level in (1, 2) and before != (PIERCING_DURATION_FRAMES, PIERCING_DURATION_FRAMES):
        raise ValueError(f"149996 主动技{level}不应出现10.5秒贯通")
    if (
        combo_before == (COMBO_SCALING_TARGET_RAW, COMBO_SCALING_TARGET_RAW)
        and before == (PIERCING_DURATION_FRAMES, PIERCING_DURATION_FRAMES)
    ):
        return raw, {
            "level": level,
            "combo_scaling_per_combo_percent": COMBO_SCALING_PER_COMBO_PERCENT,
            "combo_scaling_raw": COMBO_SCALING_TARGET_RAW,
            "combo_scaling_formula": "base_multiplier * (1 + combo * 0.007)",
            "piercing_duration_frames": PIERCING_DURATION_FRAMES,
            "piercing_duration_seconds": 12,
            "changed": False,
        }

    duration[0]["min"] = PIERCING_DURATION_FRAMES
    duration[0]["max"] = PIERCING_DURATION_FRAMES
    output = _encode_dsl(tree)
    readback = _decode_dsl(output, logical)
    if readback != tree:
        raise AssertionError("149996 主动技完整DSL语义回读不一致")
    final = [
        node
        for node in _walk(readback)
        if isinstance(node, list) and node and node[0] == "ACPiercing"
    ]
    if len(final) != 1 or final[0][1] != [{"min": 720, "max": 720}]:
        raise AssertionError("149996 主动技贯通时长回读不一致")
    final_attacks = [
        node
        for node in _walk(readback)
        if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
    ]
    if (
        len(final_attacks) != 1
        or final_attacks[0][8] is not True
        or final_attacks[0][14]
        != [{"min": COMBO_SCALING_TARGET_RAW, "max": COMBO_SCALING_TARGET_RAW}]
    ):
        raise AssertionError("149996 主动技0.7%连击修正回读不一致")
    return output, {
        "level": level,
        "combo_scaling_per_combo_percent": COMBO_SCALING_PER_COMBO_PERCENT,
        "combo_scaling_raw_before": combo_before[0],
        "combo_scaling_raw": COMBO_SCALING_TARGET_RAW,
        "combo_scaling_formula": "base_multiplier * (1 + combo * 0.007)",
        "piercing_duration_frames": PIERCING_DURATION_FRAMES,
        "piercing_duration_seconds": 12,
        "changed": True,
    }


def _leader_row(
    *,
    content: str,
    target: str,
    strength: int,
    combo: int | None,
    trigger_limit: int | None,
    wind_six: bool,
    target_group: str = "",
    trigger_kind: str | None = None,
    trigger_threshold: int | None = None,
) -> list[str]:
    """构造149996队长技的已审核124列行。"""
    row = [""] * 124
    row[0] = LEADER_ABILITY_STRING_ID
    row[1] = "0"
    row[3] = "0"
    row[4] = PRECONDITION_MEMBER if wind_six else PRECONDITION_ALWAYS
    if wind_six:
        threshold = str(LEADER_WIND_MEMBER_COUNT * 100_000)
        row[7] = row[8] = threshold
        row[9] = WIND_GROUP
    row[11] = PRECONDITION_ALWAYS
    row[18] = PRECONDITION_ALWAYS

    if combo is not None and trigger_kind is not None:
        raise ValueError("队长技单行不能同时使用连击触发和独立触发器")
    if trigger_threshold is not None and trigger_kind is None:
        raise ValueError("队长技触发阈值缺少触发器")

    row[25] = (
        INSTANT_COMBO_TRIGGER
        if combo is not None
        else (INITIAL_TRIGGER if trigger_kind is None else trigger_kind)
    )
    if combo is not None:
        threshold = str(combo * 100_000)
        row[28] = row[29] = threshold
        row[32] = "(None)" if trigger_limit is None else str(trigger_limit)
        row[33] = "0"
    elif trigger_kind is not None:
        if trigger_threshold is not None:
            threshold = str(trigger_threshold * 100_000)
            row[28] = row[29] = threshold
        row[32] = "(None)" if trigger_limit is None else str(trigger_limit)
        row[33] = "0"
    row[37] = "(None)"
    row[44] = "0"
    row[45] = content
    row[46] = target
    row[47] = target_group
    row[49] = row[50] = str(strength)
    return row


def _current_leader_rows() -> list[list[str]]:
    """1.4.88中149996现有四行，用作严格漂移护栏。"""
    return [
        _leader_row(
            content=INSTANT_ATTACK_POINT,
            target=TARGET_SELF,
            strength=LEADER_SELF_STRENGTH,
            combo=COMBO_STEP,
            trigger_limit=LEADER_TRIGGER_LIMIT,
            wind_six=False,
        ),
        _leader_row(
            content=INSTANT_DIRECT_DAMAGE,
            target=TARGET_SELF,
            strength=LEADER_SELF_STRENGTH,
            combo=COMBO_STEP,
            trigger_limit=LEADER_TRIGGER_LIMIT,
            wind_six=False,
        ),
        _leader_row(
            content=INSTANT_ATTACK_POINT,
            target=TARGET_PARTY,
            strength=LEADER_SELF_STRENGTH,
            combo=COMBO_STEP,
            trigger_limit=LEADER_TRIGGER_LIMIT,
            wind_six=True,
            target_group="(None)",
        ),
        _leader_row(
            content=INSTANT_DIRECT_DAMAGE,
            target=TARGET_PARTY,
            strength=LEADER_SELF_STRENGTH,
            combo=COMBO_STEP,
            trigger_limit=LEADER_TRIGGER_LIMIT,
            wind_six=True,
            target_group="(None)",
        ),
    ]


def _leader_rows_before_pf3_gauge() -> list[list[str]]:
    """1.4.88至1.4.90的149996队长技四行终态。"""
    rows = _current_leader_rows()[:2]
    rows.extend(
        [
            _leader_row(
                content=INSTANT_SKILL_GAUGE,
                target=TARGET_PARTY,
                strength=LEADER_GAUGE_CHARGE,
                combo=LEADER_GAUGE_COMBO,
                trigger_limit=None,
                wind_six=True,
                target_group=WIND_GROUP,
            ),
            _leader_row(
                content=INSTANT_SKILL_GAUGE_MAX,
                target=TARGET_PARTY,
                strength=LEADER_GAUGE_MAX,
                combo=None,
                trigger_limit=None,
                wind_six=True,
                target_group=WIND_GROUP,
            ),
        ]
    )
    return rows


def _patched_leader_rows() -> list[list[str]]:
    rows = _leader_rows_before_pf3_gauge()
    rows.append(
        _leader_row(
            content=INSTANT_SKILL_GAUGE,
            target=TARGET_PARTY,
            strength=LEADER_PF3_GAUGE_CHARGE,
            combo=None,
            trigger_limit=None,
            wind_six=True,
            target_group=WIND_GROUP,
            trigger_kind=INSTANT_POWER_FLIP_LV3_TRIGGER,
            trigger_threshold=1,
        )
    )
    return rows


def patch_leader_ability_rows(
    rows: list[list[str]],
) -> tuple[list[list[str]], dict[str, Any]]:
    """按确认方案替换149996队长技，拒绝覆盖任何未知中间状态。"""
    if any(len(row) != 124 for row in rows):
        raise ValueError("149996 队长技列数漂移")
    if any(row[0] != LEADER_ABILITY_STRING_ID for row in rows):
        raise ValueError("149996 队长技 string_id 漂移")

    current = _current_leader_rows()
    before_pf3_gauge = _leader_rows_before_pf3_gauge()
    patched = _patched_leader_rows()
    if rows not in (current, before_pf3_gauge, patched):
        raise ValueError("149996 队长技出现未审核行，拒绝覆盖")

    return [list(row) for row in patched], {
        "character_id": LEADER_ABILITY_KEY,
        "combo_step": COMBO_STEP,
        "trigger_limit": LEADER_TRIGGER_LIMIT,
        "self_attack_per_trigger_percent": 12.5,
        "self_direct_damage_per_trigger_percent": 12.5,
        "self_attack_max_percent": 1262.5,
        "self_direct_damage_max_percent": 1262.5,
        "wind_member_count": LEADER_WIND_MEMBER_COUNT,
        "gauge_combo_step": LEADER_GAUGE_COMBO,
        "wind_skill_gauge_per_trigger_percent": 150,
        "wind_skill_gauge_max_bonus_percent": 50,
        "wind_skill_gauge_effective_cap_percent": 150,
        "wind_skill_gauge_per_power_flip_lv3_percent": 77,
        "power_flip_lv3_trigger_limit": None,
        "power_flip_lv3_cooldown_seconds": 0,
        "writes_live": False,
    }


def patch_leader_ability_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """只替换 ``leader_ability#149996``，不写运行镜像或发布物。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, LEADER_ABILITY_LOGICAL)
    if len(table.keys) != len(set(table.keys)):
        raise ValueError("leader_ability.orderedmap 存在重复键")
    try:
        index = table.keys.index(LEADER_ABILITY_KEY)
    except ValueError as error:
        raise ValueError("leader_ability.orderedmap 缺少 149996") from error

    before_rows = list(table.rows)
    try:
        text = zlib.decompress(table.rows[index]).decode("utf-8")
    except Exception as error:
        raise ValueError("无法解码 leader_ability#149996") from error
    patched, report = patch_leader_ability_rows(core.read_csv_lines(text))
    replacement_text = core.write_csv_lines(patched)
    if replacement_text == text:
        report["changed"] = False
        return raw, report

    table.rows[index] = zlib.compress(replacement_text.encode("utf-8"))
    output = core.build_orderedmap_raw_rows(table)
    readback = core.read_orderedmap_raw_rows_from_bytes(output, LEADER_ABILITY_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("leader_ability.orderedmap 键顺序漂移")
    for position, (before, after) in enumerate(zip(before_rows, readback.rows)):
        if position != index and before != after:
            raise AssertionError(f"非目标队长技被改动: {table.keys[position]}")
    final = core.read_csv_lines(zlib.decompress(readback.rows[index]).decode("utf-8"))
    if final != patched:
        raise AssertionError("leader_ability#149996 回读不一致")
    report["changed"] = True
    return output, report


def _ability_base(string_id: str, category: str, *, main_only: bool = False) -> list[str]:
    row = [""] * 126
    row[0] = string_id
    row[1] = "true"
    row[2] = category
    row[3] = "0"
    row[5] = "0"
    row[6] = "202" if main_only else "0"
    row[13] = "0"
    row[20] = "0"
    row[39] = "(None)"
    row[46] = "0"
    return row


def _ability_combo_row(
    string_id: str,
    category: str,
    *,
    content: str,
    target: str,
    target_group: str,
    strength: int,
    trigger_limit: int,
    main_only: bool = False,
) -> list[str]:
    row = _ability_base(string_id, category, main_only=main_only)
    row[27] = INSTANT_COMBO_TRIGGER
    row[30] = row[31] = str(COMBO_STEP * 100_000)
    row[34] = str(trigger_limit)
    row[35] = "0"
    row[47] = content
    row[48] = target
    row[49] = target_group
    row[51] = row[52] = str(strength)
    return row


def _current_ability1_rows() -> list[list[str]]:
    initial = _ability_base(ABILITY1_STRING_ID, "action_skill")
    initial[27] = INITIAL_TRIGGER
    initial[47] = INSTANT_SKILL_GAUGE
    initial[48] = TARGET_SELF
    initial[51] = initial[52] = "100000"
    combo = _ability_combo_row(
        ABILITY1_STRING_ID,
        "action_skill",
        content=INSTANT_SKILL_GAUGE,
        target=TARGET_SELF,
        target_group="",
        strength=2_500,
        trigger_limit=77,
    )
    return [initial, combo]


def _patched_ability1_rows() -> list[list[str]]:
    rows = _current_ability1_rows()
    rows[1][34] = str(ABILITY_TRIGGER_LIMIT)
    rows[1][51] = rows[1][52] = str(ABILITY_GAUGE_STRENGTH)
    return rows


def patch_ability1_rows(rows: list[list[str]]) -> tuple[list[list[str]], dict[str, Any]]:
    """A1保留开局100%技能槽，并把77连击充能改为+5%、限101次。"""
    current = _current_ability1_rows()
    patched = _patched_ability1_rows()
    if rows != current and rows != patched:
        raise ValueError("149996 A1出现未审核行，拒绝覆盖")
    return [list(row) for row in patched], {
        "ability_key": ABILITY1_KEY,
        "opening_skill_gauge_percent": 100,
        "combo_step": COMBO_STEP,
        "skill_gauge_per_trigger_percent": 5,
        "trigger_limit": ABILITY_TRIGGER_LIMIT,
        "combo_skill_gauge_total_percent": 505,
    }


def _ability2_rows(target_group: str) -> list[list[str]]:
    return [
        _ability_combo_row(
            ABILITY2_STRING_ID,
            category,
            content=content,
            target=TARGET_PARTY,
            target_group=target_group,
            strength=LEADER_SELF_STRENGTH,
            trigger_limit=ABILITY_TRIGGER_LIMIT,
        )
        for category, content in (
            ("attack_green", INSTANT_ATTACK_POINT),
            ("attack_green", INSTANT_DIRECT_DAMAGE),
            ("action_skill", "34"),
        )
    ]


def patch_ability2_rows(rows: list[list[str]]) -> tuple[list[list[str]], dict[str, Any]]:
    """A2三项77连击增益从全队收窄为风属性角色。"""
    current = _ability2_rows("(None)")
    patched = _ability2_rows(WIND_GROUP)
    if rows != current and rows != patched:
        raise ValueError("149996 A2出现未审核行，拒绝覆盖")
    return [list(row) for row in patched], {
        "ability_key": ABILITY2_KEY,
        "target": "all_wind_characters",
        "combo_step": COMBO_STEP,
        "trigger_limit": ABILITY_TRIGGER_LIMIT,
        "attack_per_trigger_percent": 12.5,
        "direct_damage_per_trigger_percent": 12.5,
        "skill_damage_per_trigger_percent": 12.5,
    }


def _ability6_skill_trigger_row(content: str) -> list[str]:
    category = "attack_green" if content == INSTANT_ADD_COMBO else "condition"
    row = _ability_base(ABILITY6_STRING_ID, category, main_only=True)
    row[27] = INSTANT_SKILL_TRIGGER
    row[28] = TARGET_SELF
    row[30] = row[31] = "100000"
    row[34] = "(None)"
    row[35] = "0"
    row[47] = content
    if content == INSTANT_ADD_COMBO:
        row[51] = row[52] = str(COMBO_STEP * 100_000)
    elif content == INSTANT_CONDITION_DIRECT_ATTACK3:
        row[48] = TARGET_SELF
        row[51] = row[52] = "0"
        row[57] = row[58] = "120000000"
        row[59] = row[60] = "100000"
        for column in range(61, 66):
            row[column] = "(None)"
        row[67] = "0"
        row[72] = "false"
        row[74] = "1"
        row[75] = "0"
    elif content == INSTANT_CONDITION_SWIFT:
        row[57] = row[58] = "72000000"
        row[59] = row[60] = "100000"
        for column in range(62, 66):
            row[column] = "(None)"
        row[67] = "0"
        row[72] = "false"
    else:
        raise ValueError(f"不支持的149996 A6技能触发效果: {content}")
    return row


def _ability6_invoke_xiwei_row() -> list[str]:
    """技能发动时调用专用 ability_skill 版“旋风”，冷却1秒。"""
    row = _ability_base(ABILITY6_STRING_ID, "special", main_only=True)
    row[27] = INSTANT_SKILL_TRIGGER
    row[28] = TARGET_SELF
    row[30] = row[31] = "100000"
    row[34] = "(None)"
    row[35] = str(XIWEI_INVOKE_COOLDOWN_FRAMES)
    row[47] = INSTANT_INVOKE_SKILL
    row[70] = XIWEI_INVOKE_STRING_ID
    row[71] = XIWEI_ACTION_PATH
    return row


def _unsafe_ability6_invoke_xiwei_rare5_row() -> list[str]:
    """识别1.4.88中会按普通角色主动技路径执行的高风险中间态。"""
    row = _ability6_invoke_xiwei_row()
    row[71] = XIWEI_SOURCE_ACTION_PATH
    return row


def _legacy_ability6_invoke_ram_row() -> list[str]:
    """构造旧的拉姆调用行，仅用于安全识别尚未发布的中间态。"""
    row = _ability_base(ABILITY6_STRING_ID, "special", main_only=True)
    row[27] = INSTANT_SKILL_TRIGGER
    row[28] = TARGET_SELF
    row[30] = row[31] = "100000"
    row[34] = "(None)"
    row[35] = str(XIWEI_INVOKE_COOLDOWN_FRAMES)
    row[47] = INSTANT_INVOKE_SKILL
    row[70] = _LEGACY_RAM_INVOKE_STRING_ID
    row[71] = _LEGACY_RAM_ACTION_PATH
    return row


def _current_ability6_rows() -> list[list[str]]:
    gauge = _ability_combo_row(
        ABILITY6_STRING_ID,
        "action_skill",
        content=INSTANT_SKILL_GAUGE,
        target=TARGET_PARTY,
        target_group="(None)",
        strength=2_500,
        trigger_limit=77,
        main_only=True,
    )
    return [
        gauge,
        _ability6_skill_trigger_row(INSTANT_ADD_COMBO),
        _ability6_skill_trigger_row(INSTANT_CONDITION_DIRECT_ATTACK3),
        _ability6_skill_trigger_row(INSTANT_CONDITION_SWIFT),
    ]


def _patched_ability6_rows_without_invoked_skill() -> list[list[str]]:
    rows = _current_ability6_rows()
    gauge = rows[0]
    gauge[34] = str(ABILITY_TRIGGER_LIMIT)
    gauge[49] = WIND_GROUP
    gauge[51] = gauge[52] = str(ABILITY_GAUGE_STRENGTH)
    return [gauge, rows[2], rows[3]]


def _patched_ability6_rows() -> list[list[str]]:
    rows = _patched_ability6_rows_without_invoked_skill()
    return [*rows, _ability6_invoke_xiwei_row()]


def patch_ability6_rows(rows: list[list[str]]) -> tuple[list[list[str]], dict[str, Any]]:
    """A6改为风属性充能+5%×101，并在技能发动时追加西微旋风。"""
    current = _current_ability6_rows()
    previous = _patched_ability6_rows_without_invoked_skill()
    legacy_ram = [*previous, _legacy_ability6_invoke_ram_row()]
    unsafe_xiwei_rare5 = [*previous, _unsafe_ability6_invoke_xiwei_rare5_row()]
    patched = _patched_ability6_rows()
    if rows not in (current, previous, legacy_ram, unsafe_xiwei_rare5, patched):
        raise ValueError("149996 A6出现未审核行，拒绝覆盖")
    return [list(row) for row in patched], {
        "ability_key": ABILITY6_KEY,
        "main_position_only": True,
        "target": "all_wind_characters",
        "combo_step": COMBO_STEP,
        "skill_gauge_per_trigger_percent": 5,
        "trigger_limit": ABILITY_TRIGGER_LIMIT,
        "combo_skill_gauge_total_percent": 505,
        "skill_invoke_add_combo_removed": True,
        "skill_invoke_direct_attack3_kept": True,
        "skill_invoke_swift_kept": True,
        "invoke_other_skill_added": True,
        "invoked_character_id": XIWEI_CHARACTER_ID,
        "invoked_character_name": "西微",
        "invoked_action_skill_key": XIWEI_ACTION_SKILL_KEY,
        "invoked_action_skill_level": XIWEI_ACTION_SKILL_LEVEL,
        "invoked_action_skill_name": "风怒龙卷＋",
        "invoked_action_skill_display_name": "旋风",
        "invoked_source_action_path": XIWEI_SOURCE_ACTION_PATH,
        "invoked_action_path": XIWEI_ACTION_PATH,
        "invoked_as_native_ability_skill": True,
        "invoke_cooldown_frames": XIWEI_INVOKE_COOLDOWN_FRAMES,
        "invoke_cooldown_seconds": XIWEI_INVOKE_COOLDOWN_SECONDS,
        "legacy_ram_state_migrated": rows == legacy_ram,
        "unsafe_rare5_state_migrated": rows == unsafe_xiwei_rare5,
    }


def _require_row_shape(row: list[str]) -> None:
    if len(row) != 126:
        raise ValueError(f"149996 能力3列数漂移: {len(row)} != 126")
    if row[0] != ABILITY3_STRING_ID:
        raise ValueError(f"149996 能力3 string_id 漂移: {row[0]!r}")
    if row[6] != "202":
        raise ValueError("149996 能力3不再是主位前置条件，拒绝误改")


def _modifier_kind(row: list[str]) -> str | None:
    if row[5] == "0" and row[27] == INSTANT_COMBO_TRIGGER:
        return _INSTANT_TO_DURING.get(row[47])
    if row[5] == "1" and row[97] == DURING_COMBO_TRIGGER:
        return row[109] if row[109] in _DURING_CONTENTS else None
    return None


def _build_during_modifier(source: list[str], content: str) -> list[str]:
    row = list(source)
    row[5] = "1"
    for column in range(27, 123):
        row[column] = ""
    row[85] = "(None)"
    row[97] = DURING_COMBO_TRIGGER
    row[100] = str(COMBO_STEP * 100_000)
    row[101] = str(COMBO_STEP * 100_000)
    row[102] = str(MAX_LAYERS)
    row[108] = "false"
    row[109] = content
    row[110] = "0"  # 自身。
    row[113] = str(LAYER_STRENGTH)
    row[114] = str(LAYER_STRENGTH)
    return row


def _build_combo_reset(source: list[str]) -> list[str]:
    row = list(source)
    row[5] = "0"
    for column in range(27, 123):
        row[column] = ""
    row[27] = INSTANT_COMBO_TRIGGER
    row[30] = str(COMBO_RESET * 100_000)
    row[31] = str(COMBO_RESET * 100_000)
    row[34] = "(None)"
    row[35] = "0"
    row[39] = "(None)"
    row[46] = "0"
    row[47] = INSTANT_SET_COMBO
    row[51] = "0"
    row[52] = "0"
    return row


def patch_ability3_rows(rows: list[list[str]]) -> tuple[list[list[str]], dict[str, Any]]:
    """把能力3改为每77连击一层、10层、777连击归零的持续模式。"""
    if len(rows) not in (2, 3):
        raise ValueError(f"149996 能力3行数漂移: {len(rows)}")
    for row in rows:
        _require_row_shape(row)

    modifiers: dict[str, list[str]] = {}
    reset_rows: list[list[str]] = []
    for row in rows:
        kind = _modifier_kind(row)
        if kind is not None:
            if kind in modifiers:
                raise ValueError(f"149996 能力3重复效果行: {kind}")
            modifiers[kind] = row
        elif row[5] == "0" and row[27] == INSTANT_COMBO_TRIGGER and row[47] == INSTANT_SET_COMBO:
            reset_rows.append(row)
        else:
            raise ValueError("149996 能力3出现未审核行，拒绝覆盖")

    if set(modifiers) != _DURING_CONTENTS:
        raise ValueError(f"149996 能力3效果集合漂移: {sorted(modifiers)}")
    if len(reset_rows) > 1:
        raise ValueError("149996 能力3存在重复777连击归零行")

    output = [
        _build_during_modifier(modifiers[DURING_SEPARATED_SKILL_DAMAGE], DURING_SEPARATED_SKILL_DAMAGE),
        _build_during_modifier(modifiers[DURING_SEPARATED_DIRECT_DAMAGE], DURING_SEPARATED_DIRECT_DAMAGE),
        _build_combo_reset(reset_rows[0] if reset_rows else next(iter(modifiers.values()))),
    ]
    return output, {
        "character_id": "149996",
        "ability_key": ABILITY3_KEY,
        "main_position_only": True,
        "combo_step": COMBO_STEP,
        "combo_reset": COMBO_RESET,
        "max_layers": MAX_LAYERS,
        "skill_damage_per_layer_percent": 20,
        "direct_damage_per_layer_percent": 20,
        "skill_damage_max_percent": 200,
        "direct_damage_max_percent": 200,
        "break_clears_layers": True,
        "writes_live": False,
    }


def patch_ability_table(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """统一替换149996的A1/A2/A3/A6，并逐字节保留其他能力键。"""
    table = core.read_orderedmap_raw_rows_from_bytes(raw, ABILITY_LOGICAL)
    if len(table.keys) != len(set(table.keys)):
        raise ValueError("ability.orderedmap 存在重复键")

    patchers = {
        ABILITY1_KEY: patch_ability1_rows,
        ABILITY2_KEY: patch_ability2_rows,
        ABILITY3_KEY: patch_ability3_rows,
        ABILITY6_KEY: patch_ability6_rows,
    }
    missing = set(patchers) - set(table.keys)
    if missing:
        raise ValueError(f"ability.orderedmap 缺少149996能力键: {sorted(missing)}")

    before_outer = list(table.rows)
    replacements: dict[str, str] = {}
    ability_reports: dict[str, dict[str, Any]] = {}
    for key, patcher in patchers.items():
        index = table.keys.index(key)
        try:
            text = zlib.decompress(table.rows[index]).decode("utf-8")
        except Exception as error:
            raise ValueError(f"无法解码 ability#{key}") from error
        rows, ability_report = patcher(core.read_csv_lines(text))
        replacement = core.write_csv_lines(rows)
        replacements[key] = replacement
        ability_reports[key] = ability_report
        if replacement != text:
            table.rows[index] = zlib.compress(replacement.encode("utf-8"))

    if table.rows == before_outer:
        return raw, {
            "character_id": "149996",
            "abilities": ability_reports,
            "writes_live": False,
            "changed": False,
        }

    output = core.build_orderedmap_raw_rows(table)
    readback = core.read_orderedmap_raw_rows_from_bytes(output, ABILITY_LOGICAL)
    if readback.keys != table.keys:
        raise AssertionError("ability.orderedmap 键顺序漂移")
    for position, (before, after) in enumerate(zip(before_outer, readback.rows)):
        key = table.keys[position]
        if key not in patchers and before != after:
            raise AssertionError(f"非目标能力被改动: {key}")
        if key in patchers:
            text = zlib.decompress(after).decode("utf-8")
            if text != replacements[key]:
                raise AssertionError(f"ability#{key} 回读不一致")
    return output, {
        "character_id": "149996",
        "abilities": ability_reports,
        "writes_live": False,
        "changed": True,
    }


__all__ = [
    "ACTION_SKILL_KEY",
    "ACTION_SKILL_LOGICAL",
    "ABILITY1_KEY",
    "ABILITY2_KEY",
    "ABILITY3_KEY",
    "ABILITY6_KEY",
    "ABILITY_GAUGE_STRENGTH",
    "ABILITY_LOGICAL",
    "ABILITY_TRIGGER_LIMIT",
    "CHARACTER_TEXT_KEY",
    "CHARACTER_TEXT_LOGICAL",
    "COMBO_SCALING_PER_COMBO_PERCENT",
    "COMBO_SCALING_PREVIOUS_RAW",
    "COMBO_SCALING_TARGET_RAW",
    "COMBO_RESET",
    "COMBO_STEP",
    "CUSTOM_ABILITY_STRING_LOGICAL",
    "LEADER_ABILITY_KEY",
    "LEADER_ABILITY_LOGICAL",
    "LEADER_GAUGE_CHARGE",
    "LEADER_GAUGE_COMBO",
    "LEADER_GAUGE_MAX",
    "LEADER_PF3_GAUGE_CHARGE",
    "LEADER_SELF_STRENGTH",
    "LEADER_TRIGGER_LIMIT",
    "LEADER_WIND_MEMBER_COUNT",
    "LAYER_STRENGTH",
    "MAX_LAYERS",
    "OLD_SKILL_DESCRIPTION",
    "PIERCING_DURATION_FRAMES",
    "SKILL_DESCRIPTION",
    "SKILL_DSL_LOGICALS",
    "XIWEI_ACTION_PATH",
    "XIWEI_ABILITY_SKILL_DSL_LOGICAL",
    "XIWEI_ACTION_SKILL_KEY",
    "XIWEI_ACTION_SKILL_LEVEL",
    "XIWEI_CHARACTER_ID",
    "XIWEI_INVOKE_COOLDOWN_FRAMES",
    "XIWEI_INVOKE_COOLDOWN_SECONDS",
    "XIWEI_INVOKE_DESCRIPTION",
    "XIWEI_INVOKE_STRING_ID",
    "XIWEI_SKILL_DSL_LOGICAL",
    "XIWEI_SOURCE_ACTION_PATH",
    "XIWEI_SOURCE_DSL_SHA256",
    "build_xiwei_ability_skill_dsl",
    "patch_action_skill_entries",
    "patch_action_skill_table",
    "patch_ability1_rows",
    "patch_ability2_rows",
    "patch_ability3_rows",
    "patch_ability6_rows",
    "patch_ability_table",
    "patch_character_text_rows",
    "patch_character_text_table",
    "patch_custom_ability_string_table",
    "patch_leader_ability_rows",
    "patch_leader_ability_table",
    "patch_skill_dsl",
]
