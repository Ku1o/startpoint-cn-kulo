import io
import unittest
import zlib

from PIL import Image

import wf_assets
import wf_battle_atlas_repack as repack
import wf_dsl


def _stored_png(image):
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=9)
    return wf_assets.png_encode(stream.getvalue())


def _stored_atlas(records):
    compressor = zlib.compressobj(level=9, wbits=-15)
    raw = wf_dsl.encode_amf3(records)
    return compressor.compress(raw) + compressor.flush()


class BattleAtlasRepackTests(unittest.TestCase):
    def source(self):
        image = Image.new("RGBA", (20, 12), (0, 0, 0, 0))
        image.paste((255, 10, 20, 255), (1, 1, 4, 3))
        image.paste((20, 200, 30, 160), (8, 2, 10, 6))
        records = [
            {"n": "frame/a", "w": 3, "h": 2, "x": 1, "y": 1, "fx": -4, "tag": "keep"},
            {"n": "frame/b", "w": 2, "h": 4, "x": 8, "y": 2, "fy": -7},
            {"n": "frame/a-alias", "w": 3, "h": 2, "x": 1, "y": 1, "fx": 9},
        ]
        return image, records

    def test_repack_preserves_pixels_metadata_order_and_duplicate_coordinates(self):
        image, records = self.source()
        result = repack.repack_atlas(
            _stored_png(image),
            _stored_atlas(records),
            target_width=5,
            gap=2,
            sort_mode="height",
        )
        output_image = repack.decode_png(result.png_payload)
        output_records = repack.decode_atlas(result.atlas_payload)
        self.assertEqual([item["n"] for item in output_records], [item["n"] for item in records])
        self.assertEqual(
            [{key: value for key, value in item.items() if key not in {"x", "y"}} for item in output_records],
            [{key: value for key, value in item.items() if key not in {"x", "y"}} for item in records],
        )
        self.assertEqual(
            (output_records[0]["x"], output_records[0]["y"]),
            (output_records[2]["x"], output_records[2]["y"]),
        )
        self.assertEqual(
            repack.content_signature(image, records),
            repack.content_signature(output_image, output_records),
        )
        first = repack.Rect(
            output_records[0]["x"], output_records[0]["y"],
            output_records[0]["w"], output_records[0]["h"],
        )
        second = repack.Rect(
            output_records[1]["x"], output_records[1]["y"],
            output_records[1]["w"], output_records[1]["h"],
        )
        horizontal_gap = max(second.x - first.x - first.w, first.x - second.x - second.w)
        vertical_gap = max(second.y - first.y - first.h, first.y - second.y - second.h)
        self.assertTrue(horizontal_gap >= 2 or vertical_gap >= 2)

    def test_rejects_nontransparent_pixels_outside_atlas(self):
        image, records = self.source()
        image.putpixel((19, 11), (1, 2, 3, 255))
        with self.assertRaisesRegex(ValueError, "outside atlas rectangles"):
            repack.repack_atlas(
                _stored_png(image),
                _stored_atlas(records),
                target_width=5,
            )

    def test_rejects_overlapping_distinct_regions(self):
        image, records = self.source()
        records.append({"n": "bad", "w": 2, "h": 2, "x": 2, "y": 1})
        with self.assertRaisesRegex(ValueError, "overlap"):
            repack.repack_atlas(
                _stored_png(image),
                _stored_atlas(records),
                target_width=5,
            )


if __name__ == "__main__":
    unittest.main()
