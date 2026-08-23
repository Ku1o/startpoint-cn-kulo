#!/usr/bin/env python3
"""Build the reviewed lion/balance/raid graft as the local 1.4.86 -> 1.4.87 edge.

The received archive belongs to another CDN chain.  Its scripts and notes are
untrusted input: this publisher reads only the audited payloads, rebases the
selected rows/assets on the current terminal state, applies the locally agreed
balance values, and emits one unified incremental patch.
"""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import sys
import zipfile
import zlib
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
RUNTIME_ROOT = Path(r"F:\startpoint-cn-main")
TOOL_ROOT = Path(__file__).resolve().parent
SHARE_ARCHIVE = Path(r"F:\wfshare-lion0823-graft-1.4.351-to-1.4.352.zip")
SHARE_SHA256 = "d7aa79b8897abc86cfb39df088f6c7fe7d30af4d3af3e66174b763d6b5097210"
SHARE_PREFIX = "wfshare-1.4.351-to-1.4.352-graft"

BASE_VERSION = "1.4.86"
PATCH_VERSION = "1.4.87"
PATCH_ID = "lion-balance-raid-abyss-1.4.87"
ARCHIVE_NAME = "pinball-1.4.86-1.4.87-1-0823-lion-balance-raid-abyss-ios.zip"

CLIENT_PAYLOAD_NAME = f"{SHARE_PREFIX}/client-tables/client_tables_payload.json"
CLIENT_MANIFEST_NAME = f"{SHARE_PREFIX}/client-tables/client_tables_manifest.json"
SERVER_ROWS_NAME = f"{SHARE_PREFIX}/server-data/lion0823_rows.json"
SERVER_POOL_NAME = f"{SHARE_PREFIX}/server-data/lion0823_abyss_pool_rows.json"
REPORT_NAME = f"{SHARE_PREFIX}/report.json"

ABILITY_LOGICAL = "master/ability/ability.orderedmap"
MANA_BOARD2_LOGICAL = "master/mana_board/mana_board2_open_condition.orderedmap"
GACHA_LOGICAL = "master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap"
GACHA_KEY = "cnmod_abyss_limited_gacha_character_5"
RAID_REWARD_LOGICAL = "master/quest/event/raid_event_overall_reward.orderedmap"
RAID_REWARD_KEY = "71"
ABYSS_GACHA_ID = "990001"
CHARACTER_ID = "119996"

BANNER_LOGICAL = "dynamic/gacha_list_banner/cnmod_abyss_limited_gacha"
BANNER_MEMBER = "production/upload/ea/5620a65485fc4c2114d7fdaec22d4d04393fe1"
EXPECTED_REPLACED_ASSETS = {
    "production/upload/23/ea8849f34a4a606c9da3c28257512441bc8cbf",
    "production/upload/75/181464ae1efc9fb139ab93cfc46305335ef4b5",
    BANNER_MEMBER,
}
EXPECTED_SAME_ASSETS = {
    "production/medium_upload/2e/90dc513fa80bd0379f05c2c7cc9726b0095b91",
    "production/upload/6b/6e638ae42a1fbe5c30d9bea763030353908802",
}

LION_SKILL_LOGICALS = {
    1: "battle/action/skill/action/rare5/lion_swordman_reborn$lion_swordman_reborn_1.action.dsl.amf3.deflate",
    2: "battle/action/skill/action/rare5/lion_swordman_reborn$lion_swordman_reborn_2.action.dsl.amf3.deflate",
}
LION_PF_LOGICALS = {
    level: (
        "battle/action/power_flip/action/override/lion_swordman_reborn_pf$"
        f"lion_swordman_reborn_pf_lv{level}.action.dsl.amf3.deflate"
    )
    for level in (1, 2, 3)
}
WIND_SKILL_LOGICALS = {
    form: (
        "battle/action/skill/action/rare5/land_dragon_wind_playable$"
        f"land_dragon_wind_playable_{form}.action.dsl.amf3.deflate"
    )
    for form in (1, 2)
}
CUTIN_LOGICALS = tuple(
    f"character/lion_swordman_reborn/ui/skill_cutin_{slot}.atf.deflate"
    for slot in (0, 1)
)

DOC_ROW = {
    "id": 119996,
    "name": "玛格诺斯",
    "title": "灼原的狮王",
    "rarity": "5★",
    "element": "火",
    "gender": "男性",
    "race": "Human,Beast",
}


