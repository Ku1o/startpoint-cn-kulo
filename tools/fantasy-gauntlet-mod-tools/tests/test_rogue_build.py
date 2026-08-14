# -*- coding: utf-8 -*-
"""深渊连战活动元数据生成回归测试。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wf_rogue_build as rogue_build  # noqa: E402


class TestRushEventMetadata(unittest.TestCase):
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
