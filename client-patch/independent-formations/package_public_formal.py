"""Package the cumulative independent-formations SWF over the accepted public APK."""
import json, shutil, uuid, zipfile
from pathlib import Path

ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
WORK = Path(r"F:\codex\work\formal-client-20260923")
OUT = Path(r"F:\codex\outputs\independent-formations-public-20260923")
SOURCE_APK = Path(r"F:\codex\outputs\abyss-ex-admission-fix-20260918\StarPoint-CN-1.8.1-abyss-ex-admission-fix-20260918.apk")
SOURCE_APK_SHA = "86bfa97f6f8479ddeda7084e08fc9144e10caaf2aaa2cbe01ad5a27fbbdd3a71"
BUILD_ID = "android-181-independent-party-20260923"
SWF_MEMBER = "assets/worldflipper_android_release.swf"
SIGNATURE_MEMBERS = {"META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}
EXPECTED_SIGNER = "569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894"
JAVA = Path(r"D:\java\bin\java.exe")
SDK = Path(r"F:\codex\ios-rush-leaderboard-port-20260830\AIRSDK_51.2.1.5")
BT = Path(r"F:\StartPointCN\wf_full_patch\build-tools")


def sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def run(command, label):
    import subprocess
    p = subprocess.run([str(x) for x in command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    (WORK / (label + ".log")).write_bytes(p.stdout)
    if p.returncode:
        raise RuntimeError(label + ": " + p.stdout.decode("utf8", "replace")[-5000:])
    return p.stdout.decode("utf8", "replace")


def main():
    assert sha(SOURCE_APK.read_bytes()) == SOURCE_APK_SHA
    swf = WORK / "independent-formations.swf"
    swf_report = json.loads((WORK / "swf-report.json").read_text(encoding="utf8"))
    assert sha(swf.read_bytes()) == swf_report["output_swf_sha256"]
    with zipfile.ZipFile(SOURCE_APK) as src:
        original_swf = src.read(SWF_MEMBER)
        manifest = src.read("AndroidManifest.xml")
        original_dex = src.read("classes.dex")
        original_uuid = json.loads((ROOT / "client-patch" / "android-accepted.json").read_text(encoding="utf8"))["variants"]["public"]["uniqueappversionid"]
        assert sha(original_swf) == "8b564f3f54c46fcc023622783b33feca0992f188d1092428dcd9ff795ebc9aaa"
        assert manifest.count(original_uuid.encode("utf-16le")) == 1
        uid = str(uuid.uuid4())
        smali = WORK / ("smali-formal-" + uid)
        back = WORK / ("smali-formal-readback-" + uid)
        libs = SDK / "lib/android/lib"
        (WORK / "formal-original.dex").write_bytes(original_dex)
        run([JAVA, "-jar", libs / "baksmali.jar", "d", "-o", smali, WORK / "formal-original.dex"], "formal-dex-decode")
        originals = {p.relative_to(smali): p.read_text(encoding="utf8") for p in smali.rglob("*.smali")}
        hits = {}
        for name, text in originals.items():
            count = text.count(original_uuid)
            if count:
                assert name.as_posix() in ("cn/startpoint/StartupCache.smali", "cn/startpoint/BuildIdentity.smali")
                (smali / name).write_text(text.replace(original_uuid, uid), encoding="utf8")
                hits[str(name)] = count
        assert hits
        new_dex = WORK / "formal-classes.dex"
        run([JAVA, "-jar", libs / "smali.jar", "a", "-a", "21", "-o", new_dex, smali], "formal-dex-assemble")
        run([JAVA, "-jar", libs / "baksmali.jar", "d", "-o", back, new_dex], "formal-dex-readback")
        for name, text in originals.items():
            assert (back / name).read_text(encoding="utf8").replace(uid, original_uuid) == text

        payloads = {
            "AndroidManifest.xml": manifest.replace(original_uuid.encode("utf-16le"), uid.encode("utf-16le")),
            "classes.dex": new_dex.read_bytes(),
            SWF_MEMBER: swf.read_bytes(),
        }
        unsigned = WORK / ("formal-unsigned-" + uid + ".apk")
        aligned = WORK / ("formal-aligned-" + uid + ".apk")
        with zipfile.ZipFile(unsigned, "w") as dst:
            for item in src.infolist():
                if item.filename in SIGNATURE_MEMBERS:
                    continue
                dst.writestr(item, payloads.get(item.filename, src.read(item.filename)))

    run([BT / "zipalign.exe", "-p", "4", unsigned, aligned], "formal-zipalign")
    OUT.mkdir(parents=True, exist_ok=True)
    apk = OUT / ("StarPoint-CN-1.8.1-independent-formations-public-" + uid[:8] + ".apk")
    run(["powershell", "-NoProfile", "-NonInteractive", "-File",
         ROOT / "client-patch/lens0907-0908/sign_apk.ps1",
         "-InputApk", aligned, "-OutputApk", apk,
         "-ApkSigner", BT / "lib/apksigner.jar", "-Java", JAVA], "formal-sign")
    verify = run([JAVA, "-jar", BT / "lib/apksigner.jar", "verify", "--verbose", "--print-certs", apk], "formal-verify")
    assert EXPECTED_SIGNER in verify.lower()
    assert "Verified using v1 scheme (JAR signing): true" in verify
    assert "Verified using v2 scheme (APK Signature Scheme v2): true" in verify
    run([BT / "zipalign.exe", "-c", "-p", "4", apk], "formal-alignment-verify")
    with zipfile.ZipFile(SOURCE_APK) as src, zipfile.ZipFile(apk) as dst:
        assert dst.testzip() is None
        for name in set(src.namelist()) - SIGNATURE_MEMBERS:
            assert dst.read(name) == payloads.get(name, src.read(name)), name
        assert dst.read(SWF_MEMBER) == swf.read_bytes()
        new_manifest = dst.read("AndroidManifest.xml")
        assert new_manifest.count(uid.encode("utf-16le")) == 1
        assert original_uuid.encode("utf-16le") not in new_manifest
    report = {
        "status": "offline_candidate",
        "apk": str(apk),
        "apk_sha256": sha(apk.read_bytes()),
        "swf_sha256": sha(swf.read_bytes()),
        "source_apk": str(SOURCE_APK),
        "source_apk_sha256": SOURCE_APK_SHA,
        "source_swf_sha256": sha(original_swf),
        "uniqueappversionid": uid,
        "previous_uniqueappversionid": original_uuid,
        "build_id": BUILD_ID,
        "endpoint": "http://175.178.160.158:8001",
        "version_name": "1.8.1",
        "version_code": 1008001,
        "generic_damage_logger_removed": True,
        "generic_damage_log_path_absent": True,
        "swf_report": swf_report,
        "native_identity_sites": hits,
        "signer_certificate_sha256": EXPECTED_SIGNER,
        "zipalign": True,
        "v1_signature": True,
        "v2_signature": True,
        "unchanged_apk_members_verified": True,
        "device_tested": False,
        "scope": "accepted public EX APK plus generic damage entry without prototype disk logging and independent Rush party formations",
    }
    (OUT / "package-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    (WORK / "package-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    for path in (unsigned, aligned):
        if path.exists(): path.unlink()
    for path in (smali, back):
        if path.exists(): shutil.rmtree(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
