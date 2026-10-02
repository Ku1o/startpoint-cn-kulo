"""Build the public Android package from the accepted LAN SET-fix APK.

Only the service endpoint and AIR identity are changed.  The SWF itself is
otherwise preserved, including the SET default-title fix and the three
independent party routes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import uuid
import zipfile
import zlib
from pathlib import Path

ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
WORK = Path(r"F:\codex\work\set-edit-c8601-public-20260924")
OUT = Path(r"F:\codex\outputs\set-edit-c8601-public-20260924")
SOURCE_APK = Path(r"F:\codex\outputs\set-edit-c8601-default-title-safe-lan-20260924\StarPoint-CN-1.8.1-independent-formations-set-edit-c8601-default-title-safe-lan-20260924-da77d80a.apk")
SOURCE_APK_SHA = "e531534d9548d6e1cac5cc412d3bf9aad6d5df8330565ce022f54b0fe8180d51"
SWF_MEMBER = "assets/worldflipper_android_release.swf"
OLD_UUID = "da77d80a-5b8f-43c7-acc4-2a8dd0b21612"
PUBLIC_HOST = "175.178.160.158"
PUBLIC_ENDPOINT = f"http://{PUBLIC_HOST}:8001"
ADMISSION_ID = "android-181-independent-party-20260923"
EXPECTED_SIGNER = "569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894"
JAVA = Path(r"D:\java\bin\java.exe")
BT = Path(r"F:\StartPointCN\wf_full_patch\build-tools")
LIBS = Path(r"F:\codex\ios-rush-leaderboard-port-20260830\AIRSDK_51.2.1.5\lib\android\lib")
SIGNER = BT / "lib/apksigner.jar"
ZIPALIGN = BT / "zipalign.exe"
SIGN_SCRIPT = Path(r"F:\codex\startpoint-cn-private-clean\client-patch\lens0907-0908\sign_apk.ps1")
SIGNATURE_MEMBERS = {"META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}

from set_edit_common import s  # noqa: E402


def sha(data_or_path) -> str:
    data = data_or_path if isinstance(data_or_path, (bytes, bytearray)) else Path(data_or_path).read_bytes()
    return hashlib.sha256(bytes(data)).hexdigest()


def run(cmd, log_name, timeout=600):
    result = subprocess.run([str(x) for x in cmd], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout, check=False)
    (WORK / log_name).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f"{log_name} failed: {result.stdout.decode('utf8', 'replace')[-5000:]}")
    return result.stdout.decode("utf8", "replace")


def serialize(abc, original):
    """Keep zero-count ABC pools encoded as zero when a pool gains one item."""
    def counts(data):
        reader = s.m.abcfmt.R(data)
        reader.p = 4
        rows = []
        for fn in (reader.s32, reader.u32, reader.d64):
            at = reader.p
            n = reader.u30()
            rows.append((at, n))
            for _ in range(max(0, n - 1)):
                fn()
        return rows

    out = bytearray(abc.serialize())
    for (_, old), (at, new) in zip(counts(original), counts(out)):
        if old == 0 and new == 1:
            out[at] = 0
    return bytes(out)


def rewrite_swf(source: bytes) -> tuple[bytes, dict]:
    source_path = WORK / "source-lan.swf"
    source_path.write_bytes(source)
    version, header, tags = s.parts(source_path)
    lan_hosts = {
        match.group(1).decode()
        for tag in tags if tag[0] == 82
        for value in tag[3].strings if isinstance(value, bytes)
        for match in re.finditer(rb"\b(192\.168\.\d{1,3}\.\d{1,3})(?::8001)\b", value)
    }
    assert len(lan_hosts) == 1, lan_hosts
    lan_host, = lan_hosts
    changed_tags = []
    replaced_strings = []
    for tag_index, tag in enumerate(tags):
        if tag[0] != 82:
            continue
        abc = tag[3]
        before = bytes(tag[4])
        changed = False
        for index, value in enumerate(abc.strings):
            if isinstance(value, bytes):
                old = value
                new = old.replace(lan_host.encode(), PUBLIC_HOST.encode())
                if new != old:
                    abc.strings[index] = new
                    replaced_strings.append({"tag": tag_index, "string_index": index,
                                            "before": old.decode("utf8", "replace"),
                                            "after": new.decode("utf8", "replace")})
                    changed = True
            elif isinstance(value, str):
                new = value.replace(lan_host, PUBLIC_HOST)
                if new != value:
                    abc.strings[index] = new
                    replaced_strings.append({"tag": tag_index, "string_index": index,
                                            "before": value, "after": new})
                    changed = True
        if changed:
            payload = tag[2] + serialize(abc, tag[4])
            tag[1] = struct.pack("<HI", (82 << 6) | 63, len(payload)) + payload
            changed_tags.append(tag_index)
        else:
            assert bytes(tag[4]) == before
    raw = header + b"".join(tag[1] for tag in tags)
    # Android client SWFs are CWS files.  Keep the version and uncompressed
    # length while recompressing the rewritten movie body.
    result = b"CWS" + bytes([version]) + struct.pack("<I", len(raw) + 8) + zlib.compress(raw)
    # Endpoint text is inside compressed ABC pools, so verify it through the
    # parsed pools below rather than searching the compressed bytes.
    return result, {"lan_host": lan_host, "changed_tags": changed_tags, "replaced_strings": replaced_strings,
                    "source_sha256": sha(source), "output_sha256": sha(result)}


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    assert sha(SOURCE_APK) == SOURCE_APK_SHA
    uid = str(uuid.uuid4())
    with zipfile.ZipFile(SOURCE_APK) as src:
        original_manifest = src.read("AndroidManifest.xml")
        original_dex = src.read("classes.dex")
        original_swf = src.read(SWF_MEMBER)
        source_members = {item.filename: sha(src.read(item.filename)) for item in src.infolist()
                          if item.filename not in SIGNATURE_MEMBERS}
    assert original_manifest.count(OLD_UUID.encode("utf-16le")) == 1
    assert original_dex.count(OLD_UUID.encode()) == 1
    public_swf, swf_report = rewrite_swf(original_swf)
    (WORK / "public.swf").write_bytes(public_swf)

    original_dex_path = WORK / "original.dex"
    original_dex_path.write_bytes(original_dex)
    smali = WORK / f"smali-{uid}"
    back = WORK / f"smali-readback-{uid}"
    run([JAVA, "-jar", LIBS / "baksmali.jar", "d", "-o", smali, original_dex_path], "dex-decode.log")
    originals = {p.relative_to(smali): p.read_text(encoding="utf8") for p in smali.rglob("*.smali")}
    hits = {}
    for name, text in originals.items():
        count = text.count(OLD_UUID)
        if count:
            (smali / name).write_text(text.replace(OLD_UUID, uid), encoding="utf8")
            hits[name.as_posix()] = count
    assert hits == {"cn/startpoint/StartupCache.smali": 1, "cn/startpoint/BuildIdentity.smali": 1}, hits
    new_dex = WORK / "classes.dex"
    run([JAVA, "-jar", LIBS / "smali.jar", "a", "-a", "21", "-o", new_dex, smali], "dex-assemble.log")
    run([JAVA, "-jar", LIBS / "baksmali.jar", "d", "-o", back, new_dex], "dex-readback.log")
    for name, text in originals.items():
        if name.as_posix() in hits:
            assert (back / name).read_text(encoding="utf8").replace(uid, OLD_UUID) == text, str(name)

    payloads = {
        "AndroidManifest.xml": original_manifest.replace(OLD_UUID.encode("utf-16le"), uid.encode("utf-16le")),
        "classes.dex": new_dex.read_bytes(),
        SWF_MEMBER: public_swf,
    }
    unsigned = WORK / f"unsigned-{uid}.apk"
    aligned = WORK / f"aligned-{uid}.apk"
    with zipfile.ZipFile(SOURCE_APK) as src, zipfile.ZipFile(unsigned, "w") as dst:
        for item in src.infolist():
            if item.filename in SIGNATURE_MEMBERS:
                continue
            dst.writestr(item, payloads.get(item.filename, src.read(item.filename)))
    run([ZIPALIGN, "-p", "4", unsigned, aligned], "zipalign.log")
    apk = OUT / f"StarPoint-CN-1.8.1-independent-formations-set-edit-c8601-public-20260924-{uid[:8]}.apk"
    run(["powershell", "-NoProfile", "-NonInteractive", "-File", SIGN_SCRIPT,
         "-InputApk", aligned, "-OutputApk", apk, "-ApkSigner", SIGNER, "-Java", JAVA], "sign.log")
    verify = run([JAVA, "-jar", SIGNER, "verify", "--verbose", "--print-certs", apk], "verify.log")
    assert EXPECTED_SIGNER in verify.lower()
    assert "Verified using v1 scheme (JAR signing): true" in verify
    assert "Verified using v2 scheme (APK Signature Scheme v2): true" in verify
    run([ZIPALIGN, "-c", "-p", "4", apk], "verify-alignment.log")

    with zipfile.ZipFile(apk) as dst:
        assert dst.testzip() is None
        manifest_out = dst.read("AndroidManifest.xml")
        dex_out = dst.read("classes.dex")
        swf_out = dst.read(SWF_MEMBER)
        assert manifest_out.count(uid.encode("utf-16le")) == 1
        assert OLD_UUID.encode("utf-16le") not in manifest_out
        assert swf_out == public_swf
        assert uid.encode() in dex_out
        assert OLD_UUID.encode() not in dex_out
        final_members = {name: sha(dst.read(name)) for name in dst.namelist()
                         if name not in SIGNATURE_MEMBERS}
    unchanged = [name for name in source_members if name not in {"AndroidManifest.xml", "classes.dex", SWF_MEMBER}
                 and source_members[name] == final_members.get(name)]
    assert len(unchanged) == len(source_members) - 3

    report = {
        "status": "offline_candidate",
        "apk": str(apk),
        "apk_sha256": sha(apk),
        "source_apk": str(SOURCE_APK),
        "source_apk_sha256": sha(SOURCE_APK),
        "source_swf_sha256": sha(original_swf),
        "swf_sha256": sha(public_swf),
        "swf_endpoint_rewrite": swf_report,
        "uniqueappversionid": uid,
        "previous_uniqueappversionid": OLD_UUID,
        "package_name": "com.leiting.wf",
        "version_name": "1.8.1",
        "version_code": 1008001,
        "endpoint": PUBLIC_ENDPOINT,
        "previous_endpoint": f"http://{swf_report['lan_host']}:8001",
        "admission_id": ADMISSION_ID,
        "admission_id_key_unchanged": True,
        "native_identity_sites": hits,
        "signer_certificate_sha256": EXPECTED_SIGNER,
        "zipalign": True,
        "v1_signature": True,
        "v2_signature": True,
        "unchanged_apk_members_verified": True,
        "device_tested": False,
        "scope": "public endpoint repack from the user-tested LAN SET-fix APK; existing admission pairing preserved",
    }
    (OUT / "package-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    shutil.rmtree(smali, ignore_errors=True)
    shutil.rmtree(back, ignore_errors=True)
    for path in (unsigned, aligned, original_dex_path, new_dex):
        path.unlink(missing_ok=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
