"""Prepare an iOS full-ABC delta from the accepted IPA and formal Android donor."""
import copy, hashlib, importlib.util, json, sys, types, zipfile
from pathlib import Path

ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
WORK = Path(r"F:\codex\work\formal-ios-20260923")
OUT = Path(r"F:\codex\outputs\abyss-ex-independent-formations-20260923")
ANDROID_DONOR = Path(r"F:\codex\work\formal-client-20260923\independent-formations.swf")
IOS_REGISTRY = ROOT / "client-patch" / "ios-accepted.json"
KEYS = Path(r"F:\codex\.codex\secrets\starpoint-client-admission\config\client-admission.keys.json")
BUILD_ID = "ios-184-independent-party-20260923"
OLD_BUILD_ID = "ios-184-abyss-ex-20260917"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha(data): return hashlib.sha256(data).hexdigest()


def main():
    prep = load("formal_ios_prepare_helpers", ROOT / "client-patch/ios-cumulative-login/prepare.py")
    reg = json.loads(IOS_REGISTRY.read_text(encoding="utf8"))["artifact"]
    ipa = Path(reg["ipa"])
    assert sha(ipa.read_bytes()) == reg["ipa_sha256"]
    WORK.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ipa) as z:
        native = z.read(reg["native_member"])
        swf = z.read(reg["swf_member"])
    assert sha(native) == reg["native_sha256"]
    assert sha(swf) == reg["swf_sha256"]
    (WORK / "baseline-native").write_bytes(native)
    (WORK / "baseline.swf").write_bytes(swf)

    full = Path(reg["full_abc"]).read_bytes()
    assert sha(full) == reg["full_abc_sha256"]
    target = prep.View(types.SimpleNamespace(abc=prep.abcfmt.ABC(full)), prep.asm)
    before = copy.deepcopy(target.a)
    source = prep.View(prep.SwfAbc(ANDROID_DONOR), prep.asm)
    helper_names = ["cn.mod.GenericDamage", "cn.mod.IndependentRushParty"]

    # Import both helper classes from the already verified Android donor. The
    # donor SWF carries each helper as an ordinary ABC tag after the main ABC.
    sys.path.insert(0, str(ROOT / "client-patch/lens0907-0908/vendor/abcasm"))
    from swfabc import swftags
    helper_records = []
    _, _, _, raw = swftags.load_swf(str(ANDROID_DONOR))
    for code, offset, header, length in swftags.iter_tags(raw):
        if code != 82:
            continue
        data = raw[offset + header:offset + header + length]
        nul = data.index(b"\0", 4)
        name = data[4:nul].decode()
        if name not in helper_names:
            continue
        helper_abc = data[nul + 1:]
        hv = prep.View(types.SimpleNamespace(abc=prep.abcfmt.ABC(helper_abc)), prep.asm)
        start = len(target.a.methods)
        prep.ClassImporter(target, hv).merge()
        helper_records.append({"name": name, "sha256": sha(helper_abc),
                               "first_method": start, "methods": len(hv.a.methods),
                               "scripts": len(hv.a.scripts)})
    assert [r["name"] for r in helper_records] == helper_names

    labels = [
        "pinball.common.data.ability.instant::InstantAbilitySource/resolvePathCollection|1",
        "pinball.scene.battle.battle.ability::AbilityDamageShot/getEffect|1",
        "pinball.scene.battle.battle.ability::AbilityDamageShot/finish|1",
        "pinball.scene.battle.battle.squad.member::MemberImpl/applyInstantAbility|1",
        "pinball.scene.battle.battle.action::ActionEvaluator/addImpactToSubject|1",
        "pinball.online.battle.impact.attack::NormalAttackCalculator/calculate|1",
        "pinball.loading.rush::RushEventLoadingTask/summaryRemoteInput|1",
        "pinball.remote.event.rush.party::EventRushPartyRealRemote/<ctor>",
        "pinball.common.data.party.event.rush::RushEventPartyGroupHolder/getPartyCategory|1",
    ]
    importer = prep.Importer(target, source)
    changes = []
    changed_ids = set()
    for label in labels:
        ai, = target.by_label[label]
        bi, = source.by_label[label]
        original = before.bodies[ai]
        imported = importer.body(bi, original[0], scope=original[3])
        assert prep.activation_traits(target, original) == prep.activation_traits(target, imported), label
        prep.check_body(imported, target.a)
        target.a.bodies[ai] = imported
        changed_ids.add(original[0])
        changes.append({"label": label, "method_id": original[0], "body_index": ai,
                        "source_body_index": bi, "source_code_sha256": sha(source.a.bodies[bi][5]),
                        "target_code_sha256": sha(imported[5]), "strategy": "replace"})

    # Rotate the iOS admission proof and signing key in the full compiler ABC.
    keys = json.loads(KEYS.read_text(encoding="utf8"))
    old_key = keys[OLD_BUILD_ID].encode()
    new_key = keys[BUILD_ID].encode()
    old_id = OLD_BUILD_ID.encode()
    new_id = BUILD_ID.encode()
    old_prefix = ("SP-ADMISSION-1\n" + OLD_BUILD_ID + "\n").encode()
    new_prefix = ("SP-ADMISSION-1\n" + BUILD_ID + "\n").encode()
    admission = []
    for index, value in enumerate(target.a.strings):
        replacement = (new_prefix if value == old_prefix else
                       new_id if value == old_id else
                       new_key if value == old_key else None)
        if replacement is not None:
            target.a.strings[index] = replacement
            admission.append({"string_index": index, "old": value.decode(errors="replace"),
                              "new": replacement.decode(errors="replace")})
    assert admission
    assert any(row["old"] == old_prefix.decode() for row in admission)
    assert any(row["old"] == old_key.decode() for row in admission)
    assert any(row["new"] == new_prefix.decode() for row in admission)
    assert any(row["new"] == new_key.decode() for row in admission)

    # The AIR compiler only emits code for methods reachable from a newly
    # compiled class. Keep the reviewed implementations byte-identical as
    # synthetic static hook methods on GenericDamage; the native linker will
    # redirect the original iOS method slots to these compiled functions.
    def pool_string(value):
        raw = value.encode()
        if raw in target.a.strings:
            return target.a.strings.index(raw)
        target.a.strings.append(raw)
        return len(target.a.strings) - 1
    def qname(namespace, name):
        ns_string = pool_string(namespace)
        spaces = [i for i, row in enumerate(target.a.namespaces)
                  if i and row[0] == 22 and row[1] == ns_string]
        ns = spaces[0] if spaces else (target.a.namespaces.append((22, ns_string)) or len(target.a.namespaces) - 1)
        name_string = pool_string(name)
        target.a.multinames.append((7, ns, name_string))
        return len(target.a.multinames) - 1
    generic_class = next(i for i, row in enumerate(target.a.instances)
                         if target.a.mn_name(row[0]) == "cn.mod::GenericDamage")
    redirects = []
    for change in changes:
        original_id = change["method_id"]
        original_body = next(row for row in target.a.bodies if row[0] == original_id)
        duplicate_id = len(target.a.methods)
        target.a.methods.append(copy.deepcopy(target.a.methods[original_id]))
        duplicate_body = copy.deepcopy(original_body)
        duplicate_body[0] = duplicate_id
        target.a.bodies.append(duplicate_body)
        trait = prep.abcfmt.Trait()
        trait.name = qname("cn.mod", "formalHook_" + str(original_id))
        trait.kind = 1
        trait.attr = 0
        trait.metadata = []
        trait.data = ["method", 0, duplicate_id]
        target.a.classes[generic_class][1].append(trait)
        change["compiled_hook_method_id"] = duplicate_id
        redirects.append({"original": original_id, "compiled": duplicate_id,
                          "label": change["label"]})
    # Only the nine reviewed hooks and the two appended helper classes differ.
    for old, new in zip(before.bodies, target.a.bodies[:len(before.bodies)]):
        if old[0] not in changed_ids:
            assert prep.freeze(old) == prep.freeze(new), old[0]
    for pool in ("ints", "uints", "doubles", "namespaces", "ns_sets", "multinames"):
        old = getattr(before, pool)
        assert prep.freeze(old) == prep.freeze(getattr(target.a, pool)[:len(old)]), pool
    out_full = WORK / "formal-full.abc"
    out_full.write_bytes(target.a.serialize())
    assert sha(out_full.read_bytes()) == sha(target.a.serialize())
    equipment = dict(json.loads((Path(r"F:\codex\work\abyss-ex-clients-20260917\port.json")).read_text(encoding="utf8"))["equipment"])
    # The accepted public iOS EX baseline already carries the EX equipment
    # gate. Rebase the guard to the actual accepted bytes so this release
    # does not pretend to apply that earlier change a second time.
    equipment["source_sha256"] = sha(native[equipment["offset"]:equipment["offset"] + equipment["old_size"]])
    # The accepted EX IPA has a stripped runtime ABC distinct from its full
    # compiler ABC; calculate that exact native payload for the linker guard.
    native_abc_va = int.from_bytes(native[104549248 + 24:104549248 + 32], "little")
    native_abc_len = int.from_bytes(native[104549248 + 32:104549248 + 40], "little")
    # The accepted native's runtime ABC starts at the same file offset recorded
    # by the release linker; resolve it through its segment table in build_ios.
    sys.path.insert(0, str(ROOT / "client-patch/abyss-ex"))
    bi = load("formal_ios_link_helpers", ROOT / "client-patch/abyss-ex/build_ios.py")
    native_abc_offset = bi.link.file_offset(native, native_abc_va)
    baseline_runtime_abc_sha256 = sha(native[native_abc_offset:native_abc_offset + native_abc_len])
    report = {
        "status": "prepared_for_ios_native_link",
        "source_ipa": reg,
        "full_abc_file": out_full.name,
        "full_abc_sha256": sha(out_full.read_bytes()),
        "full_abc_sha1": hashlib.sha1(out_full.read_bytes()).hexdigest(),
        "baseline_runtime_abc_sha256": baseline_runtime_abc_sha256,
        "old_methods": len(before.methods),
        "total_methods": len(target.a.methods),
        "methods": changes,
        "helpers": helper_records,
        "admission_build_id": BUILD_ID,
        "previous_admission_build_id": OLD_BUILD_ID,
        "method_redirects": redirects,
        "admission_changes": admission,
        "equipment": equipment,
        "device_tested": False,
        "generic_damage_logger_removed": True,
        "generic_damage_log_path_absent": True,
        "scope": "accepted iOS EX full ABC plus generic damage entry without prototype disk logging and independent Rush party formations",
    }
    (WORK / "prepare-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")

    # build_ios.py expects this compact port contract and the baseline files.
    port = {
        "source_ipa": reg,
        "old_methods": len(before.methods),
        "total_methods": len(target.a.methods),
        "methods": changes,
        "full_abc_file": out_full.name,
        "full_abc_sha256": sha(out_full.read_bytes()),
        "full_abc_sha1": hashlib.sha1(out_full.read_bytes()).hexdigest(),
        "baseline_runtime_abc_sha256": baseline_runtime_abc_sha256,
        "build_id": BUILD_ID,
        "equipment": equipment,
    }
    (WORK / "port.json").write_text(json.dumps(port, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"status": report["status"], "total_methods": report["total_methods"], "changed": sorted(changed_ids), "helpers": helper_records}, ensure_ascii=False))


if __name__ == "__main__": main()
