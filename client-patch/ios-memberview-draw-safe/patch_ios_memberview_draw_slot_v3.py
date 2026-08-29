from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import plistlib
import struct
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path


MACHO_MEMBER = "Payload/worldflipper.app/worldflipper"
INFO_PLIST_MEMBER = "Payload/worldflipper.app/Info.plist"

EXPECTED_SOURCE_IPA_SHA256 = (
    "fcba08d30702bb941d412ca1d650d0573481873489c4f94a38682d46e279ec88"
)
EXPECTED_SOURCE_MACHO_SHA256 = (
    "08db334f41ac994b5076e0154357639e631849a4339249fd46ab288f14c41c1e"
)
EXPECTED_SOURCE_MACHO_SIZE = 108_757_200
EXPECTED_SOURCE_MACHO_UUID = "4c4c4408-5555-3144-a151-6203e95defe1"
TARGET_MACHO_UUID = "1f9bf173-8be0-5460-a793-bbd07508c26e"

EXPECTED_BUNDLE_ID = "com.kulo.wf"
EXPECTED_SHORT_VERSION = "1.8.4"
EXPECTED_SOURCE_BUILD = "1.8.4"
TARGET_BUILD = "1.8.43"

IMAGE_BASE = 0x100000000
ORIGINAL_DRAW_OFFSET = 0x2B990D4
ORIGINAL_DRAW_VA = IMAGE_BASE + ORIGINAL_DRAW_OFFSET
ORIGINAL_DRAW_FIRST_INSTRUCTION = bytes.fromhex("eb2bb96d")

CONSTRUCTOR_DRAW_DISPATCH_OFFSET = 0x2B9C070
CONSTRUCTOR_DRAW_CALL_OFFSET = 0x2B9C084
CONSTRUCTOR_DRAW_RETURN_OFFSET = 0x2B9C088
EXPECTED_CONSTRUCTOR_DRAW_DISPATCH = bytes.fromhex(
    "880a40f9e00314aa015d40f9280840f9082940f900013fd6"
)

SERIS_WRAPPER_OFFSET = 0x3D69180
SERIS_WRAPPER_VA = IMAGE_BASE + SERIS_WRAPPER_OFFSET
SERIS_WRAPPER_TAIL_OFFSET = 0x3D694C0
SERIS_WRAPPER_TAIL_VA = IMAGE_BASE + SERIS_WRAPPER_TAIL_OFFSET
SLOT_REPAIR_DISPATCH_OFFSET = 0x30199C0
SLOT_REPAIR_DISPATCH_VA = IMAGE_BASE + SLOT_REPAIR_DISPATCH_OFFSET
EXPECTED_WRAPPER_SHA256 = (
    "bd66305e468fc193790d1c0f47e8fc514bb0376786362d9b2a6e4d2a8a97f11a"
)

DRAW_METHOD_TABLE_OFFSET = 0x6341BA8

# Existing code-cave ownership in the exact source binary. The five-in-one
# PixelArtCharacterView trampoline must remain untouched. V3 uses only the
# unused tail of the fantasy-soul patch's already-sacrificed debug method.
FIVE_IN_ONE_CAVE_START = 0x3D694D0
FIVE_IN_ONE_USED_END = 0x3D6965C
EXPECTED_FIVE_IN_ONE_HEAD = bytes.fromhex(
    "ff030bd1e00700a9e20f01a9e41702a9"
)
FANTASY_SOUL_CAVE_START = 0x301980C
FANTASY_SOUL_USED_END = 0x30199C0
FANTASY_SOUL_CAVE_END = 0x3019C0C


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode_branch(source_va: int, target_va: int, *, link: bool = False) -> bytes:
    delta = target_va - source_va
    if delta % 4:
        raise ValueError("ARM64 branch target is not instruction-aligned")
    immediate = delta // 4
    if not -(1 << 25) <= immediate < (1 << 25):
        raise ValueError("ARM64 branch target is outside the 26-bit range")
    opcode = 0x94000000 if link else 0x14000000
    return struct.pack("<I", opcode | (immediate & 0x03FFFFFF))


