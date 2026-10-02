#!/usr/bin/env python3
"""Add the audited ten-minute AIR-cache cleaner to an accepted Android APK.

The input APK must already contain the StartupCache hooks.  This builder
replaces only the StartupCache helper classes and the AIR cache UUID, then
verifies that the SWF and every non-target APK member are preserved.  It never
touches downloaded CDN assets.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "native" / "cn" / "startpoint" / "StartupCache.java"
BASE_UUID = "5a18e114-3549-4e26-bf34-e9616562d08a"
BASE_APK_SHA256 = "5505e73fbe770ca3c81e638e6e97b103b9bb997c95b6bc63d2b277323d8e6884"
BASE_SWF_SHA256 = "9418137820c007b52a11ad0d7955c102795d8dd903213670577bf3407ed709f7"
SIGNATURE_MEMBERS = {"META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}
TARGET_CLASSES = {
    "cn/startpoint/StartupCache.smali",
    "cn/startpoint/StartupCache$Periodic.smali",
    "cn/startpoint/BuildIdentity.smali",
}
STUBS = {
    "android/content/pm/ApplicationInfo.java": (
        "package android.content.pm; "
        "public class ApplicationInfo { public String packageName,dataDir,sourceDir; public int uid; }"
    ),
    "android/os/Process.java": (
        "package android.os; public class Process { public static int myUid(){return 0;} }"
    ),
    "android/util/Log.java": (
        "package android.util; public class Log { "
        "public static int i(String t,String m){return 0;} "
        "public static int w(String t,String m){return 0;} }"
    ),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(command: list[object], work: Path, label: str, timeout: int = 600) -> str:
    result = subprocess.run(
        [str(item) for item in command],
        cwd=work,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    output = result.stdout.decode("utf-8", "replace")
    (work / f"{label}.log").write_text(output, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{label} failed:\n{output[-6000:]}")
    return output


def javac_for(java: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if java.name.lower() in {"java.exe", "java"} and java.parent != Path("."):
        return java.with_name("javac.exe")
    return Path("javac")


def compile_helper(args: argparse.Namespace, work: Path, new_uuid: str) -> Path:
    stubs = work / "stubs"
    for relative, content in STUBS.items():
        path = stubs / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    identity = work / "generated" / "cn" / "startpoint" / "BuildIdentity.java"
    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text(
        "package cn.startpoint; final class BuildIdentity { "
        f'static final String ID="{new_uuid}"; }}\n',
        encoding="utf-8",
    )
    classes = work / "javaclasses"
    classes.mkdir()
    run(
        [
            javac_for(args.java, args.javac),
            "--release",
            "8",
            "-d",
            classes,
            *sorted(stubs.rglob("*.java")),
            identity,
            SOURCE,
        ],
        work,
        "javac",
    )
    jar_path = work / "startup-cache.jar"
    with zipfile.ZipFile(jar_path, "w") as jar:
        for file in sorted((classes / "cn").rglob("*.class")):
            jar.write(file, file.relative_to(classes).as_posix())
    helper_dex = work / "helper-dex"
    helper_dex.mkdir()
    run(
        [
            args.java,
            "-cp",
            args.d8_jar,
            "com.android.tools.r8.D8",
            "--min-api",
            "21",
            "--output",
            helper_dex,
            jar_path,
        ],
        work,
        "d8",
    )
    return helper_dex / "classes.dex"


def read_smali(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*.smali")
    }


def build(args: argparse.Namespace) -> dict[str, object]:
    if not args.input_apk.is_file():
        raise FileNotFoundError(args.input_apk)
    if args.output_apk.exists():
        raise FileExistsError(args.output_apk)
    if args.work.exists():
        raise FileExistsError(args.work)
    args.work.mkdir(parents=True)
    args.output_apk.parent.mkdir(parents=True, exist_ok=True)

    input_bytes = args.input_apk.read_bytes()
    if args.expected_apk_sha256 and sha(input_bytes) != args.expected_apk_sha256:
        raise ValueError("input APK SHA-256 does not match the pinned C8016 v3 baseline")
    new_uuid = str(uuid.uuid4())
    with zipfile.ZipFile(args.input_apk) as source:
        manifest = source.read("AndroidManifest.xml")
        original_dex = source.read("classes.dex")
        original_swf = source.read("assets/worldflipper_android_release.swf")
        entries = [(copy.copy(info), source.read(info.filename)) for info in source.infolist()]
    if args.expected_swf_sha256 and sha(original_swf) != args.expected_swf_sha256:
        raise ValueError("input SWF SHA-256 does not match the pinned C8016 v3 baseline")
    if manifest.count(BASE_UUID.encode("utf-16le")) != 1:
        raise ValueError("baseline AIR UUID is not present exactly once in AndroidManifest.xml")

    original_dex_path = args.work / "original.dex"
    original_dex_path.write_bytes(original_dex)
    smali_dir = args.work / "smali"
    readback_dir = args.work / "readback"
    run([args.java, "-jar", args.baksmali_jar, "d", "-o", smali_dir, original_dex_path], args.work, "dex-decode")
    original_smali = read_smali(smali_dir)
    startup_name = "cn/startpoint/StartupCache.smali"
    identity_name = "cn/startpoint/BuildIdentity.smali"
    if startup_name not in original_smali or identity_name not in original_smali:
        raise ValueError("input APK does not contain the accepted StartupCache baseline")
    if original_smali[startup_name].count(BASE_UUID) != 1 or original_smali[identity_name].count(BASE_UUID) != 1:
        raise ValueError("accepted StartupCache UUID sites are missing or duplicated")
    if any("StartupCache$Periodic" in name for name in original_smali):
        raise ValueError("input APK already contains periodic cache classes")
    loader_a = "s/h/e/l/l/A.smali"
    loader_s = "s/h/e/l/l/S.smali"
    for name in (loader_a, loader_s):
        if original_smali.get(name, "").count("Lcn/startpoint/StartupCache;->run") != 1:
            raise ValueError(f"input APK is missing the StartupCache hook: {name}")

    helper_dex = compile_helper(args, args.work, new_uuid)
    helper_smali = args.work / "helper-smali"
    run([args.java, "-jar", args.baksmali_jar, "d", "-o", helper_smali, helper_dex], args.work, "helper-decode")
    helper_files = read_smali(helper_smali)
    if set(helper_files) != TARGET_CLASSES:
        raise ValueError(f"unexpected helper classes: {sorted(helper_files)}")
    for relative, content in helper_files.items():
        destination = smali_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    new_dex = args.work / "classes.dex"
    run([args.java, "-jar", args.smali_jar, "a", "-a", "21", "-o", new_dex, smali_dir], args.work, "dex-assemble")
    run([args.java, "-jar", args.baksmali_jar, "d", "-o", readback_dir, new_dex], args.work, "dex-readback")
    readback_smali = read_smali(readback_dir)
    expected_names = set(original_smali) | {"cn/startpoint/StartupCache$Periodic.smali"}
    if set(readback_smali) != expected_names:
        missing = sorted(expected_names - set(readback_smali))
        extra = sorted(set(readback_smali) - expected_names)
        raise ValueError(f"DEX class inventory changed unexpectedly; missing={missing}; extra={extra}")
    for name, before in original_smali.items():
        if name in TARGET_CLASSES:
            continue
        if readback_smali[name] != before:
            raise ValueError(f"non-target DEX class changed: {name}")
    startup = readback_smali[startup_name]
    periodic = readback_smali["cn/startpoint/StartupCache$Periodic.smali"]
    if "periodicPurge" not in startup or "startPeriodic" not in startup or "0x927c0" not in periodic:
        raise ValueError("periodic cleaner is missing from DEX readback")
    if new_dex.read_bytes().count(BASE_UUID.encode()) != 0:
        raise ValueError("old AIR UUID remains in rebuilt DEX")

    new_manifest = manifest.replace(BASE_UUID.encode("utf-16le"), new_uuid.encode("utf-16le"))
    unsigned = args.work / f"unsigned-{new_uuid}.apk"
    with zipfile.ZipFile(unsigned, "w", allowZip64=True) as destination:
        for info, data in entries:
            if info.filename in SIGNATURE_MEMBERS:
                continue
            if info.filename == "classes.dex":
                data = new_dex.read_bytes()
            elif info.filename == "AndroidManifest.xml":
                data = new_manifest
            destination.writestr(info, data)

    aligned = args.work / f"aligned-{new_uuid}.apk"
    if args.zipalign:
        run([args.zipalign, "-p", "4", unsigned, aligned], args.work, "zipalign")
    else:
        shutil.copy2(unsigned, aligned)

    if args.sign_script:
        if not args.apksigner:
            raise ValueError("--apksigner is required when --sign-script is used")
        run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                args.sign_script,
                "-InputApk",
                aligned,
                "-OutputApk",
                args.output_apk,
                "-ApkSigner",
                args.apksigner,
                "-Java",
                args.java,
            ],
            args.work,
            "sign",
        )
        signature = run(
            [args.java, "-jar", args.apksigner, "verify", "--verbose", "--print-certs", args.output_apk],
            args.work,
            "signature-verify",
        )
        if "Verified using v1 scheme (JAR signing): true" not in signature:
            raise ValueError("V1 signature verification failed")
        if "Verified using v2 scheme (APK Signature Scheme v2): true" not in signature:
            raise ValueError("V2 signature verification failed")
    else:
        shutil.copy2(aligned, args.output_apk)
    if args.zipalign:
        run([args.zipalign, "-c", "-p", "4", args.output_apk], args.work, "alignment-verify")

    with zipfile.ZipFile(args.output_apk) as result:
        if result.testzip() is not None:
            raise ValueError("output APK ZIP integrity check failed")
        if sha(result.read("assets/worldflipper_android_release.swf")) != sha(original_swf):
            raise ValueError("SWF changed during periodic cache packaging")
        if result.read("AndroidManifest.xml").count(new_uuid.encode("utf-16le")) != 1:
            raise ValueError("new AIR UUID is missing from output manifest")
        if result.read("AndroidManifest.xml").count(BASE_UUID.encode("utf-16le")) != 0:
            raise ValueError("old AIR UUID remains in output manifest")
        if set(result.namelist()) - SIGNATURE_MEMBERS != set(info.filename for info, _ in entries) - SIGNATURE_MEMBERS:
            raise ValueError("output APK member set changed")

    report = {
        "status": "offline_candidate",
        "input_apk_sha256": sha(input_bytes),
        "output_apk_sha256": sha(args.output_apk.read_bytes()),
        "input_swf_sha256": sha(original_swf),
        "output_swf_sha256": sha(original_swf),
        "uniqueappversionid": new_uuid,
        "previous_uniqueappversionid": BASE_UUID,
        "period_ms": 600000,
        "period_seconds": 600,
        "periodic_target": ["<DATA>/cache/app", "<DATA>/cache/.AIR"],
        "diagnostic_file": "<DATA>/sp-cache-periodic.diag",
        "cdn_download_directory_untouched": True,
        "embedded_bundle_untouched": True,
        "device_tested": False,
        "cloud_deployed": False,
    }
    report_path = args.report or args.output_apk.with_suffix(args.output_apk.suffix + ".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-apk", type=Path, required=True)
    parser.add_argument("--output-apk", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--java", type=Path, default=Path("java"))
    parser.add_argument("--javac", type=Path)
    parser.add_argument("--d8-jar", type=Path, required=True)
    parser.add_argument("--baksmali-jar", type=Path, required=True)
    parser.add_argument("--smali-jar", type=Path, required=True)
    parser.add_argument("--zipalign", type=Path)
    parser.add_argument("--sign-script", type=Path)
    parser.add_argument("--apksigner", type=Path)
    parser.add_argument("--expected-apk-sha256", default=BASE_APK_SHA256)
    parser.add_argument("--expected-swf-sha256", default=BASE_SWF_SHA256)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = build(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
