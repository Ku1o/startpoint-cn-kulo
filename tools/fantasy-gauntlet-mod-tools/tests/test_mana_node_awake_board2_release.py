from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
import zipfile


TOOL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOL_ROOT.parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import publish_mana_node_awake_board2_1_4_95_20260831 as release  # noqa: E402
import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_store_materialize as materialize  # noqa: E402


class ManaNodeAwakeBoard2ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.archive_raw, cls.report, cls.server_json, cls.manifest = release.build()
        cls.actual_archive_raw = (release.ACTIVE_DIR / release.ARCHIVE_NAME).read_bytes()
        cdn_root, _runtime_root = wf_live_cdn._resolve_locations()
        cls.android_plan = materialize.build_read_only_plan(
            cdn_root, REPO_ROOT, None, False,
        )
        cls.ios_plan = wf_live_cdn._build_ios_plan(cdn_root, REPO_ROOT)
        cls.base_plan = materialize.build_read_only_plan(
            cdn_root, REPO_ROOT, release.BASE_VERSION, False,
        )

    def test_archive_is_deterministic_and_manifest_integrity_matches(self) -> None:
        self.assertEqual(self.actual_archive_raw, self.archive_raw)
        self.assertEqual(release.sha256(self.archive_raw), self.report["archive"]["sha256"])
        with zipfile.ZipFile(io.BytesIO(self.archive_raw)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.namelist(), [release.member_name(release.LOGICAL_PATH)])

        entries = [
            item for item in self.manifest["patches"]
            if item.get("id") == release.PATCH_ID
        ]
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertTrue(entry["enabled"])
        self.assertEqual(entry["depends_on"], release.BASE_VERSION)
        self.assertEqual(entry["version"], release.TARGET_VERSION)
        self.assertEqual(entry["archive_integrity"], [self.report["archive"]])
        self.assertEqual(self.manifest["cdn_version"], release.TARGET_VERSION)

    def test_android_and_ios_reach_the_new_tail(self) -> None:
        self.assertEqual(self.android_plan.tail, release.TARGET_VERSION)
        self.assertIsNotNone(self.ios_plan)
        self.assertEqual(self.ios_plan.tail, release.TARGET_VERSION)
        self.assertFalse(self.android_plan.health.gap(self.android_plan.tail))
        self.assertEqual(self.android_plan.health.unreachable, ())
        self.assertFalse(self.ios_plan.health.gap(self.ios_plan.tail))
        self.assertEqual(self.ios_plan.health.unreachable, ())

    def test_terminal_table_has_slots_5_and_6_without_changing_existing_rows(self) -> None:
        before = release.read_plan_logical(self.base_plan, release.LOGICAL_PATH)
        after = release.read_plan_logical(self.android_plan, release.LOGICAL_PATH)
        with zipfile.ZipFile(io.BytesIO(self.archive_raw)) as archive:
            self.assertEqual(
                after,
                archive.read(release.member_name(release.LOGICAL_PATH)),
            )

        before_outer = core.read_orderedmap_raw_rows_from_bytes(before, release.LOGICAL_PATH)
        after_outer = core.read_orderedmap_raw_rows_from_bytes(after, release.LOGICAL_PATH)
        self.assertEqual(before_outer.keys, after_outer.keys)
        for rarity, before_rarity_raw, after_rarity_raw in zip(
            before_outer.keys, before_outer.rows, after_outer.rows,
        ):
            before_slots = core.read_orderedmap_raw_rows_from_bytes(
                before_rarity_raw, f"before#{rarity}",
            )
            after_slots = core.read_orderedmap_raw_rows_from_bytes(
                after_rarity_raw, f"after#{rarity}",
            )
            before_rows = dict(zip(before_slots.keys, before_slots.rows))
            after_rows = dict(zip(after_slots.keys, after_slots.rows))
            self.assertEqual(after_slots.keys, before_slots.keys + ["5", "6"])
            for slot, row in before_rows.items():
                self.assertEqual(after_rows[slot], row)
            self.assertEqual(after_rows["5"], before_rows["2"])
            slot6_source = "3" if "3" in before_rows else "2"
            self.assertEqual(after_rows["6"], before_rows[slot6_source])

    def test_server_json_matches_terminal_table(self) -> None:
        terminal = release.read_plan_logical(self.android_plan, release.LOGICAL_PATH)
        expected = release.decode_table(terminal)
        actual = json.loads(release.SERVER_JSON_PATH.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)
        self.assertEqual(actual, self.server_json)

    def test_dark_dragon_identity_tables_are_not_touched(self) -> None:
        for logical in (
            "master/character/character.orderedmap",
            "master/character/character_status.orderedmap",
        ):
            self.assertEqual(
                release.read_plan_logical(self.base_plan, logical),
                release.read_plan_logical(self.android_plan, logical),
            )


if __name__ == "__main__":
    unittest.main()
