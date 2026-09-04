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
import wf_siete_balance as balance  # noqa: E402


def numeric_range(value: float) -> dict[str, float]:
    return {"min": value, "max": value}


def normal_attack(attack_id: int, multiplier: float) -> list:
    return [
        "CreateNormalAttack",
        attack_id,
        255,
        [],
        [],
        1,
        [numeric_range(multiplier)],
        [numeric_range(0.0)],
        True,
        False,
        False,
        False,
        False,
        [numeric_range(0.0)],
        [numeric_range(0.0)],
        ["None"],
        True,
    ]


def encode_tree(tree: list) -> bytes:
    encoded = wf_dsl.encode_amf3(tree)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(encoded) + compressor.flush()


def decode_tree(raw: bytes) -> list:
    return wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]


def payload_for(level: int) -> bytes:
    branches = []
    for layer in range(12, 0, -1):
        multiplier = balance.CURRENT_MULTIPLIER_BY_LEVEL[level][layer]
        attacks = [
            ["Command", normal_attack(layer * 100 + hit, multiplier)]
            for hit in range(layer + 1)
        ]
        branches.append(
            [
                "Command",
                [
                    "ConditionalsConditionAccumulationNumber",
                    ["DCUnique", 149995],
                    layer,
                    ["Block", attacks],
                    ["Block", []],
                ],
            ]
        )
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
        ["Block", branches],
    ]
    return encode_tree(tree)


def action_skill_row(level: int, description: str) -> list[str]:
    row = [""] * 24
    row[0] = f"Cien Mil Espada {level}"
    row[1] = description
    row[7] = (
        "battle/action/skill/action/rare5/seofon_wind$"
        f"seofon_wind_{level}"
    )
    return row


def character_text_row(description: str) -> list[str]:
    return [
        "希耶提",
        "SIETE",
        "profile",
        "十天众之首",
        "skill1",
        description,
        "skill2",
        description,
        "skill3",
        description,
        "剑光统御",
        "",
    ]


class SieteSkillDslBalanceTest(unittest.TestCase):
    def test_confirmed_tiers_hit_counts_and_totals_for_both_forms(self) -> None:
        expected_tiers = {
            1: {
                **{layer: 25.0 for layer in range(1, 3)},
                **{layer: 30.0 for layer in range(3, 6)},
                **{layer: 40.0 for layer in range(6, 9)},
                **{layer: 50.0 for layer in range(9, 12)},
                12: 70.0,
            },
            2: {
                **{layer: 30.0 for layer in range(1, 3)},
                **{layer: 35.0 for layer in range(3, 6)},
                **{layer: 45.0 for layer in range(6, 9)},
                **{layer: 55.0 for layer in range(9, 12)},
                12: 80.0,
            },
        }
        self.assertEqual(balance.TARGET_MULTIPLIER_BY_LEVEL, expected_tiers)

        for level, logical in balance.SKILL_DSL_LOGICALS.items():
            with self.subTest(level=level):
                patched, report = balance.patch_skill_dsl(payload_for(level), logical)
                tree = decode_tree(patched)
                branches = balance._layer_attacks(tree, logical)
                for layer, attacks in branches.items():
                    self.assertEqual(len(attacks), layer + 1)
                    self.assertEqual(
                        [attack[6][0] for attack in attacks],
                        [numeric_range(expected_tiers[level][layer])] * (layer + 1),
                    )
                    detail = report["layers"][str(layer)]
                    self.assertEqual(detail["sword_avatar_hits"], 1)
                    self.assertEqual(detail["spirit_sword_hits"], layer)
                    self.assertEqual(detail["total_hits"], layer + 1)
                    self.assertEqual(
                        detail["after_total"],
                        (layer + 1) * expected_tiers[level][layer],
                    )

                repatched, second = balance.patch_skill_dsl(patched, logical)
                self.assertEqual(repatched, patched)
                self.assertFalse(second["changed"])

    def test_only_attack_multiplier_ranges_change(self) -> None:
        logical = balance.SKILL_DSL_LOGICALS[1]
        raw = payload_for(1)
        before = decode_tree(raw)
        patched, _report = balance.patch_skill_dsl(raw, logical)
        after = decode_tree(patched)
        expected = copy.deepcopy(before)
        for layer, attacks in balance._layer_attacks(expected, logical).items():
            for attack in attacks:
                attack[6][0] = numeric_range(
                    balance.TARGET_MULTIPLIER_BY_LEVEL[1][layer]
                )
        self.assertEqual(after, expected)

    def test_accepts_the_previous_1_4_92_uniform_bands_as_source(self) -> None:
        for level, logical in balance.SKILL_DSL_LOGICALS.items():
            with self.subTest(level=level):
                tree = decode_tree(payload_for(level))
                for layer, attacks in balance._layer_attacks(tree, logical).items():
                    legacy = balance._PREVIOUS_TARGET_MULTIPLIER_BY_LEVEL[level][layer]
                    for attack in attacks:
                        attack[6][0] = numeric_range(legacy)
                patched, report = balance.patch_skill_dsl(encode_tree(tree), logical)
                self.assertTrue(report["changed"])
                branches = balance._layer_attacks(decode_tree(patched), logical)
                for layer, attacks in branches.items():
                    target = balance.TARGET_MULTIPLIER_BY_LEVEL[level][layer]
                    self.assertEqual(
                        [attack[6][0] for attack in attacks],
                        [numeric_range(target)] * (layer + 1),
                    )

    def test_rejects_hit_count_or_unreviewed_multiplier_drift(self) -> None:
        logical = balance.SKILL_DSL_LOGICALS[1]
        tree = decode_tree(payload_for(1))
        layer_seven = next(
            node
            for node in balance._walk(tree)
            if isinstance(node, list)
            and len(node) >= 4
            and node[0] == "ConditionalsConditionAccumulationNumber"
            and node[2] == 7
        )
        layer_seven[3][1].pop()
        with self.assertRaisesRegex(ValueError, "命中段数漂移"):
            balance.patch_skill_dsl(encode_tree(tree), logical)

        tree = decode_tree(payload_for(1))
        branches = balance._layer_attacks(tree, logical)
        branches[7][0][6][0] = numeric_range(999.0)
        with self.assertRaisesRegex(ValueError, "各段倍率不一致"):
            balance.patch_skill_dsl(encode_tree(tree), logical)

    def test_official_signature_and_parameter_allowlist_are_enforced(self) -> None:
        logical = balance.SKILL_DSL_LOGICALS[1]
        tree = decode_tree(payload_for(1))
        attack = balance._layer_attacks(tree, logical)[1][0]
        attack[1] = "not-an-attack-id"
        with self.assertRaisesRegex(ValueError, "官方签名/枚举校验失败"):
            balance.patch_skill_dsl(encode_tree(tree), logical)

        before = decode_tree(payload_for(1))
        after = copy.deepcopy(before)
        balance._layer_attacks(after, logical)[1][0][1] += 1
        with self.assertRaisesRegex(ValueError, "非倍率参数发生未授权变化"):
            balance._assert_only_attack_multiplier_change(before, after, logical)

    def test_batch_requires_both_skill_forms(self) -> None:
        with self.assertRaisesRegex(ValueError, "缺少希耶提主动技能 payload"):
            balance.patch_skill_dsls({})


