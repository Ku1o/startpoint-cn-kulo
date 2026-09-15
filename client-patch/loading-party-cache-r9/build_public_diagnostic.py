"""Package the R8 LoadingTrace party-cache candidate for the public endpoint.

The public test APK keeps the same native diagnostic activity/provider as the
MuMu package.  Only the SWF endpoint and the mandatory AIR/native identity are
changed, so users can reproduce a loading issue and share the generated ZIP
from the ``星点诊断日志`` app entry.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(value)
    return value


b = module("party_cache_public_diag_build", HERE.parent / "startup-cache/build.py")
native = module("party_cache_public_diag_native", HERE.parent / "startup-cache/verify_native.py")
endpoint = module("party_cache_public_diag_endpoint", HERE / "build_public.py")

CERT = "569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894"
SIGNATURES = {"META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}


def main(args: argparse.Namespace) -> None:
    source = args.source.resolve()
    work = args.work.resolve()
    out = args.out.resolve()
    assert source.is_file()
    assert not work.exists() and not out.exists()
    assert ".cdn" not in work.parts and ".cdn" not in out.parts
    report = json.loads((source.parent / "verification.json").read_text("utf-8"))
    assert report["variant"] == "lan-diagnostic"
    assert b.sha(source.read_bytes()) == report["apk_sha256"]
    assert report["diagnostic_helpers_preserved"] is True

    work.mkdir(parents=True)
    out.mkdir(parents=True)
    with zipfile.ZipFile(source) as src:
        base_swf = work / "input-lan-diagnostic.swf"
        base_swf.write_bytes(src.read("assets/worldflipper_android_release.swf"))
        (work / "original.dex").write_bytes(src.read("classes.dex"))

    swf = work / "public-diagnostic.swf"
    old_endpoint = report["endpoint"]
    new_endpoint = "http://175.178.160.158:8001"
    old_host = old_endpoint.split("://", 1)[1]
    new_host = new_endpoint.split("://", 1)[1]
    endpoint_report = endpoint.convert_endpoint(base_swf, swf, old_host, new_host)
    endpoint_report["old_endpoint"] = old_endpoint
    endpoint_report["new_endpoint"] = new_endpoint

    manifest_old_uid = report["uniqueappversionid"]
    uid = str(uuid.uuid4())
    (work / "uuid.txt").write_text(uid + "\n", encoding="ascii")
    run, java, libs = b.run, b.JAVA, b.ALIB
    run([java, "-jar", libs / "baksmali.jar", "d", "-o", work / "smali", work / "original.dex"], work, "dex-decode")
    original = {p.relative_to(work / "smali"): p.read_text("utf-8") for p in (work / "smali").rglob("*.smali")}
    uuid_re = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    native_uids = {value for text in original.values() for value in uuid_re.findall(text)}
    assert len(native_uids) == 1, native_uids
    native_old_uid = next(iter(native_uids))
    hits = {}
    allowed = {
        "cn/startpoint/StartupCache.smali",
        "cn/startpoint/BuildIdentity.smali",
        "cn/startpoint/diagnostics/BuildInfo.smali",
        "cn/startpoint/diagnostics/DiagnosticsActivity$6.smali",
    }
    for name, text in original.items():
        count = text.count(native_old_uid)
        if count:
            assert name.as_posix() in allowed, name
            (work / "smali" / name).write_text(text.replace(native_old_uid, uid), encoding="utf-8")
            hits[name.as_posix()] = count
    assert hits, "the diagnostic identity was not present in classes.dex"

    run([java, "-jar", libs / "smali.jar", "a", "-a", "21", "-o", work / "classes.dex", work / "smali"], work, "dex-assemble")
    run([java, "-jar", libs / "baksmali.jar", "d", "-o", work / "readback", work / "classes.dex"], work, "dex-readback")
    assert len(list((work / "readback").rglob("*.smali"))) == len(original)
    for name, text in original.items():
        restored = (work / "readback" / name).read_text("utf-8").replace(uid, native_old_uid)
        assert native.canonical(restored) == native.canonical(text), name
    dex = (work / "classes.dex").read_bytes()

    payloads = {
        "AndroidManifest.xml": None,
        "assets/worldflipper_android_release.swf": swf.read_bytes(),
        "classes.dex": dex,
    }
    with zipfile.ZipFile(source) as src:
        manifest = src.read("AndroidManifest.xml")
        assert manifest.count(manifest_old_uid.encode("utf-16le")) == 1
        payloads["AndroidManifest.xml"] = manifest.replace(manifest_old_uid.encode("utf-16le"), uid.encode("utf-16le"))
        with zipfile.ZipFile(work / "unsigned.apk", "w") as dest:
            for item in src.infolist():
                if item.filename not in SIGNATURES:
                    dest.writestr(item, payloads.get(item.filename, src.read(item.filename)))

    align = Path("F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe")
    run([align, "-p", "4", work / "unsigned.apk", work / "aligned.apk"], work, "align")
    apk = out / "StarPoint-CN-1.8.1-party-cache-r9-public-diagnostic-test-20260914.apk"
    run([
        "powershell", "-NoProfile", "-NonInteractive", "-File", HERE.parent / "lens0907-0908/sign_apk.ps1",
        "-InputApk", work / "aligned.apk", "-OutputApk", apk, "-ApkSigner", libs / "apksigner.jar", "-Java", java,
    ], work, "sign")
    signature = run([java, "-jar", libs / "apksigner.jar", "verify", "--verbose", "--print-certs", apk], work, "verify-signature")
    assert CERT in signature.lower()
    assert all("Verified using " + scheme + ": true" in signature for scheme in ("v1 scheme (JAR signing)", "v2 scheme (APK Signature Scheme v2)"))
    run([align, "-c", "-p", "4", apk], work, "verify-alignment")

    with zipfile.ZipFile(source) as src, zipfile.ZipFile(apk) as dest:
        members = set(src.namelist()) - SIGNATURES
        assert members == set(dest.namelist()) - SIGNATURES
        for name in members:
            assert dest.read(name) == payloads.get(name, src.read(name)), name
        assert dest.testzip() is None
        final_manifest = dest.read("AndroidManifest.xml")
        assert final_manifest.count(uid.encode("utf-16le")) == 1
        assert manifest_old_uid.encode("utf-16le") not in final_manifest
        assert b.sha(dest.read("assets/worldflipper_android_release.swf")) == endpoint_report["output_swf_sha256"]

    _, _, tags = endpoint.s.parts(swf)
    names = [row[2][4:-1] for row in tags if row[0] == 82]
    assert b"cn.diagnostics.LoadingTrace" in names
    result = {
        "variant": "public-diagnostic",
        "apk": str(apk),
        "apk_sha256": b.sha(apk.read_bytes()),
        "size_bytes": apk.stat().st_size,
        "source_apk_sha256": report["apk_sha256"],
        "source_swf_sha256": report["swf_sha256"],
        "swf_sha256": endpoint_report["output_swf_sha256"],
        "endpoint": new_endpoint,
        "endpoint_conversion": endpoint_report,
        "uniqueappversionid": uid,
        "native_identity_sites": hits,
        "diagnostic_helpers_preserved": True,
        "title_diagnostic": "R8 LoadingTrace preserved",
        "native_export": "DiagnosticsActivity share/save/copy entry preserved",
        "changed_apk_members": ["assets/worldflipper_android_release.swf", "classes.dex", "AndroidManifest.xml"],
        "all_other_apk_members_unchanged": True,
        "signer_sha256": CERT,
        "zipalign": True,
        "v1_v2_signatures": True,
        "device_tested_public_apk": False,
        "registry_promoted": False,
        "server_synced_or_restarted": False,
        "persistence_impact": "No saved IDs, schema, progress or import/export changes; client-side diagnostics and preparation cache only.",
    }
    (out / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "SHA256.txt").write_text(result["apk_sha256"] + "  " + apk.name + "\n", encoding="ascii")
    for name in ("unsigned.apk", "aligned.apk"):
        (work / name).unlink()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
