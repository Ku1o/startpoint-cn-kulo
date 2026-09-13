"""Regression checks against the real pre-fix gacha snapshot and prepared ZIP."""
import argparse
import copy
import json
import sys
import unittest
import zipfile
from pathlib import Path
import prepare_content as p
import repair_gacha_consistency as fix

WORK = None


class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = p.readj(WORK/'report.json')
        cls.runtime = p.readj(WORK/'runtime.before.json')
        cls.rows = p.readj(WORK/'export.after.json')['gachaRows']
        cls.before_odds = {}
        for file in (WORK/'before/master/gacha_odds').glob('*.orderedmap'):
            outer=p.rawmap(file.read_bytes()); oid=file.stem
            cls.before_odds[oid]={k:p.csvrows(v)[0] for k,v in p.rawmap(outer[oid]).items()}
        cls.odds, cls.promotions = fix.promote(cls.rows, cls.before_odds)
        cls.base = p.readj(WORK/'gacha.before.json')
        cls.after = p.readj(WORK/'gacha.after.json')
        cls.final = {**cls.runtime['gachas'], **{k:cls.after[k] for k in cls.report['changed_server_pools']}}

    def test_original_actual_data_fails_and_corrected_data_passes(self):
        with self.assertRaisesRegex(AssertionError,'drift'):
            fix.validate(self.runtime['gachas'],self.rows,self.before_odds,self.runtime['characters'])
        self.assertEqual(fix.validate(self.final,self.rows,self.odds,self.runtime['characters']),self.report['checks'])

    def test_promotion_preserves_unrelated_rows_and_uses_same_class_weight(self):
        self.assertEqual(len(self.promotions),82)
        for gid, r in self.promotions.items():
            self.assertEqual([v for v in self.odds[r['four']].values() if v[0]==fix.DRAGON],[])
            new=[v for v in self.odds[r['five']].values() if v[0]==fix.DRAGON]
            self.assertEqual(new,[r['after']])
            self.assertEqual(r['before'][3:],r['after'][3:])
            self.assertEqual({v[2] for v in self.before_odds[r['five']].values() if v[0] in r['peer_ids']},{r['after'][2]})
        for oid, table in self.before_odds.items():
            self.assertEqual({k:v for k,v in table.items() if v[0]!=fix.DRAGON},
                             {k:v for k,v in self.odds[oid].items() if v[0]!=fix.DRAGON})

    def test_shared_five_star_table_cannot_add_dragon_to_an_unrelated_banner(self):
        rows=copy.deepcopy(self.rows)
        gid=next(iter(self.promotions)); row=rows[gid][0][:]
        row[15]='(None)'; rows['999999']=[row]
        with self.assertRaisesRegex(AssertionError,'leaks'):
            fix.promote(rows,self.before_odds)

    def test_ambiguous_peer_weight_is_rejected(self):
        before=copy.deepcopy(self.before_odds)
        req=next(r for r in self.promotions.values() if len(r['peer_ids'])>1)
        for row in before[req['five']].values():
            if row[0]==req['peer_ids'][0]:
                row[2]=str(int(row[2])+1);break
        with self.assertRaisesRegex(AssertionError,'ambiguous'):
            fix.promote(self.rows,before)

    def test_exchange_membership_weight_and_rank_regressions_are_rejected(self):
        for field,value in [('isExchangeable',False),('odds',99999),('rank',4)]:
            with self.subTest(field=field):
                final=copy.deepcopy(self.final)
                dragon=next(x for x in final['219']['pool']['1'] if x['id']==261089)
                dragon[field]=value
                with self.assertRaises(AssertionError):
                    fix.validate(final,self.rows,self.odds,self.runtime['characters'])
        final=copy.deepcopy(self.final)
        final['1675']['pool']['1']=[x for x in final['1675']['pool']['1'] if x['id']!=261089]
        with self.assertRaises(AssertionError):
            fix.validate(final,self.rows,self.odds,self.runtime['characters'])

    def test_metadata_and_unaffected_custom_pools_are_preserved(self):
        self.assertEqual(set(self.base),set(self.after))
        for gid in self.base:
            self.assertEqual({k:v for k,v in self.base[gid].items() if k!='pool'},
                             {k:v for k,v in self.after[gid].items() if k!='pool'})
        for gid in ['990001','990002']:
            self.assertEqual(self.runtime['gachas'][gid],self.final[gid])
        for gid,g in self.runtime['gachas'].items():
            if g['type']==1:self.assertEqual(g,self.final[gid])

    def test_serialized_zip_keeps_acquisition_fix_and_exact_repaired_odds(self):
        with zipfile.ZipFile(WORK/fix.ARCHIVE) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(len(z.namelist()),86)
            for member,sha in self.report['preserved_item_members'].items():
                self.assertEqual(p.sha(z.read(member)),sha)
            for name,receipt in self.report['resources'].items():
                data=z.read(receipt['member']);self.assertEqual(p.sha(data),receipt['sha256'])
                oid=Path(name).stem
                decoded={k:p.csvrows(v)[0] for k,v in p.rawmap(p.rawmap(data)[oid]).items()}
                self.assertEqual(decoded,self.odds[oid])


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True)
    args,rest=ap.parse_known_args();WORK=args.work
    unittest.main(argv=[sys.argv[0]]+rest)
