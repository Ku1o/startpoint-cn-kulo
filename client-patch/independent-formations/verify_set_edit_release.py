"""Offline acceptance checks for the public SET editor C8601 client pair."""
from __future__ import annotations

import hashlib
import json
import plistlib
import re
import struct
import sys
import types
import zipfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "client-patch/ios-cumulative-login"),
                str(ROOT / "client-patch/abyss-ex")]
from set_edit_common import s  # noqa: E402
import build_native as link  # noqa: E402
from macho_signing_layout import assert_signable_layout, linkedit_ranges  # noqa: E402
from public_endpoint import require_public_endpoint  # noqa: E402
from test_signing_layout import replace_signature_tail  # noqa: E402

ANDROID = Path(r"F:\codex\outputs\set-edit-c8601-public-20260924\StarPoint-CN-1.8.1-independent-formations-set-edit-c8601-public-20260924-0fcf027e.apk")
ANDROID_SOURCE = Path(r"F:\codex\outputs\set-edit-c8601-default-title-safe-lan-20260924\StarPoint-CN-1.8.1-independent-formations-set-edit-c8601-default-title-safe-lan-20260924-da77d80a.apk")
IOS = Path(r"F:\codex\outputs\set-edit-c8601-ios-public-20260924\StarPoint-iOS-1.8.4-independent-formations-set-edit-c8601-public-20260924-unsigned.ipa")
IOS_SOURCE = Path(r"F:\codex\outputs\abyss-ex-independent-formations-20260923\StarPoint-iOS-1.8.4-independent-formations-public-20260923-unsigned.ipa")
FULL = IOS.parent / "formal-set-edit-full.abc"
OUTPUT = Path(r"F:\codex\outputs\set-edit-c8601-ios-public-20260924\release-verification.json")
SET_LABEL = "pinball.scene.partyGroupEdit::PartyGroupEditSceneView/refreshPartyCategory|1"
ANDROID_SWF_MEMBER = "assets/worldflipper_android_release.swf"
IOS_NATIVE_MEMBER = "Payload/worldflipper.app/worldflipper"
IOS_SWF_MEMBER = "Payload/worldflipper.app/worldflipper_ios_release.swf"
EXPECTED_ANDROID_SHA = "f24f469c1be0cb3d2d16520a739ace52b58055ce65621f5243404026beba6066"
EXPECTED_IOS_SHA = "64edf9ada1c0cb1dd8ebff00978394907b93174b519f0106fd41b55f2949917a"
EXPECTED_FULL_SHA = "79dcca2a2936e8d0476bf42d701d4e0e6b10b206b18230909a7fec228561a10c"


