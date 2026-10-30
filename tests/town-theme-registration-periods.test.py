"""Synthetic registration checks; never read the real CDN or write real assets."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

MODULE = Path(__file__).resolve().parents[1] / 'tools/build-town-theme-catalog.py'
spec = importlib.util.spec_from_file_location('town_theme_registration', MODULE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def row(code='example', kind='1', start='2024-01-01 00:00:00', end='2024-01-02 23:59:59'):
    value = [code, kind, '', '', '', '', 'town/background/example/main', 'town/background/example/blur', '(None)', '(None)', '', '', '', '', '', '', '', '', '', 'bgm/example']
    if kind == '1':
        value[2:4] = [start, end]
    elif kind == '2':
        value[4:6] = [start, end]
    return value


class Periods(unittest.TestCase):
    def test_all_aliases_numeric_order_and_exact_behavior(self):
        selected = row('selected')
        annual = row('annual', '2', '12-20 12:00:00', '01-05 04:59:59')
        normal = row('normal', '0')
        changed = row('different_particle_behavior')
        changed[10] = '1'
        parsed = {'100': [selected], '12': [annual], '2': [row('same_identity_ignored')], '1': [normal], '3': [changed]}
        self.assertEqual(tool.original_periods(parsed, selected), [
            {'nativeTownContentId': 2, 'kind': 'event', 'start': '2024-01-01 00:00:00', 'end': '2024-01-02 23:59:59'},
            {'nativeTownContentId': 12, 'kind': 'annual', 'start': '12-20 12:00:00', 'end': '01-05 04:59:59'},
            {'nativeTownContentId': 100, 'kind': 'event', 'start': '2024-01-01 00:00:00', 'end': '2024-01-02 23:59:59'}])
        self.assertEqual(tool.original_periods({'1': [normal]}, normal), [])

    def test_event_dates_are_strict_and_not_annualized(self):
        valid = row(start='2024-02-29 00:00:00', end='2024-02-29 00:00:00')
        self.assertEqual(tool.native_period(valid)['kind'], 'event')
        for start, end in [('', ''), ('2023-02-29 00:00:00', '2024-01-01 00:00:00'),
                           ('2024-01-02 00:00:00', '2024-01-01 00:00:00'),
                           ('2024-1-01 00:00:00', '2024-01-02 00:00:00'),
                           ('2024-01-01 24:00:00', '2024-01-02 00:00:00')]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                tool.required_resources(row(start=start, end=end))

    def test_annual_time_cross_year_and_calendar_validation(self):
        annual = row(kind='2', start='12-31 23:59:59', end='01-01 00:00:00')
        self.assertIn('bgm/example.mp3', tool.required_resources(annual))
        self.assertEqual(tool.native_period(annual), {'kind': 'annual', 'start': '12-31 23:59:59', 'end': '01-01 00:00:00'})
        for value in ['', '02-29 00:00:00', '04-31 00:00:00', '13-01 00:00:00', '01-01', '1-01 00:00:00', '01-01 24:00:00', '01-01 00:00:60', '2024-01-01 00:00:00']:
            for side in ('start', 'end'):
                args = {'start': '12-20 12:00:00', 'end': '01-05 04:59:59', side: value}
                with self.subTest(value=value, side=side), self.assertRaises(ValueError):
                    tool.required_resources(row(kind='2', **args))

    def test_invalid_matching_alias_is_not_hidden(self):
        selected = row()
        for parsed in [{'1': [selected], '2': [row(start='', end='')]},
                       {'1': [selected], '02': [row()]},
                       {'1': [selected], '2': [row(), row()]},
                       {'1': [selected], '2': [row(kind='3')]}]:
            with self.subTest(parsed=parsed), self.assertRaises(ValueError):
                tool.original_periods(parsed, selected)

    def test_compact_unicode_digest(self):
        value = [{'nativeTownContentId': 3, 'kind': 'event', 'start': '2024-01-01 00:00:00', 'end': '2024-01-02 23:59:59'}]
        expected = b'[{"nativeTownContentId":3,"kind":"event","start":"2024-01-01 00:00:00","end":"2024-01-02 23:59:59"}]'
        self.assertEqual(tool.compact_sha(value), hashlib.sha256(expected).hexdigest())
        self.assertEqual(tool.compact_sha(['春樱']), hashlib.sha256('["春樱"]'.encode()).hexdigest())

    def test_full_synthetic_registration_receipt_and_dry_run(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix='town-registration-', dir=os.environ.get('TOWN_REGISTRATION_TEST_ROOT')) as scratch:
            root = Path(scratch)
            repo, source = root/'target', root/'source'
            for location in (repo, source):
                (location/'assets/asset-patch').mkdir(parents=True)
                (location/'assets/asset-patch/manifest.json').write_text('{"cdn_version":"1.4.999"}', encoding='utf8')
            png = io.BytesIO()
            Image.new('RGBA', (8, 12), (15, 30, 45, 255)).save(png, format='PNG')
            selected = row('native_selected')
            annual = row('native_annual', '2', '12-20 12:00:00', '01-05 04:59:59')
            parsed = {'100': [selected], '2': [annual], '1': [row('normal', '0')]}
            resources = {tool.MASTER: json.dumps(parsed).encode(), 'town/background/example/main.png': png.getvalue(),
                         'town/background/example/blur.png': png.getvalue(), 'bgm/example.mp3': b'ID3synthetic'}
            archive = source/'fixture.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                for logical, raw in resources.items():
                    digest = hashlib.sha1(logical.encode()).hexdigest()
                    output.writestr('production/upload/'+digest[:2]+'/'+digest[2:], raw)
            exporter = root/'fixture_exporter.py'
            exporter.write_text('''import hashlib,json,zipfile
def member(logical):
 digest=hashlib.sha1(logical.encode()).hexdigest();return 'production/upload/'+digest[:2]+'/'+digest[2:]
def parse_rows(raw,logical):return json.loads(raw)
def resolve(root,logicals):
 archive=root/'fixture.zip';stat=archive.stat();manifest=(root/'assets/asset-patch/manifest.json').read_bytes()
 with zipfile.ZipFile(archive) as source:
  values={logical:(source.read(member(logical)),{'archive':'fixture.zip','sha256':hashlib.sha256(source.read(member(logical))).hexdigest()}) for logical in logicals}
 return values,{'manifestSha256':hashlib.sha256(manifest).hexdigest(),'assetVersion':'1.4.999','actualChain':[{'archive':'fixture.zip','size':stat.st_size,'mtimeNs':str(stat.st_mtime_ns)}]}
''', encoding='utf8')
            metadata = root/'spec.json'
            metadata.write_text(json.dumps({'schemaVersion': 1, 'resourceVersion': '1.4.999', 'themes': [{'id': 'example', 'name': '示例', 'description': '合成夹具', 'nativeTownContentId': 100}, {'id': 'annual', 'name': '年度', 'description': '年度行可登记', 'nativeTownContentId': 2}]}), encoding='utf8')
            args = SimpleNamespace(repo=str(repo), resource_root=str(source), exporter=str(exporter), spec=str(metadata), write=False)
            dry = tool.build(args)
            self.assertEqual(dry['mode'], 'dry-run')
            self.assertFalse((repo/'assets/town_themes.json').exists())
            args.write = True
            written = tool.build(args)
            self.assertEqual(written['mode'], 'write')
            catalog = json.loads((repo/'assets/town_themes.json').read_bytes())
            receipt_raw = (repo/'assets/town_theme_resource_receipt.json').read_bytes()
            receipt = json.loads(receipt_raw)
            self.assertEqual(receipt['master']['sha256'], hashlib.sha256(resources[tool.MASTER]).hexdigest())
            for theme, evidence in zip(catalog['themes'], receipt['themes']):
                self.assertEqual([period['nativeTownContentId'] for period in theme['originalPeriods']], [2, 100])
                self.assertEqual(evidence['originalPeriodsSha256'], tool.compact_sha(theme['originalPeriods']))
                self.assertEqual(theme['resourceEvidence']['receiptSha256'], hashlib.sha256(receipt_raw).hexdigest())
                self.assertEqual(theme['originalPeriods'][1]['kind'], 'event')
                self.assertEqual(theme['originalPeriods'][1]['start'], '2024-01-01 00:00:00')
                self.assertEqual(theme['originalPeriods'][0]['start'], '12-20 12:00:00')


class TrustedArchiveAliases(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='town-alias-', dir=os.environ.get('TOWN_REGISTRATION_TEST_ROOT'))
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.source, self.cdn, self.other = (self.root / name for name in ('source', 'cdn', 'other'))
        for directory in (self.source, self.cdn, self.other):
            directory.mkdir()
        self.logical, self.raw = 'bgm/example.mp3', b'ID3synthetic'
        self.exporter = SimpleNamespace(member=lambda logical: 'production/upload/example')
        for directory in (self.source, self.cdn, self.other):
            with zipfile.ZipFile(directory / 'fixture.zip', 'w') as archive:
                archive.writestr(self.exporter.member(self.logical), self.raw)
        self.link(self.source / '.cdn', self.cdn)
        self.trusted = tool.resolve_trusted_cdn_root(self.source, str(self.cdn))

    @staticmethod
    def link(alias, target):
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(target)], check=True, capture_output=True)
        else:
            alias.symlink_to(target, target_is_directory=True)

    def check_archive(self, relative, trusted=None):
        physical = (self.source / relative).resolve(strict=True)
        state = physical.stat()
        identity = {'archive': relative, 'sha256': tool.sha(self.raw)}
        source = {'manifestSha256': tool.sha(b'manifest'), 'assetVersion': '1.4.999',
                  'actualChain': [{'archive': relative, 'size': state.st_size, 'mtimeNs': str(state.st_mtime_ns)}]}
        return (
            lambda: tool.verify_snapshot(source, b'manifest', '1.4.999', self.source, trusted),
            lambda: tool.verify_identity(self.source, self.logical, self.raw, identity, self.exporter, trusted),
        )

    def test_explicit_exact_alias_and_default_local_archive(self):
        for check in self.check_archive('.cdn/fixture.zip', self.trusted):
            self.assertTrue(check())
        for check in self.check_archive('fixture.zip'):
            self.assertTrue(check())

    def test_undeclared_external_alias_stays_rejected(self):
        for check in self.check_archive('.cdn/fixture.zip'):
            with self.assertRaisesRegex(ValueError, 'escapes'):
                check()

    def test_declared_target_must_match_exact_cdn_directory(self):
        for declared in (self.other, self.cdn / 'fixture.zip'):
            with self.subTest(declared=declared), self.assertRaises(ValueError):
                tool.resolve_trusted_cdn_root(self.source, str(declared))

    def test_other_alias_cannot_borrow_cdn_trust(self):
        for name in ('other_alias', '.cdn-extra'):
            self.link(self.source / name, self.cdn)
            for check in self.check_archive(name + '/fixture.zip', self.trusted):
                with self.subTest(alias=name), self.assertRaisesRegex(ValueError, 'escapes'):
                    check()

    def test_nested_links_cannot_escape_trusted_root(self):
        # Even returning inside resource-root must not authorize a .cdn escape.
        for name, target in (('outside', self.other), ('back_to_source', self.source)):
            self.link(self.cdn / name, target)
            for check in self.check_archive('.cdn/' + name + '/fixture.zip', self.trusted):
                with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'trusted CDN root'):
                    check()

    def test_alias_retargeted_after_capture_is_rejected(self):
        alias = self.source / '.cdn'
        if os.name == 'nt':
            os.rmdir(alias)
        else:
            alias.unlink()
        self.link(alias, self.other)
        for check in self.check_archive('.cdn/fixture.zip', self.trusted):
            with self.assertRaisesRegex(ValueError, 'alias changed'):
                check()

    def test_alias_does_not_relax_digest_or_member_checks(self):
        for identity in (
            {'archive': '.cdn/fixture.zip', 'sha256': '0' * 64},
            {'archive': '.cdn/fixture.zip', 'sha256': tool.sha(self.raw), 'member': 'wrong/member'},
        ):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                tool.verify_identity(self.source, self.logical, self.raw, identity, self.exporter, self.trusted)
        for relative in ('../cdn/fixture.zip', '.cdn/../fixture.zip', '/fixture.zip'):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                tool.archive_path(self.source, relative, self.trusted)

    def test_trust_does_not_allow_writes_to_source_assets(self):
        target = self.root / 'target'
        target.mkdir()
        self.link(target / 'assets', self.cdn)
        with self.assertRaises(ValueError):
            tool.output_path(target, self.source, 'assets/forbidden.json')
        nested_target = self.cdn / 'target'
        nested_target.mkdir()
        with self.assertRaisesRegex(ValueError, 'read-only trusted CDN root'):
            tool.build(SimpleNamespace(repo=str(nested_target), resource_root=str(self.source),
                                       trusted_cdn_root=str(self.cdn)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
