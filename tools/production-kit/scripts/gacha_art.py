"""Offline, recipe-driven PNG composition. Uses Pillow; never publishes resources.

build_art(spec, *, output_dir) -> receipt
Image order: crop -> optional source-size mask -> uniform fit/scale -> rotation
(expand=True, counter-clockwise) -> opacity -> composite at top-left position.
Text positions/anchors use Pillow's TrueType anchor convention (default ``la``).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

MAX_PIXELS = 64 * 1024 * 1024
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _keys(value, allowed, required, label):
    _require(isinstance(value, dict), f"{label} must be an object")
    _require(not (set(value) - set(allowed)), f"Unknown {label} fields: {sorted(set(value) - set(allowed))}")
    _require(set(required) <= set(value), f"Missing {label} fields: {sorted(set(required) - set(value))}")


def _number(value, label, *, positive=False):
    _require(type(value) in (int, float) and math.isfinite(value), f"{label} must be a finite number")
    if positive:
        _require(value > 0, f"{label} must be positive")
    return value


def _pair(value, label, *, dimensions=False):
    _require(isinstance(value, (list, tuple)) and len(value) == 2, f"{label} needs two values")
    for item in value:
        _number(item, label, positive=dimensions)
        if dimensions:
            _require(type(item) is int, f"{label} needs integer dimensions")
    if dimensions:
        _require(value[0] * value[1] <= MAX_PIXELS, f"{label} exceeds pixel limit")
    return tuple(value)


def _color(value, label, *, rgba=False):
    _require(isinstance(value, (list, tuple)) and len(value) in ((4,) if rgba else (3, 4)), f"{label} must be RGB/RGBA")
    _require(all(type(v) is int and 0 <= v <= 255 for v in value), f"{label} channels must be 0..255 integers")
    return tuple(value) if len(value) == 4 else (*value, 255)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bound_file(record, role):
    _keys(record, {"file", "sha256", "bytes"}, {"file", "sha256"}, role)
    _require(isinstance(record["file"], str), f"{role}.file must be a path")
    expected = record["sha256"]
    _require(isinstance(expected, str) and re.fullmatch(r"[a-fA-F0-9]{64}", expected) is not None, f"{role} requires SHA256")
    file = Path(record["file"]).resolve(strict=True)
    _require(file.is_file(), f"{role} is not a file: {file}")
    raw = file.read_bytes()
    _require(_sha(raw) == expected.lower(), f"SHA256 mismatch: {file}")
    _require("bytes" not in record or record["bytes"] == len(raw), f"Byte count mismatch: {file}")
    return raw, {"role": role, "file": str(file), "sha256": expected.lower(), "bytes": len(raw)}


def _open(raw):
    with Image.open(io.BytesIO(raw)) as opened:
        _require(opened.width * opened.height <= MAX_PIXELS, "Source image exceeds pixel limit")
        opened.load()
        return opened.copy()


def _alpha(image):
    alpha = image.getchannel("A")
    lo, hi = alpha.getextrema()
    return {"range": [lo, hi], "bbox": list(alpha.getbbox()) if alpha.getbbox() else None,
            "nonzero_pixels": sum(alpha.histogram()[1:])}


def _opacity(image, value):
    _number(value, "opacity")
    _require(0 <= value <= 1, "opacity must be 0..1")
    if value != 1:
        image.putalpha(image.getchannel("A").point([round(i * value) for i in range(256)]))
    return image


def _image_layer(layer):
    allowed = {"file", "sha256", "bytes", "position", "scale", "size", "crop", "opacity", "rotation", "mask"}
    _keys(layer, allowed, {"file", "sha256", "position"}, "image layer")
    _require(not ("scale" in layer and "size" in layer), "scale and size are mutually exclusive")
    raw, binding = _bound_file({k: layer[k] for k in ("file", "sha256", "bytes") if k in layer}, "image")
    original = _open(raw).convert("RGBA")
    image = original.copy()
    binding.update(size=list(original.size), alpha=_alpha(original))
    sources = [binding]
    if "crop" in layer:
        crop = layer["crop"]
        _require(isinstance(crop, (list, tuple)) and len(crop) == 4 and all(type(v) is int for v in crop), "crop must be integer [x,y,width,height]")
        x, y, w, h = crop
        _require(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= image.width and y + h <= image.height, "crop outside source image")
        image = image.crop((x, y, x + w, y + h))
    if "mask" in layer:
        mask_raw, mask_binding = _bound_file(layer["mask"], "mask")
        mask = _open(mask_raw)
        _require(mask.size == image.size, "mask dimensions must equal cropped source; no implicit stretching")
        _require(mask.mode in ("1", "L", "LA", "RGBA"), "mask must have luminance or alpha")
        mask = mask.getchannel("A") if "A" in mask.getbands() else mask.convert("L")
        image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
        sources.append(mask_binding)
    cropped_size = image.size
    factor = 1
    if "scale" in layer:
        factor = _number(layer["scale"], "scale (single uniform factor)", positive=True)
    elif "size" in layer:
        box = _pair(layer["size"], "fit size", dimensions=True)
        factor = min(box[0] / image.width, box[1] / image.height)
    scaled = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    _pair(scaled, "scaled image", dimensions=True)
    if image.size != scaled:
        image = image.resize(scaled, Image.Resampling.LANCZOS)
    angle = _number(layer.get("rotation", 0), "rotation")
    if angle % 360:
        image = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        _pair(image.size, "rotated image", dimensions=True)
    image = _opacity(image, layer.get("opacity", 1))
    return image, sources, {"kind": "image", "source_size": list(original.size), "cropped_size": list(cropped_size),
        "uniform_scale": factor, "scaled_size": list(scaled), "rendered_size": list(image.size),
        "rotation": angle, "opacity": layer.get("opacity", 1), "crop": layer.get("crop"), "mask": layer.get("mask")}


def _text_layer(layer, canvas_size):
    allowed = {"text", "font", "font_size", "position", "fill", "stroke_fill", "stroke_width", "anchor", "opacity"}
    _keys(layer, allowed, {"text", "font", "font_size", "position", "fill"}, "text layer")
    _require(isinstance(layer["text"], str) and "\n" not in layer["text"] and "\r" not in layer["text"], "text must be a single line")
    size = layer["font_size"]
    _require(type(size) is int and size > 0, "font_size must be a positive integer")
    width = layer.get("stroke_width", 0)
    _require(type(width) is int and width >= 0, "stroke_width must be a nonnegative integer")
    anchor = layer.get("anchor", "la")
    _require(isinstance(anchor, str) and re.fullmatch(r"[lmr][atmsbd]", anchor) is not None, "Unsupported text anchor")
    raw, binding = _bound_file(layer["font"], "font")
    font = ImageFont.truetype(io.BytesIO(raw), size)
    image = Image.new("RGBA", canvas_size)
    fill = _color(layer["fill"], "fill")
    stroke = _color(layer.get("stroke_fill", fill), "stroke_fill")
    draw = ImageDraw.Draw(image)
    position = _pair(layer["position"], "text position")
    text_bbox = draw.textbbox(position, layer["text"], font=font, stroke_width=width, anchor=anchor)
    draw.text(position, layer["text"], font=font,
        fill=fill, stroke_fill=stroke, stroke_width=width, anchor=anchor)
    image = _opacity(image, layer.get("opacity", 1))
    return image, [binding], {"kind": "text", "text": layer["text"], "font_size": size, "fill": list(fill),
        "stroke_fill": list(stroke), "stroke_width": width, "anchor": anchor, "opacity": layer.get("opacity", 1),
        "text_bbox": list(text_bbox), "clipped_to_canvas": any((text_bbox[0] < 0, text_bbox[1] < 0, text_bbox[2] > canvas_size[0], text_bbox[3] > canvas_size[1]))}


def build_art(spec, *, output_dir):
    """Compose ordered layers; return/write a SHA-bound receipt. Refuse overwrite.

    ``size`` is a containing box, always fitted uniformly, never stretched.
    ``mask`` uses the cropped image's dimensions before resize/rotation.
    Image positions are integer top-left pixels after transformation. Text
    positions may be fractional and follow the explicitly selected text anchor.
    """
    _keys(spec, {"schema_version", "artifacts"}, {"schema_version", "artifacts"}, "spec")
    _require(type(spec["schema_version"]) is int and spec["schema_version"] == 1, "Unsupported schema_version")
    _require(isinstance(spec["artifacts"], list) and spec["artifacts"], "artifacts must be nonempty")
    output = Path(output_dir).resolve()
    _require(not output.exists() or output.is_dir(), "output_dir must be a directory")
    _require(not (output / "receipt.json").exists(), "Refusing to overwrite receipt.json")
    keys = set()
    for artifact in spec["artifacts"]:
        _keys(artifact, {"key", "size", "background", "layers"}, {"key", "size", "background", "layers"}, "artifact")
        key = artifact["key"]
        _require(isinstance(key, str) and 0 < len(key) <= 80 and all(c.isalnum() or c in "_-" for c in key), "Unsafe artifact key")
        _require(key.upper() not in _RESERVED_NAMES, f"Reserved artifact key: {key}")
        _require(key.casefold() not in keys, f"Duplicate artifact key: {key}")
        keys.add(key.casefold())
        _require(not (output / f"{key}.png").exists(), f"Refusing to overwrite {key}.png")
    rendered = []
    for artifact in spec["artifacts"]:
        size = _pair(artifact["size"], "artifact size", dimensions=True)
        canvas = Image.new("RGBA", size, _color(artifact["background"], "background", rgba=True))
        _require(isinstance(artifact["layers"], list), "layers must be a list")
        layers = []
        for index, layer in enumerate(artifact["layers"]):
            _require(isinstance(layer, dict), "layer must be an object")
            if "text" in layer:
                image, sources, receipt = _text_layer(layer, size)
                position = (0, 0)
            else:
                image, sources, receipt = _image_layer(layer)
                position = _pair(layer["position"], "image position")
                _require(all(type(v) is int for v in position), "image position needs integer pixels")
            canvas.alpha_composite(image, dest=position)
            layers.append({**receipt, "index": index, "position": list(layer["position"]), "sources": sources})
        blob = io.BytesIO()
        canvas.save(blob, format="PNG", compress_level=9)
        raw = blob.getvalue()
        rendered.append((artifact["key"], raw, {"key": artifact["key"], "file": str(output / f"{artifact['key']}.png"),
            "sha256": _sha(raw), "bytes": len(raw), "size": list(canvas.size), "mode": "RGBA",
            "background": list(artifact["background"]), "alpha": _alpha(canvas), "layers": layers}))
    receipt = {"schema_version": 1, "status": "art_composition_built", "spec_sha256": _sha(json.dumps(spec, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")),
        "transform_order": "crop, mask, uniform scale/fit, expanded CCW rotation, opacity, ordered alpha composite",
        "artifacts": [row for _, _, row in rendered], "published": False}
    output.mkdir(parents=True, exist_ok=True)
    for key, raw, _ in rendered:
        with (output / f"{key}.png").open("xb") as handle:
            handle.write(raw)
    with (output / "receipt.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return receipt
