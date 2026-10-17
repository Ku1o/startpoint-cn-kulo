"""Portable-input boundaries, without compiling or modifying a client carrier."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import native_support
native_support.backend()
from fixed_inputs import check_dependencies, fixed_json, HASHES
import prepare_port

class RecipeContractTests(unittest.TestCase):
    def test_all_committed_metadata_matches_pinned_identity(self):
        for name in HASHES:
            self.assertIsInstance(fixed_json(name),dict)
        self.assertEqual(len(fixed_json('dependency-hashes.json')),284)
        self.assertEqual(fixed_json('baseline-contract.json')['full_abc_sha256'],prepare_port.IOS_SHA)

    def test_dependency_names_and_bytes_are_both_required(self):
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td)
            with self.assertRaisesRegex(ValueError,'284'):
                check_dependencies(directory)
            with patch('fixed_inputs.fixed_json',return_value={'000-example.abc':hashlib.sha256(b'correct').hexdigest()}):
                (directory/'000-example.abc').write_bytes(b'incorrect')
                with self.assertRaisesRegex(ValueError,'identity mismatch'):
                    check_dependencies(directory)
                (directory/'000-example.abc').write_bytes(b'correct')
                self.assertEqual(check_dependencies(directory),[directory/'000-example.abc'])

    def test_wrong_historical_ipa_refused_before_output_is_created(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);bad=root/'wrong.ipa';bad.write_bytes(b'wrong')
            with self.assertRaisesRegex(AssertionError,'IPA identity'):
                prepare_port.run(root/'output',input_ipa=bad,input_full_abc=root/'absent.abc',android_file=root/'absent.swf')
            self.assertFalse((root/'output').exists())

    def test_command_help_has_no_private_worktree_dependency(self):
        here=Path(__file__).resolve().parent
        for name in ('prepare_port.py','compile_port.py','link_port.py','package_port.py','rotate_admission.py'):
            result=subprocess.run([sys.executable,'-B',str(here/name),'--help'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,(name,result.stderr))
            self.assertIn('usage:',result.stdout)

if __name__=='__main__':unittest.main()
