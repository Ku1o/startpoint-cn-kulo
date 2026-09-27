from __future__ import annotations

import hashlib
import json
import os
import plistlib
import struct
import sys
import types
import zipfile
import zlib
from pathlib import Path

ROOT = Path(r"F:/codex")
SOURCE = ROOT / "startpoint-cn-private-clean"
WORK = Path(os.environ.get(
    "STARPOINT_OROCHI_WORK",
    str(ROOT / "work/client-public-20260926/build/ios-boss"),
))
OUT = Path(os.environ.get(
    "STARPOINT_OROCHI_OUT",
    str(ROOT / "outputs/orochi-boss-public-20260926/ios"),
))
BASELINE = ROOT / "outputs/starpoint-cn-merge-20260925/ios/StarPoint-iOS-1.8.4-author-1047-gauge-public-20260925-unsigned.ipa"
IPA = OUT / os.environ.get(
    "STARPOINT_OROCHI_IPA_NAME",
    "StarPoint-iOS-1.8.4-author-1047-orochi-boss-public-20260926-corrected-unsigned.ipa",
)
NATIVE_MEMBER = "Payload/worldflipper.app/worldflipper"
SWF_MEMBER = "Payload/worldflipper.app/worldflipper_ios_release.swf"
INFO_OFFSET = 104549248
OLD_ID = b"ios-184-author-1043-20260924"
NEW_ID = "ios-184-author-1047-20260925"
PUBLIC_ORIGIN = "http://175.178.160.158"
SYNC_LABEL = "pinball.scene.battle.battle.boss.orochi::OrochiEx/applySynchronizeKind|1"
EXTERNAL_RESOLVER_LABEL = "pinball.common.data.battle::ZoneSourceValues/resolveOrochiExsAction|1"
BOSS_GROUP_NAME_LABEL = "pinball.common.data.battle.enemy::BossElementKindTools$/getHumanReadableName|1"

