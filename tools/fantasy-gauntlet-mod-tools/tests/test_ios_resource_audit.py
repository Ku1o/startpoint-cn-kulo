"""Effective iOS coverage, legacy provenance and stale-source regressions."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wf_atf
import wf_ios_resource_audit as audit
import wf_mod_tool as core


class IosAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def entry(self, label, ver, data):
        path = self.root / (label + '.zip')
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr(label, data)
        return audit.Entry(path, label, audit.version(ver))

    def test_legacy_ios_later_than_android_source_is_current(self):
        source = self.entry('source', '1.4.61', b'unchanged')
        self.assertFalse(audit.source_changed(source, [source], (1, 4, 84)))

    def test_new_png_after_ios_is_stale(self):
        old = self.entry('old', '1.4.61', b'old pixels')
        new = self.entry('new', '1.4.119', b'new pixels')
        self.assertTrue(audit.source_changed(new, [old, new], (1, 4, 84)))

    def test_republished_identical_png_is_not_stale(self):
        old = self.entry('old', '1.4.61', b'same pixels')
        new = self.entry('new', '1.4.119', b'same pixels')
        self.assertFalse(audit.source_changed(new, [old, new], (1, 4, 84)))

    def test_source_absent_from_old_ios_epoch_requires_repair(self):
        new = self.entry('new', '1.4.119', b'new pixels')
        self.assertTrue(audit.source_changed(new, [new], (1, 4, 84)))

    def test_non_numeric_cutin_names_are_resolved(self):
        logical = 'character/seris_dragon_king/ui/skill_cutin_matched_1'
        table = core.OrderedMap('fixture', [logical], [b'0,0,1,1'], Path('fixture'))
        data = core.build_orderedmap(table)
        key = ('upload', audit.relative('master/generated/trimmed_image.orderedmap'))
        final = {key: SimpleNamespace(read=lambda: data)}
        expected = logical + '.atf.deflate'
        self.assertEqual(audit.logical_index(final)[audit.relative(expected)], expected)

    def test_missing_ios_fails_and_real_ios_slot_passes(self):
        png = wf_atf.png_encode_rgba(8, 8, bytes([50, 100, 150, 83]) * 64)
        android = self.entry('android', '1.4.119', wf_atf.deflate(wf_atf.build_cutin_atf(png)))
        ios = self.entry('ios', '1.4.351', wf_atf.deflate(wf_atf.build_cutin_atf_ios(png)))
        source = self.entry('source', '1.4.119', png)
        self.assertEqual(audit.inspect_pair(android, None, source, [source]), 'missing_ios')
        self.assertIsNone(audit.inspect_pair(android, ios, source, [source]))
        with self.assertRaisesRegex(ValueError, '内容相同'):
            audit.inspect_pair(android, android, source, [source])


if __name__ == '__main__':
    unittest.main()
