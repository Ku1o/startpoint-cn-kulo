import copy
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wf_abyss_tower_adjustments as adjust
import wf_rogue_build as rb
import wf_rogue_element_channel as channel


class TowerAdjustmentTests(unittest.TestCase):
    def test_thunder_removed_from_weak_and_combined_ban(self):
        picks = [
            {'name': '混相禁域', 'text': '雷光', 'element_resistance': [[3, 1, False], [5, 1, False]]},
            {'name': '保底', 'text': '雷光', 'element_ban_guarantee': True,
             'element_resistance': [[3, 998, False], [5, 998, False]]},
            {'name': '血量', 'text': '血量', 'hp': .85},
        ]
        before = copy.deepcopy(picks)
        clean, removed = adjust.remove_element(picks, 3)
        final, receipt = rb.guarantee_element_bans(clean, random.Random(9), excluded_elements=(3,))
        self.assertEqual(picks, before)
        self.assertEqual(len(removed), 2)
        self.assertEqual(final[2], before[2])
        totals = rb._resistance_totals_by_target(final, 'element_resistance')
        self.assertNotIn(3, totals)
        self.assertEqual(totals[5], 999)
        self.assertEqual(len(receipt['final_banned']), 2)
        self.assertEqual(channel.decode(channel.encode(totals)), totals)

    def test_keeps_all_five_rolled_bans_without_locking_thunder(self):
        picks = [{'name': '五属性', 'text': '五属性',
                  'element_resistance': [[e, 999, False] for e in (1, 2, 4, 5, 6)]}]
        for seed in range(30):
            final, receipt = rb.guarantee_element_bans(picks, random.Random(seed), excluded_elements=(3,))
            self.assertEqual(final, picks)
            self.assertEqual(receipt['final_banned'], [1, 2, 4, 5, 6])
            self.assertEqual(receipt['open_elements'], [3])

    def test_exclusion_requires_explicit_cleanup_and_valid_capacity(self):
        thunder = [{'name': '雷抗', 'text': '雷抗', 'element_resistance': [[3, 1, False]]}]
        with self.assertRaisesRegex(ValueError, '须先明确处理'):
            rb.guarantee_element_bans(thunder, random.Random(1), excluded_elements=(3,))
        with self.assertRaisesRegex(ValueError, '超过可选'):
            rb.guarantee_element_bans([], random.Random(1), minimum=5, excluded_elements=(1, 3))

    def test_pf_is_additive_after_merge_for_both_signs(self):
        for old, new in [('0.4', '0.25'), ('-0.5', '-0.65'), ('-0.4', '-0.55')]:
            source = [['4', ''], ['2', old], ['0', '0.5']]
            result, receipt = adjust.add_pf_modifier(source)
            self.assertEqual(result, [['4', ''], ['2', new], ['0', '0.5']])
            self.assertEqual(source[1][1], old)
            self.assertAlmostEqual(receipt['after'] - receipt['before'], -.15)
        self.assertEqual(adjust.add_pf_modifier([])[0], [['2', '-0.15']])

    def test_pf_does_not_change_ordinary_max_merge_policy(self):
        picks = [{'cond': [('2', '-0.5')]}, {'cond': [('2', '-0.15')]}]
        self.assertEqual(rb.merge_conds(picks), [('2', '-0.5')])
        self.assertEqual(adjust.add_pf_modifier(rb.merge_conds(picks))[0], [['2', '-0.65']])
        with self.assertRaisesRegex(ValueError, '重复'):
            adjust.add_pf_modifier([['2', '0.4'], ['2', '0.1']])
        with self.assertRaisesRegex(ValueError, '禁止截断'):
            adjust.add_pf_modifier([['0', '0.1'], ['1', '0.1'], ['3', '0.1'], ['4', ''], ['9', '0.1']])

    def test_random_half_is_reproducible_and_independent(self):
        selected = adjust.select_pf_floors(46454236)
        self.assertEqual(len(set(selected)), 15)
        for n in range(1, 31):
            adjust.policy_rng(46454236, f'ban:{n}').random()
        self.assertEqual(selected, adjust.select_pf_floors(46454236))
        self.assertNotEqual(selected, adjust.select_pf_floors(46454237))

    def test_swap_preserves_slot_rewards_and_migrates_complete_encounter(self):
        original = []
        for n in range(1, 31):
            curse = rb.apply_picks({}, [{'name': '保底', 'text': '水光',
                'element_resistance': [[2, 999, False], [5, 999, False]]}])
            row = [f'floor{n}-column{i}' for i in range(103)]
            original.append(dict(r=n, row=row, curse=curse, pick={'label': f'Boss{n}'},
                                 encounter={'field': f'f{n}', 'bosses': [f'b{n}']}))
        snapshot = copy.deepcopy(original)
        final, receipt = adjust.adjust_floors(original, 46454236)
        self.assertEqual(original, snapshot)
        for n, from_n in ((26, 30), (30, 26)):
            self.assertEqual(final[n - 1]['encounter'], original[from_n - 1]['encounter'])
            for column in range(103):
                if column not in adjust.ENCOUNTER_COLUMNS:
                    self.assertEqual(final[n - 1]['row'][column], original[n - 1]['row'][column])
                elif column != 3 and column not in range(71, 81):
                    self.assertEqual(final[n - 1]['row'][column], original[from_n - 1]['row'][column])
        self.assertEqual(sum(f['adjustment_policy']['pf_modifier'] is not None for f in final), 15)
        with self.assertRaisesRegex(ValueError, '禁止重复'):
            adjust.adjust_floors(final, 46454236)


if __name__ == '__main__':
    unittest.main()