sys.path[:0] = [
    str(SOURCE / "client-patch/lens0907-0908"),
    str(SOURCE / "client-patch/lens0907-0908/vendor/abcasm"),
    str(SOURCE / "tools/lens-integration"),
    str(SOURCE / "client-patch/ios-cumulative-login"),
    str(SOURCE / "client-patch/r10-public-release"),
]
import build_native as link  # type: ignore
import build_swf as swf_tools  # type: ignore
from compare_clients import View  # type: ignore
from swfabc import abcfmt  # type: ignore
import build_lan  # type: ignore


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    port = json.loads((WORK / "port.json").read_text(encoding="utf-8"))
    report = json.loads((OUT / "ios-build-report.json").read_text(encoding="utf-8"))
    full = (WORK / port["full_abc_file"]).read_bytes()
    assert sha(full) == port["full_abc_sha256"] == report["full_abc_sha256"]
    assert hashlib.sha1(full).digest().hex() == report["full_abc_sha1"]
    # The F2007 fix emits one helper for the boss-group name resolver and one
    # layout-safe ZoneSource getter, so this build has two more AOT methods
    # than the previous ABI-only package.
    assert port["total_methods"] == 101436
    full_abc = abcfmt.ABC(full)
    full_view = View(types.SimpleNamespace(abc=full_abc), swf_tools.asm)
    required = [
        "cn.boss::BossMechanicsRuntime$/profile|1",
        "cn.boss::BossMechanicsRuntime$/accept|1",
        "cn.boss::BossMechanicsRuntime$/restore|1",
        BOSS_GROUP_NAME_LABEL,
        "pinball.online.battle.sync::EnemySynchronizeOwnerKind$/BossMechanics|1",
        "pinball.online.battle.sync::EnemySynchronizeOwnerKind$/registerBossMechanics|1",
        "pinball.scene.battle.battle.boss.orochi::OrochiEx/acceptUnifiedPhaseDamage|1",
        "pinball.scene.battle.battle.boss.orochi::OrochiEx/unifiedPhaseHealthPoint|1",
        "pinball.scene.battle.battle.boss.orochi::OrochiEx/startPhase4Reset|1",
        "pinball.scene.battle.battle.boss.orochi::OrochiEx/resolvePhase4Break|1",
        "pinball.scene.battle.battle.boss.orochi::OrochiExSource/dynamicWeakPointSource|1",
    ]
    missing = [label for label in required if label not in full_view.by_label]
    assert not missing, missing
    with zipfile.ZipFile(BASELINE) as before, zipfile.ZipFile(IPA) as after:
        assert before.testzip() is None and after.testzip() is None
        assert before.comment == after.comment
        old_members = {item.filename: before.read(item) for item in before.infolist()}
        new_members = {item.filename: after.read(item) for item in after.infolist()}
        assert set(old_members) == set(new_members)
        changed = [name for name in old_members if old_members[name] != new_members[name]]
        assert set(changed) == {NATIVE_MEMBER, SWF_MEMBER}, changed
        native = new_members[NATIVE_MEMBER]
        native_before = old_members[NATIVE_MEMBER]
        swf = new_members[SWF_MEMBER]
        plist = plistlib.loads(new_members["Payload/worldflipper.app/Info.plist"])
    assert plist["CFBundleIdentifier"] == "com.kulo.wf"
    assert plist["CFBundleShortVersionString"] == "1.8.4"
    assert plist["CFBundleVersion"] == "1.8.46"
    assert native[INFO_OFFSET:INFO_OFFSET + 20] == hashlib.sha1(full).digest()
    runtime_va, runtime_size = struct.unpack_from("<QQ", native, INFO_OFFSET + 24)
    runtime_offset = link.file_offset(native, runtime_va, runtime_size)
    runtime = native[runtime_offset:runtime_offset + runtime_size]
    assert sha(runtime) == report["runtime_abc_sha256"]
    runtime_abc = abcfmt.ABC(runtime)
    assert len(runtime_abc.methods) == 101436
    constants = build_lan.constants([[82, None, None, runtime_abc]])
    assert constants["ID"] == NEW_ID
    assert constants["ORIGIN"] == PUBLIC_ORIGIN
    assert constants["KEY"]
    assert OLD_ID not in full and OLD_ID not in runtime
    assert hashlib.sha1(full).digest() != hashlib.sha1((WORK / "baseline-runtime.abc").read_bytes()).digest()
    raw_swf = swf[:8] + zlib.decompress(swf[8:])
    assert raw_swf.count(b"\0" * 4 + hashlib.sha1(full).digest()) == 1
    assert raw_swf.count(b"\0" * 4 + native_before[INFO_OFFSET:INFO_OFFSET + 20]) == 0
    assert report["ipa_sha256"] == sha(IPA.read_bytes())
    assert report["native_sha256"] == sha(native)
    assert report["swf_sha256"] == sha(swf)
    assert report["origin"] == PUBLIC_ORIGIN
    assert report["total_methods"] == len(full_abc.methods) == len(runtime_abc.methods)
    assert report["new_methods"] == 49
    expected_layout_classes = {
        "pinball.scene.battle.battle.boss.orochi::OrochiEx",
        "pinball.scene.battle.battle.boss.orochi::OrochiExSource",
        "pinball.master.generated::OrochiExValues",
    }
    assert set(report["layout_relinked_classes"]) == expected_layout_classes
    layout_methods = set(report["layout_relinked_methods"])
    compiled_methods = {row["method"] for row in report["functions"]}
    assert layout_methods <= compiled_methods
    external_labels = {
        "pinball.common.data.battle::ZoneSourceValues/resolveOrochiExsAction|1",
        "pinball.common.data.battle::ZoneSource/get_bossGroupName|1",
    }
    assert set(report["layout_relinked_external_labels"]) == external_labels
    assert len(report["layout_relinked_external_methods"]) == len(external_labels)
    assert set(report["layout_relinked_external_methods"]) <= layout_methods
    for external_label in sorted(external_labels):
        external_original = full_abc.bodies[full_view.by_label[external_label][0]][0]
        external_hook = next(
            row for row in report["hooks"]
            if row.get("method") == external_original and row.get("compiled_method") is not None
        )
        external_hook_method = int(external_hook["compiled_method"])
        assert full_abc.methods[external_hook_method][1] == full_abc.methods[external_original][1]
        assert len(full_abc.methods[external_hook_method][1]) == len(full_abc.methods[external_original][1])
        resolver_function = next(
            row for row in report["functions"] if row["method"] == external_hook_method
        )
        assert resolver_function["size"] > 0
    boss_original = full_abc.bodies[full_view.by_label[BOSS_GROUP_NAME_LABEL][0]][0]
    boss_redirect = next(
        row for row in port["method_redirects"]
        if row.get("original") == boss_original
    )
    assert boss_redirect["label"] == BOSS_GROUP_NAME_LABEL
    assert boss_redirect["strategy"] == "redirect_helper"
    boss_hook_method = int(boss_redirect["compiled"])
    assert boss_hook_method >= 101387
    assert full_abc.methods[boss_hook_method][1] == full_abc.methods[boss_original][1]
    assert not any(
        row["method"] in layout_methods and row["symbol"] == "_llVerifyError"
        for row in report["relocations"]
    )
    for hook in report["hooks"]:
        compiled = hook.get("compiled_method")
        if compiled is None:
            continue
        function = next(row for row in report["functions"] if row["method"] == compiled)
        if hook.get("label") == SYNC_LABEL:
            assert report.get("sync_strategy") == "activation_free_noop_redirect"
            assert function["size"] >= 8, (compiled, function["size"])
        assert not any(
            row["method"] == compiled and row["symbol"] == "_llVerifyError"
            for row in report["relocations"]
        ), compiled
    assert report["device_tested"] is False
    # The linker already proved the loader metadata is before the signature;
    # repeat the key boundary checks on the delivered bytes.
    signing = report["signing_layout"]
    assert signing["signature_is_last"] and signing["loader_metadata_before_signature"]
    assert signing["ldid_metadata_preserved"]
    result = {
        "status": "passed",
        "ipa": str(IPA),
        "ipa_sha256": sha(IPA.read_bytes()),
        "native_sha256": sha(native),
        "swf_sha256": sha(swf),
        "full_abc_sha256": sha(full),
        "runtime_abc_sha256": sha(runtime),
        "method_count": len(full_abc.methods),
        "new_aot_methods": report["new_methods"],
        "redirected_methods": [row["method"] for row in report["hooks"]],
        "changed_members": changed,
        "admission_id": NEW_ID,
        "admission_key_sha256": sha(constants["KEY"].encode()),
        "origin": PUBLIC_ORIGIN,
        "signing_layout": signing,
        "device_tested": False,
    }
    (OUT / "boss-ios-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
