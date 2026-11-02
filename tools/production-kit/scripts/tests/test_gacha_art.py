"""Unit drawing checks and real accepted-banner/font replay. No runtime/DB access."""
import copy
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from PIL import Image, ImageChops

SCRIPT = Path(__file__).resolve().parents[1] / "gacha_art.py"
loader = importlib.util.spec_from_file_location("gacha_art", SCRIPT)
art = importlib.util.module_from_spec(loader)
loader.loader.exec_module(art)
P = Path(os.environ.get("GACHA_NATIVE_CASE_ROOT", "missing-real-fixtures"))
TEST_ROOT = Path(os.environ.get("GACHA_NATIVE_TEST_OUTPUT", tempfile.gettempdir()))
BANNER = P / "refinement-265/banner-official/banner.png"
FONT = Path(os.environ.get("GACHA_TEST_FONT", "missing-test-font"))


def binding(file):
    return {"file": str(file), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}


def image_layer(file, **kwargs):
    return {**binding(file), "position": [0, 0], **kwargs}


def spec(layers, size=(100, 100), key="drawing"):
    return {"schema_version": 1, "artifacts": [{"key": key, "size": list(size), "background": [0, 0, 0, 0], "layers": layers}]}


class ArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        cls.art_run = TEST_ROOT / ("run-" + uuid.uuid4().hex[:12])
        cls.art_run.mkdir()
        cls.source = cls.art_run / "source.png"
        Image.new("RGBA", (80, 40), (255, 0, 0, 255)).save(cls.source)
        cls.blue = cls.art_run / "blue.png"
        Image.new("RGBA", (20, 20), (0, 0, 255, 255)).save(cls.blue)

    def out(self, suffix=""):
        return self.art_run / (self._testMethodName + suffix)

    def test_accepted_265_banner_uniform_replay(self):
        if not BANNER.is_file() or not FONT.is_file():
            self.skipTest("Set GACHA_NATIVE_CASE_ROOT and GACHA_TEST_FONT for real artwork replay")
        self.assertTrue(BANNER.is_file(), "Accepted265 banner fixture required")
        self.assertEqual(binding(BANNER)["sha256"], "e53cde1ff165fb7299c9fca010c008b93dfc213d44e8c8442e8e3e2d596c939c")
        recipe = spec([image_layer(BANNER, size=[510, 180])], (510, 180), "accepted265")
        receipt = art.build_art(recipe, output_dir=self.out())
        with Image.open(BANNER) as original, Image.open(self.out() / "accepted265.png") as actual:
            original = original.convert("RGBA")
            expected = Image.alpha_composite(Image.new("RGBA", original.size), original)
            self.assertEqual(actual.tobytes(), expected.tobytes())
            self.assertEqual(actual.getchannel("A").tobytes(), original.getchannel("A").tobytes())
            for point in [(80, 60), (255, 90), (440, 120), (0, 0)]:
                self.assertEqual(actual.getpixel(point), expected.getpixel(point))
        row = receipt["artifacts"][0]
        self.assertEqual(row["size"], [510, 180])
        self.assertEqual(row["layers"][0]["uniform_scale"], 1)
        self.assertEqual(row["layers"][0]["sources"][0]["sha256"], binding(BANNER)["sha256"])
        self.assertEqual(receipt, json.loads((self.out() / "receipt.json").read_text(encoding="utf-8")))
        smaller = spec([image_layer(BANNER, size=[255, 90])], (255, 90), "half")
        small = art.build_art(smaller, output_dir=self.out("-half"))
        self.assertEqual(small["artifacts"][0]["layers"][0]["uniform_scale"], .5)
        with Image.open(BANNER) as original, Image.open(self.out("-half") / "half.png") as actual:
            expected = Image.alpha_composite(Image.new("RGBA", (255, 90)), original.convert("RGBA").resize((255, 90), Image.Resampling.LANCZOS))
            self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_chinese_name_2x_bound_font_and_stroke(self):
        self.assertTrue(FONT.is_file(), "Existing Chinese recipe font required")
        text = {"text": "塞里奥尔", "font": binding(FONT), "font_size": 124, "position": [300, 83],
                "fill": [255, 255, 255, 255], "stroke_fill": [230, 83, 150, 255], "stroke_width": 4, "anchor": "mm"}
        receipt = art.build_art(spec([text], (600, 166), "name2x"), output_dir=self.out())
        row = receipt["artifacts"][0]
        self.assertEqual(row["size"], [600, 166])
        self.assertEqual(row["alpha"]["range"], [0, 255])
        self.assertEqual(row["layers"][0]["sources"][0]["sha256"], binding(FONT)["sha256"])
        self.assertFalse(row["layers"][0]["clipped_to_canvas"])
        x0, y0, x1, y1 = row["alpha"]["bbox"]
        self.assertTrue(0 < x0 < x1 < 600 and 0 < y0 < y1 < 166)
        with Image.open(self.out() / "name2x.png") as image:
            colors = {color for _, color in image.getcolors(maxcolors=image.width * image.height)}
            self.assertIn((255, 255, 255, 255), colors)
            self.assertIn((230, 83, 150, 255), colors)
            self.assertGreater(row["alpha"]["nonzero_pixels"], 5000)

    def test_fit_is_uniform_and_ordered_opacity(self):
        recipe = spec([image_layer(self.source, size=[40, 40], position=[2, 3]), image_layer(self.blue, position=[10, 10], opacity=.5)])
        receipt = art.build_art(recipe, output_dir=self.out())
        self.assertEqual(receipt["artifacts"][0]["layers"][0]["scaled_size"], [40, 20])
        self.assertEqual(receipt["artifacts"][0]["layers"][0]["uniform_scale"], .5)
        with Image.open(self.out() / "drawing.png") as image:
            self.assertEqual(image.getpixel((10, 10)), (127, 0, 128, 255))
            self.assertEqual(image.getpixel((2, 22)), (255, 0, 0, 255))
            self.assertEqual(image.getpixel((2, 23)), (0, 0, 0, 0))

    def test_crop_mask_rotation(self):
        mask_file = self.art_run / "mask.png"
        Image.new("L", (40, 40), 128).save(mask_file)
        recipe = spec([image_layer(self.source, crop=[40, 0, 40, 40], mask=binding(mask_file), scale=.5, rotation=90, position=[3, 4])])
        result = art.build_art(recipe, output_dir=self.out())["artifacts"][0]
        self.assertEqual(result["layers"][0]["cropped_size"], [40, 40])
        self.assertEqual(result["layers"][0]["rendered_size"], [20, 20])
        self.assertEqual(result["alpha"]["bbox"], [3, 4, 23, 24])
        with Image.open(self.out() / "drawing.png") as image:
            self.assertEqual(image.getpixel((10, 10)), (255, 0, 0, 128))
        rotated = art.build_art(spec([image_layer(self.source, rotation=90)]), output_dir=self.out("-nonsquare"))
        self.assertEqual(rotated["artifacts"][0]["layers"][0]["rendered_size"], [40, 80])

    def test_reject_transform_errors_without_outputs(self):
        variants = [{"scale": [1, 2]}, {"scale": 0}, {"scale": 2, "size": [10, 20]}, {"size": [0, 20]},
                    {"crop": [60, 0, 30, 20]}, {"opacity": 1.1}, {"rotation": float("nan")},
                    {"stretch": True}, {"position": [1.5, 2]}, {"mask": binding(self.blue)}]
        for i, kwargs in enumerate(variants):
            output = self.out("-" + str(i))
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                art.build_art(spec([image_layer(self.source, **kwargs)]), output_dir=output)
            self.assertFalse(output.exists())

    def test_reject_missing_hash_font_and_invalid_artifact(self):
        bad = image_layer(self.source)
        bad["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            art.build_art(spec([bad]), output_dir=self.out("-hash"))
        bad = image_layer(self.source)
        bad["file"] = str(self.art_run / "missing.png")
        with self.assertRaises(FileNotFoundError):
            art.build_art(spec([bad]), output_dir=self.out("-missing"))
        text = {"text": "名", "font": {"file": str(FONT), "sha256": "0" * 64}, "font_size": 20, "position": [0, 0], "fill": [255, 255, 255]}
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            art.build_art(spec([text]), output_dir=self.out("-font"))
        for key in ["../escape", "x/y", "", ".", "NUL", "CON", "LPT3"]:
            with self.assertRaises(ValueError):
                art.build_art(spec([], key=key), output_dir=self.out("-path"))
        duplicate = spec([])
        duplicate["artifacts"].append(copy.deepcopy(duplicate["artifacts"][0]))
        with self.assertRaises(ValueError):
            art.build_art(duplicate, output_dir=self.out("-duplicate"))
        duplicate["artifacts"][1]["key"] = "DRAWING"
        with self.assertRaises(ValueError):
            art.build_art(duplicate, output_dir=self.out("-casecollision"))

    def test_refuse_overwrite(self):
        recipe = spec([image_layer(self.source)])
        art.build_art(recipe, output_dir=self.out())
        first = (self.out() / "drawing.png").read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            art.build_art(recipe, output_dir=self.out())
        self.assertEqual((self.out() / "drawing.png").read_bytes(), first)

    @classmethod
    def tearDownClass(cls):
        # Retain outputs/receipts as the requested visual acceptance evidence.
        print("ART_TEST_OUTPUT=" + str(cls.art_run), flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
