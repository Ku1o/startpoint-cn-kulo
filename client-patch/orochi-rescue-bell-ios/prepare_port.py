"""Prepare the iOS compiler input for the rescue-bell periodic AIR cache cleanup.

Compiler input only: no IPA, linking, signing or admission material is handled
here.  The runtime change is a 600-second allow-listed purge of
``<File.cacheDirectory>/app`` and ``<File.cacheDirectory>/.AIR``.  It starts
from a native entry wrapper on
``pinball.loading.global::GlobalLoading/applyLoad`` (the accepted F1009
``native_preload_wrapper`` pattern): the wrapper calls a compiled bridge whose
four parameters mirror applyLoad's native argument registers, then continues
the original function.
"""
from __future__ import annotations
import copy
import hashlib
import json
import struct
import subprocess
import sys
import types
import zipfile
from pathlib import Path

from common import (EMBEDDED_COMPACT_BYTES, EMBEDDED_COMPACT_SHA,
                    EMBEDDED_MEMBER, EMBEDDED_OFFICIAL_SHA, FULL_ABC,
                    FULL_ABC_SHA, IPA, IPA_SHA, JAVA, NATIVE_MEMBER, NATIVE_SHA,
                    HERE, OLD_METHODS, REPO, SDK, SWF_MEMBER, SWF_SHA, WORK, dump,
                    load, sha)

sys.path[:0] = [str(REPO / "client-patch/lens0907-0908"),
                str(REPO / "client-patch/lens0907-0908/vendor/abcasm")]
import build_swf as p  # type: ignore

sc = load("task_sc_swf", REPO / "client-patch/startup-cache/build_swf.py")
abcfmt = p.abcfmt

HELPER = "cn.mod::AuthorState"
APPLY_LOAD = "pinball.loading.global::GlobalLoading/applyLoad|1"
APPLY_LOAD_MID = 41998
INFO_OFFSET = 104549248
NEW_METHODS = ("ensurePeriodicCacheCleanup", "periodicCacheTick",
               "purgePeriodicCache", "writePeriodicCacheDiag",
               "ensurePeriodicCacheCleanupBridge")
NEW_SLOTS = ("periodicStarted", "periodicTimer")


def view(abc):
    return p.View(types.SimpleNamespace(abc=abc), p.asm)


def class_index(abc, name):
    return next(i for i, row in enumerate(abc.instances) if abc.mn_name(row[0]) == name)


def trait_by_name(abc, traits, name, kind=None):
    matches = [t for t in traits
               if abc.mn_name(t.name).rsplit("::", 1)[-1] == name
               and (kind is None or t.kind == kind)]
    if len(matches) != 1:
        raise AssertionError(("trait", name, len(matches)))
    return matches[0]


def compile_state_helper(work):
    swc = work / "author-state.swc"
    command = [str(JAVA), "-Dflexlib=" + str(SDK / "frameworks"), "-Xmx512m",
               "-jar", str(SDK / "lib/compc-cli.jar"), "+configname=air",
               "-swf-version=44", "-target-player=32.0", "-debug=false",
               "-compiler.source-path=" + str(HERE / "src"),
               "-include-classes=cn.mod.AuthorState", "-output=" + str(swc)]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=180)
    (work / "compile-state.log").write_bytes(result.stdout)
    if result.returncode != 0:
        raise AssertionError("AuthorState compiler failed; inspect compile-state.log")
    return swc


