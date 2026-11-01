"""Build/check the narrow 1.4.355 five-boss second-round tuning from the enabled chain."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/fantasy-gauntlet-mod-tools"))
from wf_dsl import _Parser as Amf3Parser, encode_amf3, parse_dsl
from wf_dsl_sig import validate_action_dsl

SALT = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy"
FIRST_TUNE_VERSION = "1.4.352"
BASE_VERSION = "1.4.354"
VERSION = "1.4.355"
ARCHIVE = "pinball-1.4.354-1.4.355-1-fiveboss-second-tune.zip"

ENTRANCE_PROGRAMS = (
    "battle/action/enemy/action/mod/five_boss_v3/fb3_buff$entrance",
    "battle/action/enemy/action/mod/five_boss_v3/fb3_buff$entrance_self",
)
PURGE_PROGRAM = "battle/action/enemy/action/mod/five_boss_v2/fb2_affix$purge_r1"
ENRAGE_PROGRAMS = (
    "battle/action/enemy/action/mod/five_boss_v2/fb2_affix$enrage_r0",
    "battle/action/enemy/action/mod/five_boss_v2/fb2_affix$enrage_r1",
)
BBQ_LP = "master/quest/boss_battle_quest.orderedmap"

OLD_MULTIPLIERS = (1.0, 0.81, 0.61, 0.41, 0.21, 0.01)
NEW_MULTIPLIERS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
FIRST_HP_MULTIPLIER = 0.35
HP_MULTIPLIER = 0.7
ATK_MULTIPLIER = 0.8


def ladder_values(multipliers: tuple[float, ...]) -> list[float]:
    resistances = [1.0 / m - 1.0 for m in multipliers]
    return [round(resistances[i + 1] - resistances[i], 4) for i in range(len(multipliers) - 1)]


OLD_LADDER = ladder_values(OLD_MULTIPLIERS)
NEW_LADDER = ladder_values(NEW_MULTIPLIERS)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fmt_num(value: float) -> str:
    return f"{value:.12f}".rstrip("0").rstrip(".")


def dsl_logical(program: str) -> str:
    return program + ".action.dsl.amf3.deflate"


def member(logical: str) -> str:
    digest = hashlib.sha1((logical + SALT).encode("utf-8")).hexdigest()
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def commands(tree, name: str):
    if isinstance(tree, list):
        if tree and tree[0] == name:
            yield tree
        for child in tree:
            yield from commands(child, name)


def inflate_complete(payload: bytes, wbits: int = zlib.MAX_WBITS) -> bytes:
    decoder = zlib.decompressobj(wbits)
    raw = decoder.decompress(payload) + decoder.flush()
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Incomplete or trailing compressed resource data")
    return raw


def decode_dsl(payload: bytes):
    raw = inflate_complete(payload, -15)
    # parse_dsl does not expose how many bytes its parser consumed.
    parser = Amf3Parser(raw)
    tree = parser.read_value()
    if parser.i != len(raw):
        raise ValueError("Trailing DSL AMF3 data")
    validate_action_dsl(tree)
    return tree


def encode_dsl(tree) -> bytes:
    validate_action_dsl(tree)
    encoded = encode_amf3(tree)
    if parse_dsl(encoded)["tree"] != tree:
        raise ValueError("DSL AMF3 roundtrip mismatch")
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(encoded) + compressor.flush()


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
    return inflate_complete(chunk).decode("utf-8") if chunk else ""


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


def verify_enrage_already_dispellable(root: Path, manifest: dict) -> None:
    for program in ENRAGE_PROGRAMS:
        tree = decode_dsl(read_effective(root, manifest, dsl_logical(program)))
        conds = list(commands(tree, "CreateCondition"))
        if len(conds) != 1:
            raise ValueError(f"Expected single CreateCondition in {program}")
        cond = conds[0]
        if cond[7] != "mod_fb2_enrage_atk" or cond[5] is not True:
            raise ValueError(f"Expected dispellable mod_fb2_enrage_atk on base chain in {program}")


def rewrite_entrance(program: str, payload: bytes) -> bytes:
    if program not in ENTRANCE_PROGRAMS:
        raise ValueError("Unexpected entrance program")
    tree = copy.deepcopy(decode_dsl(payload))
    seen: dict[int, float] = {}
    for stmt in tree[11][1]:
        if stmt[0] != "Command" or stmt[1][0] != "CreateCondition":
            continue
        cond = stmt[1]
        key = cond[7]
        if key.startswith("fb3_def_") and key != "fb3_def_down":
            idx = int(key.rsplit("_", 1)[1])
            if idx not in range(5) or idx in seen:
                raise ValueError(f"Unexpected defense slot {key} in {program}")
            if cond[5] is not True or cond[2][0][0] != "ACToleranceOfElement":
                raise ValueError(f"Unexpected defense condition shape in {program}")
            cur = cond[2][0][3]
            if cur != [{"min": OLD_LADDER[idx], "max": OLD_LADDER[idx]}]:
                raise ValueError(f"Unexpected entrance ladder preimage for {key} in {program}")
            cond[2][0][3] = [{"min": NEW_LADDER[idx], "max": NEW_LADDER[idx]}]
            seen[idx] = NEW_LADDER[idx]
    if sorted(seen) != [0, 1, 2, 3, 4]:
        raise ValueError(f"Expected 5 defense layers in {program}")
    return encode_dsl(tree)


def rewrite_purge(payload: bytes) -> bytes:
    tree = copy.deepcopy(decode_dsl(payload))
    removed = []

    def strip(node):
        if isinstance(node, list):
            kept = []
            for item in node:
                if (isinstance(item, list) and len(item) == 2 and item[0] == "Command"
                        and isinstance(item[1], list) and item[1] and item[1][0] == "SubtractSkillPoint"):
                    removed.append(item[1])
                else:
                    kept.append(item)
            node[:] = kept
            for item in node:
                strip(item)

    strip(tree)
    if removed != [["SubtractSkillPoint", 0, [{"min": 1, "max": 1}]]]:
        raise ValueError("Unexpected purge_r1 SubtractSkillPoint preimage")
    if list(commands(tree, "SubtractSkillPoint")):
        raise ValueError("Residual SubtractSkillPoint in purge_r1")
    return encode_dsl(tree)


def extract_group99_rows(payload: bytes) -> dict[str, list[str]]:
    top = rawmap(payload)
    ch1 = rawmap(top["1"])
    group99 = rawmap(ch1["99"])
    parsed: dict[str, list[str]] = {}
    for qid, chunk in group99.items():
        rows = parse_csv(decode_leaf(chunk))
        if len(rows) != 1:
            raise ValueError(f"Expected single CSV row for five-boss quest {qid}")
        parsed[qid] = rows[0]
    return parsed


def rewrite_boss_battle_quest(payload: bytes, pre_first_tune_payload: bytes | None = None) -> bytes:
    top_orig = rawmap(payload)
    if "1" not in top_orig:
        raise ValueError("Missing chapter 1 in boss_battle_quest")
    ch1_orig = rawmap(top_orig["1"])
    if "99" not in ch1_orig:
        raise ValueError("Missing five-boss group 99 in boss_battle_quest")
    group_orig = rawmap(ch1_orig["99"])
    if len(group_orig) != 39:
        raise ValueError(f"Expected 39 five-boss quests, got {len(group_orig)}")

    pre_rows = extract_group99_rows(pre_first_tune_payload) if pre_first_tune_payload is not None else None
    if pre_rows is not None and set(pre_rows) != set(group_orig):
        raise ValueError("Five-boss quest key set drifted since pre-1.4.352 baseline")

    group_updated = dict(group_orig)
    for qid in sorted(group_orig, key=int):
        leaf_before = decode_leaf(group_orig[qid])
        rows = parse_csv(leaf_before)
        if len(rows) != 1 or not rows[0][2].startswith("五重决战"):
            raise ValueError(f"Unexpected five-boss quest row for {qid}")
        row = rows[0]
        if row[102] not in ("1.5", "2"):
            raise ValueError(f"Unexpected boss ATK preimage on quest {qid}: {row[102]}")
        if pre_rows is not None:
            pre_row = pre_rows[qid]
            expected_base_hp = fmt_num(float(pre_row[99]) * FIRST_HP_MULTIPLIER)
            if row[99] != expected_base_hp or row[102] != pre_row[102]:
                raise ValueError(f"Unexpected preimage vs pre-1.4.352 baseline on quest {qid}")
        row[99] = fmt_num(float(row[99]) * HP_MULTIPLIER)
        row[102] = fmt_num(float(row[102]) * ATK_MULTIPLIER)
        group_updated[qid] = encode_leaf(format_csv([row], leaf_before.endswith("\n")))

    ch1_updated = dict(ch1_orig)
    ch1_updated["99"] = packmap(group_updated)
    top_updated = dict(top_orig)
    top_updated["1"] = packmap(ch1_updated)
    packed = packmap(top_updated)

    top_rb = rawmap(packed)
    if list(top_rb) != list(top_orig) or any(top_rb[k] != top_orig[k] for k in top_orig if k != "1"):
        raise ValueError("Unrelated chapters in boss_battle_quest drifted")
    ch1_rb = rawmap(top_rb["1"])
    if list(ch1_rb) != list(ch1_orig) or any(ch1_rb[k] != ch1_orig[k] for k in ch1_orig if k != "99"):
        raise ValueError("Unrelated groups in boss_battle_quest chapter 1 drifted")
    group_rb = rawmap(ch1_rb["99"])
    if list(group_rb) != list(group_orig):
        raise ValueError("Group 99 quest key order drifted")
    return packed


def slice_before_version(manifest: dict, target_version: str) -> dict:
    matches = [i for i, patch in enumerate(manifest["patches"]) if patch["version"] == target_version]
    if len(matches) != 1 or not matches[0]:
        raise ValueError(f"Expected unique patch version {target_version} in manifest")
    sliced = copy.deepcopy(manifest)
    sliced["patches"] = sliced["patches"][: matches[0]]
    sliced["cdn_version"] = sliced["patches"][-1]["version"]
    return sliced


def build_entries(root: Path, manifest: dict) -> dict[str, bytes]:
    if manifest["cdn_version"] != BASE_VERSION:
        raise ValueError("Expected the reviewed 1.4.354 source chain")
    verify_enrage_already_dispellable(root, manifest)
    pre_first_tune = slice_before_version(manifest, FIRST_TUNE_VERSION)
    pre_bbq = read_effective(root, pre_first_tune, BBQ_LP)
    entries: dict[str, bytes] = {}
    for program in ENTRANCE_PROGRAMS:
        lp = dsl_logical(program)
        entries[member(lp)] = rewrite_entrance(program, read_effective(root, manifest, lp))
    purge_lp = dsl_logical(PURGE_PROGRAM)
    entries[member(purge_lp)] = rewrite_purge(read_effective(root, manifest, purge_lp))
    entries[member(BBQ_LP)] = rewrite_boss_battle_quest(read_effective(root, manifest, BBQ_LP), pre_bbq)
    return entries


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


def verify_boss_battle_quest(actual: bytes, expected: bytes) -> None:
    """Allow target/index compression changes while preserving all other raw blocks."""
    for key, label in (("1", "chapters"), ("99", "groups")):
        actual_rows = rawmap(actual)
        expected_rows = rawmap(expected)
        if (list(actual_rows) != list(expected_rows)
                or any(actual_rows[k] != expected_rows[k] for k in expected_rows if k != key)):
            raise ValueError(f"Unrelated boss_battle_quest {label} drifted")
        actual, expected = actual_rows[key], expected_rows[key]
    actual_rows = rawmap(actual)
    expected_rows = rawmap(expected)
    if list(actual_rows) != list(expected_rows):
        raise ValueError("Group 99 quest key order drifted")
    for qid in expected_rows:
        if decode_leaf(actual_rows[qid]) != decode_leaf(expected_rows[qid]):
            raise ValueError(f"Five-boss quest {qid} differs from the scoped recipe")


def verify_manifest(root: Path, manifest: dict) -> dict:
    matches = [index for index, patch in enumerate(manifest["patches"]) if patch["version"] == VERSION]
    if len(matches) != 1 or not matches[0]:
        raise ValueError("Expected exactly one installed 1.4.355 five-boss edge")
    index = matches[0]
    base = copy.deepcopy(manifest)
    patch = manifest["patches"][index]
    base["patches"] = base["patches"][:index]
    if base["patches"][-1]["version"] != BASE_VERSION:
        raise ValueError("Edge 1.4.355 does not follow the reviewed 1.4.354 edge")
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
        raise ValueError("Five-boss 1.4.355 archive/manifest differs from the scoped recipe")
    bbq_member = member(BBQ_LP)
    with zipfile.ZipFile(io.BytesIO(actual)) as source:
        if source.testzip() is not None or source.namelist() != names:
            raise ValueError("Five-boss 1.4.355 ZIP integrity mismatch")
        for name in names:
            payload = source.read(name)
            if name == bbq_member:
                verify_boss_battle_quest(payload, expected_entries[name])
            elif decode_dsl(payload) != decode_dsl(expected_entries[name]):
                raise ValueError(f"Five-boss DSL {name} differs from the scoped recipe")
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
        "id": "fiveboss-second-tune-" + VERSION,
        "type": "patch",
        "name": "五重二轮减难与P2去清槽调整",
        "description": "五重防御up阶梯调整为50%起（50/60/70/80/90/100%），39关Boss血量×0.70、攻击×0.80，P2入场不再清空技能槽；狂暴可驱散已在1.4.352生效，不重复下发。离线验证，未经实战验收。",
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
    parser.add_argument("--write", action="store_true", help="Append the new edge; never overwrite an archive")
    args = parser.parse_args()
    print(json.dumps(write(ROOT) if args.write else verify(ROOT), ensure_ascii=False, indent=2))
