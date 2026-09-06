import copy
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wf_quest_lib as q
import wf_publish
from wf_quest_time_revision import ABYSS_REVISION_KEY, RUSH_QUEST_MEMBER, quest_time_revisions


class QuestTimeRevisionTests(unittest.TestCase):
    def setUp(self):
        self.table = {"700099": {"1": "700099001,1,1,Boss A", "2": "700099002,1,2,Boss B", "99": "endless"},
                      "700098": {"1": "fantasy"}, "700007": {"1": "official"}}

    def revision(self, table):
        return quest_time_revisions({RUSH_QUEST_MEMBER: q.build_node(table)})

    def test_new_floor_content_changes_the_whole_tower_revision(self):
        previous = self.revision(self.table)
        self.table["700099"]["2"] = "700099002,1,2,Boss C"
        self.assertNotEqual(previous, self.revision(self.table))

    def test_unrelated_quests_endless_and_map_order_do_not_reset_times(self):
        previous = self.revision(self.table)
        changed = copy.deepcopy(self.table)
        changed["700098"]["1"] = "new fantasy"
        changed["700007"]["1"] = "new official"
        changed["700099"]["99"] = "new endless"
        changed["700099"] = dict(reversed(list(changed["700099"].items())))
        self.assertEqual(previous, self.revision(changed))
        self.assertEqual({}, quest_time_revisions({"production/upload/icon": b"icon"}))

    def test_invalid_tower_fails_without_a_revision(self):
        with self.assertRaises(ValueError):
            self.revision({"700099": {"99": "endless"}})
        with self.assertRaises(ValueError):
            quest_time_revisions({RUSH_QUEST_MEMBER: b"malformed"})

    def test_publisher_registers_the_revision_from_the_archived_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / "active"
            active.mkdir()
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"patches": []}), encoding="utf-8")
            archive = active / "pinball-1.4.101-1.4.102-1-test.zip"
            blob = q.build_node(self.table)
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr(RUSH_QUEST_MEMBER, blob)
            with mock.patch.object(wf_publish, "ACTIVE_PATCH", active), mock.patch.object(wf_publish, "PATCH_MANIFEST", manifest):
                wf_publish._register_active_patch(archive, [wf_publish.PreparedFile(RUSH_QUEST_MEMBER, blob, "")], "1.4.101", "1.4.102")
            published = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(self.revision(self.table), published["patches"][0]["quest_time_revisions"])

    def test_current_revision_matches_the_winning_live_archive(self):
        root = Path(__file__).resolve().parents[3]
        manifest = json.loads((root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig"))
        patches = sorted((p for p in manifest["patches"] if p.get("enabled") and p.get("type") == "patch"),
                         key=lambda p: tuple(map(int, p["version"].split("."))), reverse=True)
        for patch in patches:
            names = patch.get("archives") or [patch.get("archive")]
            for name in names:
                if not isinstance(name, str):
                    continue
                with zipfile.ZipFile(root / "assets/asset-patch/active" / name) as z:
                    if RUSH_QUEST_MEMBER not in z.namelist():
                        continue
                    expected = quest_time_revisions({RUSH_QUEST_MEMBER: z.read(RUSH_QUEST_MEMBER)})
                    self.assertEqual(expected[ABYSS_REVISION_KEY], patch["quest_time_revisions"][ABYSS_REVISION_KEY])
                    return
        self.fail("No effective Rush quest table found in the active patch chain")


if __name__ == "__main__":
    unittest.main()