def decode_branch_target(instruction: bytes, source_va: int) -> tuple[bool, int]:
    word = struct.unpack("<I", instruction)[0]
    opcode = word & 0xFC000000
    if opcode not in (0x14000000, 0x94000000):
        raise ValueError(f"not an ARM64 B/BL instruction: {word:#x}")
    immediate = word & 0x03FFFFFF
    if immediate & (1 << 25):
        immediate -= 1 << 26
    return opcode == 0x94000000, source_va + immediate * 4


def encode_adrp(register: int, source_va: int, target_va: int) -> bytes:
    if not 0 <= register <= 31:
        raise ValueError("ARM64 ADRP register is invalid")
    source_page = source_va & ~0xFFF
    target_page = target_va & ~0xFFF
    page_delta = (target_page - source_page) // 0x1000
    if not -(1 << 20) <= page_delta < (1 << 20):
        raise ValueError("ARM64 ADRP target is outside the 21-bit page range")
    encoded = page_delta & 0x1FFFFF
    immlo = encoded & 0x3
    immhi = encoded >> 2
    return struct.pack("<I", 0x90000000 | (immlo << 29) | (immhi << 5) | register)


def decode_adrp_target(instruction: bytes, source_va: int, register: int) -> int:
    word = struct.unpack("<I", instruction)[0]
    if word & 0x9F00001F != 0x90000000 | register:
        raise ValueError(f"not the expected ARM64 ADRP X{register}: {word:#x}")
    immediate = ((word >> 5) & 0x7FFFF) << 2 | ((word >> 29) & 0x3)
    if immediate & (1 << 20):
        immediate -= 1 << 21
    return (source_va & ~0xFFF) + immediate * 0x1000


def encode_add_immediate_x(destination: int, source: int, immediate: int) -> bytes:
    if not 0 <= destination <= 31 or not 0 <= source <= 31:
        raise ValueError("ARM64 ADD register is invalid")
    if not 0 <= immediate < 0x1000:
        raise ValueError("ARM64 ADD immediate is outside the 12-bit range")
    return struct.pack(
        "<I",
        0x91000000 | (immediate << 10) | (source << 5) | destination,
    )


LDR_X9_FROM_X1_PLUS_0X10 = struct.pack("<I", 0xF9400829)
ADD_X10_X10_WRAPPER_PAGE_OFFSET = encode_add_immediate_x(
    10, 10, SERIS_WRAPPER_VA & 0xFFF
)
STR_X10_TO_X9_PLUS_0X50 = struct.pack("<I", 0xF900292A)
BR_X10 = struct.pack("<I", 0xD61F0140)


@dataclass(frozen=True)
class BinaryPatch:
    name: str
    offset: int
    source: bytes
    target: bytes
    purpose: str


CONSTRUCTOR_DRAW_CALL_TARGET = encode_branch(
    IMAGE_BASE + CONSTRUCTOR_DRAW_CALL_OFFSET,
    SLOT_REPAIR_DISPATCH_VA,
    link=True,
)
SLOT_REPAIR_DISPATCH_SOURCE = bytes.fromhex(
    "e00316aae10308aa292940f920013fd6f70300aa"
)
SLOT_REPAIR_DISPATCH_TARGET = b"".join(
    (
        LDR_X9_FROM_X1_PLUS_0X10,
        encode_adrp(10, SLOT_REPAIR_DISPATCH_VA + 4, SERIS_WRAPPER_VA),
        ADD_X10_X10_WRAPPER_PAGE_OFFSET,
        STR_X10_TO_X9_PLUS_0X50,
        BR_X10,
    )
)


CODE_PATCHES = (
    BinaryPatch(
        name="MemberView.constructor.installStableDrawSlot",
        offset=CONSTRUCTOR_DRAW_CALL_OFFSET,
        source=bytes.fromhex("00013fd6"),
        target=CONSTRUCTOR_DRAW_CALL_TARGET,
        purpose=(
            "replace the resolver-dependent BLR X8 with a linked call to the "
            "MemberView.draw slot repair dispatcher"
        ),
    ),
    BinaryPatch(
        name="MemberView.draw.slotRepairDispatcher",
        offset=SLOT_REPAIR_DISPATCH_OFFSET,
        source=SLOT_REPAIR_DISPATCH_SOURCE,
        target=SLOT_REPAIR_DISPATCH_TARGET,
        purpose=(
            "store the retained wrapper in this method's MethodInfo+0x50 and "
            "tail-call it, so constructor and future frame draws share a stable entry"
        ),
    ),
)


