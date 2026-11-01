"""Resource contract regressions; native method replay is a separate offline check."""
import copy
import importlib.util
import io
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pumpkin_cleanup", ROOT / "tools/build-pumpkin-candle-cleanup.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class CandleCleanupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.manifest = json.loads((ROOT / "assets/asset-patch/manifest.json").read_bytes())
        cls.base = copy.deepcopy(cls.manifest)
        cls.base["patches"].pop()
        cls.base["cdn_version"] = repair.BASE_VERSION
        cls.entries = repair.build_entries(ROOT, cls.base)

    def test_published_archive_is_exact_scoped_recipe(self):
        self.assertEqual(repair.verify(ROOT)["members"], 7)

    def test_each_on_changes_only_the_discrimination_key(self):
        for program in repair.PROGRAMS[:-1]:
            with self.subTest(program=program):
                before = repair.decode(repair.read_effective(ROOT, self.base, program))
                after = repair.decode(self.entries[repair.member(program)])
                expected = copy.deepcopy(before)
                command, = repair.commands(expected, "CreateCondition")
                self.assertTrue(command[5])
                command[7] = repair.KEY
                self.assertEqual(after, expected)

    def test_off_changes_only_cancelable_selector_and_discrimination_key(self):
        before = repair.decode(repair.read_effective(ROOT, self.base, "hp_candle_off"))
        expected = copy.deepcopy(before)
        command, = repair.commands(expected, "DeleteCondition")
        self.assertEqual(command[4:6], [1, ""], "preimage reproduces the old selector mismatch")
        command[4:6] = [0, repair.KEY]
        self.assertEqual(repair.decode(self.entries[repair.member("hp_candle_off")]), expected)

    def test_unknown_program_cannot_expand_the_patch(self):
        with self.assertRaisesRegex(ValueError, "Unexpected candle program"):
            repair.rewrite("other_boss", b"")

    def test_changed_preimage_is_rejected(self):
        payload = self.entries[repair.member("hp_candle_on_1")]
        with self.assertRaisesRegex(ValueError, "preimage"):
            repair.rewrite("hp_candle_on_1", payload)

    def test_shared_android_ios_common_roots_and_roundtrip(self):
        raw = repair.archive_bytes(self.entries)
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            self.assertIsNone(source.testzip())
            self.assertEqual(len(source.namelist()), len(set(source.namelist())))
            for name in source.namelist():
                self.assertTrue(name.startswith("production/upload/"))
                tree = repair.decode(source.read(name))
                self.assertEqual(repair.parse_dsl(repair.encode_amf3(tree))["tree"], tree)


if __name__ == "__main__":
    unittest.main()
