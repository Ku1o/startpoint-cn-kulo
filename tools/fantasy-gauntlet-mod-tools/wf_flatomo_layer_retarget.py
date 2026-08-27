#!/usr/bin/env python3
"""Retarget one Flatomo effect sheet to a different battle-atlas layer.

The PNG and animation timeline stay byte-identical.  Only logical asset names
inside the atlas, parts payload and referring action DSLs are changed.  This is
useful when a large effect is safe to render as-is but must not compete for the
same 4096x4096 runtime atlas as bosses, characters and ordinary effects.
"""
from __future__ import annotations

import copy
import zlib
from dataclasses import dataclass
from pathlib import PurePosixPath

import wf_dsl


@dataclass(frozen=True, slots=True)
class LayerRetargetResult:
    atlas_payload: bytes
    parts_payload: bytes
    timeline_payload: bytes
    action_payloads: tuple[bytes, ...]
    atlas_records: int
    parts_images: int
    action_replacements: tuple[int, ...]
    old_cell_prefix: str
    new_cell_prefix: str


def decode_payload(payload: bytes):
    return wf_dsl.parse_dsl(zlib.decompress(payload, -15))["tree"]


def encode_payload(tree) -> bytes:
    compressor = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
    raw = wf_dsl.encode_amf3(tree)
    return compressor.compress(raw) + compressor.flush()


def _sheet_cell_prefix(logical_png: str) -> str:
    path = PurePosixPath(logical_png)
    if path.suffix != ".png" or path.name == ".png":
        raise ValueError(f"sheet path must end in .png: {logical_png}")
    return f"{path.parent.as_posix()}/.gen/{path.stem}/"


def _replace_exact_strings(value, old: str, new: str) -> tuple[object, int]:
    if isinstance(value, str):
        return (new, 1) if value == old else (value, 0)
    if isinstance(value, list):
        output = []
        count = 0
        for item in value:
            replaced, item_count = _replace_exact_strings(item, old, new)
            output.append(replaced)
            count += item_count
        return output, count
    if isinstance(value, dict):
        output = {}
        count = 0
        for key, item in value.items():
            replaced_key, key_count = _replace_exact_strings(key, old, new)
            replaced_item, item_count = _replace_exact_strings(item, old, new)
            output[replaced_key] = replaced_item
            count += key_count + item_count
        return output, count
    return copy.deepcopy(value), 0


def _replace_prefix(value: str, old_prefix: str, new_prefix: str) -> str:
    if not value.startswith(old_prefix):
        raise ValueError(f"asset name does not use expected prefix: {value}")
    suffix = value[len(old_prefix) :]
    if not suffix:
        raise ValueError(f"asset name has no cell suffix: {value}")
    return new_prefix + suffix


