"""Resource contract regressions for the 1.4.355 five-boss second-round tuning."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fiveboss_second_tune", ROOT / "tools/build-fiveboss-second-tune.py")
tune = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tune)


class FiveBossSecondTuneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "assets/asset-patch/manifest.json").read_bytes())
        cls.base = copy.deepcopy(cls.manifest)
        index = next(i for i, patch in enumerate(cls.base["patches"]) if patch["version"] == tune.VERSION)
        cls.base["patches"] = cls.base["patches"][:index]
        cls.base["cdn_version"] = tune.BASE_VERSION
        cls.pre352 = tune.slice_before_version(cls.base, tune.FIRST_TUNE_VERSION)
        cls.entries = tune.build_entries(ROOT, cls.base)

    def test_published_archive_is_exact_scoped_recipe(self):
        self.assertEqual(tune.verify(ROOT)["members"], 4)

    def test_later_resource_edges_do_not_invalidate_the_fixed_edge(self):
        future = copy.deepcopy(self.manifest)
        future["cdn_version"] = "1.4.999"
        future["patches"].append({"version": "1.4.999", "depends_on": tune.VERSION})
        self.assertEqual(tune.verify_manifest(ROOT, future), tune.verify(ROOT))

    def test_enrage_is_already_dispellable_on_base_and_not_reshipped(self):
        tune.verify_enrage_already_dispellable(ROOT, self.base)
        for program in tune.ENRAGE_PROGRAMS:
            self.assertNotIn(tune.member(tune.dsl_logical(program)), self.entries)

    def test_entrance_programs_change_only_five_defense_layer_values(self):
        self.assertEqual(tune.NEW_LADDER, [0.1111, 0.1389, 0.1786, 0.2381, 0.3333])
        for program in tune.ENTRANCE_PROGRAMS:
            with self.subTest(program=program):
                lp = tune.dsl_logical(program)
                before = tune.decode_dsl(tune.read_effective(ROOT, self.base, lp))
                after = tune.decode_dsl(self.entries[tune.member(lp)])
                expected = copy.deepcopy(before)
                for stmt in expected[11][1]:
                    if stmt[0] == "Command" and stmt[1][0] == "CreateCondition":
                        key = stmt[1][7]
                        if key.startswith("fb3_def_") and key != "fb3_def_down":
                            idx = int(key.rsplit("_", 1)[1])
                            val = tune.NEW_LADDER[idx]
                            stmt[1][2][0][3] = [{"min": val, "max": val}]
                self.assertEqual(after, expected)

    def test_purge_r1_removes_only_subtract_skill_point(self):
        lp = tune.dsl_logical(tune.PURGE_PROGRAM)
        before = tune.decode_dsl(tune.read_effective(ROOT, self.base, lp))
        after = tune.decode_dsl(self.entries[tune.member(lp)])
        self.assertEqual(
            list(tune.commands(before, "SubtractSkillPoint")),
            [["SubtractSkillPoint", 0, [{"min": 1, "max": 1}]]],
        )
        self.assertEqual(list(tune.commands(after, "SubtractSkillPoint")), [])

    def test_boss_battle_quest_scales_only_group99_c99_and_c102_without_double_scaling(self):
        pre_payload = tune.read_effective(ROOT, self.pre352, tune.BBQ_LP)
        before_payload = tune.read_effective(ROOT, self.base, tune.BBQ_LP)
        after_payload = self.entries[tune.member(tune.BBQ_LP)]

        before_top = tune.rawmap(before_payload)
        after_top = tune.rawmap(after_payload)
        self.assertEqual(list(after_top), list(before_top))
        self.assertEqual([k for k in before_top if after_top[k] != before_top[k]], ["1"])

        before_ch1 = tune.rawmap(before_top["1"])
        after_ch1 = tune.rawmap(after_top["1"])
        self.assertEqual(list(after_ch1), list(before_ch1))
        self.assertEqual([k for k in before_ch1 if after_ch1[k] != before_ch1[k]], ["99"])

        pre_rows = tune.extract_group99_rows(pre_payload)
        before_rows = tune.extract_group99_rows(before_payload)
        after_rows = tune.extract_group99_rows(after_payload)
        self.assertEqual(len(after_rows), 39)
        for qid, after_row in after_rows.items():
            before_row = before_rows[qid]
            pre_row = pre_rows[qid]
            expected = list(before_row)
            expected[99] = tune.fmt_num(float(before_row[99]) * 0.7)
            expected[102] = tune.fmt_num(float(before_row[102]) * 0.8)
            self.assertEqual(after_row, expected)
            # Cumulative HP multiplier vs pre-1.4.352 baseline is 0.35 * 0.70 = 0.245.
            self.assertAlmostEqual(float(after_row[99]), float(pre_row[99]) * 0.245, places=9)
            self.assertEqual(after_row[119], before_row[119])

    def test_changed_preimage_is_rejected(self):
        for program in tune.ENTRANCE_PROGRAMS:
            lp = tune.dsl_logical(program)
            with self.assertRaisesRegex(ValueError, "preimage"):
                tune.rewrite_entrance(program, self.entries[tune.member(lp)])
        with self.assertRaisesRegex(ValueError, "preimage"):
            tune.rewrite_purge(self.entries[tune.member(tune.dsl_logical(tune.PURGE_PROGRAM))])
        with self.assertRaisesRegex(ValueError, "preimage"):
            tune.rewrite_boss_battle_quest(self.entries[tune.member(tune.BBQ_LP)])

    def test_shared_android_ios_common_roots_and_zip_crc(self):
        raw = tune.archive_bytes(self.entries)
        self.assertLessEqual(len(raw), 5 * 1024 * 1024)
        bbq_member = tune.member(tune.BBQ_LP)
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            self.assertIsNone(source.testzip())
            self.assertEqual(len(source.namelist()), 4)
            for name in source.namelist():
                self.assertTrue(name.startswith("production/upload/"))
                payload = source.read(name)
                if name == bbq_member:
                    self.assertEqual(len(tune.extract_group99_rows(payload)), 39)
                else:
                    tree = tune.decode_dsl(payload)
                    self.assertEqual(tune.parse_dsl(tune.encode_amf3(tree))["tree"], tree)


if __name__ == "__main__":
    unittest.main()
