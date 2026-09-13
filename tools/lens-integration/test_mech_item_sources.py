"""Check real sparse preimages and reject missing or incorrectly routed rewards."""
import argparse
import copy
import unittest
import zipfile
from pathlib import Path

import prepare_content as p
import fix_mech_item_sources as repair

WORK = None


class MechItemSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = p.readj(WORK / 'runtime-contract.json')
        cls.before = (WORK / 'before' / repair.SEARCH).read_bytes()
        with zipfile.ZipFile(WORK / repair.ARCHIVE) as archive:
            cls.after = archive.read(p.member(('common', p.hrel(repair.SEARCH))))

    def read(self, name):
        return (WORK / 'before' / name).read_bytes()

    def validate(self, after=None, runtime=None, read=None):
        return repair.validate_index(self.before, after or self.after,
                                     runtime or self.runtime, read or self.read)

    def test_real_preimage_fails_and_serialized_fix_passes(self):
        with self.assertRaises(AssertionError):
            self.validate(self.before)
        self.assertEqual(self.validate(), dict(preserved_search_keys=507, new_search_keys=8, new_source_rows=8))

    def test_removing_any_one_material_is_rejected(self):
        for item in repair.TARGETS:
            with self.subTest(item=item):
                rows = p.rawmap(self.after)
                del rows[item]
                with self.assertRaises(AssertionError): self.validate(p.packmap(rows))

    def test_wrong_enum_color_or_historical_quest_is_rejected(self):
        for column, value in [(0, '26'), (1, '1002'), (1, '1'), (4, '1002001')]:
            with self.subTest(column=column, value=value):
                rows = p.rawmap(self.after)
                source = p.csvrows(rows['40408'])
                source[0][column] = value
                rows['40408'] = p.packcsv(source)
                with self.assertRaises(AssertionError): self.validate(p.packmap(rows))

    def test_existing_fantasy_abyss_five_boss_and_gear_sources_are_immutable(self):
        for item in ['2370097', '2370099', '10000143', '10000144', '40402']:
            with self.subTest(item=item):
                rows = p.rawmap(self.after)
                source = p.csvrows(rows[item])
                source[0][5] = '9999'
                rows[item] = p.packcsv(source)
                with self.assertRaisesRegex(AssertionError, 'existing source'): self.validate(p.packmap(rows))

    def test_runtime_reward_removal_or_winning_source_drift_is_rejected(self):
        for item, (quest_id, _, _) in repair.TARGETS.items():
            with self.subTest(item=item):
                runtime = copy.deepcopy(self.runtime)
                runtime['quests'][str(quest_id)]['scoreRewardGroup'] = []
                with self.assertRaises(AssertionError): self.validate(runtime=runtime)
        runtime = copy.deepcopy(self.runtime)
        runtime['rare']['700010'][0]['id'] = 40409
        with self.assertRaises(AssertionError): self.validate(runtime=runtime)

    def test_client_reward_pool_drift_is_rejected(self):
        rows = p.rawmap(self.read(repair.RARE))
        inner = p.rawmap(rows['700010'])
        reward = p.csvrows(inner['1'])
        reward[0][2] = '40409'
        inner['1'] = p.packcsv(reward)
        rows['700010'] = p.packmap(inner)
        raw = p.packmap(rows)
        with self.assertRaises(AssertionError):
            self.validate(read=lambda name: raw if name == repair.RARE else self.read(name))

    def test_story_and_previous_difficulty_gates_must_remain(self):
        for name, keys in [(repair.HARD, ['1001', '1']), (repair.BOSS, ['1', '60', '5'])]:
            def mutate(raw, path):
                if not path:
                    rows = p.csvrows(raw)
                    rows[0][7:12] = ['(None)', '', '', '', '(None)']
                    return p.packcsv(rows)
                rows = p.rawmap(raw)
                rows[path[0]] = mutate(rows[path[0]], path[1:])
                return p.packmap(rows)
            changed = mutate(self.read(name), keys)
            with self.subTest(table=name), self.assertRaisesRegex(AssertionError, 'gate drift'):
                self.validate(read=lambda n: changed if n == name else self.read(n))

    def test_all_seventeen_material_icons_are_preloaded(self):
        proof = repair.validate_icons(self.read)
        self.assertEqual(len(proof), 17)
        name = proof[0]['atlas'] + '.atlas.amf3.deflate'
        rows = repair.icons.codec.decode_atlas(self.read(name))
        # A valid atlas lacking a required frame must fail, even if a standalone
        # PNG still exists. Patch the decoder output without changing production.
        from unittest.mock import patch
        decode = repair.icons.codec.decode_atlas
        missing = [r for r in rows if r['n'] != proof[0]['icon']]
        raw = self.read(name)
        with patch.object(repair.icons.codec, 'decode_atlas', side_effect=lambda b: missing if b == raw else decode(b)):
            with self.assertRaisesRegex(AssertionError, 'not preloaded'): repair.validate_icons(self.read)

    def test_whole_score_inventory_separates_unreferenced_legacy_tokens(self):
        audit = repair.audit_unindexed(self.read)
        self.assertEqual(set(audit) - set(repair.TARGETS), {'2370002', '2370003', '2370004', '2370007'})
        self.assertTrue(all(not v['referenced_by_quest_score_group'] for k, v in audit.items() if k not in repair.TARGETS))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    WORK = parser.parse_args().work.resolve()
    unittest.main(argv=[__file__], verbosity=2)
