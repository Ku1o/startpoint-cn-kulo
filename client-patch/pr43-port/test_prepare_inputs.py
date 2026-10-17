"""Failure boundaries for the fixed, sparse APK input preparation entry point."""
import io
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

import prepare_inputs as p


class PrepareInputsTests(unittest.TestCase):
    def test_unknown_apk_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, donor, output = root / "base.apk", root / "donor.apk", root / "prepared"
            base.write_bytes(b"unknown APK")
            donor.write_bytes(b"another unknown APK")
            with self.assertRaisesRegex(p.InputError, "unknown APK SHA256"):
                p.prepare(base, donor, output)
            self.assertFalse(output.exists())
            self.assertEqual(base.read_bytes(), b"unknown APK")

    def test_output_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.apk"
            source.write_bytes(b"input")
            existing = root / "existing"
            existing.mkdir()
            checkout = root / "checkout"
            checkout.mkdir()
            (checkout / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
            forbidden = (existing, source, root / ".cdn" / "new",
                         root / ".git" / "new", checkout / "new",
                         p.HERE / "generated-should-not-exist")
            for output in forbidden:
                with self.subTest(output=output), self.assertRaises(p.InputError):
                    p.output_boundary(output, [source])
            self.assertEqual(p.output_boundary(root / "new", [source]), root / "new")

    def test_archive_path_traversal_and_aliases(self):
        for name in ("../escape", "/absolute", "C:/drive", "nested\\escape",
                     "a/../b", "a//b", "a/./b", "trailing./file", "a\x00b", "CON.txt", "a/NUL"):
            with self.subTest(name=name), self.assertRaises(p.InputError):
                p.safe_name(name)
        self.assertEqual(p.safe_name("assets/META-INF/AIR/file"), "assets/META-INF/AIR/file")

    def test_duplicate_or_case_colliding_archive_rejected(self):
        for names in (("same", "same"), ("Name", "name")):
            raw = io.BytesIO()
            with warnings.catch_warnings(), zipfile.ZipFile(raw, "w") as package:
                warnings.simplefilter("ignore", UserWarning)
                for name in names:
                    package.writestr(name, b"value")
            with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as package:
                with self.assertRaises(p.InputError):
                    p.zip_inventory(package)

    def test_zip_link_and_uncompressed_limit_rejected(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as package:
            info = zipfile.ZipInfo("linked")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            package.writestr(info, b"target")
        with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as package:
            with self.assertRaisesRegex(p.InputError, "links/special"):
                p.zip_inventory(package)
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as package:
            package.writestr("large", b"small")
        with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as package:
            package.infolist()[0].file_size = p.MAX_ARCHIVE_BYTES + 1
            with self.assertRaisesRegex(p.InputError, "uncompressed size"):
                p.zip_inventory(package)

    def test_crc_failure_rejected(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as package:
            package.writestr("payload", b"bytes")
        with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as package:
            package.infolist()[0].CRC ^= 1
            with self.assertRaisesRegex(p.InputError, "CRC failure"):
                p.zip_inventory(package)


if __name__ == "__main__":
    unittest.main()
