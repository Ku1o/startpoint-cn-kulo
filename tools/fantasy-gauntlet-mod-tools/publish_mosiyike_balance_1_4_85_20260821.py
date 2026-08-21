#!/usr/bin/env python3
"""Build the approved Mosiyike/balance graft as one active 1.4.84 -> 1.4.85 patch.

The share archive is anchored to another CDN chain.  This builder treats its
scripts and notes as untrusted documentation, reads only the row/asset payloads,
reconstructs the local terminal state from ``assets/asset-patch/active``, and
publishes a selective forward edge.  It never reads ``.cdn`` and never touches
the runtime mirror.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import io
import json
import math
import os
import shutil
import sys
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

import wf_assets
import wf_atf
import wf_dsl
import wf_mod_tool as core


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
SHARE_ARCHIVE = Path(r"F:\wfshare-mosiyike0820-graft-1.4.349-to-1.4.350.zip")
SHARE_SHA256 = "c03e5ddf8a3654ef3615acde03dd4fc553aa57f59e8b7f2df0b294133b3df353"
SHARE_PREFIX = "wfshare-1.4.349-to-1.4.350-graft"
BANNER_INPUT = (
    SOURCE_ROOT
    / "tools/fantasy-gauntlet-mod-tools/assets/gauntlet-hub-banner/gauntlet_hub_banner_1000x184.png"
)
BANNER_SHA256 = "f8b183b2ffd2cf035f41491d3e92e0bed01ad0ce03bd09495bf8b5e39b8aac36"
BANNER_LOGICAL = "quest/event/banner/rush_event/mod_gauntlet_hub_banner_001.png"

BASE_VERSION = "1.4.84"
PATCH_VERSION = "1.4.85"
PATCH_ID = "mosiyike-balance-ios-1.4.85"
ARCHIVE_NAME = "pinball-1.4.84-1.4.85-1-0821-mosiyike-balance-ios.zip"

CLIENT_PAYLOAD_NAME = f"{SHARE_PREFIX}/client-tables/client_tables_payload.json"
CLIENT_MANIFEST_NAME = f"{SHARE_PREFIX}/client-tables/client_tables_manifest.json"
SERVER_ROWS_NAME = f"{SHARE_PREFIX}/server-data/mosiyike0820_rows.json"
SERVER_POOL_NAME = f"{SHARE_PREFIX}/server-data/mosiyike0820_abyss_pool_rows.json"
REPORT_NAME = f"{SHARE_PREFIX}/report.json"

ABILITY_LOGICAL = "master/ability/ability.orderedmap"
LEADER_LOGICAL = "master/ability/leader_ability.orderedmap"
CHARACTER_TEXT_LOGICAL = "master/character/character_text.orderedmap"
ACTION_SKILL_LOGICAL = "master/skill/action_skill.orderedmap"
GACHA_LOGICAL = "master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap"
GACHA_KEY = "cnmod_abyss_limited_gacha_character_5"
ABYSS_GACHA_ID = "990001"

GINOVI_SKILLS = [
    f"battle/action/skill/action/rare5/ginovi$ginovi_{level}.action.dsl.amf3.deflate"
    for level in (1, 2)
]
GINOVI_POWER_FLIPS = [
    f"battle/action/power_flip/action/override/ginovi_pf$ginovi_pf_lv{level}.action.dsl.amf3.deflate"
    for level in (1, 2, 3)
]
GOLDEN_DRAGON_SKILLS = [
    f"battle/action/skill/action/rare5/golden_dragon_jr$golden_dragon_jr_{level}.action.dsl.amf3.deflate"
    for level in (1, 2)
]
DARKNESS_DRAGON_SKILLS = [
    f"battle/action/skill/action/rare4/darkness_dragon$darkness_dragon_{level}.action.dsl.amf3.deflate"
    for level in (1, 2)
]
EXTRA_ACTIVE_DSLS = (
    GINOVI_SKILLS
    + GINOVI_POWER_FLIPS
    + GOLDEN_DRAGON_SKILLS
    + DARKNESS_DRAGON_SKILLS
)

CLAUDE_POISON = {
    "battle/action/skill/action/rare5/claude_wolf_assassin_ex$claude_wolf_assassin_ex_1.action.dsl.amf3.deflate": (1, 25_000_000, 5_000_000),
    "battle/action/skill/action/rare5/claude_wolf_assassin_ex$claude_wolf_assassin_ex_2.action.dsl.amf3.deflate": (1, 25_000_000, 5_000_000),
    "battle/action/power_flip/action/override/claude_wolf_assassin_ex_pf$claude_wolf_assassin_ex_pf_lv1.action.dsl.amf3.deflate": (1, 5_000_000, 1_000_000),
    "battle/action/power_flip/action/override/claude_wolf_assassin_ex_pf$claude_wolf_assassin_ex_pf_lv2.action.dsl.amf3.deflate": (3, 15_000_000, 3_000_000),
    "battle/action/power_flip/action/override/claude_wolf_assassin_ex_pf$claude_wolf_assassin_ex_pf_lv3.action.dsl.amf3.deflate": (5, 25_000_000, 5_000_000),
}

MOSIYIKE_POWER_FLIPS = {
    1: (
        "battle/action/power_flip/action/override/mosiyike_pf$mosiyike_pf_lv1.action.dsl.amf3.deflate",
        2,
        12.5,
        7.5,
        15.0,
    ),
    2: (
        "battle/action/power_flip/action/override/mosiyike_pf$mosiyike_pf_lv2.action.dsl.amf3.deflate",
        5,
        8.28,
        6.0,
        30.0,
    ),
    3: (
        "battle/action/power_flip/action/override/mosiyike_pf$mosiyike_pf_lv3.action.dsl.amf3.deflate",
        10,
        6.44,
        4.5,
        45.0,
    ),
}

IOS_CUTINS = [
    f"character/mosiyike/ui/skill_cutin_{level}.atf.deflate"
    for level in (0, 1)
]


class PublishError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_member(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def member_name(logical: str, root_name: str = "upload") -> str:
    digest = core.sha1_path(logical)
    return f"production/{root_name}/{digest[:2]}/{digest[2:]}"


def table_member(logical: str) -> str:
    return member_name(logical, "upload")


def active_archives(root: Path, manifest: dict[str, Any]) -> list[Path]:
    result: list[Path] = []
    for patch in manifest.get("patches", []):
        if not patch.get("enabled", True):
            continue
        names: list[str] = []
        if patch.get("archive"):
            names.append(str(patch["archive"]))
        names.extend(str(value) for value in patch.get("chain", []))
        seen: set[str] = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            path = root / "assets/asset-patch/active" / name
            if not path.is_file():
                raise PublishError(f"active manifest archive is missing: {path}")
            result.append(path)
    return result


def terminal_members(
    root: Path,
    manifest: dict[str, Any],
    wanted: set[str],
) -> tuple[dict[str, bytes], dict[str, str]]:
    values: dict[str, bytes] = {}
    sources: dict[str, str] = {}
    for archive_path in active_archives(root, manifest):
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            for member in wanted & names:
                values[member] = archive.read(member)
                sources[member] = archive_path.name
    return values, sources


def read_manifest() -> tuple[dict[str, Any], bytes]:
    path = SOURCE_ROOT / "assets/asset-patch/manifest.json"
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if value.get("cdn_version") != BASE_VERSION:
        raise PublishError(f"manifest is not at {BASE_VERSION}: {path}")
    if any(entry.get("id") == PATCH_ID for entry in value.get("patches", [])):
        raise PublishError(f"patch is already present: {path}")
    target = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
    if target.exists():
        raise PublishError(f"target archive already exists: {target}")
    return value, raw


def read_share() -> dict[str, Any]:
    if not SHARE_ARCHIVE.is_file():
        raise PublishError(f"share archive is missing: {SHARE_ARCHIVE}")
    if sha256_file(SHARE_ARCHIVE) != SHARE_SHA256:
        raise PublishError("share archive hash drifted")
    with zipfile.ZipFile(SHARE_ARCHIVE) as outer:
        required = {
            CLIENT_PAYLOAD_NAME,
            CLIENT_MANIFEST_NAME,
            SERVER_ROWS_NAME,
            SERVER_POOL_NAME,
            REPORT_NAME,
        }
        missing = required - set(outer.namelist())
        if missing:
            raise PublishError(f"share archive lacks required data: {sorted(missing)}")
        payload = json.loads(outer.read(CLIENT_PAYLOAD_NAME))
        payload_manifest = json.loads(outer.read(CLIENT_MANIFEST_NAME))
        server_rows = json.loads(outer.read(SERVER_ROWS_NAME))
        server_pool = json.loads(outer.read(SERVER_POOL_NAME))
        report = json.loads(outer.read(REPORT_NAME))
        assets: dict[str, bytes] = {}
        for output in report.get("outputs", []):
            nested_name = f"{SHARE_PREFIX}/{output['path']}"
            raw = outer.read(nested_name)
            if len(raw) != int(output["size"]) or sha256_bytes(raw) != output["sha256"]:
                raise PublishError(f"nested share archive drifted: {nested_name}")
            with zipfile.ZipFile(io.BytesIO(raw)) as nested:
                for info in nested.infolist():
                    if info.is_dir():
                        continue
                    name = normalize_member(info.filename)
                    if not name.startswith(
                        (
                            "production/upload/",
                            "production/medium_upload/",
                            "production/android_upload/",
                        )
                    ):
                        raise PublishError(f"unsupported package asset root: {name}")
                    value = nested.read(info)
                    if name in assets and assets[name] != value:
                        raise PublishError(f"nested share archives disagree: {name}")
                    assets[name] = value
    if report.get("payload_tables") != 21 or report.get("payload_rows") != 34:
        raise PublishError("share row count drifted")
    if len(payload) != 21 or sum(len(rows) for rows in payload.values()) != 34:
        raise PublishError("share payload shape drifted")
    if len(assets) != 84:
        raise PublishError(f"share asset count drifted: {len(assets)}")
    if set(payload) != set(payload_manifest):
        raise PublishError("share payload/manifest table set disagrees")
    for logical, rows in payload.items():
        if set(rows) != set(payload_manifest[logical]["keys"]):
            raise PublishError(f"share row manifest disagrees: {logical}")
    return {
        "payload": payload,
        "payload_manifest": payload_manifest,
        "server_rows": server_rows,
        "server_pool": server_pool,
        "report": report,
        "assets": assets,
    }


def walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def set_range(value: Any, number: float | int) -> None:
    if not isinstance(value, dict) or set(value) != {"min", "max"}:
        raise PublishError(f"not a numeric range: {value!r}")
    value["min"] = number
    value["max"] = number


def decode_dsl(raw_deflate: bytes, logical: str) -> Any:
    try:
        return wf_dsl.parse_dsl(zlib.decompress(raw_deflate, -15))["tree"]
    except Exception as exc:
        raise PublishError(f"cannot decode DSL {logical}: {exc}") from exc


def encode_dsl(tree: Any, logical: str) -> bytes:
    encoded = wf_dsl.encode_amf3(tree)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    output = compressor.compress(encoded) + compressor.flush()
    readback = decode_dsl(output, logical)
    if readback != tree:
        raise PublishError(f"DSL tree round trip failed: {logical}")
    return output


def flat_row(raw_row: bytes, logical: str, key: str) -> list[list[str]]:
    try:
        return core.read_csv_lines(zlib.decompress(raw_row).decode("utf-8"))
    except Exception as exc:
        raise PublishError(f"cannot decode flat row {logical}/{key}: {exc}") from exc


def build_flat_row(rows: list[list[str]]) -> bytes:
    return zlib.compress(core.write_csv_lines(rows).encode("utf-8"))


def raw_rows(raw: bytes, logical: str) -> tuple[core.OrderedMap, dict[str, bytes]]:
    ordered = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    return ordered, dict(zip(ordered.keys, ordered.rows))


def edit_mosiyike_ability(key: str, raw_row: bytes) -> bytes:
    rows = flat_row(raw_row, ABILITY_LOGICAL, key)
    if key == "1499972":
        if len(rows) != 5 or rows[4][109] != "413" or rows[4][113:115] != ["50000", "50000"]:
            raise PublishError("149997 ability 2 row shape drifted")
        rows[4][113:115] = ["15000", "15000"]
    elif key == "1499973":
        if len(rows) != 4 or rows[0][27] != "23" or rows[0][47] != "211" or rows[0][35] != "0":
            raise PublishError("149997 ability 3 row shape drifted")
        rows[0][35] = "1800"
    elif key == "1499975":
        if (
            len(rows) != 4
            or rows[2][27] != "23"
            or rows[2][47] != "211"
            or rows[2][51:53] != ["20000", "20000"]
        ):
            raise PublishError("149997 ability 5 team-gauge row drifted")
        del rows[2]
    return build_flat_row(rows)


def rebuild_inner_text_row(
    raw_inner: bytes,
    logical: str,
    replacements: dict[str, tuple[str, str]],
) -> bytes:
    values = core.read_orderedmap_file_from_bytes(raw_inner)
    keys = list(values)
    for key, (before, after) in replacements.items():
        if key not in values or values[key].count(before) != 1:
            raise PublishError(f"inner text replacement drifted: {logical}/{key}")
        values[key] = values[key].replace(before, after)
    ordered = core.OrderedMap(
        logical,
        keys,
        [values[key].encode("utf-8") for key in keys],
        Path(logical),
    )
    output = core.build_orderedmap(ordered)
    check = core.read_orderedmap_file_from_bytes(output)
    if check != values:
        raise PublishError(f"inner text readback failed: {logical}")
    return output


def upsert_table_rows(
    raw: bytes,
    logical: str,
    incoming: dict[str, bytes],
) -> tuple[bytes, list[str], list[str]]:
    current = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    keys = list(current.keys)
    rows = list(current.rows)
    positions = {key: index for index, key in enumerate(keys)}
    added: list[str] = []
    changed: list[str] = []
    for key, value in incoming.items():
        if key in positions:
            index = positions[key]
            if rows[index] != value:
                rows[index] = value
                changed.append(key)
        else:
            positions[key] = len(keys)
            keys.append(key)
            rows.append(value)
            added.append(key)
    current.keys = keys
    current.rows = rows
    output = core.build_orderedmap_raw_rows(current)
    check = core.read_orderedmap_raw_rows_from_bytes(output, logical)
    check_rows = dict(zip(check.keys, check.rows))
    for key, value in incoming.items():
        if check_rows.get(key) != value:
            raise PublishError(f"table graft readback failed: {logical}/{key}")
    return output, added, changed


def build_client_tables(
    terminal: dict[str, bytes],
    share: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, Any], bytes]:
    package_payload: dict[str, dict[str, str]] = share["payload"]
    output: dict[str, bytes] = {}
    effects: dict[str, dict[str, list[str]]] = {}
    final_gacha_row = b""
    for logical, encoded_rows in package_payload.items():
        member = table_member(logical)
        if member not in terminal:
            raise PublishError(f"active terminal lacks client table: {logical}")
        incoming = {
            key: base64.b64decode(encoded)
            for key, encoded in encoded_rows.items()
        }
        if logical == ABILITY_LOGICAL:
            excluded = incoming.pop("1299972", None)
            if excluded is None:
                raise PublishError("dangerous 129997 ability 2 row is missing from package")
            for key in ("1499972", "1499973", "1499975"):
                incoming[key] = edit_mosiyike_ability(key, incoming[key])
        elif logical == CHARACTER_TEXT_LOGICAL:
            ordered, current_rows = raw_rows(terminal[member], logical)
            del ordered
            ginovi = flat_row(current_rows["169999"], logical, "169999")
            if len(ginovi) != 1:
                raise PublishError("169999 character text row shape drifted")
            text = core.write_csv_lines(ginovi)
            if text.count("最大生命值15%的护盾") != 2:
                raise PublishError("169999 character text barrier wording drifted")
            text = text.replace("最大生命值15%的护盾", "最大生命值10%的护盾")
            incoming["169999"] = zlib.compress(text.encode("utf-8"))
        elif logical == ACTION_SKILL_LOGICAL:
            ordered, current_rows = raw_rows(terminal[member], logical)
            del ordered
            incoming["ginovi"] = rebuild_inner_text_row(
                current_rows["ginovi"],
                f"{logical}/ginovi",
                {
                    "1": ("最大生命值15%的护盾", "最大生命值10%的护盾"),
                    "2": ("最大生命值15%的护盾", "最大生命值10%的护盾"),
                },
            )
        candidate, added, changed = upsert_table_rows(terminal[member], logical, incoming)
        if candidate == terminal[member]:
            raise PublishError(f"approved client table produced no change: {logical}")
        output[member] = candidate
        effects[logical] = {"added": added, "changed": changed}
        if logical == GACHA_LOGICAL:
            final_gacha_row = incoming[GACHA_KEY]

    if len(output) != 21 or len(effects) != 21:
        raise PublishError(f"changed client-table count drifted: {len(output)}")
    ability_effect = effects[ABILITY_LOGICAL]
    if "1299972" in ability_effect["added"] + ability_effect["changed"]:
        raise PublishError("dangerous 129997 ability 2 line leaked into final table")
    if set(ability_effect["added"] + ability_effect["changed"]) != {
        "1499971", "1499972", "1499973", "1499974", "1499975", "1499976"
    }:
        raise PublishError(f"149997 ability graft set drifted: {ability_effect}")
    return output, effects, final_gacha_row


def patch_claude_poison(assets: dict[str, bytes]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for logical, (expected_count, package_strength, target_strength) in CLAUDE_POISON.items():
        member = member_name(logical)
        if member not in assets:
            raise PublishError(f"share lacks Claude poison DSL: {logical}")
        tree = decode_dsl(assets[member], logical)
        nodes = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "ACPoison"
        ]
        if len(nodes) != expected_count:
            raise PublishError(f"Claude poison node count drifted: {logical}: {len(nodes)}")
        for node in nodes:
            if node[2] != [{"min": package_strength, "max": package_strength}]:
                raise PublishError(f"Claude package poison strength drifted: {logical}: {node!r}")
            set_range(node[2][0], target_strength)
        assets[member] = encode_dsl(tree, logical)
        report[logical] = {
            "nodes": len(nodes),
            "package_strength": package_strength,
            "target_strength": target_strength,
        }
    return report


def patch_mosiyike_power_flips(assets: dict[str, bytes]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for level, (logical, expected_hits, package_per_hit, per_hit, total) in MOSIYIKE_POWER_FLIPS.items():
        member = member_name(logical)
        if member not in assets:
            raise PublishError(f"share lacks Mosiyike PF DSL: {logical}")
        tree = decode_dsl(assets[member], logical)
        attacks = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
        ]
        durations = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "ACAttackPoint"
        ]
        if len(attacks) != expected_hits or len(durations) != 1:
            raise PublishError(
                f"Mosiyike PF shape drifted: lv{level}: hits={len(attacks)} duration={len(durations)}"
            )
        for node in attacks:
            before = node[6][0]
            if not (
                math.isclose(float(before["min"]), package_per_hit, abs_tol=1e-9)
                and math.isclose(float(before["max"]), package_per_hit, abs_tol=1e-9)
            ):
                raise PublishError(f"Mosiyike PF package multiplier drifted: {logical}")
            set_range(node[6][0], per_hit)
        if not math.isclose(per_hit * len(attacks), total, abs_tol=1e-9):
            raise PublishError(f"Mosiyike PF target total arithmetic failed: lv{level}")
        assets[member] = encode_dsl(tree, logical)
        report[f"lv{level}"] = {
            "duration_frames": durations[0][1][0]["min"],
            "hits": len(attacks),
            "per_hit": per_hit,
            "total": total,
        }
    return report


def patch_ginovi_power_flip(raw: bytes, logical: str, level: int) -> tuple[bytes, dict[str, Any]]:
    tree = decode_dsl(raw, logical)
    attacks = [
        node for node in walk(tree)
        if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
    ]
    durations = [
        node for node in walk(tree)
        if isinstance(node, list) and node and node[0] == "ACAttackPoint"
    ]
    spec = {
        1: (4, 20.0, 150, 20.0, 5.0, 25.0),
        2: (6, 30.0, 180, 25.0, 10.0, 35.0),
        3: (10, 40.0, 240, 45.0, 15.0, 60.0),
    }[level]
    expected_hits, mistaken_duration, restored_duration, followup_total, pf_body, combined = spec
    if len(attacks) != expected_hits or len(durations) != 1:
        raise PublishError(f"Ginovi PF shape drifted: lv{level}")
    if durations[0][1] != [{"min": mistaken_duration, "max": mistaken_duration}]:
        raise PublishError(f"Ginovi ACAttackPoint duration drifted: lv{level}: {durations[0]!r}")
    set_range(durations[0][1][0], restored_duration)
    per_hit = followup_total / expected_hits
    for node in attacks:
        if node[6] != [{"min": 5.0, "max": 5.0}]:
            raise PublishError(f"Ginovi skill-followup multiplier drifted: lv{level}")
        set_range(node[6][0], per_hit)
    if not math.isclose(pf_body + per_hit * expected_hits, combined, abs_tol=1e-9):
        raise PublishError(f"Ginovi combined PF arithmetic failed: lv{level}")
    return encode_dsl(tree, logical), {
        "restored_duration_frames": restored_duration,
        "pf_body": pf_body,
        "skill_followup_hits": expected_hits,
        "skill_followup_per_hit": per_hit,
        "skill_followup_total": followup_total,
        "combined_total": combined,
    }


def patch_ginovi_skill(raw: bytes, logical: str) -> tuple[bytes, dict[str, Any]]:
    tree = decode_dsl(raw, logical)
    barriers = [
        node for node in walk(tree)
        if isinstance(node, list) and node and node[0] == "CreateBarrier"
    ]
    values = sorted(float(node[2][0]["min"]) for node in barriers)
    if values != [0.15, 0.6]:
        raise PublishError(f"Ginovi barrier shape drifted: {logical}: {values}")
    per_cast = next(node for node in barriers if math.isclose(float(node[2][0]["min"]), 0.15))
    first_only = next(node for node in barriers if math.isclose(float(node[2][0]["min"]), 0.6))
    set_range(per_cast[2][0], 0.10)

    first_guards = [
        node for node in walk(tree)
        if isinstance(node, list)
        and node
        and node[0] == "ConditionalsConditionAccumulationNumber"
        and node[1] == ["DCUnique", 169998]
        and node[2] == 1
    ]
    if len(first_guards) != 1:
        raise PublishError(f"Ginovi first-cast guard drifted: {logical}")
    guard = first_guards[0]
    guarded_nodes = list(walk(guard[4]))
    if first_only not in guarded_nodes:
        raise PublishError(f"Ginovi 60% barrier escaped first-cast branch: {logical}")
    hp_costs = [
        node for node in guarded_nodes
        if isinstance(node, list) and node and node[0] == "CreateRatioAttack"
    ]
    markers = [
        node for node in guarded_nodes
        if isinstance(node, list) and node and node[0] == "ACUnique" and node[1] == 169998
    ]
    if len(hp_costs) != 1 or hp_costs[0][3] != [{"min": 0.95, "max": 0.95}] or len(markers) != 1:
        raise PublishError(f"Ginovi first-cast pact block drifted: {logical}")
    if first_only in list(walk(guard[3])):
        raise PublishError(f"Ginovi 60% barrier leaked into repeat branch: {logical}")

    tolerance = [
        node for node in walk(tree)
        if isinstance(node, list)
        and node
        and node[0] == "ACToleranceOfElement"
        and node[2] == 6
    ]
    if len(tolerance) != 1:
        raise PublishError(f"Ginovi dark-resistance node drifted: {logical}")
    node = tolerance[0]
    if (
        node[1] != [{"min": 600, "max": 600}]
        or node[3] != [{"min": -0.25, "max": -0.25}]
        or node[4] != [{"min": 1, "max": 1}]
    ):
        raise PublishError(f"Ginovi dark-resistance baseline drifted: {logical}: {node!r}")
    set_range(node[3][0], -0.15)
    return encode_dsl(tree, logical), {
        "per_cast_barrier": 0.10,
        "first_cast_barrier": 0.60,
        "first_cast_hp_cost": 0.95,
        "first_cast_marker": 169998,
        "dark_resistance": -0.15,
        "dark_resistance_seconds": 10,
        "dark_resistance_cap": 1,
    }


def patch_dual_resistance_skill(
    raw: bytes,
    logical: str,
    value: float,
    stack_cap: int,
    damage_per_hit: float | None,
    expected_hits: int | None,
    preserve_damage: list[float] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    tree = decode_dsl(raw, logical)
    tolerance = [
        node for node in walk(tree)
        if isinstance(node, list)
        and node
        and node[0] == "ACToleranceOfElement"
        and node[2] in (5, 6)
    ]
    if sorted(int(node[2]) for node in tolerance) != [5, 6]:
        raise PublishError(f"dual-resistance node shape drifted: {logical}")
    apply_counts: list[float] = []
    for node in tolerance:
        set_range(node[3][0], value)
        set_range(node[4][0], stack_cap)
        parents = [
            parent for parent in walk(tree)
            if isinstance(parent, list)
            and parent
            and parent[0] == "CreateCondition"
            and node in list(walk(parent))
        ]
        if len(parents) != 1:
            raise PublishError(f"dual-resistance parent shape drifted: {logical}")
        apply_counts.append(float(parents[0][11][0]["min"]))
    if apply_counts != [2.0, 2.0]:
        raise PublishError(f"dual-resistance apply-count drifted: {logical}: {apply_counts}")

    attacks = [
        node for node in walk(tree)
        if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
    ]
    damage_report: dict[str, Any]
    if damage_per_hit is not None:
        if len(attacks) != 1:
            raise PublishError(f"Golden Dragon damage node shape drifted: {logical}")
        max_hits = [
            node for node in walk(tree)
            if isinstance(node, list)
            and node
            and node[0] == "CalculatedUsingMaxNumOfHits"
            and node[1] == expected_hits
        ]
        if len(max_hits) != 1 or attacks[0][6] != [{"min": 15, "max": 15}]:
            raise PublishError(f"Golden Dragon hit geometry drifted: {logical}")
        set_range(attacks[0][6][0], damage_per_hit)
        damage_report = {
            "hits": expected_hits,
            "per_hit": damage_per_hit,
            "total": float(expected_hits or 0) * damage_per_hit,
        }
    else:
        values = [float(node[6][0]["min"]) for node in attacks]
        if preserve_damage is not None and values != preserve_damage:
            raise PublishError(f"Darkness Dragon damage drifted: {logical}: {values}")
        damage_report = {"segments": values, "total": sum(values)}
    return encode_dsl(tree, logical), {
        "resistance_per_layer": value,
        "stack_cap": stack_cap,
        "layers_per_cast": 2,
        "damage": damage_report,
    }


def build_ios_cutins(assets: dict[str, bytes]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for logical in IOS_CUTINS:
        android_member = member_name(logical, "android_upload")
        ios_member = member_name(logical, "ios_upload")
        png_logical = logical.removesuffix(".atf.deflate") + ".png"
        png_member = member_name(png_logical, "medium_upload")
        if android_member not in assets or png_member not in assets:
            raise PublishError(f"Mosiyike cut-in pair is incomplete: {logical}")
        android_plain = wf_atf.inflate(assets[android_member])
        android_info = wf_atf.parse_atf(android_plain)
        if android_info["slot"] != 2 or android_info["layout"] != "etc1":
            raise PublishError(f"Mosiyike Android cut-in is not ETC1 slot 2: {logical}")
        png = wf_assets.png_decode(assets[png_member])
        if png[:8] != wf_assets.PNG_REAL:
            raise PublishError(f"Mosiyike cut-in source is not PNG: {png_logical}")
        ios_plain = wf_atf.build_cutin_atf_ios(png, android_plain)
        wf_atf.validate_cutin_platform_pair(android_plain, ios_plain, png)
        ios_info = wf_atf.parse_atf(ios_plain)
        if ios_info["slot"] != 3 or ios_info["layout"] != "etc2-rgba":
            raise PublishError(f"Mosiyike iOS cut-in is not ETC2 RGBA slot 3: {logical}")
        ios_raw = wf_atf.deflate(ios_plain)
        if ios_raw == assets[android_member]:
            raise PublishError(f"Mosiyike iOS cut-in copied Android bytes: {logical}")
        assets[ios_member] = ios_raw
        report[logical] = {
            "android_slot": android_info["slot"],
            "android_layout": android_info["layout"],
            "ios_slot": ios_info["slot"],
            "ios_layout": ios_info["layout"],
            "width": ios_info["w"],
            "height": ios_info["h"],
            "mips": ios_info["mips"],
        }
    return report


def validate_banner() -> bytes:
    if not BANNER_INPUT.is_file() or sha256_file(BANNER_INPUT) != BANNER_SHA256:
        raise PublishError(f"canonical Gauntlet banner drifted: {BANNER_INPUT}")
    raw = BANNER_INPUT.read_bytes()
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if image.format != "PNG" or image.size != (1000, 184):
            raise PublishError("Gauntlet banner must be a native 1000x184 PNG")
    encoded = wf_assets.png_encode(raw)
    if wf_assets.png_decode(encoded) != raw:
        raise PublishError("Gauntlet banner client codec round trip failed")
    return encoded


def classify_package_assets(
    package_assets: dict[str, bytes],
    terminal: dict[str, bytes],
) -> dict[str, list[str]]:
    report = {"new": [], "same": [], "different": []}
    for member, value in package_assets.items():
        if member not in terminal:
            report["new"].append(member)
        elif terminal[member] == value:
            report["same"].append(member)
        else:
            report["different"].append(member)
    for values in report.values():
        values.sort()
    if tuple(len(report[key]) for key in ("new", "same", "different")) != (77, 0, 7):
        raise PublishError(
            "share/current asset classification drifted: "
            + ", ".join(f"{key}={len(value)}" for key, value in report.items())
        )
    expected_different = {
        member_name(logical) for logical in CLAUDE_POISON
    } | {
        member_name("character/claude_wolf_assassin_ex/pixelart/sprite_sheet.png"),
        member_name("character/claude_wolf_assassin_ex/pixelart/special_sprite_sheet.png"),
    }
    if set(report["different"]) != expected_different:
        raise PublishError("unexpected same-path package replacement remains")
    return report


def build_payloads(
    manifest: dict[str, Any],
    share: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, Any], bytes]:
    package_assets = copy.deepcopy(share["assets"])
    table_logicals = set(share["payload"])
    wanted = set(package_assets)
    wanted.update(table_member(logical) for logical in table_logicals)
    wanted.update(member_name(logical) for logical in EXTRA_ACTIVE_DSLS)
    terminal, sources = terminal_members(SOURCE_ROOT, manifest, wanted)
    missing = wanted - set(terminal) - set(package_assets)
    if missing:
        raise PublishError(f"active terminal lacks required members: {sorted(missing)}")
    classification = classify_package_assets(package_assets, terminal)

    poison_report = patch_claude_poison(package_assets)
    mosiyike_pf_report = patch_mosiyike_power_flips(package_assets)
    table_payloads, table_report, client_gacha_row = build_client_tables(terminal, share)

    output = dict(package_assets)
    if set(output) & set(table_payloads):
        raise PublishError("share asset payload unexpectedly contains a stripped table")
    output.update(table_payloads)

    ginovi_pf_report: dict[str, Any] = {}
    for level, logical in enumerate(GINOVI_POWER_FLIPS, 1):
        member = member_name(logical)
        patched, report = patch_ginovi_power_flip(terminal[member], logical, level)
        output[member] = patched
        ginovi_pf_report[f"lv{level}"] = report

    ginovi_skill_report: dict[str, Any] = {}
    for logical in GINOVI_SKILLS:
        member = member_name(logical)
        patched, report = patch_ginovi_skill(terminal[member], logical)
        output[member] = patched
        ginovi_skill_report[logical] = report

    golden_report: dict[str, Any] = {}
    for logical in GOLDEN_DRAGON_SKILLS:
        member = member_name(logical)
        patched, report = patch_dual_resistance_skill(
            terminal[member], logical, -0.04, 10, 6.0, 8
        )
        output[member] = patched
        golden_report[logical] = report

    darkness_report: dict[str, Any] = {}
    for logical in DARKNESS_DRAGON_SKILLS:
        member = member_name(logical)
        patched, report = patch_dual_resistance_skill(
            terminal[member], logical, -0.03, 10, None, None, [20.0, 30.0, 75.0]
        )
        output[member] = patched
        darkness_report[logical] = report

    banner_member = member_name(BANNER_LOGICAL)
    output[banner_member] = validate_banner()
    ios_report = build_ios_cutins(output)

    root_counts = {
        root_name: sum(1 for member in output if member.startswith(prefix))
        for root_name, prefix in {
            "common": "production/upload/",
            "medium": "production/medium_upload/",
            "android": "production/android_upload/",
            "ios": "production/ios_upload/",
        }.items()
    }
    if root_counts != {"common": 88, "medium": 25, "android": 2, "ios": 2}:
        raise PublishError(f"final archive root counts drifted: {root_counts}")
    if len(output) != 117:
        raise PublishError(f"final active member count drifted: {len(output)}")
    return output, {
        "terminal_sources": sources,
        "package_assets": classification,
        "tables": table_report,
        "claude_poison": poison_report,
        "mosiyike_power_flip": mosiyike_pf_report,
        "ginovi_power_flip": ginovi_pf_report,
        "ginovi_skill": ginovi_skill_report,
        "golden_dragon": golden_report,
        "darkness_dragon": darkness_report,
        "ios": ios_report,
        "banner": {
            "logical": BANNER_LOGICAL,
            "sha256": BANNER_SHA256,
            "size": [1000, 184],
        },
        "root_counts": root_counts,
    }, client_gacha_row


def client_gacha_rows(raw_inner: bytes) -> list[dict[str, Any]]:
    values = core.read_orderedmap_file_from_bytes(raw_inner)
    rows: list[dict[str, Any]] = []
    for key in values:
        lines = core.read_csv_lines(values[key])
        if len(lines) != 1 or len(lines[0]) != 7:
            raise PublishError(f"abyss client gacha row shape drifted: {key}")
        row = lines[0]
        rows.append({
            "id": int(row[0]),
            "rank": int(row[1]),
            "odds": int(row[2]),
            "isRateUp": row[3] == "true",
            "isLimited": row[4] == "true",
            "isExchangeable": row[5] == "true",
            "trialReadingForced": row[6] == "true",
        })
    if len(rows) != 247 or len({row["id"] for row in rows}) != 247:
        raise PublishError("abyss client gacha does not contain 247 unique characters")
    return rows


def json_output(current_raw: bytes, value: Any) -> bytes:
    newline = b"\n" if current_raw.endswith(b"\n") else b""
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + newline


def build_server_outputs(
    share: dict[str, Any],
    client_gacha_inner: bytes,
) -> tuple[dict[Path, bytes], dict[str, Any]]:
    server_rows: dict[str, dict[str, Any]] = share["server_rows"]
    outputs: dict[Path, bytes] = {}

    character_path = SOURCE_ROOT / "assets/character.json"
    character_raw = character_path.read_bytes()
    character = json.loads(character_raw.decode("utf-8-sig"))
    if "149997" in character:
        raise PublishError("149997 already exists in assets/character.json")
    current_129997 = copy.deepcopy(character["129997"])
    package_129997 = copy.deepcopy(server_rows["character.json"]["129997"])
    current_129997["name"] = package_129997["name"]
    if current_129997 != package_129997:
        raise PublishError("package changed 129997 server character fields beyond the approved name")
    character["129997"] = package_129997
    character["149997"] = server_rows["character.json"]["149997"]
    outputs[character_path] = json_output(character_raw, character)

    cdn_character_path = SOURCE_ROOT / "assets/cdndata/character.json"
    cdn_character_raw = cdn_character_path.read_bytes()
    cdn_character = json.loads(cdn_character_raw.decode("utf-8-sig"))
    if "149997" in cdn_character:
        raise PublishError("149997 already exists in assets/cdndata/character.json")
    if cdn_character.get("129997") != server_rows["cdndata/character.json"]["129997"]:
        raise PublishError("package changed unapproved 129997 cdndata character fields")
    cdn_character["149997"] = server_rows["cdndata/character.json"]["149997"]
    outputs[cdn_character_path] = json_output(cdn_character_raw, cdn_character)

    text_path = SOURCE_ROOT / "assets/cdndata/character_text.json"
    text_raw = text_path.read_bytes()
    text = json.loads(text_raw.decode("utf-8-sig"))
    if "149997" in text:
        raise PublishError("149997 already exists in assets/cdndata/character_text.json")
    current_129997_text = copy.deepcopy(text["129997"])
    current_129997_text[0][0] = "克劳斯"
    if current_129997_text != server_rows["cdndata/character_text.json"]["129997"]:
        raise PublishError("package changed 129997 server text beyond the approved name")
    text["129997"] = server_rows["cdndata/character_text.json"]["129997"]
    text["149997"] = server_rows["cdndata/character_text.json"]["149997"]
    ginovi_text = copy.deepcopy(text["169999"])
    serialized = json.dumps(ginovi_text, ensure_ascii=False)
    if serialized.count("最大生命值15%的护盾") != 2:
        raise PublishError("169999 server barrier wording drifted")
    serialized = serialized.replace("最大生命值15%的护盾", "最大生命值10%的护盾")
    text["169999"] = json.loads(serialized)
    outputs[text_path] = json_output(text_raw, text)

    mana_path = SOURCE_ROOT / "assets/mana_node.json"
    mana_raw = mana_path.read_bytes()
    mana = json.loads(mana_raw.decode("utf-8-sig"))
    if "149997" in mana:
        raise PublishError("149997 already exists in assets/mana_node.json")
    mana["149997"] = server_rows["mana_node.json"]["149997"]
    outputs[mana_path] = json_output(mana_raw, mana)

    client_rows = client_gacha_rows(client_gacha_inner)
    client_by_id = {row["id"]: row for row in client_rows}
    package_pool = copy.deepcopy(share["server_pool"]["gacha.json"][ABYSS_GACHA_ID])
    server_five = package_pool["pool"]["1"]
    if len(server_five) != 247 or {row["id"] for row in server_five} != set(client_by_id):
        raise PublishError("client/server abyss pool membership disagrees")
    mismatch_fields: list[tuple[int, str]] = []
    authoritative_fields = (
        "rank", "odds", "isRateUp", "isLimited", "isExchangeable", "trialReadingForced"
    )
    for row in server_five:
        approved = client_by_id[row["id"]]
        for field in authoritative_fields:
            if row.get(field) != approved[field]:
                mismatch_fields.append((row["id"], field))
            row[field] = approved[field]
    if len(mismatch_fields) != 217 or {field for _id, field in mismatch_fields} != {"isExchangeable"}:
        raise PublishError(f"package client/server mismatch set drifted: {len(mismatch_fields)}")
    if sum(row["odds"] for row in server_five) != 1_593_000:
        raise PublishError("abyss five-star odds total drifted")
    featured = {
        row["id"]: row for row in server_five
        if row["id"] in {129997, 129999, 139997, 139998, 139999, 149997, 149998, 149999, 169998, 169999, 179999}
    }
    if featured[149997]["odds"] != 40356 or featured[149997]["isExchangeable"]:
        raise PublishError("149997 abyss-pool settings drifted")
    for character_id, row in featured.items():
        if character_id == 149997:
            continue
        if row["odds"] != 10620 or not row["isExchangeable"]:
            raise PublishError(f"shared abyss featured setting drifted: {character_id}")

    for relative in ("gacha.json", "gacha_cnmod.json"):
        path = SOURCE_ROOT / "assets" / relative
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
        if ABYSS_GACHA_ID not in data:
            raise PublishError(f"current abyss pool is missing: {path}")
        data[ABYSS_GACHA_ID] = package_pool
        outputs[path] = json_output(raw, data)

    for relative in ("cdndata/gacha.json", "cdndata/gacha_feature_content.json"):
        path = SOURCE_ROOT / "assets" / relative
        current = json.loads(path.read_text(encoding="utf-8-sig"))
        incoming = share["server_pool"][relative][ABYSS_GACHA_ID]
        if current.get(ABYSS_GACHA_ID) != incoming:
            raise PublishError(f"unapproved CDN gacha metadata difference remains: {relative}")

    lookup_path = SOURCE_ROOT / "docs/generated/character_table.json"
    lookup_raw = lookup_path.read_bytes()
    lookup = json.loads(lookup_raw.decode("utf-8-sig"))
    existing = {int(row["id"]): row for row in lookup}
    if 149997 in existing or existing[129997]["name"] != "克劳德":
        raise PublishError("admin character lookup baseline drifted")
    existing[129997]["name"] = "克劳斯"
    lookup.append({
        "id": 149997,
        "name": "墨斯伊克",
        "title": "游历世界的羽龙",
        "rarity": "5★",
        "element": "风",
        "gender": "男性",
        "race": "Dragon",
    })
    lookup.sort(key=lambda row: int(row["id"]))
    outputs[lookup_path] = json_output(lookup_raw, lookup)

    return outputs, {
        "character_added": 149997,
        "character_renamed": {"id": 129997, "from": "克劳德", "to": "克劳斯"},
        "ginovi_barrier_text": "15% -> 10%",
        "gacha_five_star_count": len(server_five),
        "gacha_odds_sum": sum(row["odds"] for row in server_five),
        "client_authoritative_exchange_repairs": len(mismatch_fields),
        "gacha_files": ["assets/gacha.json", "assets/gacha_cnmod.json"],
    }


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for member in sorted(payloads):
            info = zipfile.ZipInfo(member, (2026, 8, 21, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(payloads):
            raise PublishError("active archive member order mismatch")
        for member, value in payloads.items():
            if archive.read(member) != value:
                raise PublishError(f"active archive readback failed: {member}")
    return raw


def updated_manifest(
    manifest: dict[str, Any],
    archive: bytes,
    payloads: dict[str, bytes],
) -> bytes:
    value = copy.deepcopy(manifest)
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "墨斯伊克、角色平衡与双端资源 1.4.85",
        "description": (
            "新增墨斯伊克并按确认值调整克劳斯、基诺维、拉夫马诺与阿鲁玛德乌斯；"
            "同步客户端权威深渊池、终始之战入口横幅以及Android/iOS技能切入资源。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "files": sorted(payloads),
        "changes": [
            "新增风属性★5墨斯伊克（149997）的角色表、6条能力、主动技、专属强化弹射、玛纳板、图像、语音与特效资源。",
            "墨斯伊克能力2独立乘区强化弹射伤害改为+15%；能力3自身技能后技能槽+20%并设30秒冷却；移除能力5每次技能发动时全队技能槽+20%。",
            "墨斯伊克专属强化弹射Lv1/Lv2/Lv3分别调整为2段×7.5、5段×6、10段×4.5，理论合计15/30/45倍。",
            "克劳德更名为克劳斯；补齐队长技第三伤害类型逐层特攻，替换2张像素演出PNG，中毒强度采用原设计×2；明确排除能力2新增的20层全队敌方特攻行。",
            "雷龙（139998）队长技计数点144修复为143，保留现有18秒主动技终态。",
            "基诺维PF ACAttackPoint持续帧恢复为150/180/240；专属PF本体与技能追击合计25/35/60倍且技能追击占大头。",
            "基诺维每次技能护盾15%改为10%；首次95%扣血与60%护盾继续由同一首次发动固有状态分支控制；暗耐性降低-25%改为-15%。",
            "至天光辉改为8段×6=48倍，光/暗耐性每层-4%、上限10层；魂魄终局保持125倍，光/暗耐性每层-3%、上限10层；两者每次各施加2层。",
            "深渊限定池按客户端247行规则回写服务端：墨斯伊克0.38%且不可兑换，既有10名共享角色各0.1%且可兑换。",
            "替换幻想/深渊连战共用文件夹的终始之战1000×184入口横幅。",
            "墨斯伊克两张技能切入图同时携带Android ETC1 slot 2与iOS ETC2 RGBA slot 3资源。",
        ],
        "created_at": "2026-08-21",
        "archive_integrity": [{
            "name": ARCHIVE_NAME,
            "size": len(archive),
            "sha256": sha256_bytes(archive),
            "members": len(payloads),
        }],
    })
    value["cdn_version"] = PATCH_VERSION
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def updated_changelog(raw: bytes) -> bytes:
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    marker = f"|---|---|---|---|---|---|{newline}"
    if marker not in text:
        raise PublishError("asset patch changelog table header drifted")
    rows = (
        f"| 2026-08-21 | character/ability/skill | 149997/129997/169999/151159/261089 | 新增墨斯伊克并按确认值完成五名角色终态调整 | 1.4.85 | active统一增量包 |{newline}"
        f"| 2026-08-21 | gacha | 990001 | 客户端247行规则作为权威源同步深渊池兑换与概率字段 | 1.4.85 | active统一增量包 |{newline}"
        f"| 2026-08-21 | image/platform | gauntlet/mosiyike | 更换终始之战入口横幅并补齐墨斯伊克Android/iOS切入图 | 1.4.85 | active统一增量包 |{newline}"
    )
    return text.replace(marker, marker + rows, 1).encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".mosiyike-1.4.85.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def assert_target(target: Path) -> None:
    target.resolve(strict=False).relative_to(SOURCE_ROOT.resolve(strict=True))


def add_target(
    targets: dict[str, tuple[Path, bytes]],
    label: str,
    path: Path,
    raw: bytes,
) -> None:
    assert_target(path)
    if label in targets or path in (entry[0] for entry in targets.values()):
        raise PublishError(f"duplicate publication target: {path}")
    targets[label] = (path, raw)


def build_targets(
    manifest_raw: bytes,
    archive_raw: bytes,
    payloads: dict[str, bytes],
    server_outputs: dict[Path, bytes],
    changelog_raw: bytes,
) -> dict[str, tuple[Path, bytes]]:
    targets: dict[str, tuple[Path, bytes]] = {}
    add_target(
        targets,
        "active-archive",
        SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME,
        archive_raw,
    )
    for member, raw in payloads.items():
        add_target(
            targets,
            f"production-{member}",
            SOURCE_ROOT / "assets/asset-patch" / member,
            raw,
        )
    for path, raw in server_outputs.items():
        add_target(
            targets,
            f"server-{path.relative_to(SOURCE_ROOT).as_posix()}",
            path,
            raw,
        )
    add_target(
        targets,
        "changelog",
        SOURCE_ROOT / "assets/asset-patch/changelog.md",
        changelog_raw,
    )
    add_target(
        targets,
        "manifest",
        SOURCE_ROOT / "assets/asset-patch/manifest.json",
        manifest_raw,
    )
    return targets


def apply_targets(
    targets: dict[str, tuple[Path, bytes]],
    report: dict[str, Any],
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = (
        SOURCE_ROOT
        / "tools/fantasy-gauntlet-mod-tools/work"
        / f"mosiyike-balance-1.4.85-backup-{stamp}"
    )
    backup.mkdir(parents=True, exist_ok=False)
    existence: dict[str, bool] = {}
    for label, (path, _raw) in targets.items():
        existence[label] = path.is_file()
        if existence[label]:
            destination = backup / label
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    (backup / "existence.json").write_text(
        json.dumps(existence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        for label, (path, raw) in targets.items():
            if label == "manifest":
                continue
            atomic_write(raw, path)
        atomic_write(targets["manifest"][1], targets["manifest"][0])

        for label, (path, expected) in targets.items():
            if not path.is_file() or path.read_bytes() != expected:
                raise PublishError(f"publication readback failed: {label}")
        written = json.loads(
            (SOURCE_ROOT / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
        )
        matches = [entry for entry in written["patches"] if entry.get("id") == PATCH_ID]
        if written.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
            raise PublishError("manifest readback registration failed")
        archive_path = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
        with zipfile.ZipFile(archive_path) as archive:
            archive_entry = matches[0]
            if archive.namelist() != archive_entry["files"]:
                raise PublishError("archive/manifest file list disagrees")
            if len(archive.infolist()) != archive_entry["archive_integrity"][0]["members"]:
                raise PublishError("archive/manifest member count disagrees")
        if sha256_file(archive_path) != matches[0]["archive_integrity"][0]["sha256"]:
            raise PublishError("archive SHA-256 readback failed")
    except Exception:
        for label, (path, _raw) in reversed(list(targets.items())):
            assert_target(path)
            if existence[label]:
                atomic_write((backup / label).read_bytes(), path)
            elif path.exists():
                path.unlink()
        raise

    report["backup"] = str(backup)
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the verified source-repository outputs")
    args = parser.parse_args()

    manifest, _manifest_current = read_manifest()
    share = read_share()
    payloads, client_report, client_gacha_inner = build_payloads(manifest, share)
    archive_raw = zip_payloads(payloads)
    manifest_raw = updated_manifest(manifest, archive_raw, payloads)
    server_outputs, server_report = build_server_outputs(share, client_gacha_inner)
    changelog_path = SOURCE_ROOT / "assets/asset-patch/changelog.md"
    changelog_raw = updated_changelog(changelog_path.read_bytes())

    report: dict[str, Any] = {
        "apply": args.apply,
        "source_only": True,
        "runtime_mirror_touched": False,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "patch_id": PATCH_ID,
        "archive": str(SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME),
        "archive_size": len(archive_raw),
        "archive_sha256": sha256_bytes(archive_raw),
        "members": len(payloads),
        "client": client_report,
        "server": server_report,
        "server_files": sorted(path.relative_to(SOURCE_ROOT).as_posix() for path in server_outputs),
        "excluded": {
            "package_129997_ability2_added_line": True,
            "package_139998_stale_10_second_server_text": True,
            "package_client_server_exchange_mismatches_repaired": 217,
        },
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    targets = build_targets(
        manifest_raw,
        archive_raw,
        payloads,
        server_outputs,
        changelog_raw,
    )
    backup = apply_targets(targets, report)
    report["backup"] = str(backup)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
