#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clone a Flatomo effect and replace an explicit set of atlas cells.

The command only writes to an explicit ordinary output directory.  It refuses
CDN/runtime/store-like destinations and never publishes, imports, or updates a
manifest.  Output PNG payloads under ``compiled-logical`` are in game storage
form; human-viewable files are placed under ``preview``.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
import re
import zlib
import zipfile
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

import wf_assets
import wf_dsl
from wf_flatomo_preview_render import flatomo_instance_profile, render_flatomo_gif


CELL_FILE = re.compile(r"FX\d+_([A-Za-z0-9_.-]+)\.png\Z", re.IGNORECASE)
SAFE_LOGICAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
GUTTER = 1
SHEET_WIDTH = 256


class ReskinError(ValueError):
    pass


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _standard_png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=9)
    return stream.getvalue()


def _raw_deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(level=9, wbits=-15)
    return compressor.compress(data) + compressor.flush()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _u32(value: int | float) -> int:
    return int(value) & 0xFFFFFFFF


def _validate_logical_base(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    if not normalized or any(not SAFE_LOGICAL.fullmatch(part) for part in normalized.split("/")):
        raise ReskinError("target reference must be a normalized relative logical path")
    if normalized.count("/") < 2:
        raise ReskinError("target reference is unexpectedly shallow")
    return normalized


def _safe_output(path: Path) -> Path:
    resolved = path.resolve()
    folded = str(resolved).replace("\\", "/").casefold()
    forbidden = (
        "/.cdn/",
        "/startpoint-cn-main/",
        "/assets/asset-patch/production/",
        "/production/upload/",
        "/production/medium_upload/",
        "/production/android_upload/",
        "/production/ios_upload/",
    )
    if any(marker in folded + "/" for marker in forbidden):
        raise ReskinError("output must not be a CDN, runtime mirror, or asset-store directory")
    return resolved


def atlas_crop(sheet: Image.Image, entry: dict[str, Any]) -> Image.Image:
    x, y = int(entry["x"]), int(entry["y"])
    width, height = int(entry["w"]), int(entry["h"])
    if width < 1 or height < 1 or x < 0 or y < 0 or x + width > sheet.width or y + height > sheet.height:
        raise ReskinError(f"atlas cell is outside the sheet: {entry.get('n')}")
    crop = sheet.crop((x, y, x + width, y + height))
    if entry.get("r", False):
        crop = crop.transpose(Image.Transpose.ROTATE_90)
    return crop


def load_replacements(source: Path | str) -> dict[str, Image.Image]:
    """Load FXnn_<atlas-terminal>.png files from a directory or ZIP."""
    path = Path(source)
    payloads: list[tuple[str, bytes]] = []
    if path.is_dir():
        payloads = [(item.name, item.read_bytes()) for item in sorted(path.glob("*.png"))]
    elif path.is_file() and path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename.casefold()):
                if info.is_dir():
                    continue
                payloads.append((Path(info.filename).name, archive.read(info)))
    else:
        raise ReskinError("replacement source must be a directory or ZIP")
    replacements: dict[str, Image.Image] = {}
    for filename, raw in payloads:
        match = CELL_FILE.fullmatch(filename)
        if not match:
            raise ReskinError(f"unexpected replacement filename: {filename}")
        terminal = match.group(1)
        if terminal in replacements:
            raise ReskinError(f"duplicate replacement cell: {terminal}")
        try:
            with Image.open(io.BytesIO(raw)) as opened:
                if opened.format != "PNG":
                    raise ReskinError(f"replacement is not PNG: {filename}")
                image = opened.convert("RGBA")
        except OSError as error:
            raise ReskinError(f"invalid replacement PNG: {filename}") from error
        if image.getchannel("A").getbbox() is None:
            raise ReskinError(f"replacement is fully transparent: {filename}")
        replacements[terminal] = image
    if not replacements:
        raise ReskinError("replacement source contains no cells")
    return replacements


def _terminal(entry: dict[str, Any]) -> str:
    value = str(entry.get("n", ""))
    terminal = value.rsplit("/", 1)[-1]
    if not terminal:
        raise ReskinError("atlas record has an empty name")
    return terminal


def _validate_frame_fit(entry: dict[str, Any], image: Image.Image) -> None:
    frame_width = int(entry.get("fw", image.width))
    frame_height = int(entry.get("fh", image.height))
    left = -int(entry.get("fx", 0))
    top = -int(entry.get("fy", 0))
    if left < 0 or top < 0 or left + image.width > frame_width or top + image.height > frame_height:
        raise ReskinError(
            f"replacement {_terminal(entry)} ({image.width}x{image.height}) does not fit "
            f"its {frame_width}x{frame_height} logical frame at ({left},{top})"
        )


