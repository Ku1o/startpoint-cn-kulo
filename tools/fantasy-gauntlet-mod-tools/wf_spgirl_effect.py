"""泳装希尔媞（149996）已确认的主动技能特效规则。

本模块只构建离线候选，或改写调用方提供的 Action DSL 字节；不写 CDN、
不生成版本边，也不接触运行镜像。已发布的保守方案把两条斜向残影烘焙进
单个 atlas cell；实验性的完整 X 方案则保留双动画分支，并按并发峰值同步
扩充 ``parts.a`` 叶图片显示对象池。中心风刃、闪光、音效和游戏判定始终各
保留一份。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

import wf_assets
from wf_effect_cell_reskin import (
    ReskinError,
    apply_interleaved_trail_x_layout,
    apply_pool_safe_trail_x_layout,
    atlas_crop,
    build_candidate,
    rewrite_action_dsl,
)


CHARACTER_ID = "149996"
SOURCE_EFFECT_REFERENCE = "battle/effect/skill_unique/wind_spgirl/wind_spgirl"
TARGET_EFFECT_REFERENCE = (
    "battle/effect/skill_unique/wind_spgirl_swim/wind_spgirl_swim"
)
SKILL_DSL_LOGICALS = {
    level: (
        "battle/action/skill/action/rare5/wind_spgirl_swim$"
        f"wind_spgirl_swim_{level}.action.dsl.amf3.deflate"
    )
    for level in (1, 2, 3)
}

REPLACEMENT_CELLS = ("f", "i", "r", "s", "t", "u", "v", "w")
REPLACEMENT_ARCHIVE_SHA256 = (
    "8d37a0bea066b1662a9da27f1552a9973bfe0db2e2fc475d555374e1e46b2f4c"
)

X_LAYOUT_SCOPE = "trail"
X_HALF_ANGLE_DEGREES = 15.0
X_INCLUDED_ANGLE_DEGREES = 30.0
EXPECTED_TARGET_GROUP = 21
EXPECTED_PARENT_GROUP = 2
EXPECTED_MATRIX_INDICES = (703, 704)

EXPECTED_COMPILED_SHA256 = {
    f"{TARGET_EFFECT_REFERENCE}.atlas.amf3.deflate": (
        "a39c96195ddfc28abd68ab88d353b8460a946e6159fed2306c1cfa219ff47cf7"
    ),
    f"{TARGET_EFFECT_REFERENCE}.parts.amf3.deflate": (
        "c1d2846db0091bd5db2069f93e486cd70dd17051126b2d37e8e508807fd64f74"
    ),
    f"{TARGET_EFFECT_REFERENCE}.png": (
        "924c2061c7272bd28d990fc5231318ec3d93b174ec7962d6e1b62f3d3f2f7192"
    ),
    f"{TARGET_EFFECT_REFERENCE}.timeline.amf3.deflate": (
        "101918b8cf6f1b3eba0e446393634c3fe664cbaf483a32c23878ddd994f09a2c"
    ),
}

# 这组哈希只用于识别已经导致 F1125 的旧双分支候选，绝不能直接发布。
UNSAFE_BRANCH_COMPILED_SHA256 = dict(EXPECTED_COMPILED_SHA256)
SAFE_BAKED_TERMINALS = ("w",)
INTERLEAVED_TRAIL_TERMINAL = "w"
INTERLEAVED_TRAIL_SEGMENTS = 26
INTERLEAVED_MATRIX_INDICES = tuple(range(136, 162))
POOL_SAFE_CAPACITY_CHANGES = {
    "f": (3, 6),
    "g": (5, 10),
    "h": (12, 24),
    "i": (3, 6),
    "p": (14, 28),
    "q": (15, 30),
    "r": (2, 4),
    "s": (2, 4),
    "t": (3, 6),
    "u": (2, 4),
    "v": (2, 4),
    "w": (7, 14),
}
SAFE_COMPILED_SHA256 = {
    f"{TARGET_EFFECT_REFERENCE}.atlas.amf3.deflate": (
        "8d4b376295550d17fb14be3890c81eee32af41387c569714a4811f765455a67f"
    ),
    f"{TARGET_EFFECT_REFERENCE}.parts.amf3.deflate": (
        "800542099ab0f5dfea892f250eb025e4ea419d74ad7fef9ee16fd91af64f4730"
    ),
    f"{TARGET_EFFECT_REFERENCE}.png": (
        "d6737857f1610e7a22280ebcad46e1979c62ad65fda1d9564cb4e42e8e7af3f8"
    ),
    f"{TARGET_EFFECT_REFERENCE}.timeline.amf3.deflate": (
        "101918b8cf6f1b3eba0e446393634c3fe664cbaf483a32c23878ddd994f09a2c"
    ),
}
POOL_SAFE_COMPILED_SHA256 = {
    f"{TARGET_EFFECT_REFERENCE}.atlas.amf3.deflate": (
        "a39c96195ddfc28abd68ab88d353b8460a946e6159fed2306c1cfa219ff47cf7"
    ),
    f"{TARGET_EFFECT_REFERENCE}.parts.amf3.deflate": (
        "f0e8ffd851487fddba1900d0ce6cf0f133440f96f737260b4e957132a10661b4"
    ),
    f"{TARGET_EFFECT_REFERENCE}.png": (
        "924c2061c7272bd28d990fc5231318ec3d93b174ec7962d6e1b62f3d3f2f7192"
    ),
    f"{TARGET_EFFECT_REFERENCE}.timeline.amf3.deflate": (
        "101918b8cf6f1b3eba0e446393634c3fe664cbaf483a32c23878ddd994f09a2c"
    ),
}


class SpgirlEffectError(ValueError):
    """149996 特效输入或输出不符合已确认方案。"""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_replacement_archive(path: Path) -> str:
    """只接受用户确认过的 8 部件透明素材包。"""
    if not path.is_file():
        raise SpgirlEffectError(f"149996 主动技部件包不存在: {path}")
    digest = _sha256_file(path)
    if digest != REPLACEMENT_ARCHIVE_SHA256:
        raise SpgirlEffectError(
            "149996 主动技部件包哈希漂移: "
            f"expected={REPLACEMENT_ARCHIVE_SHA256}, actual={digest}"
        )
    return digest


def patch_skill_effect_reference(
    raw: bytes,
    logical: str,
) -> tuple[bytes, dict[str, Any]]:
    """把一档 149996 主动技从原版希尔媞特效切到专用窄 X 特效。"""
    if logical not in SKILL_DSL_LOGICALS.values():
        raise SpgirlEffectError(f"不是149996主动技 DSL: {logical}")
    level = next(level for level, value in SKILL_DSL_LOGICALS.items() if value == logical)
    try:
        output, replacements = rewrite_action_dsl(
            raw,
            source_reference=SOURCE_EFFECT_REFERENCE,
            target_reference=TARGET_EFFECT_REFERENCE,
        )
    except ReskinError as error:
        raise SpgirlEffectError(str(error)) from error
    if replacements != 1:
        raise AssertionError(f"149996 主动技{level}特效引用替换数不是1")
    return output, {
        "character_id": CHARACTER_ID,
        "level": level,
        "source_reference": SOURCE_EFFECT_REFERENCE,
        "target_reference": TARGET_EFFECT_REFERENCE,
        "replacements": replacements,
        "gameplay_geometry_changed": False,
        "writes_live": False,
    }


def validate_confirmed_report(report: dict[str, Any]) -> None:
    """验证构建结果仍与用户确认的 30°窄 X 方案完全相符。"""
    expected_scalars = {
        "mode": "offline-candidate-only",
        "writes_live": False,
        "source_reference": SOURCE_EFFECT_REFERENCE,
        "target_reference": TARGET_EFFECT_REFERENCE,
        "atlas_records": 25,
        "anchor_metadata_preserved": True,
        "timeline_plain_bytes_identical": True,
    }
    for key, expected in expected_scalars.items():
        if report.get(key) != expected:
            raise SpgirlEffectError(
                f"149996 主动技候选字段漂移: {key}={report.get(key)!r}, "
                f"expected={expected!r}"
            )

    if tuple(report.get("replaced_cells", ())) != REPLACEMENT_CELLS:
        raise SpgirlEffectError("149996 主动技替换部件集合或顺序漂移")

    layout = report.get("visual_layout") or {}
    expected_layout = {
        "kind": "narrow-x-trail",
        "scope": "isolated-character-trail",
        "branch_count": 2,
        "half_angle_degrees": X_HALF_ANGLE_DEGREES,
        "top_bottom_included_angle_degrees": X_INCLUDED_ANGLE_DEGREES,
        "target_group": EXPECTED_TARGET_GROUP,
        "parent_group": EXPECTED_PARENT_GROUP,
        "matrix_indices": list(EXPECTED_MATRIX_INDICES),
        "sound_instances": 1,
        "central_effect_instances": 1,
        "gameplay_geometry_changed": False,
    }
    if layout != expected_layout:
        raise SpgirlEffectError("149996 主动技窄X布局漂移")

    compiled = {
        str(row.get("logical")): str(row.get("sha256"))
        for row in report.get("compiled", ())
    }
    if compiled != EXPECTED_COMPILED_SHA256:
        raise SpgirlEffectError("149996 主动技编译资源哈希漂移")

    action_rows = report.get("action_dsl", ())
    expected_files = {f"{level}.action.dsl.amf3.deflate" for level in (1, 2, 3)}
    if {str(row.get("file")) for row in action_rows} != expected_files:
        raise SpgirlEffectError("149996 主动技三档 DSL 文件集合漂移")
    if any(int(row.get("replacements", 0)) != 1 for row in action_rows):
        raise SpgirlEffectError("149996 主动技 DSL 特效引用替换数漂移")


def _compiled_path(root: Path, logical: str) -> Path:
    return root / "compiled-logical" / Path(*logical.split("/"))


def _topology_signature(parts: dict[str, Any]) -> dict[str, Any]:
    groups = parts.get("g")
    matrices = parts.get("t")
    images = parts.get("i")
    if not isinstance(groups, list) or not isinstance(matrices, list) or not isinstance(images, list):
        raise SpgirlEffectError("149996 Flatomo parts 结构不完整")
    return {
        "groups": len(groups),
        "segments": sum(len(group.get("s", ())) for group in groups),
        "matrices": len(matrices),
        "images": len(images),
        "group_segment_counts": [len(group.get("s", ())) for group in groups],
    }


def _normalize_target_parts_paths(parts: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(parts))
    source_prefix = SOURCE_EFFECT_REFERENCE.rsplit("/", 1)[0] + "/.gen/wind_spgirl/"
    target_prefix = TARGET_EFFECT_REFERENCE.rsplit("/", 1)[0] + "/.gen/wind_spgirl_swim/"
    for record in value.get("i", ()):
        path = str(record.get("p", ""))
        if not path.startswith(target_prefix):
            raise SpgirlEffectError(f"149996 安全特效出现未知图片路径: {path}")
        record["p"] = source_prefix + path.rsplit("/", 1)[-1]
    return value


def validate_runtime_safe_candidate(
    report: dict[str, Any],
    *,
    source_parts: dict[str, Any],
    target_parts: dict[str, Any],
) -> dict[str, Any]:
    """Require byte-semantic Flatomo topology equality with the original effect."""
    expected_scalars = {
        "mode": "offline-candidate-only",
        "writes_live": False,
        "source_reference": SOURCE_EFFECT_REFERENCE,
        "target_reference": TARGET_EFFECT_REFERENCE,
        "atlas_records": 25,
        "anchor_metadata_preserved": True,
        "timeline_plain_bytes_identical": True,
    }
    for key, expected in expected_scalars.items():
        if report.get(key) != expected:
            raise SpgirlEffectError(f"149996 安全候选字段漂移: {key}")
    if tuple(report.get("replaced_cells", ())) != REPLACEMENT_CELLS:
        raise SpgirlEffectError("149996 安全候选替换部件集合漂移")
    layout = report.get("visual_layout") or {}
    expected_layout = {
        "kind": "baked-raster-x",
        "scope": "atlas-cells",
        "visual_branch_count": 2,
        "runtime_branch_count": 1,
        "half_angle_degrees": X_HALF_ANGLE_DEGREES,
        "top_bottom_included_angle_degrees": X_INCLUDED_ANGLE_DEGREES,
        "baked_terminals": list(SAFE_BAKED_TERMINALS),
        "parts_topology_unchanged": True,
        "groups_added": 0,
        "segments_added": 0,
        "matrices_added": 0,
        "sound_instances": 1,
        "central_effect_instances": 1,
        "gameplay_geometry_changed": False,
    }
    for key, expected in expected_layout.items():
        if layout.get(key) != expected:
            raise SpgirlEffectError(f"149996 安全 X 布局漂移: {key}")
    if report.get("action_dsl"):
        raise SpgirlEffectError("1.4.89 安全特效不应重复改写149996主动技 DSL")
    compiled = {
        str(row.get("logical")): str(row.get("sha256"))
        for row in report.get("compiled", ())
    }
    if compiled != SAFE_COMPILED_SHA256:
        raise SpgirlEffectError("149996 安全特效编译资源哈希漂移")

    source_signature = _topology_signature(source_parts)
    target_signature = _topology_signature(target_parts)
    if source_signature != target_signature:
        raise SpgirlEffectError(
            f"149996 安全特效 Flatomo 拓扑漂移: {target_signature} != {source_signature}"
        )
    if _normalize_target_parts_paths(target_parts) != source_parts:
        raise SpgirlEffectError("149996 安全特效 parts 除图片路径外仍有变化")
    return source_signature


def _recover_replacements_from_unsafe_candidate(
    unsafe_candidate: Path,
) -> dict[str, Image.Image]:
    """Recover only the eight accepted cells from the rejected X candidate."""
    unsafe_report_path = unsafe_candidate / "candidate-report.json"
    if not unsafe_report_path.is_file():
        raise SpgirlEffectError("缺少149996旧双分支候选报告")
    unsafe_report = json.loads(unsafe_report_path.read_text(encoding="utf-8-sig"))
    validate_confirmed_report(unsafe_report)
    for logical, expected in UNSAFE_BRANCH_COMPILED_SHA256.items():
        path = _compiled_path(unsafe_candidate, logical)
        if not path.is_file() or _sha256_file(path) != expected:
            raise SpgirlEffectError(f"149996旧双分支候选资源漂移: {logical}")

    atlas_path = unsafe_candidate / "decoded" / "wind_spgirl_swim.atlas.json"
    sheet_path = _compiled_path(
        unsafe_candidate, f"{TARGET_EFFECT_REFERENCE}.png"
    )
    unsafe_atlas = json.loads(atlas_path.read_text(encoding="utf-8-sig"))
    with Image.open(io.BytesIO(wf_assets.png_decode(sheet_path.read_bytes()))) as opened:
        unsafe_sheet = opened.convert("RGBA")
    replacements = {
        str(entry["n"]).rsplit("/", 1)[-1]: atlas_crop(unsafe_sheet, entry)
        for entry in unsafe_atlas
        if str(entry["n"]).rsplit("/", 1)[-1] in REPLACEMENT_CELLS
    }
    if tuple(sorted(replacements)) != tuple(sorted(REPLACEMENT_CELLS)):
        raise SpgirlEffectError("无法从旧候选完整回收8个泳装特效部件")
    return replacements


def build_runtime_safe_candidate(
    *,
    source_effect_root: Path,
    unsafe_candidate: Path,
    output: Path,
) -> dict[str, Any]:
    """Convert the rejected two-branch candidate into a one-branch baked X."""
    replacements = _recover_replacements_from_unsafe_candidate(unsafe_candidate)

    try:
        report = build_candidate(
            source_effect_root=source_effect_root,
            replacement_source=None,
            replacement_images=replacements,
            target_reference=TARGET_EFFECT_REFERENCE,
            output=output,
            source_reference=SOURCE_EFFECT_REFERENCE,
            x_half_angle_degrees=X_HALF_ANGLE_DEGREES,
            x_layout_scope="baked",
            x_baked_terminals=set(SAFE_BAKED_TERMINALS),
        )
    except ReskinError as error:
        raise SpgirlEffectError(str(error)) from error

    source_parts = json.loads(
        (
            source_effect_root
            / "decoded"
            / f"{source_effect_root.name}.parts.json"
        ).read_text(encoding="utf-8-sig")
    )
    target_parts = json.loads(
        (output / "decoded" / "wind_spgirl_swim.parts.json").read_text(
            encoding="utf-8-sig"
        )
    )
    topology = validate_runtime_safe_candidate(
        report,
        source_parts=source_parts,
        target_parts=target_parts,
    )
    compiled = {
        str(row["logical"]): str(row["sha256"])
        for row in report.get("compiled", ())
    }
    selection = {
        "mode": "runtime-safe-baked-source-rule",
        "writes_live": False,
        "validation_status": "offline_verified_device_pending",
        "device_validation_required_before_reuse_baseline": True,
        "character_id": CHARACTER_ID,
        "source_effect_reference": SOURCE_EFFECT_REFERENCE,
        "target_effect_reference": TARGET_EFFECT_REFERENCE,
        "recovered_from_rejected_candidate": True,
        "replacement_cells": list(REPLACEMENT_CELLS),
        "baked_cells": list(SAFE_BAKED_TERMINALS),
        "layout": report["visual_layout"],
        "flatomo_topology": topology,
        "compiled_sha256": compiled,
    }
    (output / "confirmed-selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"candidate": report, "selection": selection}


def build_interleaved_runtime_safe_candidate(
    *,
    source_effect_root: Path,
    unsafe_candidate: Path,
    output: Path,
) -> dict[str, Any]:
    """Build a true X path by redistributing the original trail stamps.

    This keeps every Flatomo object count unchanged.  It only rotates and
    translates the 26 matrices already owned exclusively by the original
    vertical trail, alternating them between the two diagonal arms.
    """
    replacements = _recover_replacements_from_unsafe_candidate(unsafe_candidate)

    try:
        report = build_candidate(
            source_effect_root=source_effect_root,
            replacement_source=None,
            replacement_images=replacements,
            target_reference=TARGET_EFFECT_REFERENCE,
            output=output,
            source_reference=SOURCE_EFFECT_REFERENCE,
            x_half_angle_degrees=X_HALF_ANGLE_DEGREES,
            x_layout_scope="interleaved",
            x_interleaved_terminal=INTERLEAVED_TRAIL_TERMINAL,
        )
    except ReskinError as error:
        raise SpgirlEffectError(str(error)) from error

    source_parts = json.loads(
        (
            source_effect_root
            / "decoded"
            / f"{source_effect_root.name}.parts.json"
        ).read_text(encoding="utf-8-sig")
    )
    target_parts = json.loads(
        (output / "decoded" / "wind_spgirl_swim.parts.json").read_text(
            encoding="utf-8-sig"
        )
    )
    source_signature = _topology_signature(source_parts)
    target_signature = _topology_signature(target_parts)
    if source_signature != target_signature:
        raise SpgirlEffectError(
            f"149996交错X特效拓扑漂移: {target_signature} != {source_signature}"
        )
    expected_parts, expected_layout = apply_interleaved_trail_x_layout(
        source_parts,
        half_angle_degrees=X_HALF_ANGLE_DEGREES,
        trail_terminal=INTERLEAVED_TRAIL_TERMINAL,
    )
    if _normalize_target_parts_paths(target_parts) != expected_parts:
        raise SpgirlEffectError("149996交错X特效出现矩阵目标之外的 parts 变化")
    layout = report.get("visual_layout") or {}
    required_layout = {
        "kind": "interleaved-trail-x",
        "scope": "existing-trail-stamps",
        "visual_branch_count": 2,
        "runtime_branch_count": 1,
        "target_group": EXPECTED_TARGET_GROUP,
        "trail_segments": INTERLEAVED_TRAIL_SEGMENTS,
        "branch_stamp_counts": {"negative": 13, "positive": 13},
        "matrix_indices": list(INTERLEAVED_MATRIX_INDICES),
        "groups_added": 0,
        "segments_added": 0,
        "images_added": 0,
        "matrices_added": 0,
        "matrices_modified": INTERLEAVED_TRAIL_SEGMENTS,
        "visible_instance_budget_unchanged": True,
        "gameplay_geometry_changed": False,
    }
    for key, expected in required_layout.items():
        if layout.get(key) != expected or expected_layout.get(key) != expected:
            raise SpgirlEffectError(f"149996交错X布局漂移: {key}")
    if report.get("action_dsl"):
        raise SpgirlEffectError("交错X离线预览不应重复改写149996主动技 DSL")

    compiled = {
        str(row["logical"]): str(row["sha256"])
        for row in report.get("compiled", ())
    }
    selection = {
        "mode": "runtime-safe-interleaved-source-rule",
        "writes_live": False,
        "validation_status": "offline_preview_only",
        "device_validation_required_before_reuse_baseline": True,
        "character_id": CHARACTER_ID,
        "source_effect_reference": SOURCE_EFFECT_REFERENCE,
        "target_effect_reference": TARGET_EFFECT_REFERENCE,
        "recovered_from_rejected_candidate": True,
        "replacement_cells": list(REPLACEMENT_CELLS),
        "layout": layout,
        "flatomo_topology": source_signature,
        "compiled_sha256": compiled,
    }
    (output / "confirmed-selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"candidate": report, "selection": selection}


def build_pool_safe_full_x_candidate(
    *,
    source_effect_root: Path,
    unsafe_candidate: Path,
    output: Path,
) -> dict[str, Any]:
    """Restore the original full-density X with corrected image pools."""
    replacements = _recover_replacements_from_unsafe_candidate(unsafe_candidate)
    try:
        report = build_candidate(
            source_effect_root=source_effect_root,
            replacement_source=None,
            replacement_images=replacements,
            target_reference=TARGET_EFFECT_REFERENCE,
            output=output,
            source_reference=SOURCE_EFFECT_REFERENCE,
            x_half_angle_degrees=X_HALF_ANGLE_DEGREES,
            x_layout_scope="pool-safe",
        )
    except ReskinError as error:
        raise SpgirlEffectError(str(error)) from error

    source_parts = json.loads(
        (
            source_effect_root
            / "decoded"
            / f"{source_effect_root.name}.parts.json"
        ).read_text(encoding="utf-8-sig")
    )
    target_parts = json.loads(
        (output / "decoded" / "wind_spgirl_swim.parts.json").read_text(
            encoding="utf-8-sig"
        )
    )
    expected_parts, expected_layout = apply_pool_safe_trail_x_layout(
        source_parts,
        half_angle_degrees=X_HALF_ANGLE_DEGREES,
        replacement_terminals=set(REPLACEMENT_CELLS),
    )
    if _normalize_target_parts_paths(target_parts) != expected_parts:
        raise SpgirlEffectError("149996对象池安全X出现源规则之外的 parts 变化")
    layout = report.get("visual_layout") or {}
    if layout != expected_layout:
        raise SpgirlEffectError("149996对象池安全X布局报告与源规则不一致")
    if report.get("action_dsl"):
        raise SpgirlEffectError("对象池安全X离线预览不应重复改写149996主动技 DSL")

    pool_changes = {
        str(row["terminal"]): (int(row["before"]), int(row["after"]))
        for row in layout.get("object_pool_changes", ())
    }
    if pool_changes != POOL_SAFE_CAPACITY_CHANGES:
        raise SpgirlEffectError("149996对象池容量变化集合漂移")
    expected_layout_fields = {
        "kind": "pool-safe-narrow-x-trail",
        "scope": "isolated-character-trail",
        "branch_count": 2,
        "half_angle_degrees": X_HALF_ANGLE_DEGREES,
        "top_bottom_included_angle_degrees": X_INCLUDED_ANGLE_DEGREES,
        "target_group": EXPECTED_TARGET_GROUP,
        "parent_group": EXPECTED_PARENT_GROUP,
        "matrix_indices": list(EXPECTED_MATRIX_INDICES),
        "object_pool_entries": 25,
        "object_pool_entries_changed": len(POOL_SAFE_CAPACITY_CHANGES),
        "object_pool_capacity_before": 297,
        "object_pool_capacity_after": 367,
        "source_visible_instance_peak": 191,
        "target_visible_instance_peak": 238,
        "groups_added": 0,
        "segments_added": 1,
        "matrices_added": 2,
        "image_records_added": 0,
        "full_trail_density_per_branch": True,
        "sound_instances": 1,
        "central_effect_instances": 1,
        "gameplay_geometry_changed": False,
    }
    for key, expected in expected_layout_fields.items():
        if layout.get(key) != expected:
            raise SpgirlEffectError(f"149996对象池安全X字段漂移: {key}")

    source_signature = _topology_signature(source_parts)
    target_signature = _topology_signature(target_parts)
    expected_signature = {
        **source_signature,
        "segments": source_signature["segments"] + 1,
        "matrices": source_signature["matrices"] + 2,
        "group_segment_counts": list(source_signature["group_segment_counts"]),
    }
    expected_signature["group_segment_counts"][EXPECTED_PARENT_GROUP] += 1
    if target_signature != expected_signature:
        raise SpgirlEffectError(
            f"149996对象池安全X拓扑漂移: {target_signature} != {expected_signature}"
        )

    compiled = {
        str(row["logical"]): str(row["sha256"])
        for row in report.get("compiled", ())
    }
    if compiled != POOL_SAFE_COMPILED_SHA256:
        raise SpgirlEffectError("149996对象池安全X编译资源哈希漂移")
    selection = {
        "mode": "pool-safe-full-density-x-experiment",
        "writes_live": False,
        "validation_status": "offline_verified_device_pending",
        "device_validation_required_before_reuse_baseline": True,
        "character_id": CHARACTER_ID,
        "source_effect_reference": SOURCE_EFFECT_REFERENCE,
        "target_effect_reference": TARGET_EFFECT_REFERENCE,
        "recovered_from_rejected_candidate": True,
        "replacement_cells": list(REPLACEMENT_CELLS),
        "root_cause": "parts.a image display-object pool was not resized",
        "layout": layout,
        "source_flatomo_topology": source_signature,
        "target_flatomo_topology": target_signature,
        "compiled_sha256": compiled,
    }
    (output / "confirmed-selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"candidate": report, "selection": selection}


def build_confirmed_candidate(
    *,
    source_effect_root: Path,
    replacement_archive: Path,
    action_dsl_dir: Path,
    output: Path,
    sound_store: Path | None = None,
) -> dict[str, Any]:
    """构建并锁验 149996 的最终离线主动技特效候选。"""
    archive_sha256 = validate_replacement_archive(replacement_archive)
    try:
        report = build_candidate(
            source_effect_root=source_effect_root,
            replacement_source=replacement_archive,
            target_reference=TARGET_EFFECT_REFERENCE,
            output=output,
            action_dsl_dir=action_dsl_dir,
            source_reference=SOURCE_EFFECT_REFERENCE,
            sound_store=sound_store,
            x_half_angle_degrees=X_HALF_ANGLE_DEGREES,
            x_layout_scope=X_LAYOUT_SCOPE,
        )
    except ReskinError as error:
        raise SpgirlEffectError(str(error)) from error
    validate_confirmed_report(report)

    selection = {
        "mode": "confirmed-offline-source-rule",
        "writes_live": False,
        "validation_status": "offline_verified_device_pending",
        "device_validation_required_before_reuse_baseline": True,
        "character_id": CHARACTER_ID,
        "source_effect_reference": SOURCE_EFFECT_REFERENCE,
        "target_effect_reference": TARGET_EFFECT_REFERENCE,
        "replacement_archive_sha256": archive_sha256,
        "replacement_cells": list(REPLACEMENT_CELLS),
        "layout": {
            "scope": "isolated-character-trail",
            "branches": 2,
            "half_angle_degrees": X_HALF_ANGLE_DEGREES,
            "included_angle_degrees": X_INCLUDED_ANGLE_DEGREES,
        },
        "central_effect_instances": 1,
        "sound_instances": 1,
        "gameplay_geometry_changed": False,
        "candidate_report": "candidate-report.json",
        "compiled_sha256": EXPECTED_COMPILED_SHA256,
        "action_dsl_sha256": {
            str(row["file"]): str(row["sha256"])
            for row in report["action_dsl"]
        },
    }
    target = output / "confirmed-selection.json"
    target.write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"candidate": report, "selection": selection}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the confirmed offline active-skill effect for character 149996"
    )
    parser.add_argument("--source-effect-root", type=Path, required=True)
    parser.add_argument("--replacements", type=Path)
    parser.add_argument("--repair-unsafe-candidate", type=Path)
    parser.add_argument("--action-dsl-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sound-store", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.repair_unsafe_candidate is not None:
            if args.replacements is not None:
                raise SpgirlEffectError(
                    "安全修复模式不能同时传入 --replacements"
                )
            result = build_runtime_safe_candidate(
                source_effect_root=args.source_effect_root,
                unsafe_candidate=args.repair_unsafe_candidate,
                output=args.output,
            )
        else:
            if args.replacements is None:
                raise SpgirlEffectError("普通构建模式必须传入 --replacements")
            result = build_confirmed_candidate(
                source_effect_root=args.source_effect_root,
                replacement_archive=args.replacements,
                action_dsl_dir=args.action_dsl_dir,
                output=args.output,
                sound_store=args.sound_store,
            )
    except (OSError, SpgirlEffectError) as error:
        print(f"[ERR] {error}")
        return 2
    print(json.dumps(result["selection"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
