"""Regression for C8105: an editor-readable PNG is not a stored client PNG."""
import io
import unittest

from PIL import Image

import wf_assets
from publish_shop_banner_png_encoding_1_4_101 import repair_banner


def ordinary_png(mode):
    output = io.BytesIO()
    with Image.new(mode, (7, 5), (24, 100, 201, 67) if mode == "RGBA" else (24, 100, 201)) as image:
        image.save(output, format="PNG")
    return output.getvalue()


class PNGStorageTests(unittest.TestCase):
    def test_rejects_ordinary_png_that_editor_accepts(self):
        raw = ordinary_png("RGB")
        self.assertEqual(raw, wf_assets.png_decode(raw))
        with self.assertRaisesRegex(ValueError, "signature error: not png file"):
            wf_assets.png_decode_stored(raw)

    def test_rejects_invalid_and_truncated_signatures(self):
        for raw in (b"", wf_assets.PNG_FAKE[:7], b"not png!", b"\x00" + wf_assets.PNG_FAKE[1:]):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                wf_assets.png_decode_stored(raw)

    def test_repair_preserves_rgb_and_rgba_image_bytes(self):
        for mode in ("RGB", "RGBA"):
            with self.subTest(mode=mode):
                raw = ordinary_png(mode)
                stored = repair_banner(raw, (7, 5), mode)
                self.assertEqual(wf_assets.PNG_FAKE, stored[:8])
                self.assertEqual(raw[8:], stored[8:])
                self.assertEqual(raw, wf_assets.png_decode_stored(stored))

    def test_repair_rejects_wrong_size_mode_and_already_stored_input(self):
        raw = ordinary_png("RGBA")
        for data, size, mode in ((raw, (7, 6), "RGBA"), (raw, (7, 5), "RGB"),
                                 (wf_assets.png_encode(raw), (7, 5), "RGBA")):
            with self.subTest(size=size, mode=mode), self.assertRaises(ValueError):
                repair_banner(data, size, mode)


if __name__ == "__main__":
    unittest.main()
