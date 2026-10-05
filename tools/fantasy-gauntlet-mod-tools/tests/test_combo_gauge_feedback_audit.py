from __future__ import annotations

import copy
import unittest
from pathlib import Path

import audit_combo_gauge_feedback as audit
import wf_mod_tool as core


class ComboGaugeFeedbackAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.audit(Path(__file__).resolve().parents[3])

    def test_character_feedback_requires_main_and_six_light_characters(self) -> None:
        report = self.report
        self.assertEqual(report["code_name"], "samurai_robot_plum")
        self.assertEqual(report["ability_id"], "1599983")
        rule = report["gauge_to_combo"]
        self.assertTrue(rule["main_only"])
        self.assertIn(
            ["2", "", "", "600000", "600000", "White", ""],
            rule["preconditions"],
        )
        self.assertEqual(rule["threshold_raw"], ["100000", "100000"])
        self.assertEqual(rule["strength_raw"], ["5000000", "10000000"])
        self.assertEqual(rule["trigger_puller"], ["0", ""])
        self.assertEqual(rule["cooldown_frames_raw"], "0")
        self.assertIn(rule["trigger_limit_raw"], ("", "(None)"))

    def test_weapon_feedback_requires_flying_and_targets_whole_party(self) -> None:
        rule = self.report["combo_to_gauge"]
        self.assertEqual(rule["preconditions"][0][0], "39")
        self.assertEqual(rule["threshold_raw"], ["3000000", "3000000"])
        self.assertEqual(rule["strength_raw"], ["2000", "10000"])
        self.assertEqual(rule["target"], ["5", "(None)"])
        self.assertEqual(rule["cooldown_frames_raw"], "0")
        self.assertIn(rule["trigger_limit_raw"], ("", "(None)"))

    def test_source_provenance_and_csv_roundtrip(self) -> None:
        self.assertIn("not live CDN", self.report["scope"])
        for source in self.report["sources"].values():
            self.assertEqual(len(source["table_sha256"]), 64)
            self.assertTrue(source["archive"].startswith("assets/asset-patch/active/"))
        for name in ("gauge_to_combo", "combo_to_gauge"):
            row = self.report[name]["raw_row"]
            self.assertEqual(core.read_csv_lines(core.write_csv_lines([row])), [row])

    def test_missing_or_duplicate_rules_fail_closed(self) -> None:
        row = self.report["gauge_to_combo"]["raw_row"]
        for rows in ([], [row, row]):
            with self.assertRaises(ValueError):
                audit.select_rule(rows, "ability", "141", "226")

    def test_during_rule_is_not_mistaken_for_instant_rule(self) -> None:
        row = copy.copy(self.report["gauge_to_combo"]["raw_row"])
        row[5] = "1"
        with self.assertRaises(ValueError):
            audit.select_rule([row], "ability", "141", "226")


if __name__ == "__main__":
    unittest.main()
