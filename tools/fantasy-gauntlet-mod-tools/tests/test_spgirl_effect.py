from __future__ import annotations

import copy
import json
import sys
import unittest
import zlib
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import wf_dsl  # noqa: E402
from wf_spgirl_effect import (  # noqa: E402
    EXPECTED_COMPILED_SHA256,
    POOL_SAFE_CAPACITY_CHANGES,
    POOL_SAFE_COMPILED_SHA256,
    REPLACEMENT_CELLS,
    SAFE_COMPILED_SHA256,
    SKILL_DSL_LOGICALS,
    SOURCE_EFFECT_REFERENCE,
    TARGET_EFFECT_REFERENCE,
    SpgirlEffectError,
    patch_skill_effect_reference,
    validate_confirmed_report,
    validate_runtime_safe_candidate,
)


def raw_deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(level=9, wbits=-15)
    return compressor.compress(data) + compressor.flush()


def confirmed_report() -> dict:
    return {
        "mode": "offline-candidate-only",
        "writes_live": False,
        "source_reference": SOURCE_EFFECT_REFERENCE,
        "target_reference": TARGET_EFFECT_REFERENCE,
        "atlas_records": 25,
        "replaced_cells": list(REPLACEMENT_CELLS),
        "anchor_metadata_preserved": True,
        "timeline_plain_bytes_identical": True,
        "visual_layout": {
            "kind": "narrow-x-trail",
            "scope": "isolated-character-trail",
            "branch_count": 2,
            "half_angle_degrees": 15.0,
            "top_bottom_included_angle_degrees": 30.0,
            "target_group": 21,
            "parent_group": 2,
            "matrix_indices": [703, 704],
            "sound_instances": 1,
            "central_effect_instances": 1,
            "gameplay_geometry_changed": False,
        },
        "compiled": [
            {"logical": logical, "sha256": digest}
            for logical, digest in EXPECTED_COMPILED_SHA256.items()
        ],
        "action_dsl": [
            {
                "file": f"{level}.action.dsl.amf3.deflate",
                "replacements": 1,
                "sha256": str(level) * 64,
            }
            for level in (1, 2, 3)
        ],
    }


