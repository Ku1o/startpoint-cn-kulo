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
import wf_gerald_balance as balance  # noqa: E402


def numeric_range(value: float) -> list[dict[str, float]]:
    return [{"min": value, "max": value}]


def encode_tree(tree: list) -> bytes:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(wf_dsl.encode_amf3(tree)) + compressor.flush()


def decode_tree(raw: bytes) -> list:
    return wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]


def skill_payload(level: int) -> bytes:
    current = balance.CURRENT_RESISTANCES[level]
    tree = [
        "ActionDsl",
        1,
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
                [
                    "Command",
                    [
                        "CreateCondition",
                        2,
                        [
                            [
                                "ACAbilityDamageResistance",
                                numeric_range(1800),
                                numeric_range(current["ability"]),
                                numeric_range(1),
                            ]
                        ],
                    ],
                ],
                [
                    "Command",
                    [
                        "CreateCondition",
                        2,
                        [
                            [
                                "ACToleranceOfElement",
                                numeric_range(1800),
                                5,
                                numeric_range(current["light"]),
                                numeric_range(1),
                            ]
                        ],
                    ],
                ],
                ["Command", ["StopBall", -18, 30, ["Restore"], ["EF"], 0]],
            ],
        ],
    ]
    return encode_tree(tree)


def ability_row(string_id: str) -> list[str]:
    row = [""] * 126
    row[0] = string_id
    row[1] = "true"
    return row


def encoded_rows(rows: list[list[str]]) -> bytes:
    return zlib.compress(core.write_csv_lines(rows).encode("utf-8"))


def ability_fixture() -> bytes:
    rows2 = [ability_row("black_wolf_knight_2") for _ in range(5)]
    for row in rows2[:4]:
        row[34] = "(None)"

    rows3 = [ability_row("black_wolf_knight_3") for _ in range(4)] + [
        ability_row("black_wolf_knight_5") for _ in range(2)
    ]
    rows3[0][1] = "false"
    rows3[0][51:53] = ["1000000", "1000000"]

    rows4 = [ability_row("black_wolf_knight_4") for _ in range(2)]
    rows4[0][51:53] = ["1000000", "1000000"]

    rows5 = [ability_row("black_wolf_knight_3") for _ in range(6)]
    for row in rows5:
        row[51:53] = ["500000", "500000"]

    table = core.OrderedMap(
        balance.ABILITY_LOGICAL,
        ["other", "1499992", "1499993", "1499994", "1499995"],
        [
            b"untouched-row",
            encoded_rows(rows2),
            encoded_rows(rows3),
            encoded_rows(rows4),
            encoded_rows(rows5),
        ],
        Path("<fixture>"),
    )
    return core.build_orderedmap_raw_rows(table)


class GeraldSkillBalanceTest(unittest.TestCase):
    def test_both_forms_use_fixed_fifteen_percent_resistance_down(self) -> None:
        for level, logical in balance.SKILL_DSL_LOGICALS.items():
            with self.subTest(level=level):
                raw = skill_payload(level)
                before = decode_tree(raw)
                patched, report = balance.patch_skill_dsl(raw, logical)
                after = decode_tree(patched)
                ability, light = balance._skill_conditions(after, logical)
                self.assertEqual(ability[2], numeric_range(-0.15))
                self.assertEqual(light[3], numeric_range(-0.15))
                self.assertEqual(report["duration_seconds"], 30)

                expected = copy.deepcopy(before)
                expected_ability, expected_light = balance._skill_conditions(
                    expected, logical
                )
                expected_ability[2] = numeric_range(-0.15)
                expected_light[3] = numeric_range(-0.15)
                self.assertEqual(after, expected)

                again, second = balance.patch_skill_dsl(patched, logical)
                self.assertEqual(again, patched)
                self.assertFalse(second["changed"])

    def test_batch_requires_both_skill_forms(self) -> None:
        with self.assertRaisesRegex(ValueError, "缺少杰拉德主动技能payload"):
            balance.patch_skill_dsls({})


class GeraldAbilityBalanceTest(unittest.TestCase):
    def test_requested_limits_main_position_and_multipliers(self) -> None:
        patched, report = balance.patch_ability_table(ability_fixture())
        table = core.read_orderedmap_raw_rows_from_bytes(
            patched, balance.ABILITY_LOGICAL
        )
        self.assertEqual(table.rows[0], b"untouched-row")
        decoded = {
            key: core.read_csv_lines(
                zlib.decompress(table.rows[table.keys.index(key)]).decode("utf-8")
            )
            for key in balance.ABILITY_EDITS
        }
        self.assertEqual([row[34] for row in decoded["1499992"][:4]], ["1"] * 4)
        self.assertEqual(decoded["1499993"][0][51:53], ["300000", "300000"])
        self.assertEqual([row[1] for row in decoded["1499994"]], ["false"] * 2)
        self.assertEqual(decoded["1499994"][0][51:53], ["100000", "100000"])
        self.assertEqual([row[1] for row in decoded["1499995"]], ["false"] * 6)
        self.assertTrue(
            all(row[51:53] == ["300000", "300000"] for row in decoded["1499995"])
        )
        self.assertTrue(report["changed"])

    def test_patch_is_idempotent(self) -> None:
        patched, _report = balance.patch_ability_table(ability_fixture())
        again, report = balance.patch_ability_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(report["changed"])


if __name__ == "__main__":
    unittest.main()
