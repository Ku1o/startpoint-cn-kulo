"""Regression for the 2026-09-11 pre-main dyld crash; never signs/installs IPA."""
from pathlib import Path
import hashlib,json,struct,unittest,zipfile
from prepare import WORK
from build_native import commands,segments,read_rebase
from macho_signing_layout import assert_signable_layout,signature_range,linkedit_ranges,ldid_code_limit,string_table

BROKEN_IPA=Path(r'F:\codex\ios-artifacts\StarPoint-iOS-1.8.4-login-abyss-lens-20260911-unsigned.ipa')
FIRST_FIX_IPA=Path(r'F:\codex\ios-artifacts\StarPoint-iOS-1.8.4-login-abyss-lens-launch-fix-20260911-unsigned.ipa')


def replace_signature_tail(native,size,use_ldid=False):
    """Model signature replacement, including ldid's symbol-table code limit.

    ldid Allocate() at aaf8f23d7975ecdb8e77e3a8f22253e0a2352cef selects the
    aligned string-table end before allocating/writing a signature. This model
    contains a signature magic header but performs no cryptographic signing.
    """
    command,offset,_=signature_range(native)
    if use_ldid:offset=ldid_code_limit(native)
    blob=struct.pack('>III',0xfade0cc0,size,0)+b'\xa5'*(size-12)
    result=bytearray(native[:offset]+blob)
    struct.pack_into('<II',result,command+8,offset,size)
    link=segments(result)[-1];fs=len(result)-link['off']
    struct.pack_into('<Q',result,link['command']+48,fs)
    struct.pack_into('<Q',result,link['command']+32,(fs+0x3fff)&~0x3fff)
    return result


class SigningLayoutRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(BROKEN_IPA.read_bytes()).hexdigest()=='54a305686a8cf0ae9ad6f1ea3158d34009a7eb0a7221e807de334570d56ebe2a'
        with zipfile.ZipFile(BROKEN_IPA) as z:cls.broken=z.read('Payload/worldflipper.app/worldflipper')
        assert hashlib.sha256(FIRST_FIX_IPA.read_bytes()).hexdigest()=='77757cb88ed43593d1df3ab48b7d4fc0601476362163a013c20159f3e3832499'
        with zipfile.ZipFile(FIRST_FIX_IPA) as z:cls.first_fix=z.read('Payload/worldflipper.app/worldflipper')
        report=json.loads((WORK/'output/build-report.json').read_text('utf8'))
        with zipfile.ZipFile(report['ipa']) as z:cls.fixed=z.read('Payload/worldflipper.app/worldflipper')
        assert hashlib.sha256(cls.fixed).hexdigest()==report['native_sha256']

    def test_previous_candidate_is_rejected(self):
        with self.assertRaisesRegex(AssertionError,'data after replaceable code signature'):
            assert_signable_layout(self.broken)

    def test_crash_address_matches_first_rebase_byte(self):
        rebase=read_rebase(self.broken);link=segments(self.broken)[-1]
        # Actual image base / fault address from the supplied .ips; no user IDs.
        address=0x104ca4000+(link['vm']-0x100000000)+(rebase['offset']-link['off'])
        self.assertEqual(address,0x10cb400d0)
        self.assertEqual(rebase['offset'],0x7e2c0d0)

    def test_signature_replacement_discards_old_rebase(self):
        replaced=replace_signature_tail(self.broken,0x100000)
        rebase=next(r for r in linkedit_ranges(replaced) if r['name']=='rebase')
        self.assertGreater(rebase['offset'],len(replaced))
        with self.assertRaises(AssertionError):assert_signable_layout(replaced)

    def test_fixed_metadata_survives_signature_replacement(self):
        expected=read_rebase(self.fixed)['entries']
        for size in (0x80000,0x200000,0x400000):
            with self.subTest(signature_size=size):
                replaced=replace_signature_tail(self.fixed,size)
                assert_signable_layout(replaced)
                self.assertEqual(read_rebase(replaced)['entries'],expected)
                for r in linkedit_ranges(self.fixed):
                    a=r['offset'];b=a+r['size']
                    self.assertEqual(replaced[a:b],self.fixed[a:b],r['name'])

    def test_first_fix_is_rejected_for_ldid_truncation(self):
        with self.assertRaisesRegex(AssertionError,'ldid truncates after symbol strings'):
            assert_signable_layout(self.first_fix)

    def test_ldid_reproduces_reported_unknown_opcode_f0(self):
        replaced=replace_signature_tail(self.first_fix,0x200000,use_ldid=True)
        rebase=next(r for r in linkedit_ranges(replaced) if r['name']=='rebase')
        self.assertEqual(rebase['offset'],ldid_code_limit(self.first_fix))
        self.assertEqual(replaced[rebase['offset']]&0xf0,0xf0)
        with self.assertRaisesRegex(ValueError,'rebase opcode.*15'):read_rebase(replaced)

    def test_fixed_metadata_survives_ldid_allocation(self):
        expected=read_rebase(self.fixed)['entries']
        for size in (0x80000,0x200000,0x400000):
            with self.subTest(signature_size=size):
                replaced=replace_signature_tail(self.fixed,size,use_ldid=True)
                assert_signable_layout(replaced)
                self.assertEqual(read_rebase(replaced)['entries'],expected)
                for r in linkedit_ranges(self.fixed):
                    a=r['offset'];b=a+r['size']
                    self.assertEqual(replaced[a:b],self.fixed[a:b],r['name'])

    def test_repair_changes_layout_without_gameplay_changes(self):
        old_segments=segments(self.broken);new_segments=segments(self.fixed)
        link=old_segments[-1];prefix=bytearray(self.fixed[:link['off']])
        allowed=[(link['command']+32,link['command']+40),(link['command']+48,link['command']+56)]
        dyld,_,_=next(x for x in commands(self.fixed) if x[1] in (0x22,0x80000022))
        sign,_,_=signature_range(self.fixed)
        symtab,_,_=string_table(self.fixed)
        allowed.extend([(dyld+8,dyld+16),(sign+8,sign+16),(symtab+16,symtab+20)])
        for a,b in allowed:prefix[a:b]=self.broken[a:b]
        self.assertEqual(prefix,self.broken[:link['off']])
        self.assertEqual([(s['name'],s['vm'],s['off']) for s in old_segments],[(s['name'],s['vm'],s['off']) for s in new_segments])
        old_rb=read_rebase(self.broken);new_rb=read_rebase(self.fixed)
        self.assertEqual(old_rb['entries'],new_rb['entries'])
        self.assertEqual(self.broken[old_rb['offset']:old_rb['offset']+old_rb['size']],self.fixed[new_rb['offset']:new_rb['offset']+new_rb['size']])


if __name__=='__main__':unittest.main(verbosity=2)