class SpgirlEffectTests(unittest.TestCase):
    def test_patch_skill_effect_reference_changes_exactly_one_reference(self):
        tree = ["Command", ["ShowEffect", SOURCE_EFFECT_REFERENCE, ["untouched"]]]
        payload = raw_deflate(wf_dsl.encode_amf3(tree))
        output, report = patch_skill_effect_reference(payload, SKILL_DSL_LOGICALS[3])
        decoded = wf_dsl.parse_dsl(zlib.decompress(output, -15))["tree"]
        self.assertEqual(
            decoded,
            ["Command", ["ShowEffect", TARGET_EFFECT_REFERENCE, ["untouched"]]],
        )
        self.assertEqual(report["level"], 3)
        self.assertEqual(report["replacements"], 1)
        self.assertFalse(report["gameplay_geometry_changed"])
        self.assertFalse(report["writes_live"])

    def test_patch_rejects_unrelated_dsl(self):
        payload = raw_deflate(wf_dsl.encode_amf3(["Command"]))
        with self.assertRaisesRegex(SpgirlEffectError, "不是149996主动技"):
            patch_skill_effect_reference(payload, "battle/action/unrelated")

    def test_confirmed_report_accepts_locked_x_layout(self):
        validate_confirmed_report(confirmed_report())

    def test_confirmed_report_rejects_angle_drift(self):
        report = copy.deepcopy(confirmed_report())
        report["visual_layout"]["half_angle_degrees"] = 20.0
        with self.assertRaisesRegex(SpgirlEffectError, "窄X布局漂移"):
            validate_confirmed_report(report)

    def test_confirmed_report_rejects_compiled_resource_drift(self):
        report = copy.deepcopy(confirmed_report())
        report["compiled"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(SpgirlEffectError, "编译资源哈希漂移"):
            validate_confirmed_report(report)

    def test_runtime_safe_candidate_keeps_original_parts_topology(self):
        report = {
            "mode": "offline-candidate-only",
            "writes_live": False,
            "source_reference": SOURCE_EFFECT_REFERENCE,
            "target_reference": TARGET_EFFECT_REFERENCE,
            "atlas_records": 25,
            "replaced_cells": list(REPLACEMENT_CELLS),
            "anchor_metadata_preserved": True,
            "timeline_plain_bytes_identical": True,
            "visual_layout": {
                "kind": "baked-raster-x",
                "scope": "atlas-cells",
                "visual_branch_count": 2,
                "runtime_branch_count": 1,
                "half_angle_degrees": 15.0,
                "top_bottom_included_angle_degrees": 30.0,
                "baked_terminals": ["w"],
                "parts_topology_unchanged": True,
                "groups_added": 0,
                "segments_added": 0,
                "matrices_added": 0,
                "sound_instances": 1,
                "central_effect_instances": 1,
                "gameplay_geometry_changed": False,
                "cells": [],
            },
            "action_dsl": [],
            "compiled": [
                {"logical": logical, "sha256": digest}
                for logical, digest in SAFE_COMPILED_SHA256.items()
            ],
        }
        source_prefix = "battle/effect/skill_unique/wind_spgirl/.gen/wind_spgirl"
        target_prefix = "battle/effect/skill_unique/wind_spgirl_swim/.gen/wind_spgirl_swim"
        source_parts = {
            "g": [{"s": []}],
            "t": [],
            "i": [{"p": source_prefix + "/w"}],
        }
        target_parts = copy.deepcopy(source_parts)
        target_parts["i"][0]["p"] = target_prefix + "/w"
        topology = validate_runtime_safe_candidate(
            report,
            source_parts=source_parts,
            target_parts=target_parts,
        )
        self.assertEqual(topology["groups"], 1)
        self.assertEqual(topology["segments"], 0)
        self.assertEqual(topology["matrices"], 0)

    def test_machine_readable_recipe_matches_locked_source_rule(self):
        recipe = json.loads(
            (TOOLS / "examples" / "149996_active_skill_effect.recipe.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(recipe["character_id"], "149996")
        self.assertEqual(recipe["status"], "offline_verified_device_pending")
        self.assertEqual(
            recipe["source"]["effect_reference"], SOURCE_EFFECT_REFERENCE
        )
        self.assertEqual(
            recipe["target"]["effect_reference"], TARGET_EFFECT_REFERENCE
        )
        self.assertEqual(
            tuple(recipe["source"]["replacement_cells"]), REPLACEMENT_CELLS
        )
        self.assertEqual(recipe["target"]["layout"]["kind"], "baked-raster-x")
        self.assertEqual(recipe["target"]["layout"]["runtime_branches"], 1)
        self.assertEqual(recipe["target"]["layout"]["baked_cells"], ["w"])
        self.assertEqual(recipe["target"]["layout"]["included_angle_degrees"], 30.0)
        self.assertFalse(
            recipe["target"]["layout"]["gameplay_geometry_changed"]
        )

    def test_full_x_pool_recipe_preserves_failure_and_fix_evidence(self):
        recipe = json.loads(
            (
                TOOLS
                / "examples"
                / "149996_active_skill_effect_full_x_pool.recipe.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(recipe["character_id"], "149996")
        self.assertEqual(recipe["status"], "offline_verified_device_pending")
        self.assertEqual(
            recipe["incident"]["stack_entry"],
            "flatomo.animation.parts::PartsAnimationImageElement/fetchDisplayObject()",
        )
        self.assertEqual(recipe["target"]["layout"]["runtime_branches"], 2)
        self.assertEqual(recipe["target"]["layout"]["segments"], 226)
        self.assertEqual(recipe["target"]["layout"]["matrices"], 705)
        self.assertEqual(
            {
                terminal: tuple(values)
                for terminal, values in recipe["target"]["object_pool"][
                    "changes"
                ].items()
            },
            POOL_SAFE_CAPACITY_CHANGES,
        )
        self.assertEqual(
            recipe["target"]["compiled_sha256"],
            POOL_SAFE_COMPILED_SHA256,
        )
        self.assertTrue(recipe["release_policy"]["keep_baked_fallback"])
        self.assertEqual(
            recipe["current_result"]["device_smoke_test"],
            "user_confirmed_good",
        )


if __name__ == "__main__":
    unittest.main()
