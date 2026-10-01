"""Prepare iOS full ABC for the seven-layer equipment rules port.

This is a compiler-input preparation step only. It starts from the accepted
startup-download iOS ABC and imports the reviewed Android L7 methods. No IPA,
linking, signing or admission material is handled here.
"""
from __future__ import annotations
import copy, hashlib, json, sys, types, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[1]
ROOT = CLIENT.parent
WORK = Path(r"F:/codex/work/author-equipment-ios-public-20261001")
SOURCE_IPA = Path(r"F:/codex/outputs/ios-startup-download-20260927-r2/ios/StarPoint-iOS-1.8.4-author-1047-startup-download-fix-20260927-r2-unsigned.ipa")
SOURCE_IPA_SHA256 = "123fdafd38caff60b64bebf4bd2d7dc8f73a48de2e08ba5f99f8d9a79a20d769"
SOURCE_FULL_ABC = Path(r"F:/codex/work/ios-startup-download-20260927-r2/startup-download-full.abc")
SOURCE_FULL_ABC_SHA256 = "e100ae2f0d6b77ed278f91fda753df3402d7aa12a1b1867600c61f63e4b07f39"
DONOR_SWF = Path(r"F:/codex/work_author_review_20260930_round2/public1047-rebuild/l7.swf")
DONOR_SWF_SHA256 = "2eebe2196d5cbe51388efda7ce50bb8eb050da4bcc22eab1a0af85bb680f8845"
IOS_EXPECTED_METHODS = 101436

sys.path[:0] = [str(CLIENT / "lens0907-0908"), str(CLIENT / "lens0907-0908/vendor/abcasm"), str(ROOT / "tools/lens-integration")]
import build_swf as p  # type: ignore
from swfabc import abcfmt, swftags  # type: ignore

CHANGED = [
    "pinball.common.data.ability::AbilitySoulAbilityLogic/getDescriptionWithoutAdditional|1",
    "pinball.common.data.ability::AbilitySoulAbilityLogic/getDescriptionsWithoutAdditional|1",
    "pinball.master.generated::AbilitySoulValues$/parseAt106|1",
    "pinball.common.data.character::BattleCharacterLogic/getAvailableAbilities|1",
    "pinball.common.data.character::BattleCharacterLogic/resolvePathCollection|1",
    "pinball.common.data.ability::EquipmentEnhancementAbilityLogic/getAllDescriptionsToMapForDialog|1",
    "pinball.master.generated::EquipmentEnhancementAbilityValues$/parseAt109|1",
    "pinball.common.data.equipmentEnhancement::EquipmentEnhancementLogic/getPixelart|1",
    "pinball.scene.equipmentList::EquipmentListScene/compareByEquipmentStatus|1",
    "pinball.scene.equipmentSelect::EquipmentSelectThumbnailListRepository/sortByRarity|1",
    "pinball.ui.component.item::ItemThumbnailView/replace|1",
    "pinball.ui.component.item::ItemThumbnailView/setRarity|1",
    "pinball.common.data.item::OwnedEquipmentLogic/getUseableAwakingCrystal|1",
    "pinball.ui.component.item.party::PartyItemThumbnailView/updateEnhancedEffectAnimation|1",
]
ADDED = [
    "pinball.common.data.character::BattleCharacterLogic/wfCountEquipment|1",
    "pinball.common.data.character::BattleCharacterLogic/wfEquipmentRule|1",
    "pinball.common.data.character::BattleCharacterLogic/wfIsCursedSoul|1",
    "pinball.common.data.character::BattleCharacterLogic/wfIsDecaySoul|1",
    "pinball.common.data.character::BattleCharacterLogic/wfPreloadEquipmentTiers|1",
    "pinball.common.data.character::BattleCharacterLogic/wfTierAbility|1",
]
HELPER = "cn.mod::AuthorState"
OWNER = "pinball.common.data.character::BattleCharacterLogic"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def view(abc):
    return p.View(types.SimpleNamespace(abc=abc), p.asm)


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf8")


