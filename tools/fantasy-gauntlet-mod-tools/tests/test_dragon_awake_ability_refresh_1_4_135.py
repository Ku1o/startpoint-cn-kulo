from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
import zipfile


TOOL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOL_ROOT.parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import publish_dragon_awake_ability_refresh_1_4_135 as release  # noqa: E402
import wf_mod_tool as core  # noqa: E402


class DragonAwakeAbilityRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.archive_raw, cls.report, cls.entry = release.build()

    def test_archive_republishes_exact_current_terminal_table(self) -> None:
        member = release.member_name(release.ABILITY_LOGICAL)
        expected = release.read_member(release.TERMINAL_ARCHIVE, member)
        with zipfile.ZipFile(io.BytesIO(self.archive_raw)) as archive:
            self.assertEqual(archive.namelist(), [member])
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read(member), expected)
        self.assertEqual(release.sha256(expected), release.EXPECTED_TABLE_SHA256)
        self.assertEqual(self.report["archive"]["sha256"], release.sha256(self.archive_raw))

    def test_target_rows_match_approved_awakened_release(self) -> None:
        for key in release.TARGET_KEYS:
            row = self.report["target_rows"][key]
            self.assertEqual(row["official_rows"], 1)
            self.assertGreaterEqual(row["awakened_rows"], 1)
        self.assertEqual(
            self.report["verification"]["target_rows_equal_approved_1_4_94"],
            True,
        )
        self.assertEqual(self.report["verification"]["balance_values_changed"], False)

    def test_manifest_entry_is_a_real_new_version_edge(self) -> None:
        self.assertEqual(self.entry["depends_on"], "1.4.134")
        self.assertEqual(self.entry["version"], "1.4.135")
        self.assertEqual(self.entry["enabled"], True)
        self.assertEqual(self.entry["chain"], [release.ARCHIVE_NAME])
        self.assertEqual(self.entry["archive_integrity"], [self.report["archive"]])
        self.assertIn(
            json.loads(release.MANIFEST_PATH.read_text(encoding="utf-8"))["cdn_version"],
            (release.BASE_VERSION, release.TARGET_VERSION),
        )

    def test_target_rows_are_valid_ability_rows(self) -> None:
        member = release.member_name(release.ABILITY_LOGICAL)
        terminal_raw = release.read_member(release.TERMINAL_ARCHIVE, member)
        table = core.read_orderedmap_file_from_bytes(terminal_raw)
        for key in release.TARGET_KEYS:
            rows = core.read_csv_lines(table[key])
            self.assertTrue(all(len(row) == 126 for row in rows))
            self.assertEqual(sum(row[3:5] == ["1", "0"] for row in rows), 1)
            self.assertGreaterEqual(sum(row[3:5] == ["1", "1"] for row in rows), 1)


if __name__ == "__main__":
    unittest.main()