def _load_previous_builder():
    path = TOOL_ROOT / "publish_twochar_1_4_86_20260822.py"
    spec = importlib.util.spec_from_file_location("publish_twochar_1_4_86", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper builder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


previous = _load_previous_builder()
base = previous.base
core = previous.core
wf_assets = previous.wf_assets
wf_atf = previous.wf_atf


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


def member_name(logical: str, root: str = "upload") -> str:
    digest = core.sha1_path(logical)
    return f"production/{root}/{digest[:2]}/{digest[2:]}"


def normalize_member(value: str) -> str:
    normalized = value.replace("\\", "/").lstrip("./")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 4:
        raise PublishError(f"unsafe package member: {value}")
    return normalized


def read_manifest() -> dict[str, Any]:
    path = SOURCE_ROOT / "assets/asset-patch/manifest.json"
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if value.get("cdn_version") != BASE_VERSION:
        raise PublishError(f"manifest is not at {BASE_VERSION}: {path}")
    if any(entry.get("id") == PATCH_ID for entry in value.get("patches", [])):
        raise PublishError(f"patch is already registered: {PATCH_ID}")
    target = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
    if target.exists():
        raise PublishError(f"target archive already exists: {target}")
    base.active_archives(SOURCE_ROOT, value)
    return value


def read_share() -> dict[str, Any]:
    if not SHARE_ARCHIVE.is_file() or sha256_file(SHARE_ARCHIVE) != SHARE_SHA256:
        raise PublishError("reviewed share archive is missing or its SHA-256 drifted")
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
            raise PublishError(f"share archive lacks required payloads: {sorted(missing)}")
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
                    member = normalize_member(info.filename)
                    if not member.startswith((
                        "production/upload/",
                        "production/medium_upload/",
                        "production/android_upload/",
                    )):
                        raise PublishError(f"unsupported asset root: {member}")
                    value = nested.read(info)
                    if member in assets and assets[member] != value:
                        raise PublishError(f"share archives disagree on member: {member}")
                    assets[member] = value

    if len(payload) != 20 or sum(len(rows) for rows in payload.values()) != 153:
        raise PublishError("client row payload shape drifted")
    if set(payload) != set(payload_manifest):
        raise PublishError("client payload and row manifest table sets disagree")
    for logical, rows in payload.items():
        if set(rows) != set(payload_manifest[logical]["keys"]):
            raise PublishError(f"client row manifest disagrees: {logical}")
    if report.get("asset_entries") != 95 or len(assets) != 95:
        raise PublishError(f"share asset count drifted: {len(assets)}")
    if set(server_rows) != {
        "character.json", "cdndata/character.json",
        "cdndata/character_text.json", "mana_node.json",
    }:
        raise PublishError("server character payload file set drifted")
    if any(CHARACTER_ID not in rows for rows in server_rows.values()):
        raise PublishError("119996 is incomplete in the server character payload")
    if set(server_pool) != {
        "gacha.json", "cdndata/gacha.json", "cdndata/gacha_feature_content.json",
    }:
        raise PublishError("server abyss pool payload file set drifted")
    return {
        "payload": payload,
        "payload_manifest": payload_manifest,
        "server_rows": server_rows,
        "server_pool": server_pool,
        "assets": assets,
        "report": report,
    }


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


def set_range(value: Any, minimum: float | int, maximum: float | int | None = None) -> None:
    if not isinstance(value, dict) or not {"min", "max"}.issubset(value):
        raise PublishError(f"not a numeric range: {value!r}")
    value["min"] = minimum
    value["max"] = minimum if maximum is None else maximum


def decode_dsl(raw: bytes, logical: str) -> Any:
    return base.decode_dsl(raw, logical)


def encode_dsl(tree: Any, logical: str) -> bytes:
    return base.encode_dsl(tree, logical)


def walk(value: Any):
    yield from base.walk(value)


def patch_wind_position_rows(current_rows: dict[str, bytes]) -> tuple[dict[str, bytes], dict[str, Any]]:
    positions = {
        "1499981": "202",
        "1499983": "202",
        "1499984": "202",
        "1499985": "202",
        "1499986": "203",
    }
    expected_counts = {
        "1499981": 2, "1499983": 5, "1499984": 1,
        "1499985": 3, "1499986": 3,
    }
    output: dict[str, bytes] = {}
    report: dict[str, Any] = {}
    for key, position in positions.items():
        if key not in current_rows:
            raise PublishError(f"current ability table lacks wind dragon row {key}")
        rows = flat_row(current_rows[key], ABILITY_LOGICAL, key)
        if len(rows) != expected_counts[key] or any(len(row) <= 6 for row in rows):
            raise PublishError(f"wind dragon ability row shape drifted: {key}")
        before = [row[6] for row in rows]
        for row in rows:
            row[6] = position
        output[key] = build_flat_row(rows)
        report[key] = {"lines": len(rows), "before": before, "after": position}
    return output, report


def patch_lion_ability3(raw_row: bytes) -> tuple[bytes, dict[str, Any]]:
    rows = flat_row(raw_row, ABILITY_LOGICAL, "1199963")
    if (
        len(rows) != 7
        or rows[5][2] != "special"
        or rows[6][2] != "special"
        or rows[5][51:53] != ["2000000", "2000000"]
        or rows[6][51:53] != ["3000000", "3000000"]
    ):
        raise PublishError("119996 ability 3 dash/PF rows drifted")
    rows[5][51:53] = ["1000000", "1000000"]
    rows[6][51:53] = ["1000000", "1000000"]
    return build_flat_row(rows), {
        "dash": {"package": 20, "target": 10},
        "power_flip_all_enemies": {"package": 30, "target": 10},
    }


def patch_raid_reward(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    ordered, rows = raw_rows(raw, RAID_REWARD_LOGICAL)
    del ordered
    if RAID_REWARD_KEY not in rows:
        raise PublishError("raid event 7 total-kill 300 row is missing")
    parsed = flat_row(rows[RAID_REWARD_KEY], RAID_REWARD_LOGICAL, RAID_REWARD_KEY)
    if (
        len(parsed) != 1
        or len(parsed[0]) != 37
        or parsed[0][0] != "7"
        or parsed[0][3] != "300"
        or parsed[0][7:13] != ["2", "", "2000", "7", "80054", "1"]
    ):
        raise PublishError("raid event 7 total-kill 300 reward baseline drifted")
    parsed[0][10:13] = ["0", "999014", "25"]
    incoming = {RAID_REWARD_KEY: build_flat_row(parsed)}
    candidate, added, changed = base.upsert_table_rows(raw, RAID_REWARD_LOGICAL, incoming)
    if added or changed != [RAID_REWARD_KEY]:
        raise PublishError("raid reward row replacement effect drifted")
    return candidate, {
        "event_id": 7,
        "total_kills": 300,
        "rewards": [
            {"type": 2, "id": None, "quantity": 2000},
            {"type": 0, "id": 999014, "quantity": 25},
        ],
    }


def patch_lion_skills(assets: dict[str, bytes]) -> dict[str, Any]:
    specs = {
        1: {
            "package": [37.0, 6.25, 1.93],
            "target": [23.25, 3.9375, 1.21875],
            "hits": [1, 8, 16],
            "total": 74.25,
        },
        2: {
            "package": [48.0, 8.125, 2.5],
            "target": [31.0, 5.25, 1.625],
            "hits": [1, 8, 16],
            "total": 99.0,
        },
    }
    report: dict[str, Any] = {}
    for form, logical in LION_SKILL_LOGICALS.items():
        member = member_name(logical)
        if member not in assets:
            raise PublishError(f"share lacks lion active-skill DSL: {logical}")
        tree = decode_dsl(assets[member], logical)
        attacks = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
        ]
        hit_areas = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "CreateHitArea"
        ]
        spec = specs[form]
        if len(attacks) != 3 or len(hit_areas) != 3:
            raise PublishError(f"lion active skill shape drifted: form {form}")
        package_values = [float(node[6][0]["max"]) for node in attacks]
        if package_values != spec["package"]:
            raise PublishError(f"lion active package multipliers drifted: form {form}: {package_values}")
        hit_caps = [
            int(hit_areas[0][14][1]),
            int(hit_areas[1][14][1]),
            int(hit_areas[2][15][1][0]["max"]),
        ]
        if hit_caps != spec["hits"]:
            raise PublishError(f"lion active hit caps drifted: form {form}: {hit_caps}")
        for node, target in zip(attacks, spec["target"]):
            set_range(node[6][0], target)
        total = sum(hits * value for hits, value in zip(hit_caps, spec["target"]))
        if not math.isclose(total, spec["total"], abs_tol=1e-9):
            raise PublishError(f"lion active target arithmetic failed: form {form}")
        assets[member] = encode_dsl(tree, logical)
        report[f"form{form}"] = {
            "hits": hit_caps,
            "per_hit": spec["target"],
            "phase_totals": [hits * value for hits, value in zip(hit_caps, spec["target"])],
            "total": total,
        }
    return report


def _hit_area_attack_pair(tree: Any, logical: str) -> list[tuple[int, list[Any]]]:
    pairs: list[tuple[int, list[Any]]] = []
    for area in [
        node for node in walk(tree)
        if isinstance(node, list) and node and node[0] == "CreateHitArea"
    ]:
        attacks = [
            node for node in walk(area)
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
        ]
        if not attacks:
            continue
        if len(attacks) != 1:
            raise PublishError(f"multiple attacks share one hit area: {logical}")
        if area[14][0] == "CalculatedUsingMaxNumOfHits":
            hits = int(area[14][1])
        elif area[15][0] == "Some":
            hits = int(area[15][1][0]["max"])
        else:
            raise PublishError(f"cannot determine hit cap: {logical}")
        pairs.append((hits, attacks[0]))
    return pairs


