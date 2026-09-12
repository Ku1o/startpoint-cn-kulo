"""Regression checks for the consolidated .106 acquisition resource package."""
import argparse
import copy
import math
import unittest
import zipfile
from pathlib import Path

import prepare_content as p
import complete_how_to_get_sources as fix
import fix_mech_item_sources as mech

WORK = None


class CompleteSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = {n: (WORK / 'before' / n).read_bytes() for n in [mech.SEARCH, mech.ITEM]}
        cls.runtime = p.readj(WORK / 'runtime-contract.json')
        with zipfile.ZipFile(WORK / mech.ARCHIVE) as archive:
            cls.after = {n: archive.read(p.member(('common', p.hrel(n)))) for n in cls.before}
        cls.expected, cls.groups = fix.required_sources(cls.runtime, cls.read)

    @staticmethod
    def read(name):
        return (WORK / 'effective' / name).read_bytes()

    def validate(self, after=None, runtime=None, read=None):
        return fix.validate(self.before, after or self.after, runtime or self.runtime, read or self.read)

    def test_original_and_eight_item_patch_fail_expanded_coverage(self):
        for index in [self.before[mech.SEARCH], self.read(mech.SEARCH)]:
            with self.assertRaises(AssertionError): self.validate({**self.after, mech.SEARCH: index})

    def test_serialized_result_covers_all_known_reward_pairs(self):
        proof = self.validate()
        self.assertEqual((proof['new_keys'], proof['changed_keys'], proof['appended_source_rows']), (11, 55, 152))
        self.assertEqual((proof['covered_items'], proof['covered_pairs'], proof['missing_expected_pairs']), (66, 223, 0))
        self.assertEqual(proof['preserved_old_source_rows'], 6186)

    def test_removing_any_added_pair_even_from_an_existing_key_fails(self):
        old = p.rawmap(self.before[mech.SEARCH])
        actual = p.rawmap(self.after[mech.SEARCH])
        checked = 0
        for key, raw in actual.items():
            count = len(p.csvrows(old[key])) if key in old else 0
            source = p.csvrows(raw)
            for index in range(count, len(source)):
                with self.subTest(item=key, ref=source[index][:5]):
                    rows = dict(actual)
                    rows[key] = p.packcsv(source[:index] + source[index + 1:])
                    with self.assertRaises(AssertionError): self.validate({**self.after, mech.SEARCH: p.packmap(rows)})
                checked += 1
        self.assertEqual(checked, 152)

    def test_fantasy_schedule_and_each_final_reward_are_indexed(self):
        self.assertEqual(self.groups['fantasy_fixed'], {'items': 43, 'pairs': 105})
        refs = {tuple(r[:5]): r for r in self.expected['99']}
        for stage, amount in [(4, 5), (9, 10), (14, 15), (15, 200)]:
            self.assertEqual(float(refs[('16', '700098', '', str(stage), str(700098000 + stage))][5]), amount)
        self.assertEqual(float(refs[('16', '700099', '', '30', '700099030')][5]), 1000)
        for key, amount in [('2370099', 100), ('10002', 2), ('12001', 2)]:
            row = next(r for r in self.expected[key] if r[:5] == ['16', '700099', '', '30', '700099030'])
            self.assertEqual(float(row[5]), amount)

    def test_random_pool_weights_include_selection_probability(self):
        for item in [52, 55, 58, 61, 64, 67]:
            row = next(r for r in self.expected[str(item)] if r[:5] == ['16', '700099', '', '30', '700099030'])
            self.assertTrue(math.isclose(float(row[5]), 325 * 2.5 / 6, rel_tol=1e-10))
        # The old single-member-only handling would drop these six sources.
        changed = copy.deepcopy(self.runtime)
        changed['rogue']['folder_clear_random'] = [r for r in changed['rogue']['folder_clear_random'] if len(r['pool']) == 1]
        with self.assertRaises(AssertionError): self.validate(runtime=changed)

    def test_every_first_ss_source_is_present_with_one_time_note(self):
        rows = self.expected['14040']
        self.assertEqual(len(rows), 28)
        self.assertEqual({int(r[4]) for r in rows}, set(range(1001, 1013)) | set(range(2001, 2017)))
        self.assertTrue(all(r[0] == '12' and r[5] == '0' for r in rows))
        note = p.csvrows(p.rawmap(self.after[mech.ITEM])['14040'])[0][5]
        self.assertIn('各关首次达到SS评价时获得3个，每关仅可领取一次', note)
        with self.assertRaises(AssertionError): self.validate({**self.after, mech.ITEM: self.before[mech.ITEM]})

    def test_ordinary_item_fields_and_old_sources_cannot_change(self):
        item = p.rawmap(self.after[mech.ITEM]); row = p.csvrows(item['14040'])
        row[0][4] = 'wrong/icon'; item['14040'] = p.packcsv(row)
        with self.assertRaises(AssertionError): self.validate({**self.after, mech.ITEM: p.packmap(item)})
        for key in ['1', '2370097', '10000144', '40402']:
            rows = p.rawmap(self.after[mech.SEARCH]); source = p.csvrows(rows[key]); source[0][5] = '999999'
            rows[key] = p.packcsv(source)
            with self.assertRaises(AssertionError): self.validate({**self.after, mech.SEARCH: p.packmap(rows)})

    def test_gate_removal_and_wrong_or_hidden_targets_are_rejected(self):
        for name, keys, columns in [(fix.RUSH, ['700098', '4'], (9, 14)),
                                   (fix.RUSH, ['700099', '30'], (9, 14)),
                                   (fix.EXPERT, ['2', '1'], (9, 14))]:
            def mutate(raw, path):
                if not path:
                    row = p.csvrows(raw); row[0][columns[0]:columns[1]] = ['(None)', '', '', '', '(None)']
                    return p.packcsv(row)
                rows = p.rawmap(raw); rows[path[0]] = mutate(rows[path[0]], path[1:]); return p.packmap(rows)
            changed = mutate(self.read(name), keys)
            with self.assertRaises(AssertionError): self.validate(read=lambda n: changed if n == name else self.read(n))
        for key, bad in [('40408', ['26', '1001', '', '1', '1001001', '0.1']),
                         ('14040', ['12', '2', '', '600', '2600', '0'])]:
            rows = p.rawmap(self.after[mech.SEARCH]); source = p.csvrows(rows[key]); source[-1] = bad; rows[key] = p.packcsv(source)
            with self.assertRaises(AssertionError): self.validate({**self.after, mech.SEARCH: p.packmap(rows)})
        runtime = copy.deepcopy(self.runtime); runtime['mode']['fixed']['16'] = [{'id': 1, 'count': 999}]
        with self.assertRaises(AssertionError): self.validate(runtime=runtime)

    def test_art_checks_distinguish_optional_small_icons_from_thumbnails(self):
        checks = fix.validate_thumbnails(self.read, self.expected)
        self.assertEqual(len(checks), 66)
        ordinary = next(x for x in checks if x['item'] == '1')
        self.assertFalse(ordinary['small_icon_present'])
        self.assertTrue(ordinary['size'][0] > 0)
        required_small = [x['item'] for x in checks if x['small_icon_present']]
        self.assertEqual(len(mech.validate_icons(self.read, required_small)), 45)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    WORK = parser.parse_args().work.resolve()
    unittest.main(argv=[__file__], verbosity=2)
