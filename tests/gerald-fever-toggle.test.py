"""Resource contract regressions for the 1.4.354 Water Gerald ability-3 repair."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

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

    def verify_variant(self, entries, edit_receipt=None):
        """Verify an isolated archive against the real enabled pre-repair chain."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as target:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(name, (2026, 11, 2, 12, 0, 0))
                target.writestr(info, data)
        raw = buf.getvalue()
        manifest = copy.deepcopy(self.manifest)
        patch = next(p for p in manifest["patches"] if p["version"] == repair.VERSION)
        patch["archive_size"] = len(raw)
        patch["archive_integrity"][0].update(size=len(raw), sha256=repair.sha(raw))
        if edit_receipt:
            edit_receipt(patch)
        read_effective = repair.read_effective
        with tempfile.TemporaryDirectory(prefix="gerald-contract-") as directory:
            root = Path(directory)
            archive = root / "assets/asset-patch/active" / repair.ARCHIVE
            archive.parent.mkdir(parents=True)
            archive.write_bytes(raw)
            with mock.patch.object(repair, "read_effective", side_effect=lambda _, m, lp: read_effective(ROOT, m, lp)):
                return repair.verify_manifest(root, manifest)

    def test_alternate_target_and_index_compression_and_zip_wrapper_are_accepted(self):
        entries = dict(self.entries)
        for logical, key in ((repair.ABILITY_LP, repair.ABILITY_KEY), (repair.CAS_LP, repair.CAS_KEY)):
            name = repair.member(logical)
            rows = repair.rawmap(entries[name])
            original = rows[key]
            rows[key] = zlib.compress(repair.decode_leaf(original).encode("utf-8"), level=0)
            self.assertNotEqual(rows[key], original)
            packed = repair.packmap(rows)
            size = struct.unpack_from("<I", packed)[0]
            index = zlib.compress(zlib.decompress(packed[4:4 + size]), level=0)
            entries[name] = struct.pack("<I", len(index)) + index + packed[4 + size:]
        self.assertEqual(self.verify_variant(entries)["members"], 2)

    def test_target_text_tampering_is_rejected_with_updated_receipt(self):
        for logical, key in ((repair.ABILITY_LP, repair.ABILITY_KEY), (repair.CAS_LP, repair.CAS_KEY)):
            with self.subTest(logical=logical):
                entries = dict(self.entries)
                name = repair.member(logical)
                rows = repair.rawmap(entries[name])
                rows[key] = repair.encode_leaf(repair.decode_leaf(rows[key]) + "tampered")
                entries[name] = repair.packmap(rows)
                with self.assertRaisesRegex(ValueError, "target leaf text"):
                    self.verify_variant(entries)

    def test_unrelated_leaf_recompression_is_rejected_even_with_same_text(self):
        for logical, target_key in ((repair.ABILITY_LP, repair.ABILITY_KEY), (repair.CAS_LP, repair.CAS_KEY)):
            with self.subTest(logical=logical):
                entries = dict(self.entries)
                name = repair.member(logical)
                rows = repair.rawmap(entries[name])
                key = next(k for k, leaf in rows.items() if k != target_key and leaf)
                original = rows[key]
                rows[key] = zlib.compress(repair.decode_leaf(original).encode("utf-8"), level=0)
                self.assertNotEqual(rows[key], original)
                self.assertEqual(repair.decode_leaf(rows[key]), repair.decode_leaf(original))
                entries[name] = repair.packmap(rows)
                with self.assertRaisesRegex(ValueError, "Unrelated orderedmap leaf bytes"):
                    self.verify_variant(entries)

    def test_wrong_sha_and_unexpected_member_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "archive/manifest"):
            self.verify_variant(self.entries, lambda p: p["archive_integrity"][0].update(sha256="0" * 64))
        entries = dict(self.entries)
        entries["production/upload/unexpected"] = b"extra"
        with self.assertRaisesRegex(ValueError, "ZIP integrity"):
            self.verify_variant(entries)

    def test_orderedmap_key_removal_or_reorder_is_rejected(self):
        name = repair.member(repair.ABILITY_LP)
        original_rows = repair.rawmap(self.entries[name])
        for mutation in ("remove", "reverse"):
            with self.subTest(mutation=mutation):
                entries = dict(self.entries)
                rows = dict(original_rows)
                if mutation == "remove":
                    rows.pop(next(iter(rows)))
                else:
                    rows = dict(reversed(list(rows.items())))
                entries[name] = repair.packmap(rows)
                with self.assertRaisesRegex(ValueError, "key order or key set"):
                    self.verify_variant(entries)

    def test_trailing_or_truncated_target_stream_is_rejected(self):
        name = repair.member(repair.ABILITY_LP)
        for mutation in (lambda leaf: leaf + b"trailing", lambda leaf: leaf[:-1]):
            with self.subTest(mutation=mutation):
                entries = dict(self.entries)
                rows = repair.rawmap(entries[name])
                rows[repair.ABILITY_KEY] = mutation(rows[repair.ABILITY_KEY])
                entries[name] = repair.packmap(rows)
                with self.assertRaisesRegex(ValueError, "leaf stream"):
                    self.verify_variant(entries)

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
