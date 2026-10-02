#!/usr/bin/env python3
"""Apply the compact-centered Super+ label layout to an APK's embedded bundle.

The script is deliberately limited to the Flatomo payload and bundle marker.
Endpoint rewriting, AIR UUID rotation, signing, and delivery packaging remain
in the existing Android client builders.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import sys
import zipfile
import zlib
from pathlib import Path

TARGET = "production/android_bundle/dc/bcccb129122c0189c8eab004ecc4516a077f3e"
FRAME_GROUP = 10
FRAME_START = -2147483643
COMPACT_SEGMENTS = [
    {"s": 0, "i": 6, "l": [{"m": 41215}]},  # 超, matrix10
    {"s": 0, "i": 0, "l": [{"m": 37119}]},  # 级, matrix9
    {"s": 0, "i": 5, "l": [{"m": 45311}]},  # +, matrix11
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(data) + compressor.flush()


def clone_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    return copy.copy(info)


def load_dsl_module():
    tools = Path(__file__).resolve().parents[2] / "tools" / "fantasy-gauntlet-mod-tools"
    sys.path.insert(0, str(tools))
    import wf_dsl  # type: ignore

    return wf_dsl


def compact_payload(payload: bytes) -> tuple[bytes, dict[str, object]]:
    wf_dsl = load_dsl_module()
    tree = wf_dsl.parse_dsl(zlib.decompress(payload, -15))["tree"]
    groups = tree.get("g")
    if not isinstance(groups, list) or len(groups) not in (10, 11):
        raise ValueError(f"expected 10 or 11 Flatomo groups, got {len(groups) if isinstance(groups, list) else 'none'}")

    if len(groups) == 10:
        groups.append({"t": 1, "s": copy.deepcopy(COMPACT_SEGMENTS)})
        groups[0]["s"].insert(5, {"s": FRAME_START, "i": FRAME_GROUP, "l": [{"m": 4351}]})
    else:
        root_matches = [
            segment for segment in groups[0]["s"]
            if int(segment.get("s", 0)) == FRAME_START and int(segment.get("i", -1)) == FRAME_GROUP
        ]
        if len(root_matches) != 1:
            raise ValueError("candidate payload does not contain exactly one frame-6 root segment")

    groups[FRAME_GROUP]["s"] = copy.deepcopy(COMPACT_SEGMENTS)
    encoded = wf_dsl.encode_amf3(tree)
    output = raw_deflate(encoded)
    if wf_dsl.parse_dsl(zlib.decompress(output, -15))["tree"] != tree:
        raise ValueError("compact payload did not round-trip through AMF3")
    return output, {
        "input_payload_bytes": len(payload),
        "input_payload_sha256": sha(payload),
        "output_payload_bytes": len(output),
        "output_payload_sha256": sha(output),
        "groups": len(groups),
        "root_segments": len(groups[0]["s"]),
        "frame": 6,
        "layout": "compact-centered",
    }


def rebuild_bundle(bundle: bytes, payload: bytes) -> bytes:
    rebuilt = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle)) as source, zipfile.ZipFile(rebuilt, "w", allowZip64=True) as target:
        seen = False
        for info in source.infolist():
            data = payload if info.filename == TARGET else source.read(info.filename)
            if info.filename == TARGET:
                seen = True
            target.writestr(clone_info(info), data)
    if not seen:
        raise ValueError(f"embedded target missing: {TARGET}")
    return rebuilt.getvalue()


def rewrite_apk(input_apk: Path, payload: bytes, output_apk: Path) -> dict[str, object]:
    if output_apk.exists():
        raise FileExistsError(output_apk)
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_apk) as source:
        old_bundle = source.read("assets/bundle.zip")
        old_marker = source.read("assets/bundle.zip.sha1").decode("ascii").strip()
        with zipfile.ZipFile(io.BytesIO(old_bundle)) as inner:
            before = inner.read(TARGET)
        new_bundle = rebuild_bundle(old_bundle, payload)
        new_marker = hashlib.sha1(new_bundle).hexdigest()
        with zipfile.ZipFile(output_apk, "w", allowZip64=True) as target:
            for info in source.infolist():
                if info.filename == "assets/bundle.zip":
                    data = new_bundle
                elif info.filename == "assets/bundle.zip.sha1":
                    data = (new_marker + "\n").encode("ascii")
                else:
                    data = source.read(info.filename)
                target.writestr(clone_info(info), data)

    with zipfile.ZipFile(output_apk) as check:
        bundle = check.read("assets/bundle.zip")
        marker = check.read("assets/bundle.zip.sha1").decode("ascii").strip()
        if marker != hashlib.sha1(bundle).hexdigest():
            raise ValueError("bundle marker does not match the rebuilt bundle")
        with zipfile.ZipFile(io.BytesIO(bundle)) as inner:
            after = inner.read(TARGET)
        if after != payload:
            raise ValueError("rebuilt APK target payload mismatch")
        if check.testzip() is not None:
            raise ValueError("rebuilt APK has a bad ZIP member")
    return {
        "input_apk": str(input_apk),
        "input_apk_sha256": sha(input_apk.read_bytes()),
        "output_apk": str(output_apk),
        "output_apk_sha256": sha(output_apk.read_bytes()),
        "target": TARGET,
        "target_before_sha256": sha(before),
        "target_after_sha256": sha(payload),
        "target_after_bytes": len(payload),
        "bundle_sha1_before_marker": old_marker,
        "bundle_sha1_after_marker": new_marker,
        "changed_members": ["assets/bundle.zip", "assets/bundle.zip.sha1"],
        "signed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-apk", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output-apk", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.input_apk.is_file():
        raise SystemExit(f"input APK not found: {args.input_apk}")
    if not args.payload.is_file():
        raise SystemExit(f"payload not found: {args.payload}")
    transformed, layout = compact_payload(args.payload.read_bytes())
    report = rewrite_apk(args.input_apk, transformed, args.output_apk)
    report["layout"] = layout
    report["target"] = TARGET
    report["output_apk_sha256"] = sha(args.output_apk.read_bytes())
    report_path = args.report or args.output_apk.with_suffix(args.output_apk.suffix + ".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
