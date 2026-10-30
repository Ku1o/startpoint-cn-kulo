"""Small resolver-failure regressions; no private assets or release rebuild."""
from __future__ import annotations

import ast
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from production_20261031_cdn import release344
from production_20261031_cdn.common import SparseChain


RELATIVE = 'ab/' + '0' * 38
MEMBER = 'production/upload/' + RELATIVE
ARCHIVE = 'pinball-1.4.54-1.4.258-1-probe.zip'
SPEC = {'baseVersion': '1.4.258', 'targetVersion': '1.4.344',
        'hashedLogicalPrefix': '@sha1/', 'pr': {}}


class StopAfterBaseline(Exception):
    """Stop the synthetic probe before unrelated344 composition runs."""


class BaselineFailureTests(unittest.TestCase):
    def probe(self, resolver, observed):
        def pr_probe(context, spec, baseline, support):
            observed.append(baseline(MEMBER))
            raise StopAfterBaseline

        context = SimpleNamespace(repo=Path('.'), get_member=resolver)
        with patch.object(release344, '_load_support', return_value=object()), \
                patch.object(release344, '_pr_terminal', side_effect=pr_probe):
            release344.build(context, SPEC)

    def chain(self, root, payload, listed):
        active, baseline = root / 'active', root / 'pristine'
        active.mkdir()
        baseline.mkdir()
        if payload is not None:
            (active / ARCHIVE).write_bytes(payload)
        receipt = {'name': ARCHIVE, 'size': len(payload or b''),
                   'sha256': hashlib.sha256(payload or b'').hexdigest(),
                   'files': [MEMBER] if listed else []}
        manifest = root / 'manifest.json'
        manifest.write_text(json.dumps({'cdn_version': '1.4.258', 'patches': [{
            'version': '1.4.258', 'depends_on': '1.4.54', 'enabled': True,
            'archive': ARCHIVE, 'archive_integrity': [receipt]}]}), 'utf-8')
        return SparseChain(manifest, [active], baseline, '1.4.258')

    def test_missing_enabled_archive_propagates(self):
        with tempfile.TemporaryDirectory() as directory:
            chain = self.chain(Path(directory), None, listed=True)
            observed = []
            with self.assertRaisesRegex(FileNotFoundError, 'Missing enabled archive'):
                self.probe(chain.get_member, observed)
            self.assertEqual(observed, [])

    def test_corrupt_enabled_archive_propagates(self):
        with tempfile.TemporaryDirectory() as directory:
            chain = self.chain(Path(directory), b'not-a-zip', listed=True)
            observed = []
            with self.assertRaises(zipfile.BadZipFile):
                self.probe(chain.get_member, observed)
            self.assertEqual(observed, [])

    def test_resolver_key_error_propagates(self):
        def missing_key(root, relative):
            raise KeyError('resolver metadata missing')

        observed = []
        with self.assertRaisesRegex(KeyError, 'resolver metadata missing'):
            self.probe(missing_key, observed)
        self.assertEqual(observed, [])

    def test_genuinely_absent_resource_remains_none(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w'):
            pass
        with tempfile.TemporaryDirectory() as directory:
            chain = self.chain(Path(directory), stream.getvalue(), listed=False)
            observed = []
            with self.assertRaises(StopAfterBaseline):
                self.probe(chain.get_member, observed)
            self.assertEqual(observed, [None])

    def test_candidate_source_syntax(self):
        tools = Path(__file__).resolve().parent
        files = [tools / 'rebuild_production_20261031_cdn.py', Path(__file__).resolve(),
                 *sorted((tools / 'production_20261031_cdn').glob('*.py'))]
        for path in files:
            with self.subTest(source=path.name):
                ast.parse(path.read_text('utf-8-sig'), filename=path.name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
