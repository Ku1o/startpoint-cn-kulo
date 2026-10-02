"""Consolidate the complete Inaho terminal resources without a private CDN route.

Pinned inputs and resource digests prevent a partial test chain or older voice
encoding from silently replacing the validated terminal payloads. No live writes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import zlib

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/fantasy-gauntlet-mod-tools"))
import wf_assets as assets
import wf_mod_tool as core

CONTRACT = ROOT / "assets/asset-patch/audit/inaho-final-1.4.116/resource-contract.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_contract():
    return json.loads(CONTRACT.read_text(encoding="utf8"))


def read_archive(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive members")
        for name in names:
            parts = name.split("/")
            if (len(parts) != 4 or parts[0] != "production" or
                    parts[1] not in {"upload", "medium_upload", "small_upload", "android_upload", "ios_upload"} or
                    len(parts[2]) != 2 or len(parts[3]) != 38 or
                    any(c not in "0123456789abcdef" for c in parts[2] + parts[3])):
                raise ValueError("invalid archive member: " + name)
        return {n: archive.read(n) for n in names}


def validate_payloads(payloads, contract, *, check_digests=True):
    records = contract["files"]
    expected = {r["member"] for r in records}
    if set(payloads) != expected:
        raise ValueError(f"resource set mismatch: missing={sorted(expected-set(payloads))}, extra={sorted(set(payloads)-expected)}")
    decoded = {}
    pngs = {}
    frame_names = set()
    sound_count = 0
    for record in records:
        name, logical = record["member"], record["logical"]
        raw = payloads[name]
        digest = core.sha1_path(logical)
        if not name.endswith(digest[:2] + "/" + digest[2:]):
            raise ValueError("logical path hash mismatch: " + logical)
        if check_digests and sha(raw) != record["sha256"]:
            raise ValueError("terminal resource digest mismatch: " + logical)
        if logical.endswith(".png"):
            with Image.open(io.BytesIO(assets.png_decode_stored(raw))) as img:
                img.load()
                pngs[(name.split("/")[1], logical)] = img.size
        if logical.endswith(".mp3"):
            probe = assets.mp3_probe(raw, 1023)
            if probe["frames"] == 0 or probe["tail"] != 0 or len(probe["bitrates"]) != 1:
                raise ValueError("invalid stored CBR audio: " + logical)
            if assets.mp3_encode(assets.mp3_decode(raw)) != raw:
                raise ValueError("audio storage roundtrip mismatch: " + logical)
            sound_count += 1
        if logical.endswith((".parts.amf3.deflate", ".timeline.amf3.deflate", ".atlas.amf3.deflate")):
            reader = core.AMF3Reader(zlib.decompress(raw, -15))
            obj = reader.read_value()
            if reader.pos != len(reader.data):
                raise ValueError("trailing AMF3 bytes: " + logical)
            decoded[logical] = obj
            if logical.endswith(".atlas.amf3.deflate"):
                names = [f["n"] for f in obj]
                if len(names) != len(set(names)):
                    raise ValueError("duplicate atlas frame: " + logical)
                frame_names.update(names)
    # Every outgoing parts animation must have its own timeline and all
    # generated texture names in the delivered atlases, including cross-layout refs.
    image_references = 0
    layouts = 0
    for logical, obj in decoded.items():
        if logical.endswith(".parts.amf3.deflate"):
            timeline = logical.replace(".parts.amf3.deflate", ".timeline.amf3.deflate")
            if timeline not in decoded:
                raise ValueError("missing animation timeline: " + timeline)
            layouts += 1
            for item in obj.get("i", []):
                path = item["p"]
                if "/.gen/" in path:
                    if path not in frame_names:
                        raise ValueError("missing atlas frame: " + path)
                    image_references += 1
        if logical.endswith(".atlas.amf3.deflate") and logical.startswith("battle/effect/"):
            png = logical.replace(".atlas.amf3.deflate", ".png")
            if ("upload", png) not in pngs:
                raise ValueError("missing effect atlas PNG: " + png)
            width, height = pngs[("upload", png)]
            for frame in obj:
                if not (frame["x"] >= 0 and frame["y"] >= 0 and frame["w"] > 0 and frame["h"] > 0 and
                        frame["x"] + frame["w"] <= width and frame["y"] + frame["h"] <= height):
                    raise ValueError("effect atlas rectangle out of bounds: " + frame["n"])
    return dict(members=len(payloads), pngs=len(pngs), voices=sound_count,
                layouts=layouts, generated_image_references=image_references,
                atlas_frame_names=len(frame_names))


def verify_apk(apk, contract):
    raw = apk.read_bytes()
    if sha(raw) != contract["client"]["apk_sha256"]:
        raise ValueError("unexpected direct-8001 client")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        swf = z.read("assets/worldflipper_android_release.swf")
    if sha(swf) != contract["client"]["swf_sha256"]:
        raise ValueError("unexpected SWF")
    plain = zlib.decompress(swf[8:]) if swf[:3] == b"CWS" else swf
    if b"http://127.0.0.1:8011" in plain or b"http://192.168.3.14:8001" not in plain:
        raise ValueError("unexpected client endpoint")
    for reference in contract["client"]["resource_constants"]:
        if reference.encode() not in plain:
            raise ValueError("missing client resource constant: " + reference)
    return dict(apk_sha256=sha(raw), swf_sha256=sha(swf), endpoint="direct LAN 8001",
                private_proxy_dependency=False, rebuilt=False)


def build(base, supplement, output, apk):
    contract = load_contract()
    if sha(base.read_bytes()) != contract["inputs"]["base_sha256"]:
        raise ValueError("base archive changed")
    if sha(supplement.read_bytes()) != contract["inputs"]["supplement_sha256"]:
        raise ValueError("supplement archive changed; do not select an earlier fixture")
    before, patch = read_archive(base), read_archive(supplement)
    combined = {**before, **patch}
    validation = validate_payloads(combined, contract)
    client = verify_apk(apk, contract)
    if ".cdn" in output.resolve().parts or output.resolve() in (base.resolve(), supplement.resolve()):
        raise ValueError("unsafe output path")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(combined.items()):
            entry = zipfile.ZipInfo(name, (2026, 9, 23, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, raw, compresslevel=9)
    readback = read_archive(output)
    assert readback == combined
    validate_payloads(readback, contract)
    changes = {"added": [], "updated": [], "preserved": []}
    for name, raw in combined.items():
        changes["added" if name not in before else "updated" if raw != before[name] else "preserved"].append(name)
    return dict(base="1.4.115", version="1.4.116", archive=output.name,
                sha256=sha(output.read_bytes()), size=output.stat().st_size,
                validation=validation, changes=changes, client=client,
                save_impact="none; resource payloads only", device_tested=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "supplement", "output", "apk", "report"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    report = build(args.base, args.supplement, args.output, args.apk)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"sha256": report["sha256"], "size": report["size"],
                      "validation": report["validation"],
                      "changes": {k: len(v) for k, v in report["changes"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
