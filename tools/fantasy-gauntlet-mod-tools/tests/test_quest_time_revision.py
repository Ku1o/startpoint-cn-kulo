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
from wf_quest_time_revision import ABYSS_REVISION_KEY, RUSH_QUEST_MEMBER, quest_time_revisions, validate_current_chain


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

    def test_ex_revision_is_independent_and_cannot_be_omitted_from_release(self):
        original = self.revision(self.table)[ABYSS_REVISION_KEY]
        self.table['700100']={'1':'700100001,1,1,EX A','30':'700100030,1,30,EX B','99':'endless'}
        first = self.revision(self.table)
        self.assertEqual(first[ABYSS_REVISION_KEY],original)
        self.table['700100']['99']='new endless'
        self.assertEqual(self.revision(self.table),first)
        self.table['700100']['30']='700100030,1,30,EX C'
        current=self.revision(self.table)
        self.assertNotEqual(current['rush:700100'],first['rush:700100'])
        self.assertEqual(current[ABYSS_REVISION_KEY],original)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); active=root/'assets/asset-patch/active'; active.mkdir(parents=True)
            with zipfile.ZipFile(active/'tower.zip','w') as archive:
                archive.writestr(RUSH_QUEST_MEMBER,q.build_node(self.table))
            patch=dict(type='patch',enabled=True,version='1.4.111',archive='tower.zip',
                       quest_time_revisions={ABYSS_REVISION_KEY:original})
            manifest=active.parent/'manifest.json'
            manifest.write_text(json.dumps({'patches':[patch]}))
            with self.assertRaisesRegex(ValueError,'700100'):
                validate_current_chain(root)
            patch['quest_time_revisions']=first
            manifest.write_text(json.dumps({'patches':[patch]}))
            with self.assertRaisesRegex(ValueError,'stale'):
                validate_current_chain(root)
            patch['quest_time_revisions']=current
            manifest.write_text(json.dumps({'patches':[patch]}))
            self.assertEqual(validate_current_chain(root)['modes']['rush:700100']['revision'],current['rush:700100'])

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
        self.assertEqual(64, len(validate_current_chain(root)['revision']))

    def test_consolidation_cannot_drop_revision_and_later_metadata_can_repair_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / 'assets/asset-patch/active'
            active.mkdir(parents=True)
            manifest = active.parent / 'manifest.json'
            old = self.revision(self.table)
            changed = copy.deepcopy(self.table)
            changed['700099']['1'] = '700099001,1,1,new tower'
            new = self.revision(changed)
            with zipfile.ZipFile(active / 'tower.zip', 'w') as archive:
                archive.writestr(RUSH_QUEST_MEMBER, q.build_node(changed))
            patches = [dict(type='patch', enabled=True, version='1.4.96', quest_time_revisions=old),
                       dict(type='patch', enabled=True, version='1.4.104', archive='tower.zip')]
            manifest.write_text(json.dumps(dict(patches=patches)))
            with self.assertRaisesRegex(ValueError, 'stale'):
                validate_current_chain(root)
            patches.append(dict(type='patch', enabled=True, version='1.4.106', quest_time_revisions=new))
            manifest.write_text(json.dumps(dict(patches=patches)))
            self.assertEqual('1.4.106', validate_current_chain(root)['marker_version'])

    def test_description_proof_preserves_records_but_rejects_combat_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / 'assets/asset-patch/active'
            active.mkdir(parents=True)
            before = copy.deepcopy(self.table)
            after = copy.deepcopy(before)
            after['700099']['1'] = '700099001,1,1,description fixed'
            original = self.revision(before)
            prior = dict(id='old', type='patch', enabled=True, version='1.4.112',
                         archive='old.zip', quest_time_revisions=original)
            patch = dict(id='new', type='patch', enabled=True, version='1.4.113',
                         archive='new.zip', quest_time_revisions=original)
            def write():
                patch['quest_description_revisions'] = {ABYSS_REVISION_KEY: {
                    'content_revision': self.revision(after)[ABYSS_REVISION_KEY],
                    'record_revision': original[ABYSS_REVISION_KEY], 'reference_patch': 'old'}}
                for name, table in [('old.zip', before), ('new.zip', after)]:
                    with zipfile.ZipFile(active/name, 'w') as archive:
                        archive.writestr(RUSH_QUEST_MEMBER, q.build_node(table))
                (active.parent/'manifest.json').write_text(json.dumps({'patches':[prior,patch]}))
            write()
            self.assertEqual(validate_current_chain(root)['revision'], original[ABYSS_REVISION_KEY])
            after['700099']['1'] = '700099001,2,1,description fixed'
            write()
            with self.assertRaisesRegex(ValueError, 'combat columns'):
                validate_current_chain(root)
            after['700099']['1'] = '700099001,1,1,description fixed'
            after['700099']['99'] = 'changed endless'
            write()
            with self.assertRaisesRegex(ValueError, 'endless'):
                validate_current_chain(root)

    def test_multipart_chain_last_tower_wins_over_archive_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / 'assets/asset-patch/active'
            active.mkdir(parents=True)
            changed = copy.deepcopy(self.table)
            changed['700099']['1'] = '700099001,1,1,later split tower'
            for name, table in [('first.zip', self.table), ('second.zip', changed)]:
                with zipfile.ZipFile(active / name, 'w') as archive:
                    archive.writestr(RUSH_QUEST_MEMBER, q.build_node(table))
            patch = dict(type='patch', enabled=True, version='1.4.106', archive='first.zip',
                         chain=['first.zip', 'second.zip'], quest_time_revisions=self.revision(self.table))
            manifest = active.parent / 'manifest.json'
            manifest.write_text(json.dumps(dict(patches=[patch])))
            with self.assertRaisesRegex(ValueError, 'stale'):
                validate_current_chain(root)
            patch['quest_time_revisions'] = self.revision(changed)
            manifest.write_text(json.dumps(dict(patches=[patch])))
            self.assertEqual(self.revision(changed)[ABYSS_REVISION_KEY], validate_current_chain(root)['revision'])


if __name__ == "__main__":
    unittest.main()