def ranges_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]


def verify_patch_layout() -> None:
    dispatcher_range = (
        SLOT_REPAIR_DISPATCH_OFFSET,
        SLOT_REPAIR_DISPATCH_OFFSET + len(SLOT_REPAIR_DISPATCH_TARGET),
    )
    if dispatcher_range[0] != FANTASY_SOUL_USED_END:
        raise RuntimeError("v3 dispatcher is not anchored at the fantasy-soul used-end boundary")
    if not (
        FANTASY_SOUL_CAVE_START <= dispatcher_range[0]
        and dispatcher_range[1] <= FANTASY_SOUL_CAVE_END
    ):
        raise RuntimeError("v3 dispatcher exceeds the fantasy-soul reserved cave")

    protected_ranges = {
        "five-in-one PixelArt trampoline": (
            FIVE_IN_ONE_CAVE_START,
            FIVE_IN_ONE_USED_END,
        ),
        "fantasy-soul existing wrappers": (
            FANTASY_SOUL_CAVE_START,
            FANTASY_SOUL_USED_END,
        ),
        "Seris MemberView wrapper": (
            SERIS_WRAPPER_OFFSET,
            SERIS_WRAPPER_TAIL_OFFSET + 4,
        ),
        "official MemberView.draw entry": (
            ORIGINAL_DRAW_OFFSET,
            ORIGINAL_DRAW_OFFSET + 4,
        ),
        "MemberView.draw AOT table slot": (
            DRAW_METHOD_TABLE_OFFSET,
            DRAW_METHOD_TABLE_OFFSET + 8,
        ),
    }
    for name, protected in protected_ranges.items():
        if ranges_overlap(dispatcher_range, protected):
            raise RuntimeError(f"v3 dispatcher overlaps {name}")

    patch_ranges = [
        (item.name, (item.offset, item.offset + len(item.target)))
        for item in CODE_PATCHES
    ]
    for index, (name, current) in enumerate(patch_ranges):
        for other_name, other in patch_ranges[index + 1 :]:
            if ranges_overlap(current, other):
                raise RuntimeError(f"patch ranges overlap: {name} and {other_name}")


def macho_uuid_location(data: bytes) -> tuple[str, int]:
    if len(data) < 32 or struct.unpack_from("<I", data, 0)[0] != 0xFEEDFACF:
        raise RuntimeError("expected a thin little-endian ARM64 Mach-O")
    command_count = struct.unpack_from("<I", data, 16)[0]
    cursor = 32
    for _ in range(command_count):
        command, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or cursor + size > len(data):
            raise RuntimeError("invalid Mach-O load command")
        if command == 0x1B:
            raw_offset = cursor + 8
            return str(uuid.UUID(bytes=bytes(data[raw_offset : raw_offset + 16]))), raw_offset
        cursor += size
    raise RuntimeError("Mach-O has no LC_UUID")


def macho_uuid(data: bytes) -> str:
    return macho_uuid_location(data)[0]


def verify_source_contract(data: bytes) -> None:
    verify_patch_layout()
    dispatch = data[
        CONSTRUCTOR_DRAW_DISPATCH_OFFSET : CONSTRUCTOR_DRAW_DISPATCH_OFFSET
        + len(EXPECTED_CONSTRUCTOR_DRAW_DISPATCH)
    ]
    if dispatch != EXPECTED_CONSTRUCTOR_DRAW_DISPATCH:
        raise RuntimeError("MemberView constructor draw dispatch sequence changed")
    if data[ORIGINAL_DRAW_OFFSET : ORIGINAL_DRAW_OFFSET + 4] != ORIGINAL_DRAW_FIRST_INSTRUCTION:
        raise RuntimeError("official MemberView.draw entry is not stock")
    if (
        data[FIVE_IN_ONE_CAVE_START : FIVE_IN_ONE_CAVE_START + len(EXPECTED_FIVE_IN_ONE_HEAD)]
        != EXPECTED_FIVE_IN_ONE_HEAD
    ):
        raise RuntimeError("five-in-one PixelArt trampoline head changed")

    wrapper_hash = sha256_bytes(
        data[SERIS_WRAPPER_OFFSET : SERIS_WRAPPER_TAIL_OFFSET + 4]
    )
    if wrapper_hash != EXPECTED_WRAPPER_SHA256:
        raise RuntimeError(
            f"Seris wrapper hash mismatch: {wrapper_hash} != {EXPECTED_WRAPPER_SHA256}"
        )
    is_link, target = decode_branch_target(
        data[SERIS_WRAPPER_TAIL_OFFSET : SERIS_WRAPPER_TAIL_OFFSET + 4],
        SERIS_WRAPPER_TAIL_VA,
    )
    if is_link or target != ORIGINAL_DRAW_VA:
        raise RuntimeError("retained wrapper does not continue at official MemberView.draw")
    method_target = struct.unpack_from("<Q", data, DRAW_METHOD_TABLE_OFFSET)[0]
    if method_target != SERIS_WRAPPER_VA:
        raise RuntimeError("MemberView.draw AOT method-table target is not the retained wrapper")


