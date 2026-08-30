#!/usr/bin/env python3
"""Audit official/current data needed by the nine-character awakening migration.

This command is read-only.  It resolves both states from the live archive graph
without materialising the client store, then reports only character-owned rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
import zlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import wf_describe  # noqa: E402
import wf_dsl  # noqa: E402
import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_store_materialize as materialize  # noqa: E402


OFFICIAL_TAIL = "1.4.54"
CHARACTERS = {
    "151045": "夏日莉莉丝",
    "151027": "艾莉亚",
    "151021": "菲莉亚",
    "151015": "星川莉莉",
    "251017": "灯火莉莉丝",
    "251053": "萨莉哈",
    "151159": "拉夫马诺",
    "261089": "阿鲁玛德乌斯",
    "131020": "雷吉斯",
}

ABILITY_LOGICAL = "master/ability/ability.orderedmap"
LEADER_LOGICAL = "master/ability/leader_ability.orderedmap"
ACTION_LOGICAL = "master/skill/action_skill.orderedmap"
CHARACTER_LOGICAL = "master/character/character.orderedmap"
STATUS_LOGICAL = "master/character/character_status.orderedmap"
TEXT_LOGICAL = "master/character/character_text.orderedmap"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_plan_relative(plan: object, relative: str, root: str = "common") -> bytes:
    entry = plan.entries.get((root, relative))
    if entry is None:
        raise FileNotFoundError(f"{root}:{relative} missing at {plan.tail}")
    with zipfile.ZipFile(entry.zip_path) as archive:
        return archive.read(entry.name)


def read_plan_logical(plan: object, logical: str) -> bytes:
    digest = core.sha1_path(logical)
    return read_plan_relative(plan, f"{digest[:2]}/{digest[2:]}")


def flat_rows(raw: bytes, key: str) -> list[list[str]]:
    table = core.read_orderedmap_file_from_bytes(raw)
    return core.read_csv_lines(table[key])


def nested_rows(raw: bytes, logical: str, key: str) -> dict[str, list[list[str]]]:
    table = core.load_nested_table_bytes(raw, logical)
    return {
        inner_key: core.read_csv_lines(inner_raw)
        for inner_key, inner_raw in table.rows[key].text_rows().items()
    }


def index_diff(left: list[str], right: list[str]) -> list[dict[str, object]]:
    if len(left) != len(right):
        return [{"shape": [len(left), len(right)]}]
    return [
        {"index": index, "official": old, "current": new}
        for index, (old, new) in enumerate(zip(left, right))
        if old != new
    ]


def rowset_index_diff(
    left: list[list[str]], right: list[list[str]],
) -> list[dict[str, object]]:
    if len(left) != len(right):
        return [{"row_count": [len(left), len(right)]}]
    changes: list[dict[str, object]] = []
    for row_index, (old_row, new_row) in enumerate(zip(left, right)):
        for change in index_diff(old_row, new_row):
            changes.append({"row": row_index, **change})
    return changes


def status_rows(raw: bytes, character_id: str) -> dict[str, list[list[str]]]:
    outer = core.read_orderedmap_raw_rows_from_bytes(raw, STATUS_LOGICAL)
    positions = {key: index for index, key in enumerate(outer.keys)}
    return {
        inner_key: [row]
        for inner_key, row in core.decode_action_skill_row(
            outer.rows[positions[character_id]],
        )
    }


def action_programs(rows: dict[str, list[list[str]]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for evolution, csv_rows in rows.items():
        if len(csv_rows) != 1 or len(csv_rows[0]) <= 7:
            raise AssertionError(f"invalid action row at evolution {evolution}")
        result[evolution] = csv_rows[0][7]
    return result


def dsl_report(plan: object, programs: dict[str, str], *, current: bool) -> dict[str, object]:
    result: dict[str, object] = {}
    for evolution, program in programs.items():
        logical = f"{program}.action.dsl.amf3.deflate"
        raw = (
            wf_live_cdn.read_logical(logical).data
            if current
            else read_plan_logical(plan, logical)
        )
        tree = wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
        semantic = json.dumps(
            tree, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        result[evolution] = {
            "program": program,
            "logical": logical,
            "sha256": sha256(raw),
            "size": len(raw),
            "semantic_sha256": sha256(semantic),
        }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cdn_root, server_root = wf_live_cdn._resolve_locations()
    official = materialize.build_read_only_plan(
        cdn_root, server_root, OFFICIAL_TAIL, False,
    )
    current_view = wf_live_cdn.describe()

    official_raw = {
        logical: read_plan_logical(official, logical)
        for logical in (
            ABILITY_LOGICAL,
            LEADER_LOGICAL,
            ACTION_LOGICAL,
            CHARACTER_LOGICAL,
            STATUS_LOGICAL,
            TEXT_LOGICAL,
        )
    }
    current_raw = {
        logical: wf_live_cdn.read_logical(logical).data
        for logical in official_raw
    }

    result: dict[str, object] = {
        "schema": "wf-awakened-balance-migration-audit/v1",
        "official_tail": official.tail,
        "current_view": current_view,
        "characters": {},
    }
    character_reports = result["characters"]
    assert isinstance(character_reports, dict)

    for character_id, name in CHARACTERS.items():
        official_character = flat_rows(
            official_raw[CHARACTER_LOGICAL], character_id,
        )[0]
        current_character = flat_rows(
            current_raw[CHARACTER_LOGICAL], character_id,
        )[0]
        official_text = flat_rows(official_raw[TEXT_LOGICAL], character_id)[0]
        current_text = flat_rows(current_raw[TEXT_LOGICAL], character_id)[0]
        code = current_character[0]
        if official_character[0] != code:
            raise AssertionError(f"character code drifted for {character_id}")

        abilities: dict[str, object] = {}
        for slot in range(1, 7):
            key = f"{character_id}{slot}"
            old = flat_rows(official_raw[ABILITY_LOGICAL], key)
            new = flat_rows(current_raw[ABILITY_LOGICAL], key)
            abilities[str(slot)] = {
                "key": key,
                "changed": old != new,
                "official_rows": len(old),
                "current_rows": len(new),
                "diff": rowset_index_diff(old, new),
                "official": wf_describe.describe_rows(old, "ability"),
                "current": wf_describe.describe_rows(new, "ability"),
                "current_damage_ct_frames": [
                    {"row": index, "instant": row[35], "accumulation": row[93]}
                    for index, row in enumerate(new)
                    if len(row) > 109 and row[47] in {"253", "254", "255", "356", "357", "358"}
                ],
            }

        official_leader = flat_rows(official_raw[LEADER_LOGICAL], character_id)
        current_leader = flat_rows(current_raw[LEADER_LOGICAL], character_id)
        official_action = nested_rows(official_raw[ACTION_LOGICAL], ACTION_LOGICAL, code)
        current_action = nested_rows(current_raw[ACTION_LOGICAL], ACTION_LOGICAL, code)
        official_status = status_rows(official_raw[STATUS_LOGICAL], character_id)
        current_status = status_rows(current_raw[STATUS_LOGICAL], character_id)

        character_reports[character_id] = {
            "name": name,
            "code": code,
            "rarity": {
                "official": int(official_character[2]),
                "current": int(current_character[2]),
            },
            "character_diff": index_diff(official_character, current_character),
            "character_text_diff": index_diff(official_text, current_text),
            "status_changed": official_status != current_status,
            "status_official": official_status,
            "status_current": current_status,
            "abilities": abilities,
            "changed_ability_slots": [
                int(slot) for slot, data in abilities.items() if data["changed"]
            ],
            "leader": {
                "changed": official_leader != current_leader,
                "diff": rowset_index_diff(official_leader, current_leader),
                "official": wf_describe.describe_rows(official_leader, "leader_ability"),
                "current": wf_describe.describe_rows(current_leader, "leader_ability"),
                "current_damage_ct_frames": [
                    {"row": index, "instant": row[33], "accumulation": row[91]}
                    for index, row in enumerate(current_leader)
                    if len(row) > 107 and row[45] in {"253", "254", "255", "356", "357", "358"}
                ],
            },
            "action": {
                "changed": official_action != current_action,
                "official_rows": official_action,
                "current_rows": current_action,
                "official_dsl": dsl_report(
                    official, action_programs(official_action), current=False,
                ),
                "current_dsl": dsl_report(
                    official, action_programs(current_action), current=True,
                ),
            },
        }

    if args.summary:
        summary = {
            "official_tail": result["official_tail"],
            "current_tail": current_view["tail"],
            "characters": {
                character_id: {
                    "rarity": report["rarity"],
                    "character_diff_indexes": [
                        item.get("index") for item in report["character_diff"]
                    ],
                    "text_diff_indexes": [
                        item.get("index") for item in report["character_text_diff"]
                    ],
                    "status_changed": report["status_changed"],
                    "changed_ability_slots": report["changed_ability_slots"],
                    "leader_changed": report["leader"]["changed"],
                    "action_rows_changed": report["action"]["changed"],
                    "action_dsl_changed": {
                        evolution: (
                            item["sha256"]
                            != report["action"]["current_dsl"].get(evolution, {}).get("sha256")
                        )
                        for evolution, item in report["action"]["official_dsl"].items()
                    },
                    "action_dsl_semantically_changed": {
                        evolution: (
                            item["semantic_sha256"]
                            != report["action"]["current_dsl"].get(evolution, {}).get("semantic_sha256")
                        )
                        for evolution, item in report["action"]["official_dsl"].items()
                    },
                    "action_row_diff_indexes": {
                        evolution: rowset_index_diff(
                            report["action"]["official_rows"].get(evolution, []),
                            report["action"]["current_rows"].get(evolution, []),
                        )
                        for evolution in sorted(set(
                            report["action"]["official_rows"]
                        ) | set(report["action"]["current_rows"]))
                    },
                    "ability_damage_ct_frames": {
                        slot: item["current_damage_ct_frames"]
                        for slot, item in report["abilities"].items()
                        if item["current_damage_ct_frames"]
                    },
                    "leader_damage_ct_frames": report["leader"]["current_damage_ct_frames"],
                    **({
                        "status_official": report["status_official"],
                        "status_current": report["status_current"],
                    } if report["status_changed"] else {}),
                }
                for character_id, report in character_reports.items()
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
