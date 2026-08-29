from __future__ import annotations

from pathlib import Path
import sys
import unittest
import zlib


TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_abyss_custom_position_fix as fix  # noqa: E402
import wf_mod_tool as core  # noqa: E402


def fixture() -> tuple[bytes, bytes]:
    unrelated = zlib.compress(b"unrelated,terrain,zone\n")
    keys = ["unrelated", *fix.FIELD_FIXES]
    rows = [unrelated]
    for spec in fix.FIELD_FIXES.values():
        rows.append(zlib.compress(
            core.write_csv_lines([list(spec["before"])]).encode("utf-8")
        ))
    table = core.OrderedMap(fix.FIELD_DATA_LOGICAL, keys, rows, Path("<fixture>"))
    return core.build_orderedmap_raw_rows(table), unrelated


class AbyssCustomPositionFixTest(unittest.TestCase):
    def test_only_round_three_and_four_field_rows_change(self) -> None:
        raw, unrelated = fixture()
        patched, report = fix.patch_field_data(raw)
        table = core.read_orderedmap_raw_rows_from_bytes(
            patched, fix.FIELD_DATA_LOGICAL
        )
        self.assertEqual(unrelated, table.rows[0])
        for key, spec in fix.FIELD_FIXES.items():
            index = table.keys.index(key)
            self.assertEqual(list(spec["after"]), fix._decode_row(table.rows[index], key))
            self.assertEqual(
                list(spec["before"])[2],
                list(spec["after"])[2],
                "zone ID 必须保持不变",
            )
        self.assertTrue(report["changed"])

    def test_patch_is_idempotent(self) -> None:
        raw, _unrelated = fixture()
        patched, _first = fix.patch_field_data(raw)
        again, second = fix.patch_field_data(patched)
        self.assertEqual(patched, again)
        self.assertFalse(second["changed"])


if __name__ == "__main__":
    unittest.main()
