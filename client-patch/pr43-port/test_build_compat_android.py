"""CLI and output-boundary checks; optional immutable-fixture SWF equivalence.

Set PR43_COMPAT_BASE_APK, PR43_COMPAT_LAN_HOST, PR43_COMPAT_PUBLIC_ORIGIN and
PR43_COMPAT_EXPECTED_SWF for the full byte-equivalence check. The fixture test
only reads those inputs and keeps the rebuilt SWF in memory.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

import build_compat_android as build


LAN = '192.0.2.10'
ORIGIN = 'http://203.0.113.20:8001'


class EndpointTests(unittest.TestCase):
    def test_exact_origin_and_bare_source_host(self):
        self.assertEqual(build.origins(LAN, ORIGIN), (f'http://{LAN}:8001', ORIGIN))
        self.assertEqual(build.origins('test.lan', 'http://game.example:8001'),
                         ('http://test.lan:8001', 'http://game.example:8001'))

    def test_refuses_silent_url_normalization_or_component_dropping(self):
        for value in ('https://game.example:8001', 'http://game.example',
                      'http://game.example:80', 'http://game.example:8001/',
                      'http://game.example:8001/path', 'http://game.example:8001?x=1',
                      'http://game.example:8001#fragment', 'http://name@game.example:8001',
                      'http://game.example:8001?', ' http://game.example:8001',
                      'http://game.example:8001\n', 'http://game.example:08001',
                      'http://game.example.:8001', 'http://[::1]:8001'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build.origins(LAN, value)

    def test_refuses_nonhost_source_and_noop(self):
        for value in ('', 'http://test.lan', 'test.lan:8001', '../test.lan',
                      'test.lan/path', 'bad_host', '-bad.lan', '192.0.2.999',
                      '192.000.2.10', 'test.lan ', 'test..lan'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build.origins(value, ORIGIN)
        with self.assertRaises(ValueError):
            build.origins('game.example', 'http://game.example:8001')


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'base.bin'
        self.base.write_bytes(b'wrong carrier')
        self.work = self.root / 'work'
        self.inputs = dict(base_sha256=build.BASE_SHA, old_uuid=build.OLD_UUID,
                           lan_host=LAN, public_origin=ORIGIN)

    def test_bad_carrier_does_not_create_work_or_alter_input(self):
        with self.assertRaisesRegex(ValueError, 'base APK SHA256 mismatch'):
            build.swf_only(self.base, self.work, **self.inputs)
        self.assertFalse(self.work.exists())
        self.assertEqual(self.base.read_bytes(), b'wrong carrier')

    def test_existing_work_is_never_reused_by_swf_stage(self):
        self.work.mkdir()
        marker = self.work / 'keep.txt'
        marker.write_text('keep', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'fresh output directory'):
            build.swf_only(self.base, self.work, **self.inputs)
        self.assertEqual(marker.read_text('utf8'), 'keep')
        self.assertEqual(list(self.work.iterdir()), [marker])

    def test_readonly_baseline_and_input_containment_are_refused(self):
        for target, message in ((self.root / '.cdn' / 'new', 'read-only .cdn'),
                                (self.root, 'contain or replace'),
                                (self.base, 'contain or replace')):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, message):
                build.paths(self.base, target, fresh=True)
        self.assertFalse((self.root / '.cdn').exists())

    def test_package_rejects_an_unrelated_phase_report_before_output(self):
        self.work.mkdir()
        (self.work / 'android-game-report.json').write_text(json.dumps({'passed': True}), encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'report does not match'):
            build.package(self.base, self.work, **self.inputs)
        self.assertEqual({p.name for p in self.work.iterdir()}, {'android-game-report.json'})

    def test_package_cannot_mix_a_different_carrier_receipt_or_destination(self):
        self.work.mkdir()
        report = dict(schema_version=1, passed=True, base_apk=str(self.base.resolve()),
                      base_apk_sha256=build.BASE_SHA, base_air_uuid=build.OLD_UUID,
                      input_swf_sha256=build.SWF_SHA, swf=str(self.work.resolve() / 'android-game.swf'),
                      endpoint_before=f'http://{LAN}:8001', endpoint_after=ORIGIN)
        path = self.work / 'android-game-report.json'
        for field, value in (('base_apk_sha256', '0' * 64),
                             ('base_air_uuid', '12345678-1234-4567-8123-123456789abc'),
                             ('endpoint_after', 'http://other.example:8001')):
            changed = {**report, field: value}
            path.write_text(json.dumps(changed), encoding='utf8')
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'report does not match'):
                build.package(self.base, self.work, **self.inputs)
            self.assertEqual({p.name for p in self.work.iterdir()}, {path.name})

    def test_resolving_a_cdn_symlink_does_not_erase_the_boundary(self):
        target = self.root / 'baseline-target'
        target.mkdir()
        link = self.root / '.cdn'
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as e:
            self.skipTest(f'directory symlinks unavailable: {e}')
        with self.assertRaisesRegex(ValueError, 'read-only .cdn'):
            build.paths(self.base, link / 'new', fresh=True)
        self.assertFalse((target / 'new').exists())

    def test_package_never_overwrites_an_existing_output(self):
        self.work.mkdir()
        prior = self.work / 'unsigned-build.json'
        prior.write_text('keep', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'output already exists'):
            build.package(self.base, self.work, **self.inputs)
        self.assertEqual(prior.read_text('utf8'), 'keep')

    def test_cli_requires_all_environment_specific_arguments(self):
        parser = build.argument_parser()
        required = ['--stage', 'swf', '--base-apk', str(self.base), '--work-dir', str(self.work),
                    '--base-sha256', build.BASE_SHA, '--old-uuid', build.OLD_UUID,
                    '--lan-host', LAN, '--public-origin', ORIGIN]
        self.assertEqual(parser.parse_args(required).public_origin, ORIGIN)
        for flag in ('--base-apk', '--base-sha256', '--old-uuid', '--work-dir', '--lan-host', '--public-origin'):
            args = required.copy()
            at = args.index(flag)
            del args[at:at + 2]
            with self.subTest(flag=flag), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(args)

    def test_carrier_identity_cannot_be_omitted_or_normalized(self):
        for digest, old_uuid in (('', build.OLD_UUID), ('g' * 64, build.OLD_UUID),
                                 (build.BASE_SHA.upper(), build.OLD_UUID),
                                 (build.BASE_SHA, ''), (build.BASE_SHA, build.OLD_UUID.upper()),
                                 (build.BASE_SHA, '00000000-0000-0000-0000-000000000000')):
            with self.subTest(digest=digest, old_uuid=old_uuid), self.assertRaises(ValueError):
                build.validate_carrier_identity(digest, old_uuid)


FIXTURE_NAMES = ('PR43_COMPAT_BASE_APK', 'PR43_COMPAT_LAN_HOST',
                 'PR43_COMPAT_PUBLIC_ORIGIN', 'PR43_COMPAT_EXPECTED_SWF')


@unittest.skipUnless(all(os.environ.get(k) for k in FIXTURE_NAMES), 'external immutable compatibility fixtures not set')
class ImmutableFixtureTests(unittest.TestCase):
    def test_refactor_keeps_the_verified_swf_byte_identical(self):
        base = Path(os.environ['PR43_COMPAT_BASE_APK'])
        expected = Path(os.environ['PR43_COMPAT_EXPECTED_SWF']).read_bytes()
        carrier = base.read_bytes()
        self.assertEqual(build.sha(carrier), build.BASE_SHA)
        with zipfile.ZipFile(io.BytesIO(carrier)) as z:
            source = z.read(build.SWF)
        output, report = build.build_swf(source, lan_host=os.environ['PR43_COMPAT_LAN_HOST'],
                                        public_origin=os.environ['PR43_COMPAT_PUBLIC_ORIGIN'])
        self.assertEqual(output, expected)
        self.assertEqual(len(report['changed_main_bodies']), 2)
        self.assertEqual(len(report['endpoints']), 9)


if __name__ == '__main__':
    unittest.main()
