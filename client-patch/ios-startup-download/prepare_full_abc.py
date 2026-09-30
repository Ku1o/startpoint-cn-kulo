"""Prepare the complete compiler ABC for the bounded iOS startup gate repair."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import types
from pathlib import Path


HERE = Path(__file__).resolve().parent
CLIENT_PATCH = HERE.parent
ROOT = CLIENT_PATCH.parent
sys.path[:0] = [
    str(CLIENT_PATCH / "lens0907-0908"),
    str(CLIENT_PATCH / "lens0907-0908" / "vendor" / "abcasm"),
    str(ROOT / "tools" / "lens-integration"),
    str(CLIENT_PATCH / "ios-cumulative-login"),
]

import build_swf as p  # noqa: E402
from swfabc import abcfmt, swftags  # noqa: E402

p.asm.MNEMONICS["avm_label"] = 0x09
p.asm.BY_OPCODE[0x09] = "avm_label"

LABEL = "pinball.loading.global::GlobalLoading/applyLoad|1"
NEEDS_DOWNLOAD_MULTINAME = 27597


def view(abc):
    return p.View(types.SimpleNamespace(abc=abc), p.asm)


def main_abc(swf: Path):
    _, _, _, body = swftags.load_swf(str(swf))
    hits = []
    for code, offset, header, length in swftags.iter_tags(body):
        if code != 82:
            continue
        raw = body[offset + header : offset + header + length]
        nul = raw.index(b"\0", 4)
        name = raw[4:nul].decode("utf-8", "replace")
        if name.startswith("boot_"):
            hits.append((name, abcfmt.ABC(raw[nul + 1 :])))
    if len(hits) != 1:
        raise AssertionError(("main ABC count", len(hits)))
    return hits[0]


def patch_body(body, abc):
    rows = p.asm.decode(body[5])
    call_sites = [
        index
        for index, instruction in enumerate(rows)
        if instruction.op == p.asm.MNEMONICS["callproperty"]
        and list(instruction.args) == [NEEDS_DOWNLOAD_MULTINAME, 0]
    ]
    if call_sites != [60, 96]:
        raise AssertionError(("needsDownloadAsset call sites", call_sites))

    # Keep the native call and discard its result. The following branch then
    # sees true, matching the two native NOPs without adding a new pool entry.
    replacements = {index + 2 for index in call_sites}
    output = []
    mapping = {}
    for index, instruction in enumerate(rows):
        mapping[index] = len(output)
        if index in replacements:
            output.append(p.asm.Instruction(p.asm.MNEMONICS["pop"]))
            output.append(p.asm.Instruction(p.asm.MNEMONICS["pushtrue"]))
        else:
            output.append(copy.deepcopy(instruction))
    mapping[len(rows)] = len(output)
    for instruction in output:
        if instruction.target is not None:
            instruction.target = mapping[instruction.target]
        if instruction.default is not None:
            instruction.default = mapping[instruction.default]
        if instruction.cases is not None:
            instruction.cases = [mapping[index] for index in instruction.cases]

    patched = copy.deepcopy(body)
    patched[5] = p.asm.encode(output)[0]
    if patched[6]:
        raise AssertionError("applyLoad unexpectedly has exception records")
    p.check_body(patched, abc)
    return patched, {
        "call_sites": call_sites,
        "old_instruction_count": len(rows),
        "new_instruction_count": len(output),
        "old_code_bytes": len(body[5]),
        "new_code_bytes": len(patched[5]),
        "predicate_rewrite": "discard needsDownloadAsset result and push true",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-full-abc", type=Path, required=True)
    parser.add_argument("--android-swf", type=Path, required=True)
    parser.add_argument("--output-full-abc", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    target = abcfmt.ABC(args.baseline_full_abc.read_bytes())
    target_view = view(target)
    _, donor = main_abc(args.android_swf)
    donor_view = view(donor)
    target_index = target_view.by_label[LABEL][0]
    donor_index = donor_view.by_label[LABEL][0]
    original = copy.deepcopy(target.bodies[target_index])
    if len(original[5]) != 1:
        raise AssertionError("the target AOT body must remain a return stub")
    imported = p.Importer(target_view, donor_view).body(
        donor_index, original[0], scope=original[3]
    )
    if p.activation_traits(target_view, original) != p.activation_traits(target_view, imported):
        raise AssertionError("applyLoad activation ABI changed")
    patched, patch = patch_body(imported, target)
    target.bodies[target_index] = patched
    full = target.serialize()
    if abcfmt.ABC(full).serialize() != full:
        raise AssertionError("complete ABC does not round-trip")
    args.output_full_abc.parent.mkdir(parents=True, exist_ok=True)
    args.output_full_abc.write_bytes(full)
    report = {
        "status": "prepared_full_abc",
        "label": LABEL,
        "method_id": original[0],
        "target_body_index": target_index,
        "donor_body_index": donor_index,
        "baseline_body_sha256": hashlib.sha256(original[5]).hexdigest(),
        "patched_body_sha256": hashlib.sha256(patched[5]).hexdigest(),
        "baseline_full_abc_sha256": hashlib.sha256(args.baseline_full_abc.read_bytes()).hexdigest(),
        "full_abc_sha256": hashlib.sha256(full).hexdigest(),
        "full_abc_sha1": hashlib.sha1(full).hexdigest(),
        "method_count": len(target.methods),
        "pool_counts": {
            name: len(getattr(target, name))
            for name in ("ints", "uints", "doubles", "strings", "namespaces", "ns_sets", "multinames", "methods")
        },
        "activation_traits_unchanged": True,
        "patch": patch,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
