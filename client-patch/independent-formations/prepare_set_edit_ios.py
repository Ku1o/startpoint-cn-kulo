"""Prepare the one new iOS AOT hook for the C8601 SET editor fix.

The previous independent-formations IPA and its full compiler ABC remain the
baseline.  The patched Android SWF supplies the reviewed ActionScript body;
the iOS full ABC receives that body and one compiled duplicate hook.
"""
from __future__ import annotations

import copy
import hashlib
import json
import struct
import sys
import types
import zipfile
from pathlib import Path

ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
WORK = Path(r"F:\codex\work\set-edit-c8601-ios-public-20260924")
BASE_IPA = Path(r"F:\codex\outputs\abyss-ex-independent-formations-20260923\StarPoint-iOS-1.8.4-independent-formations-public-20260923-unsigned.ipa")
BASE_FULL = Path(r"F:\codex\work\formal-ios-20260923\formal-full.abc")
ANDROID_SWF = WORK / "android-latest.swf"
ANDROID_APK = Path(r"F:\codex\outputs\set-edit-c8601-default-title-safe-lan-20260924\StarPoint-CN-1.8.1-independent-formations-set-edit-c8601-default-title-safe-lan-20260924-da77d80a.apk")
LABEL = "pinball.scene.partyGroupEdit::PartyGroupEditSceneView/refreshPartyCategory|1"
OLD_METHODS = 101314
EXPECTED_BASE_FULL_SHA = "4ceaa2550ef46fe5a0b8cc482b7de0e3fdb260e9d0944ddc32e54df3ab21b8c7"

sys.path.insert(0, str(ROOT / "client-patch/ios-cumulative-login"))
import prepare as prep  # noqa: E402


def sha(data_or_path) -> str:
    data = data_or_path if isinstance(data_or_path, (bytes, bytearray)) else Path(data_or_path).read_bytes()
    return hashlib.sha256(bytes(data)).hexdigest()


