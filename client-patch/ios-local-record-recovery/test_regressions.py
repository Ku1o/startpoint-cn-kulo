"""Retain historical iOS failures and check the actual appended table's ASLR."""
import collections,json,struct,sys,unittest
import prepare
import build_native as link
sys.path.insert(0,str(prepare.HERE.parent/'ios-shop-first-open'))

previous=prepare.module('ios_record_previous_regressions',prepare.HERE.parent/'ios-shop-first-open/test_regressions.py')
branches=prepare.module('ios_record_branch_regressions',prepare.HERE.parent/'ios-shop-first-open/test_veneers.py')

class AppendedTableASLR(unittest.TestCase):
    def test_real_table_entries_receive_exactly_one_slide(self):
        out=prepare.WORK/'output'
        native=(out/'worldflipper').read_bytes()
        report=json.loads((out/'build-report.json').read_text('utf-8'))
        segments=link.segments(native)
        entries=link.read_rebase(native)['entries']
        locations=collections.Counter(segments[si]['vm']+off for si,off,typ in entries if typ==1)
        table=struct.unpack_from('<Q',native,prepare.INFO_OFFSET+48)[0]
        for function in report['functions']:
            location=table+function['method']*8
            self.assertEqual(locations[location],1)
            value=struct.unpack_from('<Q',native,link.file_offset(native,location,8))[0]
            self.assertEqual(value,function['address'])
            for slide in (0x4000,0x12340000,0x80000000):
                relocated=value+locations[location]*slide
                self.assertEqual(relocated,function['address']+slide)
        self.assertTrue(all(si<=15 for si,off,typ in entries))
        self.assertEqual(segments[16]['name'],'__CNRECIO')

if __name__=='__main__':
    suite=unittest.TestSuite()
    for name in ['test_previous_candidate_is_rejected','test_first_fix_is_rejected_for_ldid_truncation','test_ldid_reproduces_reported_unknown_opcode_f0']:
        suite.addTest(previous.SigningLayoutRegression(name))
    for cls in [previous.PreviousRuntimeFailures,branches.LongBranchTests,AppendedTableASLR]:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
