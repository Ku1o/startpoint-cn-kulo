import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wf_standard_enemy_links as links
import wf_rogue_build as rb


class StandardEnemyLinksCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(Path(__file__).parent/'fixtures/floor12-standard-family.json.zlib').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == 'd70eb90e2a940d3aa1864c329cb7527e3e0bb878a424647c99e49039eca02a0c'
        cls.fixture=json.loads(zlib.decompress(raw))
        cls.boss='steampunk_water_hard_multi'
        cls.core='steampunk_water_funnel_core_hard_multi'
        cls.heart='steampunk_water_funnel_heart_core_hard_multi'
        cls.ids={cls.boss:'mod_rogue_standard12', cls.core:'mod_rogue_r12_core', cls.heart:'mod_rogue_r12_heart'}

    def build(self):
        return links.clone_family(self.fixture['actors'],self.ids,self.fixture['actions'].__getitem__,
            namespace='battle/action/enemy/action/mod_rogue/test_r12')

    def test_real_floor12_broken_binding_is_repaired_and_state_watches_match(self):
        before=copy.deepcopy(self.fixture)
        active={self.ids[self.boss]}
        for core in (self.core,self.heart):
            self.assertNotIn(self.fixture['actors'][core]['bG'],active)
        repaired=self.build()
        for core in (self.core,self.heart):
            tree=repaired['actors'][self.ids[core]]
            self.assertIn(tree['bG'],active)
            self.assertTrue(all(target in active for _,target in links.reverse_boss_references(tree)))
        self.assertEqual(len(links.reverse_boss_references(repaired['actors'][self.ids[self.core]])),7)
        self.assertEqual(self.fixture,before)

    def test_hp_trial_timers_and_unrelated_actions_are_preserved(self):
        repaired=self.build()
        for code,tree in self.fixture['actors'].items():
            after=repaired['actors'][self.ids[code]]
            self.assertEqual(rb.standard_enemy_hp_base(tree),rb.standard_enemy_hp_base(after))
            self.assertEqual([s.get('d') for f in tree['au'] for s in f['g']],
                             [s.get('d') for f in after['au'] for s in f['g']])
        boss=repaired['actors'][self.ids[self.boss]]
        self.assertEqual(boss['au'][0]['g'][147]['d'],['T1',['T1',1800]])
        contract=rb.standard_damage_check_contract(self.fixture['actors'][self.boss],boss,runtime_hp_scale=1)
        self.assertEqual(contract['occurrence_count'],1)
        self.assertAlmostEqual(contract['checks'][0]['final_absolute_threshold_hp'],728571428.5714285)

    def test_callbacks_and_spawned_actor_ids_are_closed(self):
        bundle=self.build()
        for tree in bundle['actors'].values():
            self.assertTrue(links.action_roots(tree)<=set(bundle['actions']))
        for tree in bundle['actions'].values():
            for value in links.walk(tree):
                if isinstance(value,list) and len(value)==2 and value[0]=='StandardFunnel':
                    self.assertIn(value[1],bundle['actors'])
        incomplete=dict(self.fixture['actors']);del incomplete[self.heart]
        ids=dict(self.ids);del ids[self.heart]
        with self.assertRaisesRegex(ValueError,'actor closure lacks'):
            links.clone_family(incomplete,ids,self.fixture['actions'].__getitem__,
                namespace='battle/action/enemy/action/mod_rogue/test_missing')

    def test_animation_zero_does_not_hide_damage_trial(self):
        boss=self.fixture['actors'][self.boss]
        self.assertEqual(boss['au'][0]['g'][1]['e'],0)
        self.assertEqual(rb.standard_damage_check_records(boss)[0]['percentage'],10)
        changed=copy.deepcopy(boss);changed['au'][0]['g'][1]['e']=99
        self.assertEqual(rb.standard_damage_check_records(changed)[0]['percentage'],10)
        changed['au'][0]['g'][1]['m'][1]={'h':['T6',[['T2','damage_check_a']]],'d':True}
        with self.assertRaisesRegex(ValueError,'DamageCheck script'):
            rb.standard_damage_check_records(changed)

    def test_standard_funnel_links_enter_identity_guard(self):
        table={'core':{'100':'core/path'},'heart':{'100':'heart/path'}}
        records=links.funnel_boss_references(table,lambda row:[row],
            lambda path:self.fixture['actors'][self.core if path.startswith('core') else self.heart])
        refs={'hard':set(),'degraded':False,'standard_identity_references':{code for _,code in records}}
        self.assertIn('identity-locked',rb.identity_locked_boss_reason([self.boss],code_references=refs))
        self.assertIsNone(rb.identity_locked_boss_reason(['unrelated'],code_references=refs))
        refs.update(damage_share=set(),enemy_watch_partner=set(),boss_alive=set())
        self.assertIn('Standard ESDL',rb.identity_clone_locked_boss_reason([self.boss],code_references=refs))


if __name__=='__main__':unittest.main()
