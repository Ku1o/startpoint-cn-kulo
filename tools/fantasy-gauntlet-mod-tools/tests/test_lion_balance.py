from __future__ import annotations

from pathlib import Path
import sys
import unittest
import zlib


TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_mod_tool as core  # noqa: E402
import wf_lion_balance as balance  # noqa: E402


def ability_row(string_id: str) -> list[str]:
    row = [""] * 126
    row[0] = string_id
    return row


def encoded_rows(rows: list[list[str]]) -> bytes:
    return zlib.compress(core.write_csv_lines(rows).encode("utf-8"))


def fixture_table() -> bytes:
    ability3 = [ability_row("lion_swordman_reborn_3") for _ in range(7)]
    ability3[3][109:115] = ["154", "5", "Red", "", "400000", "400000"]
    ability3[4][109:115] = ["0", "5", "Red", "", "300000", "300000"]
    ability3[5][51:53] = ["1000000", "1000000"]
    ability3[6][51:53] = ["1000000", "1000000"]

    ability6 = [ability_row("lion_swordman_reborn_6") for _ in range(4)]
    ability6[0][51:53] = ["5000000", "5000000"]

    table = core.OrderedMap(
        balance.ABILITY_LOGICAL,
        ["unrelated", "1199963", "1199966"],
        [b"untouched-row", encoded_rows(ability3), encoded_rows(ability6)],
        Path("<fixture>"),
    )
    return core.build_orderedmap_raw_rows(table)


class LionBalanceTest(unittest.TestCase):
    def test_requested_targets_and_multipliers(self) -> None:
        patched, report = balance.patch_ability_table(fixture_table())
        table = core.read_orderedmap_raw_rows_from_bytes(
            patched, balance.ABILITY_LOGICAL
        )
        self.assertEqual(table.rows[0], b"untouched-row")

        ability3 = core.read_csv_lines(
            zlib.decompress(table.rows[1]).decode("utf-8")
        )
        self.assertEqual(ability3[3][110:112], ["0", ""])
        self.assertEqual(ability3[4][110:112], ["0", ""])
        self.assertEqual(ability3[5][51:53], ["500000", "500000"])
        self.assertEqual(ability3[6][51:53], ["500000", "500000"])

        ability6 = core.read_csv_lines(
            zlib.decompress(table.rows[2]).decode("utf-8")
        )
        self.assertEqual(ability6[0][51:53], ["3000000", "3000000"])
        self.assertTrue(report["changed"])

    def test_patch_is_idempotent(self) -> None:
        patched, _report = balance.patch_ability_table(fixture_table())
        again, report = balance.patch_ability_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(report["changed"])

    def test_rejects_unreviewed_drift(self) -> None:
        table = core.read_orderedmap_raw_rows_from_bytes(
            fixture_table(), balance.ABILITY_LOGICAL
        )
        ability3 = core.read_csv_lines(
            zlib.decompress(table.rows[1]).decode("utf-8")
        )
        ability3[5][51] = "999999"
        table.rows[1] = encoded_rows(ability3)
        with self.assertRaisesRegex(ValueError, "未审核"):
            balance.patch_ability_table(core.build_orderedmap_raw_rows(table))


if __name__ == "__main__":
    unittest.main()
