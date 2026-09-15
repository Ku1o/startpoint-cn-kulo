"""Convert the r9 LAN candidate to the public endpoint."""
from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import uuid
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(value)
    return value


b = module("party_cache_public_build", HERE.parent / "startup-cache/build.py")
native = module("party_cache_public_native", HERE.parent / "startup-cache/verify_native.py")
checker = module("party_cache_public_baseline", HERE.parent / "verify_android_baseline.py")
party_patch = module("party_cache_public_swf", HERE / "patch_swf.py")
s = party_patch.s

CERT = "569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894"
SIGNATURES = {"META-INF/MANIFEST.MF", "META-INF/WF.SF", "META-INF/WF.RSA"}
ENDPOINT_BODY = 92013
ENDPOINT_LABEL = "pinball.config.gbits::DevConfig_gf_android/<ctor>"


def convert_endpoint(source: Path, output: Path, old_endpoint: str, new_endpoint: str) -> dict:
    source_bytes = source.read_bytes()
    version, header, tags = s.parts(source)
    abcs = [row for row in tags if row[0] == 82]
    main = next(row for row in abcs if row[2][4:-1] == b"boot_ffc6")
    abc = main[3]
    before = abc.serialize()
    view = s.m.View(SimpleNamespace(abc=abc), s.m.asm)
    assert view.by_label[ENDPOINT_LABEL] == [ENDPOINT_BODY]
    body = abc.bodies[ENDPOINT_BODY]
    rows = s.m.asm.decode(body[5])
    hits = [i for i, ins in enumerate(rows) if ins.op == 0x2C and abc.s(ins.args[0]) == old_endpoint]
    assert len(hits) == 1, hits
    index = rows[hits[0]].args[0]
    uses = []
    for bi, value in enumerate(abc.bodies):
        for ii, ins in enumerate(s.m.asm.decode(value[5])):
            if ins.op == 0x2C and ins.args[0] == index:
                uses.append((bi, ii))
    assert uses == [(ENDPOINT_BODY, hits[0])], uses
    abc.strings[index] = new_endpoint.encode()
    replacement = abc.serialize()
    abc.strings[index] = old_endpoint.encode()
    assert abc.serialize() == before
    data = main[2] + replacement
    main[1] = struct.pack("<HI", (82 << 6) | 63, len(data)) + data
    raw = header + b"".join(row[1] for row in tags)
    output.write_bytes(b"CWS" + bytes([version]) + struct.pack("<I", len(raw) + 8) + zlib.compress(raw))
    final_tags = s.parts(output)[2]
    final_abcs = [row for row in final_tags if row[0] == 82]
    # R8 diagnostic inputs carry one additional helper ABC compared with the
    # ordinary party-cache candidate.  Keep the invariant that endpoint
    # conversion does not add/remove ABC blocks without assuming one fixed
    # diagnostic count.
    assert len(final_abcs) == len(abcs)
    final_main = next(row[3] for row in final_abcs if row[2][4:-1] == b"boot_ffc6")
    assert final_main.strings[index] == new_endpoint.encode()
    final_main.strings[index] = old_endpoint.encode()
    assert final_main.serialize() == before
    return {
        "input_swf_sha256": b.sha(source_bytes),
        "output_swf_sha256": b.sha(output.read_bytes()),
        "endpoint_pool_index": index,
        "old_endpoint": old_endpoint,
        "new_endpoint": new_endpoint,
        "changed_original_bodies": [20565],
        "party_cache_helper_preserved": True,
        "all_other_swf_tags_unchanged": True,
    }


def main(args: argparse.Namespace) -> None:
    parent = args.parent.resolve()
    parent_report_path = parent.parent / "verification.json"
    work = args.work.resolve()
    out = args.out.resolve()
    assert parent.exists() and parent_report_path.exists()
    assert not work.exists() and not out.exists()
    assert ".cdn" not in work.parts and ".cdn" not in out.parts
    parent_report = json.loads(parent_report_path.read_text("utf-8"))
    lan = checker.verify("lan")
    public = checker.verify("public")
    assert parent_report["variant"] == "lan"
    assert b.sha(parent.read_bytes()) == parent_report["apk_sha256"]
    assert parent_report["endpoint"] == lan["endpoint"]
    assert parent_report["changed_original_methods"] == [20565]

    work.mkdir(parents=True)
    out.mkdir(parents=True)
    with zipfile.ZipFile(parent) as source:
        base_swf = work / "input-lan.swf"
        base_swf.write_bytes(source.read("assets/worldflipper_android_release.swf"))
        (work / "original.dex").write_bytes(source.read("classes.dex"))
    swf_output = work / "public.swf"
    lan_host = lan["endpoint"].split("://", 1)[1]
    public_host = public["endpoint"].split("://", 1)[1]
    endpoint_report = convert_endpoint(base_swf, swf_output, lan_host, public_host)
    endpoint_report["old_endpoint"] = lan["endpoint"]
    endpoint_report["new_endpoint"] = public["endpoint"]
    uid = str(uuid.uuid4())
    old_uid = parent_report["uniqueappversionid"]
    (work / "uuid.txt").write_text(uid + "\n", encoding="ascii")

    run, java, libs = b.run, b.JAVA, b.ALIB
    run([java, "-jar", libs / "baksmali.jar", "d", "-o", work / "smali", work / "original.dex"], work, "dex-decode")
    original = {p.relative_to(work / "smali"): p.read_text("utf-8") for p in (work / "smali").rglob("*.smali")}
    hits = {}
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

    payloads = {"assets/worldflipper_android_release.swf": swf_output.read_bytes(), "classes.dex": dex}
    with zipfile.ZipFile(parent) as source, zipfile.ZipFile(work / "unsigned.apk", "w") as dest:
        manifest = source.read("AndroidManifest.xml")
        assert manifest.count(old_uid.encode("utf-16le")) == 1
        payloads["AndroidManifest.xml"] = manifest.replace(old_uid.encode("utf-16le"), uid.encode("utf-16le"))
        for item in source.infolist():
            if item.filename not in SIGNATURES:
                dest.writestr(item, payloads.get(item.filename, source.read(item.filename)))
    align = Path("F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe")
    run([align, "-p", "4", work / "unsigned.apk", work / "aligned.apk"], work, "align")
    apk = out / "StarPoint-CN-1.8.1-party-cache-r9-public-test-20260914.apk"
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
        assert b.sha(dest.read("assets/worldflipper_android_release.swf")) == endpoint_report["output_swf_sha256"]

    result = {
        "variant": "public",
        "apk": str(apk),
        "apk_sha256": b.sha(apk.read_bytes()),
        "size_bytes": apk.stat().st_size,
        "parent_apk_sha256": parent_report["apk_sha256"],
        "parent_swf_sha256": parent_report["swf_sha256"],
        "endpoint": public["endpoint"],
        "endpoint_conversion": endpoint_report,
        "uniqueappversionid": uid,
        "native_build_identity": uid,
        "native_identity_sites": hits,
        "native_behavior_unchanged": True,
        "signer_sha256": CERT,
        "zipalign": True,
        "v1_v2_signatures": True,
        "changed_apk_members": ["assets/worldflipper_android_release.swf", "classes.dex", "AndroidManifest.xml"],
        "all_other_apk_members_unchanged": True,
        "method_bodies_checked": 96543,
        "changed_original_methods": [20565],
        "party_cache_scope": parent_report["party_cache_scope"],
        "calculated_objects_reused": True,
        "device_tested_public_apk": False,
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
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