def sha(data_or_path):
    data = data_or_path if isinstance(data_or_path, (bytes, bytearray)) else Path(data_or_path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def abcs_from_swf(path: Path):
    tags = s.parts(path)[2]
    return tags, [(i, tag[2][4:-1], tag[3]) for i, tag in enumerate(tags) if tag[0] == 82]


def set_body(abc):
    view = s.m.View(types.SimpleNamespace(abc=abc), s.m.asm)
    body_index, = view.by_label[SET_LABEL]
    return abc.bodies[body_index], view.normalized(body_index)[0]


def check_android():
    assert sha(ANDROID) == EXPECTED_ANDROID_SHA
    with zipfile.ZipFile(ANDROID_SOURCE) as before, zipfile.ZipFile(ANDROID) as after:
        assert before.testzip() is None and after.testzip() is None
        original_names = before.namelist()
        assert original_names == after.namelist()
        changed = [name for name in original_names if before.read(name) != after.read(name)]
        assert set(changed) == {"AndroidManifest.xml", "classes.dex", ANDROID_SWF_MEMBER,
                                "META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}
        old_swf, new_swf = before.read(ANDROID_SWF_MEMBER), after.read(ANDROID_SWF_MEMBER)
        manifest = after.read("AndroidManifest.xml")
        assert manifest.count("0fcf027e-c219-4d6c-9221-7e10db70b513".encode("utf-16le")) == 1
        assert "da77d80a-5b8f-43c7-acc4-2a8dd0b21612".encode("utf-16le") not in manifest
    old_path, new_path = OUTPUT.parent / "verify-android-source.swf", OUTPUT.parent / "verify-android-public.swf"
    old_path.write_bytes(old_swf)
    new_path.write_bytes(new_swf)
    try:
        old_tags, old_abcs = abcs_from_swf(old_path)
        new_tags, new_abcs = abcs_from_swf(new_path)
        assert len(old_tags) == len(new_tags)
        assert [(i, name) for i, name, _ in old_abcs] == [(i, name) for i, name, _ in new_abcs]
        lan_hosts = {
            match.group(1)
            for _, _, abc in old_abcs for value in abc.strings
            for match in re.finditer(rb"\b(192\.168\.\d{1,3}\.\d{1,3})(?::8001)\b", value)
        }
        assert len(lan_hosts) == 1
        lan_host, = lan_hosts
        rewrites = []
        for (index, name, old), (_, _, new) in zip(old_abcs, new_abcs):
            for field in ("methods", "bodies", "instances", "classes", "scripts", "metadata",
                          "ints", "uints", "doubles", "namespaces", "ns_sets", "multinames"):
                assert s.m.freeze(getattr(old, field)) == s.m.freeze(getattr(new, field)), (index, field)
            assert len(old.strings) == len(new.strings)
            for left, right in zip(old.strings, new.strings):
                expected = left.replace(lan_host, b"175.178.160.158")
                assert right == expected, (index, name)
                if left != right:
                    rewrites.append((index, name.decode("utf8", "replace")))
        assert len(rewrites) == 9
        assert not any(lan_host in value for _, _, abc in new_abcs for value in abc.strings)
        main = next(abc for _, name, abc in new_abcs if name == b"boot_ffc6")
        body, rows = set_body(main)
        assert body[0] == 85066 and sha(bytes(body[5])) == "52fb8029eaaee239942cbfcfdd7fee9b9c51c3b35e3007e77566c36765899a3b"
        assert any(row[0] == 0x2c and row[1] == [("string", "party_group_edit_title_rush_event")] for row in rows)
        values = [v for _, _, abc in new_abcs for v in abc.strings]
        assert b"android-181-independent-party-20260923" in values
        assert b"SP-ADMISSION-1\nandroid-181-independent-party-20260923\n" in values
        return {"apk_sha256": EXPECTED_ANDROID_SHA, "source_apk_sha256": sha(ANDROID_SOURCE),
                "swf_sha256": sha(new_swf), "endpoint_pool_rewrites": len(rewrites),
                "set_method_id": body[0], "other_abc_bodies_unchanged": True,
                "admission_strings_unchanged": True, "air_uuid_changed": True,
                "changed_members": changed}
    finally:
        old_path.unlink(missing_ok=True)
        new_path.unlink(missing_ok=True)


def check_ios():
    assert sha(IOS) == EXPECTED_IOS_SHA and sha(FULL) == EXPECTED_FULL_SHA
    report = json.loads((IOS.parent / "ios-build-report.json").read_text(encoding="utf8"))
    assert report["ipa_sha256"] == EXPECTED_IOS_SHA
    assert report["source_ipa"]["ipa_sha256"] == sha(IOS_SOURCE)
    with zipfile.ZipFile(IOS_SOURCE) as before, zipfile.ZipFile(IOS) as after:
        assert before.testzip() is None and after.testzip() is None
        assert before.namelist() == after.namelist()
        changed = [name for name in before.namelist() if before.read(name) != after.read(name)]
        assert set(changed) == {IOS_NATIVE_MEMBER, IOS_SWF_MEMBER}
        native, swf = after.read(IOS_NATIVE_MEMBER), after.read(IOS_SWF_MEMBER)
        old_native, old_swf = before.read(IOS_NATIVE_MEMBER), before.read(IOS_SWF_MEMBER)
        plist = plistlib.loads(after.read("Payload/worldflipper.app/Info.plist"))
        assert (plist["CFBundleIdentifier"], plist["CFBundleShortVersionString"], plist["CFBundleVersion"]) == ("com.kulo.wf", "1.8.4", "1.8.46")
    assert sha(native) == report["native_sha256"] and sha(swf) == report["swf_sha256"]
    assert require_public_endpoint(native) == "http://175.178.160.158"
    layout = assert_signable_layout(native)
    assert layout["ldid_metadata_preserved"]
    old_digest, new_digest = old_native[104549248:104549268], native[104549248:104549268]
    assert new_digest == hashlib.sha1(FULL.read_bytes()).digest()
    plain = lambda data: data[:8] + zlib.decompress(data[8:]) if data[:3] == b"CWS" else data
    assert plain(old_swf).replace(b"\0" * 4 + old_digest, b"\0" * 4 + new_digest) == plain(swf)
    for size in (0x80000, 0x200000, 0x400000):
        signed = replace_signature_tail(native, size, use_ldid=True)
        assert_signable_layout(signed)
        for row in linkedit_ranges(native):
            at = row["offset"]
            assert signed[at:at + row["size"]] == native[at:at + row["size"]]
    full = s.m.abcfmt.ABC(FULL.read_bytes())
    body, rows = set_body(full)
    assert len(full.methods) == 101315 and body[0] == 85605 and len(body[5]) > 0
    assert any(row[0] == 0x2c and row[1] == [("string", "party_group_edit_title_rush_event")] for row in rows)
    hook_body = next(item for item in full.bodies if item[0] == 101314)
    assert hook_body[5] == body[5]
    info = 104549248
    # The linker preserves the original AOT method table. The appended
    # compiled hook is reached through the redirected original method slot.
    assert struct.unpack_from("<Q", old_native, info + 56)[0] == 101287
    assert struct.unpack_from("<Q", native, info + 56)[0] == 101287
    address, length = struct.unpack_from("<QQ", native, info + 24)
    runtime_at = link.file_offset(native, address)
    runtime = s.m.abcfmt.ABC(native[runtime_at:runtime_at + length])
    assert len(runtime.methods) == 101315
    old_address, old_length = struct.unpack_from("<QQ", old_native, info + 24)
    old_runtime_at = link.file_offset(old_native, old_address)
    old_runtime = s.m.abcfmt.ABC(old_native[old_runtime_at:old_runtime_at + old_length])
    for value in (b"ios-184-independent-party-20260923",
                  b"SP-ADMISSION-1\nios-184-independent-party-20260923\n"):
        assert value in runtime.strings and value in old_runtime.strings
    assert runtime.strings[:len(old_runtime.strings)] == old_runtime.strings
    hook, = [row for row in report["functions"] if row["method"] == 101314]
    redirect, = [row for row in report["hooks"] if row.get("compiled_method") == 101314]
    assert redirect["method"] == 85605 and redirect["target"] == hook["address"]
    assert hook["size"] > 0 and sha(native[hook["file_offset"]:hook["file_offset"] + hook["size"]]) == hook["sha256"]
    assert struct.unpack_from("<Q", native, report["old_active_table_offset"] + 85605 * 8)[0] == hook["address"]
    return {"ipa_sha256": EXPECTED_IOS_SHA, "source_ipa_sha256": sha(IOS_SOURCE),
            "native_sha256": sha(native), "swf_sha256": sha(swf),
            "full_abc_sha256": EXPECTED_FULL_SHA, "set_method_id": 85605,
            "compiled_hook_method_id": 101314, "compiled_hook_size": hook["size"],
            "preserved_aot_table_methods": 101287,
            "admission_strings_unchanged": True, "public_bootstrap_verified": True,
            "ldid_signature_models": 3, "changed_members": changed}


def main():
    result = {"status": "accepted_offline", "android": check_android(), "ios": check_ios(),
              "device_tested_by_this_check": False, "server_admission_config_changed": False,
              "save_schema_changed": False}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
