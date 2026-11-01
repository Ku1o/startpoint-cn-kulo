"""Build/check the narrow 1.4.354 Water Gerald ability-3 repair from the enabled chain."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
SALT = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy"

BASE_VERSION = "1.4.353"
VERSION = "1.4.354"
ARCHIVE = "pinball-1.4.353-1.4.354-1-gerald-fever-toggle.zip"

ABILITY_LP = "master/ability/ability.orderedmap"
CAS_LP = "master/string/custom_ability_string.orderedmap"
UNIQUE_COND_LP = "master/character/unique_condition.orderedmap"

ABILITY_KEY = "1299893"
EXPECTED_TOGGLE_ROWS = {4: ("184", "12998904"), 6: ("8", "12998905")}
CAS_KEY = "desc_override_white_wolf_gerald_aqua_3"
OLD_TEXT = "自身攻击力10倍的自适应伤害类型伤害"
NEW_TEXT = "自身攻击力10倍、伤害类型与队长相同的伤害"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def member(logical: str) -> str:
    digest = hashlib.sha1((logical + SALT).encode("utf-8")).hexdigest()
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def rawmap(raw: bytes) -> dict[str, bytes]:
    if len(raw) < 4:
        raise ValueError("Truncated orderedmap header")
    size = struct.unpack_from("<I", raw, 0)[0]
    if size <= 0 or size > len(raw) - 4:
        raise ValueError("Invalid orderedmap index size")
    decoder = zlib.decompressobj()
    index = decoder.decompress(raw[4 : 4 + size]) + decoder.flush()
    if not decoder.eof or decoder.unused_data or len(index) < 4:
        raise ValueError("Corrupt orderedmap index stream")
    count = struct.unpack_from("<I", index, 0)[0]
    if 4 + 8 * count > len(index):
        raise ValueError("Truncated orderedmap offset table")
    keyblob = index[4 + 8 * count :]
    rowblob = raw[4 + size :]
    rows: dict[str, bytes] = {}
    ke = re_ = 0
    for i in range(count):
        kn, rn = struct.unpack_from("<II", index, 4 + 8 * i)
        if not (ke <= kn <= len(keyblob) and re_ <= rn <= len(rowblob)):
            raise ValueError("Non-monotonic orderedmap offsets")
        key = keyblob[ke:kn].decode("utf-8")
        if key in rows:
            raise ValueError(f"Duplicate orderedmap key: {key}")
        rows[key] = rowblob[re_:rn]
        ke, re_ = kn, rn
    if ke != len(keyblob) or re_ != len(rowblob):
        raise ValueError("Trailing bytes in orderedmap")
    return rows


def packmap(rows: dict[str, bytes]) -> bytes:
    keys = bytearray()
    data = bytearray()
    pairs = []
    for key, chunk in rows.items():
        keys += key.encode("utf-8")
        data += chunk
        pairs.append((len(keys), len(data)))
    index = struct.pack("<I", len(rows)) + b"".join(struct.pack("<II", *p) for p in pairs) + keys
    compressed = zlib.compress(bytes(index))
    return struct.pack("<I", len(compressed)) + compressed + bytes(data)


def decode_leaf(chunk: bytes) -> str:
    if not chunk:
        return ""
    decoder = zlib.decompressobj()
    text = decoder.decompress(chunk) + decoder.flush()
    if not decoder.eof or decoder.unused_data:
        raise ValueError("Corrupt orderedmap leaf stream")
    return text.decode("utf-8")


def encode_leaf(text: str) -> bytes:
    return zlib.compress(text.encode("utf-8")) if text else b""


def parse_csv(text: str) -> list[list[str]]:
    return [row for row in csv.reader(io.StringIO(text)) if row]


def format_csv(rows: list[list[str]], trailing_newline: bool) -> str:
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\n").writerows(rows)
    out = buf.getvalue()
    return out if trailing_newline else out.rstrip("\n")


def read_effective(root: Path, manifest: dict, logical: str) -> bytes:
    name = member(logical)
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
    raise ValueError("Missing enabled resource: " + logical)


def verify_unique_conditions(payload: bytes) -> None:
    table = rawmap(payload)
    for uid in ("12998904", "12998905"):
        if uid not in table:
            raise ValueError(f"Missing unique_condition {uid}")
        rows = parse_csv(decode_leaf(table[uid]))
        if len(rows) != 1:
            raise ValueError(f"Expected single row for unique_condition {uid}")
        row = rows[0]
        if not row[0].startswith("wfx:3") or row[4] != "2" or row[9] != "false":
            raise ValueError(f"Unexpected unique_condition preimage for {uid}")


def rewrite_ability(payload: bytes) -> bytes:
    original = rawmap(payload)
    if ABILITY_KEY not in original:
        raise ValueError("Missing ability key 1299893")
    leaf_before = decode_leaf(original[ABILITY_KEY])
    rows = parse_csv(leaf_before)
    if len(rows) != 8 or any(r[0] != "white_wolf_gerald_aqua_3" for r in rows):
        raise ValueError("Unexpected ability 1299893 row structure")
    for idx, (trigger, uid) in EXPECTED_TOGGLE_ROWS.items():
        row = rows[idx]
        if (row[27], row[47], row[48], row[68]) != (trigger, "528", "0", uid):
            raise ValueError(f"Unexpected ability 1299893 row {idx} preimage")
        row[47] = "526"
    leaf_after = format_csv(rows, leaf_before.endswith("\n"))
    updated = dict(original)
    updated[ABILITY_KEY] = encode_leaf(leaf_after)
    packed = packmap(updated)
    readback = rawmap(packed)
    if list(readback) != list(original):
        raise ValueError("Ability orderedmap key order drifted")
    if any(readback[k] != original[k] for k in original if k != ABILITY_KEY):
        raise ValueError("Unrelated ability key bytes drifted")
    return packed


def rewrite_custom_ability_string(payload: bytes) -> bytes:
    original = rawmap(payload)
    if CAS_KEY not in original:
        raise ValueError(f"Missing custom_ability_string key {CAS_KEY}")
    leaf_before = decode_leaf(original[CAS_KEY])
    rows = parse_csv(leaf_before)
    if len(rows) != 1 or len(rows[0]) != 1:
        raise ValueError("Expected single-cell custom_ability_string entry")
    text = rows[0][0]
    if text.count(OLD_TEXT) != 1:
        raise ValueError("Unexpected custom_ability_string preimage")
    replaced = text.replace(OLD_TEXT, NEW_TEXT)
    if "自适应" in replaced:
        raise ValueError("Residual adaptive damage wording in custom_ability_string")
    leaf_after = format_csv([[replaced]], leaf_before.endswith("\n"))
    updated = dict(original)
    updated[CAS_KEY] = encode_leaf(leaf_after)
    packed = packmap(updated)
    readback = rawmap(packed)
    if list(readback) != list(original):
        raise ValueError("custom_ability_string key order drifted")
    if any(readback[k] != original[k] for k in original if k != CAS_KEY):
        raise ValueError("Unrelated custom_ability_string key bytes drifted")
    return packed


def build_entries(root: Path, manifest: dict) -> dict[str, bytes]:
    if manifest["cdn_version"] != BASE_VERSION:
        raise ValueError("Expected the reviewed 1.4.353 source chain")
    verify_unique_conditions(read_effective(root, manifest, UNIQUE_COND_LP))
    return {
        member(ABILITY_LP): rewrite_ability(read_effective(root, manifest, ABILITY_LP)),
        member(CAS_LP): rewrite_custom_ability_string(read_effective(root, manifest, CAS_LP)),
    }


def archive_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            target.writestr(info, data, compresslevel=9)
    raw = output.getvalue()
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("Archive exceeds 5 MiB limit")
    return raw


def verify(root: Path) -> dict:
    manifest = json.loads((root / "assets/asset-patch/manifest.json").read_bytes())
    return verify_manifest(root, manifest)


def verify_manifest(root: Path, manifest: dict) -> dict:
    matches = [index for index, patch in enumerate(manifest["patches"]) if patch["version"] == VERSION]
    if len(matches) != 1 or not matches[0]:
        raise ValueError("Expected exactly one installed 1.4.354 repair")
    index = matches[0]
    base = copy.deepcopy(manifest)
    patch = manifest["patches"][index]
    base["patches"] = base["patches"][:index]
    if base["patches"][-1]["version"] != BASE_VERSION:
        raise ValueError("Repair does not follow the reviewed 1.4.353 edge")
    base["cdn_version"] = BASE_VERSION
    expected_entries = build_entries(root, base)
    actual = (root / "assets/asset-patch/active" / ARCHIVE).read_bytes()
    if len(actual) > 5 * 1024 * 1024:
        raise ValueError("Archive exceeds 5 MiB limit")
    names = sorted(expected_entries)
    receipt = patch["archive_integrity"]
    if (patch["depends_on"] != BASE_VERSION or patch["archive"] != ARCHIVE
            or patch["chain"] != [ARCHIVE] or patch["files"] != names
            or patch["archive_size"] != len(actual) or len(receipt) != 1
            or receipt[0] != {"name": ARCHIVE, "size": len(actual), "sha256": sha(actual),
                              "members": len(names), "files": names}):
        raise ValueError("Repair archive/manifest differs from the scoped recipe")
    with zipfile.ZipFile(io.BytesIO(actual)) as source:
        if source.testzip() is not None or source.namelist() != names:
            raise ValueError("Repair ZIP integrity mismatch")
        target_keys = {member(ABILITY_LP): ABILITY_KEY, member(CAS_LP): CAS_KEY}
        for name in names:
            expected_rows = rawmap(expected_entries[name])
            actual_rows = rawmap(source.read(name))
            if list(actual_rows) != list(expected_rows):
                raise ValueError("Repair orderedmap key order or key set drifted")
            for key, expected_leaf in expected_rows.items():
                # Index/target compression and ZIP metadata may differ across zlib versions.
                # All unrelated leaves must retain their original compressed bytes.
                if key == target_keys[name]:
                    if decode_leaf(actual_rows[key]) != decode_leaf(expected_leaf):
                        raise ValueError("Repair target leaf text differs from the scoped recipe")
                elif actual_rows[key] != expected_leaf:
                    raise ValueError("Unrelated orderedmap leaf bytes drifted")
    return {"version": VERSION, "members": len(names), "bytes": len(actual), "sha256": sha(actual)}


def write(root: Path) -> dict:
    manifest_path = root / "assets/asset-patch/manifest.json"
    before = manifest_path.read_bytes()
    manifest = json.loads(before)
    entries = build_entries(root, manifest)
    data = archive_bytes(entries)
    names = sorted(entries)
    destination = root / "assets/asset-patch/active" / ARCHIVE
    with destination.open("xb") as target:
        target.write(data)
    if manifest_path.read_bytes() != before:
        raise ValueError("Manifest changed during generation")
    manifest["cdn_version"] = VERSION
    manifest["patches"].append({
        "id": "gerald-fever-toggle-" + VERSION,
        "type": "patch",
        "name": "水杰拉德能力3 Fever开关修复与描述修正",
        "description": "修复能力 1299893 在 Fever 进出时清理隐藏固有状态失效的问题（c47 528→526），并将文案修正为伤害类型与队长相同。离线验证，未经实战验收。",
        "version": VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "candidate_only": True,
        "archive": ARCHIVE,
        "archive_size": len(data),
        "chain": [ARCHIVE],
        "archive_integrity": [{
            "name": ARCHIVE,
            "size": len(data),
            "sha256": sha(data),
            "members": len(names),
            "files": names,
        }],
        "files": names,
        "created_at": "2026-11-01",
    })
    manifest_path.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return verify(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Append the new repair; never overwrite an archive")
    args = parser.parse_args()
    print(json.dumps(write(ROOT) if args.write else verify(ROOT), ensure_ascii=False, indent=2))
