"""Keep known iOS signing, bootstrap and HUD failures detectable."""
import unittest,zipfile
import prepare
from test_signing_layout import SigningLayoutRegression
from public_endpoint import require_public_endpoint,runtime_abc
from hud_state_layout import R3,R3_SHA,slot_offsets
from pathlib import Path

class PreviousRuntimeFailures(unittest.TestCase):
    def test_old_r2_bootstrap_is_not_public(self):
        ipa=Path('F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-login-abyss-lens-trollstore-fix-r2-20260911-unsigned.ipa')
        self.assertEqual(prepare.sha(ipa.read_bytes()),'171f0eb1d1671c9684c1ee9829af4b7f29a9ccc7481ec42144743c51cc2e6d7c')
        with zipfile.ZipFile(ipa) as z:native=z.read('Payload/worldflipper.app/worldflipper')
        with self.assertRaises(AssertionError):require_public_endpoint(native)

    def test_r3_shifted_hud_fields_differ_from_current(self):
        self.assertEqual(prepare.sha(R3.read_bytes()),R3_SHA)
        with zipfile.ZipFile(R3) as z:old=z.read('Payload/worldflipper.app/worldflipper')
        new=(prepare.WORK/'output/worldflipper').read_bytes()
        # The native verifier also proves the retained HUD code remains byte-identical.
        oldabc=runtime_abc(old)[2];newabc=runtime_abc(new)[2]
        self.assertNotEqual(slot_offsets(oldabc),slot_offsets(newabc))

if __name__=='__main__':
    suite=unittest.TestSuite()
    for name in ['test_previous_candidate_is_rejected','test_first_fix_is_rejected_for_ldid_truncation','test_ldid_reproduces_reported_unknown_opcode_f0']:
        suite.addTest(SigningLayoutRegression(name))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(PreviousRuntimeFailures))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