def bake_rotated_x_cell(
    entry: dict[str, Any],
    image: Image.Image,
    *,
    half_angle_degrees: float,
) -> tuple[Image.Image, dict[str, Any], dict[str, Any]]:
    """Bake two rotated visual branches into one atlas cell.

    The rotation pivot is the Flatomo logical-frame origin, not the cropped PNG
    center.  The returned atlas record keeps the same logical frame size while
    updating only the transparent trim offsets.  No parts group, segment, image
    record, or transform matrix is added at runtime.
    """
    if isinstance(half_angle_degrees, bool) or not isinstance(
        half_angle_degrees, (int, float)
    ):
        raise ReskinError("baked X half-angle must be numeric")
    half_angle = float(half_angle_degrees)
    if not 5.0 <= half_angle <= 30.0:
        raise ReskinError("baked X half-angle must be from 5 to 30 degrees")

    frame_width = int(entry.get("fw", image.width))
    frame_height = int(entry.get("fh", image.height))
    left = -int(entry.get("fx", 0))
    top = -int(entry.get("fy", 0))
    if (
        frame_width < 1
        or frame_height < 1
        or left < 0
        or top < 0
        or left + image.width > frame_width
        or top + image.height > frame_height
    ):
        raise ReskinError(f"baked X source cell does not fit its logical frame: {_terminal(entry)}")

    # Work on a padded canvas so clipping is detected before trimming back to
    # the original logical frame.
    padding = max(frame_width, frame_height)
    canvas = Image.new(
        "RGBA",
        (frame_width + padding * 2, frame_height + padding * 2),
        (0, 0, 0, 0),
    )
    canvas.alpha_composite(image, (padding + left, padding + top))
    pivot = (padding + left, padding + top)
    baked = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    for angle in (-half_angle, half_angle):
        branch = canvas.rotate(
            angle,
            resample=Image.Resampling.BICUBIC,
            center=pivot,
            expand=False,
        )
        baked.alpha_composite(branch)

    bounds = baked.getchannel("A").getbbox()
    if bounds is None:
        raise ReskinError(f"baked X produced a transparent cell: {_terminal(entry)}")
    frame_box = (
        padding,
        padding,
        padding + frame_width,
        padding + frame_height,
    )
    if (
        bounds[0] < frame_box[0]
        or bounds[1] < frame_box[1]
        or bounds[2] > frame_box[2]
        or bounds[3] > frame_box[3]
    ):
        raise ReskinError(f"baked X exceeds the logical frame: {_terminal(entry)}")

    logical = baked.crop(frame_box)
    logical_bounds = logical.getchannel("A").getbbox()
    if logical_bounds is None:
        raise ReskinError(f"baked X logical frame is transparent: {_terminal(entry)}")
    cropped = logical.crop(logical_bounds)
    patched_entry = copy.deepcopy(entry)
    patched_entry["fx"] = -logical_bounds[0]
    patched_entry["fy"] = -logical_bounds[1]
    patched_entry["fw"] = frame_width
    patched_entry["fh"] = frame_height
    return cropped, patched_entry, {
        "terminal": _terminal(entry),
        "visual_branch_count": 2,
        "runtime_branch_count": 1,
        "half_angle_degrees": half_angle,
        "top_bottom_included_angle_degrees": half_angle * 2.0,
        "logical_frame": [frame_width, frame_height],
        "trim_before": [left, top, image.width, image.height],
        "trim_after": [
            logical_bounds[0],
            logical_bounds[1],
            cropped.width,
            cropped.height,
        ],
    }


def _pack_cells(
    entries: list[dict[str, Any]],
    cells: dict[str, Image.Image],
    *,
    target_cell_prefix: str,
) -> tuple[Image.Image, list[dict[str, Any]]]:
    placements: list[tuple[dict[str, Any], Image.Image, int, int]] = []
    x = y = GUTTER
    row_height = 0
    for original in entries:
        terminal = _terminal(original)
        image = cells[terminal]
        if image.width + 2 * GUTTER > SHEET_WIDTH:
            raise ReskinError(f"cell is wider than the fixed output sheet: {terminal}")
        if x + image.width + GUTTER > SHEET_WIDTH:
            x = GUTTER
            y += row_height + GUTTER
            row_height = 0
        placements.append((original, image, x, y))
        x += image.width + GUTTER
        row_height = max(row_height, image.height)
    sheet_height = y + row_height + GUTTER
    sheet = Image.new("RGBA", (SHEET_WIDTH, sheet_height), (0, 0, 0, 0))
    atlas: list[dict[str, Any]] = []
    for original, image, left, top in placements:
        terminal = _terminal(original)
        sheet.alpha_composite(image, (left, top))
        record = copy.deepcopy(original)
        record["n"] = f"{target_cell_prefix}/{terminal}"
        record["x"] = left
        record["y"] = top
        record["w"] = image.width
        record["h"] = image.height
        record.pop("r", None)
        atlas.append(record)
    return sheet, atlas


def _replace_exact_strings(value: Any, old: str, new: str) -> int:
    count = 0
    if isinstance(value, list):
        for index, item in enumerate(value):
            if item == old:
                value[index] = new
                count += 1
            else:
                count += _replace_exact_strings(item, old, new)
    elif isinstance(value, dict):
        for key, item in list(value.items()):
            if item == old:
                value[key] = new
                count += 1
            else:
                count += _replace_exact_strings(item, old, new)
    return count