def retarget_effect_layer(
    *,
    png_payload: bytes,
    atlas_payload: bytes,
    parts_payload: bytes,
    timeline_payload: bytes,
    action_payloads: tuple[bytes, ...],
    old_sheet_logical: str,
    new_sheet_logical: str,
    old_effect_reference: str,
    new_effect_reference: str,
) -> LayerRetargetResult:
    """Clone an effect under a new layer path with strict semantic checks."""
    if not png_payload:
        raise ValueError("PNG payload must not be empty")
    if old_sheet_logical == new_sheet_logical:
        raise ValueError("old and new sheet paths must differ")
    if old_effect_reference == new_effect_reference:
        raise ValueError("old and new effect references must differ")
    if not action_payloads:
        raise ValueError("at least one action DSL is required")

    old_cell_prefix = _sheet_cell_prefix(old_sheet_logical)
    new_cell_prefix = _sheet_cell_prefix(new_sheet_logical)

    source_atlas = decode_payload(atlas_payload)
    if not isinstance(source_atlas, list) or not source_atlas:
        raise ValueError("atlas root must be a non-empty list")
    output_atlas = copy.deepcopy(source_atlas)
    for record in output_atlas:
        if not isinstance(record, dict) or not isinstance(record.get("n"), str):
            raise ValueError("every atlas record must contain a string name")
        record["n"] = _replace_prefix(record["n"], old_cell_prefix, new_cell_prefix)

    source_parts = decode_payload(parts_payload)
    if not isinstance(source_parts, dict) or not isinstance(source_parts.get("i"), list):
        raise ValueError("parts root must contain an image list")
    output_parts = copy.deepcopy(source_parts)
    part_names: list[str] = []
    for image in output_parts["i"]:
        if not isinstance(image, dict) or not isinstance(image.get("p"), str):
            raise ValueError("every parts image must contain a string path")
        image["p"] = _replace_prefix(image["p"], old_cell_prefix, new_cell_prefix)
        part_names.append(image["p"])

    atlas_names = {record["n"] for record in output_atlas}
    missing = sorted(set(part_names) - atlas_names)
    if missing:
        raise ValueError(f"retargeted parts reference missing atlas cells: {missing}")

    # Prove that the atlas and parts trees changed only by the requested prefix.
    reversed_atlas, atlas_reverse_count = _replace_exact_strings(
        output_atlas, new_cell_prefix, old_cell_prefix
    )
    # Exact-string replacement does not apply to prefixed cell paths; check by
    # rebuilding the original names instead.
    for before, after in zip(source_atlas, output_atlas, strict=True):
        restored = copy.deepcopy(after)
        restored["n"] = _replace_prefix(after["n"], new_cell_prefix, old_cell_prefix)
        if restored != before:
            raise AssertionError("atlas changed beyond its cell-name prefix")
    if atlas_reverse_count:
        raise AssertionError("unexpected bare atlas cell-prefix value")
    restored_parts = copy.deepcopy(output_parts)
    for image in restored_parts["i"]:
        image["p"] = _replace_prefix(image["p"], new_cell_prefix, old_cell_prefix)
    if restored_parts != source_parts:
        raise AssertionError("parts changed beyond its cell-name prefix")

    output_actions: list[bytes] = []
    action_replacements: list[int] = []
    for payload in action_payloads:
        source_action = decode_payload(payload)
        output_action, replacements = _replace_exact_strings(
            source_action, old_effect_reference, new_effect_reference
        )
        if replacements != 1:
            raise ValueError(
                "each action DSL must contain the old effect reference exactly once; "
                f"found {replacements}"
            )
        restored_action, reverse_count = _replace_exact_strings(
            output_action, new_effect_reference, old_effect_reference
        )
        if reverse_count != 1 or restored_action != source_action:
            raise AssertionError("action DSL changed beyond the effect reference")
        output_actions.append(encode_payload(output_action))
        action_replacements.append(replacements)

    # Parse all generated payloads before returning.  The timeline is deliberately
    # copied byte-for-byte because it contains no sheet or effect path.
    encoded_atlas = encode_payload(output_atlas)
    encoded_parts = encode_payload(output_parts)
    if decode_payload(encoded_atlas) != output_atlas:
        raise AssertionError("generated atlas payload failed semantic round-trip")
    if decode_payload(encoded_parts) != output_parts:
        raise AssertionError("generated parts payload failed semantic round-trip")
    decode_payload(timeline_payload)
    for payload, tree in zip(output_actions, (decode_payload(item) for item in output_actions)):
        if encode_payload(tree) != payload:
            raise AssertionError("generated action payload is not deterministic")

    return LayerRetargetResult(
        atlas_payload=encoded_atlas,
        parts_payload=encoded_parts,
        timeline_payload=timeline_payload,
        action_payloads=tuple(output_actions),
        atlas_records=len(output_atlas),
        parts_images=len(part_names),
        action_replacements=tuple(action_replacements),
        old_cell_prefix=old_cell_prefix,
        new_cell_prefix=new_cell_prefix,
    )
