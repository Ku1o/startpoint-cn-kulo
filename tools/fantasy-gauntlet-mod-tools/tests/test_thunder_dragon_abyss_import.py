from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


MOD_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOD_DIR))

import import_thunder_dragon_abyss_gacha as importer  # noqa: E402
import wf_mod_tool as core  # noqa: E402


def table(logical: str, rows: list[tuple[str, bytes]]) -> bytes:
    ordered = core.OrderedMap(
        logical,
        [key for key, _row in rows],
        [row for _key, row in rows],
        Path(logical),
    )
    return core.build_orderedmap(ordered)


class OwnedRecordMergeTests(unittest.TestCase):
    def test_preserves_all_existing_raw_rows_and_appends_owned_key(self) -> None:
        logical = "master/generated/trimmed_image.orderedmap"
        base = table(
            logical,
            [
                ("official", b"0,0,100,100"),
                ("item/equipment/mod/fantasy/skill_core", b"0,0,20,20"),
            ],
        )
        incoming = table(
            logical,
            [
                ("official", b"changed-author-copy"),
                ("character/cnmod_thunder/ui/cutin", b"0,0,1024,512"),
            ],
        )

        result = importer.merge_owned_records(
            base,
            incoming,
            logical,
            ("character/cnmod_thunder/ui/cutin",),
        )
        before = core.read_orderedmap_raw_rows_from_bytes(base, logical)
        after = core.read_orderedmap_raw_rows_from_bytes(result.payload, logical)
        self.assertEqual(before.keys, after.keys[:2])
        self.assertEqual(before.rows, after.rows[:2])
        self.assertEqual(
            ["character/cnmod_thunder/ui/cutin"],
            after.keys[2:],
        )
        self.assertEqual(
            ("character/cnmod_thunder/ui/cutin",), result.added_keys
        )

    def test_new_table_contains_only_owned_outer_key(self) -> None:
        logical = "master/gacha_odds/custom.orderedmap"
        incoming = table(
            logical,
            [("custom", b"owned"), ("unrelated", b"must-not-be-imported")],
        )
        result = importer.merge_owned_records(
            None, incoming, logical, ("custom",)
        )
        merged = core.read_orderedmap_raw_rows_from_bytes(result.payload, logical)
        self.assertEqual(["custom"], merged.keys)

    def test_conflicting_existing_owned_key_is_rejected(self) -> None:
        logical = "master/item/item.orderedmap"
        base = table(logical, [("999013", b"local")])
        incoming = table(logical, [("999013", b"author")])
        with self.assertRaisesRegex(ValueError, "conflicts"):
            importer.merge_owned_records(
                base, incoming, logical, ("999013",)
            )

    def test_output_guard_rejects_cdn_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            unsafe = Path(directory) / ".cdn" / "cn"
            with self.assertRaisesRegex(ValueError, r"\.cdn"):
                importer._assert_safe_output(unsafe)


if __name__ == "__main__":
    unittest.main()
