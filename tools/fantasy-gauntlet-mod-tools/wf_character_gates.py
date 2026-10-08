#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新角色边界门禁的纯逻辑实现（无 store / 无网络 / 不写盘）。

四道门禁（2026-10-06 凉月制作复盘，源事故见各函数注释）：

1. 仓库边界：输出路径断言（禁写 ``.cdn``；成员必须是 ``production/<root>``、
   禁止 ``production/production`` 双层前缀）。
2. 链边界：外层 key union（有效链既有 outer key 不得减少）+ 声明行合并审计。
3. 结构契约：编译产物对官方/donor 逐键对齐（timeline 的
   ``sequences/sounds/points/circles``、atlas/frame/parts）。
4. 解析器契约：声明行强类型字段校验（Bool/枚举/数值/``(None)``，
   覆盖 col47/col72/col75 类案例）与官方先例统计。

本模块只做判定与报告，I/O 由调用方提供（``check_character_edge.py``、
``wf_character_flow.py``、studio 自测）。
"""
from __future__ import annotations

import hashlib
import re
import zlib
from pathlib import PurePosixPath

import wf_describe
import wf_client_legality

CDN_COMPONENT = ".cdn"

# production/<root>/<xx>/<hash> 的合法 root（prepare_content.ROOTS 的值）
MEMBER_ROOTS = ("upload", "medium_upload", "android_upload", "ios_upload")
ROOT_TO_MEMBER = {
    "common": "upload",
    "medium": "medium_upload",
    "android": "android_upload",
    "ios": "ios_upload",
}
BOOLEAN_VALUES = frozenset(
    {"TRUE", "True", "true", "FALSE", "False", "false"}
)

# ---------------------------------------------------------------------------
# 1. 仓库边界：输出路径断言
# ---------------------------------------------------------------------------


def resolved_parts_include_cdn(path) -> bool:
    """Path/字符串解析后是否落在受保护的 ``.cdn`` 基线内。

    调用方应传入已 ``resolve()`` 的 Path（Windows junction 会被展开）；
    未解析的字符串也按部件名判定，保证 fail-closed。
    """
    try:
        text = str(path)
    except Exception:  # noqa: BLE001 - 任意对象都不能绕过 fail-closed 判定
        return True
    if not text:
        return True
    return any(part.casefold() == CDN_COMPONENT for part in re.split(r"[\\/]+", text))


def member_path_problems(member: str) -> list[str]:
    """校验一个 CDN 归档成员（存档内的 production/... 路径）与仓库边界规则。"""
    problems: list[str] = []
    if not isinstance(member, str) or not member:
        return ["成员路径为空"]
    if "\\" in member:
        problems.append(f"成员路径含反斜杠: {member}")
    if member.startswith("/") or re.match(r"^[A-Za-z]:", member):
        problems.append(f"成员路径为绝对路径: {member}")
    path = PurePosixPath(member)
    if ".." in path.parts or "." in path.parts:
        problems.append(f"成员路径含相对跳转: {member}")
    parts = path.parts
    if len(parts) != 4 or parts[0] != "production":
        return problems + [
            f"成员路径必须是 production/<upload|medium_upload|android_upload|ios_upload>/<xx>/<hash>: {member}"
        ]
    if parts[1] == "production":
        problems.append(f"成员路径出现 production/production 双层前缀: {member}")
    elif parts[1] not in MEMBER_ROOTS:
        problems.append(
            f"成员 root 不在 {sorted(MEMBER_ROOTS)}: {member}"
        )
    if not re.fullmatch(r"[0-9a-f]{2}", parts[2]) or not re.fullmatch(r"[0-9a-f]+", parts[3]):
        problems.append(f"成员桶号/文件名不是小写十六进制: {member}")
    return problems


def archive_member_report(members) -> dict:
    """整包成员报告：逐成员问题 + 重复成员 + root 统计。"""
    problems: list[str] = []
    seen: set[str] = set()
    by_root: dict[str, int] = {}
    for member in members:
        for problem in member_path_problems(member):
            problems.append(problem)
        if member in seen:
            problems.append(f"归档内成员重复: {member}")
        seen.add(member)
        parts = PurePosixPath(member).parts
        if len(parts) == 4:
            by_root[parts[1]] = by_root.get(parts[1], 0) + 1
    return {
        "members": len(seen),
        "by_root": by_root,
        "problems": problems,
    }


def audit_receipt_report(audit_dir, report_name: str | None = None) -> dict:
    """audit 目录回执齐全性：目录存在、非空、报告文件存在。"""
    from pathlib import Path

    directory = Path(audit_dir)
    report = {"directory": str(directory), "exists": directory.is_dir()}
    if not directory.is_dir():
        report["problems"] = [f"audit 目录缺失: {directory}"]
        return report
    names = sorted(path.name for path in directory.iterdir() if path.is_file())
    report["files"] = names
    report["file_count"] = len(names)
    problems = []
    if not names:
        problems.append(f"audit 目录为空: {directory}")
    if report_name and report_name not in names:
        problems.append(f"audit 报告文件缺失: {directory / report_name}")
    report["problems"] = problems
    return report


# ---------------------------------------------------------------------------
# 2. 链边界：outer key union + 声明行合并审计
# ---------------------------------------------------------------------------


def outer_key_union_report(before: dict[str, str], after: dict[str, str]) -> dict:
    """有效链既有 outer key 不得减少（C8601 整表覆盖事故的发布门禁）。

    返回逐 key 的 added/changed/removed 清单；removed 非空即 fail-closed。
    """
    before_keys = set(before)
    after_keys = set(after)
    removed = sorted(before_keys - after_keys)
    added = sorted(after_keys - before_keys)
    changed = sorted(
        key for key in before_keys & after_keys if before[key] != after[key]
    )
    return {
        "before_keys": len(before_keys),
        "after_keys": len(after_keys),
        "added": added,
        "removed": removed,
        "changed": changed,
        "changed_rows": [
            {
                "key": key,
                "before_sha256": hashlib.sha256(before[key].encode("utf-8")).hexdigest(),
                "after_sha256": hashlib.sha256(after[key].encode("utf-8")).hexdigest(),
                "before_bytes": len(before[key]),
                "after_bytes": len(after[key]),
            }
            for key in changed
        ],
        "problems": [
            f"outer key 丢失: {key}（有效链既有 key 必须保留）" for key in removed
        ],
    }


def declared_row_merge_report(
    before: dict[str, str],
    after: dict[str, str],
    declared_keys,
) -> dict:
    """声明行合并审计：声明 key 必须存在，并记录新旧存储 sha。"""
    rows = []
    problems = []
    for key in sorted({str(item) for item in declared_keys}):
        if key not in after:
            problems.append(f"声明行丢失: {key}")
            continue
        rows.append({
            "key": key,
            "present_before": key in before,
            "changed": before.get(key) != after.get(key),
            "before_sha256": (
                hashlib.sha256(before[key].encode("utf-8")).hexdigest()
                if key in before else None
            ),
            "after_sha256": hashlib.sha256(after[key].encode("utf-8")).hexdigest(),
        })
    return {"declared": rows, "problems": problems}


# ---------------------------------------------------------------------------
# 3. 结构契约：编译产物 vs 官方/donor 键集
# ---------------------------------------------------------------------------

PIXELART_TIMELINE_KEYS = frozenset({"sequences", "sounds", "points", "circles"})
EFFECT_TIMELINE_KEYS = frozenset(
    {"sequences", "sounds", "points", "circles", "rectangles", "matrices"}
)
PIXELART_ATLAS_RECORD_KEYS = frozenset(
    {"n", "w", "h", "x", "y", "fx", "fy", "fw", "fh"}
)
EFFECT_ATLAS_RECORD_KEYS = frozenset({"n", "x", "y", "w", "h"})
FRAME_KEYS = frozenset({"name", "x", "y", "scale", "smoothing"})
PARTS_KEYS = frozenset({"i", "g", "m", "a", "o", "t", "c", "s"})


def decode_amf3_deflate(raw: bytes):
    """严格 raw-deflate + AMF3 解析；失败返回 None。"""
    import wf_dsl

    try:
        decompressor = zlib.decompressobj(-15)
        plain = decompressor.decompress(raw) + decompressor.flush()
        if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
            return None
        return wf_dsl.parse_dsl(plain)["tree"]
    except Exception:  # noqa: BLE001 - 任意载荷都要能失败关闭
        return None


def is_pixelart_path(logical: str) -> bool:
    return "/pixelart/" in "/" + logical.replace("\\", "/")


def timeline_role(logical: str) -> str | None:
    path = logical.replace("\\", "/")
    if path.endswith(".timeline.amf3.deflate") and "/pixelart/" in path:
        return "pixelart"
    if path.endswith(".timeline.amf3.deflate"):
        return "effect"
    return None


def infer_role(tree) -> str | None:
    """按载荷内容判定结构角色（成员名是哈希时也能判定）。"""
    if isinstance(tree, list):
        if tree and isinstance(tree[0], dict) and "n" in tree[0]:
            # 角色像素图集的每条记录都有未裁剪画布 fw/fh；原生特效图集
            # （donor 官方结构）常常只有 n/x/y/w/h（±fx/fy），不满足全量条件。
            if all(isinstance(record, dict) and {"fw", "fh"} <= set(record)
                   for record in tree):
                return "pixelart-atlas"
            return "effect-atlas"
        return None
    if not isinstance(tree, dict):
        return None
    keys = set(tree)
    if "sequences" in keys:
        return "pixelart-timeline" if "rectangles" not in keys else "effect-timeline"
    if {"i", "g", "t"} <= keys:
        return "parts"
    if {"name", "x", "y", "scale"} <= keys:
        return "frame"
    return None


def structural_problems(logical: str, tree, donor_tree=None, role: str | None = None) -> list[str]:
    """按成员角色做逐键结构契约校验，可选与 donor 逐键对齐。

    ``role`` 未显式给出时：先按逻辑路径判定，再退回载荷内容判定
    （哈希成员名/未知路径也能检查，历史边复核用）。
    """
    path = logical.replace("\\", "/")
    timeline = timeline_role(path)
    role = role or (
        f"{timeline}-timeline" if timeline else
        "pixelart-atlas" if path.endswith(".atlas.amf3.deflate") and is_pixelart_path(path) else
        "effect-atlas" if path.endswith(".atlas.amf3.deflate") else
        "frame" if path.endswith(".frame.amf3.deflate") else
        "parts" if path.endswith(".parts.amf3.deflate") else
        infer_role(tree)
    )
    if role is None:
        return []
    problems: list[str] = []
    if role.endswith("-timeline"):
        allowed = (PIXELART_TIMELINE_KEYS if role == "pixelart-timeline"
                   else EFFECT_TIMELINE_KEYS)
        if not isinstance(tree, dict):
            return [f"{logical}: timeline 不是 AMF3 对象"]
        keys = set(tree)
        missing = sorted(allowed - keys)
        extra = sorted(keys - allowed)
        if missing:
            problems.append(f"{logical}: timeline 缺键 {missing}（角色 {role}）")
        if extra:
            problems.append(f"{logical}: timeline 多出未登记键 {extra}（角色 {role}）")
        sounds = tree.get("sounds", "__ABSENT__")
        if sounds == "__ABSENT__":
            problems.append(
                f"{logical}: timeline 缺 sounds（F1009: loadDynamicSoundEffect 无判空）"
            )
        elif not isinstance(sounds, list):
            problems.append(f"{logical}: timeline.sounds 不是数组")
        if donor_tree is not None:
            if not isinstance(donor_tree, dict):
                problems.append(f"{logical}: donor timeline 不是 AMF3 对象")
            elif set(donor_tree) != keys:
                problems.append(
                    f"{logical}: 与 donor 键集不一致 donor={sorted(donor_tree)} edge={sorted(keys)}"
                )
    elif role.endswith("-atlas"):
        problems.extend(atlas_problems(
            logical, tree, donor_tree, pixelart=(role == "pixelart-atlas")))
    elif role == "frame":
        if not isinstance(tree, dict):
            return [f"{logical}: frame 不是 AMF3 对象"]
        keys = set(tree)
        if keys != FRAME_KEYS:
            problems.append(
                f"{logical}: frame 键集 {sorted(keys)} != {sorted(FRAME_KEYS)}"
            )
        for key, expect in (("x", -128), ("y", -128)):
            value = tree.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value != expect:
                problems.append(f"{logical}: frame.{key}={value!r}（官方同构应为 {expect}）")
        scale = tree.get("scale")
        if not isinstance(scale, (int, float)) or isinstance(scale, bool) or scale <= 0:
            problems.append(f"{logical}: frame.scale 非法: {scale!r}")
        if donor_tree is not None and isinstance(donor_tree, dict) and set(donor_tree) != keys:
            problems.append(
                f"{logical}: 与 donor frame 键集不一致 donor={sorted(donor_tree)}"
            )
    elif role == "parts":
        if not isinstance(tree, dict):
            return [f"{logical}: parts 不是 AMF3 对象"]
        keys = set(tree)
        missing = sorted(PARTS_KEYS - keys)
        if missing:
            problems.append(f"{logical}: parts 缺键 {missing}")
        if donor_tree is not None and isinstance(donor_tree, dict) and set(donor_tree) != keys:
            problems.append(
                f"{logical}: 与 donor parts 键集不一致 donor={sorted(donor_tree)} edge={sorted(keys)}"
            )
    return problems


def atlas_problems(logical: str, tree, donor_tree=None, pixelart: bool | None = None) -> list[str]:
    """atlas 记录契约 + 客户端语义几何约束。

    SpriteSheetHandler.as:49-67 -> SubTexture.as:48-70 -> Texture.as:339-357：
    region=(x,y,w,h) 决定绘制尺寸，frame=(fx,fy,fw,fh) 决定绘制位置
    ``(-fx,-fy)``；``(-fx, -fy)`` 加 region 必须落在未裁剪画布 ``fw×fh`` 内。
    """
    problems: list[str] = []
    if not isinstance(tree, list):
        return [f"{logical}: atlas 不是 AMF3 数组"]
    if pixelart is None:
        pixelart = is_pixelart_path(logical)
    required = PIXELART_ATLAS_RECORD_KEYS if pixelart else EFFECT_ATLAS_RECORD_KEYS
    donor_record_keys = None
    if isinstance(donor_tree, list) and donor_tree:
        donor_record_keys = set(donor_tree[0]) if isinstance(donor_tree[0], dict) else None
    for index, record in enumerate(tree):
        if not isinstance(record, dict):
            problems.append(f"{logical}[{index}]: atlas 记录不是对象")
            continue
        keys = set(record)
        missing = sorted(required - keys)
        if missing:
            problems.append(f"{logical}[{index}]: atlas 记录缺键 {missing}")
        if donor_record_keys is not None and keys != donor_record_keys:
            problems.append(
                f"{logical}[{index}]: 与 donor 记录键集不一致 "
                f"donor={sorted(donor_record_keys)} edge={sorted(keys)}"
            )
        if pixelart:
            for key in ("n", "w", "h", "x", "y", "fx", "fy", "fw", "fh"):
                value = record.get(key)
                if key == "n":
                    if not isinstance(value, str) or not value:
                        problems.append(f"{logical}[{index}]: n 非法: {value!r}")
                    continue
                if isinstance(value, bool) or not isinstance(value, int):
                    problems.append(f"{logical}[{index}]: {key}={value!r} 不是整数")
                    continue
                if key in ("w", "h", "fw", "fh") and value <= 0:
                    problems.append(f"{logical}[{index}]: {key}={value} 必须为正")
                if key in ("x", "y") and value < 0:
                    problems.append(f"{logical}[{index}]: {key}={value} 不能为负")
            left, top = -record.get("fx", 0), -record.get("fy", 0)
            width, height = record.get("w", 0), record.get("h", 0)
            full_width, full_height = record.get("fw", 0), record.get("fh", 0)
            if full_width > 0 and full_height > 0 and width > 0 and height > 0:
                if left < 0 or top < 0:
                    problems.append(
                        f"{logical}[{index}]: (-fx,-fy)=({left},{top}) 为负（锚点越界）"
                    )
                elif left + width > full_width or top + height > full_height:
                    problems.append(
                        f"{logical}[{index}]: 区域 ({left},{top},{width},{height}) "
                        f"超出帧画布 {full_width}×{full_height}"
                    )
    return problems


def timeline_anchor_report(tree) -> dict:
    """timeline``points/circles`` 锚点和 atlas``fx/fy``不属于同一契约；本函数
    只汇总 timeline 四键状态，供历史核对与报告使用。"""
    if not isinstance(tree, dict):
        return {"ok": False, "reason": "not-an-object"}
    sounds = tree.get("sounds", "__ABSENT__")
    return {
        "ok": sounds != "__ABSENT__" and isinstance(sounds, list),
        "keys": sorted(tree),
        "sounds_len": len(sounds) if isinstance(sounds, list) else None,
        "sequences": len(tree.get("sequences") or []),
        "points": len(tree.get("points") or []),
        "circles": len(tree.get("circles") or []),
    }


def _frame_number(name: str) -> int | None:
    match = re.search(r"(\d+)$", name or "")
    return int(match.group(1)) if match else None


def anchor_regression_report(
    before_tree,
    after_tree,
    *,
    dx: int,
    dy: int,
    label: str,
    keep_frames=(),
) -> dict:
    """**锚点逐帧零变化**门禁（2026-10-06 1.4.143 像素偏移事故专用）。

    客户端语义（``Texture.as:339-357``）：区域左上角画在 ``(-fx, -fy)``。
    当一组帧的素材被替换（纯本体 ↔ 合成帧）时，声明素材在旧帧内的偏移
    ``(dx, dy)``，则新 atlas 必须满足

        ``(-fx_new, -fy_new) = (-fx_old, -fy_old) + (dx, dy)``

    1.4.143 事故把补偿符号做反（-12 而非 +12），本函数会把该错误逐帧报出。
    ``dx=dy=0`` 即“锚点逐帧零变化”（只换像素内容、不动物理位置）。
    ``keep_frames`` 里的帧号不做素材替换（例如技能帧保留合成帧），
    这些帧的期望位移是 (0, 0)。
    """
    problems: list[str] = []
    if not isinstance(before_tree, list) or not isinstance(after_tree, list):
        return {"label": label, "problems": [f"{label}: atlas 不是数组，无法做锚点回归"],
                "checked": 0, "max_deviation": None}
    keep = {int(item) for item in keep_frames}
    before = {}
    for record in before_tree:
        if isinstance(record, dict):
            number = _frame_number(record.get("n", ""))
            if number is not None:
                before[number] = record
    checked = 0
    max_deviation = 0
    deviations: list[dict] = []
    for record in after_tree:
        if not isinstance(record, dict):
            continue
        number = _frame_number(record.get("n", ""))
        if number is None:
            problems.append(f"{label}: 帧名无法解析数字后缀: {record.get('n')!r}")
            continue
        old = before.get(number)
        if old is None:
            problems.append(f"{label}: 帧 {number} 在旧版 atlas 中不存在（帧集合变化）")
            continue
        checked += 1
        for field in ("fw", "fh"):
            if record.get(field) != old.get(field):
                problems.append(
                    f"{label}: 帧 {number} {field} 变化 {old.get(field)} -> {record.get(field)}"
                    "（未裁剪画布尺寸是不变量）"
                )
        old_left, old_top = -old.get("fx", 0), -old.get("fy", 0)
        new_left, new_top = -record.get("fx", 0), -record.get("fy", 0)
        expect_x, expect_y = (0, 0) if number in keep else (dx, dy)
        dev_x = (new_left - old_left) - expect_x
        dev_y = (new_top - old_top) - expect_y
        max_deviation = max(max_deviation, abs(dev_x), abs(dev_y))
        if dev_x or dev_y:
            deviations.append({
                "frame": number,
                "delta": [new_left - old_left, new_top - old_top],
                "expected": [expect_x, expect_y],
            })
    if deviations:
        sample = ", ".join(
            f"帧{row['frame']} {row['delta']}!={row['expected']}" for row in deviations[:6]
        )
        problems.append(
            f"{label}: {len(deviations)} 帧锚点位移与声明不符（含 {sample}）"
            "（1.4.143 事故 = 补偿符号做反，位移 -24）"
        )
    removed = sorted(set(before) - {_frame_number(r.get("n", "")) for r in after_tree if isinstance(r, dict)})
    for number in removed:
        if number is not None:
            problems.append(f"{label}: 帧 {number} 在边缘中丢失")
    return {"label": label, "checked": checked, "dx": dx, "dy": dy,
            "keep_frames": sorted(keep), "max_deviation": max_deviation,
            "deviations": deviations, "problems": problems}


# ---------------------------------------------------------------------------
# 4. 解析器契约：声明行强类型字段校验 + 官方先例统计
# ---------------------------------------------------------------------------

_NUMERIC_HINTS = (
    "strength", "threshold", "number.", "frame.", "limit", "cooltime",
    "instant_delay", "initial_multiply", "additional_multiply",
    "max_accumulation",
)
_DIGIT_REQUIRED = frozenset({"kind"})
_BOOL_KEYS = frozenset({"even_if_owner_dead", "by_each_trigger_puller"})
_ENUM_DIGIT_KEYS = frozenset({"target", "trigger_puller", "awake_kind", "awake_level", "element"})
_OPTION_KEYS = frozenset({
    "flip_limit", "power_flip_limit", "end_power_flip_limit",
    "end_power_flip_accepted_levels", "max_accumulation",
})
_ID_KEYS = frozenset({"unique_condition_id", "multiball_group_id",
                      "powerflip_override.id", "powerflip_override.levels",
                      "powerflip_override.description_id", "multiply_trigger",
                      "mt.trigger_limit", "trigger_limit"})
_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# 空列里“官方同语境显式赋值、空串会造成静默 0 / 显示缺陷”的字段：
# 只有这些 (block, key) 的“空”才值得在声明行里报 warning
# （避免对大量合法未用列刷屏）。nullrole 事故 = instant_content.target.
# character_groups(c49) + instant_trigger.character_groups(c36)。
_EMPTY_WARNING_FIELDS = frozenset({
    ("instant_content", "target"),
    ("instant_content", "target.character_groups"),
    ("instant_trigger", "character_groups"),
})


def _cell(row: list[str], index: int) -> str:
    return (row[index] if 0 <= index < len(row) else "").strip()


def _is_digit(value: str) -> bool:
    return bool(value) and value.lstrip("-").isdigit()


def table_kind_for_logical(logical: str) -> str | None:
    path = logical.replace("\\", "/")
    if path.endswith("leader_ability.orderedmap"):
        return "leader_ability"
    if path.endswith("ability.orderedmap"):
        return "ability"
    return None


def _field_class(block: str, key: str) -> str:
    if key in _DIGIT_REQUIRED:
        return "digit-required"
    if key in _BOOL_KEYS:
        return "bool"
    if key in _OPTION_KEYS:
        return "option"
    if key in _ENUM_DIGIT_KEYS:
        return "digit-optional"
    if "character_groups" in key:
        return "token"
    if key in _ID_KEYS:
        return "id"
    if any(hint in key for hint in _NUMERIC_HINTS):
        return "numeric"
    if key == "cancelable":
        return "digit-optional"
    if key in ("string_id", "action_path"):
        return "text"
    return "numeric"


def _classify_cell(cls: str, value: str, label: str, errors: list[str], warnings: list[str]) -> None:
    if value == "":
        # 空列默认静默：官方数据大量未使用列合法为空；只有显式登记的
        # “空串会静默变 0 / 生成空显示”字段才进 warning 清单。
        if cls == "digit-required":
            errors.append(f"{label}={value!r} 须为数字（空串=客户端 C7050）")
        return
    if cls == "digit-required":
        if not _is_digit(value):
            errors.append(f"{label}={value!r} 须为数字")
    elif cls == "bool":
        if value not in BOOLEAN_VALUES:
            errors.append(f"{label}={value!r} 须为 true/false（空串=客户端 C7101）")
    elif cls == "option":
        if value != "(None)" and not _is_digit(value):
            errors.append(f"{label}={value!r} 须为 '(None)' 或数字")
    elif cls == "digit-optional":
        if not _is_digit(value):
            errors.append(f"{label}={value!r} 须为数字")
    elif cls == "id":
        if value != "(None)" and not _is_digit(value):
            errors.append(f"{label}={value!r} 须为 '(None)'/数字/空")
        elif value == "(None)":
            warnings.append(f"{label}='(None)'（该列官方多为空或数字）")
    elif cls == "token":
        if value != "(None)" and not _TOKEN_RE.fullmatch(value):
            errors.append(f"{label}={value!r} 不是合法角色组 token")
    elif cls == "text":
        pass
    else:  # numeric
        if value != "(None)" and not _is_digit(value):
            errors.append(f"{label}={value!r} 不是整数（会被静默读成 0）")
        elif value == "(None)":
            warnings.append(f"{label}='(None)'（普通数值列官方多为数字）")
        elif abs(int(value)) > 2147483647:
            errors.append(f"{label}={value} 超出 32 位整数范围")


def _empty_warning(block: str, key: str, value: str, label: str, warnings: list[str]) -> None:
    if value or (block, key) not in _EMPTY_WARNING_FIELDS:
        return
    if "character_groups" in key:
        warnings.append(f"{label} 为空（被读取时会渲染 null角色/空组文案）")
    else:
        warnings.append(f"{label} 为空（空串会被静默读成 0）")


def typed_row_problems(table_kind: str, row: list[str]) -> dict:
    """声明行强类型字段校验：Bool/枚举/数值/``(None)``。

    errors 覆盖已实锤会让客户端崩溃或静默变 0 的写法：
    Bool 空串（C7101 col72/70）、枚举空串（C7050 col75/73）、
    Option 空串（F1009 col61..65/59..63）、数值列非数字。
    warnings 记录“合法但可疑”的空列（官方先例里通常显式赋值）。
    """
    errors: list[str] = []
    warnings: list[str] = []
    layout = wf_describe.layout(table_kind)
    blocks = {name: int(base) for name, base in layout["blocks"].items()}
    trigger_col = blocks["precondition1"] - 1
    trigger = _cell(row, trigger_col)
    if trigger not in ("0", "1", "2"):
        return {
            "errors": [f"c{trigger_col} trigger={trigger!r} 须为 0/1/2"],
            "warnings": [],
        }

    # 共用规则（C7101/C7050/F1009 实锤类）由 wf_client_legality 提供，
    # 门禁与生成器共用同一实现，避免漂移。
    for message in wf_client_legality.client_legality_problems(table_kind, row):
        errors.append(message)

    for name in ("precondition1", "precondition2", "precondition3"):
        base = blocks[name]
        _classify_cell("digit-required", _cell(row, base), f"c{base} {name}.kind", errors, warnings)
        for offset, key, _desc in wf_describe.enum_map()["block_fields"]["precondition"]:
            if key == "kind":
                continue
            value = _cell(row, base + offset)
            label = f"c{base + offset} precondition.{key}"
            _classify_cell(_field_class("precondition", key), value, label, errors, warnings)
            _empty_warning("precondition", key, value, label, warnings)

    if trigger == "0":
        instant_blocks = ("instant_trigger", "instant_precontent", "instant_delay", "instant_content")
    elif trigger == "1":
        instant_blocks = ("during_accumulation_trigger", "during_trigger",
                          "even_if_owner_dead", "during_content")
    else:
        instant_blocks = ("opening",)

    field_map = wf_describe.enum_map()["block_fields"]
    cases = wf_describe.enum_map().get("cases", {})
    for name in instant_blocks:
        base = blocks[name]
        for offset, key, _desc in field_map.get(name, ()):
            value = _cell(row, base + offset)
            label = f"c{base + offset} {name}.{key}"
            if name == "instant_precontent" and key == "kind":
                if value != "(None)" and not _is_digit(value):
                    errors.append(f"c{base} instant_precontent={value!r} 须为 '(None)' 或数字")
                continue
            if name == "during_accumulation_trigger" and key == "kind":
                if value != "(None)" and not _is_digit(value):
                    errors.append(
                        f"c{base} during_accumulation_trigger={value!r} 须为 '(None)' 或数字"
                    )
                continue
            _classify_cell(_field_class(name, key), value, label, errors, warnings)
            _empty_warning(name, key, value, label, warnings)
            if key == "initial_multiply" and value == "":
                content_kind = _cell(row, blocks.get("instant_content", base))
                parsers = {}
                if name == "instant_content":
                    case = (cases.get("instant_content") or {}).get(content_kind)
                    parsers = (case or {}).get("fields", {}) if isinstance(case, dict) else {}
                if "initial_multiply" in parsers:
                    max_accumulation = _cell(row, base + 14) if name == "instant_content" else ""
                    capped = (
                        max_accumulation in ("", "(None)")
                        or (_is_digit(max_accumulation) and abs(int(max_accumulation)) <= 1)
                    )
                    detail = (
                        f"{label} 为空：该 kind 的客户端解析器读取 initial_multiply，"
                        "空串读成 0"
                    )
                    if capped:
                        errors.append(
                            detail + "；max_accumulation≤1 时描述乘算后显示 +0/0%"
                            "（官方同语境均写 1）"
                        )
                    else:
                        warnings.append(
                            detail + "；本行 max_accumulation>1，显示路径未证明受影响，"
                            "但官方同族行均显式写 1，建议对齐"
                        )
    return {"errors": errors, "warnings": warnings}


def precedent_report(table_kind: str, row: list[str]) -> dict:
    """官方先例统计（同表同语境）：声明行使用的枚举是否有官方先例。

    数据来自 ``ability_enum_map.json`` 的 ``cases`` 与 ``usage_counts``
    （官方全表扫描产物）；``leader`` 键对应 leader_ability 表。
    """
    layout = wf_describe.layout(table_kind)
    blocks = {name: int(base) for name, base in layout["blocks"].items()}
    trigger_col = blocks["precondition1"] - 1
    trigger = _cell(row, trigger_col)
    usage = wf_describe.enum_map().get("usage_counts", {})
    report: dict = {"table_kind": table_kind, "trigger": trigger, "groups": []}
    problems: list[str] = []

    # cases 与 usage_counts 的分组名与块名一致（trigger 总表是突发模式计数，
    # 瞬发触发枚举在 instant_trigger 组）。
    specs = [("precondition1", "precondition")]
    if trigger == "0":
        specs += [("instant_trigger", "instant_trigger"), ("instant_content", "instant_content")]
    elif trigger == "1":
        specs += [("during_trigger", "during_trigger"), ("during_content", "during_content")]
    else:
        specs += [("opening", "opening")]
    table_key = "leader" if table_kind == "leader_ability" else "ability"
    for block, group in specs:
        value = _cell(row, blocks[block])
        counts = usage.get(group, {})
        count = None
        if isinstance(counts, dict):
            per_table = counts.get(table_key)
            if isinstance(per_table, dict):
                count = per_table.get(value)
        cases = wf_describe.enum_map().get("cases", {}).get(group, {})
        case = cases.get(value) if isinstance(cases, dict) else None
        entry = {
            "block": block,
            "enum": group,
            "value": value,
            "official_count": count,
            "ctor": (case or {}).get("ctor") if isinstance(case, dict) else None,
            "field_parsers": sorted((case or {}).get("fields", {})) if isinstance(case, dict) else None,
        }
        report["groups"].append(entry)
        if count == 0:
            problems.append(
                f"{block} kind={value} 在官方 {table_key} 表零先例"
                "（先例原则：同表同语境；请过滤敌方行后确认）"
            )
        elif count is None and case is None:
            problems.append(f"{block} kind={value} 无官方先例数据（枚举未登记）")
    report["problems"] = problems
    return report


def ability_table_problems(
    raw: bytes,
    logical: str,
    *,
    read_orderedmap,
    read_rows,
    declared_rows: dict | None = None,
) -> dict:
    """扫描一张 ability/leader_ability 有序表。

    - 全表只跑「客户端一定会解析到的行」的 Bool/枚举/Option 崩溃类
      （与 ``check_ability_strong_fields.py`` 同源；敌方行为列不消费，
      全量强类型扫描会误报，见 2026-10-06 复核）；
    - ``declared_rows``（``{key: [row_index,...]}`` 或 ``{key: True}``）是
      新角色声明的行：强类型字段校验 + 官方先例统计（fail-closed）。
    """
    table_kind = table_kind_for_logical(logical)
    report: dict = {
        "logical": logical,
        "table_kind": table_kind,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": 0,
        "crash_class_cells": 0,
        "declared": [],
        "problems": [],
        "warnings": [],
    }
    if table_kind is None:
        report["problems"].append(f"无法识别表类型: {logical}")
        return report
    try:
        table = read_orderedmap(raw)
    except Exception as exc:  # noqa: BLE001 - 坏载荷必须失败关闭
        report["problems"].append(f"无法解码 orderedmap: {type(exc).__name__}: {exc}")
        return report
    declared = declared_rows or {}
    layout = wf_describe.layout(table_kind)
    blocks = {name: int(base) for name, base in layout["blocks"].items()}
    trigger_col = blocks["precondition1"] - 1
    dispatch_col = blocks["instant_content"]
    bool_col = dispatch_col + 25
    multiply_col = dispatch_col + 28
    during_col = blocks["even_if_owner_dead"]
    for key, text in table.items():
        rows = read_rows(text)
        for index, row in enumerate(rows):
            report["rows"] += 1
            _crash_class_problems(
                table_kind, row, blocks, trigger_col, dispatch_col,
                bool_col, multiply_col, during_col, report,
                key=key, index=index,
            )
            selection = declared.get(key)
            if selection is True or (
                isinstance(selection, (list, tuple, set)) and index in selection
            ):
                typed = typed_row_problems(table_kind, row)
                precedent = precedent_report(table_kind, row)
                report["declared"].append({
                    "key": key,
                    "row": index,
                    "errors": typed["errors"],
                    "warnings": typed["warnings"],
                    "precedent": precedent,
                })
                for message in typed["errors"]:
                    report["problems"].append(
                        {"key": key, "row": index, "detail": message}
                    )
                for message in typed["warnings"]:
                    report["warnings"].append(
                        {"key": key, "row": index, "detail": message}
                    )
                for message in precedent["problems"]:
                    report["problems"].append(
                        {"key": key, "row": index, "detail": message}
                    )
    return report


def _crash_class_problems(
    table_kind: str,
    row: list[str],
    blocks: dict[str, int],
    trigger_col: int,
    dispatch_col: int,
    bool_col: int,
    multiply_col: int,
    during_col: int,
    report: dict,
    *,
    key: str,
    index: int,
) -> None:
    """check_ability_strong_fields 同源的全表崩溃类规则（player 行才消费）。

    与逐行 ``client_legality_problems`` 的区别：这里不检查 precondition kind
    等“行是否会被客户端加载”的前置条件，敌方/未使用行的空列不参与判定。
    """
    def problem(detail: str) -> None:
        report["problems"].append({"key": key, "row": index, "detail": detail})

    length = max(dispatch_col, bool_col, during_col, multiply_col, trigger_col)
    if len(row) <= length:
        problem(f"短行：{len(row)} 列，至少需要 {length + 1} 列")
        return
    trigger = row[trigger_col].strip()
    if trigger == "1":
        report["crash_class_cells"] += 1
        value = row[during_col].strip()
        if value not in BOOLEAN_VALUES:
            problem(f"c{during_col} even_if_owner_dead={value!r} 须为 true/false（C7101）")
        return
    if trigger != "0":
        if trigger not in ("", "2"):
            problem(f"c{trigger_col} trigger={trigger!r} 未知触发模式")
        return
    content = row[dispatch_col].strip()
    if content in wf_client_legality.INSTANT_CONTENT_BOOL_KINDS:
        report["crash_class_cells"] += 1
        value = row[bool_col].strip()
        if value not in BOOLEAN_VALUES:
            problem(
                f"c{bool_col} by_each_trigger_puller={value!r} 须为 true/false"
                "（空串=客户端 C7101）"
            )
    if content in wf_client_legality.INSTANT_CONTENT_MULTIPLY_KINDS:
        report["crash_class_cells"] += 1
        value = row[multiply_col].strip()
        if value != "(None)" and not _is_digit(value):
            problem(
                f"c{multiply_col} multiply_trigger={value!r} 须为 '(None)' 或数字"
                "（空串=客户端 C7050）"
            )
    for message in wf_client_legality.option_cell_problems(table_kind, row):
        report["crash_class_cells"] += 1
        problem(message)
