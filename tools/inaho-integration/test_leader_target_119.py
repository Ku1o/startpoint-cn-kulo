"""Regress the real published C7050 preimage and sparse repair boundary."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import build_redesign_118 as base
import fix_leader_target_119 as fix


class LeaderTargetRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent/'fixtures/leader-empty-target.orderedmap'
        receipt = json.loads(fixture.with_suffix('.orderedmap.json').read_text('utf-8'))
        cls.raw = fixture.read_bytes()
        assert hashlib.sha256(cls.raw).hexdigest() == receipt['sha256']
        assert receipt['source_archive_sha256'] == fix.PREVIOUS_ARCHIVE_SHA
        _, table = base.raw_map(cls.raw, base.LEADER)
        cls.rows = base.core.read_csv_lines(base.ql.parse_node(table['159991']))

    def test_published_empty_target_is_rejected(self):
        self.assertEqual(self.rows[15][46], '')
        with self.assertRaisesRegex(AssertionError, 'explicitly be Myself'):
            base.check_combo_gauge(self.rows)

    def test_wrong_party_target_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[15][46] = '5'
        with self.assertRaisesRegex(AssertionError, 'explicitly be Myself'):
            base.check_combo_gauge(rows)
        with self.assertRaisesRegex(AssertionError, 'Unexpected existing gauge target'):
            fix.repair(base.pack_changes(self.raw, base.LEADER, {'159991': base.core.write_csv_lines(rows)}))

    def test_serialized_repair_changes_one_cell_and_is_idempotent(self):
        corrected = fix.repair(self.raw)
        self.assertEqual(corrected, fix.repair(corrected))
        _, before = base.raw_map(self.raw, base.LEADER)
        _, after = base.raw_map(corrected, base.LEADER)
        self.assertEqual([k for k in before if before[k] != after[k]], ['159991'])
        rows = base.core.read_csv_lines(base.ql.parse_node(after['159991']))
        expected = copy.deepcopy(self.rows)
        expected[15][46] = '0'
        self.assertEqual(rows, expected)
        base.check_combo_gauge(rows)


if __name__ == '__main__': unittest.main()
