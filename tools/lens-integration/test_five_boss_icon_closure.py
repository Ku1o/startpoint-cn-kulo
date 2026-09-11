"""Validate real sparse before/after bytes, including the reported C8004 case."""
import argparse
from pathlib import Path
import unittest

import fix_five_boss_icon_closure as fix


class IconClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def read(directory, logical):
            return (WORK / directory / fix.p.member(('common', fix.p.hrel(logical)))).read_bytes()
        cls.before = {base + suffix: read('before', base + suffix)
                      for base in fix.PRELOADED for suffix in fix.SUFFIXES}
        cls.blobs = {base + suffix: read('prepared', base + suffix)
                     for base in fix.CHANGED for suffix in fix.SUFFIXES}
        tables = {name: read('before', name) for name in (fix.ITEM, fix.STAGE, fix.SHOP)}
        cls.required = fix.requirements(tables)
        cls.atlases = {base: fix.codec.decode_atlas(cls.before[base + fix.SUFFIXES[1]])
                       for base in fix.PRELOADED}
        cls.icons = {base: {} for base in fix.CHANGED}
        for row in fix.missing_icons(cls.required, cls.atlases):
            base = next(base for base in fix.CHANGED if row['icon'].startswith(base.split('/')[0] + '/'))
            cls.icons[base][row['icon']] = read('before', row['icon'] + '.png')

    def test_all_pages_icons_and_original_pixels_preserved(self):
        fix.validate_bundle(self.blobs, self.before, self.required, self.icons)

    def test_real_preimage_fails_despite_valid_standalone_pngs(self):
        for icons in self.icons.values():
            for raw in icons.values():
                fix.strict_png(raw)
        self.assertEqual({r['id'] for r in fix.missing_icons(self.required, self.atlases)},
                         {10000144, 10000145, 10000146, 10000147})
        with self.assertRaisesRegex(AssertionError, 'small icons not preloaded'):
            fix.validate_closure(self.required, self.atlases)

    def test_removing_any_one_material_frame_fails(self):
        for base, icons in self.icons.items():
            logical = base + fix.SUFFIXES[1]
            for name in icons:
                with self.subTest(icon=name):
                    broken = dict(self.blobs)
                    rows = fix.codec.decode_atlas(broken[logical])
                    broken[logical] = fix.codec.encode_atlas([row for row in rows if row['n'] != name])
                    with self.assertRaisesRegex(AssertionError, 'small icons not preloaded'):
                        fix.validate_bundle(broken, self.before, self.required, self.icons)

    def test_old_pixel_damage_is_rejected(self):
        broken = dict(self.blobs)
        logical = 'item/sprite_sheet.png'
        im = fix.strict_png(broken[logical])
        color = im.getpixel((0, 0))
        im.putpixel((0, 0), (color[0] ^ 1, *color[1:]))
        broken[logical] = fix.codec.encode_png(im)
        with self.assertRaisesRegex(AssertionError, 'old pixels changed'):
            fix.validate_bundle(broken, self.before, self.required, self.icons)

    def test_old_metadata_damage_is_rejected(self):
        broken = dict(self.blobs)
        logical = 'item/sprite_sheet.atlas.amf3.deflate'
        rows = fix.codec.decode_atlas(broken[logical])
        rows[0]['x'] += 1
        broken[logical] = fix.codec.encode_atlas(rows)
        with self.assertRaisesRegex(AssertionError, 'old frame metadata changed'):
            fix.validate_bundle(broken, self.before, self.required, self.icons)

    def test_missing_atlas_pair_member_is_rejected(self):
        broken = dict(self.blobs)
        del broken['item_icon/sprite_sheet.png']
        with self.assertRaisesRegex(AssertionError, 'unexpected resource set'):
            fix.validate_bundle(broken, self.before, self.required, self.icons)

    def test_plain_png_rejected_by_client_storage_contract(self):
        broken = dict(self.blobs)
        logical = 'item/sprite_sheet.png'
        broken[logical] = fix.p.wf_assets.png_decode_stored(broken[logical])
        with self.assertRaises(ValueError):
            fix.validate_bundle(broken, self.before, self.required, self.icons)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    args, remaining = parser.parse_known_args()
    WORK = args.work
    unittest.main(argv=[__file__, *remaining])
