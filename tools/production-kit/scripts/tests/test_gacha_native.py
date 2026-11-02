"""Real-file regressions. Set GACHA_NATIVE_SUPPORT_ROOT/CASE_ROOT/TEST_OUTPUT.

Fixtures are read-only accepted-case bindings, not synthesized Movie stand-ins.
All generated files go beneath the explicitly selected test output directory.
"""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gacha_native as native
from PIL import Image


class RealNativeTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ["GACHA_NATIVE_SUPPORT_ROOT", "GACHA_NATIVE_CASE_ROOT", "GACHA_NATIVE_TEST_OUTPUT"]
        if not all(os.environ.get(name) for name in names):
            raise unittest.SkipTest("set explicit support, real fixture case and task output paths")
        cls.support, cls.case, cls.output = [Path(os.environ[name]).resolve() for name in names]
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.run_dir = Path(tempfile.mkdtemp(prefix="real-native-", dir=cls.output))
        cls.template270 = cls.case / "refinement-270/cover/resources.json"
        cls.template269 = cls.case / "refinement-269/cover/alternative-fixed-layout/resources.json"
        cls.single = cls.case / "single-sample/movie-resources.json"
        cls.replay = native.build_native({"schema_version": 1, "template_resources": str(cls.template270),
                                        "anchor_checks": [{"slot": 33, "pivot_texture": [104, 0]}]},
                                       support_root=cls.support, output_dir=cls.run_dir / "replay270")

    def build(self, name, spec):
        return native.build_native(spec, support_root=self.support, output_dir=self.run_dir / name)

    def test_270_noop_bound_bytes_semantics_and_pixels(self):
        receipt = self.replay
        self.assertTrue(all(receipt["checks"].values()))
        self.assertEqual(receipt["counts"], {"images": 36, "graphics": 79, "clips": 26, "root_frames": 301})
        self.assertEqual(len(receipt["scope_pools"]), 27)
        self.assertEqual(receipt["changed_motion_frames"], [])
        source = {Path(r["logical"]).name: r for r in receipt["source_resources"]}
        for r in receipt["resources"]:
            self.assertEqual(Path(r["file"]).read_bytes(), Path(source[Path(r["logical"]).name]["file"]).read_bytes())
        expected = json.loads((self.case / "refinement-270/cover/model-data.json").read_text("utf8"))["pages"]["cover"]
        actual = json.loads(Path(receipt["model_file"]).read_text("utf8"))["pages"]["cover"]
        self.assertEqual(actual["frames"], expected["frames"])
        self.assertEqual(actual["timeline"], expected["timeline"])

    def test_new_pool_marked_2x_texture_and_repacked_closure(self):
        image = Image.open(Path(self.replay["cells_dir"]) / "33.png").convert("RGBA")
        marked = Image.new("RGBA", image.size, (15, 235, 110, 255))
        marked.putalpha(image.getchannel("A"))
        file = self.run_dir / "obviously-marked-test-nameplate.png"
        marked.save(file)
        textures = [{"slot": 33, "file": str(file), "logical_canvas": [233, 67], "sample_scale": 2}]
        self.assertEqual(native.validate_textures(self.template270, textures, support_root=self.support)["status"], "textures_valid")
        receipt = self.build("other-pool", {"template_resources": str(self.template270),
                            "logical_prefix": "gacha/feature_movie/pipeline_native_test/cover",
                            "textures": textures, "repack": True, "atlas_size": 2048})
        self.assertTrue(all(receipt["checks"].values()))
        self.assertTrue(receipt["repacked"])
        self.assertEqual(receipt["atlas_size"], [2048, 2048])
        self.assertNotEqual(receipt["cell_rgba_sha256"][33], self.replay["cell_rgba_sha256"][33])
        self.assertTrue(all(a == b for i, (a, b) in enumerate(zip(receipt["cell_rgba_sha256"], self.replay["cell_rgba_sha256"])) if i != 33))
        self.assertTrue(all(r["logical"].startswith("gacha/feature_movie/pipeline_native_test/cover/") for r in receipt["resources"]))
        core_data = native._read(receipt["resources"], self.support)
        self.assertTrue(all(r["p"].startswith("gacha/feature_movie/pipeline_native_test/cover/") for r in core_data["parts"]["i"]))
        frames = json.loads(Path(receipt["model_file"]).read_text("utf8"))["pages"]["cover"]["frames"]
        reference = json.loads(Path(self.replay["model_file"]).read_text("utf8"))["pages"]["cover"]["frames"]
        self.assertEqual(frames, reference)

    def test_sampling_contract_does_not_accept_false_2x_claim(self):
        with self.assertRaisesRegex(native.NativeBuildError, "sampling contract"):
            native.validate_textures(self.template270, [{"slot": 33, "file": str(Path(self.replay["cells_dir"]) / "33.png"),
                                     "logical_canvas": [234, 67], "sample_scale": 2}], support_root=self.support)

    def test_existing_wrong_pivot_rejected_and_actual_tip_passes(self):
        check = [{"slot": 33, "pivot_texture": [104, 0]}]
        with self.assertRaisesRegex(native.NativeBuildError, "anchor drift"):
            native.validate_anchors(self.template269, check, support_root=self.support)
        valid = native.validate_anchors(self.template270, check, support_root=self.support)
        self.assertEqual(valid["anchors"][0]["max_drift_px"], 0)
        with self.assertRaisesRegex(native.NativeBuildError, "anchor drift"):
            self.build("wrong-third-plate-pivot", {"template_resources": str(self.template270), "reference_frame": 240,
                       "anchors": [{"slot": 33, "leaf_graphics": 72, "outer_graphics": 1, "outer_segment": 5,
                                    "pivot_texture": [466 * 204 / 273, 0]}], "anchor_checks": check})
        self.assertFalse((self.run_dir / "wrong-third-plate-pivot").exists())

    def test_correct_outer_anchor_recreates_accepted_270(self):
        receipt = self.build("repair269-to270", {"template_resources": str(self.template269), "reference_frame": 240,
                             "anchors": [{"slot": 33, "leaf_graphics": 72, "outer_graphics": 1,
                                          "outer_segment": 5, "pivot_texture": [104, 0]}]})
        self.assertEqual(receipt["changed_motion_frames"], list(range(190, 202)) + [203, 205])
        self.assertEqual(len(receipt["matrix_deltas"]), 2)
        self.assertEqual(len(receipt["appended_matrices"]), 2)
        self.assertEqual(receipt["anchor_checks"][0]["max_drift_px"], 0)
        actual = {Path(r["logical"]).name: Path(r["file"]).read_bytes() for r in receipt["resources"]}
        expected = {Path(r["logical"]).name: Path(r["file"]).read_bytes() for r in self.replay["resources"]}
        self.assertEqual(actual, expected)

    def test_actual_single_character_template(self):
        receipt = self.build("single-character", {"template_resources": str(self.single)})
        self.assertEqual(receipt["counts"]["images"], 16)
        self.assertEqual(receipt["counts"]["clips"], 12)
        self.assertEqual(len(receipt["scope_pools"]), 13)
        self.assertTrue(all(receipt["checks"].values()))

    def test_nested_clip_capacity_failure_is_not_hidden_by_root_array(self):
        data = native._read(self.single, self.support)
        parts = copy.deepcopy(data["parts"])
        self.assertGreater(parts["m"][7]["i"][7], 0)
        parts["m"][7]["i"][7] = 0
        fixture_dir = self.run_dir / "invalid-capacity-input"
        fixture_dir.mkdir()
        file = fixture_dir / "invalid-clip-capacity.movie"
        payload = native._encode(parts, data["dsl"])
        file.write_bytes(payload)
        records = copy.deepcopy(data["records"])
        row = next(r for r in records if r["logical"].endswith("/feature.movie.amf3.deflate"))
        row.update(file=str(file), bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        with self.assertRaisesRegex(native.NativeBuildError, "clip:7 image pool insufficient"):
            self.build("invalid-clip-pool", {"template_resources": records})
        self.assertFalse((self.run_dir / "invalid-clip-pool").exists())


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RealNativeTemplateTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if os.environ.get("GACHA_NATIVE_TEST_OUTPUT"):
        output = Path(os.environ["GACHA_NATIVE_TEST_OUTPUT"])
        output.mkdir(parents=True, exist_ok=True)
        report = {"status": "passed" if result.wasSuccessful() else "failed", "tests_run": result.testsRun,
                  "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
                  "run_directory": str(getattr(RealNativeTemplateTests, "run_dir", "")), "device_verified": False}
        (output / "LAST-RESULT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf8")
    sys.exit(not result.wasSuccessful())
