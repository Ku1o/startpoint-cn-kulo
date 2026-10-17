"""Synthetic-key regression checks; never opens private pairing files."""
import unittest

from rotate_admission import replacement_contract, replace_exact


class AdmissionRotationTests(unittest.TestCase):
    def setUp(self):
        self.old_id = 'ios-184-author-1047-public-20261001'
        self.new_id = 'ios-184-pr43-compat-public-20261017'
        self.old_key, self.new_key = b'a' * 64, b'b' * 64

    def test_equal_length_full_and_native_rotation_is_exactly_reversible(self):
        replacements = replacement_contract(self.old_id, self.new_id, self.old_key, self.new_key)
        unit = b'unchanged-methods:' + self.old_id.encode() + b'|SP-ADMISSION-1\n' + self.old_id.encode() + b'\n|' + self.old_key
        updated = replace_exact(unit, replacements, [2, 1])
        self.assertEqual(len(updated), len(unit))
        self.assertNotIn(self.old_key, updated)
        self.assertIn(b'SP-ADMISSION-1\n' + self.new_id.encode() + b'\n', updated)
        native = b'native-prologue' + unit * 3 + b'native-epilogue'
        changed = replace_exact(native, replacements, [6, 3])
        self.assertTrue(changed.startswith(b'native-prologue') and changed.endswith(b'native-epilogue'))

    def test_unknown_occurrences_and_collisions_are_refused(self):
        replacements = replacement_contract(self.old_id, self.new_id, self.old_key, self.new_key)
        with self.assertRaisesRegex(ValueError, 'occurrence contract'):
            replace_exact(self.old_id.encode() + self.old_key, replacements, [2, 1])
        with self.assertRaisesRegex(ValueError, 'occurrence contract'):
            replace_exact(self.old_id.encode() * 2 + self.old_key + self.new_id.encode(), replacements, [2, 1])

    def test_identifier_length_and_key_shape_cannot_bypass_contract(self):
        for new_id, new_key in [(self.new_id + '-x', self.new_key), (self.old_id, self.new_key),
                                (self.new_id, b'x' * 64), (self.new_id, self.old_key),
                                (self.new_id, b'b' * 63)]:
            with self.subTest(id_length=len(new_id), key_length=len(new_key)):
                with self.assertRaises(ValueError):
                    replacement_contract(self.old_id, new_id, self.old_key, new_key)


if __name__ == '__main__':
    unittest.main()
