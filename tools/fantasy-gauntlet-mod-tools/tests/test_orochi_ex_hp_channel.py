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
import wf_rogue_bundle as rbb  # noqa: E402


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

    def test_incident_phase3_overflow_reproduces_negative_icon_threshold(self) -> None:
        incident = {
            "mod_rogue_orochi_ex24": {
                "100": leaf(parent_row(1_914_595_756, 3_063_353_210)),
            },
        }
        with self.assertRaisesRegex(
                channel.OrochiExHpError, "signed int32 HP range"):
            channel.read_fixed_phase_hp(
                incident, "mod_rogue_orochi_ex24", 100)

        wrapped_phase3 = 3_063_353_210 - 2 ** 32
        middle = 1_236_336_747.684847
        wrapped_total = 1_914_595_756 + middle + wrapped_phase3
        wrapped_phase2_threshold = wrapped_phase3 / wrapped_total
        self.assertEqual(wrapped_phase3, -1_231_614_086)
        self.assertLess(wrapped_phase2_threshold, 0)
        self.assertLess(int(wrapped_phase2_threshold * 100), 0)

    def test_builder_rejects_int32_overflow_without_mutating_either_table(self) -> None:
        before_dedicated = copy.deepcopy(self.dedicated)
        before_levels = copy.deepcopy(self.levels)
        with self.assertRaisesRegex(
                channel.OrochiExHpError, "signed int32 HP range"):
            channel.build_scaled_hp_rows(
                self.dedicated, self.levels,
                "orochi_ex", "orochi_ex_overflow",
                fixed_phase_scale=30.0, middle_scale=1.0,
            )
        self.assertEqual(self.dedicated, before_dedicated)
        self.assertEqual(self.levels, before_levels)

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

    def test_builder_keeps_fractional_middle_coefficient_for_strict_readback(self) -> None:
        _node, level, _report = channel.build_scaled_hp_rows(
            self.dedicated, self.levels, "orochi_ex", "orochi_ex_fractional",
            fixed_phase_scale=1.0, middle_scale=1.234567,
        )
        self.assertEqual(core.read_csv_lines(level)[0][2], "308.64175")

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

    def test_full_parent_six_head_clone_is_atomic_and_hits_three_phase_target(self) -> None:
        parent = parent_row()
        for index, code in zip(
                rogue.OROCHI_EX_CHILD_COLUMNS,
                rogue.OROCHI_EX_CANONICAL_HEADS):
            parent[index] = code
        dedicated = {"orochi_ex": {"100": leaf(parent)}}
        heads = {
            code: {"100": leaf([""] * 179)}
            for code in rogue.OROCHI_EX_CANONICAL_HEADS
        }
        levels = {"orochi_ex": leaf(level_row())}
        levels.update({
            code: leaf(level_row(100 + ordinal))
            for ordinal, code in enumerate(
                rogue.OROCHI_EX_CANONICAL_HEADS, start=1)
        })
        bundle = rbb.NativeBossBundle(
            family_id="orochi-ex", family_name="八岐大蛇 EX",
            variant_id="orochi-ex-v", variant_name="official_three_phase",
            source_field="multi_normal_1_20_4",
            source_zone="multi_normal_1_20_4",
            terrain_logical="battle/field/orochi_ex.terrain.amf3.deflate",
            active_layers=("0",),
            slots=(rbb.ActiveBossSlot(
                "0", 1, 0, rbb.BossRef(4, "orochi_ex"),
                rbb.BossRef(4, "orochi_ex")),),
            bgm=None, thumbnail="", source_category="test",
            selected_levels=(("0", 1, 100),),
        )
        tables = {
            "orochi_ex": dedicated,
            "orochi_ex_head": heads,
            "boss_level": levels,
        }
        before = copy.deepcopy(tables)

        def true_stat(code, _kind, _level, boss_level):
            return float(core.read_csv_lines(boss_level[code])[0][2]) * 10.0, "*"

        def stats(boss_level):
            return {
                code: {"hpc": "hit_hp_boss", "hp_mode": "hit"}
                for code in boss_level
            }

        with (
            mock.patch.object(rogue, "true_stat", side_effect=true_stat),
            mock.patch.object(rogue, "boss_base_stats", side_effect=stats),
            mock.patch.object(rogue, "curve_value", return_value=1.0),
        ):
            native = rogue.orochi_ex_native_hp_evidence(bundle, 100, tables)
            self.assertTrue(native["verified"], native)
            baseline_target = float(native["native_hp"]) * 2.0
            final_target = baseline_target * 1.25
            plan = rogue.orochi_ex_hp_scale_plan(
                native, dedicated, levels,
                target_hp=baseline_target, curse_hp=1.25)
            result = rogue.clone_orochi_ex_parent_bundle(
                bundle, 12, plan["final_fixed_phase_scale"], tables,
                middle_scale=plan["final_middle_scale"])
            self.assertTrue(result.ok, result)
            self.assertEqual(result.parent_code, "mod_rogue_orochi_ex12")
            self.assertEqual(result.head_codes, tuple(
                f"mod_rogue_orochi_ex12_head{i}" for i in range(1, 7)))
            cloned_parent = core.read_csv_lines(
                dedicated[result.parent_code]["100"])[0]
            self.assertEqual(
                tuple(cloned_parent[index]
                      for index in rogue.OROCHI_EX_CHILD_COLUMNS),
                result.head_codes)
            for source_code, target_code in zip(
                    rogue.OROCHI_EX_CANONICAL_HEADS, result.head_codes):
                self.assertEqual(heads[target_code], heads[source_code])
                self.assertEqual(levels[target_code], levels[source_code])
            readback = rogue.orochi_ex_native_hp_evidence(
                result.bundle, 100, tables)
            receipt = rogue.build_hp_adaptation_audit(
                12, native, family="orochi_ex", channel="special_bundle",
                destination=plan["destinations"],
                baseline_target_hp=baseline_target,
                final_target_hp=final_target,
                baseline_c86=1.0, final_c86=1.0,
                readback_native=readback,
                baseline_component_hp=plan["baseline_component_hp"],
            )
            self.assertTrue(receipt.within_tolerance, receipt)
            self.assertLess(abs(receipt.final_error_hp), 1.0)
            self.assertTrue(
                result.evidence["clone_semantics"]["static_verified"])
            self.assertFalse(
                result.evidence["clone_semantics"]["gameplay_verified"])

        for table_name, original in before.items():
            for code, value in original.items():
                self.assertEqual(tables[table_name][code], value)

        malformed = copy.deepcopy(before)
        malformed["orochi_ex_head"][
            rogue.OROCHI_EX_CANONICAL_HEADS[-1]]["100"] = "short"
        malformed_before = copy.deepcopy(malformed)
        rejected = rogue.clone_orochi_ex_parent_bundle(
            bundle, 13, 2.0, malformed)
        self.assertFalse(rejected.ok)
        self.assertEqual(malformed, malformed_before)

        tampered = copy.deepcopy(before)
        tampered_before = copy.deepcopy(tampered)
        original_builder = channel.build_scaled_hp_rows

        def tamper_non_hp_column(*args, **kwargs):
            node, level, report = original_builder(*args, **kwargs)
            row = core.read_csv_lines(node["100"])[0]
            row[0] = "unexpected_phase_or_wait_drift"
            node["100"] = leaf(row)
            return node, level, report

        with mock.patch.object(
                channel, "build_scaled_hp_rows",
                side_effect=tamper_non_hp_column):
            rejected = rogue.clone_orochi_ex_parent_bundle(
                bundle, 14, 2.0, tampered)
        self.assertFalse(rejected.ok)
        self.assertIn("non-HP/child topology drift", rejected.detail)
        self.assertEqual(tampered, tampered_before)

    def test_high_target_uses_int32_capped_fixed_bars_and_middle_remainder(self) -> None:
        parent = parent_row()
        for index, code in zip(
                rogue.OROCHI_EX_CHILD_COLUMNS,
                rogue.OROCHI_EX_CANONICAL_HEADS):
            parent[index] = code
        dedicated = {"orochi_ex": {"100": leaf(parent)}}
        heads = {
            code: {"100": leaf([""] * 179)}
            for code in rogue.OROCHI_EX_CANONICAL_HEADS
        }
        levels = {"orochi_ex": leaf(level_row())}
        levels.update({
            code: leaf(level_row(100 + ordinal))
            for ordinal, code in enumerate(
                rogue.OROCHI_EX_CANONICAL_HEADS, start=1)
        })
        bundle = rbb.NativeBossBundle(
            family_id="orochi-ex", family_name="八岐大蛇 EX",
            variant_id="orochi-ex-v", variant_name="official_three_phase",
            source_field="multi_normal_1_20_4",
            source_zone="multi_normal_1_20_4",
            terrain_logical="battle/field/orochi_ex.terrain.amf3.deflate",
            active_layers=("0",),
            slots=(rbb.ActiveBossSlot(
                "0", 1, 0, rbb.BossRef(4, "orochi_ex"),
                rbb.BossRef(4, "orochi_ex")),),
            bgm=None, thumbnail="", source_category="test",
            selected_levels=(("0", 1, 100),),
        )
        tables = {
            "orochi_ex": dedicated,
            "orochi_ex_head": heads,
            "boss_level": levels,
        }

        def true_stat(code, _kind, _level, boss_level):
            return float(core.read_csv_lines(boss_level[code])[0][2]) * 10.0, "*"

        def stats(boss_level):
            return {
                code: {"hpc": "hit_hp_boss", "hp_mode": "hit"}
                for code in boss_level
            }

        baseline_target = 12_428_571_428.571428
        final_target = baseline_target * 0.5
        with (
            mock.patch.object(rogue, "true_stat", side_effect=true_stat),
            mock.patch.object(rogue, "boss_base_stats", side_effect=stats),
            mock.patch.object(rogue, "curve_value", return_value=1.0),
        ):
            native = rogue.orochi_ex_native_hp_evidence(bundle, 100, tables)
            plan = rogue.orochi_ex_hp_scale_plan(
                native, dedicated, levels,
                target_hp=baseline_target, curse_hp=0.5)
            result = rogue.clone_orochi_ex_parent_bundle(
                bundle, 24, plan["final_fixed_phase_scale"], tables,
                middle_scale=plan["final_middle_scale"])
            self.assertTrue(result.ok, result)
            readback = rogue.orochi_ex_native_hp_evidence(
                result.bundle, 100, tables)

        self.assertTrue(plan["baseline_fixed_phase_int32_capped"])
        self.assertTrue(plan["final_fixed_phase_int32_capped"])
        self.assertNotEqual(
            plan["final_fixed_phase_scale"], plan["final_middle_scale"])
        self.assertLessEqual(
            max(plan["final_component_hp"][0],
                plan["final_component_hp"][2]),
            channel.CLIENT_SIGNED_INT_MAX)
        self.assertLess(abs(plan["baseline_true_hp"] - baseline_target), 1.0)
        self.assertLess(abs(plan["true_hp"] - final_target), 1.0)
        self.assertLess(abs(float(readback["native_hp"]) - final_target), 1.0)
        contract = readback["phase_threshold_contract"]
        self.assertTrue(contract["static_verified"])
        self.assertTrue(all(0 <= value <= 99
                            for value in contract["icon_numbers"]))
        self.assertFalse(contract["gameplay_verified"])

        phase_safety = {
            "baseline": plan["baseline_phase_threshold_contract"],
            "final": plan["final_phase_threshold_contract"],
            "baseline_fixed_phase_scale": plan["baseline_fixed_phase_scale"],
            "baseline_middle_scale": plan["baseline_middle_scale"],
            "final_fixed_phase_scale": plan["final_fixed_phase_scale"],
            "final_middle_scale": plan["final_middle_scale"],
            "max_safe_fixed_phase_scale": plan["max_safe_fixed_phase_scale"],
            "baseline_fixed_phase_int32_capped": (
                plan["baseline_fixed_phase_int32_capped"]),
            "final_fixed_phase_int32_capped": (
                plan["final_fixed_phase_int32_capped"]),
            "clone_semantics": result.evidence["clone_semantics"],
            "static_verified": True,
            "runtime_simulated": False,
            "gameplay_verified": False,
        }
        adapter = {
            "components": [
                {
                    "baseline_readback_hp": baseline,
                    "final_readback_hp": final,
                }
                for baseline, final in zip(
                    plan["baseline_component_hp"],
                    plan["final_component_hp"])
            ],
            "phase_safety": phase_safety,
        }
        self.assertEqual(
            [], rogue._verify_orochi_ex_phase_safety_receipt(
                "第24战", adapter))
        tampered_adapter = copy.deepcopy(adapter)
        tampered_adapter["phase_safety"]["final"]["phase3_hp"] = (
            channel.CLIENT_SIGNED_INT_MAX + 1)
        self.assertTrue(any(
            "signed int32" in error or "三阶段回读不一致" in error
            for error in rogue._verify_orochi_ex_phase_safety_receipt(
                "第24战", tampered_adapter)))


if __name__ == "__main__":
    unittest.main()
