# -*- coding: utf-8 -*-
"""深渊连战活动元数据生成回归测试。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wf_rogue_build as rogue_build  # noqa: E402


class TestRushEventMetadata(unittest.TestCase):
    def test_shared_event_folder_remains_the_only_gauntlet_entry(self):
        event_list = {
            "700007": ["template"],
            "700098": ["old fantasy direct entry"],
            "700099": ["old abyss direct entry"],
        }

        actual = rogue_build.enforce_gauntlet_hub_event_list(event_list)

        self.assertIs(event_list, actual)
        self.assertEqual({"700007": ["template"]}, actual)

    def test_generated_single_player_quest_requires_rank_130(self):
        row = [f"column-{index}" for index in range(110)]
        before = list(row)

        actual = rogue_build.enforce_gauntlet_player_rank(row)

        self.assertIs(row, actual)
        self.assertEqual("130", actual[48])
        self.assertEqual(before[:48] + before[49:], actual[:48] + actual[49:])

    def test_existing_rows_in_both_gauntlet_hubs_are_repaired_to_rank_130(self):
        rows = {}
        for event_id in rogue_build.GAUNTLET_HUB_EVENT_IDS:
            row = [f"{event_id}-column-{index}" for index in range(110)]
            row[48] = "(None)"
            rows[event_id] = {"1": rogue_build.join(row, False)}
        unrelated = [f"unrelated-column-{index}" for index in range(110)]
        rows["700007"] = {"1": rogue_build.join(unrelated, False)}

        actual = rogue_build.enforce_gauntlet_quest_table_player_rank(rows)

        self.assertIs(rows, actual)
        for event_id in rogue_build.GAUNTLET_HUB_EVENT_IDS:
            self.assertEqual("130", rogue_build.cells(actual[event_id]["1"])[48])
        self.assertEqual(unrelated, rogue_build.cells(actual["700007"]["1"]))

    def test_abyss_event_always_uses_abyss_token(self):
        row = [f"column-{index}" for index in range(18)]
        row[10] = "2370007"
        before = list(row)

        actual = rogue_build.patch_event_metadata(row)

        self.assertEqual("2370099", actual[10])
        self.assertEqual(before[:10] + before[11:], actual[:10] + actual[11:])

    def test_complete_event_leaf_is_rebuilt_from_template_with_banner_only(self):
        template = [f"template-{index}" for index in range(18)]
        current = [f"foreign-{index}" for index in range(18)]
        current[3] = "custom-banner"
        current[4] = "custom-background"

        actual = rogue_build.build_event_metadata_leaf(
            rogue_build.join(template, False),
            rogue_build.join(current, False),
        )

        expected = list(template)
        expected[0] = rogue_build.EVENT_STRING_ID
        expected[1] = rogue_build.EVENT_NAME
        expected[2] = ",".join(
            (
                rogue_build.START,
                rogue_build.END,
                rogue_build.RESULT_END,
                rogue_build.EXCHANGE_END,
            )
        )
        expected[3:5] = current[3:5]
        expected[10] = rogue_build.TOKEN_ID
        expected[15] = rogue_build.START
        expected[16] = rogue_build.END
        expected[17] = rogue_build.EXCHANGE_END
        self.assertEqual([expected], [rogue_build.cells(actual)])
        self.assertIs(str, type(actual))

    def test_unscaled_hp_keeps_absolute_evidence_and_actual_value(self):
        native = {
            "verified": True,
            "absolute_verified": True,
            "native_hp": 1000.0,
            "components": [{
                "code": "standard_boss", "kind": "standard",
                "evidence_kind": "absolute", "native_hp": 1000.0,
            }],
        }

        audit = rogue_build.unscaled_floor_hp_record(
            7, native, base_duration_s=100.0, duration_s=100.0,
            curse_hp=1.0, raw_c86=2.0, target=50.0,
            scaling_error="standard c86 outside policy window",
        )

        self.assertTrue(audit["verified"])
        self.assertTrue(audit["absolute_verified"])
        self.assertTrue(audit["target_exempt"])
        self.assertEqual(2000.0, audit["true_hp"])
        self.assertEqual(20.0, audit["realized_dps"])
        records = [{"r": 1, "baseline_dps": 1.0, "warmup": True}]
        records.extend({"r": r, "baseline_dps": 50.0} for r in range(2, 7))
        records.append(audit)
        self.assertEqual([], rogue_build.hp_curve_errors(
            records, 7, last_band=(40.0, 60.0)))
        self.assertEqual([], rogue_build.hp_curve_errors(
            records, 7, last_band=(40.0, 60.0), ramp=True))

    def test_folder_preview_matches_server_fixed_rewards(self):
        template = [f"template-{index}" for index in range(37)]

        actual = rogue_build.cells(
            rogue_build.build_deep_abyss_folder_leaf(
                rogue_build.join(template, False),
            )
        )

        self.assertEqual(["1", "1", rogue_build.EVENT_NAME], actual[:3])
        self.assertEqual(["0", "99", "1500"], actual[7:10])
        self.assertEqual(["0", rogue_build.TOKEN_ID, "50"], actual[10:13])
        self.assertEqual(["0", "11003", "2"], actual[13:16])
        for base in range(16, 37, 3):
            self.assertEqual(["(None)", "", "(None)"], actual[base:base + 3])


class TestBossKindSynchronization(unittest.TestCase):
    def setUp(self):
        self.previous_special_kind = rogue_build._SPECIAL_KIND
        rogue_build._SPECIAL_KIND = {"special_enemy": 6}

    def tearDown(self):
        rogue_build._SPECIAL_KIND = self.previous_special_kind

    def test_kind_is_corrected_when_boss_table_changes(self):
        kind_of = rogue_build.zone_boss_kind_fixer(
            {"general_enemy": {}},
            {"standard_enemy": {}},
        )

        self.assertEqual(1, kind_of("general_enemy", 0))
        self.assertEqual(0, kind_of("standard_enemy", 1))
        self.assertEqual(6, kind_of("special_enemy", 1))

    def test_matching_kind_requires_no_rewrite(self):
        kind_of = rogue_build.zone_boss_kind_fixer(
            {"general_enemy": {}},
            {"standard_enemy": {}},
        )

        self.assertIsNone(kind_of("general_enemy", 1))
        self.assertIsNone(kind_of("standard_enemy", 0))
        self.assertIsNone(kind_of("special_enemy", 6))


if __name__ == "__main__":
    unittest.main()
