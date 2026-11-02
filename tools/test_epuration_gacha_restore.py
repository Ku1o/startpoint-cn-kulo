"""Scoped regression checks for the immutable .356 Epuration resource repair."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("repair", ROOT / "tools/build-epuration-gacha-restore.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class EpurationRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "assets/asset-patch/manifest.json").read_bytes())
        cls.base = repair.base_manifest(cls.manifest)

    def test_installed_archive_has_exactly_two_tables_and_preserves_every_old_compressed_row(self):
        report = repair.verify(ROOT)
        self.assertEqual(report["archive"]["members"], 2)
        _, entries, _ = repair.prepare(ROOT, self.manifest)
        for _, _, prefix, weight, _ in repair.SPECS:
            logical = f"master/gacha_odds/{prefix}_character_5.orderedmap"
            before = repair.codec.rawmap(next(iter(repair.codec.rawmap(
                repair.codec.read_effective(ROOT, self.base, logical)).values())))
            after = repair.codec.rawmap(next(iter(repair.codec.rawmap(entries[repair.codec.member(logical)]).values())))
            self.assertEqual(len(after), len(before) + 1)
            self.assertEqual([key for key in after if key in before], list(before))
            for key, raw in before.items():
                self.assertEqual(after[key], raw)
            added = [repair.leaf(raw) for key, raw in after.items() if key not in before]
            self.assertEqual(added, [["179981", "5", str(weight), "true", "true", "true", "false"]])

    def test_rejects_unknown_boolean_instead_of_publishing_a_native_parser_failure(self):
        with self.assertRaisesRegex(ValueError, "Boolean"):
            repair.leaf(repair.codec.encode_leaf("179981,5,1000,true,true,,false\n"))

    def test_rejects_rebuilding_against_a_different_base(self):
        wrong = copy.deepcopy(self.base)
        wrong["cdn_version"] = "1.4.354"
        with self.assertRaisesRegex(ValueError, "1.4.355"):
            repair.prepare(ROOT, wrong)

    def test_rejects_unexpected_existing_target_in_base(self):
        original = repair.codec.read_effective

        def injected(root, manifest, logical):
            raw = original(root, manifest, logical)
            if manifest["cdn_version"] == repair.BASE:
                outer = repair.codec.rawmap(raw)
                name = next(iter(outer))
                rows = repair.codec.rawmap(outer[name])
                rows["unexpected"] = repair.codec.encode_leaf("179981,5,1000,true,true,true,false\n")
                return repair.codec.packmap({name: repair.codec.packmap(rows)})
            return raw

        with patch.object(repair.codec, "read_effective", side_effect=injected):
            with self.assertRaisesRegex(ValueError, "already contains"):
                repair.prepare(ROOT, self.manifest)


if __name__ == "__main__":
    unittest.main()
