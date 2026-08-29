from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest
import zlib


TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_dsl  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_simoun_balance as balance  # noqa: E402


def fixed(value: float) -> list[dict[str, float]]:
    return [{"min": value, "max": value}]


def normal_attack(multiplier: float) -> list:
    return [
        "Command",
        [
            "CreateNormalAttack",
            1,
            255,
            [],
            [],
            80,
            fixed(multiplier),
            fixed(0.0),
            False,
            False,
            False,
            False,
            False,
            fixed(10.0),
            fixed(10.0),
            ["Coarse"],
            True,
        ],
    ]


def ratio_heal(ratio: float) -> list:
    return [
        "Command",
        [
            "CreateRatioHeal",
            1,
            2,
            fixed(ratio),
            [],
            fixed(0.0),
            ["GenericHealHitEffect"],
        ],
    ]


def condition_chain(layer: int = 4) -> list:
    if layer == 0:
        return normal_attack(20.0)
    multiplier = {1: 40.0, 2: 60.0, 3: 80.0, 4: 100.0}[layer]
    ratio = layer * 0.03
    return [
        "Command",
        [
            "ConditionalsConditionAccumulationNumber",
            ["DCUnique", balance.UNIQUE_CONDITION_ID],
            layer,
            ["Block", [normal_attack(multiplier), ratio_heal(ratio), ratio_heal(ratio)]],
            condition_chain(layer - 1),
        ],
    ]


def skill_payload() -> bytes:
    tree = [
        "ActionDsl",
        2,
        ["None"],
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        0,
        [
            "Block",
            [
                ["Command", ["AddSkillPoint", 20, fixed(0.2)]],
                condition_chain(),
            ],
        ],
    ]
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    encoded = wf_dsl.encode_amf3(tree)
    return compressor.compress(encoded) + compressor.flush()


def csv_table_fixture(
    logical: str,
    edits,
    row_counts: dict[str, int],
    width: int,
) -> tuple[bytes, bytes]:
    keys = ["unrelated", *edits]
    unrelated = zlib.compress(b"unrelated-row")
    payloads = [unrelated]
    for key, key_edits in edits.items():
        rows = [[""] * width for _ in range(row_counts[key])]
        string_id = "simoun_dark" + (f"_{key[-1]}" if key != balance.CHARACTER_ID else "")
        for row in rows:
            row[0] = string_id
        for line, column, current, _target, _label in key_edits:
            rows[line - 1][column] = current
        payloads.append(zlib.compress(core.write_csv_lines(rows).encode("utf-8")))
    table = core.OrderedMap(logical, keys, payloads, Path("<fixture>"))
    return core.build_orderedmap_raw_rows(table), unrelated