def verify_target_contract(data: bytes) -> None:
    verify_patch_layout()
    if data[ORIGINAL_DRAW_OFFSET : ORIGINAL_DRAW_OFFSET + 4] != ORIGINAL_DRAW_FIRST_INSTRUCTION:
        raise RuntimeError("v3 unexpectedly changed the official draw entry")
    if (
        data[FIVE_IN_ONE_CAVE_START : FIVE_IN_ONE_CAVE_START + len(EXPECTED_FIVE_IN_ONE_HEAD)]
        != EXPECTED_FIVE_IN_ONE_HEAD
    ):
        raise RuntimeError("v3 changed the five-in-one PixelArt trampoline head")
    is_link, target = decode_branch_target(
        data[CONSTRUCTOR_DRAW_CALL_OFFSET : CONSTRUCTOR_DRAW_CALL_OFFSET + 4],
        IMAGE_BASE + CONSTRUCTOR_DRAW_CALL_OFFSET,
    )
    if not is_link or target != SLOT_REPAIR_DISPATCH_VA:
        raise RuntimeError("constructor draw call does not link to the slot repair dispatcher")

    dispatcher = data[
        SLOT_REPAIR_DISPATCH_OFFSET : SLOT_REPAIR_DISPATCH_OFFSET
        + len(SLOT_REPAIR_DISPATCH_TARGET)
    ]
    if dispatcher != SLOT_REPAIR_DISPATCH_TARGET:
        raise RuntimeError("slot repair dispatcher bytes changed")
    if dispatcher[:4] != LDR_X9_FROM_X1_PLUS_0X10:
        raise RuntimeError("slot repair dispatcher does not load MethodInfo from MethodEnv")
    if (
        decode_adrp_target(dispatcher[4:8], SLOT_REPAIR_DISPATCH_VA + 4, 10)
        != (SERIS_WRAPPER_VA & ~0xFFF)
    ):
        raise RuntimeError("slot repair dispatcher does not address the wrapper page")
    if dispatcher[8:12] != ADD_X10_X10_WRAPPER_PAGE_OFFSET:
        raise RuntimeError("slot repair dispatcher does not address the retained wrapper")
    if dispatcher[12:16] != STR_X10_TO_X9_PLUS_0X50:
        raise RuntimeError("slot repair dispatcher does not repair MethodInfo+0x50")
    if dispatcher[16:20] != BR_X10:
        raise RuntimeError("slot repair dispatcher does not tail-call the retained wrapper")

    is_link, target = decode_branch_target(
        data[SERIS_WRAPPER_TAIL_OFFSET : SERIS_WRAPPER_TAIL_OFFSET + 4],
        SERIS_WRAPPER_TAIL_VA,
    )
    if is_link or target != ORIGINAL_DRAW_VA:
        raise RuntimeError("retained wrapper no longer continues at official draw")
    method_target = struct.unpack_from("<Q", data, DRAW_METHOD_TABLE_OFFSET)[0]
    if method_target != SERIS_WRAPPER_VA:
        raise RuntimeError("v3 unexpectedly changed the AOT method-table target")
    if macho_uuid(data) != TARGET_MACHO_UUID:
        raise RuntimeError("v3 Mach-O UUID marker is missing")


