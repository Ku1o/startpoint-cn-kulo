"""Bound native gacha templates: same-canvas pixels, isolated anchors and namespaces.

Public API: inspect_template(), validate_textures(), validate_anchors(), build_native().
The support_root supplies the existing read-only tools/fantasy-gauntlet-mod-tools.
No template topology, artwork, business master, manifest, ZIP or runtime is created.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import importlib
import io
import json
import math
from pathlib import Path
import sys
import zlib

sys.dont_write_bytecode = True
from PIL import Image

SUFFIXES = ("feature.movie.amf3.deflate", "feature.timeline.amf3.deflate",
            "sprite_sheet.atlas.amf3.deflate", "sprite_sheet.png")
MODEL_LIMIT = "Bounded kind1 birth/modulo clock and preserved blend commands; not native engine or device execution."


class NativeBuildError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise NativeBuildError(message)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _json(path):
    return json.loads(Path(path).read_text("utf-8-sig"))


def _dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _support(root):
    root = Path(root).resolve()
    folder = root / "tools/fantasy-gauntlet-mod-tools"
    _require(folder.is_dir(), "support_root must contain tools/fantasy-gauntlet-mod-tools")
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    modules = []
    for name in ("wf_mod_tool", "wf_dsl", "wf_assets", "wf_flatomo_preview_render"):
        existing = sys.modules.get(name)
        _require(existing is None or Path(existing.__file__).resolve().is_relative_to(folder),
                 f"{name} was loaded from another support root; use a fresh Python process")
        modules.append(importlib.import_module(name))
    return root, modules


def _decode(raw, core):
    plain = zlib.decompress(raw, -15)
    reader = core.AMF3Reader(plain)
    value = reader.read_value()
    _require(reader.pos == len(plain), "AMF has trailing undecoded bytes")
    return value


def _encode(value, dsl):
    encoder = zlib.compressobj(level=9, wbits=-15)
    return encoder.compress(dsl.encode_amf3(value)) + encoder.flush()


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG", compress_level=9)
    return buffer.getvalue()


def _records(resources, base=None):
    if isinstance(resources, (str, Path)):
        path = Path(resources).resolve()
        base = path.parent
        resources = _json(path)
    _require(isinstance(resources, list) and len(resources) == 4, "exactly four bound resource records required")
    records, seen, prefixes = [], set(), set()
    for source in resources:
        row = dict(source)
        logical = row.get("logical", "")
        name = logical.rsplit("/", 1)[-1]
        _require(name in SUFFIXES and name not in seen, "duplicate or unsupported resource suffix")
        _require(row.get("root", "common") == "common", "only the common PNG Movie family is supported")
        seen.add(name)
        prefixes.add(logical.rsplit("/", 1)[0])
        file = Path(row["file"])
        if not file.is_absolute():
            file = (base or Path.cwd()) / file
        file = file.resolve()
        raw = file.read_bytes()
        _require("sha256" in row and "bytes" in row, "resource SHA256 and byte length are required")
        _require(_sha(raw) == row["sha256"].lower() and len(raw) == row["bytes"], f"bound resource changed: {file}")
        records.append({"logical": logical, "file": str(file), "sha256": _sha(raw), "bytes": len(raw)})
    _require(len(prefixes) == 1 and seen == set(SUFFIXES), "four resources must share one logical prefix")
    return records, next(iter(prefixes))


def _atlas_check(parts, atlas, sheet):
    names = [a["n"] for a in atlas]
    paths = [i["p"] for i in parts["i"]]
    _require(len(names) == len(set(names)) and set(names) == set(paths), "image/atlas path closure is not exact")
    _require(len(paths) == len(set(paths)), "duplicate image paths require a separately supported template")
    for index, a in enumerate(atlas):
        x, y, w, h = (int(a[k]) for k in ("x", "y", "w", "h"))
        _require(w > 0 and h > 0 and x >= 0 and y >= 0 and x + w <= sheet.width and y + h <= sheet.height,
                 f"atlas rectangle outside sheet: {a['n']}")
        for b in atlas[index + 1:]:
            _require(not (x < b["x"] + b["w"] and b["x"] < x + w and y < b["y"] + b["h"] and b["y"] < y + h),
                     "overlapping atlas rectangles")


def _read(resources, support_root):
    root, (core, dsl, assets, renderer) = _support(support_root)
    records, prefix = _records(resources)
    raw = {r["logical"].rsplit("/", 1)[-1]: Path(r["file"]).read_bytes() for r in records}
    parts = _decode(raw[SUFFIXES[0]], core)
    timeline = _decode(raw[SUFFIXES[1]], core)
    atlas = _decode(raw[SUFFIXES[2]], core)
    _require(parts["l"] == timeline, "embedded and external timelines differ")
    sheet = Image.open(io.BytesIO(assets.png_decode_stored(raw[SUFFIXES[3]]))).convert("RGBA")
    _atlas_check(parts, atlas, sheet)
    cells = renderer._load_cells(sheet, atlas, parts)
    return {"root": root, "core": core, "dsl": dsl, "assets": assets, "R": renderer,
            "records": records, "prefix": prefix, "raw": raw, "parts": parts,
            "timeline": timeline, "atlas": atlas, "sheet": sheet, "cells": cells}


def _expand(parts, renderer):
    """Same bounded kind1 model as the verified template studies, plus all local pools."""
    count_i, count_m, count_g = len(parts["i"]), len(parts["m"]), len(parts["g"])
    augmented = copy.deepcopy(parts)
    augmented["g"] += [dict(t=m["o"], s=m["s"]) for m in parts["m"]]
    for group in augmented["g"]:
        _require(isinstance(group["t"], int) and 0 < group["t"] <= 10000, "unsupported graphics frame count")
        for segment in group["s"]:
            kind = (int(segment["s"]) & 0xffffffff) >> 30
            child = int(segment["i"])
            _require(kind in (0, 1, 2), "unsupported native segment kind")
            _require(0 <= child < (count_i if kind == 0 else count_m if kind == 1 else count_g), "native child reference out of range")
            for key in segment["l"]:
                _require(0 <= int(key["m"]) >> 12 < len(parts["t"]), "matrix index out of range")
                if kind == 2:
                    _require(((int(key.get("r", 0)) & 0xffffffff) >> 30) in (0, 1, 2), "unsupported graphics loop mode")
    frames = renderer._build_frames(augmented)
    memo = {}

    def demand(g, frame, visiting=()):
        key = (g, frame)
        if key in memo:
            return memo[key]
        _require(key not in visiting and len(visiting) < 64, "recursive graphics scope")
        images, movies = collections.Counter(), collections.Counter()
        for state in frames[g][frame]:
            if state.kind == 0:
                images[state.item_id] += 1
            elif state.kind == 1:
                movies[state.item_id] += 1
            else:
                a, b = demand(state.item_id, state.child_frame, visiting + (key,))
                images.update(a)
                movies.update(b)
        memo[key] = images, movies
        return images, movies

    pools = []
    scopes = [("root", 0, parts["a"], parts["o"])]
    scopes += [(f"clip:{i}", count_g + i, m["i"], m["m"]) for i, m in enumerate(parts["m"])]
    for label, g, images_capacity, movie_capacity in scopes:
        _require(len(images_capacity) == count_i and len(movie_capacity) == count_m, f"{label} capacity dimensions differ")
        for frame in range(len(frames[g])):
            images, movies = demand(g, frame)
            for i, n in images.items():
                _require(n <= images_capacity[i], f"{label} image pool insufficient at frame {frame + 1}, slot {i}")
            for i, n in movies.items():
                _require(n <= movie_capacity[i], f"{label} clip pool insufficient at frame {frame + 1}, clip {i}")
        pools.append({"scope": label, "frames": len(frames[g]), "passed": True})
    history = {}

    def flatten(g, frame, tick, parent=(1, 0, 0, 1, 0, 0), alpha=1, route=(), blend=0, depth=0):
        _require(depth < 64, "native flatten depth exceeded")
        output = []
        for state in frames[g][frame]:
            _require(state.parameters.color == renderer.DEFAULT_COLOR_TRANSFORM, "color transforms require another supported renderer")
            matrix = renderer._concat(state.parameters.matrix, parent)
            opacity = alpha * state.parameters.alpha
            mode = state.parameters.blend or blend
            _require(mode in (0, 1), "unsupported blend mode")
            path = route + (g, state.segment_id)
            if state.kind == 0:
                output.append({"image": state.item_id, "matrix": list(matrix), "alpha": opacity, "blend": mode})
            elif state.kind == 2:
                output += flatten(state.item_id, state.child_frame, tick, matrix, opacity, path, mode, depth + 1)
            else:
                last, birth = history.get(path, (-2, tick))
                if last != tick - 1:
                    birth = tick
                history[path] = tick, birth
                total = parts["m"][state.item_id]["o"]
                output += flatten(count_g + state.item_id, (tick - birth) % total, tick, matrix, opacity, path, mode, depth + 1)
        return output

    return [flatten(0, tick, tick) for tick in range(len(frames[0]))], pools


def inspect_template(resources, *, support_root):
    data = _read(resources, support_root)
    frames, pools = _expand(data["parts"], data["R"])
    return {"logical_prefix": data["prefix"], "resources": data["records"],
            "images": len(data["parts"]["i"]), "graphics": len(data["parts"]["g"]),
            "clips": len(data["parts"]["m"]), "root_frames": len(frames),
            "atlas_size": list(data["sheet"].size), "scope_pools": pools,
            "cells": [{"slot": i, "path": data["parts"]["i"][i]["p"],
                       "decoded_size": list(c.image.size), "frame": [c.frame_x, c.frame_y],
                       "rgba_sha256": _sha(c.image.tobytes())} for i, c in enumerate(data["cells"])],
            "model_limit": MODEL_LIMIT, "device_verified": False}


def _textures(data, replacements, base):
    cells = [c.image.copy() for c in data["cells"]]
    proof, seen = [], set()
    for row in replacements:
        slot = row["slot"]
        _require(isinstance(slot, int) and 0 <= slot < len(cells) and slot not in seen, "invalid or duplicate texture slot")
        seen.add(slot)
        file = Path(row["file"])
        file = file if file.is_absolute() else base / file
        raw = file.read_bytes()
        if raw[1:4] == b"png":
            raw = data["assets"].png_decode_stored(raw)
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
        _require(image.size == cells[slot].size, f"slot {slot}: replacement must retain the decoded canvas size")
        if "logical_canvas" in row or "sample_scale" in row:
            logical = row.get("logical_canvas")
            scale = row.get("sample_scale", 1)
            _require(isinstance(logical, (list, tuple)) and len(logical) == 2 and scale in (1, 2), "declare logical_canvas plus sample_scale 1 or 2")
            _require(tuple(v * scale for v in logical) == image.size, f"slot {slot}: sampling contract does not match actual pixels")
        proof.append({"slot": slot, "file": str(file.resolve()), "size": list(image.size),
                      "before_rgba_sha256": _sha(cells[slot].tobytes()), "after_rgba_sha256": _sha(image.tobytes())})
        cells[slot] = image
    return cells, proof


def validate_textures(resources, textures, *, support_root):
    """Read-only same-canvas/sampling checks, independently of anchor edits."""
    data = _read(resources, support_root)
    _, proof = _textures(data, textures, Path.cwd())
    return {"status": "textures_valid", "textures": proof, "writes": False}


def _anchor_proof(frames, checks):
    proof = []
    for row in checks:
        slot, point = row["slot"], row["pivot_texture"]
        _require(len(point) == 2 and all(math.isfinite(float(v)) for v in point), "invalid anchor point")
        tolerance = float(row.get("tolerance_px", 1 / 1024))
        _require(0 < tolerance <= 0.1, "anchor tolerance must be positive and at most0.1px")
        values = []
        for index, commands in enumerate(frames):
            active = [c for c in commands if c["image"] == slot]
            _require(len(active) <= 1, "anchor requires a single instance of the image per frame")
            if active:
                a, b, c, d, x, y = active[0]["matrix"]
                values.append((index + 1, a * point[0] + c * point[1] + x, b * point[0] + d * point[1] + y))
        _require(values, "anchor slot never appears")
        drift = max(math.hypot(x - values[0][1], y - values[0][2]) for _, x, y in values)
        _require(drift <= tolerance, f"slot {slot}: anchor drift {drift:.6f}px exceeds {tolerance:.6f}px")
        proof.append({"slot": slot, "pivot_texture": point, "visible_frames": len(values),
                      "first_frame": values[0][0], "fixed_world_point": list(values[0][1:]), "max_drift_px": drift})
    return proof


def validate_anchors(resources, anchor_checks, *, support_root):
    """Read-only tip-lock regression gate; the artwork's verified tip is explicit."""
    data = _read(resources, support_root)
    frames, _ = _expand(data["parts"], data["R"])
    return {"status": "anchors_valid", "anchors": _anchor_proof(frames, anchor_checks), "writes": False}


