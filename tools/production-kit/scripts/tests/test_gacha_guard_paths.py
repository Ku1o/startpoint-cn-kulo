from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gacha_guard as guard


class PortableGuardPaths(unittest.TestCase):
    def test_uses_existing_repository_process_support(self):
        self.assertTrue(guard.SUPPORT.is_file())
        self.assertEqual(guard.SUPPORT.parent.name, 'client-background')

    def test_requires_explicit_output_root(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            guard.receipt_root()

    def test_default_and_explicit_receipt_directory(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {'STARPOINT_WORK_ROOT': root}, clear=True):
                self.assertEqual(guard.receipt_root(), Path(root).resolve() / 'gacha-resource-runs')
            with patch.dict(os.environ, {'STARPOINT_WORK_ROOT': root,
                                        'STARPOINT_GACHA_RECEIPTS': str(Path(root) / 'chosen')}, clear=True):
                self.assertEqual(guard.receipt_root(), Path(root).resolve() / 'chosen')

    def test_rejects_source_relative_and_protected_roots(self):
        repo = Path(guard.__file__).resolve().parents[3]
        for value in [str(repo / 'work'), str(repo.parent), str(repo.anchor), 'relative',
                      str(Path(tempfile.gettempdir()) / '.cdn' / 'outputs')]:
            with self.subTest(value=value), patch.dict(os.environ, {'STARPOINT_GACHA_RECEIPTS': value}, clear=True):
                with self.assertRaises(ValueError):
                    guard.receipt_root()


if __name__ == '__main__':
    unittest.main()
