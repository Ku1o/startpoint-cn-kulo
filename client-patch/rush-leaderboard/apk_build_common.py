#!/usr/bin/env python3
"""Shared APK packaging checks; contains no profile behavior patches.

Extracted from the locally deprecated diagnostic builder so accepted builders
can run from a fresh checkout without importing discarded patch logic.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import zipfile
from pathlib import Path

BASE_UUID = "08468b1e-5dbd-47a4-9aec-00b7d1c97099"


SWF_MEMBER = "assets/worldflipper_android_release.swf"


MANIFEST_MEMBER = "AndroidManifest.xml"


SIGNATURE_MEMBERS = {"META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}


CERT_SHA256 = "569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894"


class BuildError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str | Path], *, capture: bool = False) -> str:
    completed = subprocess.run(
        [str(value) for value in command],
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        timeout=600,
    )
    return completed.stdout or ""


def extract_swf(apk: Path, destination: Path) -> None:
    with zipfile.ZipFile(apk) as archive:
        destination.write_bytes(archive.read(SWF_MEMBER))


def replace_apk(base: Path, swf: Path, destination: Path, new_uuid: str, *, base_uuid: str = BASE_UUID) -> None:
    with zipfile.ZipFile(base) as source, zipfile.ZipFile(destination, "w", allowZip64=True) as target:
        manifest = source.read(MANIFEST_MEMBER)
        old = base_uuid.encode("utf-16le")
        if manifest.count(old) != 1:
            raise BuildError("expected baseline UUID is not present exactly once")
        manifest = manifest.replace(old, new_uuid.encode("utf-16le"), 1)
        target.comment = source.comment
        for item in source.infolist():
            if item.filename in SIGNATURE_MEMBERS:
                continue
            data = swf.read_bytes() if item.filename == SWF_MEMBER else manifest if item.filename == MANIFEST_MEMBER else source.read(item.filename)
            target.writestr(item, data)


def verify(base: Path, final: Path, intended_swf: Path, new_uuid: str, java: Path, apksigner: Path, *, base_uuid: str = BASE_UUID) -> dict:
    with zipfile.ZipFile(base) as left, zipfile.ZipFile(final) as right:
        left_names = {x.filename for x in left.infolist() if x.filename not in SIGNATURE_MEMBERS}
        right_names = {x.filename for x in right.infolist() if x.filename not in SIGNATURE_MEMBERS}
        if left_names != right_names:
            raise BuildError("APK member set changed")
        for name in left_names - {SWF_MEMBER, MANIFEST_MEMBER}:
            if left.read(name) != right.read(name):
                raise BuildError(f"unrelated APK member changed: {name}")
        if hashlib.sha256(right.read(SWF_MEMBER)).hexdigest() != sha256(intended_swf):
            raise BuildError("embedded SWF does not match intended payload")
        manifest = right.read(MANIFEST_MEMBER)
        if manifest.count(new_uuid.encode("utf-16le")) != 1 or manifest.count(base_uuid.encode("utf-16le")):
            raise BuildError("AIR uniqueappversionid verification failed")
        if manifest != left.read(MANIFEST_MEMBER).replace(base_uuid.encode("utf-16le"), new_uuid.encode("utf-16le"), 1):
            raise BuildError("unrelated Android manifest data changed")
    output = run([java, "-jar", apksigner, "verify", "--verbose", "--print-certs", final], capture=True)
    if "Verified using v1 scheme (JAR signing): true" not in output or "Verified using v2 scheme (APK Signature Scheme v2): true" not in output:
        raise BuildError("APK signature verification failed")
    match = re.search(r"Signer\s+#1\s+certificate\s+SHA-256\s+digest:\s*([0-9a-fA-F]{64})", output)
    if match is None or match.group(1).lower() != CERT_SHA256:
        raise BuildError("APK signer certificate does not match StarPoint CN key")
    return {"apk_sha256": sha256(final), "swf_sha256": sha256(intended_swf), "uniqueappversionid": new_uuid, "signer_certificate_sha256": CERT_SHA256}
