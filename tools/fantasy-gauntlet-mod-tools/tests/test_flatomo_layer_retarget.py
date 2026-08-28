import io
import unittest

from PIL import Image

import wf_assets
import wf_flatomo_layer_retarget as retarget


def _stored_png():
    image = Image.new("RGBA", (4, 4), (10, 20, 30, 255))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return wf_assets.png_encode(stream.getvalue())


class FlatomoLayerRetargetTests(unittest.TestCase):
    old_sheet = "battle/effect/demo/demo.png"
    new_sheet = "battle/uncommon/layer1/demo/demo.png"
    old_effect = "battle/effect/demo/demo_transform"
    new_effect = "battle/uncommon/layer1/demo/demo_transform"

    def source(self):
        old_prefix = "battle/effect/demo/.gen/demo/"
        atlas = [
            {"n": old_prefix + "a", "w": 2, "h": 2, "x": 0, "y": 0, "fx": -1},
            {"n": old_prefix + "b", "w": 2, "h": 2, "x": 2, "y": 0, "fy": -2},
        ]
        parts = {
            "i": [{"s": False, "p": old_prefix + "b"}],
            "g": [{"t": 1, "s": []}],
            "m": [],
        }
        timeline = {"sequences": [{"begin": 1, "end": 1, "name": "neutral"}]}
        action = ["ActionDsl", ["SpecifyEffectDirectly", self.old_effect], "keep"]
        return tuple(retarget.encode_payload(item) for item in (atlas, parts, timeline, action))

    def test_retargets_only_paths_and_preserves_png_and_timeline(self):
        atlas, parts, timeline, action = self.source()
        png = _stored_png()
        result = retarget.retarget_effect_layer(
            png_payload=png,
            atlas_payload=atlas,
            parts_payload=parts,
            timeline_payload=timeline,
            action_payloads=(action,),
            old_sheet_logical=self.old_sheet,
            new_sheet_logical=self.new_sheet,
            old_effect_reference=self.old_effect,
            new_effect_reference=self.new_effect,
        )
        self.assertEqual(result.timeline_payload, timeline)
        self.assertEqual(result.atlas_records, 2)
        self.assertEqual(result.parts_images, 1)
        self.assertEqual(result.action_replacements, (1,))
        new_prefix = "battle/uncommon/layer1/demo/.gen/demo/"
        output_atlas = retarget.decode_payload(result.atlas_payload)
        output_parts = retarget.decode_payload(result.parts_payload)
        output_action = retarget.decode_payload(result.action_payloads[0])
        self.assertEqual([item["n"] for item in output_atlas], [new_prefix + "a", new_prefix + "b"])
        self.assertEqual(output_parts["i"][0]["p"], new_prefix + "b")
        self.assertIn(self.new_effect, repr(output_action))
        self.assertNotIn(self.old_effect, repr(output_action))

    def test_rejects_missing_or_duplicate_action_reference(self):
        atlas, parts, timeline, _ = self.source()
        for action_tree in (["none"], [self.old_effect, self.old_effect]):
            with self.subTest(action_tree=action_tree):
                with self.assertRaisesRegex(ValueError, "exactly once"):
                    retarget.retarget_effect_layer(
                        png_payload=_stored_png(),
                        atlas_payload=atlas,
                        parts_payload=parts,
                        timeline_payload=timeline,
                        action_payloads=(retarget.encode_payload(action_tree),),
                        old_sheet_logical=self.old_sheet,
                        new_sheet_logical=self.new_sheet,
                        old_effect_reference=self.old_effect,
                        new_effect_reference=self.new_effect,
                    )

    def test_rejects_parts_cell_missing_from_atlas(self):
        atlas, parts, timeline, action = self.source()
        parts_tree = retarget.decode_payload(parts)
        parts_tree["i"][0]["p"] = "battle/effect/demo/.gen/demo/missing"
        with self.assertRaisesRegex(ValueError, "missing atlas cells"):
            retarget.retarget_effect_layer(
                png_payload=_stored_png(),
                atlas_payload=atlas,
                parts_payload=retarget.encode_payload(parts_tree),
                timeline_payload=timeline,
                action_payloads=(action,),
                old_sheet_logical=self.old_sheet,
                new_sheet_logical=self.new_sheet,
                old_effect_reference=self.old_effect,
                new_effect_reference=self.new_effect,
            )


if __name__ == "__main__":
    unittest.main()
