import copy
import sys
import unittest
from pathlib import Path
from unittest import mock


MOD_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOD_DIR))

import wf_mod_tool as core  # noqa: E402
import wf_orochi_ex as channel  # noqa: E402
import wf_rogue_build as rogue  # noqa: E402


def leaf(row: list[str]) -> str:
    return core.write_csv_lines([row])


def parent_row(phase1: int = 75_000_000, phase3: int = 120_000_000) -> list[str]:
    row = [""] * channel.PARENT_COLUMNS
    row[channel.PHASE1_HP_COLUMN] = str(phase1)
    row[channel.PHASE3_HP_COLUMN] = str(phase3)
    return row


def level_row(c2: int = 250) -> list[str]:
    row = [""] * channel.BOSS_LEVEL_COLUMNS
    row[0] = "0"
    row[1] = "hit_hp_basic_normal"
    row[2] = str(c2)
    row[3] = "1"
    row[4] = "hit_hp_boss"
    row[7] = "atk_basic_normal"
    row[8] = "60"
    row[9] = "1"
    row[10] = "atk_multi"
    row[11] = "tp_normal"
    row[12] = "120"
    return row


class TestOrochiExHpChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.dedicated = {"orochi_ex": {"100": leaf(parent_row())}}
        self.levels = {"orochi_ex": leaf(level_row())}

    def test_reader_selects_level_ceiling_and_exposes_both_fixed_bars(self) -> None:
        got = channel.read_fixed_phase_hp(self.dedicated, "orochi_ex", 80)
        self.assertEqual(got.selected_level, 100)
        self.assertEqual(got.phase1_hp, 75_000_000)
        self.assertEqual(got.phase3_hp, 120_000_000)
        self.assertEqual(got.total, 195_000_000)

    def test_reader_fails_closed_when_no_level_can_be_selected(self) -> None:
        with self.assertRaisesRegex(channel.OrochiExHpError, "no dedicated row"):
            channel.read_fixed_phase_hp(self.dedicated, "orochi_ex", 101)

    def test_builder_scales_fixed_and_middle_channels_without_mutating_source(self) -> None:
        before_dedicated = copy.deepcopy(self.dedicated)
        before_levels = copy.deepcopy(self.levels)
        node, level, report = channel.build_scaled_hp_rows(
            self.dedicated, self.levels, "orochi_ex", "orochi_ex_high",
            fixed_phase_scale=1.4, middle_scale=1.2,
        )
        scaled = core.read_csv_lines(node["100"])[0]
        scaled_level = core.read_csv_lines(level)[0]
        self.assertEqual(scaled[24:26], ["105000000", "168000000"])
        self.assertEqual(scaled_level[2], "300")
        self.assertEqual(report["phase_hp_after"]["100"], (105_000_000, 168_000_000))
        self.assertEqual(self.dedicated, before_dedicated)
        self.assertEqual(self.levels, before_levels)

    def test_replace_validates_both_tables_before_installing_either(self) -> None:
        before = copy.deepcopy(self.dedicated)
        with self.assertRaises(channel.OrochiExHpError):
            channel.replace_hp_profile(
                self.dedicated, {"orochi_ex": "broken"}, "orochi_ex",
                fixed_phase_scale=2, middle_scale=2,
            )
        self.assertEqual(self.dedicated, before)

    def test_general_hp_evidence_keeps_fixed_phases_outside_quest_multiplier(self) -> None:
        high = {"orochi_ex_high": {"100": leaf(parent_row(105_000_000, 168_000_000))}}
        levels = {"orochi_ex_high": leaf(level_row(300))}
        stats = {"orochi_ex_high": {"hpc": "hit_hp_boss", "hp_mode": "hit"}}
        with (
            mock.patch.object(rogue, "true_stat", return_value=(100.0, "*")),
            mock.patch.object(rogue, "boss_base_stats", return_value=stats),
            mock.patch.object(rogue, "curve_value", return_value=1.0),
        ):
            got = rogue.floor_native_hp(
                ["orochi_ex_high"], 90, standard_boss={},
                boss_level=levels, orochi_ex=high,
            )
        self.assertTrue(got["verified"], got.get("reason"))
        self.assertTrue(got["absolute_verified"])
        self.assertEqual([part["phase"] for part in got["components"]], [1, 2, 3])
        self.assertEqual(
            [part["apply_quest_hp_correction"] for part in got["components"]],
            [False, True, False],
        )
        self.assertEqual(got["native_hp"], 273_236_250.0)
        self.assertEqual(rogue._true_hp_at_c86(got, 2.0), 273_472_500.0)


if __name__ == "__main__":
    unittest.main()
