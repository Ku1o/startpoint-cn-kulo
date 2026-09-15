"""Build the LAN APK from the current accepted Android baseline."""
from __future__ import annotations

import argparse
import importlib.util
import json
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(value)
    return value


b = module("party_cache_build", HERE.parent / "startup-cache/build.py")
native = module("party_cache_native", HERE.parent / "startup-cache/verify_native.py")
checker = module("party_cache_baseline", HERE.parent / "verify_android_baseline.py")

CERT = "569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894"
SIGNATURES = {"META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}


def main(args: argparse.Namespace) -> None:
    swf = args.swf.resolve()
    report_path = swf.with_suffix(".json")
    work = args.work.resolve()
    out = args.out.resolve()
    assert swf.exists() and report_path.exists()
    assert not work.exists() and not out.exists()
    assert ".cdn" not in work.parts and ".cdn" not in out.parts
    accepted = checker.verify("lan")
    parent = Path(accepted["apk"]).resolve()
    assert b.sha(parent.read_bytes()) == accepted["apk_sha256"]
    swf_report = json.loads(report_path.read_text("utf-8"))
    assert swf_report["output_swf_sha256"] == b.sha(swf.read_bytes())
    assert swf_report["changed_original_bodies"] == [20565]
    assert swf_report["added_helper_bodies"] == 5

    work.mkdir(parents=True)
    out.mkdir(parents=True)
    uid = str(uuid.uuid4())
    (work / "uuid.txt").write_text(uid + "\n", encoding="ascii")
    with zipfile.ZipFile(parent) as source:
        (work / "original.dex").write_bytes(source.read("classes.dex"))
        base_swf = source.read("assets/worldflipper_android_release.swf")
        assert b.sha(base_swf) == accepted["swf_sha256"]

    run, java, libs = b.run, b.JAVA, b.ALIB
    run([java, "-jar", libs / "baksmali.jar", "d", "-o", work / "smali", work / "original.dex"], work, "dex-decode")
    original = {p.relative_to(work / "smali"): p.read_text("utf-8") for p in (work / "smali").rglob("*.smali")}
    hits = {}
    old_uid = accepted["uniqueappversionid"]
    for name, text in original.items():
        count = text.count(old_uid)
        if count:
            assert name.as_posix() in ("cn/startpoint/StartupCache.smali", "cn/startpoint/BuildIdentity.smali")
            (work / "smali" / name).write_text(text.replace(old_uid, uid), encoding="utf-8")
            hits[name.as_posix()] = count
    assert len(hits) == 2 and sum(hits.values()) == 2
    run([java, "-jar", libs / "smali.jar", "a", "-a", "21", "-o", work / "classes.dex", work / "smali"], work, "dex-assemble")
    run([java, "-jar", libs / "baksmali.jar", "d", "-o", work / "readback", work / "classes.dex"], work, "dex-readback")
    assert len(list((work / "readback").rglob("*.smali"))) == len(original) == 6
    for name, text in original.items():
        restored = (work / "readback" / name).read_text("utf-8").replace(uid, old_uid)
        assert native.canonical(restored) == native.canonical(text), name
    dex = (work / "classes.dex").read_bytes()
    assert old_uid.encode() not in dex and dex.count(uid.encode()) == 1

    payloads = {
        "assets/worldflipper_android_release.swf": swf.read_bytes(),
        "classes.dex": dex,
    }
    with zipfile.ZipFile(parent) as source, zipfile.ZipFile(work / "unsigned.apk", "w") as dest:
        manifest = source.read("AndroidManifest.xml")
        assert manifest.count(old_uid.encode("utf-16le")) == 1
        payloads["AndroidManifest.xml"] = manifest.replace(old_uid.encode("utf-16le"), uid.encode("utf-16le"))
        for item in source.infolist():
            if item.filename not in SIGNATURES:
                dest.writestr(item, payloads.get(item.filename, source.read(item.filename)))
    align = Path("F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe")
    run([align, "-p", "4", work / "unsigned.apk", work / "aligned.apk"], work, "align")
    apk = out / "StarPoint-CN-1.8.1-party-cache-r9-lan-test-20260914.apk"
    run([
        "powershell", "-NoProfile", "-NonInteractive", "-File", HERE.parent / "lens0907-0908/sign_apk.ps1",
        "-InputApk", work / "aligned.apk", "-OutputApk", apk, "-ApkSigner", libs / "apksigner.jar", "-Java", java,
    ], work, "sign")
    signature = run([java, "-jar", libs / "apksigner.jar", "verify", "--verbose", "--print-certs", apk], work, "verify-signature")
    assert CERT in signature.lower()
    assert all("Verified using " + scheme + ": true" in signature for scheme in ("v1 scheme (JAR signing)", "v2 scheme (APK Signature Scheme v2)"))
    run([align, "-c", "-p", "4", apk], work, "verify-alignment")
    with zipfile.ZipFile(parent) as source, zipfile.ZipFile(apk) as dest:
        members = set(source.namelist()) - SIGNATURES
        assert len(dest.namelist()) == len(set(dest.namelist()))
        assert members == set(dest.namelist()) - SIGNATURES
        for name in members:
            assert dest.read(name) == payloads.get(name, source.read(name)), name
        manifest = dest.read("AndroidManifest.xml")
        assert manifest.count(uid.encode("utf-16le")) == 1 and old_uid.encode("utf-16le") not in manifest
        assert b.sha(dest.read("assets/worldflipper_android_release.swf")) == swf_report["output_swf_sha256"]

    result = {
        "variant": "lan",
        "apk": str(apk),
        "apk_sha256": b.sha(apk.read_bytes()),
        "size_bytes": apk.stat().st_size,
        "parent_apk_sha256": accepted["apk_sha256"],
        "parent_swf_sha256": accepted["swf_sha256"],
        "endpoint": accepted["endpoint"],
        "uniqueappversionid": uid,
        "native_build_identity": uid,
        "native_identity_sites": hits,
        "native_behavior_unchanged": True,
        "signer_sha256": CERT,
        "zipalign": True,
        "v1_v2_signatures": True,
        "changed_apk_members": ["assets/worldflipper_android_release.swf", "classes.dex", "AndroidManifest.xml"],
        "all_other_apk_members_unchanged": True,
        "swf": swf_report,
        "swf_sha256": swf_report["output_swf_sha256"],
        "method_bodies_checked": 96543,
        "changed_original_methods": [20565],
        "party_cache_scope": swf_report["cache_scope"],
        "calculated_objects_reused": True,
        "device_tested_at_build": False,
        "registry_promoted": False,
        "server_synced_or_restarted": False,
        "persistence_impact": "No saved IDs, schema, progress or import/export changes; client-side preparation cache only.",
    }
    (out / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "SHA256.txt").write_text(result["apk_sha256"] + "  " + apk.name + "\n", encoding="ascii")
    for name in ("unsigned.apk", "aligned.apk"):
        (work / name).unlink()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