def apply_root_x_layout(
    parts: dict[str, Any],
    *,
    half_angle_degrees: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Duplicate an identity-root effect at +/- angle without changing its timeline.

    Flatomo matrix values are 12-bit fixed point.  The locked identity-root gate
    makes the change fail closed instead of accidentally rotating an effect that
    already has a meaningful root transform.
    """
    if isinstance(half_angle_degrees, bool) or not isinstance(half_angle_degrees, (int, float)):
        raise ReskinError("X half-angle must be numeric")
    half_angle = float(half_angle_degrees)
    if not 5.0 <= half_angle <= 30.0:
        raise ReskinError("X half-angle must be from 5 to 30 degrees")
    result = copy.deepcopy(parts)
    groups = result.get("g")
    matrices = result.get("t")
    if not isinstance(groups, list) or not groups or not isinstance(matrices, list):
        raise ReskinError("parts has no usable root group or matrix table")
    root = groups[0]
    segments = root.get("s") if isinstance(root, dict) else None
    if not isinstance(segments, list) or len(segments) != 1:
        raise ReskinError("X layout requires exactly one source segment in the root group")
    source_segment = segments[0]
    keys = source_segment.get("l") if isinstance(source_segment, dict) else None
    if not isinstance(keys, list) or not keys:
        raise ReskinError("X layout root segment has no transform keys")
    for key in keys:
        packed = int(key.get("m", -1))
        matrix_index = packed >> 12
        if matrix_index < 0 or matrix_index >= len(matrices):
            raise ReskinError("X layout root matrix index is invalid")
        matrix = matrices[matrix_index]
        identity = {"a": 4096, "b": 0, "c": 0, "d": 4096, "x": 0, "y": 0}
        if any(int(matrix.get(name, 0)) != value for name, value in identity.items()):
            raise ReskinError("X layout only accepts an identity root transform")
    branch_segments = []
    matrix_indices = []
    for angle in (-half_angle, half_angle):
        radians = math.radians(angle)
        cosine = round(math.cos(radians) * 4096)
        sine = round(math.sin(radians) * 4096)
        matrix_index = len(matrices)
        matrices.append({
            "a": cosine,
            "b": sine,
            "c": -sine,
            "d": cosine,
            "x": 0,
            "y": 0,
        })
        matrix_indices.append(matrix_index)
        segment = copy.deepcopy(source_segment)
        for key in segment["l"]:
            alpha_blend = int(key["m"]) & 0x0FFF
            key["m"] = matrix_index * 4096 + alpha_blend
        branch_segments.append(segment)
    root["s"] = branch_segments
    return result, {
        "kind": "narrow-x",
        "branch_count": 2,
        "half_angle_degrees": half_angle,
        "top_bottom_included_angle_degrees": half_angle * 2.0,
        "matrix_indices": matrix_indices,
        "sound_instances": 1,
        "gameplay_geometry_changed": False,
    }


def apply_trail_x_layout(
    parts: dict[str, Any],
    *,
    half_angle_degrees: float,
    replacement_terminals: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split the smallest repeated trail group while keeping central FX single.

    The target group must contain every replaced character cell, may additionally
    contain only the locked wind companions g/h/p/q, and must have a parent with
    other imagery.  These gates identify wind_spgirl group 21 without hard-coding
    its numeric index and fail closed on an unrelated Flatomo skeleton.
    """
    if isinstance(half_angle_degrees, bool) or not isinstance(half_angle_degrees, (int, float)):
        raise ReskinError("X half-angle must be numeric")
    half_angle = float(half_angle_degrees)
    if not 5.0 <= half_angle <= 30.0:
        raise ReskinError("X half-angle must be from 5 to 30 degrees")
    if not replacement_terminals:
        raise ReskinError("trail X layout requires replacement terminals")
    result = copy.deepcopy(parts)
    groups = result.get("g")
    matrices = result.get("t")
    images = result.get("i")
    if not isinstance(groups, list) or not groups or not isinstance(matrices, list) or not isinstance(images, list):
        raise ReskinError("parts has no usable groups, matrices, or images")
    image_names = [str(record.get("p", "")).rsplit("/", 1)[-1] for record in images]
    children: dict[int, list[int]] = {index: [] for index in range(len(groups))}
    direct: dict[int, set[str]] = {index: set() for index in range(len(groups))}
    parents: dict[int, set[int]] = {index: set() for index in range(len(groups))}
    for group_index, group in enumerate(groups):
        for segment in group.get("s", []):
            packed_start = _u32(segment["s"])
            kind = packed_start >> 30
            item_id = int(segment["i"])
            if kind == 0:
                if item_id < 0 or item_id >= len(image_names):
                    raise ReskinError("trail X layout found an invalid image index")
                direct[group_index].add(image_names[item_id])
            elif kind == 2:
                if item_id < 0 or item_id >= len(groups):
                    raise ReskinError("trail X layout found an invalid group index")
                children[group_index].append(item_id)
                parents[item_id].add(group_index)
    cache: dict[int, set[str]] = {}

    def descendants(group_index: int, stack: tuple[int, ...] = ()) -> set[str]:
        if group_index in cache:
            return cache[group_index]
        if group_index in stack:
            raise ReskinError("trail X layout found cyclic group references")
        found = set(direct[group_index])
        for child in children[group_index]:
            found.update(descendants(child, stack + (group_index,)))
        cache[group_index] = found
        return found

    allowed_companions = {"g", "h", "p", "q"}
    candidates: list[tuple[int, int]] = []
    for group_index in range(len(groups)):
        owned = descendants(group_index)
        if not replacement_terminals.issubset(owned):
            continue
        if owned - replacement_terminals - allowed_companions:
            continue
        if len(parents[group_index]) != 1:
            continue
        parent_index = next(iter(parents[group_index]))
        if not descendants(parent_index) - owned:
            continue
        candidates.append((group_index, parent_index))
    if candidates:
        largest_owned = max(len(descendants(group_index)) for group_index, _ in candidates)
        candidates = [
            item for item in candidates
            if len(descendants(item[0])) == largest_owned
        ]
    if len(candidates) != 1:
        raise ReskinError(f"trail X layout expected one outer isolated trail group, found {candidates}")
    target_group, parent_group = candidates[0]
    parent_segments = groups[parent_group].get("s", [])
    matching_indices = []
    for index, segment in enumerate(parent_segments):
        packed_start = _u32(segment["s"])
        if packed_start >> 30 == 2 and int(segment["i"]) == target_group:
            matching_indices.append(index)
    if len(matching_indices) != 1:
        raise ReskinError("trail X layout expected one parent segment for the trail group")
    segment_index = matching_indices[0]
    source_segment = parent_segments[segment_index]
    keys = source_segment.get("l")
    if not isinstance(keys, list) or not keys:
        raise ReskinError("trail X layout segment has no transform keys")
    identity = {"a": 4096, "b": 0, "c": 0, "d": 4096, "x": 0, "y": 0}
    for key in keys:
        matrix_index = int(key.get("m", -1)) >> 12
        if matrix_index < 0 or matrix_index >= len(matrices):
            raise ReskinError("trail X layout matrix index is invalid")
        matrix = matrices[matrix_index]
        if any(int(matrix.get(name, 0)) != value for name, value in identity.items()):
            raise ReskinError("trail X layout only accepts an identity source transform")
    branch_segments = []
    matrix_indices = []
    for angle in (-half_angle, half_angle):
        radians = math.radians(angle)
        cosine = round(math.cos(radians) * 4096)
        sine = round(math.sin(radians) * 4096)
        matrix_index = len(matrices)
        matrices.append({"a": cosine, "b": sine, "c": -sine, "d": cosine, "x": 0, "y": 0})
        matrix_indices.append(matrix_index)
        branch = copy.deepcopy(source_segment)
        for key in branch["l"]:
            key["m"] = matrix_index * 4096 + (int(key["m"]) & 0x0FFF)
        branch_segments.append(branch)
    groups[parent_group]["s"] = (
        parent_segments[:segment_index]
        + branch_segments
        + parent_segments[segment_index + 1:]
    )
    return result, {
        "kind": "narrow-x-trail",
        "scope": "isolated-character-trail",
        "branch_count": 2,
        "half_angle_degrees": half_angle,
        "top_bottom_included_angle_degrees": half_angle * 2.0,
        "target_group": target_group,
        "parent_group": parent_group,
        "matrix_indices": matrix_indices,
        "sound_instances": 1,
        "central_effect_instances": 1,
        "gameplay_geometry_changed": False,
    }


def apply_pool_safe_trail_x_layout(
    parts: dict[str, Any],
    *,
    half_angle_degrees: float,
    replacement_terminals: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the original full-density X and resize its image object pools.

    Flatomo stores one preallocated display-object capacity per image in
    ``parts.a``.  Duplicating the trail subtree doubles the concurrent demand
    for its leaf images; keeping the original capacities makes the client run
    out of objects in ``fetchDisplayObject`` even though the graph and matrices
    decode correctly.
    """
    source_profile = flatomo_instance_profile(parts)
    source_pools = parts.get("a")
    images = parts.get("i")
    if not isinstance(source_pools, list) or not isinstance(images, list):
        raise ReskinError("pool-safe X requires image records and object pools")
    if len(source_pools) != len(images):
        raise ReskinError("pool-safe X object-pool count does not match images")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < required
        for value, required in zip(source_pools, source_profile["per_image_peaks"])
    ):
        raise ReskinError("source object pools are already smaller than runtime demand")

    result, layout = apply_trail_x_layout(
        parts,
        half_angle_degrees=half_angle_degrees,
        replacement_terminals=replacement_terminals,
    )
    target_profile = flatomo_instance_profile(result)
    target_pools = [
        max(int(existing), int(required))
        for existing, required in zip(source_pools, target_profile["per_image_peaks"])
    ]
    terminals = [str(record.get("p", "")).rsplit("/", 1)[-1] for record in images]
    changes = [
        {
            "image_index": index,
            "terminal": terminals[index],
            "before": int(source_pools[index]),
            "required_peak": int(target_profile["per_image_peaks"][index]),
            "after": int(target_pools[index]),
            "added_capacity": int(target_pools[index]) - int(source_pools[index]),
        }
        for index in range(len(images))
        if int(target_pools[index]) != int(source_pools[index])
    ]
    if not changes:
        raise ReskinError("pool-safe X did not increase any object-pool capacity")
    result["a"] = target_pools
    layout.update(
        {
            "kind": "pool-safe-narrow-x-trail",
            "object_pool_guard": "per-image-concurrent-instance-peak",
            "object_pool_entries": len(target_pools),
            "object_pool_entries_changed": len(changes),
            "object_pool_capacity_before": sum(map(int, source_pools)),
            "object_pool_capacity_after": sum(target_pools),
            "object_pool_changes": changes,
            "source_visible_instance_peak": int(source_profile["visible_instance_peak"]),
            "target_visible_instance_peak": int(target_profile["visible_instance_peak"]),
            "source_visible_instance_total": int(source_profile["visible_instance_total"]),
            "target_visible_instance_total": int(target_profile["visible_instance_total"]),
            "groups_added": 0,
            "segments_added": 1,
            "matrices_added": 2,
            "image_records_added": 0,
            "full_trail_density_per_branch": True,
        }
    )
    return result, layout


def apply_interleaved_trail_x_layout(
    parts: dict[str, Any],
    *,
    half_angle_degrees: float,
    trail_terminal: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split existing trail stamps across two diagonals without adding objects.

    ``wind_spgirl`` already has 26 independent, overlapping stamps for the
    vertical character trail.  Alternating those existing stamps between
    ``-angle`` and ``+angle`` produces two diagonal arms while keeping the
    original group/segment/image/matrix counts and visible-instance budget.
    """
    if isinstance(half_angle_degrees, bool) or not isinstance(
        half_angle_degrees, (int, float)
    ):
        raise ReskinError("interleaved X half-angle must be numeric")
    half_angle = float(half_angle_degrees)
    if not 5.0 <= half_angle <= 30.0:
        raise ReskinError("interleaved X half-angle must be from 5 to 30 degrees")
    if not SAFE_LOGICAL.fullmatch(trail_terminal):
        raise ReskinError("interleaved X trail terminal is invalid")

    result = copy.deepcopy(parts)
    groups = result.get("g")
    matrices = result.get("t")
    images = result.get("i")
    if not isinstance(groups, list) or not isinstance(matrices, list) or not isinstance(images, list):
        raise ReskinError("parts has no usable groups, matrices, or images")
    image_names = [str(record.get("p", "")).rsplit("/", 1)[-1] for record in images]
    target_images = [index for index, name in enumerate(image_names) if name == trail_terminal]
    if len(target_images) != 1:
        raise ReskinError(
            f"interleaved X expected one image terminal {trail_terminal}, found {target_images}"
        )
    target_image = target_images[0]

    def group_reaches_target(group_index: int, seen: set[int] | None = None) -> bool:
        visited = set(seen or ())
        if group_index in visited or not 0 <= group_index < len(groups):
            return False
        visited.add(group_index)
        for segment in groups[group_index].get("s", ()):
            kind = _u32(segment.get("s", 0)) >> 30
            child = int(segment.get("i", -1))
            if kind == 0 and child == target_image:
                return True
            if kind == 2 and group_reaches_target(child, visited):
                return True
        return False

    matrix_references: dict[int, int] = {}
    for group in groups:
        for segment in group.get("s", ()):
            for key in segment.get("l", ()):
                index = int(key.get("m", -1)) >> 12
                matrix_references[index] = matrix_references.get(index, 0) + 1

    candidates: list[int] = []
    for group_index, group in enumerate(groups):
        segments = group.get("s", ())
        if len(segments) < 8:
            continue
        child_groups = {int(segment.get("i", -1)) for segment in segments}
        if (
            len(child_groups) == 1
            and all(
                (_u32(segment.get("s", 0)) >> 30) == 2
                and len(segment.get("l", ())) == 1
                for segment in segments
            )
            and group_reaches_target(next(iter(child_groups)))
        ):
            candidates.append(group_index)
    if len(candidates) != 1:
        raise ReskinError(
            f"interleaved X expected one repeated trail group, found {candidates}"
        )
    target_group = candidates[0]
    segments = groups[target_group]["s"]
    trail_child_group = int(segments[0]["i"])
    matrix_indices = [int(segment["l"][0]["m"]) >> 12 for segment in segments]
    if len(matrix_indices) != len(set(matrix_indices)):
        raise ReskinError("interleaved X trail matrices are not unique")
    if any(matrix_references.get(index) != 1 for index in matrix_indices):
        raise ReskinError("interleaved X trail matrix is shared outside its stamp")

    cosine = round(math.cos(math.radians(half_angle)) * 4096)
    sine_abs = round(math.sin(math.radians(half_angle)) * 4096)
    branch_counts = {"negative": 0, "positive": 0}
    for segment_index, matrix_index in enumerate(matrix_indices):
        matrix = matrices[matrix_index]
        if any(
            int(matrix.get(name, 0)) != expected
            for name, expected in {
                "a": 4096,
                "b": 0,
                "c": 0,
                "d": 4096,
                "x": 0,
            }.items()
        ):
            raise ReskinError("interleaved X accepts only the original vertical trail matrices")
        source_y = int(matrix.get("y", 0))
        sine = -sine_abs if segment_index % 2 == 0 else sine_abs
        matrix.update(
            {
                "a": cosine,
                "b": sine,
                "c": -sine,
                "d": cosine,
                "x": round(-source_y * sine / 4096),
                "y": round(source_y * cosine / 4096),
            }
        )
        branch_counts["negative" if sine < 0 else "positive"] += 1

    return result, {
        "kind": "interleaved-trail-x",
        "scope": "existing-trail-stamps",
        "visual_branch_count": 2,
        "runtime_branch_count": 1,
        "half_angle_degrees": half_angle,
        "top_bottom_included_angle_degrees": half_angle * 2.0,
        "trail_terminal": trail_terminal,
        "target_group": target_group,
        "trail_child_group": trail_child_group,
        "trail_segments": len(segments),
        "branch_stamp_counts": branch_counts,
        "matrix_indices": matrix_indices,
        "parts_topology_unchanged": True,
        "groups_added": 0,
        "segments_added": 0,
        "images_added": 0,
        "matrices_added": 0,
        "matrices_modified": len(matrix_indices),
        "visible_instance_budget_unchanged": True,
        "sound_instances": 1,
        "central_effect_instances": 1,
        "gameplay_geometry_changed": False,
    }


def clone_reskin(
    *,
    source_sheet: Image.Image,
    source_atlas: list[dict[str, Any]],
    source_parts: dict[str, Any],
    source_timeline: dict[str, Any],
    replacements: dict[str, Image.Image],
    target_reference: str,
    x_half_angle_degrees: float | None = None,
    x_layout_scope: str = "trail",
    x_baked_terminals: set[str] | None = None,
    x_interleaved_terminal: str | None = None,
) -> dict[str, Any]:
    """Build decoded and encoded assets without touching an asset store."""
    target = _validate_logical_base(target_reference)
    target_root, target_name = target.rsplit("/", 1)
    target_cell_prefix = f"{target_root}/.gen/{target_name}"
    if not isinstance(source_atlas, list) or not source_atlas:
        raise ReskinError("source atlas must be a non-empty array")
    terminals = [_terminal(entry) for entry in source_atlas]
    if len(terminals) != len(set(terminals)):
        raise ReskinError("source atlas terminals are not unique")
    unknown = sorted(set(replacements) - set(terminals))
    if unknown:
        raise ReskinError(f"replacement cells are absent from source atlas: {unknown}")
    atlas_entries = copy.deepcopy(source_atlas)
    original_cells = {terminal: atlas_crop(source_sheet, entry) for terminal, entry in zip(terminals, source_atlas)}
    cells = {terminal: replacements.get(terminal, image) for terminal, image in original_cells.items()}
    for entry in source_atlas:
        terminal = _terminal(entry)
        if terminal in replacements:
            _validate_frame_fit(entry, cells[terminal])
    parts = copy.deepcopy(source_parts)
    layout = None
    if x_half_angle_degrees is not None and x_layout_scope == "baked":
        baked_terminals = set(x_baked_terminals or ())
        if not baked_terminals:
            raise ReskinError("baked X layout requires explicit atlas terminals")
        if not baked_terminals.issubset(replacements):
            raise ReskinError("baked X terminals must be replacement cells")
        baked_rows = []
        for terminal in sorted(baked_terminals):
            index = terminals.index(terminal)
            baked, patched_entry, detail = bake_rotated_x_cell(
                atlas_entries[index],
                cells[terminal],
                half_angle_degrees=x_half_angle_degrees,
            )
            atlas_entries[index] = patched_entry
            cells[terminal] = baked
            baked_rows.append(detail)
        layout = {
            "kind": "baked-raster-x",
            "scope": "atlas-cells",
            "visual_branch_count": 2,
            "runtime_branch_count": 1,
            "half_angle_degrees": float(x_half_angle_degrees),
            "top_bottom_included_angle_degrees": float(x_half_angle_degrees) * 2.0,
            "baked_terminals": sorted(baked_terminals),
            "parts_topology_unchanged": True,
            "groups_added": 0,
            "segments_added": 0,
            "matrices_added": 0,
            "sound_instances": 1,
            "central_effect_instances": 1,
            "gameplay_geometry_changed": False,
            "cells": baked_rows,
        }
    sheet, atlas = _pack_cells(atlas_entries, cells, target_cell_prefix=target_cell_prefix)
    source_names = {str(entry["n"]) for entry in source_atlas}
    target_names = {str(entry["n"]) for entry in atlas}
    if len(source_names) != len(source_atlas) or len(target_names) != len(atlas):
        raise ReskinError("atlas name uniqueness check failed")
    path_changes = 0
    for image_record in parts.get("i", []):
        path = str(image_record.get("p", ""))
        if path not in source_names:
            raise ReskinError(f"parts references a cell outside the source atlas: {path}")
        terminal = path.rsplit("/", 1)[-1]
        image_record["p"] = f"{target_cell_prefix}/{terminal}"
        path_changes += 1
    if path_changes != len(source_atlas):
        raise ReskinError("parts image count does not match atlas record count")
    if x_half_angle_degrees is not None and x_layout_scope != "baked":
        if x_layout_scope == "trail":
            parts, layout = apply_trail_x_layout(
                parts,
                half_angle_degrees=x_half_angle_degrees,
                replacement_terminals=set(replacements),
            )
        elif x_layout_scope == "root":
            parts, layout = apply_root_x_layout(parts, half_angle_degrees=x_half_angle_degrees)
        elif x_layout_scope == "pool-safe":
            parts, layout = apply_pool_safe_trail_x_layout(
                parts,
                half_angle_degrees=x_half_angle_degrees,
                replacement_terminals=set(replacements),
            )
        elif x_layout_scope == "interleaved":
            if x_interleaved_terminal is None:
                raise ReskinError("interleaved X layout requires one trail terminal")
            parts, layout = apply_interleaved_trail_x_layout(
                parts,
                half_angle_degrees=x_half_angle_degrees,
                trail_terminal=x_interleaved_terminal,
            )
        else:
            raise ReskinError(f"unsupported X layout scope: {x_layout_scope}")
    timeline = copy.deepcopy(source_timeline)
    standard_png = _standard_png(sheet)
    compiled = {
        f"{target}.png": wf_assets.png_encode(standard_png),
        f"{target}.atlas.amf3.deflate": _raw_deflate(wf_dsl.encode_amf3(atlas)),
        f"{target}.parts.amf3.deflate": _raw_deflate(wf_dsl.encode_amf3(parts)),
        f"{target}.timeline.amf3.deflate": _raw_deflate(wf_dsl.encode_amf3(timeline)),
    }
    return {
        "sheet": sheet,
        "atlas": atlas,
        "parts": parts,
        "timeline": timeline,
        "compiled": compiled,
        "original_cells": original_cells,
        "cells": cells,
        "replaced": sorted(replacements),
        "unchanged": sorted(set(terminals) - set(replacements)),
        "layout": layout,
    }


def rewrite_action_dsl(raw: bytes, *, source_reference: str, target_reference: str) -> tuple[bytes, int]:
    try:
        plain = zlib.decompress(raw, -15)
        parsed = wf_dsl.parse_dsl(plain)
    except Exception as error:
        raise ReskinError("action DSL cannot be decoded") from error
    tree = parsed["tree"]
    count = _replace_exact_strings(tree, source_reference, target_reference)
    if count != 1:
        raise ReskinError(f"expected one effect reference in action DSL, found {count}")
    return _raw_deflate(wf_dsl.encode_amf3(tree)), count


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\msyhbd.ttc") if bold else Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    scale = min(size[0] / image.width, size[1] / image.height)
    return image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.NEAREST,
    )


def render_comparison(
    original: dict[str, Image.Image],
    candidate: dict[str, Image.Image],
    replaced: Iterable[str],
    target: Path,
) -> None:
    names = list(replaced)
    card_width, card_height = 360, 280
    output = Image.new("RGB", (40 + card_width * 2, 110 + card_height * len(names)), "#eef2f7")
    draw = ImageDraw.Draw(output)
    draw.text((24, 18), "149996 主动技部件精准替换对照", font=_font(29, True), fill="#172033")
    draw.text((24, 60), "左：原版希尔媞共用部件　右：泳装专用部件（锚点保持）", font=_font(17), fill="#526176")
    for row, name in enumerate(names):
        top = 96 + row * card_height
        for column, (label, image) in enumerate((("原", original[name]), ("新", candidate[name]))):
            left = 20 + column * card_width
            draw.rounded_rectangle((left, top, left + card_width - 16, top + card_height - 16), 12, fill="#222a38")
            draw.text((left + 14, top + 10), f"{name} · {label} · {image.width}×{image.height}", font=_font(16, True), fill="white")
            checker = Image.new("RGBA", (card_width - 52, card_height - 74), (49, 58, 74, 255))
            cell = 16
            checker_draw = ImageDraw.Draw(checker)
            for y in range(0, checker.height, cell):
                for x in range(0, checker.width, cell):
                    if (x // cell + y // cell) % 2:
                        checker_draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(61, 72, 91, 255))
            fitted = _contain(image, (checker.width - 24, checker.height - 24))
            checker.alpha_composite(fitted, ((checker.width - fitted.width) // 2, (checker.height - fitted.height) // 2))
            output.paste(checker.convert("RGB"), (left + 18, top + 48))
    target.parent.mkdir(parents=True, exist_ok=True)
    output.save(target, format="PNG", compress_level=9)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_compiled(output: Path, compiled: dict[str, bytes]) -> list[dict[str, Any]]:
    rows = []
    for logical, payload in sorted(compiled.items()):
        target = output / "compiled-logical" / Path(*logical.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        rows.append({"logical": logical, "relative": target.relative_to(output).as_posix(), "bytes": len(payload), "sha256": _sha256(payload)})
    return rows


def build_candidate(
    *,
    source_effect_root: Path,
    replacement_source: Path | None,
    target_reference: str,
    output: Path,
    action_dsl_dir: Path | None = None,
    source_reference: str | None = None,
    sound_store: Path | None = None,
    x_half_angle_degrees: float | None = None,
    x_layout_scope: str = "trail",
    x_baked_terminals: set[str] | None = None,
    x_interleaved_terminal: str | None = None,
    replacement_images: dict[str, Image.Image] | None = None,
) -> dict[str, Any]:
    output = _safe_output(output)
    if output.exists() and any(output.iterdir()):
        raise ReskinError("output directory must be absent or empty")
    source_name = source_effect_root.name
    source_sheet_path = source_effect_root / f"{source_name}.png"
    source_atlas_path = source_effect_root / f"{source_name}.atlas.json"
    source_parts_path = source_effect_root / "decoded" / f"{source_name}.parts.json"
    source_timeline_path = source_effect_root / "decoded" / f"{source_name}.timeline.json"
    for path in (source_sheet_path, source_atlas_path, source_parts_path, source_timeline_path):
        if not path.is_file():
            raise ReskinError(f"source effect file is missing: {path}")
    with Image.open(source_sheet_path) as opened:
        source_sheet = opened.convert("RGBA")
    source_atlas = _json(source_atlas_path)
    source_parts = _json(source_parts_path)
    source_timeline = _json(source_timeline_path)
    if replacement_images is not None:
        if replacement_source is not None:
            raise ReskinError("use either replacement_source or replacement_images")
        replacements = {
            str(name): image.convert("RGBA").copy()
            for name, image in replacement_images.items()
        }
        if not replacements:
            raise ReskinError("replacement_images contains no cells")
    elif replacement_source is not None:
        replacements = load_replacements(replacement_source)
    else:
        raise ReskinError("replacement source is required")
    result = clone_reskin(
        source_sheet=source_sheet,
        source_atlas=source_atlas,
        source_parts=source_parts,
        source_timeline=source_timeline,
        replacements=replacements,
        target_reference=target_reference,
        x_half_angle_degrees=x_half_angle_degrees,
        x_layout_scope=x_layout_scope,
        x_baked_terminals=x_baked_terminals,
        x_interleaved_terminal=x_interleaved_terminal,
    )
    output.mkdir(parents=True, exist_ok=True)
    preview = output / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    target_name = target_reference.rsplit("/", 1)[-1]
    result["sheet"].save(preview / f"{target_name}.sheet.png", format="PNG", compress_level=9)
    render_comparison(result["original_cells"], result["cells"], result["replaced"], preview / "affected-cells-before-after.png")
    layout_suffix = ""
    preview_title = "149996 · wind_spgirl_swim · 泳装主动技候选预览"
    affected_title = "149996 · 仅显示 8 个已替换部件 · 原骨架运动"
    if result["layout"] is not None:
        included = result["layout"]["top_bottom_included_angle_degrees"]
        layout_suffix = f"-x{included:g}"
        preview_title = f"149996 · 窄 X 主动技候选 · 上下夹角 {included:g}°"
        affected_title = f"149996 · 窄 X 的 8 个泳装部件 · 夹角 {included:g}°"
    preview_report = render_flatomo_gif(
        sheet=result["sheet"],
        atlas=result["atlas"],
        parts=result["parts"],
        timeline=result["timeline"],
        target=preview / f"{target_name}{layout_suffix}-97tick-preview.gif",
        title=preview_title,
    )
    affected_preview_report = render_flatomo_gif(
        sheet=result["sheet"],
        atlas=result["atlas"],
        parts=result["parts"],
        timeline=result["timeline"],
        target=preview / f"{target_name}{layout_suffix}-affected-cells-97tick-preview.gif",
        title=affected_title,
        include_terminals=set(result["replaced"]),
    )
    decoded = output / "decoded"
    _write_json(decoded / f"{target_name}.atlas.json", result["atlas"])
    _write_json(decoded / f"{target_name}.parts.json", result["parts"])
    _write_json(decoded / f"{target_name}.timeline.json", result["timeline"])
    compiled_rows = _write_compiled(output, result["compiled"])
    dsl_rows: list[dict[str, Any]] = []
    if action_dsl_dir is not None:
        if source_reference is None:
            raise ReskinError("source reference is required when rewriting action DSLs")
        raw_files = sorted(action_dsl_dir.glob("*.action.dsl.amf3.deflate"))
        if not raw_files:
            raise ReskinError("action DSL directory contains no raw DSL files")
        for source in raw_files:
            payload, count = rewrite_action_dsl(
                source.read_bytes(),
                source_reference=source_reference,
                target_reference=target_reference,
            )
            target = output / "compiled-action-dsl" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            dsl_rows.append({"file": source.name, "replacements": count, "bytes": len(payload), "sha256": _sha256(payload)})
    sound_row = None
    sounds = result["timeline"].get("sounds", [])
    if sound_store is not None and sounds:
        sound_reference = str(sounds[0]["path"])
        logical = sound_reference if sound_reference.endswith(".mp3") else sound_reference + ".mp3"
        located = wf_assets.read_current(sound_store, logical)
        if located is None:
            raise ReskinError(f"timeline sound is absent from the current store: {logical}")
        decoded_mp3 = wf_assets.mp3_decode(located[1])
        sound_target = preview / (Path(logical).name)
        sound_target.write_bytes(decoded_mp3)
        probe = wf_assets.mp3_probe(decoded_mp3, 2047)
        probe = {
            key: sorted(value) if isinstance(value, set) else value
            for key, value in probe.items()
        }
        sound_row = {
            "logical": logical,
            "timeline_begin_tick": int(sounds[0].get("begin", -1)),
            "source": located[2],
            "root": located[0],
            "bytes": len(decoded_mp3),
            "sha256": _sha256(decoded_mp3),
            "probe": probe,
            "relative": sound_target.relative_to(output).as_posix(),
        }
    source_plain = wf_dsl.encode_amf3(source_timeline)
    target_plain = zlib.decompress(result["compiled"][f"{target_reference}.timeline.amf3.deflate"], -15)
    if source_plain != target_plain:
        raise ReskinError("timeline changed while cloning the effect")
    report = {
        "mode": "offline-candidate-only",
        "writes_live": False,
        "target_reference": target_reference,
        "source_reference": source_reference,
        "atlas_records": len(result["atlas"]),
        "replaced_cells": result["replaced"],
        "unchanged_cells": result["unchanged"],
        "anchor_metadata_preserved": True,
        "timeline_plain_bytes_identical": True,
        "visual_layout": result["layout"],
        "preview": preview_report,
        "affected_cells_preview": affected_preview_report,
        "compiled": compiled_rows,
        "action_dsl": dsl_rows,
        "sound": sound_row,
    }
    _write_json(output / "candidate-report.json", report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Flatomo effect-cell clone/reskin builder")
    parser.add_argument("--source-effect-root", type=Path, required=True)
    parser.add_argument("--replacements", type=Path, required=True)
    parser.add_argument("--target-reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--action-dsl-dir", type=Path)
    parser.add_argument("--source-reference")
    parser.add_argument("--sound-store", type=Path)
    parser.add_argument("--x-half-angle-degrees", type=float)
    parser.add_argument(
        "--x-layout-scope",
        choices=("trail", "root", "baked", "pool-safe", "interleaved"),
        default="trail",
    )
    parser.add_argument("--x-baked-terminal", action="append", default=[])
    parser.add_argument("--x-interleaved-terminal")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_candidate(
            source_effect_root=args.source_effect_root,
            replacement_source=args.replacements,
            target_reference=args.target_reference,
            output=args.output,
            action_dsl_dir=args.action_dsl_dir,
            source_reference=args.source_reference,
            sound_store=args.sound_store,
            x_half_angle_degrees=args.x_half_angle_degrees,
            x_layout_scope=args.x_layout_scope,
            x_baked_terminals=set(args.x_baked_terminal),
            x_interleaved_terminal=args.x_interleaved_terminal,
        )
    except (OSError, ReskinError, zipfile.BadZipFile) as error:
        print(f"[ERR] {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