def main():
    if sha(IPA.read_bytes()) != IPA_SHA:
        raise AssertionError("accepted iOS IPA hash changed")
    full_bytes = FULL_ABC.read_bytes()
    if sha(full_bytes) != FULL_ABC_SHA:
        raise AssertionError("accepted iOS full ABC hash changed")
    with zipfile.ZipFile(IPA) as archive:
        native = archive.read(NATIVE_MEMBER)
        swf = archive.read(SWF_MEMBER)
        official_payload = archive.read(EMBEDDED_MEMBER)
    if sha(native) != NATIVE_SHA or sha(swf) != SWF_SHA:
        raise AssertionError("accepted iOS member hash changed")
    if sha(official_payload) != EMBEDDED_OFFICIAL_SHA:
        raise AssertionError("accepted iOS embedded payload hash changed")
    (WORK / "baseline-native").write_bytes(native)
    (WORK / "baseline.swf").write_bytes(swf)

    sys.path.insert(0, str(REPO / "client-patch/ios-cumulative-login"))
    import build_native as bn  # type: ignore
    abc_va = struct.unpack_from("<Q", native, INFO_OFFSET + 24)[0]
    abc_len = struct.unpack_from("<Q", native, INFO_OFFSET + 32)[0]
    runtime_abc = native[bn.file_offset(native, abc_va):bn.file_offset(native, abc_va) + abc_len]
    if struct.unpack_from("<Q", native, INFO_OFFSET + 56)[0] != OLD_METHODS:
        raise AssertionError("accepted iOS method count changed")
    active_va = struct.unpack_from("<Q", native, INFO_OFFSET + 48)[0]
    active_off = bn.file_offset(native, active_va, (APPLY_LOAD_MID + 1) * 8)
    apply_load_entry = struct.unpack_from("<Q", native, active_off + APPLY_LOAD_MID * 8)[0]
    entry_off = bn.file_offset(native, apply_load_entry, 4)
    displaced = native[entry_off:entry_off + 4]

    target = view(abcfmt.ABC(full_bytes))
    a = target.a
    before = copy.deepcopy(a)
    if len(a.methods) != OLD_METHODS:
        raise AssertionError(("unexpected accepted iOS method count", len(a.methods)))
    helper_i = class_index(a, HELPER)
    helper_traits = a.classes[helper_i][1]
    helper_traits_before = copy.deepcopy(helper_traits)
    apply_load_body, = target.by_label[APPLY_LOAD]
    apply_load_mid = a.bodies[apply_load_body][0]
    if apply_load_mid != APPLY_LOAD_MID:
        raise AssertionError(("applyLoad method id changed", apply_load_mid))

    swc = compile_state_helper(WORK)
    source = view(sc.helper_abc(swc))
    source_i = class_index(source.a, HELPER)
    source_traits = list(source.a.instances[source_i][6]) + list(source.a.classes[source_i][1])
    importer = p.Importer(target, source)
    compiled = {}
    for name in NEW_METHODS:
        trait = trait_by_name(source.a, source_traits, name, kind=1)
        source_mid = trait.data[2]
        source_bi, = [i for i, b in enumerate(source.a.bodies) if b[0] == source_mid]
        target_mid = len(a.methods)
        importer.methods[source_mid] = target_mid
        a.methods.append(importer.info(source_mid))
        body = importer.body(source_bi, target_mid)
        p.check_body(body, a)
        a.bodies.append(body)
        helper_traits.append(importer.trait(trait))
        compiled[name] = target_mid
    for name in NEW_SLOTS:
        trait = trait_by_name(source.a, source_traits, name, kind=0)
        helper_traits.append(importer.trait(trait))
    bridge_mid = compiled["ensurePeriodicCacheCleanupBridge"]
    bridge_info = a.methods[bridge_mid]
    if len(bridge_info[1]) != 4:
        raise AssertionError(("bridge parameter count", bridge_info))
    for type_mn in bridge_info[1]:
        if a.mn_name(type_mn) in ("Number", "Number?", "double"):
            raise AssertionError("bridge parameter must stay in integer registers")

    for pool in ("ints", "uints", "doubles", "strings", "namespaces", "ns_sets", "multinames"):
        old = getattr(before, pool)
        if p.freeze(old) != p.freeze(getattr(a, pool)[:len(old)]):
            raise AssertionError(("pool prefix changed", pool))
    if p.freeze(before.methods) != p.freeze(a.methods[:len(before.methods)]):
        raise AssertionError("old method_info prefix changed")
    for field in ("metadata", "scripts"):
        old = getattr(before, field)
        if p.freeze(old) != p.freeze(getattr(a, field)[:len(old)]):
            raise AssertionError(("prefix changed", field))
    for ci, old_class in enumerate(before.classes):
        new_class = a.classes[ci]
        if ci == helper_i:
            if p.freeze(old_class[0]) != p.freeze(new_class[0]):
                raise AssertionError("AuthorState class ctor changed")
            if p.freeze(old_class[1]) != p.freeze(new_class[1][:len(old_class[1])]):
                raise AssertionError("AuthorState class traits prefix changed")
        elif p.freeze(old_class) != p.freeze(new_class):
            raise AssertionError(("unrelated class changed", ci))
    for i, old in enumerate(before.instances):
        new = a.instances[i]
        if p.freeze(old[:-1]) != p.freeze(new[:-1]):
            raise AssertionError(("instance header changed", i))
        if p.freeze(old[-1]) != p.freeze(new[-1][:len(old[-1])]):
            raise AssertionError(("instance traits changed", i))
    actual_changed = {i for i, (x, y) in enumerate(zip(before.bodies, a.bodies))
                      if p.freeze(x) != p.freeze(y)}
    if actual_changed:
        raise AssertionError(("existing bodies must stay untouched", sorted(actual_changed)))
    if len(a.methods) != OLD_METHODS + len(NEW_METHODS):
        raise AssertionError("unexpected new method count")

    full = a.serialize()
    if abcfmt.ABC(full).serialize() != full:
        raise AssertionError("full ABC roundtrip failed")
    out_full = WORK / "cache-ios-full.abc"
    out_full.write_bytes(full)

    layout_builder = load(
        "embedded_layout_builder",
        REPO / "client-patch/orochi-rescue-bell-superplus/build_embedded_layout.py")
    payload, layout = layout_builder.compact_payload(official_payload)
    if len(payload) != EMBEDDED_COMPACT_BYTES or sha(payload) != EMBEDDED_COMPACT_SHA:
        raise AssertionError("compact payload identity changed")
    (WORK / "superplus-compact.payload").write_bytes(payload)

    port = {
        "source_ipa": {
            "ipa": str(IPA), "ipa_sha256": IPA_SHA,
            "native_member": NATIVE_MEMBER, "native_sha256": NATIVE_SHA,
            "swf_member": SWF_MEMBER, "swf_sha256": SWF_SHA,
            "build_id": "ios-184-author-1047-public-20261001",
            "signing": "unsigned", "bundle_id": "com.kulo.wf",
            "version": "1.8.4", "build": "1.8.46",
        },
        "old_methods": len(before.methods), "total_methods": len(a.methods),
        "baseline_runtime_abc_sha256": sha(runtime_abc),
        "full_abc_file": out_full.name, "full_abc_sha256": sha(full),
        "full_abc_sha1": hashlib.sha1(full).hexdigest(),
        "methods": [],
        "method_redirects": [],
        "compiled_helpers": [],
        "native_aliases": [],
        "added_methods": {name: mid for name, mid in compiled.items()},
        "hook_method": None,
        "helper_class": HELPER,
        "new_traits": len(helper_traits) - len(helper_traits_before),
        "period_ms": 600000,
        "periodic_targets": ["<File.cacheDirectory>/app", "<File.cacheDirectory>/.AIR"],
        "diagnostic_file": "<File.cacheDirectory>/sp-cache-periodic.diag",
        "native_start_wrapper": {
            "label": APPLY_LOAD, "method": APPLY_LOAD_MID,
            "bridge_method": bridge_mid, "bridge_params": 4,
            "original_entry": apply_load_entry,
            "displaced_instruction": displaced.hex(),
            "env_register": "x5",
        },
        "embedded_payload": {
            "member": ("Payload/worldflipper.app/asset/production/ios_bundle/dc/"
                       "bcccb129122c0189c8eab004ecc4516a077f3e"),
            "before_sha256": "bf37fe2fa8b7f25b2924bed0093f8f2b53970dd62162532099d04d3aa01885cc",
            "after_sha256": sha(payload), "after_bytes": len(payload),
            "file": "superplus-compact.payload", "layout": layout,
        },
        "inaho_helper": "unchanged: accepted iOS preload already adds all six "
                        "layouts unconditionally (superset of Android v3 guard)",
        "ipa_built": False, "linked": False, "device_tested": False,
    }
    dump(WORK / "port.json", port)
    print(json.dumps({k: port[k] for k in ("old_methods", "total_methods",
                                           "full_abc_sha256", "full_abc_sha1",
                                           "added_methods", "native_start_wrapper",
                                           "new_traits")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
