#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a decoded Flatomo PartsAnimation to a local GIF.

This module is intentionally read-only.  It accepts already decoded metadata
and a standard PNG sheet; it never reads or writes a game asset store.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


RESOLUTION = 4096.0
MASK_30 = 0x3FFFFFFF
DEFAULT_COLOR_TRANSFORM = 0x64000000


@dataclass(frozen=True)
class Parameters:
    matrix: tuple[float, float, float, float, float, float]
    alpha: float
    blend: int
    color: int = DEFAULT_COLOR_TRANSFORM


@dataclass(frozen=True)
class State:
    kind: int
    item_id: int
    child_frame: int
    parameters: Parameters


@dataclass(frozen=True)
class Cell:
    image: Image.Image
    frame_x: int
    frame_y: int


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\msyhbd.ttc") if bold else Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _u32(value: int | float) -> int:
    return int(value) & 0xFFFFFFFF


def _matrix(record: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
    return tuple(float(record[key]) / RESOLUTION for key in ("a", "b", "c", "d", "x", "y"))  # type: ignore[return-value]


def _parameters(key: dict[str, Any], matrices: list[tuple[float, ...]]) -> Parameters:
    packed = int(key["m"])
    alpha_blend = packed & 0x0FFF
    return Parameters(
        matrix=matrices[packed >> 12],  # type: ignore[arg-type]
        alpha=(alpha_blend & 0xFF) / 255.0,
        blend=alpha_blend >> 8,
        color=int(key.get("c", DEFAULT_COLOR_TRANSFORM)),
    )


def _bezier_coordinate(t: float, control1: float, control2: float) -> float:
    one_minus = 1.0 - t
    return (
        3.0 * one_minus * one_minus * t * control1
        + 3.0 * one_minus * t * t * control2
        + t * t * t
    )


def _custom_tween_ratio(resource: list[int], progress: float) -> float:
    max_value = 1_000_000.0
    segment_count = (len(resource) + 2) // 6
    segment = 0
    for index in range(1, segment_count):
        if progress < resource[index * 6 - 2] / max_value:
            break
        segment = index
    if segment == 0:
        left_x = left_y = 0.0
    else:
        left_x = resource[segment * 6 - 2] / max_value
        left_y = resource[segment * 6 - 1] / max_value
    if segment == segment_count - 1:
        right_x = right_y = 1.0
    else:
        right_x = resource[segment * 6 + 4] / max_value
        right_y = resource[segment * 6 + 5] / max_value
    c1x = (resource[segment * 6] / max_value - left_x) / (right_x - left_x)
    c1y = (resource[segment * 6 + 1] / max_value - left_y) / (right_y - left_y)
    c2x = (resource[segment * 6 + 2] / max_value - left_x) / (right_x - left_x)
    c2y = (resource[segment * 6 + 3] / max_value - left_y) / (right_y - left_y)
    x = (progress - left_x) / (right_x - left_x)
    low, high = 0.0, 1.0
    for _ in range(24):
        middle = (low + high) * 0.5
        if _bezier_coordinate(middle, c1x, c2x) < x:
            low = middle
        else:
            high = middle
    y = _bezier_coordinate((low + high) * 0.5, c1y, c2y)
    return left_y * (1.0 - y) + right_y * y


def _easing_ratio(packed_duration: int, progress: float, custom_tweens: list[list[int]]) -> float:
    kind = (packed_duration >> 16) & 3
    easing_value = packed_duration >> 18
    if kind == 2:
        easing_value -= 63
        easing = easing_value / 100.0
        if easing == 0:
            return progress
        if easing < 0:
            return progress * (progress * -easing + (1.0 + easing))
        return progress * ((2.0 - progress) * easing + (1.0 - easing))
    if kind == 1:
        return _custom_tween_ratio(custom_tweens[easing_value], progress)
    return progress


def _mix(first: Parameters, second: Parameters, ratio: float) -> Parameters:
    inverse = 1.0 - ratio
    matrix = tuple(a * inverse + b * ratio for a, b in zip(first.matrix, second.matrix))
    return Parameters(
        matrix=matrix,  # type: ignore[arg-type]
        alpha=first.alpha * inverse + second.alpha * ratio,
        blend=first.blend,
        color=first.color,
    )


def _future_frame(loop_kind: int, start: int, offset: int, total: int) -> int:
    if loop_kind == 0:
        return start
    if loop_kind == 1:
        return min(start + offset, total - 1)
    if loop_kind == 2:
        return (start + offset) % total
    return total


def _build_frames(parts: dict[str, Any]) -> list[list[list[State]]]:
    matrices = [_matrix(record) for record in parts["t"]]
    custom_tweens = [list(map(int, resource)) for resource in parts.get("c", [])]
    groups = parts["g"]
    all_frames: list[list[list[State]]] = [
        [[] for _ in range(int(group["t"]))] for group in groups
    ]
    for group_index, group in enumerate(groups):
        frames = all_frames[group_index]
        for segment in group["s"]:
            packed_start = _u32(segment["s"])
            kind = packed_start >> 30
            start = packed_start & MASK_30
            child_id = int(segment["i"])
            child_total = int(groups[child_id]["t"]) if kind == 2 else 0
            elapsed = 0
            keys = segment["l"]
            for key_index, key in enumerate(keys):
                packed_duration = int(key.get("t", 1))
                duration = packed_duration & 0xFFFF
                tween_kind = (packed_duration >> 16) & 3
                first = _parameters(key, matrices)
                for offset in range(duration):
                    frame_index = start + elapsed + offset
                    if frame_index >= len(frames):
                        continue
                    parameters = first
                    if tween_kind and offset and key_index + 1 < len(keys):
                        ratio = _easing_ratio(packed_duration, offset / duration, custom_tweens)
                        parameters = _mix(first, _parameters(keys[key_index + 1], matrices), ratio)
                    child_frame = 0
                    if kind == 2:
                        packed_loop = _u32(key.get("r", 0))
                        child_frame = _future_frame(
                            packed_loop >> 30,
                            packed_loop & MASK_30,
                            offset,
                            child_total,
                        )
                        if child_frame >= child_total:
                            continue
                    frames[frame_index].append(
                        State(kind=kind, item_id=child_id, child_frame=child_frame, parameters=parameters)
                    )
                elapsed += duration
    return all_frames


def _concat(
    local: tuple[float, float, float, float, float, float],
    parent: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    a, b, c, d, tx, ty = local
    pa, pb, pc, pd, ptx, pty = parent
    return (
        a * pa + b * pc,
        a * pb + b * pd,
        c * pa + d * pc,
        c * pb + d * pd,
        tx * pa + ty * pc + ptx,
        tx * pb + ty * pd + pty,
    )


def _flatten(
    frames: list[list[list[State]]],
    group_id: int,
    frame: int,
    parent_matrix: tuple[float, float, float, float, float, float],
    parent_alpha: float,
    depth: int = 0,
) -> list[tuple[int, tuple[float, ...], float]]:
    if depth > 64:
        raise ValueError("Flatomo group recursion exceeded 64 levels")
    commands: list[tuple[int, tuple[float, ...], float]] = []
    for state in frames[group_id][frame]:
        matrix = _concat(state.parameters.matrix, parent_matrix)
        alpha = parent_alpha * state.parameters.alpha
        if state.kind == 0:
            commands.append((state.item_id, matrix, alpha))
        elif state.kind == 2:
            commands.extend(
                _flatten(frames, state.item_id, state.child_frame, matrix, alpha, depth + 1)
            )
        else:
            raise ValueError("MovieClip segments are not supported by this renderer")
    return commands


def flatomo_instance_profile(parts: dict[str, Any]) -> dict[str, Any]:
    """Return the runtime image-instance demand implied by the root timeline.

    ``parts.a`` has one display-object pool capacity per image record.  The
    client fetches one object for every concurrent flattened image instance;
    a structural edit that raises this demand without raising the matching
    capacity can fail in ``PartsAnimationImageElement/fetchDisplayObject``.
    """
    images = parts.get("i")
    if not isinstance(images, list):
        raise ValueError("parts has no image records")
    frames = _build_frames(parts)
    if not frames or not frames[0]:
        raise ValueError("parts has no root animation frames")
    peaks = [0] * len(images)
    frame_totals: list[int] = []
    for frame_index in range(len(frames[0])):
        commands = _flatten(
            frames,
            0,
            frame_index,
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            1.0,
        )
        counts = [0] * len(images)
        for image_id, _matrix_value, _alpha in commands:
            if image_id < 0 or image_id >= len(images):
                raise ValueError(f"flattened image index is invalid: {image_id}")
            counts[image_id] += 1
        peaks = [max(old, current) for old, current in zip(peaks, counts)]
        frame_totals.append(sum(counts))
    return {
        "frames": len(frame_totals),
        "per_image_peaks": peaks,
        "visible_instance_peak": max(frame_totals, default=0),
        "visible_instance_total": sum(frame_totals),
        "peak_frame": frame_totals.index(max(frame_totals)) if frame_totals else None,
    }


def _atlas_crop(sheet: Image.Image, entry: dict[str, Any]) -> Image.Image:
    x, y = int(entry["x"]), int(entry["y"])
    width, height = int(entry["w"]), int(entry["h"])
    crop = sheet.crop((x, y, x + width, y + height))
    if entry.get("r", False):
        crop = crop.transpose(Image.Transpose.ROTATE_90)
    return crop


def _load_cells(
    sheet: Image.Image,
    atlas: list[dict[str, Any]],
    parts: dict[str, Any],
) -> list[Cell]:
    records = {str(record["n"]): record for record in atlas}
    cells: list[Cell] = []
    for image_record in parts["i"]:
        path = str(image_record["p"])
        if path not in records:
            raise ValueError(f"parts image has no atlas record: {path}")
        record = records[path]
        cells.append(
            Cell(
                image=_atlas_crop(sheet, record),
                frame_x=int(record.get("fx", 0)),
                frame_y=int(record.get("fy", 0)),
            )
        )
    return cells


def _command_bounds(command: tuple[int, tuple[float, ...], float], cells: list[Cell]) -> tuple[float, ...]:
    image_id, matrix, _ = command
    cell = cells[image_id]
    a, b, c, d, tx, ty = matrix
    x0, y0 = -cell.frame_x, -cell.frame_y
    x1, y1 = x0 + cell.image.width, y0 + cell.image.height
    points = [
        (a * x + c * y + tx, b * x + d * y + ty)
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
    ]
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _warp_cell(
    cell: Cell,
    matrix: tuple[float, ...],
    alpha: float,
    scale: float,
    origin: tuple[float, float],
) -> tuple[Image.Image, tuple[int, int]] | None:
    a, b, c, d, tx, ty = matrix
    a *= scale
    b *= scale
    c *= scale
    d *= scale
    tx = (tx - a / scale * cell.frame_x - c / scale * cell.frame_y) * scale + origin[0]
    ty = (ty - b / scale * cell.frame_x - d / scale * cell.frame_y) * scale + origin[1]
    determinant = a * d - b * c
    if abs(determinant) < 1e-9 or alpha <= 0:
        return None
    width, height = cell.image.size
    points = [
        (a * x + c * y + tx, b * x + d * y + ty)
        for x, y in ((0, 0), (width, 0), (0, height), (width, height))
    ]
    left = math.floor(min(point[0] for point in points)) - 2
    top = math.floor(min(point[1] for point in points)) - 2
    right = math.ceil(max(point[0] for point in points)) + 2
    bottom = math.ceil(max(point[1] for point in points)) + 2
    if right <= left or bottom <= top:
        return None
    ia, ib = d / determinant, -b / determinant
    ic, id_ = -c / determinant, a / determinant
    patch = cell.image.transform(
        (right - left, bottom - top),
        Image.Transform.AFFINE,
        (
            ia,
            ic,
            ia * (left - tx) + ic * (top - ty),
            ib,
            id_,
            ib * (left - tx) + id_ * (top - ty),
        ),
        resample=Image.Resampling.BICUBIC,
    )
    if alpha < 0.999:
        channel = patch.getchannel("A").point(lambda value: int(value * alpha))
        patch.putalpha(channel)
    return patch, (left, top)


def render_flatomo_gif(
    *,
    sheet: Image.Image,
    atlas: list[dict[str, Any]],
    parts: dict[str, Any],
    timeline: dict[str, Any],
    target: Path | str,
    title: str,
    viewport: tuple[int, int] = (960, 720),
    include_terminals: set[str] | None = None,
) -> dict[str, Any]:
    """Render the first once-sequence and return verifiable preview metadata."""
    sequences = timeline.get("sequences", [])
    if not sequences:
        raise ValueError("timeline has no sequences")
    sequence = sequences[0]
    begin, end = int(sequence["begin"]), int(sequence["end"])
    if begin < 1 or end < begin or sequence.get("kind") != "once":
        raise ValueError(f"unsupported preview sequence: {sequence}")
    if parts.get("m"):
        raise ValueError("MovieClip metadata is not supported by this renderer")
    frame_count = end - begin + 1
    frames = _build_frames(parts)
    cells = _load_cells(sheet, atlas, parts)
    commands_by_frame = [
        _flatten(frames, 0, frame, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), 1.0)
        for frame in range(begin - 1, end)
    ]
    if include_terminals is not None:
        image_terminals = [str(record["p"]).rsplit("/", 1)[-1] for record in parts["i"]]
        unknown = include_terminals - set(image_terminals)
        if unknown:
            raise ValueError(f"requested preview cells are absent: {sorted(unknown)}")
        commands_by_frame = [
            [command for command in commands if image_terminals[command[0]] in include_terminals]
            for commands in commands_by_frame
        ]
    bounds = [
        _command_bounds(command, cells)
        for commands in commands_by_frame
        for command in commands
        if command[2] > 0
    ]
    if not bounds:
        raise ValueError("effect produced no visible commands")
    min_x = min(box[0] for box in bounds)
    min_y = min(box[1] for box in bounds)
    max_x = max(box[2] for box in bounds)
    max_y = max(box[3] for box in bounds)
    header, margin = 86, 42
    available_w = viewport[0] - margin * 2
    available_h = viewport[1] - header - margin * 2
    game_scale = float(parts["s"])
    preview_scale = min(
        available_w / ((max_x - min_x) * game_scale),
        available_h / ((max_y - min_y) * game_scale),
    )
    scale = game_scale * preview_scale
    origin = (
        margin + (available_w - (max_x - min_x) * scale) / 2 - min_x * scale,
        header + margin + (available_h - (max_y - min_y) * scale) / 2 - min_y * scale,
    )
    rendered: list[Image.Image] = []
    for index, commands in enumerate(commands_by_frame):
        canvas = Image.new("RGBA", viewport, (22, 28, 40, 255))
        draw = ImageDraw.Draw(canvas)
        block = 24
        for y in range(header, viewport[1], block):
            for x in range(0, viewport[0], block):
                if (x // block + y // block) % 2:
                    draw.rectangle((x, y, x + block - 1, y + block - 1), fill=(30, 38, 54, 255))
        for image_id, matrix, alpha in commands:
            warped = _warp_cell(cells[image_id], matrix, alpha, scale, origin)
            if warped is not None:
                patch, position = warped
                canvas.alpha_composite(patch, position)
        draw.rectangle((0, 0, viewport[0], header), fill=(15, 23, 42, 255))
        draw.text((24, 14), title, font=_font(25, True), fill="white")
        draw.text(
            (25, 51),
            f"tick {index + begin:02d}/{end}  ·  60 tick/s  ·  独立特效层（不含角色与镜头）",
            font=_font(15),
            fill="#C7D7F4",
        )
        rendered.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=255))
    output = Path(target)
    output.parent.mkdir(parents=True, exist_ok=True)
    durations = [20 if index % 3 != 2 else 10 for index in range(len(rendered))]
    rendered[0].save(
        output,
        save_all=True,
        append_images=rendered[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=False,
    )
    with Image.open(output) as check:
        if getattr(check, "n_frames", 1) != frame_count:
            raise ValueError("rendered GIF frame count mismatch")
        decoded_duration = 0
        for frame_index in range(check.n_frames):
            check.seek(frame_index)
            decoded_duration += int(check.info.get("duration", 0))
    return {
        "frames": frame_count,
        "duration_ms": decoded_duration,
        "game_scale": game_scale,
        "preview_scale": preview_scale,
        "logical_bounds": [min_x, min_y, max_x, max_y],
        "viewport": list(viewport),
        "included_terminals": sorted(include_terminals) if include_terminals is not None else None,
    }


__all__ = ["flatomo_instance_profile", "render_flatomo_gif"]