class SimounSkillBalanceTest(unittest.TestCase):
    def test_skill_gauge_is_fifteen_percent_without_flock_reset(self) -> None:
        logical = balance.SKILL_DSL_LOGICALS[1]
        raw = skill_payload()
        before = balance._decode_skill(raw, logical)
        patched, report = balance.patch_skill_dsl(raw, logical)
        after = balance._decode_skill(patched, logical)
        facts = balance._skill_facts(after, logical)

        self.assertEqual(facts["gauge"], ["AddSkillPoint", 20, fixed(0.15)])
        self.assertEqual(facts["resets"], [])
        self.assertEqual(sorted(facts["attacks"]), [20, 40, 60, 80, 100])
        self.assertEqual(
            sorted(facts["heals"]),
            [0.03, 0.03, 0.06, 0.06, 0.09, 0.09, 0.12, 0.12],
        )
        expected = copy.deepcopy(before)
        expected[11][1][0][1] = ["AddSkillPoint", 20, fixed(0.15)]
        self.assertEqual(after, expected)
        self.assertTrue(report["changed"])

        again, second = balance.patch_skill_dsl(patched, logical)
        self.assertEqual(again, patched)
        self.assertFalse(second["changed"])

    def test_previously_published_unsafe_flock_reset_is_removed(self) -> None:
        logical = balance.SKILL_DSL_LOGICALS[2]
        tree = balance._decode_skill(skill_payload(), logical)
        tree[11][1].append(copy.deepcopy(balance.UNSAFE_RESET_COMMAND))
        raw = balance._raw_deflate(wf_dsl.encode_amf3(tree))

        patched, report = balance.patch_skill_dsl(raw, logical)
        after = balance._decode_skill(patched, logical)

        self.assertEqual(balance._skill_facts(after, logical)["resets"], [])
        self.assertEqual(after[11][1][0][1], ["AddSkillPoint", 20, fixed(0.15)])
        self.assertTrue(report["changed"])

    def test_previously_published_invalid_skill_point_target_is_repaired(self) -> None:
        logical = balance.SKILL_DSL_LOGICALS[3]
        tree = balance._decode_skill(skill_payload(), logical)
        tree[11][1][0][1] = ["AddSkillPoint", 15, fixed(0.15)]
        raw = balance._raw_deflate(wf_dsl.encode_amf3(tree))

        patched, report = balance.patch_skill_dsl(raw, logical)
        after = balance._decode_skill(patched, logical)

        self.assertEqual(after[11][1][0][1], ["AddSkillPoint", 20, fixed(0.15)])
        self.assertEqual(balance._skill_facts(after, logical)["resets"], [])
        self.assertEqual(report["skill_point_target_id"], 20)
        self.assertTrue(report["changed"])

    def test_description_is_exact_about_hp_and_cast_time_flock(self) -> None:
        description = balance.SKILL_DESCRIPTION
        self.assertIn("发动技能时自身「羊群」等级", description)
        self.assertIn("生命回复量为各自最大生命值的0%／3%／6%／9%／12%", description)
        self.assertIn("全体队员技能槽增加15%", description)
        self.assertNotIn("清零", description)


class SimounAbilityBalanceTest(unittest.TestCase):
    def test_ability_table_only_changes_reviewed_simoun_values(self) -> None:
        counts = {
            "1699961": 5,
            "1699962": 3,
            "1699963": 4,
        }
        raw, unrelated = csv_table_fixture(
            balance.ABILITY_LOGICAL,
            balance.ABILITY_EDITS,
            counts,
            126,
        )
        patched, report = balance.patch_ability_table(raw)
        table = core.read_orderedmap_raw_rows_from_bytes(patched, balance.ABILITY_LOGICAL)
        self.assertEqual(table.rows[0], unrelated)
        for key, edits in balance.ABILITY_EDITS.items():
            rows = core.read_csv_lines(
                zlib.decompress(table.rows[table.keys.index(key)]).decode("utf-8")
            )
            for line, column, _current, target, _label in edits:
                self.assertEqual(rows[line - 1][column], target)
        self.assertTrue(report["changed"])

        again, second = balance.patch_ability_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second["changed"])

    def test_leader_table_only_changes_reviewed_simoun_values(self) -> None:
        raw, unrelated = csv_table_fixture(
            balance.LEADER_ABILITY_LOGICAL,
            balance.LEADER_EDITS,
            {balance.CHARACTER_ID: 6},
            124,
        )
        patched, report = balance.patch_leader_ability_table(raw)
        table = core.read_orderedmap_raw_rows_from_bytes(
            patched, balance.LEADER_ABILITY_LOGICAL
        )
        self.assertEqual(table.rows[0], unrelated)
        rows = core.read_csv_lines(zlib.decompress(table.rows[1]).decode("utf-8"))
        for line, column, _current, target, _label in balance.LEADER_EDITS[balance.CHARACTER_ID]:
            self.assertEqual(rows[line - 1][column], target)
        self.assertTrue(report["changed"])

        again, second = balance.patch_leader_ability_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second["changed"])


if __name__ == "__main__":
    unittest.main()
