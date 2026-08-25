#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild a sprite sheet and atlas from extractor-provided unique frame PNGs.

Some character dumps contain a stale packed sheet beside authoritative, edited
frames in ``sprite_sheet/`` or ``special_sprite_sheet/``.  The extractor names
one PNG after the first atlas record that owns each unique source rectangle.
This compiler validates that contract, packs the unrotated frames without
copying any pixels from the stale sheet, and preserves each record's full-frame
placement (``fx/fy/fw/fh``).
"""
from __future__ import annotations

import copy
import hashlib
import io
import zlib
from collections.abc import Mapping, Sequence

from PIL import Image

import wf_assets
import wf_dsl


_RECT_KEYS = ("x", "y", "w", "h", "r")
_PLACEMENT_KEYS = ("fx", "fy", "fw", "fh")


def _prefix(value: str, label: str) -> str:
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ValueError(f"{label} must be a normalized logical path prefix")
    return value


def _raw_deflate(raw: bytes) -> bytes:
    compressor = zlib.compressobj(level=9, wbits=-15)
    return compressor.compress(raw) + compressor.flush()


def _stored_png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=9)
    return wf_assets.png_encode(stream.getvalue())


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def compile_split_sheet(
    atlas_records: Sequence[object],
    cel_payloads: Mapping[str, bytes],
    *,
    source_prefix: str,
    target_prefix: str,
    sheet_basename: str,
    sheet_width: int,
    maximum_sheet_height: int | None = None,
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Compile unique extractor frame PNGs into one stored PNG and AMF3 atlas.

    ``cel_payloads`` is keyed by the terminal atlas name without ``.png``.  It
    must contain exactly the first record for every unique source rectangle.
    """
    source = _prefix(source_prefix, "source_prefix")
    target = _prefix(target_prefix, "target_prefix")
    if source == target:
        raise ValueError("source_prefix and target_prefix must differ")
    if not sheet_basename or "/" in sheet_basename or "\\" in sheet_basename:
        raise ValueError("sheet_basename must be one normalized filename stem")
    if isinstance(sheet_width, bool) or not isinstance(sheet_width, int) or sheet_width < 3:
        raise ValueError("sheet_width must be an integer of at least 3")
    if maximum_sheet_height is not None and (
        isinstance(maximum_sheet_height, bool)
        or not isinstance(maximum_sheet_height, int)
        or maximum_sheet_height < 3
    ):
        raise ValueError("maximum_sheet_height must be an integer of at least 3")
    if not atlas_records:
        raise ValueError("atlas_records must be non-empty")

    normalized: list[dict[str, object]] = []
    representatives: dict[tuple[object, ...], str] = {}
    seen_names: set[str] = set()
    for index, raw in enumerate(atlas_records):
        if not isinstance(raw, dict):
            raise ValueError(f"atlas record {index} must be an object")
        entry = copy.deepcopy(raw)
        name = entry.get("n")
        expected = source + "/"
        if not isinstance(name, str) or not name.startswith(expected):
            raise ValueError(f"atlas record {index} does not use source_prefix")
        terminal = name[len(expected):]
        if not terminal or "/" in terminal or terminal in seen_names:
            raise ValueError(f"atlas record {index} has an invalid or duplicate name")
        seen_names.add(terminal)
        for key in ("x", "y", "w", "h", *_PLACEMENT_KEYS):
            _integer(entry.get(key), f"atlas record {index} {key}")
        if entry["x"] < 0 or entry["y"] < 0 or entry["w"] <= 0 or entry["h"] <= 0:
            raise ValueError(f"atlas record {index} has invalid source geometry")
        rotated = entry.get("r", False)
        if not isinstance(rotated, bool):
            raise ValueError(f"atlas record {index} rotation flag must be boolean")
        rectangle = tuple(entry.get(key) for key in _RECT_KEYS)
        representatives.setdefault(rectangle, terminal)
        normalized.append(entry)

    expected_cels = set(representatives.values())
    if set(cel_payloads) != expected_cels:
        missing = sorted(expected_cels.difference(cel_payloads))
        extra = sorted(set(cel_payloads).difference(expected_cels))
        raise ValueError(f"split cel contract mismatch: missing={missing}, extra={extra}")

    images: dict[str, Image.Image] = {}
    input_hashes: dict[str, str] = {}
    input_stats: dict[str, dict[str, object]] = {}
    for terminal in representatives.values():
        payload = cel_payloads[terminal]
        try:
            with Image.open(io.BytesIO(payload)) as opened:
                if opened.format != "PNG":
                    raise ValueError
                image = opened.convert("RGBA")
        except Exception as error:
            raise ValueError(f"split cel must be a valid PNG: {terminal}") from error
        if image.width <= 0 or image.height <= 0 or image.width + 2 > sheet_width:
            raise ValueError(f"split cel cannot fit the configured sheet: {terminal}")
        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        if bbox is None:
            raise ValueError(f"split cel is fully transparent: {terminal}")
        images[terminal] = image
        input_hashes[terminal] = hashlib.sha256(payload).hexdigest()
        input_stats[terminal] = {
            "size": [image.width, image.height],
            "alpha_bbox": list(bbox),
            "alpha_values": sorted(set(alpha.get_flattened_data())),
        }

    placements: dict[str, dict[str, int]] = {}
    x = 1
    y = 1
    row_height = 0
    for terminal in representatives.values():
        image = images[terminal]
        if x + image.width + 1 > sheet_width:
            x = 1
            y += row_height + 2
            row_height = 0
        placements[terminal] = {
            "x": x,
            "y": y,
            "w": image.width,
            "h": image.height,
        }
        x += image.width + 2
        row_height = max(row_height, image.height)
    sheet_height = y + row_height + 1
    if maximum_sheet_height is not None and sheet_height > maximum_sheet_height:
        raise ValueError(
            f"split cels require sheet height {sheet_height}, above limit {maximum_sheet_height}"
        )

    sheet = Image.new("RGBA", (sheet_width, sheet_height), (0, 0, 0, 0))
    for terminal in representatives.values():
        geometry = placements[terminal]
        sheet.alpha_composite(images[terminal], (geometry["x"], geometry["y"]))

    compiled_atlas: list[dict[str, object]] = []
    for index, entry in enumerate(normalized):
        rectangle = tuple(entry.get(key) for key in _RECT_KEYS)
        terminal = representatives[rectangle]
        geometry = placements[terminal]
        output = copy.deepcopy(entry)
        output["n"] = target + "/" + str(output["n"])[len(source) + 1:]
        output.update(geometry)
        output.pop("r", None)
        if (
            -output["fx"] < 0
            or -output["fy"] < 0
            or -output["fx"] + output["w"] > output["fw"]
            or -output["fy"] + output["h"] > output["fh"]
        ):
            raise ValueError(f"rebuilt cel escapes its full frame: atlas record {index}")
        compiled_atlas.append(output)

    sheet_logical = f"{target}/{sheet_basename}.png"
    atlas_logical = f"{target}/{sheet_basename}.atlas.amf3.deflate"
    files = {
        sheet_logical: _stored_png(sheet),
        atlas_logical: _raw_deflate(wf_dsl.encode_amf3(compiled_atlas)),
    }
    report: dict[str, object] = {
        "schema_version": 1,
        "writes_live": False,
        "package_manifest_eligible": True,
        "source_prefix": source,
        "target_prefix": target,
        "sheet_basename": sheet_basename,
        "atlas_records": len(compiled_atlas),
        "unique_cels": len(images),
        "source_sheet_pixels_read": False,
        "rotation_records_removed": sum(bool(entry.get("r", False)) for entry in normalized),
        "sheet_size": [sheet_width, sheet_height],
        "input_sha256": input_hashes,
        "input_stats": input_stats,
        "output_sha256": {
            logical: hashlib.sha256(payload).hexdigest()
            for logical, payload in sorted(files.items())
        },
    }
    return files, report
