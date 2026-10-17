"""Rotate only the actual admission constants in the pinned public compat SWF.

Keys are read in memory from a private complete pair. No generated source or
report contains key material. APK packaging must allocate a fresh AIR UUID.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

import port_game
from build_compat_android import replace_abc_tags, serialize_abc


INPUT_SHA256 = "0d88486dc2a7c4016933efffdee7708895361f93d924c201f9b4387aba7ce678"
OLD_ID = "android-181-author-1047-public-20261001"
ORIGIN = "http://124.222.203.221:8001"
TARGETS = {
    b"cn/admission/ClientAdmission": {162: "key", 163: "prefix", 178: "id"},
    b"cn/admission/BuildConfig": {4: "id", 6: "key"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def constants(abc):
    matches = [ci for ci, ins in enumerate(abc.instances)
               if abc.mn_name(ins[0]) == "cn.admission::BuildConfig"]
    require(len(matches) == 1, "Expected one BuildConfig class")
    result = {}
    for trait in abc.classes[matches[0]][1]:
        require(trait.kind == 6 and trait.data[0] == "slot" and trait.data[4] == 1,
                "Unexpected BuildConfig constant declaration")
        name = abc.mn_name(trait.name).split("::")[-1]
        require(name not in result, "Duplicate BuildConfig declaration")
        result[name] = abc.s(trait.data[3])
    require(set(result) == {"ID", "KEY", "ORIGIN"}, "Unexpected BuildConfig fields")
    return result


def read_pair(pair_dir, build_id):
    require(isinstance(build_id, str) and re.fullmatch(r"android-[a-z0-9-]{1,110}", build_id),
            "Expected an Android build ID")
    require(build_id != OLD_ID, "A new build ID is required")
    policy = json.loads((pair_dir / "config/client-admission.json").read_text("utf-8-sig"))
    keys = json.loads((pair_dir / "config/client-admission.keys.json").read_text("utf-8-sig"))
    require(isinstance(policy, dict) and isinstance(policy.get("builds"), list)
            and isinstance(keys, dict), "Invalid private pair structure")
    builds = policy["builds"]
    require(all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in builds),
            "Invalid admission build entry")
    require(len({row["id"] for row in builds}) == len(builds), "Duplicate admission build IDs")
    require(all(row["id"] in keys for row in builds), "Incomplete private pair")
    rows = {row["id"]: row for row in builds}
    require(OLD_ID in rows and build_id in rows, "Private pair lacks an input or output build")
    require(all(rows[value].get("platform") == "android" for value in (OLD_ID, build_id)),
            "Private pair platform mismatch")
    require(rows[build_id].get("enabled") is True, "Output build is not enabled")
    require(all(isinstance(keys.get(value), str)
                and re.fullmatch(r"[0-9a-f]{64}", keys[value])
                for value in (OLD_ID, build_id)), "Invalid admission key format")
    require(keys[OLD_ID] != keys[build_id], "The admission key must also rotate")
    return keys[OLD_ID], keys[build_id]


def rotate(source, pair_dir, build_id):
    require(port_game.sha(source) == INPUT_SHA256, "Input is not the pinned public compat SWF")
    old_key, new_key = read_pair(pair_dir, build_id)
    common, _ = port_game.dependencies()
    original_tags = common.abc_tags(source)
    require(len(original_tags) == 302, "Unexpected DoABC count")
    names = Counter(row[0] for row in original_tags)
    require(all(names[name] == 1 for name in TARGETS), "Admission DoABC missing or duplicated")
    old_values = {"id": OLD_ID.encode(), "key": old_key.encode(),
                  "prefix": ("SP-ADMISSION-1\n" + OLD_ID + "\n").encode()}
    new_values = {"id": build_id.encode(), "key": new_key.encode(),
                  "prefix": ("SP-ADMISSION-1\n" + build_id + "\n").encode()}
    edits, changes, targeted_methods = {}, [], 0
    for name, at, _, _, raw in original_tags:
        if name not in TARGETS:
            require(all(value not in raw for value in old_values.values()),
                    "Admission material unexpectedly occurs outside the target DoABCs")
            continue
        abc = common.ABC(raw)
        require(serialize_abc(abc, raw, common) == raw, "Admission ABC did not roundtrip")
        mapping = TARGETS[name]
        expected = {index: old_values[kind] for index, kind in mapping.items()}
        require({index: value for index, value in enumerate(abc.strings)
                 if value in old_values.values()} == expected,
                "Admission constant slots do not match the pinned structure")
        if name.endswith(b"BuildConfig"):
            require(constants(abc) == {"ID": OLD_ID, "KEY": old_key, "ORIGIN": ORIGIN},
                    "Input BuildConfig does not match the private pair")
        else:
            sites = []
            for body in abc.bodies:
                for ordinal, ins in enumerate(common.asm.decode(body[5])):
                    if ins.name == "pushstring" and ins.args[0] in mapping:
                        sites.append((body[0], ordinal, ins.args[0]))
            require(sites == [(31, 15, 162), (31, 16, 163), (30, 27, 178)],
                    "Admission proof/challenge runtime constant references changed")
        for index, kind in mapping.items():
            abc.strings[index] = new_values[kind]
        edits[at] = serialize_abc(abc, raw, common)
        targeted_methods += len(abc.bodies)
        for index, kind in mapping.items():
            abc.strings[index] = old_values[kind]
        require(serialize_abc(abc, raw, common) == raw, "Admission ABC inverse failed")
        changes.append({"abc": name.decode(), "pool_slots":
                        [{"index": index, "kind": kind} for index, kind in mapping.items()]})
    output = replace_abc_tags(source, edits, common)
    readback = common.abc_tags(output)
    require(len(readback) == len(original_tags), "Output DoABC count changed")
    for old, current in zip(original_tags, readback):
        require(old[0] == current[0] and old[3] == current[3], "DoABC order or prefix changed")
        if old[0] not in TARGETS:
            require(old[4] == current[4], "Unrelated DoABC bytes changed")
            continue
        abc = common.ABC(current[4])
        for index, kind in TARGETS[old[0]].items():
            require(abc.strings[index] == new_values[kind], "Output admission constant mismatch")
        if old[0].endswith(b"BuildConfig"):
            require(constants(abc) == {"ID": build_id, "KEY": new_key, "ORIGIN": ORIGIN},
                    "Output BuildConfig does not match the private pair")
        for index, kind in TARGETS[old[0]].items():
            abc.strings[index] = old_values[kind]
        require(serialize_abc(abc, old[4], common) == old[4], "Output admission inverse failed")
    old_data, new_data = common.swf_data(source), common.swf_data(output)
    old_raw_tags = list(common.swftags.iter_tags(old_data))
    new_raw_tags = list(common.swftags.iter_tags(new_data))
    require(len(old_raw_tags) == len(new_raw_tags), "SWF tag count changed")
    for a, b in zip(old_raw_tags, new_raw_tags):
        ak, ao, ah, an = a
        bk, bo, bh, bn = b
        require(ak == bk, "SWF tag order changed")
        if ao not in edits:
            require(old_data[ao:ao + ah + an] == new_data[bo:bo + bh + bn],
                    "Non-target SWF tag bytes changed")
    require(all(value not in new_data for value in old_values.values()),
            "Output retains old admission material")
    report = {
        "passed": True, "input_swf_sha256": port_game.sha(source),
        "output_swf_sha256": port_game.sha(output), "previous_admission_id": OLD_ID,
        "admission_id": build_id, "platform": "android", "origin": ORIGIN,
        "key_rotated": True, "admission_pool_rewrites": changes,
        "doabc_count": len(original_tags), "changed_doabc_count": len(edits),
        "unchanged_doabc_count": len(original_tags) - len(edits),
        "unchanged_admission_method_bodies": targeted_methods,
        "admission_runtime_proof_and_challenge_references_verified": True,
        "all_gameplay_bodies_and_traits_preserved": True,
        "all_non_target_swf_tags_preserved": True,
        "admission_pool_inverse_verified": True, "device_tested": False,
        "requires_fresh_air_uuid_and_apk_signing": True,
    }
    return output, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-swf", type=Path, required=True)
    parser.add_argument("--pair-dir", type=Path, required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--output-swf", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    paths = [args.input_swf.resolve(), args.output_swf.resolve(), args.report.resolve()]
    require(len(set(paths)) == 3, "Input, output and report must have different paths")
    for path in paths[1:]:
        require(".cdn" not in [part.lower() for part in path.parts], "Read-only CDN boundary")
        require(not path.exists(), "Fresh output and report paths are required")
    output, report = rotate(args.input_swf.read_bytes(), args.pair_dir.resolve(), args.build_id)
    args.output_swf.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output_swf.write_bytes(output)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"passed": True, "swf": str(args.output_swf),
                      "sha256": report["output_swf_sha256"], "admission_id": args.build_id}))


if __name__ == "__main__":
    main()
