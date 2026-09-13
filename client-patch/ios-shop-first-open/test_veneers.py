"""Regress the actual out-of-range call and decode veneers independently."""
import unittest
import prepare
import build_native  # Configures the existing local native-analysis dependencies.
import capstone
import veneers


class LongBranchTests(unittest.TestCase):
    def decode_target(self, address, target, slide=0):
        decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
        decoder.detail = True
        code = veneers.encode(address, target)
        instructions = list(decoder.disasm(code, address + slide))
        self.assertEqual([i.mnemonic for i in instructions], ['adrp', 'add', 'br', 'nop'])
        self.assertEqual(instructions[0].reg_name(instructions[0].operands[0].reg), 'x16')
        self.assertEqual([instructions[1].reg_name(o.reg) for o in instructions[1].operands[:2]], ['x16', 'x16'])
        self.assertEqual(instructions[2].op_str, 'x16')
        self.assertEqual(instructions[0].operands[1].imm + instructions[1].operands[2].imm, target + slide)

    def test_reported_long_call(self):
        pc, target = 0x108bf972c, 0x100a2676c
        self.assertFalse(veneers.reachable(pc, target))
        island = pc + 0x1000
        self.assertTrue(veneers.reachable(pc, island))
        self.decode_target(island, target)

    def test_branch26_boundaries(self):
        pc = 0x108000000
        for delta in (-(1 << 27), -4, 0, 4, (1 << 27) - 4):
            self.assertTrue(veneers.reachable(pc, pc + delta))
        for delta in (-(1 << 27) - 4, (1 << 27), 2):
            self.assertFalse(veneers.reachable(pc, pc + delta))

    def test_page_boundaries_and_aslr(self):
        for address in (0x100000ffc, 0x108bf972c, 0x110000000):
            for delta in (-0x1234560, -0x1000, -4, 0, 4, 0x1000, 0x1234560):
                for slide in (0, 0x4000, 0x12340000):
                    self.decode_target(address, address + delta, slide)

    def test_unsupported_target_is_rejected(self):
        with self.assertRaises(AssertionError):
            veneers.encode(0x100000000, 0x200000000)
        with self.assertRaises(AssertionError):
            veneers.encode(0x100000000, 0x100000002)


if __name__ == '__main__':
    unittest.main(verbosity=2)
