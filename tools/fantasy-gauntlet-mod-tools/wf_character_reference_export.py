#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export one live CN character as a read-only, human-facing reference bundle.

The exporter reads the client-visible terminal CDN without materialising the
store.  It emits decoded UI/pixel/voice assets, human-readable master rows,
ActionDsl trees, and every directly referenced ``battle/effect`` four-piece.
It never writes the live store, active patches, server data, or a release.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
import zlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from PIL import Image, ImageDraw


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
TOOL_ROOT = Path(__file__).resolve().parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import wf_assets  # noqa: E402
import wf_character_requirements as requirements  # noqa: E402
import wf_dsl  # noqa: E402
import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402


PATHLIST = TOOL_ROOT / "WF_PATHLIST_recovered.txt"
OUTPUT_ROOT = SOURCE_ROOT / "work" / "character-reference"
FRAME_NUMBER = re.compile(r"(\d+)$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ExportError(RuntimeError):
    pass


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_relative(value: str) -> PurePosixPath:
    if "\\" in value:
        raise ExportError(f"output path uses a backslash: {value}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ExportError(f"unsafe output path: {value}")
    return path


class BundleWriter:
    def __init__(self, root: Path):
        self.root = root
        self.records: dict[str, dict[str, Any]] = {}

    def write(self, relative: str, raw: bytes, **metadata: Any) -> Path:
        pure = safe_relative(relative)
        target = self.root.joinpath(*pure.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        self.records[pure.as_posix()] = {
            "size": len(raw),
            "sha256": sha256_bytes(raw),
            **metadata,
        }
        return target

    def text(self, relative: str, value: str, **metadata: Any) -> Path:
        return self.write(relative, value.encode("utf-8-sig"), **metadata)

    def json(self, relative: str, value: Any, **metadata: Any) -> Path:
        return self.text(relative, json_text(value), **metadata)


def load_repo_json(relative: str) -> Any:
    return json.loads((SOURCE_ROOT / relative).read_text(encoding="utf-8-sig"))


def decode_amf3_deflate(raw: bytes, logical: str) -> Any:
    try:
        inflater = zlib.decompressobj(-15)
        plain = inflater.decompress(raw) + inflater.flush()
        if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise ValueError("not one strict raw-deflate stream")
        reader = core.AMF3Reader(plain)
        value = reader.read_value()
        if reader.pos != len(plain):
            raise ValueError("trailing AMF3 bytes")
        return value
    except Exception as exc:
        raise ExportError(f"cannot decode AMF3 metadata: {logical}") from exc


def live_variants(logical: str) -> list[Any]:
    digest = core.sha1_path(logical)
    relative = f"{digest[:2]}/{digest[2:]}"
    found = []
    for root in wf_live_cdn.ROOT_ORDER:
        try:
            found.append(wf_live_cdn.read_relative(relative, roots=(root,)))
        except FileNotFoundError:
            pass
    return found


def live_one(logical: str, preferred: Iterable[str] = ("common", "medium")) -> Any:
    digest = core.sha1_path(logical)
    try:
        return wf_live_cdn.read_relative(
            f"{digest[:2]}/{digest[2:]}", roots=tuple(preferred)
        )
    except FileNotFoundError as exc:
        raise ExportError(f"live logical path is missing: {logical}") from exc


def try_live(logical: str, preferred: Iterable[str] = wf_live_cdn.ROOT_ORDER) -> Any | None:
    try:
        return live_one(logical, preferred)
    except ExportError:
        return None


def standard_png(raw: bytes, logical: str) -> bytes:
    decoded = wf_assets.png_decode(raw)
    if not decoded.startswith(PNG_SIGNATURE):
        raise ExportError(f"decoded image is not a PNG: {logical}")
    return decoded


def image_size(raw: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(raw)) as opened:
        return opened.size


def csv_rows(text: str) -> list[list[str]]:
    return [row for row in csv.reader(io.StringIO(text)) if row]


def flat_table(logical: str) -> tuple[dict[str, str], Any]:
    live = live_one(logical, ("common",))
    try:
        return core.read_orderedmap_file_from_bytes(live.data), live
    except Exception as exc:
        raise ExportError(f"cannot decode flat table: {logical}") from exc


def table_selection(logical: str, keys: Iterable[str]) -> dict[str, Any]:
    rows, live = flat_table(logical)
    selected = {
        key: {"raw_csv": rows[key], "rows": csv_rows(rows[key])}
        for key in keys
        if key in rows
    }
    return {
        "logical_path": logical,
        "source_archive": live.archive.name,
        "source_tail": live.tail,
        "selected": selected,
    }


def contact_sheet(
    items: list[tuple[str, bytes]], *, cell: tuple[int, int] = (240, 240), columns: int = 4
) -> bytes | None:
    if not items:
        return None
    label_height = 28
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell[0], rows * (cell[1] + label_height)), (34, 34, 38))
    draw = ImageDraw.Draw(sheet)
    for index, (label, raw) in enumerate(items):
        with Image.open(io.BytesIO(raw)) as opened:
            image = opened.convert("RGBA")
        scale = min((cell[0] - 16) / image.width, (cell[1] - 16) / image.height)
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
        background = Image.new("RGBA", cell, (50, 50, 56, 255))
        x = (cell[0] - image.width) // 2
        y = (cell[1] - image.height) // 2
        background.alpha_composite(image, (x, y))
        left = (index % columns) * cell[0]
        top = (index // columns) * (cell[1] + label_height)
        sheet.paste(background.convert("RGB"), (left, top))
        draw.text((left + 6, top + cell[1] + 6), label[:38], fill=(235, 235, 240))
    stream = io.BytesIO()
    sheet.save(stream, format="PNG", compress_level=9)
    return stream.getvalue()


def atlas_crop(sheet: Image.Image, entry: dict[str, Any]) -> Image.Image:
    x, y = int(entry["x"]), int(entry["y"])
    width, height = int(entry["w"]), int(entry["h"])
    crop = sheet.crop((x, y, x + width, y + height))
    if entry.get("r", False):
        crop = crop.transpose(Image.Transpose.ROTATE_90)
    return crop


def sanitized_cell_name(value: str) -> str:
    clean = value.replace("\\", "/").strip("/")
    clean = re.sub(r"[^A-Za-z0-9._-]+", "__", clean)
    return clean or "cell"


def split_atlas_cells(
    writer: BundleWriter,
    *,
    sheet_raw: bytes,
    atlas: list[Any],
    output_prefix: str,
    pixel_mode: bool,
) -> tuple[int, list[dict[str, Any]], list[tuple[str, bytes]]]:
    with Image.open(io.BytesIO(sheet_raw)) as opened:
        sheet = opened.convert("RGBA")
    representatives: dict[tuple[Any, ...], str] = {}
    manifest: list[dict[str, Any]] = []
    previews: list[tuple[str, bytes]] = []
    for index, raw in enumerate(atlas):
        if not isinstance(raw, dict):
            raise ExportError(f"atlas entry {index} is not an object")
        name = str(raw.get("n", ""))
        rectangle = (
            raw.get("x"), raw.get("y"), raw.get("w"), raw.get("h"), raw.get("r", False)
        )
        representative = representatives.setdefault(rectangle, name)
        manifest.append({
            "name": name,
            "representative": representative,
            "source": {
                key: raw.get(key)
                for key in ("x", "y", "w", "h", "r", "fx", "fy", "fw", "fh")
                if key in raw
            },
        })
        if representative != name:
            continue
        image = atlas_crop(sheet, raw)
        stream = io.BytesIO()
        image.save(stream, format="PNG", compress_level=9)
        payload = stream.getvalue()
        terminal = name.rsplit("/", 1)[-1] if pixel_mode else sanitized_cell_name(name)
        writer.write(f"{output_prefix}/{terminal}.png", payload, atlas_name=name)
        previews.append((terminal, payload))
    return len(representatives), manifest, previews


def render_pixel_frame(sheet: Image.Image, entry: dict[str, Any]) -> Image.Image:
    crop = atlas_crop(sheet, entry)
    width = int(entry.get("fw", crop.width))
    height = int(entry.get("fh", crop.height))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.paste(crop, (-int(entry.get("fx", 0)), -int(entry.get("fy", 0))), crop)
    return canvas


def pixel_gifs(
    writer: BundleWriter,
    *,
    sheet_raw: bytes,
    atlas: list[Any],
    timeline: dict[str, Any],
    output_prefix: str,
) -> list[dict[str, Any]]:
    with Image.open(io.BytesIO(sheet_raw)) as opened:
        sheet = opened.convert("RGBA")
    numbered: list[tuple[int, dict[str, Any]]] = []
    for raw in atlas:
        if not isinstance(raw, dict):
            continue
        match = FRAME_NUMBER.search(str(raw.get("n", "")))
        if match:
            numbered.append((int(match.group(1)), raw))
    numbered.sort(key=lambda item: item[0])
    ticks = [item[0] for item in numbered]
    if not numbered:
        return []
    reports = []
    for sequence in timeline.get("sequences", []):
        if not isinstance(sequence, dict):
            continue
        begin, end = int(sequence["begin"]), int(sequence["end"])
        collapsed: list[tuple[dict[str, Any], int]] = []
        previous_signature = None
        for tick in range(begin, end + 1):
            offset = bisect.bisect_right(ticks, tick) - 1
            entry = numbered[max(0, offset)][1]
            signature = tuple(entry.get(key) for key in (
                "n", "x", "y", "w", "h", "r", "fx", "fy", "fw", "fh"
            ))
            if signature == previous_signature:
                collapsed[-1] = (collapsed[-1][0], collapsed[-1][1] + 1)
            else:
                collapsed.append((entry, 1))
                previous_signature = signature
        frames = [render_pixel_frame(sheet, entry) for entry, _duration in collapsed]
        boxes = [frame.getchannel("A").getbbox() for frame in frames]
        boxes = [box for box in boxes if box is not None]
        if not boxes:
            continue
        left = max(0, min(box[0] for box in boxes) - 3)
        top = max(0, min(box[1] for box in boxes) - 3)
        right = min(frames[0].width, max(box[2] for box in boxes) + 3)
        bottom = min(frames[0].height, max(box[3] for box in boxes) + 3)
        cropped = [frame.crop((left, top, right, bottom)) for frame in frames]
        largest = max(right - left, bottom - top)
        scale = max(1, min(4, 320 // max(1, largest)))
        if scale > 1:
            cropped = [frame.resize(
                (frame.width * scale, frame.height * scale), Image.Resampling.NEAREST
            ) for frame in cropped]
        durations = [max(20, round(count * 1000 / 60)) for _entry, count in collapsed]
        stream = io.BytesIO()
        cropped[0].save(
            stream,
            format="GIF",
            save_all=True,
            append_images=cropped[1:],
            duration=durations,
            loop=0,
            disposal=2,
            optimize=False,
        )
        name = sanitized_cell_name(str(sequence.get("name", "sequence")))
        writer.write(
            f"{output_prefix}/{name}.gif",
            stream.getvalue(),
            sequence=sequence,
        )
        reports.append({
            "name": sequence.get("name"),
            "kind": sequence.get("kind"),
            "begin": begin,
            "end": end,
            "gif_frames": len(cropped),
            "source_ticks": end - begin + 1,
        })
    return reports


def character_candidates(code_name: str) -> list[str]:
    prefix = f"character/{code_name}/"
    candidates: set[str] = set()
    if PATHLIST.is_file():
        for line in PATHLIST.read_text(encoding="utf-8-sig").splitlines():
            logical = line.strip()
            if logical.startswith(prefix):
                candidates.add(logical)
    candidates.update(item.logical_path for item in requirements.char_asset_requirements(code_name))
    return sorted(candidates)


def export_character_assets(
    writer: BundleWriter, code_name: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prefix = f"character/{code_name}/"
    requirement_map = {
        item.logical_path: item for item in requirements.char_asset_requirements(code_name)
    }
    contract: list[dict[str, Any]] = []
    png_contacts: list[tuple[str, bytes]] = []
    story_contacts: list[tuple[str, bytes]] = []
    pixel_payloads: dict[str, bytes] = {}
    pixel_trees: dict[str, Any] = {}
    voice_counts: defaultdict[str, int] = defaultdict(int)

    for logical in character_candidates(code_name):
        relative = logical[len(prefix):]
        variants = live_variants(logical)
        req = requirement_map.get(logical)
        row: dict[str, Any] = {
            "logical_path": logical,
            "relative_path": relative,
            "requirement_category": req.category if req else "discovered",
            "exists": bool(variants),
            "variants": [{
                "root": item.root,
                "size": len(item.data),
                "archive": item.archive.name,
                "member": item.member,
            } for item in variants],
        }
        if not variants:
            contract.append(row)
            continue

        if relative.endswith(".atf.deflate"):
            row["export"] = "not exported; platform derivative"
            contract.append(row)
            continue
        live = next(
            (item for item in variants if item.root in ("common", "medium")), variants[0]
        )
        if relative.endswith(".png"):
            standard = standard_png(live.data, logical)
            dims = image_size(standard)
            row["dimensions"] = list(dims)
            if relative.startswith("pixelart/"):
                target = f"reference/pixelart/{Path(relative).name}"
                pixel_payloads[Path(relative).name] = standard
            elif relative.startswith("ui/story/"):
                target = f"reference/ui/story/{Path(relative).name}"
                story_contacts.append((Path(relative).stem, standard))
            else:
                target = f"reference/ui/{Path(relative).name}"
                png_contacts.append((Path(relative).stem, standard))
            writer.write(target, standard, logical_path=logical, source_root=live.root)
            row["export"] = target
        elif relative.endswith(".mp3"):
            category = relative.split("/", 2)[1]
            voice_counts[category] += 1
            if category == "words":
                row["export"] = "slot listed only"
            else:
                decoded = wf_assets.mp3_decode(live.data)
                target = f"reference/voice/{relative[len('voice/') :]}"
                writer.write(target, decoded, logical_path=logical, source_root=live.root)
                row["export"] = target
        elif relative.startswith("pixelart/") and relative.endswith(".amf3.deflate"):
            tree = decode_amf3_deflate(live.data, logical)
            stem = Path(relative).name.removesuffix(".amf3.deflate")
            target = f"reference/pixelart/{stem}.json"
            writer.json(target, tree, logical_path=logical, source_root=live.root)
            pixel_trees[stem] = tree
            row["export"] = target
        elif relative.startswith("battle/"):
            target = f"reference/battle/raw/{Path(relative).name}"
            writer.write(target, live.data, logical_path=logical, source_root=live.root)
            row["export"] = target
            try:
                tree = decode_amf3_deflate(live.data, logical)
                decoded_target = f"reference/battle/decoded/{Path(relative).name}.json"
                writer.json(decoded_target, tree, logical_path=logical)
                row["decoded_export"] = decoded_target
            except ExportError:
                row["decoded_export"] = "unsupported battle payload"
        else:
            row["export"] = "listed only"
        contract.append(row)

    if png_contacts:
        contact = contact_sheet(png_contacts, cell=(280, 260), columns=3)
        assert contact is not None
        writer.write("reference/ui/contact_sheet.png", contact)
    if story_contacts:
        contact = contact_sheet(story_contacts, cell=(220, 260), columns=5)
        assert contact is not None
        writer.write("reference/ui/story_contact_sheet.png", contact)

    pixel_report: dict[str, Any] = {"variants": {}, "voice_counts": dict(voice_counts)}
    for variant, sheet_name, atlas_name, timeline_name in (
        ("normal", "sprite_sheet.png", "sprite_sheet.atlas", "pixelart.timeline"),
        ("special", "special_sprite_sheet.png", "special_sprite_sheet.atlas", "special.timeline"),
    ):
        if not all(name in pixel_payloads or name in pixel_trees for name in (
            sheet_name, atlas_name, timeline_name
        )):
            pixel_report["variants"][variant] = {"exists": False}
            continue
        sheet_raw = pixel_payloads[sheet_name]
        atlas = pixel_trees[atlas_name]
        timeline = pixel_trees[timeline_name]
        if not isinstance(atlas, list) or not isinstance(timeline, dict):
            raise ExportError(f"invalid {variant} pixel metadata")
        unique, manifest, previews = split_atlas_cells(
            writer,
            sheet_raw=sheet_raw,
            atlas=atlas,
            output_prefix=f"reference/pixelart/{variant}_cells",
            pixel_mode=True,
        )
        writer.json(f"reference/pixelart/{variant}_cells_manifest.json", manifest)
        contact = contact_sheet(previews, cell=(180, 180), columns=6)
        if contact is not None:
            writer.write(f"reference/pixelart/{variant}_cells_contact_sheet.png", contact)
        gifs = pixel_gifs(
            writer,
            sheet_raw=sheet_raw,
            atlas=atlas,
            timeline=timeline,
            output_prefix=f"reference/pixelart/previews/{variant}",
        )
        pixel_report["variants"][variant] = {
            "exists": True,
            "atlas_records": len(atlas),
            "unique_cells": unique,
            "sequences": gifs,
        }

    return contract, pixel_report


def export_data_and_dsl(
    writer: BundleWriter, character_id: str, code_name: str
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    flat_specs = {
        "character": ("master/character/character.orderedmap", [character_id]),
        "character_text": ("master/character/character_text.orderedmap", [character_id]),
        "character_speech": ("master/character/character_speech.orderedmap", [character_id]),
        "abilities": (
            "master/ability/ability.orderedmap",
            [f"{character_id}{index}" for index in range(1, 7)],
        ),
        "leader_ability": ("master/ability/leader_ability.orderedmap", [character_id]),
        "skill_preview": (
            "master/skill_preview/skill_preview_character.orderedmap", [character_id]
        ),
        "upskill": ("master/mana_board/upskill.orderedmap", [character_id]),
    }
    flat_selected: dict[str, dict[str, str]] = {}
    for label, (logical, keys) in flat_specs.items():
        value = table_selection(logical, keys)
        writer.json(f"reference/data_readable/{label}.json", value)
        flat_selected[logical] = {
            key: entry["raw_csv"] for key, entry in value["selected"].items()
        }

    status_logical = "master/character/character_status.orderedmap"
    status_live = live_one(status_logical, ("common",))
    status_outer = core.read_orderedmap_raw_rows_from_bytes(status_live.data, status_logical)
    status = []
    if character_id in status_outer.keys:
        index = status_outer.keys.index(character_id)
        status = [
            {"level": level, "hp": hp, "attack": attack}
            for level, hp, attack in core.decode_status_row(status_outer.rows[index])
        ]
    writer.json("reference/data_readable/status.json", {
        "logical_path": status_logical,
        "source_archive": status_live.archive.name,
        "rows": status,
    })

    action_logical = "master/skill/action_skill.orderedmap"
    action_live = live_one(action_logical, ("common",))
    action_table = core.load_nested_table_bytes(action_live.data, action_logical)
    if code_name not in action_table.rows:
        raise ExportError(f"action skill outer key is missing: {code_name}")
    action_inner = action_table.rows[code_name]
    action_rows: list[dict[str, Any]] = []
    nested_text: dict[str, str] = {}
    dsl_trees: dict[str, Any] = {}
    programs: list[str] = []
    direct_effects: set[str] = set()
    known_columns = {
        0: "name", 1: "description", 2: "action_path", 3: "unknown_bool",
        4: "min_skill_weight", 5: "max_skill_weight", 6: "unknown_6",
        7: "program_path",
    }
    for inner_key, row_raw in zip(action_inner.keys, action_inner.rows):
        text = row_raw.decode("utf-8")
        nested_text[inner_key] = text
        rows = csv_rows(text)
        fields = rows[0] if rows else []
        mapped = {name: fields[index] if index < len(fields) else ""
                  for index, name in known_columns.items()}
        program = mapped["program_path"]
        programs.append(program)
        dsl_logical = wf_dsl.dsl_logical(program)
        dsl_live = live_one(dsl_logical, ("common",))
        dsl_plain = zlib.decompress(dsl_live.data, -15)
        parsed = wf_dsl.parse_dsl(dsl_plain)
        tree = parsed["tree"]
        dsl_trees[dsl_logical] = tree
        strings: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, str):
                strings.append(node)
            elif isinstance(node, dict):
                for child in node.values():
                    walk(child)
            elif isinstance(node, (list, tuple)):
                for child in node:
                    walk(child)

        walk(tree)
        effects = sorted(set(value for value in strings if value.startswith("battle/effect/")))
        direct_effects.update(effects)
        dsl_slug = sanitized_cell_name(inner_key)
        writer.write(
            f"reference/data_readable/action_dsl/raw/{dsl_slug}.action.dsl.amf3.deflate",
            dsl_live.data,
            logical_path=dsl_logical,
            source_archive=dsl_live.archive.name,
        )
        writer.json(
            f"reference/data_readable/action_dsl/decoded/{dsl_slug}.json",
            {"logical_path": dsl_logical, "tree": tree, "numbers": parsed["numbers"]},
        )
        action_rows.append({
            "inner_key": inner_key,
            "fields": fields,
            "known": mapped,
            "dsl_logical_path": dsl_logical,
            "source_archive": dsl_live.archive.name,
            "effect_references": effects,
        })
    writer.json("reference/data_readable/action_skill.json", {
        "logical_path": action_logical,
        "outer_key": code_name,
        "source_archive": action_live.archive.name,
        "rows": action_rows,
    })

    switched: dict[str, Any] = {"exists": False}
    switched_logical = "master/skill/switched_action_skill.orderedmap"
    switched_live = try_live(switched_logical, ("common",))
    if switched_live is not None:
        switched_table = core.load_nested_table_bytes(switched_live.data, switched_logical)
        if code_name in switched_table.rows:
            inner = switched_table.rows[code_name]
            switched = {
                "exists": True,
                "logical_path": switched_logical,
                "rows": {
                    key: csv_rows(raw.decode("utf-8"))
                    for key, raw in zip(inner.keys, inner.rows)
                },
            }
    writer.json("reference/data_readable/switched_skill.json", switched)

    refs = requirements.extract_master_asset_references(
        flat_selected,
        {action_logical: {code_name: nested_text}},
        dsl_trees,
    )
    references_json = [
        {
            "kind": ref.kind,
            "value": ref.value,
            "source": ref.source,
            "required_paths": list(requirements.required_asset_paths(ref)),
        }
        for ref in refs
    ]
    writer.json("reference/data_readable/master_asset_references.json", references_json)
    summary = {
        "programs": programs,
        "action_rows": action_rows,
        "master_asset_references": references_json,
    }
    return summary, sorted(direct_effects), flat_selected


def export_effects(
    writer: BundleWriter, effect_refs: list[str], code_name: str
) -> dict[str, Any]:
    directories: dict[str, set[str]] = defaultdict(set)
    for ref in effect_refs:
        directory, _, name = ref.rpartition("/")
        directories[directory].add(name)
    report: dict[str, Any] = {"directories": []}
    for directory, names in sorted(directories.items()):
        dirname = directory.rsplit("/", 1)[-1]
        owner = dirname
        directory_report: dict[str, Any] = {
            "directory": directory,
            "owner_segment": owner,
            "relationship": "independent" if owner == code_name else "reused",
            "effects": [],
        }
        texture_logical = f"{directory}/{dirname}.png"
        atlas_logical = f"{directory}/{dirname}.atlas.amf3.deflate"
        try:
            texture_live = live_one(texture_logical, ("common", "medium"))
            atlas_live = live_one(atlas_logical, ("common",))
        except ExportError as exc:
            # Some official DSLs point at built-in/general effects whose texture
            # bundle is not exposed as a standalone live-CDN logical path.  That
            # is a valid resource-contract difference, not a reason to discard
            # all of the character's otherwise exportable reference data.
            directory_report.update({
                "available": False,
                "unresolved_paths": [texture_logical, atlas_logical],
                "note": str(exc),
            })
            report["directories"].append(directory_report)
            continue
        directory_report["available"] = True
        texture = standard_png(texture_live.data, texture_logical)
        atlas = decode_amf3_deflate(atlas_live.data, atlas_logical)
        if not isinstance(atlas, list):
            raise ExportError(f"effect atlas is not an array: {atlas_logical}")
        writer.write(
            f"reference/effect/{dirname}/{dirname}.png",
            texture,
            logical_path=texture_logical,
            source_archive=texture_live.archive.name,
        )
        writer.json(
            f"reference/effect/{dirname}/{dirname}.atlas.json",
            atlas,
            logical_path=atlas_logical,
        )
        writer.write(
            f"reference/effect/{dirname}/raw/{dirname}.atlas.amf3.deflate",
            atlas_live.data,
            logical_path=atlas_logical,
            source_archive=atlas_live.archive.name,
        )
        unique, manifest, previews = split_atlas_cells(
            writer,
            sheet_raw=texture,
            atlas=atlas,
            output_prefix=f"reference/effect/{dirname}/cells",
            pixel_mode=False,
        )
        writer.json(f"reference/effect/{dirname}/cells_manifest.json", manifest)
        contact = contact_sheet(previews, cell=(180, 180), columns=5)
        if contact is not None:
            writer.write(f"reference/effect/{dirname}/cells_contact_sheet.png", contact)
        directory_report["atlas_records"] = len(atlas)
        directory_report["unique_cells"] = unique
        directory_report["texture_dimensions"] = list(image_size(texture))

        for name in sorted(names):
            base = f"{directory}/{name}"
            effect_report: dict[str, Any] = {"reference": base, "sounds": []}
            for suffix in ("parts", "timeline"):
                logical = f"{base}.{suffix}.amf3.deflate"
                live = live_one(logical, ("common",))
                tree = decode_amf3_deflate(live.data, logical)
                writer.write(
                    f"reference/effect/{dirname}/raw/{name}.{suffix}.amf3.deflate",
                    live.data,
                    logical_path=logical,
                    source_archive=live.archive.name,
                )
                writer.json(
                    f"reference/effect/{dirname}/decoded/{name}.{suffix}.json",
                    tree,
                    logical_path=logical,
                )
                effect_report[f"{suffix}_source"] = live.archive.name
                if suffix == "timeline" and isinstance(tree, dict):
                    effect_report["sequences"] = tree.get("sequences", [])
                    effect_report["sounds"] = tree.get("sounds", [])
            directory_report["effects"].append(effect_report)
        report["directories"].append(directory_report)
    writer.json("reference/effect/effect_summary.json", report)
    return report


def write_contract_csv(writer: BundleWriter, contract: list[dict[str, Any]]) -> None:
    stream = io.StringIO(newline="")
    output = csv.writer(stream)
    output.writerow([
        "logical_path", "relative_path", "requirement_category", "exists",
        "roots", "dimensions", "export",
    ])
    for row in contract:
        output.writerow([
            row["logical_path"],
            row["relative_path"],
            row["requirement_category"],
            "true" if row["exists"] else "false",
            ",".join(item["root"] for item in row.get("variants", [])),
            "x".join(str(value) for value in row.get("dimensions", [])),
            row.get("export", ""),
        ])
    writer.text("reference/asset_contract/required_assets.csv", stream.getvalue())


def copy_prefilled_request(
    writer: BundleWriter,
    *,
    character_id: str,
    code_name: str,
    name: str,
    tail: str,
    effect_report: dict[str, Any],
) -> None:
    relationships = [
        f"{item['directory']} ({item['relationship']})"
        for item in effect_report.get("directories", [])
    ]
    text = f"""# 角色改动回传单

制作方提供的参考包名称：{character_id}-{code_name}-reference
参考包资源版本：{tail}
参考包角色：{character_id} / {code_name} / {name}

改动方式：修改原角色 / 以本角色为模板新建角色
新角色名称与设定：

数据与玩法改动：
立绘与UI：复用 / 使用 return/masters
像素小人：复用 / 只换色 / 使用 return/pixelart 拆分帧 / 新动作
语音：复用 / 使用 return/voice
剧情：不改 / 使用 return/story

主动技能场上特效必须选择：
- [ ] 复用当前特效
- [ ] 以当前 parts/timeline 为骨架，只换贴图
- [ ] 完全原创并提供四件套或明确骨架

当前效果目录：
{chr(10).join(f'- {value}' for value in relationships) or '- 无直接 battle/effect 引用'}

必须保留不动的内容：
精确数值、触发、持续时间、冷却与叠加上限：
素材来源与授权：
验收要求：

请只修改 return/ 中的内容；reference/ 是当前终态的只读快照。
"""
    writer.text("return/request.md", text)


def deterministic_zip(source: Path, target: Path, wrapper: str) -> tuple[int, str]:
    files = sorted(path for path in source.rglob("*") if path.is_file())
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(f"{wrapper}/{relative}", (2026, 8, 24, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return len(files), sha256_bytes(target.read_bytes())


def export_reference(character_id: str, output_root: Path) -> dict[str, Any]:
    character_id = str(character_id).strip()
    if not character_id.isdigit():
        raise ExportError("character id must contain only digits")
    cdn_character = load_repo_json("assets/cdndata/character.json")
    if character_id not in cdn_character or not cdn_character[character_id]:
        raise ExportError(f"character is not present in cdndata: {character_id}")
    row = cdn_character[character_id][0]
    code_name = str(row[0])
    character_text = load_repo_json("assets/cdndata/character_text.json").get(character_id)
    server_character = load_repo_json("assets/character.json").get(character_id)
    mana_node = load_repo_json("assets/mana_node.json").get(character_id)
    generated_rows = load_repo_json("docs/generated/character_table.json")
    generated = next(
        (item for item in generated_rows if str(item.get("id")) == character_id), {}
    )
    name = str(generated.get("name") or (server_character or {}).get("name") or character_id)
    live_description = wf_live_cdn.describe()
    tail = str(live_description["tail"])
    wrapper = f"{character_id}-{code_name}-reference-{tail}"
    bundle_dir = output_root / wrapper
    zip_path = output_root / f"{wrapper}.zip"
    if bundle_dir.exists() or zip_path.exists():
        raise ExportError(f"reference output already exists: {bundle_dir} or {zip_path}")
    bundle_dir.mkdir(parents=True, exist_ok=False)
    writer = BundleWriter(bundle_dir)

    identity = {
        "character_id": character_id,
        "code_name": code_name,
        "name": name,
        "generated_summary": generated,
        "server_character": server_character,
        "cdndata_character": cdn_character[character_id],
        "cdndata_character_text": character_text,
        "server_mana_node": mana_node,
    }
    writer.json("reference/data_readable/identity.json", identity)

    data_report, effect_refs, _flat = export_data_and_dsl(
        writer, character_id, code_name
    )
    contract, pixel_report = export_character_assets(writer, code_name)
    write_contract_csv(writer, contract)
    writer.json("reference/asset_contract/pixel_report.json", pixel_report)
    effect_report = export_effects(writer, effect_refs, code_name)

    story_count = sum(
        row["exists"] and row["relative_path"].startswith("ui/story/")
        for row in contract
    )
    actual_paths = [row for row in contract if row["exists"]]
    missing_required = [
        row["logical_path"] for row in contract
        if row["requirement_category"] == "required" and not row["exists"]
    ]
    summary = {
        "character_id": character_id,
        "code_name": code_name,
        "name": name,
        "resource_tail": tail,
        "character_assets_present": len(actual_paths),
        "story_images": story_count,
        "voice_counts": pixel_report.get("voice_counts", {}),
        "pixelart": pixel_report.get("variants", {}),
        "action_skill_rows": len(data_report["action_rows"]),
        "effect_references": effect_refs,
        "effect_directories": effect_report.get("directories", []),
        "generic_new_character_requirements_missing": missing_required,
    }
    writer.json("reference/REFERENCE_REPORT.json", summary)

    effect_lines = []
    sound_lines = []
    for directory in effect_report.get("directories", []):
        if not directory.get("available", True):
            effect_lines.append(
                f"- `{directory['directory']}`：{directory['relationship']}，"
                f"当前 CDN 无独立纹理/atlas，已记录未解析路径"
            )
            continue
        effect_lines.append(
            f"- `{directory['directory']}`：{directory['relationship']}，"
            f"{len(directory['effects'])} 个效果，{directory['atlas_records']} 条 atlas，"
            f"{directory['unique_cells']} 个唯一 cell"
        )
        for effect in directory["effects"]:
            for sound in effect.get("sounds", []):
                sound_lines.append(
                    f"- `{effect['reference']}` → `{sound.get('path')}`，begin={sound.get('begin')}"
                )
    normal = pixel_report.get("variants", {}).get("normal", {})
    special = pixel_report.get("variants", {}).get("special", {})
    readme = f"""# {character_id} {name}（{code_name}）角色专用参考包

本包从客户端可见终态 `{tail}` 只读导出，不是可直接覆盖游戏的补丁。
`reference/` 是当前角色基准，修改者只应向 `return/` 放回原创源素材和改动说明。

## 本角色的实际差异

- 当前角色：{character_id} / {name} / `{code_name}`；
- 普通 pixelart：{normal.get('atlas_records', 0)} 条 atlas，{normal.get('unique_cells', 0)} 个唯一 cell，{len(normal.get('sequences', []))} 段动作；
- 独立 special pixelart：{'存在' if special.get('exists') else '不存在；不要按通用新角色模板强行补空文件'}；
- 主动技数据：{len(data_report['action_rows'])} 个内层行；
- 核心语音：ally {pixel_report.get('voice_counts', {}).get('ally', 0)} / battle {pixel_report.get('voice_counts', {}).get('battle', 0)} / home {pixel_report.get('voice_counts', {}).get('home', 0)}；
- words 语料只列槽位，不复制音频：{pixel_report.get('voice_counts', {}).get('words', 0)} 条；
- 剧情表情：{story_count} 张。

## 主动技能场上特效

{chr(10).join(effect_lines) or '- ActionDsl 没有直接引用 `battle/effect`。'}

已经导出标准 PNG、atlas JSON、拆分 cell、contact sheet，以及每个效果的原始/解码 parts 和 timeline。
这些是真正的场上技能特效，和 pixelart 的 `skill_ready`、获取演出不是同一层。

timeline 中的音效引用：

{chr(10).join(sound_lines) or '- 无音效引用。'}

音效路径属于游戏通用 SFX 系统，本参考包记录触发路径和帧，不把无法作为独立 CDN 逻辑文件解析的
主程序内音效伪装成可编辑音频。

## 使用方式

1. 数据参考看 `reference/data_readable/`；
2. UI 与剧情看 contact sheet 和解码 PNG；
3. 像素修改优先使用 `reference/pixelart/normal_cells/` 同名帧；
4. 技能特效重皮看 `reference/effect/{code_name}/cells_contact_sheet.png` 和 `cells/`；
5. 填写 `return/request.md`，只回传发生变化的源文件。

`generic_new_character_requirements_missing` 只说明它与当前通用37项新角色模板的差异，不代表这个
角色损坏。本包以 {character_id} 当前真实资源契约为准。
"""
    writer.text("README.md", readme)
    copy_prefilled_request(
        writer,
        character_id=character_id,
        code_name=code_name,
        name=name,
        tail=tail,
        effect_report=effect_report,
    )

    payload_rows = [
        f"{relative}\0{record['sha256']}\0{record['size']}"
        for relative, record in sorted(writer.records.items())
    ]
    payload_digest = sha256_bytes("\n".join(payload_rows).encode("utf-8"))
    reference_info = {
        "format": "wf-character-reference-v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "resource_version": tail,
        "character_id": character_id,
        "code_name": code_name,
        "rarity": int(row[2]),
        "element": int(row[3]),
        "source_code": code_name,
        "target_code": code_name,
        "live_cdn_revision": live_description["revision"],
        "payload_digest": payload_digest,
    }
    writer.json("REFERENCE_INFO.json", reference_info)
    checksums = {
        relative: record for relative, record in sorted(writer.records.items())
    }
    writer.json("checksums.json", checksums)
    members, archive_sha = deterministic_zip(bundle_dir, zip_path, wrapper)
    return {
        "directory": str(bundle_dir),
        "archive": str(zip_path),
        "archive_size": zip_path.stat().st_size,
        "archive_sha256": archive_sha,
        "members": members,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="导出指定角色的只读参考包")
    parser.add_argument("character_id")
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    result = export_reference(args.character_id, args.output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
