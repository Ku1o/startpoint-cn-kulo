"""Pinned artwork reads, explicit inputs, and fail-closed archive provenance."""
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import artwork_sources as art


class ArtworkSources(unittest.TestCase):
    key = 'sponsor-special-thanks/degree_mod_special_thanks_wide.png'

    def fixture(self, root, *, member=None, raw=None):
        source = art.SOURCES[self.key]
        if raw is None:
            original = art.read_artwork(self.key)
            raw = art.PNG_STORED + original[8:]
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as bundle:
            bundle.writestr(member or source.member, raw)
        archive = output.getvalue()
        path = root / 'assets/asset-patch/active' / source.archive
        path.parent.mkdir(parents=True)
        path.write_bytes(archive)
        return source, hashlib.sha256(archive).hexdigest()

    def test_all_eight_retained_originals(self):
        self.assertEqual(len(art.SOURCES), 8)
        for key, source in art.SOURCES.items():
            with self.subTest(key=key):
                raw = art.read_artwork(key)
                self.assertEqual(raw[:8], art.PNG_REAL)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), source.png_sha256)

    def test_retired_title_has_no_reader(self):
        with self.assertRaisesRegex(ValueError, 'unsupported artwork key'):
            art.read_artwork('sponsor-special-thanks/degree_mod_special_thanks.png')

    def test_explicit_missing_input_never_falls_back(self):
        with tempfile.TemporaryDirectory(prefix='artwork-input-') as directory:
            with self.assertRaisesRegex(FileNotFoundError, 'explicit artwork input is missing'):
                art.read_artwork(self.key, images_dir=Path(directory))

    def test_custom_input_does_not_require_original_digest_or_archive(self):
        # A different real PNG proves that explicit replacement is not pinned.
        custom = art.read_artwork('five-boss/20260910/五王心核.png')
        with tempfile.TemporaryDirectory(prefix='artwork-input-') as directory:
            root = Path(directory)
            (root / Path(self.key).name).write_bytes(custom)
            self.assertEqual(art.read_artwork(self.key, images_dir=root, repo_root=root), custom)

    def test_explicit_stored_signature_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='artwork-input-') as directory:
            root = Path(directory)
            (root / Path(self.key).name).write_bytes(art.PNG_STORED)
            with self.assertRaisesRegex(ValueError, 'standard PNG signature'):
                art.read_artwork(self.key, images_dir=root)

    def test_wrong_archive_digest_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='artwork-archive-') as directory:
            root = Path(directory)
            self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'archive SHA-256 mismatch'):
                art.read_artwork(self.key, repo_root=root)

    def test_wrong_member_is_rejected_after_valid_archive_digest(self):
        with tempfile.TemporaryDirectory(prefix='artwork-archive-') as directory:
            root = Path(directory)
            source, digest = self.fixture(root, member='different/member')
            with patch.dict(art.ARCHIVES, {source.archive: digest}):
                with self.assertRaisesRegex(ValueError, 'member must occur exactly once'):
                    art.read_artwork(self.key, repo_root=root)

    def test_duplicate_member_is_rejected(self):
        source = art.SOURCES[self.key]
        with tempfile.TemporaryDirectory(prefix='artwork-archive-') as directory:
            root = Path(directory)
            _, digest = self.fixture(root)
            with patch.dict(art.ARCHIVES, {source.archive: digest}):
                # Model a duplicate entry without relying on zipfile's warning.
                with patch.object(zipfile.ZipFile, 'namelist', return_value=[source.member] * 2):
                    with self.assertRaisesRegex(ValueError, 'member must occur exactly once'):
                        art.read_artwork(self.key, repo_root=root)

    def test_wrong_png_digest_is_rejected(self):
        original = art.read_artwork(self.key)
        corrupted = art.PNG_STORED + original[8:-1] + bytes([original[-1] ^ 1])
        with tempfile.TemporaryDirectory(prefix='artwork-archive-') as directory:
            root = Path(directory)
            source, digest = self.fixture(root, raw=corrupted)
            with patch.dict(art.ARCHIVES, {source.archive: digest}):
                with self.assertRaisesRegex(ValueError, 'PNG SHA-256 mismatch'):
                    art.read_artwork(self.key, repo_root=root)

    def test_standard_signature_in_archive_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='artwork-archive-') as directory:
            root = Path(directory)
            source, digest = self.fixture(root, raw=art.read_artwork(self.key))
            with patch.dict(art.ARCHIVES, {source.archive: digest}):
                with self.assertRaisesRegex(ValueError, 'stored lowercase png signature'):
                    art.read_artwork(self.key, repo_root=root)

    def test_consumers_import_and_help_without_cache_writes(self):
        tools = Path(__file__).resolve().parent
        scopes = (tools, tools.parent / 'fantasy-gauntlet-mod-tools')

        def caches():
            return {path: (path.stat().st_size, path.stat().st_mtime_ns)
                    for scope in scopes for path in scope.rglob('*.pyc')}

        before = caches()
        commands = [
            ['-c', 'import replace_five_boss_ui_art; import update_five_boss_item_art'],
            [str(tools / 'replace_five_boss_ui_art.py'), '--help'],
            [str(tools / 'update_five_boss_item_art.py'), 'build', '--help'],
        ]
        for command in commands:
            result = subprocess.run([sys.executable, '-B', *command], cwd=tools,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            if '--help' in command:
                self.assertIn('[--images IMAGES]', result.stdout)
        self.assertEqual(caches(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
