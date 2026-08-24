from __future__ import annotations

import sys
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOD_DIR))

import wf_mode15_build as mode15  # noqa: E402


def blank_row(size: int) -> list[str]:
    return [""] * size


class TestMode15Progression(unittest.TestCase):
    def test_multiplayer_quest_sets_keep_published_identifiers(self) -> None:
        table = {"template": mode15.join(blank_row(6), False)}
        rows = mode15.build_mode15_quest_sets(table)
        self.assertEqual(
            ["mod_fifteen_stage_boss_5", "6", "300098", "", "1", "300098001"],
            mode15.cells(rows[str(mode15.MULTI_QUEST_SET_5_ID)]),
        )
        self.assertEqual(
            ["mod_fifteen_stage_boss_10", "6", "300098", "", "2", "300098002"],
            mode15.cells(rows[str(mode15.MULTI_QUEST_SET_10_ID)]),
        )

    def test_legacy_event_folder_rows_match_current_carriers(self) -> None:
        table = {"1": {"1": mode15.join(["13", "1001", "1"], False)}}
        rows = mode15.build_event_folder_events(table)
        self.assertEqual(["11", "700098", "2"], mode15.cells(rows["1"]))
        self.assertEqual(["0", "300098", "1"], mode15.cells(rows["2"]))

    def test_rush_is_published_directly_in_event_list(self) -> None:
        self.assertIn("event_list", mode15.PUBLISH_TABLES)
        self.assertEqual(700098, mode15.RUSH_EVENT_ID)
        self.assertEqual(700099, mode15.HIDDEN_DEEP_ABYSS_EVENT_ID)

    def test_retired_carriers_are_part_of_forward_cleanup(self) -> None:
        self.assertIn("hard_multi_event", mode15.PUBLISH_TABLES)
        self.assertIn("carnival_event", mode15.PUBLISH_TABLES)
        self.assertNotEqual(mode15.LEGACY_HARD_MULTI_EVENT_ID, mode15.MULTI_EVENT_ID)


if __name__ == "__main__":
    unittest.main()
