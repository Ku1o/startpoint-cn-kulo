import io
import unittest
import zlib

from PIL import Image

import wf_assets
import wf_dsl
from wf_pixelart_split_compile import compile_split_sheet


SOURCE = "character/source/pixelart"
TARGET = "character/target/pixelart"


def png(size, color):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.putpixel((0, 0), color)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def atlas():
    return [
        {
            "n": f"{SOURCE}/pixelart0002",
            "x": 10, "y": 20, "w": 3, "h": 2,
            "fx": -4, "fy": -5, "fw": 16, "fh": 16,
        },
        {
            "n": f"{SOURCE}/pixelart0008",
            "x": 30, "y": 40, "w": 4, "h": 2, "r": True,
            "fx": -6, "fy": -3, "fw": 16, "fh": 16,
        },
        {
            "n": f"{SOURCE}/pixelart0010",
            "x": 10, "y": 20, "w": 3, "h": 2,
            "fx": -7, "fy": -8, "fw": 16, "fh": 16,
        },
    ]


class SplitPixelArtCompileTests(unittest.TestCase):
    def test_rebuilds_from_one_cel_per_unique_source_rectangle(self):
        cels = {
            "pixelart0002": png((3, 2), (10, 20, 30, 255)),
            "pixelart0008": png((2, 4), (40, 50, 60, 255)),
        }
        files, report = compile_split_sheet(
            atlas(), cels,
            source_prefix=SOURCE,
            target_prefix=TARGET,
            sheet_basename="sprite_sheet",
            sheet_width=8,
            maximum_sheet_height=16,
        )
        files_again, report_again = compile_split_sheet(
            atlas(), cels,
            source_prefix=SOURCE,
            target_prefix=TARGET,
            sheet_basename="sprite_sheet",
            sheet_width=8,
            maximum_sheet_height=16,
        )
        self.assertEqual(files, files_again)
        self.assertEqual(report, report_again)
        self.assertFalse(report["writes_live"])
        self.assertTrue(report["package_manifest_eligible"])
        self.assertFalse(report["source_sheet_pixels_read"])
        self.assertEqual(3, report["atlas_records"])
        self.assertEqual(2, report["unique_cels"])
        self.assertEqual(1, report["rotation_records_removed"])

        sheet_raw = wf_assets.png_decode(files[f"{TARGET}/sprite_sheet.png"])
        with Image.open(io.BytesIO(sheet_raw)) as opened:
            sheet = opened.convert("RGBA")
        rebuilt = wf_dsl.parse_dsl(
            zlib.decompress(files[f"{TARGET}/sprite_sheet.atlas.amf3.deflate"], -15)
        )["tree"]
        self.assertEqual(
            [f"{TARGET}/pixelart0002", f"{TARGET}/pixelart0008", f"{TARGET}/pixelart0010"],
            [entry["n"] for entry in rebuilt],
        )
        self.assertTrue(all("r" not in entry for entry in rebuilt))
        self.assertEqual(
            (rebuilt[0]["x"], rebuilt[0]["y"], rebuilt[0]["w"], rebuilt[0]["h"]),
            (rebuilt[2]["x"], rebuilt[2]["y"], rebuilt[2]["w"], rebuilt[2]["h"]),
        )
        self.assertEqual((-7, -8), (rebuilt[2]["fx"], rebuilt[2]["fy"]))
        for entry, expected in zip(
            rebuilt[:2], ((10, 20, 30, 255), (40, 50, 60, 255)), strict=True
        ):
            self.assertEqual(expected, sheet.getpixel((entry["x"], entry["y"])))

    def test_rejects_missing_extra_transparent_and_out_of_frame_cels(self):
        cels = {
            "pixelart0002": png((3, 2), (10, 20, 30, 255)),
            "pixelart0008": png((2, 4), (40, 50, 60, 255)),
        }
        with self.assertRaisesRegex(ValueError, "split cel contract mismatch"):
            compile_split_sheet(
                atlas(), {"pixelart0002": cels["pixelart0002"]},
                source_prefix=SOURCE, target_prefix=TARGET,
                sheet_basename="sprite_sheet", sheet_width=8,
            )
        transparent = Image.new("RGBA", (2, 4), (0, 0, 0, 0))
        stream = io.BytesIO()
        transparent.save(stream, format="PNG")
        with self.assertRaisesRegex(ValueError, "fully transparent"):
            compile_split_sheet(
                atlas(), {**cels, "pixelart0008": stream.getvalue()},
                source_prefix=SOURCE, target_prefix=TARGET,
                sheet_basename="sprite_sheet", sheet_width=8,
            )
        drifted = atlas()
        drifted[1]["fx"] = -15
        with self.assertRaisesRegex(ValueError, "escapes its full frame"):
            compile_split_sheet(
                drifted, cels,
                source_prefix=SOURCE, target_prefix=TARGET,
                sheet_basename="sprite_sheet", sheet_width=8,
            )


if __name__ == "__main__":
    unittest.main()
