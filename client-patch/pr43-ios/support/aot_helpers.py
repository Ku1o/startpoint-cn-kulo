"""Selected unchanged AIR arm64 relocation helpers; see SOURCES.md."""
from __future__ import annotations
import struct, re, zlib
from dataclasses import dataclass
from pathlib import Path

IMAGE_BASE = 0x100000000

MAIN_METHOD_TABLE_OFFSET = 0x62C0780

MAIN_METHOD_COUNT = 101071

BUILTIN_AOT_INFO_VA = 0x1063B7D00

DISPLAY_OBJECT_AOT_INFO_VA = 0x1063AAC00

DISPLAY_OBJECT_CONTAINER_AOT_INFO_VA = 0x1063AB650

DEPENDENCY_AOT_INFOS = {
    "_builtin_aotInfo": BUILTIN_AOT_INFO_VA,
    "_051-starling_display_DisplayObject_51_aotInfo": DISPLAY_OBJECT_AOT_INFO_VA,
    "_066-starling_display_DisplayObjectContainer_66_aotInfo": DISPLAY_OBJECT_CONTAINER_AOT_INFO_VA,
}

STRICT_EQUALS_SYMBOL = "__ZN8halfmoon5Stubs19do_abc_strictequalsEPN7avmplus11MethodFrameExx"

STRICT_EQUALS_VA = 0x100A27338

def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & -alignment

def text(value) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else value

def sign_extend_24(value: int) -> int:
    return value - (1 << 24) if value & (1 << 23) else value

def patch_branch26(code: bytearray, offset: int, pc: int, target: int) -> None:
    instruction = struct.unpack_from("<I", code, offset)[0]
    delta = target - pc
    if delta & 3 or not -(1 << 27) <= delta < (1 << 27):
        raise ValueError(f"BRANCH26 out of range: pc={pc:#x} target={target:#x}")
    instruction = (instruction & 0xFC000000) | ((delta >> 2) & 0x03FFFFFF)
    struct.pack_into("<I", code, offset, instruction)

def write_unconditional_branch(
    data: bytearray, offset: int, pc: int, target: int
) -> None:
    """Write an AArch64 B instruction without inheriting the old opcode."""
    delta = target - pc
    if delta & 3 or not -(1 << 27) <= delta < (1 << 27):
        raise ValueError(f"B out of range: pc={pc:#x} target={target:#x}")
    instruction = 0x14000000 | ((delta >> 2) & 0x03FFFFFF)
    struct.pack_into("<I", data, offset, instruction)

def patch_adrp(code: bytearray, offset: int, pc: int, target: int) -> None:
    instruction = struct.unpack_from("<I", code, offset)[0]
    page_delta = ((target & ~0xFFF) - (pc & ~0xFFF)) >> 12
    if not -(1 << 20) <= page_delta < (1 << 20):
        raise ValueError(f"ADRP out of range: pc={pc:#x} target={target:#x}")
    encoded = page_delta & 0x1FFFFF
    instruction &= ~((0x3 << 29) | (0x7FFFF << 5))
    instruction |= (encoded & 0x3) << 29
    instruction |= ((encoded >> 2) & 0x7FFFF) << 5
    struct.pack_into("<I", code, offset, instruction)

def patch_pageoff12(
    code: bytearray,
    offset: int,
    target: int,
    *,
    relax_got_load: bool,
) -> None:
    instruction = struct.unpack_from("<I", code, offset)[0]
    page_offset = target & 0xFFF
    if relax_got_load:
        rd = instruction & 0x1F
        rn = (instruction >> 5) & 0x1F
        instruction = 0x91000000 | (page_offset << 10) | (rn << 5) | rd
    elif (instruction & 0x7F000000) == 0x11000000:
        instruction &= ~(0xFFF << 10)
        instruction |= page_offset << 10
    elif (instruction & 0x3B000000) == 0x39000000:
        scale = 1 << ((instruction >> 30) & 0x3)
        if page_offset % scale:
            raise ValueError(
                f"unaligned load/store PAGEOFF12 target {target:#x} scale={scale}"
            )
        immediate = page_offset // scale
        if immediate >= 0x1000:
            raise ValueError(f"PAGEOFF12 immediate too large: {immediate:#x}")
        instruction &= ~(0xFFF << 10)
        instruction |= immediate << 10
    else:
        raise ValueError(
            f"unsupported PAGEOFF12 instruction {instruction:#010x} at {offset:#x}"
        )
    struct.pack_into("<I", code, offset, instruction)

def decompress_swf(data: bytes) -> tuple[bytes, bytes]:
    signature = data[:3]
    if signature == b"FWS":
        return signature, data
    if signature != b"CWS":
        raise ValueError(f"unsupported SWF signature {signature!r}")
    return signature, b"FWS" + data[3:8] + zlib.decompress(data[8:])

def replace_main_swf_hash(data: bytes, old_hash: bytes, new_hash: bytes) -> bytes:
    signature, plain = decompress_swf(data)
    needle = b"\x00\x00\x00\x00" + old_hash
    replacement = b"\x00\x00\x00\x00" + new_hash
    count = plain.count(needle)
    if count != 1:
        raise ValueError(f"expected one main SWF AOT hash stub, found {count}")
    patched = plain.replace(needle, replacement)
    if len(patched) != len(plain):
        raise AssertionError("SWF size changed")
    if signature == b"FWS":
        return patched
    return b"CWS" + patched[3:8] + zlib.compress(patched[8:], level=9)

@dataclass
class FunctionRecord:
    method_id: int
    symbol: str
    source_start: int
    source_end: int
    destination_offset: int = 0

    @property
    def size(self) -> int:
        return self.source_end - self.source_start

    @property
    def destination_va(self) -> int:
        return IMAGE_BASE + self.destination_offset

def find_section(binary, symbol):
    return next(
        section
        for section in binary.sections
        if section.virtual_address <= symbol.value < section.virtual_address + section.size
    )

def extract_symbol_bytes(binary, symbol_name: str, size: int) -> bytes:
    symbol = next(symbol for symbol in binary.symbols if text(symbol.name) == symbol_name)
    section = find_section(binary, symbol)
    start = symbol.value - section.virtual_address
    return bytes(section.content)[start : start + size]

def parse_relocations(object_path: Path, section, symbols, record: FunctionRecord):
    raw = object_path.read_bytes()
    rows = []
    for index in range(section.numberof_relocations):
        address, word = struct.unpack_from("<iI", raw, section.relocation_offset + index * 8)
        if not record.source_start <= address < record.source_end:
            continue
        external = (word >> 27) & 1
        symbol_index = word & 0xFFFFFF
        rows.append(
            {
                "source_address": address,
                "offset": address - record.source_start,
                "type": (word >> 28) & 0xF,
                "external": external,
                "symbol": text(symbols[symbol_index].name)
                if external and symbol_index < len(symbols)
                else None,
                "raw": word,
            }
        )
    return rows
