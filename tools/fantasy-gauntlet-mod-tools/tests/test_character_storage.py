import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wf_character_storage import is_scaled_character_png, missing_character_image_roots


class CharacterStorageTests(unittest.TestCase):
    def test_common_only_images_are_not_native_reader_closure(self):
        images = ['character/test/ui/full_shot_1440_1920_0.png',
                  'character/test/ui/illustration_setting_sprite_sheet.png',
                  'character/test/ui/square_0.png']
        wrong = [('upload', p) for p in images]
        self.assertEqual(len(missing_character_image_roots(images, wrong)), 6)
        repaired = wrong + [(root, p) for root in ['medium_upload', 'small_upload'] for p in images]
        self.assertEqual(missing_character_image_roots(images, repaired), [])
        repaired.remove(('medium_upload', images[1]))
        self.assertEqual(missing_character_image_roots(images, repaired), [('medium_upload', images[1])])

    def test_platform_cutins_atlas_data_and_pixel_art_keep_their_roots(self):
        for p in ['character/test/ui/skill_cutin_0.png',
                  'character/test/ui/illustration_setting_sprite_sheet.atlas.amf3.deflate',
                  'character/test/pixelart/sprite_sheet.png']:
            self.assertFalse(is_scaled_character_png(p))


if __name__ == '__main__':
    unittest.main()