def qname(abc, value_namespace, value_name):
    """Return a QName, appending only new pool entries after the old prefix."""
    def pool_string(value):
        raw = value.encode()
        for i, item in enumerate(abc.strings):
            if item == raw:
                return i
        abc.strings.append(raw)
        return len(abc.strings) - 1

    ns_string = pool_string(value_namespace)
    namespaces = [i for i, row in enumerate(abc.namespaces)
                  if i and row[0] == 22 and row[1] == ns_string]
    if namespaces:
        ns = namespaces[0]
    else:
        abc.namespaces.append((22, ns_string))
        ns = len(abc.namespaces) - 1
    name_string = pool_string(value_name)
    for i, row in enumerate(abc.multinames):
        if row == (7, ns, name_string):
            return i
    abc.multinames.append((7, ns, name_string))
    return len(abc.multinames) - 1


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    assert sha(BASE_IPA) == "3eedbcb595856a0a2347058ae4a8fecc9a5a3e80a7f636ab0de35d1ffaa37188"
    assert sha(BASE_FULL) == EXPECTED_BASE_FULL_SHA
    assert sha(ANDROID_APK) == "e531534d9548d6e1cac5cc412d3bf9aad6d5df8330565ce022f54b0fe8180d51"
    with zipfile.ZipFile(BASE_IPA) as archive:
        native = archive.read("Payload/worldflipper.app/worldflipper")
        swf = archive.read("Payload/worldflipper.app/worldflipper_ios_release.swf")
    assert sha(native) == "e1d4d3e9f1ae9966416ae38e9cfa9ca1fabf1391a7f8bbfaf5c149c7cc4a0661"
    assert sha(swf) == "0d868c286d939ca33d0748db9a9ef55ec42ca4a6c8baeb86ef0d7f24418ee625"
    (WORK / "baseline-native").write_bytes(native)
    (WORK / "baseline.swf").write_bytes(swf)
    with zipfile.ZipFile(ANDROID_APK) as archive:
        ANDROID_SWF.write_bytes(archive.read("assets/worldflipper_android_release.swf"))
    assert sha(ANDROID_SWF) == "c5d04f4ca144fcdb17f1d64eeddcaef8d1c639fee7a2b59128422f8118c13802"

    full = prep.abcfmt.ABC(BASE_FULL.read_bytes())
    assert len(full.methods) == OLD_METHODS
    target = prep.View(types.SimpleNamespace(abc=full), prep.asm)
    source = prep.View(prep.SwfAbc(ANDROID_SWF), prep.asm)
    target_body_index, = target.by_label[LABEL]
    source_body_index, = source.by_label[LABEL]
    original = copy.deepcopy(full.bodies[target_body_index])
    original_method = original[0]
    assert original_method == 85605
    source_method = source.a.bodies[source_body_index][0]
    imported = prep.Importer(target, source).body(source_body_index, original_method, scope=original[3])
    assert prep.activation_traits(target, original) == prep.activation_traits(target, imported)
    checks = prep.check_body(imported, full)
    full.bodies[target_body_index] = imported

    # Compile a duplicate method as a class trait so the AIR compiler emits a
    # native function. The linker redirects the original method slot to it.
    helper_instance, = [i for i, row in enumerate(full.instances)
                        if full.mn_name(row[0]) == "cn.mod::IndependentRushParty"]
    hook_method = len(full.methods)
    full.methods.append(copy.deepcopy(full.methods[original_method]))
    duplicate = copy.deepcopy(imported)
    duplicate[0] = hook_method
    full.bodies.append(duplicate)
    hook_trait = prep.abcfmt.Trait()
    hook_trait.name = qname(full, "cn.mod", "setEditTitleHook")
    hook_trait.kind = 1
    hook_trait.attr = 0
    hook_trait.metadata = []
    hook_trait.data = ["method", 0, hook_method]
    full.classes[helper_instance][1].append(hook_trait)

    # Existing method/pool prefixes from the previous independent release are
    # retained; only the reviewed target body and the appended hook change.
    before = prep.abcfmt.ABC(BASE_FULL.read_bytes())
    for index, body in enumerate(before.bodies):
        if index != target_body_index:
            assert prep.freeze(body) == prep.freeze(full.bodies[index]), index
    assert prep.freeze(before.methods) == prep.freeze(full.methods[:OLD_METHODS])
    for field in ("metadata", "instances", "scripts"):
        old = getattr(before, field)
        assert prep.freeze(old) == prep.freeze(getattr(full, field)[:len(old)]), field
    # The helper class is the sole pre-existing trait table intentionally
    # extended with the new compiled hook.
    for index, old_row in enumerate(before.classes):
        new_row = full.classes[index]
        if index == helper_instance:
            assert prep.freeze(old_row[0]) == prep.freeze(new_row[0])
            assert prep.freeze(old_row[1]) == prep.freeze(new_row[1][:len(old_row[1])])
        else:
            assert prep.freeze(old_row) == prep.freeze(new_row), index
    for field in ("ints", "uints", "doubles", "namespaces", "ns_sets", "multinames"):
        old = getattr(before, field)
        assert prep.freeze(old) == prep.freeze(getattr(full, field)[:len(old)]), field

    out = WORK / "formal-set-edit-full.abc"
    out.write_bytes(full.serialize())
    assert len(full.methods) == OLD_METHODS + 1
    from build_native import file_offset
    info_offset = 104549248
    runtime_address, runtime_size = struct.unpack_from("<QQ", native, info_offset + 24)
    runtime_offset = file_offset(native, runtime_address)
    runtime_sha = sha(native[runtime_offset:runtime_offset + runtime_size])
    equipment_offset, equipment_size = 64394848, 548
    equipment = native[equipment_offset:equipment_offset + equipment_size]
    (WORK / "abyss-ex-ios-equipment.bin").write_bytes(equipment)
    source = {
        "ipa": str(BASE_IPA), "ipa_sha256": sha(BASE_IPA), "size_bytes": BASE_IPA.stat().st_size,
        "native_member": "Payload/worldflipper.app/worldflipper", "native_sha256": sha(native),
        "swf_member": "Payload/worldflipper.app/worldflipper_ios_release.swf", "swf_sha256": sha(swf),
        "bundle_id": "com.kulo.wf", "version": "1.8.4", "build": "1.8.46",
        "signing": "unsigned", "build_id": "ios-184-independent-party-20260923",
    }
    port = {
        "source_ipa": source, "old_methods": OLD_METHODS, "total_methods": len(full.methods),
        "full_abc_file": out.name, "full_abc_sha256": sha(out),
        "baseline_runtime_abc_sha256": runtime_sha,
        "methods": [{"label": LABEL, "method_id": original_method, "strategy": "replace"}],
        "method_redirects": [{"original": original_method, "compiled": hook_method, "label": LABEL}],
        "class_trait_extensions": [{"class": "cn.mod::IndependentRushParty",
                                    "trait": "cn.mod::setEditTitleHook", "method_id": hook_method}],
        "equipment": {"offset": equipment_offset, "old_size": equipment_size,
                      "new_size": equipment_size, "source_sha256": sha(equipment),
                      "sha256": sha(equipment)},
    }
    (WORK / "port.json").write_text(json.dumps(port, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    report = {
        "status": "prepared_for_ios_native_link",
        "baseline_ipa": str(BASE_IPA),
        "baseline_ipa_sha256": sha(BASE_IPA),
        "baseline_full_abc": str(BASE_FULL),
        "baseline_full_abc_sha256": sha(BASE_FULL),
        "full_abc_file": out.name,
        "full_abc_sha256": sha(out),
        "old_methods": OLD_METHODS,
        "total_methods": len(full.methods),
        "source_android_swf": str(ANDROID_SWF),
        "source_android_swf_sha256": sha(ANDROID_SWF),
        "method_label": LABEL,
        "original_method_id": original_method,
        "source_method_id": source_method,
        "target_body_index": target_body_index,
        "source_body_index": source_body_index,
        "original_body_sha256": sha(bytes(original[5])),
        "imported_body_sha256": sha(bytes(imported[5])),
        "hook_method_id": hook_method,
        "hook_trait": "cn.mod::IndependentRushParty.setEditTitleHook",
        "body_checks": checks,
        "strategy": "replace original iOS placeholder body and compile duplicate hook; preserve independent-formations baseline",
    }
    (WORK / "prepare-set-edit-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