def apply_patch(source: bytes) -> tuple[bytes, list[dict[str, object]]]:
    if len(source) != EXPECTED_SOURCE_MACHO_SIZE:
        raise RuntimeError(
            f"source Mach-O size mismatch: {len(source)} != {EXPECTED_SOURCE_MACHO_SIZE}"
        )
    actual_hash = sha256_bytes(source)
    if actual_hash != EXPECTED_SOURCE_MACHO_SHA256:
        raise RuntimeError(
            f"source Mach-O hash mismatch: {actual_hash} != {EXPECTED_SOURCE_MACHO_SHA256}"
        )
    actual_uuid, uuid_offset = macho_uuid_location(source)
    if actual_uuid != EXPECTED_SOURCE_MACHO_UUID:
        raise RuntimeError(
            f"source Mach-O UUID mismatch: {actual_uuid} != {EXPECTED_SOURCE_MACHO_UUID}"
        )
    verify_source_contract(source)

    patches = CODE_PATCHES + (
        BinaryPatch(
            name="MachO.testBuildUuidMarker",
            offset=uuid_offset,
            source=uuid.UUID(EXPECTED_SOURCE_MACHO_UUID).bytes,
            target=uuid.UUID(TARGET_MACHO_UUID).bytes,
            purpose="give v3 a distinct LC_UUID so a later IPS proves which binary ran",
        ),
    )
    patched = bytearray(source)
    reports: list[dict[str, object]] = []
    allowed_offsets: set[int] = set()
    for item in patches:
        end = item.offset + len(item.source)
        if len(item.source) != len(item.target):
            raise RuntimeError(f"{item.name} is not an in-place patch")
        actual = source[item.offset:end]
        if actual != item.source:
            raise RuntimeError(
                f"{item.name} source bytes mismatch at {item.offset:#x}: "
                f"{actual.hex()} != {item.source.hex()}"
            )
        patched[item.offset:end] = item.target
        allowed_offsets.update(range(item.offset, end))
        reports.append(
            {
                "name": item.name,
                "offset": hex(item.offset),
                "size": len(item.source),
                "sourceHex": item.source.hex(),
                "targetHex": item.target.hex(),
                "purpose": item.purpose,
            }
        )

    target = bytes(patched)
    unexpected = [
        index
        for index, (before, after) in enumerate(zip(source, target))
        if before != after and index not in allowed_offsets
    ]
    if unexpected:
        raise RuntimeError(f"unexpected Mach-O change at {unexpected[0]:#x}")
    verify_target_contract(target)
    return target, reports


def build_target_plist(source: bytes) -> bytes:
    descriptor = plistlib.loads(source)
    if descriptor.get("CFBundleIdentifier") != EXPECTED_BUNDLE_ID:
        raise RuntimeError("source CFBundleIdentifier mismatch")
    if descriptor.get("CFBundleShortVersionString") != EXPECTED_SHORT_VERSION:
        raise RuntimeError("source CFBundleShortVersionString mismatch")
    if descriptor.get("CFBundleVersion") != EXPECTED_SOURCE_BUILD:
        raise RuntimeError("source CFBundleVersion mismatch")
    descriptor["CFBundleVersion"] = TARGET_BUILD
    output_format = plistlib.FMT_BINARY if source.startswith(b"bplist00") else plistlib.FMT_XML
    return plistlib.dumps(descriptor, fmt=output_format, sort_keys=False)


def verify_plist_contract(source: bytes, target: bytes) -> None:
    before = plistlib.loads(source)
    after = plistlib.loads(target)
    expected = copy.deepcopy(before)
    expected["CFBundleVersion"] = TARGET_BUILD
    if after != expected:
        raise RuntimeError("Info.plist changed outside CFBundleVersion")
    if after.get("CFBundleIdentifier") != EXPECTED_BUNDLE_ID:
        raise RuntimeError("CFBundleIdentifier changed unexpectedly")
    if after.get("CFBundleShortVersionString") != EXPECTED_SHORT_VERSION:
        raise RuntimeError("CFBundleShortVersionString changed unexpectedly")
    if after.get("CFBundleVersion") != TARGET_BUILD:
        raise RuntimeError("v3 build marker is missing")


def zipinfo_signature(info: zipfile.ZipInfo) -> tuple[object, ...]:
    return (
        info.filename,
        info.date_time,
        info.compress_type,
        info.comment,
        info.extra,
        info.create_system,
        info.create_version,
        info.extract_version,
        info.flag_bits,
        info.volume,
        info.internal_attr,
        info.external_attr,
    )