def main_abc(swf: Path):
    _, _, _, raw = swftags.load_swf(str(swf))
    hits = []
    for code, off, header, length in swftags.iter_tags(raw):
        if code != 82:
            continue
        data = raw[off + header : off + header + length]
        nul = data.index(b"\0", 4)
        name = data[4:nul].decode("utf8", "replace")
        if name.startswith("boot_"):
            hits.append((name, abcfmt.ABC(data[nul + 1 :])))
    if len(hits) != 1:
        raise AssertionError(("main ABC count", len(hits)))
    return hits[0]


def method_info(v, mid):
    m = v.a.methods[mid]
    return v.mn(m[0]), tuple(v.mn(x) for x in m[1]), m[3]


def activation(v, body):
    return p.activation_traits(v, body)


def main():
    ipa = SOURCE_IPA
    full_path = SOURCE_FULL_ABC
    if sha(ipa.read_bytes()) != SOURCE_IPA_SHA256:
        raise AssertionError("accepted iOS IPA hash changed")
    full_bytes = full_path.read_bytes()
    if sha(full_bytes) != SOURCE_FULL_ABC_SHA256:
        raise AssertionError("accepted iOS full ABC hash changed")
    if len(abcfmt.ABC(full_bytes).methods) != IOS_EXPECTED_METHODS:
        raise AssertionError("unexpected accepted iOS method count")
    if sha(DONOR_SWF.read_bytes()) != DONOR_SWF_SHA256:
        raise AssertionError("Android L7 donor hash changed")
    _, donor_abc = main_abc(DONOR_SWF)
    target_abc = abcfmt.ABC(full_bytes)
    target_before = copy.deepcopy(target_abc)
    target = view(target_abc)
    donor = view(donor_abc)
    if len(donor.a.methods) != 101074:
        raise AssertionError(("unexpected L7 method count", len(donor.a.methods)))

    importer = p.Importer(target, donor)
    # The two closures are ordinary compiler methods referenced by newfunction.
    # They are appended before parent bodies so Importer can rewrite call IDs.
    closure_labels = [
        "pinball.common.data.character::BattleCharacterLogic/resolvePathCollection|1/closure:0",
        "pinball.common.data.ability::EquipmentEnhancementAbilityLogic/getAllDescriptionsToMapForDialog|1/closure:0",
    ]
    appended = []
    for label in closure_labels:
        if label not in donor.by_label or label in target.by_label:
            raise AssertionError(("closure mapping", label))
        source_bi = donor.by_label[label][0]
        source_mid = donor.a.bodies[source_bi][0]
        target_mid = len(target.a.methods)
        importer.methods[source_mid] = target_mid
        target.a.methods.append(importer.info(source_mid))
        body = importer.body(source_bi, target_mid)
        p.check_body(body, target.a)
        target.a.bodies.append(body)
        appended.append({"label": label, "source_method": source_mid, "compiled_method": target_mid, "kind": "closure", "body_sha256": sha(body[5])})

    # Append the six BattleCharacterLogic methods to the runtime class. Their
    # compiled copies are added to AuthorState below because AIR does not emit
    # native implementations appended to an already-native class.
    owner_i = next(i for i, row in enumerate(target.a.instances) if target.a.mn_name(row[0]) == OWNER)
    owner_traits = target.a.instances[owner_i][6]
    helper_i = next(i for i, row in enumerate(target.a.instances) if target.a.mn_name(row[0]) == HELPER)
    helper_traits = target.a.classes[helper_i][1]
    added_records = []
    for label in ADDED:
        source_bi = donor.by_label[label][0]
        source_mid = donor.a.bodies[source_bi][0]
        target_mid = len(target.a.methods)
        importer.methods[source_mid] = target_mid
        target.a.methods.append(importer.info(source_mid))
        body = importer.body(source_bi, target_mid)
        p.check_body(body, target.a)
        target.a.bodies.append(body)
        source_trait = next(t for t in donor.a.instances[next(i for i,r in enumerate(donor.a.instances) if donor.a.mn_name(r[0]) == OWNER)][6]
                            if donor.a.mn_name(t.name) == label.split("/")[-1].split("|")[0])
        trait = importer.trait(source_trait)
        owner_traits.append(trait)
        # Give the compiler a native-emittable owner for this method. Runtime
        # dispatch remains on BattleCharacterLogic through the original method
        # ID; link_ios will alias that ID to this compiled method.
        compiled_mid = len(target.a.methods)
        target.a.methods.append(copy.deepcopy(target.a.methods[target_mid]))
        compiled_body = copy.deepcopy(body); compiled_body[0] = compiled_mid
        target.a.bodies.append(compiled_body)
        hook = p.abcfmt.Trait()
        # qname helper: reuse the target pool's public cn.mod namespace/name.
        ns = next(i for i,n in enumerate(target.a.namespaces) if n[0] == 22 and target.a.s(n[1]) == "cn.mod")
        name = f"authorEquipmentMethod{target_mid}".encode("utf8")
        if name in target.a.strings: si = target.a.strings.index(name)
        else: target.a.strings.append(name); si = len(target.a.strings)-1
        mn = next((i for i,m in enumerate(target.a.multinames) if m[0] == 7 and m[1] == ns and m[2] == si), None)
        if mn is None:
            target.a.multinames.append((7, ns, si)); mn = len(target.a.multinames)-1
        hook.name = mn; hook.kind = 1; hook.attr = 0; hook.metadata = []; hook.data = ["method", 0, compiled_mid]
        helper_traits.append(hook)
        added_records.append({"label": label, "source_method": source_mid, "runtime_method": target_mid, "compiled_method": compiled_mid,
                              "runtime_body_sha256": sha(body[5]), "compiled_body_sha256": sha(compiled_body[5])})

    # Import changed methods and compile every one through an append-only helper
    # hook. A method with a different activation frame keeps its original ABC
    # body; the linker redirects its method-table entry to the compiled hook.
    changed_records = []
    for label in CHANGED:
        target_bi = target.by_label[label][0]
        source_bi = donor.by_label[label][0]
        old = copy.deepcopy(target.a.bodies[target_bi])
        source = donor.a.bodies[source_bi]
        target_mid = old[0]
        # Importer maps all same-label calls plus the six methods above.
        try:
            imported = importer.body(source_bi, target_mid, scope=old[3])
        except AssertionError as exc:
            if "lexical scope index" not in str(exc):
                raise
            imported = importer.body(source_bi, target_mid, scope=None)
        p.check_body(imported, target.a)
        same_activation = activation(view(target_before), old) == activation(target, imported)
        strategy = "replace" if same_activation else "redirect_activation"
        if same_activation:
            target.a.bodies[target_bi] = imported
        # Append a compiler method with the imported body and preserve the
        # original method_info/activation ABI on the existing method ID.
        hook_mid = len(target.a.methods)
        target.a.methods.append(copy.deepcopy(target.a.methods[target_mid]))
        hook_body = copy.deepcopy(imported); hook_body[0] = hook_mid
        target.a.bodies.append(hook_body)
        nm = f"authorEquipmentHook{target_mid}".encode("utf8")
        if nm in target.a.strings: si = target.a.strings.index(nm)
        else: target.a.strings.append(nm); si = len(target.a.strings)-1
        ns = next(i for i,n in enumerate(target.a.namespaces) if n[0] == 22 and target.a.s(n[1]) == "cn.mod")
        qmn = next((i for i,m in enumerate(target.a.multinames) if m[0] == 7 and m[1] == ns and m[2] == si), None)
        if qmn is None:
            target.a.multinames.append((7, ns, si)); qmn = len(target.a.multinames)-1
        trait = p.abcfmt.Trait(); trait.name=qmn; trait.kind=1; trait.attr=0; trait.metadata=[]; trait.data=["method",0,hook_mid]; helper_traits.append(trait)
        changed_records.append({"label": label, "runtime_method": target_mid, "compiled_method": hook_mid,
                                "strategy": strategy, "source_method": source[0],
                                "activation_runtime": len(activation(view(target_before), old)),
                                "activation_imported": len(activation(target, imported)),
                                "runtime_body_sha256": sha(imported[5]) if strategy == "replace" else sha(old[5]),
                                "compiled_body_sha256": sha(hook_body[5]),
                                "source_body_sha256": sha(source[5])})

    # Structural prefix checks: all existing pools, methods, scripts, classes,
    # and instance traits remain in place; only listed method bodies and the
    # two explicitly extended trait lists are changed.
    for pool in ("ints", "uints", "doubles", "strings", "namespaces", "ns_sets", "multinames"):
        old = getattr(target_before, pool); new = getattr(target.a, pool)
        if p.freeze(old) != p.freeze(new[:len(old)]):
            raise AssertionError(("pool prefix changed", pool))
    if p.freeze(target_before.methods) != p.freeze(target.a.methods[:len(target_before.methods)]):
        raise AssertionError("old method_info prefix changed")
    if p.freeze(target_before.metadata) != p.freeze(target.a.metadata[:len(target_before.metadata)]):
        raise AssertionError("metadata prefix changed")
    if p.freeze(target_before.scripts) != p.freeze(target.a.scripts[:len(target_before.scripts)]):
        raise AssertionError("script prefix changed")
    for ci, old_class in enumerate(target_before.classes):
        new_class = target.a.classes[ci]
        if ci != helper_i and p.freeze(old_class) != p.freeze(new_class):
            raise AssertionError(("unrelated class prefix changed", ci))
    for i, old in enumerate(target_before.instances):
        new = target.a.instances[i]
        if p.freeze(old[:-1]) != p.freeze(new[:-1]): raise AssertionError(("instance header changed", i))
        old_traits = old[-1]; new_traits = new[-1]
        if i != owner_i and i != helper_i and p.freeze(old_traits) != p.freeze(new_traits[:len(old_traits)]):
            raise AssertionError(("unrelated instance traits changed", i))
    expected_changed = {target.by_label[r["label"]][0] for r in changed_records if r["strategy"] == "replace"}
    actual_changed = {i for i,(old,new) in enumerate(zip(target_before.bodies,target.a.bodies)) if p.freeze(old) != p.freeze(new)}
    if actual_changed != expected_changed:
        raise AssertionError(("unexpected existing body changes", sorted(actual_changed), sorted(expected_changed)))
    full = target.a.serialize()
    if abcfmt.ABC(full).serialize() != full: raise AssertionError("full ABC roundtrip failed")
    WORK.mkdir(parents=True, exist_ok=True)
    out_full = WORK / "equipment-ios-full.abc"; out_full.write_bytes(full)
    report = {
        "status": "ios_equipment_full_abc_prepared_native_link_pending",
        "source_ipa": str(ipa), "source_ipa_sha256": SOURCE_IPA_SHA256,
        "source_full_abc": str(full_path), "source_full_abc_sha256": SOURCE_FULL_ABC_SHA256,
        "source_full_abc_method_count": len(target_before.methods),
        "donor_swf": str(DONOR_SWF), "donor_swf_sha256": DONOR_SWF_SHA256,
        "donor_main_abc_method_count": len(donor.a.methods),
        "full_abc_file": str(out_full), "full_abc_sha256": sha(full), "full_abc_sha1": hashlib.sha1(full).hexdigest(),
        "old_methods": len(target_before.methods), "total_methods": len(target.a.methods),
        "changed_existing": changed_records, "added_equipment": added_records,
        "closures": appended, "helper_class": HELPER,
        "runtime_body_changes": sorted(expected_changed),
        "new_traits": len(added_records) + len(changed_records),
        "admission_rotation": "deferred_to_iOS_linker",
        "ipa_built": False, "linked": False, "device_tested": False,
    }
    dump(WORK / "port.json", report)
    print(json.dumps({k: report[k] for k in ("status","old_methods","total_methods","full_abc_sha256","full_abc_sha1","new_traits","runtime_body_changes")}, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
