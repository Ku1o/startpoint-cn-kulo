#!/usr/bin/env python3
"""Replace only the InahoAbilityVisuals helper ABC in a SWF.

The input SWF is treated as an immutable cumulative client artifact.  The
patcher replaces the existing helper ABC at its existing tag and verifies that
every other SWF tag remains byte-identical.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import zlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "startup-cache" / "build_swf.py"
SPEC = importlib.util.spec_from_file_location("startup_cache_swf_tools", TOOLS)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"cannot load SWF tools: {TOOLS}")
swf_tools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(swf_tools)


def sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def helper_tag(prefix: bytes, abc) -> bytes:
    payload = prefix + abc.serialize()
    return struct.pack("<HI", (82 << 6) | 63, len(payload)) + payload


def patch(source: Path, helper_swc: Path, output: Path, report_path: Path) -> dict[str, object]:
    if not source.is_file():
        raise FileNotFoundError(source)
    if not helper_swc.is_file():
        raise FileNotFoundError(helper_swc)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    version, header, tags = swf_tools.parts(source)
    matches = [
        (index, row)
        for index, row in enumerate(tags)
        if row[0] == 82 and row[2][4:-1] == b"cn.mod.InahoAbilityVisuals"
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one InahoAbilityVisuals helper tag, found {len(matches)}")
    helper_index, helper = matches[0]

    # helper_abc() writes a temporary library.swf beside the SWC.  Copying it
    # to a task-local temporary directory avoids changing the donor directory.
    import tempfile
    import zipfile

    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        temporary_swf = Path(temporary) / "library.swf"
        with zipfile.ZipFile(helper_swc) as archive:
            temporary_swf.write_bytes(archive.read("library.swf"))
        helper_values = [
            row[3] for row in swf_tools.parts(temporary_swf)[2] if row[0] == 82
        ]
    if len(helper_values) != 1:
        raise ValueError(f"expected one helper ABC in {helper_swc}, found {len(helper_values)}")
    new_class = helper_values[0]
    if len(new_class.instances) != 1 or new_class.mn_name(new_class.instances[0][0]) != "cn.mod::InahoAbilityVisuals":
        raise ValueError("helper SWC does not contain cn.mod::InahoAbilityVisuals")
    for body in new_class.bodies:
        swf_tools.m.check_body(body, new_class)

    original_tag_bytes = [bytes(row[1]) for row in tags]
    old_prefix = bytes(helper[2])
    old_bodies = len(helper[3].bodies)
    helper[1] = helper_tag(old_prefix, new_class)
    raw = header + b"".join(row[1] for row in tags)
    output.write_bytes(
        b"CWS"
        + bytes([version])
        + struct.pack("<I", len(raw) + 8)
        + zlib.compress(raw)
    )

    _, _, readback = swf_tools.parts(output)
    if len(readback) != len(tags):
        raise ValueError("SWF tag count changed")
    for index, (before, after) in enumerate(zip(original_tag_bytes, readback)):
        if index == helper_index:
            if before == after or old_prefix != after[2]:
                raise ValueError("helper tag did not change in place")
            if after[3].mn_name(after[3].instances[0][0]) != "cn.mod::InahoAbilityVisuals":
                raise ValueError("helper tag class changed unexpectedly")
        elif before != after[1]:
            raise ValueError(f"unrelated SWF tag changed: {index}")

    report = {
        "status": "offline_candidate",
        "input_swf_sha256": sha(source.read_bytes()),
        "output_swf_sha256": sha(output.read_bytes()),
        "helper_tag_index": helper_index,
        "old_helper_bodies": old_bodies,
        "new_helper_bodies": len(new_class.bodies),
        "changed_tags": [helper_index],
        "other_swf_tags_byte_identical": True,
        "preload_guard": "content index 4; nested damage index 13/14 or InvokeSkill index 19 with cnmod_inaho_midautumn marker",
        "device_tested": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--helper-swc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = patch(
        args.source,
        args.helper_swc,
        args.output,
        args.report or args.output.with_suffix(".json"),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
