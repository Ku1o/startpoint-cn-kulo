from __future__ import annotations

from pathlib import Path
import sys
import unittest
import zlib


TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_mod_tool as core  # noqa: E402
import wf_vaseraga_balance as balance  # noqa: E402


def leader_rows() -> list[list[str]]:
    rows = [[""] * 124 for _ in range(13)]
    for row in rows:
        row[0] = "vaseraga_dark"
    refund = rows[7]
    for column, value in balance._REFUND_NONDEFAULT:
        refund[column] = value
    return rows


class VaseragaBalanceTest(unittest.TestCase):
    def test_removes_only_skill_gauge_refund_and_is_idempotent(self) -> None:
        rows = leader_rows()
        rows[8][45] = "32"
        rows[8][49] = rows[8][50] = "300000"
        expected_next = list(rows[8])
        patched, report = balance.patch_leader_ability_rows(rows)
        self.assertEqual(len(patched), 12)
        self.assertEqual(patched[7], expected_next)
        self.assertEqual(report["removed_line"], 8)
        self.assertTrue(report["changed"])

        again, second = balance.patch_leader_ability_rows(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second["changed"])

    def test_table_preserves_every_other_character_byte_for_byte(self) -> None:
        target = zlib.compress(core.write_csv_lines(leader_rows()).encode("utf-8"))
        unrelated = b"unrelated-compressed-row"
        table = core.OrderedMap(
            balance.LEADER_ABILITY_LOGICAL,
            ["100001", balance.CHARACTER_ID],
            [unrelated, target],
            Path("<fixture>"),
        )
        raw = core.build_orderedmap_raw_rows(table)
        patched, report = balance.patch_leader_ability_table(raw)
        readback = core.read_orderedmap_raw_rows_from_bytes(
            patched, balance.LEADER_ABILITY_LOGICAL
        )
        self.assertEqual(readback.rows[0], unrelated)
        rows = core.read_csv_lines(zlib.decompress(readback.rows[1]).decode("utf-8"))
        self.assertEqual(len(rows), 12)
        self.assertIsNone(balance.refund_line_number(rows))
        self.assertTrue(report["changed"])

        again, second = balance.patch_leader_ability_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second["changed"])

    def test_skill_text_has_no_direct_gauge_or_hp_cost_claim(self) -> None:
        description = balance.SKILL_DESCRIPTION
        self.assertNotIn("技能槽增加", description)
        self.assertNotIn("消耗自身最大生命值", description)
        self.assertIn("能力伤害提升400%（20秒）", description)
        self.assertEqual(
            balance.SKILL_DESCRIPTION_FIELDS,
            {
                "skill_desc": description,
                "skill_plus_desc": description,
                "skill_plusplus_desc": description,
            },
        )


if __name__ == "__main__":
    unittest.main()
