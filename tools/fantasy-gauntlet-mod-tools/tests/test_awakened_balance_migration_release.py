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

import publish_awakened_balance_migration_1_4_94_20260830 as release  # noqa: E402
import wf_live_cdn  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_store_materialize as materialize  # noqa: E402


class AwakenedBalanceMigrationReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.archive_raw, cls.report, cls.server_assets, cls.manifest, _ = release.build()
        cls.archive_path = release.ACTIVE_DIR / release.ARCHIVE_NAME
        cls.actual_archive_raw = cls.archive_path.read_bytes()
        cdn_root, _runtime_root = wf_live_cdn._resolve_locations()
        cls.android_plan = materialize.build_read_only_plan(
            cdn_root, REPO_ROOT, None, False,
        )
        cls.ios_plan = wf_live_cdn._build_ios_plan(cdn_root, REPO_ROOT)
        cls.official_plan = materialize.build_read_only_plan(
            cdn_root, REPO_ROOT, release.OFFICIAL_VERSION, False,
        )
        cls.base_plan = materialize.build_read_only_plan(
            cdn_root, REPO_ROOT, release.BASE_VERSION, False,
        )

    def test_archive_is_deterministic_and_manifest_integrity_matches(self) -> None:
        self.assertEqual(self.actual_archive_raw, self.archive_raw)
        self.assertEqual(release.sha256(self.actual_archive_raw), self.report["archive"]["sha256"])
        with zipfile.ZipFile(io.BytesIO(self.actual_archive_raw)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.namelist()), 34)
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))

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

    def test_terminal_tables_equal_the_archive_payloads(self) -> None:
        with zipfile.ZipFile(io.BytesIO(self.actual_archive_raw)) as archive:
            for logical in (
                release.ABILITY_LOGICAL,
                release.LEADER_LOGICAL,
                release.ACTION_LOGICAL,
                release.AWAKE_EVENT_LOGICAL,
                release.AWAKE_STATUS_LOGICAL,
                release.AWAKE_MISSION_LOGICAL,
                release.AWAKE_REWARD_LOGICAL,
            ):
                expected = archive.read(release.member_name(logical))
                actual = release.read_plan_logical(self.android_plan, logical)
                self.assertEqual(actual, expected, logical)

    def test_dark_dragon_rarity_and_status_are_not_rolled_back(self) -> None:
        before_character = release.read_plan_logical(self.base_plan, release.CHARACTER_LOGICAL)
        after_character = release.read_plan_logical(self.android_plan, release.CHARACTER_LOGICAL)
        before_status = release.read_plan_logical(self.base_plan, release.STATUS_LOGICAL)
        after_status = release.read_plan_logical(self.android_plan, release.STATUS_LOGICAL)
        self.assertEqual(before_character, after_character)
        self.assertEqual(before_status, after_status)
        dark_row = release.flat_rows(after_character, "261089")[0]
        self.assertEqual(dark_row[2], "5")

    def test_ability_and_leader_awake_selection(self) -> None:
        official_ability = release.read_plan_logical(self.official_plan, release.ABILITY_LOGICAL)
        base_ability = release.read_plan_logical(self.base_plan, release.ABILITY_LOGICAL)
        expected_ability, _, awakened_abilities = release.build_ability(
            official_ability, base_ability,
        )
        terminal_ability = release.read_plan_logical(self.android_plan, release.ABILITY_LOGICAL)
        self.assertEqual(terminal_ability, expected_ability)
        official_map = core.read_orderedmap_file_from_bytes(official_ability)
        terminal_map = core.read_orderedmap_file_from_bytes(terminal_ability)
        for key, awakened_rows in awakened_abilities.items():
            rows = core.read_csv_lines(terminal_map[key])
            official_rows = core.read_csv_lines(official_map[key])
            self.assertEqual(
                release.without_gate(release.select_rows(rows, 0, 3, 4), 3, 4),
                official_rows,
            )
            self.assertEqual(
                release.without_gate(release.select_rows(rows, 1, 3, 4), 3, 4),
                awakened_rows,
            )
        summer_ability = release.select_rows(
            core.read_csv_lines(terminal_map["1510453"]), 1, 3, 4,
        )
        summer_damage = [row for row in summer_ability if row[47] == "356"]
        self.assertEqual(len(summer_damage), 1)
        self.assertEqual(summer_damage[0][35], "150")

        official_leader = release.read_plan_logical(self.official_plan, release.LEADER_LOGICAL)
        base_leader = release.read_plan_logical(self.base_plan, release.LEADER_LOGICAL)
        expected_leader, _, awakened_leaders = release.build_leader(
            official_leader, base_leader,
        )
        terminal_leader = release.read_plan_logical(self.android_plan, release.LEADER_LOGICAL)
        self.assertEqual(terminal_leader, expected_leader)
        official_map = core.read_orderedmap_file_from_bytes(official_leader)
        terminal_map = core.read_orderedmap_file_from_bytes(terminal_leader)
        for key, awakened_rows in awakened_leaders.items():
            rows = core.read_csv_lines(terminal_map[key])
            official_rows = core.read_csv_lines(official_map[key])
            self.assertEqual(
                release.without_gate(release.select_rows(rows, 0, 1, 2), 1, 2),
                official_rows,
            )
            self.assertEqual(
                release.without_gate(release.select_rows(rows, 1, 1, 2), 1, 2),
                awakened_rows,
            )

        summer_leader = release.select_rows(
            core.read_csv_lines(terminal_map["151045"]), 1, 1, 2,
        )
        summer_damage = [row for row in summer_leader if row[45] == "356"]
        self.assertEqual(len(summer_damage), 1)
        self.assertEqual(summer_damage[0][33], "150")

    def test_server_extensions_match_client_mission_rows(self) -> None:
        definitions = json.loads(release.MISSION_EXTENSION_PATH.read_text(encoding="utf-8"))
        rewards = json.loads(release.REWARD_EXTENSION_PATH.read_text(encoding="utf-8"))
        links = json.loads(release.EXTENSION_PATH.read_text(encoding="utf-8"))
        self.assertEqual(definitions, self.server_assets["mission_char_awake_cnmod.json"])
        self.assertEqual(rewards, self.server_assets["mission_char_awake_reward_cnmod.json"])
        self.assertEqual(links, self.server_assets["character_awake_extension.json"])
        self.assertEqual(len(definitions), 36)
        self.assertEqual(len(rewards), 36)


if __name__ == "__main__":
    unittest.main()
