"""Real missing-row regression; no game or desktop AIR process is launched."""
import copy
import unittest

import restore_kyubi_afterglow as fix


class KyubiAfterglowTests(unittest.TestCase):
    def setUp(self):
        _, data = fix.fixture()
        self.before_leaf = data['leader_before']
        self.before_rows = fix.p.csvrows(self.before_leaf)
        self.ability_rows = fix.p.csvrows(data['ability1'])
        self.ability = fix.p.packmap({'1399951': data['ability1']})
        self.unrelated = fix.p.packcsv([['keep', 'all', 'bytes']])
        self.before = fix.p.packmap({'12': self.unrelated, fix.KEY: self.before_leaf, '13': self.unrelated})

    def test_actual_deleted_row_fails_two_source_contract(self):
        self.assertEqual(len(fix.stack_rows(self.before_rows, 'leader_ability')), 0)
        self.assertEqual(len(fix.stack_rows(self.ability_rows, 'ability')), 1)
        with self.assertRaisesRegex(AssertionError, 'leader must have exactly one'):
            fix.validate_stacks(self.before_rows, self.ability_rows)

    def test_restores_leader_source_without_deduplicating_ability(self):
        after = fix.restore(self.before, self.ability)
        parsed = fix.p.rawmap(after)
        self.assertEqual(list(parsed), ['12', fix.KEY, '13'])
        self.assertEqual(parsed['12'], self.unrelated)
        self.assertEqual(parsed['13'], self.unrelated)
        rows = fix.p.csvrows(parsed[fix.KEY])
        self.assertEqual(rows[:-1], self.before_rows)
        self.assertEqual(rows[-1][3:], self.ability_rows[3][5:])
        fix.validate_stacks(rows, self.ability_rows)
        self.assertEqual(fix.restore(after, self.ability), after)

    def test_rejects_unknown_balance_changes_in_target(self):
        changed = copy.deepcopy(self.before_rows)
        changed[2][111] = '50000'
        raw = fix.p.packmap({fix.KEY: fix.p.packcsv(changed)})
        with self.assertRaisesRegex(AssertionError, 'unknown Kyubi preimage'):
            fix.restore(raw, self.ability)

    def test_rejects_missing_or_changed_ability_source(self):
        for rows in [self.ability_rows[:3]+self.ability_rows[4:], copy.deepcopy(self.ability_rows)]:
            if len(rows) == 6:
                rows[3][51] = '200000'
            ability = fix.p.packmap({'1399951': fix.p.packcsv(rows)})
            with self.assertRaisesRegex(AssertionError, 'ability .* source drift'):
                fix.restore(self.before, ability)

    def test_rejects_extra_leader_stack_and_preserves_99_cap_reference(self):
        rows = fix.p.csvrows(fix.p.rawmap(fix.restore(self.before, self.ability))[fix.KEY])
        self.assertEqual(rows[-1][66], '1399952')
        rows.append(rows[-1][:])
        with self.assertRaisesRegex(AssertionError, 'leader must have exactly one'):
            fix.validate_stacks(rows, self.ability_rows)


if __name__ == '__main__':
    unittest.main()