def patch_lion_power_flips(assets: dict[str, bytes]) -> dict[str, Any]:
    specs = {
        1: {"hits": [3, 3], "package": [3.25, 3.2], "target": None, "total": 19.35},
        2: {"hits": [4, 4], "package": [4.75, 4.35], "target": [3.25, 3.0], "total": 25.0},
        3: {"hits": [5, 4], "package": [6.3, 8.4], "target": [3.4, 4.5], "total": 35.0},
    }
    report: dict[str, Any] = {}
    for level, logical in LION_PF_LOGICALS.items():
        member = member_name(logical)
        if member not in assets:
            raise PublishError(f"share lacks lion power-flip DSL: {logical}")
        tree = decode_dsl(assets[member], logical)
        pairs = _hit_area_attack_pair(tree, logical)
        hits = [pair[0] for pair in pairs]
        values = [float(pair[1][6][0]["max"]) for pair in pairs]
        spec = specs[level]
        if hits != spec["hits"] or values != spec["package"]:
            raise PublishError(f"lion PF package shape drifted: lv{level}: {hits}/{values}")
        targets = values if spec["target"] is None else spec["target"]
        for (_hits, attack), target in zip(pairs, targets):
            set_range(attack[6][0], target)
        total = sum(count * value for count, value in zip(hits, targets))
        if not math.isclose(total, spec["total"], abs_tol=1e-9):
            raise PublishError(f"lion PF target arithmetic failed: lv{level}")
        if level != 1:
            assets[member] = encode_dsl(tree, logical)
        report[f"pf{level}"] = {
            "unchanged": level == 1,
            "hits": hits,
            "per_hit": targets,
            "phase_totals": [count * value for count, value in zip(hits, targets)],
            "total": total,
        }
    return report


def patch_wind_skills(
    terminal: dict[str, bytes], sources: dict[str, str]
) -> tuple[dict[str, bytes], dict[str, Any]]:
    output: dict[str, bytes] = {}
    report: dict[str, Any] = {}
    expected_by_form = {
        1: {3.0: 8, 10.0: 16, 80.0: 1},
        2: {3.0: 8, 4.125: 16, 33.0: 1},
    }
    targets = {
        "normal": (1.1111111111111112, 1.4814814814814814),
        "fever_multi": (1.125, 1.5),
        "fever_claw": (7.5, 10.0),
    }
    for form, logical in WIND_SKILL_LOGICALS.items():
        member = member_name(logical)
        if member not in terminal:
            raise PublishError(f"active terminal lacks wind dragon skill: {logical}")
        tree = decode_dsl(terminal[member], logical)
        attacks = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
        ]
        groups: dict[float, list[list[Any]]] = {}
        for node in attacks:
            groups.setdefault(float(node[6][0]["max"]), []).append(node)
        if {value: len(nodes) for value, nodes in groups.items()} != expected_by_form[form]:
            raise PublishError(f"wind dragon attack groups drifted: form {form}")
        normal = groups[3.0]
        fever_multi = groups[10.0 if form == 1 else 4.125]
        fever_claw = groups[80.0 if form == 1 else 33.0]
        for node in normal:
            set_range(node[6][0], *targets["normal"])
        for node in fever_multi:
            set_range(node[6][0], *targets["fever_multi"])
        for node in fever_claw:
            set_range(node[6][0], *targets["fever_claw"])

        tolerance = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "ACToleranceOfElement"
        ]
        fever_points = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "AddFeverPoint"
        ]
        stop_ball = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "StopBall"
        ]
        if (
            len(tolerance) != 4
            or sorted(int(node[1][0]["max"]) for node in tolerance) != [900, 1200, 1200, 1200]
            or len(fever_points) != 1
            or fever_points[0][1] != [{"min": 240, "max": 300}]
            or len(stop_ball) != 1
            or stop_ball[0][2] != 50
        ):
            raise PublishError(f"wind dragon non-damage skill data drifted: form {form}")
        for node in tolerance:
            set_range(node[3][0], -0.1)

        output[member] = encode_dsl(tree, logical)
        report[f"form{form}"] = {
            "terminal_source": sources[member],
            "normal_single_unit": {
                "hits": 27, "level1_total": 30, "max_total": 40,
                "per_hit": list(targets["normal"]),
            },
            "fever_laser": {
                "hits": 40, "level1_total": 45, "max_total": 60,
                "per_hit": list(targets["fever_multi"]),
            },
            "fever_whirlwind": {
                "hits": 40, "level1_total": 45, "max_total": 60,
                "per_hit": list(targets["fever_multi"]),
            },
            "fever_claw_single_unit": {
                "hits": 6, "level1_total": 45, "max_total": 60,
                "per_hit": list(targets["fever_claw"]),
            },
            "wind_resistance": -0.1,
            "normal_resistance_seconds": 15,
            "fever_resistance_seconds": 20,
            "fever_points": [240, 300],
            "stop_ball_frames": 50,
        }
    return output, report


