"""Read the existing ARM64 constructor origin without importing a build recipe.

The caller supplies its existing ABC parser and Mach-O address mapper. Nothing
here loads a source module, opens a historical work directory or patches bytes.
Endpoint policy stays with the caller; both strings come from the actual image.
"""
import struct

SCHEME_SITE = 0x33d08a0
HOST_SITE = 0x33d08b0


def constructor_origin(native, *, abc_parser, address_to_offset, info_offset):
    pointer, size = struct.unpack_from('<QQ', native, info_offset + 24)
    offset = address_to_offset(native, pointer, size)
    abc = abc_parser(native[offset:offset + size])
    values = []
    for site in (SCHEME_SITE, HOST_SITE):
        word = struct.unpack_from('<I', native, site)[0]
        assert word & 0xffe0001f == 0x52800001, 'expected MOVZ W1, imm16'
        values.append(abc.s((word >> 5) & 0xffff))
    return values[0] + '://' + values[1]