def write_output(
    source_path: Path,
    output_path: Path,
    patched_macho: bytes,
    patched_plist: bytes,
) -> None:
    temporary = output_path.with_name(output_path.name + ".tmp")
    if temporary.exists():
        raise RuntimeError(f"temporary output already exists: {temporary}")
    try:
        with zipfile.ZipFile(source_path, "r") as source_zip, zipfile.ZipFile(
            temporary, "w"
        ) as output_zip:
            output_zip.comment = source_zip.comment
            for source_info in source_zip.infolist():
                if source_info.filename == MACHO_MEMBER:
                    data = patched_macho
                elif source_info.filename == INFO_PLIST_MEMBER:
                    data = patched_plist
                else:
                    data = source_zip.read(source_info)
                output_zip.writestr(copy.copy(source_info), data)
        os.replace(temporary, output_path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def verify_output(
    source_path: Path,
    output_path: Path,
    target_macho: bytes,
    target_plist: bytes,
) -> None:
    with zipfile.ZipFile(source_path, "r") as source_zip, zipfile.ZipFile(
        output_path, "r"
    ) as output_zip:
        source_infos = source_zip.infolist()
        output_infos = output_zip.infolist()
        if [info.filename for info in output_infos] != [info.filename for info in source_infos]:
            raise RuntimeError("output IPA member order or names changed")
        if output_zip.comment != source_zip.comment:
            raise RuntimeError("output IPA ZIP comment changed")
        for source_info, output_info in zip(source_infos, output_infos):
            if zipinfo_signature(source_info) != zipinfo_signature(output_info):
                raise RuntimeError(f"ZIP metadata changed for {source_info.filename}")
            output_data = output_zip.read(output_info)
            if source_info.filename == MACHO_MEMBER:
                if output_data != target_macho:
                    raise RuntimeError("output IPA Mach-O readback mismatch")
            elif source_info.filename == INFO_PLIST_MEMBER:
                if output_data != target_plist:
                    raise RuntimeError("output IPA Info.plist readback mismatch")
            elif output_data != source_zip.read(source_info):
                raise RuntimeError(f"unexpected IPA member content change: {source_info.filename}")

        verify_target_contract(output_zip.read(MACHO_MEMBER))
        verify_plist_contract(
            source_zip.read(INFO_PLIST_MEMBER), output_zip.read(INFO_PLIST_MEMBER)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Patch the vetted iOS final IPA so the MemberView constructor installs "
            "a stable retained-wrapper pointer in draw's MethodInfo implementation slot."
        )
    )
    parser.add_argument("--ipa", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path: Path = args.ipa.resolve()
    output_path: Path = args.out.resolve()
    report_path: Path = (
        args.report.resolve() if args.report is not None else output_path.with_suffix(".json")
    )
    if not source_path.is_file():
        raise SystemExit(f"source IPA does not exist: {source_path}")
    if output_path.exists():
        raise SystemExit(f"refusing to overwrite output IPA: {output_path}")
    if report_path.exists():
        raise SystemExit(f"refusing to overwrite report: {report_path}")
    if source_path == output_path:
        raise SystemExit("source and output IPA must be different files")

    source_ipa_hash = sha256_file(source_path)
    if source_ipa_hash != EXPECTED_SOURCE_IPA_SHA256:
        raise SystemExit(
            f"source IPA hash mismatch: {source_ipa_hash} != {EXPECTED_SOURCE_IPA_SHA256}"
        )
    with zipfile.ZipFile(source_path, "r") as source_zip:
        names = source_zip.namelist()
        if names.count(MACHO_MEMBER) != 1:
            raise SystemExit(f"expected exactly one {MACHO_MEMBER} member")
        if names.count(INFO_PLIST_MEMBER) != 1:
            raise SystemExit(f"expected exactly one {INFO_PLIST_MEMBER} member")
        source_macho = source_zip.read(MACHO_MEMBER)
        source_plist = source_zip.read(INFO_PLIST_MEMBER)

    target_macho, patch_reports = apply_patch(source_macho)
    target_plist = build_target_plist(source_plist)
    verify_plist_contract(source_plist, target_plist)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_output(source_path, output_path, target_macho, target_plist)
    verify_output(source_path, output_path, target_macho, target_plist)

    report = {
        "schemaVersion": 3,
        "status": "unsigned_device_test_required",
        "purpose": (
            "MemberView.draw MethodInfo slot repair with retained MOD wrapper and "
            "official draw continuation"
        ),
        "sourceIpa": str(source_path),
        "sourceIpaSha256": source_ipa_hash,
        "outputIpa": str(output_path),
        "outputIpaSha256": sha256_file(output_path),
        "sourceMachoSha256": sha256_bytes(source_macho),
        "outputMachoSha256": sha256_bytes(target_macho),
        "sourceMachoUuid": EXPECTED_SOURCE_MACHO_UUID,
        "outputMachoUuid": macho_uuid(target_macho),
        "bundleIdentifier": EXPECTED_BUNDLE_ID,
        "shortVersion": EXPECTED_SHORT_VERSION,
        "sourceBuild": EXPECTED_SOURCE_BUILD,
        "outputBuild": TARGET_BUILD,
        "observedCrash": {
            "callOffset": hex(CONSTRUCTOR_DRAW_CALL_OFFSET),
            "returnOffset": hex(CONSTRUCTOR_DRAW_RETURN_OFFSET),
            "fault": (
                "AIR draw implementation dispatch ultimately reached address zero; "
                "the prior pre-resolver null check did not cover this path"
            ),
        },
        "routing": {
            "constructorCall": hex(IMAGE_BASE + CONSTRUCTOR_DRAW_CALL_OFFSET),
            "slotRepairDispatcher": hex(SLOT_REPAIR_DISPATCH_VA),
            "methodInfoImplementationOffset": "0x50",
            "installedTarget": hex(SERIS_WRAPPER_VA),
            "retainedWrapper": hex(SERIS_WRAPPER_VA),
            "officialContinuation": hex(ORIGINAL_DRAW_VA),
            "firstDraw": "constructor -> slot repair -> retained wrapper -> official draw",
            "futureDraws": (
                "Drawable.draw dispatch -> repaired MethodInfo+0x50 -> retained wrapper "
                "-> official draw"
            ),
        },
        "codeCaveLayout": {
            "fantasySoulCave": [
                hex(FANTASY_SOUL_CAVE_START),
                hex(FANTASY_SOUL_CAVE_END),
            ],
            "fantasySoulExistingUsedEnd": hex(FANTASY_SOUL_USED_END),
            "v3DispatcherRange": [
                hex(SLOT_REPAIR_DISPATCH_OFFSET),
                hex(SLOT_REPAIR_DISPATCH_OFFSET + len(SLOT_REPAIR_DISPATCH_TARGET)),
            ],
            "fiveInOneProtectedRange": [
                hex(FIVE_IN_ONE_CAVE_START),
                hex(FIVE_IN_ONE_USED_END),
            ],
            "fiveInOnePixelArtTrampoline": "preserved",
        },
        "modCompatibility": {
            "serisDualFormWrapper": "preserved",
            "renderScale": "unchanged",
            "fantasySoulAsyncTexture": "unchanged",
            "otherFiveInOnePatches": "unchanged",
        },
        "patches": patch_reports,
        "verification": [
            "exact input IPA/Mach-O hash and source LC_UUID",
            "exact constructor dispatch, retained wrapper, and code-host source bytes",
            "ARM64 BL/ADRP/ADD/STR/BR targets and ABI-preserving tail call",
            "dispatcher range does not overlap existing fantasy-soul, five-in-one, or Seris code",
            "five-in-one PixelArt trampoline head remains byte-identical",
            "retained wrapper tail still continues at stock MemberView.draw",
            "AOT MemberView.draw table remains on the retained wrapper",
            "only declared Mach-O ranges changed",
            "distinct CFBundleVersion and LC_UUID diagnostic markers",
            "all other Info.plist values unchanged",
            "all other IPA members and ZIP metadata unchanged",
            "output IPA full readback",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_report = report_path.with_name(report_path.name + ".tmp")
    temporary_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary_report, report_path)
    print(f"output IPA: {output_path}")
    print(f"output SHA-256: {report['outputIpaSha256']}")
    print(f"build marker: {TARGET_BUILD}")
    print(f"Mach-O UUID marker: {report['outputMachoUuid']}")
    print(f"report: {report_path}")
    print("status: unsigned; device signing and regression testing are required")


if __name__ == "__main__":
    main()