def build_ios_cutins(assets: dict[str, bytes]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for logical in CUTIN_LOGICALS:
        android_member = member_name(logical, "android_upload")
        ios_member = member_name(logical, "ios_upload")
        png_logical = logical.removesuffix(".atf.deflate") + ".png"
        png_member = member_name(png_logical, "medium_upload")
        if android_member not in assets or png_member not in assets:
            raise PublishError(f"cut-in platform pair is incomplete: {logical}")
        android_plain = wf_atf.inflate(assets[android_member])
        android_info = wf_atf.parse_atf(android_plain)
        if (android_info["slot"], android_info["layout"]) != (2, "etc1"):
            raise PublishError(f"Android cut-in is not ETC1 slot 2: {logical}")
        png = wf_assets.png_decode(assets[png_member])
        if png[:8] != wf_assets.PNG_REAL:
            raise PublishError(f"cut-in source is not a PNG: {png_logical}")
        ios_plain = wf_atf.build_cutin_atf_ios(png, android_plain)
        wf_atf.validate_cutin_platform_pair(android_plain, ios_plain, png)
        ios_info = wf_atf.parse_atf(ios_plain)
        if (ios_info["slot"], ios_info["layout"]) != (3, "etc2-rgba"):
            raise PublishError(f"iOS cut-in is not ETC2 RGBA slot 3: {logical}")
        assets[ios_member] = wf_atf.deflate(ios_plain)
        report[logical] = {
            "android": "ETC1 slot 2",
            "ios": "ETC2 RGBA slot 3",
            "size": [ios_info["w"], ios_info["h"]],
            "mips": ios_info["mips"],
        }
    return report


def build_client_payloads(
    manifest: dict[str, Any], share: dict[str, Any]
) -> tuple[dict[str, bytes], dict[str, Any], bytes]:
    package_assets = copy.deepcopy(share["assets"])
    wanted = set(package_assets)
    wanted.update(member_name(logical) for logical in share["payload"])
    wanted.add(member_name(RAID_REWARD_LOGICAL))
    wanted.update(member_name(logical) for logical in WIND_SKILL_LOGICALS.values())
    terminal, sources = base.terminal_members(SOURCE_ROOT, manifest, wanted)

    required_terminal = {
        member_name(logical) for logical in share["payload"]
    } | {member_name(RAID_REWARD_LOGICAL)} | {
        member_name(logical) for logical in WIND_SKILL_LOGICALS.values()
    }
    missing = required_terminal - set(terminal)
    if missing:
        raise PublishError(f"active terminal lacks required client members: {sorted(missing)}")

    classification = {"new": [], "same": [], "different": []}
    for member, value in package_assets.items():
        state = "new" if member not in terminal else (
            "same" if terminal[member] == value else "different"
        )
        classification[state].append(member)
    for values in classification.values():
        values.sort()
    counts = {key: len(value) for key, value in classification.items()}
    if counts != {"new": 90, "same": 2, "different": 3}:
        raise PublishError(f"package/current asset classification drifted: {counts}")
    if set(classification["same"]) != EXPECTED_SAME_ASSETS:
        raise PublishError("unexpected identical package assets remain")
    if set(classification["different"]) != EXPECTED_REPLACED_ASSETS:
        raise PublishError("unexpected same-path asset replacement remains")

    banner_png = wf_assets.png_decode(package_assets[BANNER_MEMBER])
    banner_size = wf_assets.png_dims(banner_png)
    if banner_png[:8] != wf_assets.PNG_REAL or banner_size is None:
        raise PublishError("approved abyss list banner is not a decodable PNG")

    ability_member = member_name(ABILITY_LOGICAL)
    _ability_ordered, current_ability_rows = raw_rows(terminal[ability_member], ABILITY_LOGICAL)
    wind_rows, wind_position_report = patch_wind_position_rows(current_ability_rows)

    table_payloads: dict[str, bytes] = {}
    table_report: dict[str, Any] = {}
    lion_ability_report: dict[str, Any] = {}
    client_gacha_row = b""
    for logical, encoded_rows in share["payload"].items():
        member = member_name(logical)
        incoming = {key: base64.b64decode(raw) for key, raw in encoded_rows.items()}
        if logical == ABILITY_LOGICAL:
            incoming.update(wind_rows)
            incoming["1199963"], lion_ability_report = patch_lion_ability3(incoming["1199963"])
        elif logical == MANA_BOARD2_LOGICAL:
            if set(incoming) != set(share["payload_manifest"][logical]["keys"]):
                raise PublishError("mana-board2 package key set drifted")
            incoming = {CHARACTER_ID: incoming[CHARACTER_ID]}
        candidate, added, changed = base.upsert_table_rows(
            terminal[member], logical, incoming
        )
        if candidate == terminal[member]:
            raise PublishError(f"approved client table produced no change: {logical}")
        table_payloads[member] = candidate
        table_report[logical] = {"added": added, "changed": changed}
        if logical == GACHA_LOGICAL:
            client_gacha_row = incoming[GACHA_KEY]

    raid_member = member_name(RAID_REWARD_LOGICAL)
    raid_raw, raid_report = patch_raid_reward(terminal[raid_member])
    table_payloads[raid_member] = raid_raw
    table_report[RAID_REWARD_LOGICAL] = {"added": [], "changed": [RAID_REWARD_KEY]}
    if len(table_payloads) != 21 or not client_gacha_row:
        raise PublishError(f"final client table set drifted: {len(table_payloads)}")

    lion_skill_report = patch_lion_skills(package_assets)
    lion_pf_report = patch_lion_power_flips(package_assets)
    wind_skills, wind_skill_report = patch_wind_skills(terminal, sources)

    output = dict(package_assets)
    collisions = set(output) & (set(table_payloads) | set(wind_skills))
    if collisions:
        raise PublishError(f"asset/table output collision: {sorted(collisions)}")
    output.update(wind_skills)
    output.update(table_payloads)
    ios_report = build_ios_cutins(output)
    root_counts = {
        root: sum(member.startswith(prefix) for member in output)
        for root, prefix in {
            "common": "production/upload/",
            "medium": "production/medium_upload/",
            "android": "production/android_upload/",
            "ios": "production/ios_upload/",
        }.items()
    }
    if root_counts != {"common": 90, "medium": 26, "android": 2, "ios": 2}:
        raise PublishError(f"final client root counts drifted: {root_counts}")
    if len(output) != 120:
        raise PublishError(f"final active member count drifted: {len(output)}")
    return output, {
        "terminal_sources": sources,
        "package_assets": classification,
        "tables": table_report,
        "lion_ability3": lion_ability_report,
        "lion_active_skill": lion_skill_report,
        "lion_power_flip": lion_pf_report,
        "wind_positions": wind_position_report,
        "wind_active_skill": wind_skill_report,
        "swim_shilty": {
            "ability_rows": [f"149996{index}" for index in range(1, 7)],
            "leader_row": "149996",
            "policy": "accepted reviewed package rows in full",
        },
        "raid_reward": raid_report,
        "abyss_list_banner": {
            "logical": BANNER_LOGICAL,
            "member": BANNER_MEMBER,
            "size": list(banner_size),
            "sha256": sha256_bytes(package_assets[BANNER_MEMBER]),
        },
        "ios": ios_report,
        "root_counts": root_counts,
    }, client_gacha_row


def client_gacha_rows(raw_inner: bytes) -> list[dict[str, Any]]:
    values = core.read_orderedmap_file_from_bytes(raw_inner)
    rows: list[dict[str, Any]] = []
    for key in values:
        lines = core.read_csv_lines(values[key])
        if len(lines) != 1 or len(lines[0]) != 7:
            raise PublishError(f"abyss client row shape drifted: {key}")
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
    if len(rows) != 250 or len({row["id"] for row in rows}) != 250:
        raise PublishError("abyss client gacha does not contain 250 unique characters")
    return rows


def json_output(current_raw: bytes, value: Any) -> bytes:
    newline = b"\n" if current_raw.endswith(b"\n") else b""
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + newline


def build_character_csv(current_raw: bytes) -> bytes:
    has_utf8_bom = current_raw.startswith(b"\xef\xbb\xbf")
    text = current_raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames
    if not fieldnames:
        raise PublishError("generated character CSV has no header")
    rows = list(reader)
    if any(int(row["id"]) == DOC_ROW["id"] for row in rows):
        raise PublishError("119996 already exists in generated character CSV")
    rows.append({key: str(value) for key, value in DOC_ROW.items()})
    rows.sort(key=lambda row: int(row["id"]))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator=newline)
    writer.writeheader()
    writer.writerows(rows)
    encoded = output.getvalue().encode("utf-8")
    return (b"\xef\xbb\xbf" if has_utf8_bom else b"") + encoded


