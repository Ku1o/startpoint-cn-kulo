"""Structured DEX/AXML identity and sparse bundle packaging regression tests."""
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

import package_android as p

OLD = '4728fb03-7242-4fcc-9bc4-e8b4fc073a43'
NEW = '5728fb03-7242-4fcc-9bc4-e8b4fc073a43'


def dex(strings=None, extra=b'UNCHANGED-CODE'):
    strings = strings or ['/system/bin/linker', OLD, '<clinit>']
    count = len(strings)
    data_off = 112 + count * 4
    offsets, data = [], bytearray()
    for s in strings:
        b = s.encode()
        offsets.append(data_off + len(data))
        data.extend(bytes([len(s)]) + b + b'\0')
    data.extend(extra)
    while (data_off + len(data)) % 4:
        data.append(0)
    map_off = data_off + len(data)
    data.extend(struct.pack('<I', 4))
    for kind, num, off in [(0, 1, 0), (1, count, 112), (0x2002, count, data_off), (0x1000, 1, map_off)]:
        data.extend(struct.pack('<HHII', kind, 0, num, off))
    header = bytearray(112)
    header[:8] = b'dex\n035\0'
    struct.pack_into('<III', header, 32, data_off + len(data), 112, 0x12345678)
    struct.pack_into('<I', header, 52, map_off)
    struct.pack_into('<II', header, 56, count, 112)
    struct.pack_into('<II', header, 104, len(data), data_off)
    return p.dex_fix_checksums(bytes(header) + struct.pack('<' + 'I' * count, *offsets) + bytes(data))


def manifest():
    strings = ['manifest', 'package', 'versionCode', 'versionName',
               'http://schemas.android.com/apk/res/android', 'com.leiting.wf', '1.8.1', OLD]
    data, offsets = bytearray(), []
    for s in strings:
        offsets.append(len(data))
        data.extend(struct.pack('<H', len(s)) + s.encode('utf-16le') + b'\0\0')
    while len(data) % 4:
        data.append(0)
    size = 28 + 4 * len(strings) + len(data)
    pool = struct.pack('<HHI5I', 1, 28, size, len(strings), 0, 0, 28 + 4 * len(strings), 0)
    pool += struct.pack('<' + 'I' * len(strings), *offsets) + data
    ids = [0] * len(strings); ids[2] = 0x0101021B
    resource = struct.pack('<HHI', 0x180, 8, 8 + 4 * len(ids)) + struct.pack('<' + 'I' * len(ids), *ids)
    attrs = b''
    for ns, name, raw, typ, val in [(0xffffffff, 1, 5, 3, 5), (4, 2, 0xffffffff, 0x10, 1008001), (4, 3, 6, 3, 6)]:
        attrs += struct.pack('<IIIHBBI', ns, name, raw, 8, 0, typ, val)
    root = struct.pack('<HHIII', 0x102, 16, 36 + len(attrs), 1, 0xffffffff)
    root += struct.pack('<IIHHHHHH', 0xffffffff, 0, 20, 20, 3, 0, 0, 0) + attrs
    body = pool + resource + root
    return struct.pack('<HHI', 3, 8, len(body) + 8) + body


def zipped(members):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for n, b in members.items():
            z.writestr(n, b)
    return out.getvalue()


