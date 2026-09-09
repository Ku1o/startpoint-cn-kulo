"""Exercise cumulative Lens metadata selection against the actual retained IPA."""
import json
import unittest
import zipfile

import build_native as build
from prepare import HERE, IPA_HASH, LENS_WORK, sha, source_record


class CurrentRuntimePointer(unittest.TestCase):
    def test_reads_the_lens_abc_instead_of_the_historical_offset(self):
        reg = source_record(reproduce=True)
        self.assertEqual(reg['ipa_sha256'], IPA_HASH)
        with zipfile.ZipFile(reg['ipa']) as archive:
            native = archive.read(reg['native_member'])
        self.assertEqual(sha(native), reg['native_sha256'])
        offset = build.runtime_abc_offset(native)
        size = build.aot.read_u64(native, build.aot.MAIN_AOT_INFO_OFFSET+32)
        expected = json.loads((LENS_WORK/'output/build-report.json').read_text('utf-8'))['runtime_abc_sha256']
        self.assertEqual(sha(native[offset:offset+size]), expected)
        # The original pre-Lens offset still contains a parseable older ABC.
        # Accidentally choosing it must not silently lose the current Lens data.
        old_offset = build.aot.MAIN_ABC_OFFSET
        self.assertNotEqual(offset, old_offset)
        self.assertNotEqual(sha(native[old_offset:old_offset+size]), expected)

    def test_current_accepted_ipa_is_not_patched_a_second_time(self):
        with self.assertRaisesRegex(ValueError, 'baseline advanced'):
            source_record()


if __name__ == '__main__': unittest.main()
