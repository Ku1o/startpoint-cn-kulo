"""ETC2 RGBA alpha vectors derived independently from Khronos Data Format 1.4.

Section 22.3, Tables 22.5/22.6, printed pp. 244-245:
https://registry.khronos.org/DataFormat/specs/1.4/dataformat.1.4.pdf
These tests never obtain expected values from wf_atf's decoder/modifier table.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wf_atf


# Independent transcription of normative Table 22.6 for checking encoder output.
SPEC_MODIFIERS = (
    (-3, -6, -9, -15, 2, 5, 8, 14),
    (-3, -7, -10, -13, 2, 6, 9, 12),
    (-2, -5, -8, -13, 1, 4, 7, 12),
    (-2, -4, -6, -13, 1, 3, 5, 12),
    (-3, -6, -8, -12, 2, 5, 7, 11),
    (-3, -7, -9, -11, 2, 6, 8, 10),
    (-4, -7, -8, -11, 3, 6, 7, 10),
    (-3, -5, -8, -11, 2, 4, 7, 10),
    (-2, -6, -8, -10, 1, 5, 7, 9),
    (-2, -5, -8, -10, 1, 4, 7, 9),
    (-2, -4, -8, -10, 1, 3, 7, 9),
    (-2, -5, -7, -10, 1, 4, 6, 9),
    (-3, -4, -7, -10, 2, 3, 6, 9),
    (-1, -2, -3, -10, 0, 1, 2, 9),
    (-4, -6, -8, -9, 3, 5, 7, 8),
    (-3, -5, -7, -9, 2, 4, 6, 8),
)


def spec_decode_column_major(block):
    """Reference bit positions in one big-endian word, not production helpers."""
    word = int.from_bytes(block, 'big')
    base = (word >> 56) & 255
    multiplier = (word >> 52) & 15
    modifiers = SPEC_MODIFIERS[(word >> 48) & 15]
    return tuple(max(0, min(255, base + multiplier * modifiers[(word >> bit) & 7]))
                 for bit in range(45, -1, -3))


class TestEacAlphaSpecification(unittest.TestCase):
    def test_khronos_worked_example(self):
        # Normative example: base 103, table 13, multiplier 2, selector 3.
        # 103 + (-10)*2 = 83. Repeated 011 selectors pack to 6db6db6db6db.
        self.assertEqual(wf_atf.decode_eac_alpha(
            bytes.fromhex('672d6db6db6db6db'), 4, 4), bytearray([83] * 16))

    def test_all_selectors_and_pixel_order(self):
        # 01234567 repeated in column-major order pack to 053977053977.
        # Table 13 gives 103 + 2*(-1,-2,-3,-10,0,1,2,9).
        expected_rows = [101, 103, 101, 103,
                         99, 105, 99, 105,
                         97, 107, 97, 107,
                         83, 121, 83, 121]
        self.assertEqual(wf_atf.decode_eac_alpha(
            bytes.fromhex('672d053977053977'), 4, 4), bytearray(expected_rows))

    def test_clamp_both_ends(self):
        for vector, column in (
                ('04f0053977053977', [0, 0, 0, 0, 34, 79, 124, 214] * 2),
                ('faf0053977053977', [205, 160, 115, 25, 255, 255, 255, 255] * 2)):
            with self.subTest(vector=vector):
                rows = [column[x * 4 + y] for y in range(4) for x in range(4)]
                self.assertEqual(wf_atf.decode_eac_alpha(
                    bytes.fromhex(vector), 4, 4), bytearray(rows))

    def test_decoder_accepts_zero_multiplier_for_every_table(self):
        # Alpha uses zero literally, unlike the distinct R11 EAC format.
        for table in range(16):
            with self.subTest(table=table):
                block = bytes((103, table)) + bytes.fromhex('053977053977')
                self.assertEqual(wf_atf.decode_eac_alpha(block, 4, 4), bytearray([103] * 16))

    def test_encoder_matches_external_representable_vector(self):
        values = (101, 99, 97, 83, 103, 105, 107, 121) * 2
        encoded = wf_atf._encode_eac_alpha_block(values)
        self.assertGreater(encoded[1] >> 4, 0)
        self.assertEqual(spec_decode_column_major(encoded), values)

    def test_encoder_constants_never_emit_zero_multiplier(self):
        for alpha in range(256):
            with self.subTest(alpha=alpha):
                encoded = wf_atf._encode_eac_alpha_block((alpha,) * 16)
                self.assertGreater(encoded[1] >> 4, 0)
                self.assertEqual(spec_decode_column_major(encoded), (alpha,) * 16)

    def test_legal_constant_rewrite_preserves_legacy_zero_intent(self):
        # A legacy zero-multiplier block intended a flat base. A standard block
        # can preserve that intent using table 13 / multiplier 1 / selector 4.
        for alpha in (0, 1, 103, 137, 254, 255):
            with self.subTest(alpha=alpha):
                rewritten = bytes((alpha, 0x1d)) + bytes.fromhex('924924924924')
                self.assertEqual(spec_decode_column_major(rewritten), (alpha,) * 16)
                self.assertEqual(wf_atf.decode_eac_alpha(rewritten, 4, 4), bytearray([alpha] * 16))


if __name__ == '__main__':
    unittest.main(verbosity=2)
