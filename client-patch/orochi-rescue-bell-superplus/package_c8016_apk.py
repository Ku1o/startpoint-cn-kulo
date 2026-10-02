#!/usr/bin/env python3
"""Package the C8016 helper SWF on the accepted Super+ Android baseline.

The package step replaces the SWF, rotates AIR's uniqueappversionid, and
rewrites only the two existing StartupCache identity sites in the primary DEX.
It does not add CDN resources or change the admission pair.
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


BASE_APK_SHA256 = "8ab2533469bb88d1292db9c2406b7ff696cb1d1064c027bd83b4985f5e19dcc1"
BASE_SWF_SHA256 = "457d148d55f8cf6b85d8d144e14a12ab12feff1e5561018a9de1fa08c05fc836"
BASE_UUID = "08f205a0-4fdc-4faf-9201-16aade2e174f"
SWF_MEMBER = "assets/worldflipper_android_release.swf"
SIGNATURE_MEMBERS = {"META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}
TARGET_IDENTITY_CLASSES = {
    "cn/startpoint/StartupCache.smali",
    "cn/startpoint/BuildIdentity.smali",
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


def read_smali(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*.smali")
    }


def package(args: argparse.Namespace) -> dict[str, object]:
    if not args.input_apk.is_file():
        raise FileNotFoundError(args.input_apk)
    if not args.swf.is_file():
        raise FileNotFoundError(args.swf)
    if args.output_apk.exists() or args.work.exists():
        raise FileExistsError("output or work path already exists")
    args.work.mkdir(parents=True)
    args.output_apk.parent.mkdir(parents=True, exist_ok=True)
    input_bytes = args.input_apk.read_bytes()
    if sha(input_bytes) != args.expected_apk_sha256:
        raise ValueError("input APK SHA-256 does not match the accepted Super+ baseline")
    swf_bytes = args.swf.read_bytes()
    if sha(swf_bytes) != args.expected_swf_sha256:
        raise ValueError("helper SWF SHA-256 does not match the expected C8016 output")
    if sha(swf_bytes) == BASE_SWF_SHA256:
        raise ValueError("helper SWF is unchanged; package the C8016 output instead")
    new_uuid = str(uuid.uuid4())

    with zipfile.ZipFile(args.input_apk) as source:
        manifest = source.read("AndroidManifest.xml")
        original_dex = source.read("classes.dex")
        original_swf = source.read(SWF_MEMBER)
        entries = [(copy.copy(info), source.read(info.filename)) for info in source.infolist()]
    if sha(original_swf) != BASE_SWF_SHA256:
        raise ValueError("input APK does not contain the accepted Super+ SWF")
    if manifest.count(BASE_UUID.encode("utf-16le")) != 1:
        raise ValueError("baseline AIR UUID is not present exactly once in manifest")

    original_dex_path = args.work / "original.dex"
    original_dex_path.write_bytes(original_dex)
    smali_dir = args.work / "smali"
    readback_dir = args.work / "readback"
    run([args.java, "-jar", args.baksmali_jar, "d", "-o", smali_dir, original_dex_path], args.work, "dex-decode")
    original_smali = read_smali(smali_dir)
    if not TARGET_IDENTITY_CLASSES.issubset(original_smali):
        raise ValueError("accepted StartupCache identity classes are missing")
    for name in TARGET_IDENTITY_CLASSES:
        if original_smali[name].count(BASE_UUID) != 1:
            raise ValueError(f"unexpected AIR UUID count in {name}")
    for name in TARGET_IDENTITY_CLASSES:
        destination = smali_dir / name
        destination.write_text(original_smali[name].replace(BASE_UUID, new_uuid), encoding="utf-8")

    new_dex = args.work / "classes.dex"
    run([args.java, "-jar", args.smali_jar, "a", "-a", "21", "-o", new_dex, smali_dir], args.work, "dex-assemble")
    run([args.java, "-jar", args.baksmali_jar, "d", "-o", readback_dir, new_dex], args.work, "dex-readback")
    readback_smali = read_smali(readback_dir)
    if set(readback_smali) != set(original_smali):
        raise ValueError("DEX class inventory changed unexpectedly")
    for name, before in original_smali.items():
        if name in TARGET_IDENTITY_CLASSES:
            after = readback_smali[name].replace(new_uuid, BASE_UUID)
            if after != before:
                raise ValueError(f"identity class did not round-trip: {name}")
        elif readback_smali[name] != before:
            raise ValueError(f"non-target DEX class changed: {name}")
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
            elif info.filename == SWF_MEMBER:
                data = swf_bytes
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
        if sha(result.read(SWF_MEMBER)) != args.expected_swf_sha256:
            raise ValueError("output SWF hash changed during packaging")
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
        "output_swf_sha256": sha(swf_bytes),
        "swf_member": SWF_MEMBER,
        "previous_uniqueappversionid": BASE_UUID,
        "uniqueappversionid": new_uuid,
        "helper_only_swf_change": True,
        "unchanged_apk_members": len(entries) - len(SIGNATURE_MEMBERS) - 3,
        "admission_pair_unchanged": True,
        "resource_source": "APK embedded bundle",
        "cdn_increment_used": False,
        "device_tested": False,
        "ios_ipa_built": False,
    }
    report_path = args.report or args.output_apk.with_suffix(args.output_apk.suffix + ".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-apk", type=Path, required=True)
    parser.add_argument("--swf", type=Path, required=True)
    parser.add_argument("--output-apk", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--java", type=Path, default=Path("java"))
    parser.add_argument("--baksmali-jar", type=Path, required=True)
    parser.add_argument("--smali-jar", type=Path, required=True)
    parser.add_argument("--zipalign", type=Path)
    parser.add_argument("--sign-script", type=Path)
    parser.add_argument("--apksigner", type=Path)
    parser.add_argument("--expected-apk-sha256", default=BASE_APK_SHA256)
    parser.add_argument("--expected-swf-sha256", default="9418137820c007b52a11ad0d7955c102795d8dd903213670577bf3407ed709f7")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = package(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
