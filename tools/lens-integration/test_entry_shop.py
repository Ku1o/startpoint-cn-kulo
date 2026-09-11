import copy
import os
from pathlib import Path
import unittest
import fix_entry_shop as fix
import prepare_content as p


class EntryShopClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidate=os.environ.get('LENS_NAVIGATION_CANDIDATE')
        if candidate:
            cls.blobs={logical:(Path(candidate)/p.member(('common',p.hrel(logical)))).read_bytes()
                       for logical in (fix.STAGE,fix.CATEGORY,fix.SHOP)}
        else:
            chain=p.Chain()
            cls.blobs={logical:chain.get(('common',p.hrel(logical)))
                       for logical in (fix.STAGE,fix.CATEGORY,fix.SHOP)}
        cls.shop=p.readj(p.REPO/'assets/boss_coin_shop.json')

    def test_current_navigation_matches_server_products(self):
        self.assertEqual(fix.validate_navigation(self.blobs,self.shop)['quest'],1099001)

    def test_missing_stage_entry_is_rejected(self):
        blobs=dict(self.blobs);root=p.rawmap(blobs[fix.STAGE]);rows=p.rawmap(root['1'])
        del rows['99'];root['1']=p.packmap(rows);blobs[fix.STAGE]=p.packmap(root)
        with self.assertRaisesRegex(AssertionError,'stage entry'):fix.validate_navigation(blobs,self.shop)

    def test_missing_shop_category_is_rejected(self):
        blobs=dict(self.blobs);rows=p.rawmap(blobs[fix.CATEGORY]);del rows['99'];blobs[fix.CATEGORY]=p.packmap(rows)
        with self.assertRaisesRegex(AssertionError,'shop category'):fix.validate_navigation(blobs,self.shop)

    def test_server_returning_absent_weapon_is_rejected(self):
        blobs=dict(self.blobs);rows=p.rawmap(blobs[fix.SHOP]);del rows['990099001'];blobs[fix.SHOP]=p.packmap(rows)
        with self.assertRaisesRegex(AssertionError,'990099001'):fix.validate_navigation(blobs,self.shop)

    def test_displayed_exchange_cost_must_match_server(self):
        shop=copy.deepcopy(self.shop);shop['99']['990099001']['costs'][0]['amount']=9
        with self.assertRaises(AssertionError):fix.validate_navigation(self.blobs,shop)


if __name__=='__main__':unittest.main()
