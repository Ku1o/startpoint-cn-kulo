"""Focused checks for the delta compiler/linker's preservation boundaries."""
import struct
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import native_support as support
from compile_port import compile_input


class DeltaSelectionTests(unittest.TestCase):
    def test_existing_replacement_redirect_and_all_appended_methods(self):
        port = dict(old_methods=10, total_methods=14, methods=[
            dict(method_id=2, strategy='replace'),
            dict(method_id=3, compiled=11, strategy='redirect')],
            method_redirects=[dict(original=3, compiled=11)], compiled_helpers=[8])
        self.assertEqual(support.wanted_methods(port), {2, 8, 10, 11, 12, 13})

    def test_target_verifier_warning_is_fatal_and_baseline_warning_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'compiler.log'
            path.write_text('Verify error: cumulative:5: bad\n', 'utf8')
            self.assertEqual(len(support.verify_warnings(path, {6})), 1)
            with self.assertRaises(AssertionError):
                support.verify_warnings(path, {5})
            path.write_text('Verify error: cannot identify method\n', 'utf8')
            with self.assertRaises(AssertionError):
                support.verify_warnings(path, {5})

    def test_new_activation_pointer_relocation_needs_full_width_and_handler_offset(self):
        symbols = [SimpleNamespace(name='_generated_init')]
        section = SimpleNamespace(numberof_relocations=1, relocation_offset=0)
        obj = SimpleNamespace(symbols=symbols)
        backend = SimpleNamespace(aot=SimpleNamespace(text=str))
        with tempfile.TemporaryDirectory() as directory, patch.object(support, 'backend', return_value=backend):
            path = Path(directory) / 'object.o'
            path.write_bytes(struct.pack('<iI', 24, (3 << 25) | (1 << 27)))
            self.assertEqual(support.activation_relocations(path, obj, section, 16, 16),
                             [dict(offset=8, symbol='_generated_init')])
            path.write_bytes(struct.pack('<iI', 16, (3 << 25) | (1 << 27)))
            with self.assertRaises(AssertionError):
                support.activation_relocations(path, obj, section, 16, 16)

    def test_shared_entry_hook_requires_reviewed_alias_and_one_replacement(self):
        native = struct.pack('<QQQ', 0x100, 0x100, 0x200)
        backend = SimpleNamespace(file_offset=lambda data, address, size: 0)
        port = dict(old_methods=3)
        with patch.object(support, 'backend', return_value=backend), \
                patch.object(support, 'read64', return_value=0):
            with self.assertRaisesRegex(AssertionError, 'unreviewed native entry aliases'):
                support.verify_entry_aliases(native, port, {0})
            port['permitted_native_entry_aliases'] = {'0': [1]}
            self.assertEqual(support.verify_entry_aliases(native, port, {0})['0']['aliases'], [1])
            with self.assertRaisesRegex(AssertionError, 'multiple replacements'):
                support.verify_entry_aliases(native, port, {0, 1})


class CompilerInputTests(unittest.TestCase):
    def test_real_accepted_abc_only_non_target_code_is_stubbed(self):
        link = support.backend()
        value = os.environ.get('STARPOINT_PR43_IOS_FULL_ABC')
        if not value:
            self.skipTest('set STARPOINT_PR43_IOS_FULL_ABC to the fixed private 10-04 full ABC')
        source_path = Path(value)
        source = source_path.read_bytes()
        from fixed_inputs import fixed_json
        self.assertEqual(support.sha(source), fixed_json('baseline-contract.json')['full_abc_sha256'])
        before = link.abcfmt.ABC(source)
        target = next(b[0] for b in before.bodies if len(b[5]) > 16)
        result, replaced, contexts = compile_input(source, {target})
        after = link.abcfmt.ABC(result)
        a = {b[0]: b for b in after.bodies}
        self.assertEqual(link.freeze(a[target]), link.freeze(next(b for b in before.bodies if b[0] == target)))
        for body in before.bodies:
            self.assertEqual(link.freeze(body[7]), link.freeze(a[body[0]][7]))
        for field in ('methods', 'classes', 'instances', 'scripts', 'strings'):
            self.assertEqual(link.freeze(getattr(before, field)), link.freeze(getattr(after, field)))
        self.assertNotIn(target, replaced)
        self.assertEqual(len(replaced) + len(contexts), len(before.bodies) - 1)


if __name__ == '__main__':
    unittest.main()
