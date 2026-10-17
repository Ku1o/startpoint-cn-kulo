"""HUD bytecode relocation tests plus actual Android-to-iOS import checks."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import hud_adapter as adapter


def model():
    path = Path(__file__).resolve().parents[1] / 'lens0907-0908/build_swf.py'
    spec = importlib.util.spec_from_file_location('hud_adapter_shared_model', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def fixture_abc():
    names = {1: adapter.OWNER, 2: 'Number', 3: 'int',
             10: adapter.COUNTERS[0], 11: adapter.COUNTERS[1], 12: adapter.COUNTERS[2]}
    traits = [SimpleNamespace(name=10 + i, kind=0,
                              data=['slot', 0, 2, 1, 6]) for i in range(3)]
    return SimpleNamespace(instances=[[1, 0, 0, None, [], 0, traits]],
                           doubles=[0.0, 0.0], mn_name=lambda n: names[n])


class HudRelocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = model()

    def synthetic(self):
        a = self.p.asm
        # Both switch and ordinary branch destinations straddle the insertion.
        instructions = [a.Instruction(0xd0), a.Instruction(0x30),
                        a.Instruction(0x24, [0]),
                        a.Instruction(0x1b, cases=[4, 9], default=9),
                        a.Instruction(0xd0), a.Instruction(0x66, [10]),
                        a.Instruction(0x29), a.Instruction(0x10, target=13),
                        a.Instruction(0x02), a.Instruction(0xd0),
                        a.Instruction(0x66, [11]), a.Instruction(0x73),
                        a.Instruction(0x29), a.Instruction(0x47),
                        a.Instruction(0x29), a.Instruction(0x47)]
        code, offsets = a.encode(instructions)
        body = [0, 2, 1, 1, 2, code, [(offsets[4], offsets[7], offsets[14], 0, 0)], []]
        return fixture_abc(), body, offsets

    def test_switch_branches_and_exception_offsets(self):
        abc, body, old_offsets = self.synthetic()
        before = copy.deepcopy(body)
        result, report = adapter.adapt_hud_body(abc, body, self.p.asm, expected_reads=2)
        self.assertEqual(body, before)
        self.assertEqual((report['reads'], report['inserted'], report['already_converted']), (2, 1, 1))
        rows = self.p.asm.decode(result[5]); pos = report['old_to_new_instruction']
        self.assertEqual(rows[pos[3]].cases, [pos[4], pos[9]])
        self.assertEqual(rows[pos[3]].default, pos[9])
        self.assertEqual(rows[pos[7]].target, pos[13])
        offsets = report['old_to_new_byte_offset']
        self.assertEqual(result[6], [(offsets[old_offsets[4]], offsets[old_offsets[7]],
                                      offsets[old_offsets[14]], 0, 0)])
        self.assertEqual(result[:5], body[:5]); self.assertEqual(result[7], body[7])
        again, second = adapter.adapt_hud_body(abc, result, self.p.asm, expected_reads=2)
        self.assertEqual(again, result); self.assertEqual(second['inserted'], 0)

    def test_wrong_read_count_refused_without_mutation(self):
        abc, body, _ = self.synthetic(); before = copy.deepcopy(body)
        with self.assertRaisesRegex(ValueError, 'read count'):
            adapter.adapt_hud_body(abc, body, self.p.asm)
        self.assertEqual(body, before)

    def test_int_trait_refused(self):
        abc, body, _ = self.synthetic(); abc.instances[0][6][0].data[2] = 3
        with self.assertRaisesRegex(ValueError, 'Number tail slot'):
            adapter.adapt_hud_body(abc, body, self.p.asm, expected_reads=2)

    def test_nonzero_default_refused(self):
        abc, body, _ = self.synthetic(); abc.doubles[1] = 1.0
        with self.assertRaisesRegex(ValueError, 'zero Number default'):
            adapter.adapt_hud_body(abc, body, self.p.asm, expected_reads=2)

    def test_noninstruction_exception_boundary_refused(self):
        abc, body, offsets = self.synthetic()
        body[6] = [(offsets[5] + 1, offsets[7], offsets[14], 0, 0)]
        with self.assertRaisesRegex(ValueError, 'exception boundary'):
            adapter.adapt_hud_body(abc, body, self.p.asm, expected_reads=2)


def check_actual(ios_abc, android_swf):
    p = model()
    target = p.View(SimpleNamespace(abc=p.abcfmt.ABC(ios_abc.read_bytes())), p.asm)
    source = p.View(p.SwfAbc(android_swf), p.asm)
    label = adapter.OWNER + '/update|1'
    si, = source.by_label[label]; ti, = target.by_label[label]
    original = copy.deepcopy(target.a)
    importer = p.Importer(target, source)
    imported = importer.body(si, target.a.bodies[ti][0], scope=target.a.bodies[ti][3])
    imported_before = copy.deepcopy(imported)
    structure_before = dict((name, p.freeze(getattr(target.a, name)))
                            for name in ('methods', 'instances', 'classes', 'scripts', 'metadata'))
    adapted, report = adapter.adapt_hud_body(target.a, imported, p.asm)
    assert p.freeze(imported) == p.freeze(imported_before)
    assert report['reads'] == 16 and report['inserted'] == 15 and report['already_converted'] == 1
    assert all(p.freeze(getattr(target.a, name)) == value for name, value in structure_before.items())
    before_rows = p.asm.decode(imported[5]); after_rows = p.asm.decode(adapted[5])
    positions = report['old_to_new_instruction']
    for i, ins in enumerate(before_rows):
        got = after_rows[positions[i]]
        assert ins.op == got.op and ins.args == got.args
        assert got.target == (positions[ins.target] if ins.target is not None else None)
        assert got.default == (positions[ins.default] if ins.default is not None else None)
        assert got.cases == ([positions[x] for x in ins.cases] if ins.cases is not None else None)
        if ins.op == 0x66 and target.a.mn_name(ins.args[0]) in adapter.COUNTERS:
            assert after_rows[positions[i] + 1].op == 0x73
    # Remove just the inserted operations and restore instruction-index targets.
    collapsed = [copy.deepcopy(after_rows[positions[i]]) for i in range(len(before_rows))]
    inverse = dict((v, k) for k, v in positions.items())
    for ins in collapsed:
        if ins.target is not None: ins.target = inverse[ins.target]
        if ins.default is not None: ins.default = inverse[ins.default]
        if ins.cases is not None: ins.cases = [inverse[x] for x in ins.cases]
    assert p.asm.encode(collapsed)[0] == imported[5]
    checked = p.check_body(adapted, target.a)
    repeat, repeated = adapter.adapt_hud_body(target.a, adapted, p.asm)
    assert p.freeze(repeat) == p.freeze(adapted) and repeated['inserted'] == 0
    target.a.bodies[ti] = adapted
    assert all(p.freeze(a) == p.freeze(b) for i, (a, b) in enumerate(zip(original.bodies, target.a.bodies)) if i != ti)
    return dict(passed=True, actual_android_method=source.a.bodies[si][0], ios_method=adapted[0],
                body=report, verifier=checked, original_instruction_stream_recovered=True,
                old_traits_slots_signatures_preserved=True, all_other_bodies_preserved=True,
                idempotent=True, aot_compiled=False, native_executed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ios-abc', type=Path)
    parser.add_argument('--android-swf', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HudRelocationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)
    if args.ios_abc or args.android_swf:
        assert args.ios_abc and args.android_swf, 'Both actual inputs are required'
        report = check_actual(args.ios_abc, args.android_swf)
        report['focused_tests'] = result.testsRun
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Actual HUD imported: 16 reads, 15 convert_i insertions, traits and all other bodies preserved')