class IdentityTests(unittest.TestCase):
    def test_dex_narrow_replace_preserves_code_and_all_offsets(self):
        before = dex()
        after, report = p.patch_dex(before, OLD, NEW)
        start = report['stringDataOffset']
        self.assertEqual(before[32:start], after[32:start])
        self.assertEqual(before[start+36:], after[start+36:])
        self.assertIn(b'UNCHANGED-CODE', after)
        self.assertEqual(p.dex_strings(after)[1]['text'], NEW)

    def test_dex_bad_checksum(self):
        b = bytearray(dex()); b[8] ^= 1
        with self.assertRaisesRegex(p.PortError, 'Adler32'):
            p.patch_dex(bytes(b), OLD, NEW)
        b = bytearray(dex()); b[12] ^= 1
        with self.assertRaisesRegex(p.PortError, 'SHA1'):
            p.patch_dex(bytes(b), OLD, NEW)

    def test_dex_nonstring_extra_uuid_hit(self):
        with self.assertRaisesRegex(p.PortError, 'extra/nonstring'):
            p.patch_dex(dex(extra=OLD.encode()), OLD, NEW)

    def test_dex_missing_and_duplicate_string_uuid(self):
        with self.assertRaisesRegex(p.PortError, 'count mismatch'):
            p.patch_dex(dex(strings=['/system', '<clinit>']), OLD, NEW)
        with self.assertRaisesRegex(p.PortError, 'order/duplicates'):
            p.patch_dex(dex(strings=['/system', OLD, OLD, '<clinit>']), OLD, NEW)

    def test_uuid_and_string_order_guards(self):
        with self.assertRaisesRegex(p.PortError, 'differ'):
            p.patch_dex(dex(), OLD, OLD)
        with self.assertRaises(p.PortError):
            p.patch_dex(dex(), OLD, 'short')
        with self.assertRaisesRegex(p.PortError, 'order/duplicates'):
            p.patch_dex(dex(), OLD, 'a728fb03-7242-4fcc-9bc4-e8b4fc073a43')

    def test_bad_dex_map_and_header(self):
        b = bytearray(dex()); struct.pack_into('<I', b, 36, 113)
        with self.assertRaisesRegex(p.PortError, 'header_size'):
            p.patch_dex(p.dex_fix_checksums(b), OLD, NEW)
        b = bytearray(dex()); off = struct.unpack_from('<I', b, 52)[0]; struct.pack_into('<I', b, off, 99999)
        with self.assertRaisesRegex(p.PortError, 'truncated map'):
            p.patch_dex(p.dex_fix_checksums(b), OLD, NEW)

    def test_manifest_structural_identity_and_roundtrip(self):
        before = manifest()
        after, identity = p.patch_manifest(before, OLD, NEW)
        self.assertEqual(identity['package_name'], 'com.leiting.wf')
        self.assertEqual(identity['versionCode'], 1008001)
        self.assertEqual(after.replace(NEW.encode('utf-16le'), OLD.encode('utf-16le')), before)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base, self.swf, self.targets = [self.root / n for n in ('base.apk', 'final.swf', 'targets.json')]
        resources, members = [], {'untouched': b'keep bundle bytecode'}
        for i in range(4):
            n = 'production/android_bundle/target' + str(i)
            old, new = f'before{i}'.encode(), f'after{i}'.encode()
            members[n] = old
            donor = self.root / f'donor{i}'; donor.write_bytes(new)
            resources.append({'member': n, 'donor_file': str(donor), 'before_sha256': p.sha(old), 'after_sha256': p.sha(new), 'before_size': len(old), 'after_size': len(new)})
        self.targets.write_text(json.dumps({'resources': resources}))
        bundle = zipped(members)
        self.members = {'AndroidManifest.xml': manifest(), 'classes.dex': dex(), p.SWF: b'FWS-old',
                        'assets/bundle.zip': bundle, 'assets/bundle.zip.sha1': hashlib.sha1(bundle).hexdigest().encode() + b'\n',
                        'assets/keep': b'preserve', 'lib/arm64-v8a/native.so': b'preserve native',
                        'META-INF/WF.SF': b'drop signature', 'assets/META-INF/KEEP.RSA': b'keep resource'}
        self.base.write_bytes(zipped(self.members)); self.swf.write_bytes(b'FWS-final')

    def package(self, name='out', new_uuid=NEW):
        return p.package(self.base, self.swf, self.targets, new_uuid, self.root / name,
                         base_sha256=p.sha(self.base.read_bytes()), swf_sha256=p.sha(self.swf.read_bytes()),
                         old_uuid=OLD, output_root=self.root)

    def test_final_payload_and_only_five_apk_members_change(self):
        report = self.package()
        self.assertEqual(len(report['changed_members']), 5)
        with zipfile.ZipFile(report['apk']) as z:
            self.assertEqual(z.read(p.SWF), self.swf.read_bytes())
            for n, b in self.members.items():
                if n not in report['changed_members'] and not p.signature(n):
                    self.assertEqual(z.read(n), b)
            bundle = z.read('assets/bundle.zip')
            self.assertEqual(hashlib.sha1(bundle).hexdigest(), z.read('assets/bundle.zip.sha1').decode().strip())
            with zipfile.ZipFile(io.BytesIO(bundle)) as inner:
                self.assertEqual(inner.read('untouched'), b'keep bundle bytecode')
                for r in json.loads(self.targets.read_text())['resources']:
                    self.assertEqual(p.sha(inner.read(r['member'])), r['after_sha256'])

    def test_uuid_reuse_for_different_swf_rejected(self):
        self.package()
        self.swf.write_bytes(b'FWS-different')
        with self.assertRaisesRegex(p.PortError, 'different SWF'):
            self.package('other')

    def test_missing_target_and_bad_donor_hash(self):
        records = json.loads(self.targets.read_text())
        r = records['resources'][0]; r['after_sha256'] = '0' * 64
        self.targets.write_text(json.dumps(records))
        with self.assertRaisesRegex(p.PortError, 'donor hash'):
            self.package()
        r['member'] = 'missing'
        self.targets.write_text(json.dumps(records))
        with self.assertRaisesRegex(p.PortError, 'target missing'):
            self.package()

    def test_bundle_hash_marker_mismatch(self):
        self.members['assets/bundle.zip.sha1'] = b'0' * 40
        self.base.write_bytes(zipped(self.members))
        with self.assertRaisesRegex(p.PortError, 'sha1 does not match'):
            self.package()

    def test_missing_donor_and_output_overwrite(self):
        self.package()
        with self.assertRaisesRegex(p.PortError, 'new child directory'):
            self.package()
        (self.root / 'donor0').unlink()
        with self.assertRaises(FileNotFoundError):
            self.package('other')

    def test_cdn_output_is_rejected_without_writing(self):
        root = self.root / '.cdn'
        with self.assertRaisesRegex(p.PortError, 'read-only CDN'):
            p.package(self.base, self.swf, self.targets, NEW, root / 'out',
                      base_sha256=p.sha(self.base.read_bytes()), swf_sha256=p.sha(self.swf.read_bytes()),
                      old_uuid=OLD, output_root=root)
        self.assertFalse(root.exists())

    def test_swf_only_preserves_existing_bundle_and_marker(self):
        report = p.package(self.base, self.swf, None, NEW, self.root / 'swf-only',
                           base_sha256=p.sha(self.base.read_bytes()), swf_sha256=p.sha(self.swf.read_bytes()),
                           old_uuid=OLD, output_root=self.root)
        self.assertEqual(set(report['changed_members']), {p.SWF, 'AndroidManifest.xml', 'classes.dex'})
        self.assertEqual(report['changed_bundle_members'], [])
        with zipfile.ZipFile(report['apk']) as z:
            self.assertEqual(z.read('assets/bundle.zip'), self.members['assets/bundle.zip'])
            self.assertEqual(z.read('assets/bundle.zip.sha1'), self.members['assets/bundle.zip.sha1'])


if __name__ == '__main__':
    unittest.main()