class SieteDescriptionBalanceTest(unittest.TestCase):
    def test_description_links_layers_hits_and_new_tiers(self) -> None:
        description = balance.SKILL_DESCRIPTION
        self.assertIn("N把灵剑（每把攻击1段）", description)
        self.assertIn("共N+1段", description)
        self.assertIn("进化前每段倍率：1～2级25倍，3～5级30倍，6～8级40倍，9～11级50倍，12级70倍", description)
        self.assertIn("进化后每段倍率：1～2级30倍，3～5级35倍，6～8级45倍，9～11级55倍，12级80倍", description)
        self.assertIn("30%加速（10秒）", description)

    def test_action_skill_table_changes_only_seofon_descriptions(self) -> None:
        target = core.encode_action_skill_row(
            [
                ("1", action_skill_row(1, balance.OLD_SKILL_DESCRIPTION)),
                ("2", action_skill_row(2, balance.OLD_SKILL_DESCRIPTION)),
            ]
        )
        unrelated = b"untouched-action-skill-row"
        table = core.OrderedMap(
            balance.ACTION_SKILL_LOGICAL,
            ["other_skill", balance.ACTION_SKILL_KEY],
            [unrelated, target],
            Path("<fixture>"),
        )
        raw = core.build_orderedmap_raw_rows(table)
        patched, report = balance.patch_action_skill_table(raw)
        readback = core.read_orderedmap_raw_rows_from_bytes(
            patched, balance.ACTION_SKILL_LOGICAL
        )
        self.assertEqual(readback.rows[0], unrelated)
        rows = core.decode_action_skill_row(readback.rows[1])
        self.assertEqual(
            [row[1] for _level, row in rows],
            [
                balance.SKILL_DESCRIPTION_BY_LEVEL[1],
                balance.SKILL_DESCRIPTION_BY_LEVEL[2],
            ],
        )
        self.assertTrue(report["changed"])
        again, second = balance.patch_action_skill_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second["changed"])

    def test_character_text_tables_and_server_document_use_same_description(self) -> None:
        target = zlib.compress(
            core.write_csv_lines(
                [character_text_row(balance.OLD_SKILL_DESCRIPTION)]
            ).encode("utf-8")
        )
        unrelated = zlib.compress(b"other-character-row")
        table = core.OrderedMap(
            balance.CHARACTER_TEXT_LOGICAL,
            ["100001", balance.CHARACTER_ID],
            [unrelated, target],
            Path("<fixture>"),
        )
        raw = core.build_orderedmap_raw_rows(table)
        patched, report = balance.patch_character_text_table(raw)
        readback = core.read_orderedmap_raw_rows_from_bytes(
            patched, balance.CHARACTER_TEXT_LOGICAL
        )
        self.assertEqual(readback.rows[0], unrelated)
        row = core.read_csv_lines(
            zlib.decompress(readback.rows[1]).decode("utf-8")
        )[0]
        self.assertEqual(
            [row[column] for column in (5, 7, 9)],
            [balance.SKILL_DESCRIPTION] * 3,
        )
        self.assertTrue(report["changed"])

        document, server_report = balance.patch_server_character_text_document(
            {
                balance.CHARACTER_ID: [
                    character_text_row(balance.OLD_SKILL_DESCRIPTION)
                ]
            }
        )
        self.assertEqual(
            [document[balance.CHARACTER_ID][0][column] for column in (5, 7, 9)],
            [balance.SKILL_DESCRIPTION] * 3,
        )
        self.assertTrue(server_report["changed"])


if __name__ == "__main__":
    unittest.main()
