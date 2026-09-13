"""Regress the real .107 preimage and serialized .108 resource candidate."""
import argparse
import copy
import json
from pathlib import Path
import unittest
import zipfile

import build_resources as build


class ResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = (WORK / 'before' / build.DEGREE).read_bytes()
        cls.manifest = json.loads((WORK / 'after' / build.AUDIT / 'degree-manifest.json').read_bytes())
        cls.degrees = cls.manifest['degrees']
        cls.archive_path = WORK / 'after/assets/asset-patch/active' / build.ARCHIVE
        with zipfile.ZipFile(cls.archive_path) as archive:
            cls.payload = {name: archive.read(name) for name in archive.namelist()}
        cls.after = cls.payload[build.assets.member(('common', build.assets.hrel(build.DEGREE)))]
        category = (WORK / 'before' / build.CATEGORY).read_bytes()
        cls.categories = set(build.assets.core.read_orderedmap_raw_rows_from_bytes(category).keys)

    def test_preserves_all_current_titles_as_compressed_bytes(self):
        old, _ = build.decoded_rows(self.before)
        new, rows = build.decoded_rows(self.after)
        self.assertEqual(len(old.keys), 1497)
        self.assertEqual(new.keys[:len(old.keys)], old.keys)
        self.assertEqual(new.rows[:len(old.rows)], old.rows)
        self.assertEqual(len(rows), 1545)
        for item in self.degrees:
            self.assertEqual(rows[str(item['degree_id'])], item['row'])

    def test_complete_replay_does_not_change_any_bytes(self):
        repeated, report = build.merge_degrees(self.after, self.degrees, self.categories)
        self.assertEqual(repeated, self.after)
        self.assertEqual(report['added_ids'], [])

    def test_existing_degree_with_different_content_is_rejected(self):
        changed = copy.deepcopy(self.degrees)
        changed[0]['row'][2] = 'different title'
        with self.assertRaisesRegex(ValueError, 'existing degree ID differs'):
            build.merge_degrees(self.after, changed, self.categories)

    def test_foreign_display_order_collision_is_rejected(self):
        table, _ = build.decoded_rows(self.before)
        row = list(self.degrees[0]['row'])
        row[0] = 'foreign_degree'
        row[8] = 'dynamic/degree/foreign_degree'
        table.keys.append('9999991')
        table.rows.append(build.zlib.compress(build.assets.core.write_csv_lines([row]).encode('utf-8')))
        foreign = build.assets.core.build_orderedmap_raw_rows(table)
        with self.assertRaisesRegex(ValueError, 'occupied string/order/image'):
            build.merge_degrees(foreign, self.degrees, self.categories)

    def test_invalid_category_or_broken_csv_cannot_be_published(self):
        with self.assertRaisesRegex(ValueError, 'invalid native degree row'):
            build.merge_degrees(self.before, self.degrees, self.categories - {'2'})
        for column in range(9):
            changed = copy.deepcopy(self.degrees)
            changed[-1]['row'][column] += '\n'
            with self.assertRaises(ValueError):
                build.merge_degrees(self.before, changed, self.categories)

    def test_all_stored_images_decode_to_the_reviewed_originals(self):
        for item in self.degrees:
            metadata = item['image']
            stored = self.payload[build.assets.member(('common', build.assets.hrel(metadata['logical'])))]
            self.assertEqual(stored[:8], build.assets.wf_assets.PNG_FAKE)
            self.assertEqual(build.sha(stored), metadata['stored_sha256'])
            standard = build.assets.wf_assets.png_decode_stored(stored)
            self.assertEqual(build.sha(standard), metadata['sha256'])
            self.assertEqual(build.validate_picture(standard, metadata), stored)
            with self.assertRaises(ValueError):
                build.assets.wf_assets.png_decode_stored(standard)
            with self.assertRaisesRegex(ValueError, 'stored picture SHA mismatch'):
                build.validate_picture(standard, {**metadata, 'stored_sha256': '0' * 64})

    def test_delta_has_only_49_common_resources_and_preserves_the_prior_chain(self):
        self.assertEqual(len(self.payload), 49)
        self.assertTrue(all(name.startswith('production/upload/') for name in self.payload))
        before = json.loads((WORK / 'manifest.before.json').read_bytes())
        after = json.loads((WORK / 'after/assets/asset-patch/manifest.json').read_bytes())
        self.assertEqual(after['patches'][:-1], before['patches'])
        self.assertEqual(before['cdn_version'], build.BASE)
        self.assertEqual(after['cdn_version'], build.TARGET)
        tail = after['patches'][-1]
        self.assertEqual(tail['depends_on'], build.BASE)
        self.assertEqual(tail['archive_integrity'][0]['sha256'], build.sha(self.archive_path.read_bytes()))
        self.assertEqual(build.deterministic_archive(self.payload), self.archive_path.read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    args, remaining = parser.parse_known_args()
    WORK = args.work
    unittest.main(argv=[__file__, *remaining])
