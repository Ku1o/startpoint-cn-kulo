"""Resource contract regressions for the 1.4.355 five-boss second-round tuning."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import struct
import unittest
from unittest import mock
import zipfile
import zlib

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

    @staticmethod
    def packmap(rows):
        # Deliberately use a different index compression representation.
        keys = bytearray()
        data = bytearray()
        offsets = bytearray(struct.pack("<I", len(rows)))
        for key, chunk in rows.items():
            keys.extend(key.encode("utf-8"))
            data.extend(chunk)
            offsets.extend(struct.pack("<II", len(keys), len(data)))
        index = zlib.compress(bytes(offsets + keys), level=0)
        return struct.pack("<I", len(index)) + index + data

    @staticmethod
    def stored_archive(entries):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, payload in sorted(entries.items()):
                archive.writestr(name, payload)
        return output.getvalue()

    def verify_archive(self, raw, manifest=None):
        manifest = copy.deepcopy(self.manifest if manifest is None else manifest)
        patch = next(p for p in manifest["patches"] if p["version"] == tune.VERSION)
        patch["archive_size"] = len(raw)
        patch["archive_integrity"][0]["size"] = len(raw)
        patch["archive_integrity"][0]["sha256"] = tune.sha(raw)
        archive_path = ROOT / "assets/asset-patch/active" / tune.ARCHIVE
        read_bytes = Path.read_bytes
        with mock.patch.object(Path, "read_bytes", autospec=True,
                               side_effect=lambda path: raw if path == archive_path else read_bytes(path)):
            return tune.verify_manifest(ROOT, manifest)

    def edit_quest(self, payload, edit):
        top = tune.rawmap(payload)
        chapter = tune.rawmap(top["1"])
        quests = tune.rawmap(chapter["99"])
        edit(quests)
        chapter["99"] = self.packmap(quests)
        top["1"] = self.packmap(chapter)
        return self.packmap(top)

    def test_equivalent_zip_dsl_and_target_table_compression_is_accepted(self):
        entries = dict(self.entries)
        bbq_member = tune.member(tune.BBQ_LP)
        for name, payload in entries.items():
            if name == bbq_member:
                def recompress(quests):
                    for qid, chunk in quests.items():
                        quests[qid] = zlib.compress(zlib.decompress(chunk), level=0)
                entries[name] = self.edit_quest(payload, recompress)
            else:
                amf = zlib.decompress(payload, -15)
                # A redundant U29 prefix changes AMF3 bytes without changing the tree.
                self.assertEqual(amf[0], 9)
                self.assertLess(amf[1], 128)
                amf = amf[:1] + b"\x80" + amf[1:]
                compressor = zlib.compressobj(0, zlib.DEFLATED, -15)
                entries[name] = compressor.compress(amf) + compressor.flush()
            self.assertNotEqual(entries[name], payload)
        raw = self.stored_archive(entries)
        self.assertEqual(self.verify_archive(raw)["sha256"], tune.sha(raw))

    def test_changed_quest_or_dsl_content_is_rejected_with_matching_receipt(self):
        bbq_member = tune.member(tune.BBQ_LP)
        for column in (99, 97):
            with self.subTest(column=column):
                entries = dict(self.entries)
                def change_row(quests):
                    qid = next(iter(quests))
                    rows = tune.parse_csv(tune.decode_leaf(quests[qid]))
                    rows[0][column] = "123"
                    quests[qid] = tune.encode_leaf(tune.format_csv(rows, True))
                entries[bbq_member] = self.edit_quest(entries[bbq_member], change_row)
                with self.assertRaisesRegex(ValueError, "differs from the scoped recipe"):
                    self.verify_archive(self.stored_archive(entries))
        entries = dict(self.entries)
        name = tune.member(tune.dsl_logical(tune.ENTRANCE_PROGRAMS[0]))
        tree = tune.decode_dsl(entries[name])
        tree[11][1][0][1][5] = True  # Alter the unrelated debuff-resistance cancelable flag.
        entries[name] = tune.encode_dsl(tree)
        with self.assertRaisesRegex(ValueError, "DSL .* differs from the scoped recipe"):
            self.verify_archive(self.stored_archive(entries))

    def test_recompressed_unrelated_chapter_or_group_is_rejected(self):
        name = tune.member(tune.BBQ_LP)
        for scope in ("chapter", "group"):
            with self.subTest(scope=scope):
                entries = dict(self.entries)
                top = tune.rawmap(entries[name])
                if scope == "chapter":
                    # This published table has only chapter 1; add a synthetic peer
                    # to exercise the same preservation guard at the outer level.
                    top["2"] = top["1"]
                    expected = self.packmap(top)
                rows = top if scope == "chapter" else tune.rawmap(top["1"])
                key = next(k for k in rows if k != ("1" if scope == "chapter" else "99"))
                old = rows[key]
                rows[key] = self.packmap(tune.rawmap(old))
                self.assertNotEqual(rows[key], old)
                if scope == "group":
                    top["1"] = self.packmap(rows)
                entries[name] = self.packmap(top)
                with self.assertRaisesRegex(ValueError, "Unrelated boss_battle_quest"):
                    if scope == "chapter":
                        tune.verify_boss_battle_quest(entries[name], expected)
                    else:
                        self.verify_archive(self.stored_archive(entries))

    def test_trailing_dsl_or_target_leaf_data_is_rejected_with_matching_receipt(self):
        name = tune.member(tune.dsl_logical(tune.ENTRANCE_PROGRAMS[0]))
        for kind in ("deflate", "amf3", "leaf"):
            with self.subTest(kind=kind):
                entries = dict(self.entries)
                if kind == "deflate":
                    entries[name] += b"trailing"
                elif kind == "amf3":
                    amf = zlib.decompress(entries[name], -15) + b"\x01"
                    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
                    entries[name] = compressor.compress(amf) + compressor.flush()
                else:
                    bbq_member = tune.member(tune.BBQ_LP)
                    def append_trailing(quests):
                        quests[next(iter(quests))] += b"trailing"
                    entries[bbq_member] = self.edit_quest(entries[bbq_member], append_trailing)
                with self.assertRaisesRegex(ValueError, "trailing|Trailing"):
                    self.verify_archive(self.stored_archive(entries))

    def test_bad_hash_member_set_and_crc_are_rejected(self):
        raw = self.stored_archive(self.entries)
        with self.assertRaisesRegex(ValueError, "exceeds 5 MiB"):
            self.verify_archive(raw + b"\x00" * (5 * 1024 * 1024 + 1 - len(raw)))
        archive_path = ROOT / "assets/asset-patch/active" / tune.ARCHIVE
        read_bytes = Path.read_bytes
        with mock.patch.object(Path, "read_bytes", autospec=True,
                               side_effect=lambda path: raw if path == archive_path else read_bytes(path)):
            with self.assertRaisesRegex(ValueError, "archive/manifest"):
                tune.verify_manifest(ROOT, self.manifest)
        for kind in ("missing", "extra", "duplicate"):
            with self.subTest(kind=kind):
                entries = dict(self.entries)
                name = next(iter(entries))
                if kind == "missing":
                    del entries[name]
                elif kind == "extra":
                    entries["production/upload/extra"] = b"extra"
                altered = self.stored_archive(entries)
                if kind == "duplicate":
                    output = io.BytesIO(altered)
                    with zipfile.ZipFile(output, "a") as archive:
                        with self.assertWarns(UserWarning):
                            archive.writestr(name, entries[name])
                    altered = output.getvalue()
                with self.assertRaisesRegex(ValueError, "ZIP integrity"):
                    self.verify_archive(altered)
        corrupt = bytearray(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entry = archive.infolist()[0]
            offset = entry.header_offset + 30 + len(entry.filename.encode("utf-8")) + len(entry.extra)
        corrupt[offset] ^= 1
        with self.assertRaisesRegex(ValueError, "ZIP integrity"):
            self.verify_archive(bytes(corrupt))

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
