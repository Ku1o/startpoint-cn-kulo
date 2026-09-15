"""Package the fixed party cache over the R8 LAN diagnostic APK.

This variant intentionally keeps the R8 LoadingTrace ABC and native helper so
the title screen remains a measurement build for the internal MuMu test.
"""
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


b = module("party_cache_r8_build", HERE.parent / "startup-cache/build.py")
patch = module("party_cache_r8_patch", HERE / "patch_swf.py")

CERT = "569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894"
SIGNATURES = {"META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}
# The R8 package already replaced its manifest UUID once; classes.dex remains
# the original diagnostic native payload and is intentionally preserved.
OLD_UUID = "b5bfd7b5-3e3b-4892-ae70-802d19db7511"


def main(args: argparse.Namespace) -> None:
    source = args.source.resolve()
    swf = args.swf.resolve()
    work = args.work.resolve()
    out = args.out.resolve()
    assert source.is_file() and swf.is_file()
    assert not work.exists() and not out.exists()
    assert ".cdn" not in work.parts and ".cdn" not in out.parts
    swf_report_path = swf.with_suffix(".json")
    swf_report = json.loads(swf_report_path.read_text("utf-8"))
    assert b.sha(swf.read_bytes()) == swf_report["output_swf_sha256"]
    assert swf_report["input_swf_sha256"] == "c5a40aea2ccb8e352e7893e027b955679955a65ecf40562400ab826bd5bea865"
    assert swf_report["changed_original_bodies"] == [20565]

    work.mkdir(parents=True)
    out.mkdir(parents=True)
    uid = str(uuid.uuid4())
    with zipfile.ZipFile(source) as src:
        manifest = src.read("AndroidManifest.xml")
        assert manifest.count(OLD_UUID.encode("utf-16le")) == 1
        final_manifest = manifest.replace(OLD_UUID.encode("utf-16le"), uid.encode("utf-16le"))
        payloads = {
            "AndroidManifest.xml": final_manifest,
            "assets/worldflipper_android_release.swf": swf.read_bytes(),
        }
        source_sha = b.sha(source.read_bytes())
        (work / "source-identity.json").write_text(
            json.dumps({"source_apk_sha256": source_sha, "old_uuid": OLD_UUID}, indent=2) + "\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(work / "unsigned.apk", "w") as dest:
            for item in src.infolist():
                if item.filename not in SIGNATURES:
                    dest.writestr(item, payloads.get(item.filename, src.read(item.filename)))

    align = Path("F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe")
    b.run([align, "-p", "4", work / "unsigned.apk", work / "aligned.apk"], work, "align")
    apk = out / "StarPoint-CN-1.8.1-party-cache-r9-lan-diagnostic-test-20260914.apk"
    b.run([
        "powershell", "-NoProfile", "-NonInteractive", "-File",
        HERE.parent / "lens0907-0908/sign_apk.ps1",
        "-InputApk", work / "aligned.apk", "-OutputApk", apk,
        "-ApkSigner", b.ALIB / "apksigner.jar", "-Java", b.JAVA,
    ], work, "sign")
    signature = b.run([b.JAVA, "-jar", b.ALIB / "apksigner.jar", "verify", "--verbose", "--print-certs", apk], work, "verify-signature")
    assert CERT in signature.lower()
    assert all("Verified using " + scheme + ": true" in signature for scheme in ("v1 scheme (JAR signing)", "v2 scheme (APK Signature Scheme v2)"))
    b.run([align, "-c", "-p", "4", apk], work, "verify-alignment")

    with zipfile.ZipFile(source) as src, zipfile.ZipFile(apk) as dest:
        members = set(src.namelist()) - SIGNATURES
        assert members == set(dest.namelist()) - SIGNATURES
        for name in members:
            assert dest.read(name) == payloads.get(name, src.read(name)), name
        assert dest.testzip() is None
        assert dest.read("AndroidManifest.xml").count(uid.encode("utf-16le")) == 1

    _, _, tags = patch.s.parts(swf)
    names = [row[2][4:-1] for row in tags if row[0] == 82]
    assert b"cn.diagnostics.LoadingTrace" in names
    report = {
        "variant": "lan-diagnostic",
        "apk": str(apk),
        "apk_sha256": b.sha(apk.read_bytes()),
        "size_bytes": apk.stat().st_size,
        "source_apk_sha256": source_sha,
        "source_r8_swf_sha256": swf_report["input_swf_sha256"],
        "swf_sha256": swf_report["output_swf_sha256"],
        "endpoint": "source APK endpoint (unchanged)",
        "uniqueappversionid": uid,
        "diagnostic_helpers_preserved": True,
        "title_diagnostic": "R8 LoadingTrace preserved",
        "party_cache": swf_report,
        "changed_apk_members": ["assets/worldflipper_android_release.swf", "AndroidManifest.xml"],
        "all_other_apk_members_unchanged": True,
        "signer_sha256": CERT,
        "zipalign": True,
        "v1_v2_signatures": True,
        "device_tested_at_build": False,
        "registry_promoted": False,
        "server_synced_or_restarted": False,
    }
    (out / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "SHA256.txt").write_text(report["apk_sha256"] + "  " + apk.name + "\n", encoding="ascii")
    for name in ("unsigned.apk", "aligned.apk"):
        (work / name).unlink()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--swf", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
