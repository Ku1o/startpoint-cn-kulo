from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from unittest import mock


MOD_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOD_DIR))

import wf_mode15_build as mode15  # noqa: E402


class TestMode15AbyssPlan(unittest.TestCase):
    def test_schedule_stays_twelve_solo_and_three_multiplayer(self) -> None:
        plan = mode15.MODE15_ABYSS_PLAN
        self.assertEqual(15, plan["rounds"])
        self.assertEqual(list(mode15.SOLO_STAGES), plan["rules"]["solo_stages"])
        self.assertEqual(
            [5, 10, 15],
            plan["rules"]["multiplayer_stages"],
        )
        self.assertEqual(
            ["multiplayer", "multiplayer", "multiplayer"],
            [
                mode15.STAGE_BY_NUMBER[stage]["mode"]
                for stage in mode15.MULTI_STAGES
            ],
        )

    def test_character_reuse_is_enabled_for_testing(self) -> None:
        self.assertIs(
            True,
            mode15.MODE15_ABYSS_PLAN["rules"]["allow_character_reuse"],
        )
        self.assertEqual(
            3,
            mode15.MODE15_ABYSS_PLAN["rules"]["visible_party_sets"],
        )

    def test_normalized_targets_define_hp_and_bound_attack(self) -> None:
        difficulty = mode15.MODE15_ABYSS_PLAN["difficulty"]
        self.assertEqual("normalized-fantasy", difficulty["preset"])
        exempt = set(
            mode15.MODE15_ABYSS_PLAN["rules"]["hp_progression_exempt_stages"]
        )
        for config in mode15.STAGE_CONFIGS:
            if config["stage"] not in exempt:
                self.assertTrue(
                    math.isclose(
                        config["hp"],
                        config["target_effective_hp"] / config["audited_base_hp"],
                        rel_tol=5e-5,
                    )
                )
            self.assertGreater(config["atk"], 0)
            self.assertLessEqual(config["atk"], difficulty["atk_hard_ceiling"])
        self.assertLessEqual(difficulty["atk_hard_ceiling"], 8.0)

    def test_multiplayer_scale_metadata_only_marks_milestones(self) -> None:
        scales = mode15.MODE15_ABYSS_PLAN["multiplayer_hp_scale"]
        for stage, scale in ((5, 1.75), (10, 2.0), (15, 2.25)):
            config = mode15.STAGE_BY_NUMBER[stage]
            self.assertEqual(scale, scales[str(stage)])
            self.assertEqual(scale, config["multiplayer_hp_scale"])
        for stage in mode15.SOLO_STAGES:
            self.assertNotIn("multiplayer_hp_scale", mode15.STAGE_BY_NUMBER[stage])

    def test_curse_density_never_exceeds_native_five_slots(self) -> None:
        for config in mode15.STAGE_CONFIGS:
            self.assertLessEqual(len(config["conditions"]), 5)
        self.assertEqual("off", mode15.STAGE_BY_NUMBER[1]["curse_tier"])
        self.assertEqual("final", mode15.STAGE_BY_NUMBER[15]["curse_tier"])

    def test_live_absolute_hp_rebases_multiplier_without_changing_target(self) -> None:
        old = dict(mode15._ACTIVE_STAGE_HP)

        def evidence(_tables, config):
            return {
                "verified": True,
                "absolute_verified": True,
                "native_hp": float(config["stage"]) * 100_000_000.0,
                "components": (),
                "reason": None,
                "field": f"field_{config['stage']}",
                "bosses": (f"boss_{config['stage']}",),
            }

        try:
            with mock.patch.object(
                mode15, "mode15_stage_hp_evidence", side_effect=evidence
            ):
                audits = mode15.refresh_mode15_stage_hp({})
            self.assertEqual(15, len(audits))
            for config in mode15.STAGE_CONFIGS:
                expected = (
                    float(config["target_effective_hp"])
                    / (float(config["stage"]) * 100_000_000.0)
                )
                self.assertTrue(math.isclose(mode15.stage_hp(config), expected))
        finally:
            mode15._ACTIVE_STAGE_HP.clear()
            mode15._ACTIVE_STAGE_HP.update(old)

    def test_proxy_hp_cannot_drive_fantasy_multiplier(self) -> None:
        proxy = {
            "verified": True,
            "absolute_verified": False,
            "native_hp": 100.0,
            "components": (),
            "reason": None,
        }
        with (
            mock.patch.object(
                mode15, "mode15_stage_hp_evidence", return_value=proxy
            ),
            self.assertRaisesRegex(ValueError, "proxy-only"),
        ):
            mode15.refresh_mode15_stage_hp({})


if __name__ == "__main__":
    unittest.main()
