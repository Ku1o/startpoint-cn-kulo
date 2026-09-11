"""Regress source completeness and mutation boundaries against sparse real assets."""
import argparse
import copy
from pathlib import Path
import unittest
import zipfile
import prepare_content as p
import build_how_to_get_sources as publisher

WORK = None


class SourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chain = p.Chain()
        cls.before = {name: (WORK / 'before' / p.member(('common', p.hrel(name)))).read_bytes()
                      for name in [publisher.ITEM, publisher.SEARCH]}
        with zipfile.ZipFile(WORK / publisher.ARCHIVE) as archive:
            cls.after = {name: archive.read(p.member(('common', p.hrel(name)))) for name in cls.before}
        cls.sources = publisher.reward_sources(publisher.verify_server_contract())

    def read(self, name):
        return self.chain.get(('common', p.hrel(name)))

    def validate(self, after, sources=None):
        return publisher.validate_tables(self.before, after, sources or self.sources, self.read)

    def test_real_unindexed_preimage_fails_completeness(self):
        with self.assertRaises(AssertionError):
            self.validate({**self.after, publisher.SEARCH: self.before[publisher.SEARCH]})

    def test_serialized_package_preserves_originals_and_adds_all_sources(self):
        proof = self.validate(self.after)
        self.assertEqual(proof['new_search_keys'], 12)
        self.assertEqual(proof['new_source_rows'], 71)
        self.assertEqual(proof['description_rows'], 16)

    def test_removing_each_required_item_source_is_rejected(self):
        for key in self.sources:
            with self.subTest(item=key):
                rows = p.rawmap(self.after[publisher.SEARCH])
                del rows[key]
                with self.assertRaises(AssertionError):
                    self.validate({**self.after, publisher.SEARCH: p.packmap(rows)})

    def test_old_quest_source_cannot_be_rewritten(self):
        rows = p.rawmap(self.after[publisher.SEARCH])
        old_key = next(iter(p.rawmap(self.before[publisher.SEARCH])))
        del rows[old_key]
        with self.assertRaises((AssertionError, KeyError)):
            self.validate({**self.after, publisher.SEARCH: p.packmap(rows)})

    def test_item_icon_or_identity_changes_are_rejected(self):
        items = p.rawmap(self.after[publisher.ITEM])
        row = p.csvrows(items['10000143'])
        row[0][0] = '99999999'
        items['10000143'] = p.packcsv(row)
        with self.assertRaisesRegex(AssertionError, 'non-description'):
            self.validate({**self.after, publisher.ITEM: p.packmap(items)})

    def test_hidden_training_round_is_not_a_valid_source(self):
        sources = copy.deepcopy(self.sources)
        sources['2370097'] = [publisher.quest_row(700098, 16, 1)]
        after = publisher.build_tables(self.before, sources)
        with self.assertRaisesRegex(AssertionError, 'hidden/training'):
            self.validate(after, sources)

    def test_expected_yield_obeys_optional_slots_curves_and_exclusions(self):
        def expected(item, event, quest):
            return next(float(row[5]) for row in self.sources[str(item)]
                        if row[1] == str(event) and row[3] == str(quest))
        self.assertAlmostEqual(expected(2370099, 700099, 2), 3.24)
        self.assertAlmostEqual(expected(2370099, 700099, 29), 6.92)
        self.assertAlmostEqual(expected(999013, 700099, 29), 0.15)
        self.assertFalse(any(row[3] in ['5', '10', '15', '20', '25', '30']
                             for row in self.sources['999013']))
        self.assertAlmostEqual(expected(10000143, 700099, 30), 1.5)
        self.assertAlmostEqual(expected(2370101, 700099, 30), 1.2)

    def test_removing_previous_round_visibility_gate_is_rejected(self):
        rush = p.rawmap(self.read(publisher.RUSH))
        quests = p.rawmap(rush['700099'])
        row = p.csvrows(quests['30'])
        row[0][9:14] = ['(None)', '', '', '', '(None)']
        quests['30'] = p.packcsv(row)
        rush['700099'] = p.packmap(quests)
        changed = p.packmap(rush)
        with self.assertRaisesRegex(AssertionError, 'previous-round visibility gate'):
            publisher.validate_tables(self.before, self.after, self.sources,
                                      lambda n: changed if n == publisher.RUSH else self.read(n))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    WORK = args.work.resolve()
    unittest.main(argv=[__file__], verbosity=2)
