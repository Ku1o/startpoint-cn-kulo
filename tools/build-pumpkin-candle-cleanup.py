"""Build/check the narrow 1.4.353 candle-condition repair from the enabled chain."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/fantasy-gauntlet-mod-tools"))
from wf_dsl import encode_amf3, parse_dsl
from wf_dsl_sig import validate_action_dsl

BASE_VERSION = "1.4.352"
VERSION = "1.4.353"
ARCHIVE = "pinball-1.4.352-1.4.353-1-pumpkin-candle-buff-cleanup.zip"
PREFIX = "battle/action/enemy/action/mod/hell_pumpkin/"
KEY = "mod_hp_candle_attack"
PROGRAMS = tuple(f"hp_candle_on_{i}" for i in range(1, 7)) + ("hp_candle_off",)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def member(program: str) -> str:
    logical = PREFIX + program + ".action.dsl.amf3.deflate"
    digest = hashlib.sha1((logical + "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy").encode()).hexdigest()
    return "production/upload/" + digest[:2] + "/" + digest[2:]


def commands(tree, name):
    if isinstance(tree, list):
        if tree and tree[0] == name:
            yield tree
        for child in tree:
            yield from commands(child, name)


def decode(payload: bytes):
    tree = parse_dsl(zlib.decompress(payload, -15))["tree"]
    validate_action_dsl(tree)
    return tree


def rewrite(program: str, payload: bytes) -> bytes:
    if program not in PROGRAMS:
        raise ValueError("Unexpected candle program")
    original = decode(payload)
    tree = copy.deepcopy(original)
    name = "DeleteCondition" if program == "hp_candle_off" else "CreateCondition"
    found = list(commands(tree, name))
    if len(found) != 1:
        raise ValueError("Expected exactly one candle condition command")
    command = found[0]
    if name == "CreateCondition":
        # p5=cancelable, p7=discriminationKey; retain magnitude/lifetime/targets.
        if command[5] is not True or command[7] != "" or command[2][0][0] != "ACAttackPoint":
            raise ValueError("Unexpected candle-on preimage")
        command[7] = KEY
    else:
        # p3=limit, p4=cancelableKind (0=cancelable), p5=discriminationKey.
        if command != ["DeleteCondition", 0, ["DCAttackPoint", 2], 1, 1, "", ["Default"]]:
            raise ValueError("Unexpected candle-off preimage")
        command[4], command[5] = 0, KEY
    validate_action_dsl(tree)
    encoded = encode_amf3(tree)
    if parse_dsl(encoded)["tree"] != tree:
        raise ValueError("Candle AMF3 roundtrip mismatch")
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(encoded) + compressor.flush()


def read_effective(root: Path, manifest: dict, program: str) -> bytes:
    name = member(program)
    for patch in reversed(manifest["patches"]):
        if not patch.get("enabled"):
            continue
        if patch.get("files") and name not in patch["files"]:
            continue
        for archive in reversed(patch.get("chain") or [patch["archive"]]):
            if Path(archive).name != archive or not archive.endswith(".zip"):
                raise ValueError("Unsafe active archive name")
            with zipfile.ZipFile(root / "assets/asset-patch/active" / archive) as source:
                if name in source.namelist():
                    return source.read(name)
    raise ValueError("Missing enabled candle resource: " + program)


def build_entries(root: Path, manifest: dict) -> dict[str, bytes]:
    if manifest["cdn_version"] != BASE_VERSION:
        raise ValueError("Expected the reviewed 1.4.352 source chain")
    return {member(program): rewrite(program, read_effective(root, manifest, program)) for program in PROGRAMS}


def archive_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            target.writestr(info, data, compresslevel=9)
    return output.getvalue()


def verify(root: Path) -> dict:
    manifest = json.loads((root / "assets/asset-patch/manifest.json").read_bytes())
    return verify_manifest(root, manifest)


def verify_manifest(root: Path, manifest: dict) -> dict:
    matches = [index for index, patch in enumerate(manifest["patches"]) if patch["version"] == VERSION]
    if len(matches) != 1 or not matches[0]:
        raise ValueError("Expected exactly one installed 1.4.353 repair")
    index = matches[0]
    base = copy.deepcopy(manifest)
    patch = manifest["patches"][index]
    base["patches"] = base["patches"][:index]
    if base["patches"][-1]["version"] != BASE_VERSION:
        raise ValueError("Repair does not follow the reviewed source edge")
    base["cdn_version"] = BASE_VERSION
    expected = archive_bytes(build_entries(root, base))
    actual = (root / "assets/asset-patch/active" / ARCHIVE).read_bytes()
    names = sorted(member(program) for program in PROGRAMS)
    receipt = patch["archive_integrity"]
    if (patch["depends_on"] != BASE_VERSION or patch["archive"] != ARCHIVE
            or patch["chain"] != [ARCHIVE] or patch["files"] != names
            or patch["archive_size"] != len(actual) or len(receipt) != 1
            or receipt[0] != {"name": ARCHIVE, "size": len(actual), "sha256": sha(actual),
                              "members": len(names), "files": names} or actual != expected):
        raise ValueError("Repair archive/manifest differs from the scoped recipe")
    with zipfile.ZipFile(io.BytesIO(actual)) as source:
        if source.testzip() is not None or source.namelist() != names:
            raise ValueError("Repair ZIP integrity mismatch")
        for name in names:
            decode(source.read(name))
    return {"version": VERSION, "members": len(names), "bytes": len(actual), "sha256": sha(actual)}


def write(root: Path):
    manifest_path = root / "assets/asset-patch/manifest.json"
    before = manifest_path.read_bytes()
    manifest = json.loads(before)
    data = archive_bytes(build_entries(root, manifest))
    names = sorted(member(program) for program in PROGRAMS)
    destination = root / "assets/asset-patch/active" / ARCHIVE
    # Never rewrite an existing package, including one shared with another worktree.
    with destination.open("xb") as target:
        target.write(data)
    if manifest_path.read_bytes() != before:
        raise ValueError("Manifest changed during generation")
    manifest["cdn_version"] = VERSION
    manifest["patches"].append({
        "id": "pumpkin-candle-buff-cleanup-" + VERSION, "type": "patch",
        "name": "地狱南瓜蜡烛加攻清理修复",
        "description": "蜡烛加攻使用专用标识，死亡时仅移除对应的可驱散加攻；保留五重及南瓜战斗数值。离线验证，未经实战验收。",
        "version": VERSION, "depends_on": BASE_VERSION, "enabled": True,
        "candidate_only": True, "archive": ARCHIVE, "archive_size": len(data), "chain": [ARCHIVE],
        "archive_integrity": [{"name": ARCHIVE, "size": len(data), "sha256": sha(data),
                               "members": len(names), "files": names}],
        "files": names, "created_at": "2026-11-01",
    })
    manifest_path.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return verify(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Append the new repair; never overwrite an archive")
    args = parser.parse_args()
    print(json.dumps(write(ROOT) if args.write else verify(ROOT), ensure_ascii=False, indent=2))
