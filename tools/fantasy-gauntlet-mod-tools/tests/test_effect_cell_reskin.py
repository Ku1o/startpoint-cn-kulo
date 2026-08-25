from __future__ import annotations

import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image


TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import wf_assets  # noqa: E402
import wf_dsl  # noqa: E402
from wf_effect_cell_reskin import (  # noqa: E402
    ReskinError,
    _safe_output,
    apply_interleaved_trail_x_layout,
    apply_pool_safe_trail_x_layout,
    apply_root_x_layout,
    apply_trail_x_layout,
    clone_reskin,
    rewrite_action_dsl,
)


def raw_deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(level=9, wbits=-15)
    return compressor.compress(data) + compressor.flush()


class EffectCellReskinTests(unittest.TestCase):
    def fixture(self):
        sheet = Image.new("RGBA", (12, 6), (0, 0, 0, 0))
        red = Image.new("RGBA", (3, 4), (255, 0, 0, 255))
        blue = Image.new("RGBA", (4, 3), (0, 0, 255, 255))
        sheet.alpha_composite(red, (1, 1))
        sheet.alpha_composite(blue.transpose(Image.Transpose.ROTATE_270), (6, 1))
        prefix = "battle/effect/skill_unique/source/.gen/source"
        atlas = [
            {"n": f"{prefix}/a", "x": 1, "y": 1, "w": 3, "h": 4, "fx": -1, "fy": -1, "fw": 8, "fh": 8},
            {"n": f"{prefix}/b", "x": 6, "y": 1, "w": 3, "h": 4, "r": True, "fx": -2, "fy": -1, "fw": 8, "fh": 8},
        ]
        parts = {
            "i": [{"s": False, "p": f"{prefix}/a"}, {"s": False, "p": f"{prefix}/b"}],
            "g": [], "m": [], "a": [], "o": [], "t": [], "c": [], "s": 1,
        }
        timeline = {
            "sequences": [{"begin": 1, "end": 2, "name": "neutral", "kind": "once"}],
            "sounds": [{"path": "sound_effect/wind/test", "begin": 2}],
            "points": [], "circles": [], "rectangles": [], "matrices": [],
        }
        return sheet, atlas, parts, timeline

    def test_clone_changes_only_requested_cell_and_namespace(self):
        sheet, atlas, parts, timeline = self.fixture()
        green = Image.new("RGBA", (2, 2), (0, 255, 0, 255))
        target = "battle/effect/skill_unique/target/target"
        result = clone_reskin(
            source_sheet=sheet,
            source_atlas=atlas,
            source_parts=parts,
            source_timeline=timeline,
            replacements={"b": green},
            target_reference=target,
        )
        self.assertEqual(result["replaced"], ["b"])
        self.assertEqual(result["unchanged"], ["a"])
        self.assertEqual(result["cells"]["a"].tobytes(), result["original_cells"]["a"].tobytes())
        self.assertEqual(result["cells"]["b"].tobytes(), green.tobytes())
        self.assertEqual(
            result["parts"]["i"],
            [
                {"s": False, "p": "battle/effect/skill_unique/target/.gen/target/a"},
                {"s": False, "p": "battle/effect/skill_unique/target/.gen/target/b"},
            ],
        )
        new_b = result["atlas"][1]
        self.assertEqual({key: new_b[key] for key in ("fx", "fy", "fw", "fh")}, {"fx": -2, "fy": -1, "fw": 8, "fh": 8})
        self.assertNotIn("r", new_b)
        self.assertEqual(result["timeline"], timeline)
        encoded_png = result["compiled"][target + ".png"]
        self.assertTrue(wf_assets.png_decode(encoded_png).startswith(wf_assets.PNG_REAL))

    def test_replacement_must_fit_existing_logical_frame(self):
        sheet, atlas, parts, timeline = self.fixture()
        with self.assertRaisesRegex(ReskinError, "does not fit"):
            clone_reskin(
                source_sheet=sheet,
                source_atlas=atlas,
                source_parts=parts,
                source_timeline=timeline,
                replacements={"a": Image.new("RGBA", (8, 8), (1, 2, 3, 255))},
                target_reference="battle/effect/skill_unique/target/target",
            )

    def test_baked_x_preserves_runtime_parts_topology(self):
        sheet, atlas, parts, timeline = self.fixture()
        atlas[1]["fx"] = -3
        atlas[1]["fy"] = -3
        green = Image.new("RGBA", (2, 2), (0, 255, 0, 255))
        result = clone_reskin(
            source_sheet=sheet,
            source_atlas=atlas,
            source_parts=parts,
            source_timeline=timeline,
            replacements={"b": green},
            target_reference="battle/effect/skill_unique/target/target",
            x_half_angle_degrees=15,
            x_layout_scope="baked",
            x_baked_terminals={"b"},
        )
        self.assertEqual(result["parts"]["g"], parts["g"])
        self.assertEqual(result["parts"]["t"], parts["t"])
        self.assertEqual(result["layout"]["visual_branch_count"], 2)
        self.assertEqual(result["layout"]["runtime_branch_count"], 1)
        self.assertEqual(result["layout"]["groups_added"], 0)
        self.assertEqual(result["layout"]["segments_added"], 0)
        self.assertEqual(result["layout"]["matrices_added"], 0)
        self.assertEqual(result["layout"]["baked_terminals"], ["b"])
        self.assertGreaterEqual(result["cells"]["b"].width, green.width)
        self.assertGreaterEqual(result["cells"]["b"].height, green.height)

    def test_baked_x_rejects_cell_outside_replacements(self):
        sheet, atlas, parts, timeline = self.fixture()
        with self.assertRaisesRegex(ReskinError, "must be replacement cells"):
            clone_reskin(
                source_sheet=sheet,
                source_atlas=atlas,
                source_parts=parts,
                source_timeline=timeline,
                replacements={"b": Image.new("RGBA", (2, 2), (0, 255, 0, 255))},
                target_reference="battle/effect/skill_unique/target/target",
                x_half_angle_degrees=15,
                x_layout_scope="baked",
                x_baked_terminals={"a"},
            )

    def test_rewrite_action_dsl_requires_exactly_one_reference(self):
        old = "battle/effect/skill_unique/source/source"
        new = "battle/effect/skill_unique/target/target"
        tree = ["Command", ["ShowEffect", old, ["untouched"]]]
        payload = raw_deflate(wf_dsl.encode_amf3(tree))
        rewritten, count = rewrite_action_dsl(payload, source_reference=old, target_reference=new)
        self.assertEqual(count, 1)
        decoded = wf_dsl.parse_dsl(zlib.decompress(rewritten, -15))["tree"]
        self.assertEqual(decoded, ["Command", ["ShowEffect", new, ["untouched"]]])
        with self.assertRaisesRegex(ReskinError, "found 0"):
            rewrite_action_dsl(payload, source_reference="absent", target_reference=new)

    def test_runtime_like_output_is_rejected(self):
        with self.assertRaisesRegex(ReskinError, "must not"):
            _safe_output(Path("F:/startpoint-cn-main/.cdn/cn/candidate"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(_safe_output(Path(temp)), Path(temp).resolve())

    def test_root_x_layout_duplicates_only_the_identity_root(self):
        parts = {
            "g": [
                {
                    "t": 97,
                    "s": [{
                        "s": -2147483648.0,
                        "i": 1,
                        "l": [{"m": 255, "t": 97, "r": -2147483648.0}],
                    }],
                },
                {"t": 97, "s": []},
            ],
            "t": [{"a": 4096, "b": 0, "c": 0, "d": 4096, "x": 0, "y": 0}],
        }
        changed, report = apply_root_x_layout(parts, half_angle_degrees=15)
        self.assertEqual(len(parts["g"][0]["s"]), 1)
        self.assertEqual(len(changed["g"][0]["s"]), 2)
        self.assertEqual(len(changed["t"]), 3)
        self.assertEqual(report["top_bottom_included_angle_degrees"], 30.0)
        self.assertEqual(report["sound_instances"], 1)
        self.assertFalse(report["gameplay_geometry_changed"])
        self.assertEqual([segment["l"][0]["m"] >> 12 for segment in changed["g"][0]["s"]], [1, 2])
        self.assertEqual(changed["t"][1], {"a": 3956, "b": -1060, "c": 1060, "d": 3956, "x": 0, "y": 0})
        self.assertEqual(changed["t"][2], {"a": 3956, "b": 1060, "c": -1060, "d": 3956, "x": 0, "y": 0})

    def test_root_x_layout_rejects_non_identity_root(self):
        parts = {
            "g": [{"t": 1, "s": [{"s": -2147483648.0, "i": 0, "l": [{"m": 255}]}]}],
            "t": [{"a": 4000, "b": 0, "c": 0, "d": 4096, "x": 0, "y": 0}],
        }
        with self.assertRaisesRegex(ReskinError, "identity root"):
            apply_root_x_layout(parts, half_angle_degrees=15)

    def test_trail_x_layout_splits_only_isolated_character_trail(self):
        prefix = "battle/effect/example/.gen/example"
        parts = {
            "i": [
                {"p": f"{prefix}/f"},
                {"p": f"{prefix}/i"},
                {"p": f"{prefix}/g"},
                {"p": f"{prefix}/x"},
            ],
            "g": [
                {
                    "t": 10,
                    "s": [
                        {"s": -2147483648.0, "i": 1, "l": [{"m": 255, "t": 10, "r": 1073741824.0}]},
                        {"s": 0, "i": 3, "l": [{"m": 255, "t": 10}]},
                    ],
                },
                {
                    "t": 10,
                    "s": [
                        {"s": 0, "i": 0, "l": [{"m": 255, "t": 10}]},
                        {"s": 0, "i": 1, "l": [{"m": 255, "t": 10}]},
                        {"s": 0, "i": 2, "l": [{"m": 255, "t": 10}]},
                    ],
                },
            ],
            "t": [{"a": 4096, "b": 0, "c": 0, "d": 4096, "x": 0, "y": 0}],
        }
        changed, report = apply_trail_x_layout(
            parts,
            half_angle_degrees=15,
            replacement_terminals={"f", "i"},
        )
        self.assertEqual(report["target_group"], 1)
        self.assertEqual(report["parent_group"], 0)
        self.assertEqual(report["central_effect_instances"], 1)
        self.assertEqual(len(parts["g"][0]["s"]), 2)
        self.assertEqual(len(changed["g"][0]["s"]), 3)
        self.assertEqual(sum(int(segment["i"]) == 1 for segment in changed["g"][0]["s"]), 2)
        self.assertEqual(sum((int(segment["s"]) & 0xFFFFFFFF) >> 30 == 0 for segment in changed["g"][0]["s"]), 1)

    def test_pool_safe_trail_x_resizes_leaf_display_object_capacity(self):
        prefix = "battle/effect/example/.gen/example"
        parts = {
            "i": [
                {"p": f"{prefix}/f"},
                {"p": f"{prefix}/i"},
                {"p": f"{prefix}/g"},
                {"p": f"{prefix}/x"},
            ],
            "g": [
                {
                    "t": 10,
                    "s": [
                        {
                            "s": -2147483648.0,
                            "i": 1,
                            "l": [{"m": 255, "t": 10, "r": 1073741824.0}],
                        },
                        {"s": 0, "i": 3, "l": [{"m": 255, "t": 10}]},
                    ],
                },
                {
                    "t": 10,
                    "s": [
                        {"s": 0, "i": 0, "l": [{"m": 255, "t": 10}]},
                        {"s": 0, "i": 1, "l": [{"m": 255, "t": 10}]},
                        {"s": 0, "i": 2, "l": [{"m": 255, "t": 10}]},
                    ],
                },
            ],
            "t": [{"a": 4096, "b": 0, "c": 0, "d": 4096, "x": 0, "y": 0}],
            "a": [1, 1, 1, 1],
            "m": [],
            "o": [],
            "c": [],
            "s": 1,
        }
        changed, report = apply_pool_safe_trail_x_layout(
            parts,
            half_angle_degrees=15,
            replacement_terminals={"f", "i"},
        )
        self.assertEqual(changed["a"], [2, 2, 2, 1])
        self.assertEqual(parts["a"], [1, 1, 1, 1])
        self.assertEqual(report["object_pool_entries_changed"], 3)
        self.assertEqual(report["object_pool_capacity_before"], 4)
        self.assertEqual(report["object_pool_capacity_after"], 7)
        self.assertEqual(report["source_visible_instance_peak"], 4)
        self.assertEqual(report["target_visible_instance_peak"], 7)
        self.assertEqual(report["groups_added"], 0)
        self.assertEqual(report["segments_added"], 1)
        self.assertEqual(report["matrices_added"], 2)
        self.assertTrue(report["full_trail_density_per_branch"])

    def test_interleaved_trail_x_reuses_existing_stamps(self):
        prefix = "battle/effect/example/.gen/example"
        y_values = [(-4 + index) * 131072 for index in range(8)]
        parts = {
            "i": [{"p": f"{prefix}/w"}],
            "g": [
                {
                    "t": 97,
                    "s": [
                        {
                            "s": -2147483648 + index,
                            "i": 1,
                            "l": [{"m": index << 12, "t": 97}],
                        }
                        for index in range(8)
                    ],
                },
                {
                    "t": 97,
                    "s": [{"s": 0, "i": 0, "l": [{"m": 8 << 12, "t": 97}]}],
                },
            ],
            "t": [
                {"a": 4096, "b": 0, "c": 0, "d": 4096, "x": 0, "y": y}
                for y in y_values
            ] + [{"a": 4096, "b": 0, "c": 0, "d": 4096, "x": 0, "y": 0}],
        }
        changed, report = apply_interleaved_trail_x_layout(
            parts,
            half_angle_degrees=15,
            trail_terminal="w",
        )
        self.assertEqual(len(changed["g"]), len(parts["g"]))
        self.assertEqual(len(changed["g"][0]["s"]), len(parts["g"][0]["s"]))
        self.assertEqual(len(changed["i"]), len(parts["i"]))
        self.assertEqual(len(changed["t"]), len(parts["t"]))
        self.assertEqual(report["branch_stamp_counts"], {"negative": 4, "positive": 4})
        self.assertEqual(report["groups_added"], 0)
        self.assertEqual(report["segments_added"], 0)
        self.assertEqual(report["images_added"], 0)
        self.assertEqual(report["matrices_added"], 0)
        self.assertEqual(report["matrices_modified"], 8)
        self.assertTrue(report["visible_instance_budget_unchanged"])
        self.assertEqual(
            [matrix["b"] for matrix in changed["t"][:8]],
            [-1060, 1060, -1060, 1060, -1060, 1060, -1060, 1060],
        )
        self.assertEqual([matrix["x"] for matrix in parts["t"]], [0] * 9)


if __name__ == "__main__":
    unittest.main()
