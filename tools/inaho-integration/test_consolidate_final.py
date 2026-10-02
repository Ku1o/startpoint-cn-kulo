"""Regressions for omitted effect dependencies and reverted final voice bytes."""
import argparse
from pathlib import Path
import unittest

import consolidate_final as merge


class TerminalResources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = merge.load_contract()
        cls.final = merge.read_archive(ARGS.archive)
        cls.before = merge.read_archive(ARGS.before)

    def test_final_resource_closure_and_stored_formats(self):
        result = merge.validate_payloads(self.final, self.contract)
        self.assertEqual(result["members"], 161)
        self.assertEqual(result["voices"], 18)
        self.assertEqual(result["generated_image_references"], 93)

    def test_broken_consolidation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "resource set mismatch"):
            merge.validate_payloads(self.before, self.contract)

    def test_removing_any_supplement_effect_is_rejected(self):
        added = [r for r in self.contract["files"] if r["change"] == "added"]
        self.assertEqual(len(added), 12)
        for record in added:
            with self.subTest(resource=record["logical"]):
                broken = dict(self.final)
                del broken[record["member"]]
                with self.assertRaisesRegex(ValueError, "resource set mismatch"):
                    merge.validate_payloads(broken, self.contract)

    def test_reverting_any_updated_voice_is_rejected(self):
        updated = [r for r in self.contract["files"] if r["change"] == "updated"]
        self.assertEqual(len(updated), 7)
        for record in updated:
            with self.subTest(resource=record["logical"]):
                self.assertTrue(record["logical"].endswith(".mp3"))
                broken = {**self.final, record["member"]: self.before[record["member"]]}
                with self.assertRaisesRegex(ValueError, "terminal resource digest mismatch"):
                    merge.validate_payloads(broken, self.contract)

    def test_cross_layout_texture_dependency_without_digest_gate(self):
        record = next(r for r in self.contract["files"] if
                      r["logical"] == "battle/effect/skill_unique/inaho_midautumn_wip/midautumn_native/midautumn_native.atlas.amf3.deflate")
        broken = {n: b for n, b in self.final.items() if n != record["member"]}
        # Removing the contract entry too must not bypass semantic closure.
        reduced = {**self.contract, "files": [r for r in self.contract["files"] if r != record]}
        with self.assertRaisesRegex(ValueError, "missing atlas frame"):
            merge.validate_payloads(broken, reduced, check_digests=False)

    def test_earlier_visual_supplement_cannot_restore_final_state(self):
        earlier = merge.read_archive(ARGS.earlier)
        with self.assertRaises(ValueError):
            merge.validate_payloads({**self.before, **earlier}, self.contract)

    def test_current_direct_client_matches_resource_contract(self):
        result = merge.verify_apk(ARGS.apk, self.contract)
        self.assertFalse(result["private_proxy_dependency"])

    def test_existing_character_data_preserved(self):
        unchanged = [r for r in self.contract["files"] if r["change"] == "preserved"]
        self.assertEqual(len(unchanged), 142)
        for record in unchanged:
            self.assertEqual(self.before[record["member"]], self.final[record["member"]])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ("archive", "before", "earlier", "apk"):
        parser.add_argument("--" + key, type=Path, required=True)
    ARGS, remaining = parser.parse_known_args()
    unittest.main(argv=[__file__, *remaining])