def patch_server_character_text(value: Any) -> Any:
    output = copy.deepcopy(value)
    if not isinstance(output, list) or len(output) != 1 or len(output[0]) < 8:
        raise PublishError("119996 server character text row shape drifted")
    before = "造成 48 倍火属性伤害，随即引发大范围火焰爆炸造成 65 倍伤害"
    if output[0][5].count(before) != 1 or output[0][7].count(before) != 1:
        raise PublishError("119996 server active-skill description baseline drifted")
    common = "领域内的敌人持续受到火属性伤害"
    if output[0][5].count(common) != 1 or output[0][7].count(common) != 1:
        raise PublishError("119996 server field-damage description baseline drifted")
    output[0][5] = output[0][5].replace(
        before, "造成 23.25 倍火属性伤害，随即引发大范围火焰爆炸造成 31.5 倍伤害"
    ).replace(common, "领域内的敌人持续受到合计 19.5 倍火属性伤害")
    output[0][7] = output[0][7].replace(
        before, "造成 31 倍火属性伤害，随即引发大范围火焰爆炸造成 42 倍伤害"
    ).replace(common, "领域内的敌人持续受到合计 26 倍火属性伤害")
    return output


def build_server_outputs(
    share: dict[str, Any], client_gacha_inner: bytes
) -> tuple[dict[Path, bytes], dict[str, Any]]:
    outputs: dict[Path, bytes] = {}
    for relative, incoming_rows in share["server_rows"].items():
        path = SOURCE_ROOT / "assets" / relative
        raw = path.read_bytes()
        current = json.loads(raw.decode("utf-8-sig"))
        if CHARACTER_ID in current:
            raise PublishError(f"119996 already exists in server table: {relative}")
        incoming = copy.deepcopy(incoming_rows[CHARACTER_ID])
        if relative == "cdndata/character_text.json":
            incoming = patch_server_character_text(incoming)
        current[CHARACTER_ID] = incoming
        outputs[path] = json_output(raw, current)

    client_rows = client_gacha_rows(client_gacha_inner)
    client_by_id = {row["id"]: row for row in client_rows}
    package_pool = copy.deepcopy(
        share["server_pool"]["gacha.json"][ABYSS_GACHA_ID]
    )
    server_five = package_pool["pool"]["1"]
    if len(server_five) != 250 or {row["id"] for row in server_five} != set(client_by_id):
        raise PublishError("client/server abyss pool membership disagrees")
    authoritative_fields = (
        "rank", "odds", "isRateUp", "isLimited", "isExchangeable",
        "trialReadingForced",
    )
    mismatches: list[tuple[int, str]] = []
    for row in server_five:
        approved = client_by_id[row["id"]]
        for field in authoritative_fields:
            if row.get(field) != approved[field]:
                mismatches.append((row["id"], field))
            row[field] = approved[field]
    if len(mismatches) != 217 or {field for _id, field in mismatches} != {"isExchangeable"}:
        raise PublishError(f"package client/server mismatch set drifted: {mismatches[:10]}")
    if sum(row["odds"] for row in server_five) != 1_593_000:
        raise PublishError("abyss five-star odds total drifted")
    if sum(bool(row["isExchangeable"]) for row in server_five) != 32:
        raise PublishError("client-authoritative exchangeable count drifted")
    if sum(bool(row["isRateUp"]) for row in server_five) != 14:
        raise PublishError("abyss rate-up count drifted")
    featured = server_five[:14]
    if not all(row["isRateUp"] for row in featured) or any(
        row["isRateUp"] for row in server_five[14:]
    ):
        raise PublishError("the 14 abyss rate-up rows are not a contiguous prefix")
    lion = featured[0]
    if lion["id"] != 119996 or lion["odds"] != 40356 or lion["isExchangeable"]:
        raise PublishError("119996 abyss settings drifted")
    if any(row["odds"] != 10620 or not row["isExchangeable"] for row in featured[1:]):
        raise PublishError("existing featured abyss settings drifted")

    for relative in ("gacha.json", "gacha_cnmod.json"):
        path = SOURCE_ROOT / "assets" / relative
        raw = path.read_bytes()
        current = json.loads(raw.decode("utf-8-sig"))
        if ABYSS_GACHA_ID not in current:
            raise PublishError(f"current abyss pool is missing: {path}")
        current[ABYSS_GACHA_ID] = package_pool
        outputs[path] = json_output(raw, current)
    for relative in ("cdndata/gacha.json", "cdndata/gacha_feature_content.json"):
        path = SOURCE_ROOT / "assets" / relative
        current = json.loads(path.read_text(encoding="utf-8-sig"))
        incoming = share["server_pool"][relative][ABYSS_GACHA_ID]
        if current.get(ABYSS_GACHA_ID) != incoming:
            raise PublishError(f"unreviewed CDN gacha metadata difference remains: {relative}")

    json_path = SOURCE_ROOT / "docs/generated/character_table.json"
    json_raw = json_path.read_bytes()
    lookup = json.loads(json_raw.decode("utf-8-sig"))
    if any(int(row["id"]) == DOC_ROW["id"] for row in lookup):
        raise PublishError("119996 already exists in generated character JSON")
    lookup.append(copy.deepcopy(DOC_ROW))
    lookup.sort(key=lambda row: int(row["id"]))
    outputs[json_path] = json_output(json_raw, lookup)
    csv_path = SOURCE_ROOT / "docs/generated/character_table.csv"
    outputs[csv_path] = build_character_csv(csv_path.read_bytes())

    return outputs, {
        "character_added": 119996,
        "gacha_five_star_count": len(server_five),
        "gacha_odds_sum": sum(row["odds"] for row in server_five),
        "gacha_exchangeable_count": sum(bool(row["isExchangeable"]) for row in server_five),
        "client_authoritative_exchange_repairs": len(mismatches),
        "gacha_files": ["assets/gacha.json", "assets/gacha_cnmod.json"],
    }


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for member in sorted(payloads):
            info = zipfile.ZipInfo(member, (2026, 8, 23, 18, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(payloads):
            raise PublishError("active archive member order mismatch")
        for member, expected in payloads.items():
            if archive.read(member) != expected:
                raise PublishError(f"active archive readback failed: {member}")
    return raw


def updated_manifest(
    manifest: dict[str, Any], archive: bytes, payloads: dict[str, bytes]
) -> bytes:
    value = copy.deepcopy(manifest)
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "玛格诺斯、角色平衡、战阵奖励与深渊横幅 1.4.87",
        "description": (
            "新增玛格诺斯并按确认值调整主动技、能力3和专属强化弹射；统一风巨蜥进化前后技能与位置限制；"
            "采用泳装希尔媞包内能力改动，并更新战阵300次奖励预览、深渊池及黑金列表横幅。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive),
        "files": sorted(payloads),
        "changes": [
            "新增火属性★5玛格诺斯（119996）的完整角色、玛纳板、主动技、专属强化弹射、立绘、像素演出、语音及双端技能切入资源。",
            "玛格诺斯进化前主动技完整单目标理论倍率统一为74.25倍，进化后为99倍；能力3冲刺与强化弹射全体伤害均为10倍。",
            "玛格诺斯专属强化弹射PF1保持19.35倍，PF2调整为25倍，PF3调整为35倍。",
            "风巨蜥能力1/3/4/5仅主位生效，能力6仅副位生效，其他能力数值保持当前终态。",
            "风巨蜥主动技进化前后统一：普通单部位27段满级40倍；Fever激光与旋风各40段满级60倍；Fever爪击普通单部位6段满级60倍。",
            "完整采用泳装希尔媞包内六条能力与队长技修订，并纳入其已审查的同路径资源替换。",
            "深渊五星池扩为250名：玛格诺斯0.38%不可兑换，原13名UP各0.1%可兑换；客户端权威兑换字段同步回服务端。",
            "将深渊扭蛋扩展名列表兼容横幅替换为朋友包黑金版；当前黑金主横幅和PNG列表横幅保持不变。",
            "战阵之宴event_id=7总击破300次客户端预览保留星导石×2000，第二项改为深渊十连券（999014）×25。",
            "未纳入朋友包对110个既有角色玛纳板2开放时间窗的无关改动。",
        ],
        "created_at": "2026-08-23",
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
        f"| 2026-08-23 | character/ability/skill/power_flip | 119996 | 新增玛格诺斯完整角色并调整主动技99倍、能力3双10倍、PF2 25倍与PF3 35倍 | 1.4.87 | active统一增量包 |{newline}"
        f"| 2026-08-23 | ability/skill | 149998 | 仅应用主副位限制并统一进化前后主动技：普通40倍、三类Fever各60倍 | 1.4.87 | active统一增量包 |{newline}"
        f"| 2026-08-23 | ability/leader_ability | 149996 | 完整采用朋友包内泳装希尔媞六能力与队长技修订 | 1.4.87 | active统一增量包 |{newline}"
        f"| 2026-08-23 | gacha/banner | 990001 | 深渊五星池加入玛格诺斯并将扩展名列表兼容横幅统一为黑金版 | 1.4.87 | active统一增量包 |{newline}"
        f"| 2026-08-23 | raid_event_overall_reward | event_id=7/300 | 300次奖励预览改为星导石2000加深渊十连券25 | 1.4.87 | active统一增量包 |{newline}"
    )
    return text.replace(marker, marker + rows, 1).encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".lion-1.4.87.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def assert_target(path: Path) -> None:
    path.resolve(strict=False).relative_to(SOURCE_ROOT.resolve(strict=True))


def build_targets(
    manifest_raw: bytes,
    archive_raw: bytes,
    payloads: dict[str, bytes],
    server_outputs: dict[Path, bytes],
    changelog_raw: bytes,
) -> dict[str, tuple[Path, bytes]]:
    targets: dict[str, tuple[Path, bytes]] = {}

    def add(label: str, path: Path, raw: bytes) -> None:
        assert_target(path)
        if label in targets or path in (entry[0] for entry in targets.values()):
            raise PublishError(f"duplicate publication target: {path}")
        targets[label] = (path, raw)

    add("active-archive", SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME, archive_raw)
    for member, raw in payloads.items():
        add(f"production-{member}", SOURCE_ROOT / "assets/asset-patch" / member, raw)
    for path, raw in server_outputs.items():
        add(f"source-{path.relative_to(SOURCE_ROOT).as_posix()}", path, raw)
    add("changelog", SOURCE_ROOT / "assets/asset-patch/changelog.md", changelog_raw)
    add("manifest", SOURCE_ROOT / "assets/asset-patch/manifest.json", manifest_raw)
    return targets


def apply_targets(
    targets: dict[str, tuple[Path, bytes]], report: dict[str, Any]
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TOOL_ROOT / "work" / f"lion-1.4.87-backup-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    existence: dict[str, bool] = {}
    for label, (path, _raw) in targets.items():
        existence[label] = path.is_file()
        if existence[label]:
            destination = backup / label
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    (backup / "existence.json").write_text(
        json.dumps(existence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        for label, (path, raw) in targets.items():
            if label != "manifest":
                atomic_write(raw, path)
        atomic_write(targets["manifest"][1], targets["manifest"][0])
        for label, (path, expected) in targets.items():
            if not path.is_file() or path.read_bytes() != expected:
                raise PublishError(f"publication readback failed: {label}")
        manifest = json.loads(
            (SOURCE_ROOT / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
        )
        matches = [entry for entry in manifest["patches"] if entry.get("id") == PATCH_ID]
        if manifest.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
            raise PublishError("manifest readback registration failed")
        archive_path = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
        with zipfile.ZipFile(archive_path) as archive:
            if archive.namelist() != matches[0]["files"]:
                raise PublishError("archive and manifest file lists disagree")
        if sha256_file(archive_path) != matches[0]["archive_integrity"][0]["sha256"]:
            raise PublishError("active archive SHA-256 readback failed")
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
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return backup


def verify_existing_release() -> dict[str, Any]:
    manifest_path = SOURCE_ROOT / "assets/asset-patch/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    entries = [entry for entry in manifest.get("patches", []) if entry.get("id") == PATCH_ID]
    if manifest.get("cdn_version") != PATCH_VERSION or len(entries) != 1:
        raise PublishError("published manifest registration is missing or ambiguous")
    entry = entries[0]
    archive_path = SOURCE_ROOT / "assets/asset-patch/active" / entry["archive"]
    integrity = entry["archive_integrity"][0]
    if (
        not archive_path.is_file()
        or archive_path.stat().st_size != integrity["size"]
        or sha256_file(archive_path) != integrity["sha256"]
    ):
        raise PublishError("published archive integrity drifted")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.namelist() != entry["files"] or len(entry["files"]) not in {120, 121, 133, 134}:
            raise PublishError("published archive member list drifted")
        payloads = {name: archive.read(name) for name in archive.namelist()}
    for member, expected in payloads.items():
        direct = SOURCE_ROOT / "assets/asset-patch" / member
        if not direct.is_file() or direct.read_bytes() != expected:
            raise PublishError(f"direct production member drifted: {member}")

    share = read_share()
    ability_raw = payloads[member_name(ABILITY_LOGICAL)]
    _ability, ability_rows = raw_rows(ability_raw, ABILITY_LOGICAL)
    lion_a3 = flat_row(ability_rows["1199963"], ABILITY_LOGICAL, "1199963")
    if (
        lion_a3[5][51:53] != ["1000000", "1000000"]
        or lion_a3[6][51:53] != ["1000000", "1000000"]
    ):
        raise PublishError("published 119996 ability 3 multipliers drifted")
    wind_positions = {
        key: {row[6] for row in flat_row(ability_rows[key], ABILITY_LOGICAL, key)}
        for key in ("1499981", "1499983", "1499984", "1499985", "1499986")
    }
    expected_positions = {
        "1499981": {"202"}, "1499983": {"202"}, "1499984": {"202"},
        "1499985": {"202"}, "1499986": {"203"},
    }
    if wind_positions != expected_positions:
        raise PublishError(f"published wind position limits drifted: {wind_positions}")
    for key in (f"149996{index}" for index in range(1, 7)):
        expected = base64.b64decode(share["payload"][ABILITY_LOGICAL][key])
        if ability_rows.get(key) != expected:
            raise PublishError(f"published swim Shilty package row drifted: {key}")
    leader_logical = "master/ability/leader_ability.orderedmap"
    _leader, leader_rows = raw_rows(payloads[member_name(leader_logical)], leader_logical)
    expected_leader = base64.b64decode(share["payload"][leader_logical]["149996"])
    if leader_rows.get("149996") != expected_leader:
        raise PublishError("published swim Shilty leader row drifted")

    lion_active: dict[int, float] = {}
    for form, logical in LION_SKILL_LOGICALS.items():
        tree = decode_dsl(payloads[member_name(logical)], logical)
        attacks = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
        ]
        if len(attacks) != 3:
            raise PublishError(f"published lion active shape drifted: form {form}")
        lion_active[form] = sum(
            hits * float(node[6][0]["max"])
            for hits, node in zip((1, 8, 16), attacks)
        )
    if lion_active != {1: 74.25, 2: 99.0}:
        raise PublishError(f"published lion active totals drifted: {lion_active}")

    lion_pf: dict[int, float] = {}
    for level, logical in LION_PF_LOGICALS.items():
        pairs = _hit_area_attack_pair(
            decode_dsl(payloads[member_name(logical)], logical), logical
        )
        lion_pf[level] = sum(
            hits * float(attack[6][0]["max"]) for hits, attack in pairs
        )
    expected_pf = {1: 19.35, 2: 25.0, 3: 35.0}
    if any(not math.isclose(lion_pf[key], value, abs_tol=1e-9) for key, value in expected_pf.items()):
        raise PublishError(f"published lion PF totals drifted: {lion_pf}")

    wind_skill: dict[int, dict[str, int | float]] = {}
    for form, logical in WIND_SKILL_LOGICALS.items():
        tree = decode_dsl(payloads[member_name(logical)], logical)
        attacks = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
        ]
        groups: dict[tuple[float, float], int] = {}
        for node in attacks:
            key = (float(node[6][0]["min"]), float(node[6][0]["max"]))
            groups[key] = groups.get(key, 0) + 1
        expected_groups = {
            (1.1111111111111112, 1.4814814814814814): 8,
            (1.125, 1.5): 16,
            (7.5, 10.0): 1,
        }
        tolerance = [
            node for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "ACToleranceOfElement"
        ]
        if groups != expected_groups or any(node[3] != [{"min": -0.1, "max": -0.1}] for node in tolerance):
            raise PublishError(f"published wind active skill drifted: form {form}")
        wind_skill[form] = {"normal": 40, "fever_laser": 60, "fever_whirlwind": 60, "fever_claw": 60}

    raid_logical = RAID_REWARD_LOGICAL
    _raid, raid_rows = raw_rows(payloads[member_name(raid_logical)], raid_logical)
    raid = flat_row(raid_rows[RAID_REWARD_KEY], raid_logical, RAID_REWARD_KEY)[0]
    if raid[7:13] != ["2", "", "2000", "0", "999014", "25"]:
        raise PublishError(f"published raid reward preview drifted: {raid[7:13]}")

    banner = payloads[BANNER_MEMBER]
    banner_png = wf_assets.png_decode(banner)
    if (
        sha256_bytes(banner) != "2f9fce137e7fe8d5ed9e77b665e99f3e7cec5a84443ea653669389f6fe93f42a"
        or wf_assets.png_dims(banner_png) != (510, 180)
    ):
        raise PublishError("published abyss list banner drifted")

    _gacha, gacha_rows = raw_rows(payloads[member_name(GACHA_LOGICAL)], GACHA_LOGICAL)
    client_pool = client_gacha_rows(gacha_rows[GACHA_KEY])
    server_pool = json.loads(
        (SOURCE_ROOT / "assets/gacha.json").read_text(encoding="utf-8-sig")
    )[ABYSS_GACHA_ID]["pool"]["1"]
    if (
        len(client_pool) != 250
        or len(server_pool) != 250
        or sum(row["odds"] for row in server_pool) != 1_593_000
        or sum(bool(row["isExchangeable"]) for row in server_pool) != 32
    ):
        raise PublishError("published abyss pool totals drifted")
    characters = json.loads(
        (SOURCE_ROOT / "assets/character.json").read_text(encoding="utf-8-sig")
    )
    if characters.get(CHARACTER_ID, {}).get("name") != "玛格诺斯":
        raise PublishError("published 119996 server character row drifted")

    return {
        "cdn_version": PATCH_VERSION,
        "archive": str(archive_path),
        "archive_sha256": integrity["sha256"],
        "members": len(payloads),
        "lion_active": lion_active,
        "lion_pf": lion_pf,
        "lion_ability3": {"dash": 10, "power_flip_all_enemies": 10},
        "wind_positions": {key: next(iter(value)) for key, value in wind_positions.items()},
        "wind_active": wind_skill,
        "swim_shilty": "six ability rows and leader row exactly match reviewed package",
        "raid_300": raid[7:13],
        "abyss_list_banner": {"size": [510, 180], "sha256": sha256_bytes(banner)},
        "abyss_pool": {"five_star": 250, "odds_sum": 1_593_000, "exchangeable": 32},
    }


def sync_runtime_preserving_local_state() -> dict[str, Any]:
    verification = verify_existing_release()
    source_manifest = json.loads(
        (SOURCE_ROOT / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
    )
    source_entry = next(
        entry for entry in source_manifest["patches"] if entry.get("id") == PATCH_ID
    )
    runtime_manifest_path = RUNTIME_ROOT / "assets/asset-patch/manifest.json"
    runtime_changelog_path = RUNTIME_ROOT / "assets/asset-patch/changelog.md"
    if not RUNTIME_ROOT.is_dir() or not runtime_manifest_path.is_file():
        raise PublishError(f"runtime mirror is unavailable: {RUNTIME_ROOT}")
    runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8-sig"))
    if any(entry.get("id") == PATCH_ID for entry in runtime_manifest.get("patches", [])):
        raise PublishError("runtime mirror already contains this patch id")
    runtime_version = runtime_manifest.get("cdn_version")
    if runtime_version not in {BASE_VERSION, PATCH_VERSION}:
        raise PublishError(f"runtime CDN version cannot be safely merged: {runtime_version}")
    source_ids = {entry.get("id") for entry in source_manifest["patches"]}
    preserved_runtime_patch_ids = [
        entry.get("id") for entry in runtime_manifest.get("patches", [])
        if entry.get("id") not in source_ids
    ]
    merged_manifest = copy.deepcopy(runtime_manifest)
    merged_manifest["patches"].append(copy.deepcopy(source_entry))
    merged_manifest["cdn_version"] = PATCH_VERSION
    merged_manifest_raw = (
        json.dumps(merged_manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    source_changelog = (
        SOURCE_ROOT / "assets/asset-patch/changelog.md"
    ).read_text(encoding="utf-8-sig")
    runtime_changelog = runtime_changelog_path.read_text(encoding="utf-8-sig")
    newline = "\r\n" if "\r\n" in runtime_changelog else "\n"
    marker = f"|---|---|---|---|---|---|{newline}"
    if marker not in runtime_changelog:
        raise PublishError("runtime changelog table header drifted")
    release_rows = [line for line in source_changelog.splitlines() if "| 1.4.87 |" in line]
    if len(release_rows) != 5:
        raise PublishError("source 1.4.87 changelog row set drifted")
    if any(row in runtime_changelog.splitlines() for row in release_rows):
        raise PublishError("runtime changelog already contains part of this release")
    merged_changelog_raw = runtime_changelog.replace(
        marker, marker + newline.join(release_rows) + newline, 1
    ).encode("utf-8")

    targets: dict[str, tuple[Path, bytes]] = {}

    def add(relative: str, raw: bytes) -> None:
        target = (RUNTIME_ROOT / relative).resolve(strict=False)
        target.relative_to(RUNTIME_ROOT.resolve(strict=True))
        if ".cdn" in target.parts:
            raise PublishError(f"base .cdn write is forbidden: {target}")
        if relative in targets:
            raise PublishError(f"duplicate runtime target: {relative}")
        targets[relative] = (target, raw)

    add("assets/asset-patch/manifest.json", merged_manifest_raw)
    add("assets/asset-patch/changelog.md", merged_changelog_raw)
    archive_relative = f"assets/asset-patch/active/{source_entry['archive']}"
    add(
        archive_relative,
        (SOURCE_ROOT / archive_relative).read_bytes(),
    )
    for member in source_entry["files"]:
        relative = f"assets/asset-patch/{member}"
        add(relative, (SOURCE_ROOT / relative).read_bytes())

    character_files = (
        "assets/character.json",
        "assets/cdndata/character.json",
        "assets/cdndata/character_text.json",
        "assets/mana_node.json",
    )
    for relative in character_files:
        source_path = SOURCE_ROOT / relative
        runtime_path = RUNTIME_ROOT / relative
        source_value = json.loads(source_path.read_text(encoding="utf-8-sig"))
        runtime_raw = runtime_path.read_bytes()
        runtime_value = json.loads(runtime_raw.decode("utf-8-sig"))
        incoming = copy.deepcopy(source_value[CHARACTER_ID])
        if CHARACTER_ID in runtime_value and runtime_value[CHARACTER_ID] != incoming:
            raise PublishError(f"runtime has a conflicting 119996 row: {relative}")
        runtime_value[CHARACTER_ID] = incoming
        add(relative, json_output(runtime_raw, runtime_value))
    for relative in ("assets/gacha.json", "assets/gacha_cnmod.json"):
        source_value = json.loads((SOURCE_ROOT / relative).read_text(encoding="utf-8-sig"))
        runtime_path = RUNTIME_ROOT / relative
        runtime_raw = runtime_path.read_bytes()
        runtime_value = json.loads(runtime_raw.decode("utf-8-sig"))
        runtime_value[ABYSS_GACHA_ID] = copy.deepcopy(source_value[ABYSS_GACHA_ID])
        add(relative, json_output(runtime_raw, runtime_value))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = RUNTIME_ROOT / ".codex-backups" / f"{stamp}-lion-balance-1.4.87"
    backup.mkdir(parents=True, exist_ok=False)
    existence: dict[str, bool] = {}
    for relative, (target, _raw) in targets.items():
        existence[relative] = target.is_file()
        if target.is_file():
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)
    (backup / "existence.json").write_text(
        json.dumps(existence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        for relative, (target, raw) in targets.items():
            if relative != "assets/asset-patch/manifest.json":
                atomic_write(raw, target)
        atomic_write(
            targets["assets/asset-patch/manifest.json"][1],
            targets["assets/asset-patch/manifest.json"][0],
        )
        for relative, (target, expected) in targets.items():
            if not target.is_file() or target.read_bytes() != expected:
                raise PublishError(f"runtime synchronization readback failed: {relative}")
        readback_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8-sig"))
        matches = [entry for entry in readback_manifest["patches"] if entry.get("id") == PATCH_ID]
        if readback_manifest.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
            raise PublishError("runtime merged manifest readback failed")
        if any(
            not any(entry.get("id") == patch_id for entry in readback_manifest["patches"])
            for patch_id in preserved_runtime_patch_ids
        ):
            raise PublishError("a pre-existing runtime patch was lost during merge")
    except Exception:
        for relative, (target, _raw) in reversed(list(targets.items())):
            if existence[relative]:
                atomic_write((backup / relative).read_bytes(), target)
            elif target.exists():
                target.unlink()
        raise

    report = {
        "runtime_root": str(RUNTIME_ROOT),
        "backup": str(backup),
        "paths": len(targets),
        "overwritten": sum(existence.values()),
        "created": len(targets) - sum(existence.values()),
        "cdn_version": PATCH_VERSION,
        "patch_id": PATCH_ID,
        "archive_sha256": verification["archive_sha256"],
        "preserved_runtime_patch_ids": preserved_runtime_patch_ids,
        "base_cdn_touched": False,
        "source_repository_touched_by_sync": False,
    }
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write verified source-repository outputs")
    parser.add_argument("--verify-existing", action="store_true", help="verify the already published 1.4.87 source outputs")
    parser.add_argument("--sync-runtime", action="store_true", help="merge this release into the runtime mirror while preserving local-only patches")
    args = parser.parse_args()

    if args.verify_existing:
        if args.apply or args.sync_runtime:
            raise PublishError("--verify-existing is mutually exclusive with write modes")
        print(json.dumps(verify_existing_release(), ensure_ascii=False, indent=2))
        return 0
    if args.sync_runtime:
        if args.apply:
            raise PublishError("--apply and --sync-runtime are mutually exclusive")
        print(json.dumps(sync_runtime_preserving_local_state(), ensure_ascii=False, indent=2))
        return 0

    manifest = read_manifest()
    share = read_share()
    payloads, client_report, client_gacha_inner = build_client_payloads(manifest, share)
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
        "share_sha256": SHARE_SHA256,
        "archive": str(SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME),
        "archive_size": len(archive_raw),
        "archive_sha256": sha256_bytes(archive_raw),
        "members": len(payloads),
        "client": client_report,
        "server": server_report,
        "source_files": sorted(path.relative_to(SOURCE_ROOT).as_posix() for path in server_outputs),
        "excluded": {
            "share_scripts_executed": False,
            "unrelated_mana_board2_windows_imported": False,
            "raid_server_summary_fix_duplicated": False,
            "rankings_or_raid_rules_changed": False,
            "runtime_mirror_touched": False,
        },
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    targets = build_targets(manifest_raw, archive_raw, payloads, server_outputs, changelog_raw)
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
