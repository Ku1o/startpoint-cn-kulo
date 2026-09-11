"""Regression against the actual pre-Lens APKs that caused C7050.

Requires the locally retained current and rejected artifacts named by the registry.
No APK is executed or modified. Missing artifacts are errors, not silent skips.
"""
from pathlib import Path
import json
import tempfile
import unittest
import zipfile

import build_apk as build


class LensBaselineRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((build.HERE.parent / 'android-accepted.json').read_text('utf-8'))

    def check_apk(self, path, accepted):
        with tempfile.TemporaryDirectory(prefix='abyss-lineage-') as folder:
            swf = Path(folder) / 'client.swf'
            with zipfile.ZipFile(path) as archive:
                swf.write_bytes(archive.read(build.common.SWF_MEMBER))
            if accepted:
                build.check_lens_base(swf)
            else:
                with self.assertRaisesRegex(ValueError, 'Lens v3'):
                    build.check_lens_base(swf)

    def test_historical_lens_inputs_remain_available_for_explicit_reproduction(self):
        for variant in ('public', 'lan'):
            with self.subTest(variant=variant):
                identity = build.resolve_identity(variant, reproduce=True)
                self.check_apk(Path(identity['apk']), True)

    def test_current_accepted_packages_are_not_patched_a_second_time(self):
        for variant, entry in self.record['variants'].items():
            with self.subTest(variant=variant):
                build.baseline_checker.verify(variant)
                with self.assertRaisesRegex(ValueError, 'registry advanced'):
                    build.resolve_identity(variant)

    def test_rejected_autostart_packages_cannot_be_reused(self):
        for entry in self.record['excluded_artifacts']:
            with self.subTest(apk=entry['apk']):
                self.check_apk(build.ROOT / entry['apk'], False)


if __name__ == '__main__':
    unittest.main()