def _apply_anchors(parts, edits):
    deltas, affected, old_count = [], set(), len(parts["t"])
    for row in edits:
        slot, leaf_g, outer_g, outer_s = (int(row[k]) for k in ("slot", "leaf_graphics", "outer_graphics", "outer_segment"))
        _require(slot not in affected, "duplicate anchor edit")
        affected.add(slot)
        leaf_group = parts["g"][leaf_g]
        _require(len(leaf_group["s"]) == 1, "anchor leaf must be a single-image graphics")
        leaf_segment = leaf_group["s"][0]
        _require((int(leaf_segment["s"]) & 0xffffffff) >> 30 == 0 and leaf_segment["i"] == slot and len(leaf_segment["l"]) == 1,
                 "anchor leaf must have one static matrix for the requested image")
        outer_segment = parts["g"][outer_g]["s"][outer_s]
        _require((int(outer_segment["s"]) & 0xffffffff) >> 30 == 2 and len(outer_segment["l"]) == 1,
                 "outer layout must be a constant graphics branch")

        def descendants(g, seen=()):
            _require(g not in seen and len(seen) < 64, "recursive anchor branch")
            found = set()
            for s in parts["g"][g]["s"]:
                kind = (int(s["s"]) & 0xffffffff) >> 30
                _require(kind != 1, "autonomous clips inside an anchor branch are not supported")
                found |= {s["i"]} if kind == 0 else descendants(s["i"], seen + (g,))
            return found

        _require(descendants(outer_segment["i"]) == {slot}, "outer anchor layout contains other images; isolate it first")
        keys = [leaf_segment["l"][0], outer_segment["l"][0]]
        old_leaf, old_outer = [copy.deepcopy(parts["t"][int(k["m"]) >> 12]) for k in keys]
        _require(old_outer["a"] == old_outer["d"] == 4096 and old_outer["b"] == old_outer["c"] == 0,
                 "outer anchor layout must be translation-only")
        _require(old_leaf["a"] == old_leaf["d"] and old_leaf["a"] > 0 and old_leaf["b"] == old_leaf["c"] == 0,
                 "anchor leaf must have a positive uniform scale")
        point = row["pivot_texture"]
        _require(len(point) == 2 and all(math.isfinite(float(v)) for v in point), "invalid anchor point")
        leaf = {**old_leaf, "x": round(-old_leaf["a"] * point[0]), "y": round(-old_leaf["d"] * point[1])}
        outer = {**old_outer, "x": old_outer["x"] + old_leaf["x"] - leaf["x"],
                 "y": old_outer["y"] + old_leaf["y"] - leaf["y"]}
        for key, matrix, path in zip(keys, (leaf, outer), (("g", leaf_g, "s", 0, "l", 0, "m"), ("g", outer_g, "s", outer_s, "l", 0, "m"))):
            old = key["m"]
            key["m"] = len(parts["t"]) * 4096 + (int(old) & 4095)
            parts["t"].append(matrix)
            deltas.append({"path": list(path), "before": old, "after": key["m"]})
    return deltas, affected, old_count


