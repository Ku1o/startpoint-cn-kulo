from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zipfile


TOOL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOL_ROOT.parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import publish_simoun_abyss_stability_1_4_93_20260830 as release  # noqa: E402
import wf_abyss_custom_position_fix as abyss_fix  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_simoun_balance as simoun  # noqa: E402


class SimounAbyssStabilityReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(release.MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.base = release.base_entry(cls.manifest)
        cls.entry = next(
            item for item in cls.manifest["patches"] if item["id"] == release.PATCH_ID
        )

    def read_member(self, archive_name: str, logical: str) -> bytes:
        with zipfile.ZipFile(release.ACTIVE_DIR / archive_name) as archive:
            return archive.read(release.member_name(logical))

    def test_manifest_advances_only_to_1_4_93_with_two_segments(self) -> None:
        self.assertEqual("1.4.93", self.manifest["cdn_version"])
        enabled = [item for item in self.manifest["patches"] if item.get("enabled")]
        self.assertEqual(release.PATCH_ID, enabled[-1]["id"])
        self.assertEqual("1.4.92", self.entry["depends_on"])
        self.assertEqual("1.4.93", self.entry["version"])
        self.assertEqual(
            [release.SIMOUN_ARCHIVE, release.ABYSS_ARCHIVE], self.entry["chain"]
        )
        self.assertFalse(any(item.get("version") == "1.4.94" for item in enabled))
        for expected in self.entry["archive_integrity"]:
            raw = (release.ACTIVE_DIR / expected["name"]).read_bytes()
            self.assertEqual(expected["size"], len(raw))
            self.assertEqual(expected["sha256"], hashlib.sha256(raw).hexdigest())

    def test_existing_1_4_92_archives_remain_byte_exact(self) -> None:
        for expected in self.base["archive_integrity"]:
            raw = (release.ACTIVE_DIR / expected["name"]).read_bytes()
            self.assertEqual(expected["size"], len(raw))
            self.assertEqual(expected["sha256"], hashlib.sha256(raw).hexdigest())

    def test_simoun_tables_change_only_the_target_row(self) -> None:
        for logical, targets in release.SIMOUN_TABLE_TARGETS.items():
            before_raw = release.latest_base_payload(self.base, logical)
            after_raw = self.read_member(release.SIMOUN_ARCHIVE, logical)
            before = core.read_orderedmap_raw_rows_from_bytes(before_raw, logical)
            after = core.read_orderedmap_raw_rows_from_bytes(after_raw, logical)
            self.assertEqual(before.keys, after.keys)
            for key, old_row, new_row in zip(before.keys, before.rows, after.rows):
                if key not in targets:
                    self.assertEqual(old_row, new_row, key)

    def test_simoun_dsls_remove_reset_and_restore_skill_point_target(self) -> None:
        for logical in release.SIMOUN_DSL_LOGICALS:
            before_raw = release.latest_base_payload(self.base, logical)
            after_raw = self.read_member(release.SIMOUN_ARCHIVE, logical)
            before = simoun._decode_skill(before_raw, logical)
            after = simoun._decode_skill(after_raw, logical)
            self.assertEqual(1, len(simoun._skill_facts(before, logical)["resets"]))
            self.assertEqual([], simoun._skill_facts(after, logical)["resets"])
            expected = copy.deepcopy(before)
            expected[11][1].remove(simoun.UNSAFE_RESET_COMMAND)
            simoun._skill_facts(expected, logical)["gauge"][1] = 20
            self.assertEqual(expected, after)
            gauge = simoun._skill_facts(after, logical)["gauge"]
            self.assertEqual(20, gauge[1])
            self.assertEqual(0.15, simoun._fixed_range(gauge[2], "技能槽"))

    def test_abyss_segment_changes_only_round_three_and_four_fields(self) -> None:
        logical = abyss_fix.FIELD_DATA_LOGICAL
        before_raw = release.latest_base_payload(self.base, logical)
        after_raw = self.read_member(release.ABYSS_ARCHIVE, logical)
        before = core.read_orderedmap_raw_rows_from_bytes(before_raw, logical)
        after = core.read_orderedmap_raw_rows_from_bytes(after_raw, logical)
        self.assertEqual(before.keys, after.keys)
        for key, old_row, new_row in zip(before.keys, before.rows, after.rows):
            if key not in abyss_fix.FIELD_FIXES:
                self.assertEqual(old_row, new_row, key)
            else:
                self.assertEqual(
                    list(abyss_fix.FIELD_FIXES[key]["after"]),
                    abyss_fix._decode_row(new_row, key),
                )

    def test_fixed_terrains_have_every_required_custom_position(self) -> None:
        raw = self.read_member(release.ABYSS_ARCHIVE, abyss_fix.FIELD_DATA_LOGICAL)
        reports = release.audit_fixed_terrains(raw)
        self.assertEqual(["mod_rogue_f3", "mod_rogue_f4"], [r["field"] for r in reports])
        for report in reports:
            positions = dict(report["target_positions"])
            for name in report["required_positions"]:
                self.assertEqual(1, positions.get(name), (report["field"], name))
            self.assertTrue(report["source_positions_equal"])


if __name__ == "__main__":
    unittest.main()
