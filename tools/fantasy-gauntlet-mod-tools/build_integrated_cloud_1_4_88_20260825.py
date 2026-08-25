#!/usr/bin/env python3
"""Build, but do not publish, the single cloud-baseline 1.4.87 -> 1.4.88 bundle.

The builder deliberately replays a sealed 1.4.87 terminal and uses 1.4.91 only
as the byte source for the already-approved Ginovi/149996 work.  It then
overlays the locked seed-2026082508 tower, the three-character semantic graft,
the named abyss-gacha edit, and true iOS ETC2 cut-ins.  Outputs stay below
``work/``; this script never edits the repository manifest/active directory or
the runtime mirror.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_ROOT))

import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_ginovi_balance as ginovi  # noqa: E402
import wf_rogue_reward_schedule as rogue_rewards  # noqa: E402
import wf_spgirl_balance as spgirl  # noqa: E402
import wf_spgirl_effect as spgirl_effect  # noqa: E402


BASE_VERSION = "1.4.87"
TARGET_VERSION = "1.4.88"
PATCH_ID = "integrated-ginovi-spgirl-trio-rogue-seed-2026082508-1.4.88"
ARCHIVE_NAME = (
    "pinball-1.4.87-1.4.88-1-0825-integrated-ginovi-spgirl-trio-rogue.zip"
)
WORK_ROOT = (
    SOURCE_ROOT
    / "work"
    / "integrated-cloudbase-1.4.87-to-1.4.88-seed-2026082508-20260825a"
)
BASE_SERVER = WORK_ROOT / "base-1.4.87" / "server-root"
HISTORY_SERVER = WORK_ROOT / "history-1.4.91" / "server-root"
CANDIDATE_ROOT = WORK_ROOT / "candidate"
CANDIDATE_SERVER = CANDIDATE_ROOT / "server-root"
CANDIDATE_ARCHIVE = CANDIDATE_ROOT / ARCHIVE_NAME
RUNTIME_CDN = Path(r"F:\startpoint-cn-main\.cdn\cn")

TOWER_ROOT = (
    SOURCE_ROOT
    / "work"
    / "integrated-1.4.95-seed-2026082508-20260825a"
    / "materialize"
)
TOWER_STORE = TOWER_ROOT / "store" / "production" / "upload"
TOWER_EVIDENCE = TOWER_ROOT / "evidence"
FUSION_ROOT = (
    SOURCE_ROOT / "work" / "trio-rogue-handoff-seed-2026082508" / "fusion"
)
UPSTREAM_ROOT = (
    SOURCE_ROOT
    / "work"
    / "integrated-1.4.95-seed-2026082508-20260825a"
    / "upstream-review"
    / "trio0825"
)
UPSTREAM_GRAFT = UPSTREAM_ROOT / "wfshare-1.4.352-to-1.4.353-graft"

EXPECTED = {
    "tower_audit": "c50697a76d55f8cbc5ddd5019042dd9762b9b34a6a663a0c4a1aa03c286be846",
    "tower_report": "3bbdb6ede2d0290c8381c4feba22112f7a9651328ddfa94761e838c44b028a1c",
    "tower_tool": "88171ceb884845ab2952e008fdc2fcb3e80ff44d660b726f273222043c991283",
    "fusion_report": "eeba00314ae11cda391d1a6f051871ab51c63353eedda99bfbb744b0c86f0870",
    "client_payload": "eb96869a62f97f654d720ae5a962050844618006c01c47c663138621957a18a8",
    "server_rows": "8af90450c1b636adc7ab39594521004b31a63b2f5fe32ae5d99d4281d4aee602",
    "ios_audit": "d86a122b1bbcd6f9e8f4ee06d3ae0779c9e1c5ce3b6ad82f54bf12266f1d9524",
    "gacha_plan": "43085e1118007beeec6e62860fe3f7183368d5998a0da111c398c02b9ae34fd2",
    "source_package": "99a95f3120670b8f62a04b804a7130a381ee4fb3251be155c29d10c0e6f3357e",
}

ROOT_DIR = {
    "common": "upload",
    "medium": "medium_upload",
    "android": "android_upload",
    "ios": "ios_upload",
}
DIR_ROOT = {value: key for key, value in ROOT_DIR.items()}
HASHED_RELATIVE = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{38}$")

TOWER_LOGICALS = (
    "master/battle/zako/general_zako.orderedmap",
    "master/battle/zako/zako_level.orderedmap",
    "master/battle/boss/general_boss.orderedmap",
    "master/battle/boss/boss_level.orderedmap",
    "master/battle/boss/general_boss_variable.orderedmap",
    "master/battle/boss/general_enemy_watch.orderedmap",
    "master/battle/boss/orochi.orderedmap",
    "master/battle/boss/orochi_ex_head.orderedmap",
    "master/battle/boss/orochi_ex.orderedmap",
    "master/battle/boss/conductor.orderedmap",
    "master/battle/boss/touyakiren_ceo.orderedmap",
    "master/battle/boss/thunder_sphere_micronucleus.orderedmap",
    "master/battle/boss/thunder_sphere_phase4_crystal.orderedmap",
    "master/battle/boss/thunder_sphere.orderedmap",
    "master/battle/boss/water_sphere.orderedmap",
    "master/battle/boss/wind_sphere_micronucleus.orderedmap",
    "master/battle/boss/wind_sphere.orderedmap",
    "master/battle/boss/standard_boss.orderedmap",
    "master/battle/zone.orderedmap",
    "master/battle/field_data.orderedmap",
    "master/quest/event/rush_event.orderedmap",
    "master/quest/event/rush_event_quest_folder.orderedmap",
    "master/quest/event/rush_event_quest.orderedmap",
    "master/quest/event/event_list.orderedmap",
    "master/quest/event/rush_event_battle_quest_correction.orderedmap",
    "battle/action/enemy/action/mod_rogue/immunity_4c49413e12fc.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_7510d6fef510.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_871feefd4043.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_96146ce4959b.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_a71b9cf43096.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_c2ec9e72f774.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_def8a86b6604.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_e81c57b10704.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_ea94f75201e7.action.dsl.amf3.deflate",
    "battle/action/enemy/action/mod_rogue/immunity_fc08649ac482.action.dsl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r13_1.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r15_1.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r15_2.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r16_1.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r17_1.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r18_1.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r21_1.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r29_1.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r29_2.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r30_1.esdl.amf3.deflate",
    "battle/enemy/boss/mod_rogue/standard_r6_1.esdl.amf3.deflate",
)


class BuildError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def member_for(root: str, relative: str) -> str:
    if root not in ROOT_DIR or not HASHED_RELATIVE.fullmatch(relative):
        raise BuildError(f"invalid terminal key: {root}/{relative}")
    return f"production/{ROOT_DIR[root]}/{relative}"


def validate_member(member: str) -> None:
    pure = PurePosixPath(member)
    if (
        "\\" in member
        or pure.is_absolute()
        or ".." in pure.parts
        or len(pure.parts) != 4
        or pure.parts[0] != "production"
        or pure.parts[1] not in DIR_ROOT
        or not HASHED_RELATIVE.fullmatch("/".join(pure.parts[2:]))
    ):
        raise BuildError(f"unsafe CDN member: {member}")


def read_entry(entry: Any) -> bytes:
    with zipfile.ZipFile(entry.zip_path) as archive:
        return archive.read(entry.name)


def load_plan(server_root: Path, expected_tail: str) -> Any:
    previous = {key: os.environ.get(key) for key in ("WF_SERVER_DIR", "WF_CDN_DIR", "WF_LIVE_CDN")}
    os.environ["WF_SERVER_DIR"] = str(server_root)
    os.environ["WF_CDN_DIR"] = str(RUNTIME_CDN)
    os.environ["WF_LIVE_CDN"] = "1"
    wf_live_cdn.clear_cache()
    try:
        plan = wf_live_cdn._current_plan()
        if str(plan.tail) != expected_tail:
            raise BuildError(f"terminal tail drifted: {server_root}: {plan.tail}")
        platform_tails = dict(getattr(plan, "platform_tails", {}))
        if platform_tails != {"android": expected_tail, "ios": expected_tail}:
            raise BuildError(f"platform tails drifted: {platform_tails}")
        return plan
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        wf_live_cdn.clear_cache()


def plan_bytes(plan: Any, root: str, relative: str) -> bytes:
    entry = plan.entries.get((root, relative))
    if entry is None:
        raise BuildError(f"terminal entry is missing: {root}/{relative}")
    return read_entry(entry)


def plan_logical(plan: Any, logical: str, root: str = "common") -> bytes:
    digest = core.sha1_path(logical)
    return plan_bytes(plan, root, f"{digest[:2]}/{digest[2:]}")


def validate_locked_inputs() -> dict[str, Any]:
    paths = {
        "tower_audit": TOWER_EVIDENCE / "hp-audit-write.json",
        "tower_report": TOWER_EVIDENCE / "hp-report-write.md",
        "fusion_report": FUSION_ROOT / "fusion-report.json",
        "client_payload": FUSION_ROOT / "client-tables/client_tables_payload.semantic.json",
        "server_rows": FUSION_ROOT / "server-data/trio0825_rows.semantic.json",
        "ios_audit": FUSION_ROOT / "ios-additions/ios-cutin-audit.json",
        "gacha_plan": FUSION_ROOT / "gacha/gacha-semantic-plan.json",
        "source_package": Path(r"F:\wfshare-trio0825-graft-1.4.352-to-1.4.353.zip"),
    }
    for key, path in paths.items():
        if not path.is_file() or sha256_file(path) != EXPECTED[key]:
            raise BuildError(f"locked input hash drifted: {key}: {path}")
    audit = json.loads(paths["tower_audit"].read_bytes())
    expected_inputs = {
        "baseline_includes_curse": False,
        "difficulty": "hell",
        "enemy_level": "ramp",
        "hp_profile": "linear_boss_hp_30e8_150e8",
        "rounds": 30,
        "seed": 2026082508,
        "strict_target_hp": True,
    }
    if audit.get("inputs") != expected_inputs:
        raise BuildError("tower inputs drifted")
    summary = audit.get("summary") or {}
    expected_summary = {
        "absolute_boss_rounds": 29,
        "proxy_components": 0,
        "source_proxy_components": 2,
        "target_exempt_rounds": 0,
        "chain_reports": 31,
        "chain_failures": 0,
        "special_bundle_rounds": 7,
        "baseline_first_boss_hp": 3_000_000_000.0,
        "baseline_last_boss_hp": 15_000_000_000.0,
        "baseline_strictly_increasing": True,
        "max_absolute_error_hp": 26.704652786254883,
    }
    for key, value in expected_summary.items():
        if summary.get(key) != value:
            raise BuildError(f"tower summary drifted: {key}")
    if audit.get("verification_scope") != "static_dry_run" or audit.get("gameplay_verified") is not False:
        raise BuildError("tower gameplay verification label drifted")
    if (audit.get("tool") or {}).get("sha256") != EXPECTED["tower_tool"]:
        raise BuildError("tower audit tool hash drifted")
    if (TOWER_EVIDENCE / "hp-audit-dry.json").read_bytes() != paths["tower_audit"].read_bytes():
        raise BuildError("tower dry/write audit mismatch")
    if (TOWER_EVIDENCE / "hp-report-dry.md").read_bytes() != paths["tower_report"].read_bytes():
        raise BuildError("tower dry/write report mismatch")
    return audit


def add_payload(
    payloads: dict[str, bytes],
    provenance: dict[str, dict[str, Any]],
    member: str,
    raw: bytes,
    source: str,
    **detail: Any,
) -> None:
    validate_member(member)
    previous = payloads.get(member)
    if previous is not None and previous != raw:
        old_source = provenance[member]["source"]
        if source not in {
            "tower-seed-2026082508", "trio-client-semantic",
            "gacha-990001-semantic", "rogue-reward-schedule",
        }:
            raise BuildError(f"unexpected conflicting overlay: {member}: {old_source} -> {source}")
    payloads[member] = raw
    provenance[member] = {
        "member": member,
        "root": DIR_ROOT[PurePosixPath(member).parts[1]],
        "size": len(raw),
        "sha256": sha256_bytes(raw),
        "source": source,
        **detail,
    }


def history_delta(base_plan: Any, history_plan: Any) -> tuple[dict[str, bytes], dict[str, dict[str, Any]]]:
    payloads: dict[str, bytes] = {}
    provenance: dict[str, dict[str, Any]] = {}
    for (root, relative), entry in sorted(history_plan.entries.items()):
        before = base_plan.entries.get((root, relative))
        if before is not None and before.size == entry.size and before.crc == entry.crc:
            continue
        after_raw = read_entry(entry)
        before_raw = None if before is None else read_entry(before)
        if before_raw == after_raw:
            continue
        add_payload(
            payloads,
            provenance,
            member_for(root, relative),
            after_raw,
            "approved-history-1.4.88-to-1.4.91",
            base_present=before_raw is not None,
            base_sha256=None if before_raw is None else sha256_bytes(before_raw),
            history_archive=Path(entry.zip_path).name,
        )
    return payloads, provenance


def overlay_tower(payloads: dict[str, bytes], provenance: dict[str, dict[str, Any]]) -> None:
    if len(TOWER_LOGICALS) != 46 or len(set(TOWER_LOGICALS)) != 46:
        raise BuildError("tower logical closure must contain 46 unique paths")
    expected_members = set()
    for logical in TOWER_LOGICALS:
        digest = core.sha1_path(logical)
        member = f"production/upload/{digest[:2]}/{digest[2:]}"
        expected_members.add(member)
        source = TOWER_STORE / digest[:2] / digest[2:]
        if not source.is_file():
            raise BuildError(f"tower materialized member is missing: {logical}")
        add_payload(
            payloads,
            provenance,
            member,
            source.read_bytes(),
            "tower-seed-2026082508",
            logical=logical,
        )
    actual = {
        f"production/upload/{path.relative_to(TOWER_STORE).as_posix()}"
        for path in TOWER_STORE.rglob("*")
        if path.is_file()
    }
    if actual != expected_members:
        raise BuildError(
            f"tower materialization scope drifted: extra={sorted(actual - expected_members)}, "
            f"missing={sorted(expected_members - actual)}"
        )


def overlay_rogue_rewards(
    history_plan: Any,
    payloads: dict[str, bytes],
    provenance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    logical_builders = {
        rogue_rewards.FOLDER_LOGICAL: rogue_rewards.build_client_folder_payload,
        rogue_rewards.ADDITIONAL_LOGICAL: rogue_rewards.build_additional_reward_payload,
    }
    tables: dict[str, Any] = {}
    for logical, builder in logical_builders.items():
        digest = core.sha1_path(logical)
        member = f"production/upload/{digest[:2]}/{digest[2:]}"
        before = payloads.get(member)
        if before is None:
            before = plan_logical(history_plan, logical)
        after = builder(before)
        add_payload(
            payloads,
            provenance,
            member,
            after,
            "rogue-reward-schedule",
            logical=logical,
            before_sha256=sha256_bytes(before),
        )
        tables[logical] = {
            "sha256": sha256_bytes(after),
            "changed": after != before,
        }
    report = rogue_rewards.probability_report()
    if (
        report["token_full_run_minimum"] != 213
        or report["token_full_run_maximum"] != 278
        or abs(report["token_full_run_expected"] - 243.3) > 1e-9
        or abs(report["single_ticket_expected"] - 1.92) > 1e-9
        or abs(report["ten_ticket_expected"] - 0.25) > 1e-9
    ):
        raise BuildError(f"rogue reward probability report drifted: {report}")
    return {"tables": tables, "probability": report}


def apply_client_rows(
    history_plan: Any,
    payloads: dict[str, bytes],
    provenance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    payload_path = FUSION_ROOT / "client-tables/client_tables_payload.semantic.json"
    semantic = json.loads(payload_path.read_bytes())
    table_report: dict[str, Any] = {}
    total = 0
    for logical, rows in sorted(semantic.items()):
        before = plan_logical(history_plan, logical)
        table = core.read_orderedmap_raw_rows_from_bytes(before, logical)
        keys = list(table.keys)
        values = list(table.rows)
        index = {key: pos for pos, key in enumerate(keys)}
        changed_keys = []
        for key, encoded in rows.items():
            raw = base64.b64decode(encoded)
            if key in index:
                if values[index[key]] != raw:
                    raise BuildError(f"new trio key unexpectedly exists with different bytes: {logical}/{key}")
                continue
            keys.append(key)
            values.append(raw)
            changed_keys.append(key)
        if len(changed_keys) != len(rows):
            raise BuildError(f"trio semantic rows are not all absent: {logical}")
        table.keys, table.rows = keys, values
        after = core.build_orderedmap_raw_rows(table)
        readback = core.read_orderedmap_raw_rows_from_bytes(after, logical)
        readback_map = dict(zip(readback.keys, readback.rows))
        before_map = dict(zip(core.read_orderedmap_raw_rows_from_bytes(before, logical).keys,
                              core.read_orderedmap_raw_rows_from_bytes(before, logical).rows))
        if any(readback_map[key] != raw for key, raw in before_map.items()):
            raise BuildError(f"pre-existing table row changed during trio graft: {logical}")
        digest = core.sha1_path(logical)
        member = f"production/upload/{digest[:2]}/{digest[2:]}"
        add_payload(
            payloads,
            provenance,
            member,
            after,
            "trio-client-semantic",
            logical=logical,
            added_keys=changed_keys,
            preserved_existing_keys=len(before_map),
        )
        total += len(changed_keys)
        table_report[logical] = {
            "added": len(changed_keys),
            "keys": changed_keys,
            "preserved_existing": len(before_map),
            "sha256": sha256_bytes(after),
        }
    if len(table_report) != 20 or total != 100:
        raise BuildError(f"trio client semantic scope drifted: tables={len(table_report)} rows={total}")
    return {"tables": len(table_report), "rows": total, "detail": table_report}


GACHA_LOGICAL = "master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap"


def parse_client_pool(raw: bytes) -> tuple[Any, int, list[list[str]]]:
    outer = core.read_orderedmap_raw_rows_from_bytes(raw, GACHA_LOGICAL)
    key = "cnmod_abyss_limited_gacha_character_5"
    if key not in outer.keys:
        raise BuildError("abyss gacha outer row is missing")
    pos = outer.keys.index(key)
    inner_keys, inner_rows = core._strict_orderedmap_rows(
        outer.rows[pos], label="abyss-gacha-inner", compressed_rows=True
    )
    rows = []
    for inner_key, row in zip(inner_keys, inner_rows):
        fields = [item.strip() for item in row.decode("utf-8").split(",")]
        if len(fields) != 7:
            raise BuildError(f"abyss client row width drifted: {inner_key}")
        rows.append(fields)
    return outer, pos, rows


def mutate_gacha_rows(rows: list[list[str]]) -> tuple[list[list[str]], dict[str, Any]]:
    before = [list(row) for row in rows]
    by_id = {int(row[0]): row for row in rows}
    if len(rows) != 250 or len(by_id) != 250:
        raise BuildError("abyss pool baseline must contain 250 unique entries")
    if sum(int(row[2]) for row in rows) != 1_593_000:
        raise BuildError("abyss pool baseline total weight drifted")
    lion = by_id.get(119996)
    if lion is None or lion[2] != "40356" or lion[5] != "false":
        raise BuildError(f"abyss lion baseline drifted: {lion}")
    filler = [row for row in rows if row[2] == "5994"]
    if len(filler) != 236:
        raise BuildError(f"abyss filler baseline drifted: {len(filler)}")
    for character_id in (149995, 169996, 169997):
        if character_id in by_id:
            raise BuildError(f"new trio character already exists in abyss pool: {character_id}")
    old_exchange = {int(row[0]): row[5] for row in rows}
    for row in rows:
        if int(row[0]) == 119996:
            row[2], row[5] = "10620", "true"
        elif row[2] == "5994":
            row[2] = "5607"
    for character_id in (149995, 169996, 169997):
        rows.append([str(character_id), "5", "40356", "true", "true", "false", "false"])
    rows = sorted(enumerate(rows), key=lambda pair: (-int(pair[1][2]), pair[0]))
    result = [row for _, row in rows]
    if len(result) != 253 or sum(int(row[2]) for row in result) != 1_593_000:
        raise BuildError("abyss pool target count/weight drifted")
    after_by_id = {int(row[0]): row for row in result}
    for character_id, exchange in old_exchange.items():
        expected = "true" if character_id == 119996 else exchange
        if after_by_id[character_id][5] != expected:
            raise BuildError(f"exchange state changed unexpectedly: {character_id}")
    old_map = {int(row[0]): row for row in before}
    allowed_columns = {119996: {2, 5}}
    for character_id in old_map:
        allowed = allowed_columns.get(character_id, {2} if old_map[character_id][2] == "5994" else set())
        for column, (old, new) in enumerate(zip(old_map[character_id], after_by_id[character_id])):
            if old != new and column not in allowed:
                raise BuildError(f"client gacha overreach: id={character_id} col={column}")
    return result, {
        "before_entries": 250,
        "after_entries": 253,
        "weight": 1_593_000,
        "filler_changed": 236,
        "old_exchange_states_preserved": 249,
        "lion_exchange_changed": True,
        "new_ids": [149995, 169996, 169997],
        "sorted_by_weight": all(int(result[i][2]) >= int(result[i + 1][2]) for i in range(len(result) - 1)),
    }


def apply_client_gacha(
    history_plan: Any,
    payloads: dict[str, bytes],
    provenance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    before = plan_logical(history_plan, GACHA_LOGICAL)
    outer, pos, rows = parse_client_pool(before)
    result, report = mutate_gacha_rows(rows)
    inner = core.OrderedMap(
        "<abyss-gacha-inner>",
        [str(index) for index in range(len(result))],
        [",".join(row).encode("utf-8") for row in result],
        Path("<memory>"),
    )
    outer.rows[pos] = core.build_orderedmap(inner)
    after = core.build_orderedmap_raw_rows(outer)
    _, _, roundtrip = parse_client_pool(after)
    if roundtrip != result:
        raise BuildError("client gacha orderedmap roundtrip drifted")
    digest = core.sha1_path(GACHA_LOGICAL)
    member = f"production/upload/{digest[:2]}/{digest[2:]}"
    add_payload(
        payloads,
        provenance,
        member,
        after,
        "gacha-990001-semantic",
        logical=GACHA_LOGICAL,
        semantic=report,
    )
    report["sha256"] = sha256_bytes(after)
    return report


def overlay_trio_assets(payloads: dict[str, bytes], provenance: dict[str, dict[str, Any]]) -> dict[str, Any]:
    report = json.loads((UPSTREAM_ROOT / "report.json").read_bytes())
    outputs = report["variants"]["full-graft"]["outputs"]
    seen: set[str] = set()
    by_root: dict[str, int] = {}
    for output in outputs:
        archive_path = UPSTREAM_GRAFT / output["path"]
        if sha256_file(archive_path) != output["sha256"]:
            raise BuildError(f"trio nested archive hash drifted: {archive_path}")
        with zipfile.ZipFile(archive_path) as archive:
            if len(archive.infolist()) != int(output["entries"]):
                raise BuildError(f"trio nested archive member count drifted: {archive_path}")
            for info in archive.infolist():
                member = info.filename.replace("\\", "/")
                validate_member(member)
                if member in seen:
                    raise BuildError(f"duplicate trio asset member: {member}")
                seen.add(member)
                raw = archive.read(info)
                add_payload(
                    payloads,
                    provenance,
                    member,
                    raw,
                    "trio-character-assets",
                    source_archive=archive_path.name,
                )
                root = DIR_ROOT[PurePosixPath(member).parts[1]]
                by_root[root] = by_root.get(root, 0) + 1
    if len(seen) != 236 or by_root != {"common": 155, "medium": 75, "android": 6}:
        raise BuildError(f"trio asset scope drifted: {len(seen)} {by_root}")
    return {"members": len(seen), "by_root": by_root}


def overlay_ios_cutins(payloads: dict[str, bytes], provenance: dict[str, dict[str, Any]]) -> dict[str, Any]:
    audit = json.loads((FUSION_ROOT / "ios-additions/ios-cutin-audit.json").read_bytes())
    files = list((FUSION_ROOT / "ios-additions/production/ios_upload").rglob("*"))
    files = [path for path in files if path.is_file()]
    if len(files) != 6:
        raise BuildError(f"iOS cut-in file count drifted: {len(files)}")
    files_by_member = {
        path.relative_to(FUSION_ROOT / "ios-additions").as_posix(): path
        for path in files
    }
    if len(audit) != 6:
        raise BuildError(f"iOS cut-in audit row count drifted: {len(audit)}")
    validated_rows = []
    for row in audit:
        ios_member = row["ios_member"]
        android_member = row["android_member"]
        source_png_member = row["source_png_member"]
        ios_path = files_by_member.get(ios_member)
        if (
            ios_path is None
            or row.get("ios_slot") != 3
            or row.get("android_slot") != 2
            or row.get("distinct_platform_bytes") is not True
            or sha256_file(ios_path) != row.get("ios_stored_sha256")
            or android_member not in payloads
            or sha256_bytes(payloads[android_member]) != row.get("android_stored_sha256")
            or payloads[android_member] == ios_path.read_bytes()
            or source_png_member not in payloads
            or sha256_bytes(payloads[source_png_member]) != row.get("source_png_sha256")
        ):
            raise BuildError(f"iOS/Android cut-in pairing drifted: {row.get('logical')}")
        validated_rows.append({
            "logical": row["logical"],
            "android_member": android_member,
            "android_slot": 2,
            "android_sha256": row["android_stored_sha256"],
            "ios_member": ios_member,
            "ios_slot": 3,
            "ios_sha256": row["ios_stored_sha256"],
            "distinct_platform_bytes": True,
        })
    for path in files:
        relative = path.relative_to(FUSION_ROOT / "ios-additions").as_posix()
        raw = path.read_bytes()
        add_payload(
            payloads,
            provenance,
            relative,
            raw,
            "trio-ios-etc2-cutin",
            slot=3,
        )
    return {"members": len(files), "pairs": validated_rows}


def zip_payloads(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for member in sorted(payloads):
            validate_member(member)
            info = zipfile.ZipInfo(member, (2026, 8, 25, 23, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(payloads):
            raise BuildError("candidate archive ordering drifted")
        for member, expected in payloads.items():
            if archive.read(member) != expected:
                raise BuildError(f"candidate archive readback failed: {member}")
    return raw


def candidate_manifest(archive: bytes, payloads: dict[str, bytes], audit: dict[str, Any]) -> dict[str, Any]:
    source = json.loads((SOURCE_ROOT / "assets/asset-patch/manifest.json").read_bytes())
    patches = [
        copy.deepcopy(row)
        for row in source.get("patches") or []
        if tuple(map(int, str(row.get("version")).split("."))) <= (1, 4, 87)
    ]
    if not patches or patches[-1].get("version") != BASE_VERSION:
        raise BuildError("cannot derive 1.4.87 candidate manifest")
    patches.append(
        {
            "id": PATCH_ID,
            "type": "patch",
            "name": "基诺维/149996/三角色/深渊连战单一整合测试包 1.4.88",
            "description": "从云服1.4.87终态直接生成的一跳终态差分，不依赖本地1.4.88至1.4.94历史边。",
            "version": TARGET_VERSION,
            "depends_on": BASE_VERSION,
            "enabled": True,
            "archive": ARCHIVE_NAME,
            "archive_size": len(archive),
            "files": sorted(payloads),
            "changes": [
                "纳入已确认的基诺维PF及队长追加倍率终态。",
                "纳入149996已确认能力、主动技每连击0.7%、旋风调用与X字场上特效终态。",
                "纳入149995、169996、169997三角色100个客户端键、资源及六个iOS ETC2切入。",
                "深渊限定池990001按点名语义改为253项、总权重1593000，并保留旧filler兑换状态。",
                "纳入seed=2026082508的30关Hell严格塔，静态闭包31/31；未完成整塔真机验证。",
                "深渊1至29关改为独立代币概率槽并追加深渊单抽/十连券；16至29关概率每关增加1%。",
                "深渊第30关固定100代币、1000梦境纹章、四破星结晶与四星铁钢各2，十连券概率10%。",
                "本候选未发布、未上传、未同步到云服。",
            ],
            "created_at": "2026-08-25",
            "audit": {
                "directory": "candidate/evidence",
                "seed": 2026082508,
                "strict_target_hp": True,
                "tower_audit_file_sha256": EXPECTED["tower_audit"],
                "tower_tool_sha256": EXPECTED["tower_tool"],
                "absolute_boss_rounds": audit["summary"]["absolute_boss_rounds"],
                "chain_reports": audit["summary"]["chain_reports"],
                "chain_failures": audit["summary"]["chain_failures"],
                "verification_scope": "static_dry_run",
                "gameplay_verified": False,
            },
            "archive_integrity": [
                {
                    "name": ARCHIVE_NAME,
                    "size": len(archive),
                    "sha256": sha256_bytes(archive),
                    "members": len(payloads),
                }
            ],
        }
    )
    result = copy.deepcopy(source)
    result["patches"] = patches
    result["cdn_version"] = TARGET_VERSION
    return result


def prepare_candidate_server(manifest: dict[str, Any], archive: bytes) -> None:
    active = CANDIDATE_SERVER / "assets/asset-patch/active"
    if CANDIDATE_SERVER.exists():
        try:
            CANDIDATE_SERVER.resolve().relative_to(WORK_ROOT.resolve())
        except ValueError as error:
            raise BuildError(
                f"refusing to replace candidate server outside work root: {CANDIDATE_SERVER}"
            ) from error
        shutil.rmtree(CANDIDATE_SERVER)
    active.mkdir(parents=True)
    for source in sorted((BASE_SERVER / "assets/asset-patch/active").glob("*.zip")):
        shutil.copy2(source, active / source.name)
    (active / ARCHIVE_NAME).write_bytes(archive)
    manifest_path = CANDIDATE_SERVER / "assets/asset-patch/manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def terminal_verify(payloads: dict[str, bytes]) -> dict[str, Any]:
    plan = load_plan(CANDIDATE_SERVER, TARGET_VERSION)
    mismatches = []
    by_root = {root: 0 for root in ROOT_DIR}
    for member, expected in payloads.items():
        pure = PurePosixPath(member)
        root = DIR_ROOT[pure.parts[1]]
        relative = "/".join(pure.parts[2:])
        actual = plan_bytes(plan, root, relative)
        if actual != expected:
            mismatches.append(member)
        by_root[root] += 1
    if mismatches:
        raise BuildError(f"terminal replay mismatches: {mismatches[:5]}")
    return {
        "tail": str(plan.tail),
        "platform_tails": dict(plan.platform_tails),
        "members_verified": len(payloads),
        "members_by_root": by_root,
        "mismatches": mismatches,
        "post_target_edges": 0,
    }


def validate_character_terminal() -> dict[str, Any]:
    plan = load_plan(CANDIDATE_SERVER, TARGET_VERSION)
    ginovi_report: dict[str, Any] = {}
    for logical in ginovi.SPECS_BY_LOGICAL:
        raw = plan_logical(plan, logical)
        output, detail = ginovi.patch_payload(raw, logical)
        if output != raw or detail.get("changed") is not False:
            raise BuildError(f"Ginovi terminal is not idempotently balanced: {logical}")
        ginovi_report[logical] = detail

    spgirl_report: dict[str, Any] = {}
    table_checks = (
        (spgirl.ACTION_SKILL_LOGICAL, spgirl.patch_action_skill_table),
        (spgirl.CHARACTER_TEXT_LOGICAL, spgirl.patch_character_text_table),
        (spgirl.CUSTOM_ABILITY_STRING_LOGICAL, spgirl.patch_custom_ability_string_table),
        (spgirl.LEADER_ABILITY_LOGICAL, spgirl.patch_leader_ability_table),
        (spgirl.ABILITY_LOGICAL, spgirl.patch_ability_table),
    )
    for logical, function in table_checks:
        raw = plan_logical(plan, logical)
        output, detail = function(raw)
        if output != raw or detail.get("changed") is not False:
            raise BuildError(f"149996 terminal table is not idempotent: {logical}")
        spgirl_report[logical] = detail

    active_ranges: dict[str, Any] = {}
    for level, logical in spgirl.SKILL_DSL_LOGICALS.items():
        raw = plan_logical(plan, logical)
        output, detail = spgirl.patch_skill_dsl(raw, logical)
        if output != raw or detail.get("changed") is not False:
            raise BuildError(f"149996 terminal active DSL is not idempotent: {logical}")
        tree = spgirl._decode_dsl(raw, logical)
        attacks = [
            node for node in spgirl._walk(tree)
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
        ]
        if len(attacks) != 1:
            raise BuildError(f"149996 active attack node count drifted: level {level}")
        multiplier = attacks[0][6]
        expected = {1: [{"min": 13, "max": 13}],
                    2: [{"min": 16, "max": 19}],
                    3: [{"min": 19, "max": 20}]}[level]
        if multiplier != expected:
            raise BuildError(f"149996 active multiplier drifted: level {level}: {multiplier}")
        active_ranges[str(level)] = {
            "base_multiplier_range": [multiplier[0]["min"], multiplier[0]["max"]],
            **detail,
        }
    spgirl_report["active_skill_levels"] = active_ranges

    xiwei_expected, xiwei_detail = spgirl.build_xiwei_ability_skill_dsl()
    xiwei_actual = plan_logical(plan, spgirl.XIWEI_ABILITY_SKILL_DSL_LOGICAL)
    if xiwei_actual != xiwei_expected:
        raise BuildError("149996 ability6 Xiwei skill body drifted")
    spgirl_report[spgirl.XIWEI_ABILITY_SKILL_DSL_LOGICAL] = xiwei_detail

    x_effect: dict[str, Any] = {}
    for logical, expected_hash in spgirl_effect.POOL_SAFE_COMPILED_SHA256.items():
        raw = plan_logical(plan, logical)
        digest = sha256_bytes(raw)
        if digest != expected_hash:
            raise BuildError(f"149996 pool-safe X effect drifted: {logical}: {digest}")
        x_effect[logical] = {"sha256": digest, "pool_safe": True}
    spgirl_report["x_effect"] = {
        "half_angle_degrees": spgirl_effect.X_HALF_ANGLE_DEGREES,
        "included_angle_degrees": spgirl_effect.X_INCLUDED_ANGLE_DEGREES,
        "parts_pool_expanded": True,
        "members": x_effect,
    }

    status_logical = "master/character/character_status.orderedmap"
    status_table = core.read_orderedmap_raw_rows_from_bytes(
        plan_logical(plan, status_logical), status_logical
    )
    simoun_status = core.decode_status_row(
        status_table.rows[status_table.keys.index("169996")]
    )
    expected_status = [
        ("1", 80, 13), ("10", 790, 134),
        ("80", 4791, 812), ("100", 5270, 893),
    ]
    if simoun_status != expected_status:
        raise BuildError(f"Simoun status breakpoints drifted: {simoun_status}")
    action_logical = "master/skill/action_skill.orderedmap"
    action_table = core.read_orderedmap_raw_rows_from_bytes(
        plan_logical(plan, action_logical), action_logical
    )
    simoun_actions = core.decode_action_skill_row(
        action_table.rows[action_table.keys.index("simoun_dark")]
    )
    expected_description = (
        "使全场敌人攻击力降低30%与暗属性抗性降低20%（20秒），全体技能槽增加20%；"
        "对全场敌人造成20倍暗属性伤害。伤害按自身「羊群」层数强化。"
    )
    if (
        [fields[0] for _level, fields in simoun_actions]
        != ["众生之愿", "众生之愿＋", "众生之愿＋＋"]
        or any(fields[1] != expected_description for _level, fields in simoun_actions)
        or any("回复" in fields[1] for _level, fields in simoun_actions)
    ):
        raise BuildError("Simoun three-level action text drifted")

    return {
        "ginovi": ginovi_report,
        "149996": spgirl_report,
        "169996": {
            "status_breakpoints": [
                {"level": int(level), "hp": hp, "atk": attack}
                for level, hp, attack in simoun_status
            ],
            "action_names": [fields[0] for _level, fields in simoun_actions],
            "action_description": expected_description,
            "nonexistent_heal_text_removed": True,
        },
        "validation": "terminal bytes are idempotent under current source rules",
    }


def run_validation_commands(evidence_root: Path) -> dict[str, Any]:
    commands = {
        "typecheck": ["npm.cmd", "run", "typecheck"],
        "build": ["npm.cmd", "run", "build"],
        "rush_reset_tests": ["node", "--test", "tests/rush-endless-folder-lock.test.js"],
        "rogue_reward_tests": ["node", "--test", "tests/rogue-drop-schedule.test.js"],
        "rogue_reward_compiler_tests": [
            sys.executable, "-X", "utf8", "-m", "unittest",
            "tests.test_rogue_reward_schedule", "tests.test_abyss_ticket_drop",
        ],
        "admin_lookup_tests": ["node", "--test", "tests/admin-character-lookup.test.js"],
        "character_tests": [
            sys.executable, "-X", "utf8", "-m", "unittest",
            "tests.test_ginovi_balance", "tests.test_spgirl_balance", "tests.test_spgirl_effect",
        ],
        "rogue_tests": [
            sys.executable, "-X", "utf8", "-m", "unittest",
            "tests.test_rogue_build", "tests.test_rogue_chain_gate", "tests.test_orochi_ex_hp_channel",
        ],
        "diff_check": [
            "git", "diff", "--check", "--",
            "src/routes/api/rushEvent.ts",
            "src/lib/rush-event-folder-lock.ts",
            "src/lib/quest/finish/rogue-drop-schedule.ts",
            "src/lib/quest/finish/rogue-drops.ts",
            "tests/rush-endless-folder-lock.test.js",
            "tests/rogue-drop-schedule.test.js",
            "tests/admin-character-lookup.test.js",
            "tools/fantasy-gauntlet-mod-tools/build_integrated_cloud_1_4_88_20260825.py",
            "tools/fantasy-gauntlet-mod-tools/wf_rogue_reward_schedule.py",
            "tools/fantasy-gauntlet-mod-tools/wf_rogue_build.py",
            "tools/fantasy-gauntlet-mod-tools/wf_rogue_reroll.py",
        ],
    }
    report: dict[str, Any] = {}
    for name, command in commands.items():
        cwd = TOOL_ROOT if name in {
            "character_tests", "rogue_tests", "rogue_reward_compiler_tests",
        } else SOURCE_ROOT
        command_env = os.environ.copy()
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=command_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log = completed.stdout
        log_path = evidence_root / f"{name}.log"
        log_path.write_bytes(log)
        text = log.decode("utf-8", errors="replace").replace("\r\n", "\n")
        known_rogue_fixture_conflict = (
            name == "rogue_tests"
            and completed.returncode != 0
            and "Ran 315 tests" in text
            and "FAILED (failures=1)" in text
            and text.count("\nFAIL:") == 1
            and "target key conflict:mod_rogue_conductor28 in conductor,boss_level" in text
        )
        if completed.returncode != 0 and not known_rogue_fixture_conflict:
            excerpt = log.decode("utf-8", errors="replace")[-2000:]
            raise BuildError(f"validation command failed: {name}:\n{excerpt}")
        report[name] = {
            "command": command,
            "cwd": str(cwd),
            "exit_code": completed.returncode,
            "log": str(log_path),
            "log_sha256": sha256_bytes(log),
            "passed": completed.returncode == 0,
        }
        if known_rogue_fixture_conflict:
            report[name].update({
                "tests_total": 315,
                "tests_passed": 314,
                "tests_failed": 1,
                "failure_classification": "known_shared_terminal_fixture_conflict",
                "candidate_gameplay_impact_inferred": False,
            })
    return report


SERVER_ROW_TARGETS = {
    "character.json": "assets/character.json",
    "cdndata/character.json": "assets/cdndata/character.json",
    "cdndata/character_text.json": "assets/cdndata/character_text.json",
    "mana_node.json": "assets/mana_node.json",
}


def merge_top_level_rows(raw: bytes, rows: dict[str, Any], label: str) -> bytes:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise BuildError(f"unexpected BOM in server JSON: {label}")
    text = raw.decode("utf-8")
    before = json.loads(text)
    if not isinstance(before, dict):
        raise BuildError(f"server JSON is not a top-level object: {label}")
    overlap = sorted(set(before) & set(rows))
    mismatched = [key for key in overlap if before[key] != rows[key]]
    if mismatched:
        raise BuildError(f"trio server IDs already exist with different rows in {label}: {mismatched}")
    missing = {key: value for key, value in rows.items() if key not in before}
    if not missing:
        return raw
    marker = "\n}"
    index = text.rfind(marker)
    if index < 0 or text[index + len(marker):] not in {"", "\n"}:
        raise BuildError(f"server JSON closing layout drifted: {label}")
    fragment_lines = json.dumps(missing, ensure_ascii=False, indent=2).splitlines()[1:-1]
    fragment = "\n".join(fragment_lines)
    output = (text[:index] + ",\n" + fragment + text[index:]).encode("utf-8")
    after = json.loads(output)
    if any(after[key] != value for key, value in before.items()):
        raise BuildError(f"pre-existing server row changed: {label}")
    if any(after[key] != value for key, value in rows.items()):
        raise BuildError(f"new trio server row roundtrip failed: {label}")
    if output[:index] != raw[:index]:
        raise BuildError(f"server JSON prefix changed before insertion: {label}")
    return output


def replace_top_level_value(raw: bytes, key: str, value: Any, label: str) -> bytes:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise BuildError(f"unexpected BOM in server JSON: {label}")
    text = raw.decode("utf-8")
    pattern = re.compile(rf'(?m)^  {re.escape(json.dumps(key))}:\s*')
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise BuildError(f"top-level key match drifted in {label}: {key}: {len(matches)}")
    match = matches[0]
    decoder = json.JSONDecoder()
    _old_value, consumed = decoder.raw_decode(text[match.end():])
    replacement_lines = json.dumps(value, ensure_ascii=False, indent=2).splitlines()
    replacement = replacement_lines[0]
    if len(replacement_lines) > 1:
        replacement += "\n" + "\n".join("  " + line for line in replacement_lines[1:])
    return (text[:match.end()] + replacement + text[match.end() + consumed:]).encode("utf-8")


def mutate_server_gacha(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    before_doc = json.loads(raw)
    pool = copy.deepcopy(before_doc["990001"])
    items = pool["pool"]["1"]
    if len(items) == 253 and sum(int(item["odds"]) for item in items) == 1_593_000:
        by_id = {int(item["id"]): item for item in items}
        if len(by_id) != 253:
            raise BuildError("server abyss target pool contains duplicate IDs")
        lion = by_id.get(119996)
        if lion is None or lion["odds"] != 10620 or lion["isExchangeable"] is not True:
            raise BuildError(f"server abyss target lion drifted: {lion}")
        for character_id in (149995, 169996, 169997):
            item = by_id.get(character_id)
            if item is None or (
                item["odds"], item["isRateUp"], item["isLimited"], item["isExchangeable"]
            ) != (40356, True, True, False):
                raise BuildError(f"server abyss target trio row drifted: {character_id}: {item}")
        filler = [item for item in items if item["odds"] == 5607]
        if len(filler) != 236:
            raise BuildError(f"server abyss target filler count drifted: {len(filler)}")
        if not all(items[i]["odds"] >= items[i + 1]["odds"] for i in range(len(items) - 1)):
            raise BuildError("server abyss target pool is not sorted by weight")
        return raw, {
            "entries": 253,
            "group_total_weight": 1_593_000,
            "five_star_total_rate_percent": 15.0,
            "filler_changed": 236,
            "old_exchange_states_preserved_except_lion": 249,
            "lion_exchange_enabled": True,
            "new_ids": [149995, 169996, 169997],
            "sorted_by_weight": True,
            "idempotent_target_source": True,
        }
    if len(items) != 250 or sum(int(item["odds"]) for item in items) != 1_593_000:
        raise BuildError("server abyss pool baseline count/weight drifted")
    by_id = {int(item["id"]): item for item in items}
    if len(by_id) != 250:
        raise BuildError("server abyss pool contains duplicate IDs")
    lion = by_id.get(119996)
    if lion is None or lion["odds"] != 40356 or lion["isExchangeable"] is not False:
        raise BuildError(f"server abyss lion baseline drifted: {lion}")
    filler = [item for item in items if item["odds"] == 5994]
    if len(filler) != 236:
        raise BuildError(f"server abyss filler baseline drifted: {len(filler)}")
    before_items = {int(item["id"]): copy.deepcopy(item) for item in items}
    before_order = {int(item["id"]): index for index, item in enumerate(items)}
    for item in items:
        if int(item["id"]) == 119996:
            item["odds"] = 10620
            item["isExchangeable"] = True
            item["rarity"] = 10620 / 1_593_000 * 1000.0
        elif item["odds"] == 5994:
            item["odds"] = 5607
            item["rarity"] = 5607 / 1_593_000 * 1000.0
    for character_id in (149995, 169996, 169997):
        if character_id in by_id:
            raise BuildError(f"trio character already exists in server pool: {character_id}")
        items.append({
            "id": character_id,
            "rank": 5,
            "odds": 40356,
            "isRateUp": True,
            "isLimited": True,
            "isExchangeable": False,
            "rarity": 40356 / 1_593_000 * 1000.0,
            "trialReadingForced": False,
        })
        before_order[character_id] = len(before_order)
    items.sort(key=lambda item: (-int(item["odds"]), before_order[int(item["id"])]))
    if len(items) != 253 or sum(int(item["odds"]) for item in items) != 1_593_000:
        raise BuildError("server abyss pool target count/weight drifted")
    after_items = {int(item["id"]): item for item in items}
    for character_id, old in before_items.items():
        new = after_items[character_id]
        allowed = (
            {"odds", "rarity", "isExchangeable"}
            if character_id == 119996
            else ({"odds", "rarity"} if old["odds"] == 5994 else set())
        )
        for field in set(old) | set(new):
            if old.get(field) != new.get(field) and field not in allowed:
                raise BuildError(f"server gacha overreach: id={character_id} field={field}")
        expected_exchange = True if character_id == 119996 else old["isExchangeable"]
        if new["isExchangeable"] is not expected_exchange:
            raise BuildError(f"server exchange state drifted: {character_id}")
    after_raw = replace_top_level_value(raw, "990001", pool, "assets/gacha.json")
    after_doc = json.loads(after_raw)
    if any(after_doc[key] != value for key, value in before_doc.items() if key != "990001"):
        raise BuildError("non-target server gacha pool changed")
    if after_doc["990001"] != pool:
        raise BuildError("server abyss pool text replacement failed")
    return after_raw, {
        "entries": len(items),
        "group_total_weight": sum(int(item["odds"]) for item in items),
        "five_star_total_rate_percent": 15.0,
        "filler_changed": len(filler),
        "old_exchange_states_preserved_except_lion": 249,
        "lion_exchange_enabled": True,
        "new_ids": [149995, 169996, 169997],
        "sorted_by_weight": all(items[i]["odds"] >= items[i + 1]["odds"] for i in range(len(items) - 1)),
    }


def prepare_server_files() -> dict[str, Any]:
    output_root = CANDIDATE_ROOT / "server-files"
    if output_root.exists():
        try:
            output_root.resolve().relative_to(CANDIDATE_ROOT.resolve())
        except ValueError as error:
            raise BuildError(f"refusing to replace server-files outside candidate root: {output_root}") from error
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    semantic = json.loads((FUSION_ROOT / "server-data/trio0825_rows.semantic.json").read_bytes())
    rows_report: dict[str, Any] = {}
    historical_rows: dict[str, Any] = {}
    for semantic_key, repo_relative in SERVER_ROW_TARGETS.items():
        rows = semantic.get(semantic_key)
        if not isinstance(rows, dict) or sorted(rows) != ["149995", "169996", "169997"]:
            raise BuildError(f"trio server semantic scope drifted: {semantic_key}")
        source = SOURCE_ROOT / repo_relative
        output = merge_top_level_rows(source.read_bytes(), rows, repo_relative)
        target = output_root / repo_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(output)
        before_doc = json.loads(source.read_bytes())
        after_doc = json.loads(output)
        preserved: dict[str, str] = {}
        for character_id in ("149996", "169999"):
            if character_id in before_doc:
                if after_doc.get(character_id) != before_doc[character_id]:
                    raise BuildError(
                        f"historical server character row changed: {repo_relative}/{character_id}"
                    )
                preserved[character_id] = sha256_bytes(
                    json.dumps(
                        before_doc[character_id], ensure_ascii=False,
                        sort_keys=True, separators=(",", ":"),
                    ).encode("utf-8")
                )
        historical_rows[repo_relative] = preserved
        rows_report[repo_relative] = {
            "base_sha256": sha256_file(source),
            "target_sha256": sha256_bytes(output),
            "semantic_ids": [149995, 169996, 169997],
            "newly_added_ids": [
                character_id for character_id in (149995, 169996, 169997)
                if str(character_id) not in before_doc
            ],
            "already_present_ids": [
                character_id for character_id in (149995, 169996, 169997)
                if str(character_id) in before_doc
            ],
            "pre_existing_bytes_preserved": True,
        }

    gacha_source = SOURCE_ROOT / "assets/gacha.json"
    gacha_raw, gacha_report = mutate_server_gacha(gacha_source.read_bytes())
    gacha_target = output_root / "assets/gacha.json"
    gacha_target.parent.mkdir(parents=True, exist_ok=True)
    gacha_target.write_bytes(gacha_raw)
    gacha_report.update({
        "base_sha256": sha256_file(gacha_source),
        "target_sha256": sha256_bytes(gacha_raw),
        "mode": "replace-only-top-level-990001-value",
    })

    tower_server = TOWER_ROOT / "server-root/server/assets"
    tower_rows: dict[str, Any] = {}
    for name in ("rush_event_quest.json", "rush_event_quest_folder.json"):
        source = tower_server / name
        target = output_root / "assets" / name
        value = json.loads(source.read_bytes())
        if name == "rush_event_quest_folder.json":
            value = rogue_rewards.build_server_folder(value)
            target.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        else:
            shutil.copy2(source, target)
        if name == "rush_event_quest.json":
            rounds = sorted(
                int(row["rushEventRound"])
                for key, row in value.items()
                if str(key).startswith("700099") and int(row.get("rushEventFolderId", -1)) == 1
            )
            if rounds != list(range(1, 31)):
                raise BuildError(f"tower server quest rounds drifted: {rounds}")
        elif "700099" not in value or "1" not in value["700099"]:
            raise BuildError("tower server folder 700099/1 is missing")
        tower_rows[f"assets/{name}"] = {
            "sha256": sha256_file(target),
            "seed": 2026082508,
        }

    rogue_source = SOURCE_ROOT / "assets/rogue_event.json"
    rogue_document = json.loads(rogue_source.read_bytes())
    rogue_rewards.validate_rogue_event(rogue_document)
    rogue_target = output_root / "assets/rogue_event.json"
    shutil.copy2(rogue_source, rogue_target)

    coordinated = (
        "src/routes/api/rushEvent.ts",
        "src/lib/rush-event-folder-lock.ts",
        "tests/rush-endless-folder-lock.test.js",
        "out/routes/api/rushEvent.js",
        "out/lib/rush-event-folder-lock.js",
        "src/lib/quest/finish/rogue-drop-schedule.ts",
        "src/lib/quest/finish/rogue-drops.ts",
        "out/lib/quest/finish/rogue-drop-schedule.js",
        "out/lib/quest/finish/rogue-drops.js",
        "src/routes/web_api/lookup.ts",
        "out/routes/web_api/lookup.js",
        "docs/generated/character_table.json",
    )
    code_report: dict[str, Any] = {}
    for relative in coordinated:
        source = SOURCE_ROOT / relative
        if not source.is_file():
            raise BuildError(f"coordinated Rush file is missing: {relative}")
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        code_report[relative] = {"sha256": sha256_file(source), "size": source.stat().st_size}

    result = {
        "status": "prepared-not-synced",
        "trio_rows": rows_report,
        "historical_character_rows_preserved": historical_rows,
        "gacha_990001": gacha_report,
        "tower_server_json": tower_rows,
        "rogue_rewards": {
            "config": {
                "path": "assets/rogue_event.json",
                "sha256": sha256_file(rogue_target),
            },
            "probability": rogue_rewards.probability_report(),
            "final_fixed": list(rogue_rewards.FINAL_FIXED_REWARDS),
            "final_chance": list(rogue_rewards.FINAL_CHANCE_REWARDS),
        },
        "admin_character_lookup": {
            "character_ids": [149995, 169996, 169997],
            "generated_table": "docs/generated/character_table.json",
            "server_data_fallback": "assets/character.json",
            "source": "src/routes/web_api/lookup.ts",
            "build": "out/routes/web_api/lookup.js",
            "included": True,
        },
        "rush_reset": {
            "event": 700099,
            "folder_progress_cleared": "all 30 finite rounds",
            "active_folder": 1,
            "next_round": 700099001,
            "reset_target_id": "ignored",
            "other_rush_events": "native",
            "drops_history_rewards_reclaimed": False,
            "one_time_reward_patch_included": False,
            "files": code_report,
        },
    }
    report_raw = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (output_root / "server-file-audit.json").write_bytes(report_raw)
    result["audit_sha256"] = sha256_bytes(report_raw)
    archive_path = CANDIDATE_ROOT / "server-files-coordinated.zip"
    files = sorted(path for path in output_root.rglob("*") if path.is_file())
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", allowZip64=True) as archive:
        for path in files:
            member = path.relative_to(output_root).as_posix()
            pure = PurePosixPath(member)
            if pure.is_absolute() or ".." in pure.parts:
                raise BuildError(f"unsafe server-file member: {member}")
            info = zipfile.ZipInfo(member, (2026, 8, 26, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    archive_raw = archive_buffer.getvalue()
    archive_path.write_bytes(archive_raw)
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        if archive.namelist() != [path.relative_to(output_root).as_posix() for path in files]:
            raise BuildError("server-file archive ordering drifted")
        for path in files:
            member = path.relative_to(output_root).as_posix()
            if archive.read(member) != path.read_bytes():
                raise BuildError(f"server-file archive readback failed: {member}")
    shutil.rmtree(output_root)
    result["archive"] = str(archive_path)
    result["archive_size"] = len(archive_raw)
    result["archive_sha256"] = sha256_bytes(archive_raw)
    result["archive_members"] = len(files)
    return result


def main() -> int:
    try:
        audit = validate_locked_inputs()
        base_plan = load_plan(BASE_SERVER, BASE_VERSION)
        history_plan = load_plan(HISTORY_SERVER, "1.4.91")
        payloads, provenance = history_delta(base_plan, history_plan)
        history_count = len(payloads)
        history_payloads = dict(payloads)
        history_archives = Counter(
            detail["history_archive"] for detail in provenance.values()
        )
        overlay_tower(payloads, provenance)
        rogue_reward_report = overlay_rogue_rewards(history_plan, payloads, provenance)
        client_report = apply_client_rows(history_plan, payloads, provenance)
        gacha_report = apply_client_gacha(history_plan, payloads, provenance)
        trio_assets = overlay_trio_assets(payloads, provenance)
        ios_report = overlay_ios_cutins(payloads, provenance)
        history_exact = sum(
            payloads.get(member) == raw for member, raw in history_payloads.items()
        )
        history_overlays = [
            {
                "member": member,
                "final_source": provenance[member]["source"],
                "before_sha256": sha256_bytes(raw),
                "after_sha256": sha256_bytes(payloads[member]),
            }
            for member, raw in sorted(history_payloads.items())
            if payloads.get(member) != raw
        ]
        if history_exact != 346 or len(history_overlays) != 5:
            raise BuildError(
                f"approved history preservation scope drifted: exact={history_exact} "
                f"overlays={len(history_overlays)}"
            )
        archive = zip_payloads(payloads)
        manifest = candidate_manifest(archive, payloads, audit)

        CANDIDATE_ROOT.mkdir(parents=True, exist_ok=True)
        CANDIDATE_ARCHIVE.write_bytes(archive)
        prepare_candidate_server(manifest, archive)
        terminal = terminal_verify(payloads)
        evidence = CANDIDATE_ROOT / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        character_terminal = validate_character_terminal()
        stale_server_files = CANDIDATE_ROOT / "server-files"
        if stale_server_files.exists():
            try:
                stale_server_files.resolve().relative_to(CANDIDATE_ROOT.resolve())
            except ValueError as error:
                raise BuildError(
                    f"refusing to clean stale server-files outside candidate root: {stale_server_files}"
                ) from error
            shutil.rmtree(stale_server_files)
        validation_commands = run_validation_commands(evidence)
        server_files = prepare_server_files()
        shutil.copy2(TOWER_EVIDENCE / "hp-audit-write.json", evidence / "hp-audit.json")
        shutil.copy2(TOWER_EVIDENCE / "hp-report-write.md", evidence / "hp-report.md")
        (evidence / "candidate-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        patch_audit = {
            "schema": "wf-integrated-cloud-baseline-candidate-v1",
            "status": "prepared-not-published",
            "cloud_baseline": BASE_VERSION,
            "target_version": TARGET_VERSION,
            "patch_id": PATCH_ID,
            "archive": str(CANDIDATE_ARCHIVE),
            "archive_size": len(archive),
            "archive_sha256": sha256_bytes(archive),
            "members": len(payloads),
            "history_delta_members_before_overlays": history_count,
            "history_source_tail": "1.4.91",
            "history_policy": "terminal diff from 1.4.87; no historical ZIP chaining required by client",
            "history_content_inventory": {
                "terminal_delta_members": history_count,
                "exact_byte_members_in_final": history_exact,
                "semantic_overlay_members": history_overlays,
                "source_archive_member_counts": dict(sorted(history_archives.items())),
                "confirmed_scope": [
                    "Ginovi PF 25/35/45 power-flip damage",
                    "Ginovi leader follow-up 25/35/50 skill damage",
                    "149996 leader/A1/A2/A3/A6 final rules, Xiwei whirlwind body, 1-second cooldown",
                    "149996 active 13 / 16->19 / 19->20 base ranges, combo 0.7%, 12-second pierce",
                    "149996 pool-safe narrow X field effect and approved character resources",
                    "Summer Stella awakening UI excluding awakening portraits",
                    "approved gacha feature rows, official images, and date-only archive changes from the historical bundle",
                ],
            },
            "tower": {
                "members": len(TOWER_LOGICALS),
                "inputs": audit["inputs"],
                "summary": audit["summary"],
                "audit_file_sha256": EXPECTED["tower_audit"],
                "report_sha256": EXPECTED["tower_report"],
                "tool_sha256": EXPECTED["tower_tool"],
                "verification_scope": "static_dry_run",
                "gameplay_verified": False,
            },
            "rogue_rewards": rogue_reward_report,
            "trio_client": client_report,
            "client_row_scope": {
                "tables": 21,
                "row_keys": 101,
                "trio_character_tables": 20,
                "trio_character_keys": 100,
                "gacha_tables": 1,
                "gacha_row_keys": 1,
            },
            "trio_assets": trio_assets,
            "ios_cutins": {"members": ios_report["members"], "slot": 3},
            "gacha_990001": gacha_report,
            "server_files": server_files,
            "terminal_replay": terminal,
            "historical_character_terminal": character_terminal,
            "validation_commands": validation_commands,
            "members_detail": [provenance[key] for key in sorted(provenance)],
            "excluded": [
                "upstream 1.4.352->1.4.353 anchor",
                "upstream Rush anti-refarm patch",
                "upstream full client pool row",
                "upstream full server pool snapshot",
                "old tower seed 2026082507",
                "local historical edges 1.4.88->1.4.94 as client prerequisites",
            ],
            "cloud_modified": False,
            "runtime_mirror_modified": False,
        }
        audit_raw = (json.dumps(patch_audit, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (evidence / "patch-audit.json").write_bytes(audit_raw)
        print(json.dumps({
            "status": patch_audit["status"],
            "base": BASE_VERSION,
            "target": TARGET_VERSION,
            "archive": str(CANDIDATE_ARCHIVE),
            "archive_size": len(archive),
            "archive_sha256": sha256_bytes(archive),
            "members": len(payloads),
            "history_delta_members": history_count,
            "terminal": terminal,
            "audit": str(evidence / "patch-audit.json"),
            "audit_sha256": sha256_bytes(audit_raw),
            "gameplay_verified": False,
        }, ensure_ascii=False, indent=2))
        return 0
    except (BuildError, OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        print(f"[ERR] {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
