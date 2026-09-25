from __future__ import annotations

import copy
import hashlib
import json
import struct
import sys
import types
import zipfile
from pathlib import Path

ROOT = Path(r"F:/codex/startpoint-cn-private-clean")
WORK = Path(r"F:/codex/work/client-public-20260926/build/ios-boss")
IOS_FULL = Path(r"F:/codex/outputs/starpoint-cn-merge-20260925/ios/author-full.abc")
IOS_IPA = Path(r"F:/codex/outputs/starpoint-cn-merge-20260925/ios/StarPoint-iOS-1.8.4-author-1047-gauge-public-20260925-unsigned.ipa")
ANDROID_SWF = Path(r"F:/codex/work/orochi-boss-v2-1047-20260925/balance-revamp-20260925/orochi-balance-ledger-f1034-fixed-v2.swf")
IOS_EXPECTED_FULL_SHA = "f4706de52e975edb42a7d25750158c2986f60508127028861214f41fef500a64"
IOS_EXPECTED_IPA_SHA = "e884eed2a859b2de0dfae40365c3aa7497ebf847f7d513db9a9545daf7f50a95"
IOS_NATIVE_MEMBER = "Payload/worldflipper.app/worldflipper"
IOS_SWF_MEMBER = "Payload/worldflipper.app/worldflipper_ios_release.swf"
IOS_INFO = 104549248
OLD_ID = "ios-184-author-1043-20260924"
NEW_ID = "ios-184-author-1047-20260925"
PAIR = Path(r"F:/codex/.codex/secrets/starpoint-client-admission/releases/orochi-boss-public-20260926/config")

sys.path[:0] = [
    str(ROOT / "client-patch/lens0907-0908"),
    str(ROOT / "client-patch/lens0907-0908/vendor/abcasm"),
    str(ROOT / "tools/lens-integration"),
    str(ROOT / "client-patch/ios-cumulative-login"),
]
import build_swf as p  # type: ignore
from compare_clients import View  # type: ignore
from swfabc import abcfmt, swftags  # type: ignore
from prepare import ClassImporter  # type: ignore

p.asm.MNEMONICS["avm_label"] = 0x09
p.asm.BY_OPCODE[0x09] = "avm_label"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def view(abc):
    return View(types.SimpleNamespace(abc=abc), p.asm)


def class_index(v, name: str) -> int:
    hits = [i for i, row in enumerate(v.a.instances) if v.a.mn_name(row[0]) == name]
    if len(hits) != 1:
        raise AssertionError((name, hits))
    return hits[0]


def trait_key(v, trait) -> tuple[int, str]:
    return trait.kind, v.a.mn_name(trait.name)


def qname(abc, namespace_name: str, value_name: str) -> int:
    """Return a QName while appending only new constant-pool entries."""
    def string_index(value: str) -> int:
        raw = value.encode("utf-8")
        for index, existing in enumerate(abc.strings):
            if existing == raw:
                return index
        abc.strings.append(raw)
        return len(abc.strings) - 1

    namespace_string = string_index(namespace_name)
    namespace = next((i for i, row in enumerate(abc.namespaces)
                      if i and row[0] == 22 and row[1] == namespace_string), None)
    if namespace is None:
        abc.namespaces.append((22, namespace_string))
        namespace = len(abc.namespaces) - 1
    name_string = string_index(value_name)
    for index, row in enumerate(abc.multinames):
        if row == (7, namespace, name_string):
            return index
    abc.multinames.append((7, namespace, name_string))
    return len(abc.multinames) - 1


def helper_abc(path: Path, class_name: str) -> bytes:
    _signature, _version, _declared, body = swftags.load_swf(str(path))
    matches = []
    needle = class_name.encode("ascii")
    for code, offset, header, length in swftags.iter_tags(body):
        if code != 82:
            continue
        raw = body[offset + header:offset + header + length]
        nul = raw.index(b"\0", 4)
        if raw[4:nul] == needle:
            matches.append(raw[nul + 1:])
    if len(matches) != 1:
        raise AssertionError((class_name, len(matches)))
    return matches[0]


def method_signature(v, mid: int):
    row = v.a.methods[mid]
    return v.mn(row[0]), tuple(v.mn(x) for x in row[1]), row[3]


