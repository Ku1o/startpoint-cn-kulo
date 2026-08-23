#!/usr/bin/env python3
"""Safely merge the reviewed 2026-08-23 abyss reroll into the unified 1.4.87 edge.

The three input ZIPs were produced from a mutable runtime workspace.  This tool
therefore pins their hashes, accepts only the six combat tables and seven DSLs,
repairs both gauntlet hubs to player rank 130, and deliberately rejects the
stale event-list and reward-preview tables carried by the raw export.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


TOOL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_ROOT))

import wf_dev_catalog  # noqa: E402
import wf_quest_lib as quest  # noqa: E402
import wf_rogue_build as rogue  # noqa: E402


def _load_publisher():
    path = TOOL_ROOT / "publish_lion_balance_1_4_87_20260823.py"
    spec = importlib.util.spec_from_file_location("lion_1_4_87_publisher", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load unified publisher: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


publisher = _load_publisher()
SOURCE_ROOT = publisher.SOURCE_ROOT
RUNTIME_ROOT = publisher.RUNTIME_ROOT
PATCH_ID = publisher.PATCH_ID
PATCH_VERSION = publisher.PATCH_VERSION
ARCHIVE_NAME = publisher.ARCHIVE_NAME

INPUT_ZIPS = {
    Path(r"F:\pinball-1.4.86-1.4.87-1-08231348.zip"):
        "9db9ef93c203fc9ba842bb071c2d3e2180a1a698bf60b88caa1ded2efe285f86",
    Path(r"F:\pinball-1.4.86-1.4.87-2-08231348.zip"):
        "f17b6e99083614fa9e40707b92f7c752e38dace16e31ca8ff40b4a0eebff4dad",
    Path(r"F:\pinball-1.4.86-1.4.87-3-08231348.zip"):
        "f17b6e99083614fa9e40707b92f7c752e38dace16e31ca8ff40b4a0eebff4dad",
}
COMMON_INPUT = next(iter(INPUT_ZIPS))

SAFE_TABLES = {
    logical: publisher.member_name(logical)
    for logical in (
        "master/battle/boss/general_boss.orderedmap",
        "master/battle/boss/boss_level.orderedmap",
        "master/battle/boss/general_boss_variable.orderedmap",
        "master/battle/field_data.orderedmap",
        "master/battle/zone.orderedmap",
        "master/quest/event/rush_event_quest.orderedmap",
    )
}

DSL_LOGICALS = (
    "battle/action/enemy/action/mod_rogue/immunity_32d64c29eed9.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_560e45608767.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_7a2abe45bc4b.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_9f6dab28fc99.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_b2a114e4f14e.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_b853b0950500.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_c524568a3ba9.action.dsl.amf3.deflate",
)
DSL_MEMBERS = {logical: publisher.member_name(logical) for logical in DSL_LOGICALS}

DROPPED_TABLES = {
    logical: publisher.member_name(logical)
    for logical in (
        "master/battle/zako/general_zako.orderedmap",
        "master/battle/zako/zako_level.orderedmap",
        "master/battle/boss/general_enemy_watch.orderedmap",
        "master/quest/event/rush_event.orderedmap",
        "master/quest/event/rush_event_battle_quest_correction.orderedmap",
        "master/quest/event/event_list.orderedmap",
        "master/quest/event/rush_event_quest_folder.orderedmap",
    )
}

EXPECTED_COMMON_MEMBERS = set(SAFE_TABLES.values()) | set(DSL_MEMBERS.values()) | set(
    DROPPED_TABLES.values()
)
NEW_MEMBERS = set(SAFE_TABLES.values()) | set(DSL_MEMBERS.values())
QUEST_LOGICAL = "master/quest/event/rush_event_quest.orderedmap"
GENERAL_BOSS_LOGICAL = "master/battle/boss/general_boss.orderedmap"
REROLL_CHANGE = (
    "安全合入深渊连战30层重roll：28个普通层实质调整，15/21层仅更新显示文字，"
    "无尽层更新；12层使用隔离克隆Boss，7个免疫DSL随包发布，700098/700099等级均保持130。"
)
CHANGELOG_ROW = (
    "| 2026-08-23 | rush_event_quest/battle | 700099 | "
    "深渊30层阵容安全重roll：28关实质调整、15/21保留战斗配置、无尽更新；"
    "双活动等级保持130 | 1.4.87 | active统一增量包 |"
)
STANDARD_BOSS_ARCHIVE = (
    RUNTIME_ROOT / ".cdn/cn/archive-common-diff/"
    "pinball-1.4.40-1.4.41-1-c75a46f2.zip"
)
STANDARD_BOSS_ARCHIVE_SHA256 = (
    "7b139accfb189b6ad8c7a1070ce0db68efa95b19b951b64edd8abc318d8966b8"
)
STANDARD_BOSS_PAYLOAD_SHA256 = (
    "5924c2f08b1146db387d358bf1ecdf7dad92c7688e28be223eccd413f5b98e44"
)
PINNED_EFFECTIVE_STORE = Path(r"F:\codex\tower-v2-work-20260812\effective-store-v2")
SPECIAL_BOSS_PAYLOAD_SHA256 = {
    "master/battle/boss/orochi.orderedmap":
        "ced08a4b1192c34f63ff13ad19c1bb5ce0893c11278a807000850a660ec876b0",
    "master/battle/boss/orochi_ex.orderedmap":
        "19754b19346d41965b2bc5996b8b54c031ea1e7f2073b962e83f73caa662e917",
    "master/battle/boss/kraken.orderedmap":
        "5f58a171c0996a133b95e1ec0a6583f6d7b9754bb3846c94fcb642a784c927d8",
    "master/battle/boss/conductor.orderedmap":
        "8fe812848b7771843d18bef3a65c205b7f08c953ec50014fbe156ebe9a7377f3",
    "master/battle/boss/touyakiren_ceo.orderedmap":
        "3e2d40b42148c614db5e0ffd794bb8678b0724a13afd3c0af0a02b72c4e062ae",
    "master/battle/boss/fire_sphere.orderedmap":
        "40807756750503ffe56e9f9338b2d9fc7cc9fd378e1181dd9da77bb9063d85d5",
    "master/battle/boss/water_sphere.orderedmap":
        "bcf94c7380eab0788cd94ae99f35fd1ffc51b3d1b5d1921dcd09d5e88f0bd8b2",
    "master/battle/boss/thunder_sphere.orderedmap":
        "7e647c7ba1f94699ee77df8946824955de9ec752f3d724cbb915c7e66c658f06",
    "master/battle/boss/wind_sphere.orderedmap":
        "dc0eef33fc997a072fcb9fcaf00746825b52cfcdada83c7d03494e3ba15d1cf5",
    "master/battle/boss/holy_sphere.orderedmap":
        "904f6bb0d70c5924a7c5f0d1ac8d1bda9773830352c890618a3df136a343dd52",
}
RUNTIME_UPSTREAM_BUILDER_PREPATCH_SHA256 = (
    "3981f9b5c055fe030cf3e0f7fc62fae05f6e05fd9cc4b9c24f02c70a6029b347"
)


class MergeError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_cells(leaf: str) -> list[str]:
    return next(csv.reader(io.StringIO(leaf)))


def csv_leaf(row: list[str]) -> str:
    stream = io.StringIO()
    csv.writer(stream, lineterminator="").writerow(row)
    return stream.getvalue()


def load_manifest(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(
        (root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
    )
    matches = [entry for entry in manifest.get("patches", []) if entry.get("id") == PATCH_ID]
    if manifest.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
        raise MergeError(f"{root}: unified 1.4.87 manifest entry is missing or ambiguous")
    return manifest, matches[0]


def read_inputs() -> dict[str, bytes]:
    for path, expected_hash in INPUT_ZIPS.items():
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise MergeError(f"input ZIP is missing or drifted: {path}")
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None or len(archive.namelist()) != len(set(archive.namelist())):
                raise MergeError(f"input ZIP is corrupt or contains duplicate names: {path}")
            if path != COMMON_INPUT:
                if archive.namelist() != [".empty"] or archive.read(".empty") != b"\n":
                    raise MergeError(f"empty split unexpectedly contains payloads: {path}")
    with zipfile.ZipFile(COMMON_INPUT) as archive:
        names = archive.namelist()
        if set(names) != EXPECTED_COMMON_MEMBERS or len(names) != 20:
            raise MergeError("common reroll ZIP member set drifted")
        return {name: archive.read(name) for name in names}


def terminal_members(
    manifest: dict[str, Any], wanted: set[str], *, root: Path = SOURCE_ROOT
) -> dict[str, bytes]:
    payloads, _sources = publisher.base.terminal_members(root, manifest, wanted)
    missing = wanted - set(payloads)
    if missing:
        raise MergeError(f"current chain at {root} lacks terminal members: {sorted(missing)}")
    return payloads


def repair_quest_payload(
    raw: bytes, current: bytes, *, allow_applied: bool = False
) -> tuple[bytes, dict[str, Any]]:
    raw_tree = quest.parse_node(raw)
    current_tree = quest.parse_node(current)
    if not isinstance(raw_tree, dict) or not isinstance(current_tree, dict):
        raise MergeError("rush_event_quest is not a nested orderedmap")

    raw_rank_values: dict[str, set[str]] = {}
    candidate = copy.deepcopy(raw_tree)
    for event_id in rogue.GAUNTLET_HUB_EVENT_IDS:
        event = candidate.get(event_id)
        if not isinstance(event, dict):
            raise MergeError(f"raw quest table lacks nested event {event_id}")
        raw_rank_values[event_id] = set()
        for quest_key, leaf in event.items():
            if not isinstance(leaf, str):
                raise MergeError(f"raw quest leaf is not CSV: {event_id}/{quest_key}")
            row = csv_cells(leaf)
            if len(row) <= 48:
                raise MergeError(f"raw quest row is too short: {event_id}/{quest_key}")
            raw_rank_values[event_id].add(row[48])
            row[48] = rogue.GAUNTLET_MIN_PLAYER_RANK
            event[quest_key] = csv_leaf(row)
    if raw_rank_values != {"700098": {"(None)"}, "700099": {"(None)"}}:
        raise MergeError(f"expected raw player-rank regression changed: {raw_rank_values}")

    changed_outer = [
        key for key in set(candidate) | set(current_tree)
        if candidate.get(key) != current_tree.get(key)
    ]
    if changed_outer != ["700099"] and not (allow_applied and not changed_outer):
        raise MergeError(f"quest table changes escaped event 700099: {changed_outer}")
    if len(candidate["700099"]) != 31 or set(candidate["700099"]) != {
        *(str(index) for index in range(1, 31)), "99"
    }:
        raise MergeError("event 700099 is not the expected 30-stage plus endless layout")

    changed_rounds: list[str] = []
    display_only_rounds: list[str] = []
    for quest_key, leaf in candidate["700099"].items():
        row = csv_cells(leaf)
        if row[48] != "130":
            raise MergeError(f"candidate player rank was not repaired: 700099/{quest_key}")
        before = csv_cells(current_tree["700099"][quest_key])
        differences = [index for index, pair in enumerate(zip(before, row)) if pair[0] != pair[1]]
        if differences:
            changed_rounds.append(quest_key)
        if differences == [3]:
            display_only_rounds.append(quest_key)
    if not changed_outer and allow_applied:
        changed_rounds = [*(str(index) for index in range(1, 31)), "99"]
        display_only_rounds = ["15", "21"]
    if set(display_only_rounds) != {"15", "21"} or len(changed_rounds) != 31:
        raise MergeError(
            f"reroll round classification drifted: changed={len(changed_rounds)}, "
            f"display-only={display_only_rounds}"
        )
    for event_id in rogue.GAUNTLET_HUB_EVENT_IDS:
        for leaf in candidate[event_id].values():
            if csv_cells(leaf)[48] != "130":
                raise MergeError(f"candidate event {event_id} still contains a non-130 rank")

    rebuilt = quest.build_node(candidate)
    if quest.parse_node(rebuilt) != candidate:
        raise MergeError("sanitized quest table failed build/parse roundtrip")
    return rebuilt, {
        "changed_rounds": len(changed_rounds),
        "substantive_normal_rounds": 28,
        "display_only_rounds": [15, 21],
        "endless_changed": True,
        "rank_repairs": {"700098": 16, "700099": 31},
    }


def audit_inputs(
    manifest: dict[str, Any], raw: dict[str, bytes], *, allow_applied: bool = False
) -> tuple[dict[str, bytes], dict[str, Any]]:
    terminal = terminal_members(manifest, set(SAFE_TABLES.values()) | set(DROPPED_TABLES.values()))
    candidate: dict[str, bytes] = {}
    table_changes: dict[str, list[str]] = {}
    for logical, member in SAFE_TABLES.items():
        if logical == QUEST_LOGICAL:
            candidate[member], quest_report = repair_quest_payload(
                raw[member], terminal[member], allow_applied=allow_applied
            )
            continue
        current_tree = quest.parse_node(terminal[member])
        incoming_tree = quest.parse_node(raw[member])
        changed = sorted(
            key for key in set(current_tree) | set(incoming_tree)
            if current_tree.get(key) != incoming_tree.get(key)
        )
        if (not changed and not allow_applied) or any(
            not key.startswith("mod_rogue_") for key in changed
        ):
            raise MergeError(f"{logical} has unscoped top-level changes: {changed}")
        if not changed and raw[member] != terminal[member]:
            raise MergeError(f"{logical} is semantically equal but bytewise drifted after apply")
        candidate[member] = raw[member]
        table_changes[logical] = changed

    identical_dropped = {
        "master/battle/zako/general_zako.orderedmap",
        "master/battle/zako/zako_level.orderedmap",
        "master/battle/boss/general_enemy_watch.orderedmap",
        "master/quest/event/rush_event.orderedmap",
        "master/quest/event/rush_event_battle_quest_correction.orderedmap",
    }
    for logical in identical_dropped:
        member = DROPPED_TABLES[logical]
        if raw[member] != terminal[member]:
            raise MergeError(f"redundant dropped table unexpectedly differs: {logical}")

    event_list_raw = quest.parse_node(raw[DROPPED_TABLES["master/quest/event/event_list.orderedmap"]])
    event_list_current = quest.parse_node(
        terminal[DROPPED_TABLES["master/quest/event/event_list.orderedmap"]]
    )
    if not all(event_id in event_list_raw for event_id in rogue.GAUNTLET_HUB_EVENT_IDS):
        raise MergeError("raw event_list no longer demonstrates the duplicate direct-entry regression")
    if any(event_id in event_list_current for event_id in rogue.GAUNTLET_HUB_EVENT_IDS):
        raise MergeError("current source terminal unexpectedly contains direct gauntlet entries")

    folder_member = DROPPED_TABLES["master/quest/event/rush_event_quest_folder.orderedmap"]
    raw_folder = quest.parse_node(raw[folder_member])
    current_folder = quest.parse_node(terminal[folder_member])
    raw_preview = csv_cells(raw_folder["700099"]["1"])[7:16]
    current_preview = csv_cells(current_folder["700099"]["1"])[7:16]
    if raw_preview == current_preview or current_preview != [
        "0", "99", "1500", "0", rogue.TOKEN_ID, "50", "0", "11003", "2"
    ]:
        raise MergeError("folder reward-preview regression or fixed terminal value drifted")

    for logical, member in DSL_MEMBERS.items():
        publisher.decode_dsl(raw[member], logical)
        candidate[member] = raw[member]
    referenced = set()
    for leaf in quest.parse_node(candidate[SAFE_TABLES[GENERAL_BOSS_LOGICAL]]).values():
        nodes = leaf.values() if isinstance(leaf, dict) else (leaf,)
        for node in nodes:
            if isinstance(node, str):
                referenced.update(
                    re.findall(r"battle/action/enemy/action/mod_rogue/immunity_[0-9a-f]+", node)
                )
    expected_references = {logical.removesuffix(".action.dsl.amf3.deflate") for logical in DSL_LOGICALS}
    if referenced != expected_references:
        raise MergeError(f"immunity DSL references drifted: {sorted(referenced)}")
    if set(candidate) != NEW_MEMBERS:
        raise MergeError(f"safe candidate member set drifted: {len(candidate)}")
    return candidate, {
        "table_changes": table_changes,
        "quest": quest_report,
        "dsl_references": sorted(referenced),
        "dropped": sorted(set(DROPPED_TABLES.values())),
    }


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    return publisher.zip_payloads(payloads)


def update_manifest(
    manifest: dict[str, Any], payloads: dict[str, bytes], archive_raw: bytes
) -> bytes:
    value = copy.deepcopy(manifest)
    entry = next(item for item in value["patches"] if item.get("id") == PATCH_ID)
    entry["name"] = "玛格诺斯、角色平衡、战阵奖励、深渊横幅与30层重roll 1.4.87"
    if "深渊30层" not in entry.get("description", ""):
        entry["description"] = entry.get("description", "").rstrip("。") + (
            "；安全合入深渊30层重roll及其隔离Boss/免疫DSL，活动入口、固定奖励与等级约束保持终态。"
        )
    changes = entry.setdefault("changes", [])
    if REROLL_CHANGE not in changes:
        changes.append(REROLL_CHANGE)
    entry["archive_size"] = len(archive_raw)
    entry["files"] = sorted(payloads)
    entry["archive_integrity"] = [{
        "name": ARCHIVE_NAME,
        "size": len(archive_raw),
        "sha256": sha256_bytes(archive_raw),
        "members": len(payloads),
    }]
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def update_changelog(raw: bytes) -> bytes:
    text = raw.decode("utf-8-sig")
    if CHANGELOG_ROW in text.splitlines():
        return raw
    newline = "\r\n" if "\r\n" in text else "\n"
    marker = f"|---|---|---|---|---|---|{newline}"
    if marker not in text:
        raise MergeError("asset-patch changelog table header drifted")
    return text.replace(marker, marker + CHANGELOG_ROW + newline, 1).encode("utf-8")


def build_source_candidate() -> tuple[dict[str, bytes], dict[str, bytes], dict[str, Any]]:
    publisher.verify_existing_release()
    manifest, entry = load_manifest(SOURCE_ROOT)
    if len(entry["files"]) != 120:
        raise MergeError(f"source release is not the expected pre-merge 120-member build: {len(entry['files'])}")
    archive_path = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
    with zipfile.ZipFile(archive_path) as archive:
        old_payloads = {name: archive.read(name) for name in archive.namelist()}
    raw = read_inputs()
    additions, audit = audit_inputs(manifest, raw)
    overlap = set(old_payloads) & set(additions)
    if overlap:
        raise MergeError(f"reroll additions overlap the existing unified payloads: {sorted(overlap)}")
    payloads = {**old_payloads, **additions}
    if len(payloads) != 133:
        raise MergeError(f"merged member count drifted: {len(payloads)}")
    archive_raw = zip_payloads(payloads)
    targets = {
        f"assets/asset-patch/active/{ARCHIVE_NAME}": archive_raw,
        "assets/asset-patch/changelog.md": update_changelog(
            (SOURCE_ROOT / "assets/asset-patch/changelog.md").read_bytes()
        ),
    }
    for member in additions:
        targets[f"assets/asset-patch/{member}"] = additions[member]
    targets["assets/asset-patch/manifest.json"] = update_manifest(manifest, payloads, archive_raw)
    report = {
        "input_zip": str(COMMON_INPUT),
        "input_sha256": INPUT_ZIPS[COMMON_INPUT],
        "old_members": len(old_payloads),
        "added_members": len(additions),
        "new_members": len(payloads),
        "audit": audit,
        "archive_size": len(archive_raw),
        "archive_sha256": sha256_bytes(archive_raw),
    }
    return targets, old_payloads, report


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".abyss-reroll-1.4.87.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def apply_file_targets(
    root: Path, targets: dict[str, bytes], backup: Path, manifest_relative: str
) -> None:
    resolved_root = root.resolve(strict=True)
    backup.mkdir(parents=True, exist_ok=False)
    existence: dict[str, bool] = {}
    for relative in targets:
        target = (root / relative).resolve(strict=False)
        target.relative_to(resolved_root)
        existence[relative] = target.is_file()
        if target.is_file():
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)
    (backup / "existence.json").write_text(
        json.dumps(existence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        for relative, raw in targets.items():
            if relative != manifest_relative:
                atomic_write(root / relative, raw)
        atomic_write(root / manifest_relative, targets[manifest_relative])
        for relative, expected in targets.items():
            if (root / relative).read_bytes() != expected:
                raise MergeError(f"write readback failed: {root / relative}")
    except Exception:
        for relative in reversed(list(targets)):
            target = root / relative
            if existence[relative]:
                atomic_write(target, (backup / relative).read_bytes())
            elif target.is_file():
                target.unlink()
        raise


def validate_chain(payloads: dict[str, bytes], raw_inputs: dict[str, bytes]) -> dict[str, Any]:
    qt = quest.parse_node(payloads[SAFE_TABLES[QUEST_LOGICAL]])
    fd = quest.parse_node(payloads[SAFE_TABLES["master/battle/field_data.orderedmap"]])
    zone = quest.parse_node(payloads[SAFE_TABLES["master/battle/zone.orderedmap"]])
    gb = quest.parse_node(payloads[SAFE_TABLES[GENERAL_BOSS_LOGICAL]])
    gv = quest.parse_node(
        payloads[SAFE_TABLES["master/battle/boss/general_boss_variable.orderedmap"]]
    )
    gz = quest.parse_node(
        raw_inputs[DROPPED_TABLES["master/battle/zako/general_zako.orderedmap"]]
    )
    standard_logical = "master/battle/boss/standard_boss.orderedmap"
    standard_member = publisher.member_name(standard_logical)
    if (
        not STANDARD_BOSS_ARCHIVE.is_file()
        or sha256_file(STANDARD_BOSS_ARCHIVE) != STANDARD_BOSS_ARCHIVE_SHA256
    ):
        raise MergeError("pinned official standard_boss dependency archive is missing or drifted")
    with zipfile.ZipFile(STANDARD_BOSS_ARCHIVE) as archive:
        standard_raw = archive.read(standard_member)
    if sha256_bytes(standard_raw) != STANDARD_BOSS_PAYLOAD_SHA256:
        raise MergeError("pinned official standard_boss payload drifted")
    standard = quest.parse_node(standard_raw)
    special_levels: dict[str, Any] = {}
    for logical, expected_hash in SPECIAL_BOSS_PAYLOAD_SHA256.items():
        digest = publisher.core.sha1_path(logical)
        path = PINNED_EFFECTIVE_STORE / digest[:2] / digest[2:]
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise MergeError(f"pinned special-boss dependency is missing or drifted: {logical}")
        table = quest.parse_node(path.read_bytes())
        special_levels.update(
            (str(code), node) for code, node in table.items() if isinstance(node, dict)
        )
    previous_special_levels = rogue._SPECIAL_LV
    rogue._SPECIAL_LV = special_levels
    try:
        reports = rogue.validate_event_chain(
            "700099",
            qt=qt,
            fd=fd,
            zone=zone,
            enemies=set(gb) | set(standard) | set(gz),
            zakos=set(gz),
            lv_ceil=standard,
            lv_floor=gv,
            lv_gb=gb,
        )
    finally:
        rogue._SPECIAL_LV = previous_special_levels
    failed = [report for report in reports if not report.get("ok")]
    if len(reports) != 31 or failed:
        raise MergeError(f"event 700099 chain validation failed: {failed}")
    return {"quests": len(reports), "passed": len(reports)}


def verify_release(expected_old_payloads: dict[str, bytes] | None = None) -> dict[str, Any]:
    base_report = publisher.verify_existing_release()
    manifest, entry = load_manifest(SOURCE_ROOT)
    member_count = len(entry["files"])
    if member_count not in {133, 134} or entry["archive_integrity"][0].get("members") != member_count:
        raise MergeError("published reroll does not contain the expected 133/134 members")
    archive_path = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None or archive.namelist() != sorted(entry["files"]):
            raise MergeError("published archive ordering/integrity drifted")
        payloads = {name: archive.read(name) for name in archive.namelist()}
    if expected_old_payloads is not None:
        for member, expected in expected_old_payloads.items():
            if payloads.get(member) != expected:
                raise MergeError(f"pre-existing unified member changed during merge: {member}")
    raw = read_inputs()
    _candidate, audit = audit_inputs(manifest, raw, allow_applied=True)
    for member in NEW_MEMBERS:
        direct = SOURCE_ROOT / "assets/asset-patch" / member
        if not direct.is_file() or direct.read_bytes() != payloads[member]:
            raise MergeError(f"new direct member drifted: {member}")
    chain = validate_chain(payloads, raw)
    changelog = (SOURCE_ROOT / "assets/asset-patch/changelog.md").read_text(encoding="utf-8-sig")
    if changelog.splitlines().count(CHANGELOG_ROW) != 1 or entry.get("changes", []).count(REROLL_CHANGE) != 1:
        raise MergeError("reroll changelog/manifest registration is not unique")
    return {
        **base_report,
        "members": len(payloads),
        "archive_size": archive_path.stat().st_size,
        "archive_sha256": sha256_file(archive_path),
        "chain": chain,
        "quest": audit["quest"],
        "added_members": len(NEW_MEMBERS),
    }


def apply_source() -> dict[str, Any]:
    targets, old_payloads, report = build_source_candidate()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TOOL_ROOT / "work" / f"abyss-reroll-1.4.87-backup-{stamp}"
    apply_file_targets(
        SOURCE_ROOT, targets, backup, "assets/asset-patch/manifest.json"
    )
    try:
        verification = verify_release(old_payloads)
    except Exception:
        existence = json.loads((backup / "existence.json").read_text(encoding="utf-8"))
        for relative in reversed(list(targets)):
            target = SOURCE_ROOT / relative
            if existence[relative]:
                atomic_write(target, (backup / relative).read_bytes())
            elif target.is_file():
                target.unlink()
        raise
    report["backup"] = str(backup)
    report["verification"] = verification
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def snapshot_tree(root: Path, backup: Path) -> set[str]:
    existing: set[str] = set()
    if not root.is_dir():
        return existing
    for path in root.rglob("*"):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            existing.add(relative)
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    return existing


def restore_tree_files(root: Path, backup: Path, existing: set[str]) -> None:
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file() and path.relative_to(root).as_posix() not in existing:
                path.unlink()
    for relative in existing:
        atomic_write(root / relative, (backup / relative).read_bytes())


def verify_runtime_catalog(out_dir: Path, expected_size: int) -> dict[str, Any]:
    catalog_path = out_dir / f"catalog-cn-{PATCH_VERSION}.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
    archives = catalog["catalogInput"]["archives"]
    matches = [
        row for row in archives
        if row.get("relativePath", "").replace("\\", "/").endswith("/" + ARCHIVE_NAME)
        or row.get("relativePath") == ARCHIVE_NAME
    ]
    if len(matches) != 1 or matches[0].get("compressedBytes") != expected_size:
        raise MergeError(f"runtime dev catalog unified archive entry drifted: {matches}")
    stale = [row for row in archives if "08231348" in row.get("relativePath", "")]
    if stale:
        raise MergeError(f"runtime dev catalog still contains manual reroll ZIPs: {stale}")
    return {"catalog": str(catalog_path), "archives": len(archives)}


def patched_runtime_upstream_builder() -> bytes:
    """Add only the table-wide rank repair to the locally advanced upstream tool."""
    path = RUNTIME_ROOT / "mod-tools-upstream/wf_rogue_build.py"
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if "def enforce_gauntlet_quest_table_player_rank(" in text:
        if "save(Q_QUEST, enforce_gauntlet_quest_table_player_rank(qt))" not in text:
            raise MergeError("runtime upstream rank helper exists but is not used at save")
        return raw
    if sha256_bytes(raw) != RUNTIME_UPSTREAM_BUILDER_PREPATCH_SHA256:
        raise MergeError("runtime upstream builder changed since audit; refusing to overwrite it")
    join_block = '''def join(row: list[str], as_bytes: bool):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(row)
    s = buf.getvalue()
    return s.encode("utf-8") if as_bytes else s


'''
    helper = '''def enforce_gauntlet_quest_table_player_rank(quest_table: dict) -> dict:
    """Repair both gauntlet hubs, including rows inherited from an older roll."""
    for event_id in GAUNTLET_HUB_EVENT_IDS:
        event = quest_table.get(event_id)
        if event is None:
            continue
        if not isinstance(event, dict):
            raise ValueError(f"rush_event_quest[{event_id}] is not a nested map")
        for quest_key, leaf in event.items():
            if isinstance(leaf, dict):
                raise ValueError(
                    f"rush_event_quest[{event_id}][{quest_key}] is not a CSV leaf"
                )
            row = cells(leaf)
            if len(row) <= 48:
                raise ValueError(
                    f"rush_event_quest[{event_id}][{quest_key}] has only {len(row)} columns"
                )
            enforce_gauntlet_player_rank(row)
            event[quest_key] = join(row, isinstance(leaf, bytes))
    return quest_table


'''
    if text.count(join_block) != 1 or text.count("    save(Q_QUEST, qt)\n") != 1:
        raise MergeError("runtime upstream builder patch anchors drifted")
    text = text.replace(join_block, join_block + helper, 1)
    text = text.replace(
        "    save(Q_QUEST, qt)\n",
        "    save(Q_QUEST, enforce_gauntlet_quest_table_player_rank(qt))\n",
        1,
    )
    return text.encode("utf-8")


def sync_runtime() -> dict[str, Any]:
    verification = verify_release()
    source_manifest, source_entry = load_manifest(SOURCE_ROOT)
    runtime_manifest, _runtime_entry = load_manifest(RUNTIME_ROOT)
    merged_manifest = copy.deepcopy(runtime_manifest)
    merged_manifest["patches"] = [
        copy.deepcopy(source_entry) if item.get("id") == PATCH_ID else item
        for item in merged_manifest["patches"]
    ]
    merged_manifest["cdn_version"] = PATCH_VERSION
    targets: dict[str, bytes] = {
        "assets/asset-patch/manifest.json": (
            json.dumps(merged_manifest, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8"),
        "assets/asset-patch/changelog.md": update_changelog(
            (RUNTIME_ROOT / "assets/asset-patch/changelog.md").read_bytes()
        ),
        f"assets/asset-patch/active/{ARCHIVE_NAME}": (
            SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
        ).read_bytes(),
        "tools/fantasy-gauntlet-mod-tools/wf_rogue_build.py": (
            SOURCE_ROOT / "tools/fantasy-gauntlet-mod-tools/wf_rogue_build.py"
        ).read_bytes(),
        "mod-tools-upstream/wf_rogue_build.py": patched_runtime_upstream_builder(),
    }
    for member in NEW_MEMBERS:
        targets[f"assets/asset-patch/{member}"] = (
            SOURCE_ROOT / "assets/asset-patch" / member
        ).read_bytes()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = RUNTIME_ROOT / ".codex-backups" / f"{stamp}-abyss-reroll-1.4.87"
    catalog_dir = RUNTIME_ROOT / "assets/asset-patch/dev-catalog"
    catalog_backup = backup / "catalog-before"
    cache_path = RUNTIME_ROOT / ".cdn/dev-catalog-digest-cache.json"
    cache_existed = cache_path.is_file()
    apply_file_targets(
        RUNTIME_ROOT, targets, backup / "files", "assets/asset-patch/manifest.json"
    )
    catalog_existing = snapshot_tree(catalog_dir, catalog_backup)
    if cache_existed:
        destination = backup / "dev-catalog-digest-cache.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_path, destination)
    try:
        manifest_path, issues, summary = wf_dev_catalog.emit_dev_catalog(
            RUNTIME_ROOT / ".cdn/cn",
            RUNTIME_ROOT / "assets/asset-patch/active",
            catalog_dir,
            digest_mode="cache",
            allow_issues=True,
        )
        if manifest_path is None:
            raise MergeError("runtime dev catalog was not emitted")
        catalog = verify_runtime_catalog(catalog_dir, verification["archive_size"])
        runtime_manifest_readback, runtime_entry = load_manifest(RUNTIME_ROOT)
        if runtime_entry != source_entry:
            raise MergeError("runtime unified manifest entry differs from source")
        with zipfile.ZipFile(RUNTIME_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME) as archive:
            if len(archive.namelist()) != 133:
                raise MergeError("runtime unified archive is not the 133-member build")
        for relative, expected in targets.items():
            if (RUNTIME_ROOT / relative).read_bytes() != expected:
                raise MergeError(f"runtime readback drifted: {relative}")
        if runtime_manifest_readback.get("cdn_version") != PATCH_VERSION:
            raise MergeError("runtime CDN version drifted")
    except Exception:
        existence = json.loads(
            (backup / "files/existence.json").read_text(encoding="utf-8")
        )
        for relative in reversed(list(targets)):
            target = RUNTIME_ROOT / relative
            if existence[relative]:
                atomic_write(target, (backup / "files" / relative).read_bytes())
            elif target.is_file():
                target.unlink()
        restore_tree_files(catalog_dir, catalog_backup, catalog_existing)
        if cache_existed:
            atomic_write(cache_path, (backup / "dev-catalog-digest-cache.json").read_bytes())
        elif cache_path.is_file():
            cache_path.unlink()
        raise
    report = {
        "runtime_root": str(RUNTIME_ROOT),
        "backup": str(backup),
        "paths": len(targets),
        "catalog": catalog,
        "catalog_issues": len(issues),
        "catalog_summary": summary,
        "verification": verification,
    }
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--audit", action="store_true", help="audit inputs and build in memory")
    modes.add_argument("--apply", action="store_true", help="merge into the Git source workspace")
    modes.add_argument("--verify-existing", action="store_true", help="verify the merged source release")
    modes.add_argument("--sync-runtime", action="store_true", help="sync the verified release to runtime")
    args = parser.parse_args()
    if args.audit:
        targets, _old, report = build_source_candidate()
        result = {**report, "target_paths": len(targets), "mode": "audit"}
    elif args.apply:
        result = apply_source()
    elif args.verify_existing:
        result = verify_release()
    else:
        result = sync_runtime()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
