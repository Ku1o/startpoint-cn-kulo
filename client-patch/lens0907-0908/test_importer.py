"""Regressions for constant relocation and preservation of existing branches."""
import unittest
from types import SimpleNamespace
from build_swf import Importer, insertion_proof


class ConstantTests(unittest.TestCase):
    def importer(self, **pools):
        view = SimpleNamespace(a=SimpleNamespace(**pools), labels={})
        return Importer(view, view)

    def test_empty_string_default_does_not_become_reserved_zero(self):
        imp = self.importer(strings=[b'', b'other', b''])
        self.assertEqual(imp.append('strings', b''), 2)

    def test_zero_constant_does_not_alias_parser_sentinel(self):
        imp = self.importer(doubles=[0.0], ints=[0], uints=[0])
        for pool in ('doubles', 'ints', 'uints'):
            self.assertEqual(imp.append(pool, 0), 1)
            self.assertEqual(imp.append(pool, 0), 1)
        self.assertEqual(imp.append('doubles', -0.0), 2)


def row(op, target=None):
    return (op, [], target, None, None)


class ControlFlowTests(unittest.TestCase):
    def test_reject_changed_live_jump(self):
        with self.assertRaisesRegex(AssertionError, 'live branch changed'):
            insertion_proof(([row(0x10, 1), row(0x47)], []),
                            ([row(0x10, 0), row(0x47)], []), [])

    def test_allow_canonicalized_dead_jump(self):
        insertion_proof(([row(0x47), row(0x10, 0)], []),
                        ([row(0x47), row(0x10, 1)], []), [])

    def test_exception_handler_is_reachable(self):
        with self.assertRaisesRegex(AssertionError, 'live branch changed'):
            insertion_proof(([row(0x47), row(0x10, 0)], [(0, 1, 1, None, None)]),
                            ([row(0x47), row(0x10, 1)], [(0, 1, 1, None, None)]), [])


if __name__ == '__main__':
    unittest.main()
