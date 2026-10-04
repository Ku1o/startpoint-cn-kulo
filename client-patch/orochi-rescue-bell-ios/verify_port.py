"""Independent read-back verification of the rescue-bell iOS IPA candidate."""
from __future__ import annotations
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

from common import (FULL_ABC, IPA, OUT, REPO, WORK, dump, load, sha)

INFO_OFFSET = 104549248
OLD_COUNT = 101458
sys.path[:0] = [str(REPO / "client-patch/ios-cumulative-login")]
sys.path.insert(0, r"F:/codex/tools/ios-re-libs")
import build_native as link  # type: ignore
import capstone  # type: ignore
from macho_signing_layout import assert_signable_layout  # type: ignore


def ranges_of(diffs):
    out = []
    for at in diffs:
        if out and at == out[-1][1]:
            out[-1][1] = at + 1
        else:
            out.append([at, at + 1])
    return out


def inside(offset, allowed):
    return any(begin <= offset < end for begin, end in allowed)


def main():
    report = json.loads((OUT / "ios-build-report.json").read_text("utf-8"))
    port = json.loads((WORK / "port.json").read_text("utf-8"))
    ipa = Path(report["ipa"])
    baseline = Path(report["source_ipa"]["ipa"])
    problems = []
    checks = {}

    with zipfile.ZipFile(ipa) as new, zipfile.ZipFile(baseline) as old:
        new_names, old_names = new.namelist(), old.namelist()
        checks["member_count_equal"] = len(new_names) == len(old_names)
        checks["member_order_equal"] = new_names == old_names
        changed = [n for n in new_names if new.read(n) != old.read(n)]
        checks["changed_members"] = changed
        payload_member = ("Payload/worldflipper.app/asset/production/ios_bundle/dc/"
                          "bcccb129122c0189c8eab004ecc4516a077f3e")
        expected = {report["source_ipa"]["native_member"], report["source_ipa"]["swf_member"],
                    payload_member}
        checks["changed_members_expected"] = set(changed) == expected
        checks["comment_equal"] = new.comment == old.comment
        native = new.read(report["source_ipa"]["native_member"])
        base_native = old.read(report["source_ipa"]["native_member"])
        swf = new.read(report["source_ipa"]["swf_member"])
        base_swf = old.read(report["source_ipa"]["swf_member"])
        payload = new.read(payload_member)
        checks["payload_sha256"] = sha(payload)
        checks["payload_bytes"] = len(payload)
        checks["payload_matches_compact"] = (
            sha(payload) == port["embedded_payload"]["after_sha256"]
            and len(payload) == port["embedded_payload"]["after_bytes"])
    checks["native_sha256"] = sha(native)
    checks["native_sha_matches_report"] = sha(native) == report["native_sha256"]
    checks["swf_sha256"] = sha(swf)
    checks["swf_sha_matches_report"] = sha(swf) == report["swf_sha256"]
    checks["ipa_sha256"] = sha(ipa.read_bytes())
    checks["ipa_sha_matches_report"] = checks["ipa_sha256"] == report["ipa_sha256"]

    # AOT identity and runtime ABC.
    full = (WORK / port["full_abc_file"]).read_bytes()
    digest = hashlib.sha1(full).digest()
    checks["aot_digest"] = native[INFO_OFFSET:INFO_OFFSET + 20].hex()
    checks["aot_digest_matches_full"] = native[INFO_OFFSET:INFO_OFFSET + 20] == digest
    abc_va = struct.unpack_from("<Q", native, INFO_OFFSET + 24)[0]
    abc_len = struct.unpack_from("<Q", native, INFO_OFFSET + 32)[0]
    abc_off = link.file_offset(native, abc_va)
    runtime = native[abc_off:abc_off + abc_len]
    checks["runtime_abc_sha256"] = sha(runtime)
    checks["runtime_abc_matches_report"] = sha(runtime) == report["runtime_abc_sha256"]
    checks["method_count"] = struct.unpack_from("<Q", native, INFO_OFFSET + 56)[0]
    checks["method_count_expected"] = checks["method_count"] == report["total_methods"]
    flags_va = struct.unpack_from("<Q", native, INFO_OFFSET + 64)[0]
    flags_off = link.file_offset(native, flags_va)
    checks["flags_offset"] = flags_off
    checks["flags_in_extension"] = flags_off >= link.segments(base_native)[-1]["off"]

    abc = link.abcfmt.ABC(runtime)
    prepared = link.abcfmt.ABC(full)
    baseline_abc = link.abcfmt.ABC(base_native[
        link.file_offset(base_native, struct.unpack_from("<Q", base_native, INFO_OFFSET + 24)[0]):
        link.file_offset(base_native, struct.unpack_from("<Q", base_native, INFO_OFFSET + 24)[0])
        + struct.unpack_from("<Q", base_native, INFO_OFFSET + 32)[0]])
    checks["runtime_methods"] = len(abc.methods)
    checks["runtime_instances_equal_prepared"] = (
        link.freeze(abc.instances) == link.freeze(prepared.instances))
    checks["runtime_classes_equal_prepared"] = (
        link.freeze(abc.classes) == link.freeze(prepared.classes))
    # The cleanup state must live in its own class: cn.mod::AuthorState keeps
    # the accepted carrier traits, so every previously linked AOT accessor
    # still reads the slot it was compiled against.
    def class_snapshot(abc_, name):
        index = next(i for i, row in enumerate(abc_.instances)
                     if abc_.mn_name(row[0]) == name)
        return link.freeze(abc_.classes[index][1]), link.freeze(abc_.instances[index])

    carrier_full = link.abcfmt.ABC(FULL_ABC.read_bytes())
    checks["authorstate_untouched"] = (
        class_snapshot(carrier_full, "cn.mod::AuthorState")
        == class_snapshot(prepared, "cn.mod::AuthorState")
        == class_snapshot(abc, "cn.mod::AuthorState"))
    helper_name = port["helper_class"]
    helper_i = next((i for i, row in enumerate(prepared.instances)
                     if prepared.mn_name(row[0]) == helper_name), None)
    checks["cleanup_class_present"] = helper_i is not None
    checks["cleanup_class_runtime_present"] = any(
        abc.mn_name(row[0]) == helper_name for row in abc.instances)
    if helper_i is not None:
        traits = prepared.classes[helper_i][1]
        checks["cleanup_class_slots"] = sorted(
            prepared.mn_name(t.name).rsplit("::", 1)[-1]
            for t in traits if t.data[0] == "slot")
        checks["cleanup_class_methods"] = sorted(
            prepared.mn_name(t.name).rsplit("::", 1)[-1]
            for t in traits if t.data[0] == "method")
    compile_report = json.loads((WORK / "compile-cachefix-r1-report.json").read_text("utf-8"))
    guard = compile_report["accessor_slot_guard"]
    checks["accessor_slot_guard_frozen"] = guard["frozen"]
    checks["accessor_slot_guard_recompiled"] = guard["recompiled"]
    checks["accessor_slot_guard_matches"] = guard["frozen"] == guard["recompiled"]
    old_bodies = {b[0]: b for b in baseline_abc.bodies}
    mismatched_old = [b[0] for b in abc.bodies
                      if b[0] < OLD_COUNT and link.freeze(b) != link.freeze(old_bodies[b[0]])]
    checks["old_bodies_unchanged"] = not mismatched_old
    new_ids = sorted(b[0] for b in abc.bodies if b[0] >= OLD_COUNT)
    checks["new_body_ids"] = new_ids
    checks["new_body_ids_expected"] = new_ids == port["new_method_ids"]
    prepared_bodies = {b[0]: b for b in prepared.bodies}
    # The accepted carrier stores stripped bodies in the runtime ABC; the new
    # methods execute from their AOT table entries.  Compare the compiler
    # metrics instead of stripped code bytes.
    checks["new_bodies_stripped"] = all(
        len(b[5]) == 0 for b in abc.bodies if b[0] >= OLD_COUNT)
    checks["new_body_metrics_match_prepared"] = all(
        [b[1], b[2], b[3], b[4]] == [prepared_bodies[b[0]][1], prepared_bodies[b[0]][2],
                                     prepared_bodies[b[0]][3], prepared_bodies[b[0]][4]]
        for b in abc.bodies if b[0] >= OLD_COUNT)
    checks["scripts_prefix_unchanged"] = (
        link.freeze(baseline_abc.scripts) == link.freeze(abc.scripts[:len(baseline_abc.scripts)]))
    checks["strings_prefix_unchanged"] = runtime[:0] == b"" and \
        abc.strings[:len(baseline_abc.strings)] == baseline_abc.strings

    # Native entry wrapper and compiled functions.
    active_va = struct.unpack_from("<Q", native, INFO_OFFSET + 48)[0]
    active_off = link.file_offset(native, active_va)
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)

    def disasm(va, size):
        off = link.file_offset(native, va, size)
        return list(md.disasm(native[off:off + size], va))

    wrapper = port["native_start_wrapper"]
    entry = struct.unpack_from("<Q", native, active_off + int(wrapper["method"]) * 8)[0]
    checks["apply_load_table_entry"] = entry
    first = disasm(entry, 4)[0]
    checks["apply_load_entry_branch"] = f"{first.mnemonic} {first.op_str}"
    checks["apply_load_entry_branches_to_wrapper"] = (
        first.mnemonic == "b" and int(first.op_str.lstrip("#"), 16) ==
        report["hooks"][0]["target"] if report.get("hooks") else None)
    hook = next(h for h in report["hooks"] if h.get("kind") == "native_start_wrapper")
    checks["wrapper_address"] = hook["target"]
    checks["wrapper_exit_is_original"] = (
        disasm(entry, 4)[0].mnemonic == "b"
        and int(disasm(entry, 4)[0].op_str.lstrip("#"), 16) == hook["target"])
    wrapper_code = disasm(hook["target"], hook["size"])
    checks["wrapper_size"] = hook["size"]
    checks["wrapper_sha256_matches"] = sha(native[
        link.file_offset(native, hook["target"]):
        link.file_offset(native, hook["target"]) + hook["size"]]) == hook["sha256"]
    bridge_target = int(wrapper["bridge_method"])
    bridge_fn = next(f for f in report["functions"] if f["method"] == bridge_target)
    checks["wrapper_calls_bridge"] = wrapper_code[6].mnemonic == "bl" and \
        int(wrapper_code[6].op_str.lstrip("#"), 16) == bridge_fn["address"]
    checks["wrapper_returns_to_original_plus_4"] = wrapper_code[-1].mnemonic == "b" and \
        int(wrapper_code[-1].op_str.lstrip("#"), 16) == int(wrapper["original_entry"]) + 4
    checks["wrapper_displaced_instruction"] = wrapper_code[-2].mnemonic + " " + wrapper_code[-2].op_str
    base_entry_off = link.file_offset(base_native, int(wrapper["original_entry"]), 4)
    checks["displaced_matches_baseline"] = base_native[base_entry_off:base_entry_off + 4] == \
        native[link.file_offset(native, hook["target"]) + hook["size"] - 8:
              link.file_offset(native, hook["target"]) + hook["size"] - 4]
    checks["bridge_entry"] = bridge_fn
    checks["bridge_code_sha"] = sha(native[
        bridge_fn["file_offset"]:bridge_fn["file_offset"] + bridge_fn["size"]]) == bridge_fn["sha256"]
    for f in report["functions"]:
        ok = sha(native[f["file_offset"]:f["file_offset"] + f["size"]]) == f["sha256"]
        if not ok:
            problems.append(("function", f["method"]))
    checks["all_function_hashes_match"] = not problems
    table_targets = {mid: struct.unpack_from("<Q", native, active_off + mid * 8)[0]
                     for mid in range(OLD_COUNT, report["total_methods"])}
    checks["new_table_entries"] = {m: hex(v) for m, v in table_targets.items()}
    checks["new_table_entries_expected"] = all(
        v == next(f["address"] for f in report["functions"] if f["method"] == m)
        for m, v in table_targets.items())

    # Whole-file change ranges must stay inside the declared edit set.
    allowed = []
    for begin, end in report["native_change_ranges"]:
        allowed.append((begin, min(end, len(base_native))))
    allowed.append((link.segments(base_native)[-1]["off"], len(native)))
    diffs = [i for i, (a, b) in enumerate(zip(native, base_native)) if a != b]
    stray = [r for r in ranges_of(diffs) if not inside(r[0], allowed)]
    checks["stray_change_ranges"] = stray
    checks["native_changes_declared"] = not stray
    signing = assert_signable_layout(native)
    checks["signing_layout"] = signing

    # SWF digest replacement.
    old_digest = base_native[INFO_OFFSET:INFO_OFFSET + 20]
    tag, old_plain = link.aot.decompress_swf(base_swf)
    tag2, new_plain = link.aot.decompress_swf(swf)
    checks["swf_signature"] = tag == tag2
    checks["swf_old_digest_count"] = old_plain.count(b"\0\0\0\0" + old_digest)
    checks["swf_new_digest_count"] = new_plain.count(b"\0\0\0\0" + digest)
    plain_diffs = [i for i, (a, b) in enumerate(zip(old_plain, new_plain)) if a != b]
    old_at = old_plain.index(b"\0\0\0\0" + old_digest) + 4
    checks["swf_changed_only_digest"] = plain_diffs == list(range(old_at, old_at + 20))
    checks["swf_uncompressed_same_length"] = len(old_plain) == len(new_plain)

    checks["problems"] = problems
    failures = {k: v for k, v in checks.items() if v is False}
    dump(OUT / "ios-verification-report.json",
         {"status": "verified" if not failures else "failed",
          "ipa": str(ipa), "ipa_sha256": checks["ipa_sha256"],
          "source_ipa": str(baseline), "checks": checks, "failures": failures})
    print(json.dumps({"status": "verified" if not failures else "failed",
                      "ipa_sha256": checks["ipa_sha256"],
                      "changed_members": checks["changed_members"],
                      "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
