#!/usr/bin/env python3
"""Restore the three .55 weapon caps and scale only the two tough practice modes.

Default: inspect/build in memory. --apply appends the local source CDN edge.
--verify checks the actual winning source chain. No runtime copy or deployment.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
import zipfile
import zlib
from decimal import Decimal
from pathlib import Path

import wf_mod_tool as core
import wf_quest_lib as quest
import wf_store_materialize as materialize


ROOT = Path(__file__).resolve().parents[2]
BASE = "1.4.106"
TARGET = "1.4.107"
PATCH_ID = "weapon-caps-practice-hp-1.4.107"
ARCHIVE = f"pinball-{BASE}-{TARGET}-1-weapon-caps-practice-hp.zip"
AUDIT = ROOT / "assets/asset-patch/audit" / PATCH_ID
MANIFEST = ROOT / "assets/asset-patch/manifest.json"
ACTIVE = ROOT / "assets/asset-patch/active"
ABILITY = "master/ability/ability_soul.orderedmap"
PRACTICE = "master/quest/practice/practice_quest.orderedmap"
WEAPONS = {"4010014": (0, "3"), "2040001": (0, "10"), "5040009": (1, "10")}
SOLO = {str(i) for i in range(91, 98)}
GROUP = {str(i) for i in range(81, 88)}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rows(data: bytes, logical: str):
    return core.read_orderedmap_raw_rows_from_bytes(data, logical)


def text_rows(raw: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(zlib.decompress(raw).decode("utf-8"))))


def read(plan, logical: str, evidence: dict | None = None) -> bytes:
    entry = plan.entries[("common", quest.hashed_rel(logical))]
    with zipfile.ZipFile(entry.zip_path) as archive:
        data = archive.read(entry.name)
    if evidence is not None:
        evidence[logical] = {
            "archive": str(entry.zip_path), "member": entry.name,
            "sha256": digest(data), "size": len(data),
        }
    return data


def parse_table(data: bytes) -> dict:
    # The client permits an empty orderedmap; the generic quest helper rejects it.
    if data.hex() == "0c00000078da63606060000000040001":
        return {}
    return quest.parse_node(data)


def verify_scope(before: bytes, after: bytes, logical: str, allowed: dict) -> dict:
    old, new = rows(before, logical), rows(after, logical)
    if old.keys != new.keys:
        raise ValueError(f"ordered keys changed: {logical}")
    changes = []
    for key, old_raw, new_raw in zip(old.keys, old.rows, new.rows):
        if key not in allowed:
            if old_raw != new_raw:
                raise ValueError(f"unrelated compressed row changed: {logical}:{key}")
            continue
        a, b = text_rows(old_raw), text_rows(new_raw)
        if len(a) != len(b) or any(len(x) != len(y) for x, y in zip(a, b)):
            raise ValueError(f"row shape changed: {logical}:{key}")
        differences = {
            (line, column): (x, y)
            for line, (ra, rb) in enumerate(zip(a, b))
            for column, (x, y) in enumerate(zip(ra, rb)) if x != y
        }
        if differences != allowed[key]:
            raise ValueError(f"unexpected field changes: {logical}:{key}: {differences}")
        changes.append({
            "id": key,
            "fields": [dict(row=r, column=c, before=a, after=b)
                       for (r, c), (a, b) in sorted(differences.items())],
            "before": zlib.decompress(old_raw).decode("utf-8"),
            "after": zlib.decompress(new_raw).decode("utf-8"),
        })
    if {x["id"] for x in changes} != set(allowed):
        raise ValueError(f"missing target rows: {logical}")
    return {"logical": logical, "changed_rows": len(changes),
            "unchanged_raw_rows": len(old.keys) - len(changes), "changes": changes,
            "before_sha256": digest(before), "after_sha256": digest(after)}


def hp_readback(plan, practice: bytes, evidence: dict) -> dict:
    registry = json.loads((ROOT / "client-patch/android-accepted.json").read_text(encoding="utf-8-sig"))
    client = registry["variants"]["public"]
    apk = ROOT / client["apk"]
    if digest(apk.read_bytes()) != client["apk_sha256"]:
        raise ValueError("registered client APK identity changed")
    bundled = {}
    with zipfile.ZipFile(apk) as outer:
        with zipfile.ZipFile(io.BytesIO(outer.read("assets/bundle.zip"))) as archive:
            for stem in ("hp/hit_hp_basic_curve", "hp/hit_hp_correction_curve", "party/party_atk_curve"):
                logical = f"master/battle/enemy/{stem}_iosbundled.orderedmap"
                member = next(n for n in archive.namelist() if n.endswith(quest.hashed_rel(logical)))
                data = archive.read(member)
                table = parse_table(data)
                downloaded = f"master/battle/enemy/{stem}.orderedmap"
                table.update(parse_table(read(plan, downloaded, evidence)))
                bundled[stem] = table
                evidence[logical] = {"archive": str(apk), "nested_archive": "assets/bundle.zip",
                                     "member": member, "sha256": digest(data)}
    boss = parse_table(read(plan, "master/battle/boss/boss_level.orderedmap", evidence))
    funnel = parse_table(read(plan, "master/battle/boss/funnel_level.orderedmap", evidence))
    fields = parse_table(read(plan, "master/battle/field_data.orderedmap", evidence))
    zones = parse_table(read(plan, "master/battle/zone.orderedmap", evidence))
    quests = parse_table(practice)

    def pick(table, level):
        return Decimal(table[min((k for k in table if int(k) >= level), key=int)])

    def compute(row, level, correction):
        c = row.split(",")
        if c[0] != "0":
            raise ValueError("practice HP changed from the audited Hit formula")
        factors = [Decimal(375), pick(bundled["party/party_atk_curve"], level),
                   pick(bundled["hp/hit_hp_basic_curve"][c[1]], level),
                   Decimal(c[2]), Decimal(c[3]),
                   pick(bundled["hp/hit_hp_correction_curve"][c[4]], level),
                   Decimal(correction), Decimal(1)]
        return {"factors": [str(x) for x in factors], "hp": int(math.prod(factors))}

    result = []
    for key in sorted(SOLO | GROUP, key=int):
        c = next(csv.reader([quests[key]]))
        expected_field = "practice_waraboss_tough" + ("_funnel" if key in GROUP else "")
        if key in {"87", "97"}:
            expected_field += "_colorless"
        if c[110] != expected_field or c[107] != "80" or c[112] != "10800":
            raise ValueError(f"practice identity changed: {key}")
        zone = fields[expected_field].split(",")[2]
        if zone != expected_field or expected_field not in zones[zone]["0"].split(","):
            raise ValueError(f"practice boss route changed: {key}")
        main = compute(boss[expected_field], 80, c[100])
        child_code = "funnel_waraboss_tough" + ("_colorless" if key == "87" else "")
        child = compute(funnel[child_code], 80, c[99]) if key in GROUP else None
        if main["hp"] >= 2**53 or (child and child["hp"] >= 2**53):
            raise ValueError("HP exceeds the client's exact Number integer range")
        result.append({"quest": key, "name": c[2], "boss": main,
                       "funnel_each": child, "funnel_count": 4 if child else 0,
                       "initial_total": main["hp"] + (4 * child["hp"] if child else 0)})
    return {"client_apk_sha256": client["apk_sha256"], "quests": result,
            "formula": "floor(375 * PartyAtk * HitHpBasic * hits * coefficient * correction * questHP * battleScale)",
            "integer_note": "倍率在客户端最终 floor 前乘 10；与旧整数直接乘 10 的差为本体 1 HP、小木人 6 HP。"}


def build():
    cdn = (ROOT / ".cdn/cn").resolve()
    plan = materialize.build_read_only_plan(cdn, ROOT, BASE, False)
    official = materialize.build_read_only_plan(cdn, ROOT, "1.4.54", True)
    evidence = {}
    before = {logical: read(plan, logical, evidence) for logical in (ABILITY, PRACTICE)}
    original = rows(read(official, ABILITY), ABILITY)
    original_rows = dict(zip(original.keys, original.rows))
    restored = rows(before[ABILITY], ABILITY)
    ability_allowed = {key: {(line, 31): ("99", cap)} for key, (line, cap) in WEAPONS.items()}
    for key in WEAPONS:
        restored.rows[restored.keys.index(key)] = original_rows[key]
    after = {ABILITY: core.build_orderedmap_raw_rows(restored)}
    practice = rows(before[PRACTICE], PRACTICE)
    practice_allowed = {key: {(0, 100): ("1", "10")} for key in SOLO | GROUP}
    for key in GROUP:
        practice_allowed[key][(0, 99)] = ("1", "10")
    for key, edits in practice_allowed.items():
        index = practice.keys.index(key)
        plain = zlib.decompress(practice.rows[index]).decode("utf-8")
        cells = plain.split(",")
        if list(csv.reader([plain])) != [cells]:
            raise ValueError(f"unexpected quoted practice layout: {key}")
        for (_line, column), (old, new) in edits.items():
            if cells[column] != old:
                raise ValueError(f"practice preimage changed: {key}:{column}")
            cells[column] = new
        practice.rows[index] = zlib.compress(",".join(cells).encode("utf-8"), 9)
    after[PRACTICE] = core.build_orderedmap_raw_rows(practice)
    scope = [verify_scope(before[ABILITY], after[ABILITY], ABILITY, ability_allowed),
             verify_scope(before[PRACTICE], after[PRACTICE], PRACTICE, practice_allowed)]
    restored_readback = rows(after[ABILITY], ABILITY)
    for key in WEAPONS:
        if restored_readback.rows[restored_readback.keys.index(key)] != original_rows[key]:
            raise ValueError(f"weapon is not byte-identical to .54: {key}")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for logical, data in sorted(after.items()):
            name = "production/upload/" + quest.hashed_rel(logical)
            info = zipfile.ZipInfo(name, (2026, 9, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    archive_raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        if len(archive.namelist()) != 2 or archive.testzip() is not None:
            raise ValueError("invalid CDN archive")
        for logical, data in after.items():
            if archive.read("production/upload/" + quest.hashed_rel(logical)) != data:
                raise ValueError("serialized archive payload differs")
    report = {"patch_id": PATCH_ID, "base_version": BASE, "target_version": TARGET,
              "archive": {"name": ARCHIVE, "size": len(archive_raw),
                          "sha256": digest(archive_raw), "members": 2},
              "scope": scope, "hp": hp_readback(plan, after[PRACTICE], evidence),
              "sources": evidence, "weapon_rows_equal_official_1_4_54": True,
              "platforms": "common orderedmap resources for Android and iOS; no platform texture or APK/IPA changes",
              "save_impact": "balance-only; no stored IDs, progress, schema, rewards or acquisition changes",
              "validation": "serialized data and client formula checks; no device battle or HTTP service run",
              "delivery": "local source only; no commit, push, runtime sync or cloud overlay"}
    return before, after, archive_raw, report


def verify_winning(after: dict[str, bytes]) -> dict:
    manifest = json.loads(MANIFEST.read_bytes())
    original = json.loads((AUDIT / "manifest.before.json").read_bytes())
    enabled = [item for item in manifest["patches"] if item.get("enabled")]
    if manifest.get("cdn_version") != TARGET or enabled[-1].get("id") != PATCH_ID:
        raise ValueError("manifest does not advertise the new edge")
    reverted = json.loads(json.dumps(manifest))
    entry = reverted["patches"].pop()
    reverted["cdn_version"] = BASE
    if reverted != original or entry.get("depends_on") != BASE or entry.get("version") != TARGET:
        raise ValueError("manifest changed outside the one new version edge")
    if entry.get("archive") != ARCHIVE or entry.get("archive_integrity", [{}])[0].get("sha256") != digest((ACTIVE / ARCHIVE).read_bytes()):
        raise ValueError("manifest archive identity differs from the delivered ZIP")
    plan = materialize.build_read_only_plan((ROOT / ".cdn/cn").resolve(), ROOT, None, False)
    if plan.tail != TARGET or plan.health.unreachable or plan.health.issues:
        raise ValueError(f"unexpected terminal chain: {plan.tail}, {plan.health}")
    for logical, expected in after.items():
        entry = plan.entries[("common", quest.hashed_rel(logical))]
        if entry.zip_path.resolve() != (ACTIVE / ARCHIVE).resolve() or read(plan, logical) != expected:
            raise ValueError(f"patch is not the actual winning resource: {logical}")
    return {"tail": plan.tail, "winning_archive": ARCHIVE, "both_tables_match": True}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    before, after, archive_raw, report = build()
    if args.verify:
        if (ACTIVE / ARCHIVE).read_bytes() != archive_raw:
            raise ValueError("archive differs from reproducible build")
        report["effective_chain"] = verify_winning(after)
    elif args.apply:
        manifest_before = MANIFEST.read_bytes()
        manifest = json.loads(manifest_before)
        current = materialize.build_read_only_plan((ROOT / ".cdn/cn").resolve(), ROOT, None, False)
        if manifest["cdn_version"] != BASE or current.tail != BASE or current.health.unreachable or current.health.issues:
            raise ValueError("active source version changed; rebase the candidate")
        enabled = [p for p in manifest["patches"] if p.get("enabled")]
        if enabled[-1]["version"] != BASE or any(p.get("id") == PATCH_ID for p in manifest["patches"]):
            raise ValueError("manifest does not permit the expected new version edge")
        if (ACTIVE / ARCHIVE).exists() or AUDIT.exists():
            raise FileExistsError("refusing to replace an existing patch or audit")
        for path in (ACTIVE / ARCHIVE, AUDIT, MANIFEST):
            resolved = path.resolve()
            if ROOT.resolve() not in resolved.parents or ".cdn" in [x.lower() for x in resolved.parts]:
                raise ValueError(f"unsafe output: {path}")
        entry = {"id": PATCH_ID, "type": "patch", "name": "三把武器次数复原与练习木人十倍血量",
                 "description": "恢复木灵大剑、无名之弓、埃俄罗斯之弓原触发次数；仅三分钟结实假人及结实假人们的关卡 HP 倍率改为 10。",
                 "depends_on": BASE, "version": TARGET, "enabled": True,
                 "archive": ARCHIVE, "chain": [ARCHIVE], "archive_size": len(archive_raw),
                 "archive_integrity": [report["archive"]],
                 "files": ["production/upload/" + quest.hashed_rel(x) for x in sorted(after)],
                 "changes": ["木灵大剑 99→3 次，无名之弓及埃俄罗斯之弓回充 99→10 次；目标能力行逐字节恢复至 1.4.54。",
                             "Practice 91–97 本体 HP 修正 1→10；Practice 81–87 本体及小木人 HP 修正均 1→10。",
                             "两类练习关覆盖六属性及无属性；其他练习关、攻击力、回血、时间限制、存档及奖励不变。"],
                 "created_at": "2026-09-13",
                 "audit": {"directory": AUDIT.relative_to(ROOT).as_posix(), "report": "report.json"}}
        manifest["patches"].append(entry)
        manifest["cdn_version"] = TARGET
        # All validation precedes activation, and the original manifest is retained.
        AUDIT.mkdir(parents=True)
        (AUDIT / "manifest.before.json").write_bytes(manifest_before)
        for logical in after:
            leaf = Path(logical).name
            for stage, payloads in (("before", before), ("after", after)):
                target = AUDIT / stage / leaf
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(payloads[logical])
        (AUDIT / "manifest-entry.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if MANIFEST.read_bytes() != manifest_before:
            raise ValueError("manifest changed concurrently; no archive activated")
        with (ACTIVE / ARCHIVE).open("xb") as stream:
            stream.write(archive_raw)
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["effective_chain"] = verify_winning(after)
        (AUDIT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sample = {x["quest"]: x for x in report["hp"]["quests"] if x["quest"] in {"81", "91"}}
    print(json.dumps({"ok": True, "mode": "verify" if args.verify else "apply" if args.apply else "dry-run",
                      "archive": report["archive"], "scope_rows": [x["changed_rows"] for x in report["scope"]],
                      "hp": sample, "effective_chain": report.get("effective_chain")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
