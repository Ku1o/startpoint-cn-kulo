from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import unittest
import zlib


TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_dsl  # noqa: E402
import wf_ginovi_balance as balance  # noqa: E402


SEGMENT_HITS = {
    ("power_flip", 1): (1, 1, 1, 1),
    ("power_flip", 2): (1, 1, 1, 1, 1, 1),
    ("power_flip", 3): (1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    ("leader_skill_followup", 1): (21, 1),
    ("leader_skill_followup", 2): (1,),
    ("leader_skill_followup", 3): (7,),
}


def numeric_range(value: float) -> dict[str, float]:
    return {"min": value, "max": value}


def normal_attack(attack_id: int, multiplier: float) -> list:
    return [
        "CreateNormalAttack",
        attack_id,
        255,
        [],
        [],
        1,
        [numeric_range(multiplier)],
        [numeric_range(0.0)],
        True,
        False,
        False,
        False,
        False,
        [numeric_range(0.0)],
        [numeric_range(0.0)],
        ["None"],
        True,
    ]


def hit_area(area_id: int, max_hits: int, multiplier: float) -> list:
    attack = normal_attack(area_id + 2, multiplier)
    return [
        "CreateHitArea",
        "*",
        -18,
        ["AB"],
        0,
        0,
        0,
        True,
        False,
        ["Circle", [numeric_range(100.0)]],
        ["Center"],
        ["Center"],
        ["Single"],
        ["SpecifyHitAreaLifetimeDirectly", 10],
        ["CalculatedUsingMaxNumOfHits", max_hits],
        ["None"],
        False,
        True,
        ["None"],
        area_id,
        ["Block", []],
        area_id + 1,
        area_id + 2,
        ["Block", [["Command", attack]]],
        0,
        0,
        ["None"],
    ]


def encode_tree(tree: list) -> bytes:
    encoded = wf_dsl.encode_amf3(tree)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(encoded) + compressor.flush()


def decode_tree(raw: bytes) -> list:
    return wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]


def payload_for(spec: balance.GinoviDamageSpec, total: float) -> bytes:
    hits = SEGMENT_HITS[(spec.family, spec.level)]
    per_hit = (total - spec.engine_base) / sum(hits)
    areas = [
        hit_area(1000 + index * 10, max_hits, per_hit)
        for index, max_hits in enumerate(hits)
    ]
    tree = [
        "ActionDsl",
        1,
        ["None"],
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        0,
        ["Block", [["Command", area] for area in areas]],
    ]
    return encode_tree(tree)


class GinoviBalanceTest(unittest.TestCase):
    def test_confirmed_targets_and_damage_types(self) -> None:
        self.assertEqual(
            {level: spec.target_total for level, spec in balance.PF_SPECS.items()},
            {1: 25.0, 2: 35.0, 3: 45.0},
        )
        self.assertEqual(
            {
                level: spec.target_total
                for level, spec in balance.LEADER_SKILL_SPECS.items()
            },
            {1: 25.0, 2: 35.0, 3: 50.0},
        )
        self.assertTrue(
            all(spec.damage_type == "power_flip" for spec in balance.PF_SPECS.values())
        )
        self.assertTrue(
            all(
                spec.damage_type == "skill"
                for spec in balance.LEADER_SKILL_SPECS.values()
            )
        )

    def test_all_current_totals_patch_to_confirmed_nonzero_values(self) -> None:
        for spec in balance.ALL_SPECS:
            current_total = spec.accepted_before_totals[0]
            with self.subTest(family=spec.family, level=spec.level):
                raw = payload_for(spec, current_total)
                patched, report = balance.patch_payload(raw, spec.logical)
                self.assertTrue(report["target_total"] > 0)
                self.assertTrue(report["per_hit"] > 0)
                self.assertTrue(
                    math.isclose(
                        report["target_total"],
                        spec.target_total,
                        rel_tol=0.0,
                        abs_tol=1e-9,
                    )
                )
                repatched, second = balance.patch_payload(patched, spec.logical)
                self.assertEqual(repatched, patched)
                self.assertFalse(second["changed"])

    def test_only_attack_multiplier_ranges_change(self) -> None:
        spec = balance.LEADER_SKILL_SPECS[1]
        raw = payload_for(spec, 60.0)
        before = decode_tree(raw)
        patched, _ = balance.patch_payload(raw, spec.logical)
        after = decode_tree(patched)

        expected = copy.deepcopy(before)
        per_hit = spec.target_total / spec.expected_weighted_hits
        for node in balance._walk(expected):
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack":
                node[6][0]["min"] = per_hit
                node[6][0]["max"] = per_hit
        self.assertEqual(after, expected)

    def test_rejects_unreviewed_multiplier_drift(self) -> None:
        spec = balance.PF_SPECS[3]
        raw = payload_for(spec, 999.0)
        with self.assertRaisesRegex(ValueError, "当前总倍率"):
            balance.patch_payload(raw, spec.logical)

    def test_batch_requires_all_six_payloads(self) -> None:
        with self.assertRaisesRegex(ValueError, "缺少基诺维倍率 payload"):
            balance.patch_payloads({})


if __name__ == "__main__":
    unittest.main()
