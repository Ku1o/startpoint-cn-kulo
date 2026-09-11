from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import wf_mod_tool as core
import wf_race_character_nerf as nerf

FIXTURES = Path(__file__).parent / 'fixtures/race-character-nerf-v1'
ABILITY = 'master/ability/ability.orderedmap'
LEADER = 'master/ability/leader_ability.orderedmap'


def fixture(logical=ABILITY):
    return (FIXTURES / Path(logical).name).read_bytes()


def decoded(raw, logical=ABILITY):
    return {key:core.read_csv_lines(value) for key,value in
            core.read_orderedmap_bytes(raw,logical).text_rows().items()}


def mutate(raw, key, transform, logical=ABILITY):
    table = core.read_orderedmap_raw_rows_from_bytes(raw,logical)
    index = table.keys.index(key)
    rows = core.read_csv_lines(zlib.decompress(table.rows[index]).decode('utf-8'))
    transform(rows)
    table.rows[index] = zlib.compress(core.write_csv_lines(rows).encode('utf-8'),9)
    return core.build_orderedmap_raw_rows(table)


class RaceCharacterNerfTests(unittest.TestCase):
    def test_reviewed_maxima_and_stack_outcomes(self):
        after, a_report = nerf.patch_table(ABILITY,fixture())
        leaders, l_report = nerf.patch_table(LEADER,fixture(LEADER))
        rows = decoded(after)
        lead = decoded(leaders,LEADER)
        # Independent full-level expectations from the approved first-round report.
        maxima = {
            '1299982':(114,{0:40000,1:40000,2:30000,3:15000,4:15000,5:12000,6:6000}),
            '1299984':(52,{3:30000,5:2000}),
            '1199931':(114,{1:15000,2:15000}),
            '1199933':(114,{0:17500,1:12500}),
            '1199935':(114,{1:3500}),
            '1499943':(52,{3:3000,4:60000}),
            '1499944':(52,{2:25000}),
            '1499946':(52,{4:60000,5:60000}),
            '1399962':(52,{0:40000,1:15000,2:25000,3:25000}),
            '1399964':(52,{0:100000,2:25000}),
        }
        for key,(column,expected) in maxima.items():
            for index,value in expected.items():
                self.assertEqual(int(rows[key][index][column]),value,(key,index))
        self.assertEqual([lead['119993'][i][112] for i in (2,3)],['25000','30000'])
        self.assertEqual(lead['139996'][4][50],'40000')
        self.assertEqual(8*int(rows['1299982'][6][114]),48000)
        self.assertEqual(6*(int(rows['1199931'][1][114])+int(rows['1199933'][0][114])),195000)
        self.assertEqual(6*(int(rows['1199931'][2][114])+int(rows['1199933'][1][114])),165000)
        self.assertEqual(a_report['changed_cells']+l_report['changed_cells'],56)

    def test_cube_main_only_is_per_row_and_cycle_timings_preserved(self):
        before = decoded(fixture())
        after,_ = nerf.patch_table(ABILITY,fixture())
        rows = decoded(after)
        cube = rows['1399964']
        self.assertEqual([r[6] for r in cube],['202','0','202','0'])
        self.assertEqual(cube[1],before['1399964'][1])  # Charge speed remains usable as Unison.
        self.assertEqual(cube[3],before['1399964'][3])  # Gauge cap likewise.
        for key,index in [('1299984',3),('1499944',2),('1399964',2)]:
            self.assertEqual(rows[key][index][46],'2')
        for key,index in [('1299984',5),('1499943',3)]:
            self.assertEqual(rows[key][index][35],'60')
        self.assertEqual([rows['1499946'][i][6] for i in (4,5)],['203','203'])

    def test_minimums_scale_proportionally(self):
        for logical in (ABILITY,LEADER):
            before = decoded(fixture(logical),logical)
            output,report = nerf.patch_table(logical,fixture(logical))
            after = decoded(output,logical)
            for cell in report['changes']:
                col = cell['column']
                if col not in (51,113,49,111):
                    continue
                old = before[cell['key']][cell['row']]
                new = after[cell['key']][cell['row']]
                numerator = int(old[col])*int(new[col+1])
                denominator = int(old[col+1])
                rounded = (2*numerator+denominator)//(2*denominator)
                self.assertEqual(int(new[col]),rounded)

    def test_byte_idempotence_and_unrelated_compressed_rows(self):
        for logical in (ABILITY,LEADER):
            before = fixture(logical)
            output,report = nerf.patch_table(logical,before)
            again,second = nerf.patch_table(logical,output)
            self.assertEqual(output,again)
            self.assertEqual(second['changed_cells'],0)
            a = core.read_orderedmap_raw_rows_from_bytes(before,logical)
            b = core.read_orderedmap_raw_rows_from_bytes(output,logical)
            self.assertEqual(a.keys,b.keys)
            allowed = {(c['key'],c['row'],c['column']) for c in report['changes']}
            for key,old,new in zip(a.keys,a.rows,b.rows):
                if key not in report['changed_keys']:
                    self.assertEqual(old,new)
                old_rows = core.read_csv_lines(zlib.decompress(old).decode('utf-8'))
                new_rows = core.read_csv_lines(zlib.decompress(new).decode('utf-8'))
                for index,(x,y) in enumerate(zip(old_rows,new_rows)):
                    for col,(v,w) in enumerate(zip(x,y)):
                        if v != w:
                            self.assertIn((key,index,col),allowed)

    def test_rebase_preserves_new_unrelated_work_in_same_key(self):
        newer = mutate(fixture(),'1299982',lambda rows:rows[7].__setitem__(114,'99000'))
        output,_ = nerf.patch_table(ABILITY,newer)
        self.assertEqual(decoded(output)['1299982'][7][114],'99000')

    def test_unknown_trigger_target_numeric_and_partial_changes_fail(self):
        for column,value in [(27,'999'),(48,'5'),(52,'35000'),(51,'15000')]:
            drift = mutate(fixture(),'1299984',lambda rows:rows[3].__setitem__(column,value))
            with self.subTest(column=column),self.assertRaises(ValueError):
                nerf.patch_table(ABILITY,drift)
        reordered = mutate(fixture(),'1399964',lambda rows:rows.reverse())
        with self.assertRaises(ValueError):
            nerf.patch_table(ABILITY,reordered)

    def test_missing_key_and_shape_drift_fail(self):
        table = core.read_orderedmap_raw_rows_from_bytes(fixture(),ABILITY)
        index = table.keys.index('1199931')
        table.keys.pop(index)
        table.rows.pop(index)
        with self.assertRaises(ValueError):
            nerf.patch_table(ABILITY,core.build_orderedmap_raw_rows(table))
        for transform in (lambda rows:rows.pop(),lambda rows:rows[0].pop()):
            with self.assertRaises(ValueError):
                nerf.patch_table(ABILITY,mutate(fixture(),'1199931',transform))

    def test_pristine_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                nerf.checked_output_dir(root,root/'.cdn/cn/candidate')
            self.assertEqual(nerf.checked_output_dir(root,root/'work/candidate'),(root/'work/candidate').resolve())


if __name__ == '__main__':
    unittest.main()
