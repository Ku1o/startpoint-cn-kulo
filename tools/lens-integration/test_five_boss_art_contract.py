"""Regress the actual .110 device failures against sparse before/after assets."""
import argparse
from pathlib import Path
import unittest
import prepare_content as p
import five_boss_art_contract as contract
import update_five_boss_item_art as publisher

WORK=None


class DisplayContracts(unittest.TestCase):
    def before(self,name):
        path=WORK/'before'/name
        return path.read_bytes() if path.is_file() else None

    def final(self,name):
        path=WORK/'after'/name
        return path.read_bytes() if path.is_file() else self.before(name)

    def test_real_twenty_pixel_material_bar_is_rejected(self):
        with self.assertRaisesRegex(AssertionError,'material bar needs 40x40'):
            contract.validate_display(self.before)

    def test_enlarged_weapon_is_rejected_even_with_fixed_materials(self):
        name='item/equipment/mod/five_boss/deathbringer_final_lv0.png'
        with self.assertRaisesRegex(AssertionError,'detail thumbnail oversized'):
            contract.validate_display(lambda n:self.before(n) if n==name else self.final(n))

    def test_missing_full_canvas_frame_is_rejected(self):
        with self.assertRaisesRegex(AssertionError,'missing thumbnail frame'):
            contract.validate_display(lambda n:self.before(n) if n==contract.TRIM else self.final(n))

    def test_corrected_serialized_assets_fit_both_readers(self):
        proof=contract.validate_display(self.final)
        self.assertEqual(proof['material_size'],[40,40])
        self.assertEqual(proof['rendered_thumbnail_size'],[120,120])
        self.assertLess(proof['rendered_thumbnail_size'][0],proof['native_frame_size'])

    def test_publisher_cannot_regress_corrected_icons_on_rebuild(self):
        originals={p.name:p.read_bytes() for p in publisher.ART.glob('*.png')}
        result=contract.make_resources(self.final,originals,publisher.replace_frames)
        self.assertEqual(result['resources'],{})

    def test_atlas_variable_cannot_be_a_patch_dependency(self):
        old=p.readj(p.REPO/'assets/asset-patch/audit/five-boss-item-art-1.4.110-test/manifest.json')
        with self.assertRaisesRegex(AssertionError,'invalid dependency'):
            contract.validate_manifest(old)
        final=p.readj(WORK/'candidate-server/assets/asset-patch/manifest.json')
        contract.validate_manifest(final)
        self.assertEqual(final['patches'][-1]['depends_on'],'1.4.110')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();WORK=args.work.resolve()
    unittest.main(argv=[__file__],verbosity=2)