def relevant(label: str) -> bool:
    # Keep the port limited to the four owners that form the Boss contract.
    # A broad ``OrochiEx`` prefix also matches OrochiExHead, trial-gauge and
    # unique-state classes; those are unchanged in the accepted iOS baseline
    # and importing them would silently widen the port.
    owners = (
        "pinball.scene.battle.battle.boss.orochi::OrochiEx",
        "pinball.scene.battle.battle.boss.orochi::OrochiExSource",
        "pinball.master.generated::OrochiExValues",
        "pinball.online.battle.sync::EnemySynchronizeOwnerKind",
    )
    for owner in owners:
        if label.startswith(owner + "/") or label.startswith(owner + "$"):
            return True
        script_owner = "script:" + owner
        if label.startswith(script_owner + "/") or label.startswith(script_owner + "$"):
            return True
    return False


def extract_native() -> tuple[bytes, bytes, int, int]:
    with zipfile.ZipFile(IOS_IPA) as archive:
        native = archive.read(IOS_NATIVE_MEMBER)
        swf = archive.read(IOS_SWF_MEMBER)
    if native[IOS_INFO:IOS_INFO + 20] != hashlib.sha1(IOS_FULL.read_bytes()).digest():
        raise AssertionError("accepted native full-ABC digest mismatch")
    va, length = struct.unpack_from("<QQ", native, IOS_INFO + 24)
    from build_native import file_offset  # type: ignore
    offset = file_offset(native, va, length)
    return native, swf, offset, length


def rotate_admission(a) -> dict:
    keys = json.loads((PAIR / "client-admission.keys.json").read_text(encoding="utf-8-sig"))
    new_key = keys[NEW_ID]
    old_id = OLD_ID.encode()
    new_id = NEW_ID.encode()
    old_key = keys[OLD_ID].encode()
    replacements = {
        old_id: new_id,
        old_key: new_key.encode(),
        (b"SP-ADMISSION-1\n" + old_id + b"\n"): (b"SP-ADMISSION-1\n" + new_id + b"\n"),
    }
    found = {x: [] for x in replacements}
    for index, value in enumerate(a.strings):
        if value in replacements:
            found[value].append(index)
            a.strings[index] = replacements[value]
    if {k: len(v) for k, v in found.items()} != {k: 1 for k in replacements}:
        raise AssertionError({k.decode("utf-8", "replace"): v for k, v in found.items()})
    if any(old in a.strings for old in (old_id, old_key)):
        raise AssertionError("old admission constants remain")
    return {"id": NEW_ID, "key_sha256": sha(new_key.encode()), "string_indexes": [found[x][0] for x in replacements]}


