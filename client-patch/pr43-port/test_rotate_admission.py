"""Exact-byte admission rotation plus malformed/incomplete private-pair refusals."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest

import rotate_admission as rotation


SOURCE = None
BUILD_ID = "android-test-rotation"


class RotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SOURCE is None:
            raise unittest.SkipTest('Pass --input-swf to run the private carrier checks')
        cls.source = SOURCE.read_bytes()
        cls.common, _ = rotation.port_game.dependencies()
        tag, = [t for t in cls.common.abc_tags(cls.source)
                if t[0] == b"cn/admission/BuildConfig"]
        cls.old_key = rotation.constants(cls.common.ABC(tag[4]))["KEY"]
        # A fixed fixture value is deliberately unrelated to a release key.
        cls.new_key = "00" * 32 if cls.old_key != "00" * 32 else "11" * 32
        cls.policy = {"enforce": True, "updateMessage": "fixture", "builds": [
            {"id": rotation.OLD_ID, "platform": "android", "enabled": True, "allowUntil": None},
            {"id": BUILD_ID, "platform": "android", "enabled": True, "allowUntil": None},
        ]}

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="admission-rotation-test-")
        self.addCleanup(self.directory.cleanup)
        self.pair = Path(self.directory.name)
        (self.pair / "config").mkdir()
        self.policy = copy.deepcopy(type(self).policy)
        self.keys = {rotation.OLD_ID: self.old_key, BUILD_ID: self.new_key}
        self.write_pair()

    def write_pair(self):
        (self.pair / "config/client-admission.json").write_text(json.dumps(self.policy), "utf-8")
        (self.pair / "config/client-admission.keys.json").write_text(json.dumps(self.keys), "utf-8")

    def reject(self, source=None, build=BUILD_ID):
        self.write_pair()
        with self.assertRaises(ValueError):
            rotation.rotate(self.source if source is None else source, self.pair, build)

    def test_exact_rotation_and_inverse_preserve_all_non_admission_bytes(self):
        output, report = rotation.rotate(self.source, self.pair, BUILD_ID)
        self.assertNotEqual(output, self.source)
        self.assertEqual(report["changed_doabc_count"], 2)
        self.assertEqual(report["unchanged_doabc_count"], 300)
        self.assertEqual(report["unchanged_admission_method_bodies"], 47)
        self.assertTrue(report["admission_pool_inverse_verified"])
        report_text = json.dumps(report)
        self.assertNotIn(self.old_key, report_text)
        self.assertNotIn(self.new_key, report_text)
        self.assertNotIn("SP-ADMISSION-1", report_text)
        tag, = [t for t in self.common.abc_tags(output)
                if t[0] == b"cn/admission/BuildConfig"]
        result = rotation.constants(self.common.ABC(tag[4]))
        self.assertTrue(result["ID"] == BUILD_ID and result["KEY"] == self.new_key
                        and result["ORIGIN"] == rotation.ORIGIN)

    def test_reject_changed_input(self):
        self.reject(self.source + b"unexpected")

    def test_reject_old_id(self):
        self.reject(build=rotation.OLD_ID)

    def test_reject_non_android_id(self):
        self.reject(build="ios-test-rotation")

    def test_reject_incomplete_pair(self):
        del self.keys[rotation.OLD_ID]
        self.reject()

    def test_reject_wrong_platform(self):
        self.policy["builds"][1]["platform"] = "ios"
        self.reject()

    def test_reject_disabled_build(self):
        self.policy["builds"][1]["enabled"] = False
        self.reject()

    def test_reject_duplicate_build(self):
        self.policy["builds"].append(copy.deepcopy(self.policy["builds"][1]))
        self.reject()

    def test_reject_unchanged_key(self):
        self.keys[BUILD_ID] = self.old_key
        self.reject()

    def test_reject_malformed_key(self):
        self.keys[BUILD_ID] = "invalid fixture"
        self.reject()

    def test_reject_wrong_input_key(self):
        self.keys[rotation.OLD_ID] = "22" * 32 if self.old_key != "22" * 32 else "33" * 32
        self.reject()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-swf", type=Path, required=True)
    args, rest = parser.parse_known_args()
    SOURCE = args.input_swf
    unittest.main(argv=[__file__, *rest])