def _rename(value, old, new, path=(), changes=None):
    changes = changes if changes is not None else []
    if isinstance(value, dict):
        return {k: _rename(v, old, new, path + (k,), changes) for k, v in value.items()}
    if isinstance(value, list):
        return [_rename(v, old, new, path + (i,), changes) for i, v in enumerate(value)]
    if isinstance(value, str) and (value == old or value.startswith(old + "/")):
        replacement = new + value[len(old):]
        if replacement != value:
            changes.append({"path": list(path), "before": value, "after": replacement})
        return replacement
    return value


def _set_path(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def _pack(images, size):
    """Verified deterministic free-rectangle pack, with2px transparent gutters."""
    for ordering in (lambda p: -p[1].height, lambda p: -p[1].width * p[1].height, lambda p: -max(p[1].size)):
        free, positions = [(0, 0, *size)], {}
        for index, image in sorted(enumerate(images), key=ordering):
            w, h = image.width + 4, image.height + 4
            fits = [(min(r[2] - w, r[3] - h), max(r[2] - w, r[3] - h), r[1], r[0], r) for r in free if w <= r[2] and h <= r[3]]
            if not fits:
                break
            r = min(fits)[-1]
            px, py, pw, ph = r[0], r[1], w, h
            positions[index] = px + 2, py + 2
            remaining = []
            for x, y, rw, rh in free:
                if not (x < px + pw and px < x + rw and y < py + ph and py < y + rh):
                    remaining.append((x, y, rw, rh))
                    continue
                if px > x: remaining.append((x, y, px - x, rh))
                if px + pw < x + rw: remaining.append((px + pw, y, x + rw - px - pw, rh))
                if py > y: remaining.append((x, y, rw, py - y))
                if py + ph < y + rh: remaining.append((x, py + ph, rw, y + rh - py - ph))
            free = [a for i, a in enumerate(remaining) if a[2] > 0 and a[3] > 0 and not any(i != j and a[0] >= b[0] and a[1] >= b[1] and a[0] + a[2] <= b[0] + b[2] and a[1] + a[3] <= b[1] + b[3] and (a != b or i > j) for j, b in enumerate(remaining))]
        if len(positions) == len(images):
            sheet = Image.new("RGBA", size)
            for i, image in enumerate(images):
                sheet.paste(image, positions[i])
            return sheet, positions
    raise NativeBuildError("decoded cells do not fit the requested atlas budget; no automatic texture-size upgrade")


def build_native(spec, *, support_root, output_dir):
    """Build four payloads plus resources.json/model-data.json/receipt.json.

    `textures` only swaps equal decoded canvases. `anchors` explicitly identifies
    a static leaf and an isolated constant outer branch; original curves remain.
    `anchor_checks` can validate an existing template without changing anchors.
    Output must be a new directory outside support_root and template directories.
    """
    base = Path.cwd()
    if isinstance(spec, (str, Path)):
        file = Path(spec).resolve()
        base, spec = file.parent, _json(file)
    spec = dict(spec)
    _require(spec.get("schema_version", 1) == 1, "unsupported native spec schema")
    allowed = {"schema_version", "template_resources", "logical_prefix", "textures", "anchors", "anchor_checks", "repack", "atlas_size", "reference_frame", "label"}
    _require(not (set(spec) - allowed), f"unknown native spec fields: {sorted(set(spec) - allowed)}")
    resources = spec["template_resources"]
    if isinstance(resources, (str, Path)) and not Path(resources).is_absolute():
        resources = base / resources
    data = _read(resources, support_root)
    out = Path(output_dir).resolve()
    _require(not out.exists(), "output_dir must be new; accepted outputs are never overwritten")
    _require(not out.is_relative_to(data["root"]) and ".cdn" not in out.parts, "output_dir must be outside the support repository/CDN")
    _require(all(not out.is_relative_to(Path(r["file"]).parent) for r in data["records"]), "output_dir must not be inside a template payload directory")
    source = data["parts"]
    before, before_pools = _expand(source, data["R"])
    parts = copy.deepcopy(source)
    prefix = spec.get("logical_prefix", data["prefix"]).strip("/")
    _require(prefix.startswith("gacha/feature_movie/") and "\\" not in prefix and ".." not in prefix.split("/"), "invalid native gacha logical_prefix")
    path_changes = []
    parts = _rename(parts, data["prefix"], prefix, changes=path_changes)
    for record in parts["i"]:
        _require(record["p"].startswith(prefix + "/"), "template image path is outside its owned logical prefix")
    matrix_changes, motion_slots, old_matrix_count = _apply_anchors(parts, spec.get("anchors", []))
    cells, texture_proof = _textures(data, spec.get("textures", []), base)
    atlas = copy.deepcopy(data["atlas"])
    by_name = {a["n"]: a for a in atlas}
    if spec.get("repack", False):
        size = spec.get("atlas_size", list(data["sheet"].size))
        size = (size, size) if isinstance(size, int) else tuple(size)
        _require(len(size) == 2 and all(isinstance(v, int) and 0 < v <= 2048 for v in size), "atlas budget must be explicit and at most2048 per dimension")
        sheet, positions = _pack(cells, size)
        atlas = []
        for i, image in enumerate(cells):
            entry = {k: v for k, v in by_name[source["i"][i]["p"]].items() if k not in ("x", "y", "w", "h", "r")}
            entry.update(n=parts["i"][i]["p"], x=positions[i][0], y=positions[i][1], w=image.width, h=image.height)
            atlas.append(entry)
    else:
        sheet = data["sheet"].copy()
        for i in {r["slot"] for r in texture_proof}:
            entry = by_name[source["i"][i]["p"]]
            stored = cells[i].transpose(Image.Transpose.ROTATE_270) if entry.get("r") else cells[i]
            _require(stored.size == (entry["w"], entry["h"]), "stored texture orientation size mismatch")
            sheet.paste(stored, (entry["x"], entry["y"]))
        atlas = _rename(atlas, data["prefix"], prefix)
    _atlas_check(parts, atlas, sheet)
    raw = dict(data["raw"])
    if parts != source: raw[SUFFIXES[0]] = _encode(parts, data["dsl"])
    if atlas != data["atlas"]: raw[SUFFIXES[2]] = _encode(atlas, data["dsl"])
    if sheet.tobytes() != data["sheet"].tobytes() or sheet.size != data["sheet"].size:
        raw[SUFFIXES[3]] = data["assets"].png_encode(_png(sheet))
    actual = _decode(raw[SUFFIXES[0]], data["core"])
    actual_atlas = _decode(raw[SUFFIXES[2]], data["core"])
    actual_sheet = Image.open(io.BytesIO(data["assets"].png_decode_stored(raw[SUFFIXES[3]]))).convert("RGBA")
    _require(actual == parts and actual_atlas == atlas, "stored AMF roundtrip differs")
    _require(raw[SUFFIXES[1]] == data["raw"][SUFFIXES[1]] and actual["l"] == data["timeline"], "timeline bytes or semantics changed")
    _atlas_check(actual, actual_atlas, actual_sheet)
    actual_cells = data["R"]._load_cells(actual_sheet, actual_atlas, actual)
    for i, (expected, cell, old_cell) in enumerate(zip(cells, actual_cells, data["cells"])):
        _require(expected.size == cell.image.size and expected.tobytes() == cell.image.tobytes(), f"slot {i}: RGBA roundtrip differs")
        _require((cell.frame_x, cell.frame_y) == (old_cell.frame_x, old_cell.frame_y), f"slot {i}: logical trim anchor changed")
    after, pools = _expand(actual, data["R"])
    _require(len(before) == len(after), "root frame count changed")
    changed_frames = []
    for tick, (old, new) in enumerate(zip(before, after)):
        _require([c["image"] for c in old] == [c["image"] for c in new], "draw order or instance count changed")
        _require([c for c in old if c["image"] not in motion_slots] == [c for c in new if c["image"] not in motion_slots], "non-target frame commands changed")
        for a, b in zip(old, new):
            _require(a["matrix"][:4] == b["matrix"][:4] and a["alpha"] == b["alpha"] and a["blend"] == b["blend"], "anchor edit changed scale/rotation/opacity/blend")
        if old != new: changed_frames.append(tick + 1)
    reference_frame = spec.get("reference_frame", len(after))
    _require(isinstance(reference_frame, int) and 1 <= reference_frame <= len(after), "reference_frame is one-based")
    _require(before[reference_frame - 1] == after[reference_frame - 1], "reference stable frame changed; anchor placement is not applicable to this template")
    anchor_checks = list(spec.get("anchor_checks", []))
    checked = {r["slot"] for r in anchor_checks}
    anchor_checks += [{"slot": r["slot"], "pivot_texture": r["pivot_texture"]} for r in spec.get("anchors", []) if r["slot"] not in checked]
    anchor_proof = _anchor_proof(after, anchor_checks)
    restored = copy.deepcopy(actual)
    for delta in matrix_changes: _set_path(restored, delta["path"], delta["before"])
    restored["t"] = restored["t"][:old_matrix_count]
    for delta in path_changes: _set_path(restored, delta["path"], delta["before"])
    _require(restored == source, "AST differs outside declared namespace/matrix changes")
    # All validation precedes writes; only this new task directory is materialized.
    (out / "payload").mkdir(parents=True)
    (out / "cells").mkdir()
    records = []
    for suffix in SUFFIXES:
        file = out / "payload" / suffix
        file.write_bytes(raw[suffix])
        records.append({"logical": prefix + "/" + suffix, "file": str(file), "sha256": _sha(raw[suffix]), "bytes": len(raw[suffix])})
    cell_records = []
    for i, cell in enumerate(actual_cells):
        file = out / "cells" / f"{i:02}.png"
        file.write_bytes(_png(cell.image))
        cell_records.append({"file": str(file), "frame": [cell.frame_x, cell.frame_y]})
    ends = [s["begin"] for s in actual["l"]["sequences"] if s["name"] == "end"]
    page = {"frameCount": len(after), "endBegin": ends[0] if ends else len(after), "timeline": actual["l"], "frames": after, "cells": cell_records, "label": spec.get("label", "Bound native template")}
    _dump(out / "model-data.json", {"pages": {prefix.rsplit("/", 1)[-1]: page}})
    _dump(out / "resources.json", records)
    receipt = {"schema_version": 1, "status": "native_template_built_offline", "resources_file": str(out / "resources.json"),
               "model_file": str(out / "model-data.json"), "receipt_file": str(out / "receipt.json"), "cells_dir": str(out / "cells"),
               "resources": records, "source_resources": data["records"], "source_prefix": data["prefix"], "logical_prefix": prefix,
               "counts": {"images": len(actual["i"]), "graphics": len(actual["g"]), "clips": len(actual["m"]), "root_frames": len(after)},
               "atlas_size": list(actual_sheet.size), "repacked": bool(spec.get("repack", False)), "texture_changes": texture_proof,
               "namespace_deltas": path_changes, "matrix_deltas": matrix_changes, "appended_matrices": actual["t"][old_matrix_count:],
               "changed_motion_frames": changed_frames, "reference_frame": reference_frame, "anchor_checks": anchor_proof,
               "scope_pools": pools, "source_scope_pools": before_pools,
               "cell_rgba_sha256": [_sha(c.image.tobytes()) for c in actual_cells],
               "checks": {"four_resource_closure": True, "stored_readback": True, "timeline_bytes_exact": True,
                          "all_cells_rgba_roundtrip_exact": True, "non_target_cells_rgba_exact": all(cells[i].tobytes() == data["cells"][i].image.tobytes() for i in range(len(cells)) if i not in {r["slot"] for r in texture_proof}),
                          "trim_frames_exact": True, "reverse_ast_exact": True, "topology_exact": True,
                          "all_frames_expanded": True, "non_target_commands_exact": True, "scale_rotation_alpha_blend_exact": True,
                          "reference_frame_exact": True, "all_local_scope_pools": True},
               "model_limit": MODEL_LIMIT, "device_verified": False, "activated": False}
    _dump(out / "receipt.json", receipt)
    for row in data["records"]:
        _require(_sha(Path(row["file"]).read_bytes()) == row["sha256"], "source resource drifted during build")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--support-root", required=True, type=Path)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--spec", type=Path)
    choice.add_argument("--inspect", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.inspect:
            result = inspect_template(args.inspect, support_root=args.support_root)
        else:
            _require(args.output is not None, "--output is required with --spec")
            result = build_native(args.spec, support_root=args.support_root, output_dir=args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (NativeBuildError, OSError, ValueError, KeyError) as error:
        parser.exit(2, f"gacha_native: {error}\n")


if __name__ == "__main__":
    main()
