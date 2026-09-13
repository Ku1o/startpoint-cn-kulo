"""Resource-only campus summon repair, appended as split 3 on 1.4.107 -> 1.4.108.

Read effective assets sparsely. Never write through .cdn or modify a client binary.
The existing, separately authored .108 degree archive is retained byte-for-byte.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/fantasy-gauntlet-mod-tools"))
import restore_weapon_caps_practice_hp_1_4_107 as assets
import wf_dsl
import wf_dsl_sig as sig
import wf_quest_lib as quest
import wf_store_materialize as materialize

BASE, TARGET = "1.4.107", "1.4.108"
ARCHIVE = f"pinball-{BASE}-{TARGET}-3-campus-summon-g1008.zip"
FIRST = f"pinball-{BASE}-{TARGET}-1-reborn-character-degrees.zip"
PRIOR_ARCHIVES = [FIRST, f"pinball-{BASE}-{TARGET}-2-epuration-gacha.zip"]
AUDIT = "assets/asset-patch/audit/campus-summon-g1008-1.4.108"
MANIFEST = ROOT / "assets/asset-patch/manifest.json"
ACTIVE = ROOT / "assets/asset-patch/active"
BREATH, SIGNAL, DEPART = ("campus_dragon_breath_begin", "campus_dragon_breath_signal", "campus_dragon_depart")
ACTIVATED = "campus_dragon_activated"
RARE = "battle/action/skill/action/rare5/"
ABILITY = "battle/action/skill/action/ability_skill/"
BIANCA = tuple(RARE + f"lady_summoner_campus$lady_summoner_campus_{n}.action.dsl.amf3.deflate" for n in (1, 2))
NEPHTIM = tuple(RARE + f"ruin_girl_campus$ruin_girl_campus_{n}.action.dsl.amf3.deflate" for n in (1, 2))
AURAS = tuple(ABILITY + f"ruin_girl_campus$ruin_girl_campus_{n}.action.dsl.amf3.deflate" for n in ("multiball_direct", "multiball_direct_a4"))
SPAWN = ABILITY + "ruin_girl_campus$ruin_girl_campus_fever_spawn.action.dsl.amf3.deflate"
PFS = tuple(f"battle/action/power_flip/action/override/ruin_girl_campus_fever$ruin_girl_campus_fever_lv{n}.action.dsl.amf3.deflate" for n in (1, 2, 3))
PREIMAGES = {
    **{x: "d8a00ca55ed65bfcfce2a6c6be45042e391998e6f12556c0f6ea7b3aa656a4ff" for x in BIANCA},
    **{x: "a5333be524f06f9a1be4a6540ffa6582c1f3c48b20f45ca1ec6155a11df12cd2" for x in NEPHTIM},
    AURAS[0]: "66a42a466a06f2d56821f320943fa6b35a066c8df138610f7130459f4734f0a8",
    AURAS[1]: "0409013ad7e453f408238b913917f041c54b119c6c78d0e2c14420829299e19b",
}
UNCHANGED_DSL = {
    SPAWN: "3b28adf1289ddc7251b009db2ffc7fc2b53e307548ecd12dffc6a3a5c72cef30",
    PFS[0]: "9860cb7754c11a718be45553a1b01f845648e39fe7d64db5a1616aab6528744b",
    PFS[1]: "8dd079caf4e2d42548b5a5a995b41505689398db62d9e27d6a810cce40427962",
    PFS[2]: "191c9e7d065be60a916d957f98a774a5f3f74824dbad63e3317dc4d6128c4150",
}
TABLES = (
    "master/ability/ability.orderedmap", "master/character/unique_condition.orderedmap",
    "master/battle/multiball/multiball.orderedmap", "master/battle/multiball/multiball_level.orderedmap",
    "master/skill/action_skill.orderedmap", "master/skill/switched_action_skill.orderedmap",
    "master/character/character_text.orderedmap",
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def walk(value):
    if isinstance(value, list):
        if value and isinstance(value[0], str):
            yield value
        for child in value:
            yield from walk(child)
    elif isinstance(value, dict):
        for child in value.values():
            yield from walk(child)


def command(name, *args):
    return ["Command", [name, *args]]


def block(*expressions):
    return ["Block", list(expressions)]


def wait(frames, name, body):
    return ["Event", ["Wait", frames, name, body]]


def named_wait(tree, name):
    found = [x for x in walk(tree) if x[0] == "Wait" and x[2] == name]
    require(len(found) == 1, "missing/ambiguous Wait: " + name)
    return found[0]


def validate(tree):
    # The native signatures allow these nullable arguments. The shared
    # static validator has no nullable type syntax; validate a disposable copy.
    typed = copy.deepcopy(tree)
    for node in walk(typed):
        if node[0] == "CreateCondition":
            require(len(node) == 13, "CreateCondition arity")
            if node[8] is None:
                node[8] = ["Skill"]
            for condition in node[2]:
                require(sig._dsl_type_ok(condition, "AdditionalConditionKind"), "invalid AdditionalConditionKind")
        if node[0] == "CreateSummonsMultiball" and len(node) == 14 and node[13] is None:
            node[13] = {}
        if node[0] == "MultiballNumberVariable" and len(node) == 7 and node[3] is None:
            # p3 is passed to SquadImpl.matchMultiball; null means no ID filter.
            node[3] = []
    sig.validate_action_dsl(typed)
    # Scalar values nested inside Array parameters are not checked by sig.
    def scalars(value):
        if isinstance(value, list):
            for child in value:
                scalars(child)
        elif isinstance(value, dict):
            if "min" in value or "max" in value:
                require("min" in value and "max" in value, "incomplete SLv value")
                require(set(value) <= {"min", "max", "mul", "add"}, "unknown SLv field")
                for key, item in value.items():
                    require(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item), "invalid SLv scalar: " + key)
            for child in value.values():
                scalars(child)
    scalars(tree)


def parse(raw):
    tree = wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
    validate(tree)
    return tree


def canonical(tree):
    return json.dumps(tree, ensure_ascii=False, separators=(",", ":"))


def bianca_parts(tree):
    lookup = tree[11][1][1][1]
    require(lookup[:5] == ["FindMultiballSubjects", 10, 11, True, [1199891]], "Bianca top-level lookup drift")
    require(lookup[5][0] == lookup[6][0] == "Block", "Bianca branch drift")
    return lookup[5][1], lookup[6][1]


def repair_bianca(tree):
    """Move only removal scheduling; re-find before the unique condition.

    Wait p1/p3 and branch expression topology are explicitly mutable. Existing
    command positional values, including identifiers and combat values, stay
    unchanged. RemoveEventFromOwner p1 is a new owner-scoped event-name string.
    """
    result = copy.deepcopy(tree)
    absent, present = bianca_parts(result)
    breath = named_wait(result, BREATH)
    signal = named_wait(result, SIGNAL)
    depart = named_wait(result, DEPART)
    require(breath[1] == 24 and signal[1] == 1, "Bianca breath/signal timing drift")
    require(depart == ["Wait", 2, DEPART, block(command("RemoveMultiball", True, [1199891]))], "Bianca nested departure drift")
    require(signal[3][1][-1] == ["Event", depart], "Bianca departure no longer nested in signal")
    unique = [x for x in breath[3][1] if x[:1] == ["Command"] and x[1][:3] == ["CreateCondition", 11, [["ACUnique", 11998902, [{"min": 1, "max": 1}]]]]]
    require(len(unique) == 1, "Bianca delayed unique condition drift")
    index = breath[3][1].index(unique[0])
    # Unlike a stored Member reference, this resolves from the live scene at
    # callback time. A newly spawned dragon clears this callback before spawn.
    breath[3][1][index] = command("FindMultiballSubjects", 10, 11, True, [1199891], block(), block(unique[0]))
    signal[3][1].pop()
    # Each nested Wait is created after the current update-phase scan; with an
    # initial counter of -1, 24 -> nested 1 -> nested 2 retires at local tick 29.
    present.insert(0, command("RemoveEventFromOwner", DEPART))
    present.append(wait(29, DEPART, copy.deepcopy(depart[3])))
    # Cancel old callbacks only when starting a new dragon generation. Ordinary
    # repeated breaths retain every cast's own breath, self signal and FEVER.
    absent[:0] = [command("RemoveEventFromOwner", name) for name in (BREATH, SIGNAL, DEPART, ACTIVATED)]
    validate(result)
    # Prove there was no implicit change to another command, scalar or branch.
    restored = copy.deepcopy(result)
    a, p = bianca_parts(restored)
    del a[:4]
    require(p.pop(0) == command("RemoveEventFromOwner", DEPART), "departure cancellation inverse")
    moved = p.pop()
    require(moved[1][:3] == ["Wait", 29, DEPART], "departure relocation inverse")
    moved[1][1] = 2
    named_wait(restored, SIGNAL)[3][1].append(moved)
    b = named_wait(restored, BREATH)[3][1]
    require(b[index][1][:5] == ["FindMultiballSubjects", 10, 11, True, [1199891]], "guard inverse")
    b[index] = b[index][1][6][1][0]
    require(canonical(restored) == canonical(tree), "undeclared Bianca change")
    return result


def repair_nephtim(tree, logical):
    result = copy.deepcopy(tree)
    # Only summon targets: party-member buffs and self ACUnique are unchanged.
    target, kinds = (71, {"ACAdditionalDirectAttack", "ACAttackPoint"}) if logical in NEPHTIM else (71 if logical == AURAS[0] else 81, {"ACSeparatedTermDirectDamage"})
    changed = []
    for node in walk(result):
        if node[0] == "CreateCondition" and node[1] == target:
            require(len(node[2]) == 1 and node[2][0][0] in kinds and node[12] is True, "Neph summon condition drift")
            node[12] = False  # p12 forceApply; not p5 cancelable or p9 invisible.
            changed.append(node)
    require(len(changed) == (2 if logical in NEPHTIM else 1), "Neph condition count drift")
    validate(result)
    inverse = copy.deepcopy(result)
    for node in walk(inverse):
        if node[0] == "CreateCondition" and node[1] == target:
            node[12] = True
    require(canonical(inverse) == canonical(tree), "undeclared Neph change")
    return result


def transform(logical, raw, original):
    require(logical in PREIMAGES and sha(original) == PREIMAGES[logical], "unrecognized original: " + logical)
    before = parse(original)
    after = repair_bianca(before) if logical in BIANCA else repair_nephtim(before, logical)
    tree = parse(raw)
    require(canonical(tree) in (canonical(before), canonical(after)), "unrecognized current tree: " + logical)
    encoded = zlib.compress(wf_dsl.encode_amf3(after), 9, wbits=-15)
    require(canonical(parse(encoded)) == canonical(after), "DSL serialized readback mismatch")
    return encoded


def pack(payloads):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    result = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        require(archive.testzip() is None and set(archive.namelist()) == set(payloads), "archive member mismatch")
        for name, raw in payloads.items():
            require(name.startswith("production/upload/") and ".." not in Path(name).parts, "unsafe archive path")
            require(archive.read(name) == raw, "archive readback mismatch")
    return result


def merge_manifest(before, integrity):
    result = copy.deepcopy(before)
    enabled = [p for p in result["patches"] if p.get("enabled")]
    require(result["cdn_version"] == TARGET and enabled[-1]["version"] == TARGET, "expected current .108 tail")
    edge = enabled[-1]
    require(edge["depends_on"] == BASE and edge["archive"] == FIRST, "unexpected .108 edge")
    chain = edge.get("chain") or [edge["archive"]]
    require(chain == PRIOR_ARCHIVES and [x["name"] for x in edge["archive_integrity"]] == PRIOR_ARCHIVES, "split 3 already occupied or manifest drift")
    require(not set(edge["files"]) & set(integrity["files"]), "repair overlaps existing .108 resources")
    edge["chain"] = [*PRIOR_ARCHIVES, ARCHIVE]
    edge["archive_integrity"].append(integrity)
    edge["archive_size"] = sum(x["size"] for x in edge["archive_integrity"])
    edge["files"] = sorted(set(edge["files"]) | set(integrity["files"]))
    edge["changes"].extend([
        "校园碧安卡重复吐息刷新统一退场计时；延迟状态重查小龙，重新召唤前清理旧回调。",
        "校园奈芙提姆主动技能及能力3/4的召唤物普通增益不再强制施加，跳过已退场对象；数值与召唤数量不变。",
    ])
    edge["audit"]["campus_summon_g1008_directory"] = AUDIT
    return result


def safe_path(path):
    resolved = path.resolve()
    require(resolved.is_relative_to(ROOT.resolve()) and not resolved.is_relative_to((ROOT / ".cdn").resolve()), "unsafe source output: " + str(path))


def current_plan():
    plan = materialize.build_read_only_plan((ROOT / ".cdn/cn").resolve(), ROOT, None, False)
    require(plan.tail == TARGET and not plan.health.unreachable and not plan.health.issues, "unhealthy current .108 chain")
    return plan


def prepare(work):
    require(not work.resolve().is_relative_to((ROOT / ".cdn").resolve()), "work must be outside pristine CDN")
    manifest_raw = MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)
    plan = current_plan()
    before, after, sources, payloads = {}, {}, {}, {}
    for logical, expected in PREIMAGES.items():
        raw = assets.read(plan, logical, sources)
        require(sha(raw) == expected, "effective input drift: " + logical)
        before[logical] = raw
        after[logical] = transform(logical, raw, raw)
        require(transform(logical, after[logical], raw) == after[logical], "non-idempotent repair")
        payloads["production/upload/" + quest.hashed_rel(logical)] = after[logical]
    for logical, expected in UNCHANGED_DSL.items():
        raw = assets.read(plan, logical, sources)
        require(sha(raw) == expected, "unchanged DSL drift: " + logical)
        parse(raw)
        before[logical] = raw
    for logical in TABLES:
        before[logical] = assets.read(plan, logical, sources)
    archive_raw = pack(payloads)
    integrity = {"name": ARCHIVE, "size": len(archive_raw), "sha256": sha(archive_raw), "members": len(payloads), "files": sorted(payloads)}
    merged = merge_manifest(manifest, integrity)
    preserved = {name: sha((ACTIVE / name).read_bytes()) for name in PRIOR_ARCHIVES}
    for name, digest in preserved.items():
        record = next(x for x in merged["patches"][-1]["archive_integrity"] if x["name"] == name)
        require(record["sha256"] == digest, "existing archive integrity mismatch: " + name)
    report = {
        "base": BASE, "target": TARGET, "archive": integrity,
        "manifest_before_sha256": sha(manifest_raw), "manifest_after_sha256": sha(json_bytes(merged)),
        "preserved_archives": preserved, "sources": sources,
        "changes": [{"logical": logical, "before_sha256": sha(before[logical]), "after_sha256": sha(raw),
                     "inverse_scope_check": True, "idempotent": True, "signature_and_serialized_readback": True} for logical, raw in after.items()],
        "unchanged": {logical: sha(raw) for logical, raw in before.items() if logical not in after},
        "bianca": {"forms": [1, 2], "dragon_id": 1199891, "unique_condition_id": 11998902,
                   "breath_wait": 24, "self_signal_nested_wait": 1, "departure_initial_wait": 29,
                   "repeated_casts": "preserve per-cast signals; refresh only departure", "new_generation": "cancel prior owner breath/signal/depart/activated events"},
        "nephtim": {"forms": [1, 2], "changed_force_apply_positions": 6,
                    "scope": "two summon-target buffs per skill form; one summon-target condition in each A3/A4 action",
                    "fresh_spawn_callback": "unchanged: evaluated in the normal action/impact cycle; mixed heal-rejection semantics preserved"},
        "platforms": "Android/iOS common ActionDSL; no texture, SWF, APK or IPA changes",
        "save_impact": "transient combat script only; no saved IDs, schema, ownership, rewards or transfer format changes",
        "device_tested": False, "runtime_synced": False, "committed": False, "cloud_deployed": False,
    }
    work.mkdir(parents=True, exist_ok=True)
    (work / "manifest.before.json").write_bytes(manifest_raw)
    (work / "manifest.after.json").write_bytes(json_bytes(merged))
    # Hashed sparse snapshots avoid duplicate filenames across logical roots.
    for stage, items in (("before", before), ("after", after)):
        for logical, raw in items.items():
            path = work / stage / quest.hashed_rel(logical)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    (work / ARCHIVE).write_bytes(archive_raw)
    (work / "report.json").write_bytes(json_bytes(report))
    require(MANIFEST.read_bytes() == manifest_raw, "manifest changed during preparation")
    return report


def verify(work):
    report = json.loads((work / "report.json").read_bytes())
    require(MANIFEST.read_bytes() == (work / "manifest.after.json").read_bytes(), "activated manifest mismatch")
    require(sha((ACTIVE / ARCHIVE).read_bytes()) == report["archive"]["sha256"], "activated ZIP mismatch")
    for name, digest in report["preserved_archives"].items():
        require(sha((ACTIVE / name).read_bytes()) == digest, "existing archive changed: " + name)
    plan = current_plan()
    for item in report["changes"]:
        logical = item["logical"]
        entry = plan.entries[("common", quest.hashed_rel(logical))]
        require(entry.zip_path.resolve() == (ACTIVE / ARCHIVE).resolve(), "repair is shadowed: " + logical)
        raw = assets.read(plan, logical)
        require(sha(raw) == item["after_sha256"], "effective readback mismatch")
        original = (work / "before" / quest.hashed_rel(logical)).read_bytes()
        require(transform(logical, raw, original) == raw, "active resource failed reproduction")
    for logical, expected in report["unchanged"].items():
        require(sha(assets.read(plan, logical)) == expected, "unrelated runtime asset changed: " + logical)
    return {"tail": plan.tail, "winning_archive": ARCHIVE, "changed_resources": len(report["changes"]), "unchanged_resources": len(report["unchanged"]), "prior_archives_preserved": True}


def apply(work):
    report = json.loads((work / "report.json").read_bytes())
    # Rebuild all inputs/outputs in memory before mutating the source manifest.
    before_manifest = (work / "manifest.before.json").read_bytes()
    require(MANIFEST.read_bytes() == before_manifest, "manifest drift; prepare again")
    plan = current_plan()
    payloads = {}
    for logical in PREIMAGES:
        original = (work / "before" / quest.hashed_rel(logical)).read_bytes()
        require(assets.read(plan, logical) == original, "effective source changed before apply")
        raw = transform(logical, original, original)
        require(raw == (work / "after" / quest.hashed_rel(logical)).read_bytes(), "candidate drift")
        payloads["production/upload/" + quest.hashed_rel(logical)] = raw
    packed = pack(payloads)
    require(sha(packed) == report["archive"]["sha256"], "candidate ZIP drift")
    merged = json_bytes(merge_manifest(json.loads(before_manifest), report["archive"]))
    require(merged == (work / "manifest.after.json").read_bytes(), "candidate manifest drift")
    target, audit = ACTIVE / ARCHIVE, ROOT / AUDIT
    for path in (target, audit, MANIFEST):
        safe_path(path)
    require(not target.exists() and not audit.exists(), "refusing to replace existing repair outputs")
    for name, digest in report["preserved_archives"].items():
        require(sha((ACTIVE / name).read_bytes()) == digest, "existing archive changed before apply: " + name)
    # Only the explicitly prepared sparse receipts are copied into the audit.
    audit.mkdir(parents=True)
    for stage in ("before", "after"):
        for logical in PREIMAGES:
            name = quest.hashed_rel(logical)
            dest = audit / stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((work / stage / name).read_bytes())
    for name in ("manifest.before.json", "report.json"):
        (audit / name).write_bytes((work / name).read_bytes())
    with target.open("xb") as stream:
        stream.write(packed)
    require(MANIFEST.read_bytes() == before_manifest, "manifest changed before activation")
    temporary = MANIFEST.with_name("manifest.campus-summon-g1008.tmp")
    with temporary.open("xb") as stream:
        stream.write(merged)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, MANIFEST)
    receipt = verify(work)
    (audit / "effective-chain.json").write_bytes(json_bytes(receipt))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = apply(args.work) if args.apply else verify(args.work) if args.verify else prepare(args.work)
    print(json.dumps(result if args.apply or args.verify else {"archive": result["archive"], "changed": len(result["changes"]), "unchanged": len(result["unchanged"])}, ensure_ascii=False))
