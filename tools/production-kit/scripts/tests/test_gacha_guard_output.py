from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gacha_guard import cli_result


class GuardOutputTests(unittest.TestCase):
    def test_compact_result(self):
        self.assertEqual(cli_result('progress\n{"status":"ok","pages":4}\n'), {'status': 'ok', 'pages': 4})

    def test_native_pretty_result(self):
        self.assertEqual(cli_result('progress\n{\n  "pages": [1, 2],\n  "native": {"ok": true}\n}\n'),
                         {'pages': [1, 2], 'native': {'ok': True}})

    def test_truncated_result_does_not_invent_fields(self):
        self.assertIsNone(cli_result('"pages": [1, 2]\n}\n'))


if __name__ == '__main__':
    unittest.main()
