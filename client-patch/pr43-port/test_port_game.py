"""Boundary tests for method replay and debug-aware bytecode checking."""
import copy
import types
import unittest

import port_game as game


class PrefixTests(unittest.TestCase):
    def setUp(self):
        self.common, self.core = game.dependencies()
        self.base = types.SimpleNamespace(instances=[], classes=[], scripts=[], methods=[], metadata=[],
            ints=[0, 7], uints=[0], doubles=[0.0], strings=[b"", b"current-endpoint"],
            namespaces=[(0, 0)], ns_sets=[()], multinames=[(0,)])
        self.donor = copy.deepcopy(self.base)
        self.donor.strings[1] = b"donor-endpoint"
        self.plan = {"preserved_existing_string_indices": [1]}

    def test_pool_check_never_replaces_current_endpoint(self):
        self.donor.strings.append(b"new-path")
        result = game.check_prefix(self.base, self.donor, self.plan, self.common)
        self.assertEqual(result["strings"], 1)
        self.assertEqual(self.base.strings[1], b"current-endpoint")

    def test_existing_numeric_mutation_is_rejected(self):
        self.donor.ints[1] = 8
        with self.assertRaisesRegex(ValueError, "existing pool"):
            game.check_prefix(self.base, self.donor, self.plan, self.common)

    def test_new_private_namespace_in_prefix_is_rejected(self):
        self.base.namespaces.append((5, 1))
        self.donor.namespaces.append((5, 0))
        with self.assertRaisesRegex(ValueError, "existing pool"):
            game.check_prefix(self.base, self.donor, self.plan, self.common)

    def test_method_signature_change_is_rejected(self):
        self.donor.methods.append([0, [], 0, 0, None, None])
        with self.assertRaisesRegex(ValueError, "structure"):
            game.check_prefix(self.base, self.donor, self.plan, self.common)

    def test_new_instance_slot_is_rejected(self):
        self.donor.instances.append([0, 0, 0, None, [], 0, []])
        with self.assertRaisesRegex(ValueError, "structure"):
            game.check_prefix(self.base, self.donor, self.plan, self.common)

    def test_unknown_input_is_rejected_before_parsing(self):
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            game.apply_game(b"not-an-accepted-swf", b"not-a-donor")

    def test_debug_metadata_preserves_stack_and_raw_bytes(self):
        # debug(local-info), debugline, debugfile, bkptline, returnvoid.
        raw = bytes([0xEF, 1, 0, 0, 0, 0xF0, 1, 0xF1, 0, 0xF2, 1, 0x47])
        body = [0, 0, 1, 0, 0, raw, [], []]
        old = copy.deepcopy(self.common.asm._POP_PUSH)
        checked = game.validate_body(self.base, body, self.common, self.core)
        self.assertEqual(checked["debug_instructions"], 4)
        self.assertEqual(body[5], raw)
        self.assertEqual(self.common.asm._POP_PUSH, old)

    def test_debug_support_does_not_hide_stack_underflow(self):
        body = [0, 0, 1, 0, 0, bytes([0xEF, 1, 0, 0, 0, 0x29, 0x47]), [], []]
        with self.assertRaises(self.common.asm.AsmError):
            game.validate_body(self.base, body, self.common, self.core)


if __name__ == "__main__":
    unittest.main()
