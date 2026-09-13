"""AAPCS64 long-branch veneer using only the linker scratch register IP0."""
import struct


def reachable(pc, target):
    delta = target - pc
    return delta % 4 == 0 and -(1 << 27) <= delta < (1 << 27)


def encode(address, target):
    assert address % 4 == target % 4 == 0
    pages = (target >> 12) - (address >> 12)
    assert -(1 << 20) <= pages < (1 << 20), 'ADRP out of range'
    immediate = pages & ((1 << 21) - 1)
    adrp = 0x90000010 | ((immediate & 3) << 29) | ((immediate >> 2) << 5)
    add = 0x91000210 | ((target & 0xfff) << 10)
    # BR preserves LR for both BL callers and B tail callers. No stack,
    # argument/result registers, condition flags or absolute pointers change.
    return struct.pack('<IIII', adrp, add, 0xd61f0200, 0xd503201f)
