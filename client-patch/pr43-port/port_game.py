"""Port the reviewed v33 method deltas onto the preserved Android baseline.

The constant-pool prefix, method signatures and every existing game trait are
checked before method-level replay. Current endpoint/admission and Inaho v3
helpers remain intact; the archive's R4 implementation is never an input.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path
import struct
import sys
import types
import zlib

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SUPPORT = HERE / "support"


def dependencies():
    sys.path.insert(0, str(SUPPORT))
    common = importlib.import_module("common")
    core = importlib.import_module("perf2_core")
    modules = {name: sys.modules[name] for name in ("common", "perf2_core", "asm", "bodies", "swfabc")}
    modules.update(abcfmt=common.abcfmt, swftags=common.swftags)
    for name, module in modules.items():
        if not Path(module.__file__).resolve().is_relative_to(SUPPORT.resolve()):
            raise ValueError(f"Unexpected support module: {name}")
    return common, core


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_body(abc, body, common, core):
    """Keep debug metadata intact while extending the archived static checker.

    Adobe AVM2 opcode definitions assign no operand-stack movement to
    debug/debugline/debugfile/bkptline (0xef..0xf2):
    https://github.com/adobe/avmplus/blob/master/core/opcodes.tbl
    The source archive's opcode table omits their stack effects.
    """
    asm = common.asm
    instructions = asm.decode(body[5])
    encoded, offsets = asm.encode(instructions)
    if encoded != body[5]:
        raise ValueError("Instruction encoding roundtrip changed the method")
    effect_globals = dict(asm._effect.__globals__)
    effects = dict(asm._POP_PUSH)
    effects.update({opcode: (0, 0) for opcode in (0xEF, 0xF0, 0xF1, 0xF2)})
    effect_globals["_POP_PUSH"] = effects
    effect = types.FunctionType(asm._effect.__code__, effect_globals, argdefs=asm._effect.__defaults__)
    simulate_globals = dict(asm.simulate.__globals__)
    simulate_globals["_effect"] = effect
    simulate = types.FunctionType(asm.simulate.__code__, simulate_globals, argdefs=asm.simulate.__defaults__)
    index_of = {offset: index for index, offset in enumerate(offsets)}
    handlers = [index_of[row[2]] for row in body[6]]
    maximum, scope, unreachable = simulate(instructions, body[3], abc.multinames, handlers)
    if maximum > body[1] or scope > body[4] or asm.block_locals(instructions) > body[2]:
        raise core.Refused("Method stack/scope/locals exceed its header")
    return {"max_stack": maximum, "max_scope": scope, "unreachable": unreachable,
            "debug_instructions": sum(ins.op in (0xEF, 0xF0, 0xF1, 0xF2) for ins in instructions)}


def check_prefix(current, donor, plan, common):
    appended = {}
    for name in ("instances", "classes", "scripts", "methods", "metadata"):
        if common.freeze(getattr(current, name)) != common.freeze(getattr(donor, name)):
            raise ValueError(f"Incompatible game structure: {name}")
    for name in ("ints", "uints", "doubles", "strings", "namespaces", "ns_sets", "multinames"):
        old, new = getattr(current, name), getattr(donor, name)
        if len(new) < len(old):
            raise ValueError(f"Donor pool is shorter: {name}")
        differences = [index for index, (a, b) in enumerate(zip(old, new)) if common.freeze(a) != common.freeze(b)]
        allowed = plan["preserved_existing_string_indices"] if name == "strings" else []
        if differences != allowed:
            raise ValueError(f"Unexpected existing pool mutation: {name} {differences}")
        appended[name] = len(new) - len(old)
    return appended


def replace_tags(source, donor, main, plan, common):
    data = common.swf_data(source)
    donor_tags = {row[0].decode(): row for row in common.abc_tags(donor)}
    replacements = {}
    for name in plan["updated_helper_tags"]:
        replacements[name] = donor_tags[name][3] + donor_tags[name][4]
    replacements["boot_ffc6"] = next(row[3] for row in common.abc_tags(source) if row[0] == common.MAIN) + main.serialize()
    added = [donor_tags[name][3] + donor_tags[name][4] for name in plan["new_helper_tags"]]
    source_names = [row[0].decode() for row in common.abc_tags(source)]
    if any(source_names.count(name) != 1 for name in replacements) or any(name in source_names for name in plan["new_helper_tags"]):
        raise ValueError("Duplicate or already present helper tag")
    pieces, cursor, changed = [], 0, []
    for kind, offset, header, length in common.swftags.iter_tags(data):
        if kind != 82:
            continue
        content = data[offset + header:offset + header + length]
        nul = content.index(b"\0", 4)
        name = content[4:nul].decode()
        if name not in replacements:
            continue
        pieces.append(data[cursor:offset])
        if name == "boot_ffc6":
            for payload in added:
                pieces.append(struct.pack("<HI", (82 << 6) | 63, len(payload)) + payload)
        payload = replacements[name]
        pieces.append(struct.pack("<HI", (82 << 6) | 63, len(payload)) + payload)
        changed.append(name)
        cursor = offset + header + length
    if set(changed) != set(replacements):
        raise ValueError("A required tag replacement was not found")
    pieces.append(data[cursor:])
    output = b"".join(pieces)
    payload = zlib.compress(output) if source[:3] == b"CWS" else output
    return source[:4] + struct.pack("<I", len(output) + 8) + payload


def apply_game(source: bytes, donor: bytes, *, include_overlimit=True):
    common, core = dependencies()
    plan = json.loads((HERE / "game-plan.json").read_text("utf-8"))
    if sha(source) != plan["base_swf_sha256"] or sha(donor) != plan["donor_swf_sha256"]:
        raise ValueError("SWF input identity mismatch")
    abc, main_tag = common.main_abc(source)
    other, _ = common.main_abc(donor)
    if abc.serialize() != main_tag[4]:
        raise ValueError("Baseline ABC serialization changes untouched data")
    original_bodies = copy.deepcopy(abc.bodies)
    appended = check_prefix(abc, other, plan, common)
    donor_by_method = {body[0]: (index, body) for index, body in enumerate(other.bodies)}
    selected = [row for row in plan["methods"] if row["action"] == "apply_final_v33_semantic_delta"]
    if len(selected) != 37:
        raise ValueError("Unexpected method selection")
    reserved_strings = set(plan["preserved_existing_string_indices"])
    for row in selected:
        index = common.bodies.resolve(abc, row["label"])
        current = abc.bodies[index]
        donor_index, proposed = donor_by_method[current[0]]
        if index != row["body"] or sha(current[5]) != row["current_sha256"] or sha(proposed[5]) != row["donor_sha256"]:
            raise ValueError(f"Method input mismatch: {row['label']}")
        if any(ins.name == "pushstring" and ins.args[0] in reserved_strings for ins in common.asm.decode(proposed[5])):
            raise ValueError(f"Method depends on an excluded identity constant: {row['label']}")
    for name, count in appended.items():
        if count:
            old, new = getattr(abc, name), getattr(other, name)
            old.extend(copy.deepcopy(new[len(old):]))
    checks = []
    for row in selected:
        index = row["body"]
        _, proposed = donor_by_method[abc.bodies[index][0]]
        abc.bodies[index] = copy.deepcopy(proposed)
        checks.append({"label": row["label"], "body": index, "patches": row["patches"], "code_sha256": sha(proposed[5]),
                       "verifier": validate_body(abc, proposed, common, core)})
    overlimit = []
    if include_overlimit:
        import overlimit_port
        for definition in overlimit_port.PATCHES:
            overlimit.append(overlimit_port.apply(definition, abc, core.Pool(abc, False), core))
    changed = [index for index, (old, new) in enumerate(zip(original_bodies, abc.bodies)) if common.freeze(old) != common.freeze(new)]
    expected = {row["body"] for row in selected}
    if include_overlimit:
        expected.update(common.bodies.resolve(abc, definition["label"]) for definition in overlimit_port.PATCHES)
    if set(changed) != expected:
        raise ValueError("Unexpected changed method body set")
    old_cell = next(row["body"] for row in plan["methods"] if row["action"] == "keep_current")
    if common.freeze(abc.bodies[old_cell]) != common.freeze(original_bodies[old_cell]):
        raise ValueError("Preserved character lifecycle method changed")
    output = replace_tags(source, donor, abc, plan, common)
    readback, _ = common.main_abc(output)
    if readback.serialize() != abc.serialize():
        raise ValueError("Final ABC readback mismatch")
    old_tags = [(row[0].decode(), row[4]) for row in common.abc_tags(source)]
    new_tags = [(row[0].decode(), row[4]) for row in common.abc_tags(output)]
    allowed_tags = {"boot_ffc6", *plan["updated_helper_tags"]}
    old_untouched = [(name, raw) for name, raw in old_tags if name not in allowed_tags]
    new_untouched = [(name, raw) for name, raw in new_tags if name not in allowed_tags and name not in plan["new_helper_tags"]]
    if old_untouched != new_untouched:
        raise ValueError("An unrelated helper changed")
    if {name for name, _ in new_tags} - {name for name, _ in old_tags} != set(plan["new_helper_tags"]) or len(new_tags) != len(old_tags) + 2:
        raise ValueError("Unexpected new helper tag set")
    return output, {"passed": True, "input_swf_sha256": sha(source), "donor_swf_sha256": sha(donor),
        "output_swf_sha256": sha(output), "game_methods_replayed": checks, "overlimit": overlimit,
        "changed_main_bodies": changed, "unchanged_main_bodies": len(original_bodies) - len(changed),
        "appended_pool_entries": appended, "existing_pool_prefix_preserved": True,
        "current_helper_tags_preserved": plan["preserved_helper_tags"], "added_helper_tags": plan["new_helper_tags"],
        "updated_helper_tags": plan["updated_helper_tags"], "kept_character_update_cells": True,
        "r4_archive_patches_applied": False, "device_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.source.resolve(), args.donor.resolve()) or args.output.exists() or args.report.exists():
        raise ValueError("Inputs are immutable and output/report paths must be new")
    output, report = apply_game(args.source.read_bytes(), args.donor.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "output_swf_sha256", "unchanged_main_bodies")}))


if __name__ == "__main__":
    main()
