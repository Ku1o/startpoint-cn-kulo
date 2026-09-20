"""Regression checks for the actual deployed-format EX20 family and exchange rows."""
import copy, csv, io, json, os, sys, unittest, zipfile, zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/fantasy-gauntlet-mod-tools'))
os.environ.update(WF_SERVER_DIR=str(ROOT),WF_CDN_DIR=str(ROOT/'.cdn/cn'),WF_LIVE_CDN='1')
import wf_live_cdn as live, wf_quest_lib as q, wf_rogue_build as rb, wf_dsl, wf_dsl_sig
import repair_abyss_ex20_exchange_115 as repair

def table(logical):return q.parse_node(live.read_logical(logical).data)

class Ex20Regression(unittest.TestCase):
    def test_score_mode_is_blocked_even_without_external_identity_references(self):
        refs={'hard':set(),'damage_share':set(),'enemy_watch_partner':set(),'boss_alive':set()}
        self.assertFalse(rb._pool_safe(['shark_score_event']))
        for gate in (rb.identity_locked_boss_reason,rb.identity_clone_locked_boss_reason):
            self.assertIn('计分',gate(['shark_score_event'],code_references=refs))
        self.assertNotIn('score_event_shark',rb.DEEP_HP_ANCHOR_FIELDS_30)
        self.assertIsNone(rb.deep_hp_anchor_field(25,30))

    def test_official_nullable_condition_field_does_not_relax_other_positions(self):
        tree=['ActionDsl',2,['None'],False,False,False,False,False,False,False,0,
              ['Block',[['Command',['CreateCondition',0,[],[],['GenericConditionHitEffect'],False,False,'',None,False,0,[],False]]]]]
        wf_dsl_sig.validate_action_dsl(tree)
        bad=copy.deepcopy(tree);bad[11][1][0][1][4]=None
        with self.assertRaises(wf_dsl_sig.DslSignatureError):wf_dsl_sig.validate_action_dsl(bad)
        bad=copy.deepcopy(tree);bad[11][1][0][1][8]=['NotAnEnum']
        with self.assertRaises(wf_dsl_sig.DslSignatureError):wf_dsl_sig.validate_action_dsl(bad)

    def test_complete_published_family_roundtrips_to_ordinary_native_actions(self):
        audit=json.loads((ROOT/'assets/asset-patch/audit/abyss-ex20-exchange-1.4.115/report.json').read_text('utf-8'))
        mapping=audit['actors'];inverse={v:k for k,v in mapping.items()}
        for source,target in mapping.items():
            if not source.startswith('battle/action/'):continue
            a=wf_dsl.parse_dsl(zlib.decompress(live.read_logical(source+repair.SUFFIX).data,-15))['tree']
            b=wf_dsl.parse_dsl(zlib.decompress(live.read_logical(target+repair.SUFFIX).data,-15))['tree']
            wf_dsl_sig.validate_action_dsl(b)
            self.assertEqual(repair.exact(b,inverse),a)
        bosses=table(repair.B+'general_boss.orderedmap');funnels=table(repair.B+'funnel/general_funnel.orderedmap')
        for color in ('blue','brown','red'):
            for row in funnels[mapping['shark_'+color]].values():self.assertEqual(rb.cells(row)[32],mapping['shark'])
        for row in bosses[mapping['shark']].values():
            c=rb.cells(row);self.assertEqual(c[42],mapping['shark'])
            self.assertNotIn('score_event',c[109]);self.assertIn('mod_ex20/boss_shark$pre_action',c[109])
            self.assertEqual(c[47],'0.5')
        states=table(repair.B+'funnel/general_funnel_state.orderedmap')
        for color in ('blue','brown','red'):
            a=rb.general_damage_check_records(states['shark_'+color]);b=rb.general_damage_check_records(states[mapping['shark_'+color]])
            self.assertEqual(len(a),len(b))
            for x,y in zip(a,b):self.assertAlmostEqual(x['percentage'],y['percentage']*audit['hp_scale'],places=7)
        self.assertIn('mod_abyss_ex_f20_115',table(repair.QUEST)['700100']['20'])

    def test_exchange_client_and_server_only_enable_the_two_flags(self):
        def flatten(x):
            for v in repair.walk(x):
                if isinstance(v,str):
                    yield from csv.reader(io.StringIO(v))
        client={int(r[0]):r for r in flatten(table(repair.ODDS))}
        for rel in ('assets/gacha.json','assets/gacha_cnmod.json'):
            pool=json.loads((ROOT/rel).read_text('utf-8'))['990001']['pool']
            rows={x['id']:x for group in pool.values() for x in group}
            for ident in (149988,149990):
                self.assertTrue(rows[ident]['isExchangeable']);self.assertEqual(rows[ident]['odds'],1000)
                self.assertEqual(client[ident][5],'true');self.assertEqual(client[ident][2],'1000')
        note=zlib.decompress(live.read_logical(repair.NOTE).data,-15).decode()
        self.assertIn('夏日白、盾牌座、校园碧安卡',note)
        self.assertNotIn('夏日白、盾牌座与十五位小 Boss 不可兑换',note)

if __name__=='__main__':unittest.main()
