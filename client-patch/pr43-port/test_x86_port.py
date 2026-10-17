"""Fault-injection and byte-preservation tests for the unsigned ABI adapter."""
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

import x86_port as x


def elf(machine, marker=b'', api=('JNI_OnLoad', 'Java_fixture_call'), needed=('libc.so',)):
    strings = bytearray(b'\0')
    indexes = {}
    for s in (*api, *needed):
        indexes[s] = len(strings)
        strings.extend(s.encode() + b'\0')
    symbols = bytes(24) + b''.join(struct.pack('<IBBHQQ', indexes[s], 0x12, 0, 1, 1, 0) for s in api)
    dynamic = b''.join(struct.pack('<QQ', 1, indexes[s]) for s in needed) + bytes(16)
    body = bytes(strings) + symbols + dynamic + marker
    header = bytearray(64)
    header[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', header, 18, machine)
    struct.pack_into('<Q', header, 40, 64 + len(body))
    struct.pack_into('<HH', header, 58, 64, 4)
    sections = bytes(64)
    sections += struct.pack('<IIQQQQIIQQ', 0, 3, 0, 0, 64, len(strings), 0, 0, 1, 0)
    sections += struct.pack('<IIQQQQIIQQ', 0, 11, 0, 0, 64 + len(strings), len(symbols), 1, 0, 8, 24)
    sections += struct.pack('<IIQQQQIIQQ', 0, 6, 0, 0, 64 + len(strings) + len(symbols), len(dynamic), 1, 0, 8, 16)
    return bytes(header) + body + sections


class PortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = self.root / 'inputs'
        self.base = self.root / 'base.apk'
        self.output = self.root / 'out' / 'candidate.apk'
        self.members = {'AndroidManifest.xml': b'identity-unchanged', 'classes.dex': b'dex-original',
                        'assets/game.swf': b'chosen-current-SWF', 'META-INF/AIR/application.xml': b'air-uuid',
                        'META-INF/OLD.SF': b'signature', 'META-INF/OLD.RSA': b'signature',
                        'META-INF/MANIFEST.MF': b'signature', 'assets/META-INF/KEEP.RSA': b'asset',
                        'META-INF/nested/KEEP.SF': b'asset', 'META-INF/NOTICE': b'notice'}
        for n in x.LIBS:
            name = f'lib{n}.so'
            marker = b'33.1.1.620 Android-ARM64' if n == 'Core' else b''
            self.members['lib/arm64-v8a/' + name] = elf(183, marker)
            self.put('lib/x86_64/' + name, elf(62, marker.replace(b'ARM64', b'x64')))
        for a in x.ANES:
            p = x.EXT + a + '/META-INF/ANE/'
            xml = b'<extension xmlns="urn:test"><platforms><platform name="Android-ARM64"><applicationDeployment><initializer>init</initializer></applicationDeployment></platform></platforms></extension>'
            self.members[p + 'extension.xml'] = xml
            self.members[p + 'Android-ARM64/library.swf'] = b'ANE-API-bytecode'
            self.put(p + 'extension.xml', xml.replace(b'</platforms>', b'<platform name="Android-x64"><applicationDeployment><initializer>init</initializer></applicationDeployment></platform></platforms>'))
            self.put(p + 'Android-x64/library.swf', b'ANE-API-bytecode')
        self.write_base()

    def put(self, n, data):
        p = self.inputs / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def write_base(self):
        with zipfile.ZipFile(self.base, 'w') as z:
            z.comment = b'archive comment'
            for n, b in self.members.items():
                info = zipfile.ZipInfo(n, (2024, 2, 3, 4, 5, 6))
                info.compress_type = zipfile.ZIP_STORED if n.startswith('lib/') else zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                info.comment = b'entry comment'
                z.writestr(info, b)

    def run_port(self, **kw):
        args = {'base_sha256': x.sha(self.base.read_bytes()), 'inputs_sha256': x.tree_hash(self.inputs), 'output_root': self.output.parent}
        args.update(kw)
        return x.port(self.base, self.inputs, self.output, **args)

    def test_preserves_game_identity_arm_and_metadata(self):
        report = self.run_port()
        self.assertEqual((report['nativeCount'], report['aneCount']), (15, 13))
        with zipfile.ZipFile(self.base) as before, zipfile.ZipFile(self.output) as after:
            self.assertEqual(after.comment, before.comment)
            for n, data in self.members.items():
                if x.signature(n):
                    self.assertNotIn(n, after.namelist())
                elif not n.endswith('/extension.xml'):
                    self.assertEqual(after.read(n), data, n)
                    for k in ('compress_type', 'date_time', 'external_attr', 'comment', 'extra'):
                        self.assertEqual(getattr(before.getinfo(n), k), getattr(after.getinfo(n), k))
            self.assertEqual(after.read('lib/x86_64/libCore.so'), (self.inputs / 'lib/x86_64/libCore.so').read_bytes())

    def test_accepts_new_final_swf_with_its_own_explicit_hash(self):
        self.members['assets/game.swf'] = b'new-final-functional-SWF'
        self.write_base()
        self.run_port()
        with zipfile.ZipFile(self.output) as z:
            self.assertEqual(z.read('assets/game.swf'), b'new-final-functional-SWF')

    def test_wrong_base_hash(self):
        with self.assertRaisesRegex(x.PortError, 'base SHA256'):
            self.run_port(base_sha256='0' * 64)
        self.assertFalse(self.output.exists())

    def test_wrong_input_hash(self):
        with self.assertRaisesRegex(x.PortError, 'tree SHA256'):
            self.run_port(inputs_sha256='0' * 64)

    def test_missing_native(self):
        (self.inputs / 'lib/x86_64/libSocketHelper.so').unlink()
        with self.assertRaisesRegex(x.PortError, '15 native'):
            self.run_port()

    def test_wrong_abi(self):
        self.put('lib/x86_64/libCore.so', elf(183, b'33.1.1.620 Android-x64'))
        with self.assertRaisesRegex(x.PortError, 'ELF machine'):
            self.run_port()

    def test_missing_native_api(self):
        self.put('lib/x86_64/libSocketHelper.so', elf(62, api=('JNI_OnLoad',)))
        with self.assertRaisesRegex(x.PortError, 'JNI API mismatch'):
            self.run_port()

    def test_unresolved_dependency(self):
        self.put('lib/x86_64/libsobot.so', elf(62, needed=('libmissing.so',)))
        with self.assertRaisesRegex(x.PortError, 'unresolved'):
            self.run_port()

    def test_missing_resource(self):
        next(self.inputs.rglob('library.swf')).unlink()
        with self.assertRaisesRegex(x.PortError, 'missing input ANE resource'):
            self.run_port()

    def test_changed_arm_ane_api(self):
        resource = next(n for n in self.members if n.endswith('Android-ARM64/library.swf'))
        self.members[resource] = b'new incompatible ANE bytecode'
        self.write_base()
        with self.assertRaisesRegex(x.PortError, 'resource/API differs'):
            self.run_port()

    def test_existing_x64_conflict_is_not_overwritten(self):
        self.members['lib/x86_64/libCore.so'] = b'different existing native'
        self.write_base()
        with self.assertRaisesRegex(x.PortError, 'conflicting existing native'):
            self.run_port()

    def test_existing_ane_resource_conflict(self):
        n = next(n for n in self.members if n.endswith('Android-ARM64/library.swf'))
        self.members[n.replace('/Android-ARM64/', '/Android-x64/')] = b'keep me'
        self.write_base()
        with self.assertRaisesRegex(x.PortError, 'conflicting existing ANE resource'):
            self.run_port()

    def test_existing_identical_x64_is_preserved(self):
        self.run_port()
        first = self.output.read_bytes()
        self.base.write_bytes(first)
        self.output = self.output.parent / 'second.apk'
        report = self.run_port()
        self.assertEqual(report['addedMembers'], 0)
        with zipfile.ZipFile(self.base) as before, zipfile.ZipFile(self.output) as after:
            for n in before.namelist():
                self.assertEqual(before.read(n), after.read(n))

    def test_incompatible_platform_api(self):
        desc = next(n for n in self.members if n.endswith('/extension.xml'))
        self.put(desc, (self.inputs / desc).read_bytes().replace(b'<initializer>init</initializer>', b'<initializer>other</initializer>'))
        with self.assertRaisesRegex(x.PortError, 'initializer/finalizer'):
            self.run_port()

    def test_wrong_air_version(self):
        n = 'lib/arm64-v8a/libCore.so'
        self.members[n] = self.members[n].replace(b'33.1.1.620', b'33.1.1.999')
        self.write_base()
        with self.assertRaisesRegex(x.PortError, 'base AIR'):
            self.run_port()

    def test_unexpected_inputs_are_not_silently_ignored(self):
        self.put('assets/unrelated-resource', b'not part of ABI patch')
        with self.assertRaisesRegex(x.PortError, 'unexpected input'):
            self.run_port()

    def test_path_traversal_and_duplicate_members(self):
        self.members['../escape'] = b'bad'
        self.write_base()
        with self.assertRaisesRegex(x.PortError, 'unsafe'):
            self.run_port()
        del self.members['../escape']
        self.write_base()
        with zipfile.ZipFile(self.base, 'a') as z:
            z.writestr('classes.dex', b'duplicate')
        with self.assertRaisesRegex(x.PortError, 'duplicate ZIP'):
            self.run_port()

    def test_output_boundary_and_no_overwrite(self):
        with self.assertRaisesRegex(x.PortError, 'output'):
            self.run_port(output_root=self.root / 'elsewhere')
        self.output.parent.mkdir()
        self.output.write_bytes(b'keep')
        with self.assertRaisesRegex(x.PortError, 'output'):
            self.run_port()
        self.assertEqual(self.output.read_bytes(), b'keep')

    def test_signature_filter_is_narrow(self):
        self.assertTrue(x.signature('META-INF/WF.SF'))
        self.assertFalse(x.signature('META-INF/nested/WF.SF'))
        self.assertFalse(x.signature('assets/META-INF/WF.RSA'))
        self.assertFalse(x.signature('META-INF/NOTICE'))

    def test_output_cannot_modify_input_tree_or_cdn(self):
        self.output = self.inputs / 'candidate.apk'
        with self.assertRaisesRegex(x.PortError, 'input tree'):
            self.run_port()
        self.assertFalse(self.output.exists())
        self.output = self.root / '.cdn' / 'candidate.apk'
        with self.assertRaisesRegex(x.PortError, 'read-only CDN'):
            self.run_port()
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
