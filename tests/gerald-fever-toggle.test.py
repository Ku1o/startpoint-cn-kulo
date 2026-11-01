"""Resource contract regressions for the 1.4.354 Water Gerald ability-3 repair."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gerald_fever_toggle", ROOT / "tools/build-gerald-fever-toggle.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class GeraldFeverToggleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "assets/asset-patch/manifest.json").read_bytes())
        cls.base = copy.deepcopy(cls.manifest)
        index = next(i for i, patch in enumerate(cls.base["patches"]) if patch["version"] == repair.VERSION)
        cls.base["patches"] = cls.base["patches"][:index]
        cls.base["cdn_version"] = repair.BASE_VERSION
        cls.entries = repair.build_entries(ROOT, cls.base)

    def test_published_archive_is_exact_scoped_recipe(self):
        self.assertEqual(repair.verify(ROOT)["members"], 2)

    def test_later_resource_edges_do_not_invalidate_the_fixed_repair(self):
        future = copy.deepcopy(self.manifest)
        future["cdn_version"] = "1.4.999"
        future["patches"].append({"version": "1.4.999", "depends_on": repair.VERSION})
        self.assertEqual(repair.verify_manifest(ROOT, future), repair.verify(ROOT))

    def test_ability_changes_only_1299893_rows_4_and_6_c47(self):
        before_raw = repair.rawmap(repair.read_effective(ROOT, self.base, repair.ABILITY_LP))
        after_raw = repair.rawmap(self.entries[repair.member(repair.ABILITY_LP)])
        self.assertEqual(list(after_raw), list(before_raw))
        changed_keys = [k for k in before_raw if after_raw[k] != before_raw[k]]
        self.assertEqual(changed_keys, [repair.ABILITY_KEY])
        before_rows = repair.parse_csv(repair.decode_leaf(before_raw[repair.ABILITY_KEY]))
        after_rows = repair.parse_csv(repair.decode_leaf(after_raw[repair.ABILITY_KEY]))
        self.assertEqual(len(after_rows), 8)
        for idx in range(8):
            if idx in (4, 6):
                expected = list(before_rows[idx])
                self.assertEqual(expected[47], "528")
                expected[47] = "526"
                self.assertEqual(after_rows[idx], expected)
            else:
                self.assertEqual(after_rows[idx], before_rows[idx])

    def test_custom_ability_string_changes_only_gerald_aqua_3_description(self):
        before_raw = repair.rawmap(repair.read_effective(ROOT, self.base, repair.CAS_LP))
        after_raw = repair.rawmap(self.entries[repair.member(repair.CAS_LP)])
        self.assertEqual(list(after_raw), list(before_raw))
        changed_keys = [k for k in before_raw if after_raw[k] != before_raw[k]]
        self.assertEqual(changed_keys, [repair.CAS_KEY])
        before_text = repair.parse_csv(repair.decode_leaf(before_raw[repair.CAS_KEY]))[0][0]
        after_text = repair.parse_csv(repair.decode_leaf(after_raw[repair.CAS_KEY]))[0][0]
        self.assertIn(repair.OLD_TEXT, before_text)
        self.assertNotIn("自适应", after_text)
        self.assertEqual(after_text, before_text.replace(repair.OLD_TEXT, repair.NEW_TEXT))

    def test_changed_preimage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "preimage"):
            repair.rewrite_ability(self.entries[repair.member(repair.ABILITY_LP)])
        with self.assertRaisesRegex(ValueError, "preimage"):
            repair.rewrite_custom_ability_string(self.entries[repair.member(repair.CAS_LP)])

    def test_shared_android_ios_common_roots_and_zip_crc(self):
        raw = repair.archive_bytes(self.entries)
        self.assertLessEqual(len(raw), 5 * 1024 * 1024)
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            self.assertIsNone(source.testzip())
            self.assertEqual(len(source.namelist()), 2)
            for name in source.namelist():
                self.assertTrue(name.startswith("production/upload/"))
                repair.rawmap(source.read(name))


if __name__ == "__main__":
    unittest.main()