def main() -> None:
    if sha(IOS_FULL.read_bytes()) != IOS_EXPECTED_FULL_SHA or sha(IOS_IPA.read_bytes()) != IOS_EXPECTED_IPA_SHA:
        raise RuntimeError("accepted iOS baseline hash changed")
    if not ANDROID_SWF.is_file():
        raise FileNotFoundError(ANDROID_SWF)
    WORK.mkdir(parents=True, exist_ok=True)
    native, swf, runtime_offset, runtime_size = extract_native()
    (WORK / "baseline-native").write_bytes(native)
    (WORK / "baseline.swf").write_bytes(swf)
    (WORK / "android-boss.swf").write_bytes(ANDROID_SWF.read_bytes())
    full_before = IOS_FULL.read_bytes()
    target = view(abcfmt.ABC(full_before))
    before = copy.deepcopy(target.a)
    source = p.View(p.SwfAbc(ANDROID_SWF), p.asm)
    old_methods = len(before.methods)
    if old_methods != 101387:
        raise AssertionError(("unexpected iOS method count", old_methods))

    # The generic runtime helper is an extra DoABC in the Android source. Merge
    # it as a normal class so the iOS compiler receives the same reusable
    # BossMechanicsRuntime implementation rather than a string-only stub.
    helper_raw = helper_abc(ANDROID_SWF, "cn.boss.BossMechanicsRuntime")
    helper_view = view(abcfmt.ABC(helper_raw))
    helper_start = len(target.a.methods)
    ClassImporter(target, helper_view).merge()
    helper_record = {
        "class": "cn.boss.BossMechanicsRuntime",
        "source_sha256": sha(helper_raw),
        "first_method": helper_start,
        "methods": len(helper_view.a.methods),
        "scripts": len(helper_view.a.scripts),
    }
    target = view(target.a)
    importer = p.Importer(target, source)

    # Register every new main-ABC method before importing any body or trait;
    # several of the Boss methods call one another.
    # Android and iOS carry different platform-only classes. Restrict the
    # append set to the Boss-owned methods; unrelated Android-only closures
    # are not part of this port and remain unmapped by design.
    new_labels = sorted(
        label for label in source.by_label
        if label not in target.by_label and relevant(label)
    )
    additions = []
    for label in new_labels:
        source_body = source.a.bodies[source.by_label[label][0]]
        source_mid = source_body[0]
        target_mid = len(target.a.methods)
        importer.methods[source_mid] = target_mid
        target.a.methods.append(importer.info(source_mid))
        additions.append((label, source_mid, target_mid))

    # Append only the source traits that are absent from the accepted iOS
    # class. Existing trait prefixes and native slot order remain untouched.
    trait_additions = []
    for owner in (
        "pinball.scene.battle.battle.boss.orochi::OrochiEx",
        "pinball.scene.battle.battle.boss.orochi::OrochiExSource",
        "pinball.master.generated::OrochiExValues",
        "pinball.online.battle.sync::EnemySynchronizeOwnerKind",
    ):
        si = class_index(source, owner)
        ti = class_index(target, owner)
        for static in (False, True):
            source_traits = source.a.classes[si][1] if static else source.a.instances[si][6]
            target_traits = target.a.classes[ti][1] if static else target.a.instances[ti][6]
            existing = {trait_key(target, t) for t in target_traits}
            for old_trait in source_traits:
                key = trait_key(source, old_trait)
                if key in existing:
                    continue
                target_traits.append(importer.trait(old_trait))
                existing.add(key)
                trait_additions.append({"owner": owner, "static": static, "kind": key[0], "name": key[1]})

    target = view(target.a)
    changed_labels = sorted(label for label in source.by_label if label in target.by_label and relevant(label))
    # Import all relevant Boss method bodies from the reviewed Android carrier.
    # This includes the state machine, native sync enum, generated values and
    # script initializers that install the appended fields.
    replacements = []
    redirects = []
    changed_ids = set()
    for label in changed_labels:
        source_body_index = source.by_label[label][0]
        target_body_index = target.by_label[label][0]
        source_body = source.a.bodies[source_body_index]
        old_body = copy.deepcopy(before.bodies[target_body_index])
        source_sig = method_signature(source, source_body[0])
        target_sig = method_signature(target, old_body[0])
        # Haxe emits `any` for constructors and class initializers in the
        # Android carrier while the accepted iOS ABC records `void`. Keep the
        # iOS method_info/flags and require the actual argument list to match.
        if source_sig[1] != target_sig[1]:
            raise AssertionError((label, source_sig, target_sig))
        try:
            body = importer.body(source_body_index, old_body[0], scope=old_body[3])
        except AssertionError as exc:
            if "lexical scope index" not in str(exc):
                raise RuntimeError(f"failed to import {label}: {exc}") from exc
            # The Boss sync branch adds a lexical scope object. Retaining the
            # carrier's scope depth is safe for this body and avoids shifting
            # getscopeobject/getouterscope operands by guesswork.
            body = importer.body(source_body_index, old_body[0], scope=None)
        except Exception as exc:
            raise RuntimeError(f"failed to import {label}: {exc}") from exc
        p.check_body(body, target.a)
        changed_ids.add(old_body[0])
        old_activation = p.activation_traits(view(before), old_body)
        new_activation = p.activation_traits(target, body)
        if old_activation != new_activation:
            # The accepted iOS method has no activation frame, while the
            # Android implementation of applySynchronizeKind introduces one.
            # Keep the old method body and compile the imported implementation
            # as an appended hook. The linker redirects the original method
            # table entry to this hook, so no existing activation metadata or
            # native closure layout is overwritten.
            hook_mid = len(target.a.methods)
            target.a.methods.append(copy.deepcopy(target.a.methods[old_body[0]]))
            hook_body = copy.deepcopy(body)
            hook_body[0] = hook_mid
            target.a.bodies.append(hook_body)
            helper_index = class_index(target, "cn.boss::BossMechanicsRuntime")
            hook_traits = target.a.classes[helper_index][1]
            hook_name = f"bossMethod{old_body[0]}"
            hook_trait = abcfmt.Trait()
            hook_trait.name = qname(target.a, "cn.boss", hook_name)
            hook_trait.kind = 1
            hook_trait.attr = 0
            hook_trait.metadata = []
            hook_trait.data = ["method", 0, hook_mid]
            hook_traits.append(hook_trait)
            trait_additions.append({
                "owner": "cn.boss.BossMechanicsRuntime",
                "static": True,
                "kind": 1,
                "name": hook_name,
            })
            redirects.append({
                "original": old_body[0],
                "compiled": hook_mid,
                "label": label,
                "strategy": "redirect",
            })
            replacements.append({
                "label": label,
                "method_id": old_body[0],
                "compiled_method": hook_mid,
                "target_body": target_body_index,
                "source_body": source_body_index,
                "strategy": "redirect",
                "source_code_sha256": sha(source_body[5]),
                "target_code_sha256": sha(hook_body[5]),
            })
        else:
            target.a.bodies[target_body_index] = body
            replacements.append({
                "label": label,
                "method_id": old_body[0],
                "target_body": target_body_index,
                "source_body": source_body_index,
                "strategy": "replace",
                "source_code_sha256": sha(source_body[5]),
                "target_code_sha256": sha(body[5]),
            })

    # Add bodies for the newly registered main-ABC methods.
    for label, source_mid, target_mid in additions:
        source_body_index = source.by_label[label][0]
        body = importer.body(source_body_index, target_mid)
        p.check_body(body, target.a)
        target.a.bodies.append(body)
        replacements.append({
            "label": label,
            "method_id": target_mid,
            "source_body": source_body_index,
            "strategy": "new_method",
            "source_code_sha256": sha(source.a.bodies[source_body_index][5]),
            "target_code_sha256": sha(body[5]),
        })

    admission = rotate_admission(target.a)
    full_after = target.a.serialize()
    if abcfmt.ABC(full_after).serialize() != full_after:
        raise AssertionError("Boss full ABC roundtrip failed")
    (WORK / "boss-full.abc").write_bytes(full_after)
    runtime_before = native[runtime_offset:runtime_offset + runtime_size]
    # The runtime ABC is the stripped/full compiler image. Its admission pool
    # is rotated by the native linker after compiling the new full ABC.
    (WORK / "baseline-runtime.abc").write_bytes(runtime_before)
    report = {
        "status": "boss_ios_full_abc_prepared",
        "source_ipa": {
            "ipa": str(IOS_IPA),
            "ipa_sha256": IOS_EXPECTED_IPA_SHA,
            "native_member": IOS_NATIVE_MEMBER,
            "swf_member": IOS_SWF_MEMBER,
            "native_sha256": sha(native),
            "swf_sha256": sha(swf),
            "build_id": "ios-184-author-1043-20260924",
        },
        "full_abc_file": "boss-full.abc",
        "full_abc_sha256": sha(full_after),
        "full_abc_sha1": hashlib.sha1(full_after).hexdigest(),
        "baseline_runtime_abc_sha256": sha(runtime_before),
        "old_methods": old_methods,
        "total_methods": len(target.a.methods),
        "helper": helper_record,
        "methods": replacements,
        "native_aliases": [],
        "method_redirects": redirects,
        "trait_additions": trait_additions,
        "main_new_method_count": len(additions),
        "replaced_method_count": len([r for r in replacements if r["strategy"] == "replace"]),
        "redirected_method_count": len(redirects),
        "runtime_offset": runtime_offset,
        "runtime_size": runtime_size,
        "admission": admission,
        "android_source_swf_sha256": sha(ANDROID_SWF.read_bytes()),
        "device_tested": False,
        "save_schema_changed": False,
    }
    (WORK / "port.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "old_methods", "total_methods", "main_new_method_count", "replaced_method_count", "full_abc_sha256", "helper")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
