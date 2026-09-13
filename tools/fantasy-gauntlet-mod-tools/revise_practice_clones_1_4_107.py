#!/usr/bin/env python3
"""Revise the user-selected, unpublished .107 first archive in place.

Default is an in-memory build. --apply replaces only the authorized first ZIP,
its manifest metadata and the two new server quest rows. --verify reads back
the effective source chain. No runtime synchronization or deployment.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import math
import sys
import zipfile
import zlib
from decimal import Decimal
from pathlib import Path

import restore_weapon_caps_practice_hp_1_4_107 as prior
import wf_mod_tool as core
import wf_quest_lib as quest
import wf_store_materialize as materialize

ROOT = prior.ROOT
ARCHIVE = prior.ARCHIVE
ACTIVE = prior.ACTIVE
MANIFEST = prior.MANIFEST
SERVER = ROOT / "assets/practice_quest.json"
AUDIT = ROOT / "assets/asset-patch/audit/practice-clones-100x-1.4.107"
OLD_SHA256 = "55f99926afbd3588890505ec52a26f0b67dc13225a2b951509886d91db4f4171"
CLONES = {
    "1101": {"source": "97", "folder": "100", "name": "高血量木人·无", "group": False},
    "1102": {"source": "87", "folder": "99", "name": "高血量木人们·无", "group": True},
}
RANK_FIELDS = ("bRankTime", "aRankTime", "sRankTime", "sPlusRankTime")
FOLDER = "master/quest/practice/practice_quest_folder.orderedmap"


def encode_json(value, model: bytes | None = None) -> bytes:
    newline = "\r\n" if model and b"\r\n" in model else "\n"
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").replace("\n", newline).encode("utf-8")


def current_plan():
    plan = materialize.build_read_only_plan((ROOT / ".cdn/cn").resolve(), ROOT, None, False)
    if plan.tail != prior.TARGET or plan.health.unreachable or plan.health.issues:
        raise ValueError(f"source tail changed: {plan.tail}, {plan.health}")
    return plan


def clone_practice(before: bytes) -> tuple[bytes, dict]:
    original = prior.rows(before, prior.PRACTICE)
    table = prior.rows(before, prior.PRACTICE)
    originals = dict(zip(original.keys, original.rows))
    parsed = prior.parse_table(before)
    added = []
    for new_id, spec in CLONES.items():
        if new_id in originals:
            raise ValueError(f"client quest ID already used: {new_id}")
        source = prior.text_rows(originals[spec["source"]])[0]
        if source[0] != spec["folder"] or source[100] != "1" or source[112] != "10800":
            raise ValueError(f"original practice identity changed: {spec['source']}")
        orders = [int(row.split(",")[1]) for row in parsed.values() if row.split(",")[0] == spec["folder"]]
        cells = source.copy()
        edits = {1: str(max(orders) + 1), 2: spec["name"], 100: "100", 112: "36000",
                 **{i: "600" for i in range(85, 89)}}
        if spec["group"]:
            edits[99] = "100"
        for column, value in edits.items():
            cells[column] = value
        if any("," in cell or "\n" in cell for cell in cells):
            raise ValueError("unexpected CSV quoting")
        raw = zlib.compress(",".join(cells).encode("utf-8"), 9)
        table.keys.append(new_id)
        table.rows.append(raw)
        added.append({"id": new_id, **spec, "fields": [
            {"column": i, "before": a, "after": b}
            for i, (a, b) in enumerate(zip(source, cells)) if a != b
        ]})
    output = core.build_orderedmap_raw_rows(table)
    back = prior.rows(output, prior.PRACTICE)
    if back.keys != original.keys + list(CLONES) or back.rows[:len(original.rows)] != original.rows:
        raise ValueError("an original practice row or its order changed")
    round_trip = prior.parse_table(output)
    for new_id, spec in CLONES.items():
        cells = round_trip[new_id].split(",")
        if cells[0] != spec["folder"] or cells[2] != spec["name"] or cells[112] != "36000":
            raise ValueError("clone identity/time did not survive serialization")
    return output, {"original_rows_byte_identical": len(original.keys), "added_rows": added,
                    "before_sha256": prior.digest(before), "after_sha256": prior.digest(output)}


def server_data() -> tuple[bytes, bytes]:
    baseline = AUDIT / "before/practice_quest.json"
    before = baseline.read_bytes() if baseline.exists() else SERVER.read_bytes()
    old = json.loads(before)
    updated = copy.deepcopy(old)
    for new_id, spec in CLONES.items():
        if new_id in old:
            raise ValueError(f"server quest ID already used: {new_id}")
        row = copy.deepcopy(old[spec["source"]])
        if any(row[field] != 180000 for field in RANK_FIELDS):
            raise ValueError("original server rank time changed")
        row["name"] = spec["name"]
        row.update({field: 600000 for field in RANK_FIELDS})
        updated[new_id] = row
    # Append only the two members, preserving the original JSON bytes (including
    # its mixed historical newline formatting) rather than reformatting it.
    end = len(before.rstrip())
    if before[end - 1:end] != b"}":
        raise ValueError("unexpected server JSON terminator")
    prefix_end = len(before[:end - 1].rstrip())
    newline = b"\r\n" if b"\r\n" in before else b"\n"
    members = json.dumps({k: updated[k] for k in CLONES}, ensure_ascii=False, indent=2).splitlines()[1:-1]
    after = before[:prefix_end] + b"," + newline + newline.join(x.encode("utf-8") for x in members) + before[prefix_end:]
    if {k: v for k, v in json.loads(after).items() if k not in CLONES} != old:
        raise ValueError("unrelated server quest data changed")
    return before, after


def hp_report(plan, original: bytes, evidence: dict) -> dict:
    result = prior.hp_readback(plan, original, evidence)
    result.pop("integer_note", None)
    base = {row["quest"]: row for row in result["quests"]}
    clones = []
    for new_id, spec in CLONES.items():
        source = base[spec["source"]]
        entry = {"quest": new_id, **spec, "time_limit_seconds": 600, "hp_multiplier": 100}
        for actor in ("boss", "funnel_each"):
            if source[actor] is None:
                entry[actor] = None
                continue
            factors = source[actor]["factors"].copy()
            factors[-2] = "100"
            exact = int(math.prod(Decimal(x) for x in factors))
            client_number = math.floor(math.prod(float(x) for x in factors))
            if abs(exact - client_number) > 1 or client_number >= 2**53:
                raise ValueError("HP rounding or integer range exceeds the verified Number contract")
            # AVM2 uses IEEE-754 Number before floor. At 100x the funnel product
            # is just below an integer; its real client HP is one below the
            # exact-decimal floor. Do not substitute Decimal for game arithmetic.
            entry[actor] = {"factors": factors, "hp": client_number, "decimal_floor": exact}
        entry["funnel_count"] = 4 if spec["group"] else 0
        entry["initial_total"] = entry["boss"]["hp"] + (4 * entry["funnel_each"]["hp"] if spec["group"] else 0)
        clones.append(entry)
    return {"original": result, "clones": clones, "client_number_range_safe": True,
            "integer_note": "100倍在最终floor之前应用；原关保持原整数血量。"}


def build():
    # Rebuild the original authorized weapon rows, then discard its old 10x
    # practice table. Every original practice row comes from the .106 preimage.
    before, previous, old_zip, old_report = prior.build()
    if prior.digest(old_zip) != OLD_SHA256:
        raise ValueError("the superseded .107 package no longer reproduces")
    practice, scope = clone_practice(before[prior.PRACTICE])
    payloads = {prior.ABILITY: previous[prior.ABILITY], prior.PRACTICE: practice}
    server_before, server_after = server_data()
    plan = current_plan()
    evidence = {}
    folders = prior.parse_table(prior.read(plan, FOLDER, evidence))
    for spec in CLONES.values():
        if spec["folder"] not in folders:
            raise ValueError("existing practice entry is missing")
        source = prior.parse_table(before[prior.PRACTICE])[spec["source"]].split(",")
        # Reusing the original quest's exact cover and all battle references.
        thumbnail = source[3] + ".png"
        prior.read(plan, thumbnail, evidence)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for logical, data in sorted(payloads.items()):
            info = zipfile.ZipInfo("production/upload/" + quest.hashed_rel(logical), (2026, 9, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    archive_raw = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != 2:
            raise ValueError("invalid revised archive")
        for logical, expected in payloads.items():
            if archive.read("production/upload/" + quest.hashed_rel(logical)) != expected:
                raise ValueError("archive payload changed during serialization")
    report = {
        "version": prior.TARGET, "base_version": prior.BASE, "archive": {
            "name": ARCHIVE, "size": len(archive_raw), "sha256": prior.digest(archive_raw), "members": 2},
        "replaces_unpublished_archive_sha256": OLD_SHA256,
        "authorization": "恢复原版木人；两类对应入口增加无属性独立关，原版100倍HP、10分钟；CDN增量合并进此前生成的包。",
        "scope": scope, "weapon_scope": old_report["scope"][0],
        "weapon_rows_equal_official_1_4_54": True,
        "weapon_table_unchanged_from_previous_archive": True,
        "hp": hp_report(plan, before[prior.PRACTICE], evidence), "sources": evidence,
        "server": {"path": SERVER.relative_to(ROOT).as_posix(), "before_sha256": prior.digest(server_before),
                   "after_sha256": prior.digest(server_after), "existing_rows_preserved": len(json.loads(server_before)),
                   "added": {k: json.loads(server_after)[k] for k in CLONES}},
        "save_impact": "Adds category 15 quest IDs 1101/1102 using existing portable quest progress and practice history tables. Original IDs and database schema retained; old V1/V2 archives stay compatible.",
        "resources": "Two common orderedmaps; existing folders, covers, field, bosses, funnels and heal actions reused without modification. No APK/IPA or platform texture changes.",
        "delivery": "Source only. No commit, push, runtime sync, service restart or cloud overlay.",
    }
    return before, payloads, archive_raw, server_before, server_after, report


def revised_manifest(before: bytes, report: dict) -> bytes:
    manifest = json.loads(before)
    entries = [p for p in manifest["patches"] if p.get("id") == prior.PATCH_ID]
    if manifest["cdn_version"] != prior.TARGET or len(entries) != 1:
        raise ValueError("target version/manifest identity changed")
    entry = entries[0]
    if entry["chain"][0] != ARCHIVE or entry["depends_on"] != prior.BASE:
        raise ValueError("first archive is no longer the authorized target")
    integrity = next(x for x in entry["archive_integrity"] if x["name"] == ARCHIVE)
    if integrity["sha256"] != OLD_SHA256:
        raise ValueError("refusing to replace a different archive revision")
    entry["name"] = entry["name"].replace("练习木人十倍血量", "独立无属性木人百倍血量（10分钟）", 1)
    old_description = "仅三分钟结实假人及结实假人们的关卡 HP 倍率改为 10。"
    if old_description not in entry["description"]:
        raise ValueError("target description changed concurrently")
    entry["description"] = entry["description"].replace(old_description, "原版练习关保持原状；在结实假人及结实假人们对应入口新增无属性关，HP 为原版 100 倍、时限 10 分钟。", 1)
    entry["changes"][1:3] = [
        "撤回原版 Practice 81–87、91–97 的十倍血量修改，全部 91 条原有关卡压缩行匹配 .106。",
        "新增 Practice 1101 高血量木人·无（入口 100）与 1102 高血量木人们·无（入口 99）；HP 为原版 100 倍，时限与评价时间均 10 分钟。",
    ]
    integrity.update(report["archive"])
    entry["archive_size"] = sum(x["size"] for x in entry["archive_integrity"])
    entry["audit"]["previous_directory"] = entry["audit"]["directory"]
    entry["audit"]["directory"] = AUDIT.relative_to(ROOT).as_posix()
    entry["audit"]["report"] = "report.json"
    return encode_json(manifest, before)


def verify(payloads: dict[str, bytes], archive_raw: bytes, server_after: bytes, report: dict) -> dict:
    if (ACTIVE / ARCHIVE).read_bytes() != archive_raw or SERVER.read_bytes() != server_after:
        raise ValueError("delivered bytes differ from the reproducible build")
    manifest_before = (AUDIT / "manifest.before.json").read_bytes()
    if MANIFEST.read_bytes() != revised_manifest(manifest_before, report):
        raise ValueError("manifest changed beyond the authorized revision")
    entry = next(p for p in json.loads(MANIFEST.read_bytes())["patches"] if p.get("id") == prior.PATCH_ID)
    for item in entry["archive_integrity"]:
        data = (ACTIVE / item["name"]).read_bytes()
        if prior.digest(data) != item["sha256"] or len(data) != item["size"]:
            raise ValueError(f"archive integrity mismatch: {item['name']}")
    plan = current_plan()
    for logical, expected in payloads.items():
        if prior.read(plan, logical) != expected:
            raise ValueError(f"effective winning resource differs: {logical}")
    baseline = materialize.build_read_only_plan((ROOT / ".cdn/cn").resolve(), ROOT, prior.BASE, False)
    if prior.read(plan, FOLDER) != prior.read(baseline, FOLDER):
        raise ValueError("original practice entry table changed")
    return {"tail": plan.tail, "archive_count_on_edge": len(entry["chain"]),
            "winning_tables_match": True, "other_archive_integrity_preserved": True,
            "server_rows_match": True, "original_folder_table_preserved": True}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    before, payloads, archive_raw, server_before, server_after, report = build()
    if args.apply:
        if AUDIT.exists():
            raise FileExistsError("revision receipt exists; use --verify")
        manifest_before = MANIFEST.read_bytes()
        old_archive = (ACTIVE / ARCHIVE).read_bytes()
        if prior.digest(old_archive) != OLD_SHA256 or SERVER.read_bytes() != server_before:
            raise ValueError("archive/server preimage changed before replacement")
        manifest_after = revised_manifest(manifest_before, report)
        for path in [AUDIT, ACTIVE / ARCHIVE, MANIFEST, SERVER]:
            resolved = path.resolve()
            if ROOT.resolve() not in resolved.parents or ".cdn" in [p.lower() for p in resolved.parts]:
                raise ValueError(f"unsafe write target: {resolved}")
        AUDIT.mkdir(parents=True)
        (AUDIT / "before").mkdir()
        (AUDIT / "after").mkdir()
        (AUDIT / "manifest.before.json").write_bytes(manifest_before)
        (AUDIT / "before/practice_quest.json").write_bytes(server_before)
        (AUDIT / "after/practice_quest.json").write_bytes(server_after)
        for logical, data in payloads.items():
            (AUDIT / "before" / Path(logical).name).write_bytes(before[logical])
            (AUDIT / "after" / Path(logical).name).write_bytes(data)
        if MANIFEST.read_bytes() != manifest_before or SERVER.read_bytes() != server_before or (ACTIVE / ARCHIVE).read_bytes() != old_archive:
            raise ValueError("preimage changed concurrently; no content activated")
        (ACTIVE / ARCHIVE).write_bytes(archive_raw)
        SERVER.write_bytes(server_after)
        MANIFEST.write_bytes(manifest_after)
        report["effective_chain"] = verify(payloads, archive_raw, server_after, report)
        (AUDIT / "report.json").write_bytes(encode_json(report))
        entry = next(p for p in json.loads(manifest_after)["patches"] if p.get("id") == prior.PATCH_ID)
        (AUDIT / "manifest-entry.json").write_bytes(encode_json(entry))
    elif args.verify:
        report["effective_chain"] = verify(payloads, archive_raw, server_after, report)
    print(json.dumps({"mode": "apply" if args.apply else "verify" if args.verify else "dry-run",
                      "archive": report["archive"], "practice_scope": report["scope"],
                      "hp": report["hp"]["clones"], "effective_chain": report.get("effective_chain")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
