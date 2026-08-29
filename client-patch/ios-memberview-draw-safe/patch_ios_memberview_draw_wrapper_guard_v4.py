from __future__ import annotations

import argparse
import copy
import json
import os
import plistlib
import struct
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

import patch_ios_memberview_draw_slot_v3 as v3


TARGET_BUILD = "1.8.44"
TARGET_MACHO_UUID = "f8ccbffa-2f58-587a-91a0-bd47d4d0efa2"

WRAPPER_GUARD_OFFSET = 0x30199D4
WRAPPER_GUARD_VA = v3.IMAGE_BASE + WRAPPER_GUARD_OFFSET
WRAPPER_GUARD_SOURCE = bytes.fromhex("575301b4e80a40f9e00317aa")

WRAPPER_CLEANUP_OFFSET = 0x3D6948C
WRAPPER_CLEANUP_VA = v3.IMAGE_BASE + WRAPPER_CLEANUP_OFFSET

# These are the retained Seris wrapper's MethodInfo implementation dispatches.
# The call at 0x3D69360 is deliberately excluded: it already compares X8 with
# its exact expected implementation and takes the wrapper fallback on mismatch.
UNSAFE_WRAPPER_CALL_OFFSETS = (
    0x3D69318,
    0x3D693E4,
    0x3D69418,
    0x3D69458,
    0x3D69488,
)
BLR_X8 = struct.pack("<I", 0xD63F0100)
BR_X8 = struct.pack("<I", 0xD61F0100)


def encode_cbz_x(register: int, source_va: int, target_va: int) -> bytes:
    if not 0 <= register <= 31:
        raise ValueError("ARM64 CBZ register is invalid")
    delta = target_va - source_va
    if delta % 4:
        raise ValueError("ARM64 CBZ target is not instruction-aligned")
    immediate = delta // 4
    if not -(1 << 18) <= immediate < (1 << 18):
        raise ValueError("ARM64 CBZ target is outside the 19-bit range")
    return struct.pack(
        "<I",
        0xB4000000 | ((immediate & 0x7FFFF) << 5) | register,
    )


def decode_cbz_x_target(
    instruction: bytes,
    source_va: int,
    expected_register: int,
) -> int:
    word = struct.unpack("<I", instruction)[0]
    if word & 0xFF00001F != 0xB4000000 | expected_register:
        raise ValueError(
            f"not the expected ARM64 CBZ X{expected_register}: {word:#x}"
        )
    immediate = (word >> 5) & 0x7FFFF
    if immediate & (1 << 18):
        immediate -= 1 << 19
    return source_va + immediate * 4


WRAPPER_GUARD_TARGET = b"".join(
    (
        encode_cbz_x(8, WRAPPER_GUARD_VA, WRAPPER_GUARD_VA + 8),
        BR_X8,
        v3.encode_branch(WRAPPER_GUARD_VA + 8, WRAPPER_CLEANUP_VA),
    )
)


@dataclass(frozen=True)
class IncrementalPatch:
    name: str
    offset: int
    source: bytes
    target: bytes
    purpose: str


def call_patch(offset: int) -> IncrementalPatch:
    return IncrementalPatch(
        name=f"SerisWrapper.guardDynamicCall.{offset:#x}",
        offset=offset,
        source=BLR_X8,
        target=v3.encode_branch(
            v3.IMAGE_BASE + offset,
            WRAPPER_GUARD_VA,
            link=True,
        ),
        purpose=(
            "route the wrapper's AIR implementation call through the shared null "
            "guard while preserving normal non-null call/return behavior"
        ),
    )


INCREMENTAL_CODE_PATCHES = (
    IncrementalPatch(
        name="SerisWrapper.dynamicCallNullGuard",
        offset=WRAPPER_GUARD_OFFSET,
        source=WRAPPER_GUARD_SOURCE,
        target=WRAPPER_GUARD_TARGET,
        purpose=(
            "BR to a non-null X8 implementation, or jump to the wrapper's existing "
            "cleanup and official-draw fallback when X8 is null"
        ),
    ),
    *(call_patch(offset) for offset in UNSAFE_WRAPPER_CALL_OFFSETS),
)


def ranges_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]


def verify_patch_layout() -> None:
    v3.verify_patch_layout()
    guard_range = (
        WRAPPER_GUARD_OFFSET,
        WRAPPER_GUARD_OFFSET + len(WRAPPER_GUARD_TARGET),
    )
    dispatcher_end = v3.SLOT_REPAIR_DISPATCH_OFFSET + len(
        v3.SLOT_REPAIR_DISPATCH_TARGET
    )
    if guard_range[0] != dispatcher_end:
        raise RuntimeError("v4 guard is not immediately after the v3 dispatcher")
    if not (
        v3.FANTASY_SOUL_CAVE_START <= guard_range[0]
        and guard_range[1] <= v3.FANTASY_SOUL_CAVE_END
    ):
        raise RuntimeError("v4 guard exceeds the fantasy-soul reserved cave")

    protected_ranges = {
        "fantasy-soul existing wrappers": (
            v3.FANTASY_SOUL_CAVE_START,
            v3.FANTASY_SOUL_USED_END,
        ),
        "v3 slot repair dispatcher": (
            v3.SLOT_REPAIR_DISPATCH_OFFSET,
            dispatcher_end,
        ),
        "five-in-one PixelArt trampoline": (
            v3.FIVE_IN_ONE_CAVE_START,
            v3.FIVE_IN_ONE_USED_END,
        ),
        "official MemberView.draw entry": (
            v3.ORIGINAL_DRAW_OFFSET,
            v3.ORIGINAL_DRAW_OFFSET + 4,
        ),
        "MemberView.draw AOT table slot": (
            v3.DRAW_METHOD_TABLE_OFFSET,
            v3.DRAW_METHOD_TABLE_OFFSET + 8,
        ),
    }
    for name, protected in protected_ranges.items():
        if ranges_overlap(guard_range, protected):
            raise RuntimeError(f"v4 guard overlaps {name}")

    patch_ranges = [
        (item.name, (item.offset, item.offset + len(item.target)))
        for item in INCREMENTAL_CODE_PATCHES
    ]
    for index, (name, current) in enumerate(patch_ranges):
        for other_name, other in patch_ranges[index + 1 :]:
            if ranges_overlap(current, other):
                raise RuntimeError(f"v4 patch ranges overlap: {name} and {other_name}")

    wrapper_range = (v3.SERIS_WRAPPER_OFFSET, v3.SERIS_WRAPPER_TAIL_OFFSET)
    for offset in UNSAFE_WRAPPER_CALL_OFFSETS:
        if not (wrapper_range[0] <= offset and offset + 4 <= wrapper_range[1]):
            raise RuntimeError(f"wrapper call site is outside the retained wrapper: {offset:#x}")


def restore_v3_target(data: bytes) -> bytes:
    restored = bytearray(data)
    actual_uuid, uuid_offset = v3.macho_uuid_location(data)
    if actual_uuid != TARGET_MACHO_UUID:
        raise RuntimeError("v4 Mach-O UUID marker is missing")
    restored[uuid_offset : uuid_offset + 16] = uuid.UUID(v3.TARGET_MACHO_UUID).bytes
    for item in INCREMENTAL_CODE_PATCHES:
        end = item.offset + len(item.target)
        if restored[item.offset:end] != item.target:
            raise RuntimeError(f"v4 patch bytes changed: {item.name}")
        restored[item.offset:end] = item.source
    return bytes(restored)


def verify_target_contract(data: bytes) -> None:
    verify_patch_layout()

    # Reconstruct the already-verified v3 image and reuse its full contract for
    # the constructor repair, MOD wrapper tail, AOT table, and protected caves.
    v3.verify_target_contract(restore_v3_target(data))

    guard = data[
        WRAPPER_GUARD_OFFSET : WRAPPER_GUARD_OFFSET + len(WRAPPER_GUARD_TARGET)
    ]
    if guard != WRAPPER_GUARD_TARGET:
        raise RuntimeError("v4 wrapper guard bytes changed")
    if (
        decode_cbz_x_target(guard[:4], WRAPPER_GUARD_VA, 8)
        != WRAPPER_GUARD_VA + 8
    ):
        raise RuntimeError("v4 guard does not select fallback when X8 is null")
    if guard[4:8] != BR_X8:
        raise RuntimeError("v4 guard does not tail-call a non-null X8")
    is_link, target = v3.decode_branch_target(guard[8:12], WRAPPER_GUARD_VA + 8)
    if is_link or target != WRAPPER_CLEANUP_VA:
        raise RuntimeError("v4 guard does not branch to wrapper cleanup")

    for offset in UNSAFE_WRAPPER_CALL_OFFSETS:
        is_link, target = v3.decode_branch_target(
            data[offset : offset + 4],
            v3.IMAGE_BASE + offset,
        )
        if not is_link or target != WRAPPER_GUARD_VA:
            raise RuntimeError(
                f"wrapper call does not link to the shared guard: {offset:#x}"
            )

    if v3.macho_uuid(data) != TARGET_MACHO_UUID:
        raise RuntimeError("v4 Mach-O UUID marker is missing")


def apply_patch(source: bytes) -> tuple[bytes, list[dict[str, object]]]:
    v3_target, v3_reports = v3.apply_patch(source)
    v3.verify_target_contract(v3_target)
    verify_patch_layout()

    actual_uuid, uuid_offset = v3.macho_uuid_location(v3_target)
    if actual_uuid != v3.TARGET_MACHO_UUID:
        raise RuntimeError("v3 intermediate Mach-O UUID marker is missing")
    patches = INCREMENTAL_CODE_PATCHES + (
        IncrementalPatch(
            name="MachO.v4TestBuildUuidMarker",
            offset=uuid_offset,
            source=uuid.UUID(v3.TARGET_MACHO_UUID).bytes,
            target=uuid.UUID(TARGET_MACHO_UUID).bytes,
            purpose="give v4 a distinct LC_UUID so a later IPS proves which binary ran",
        ),
    )

    patched = bytearray(v3_target)
    reports = list(v3_reports)
    allowed_offsets: set[int] = set()
    for item in patches:
        end = item.offset + len(item.source)
        if len(item.source) != len(item.target):
            raise RuntimeError(f"{item.name} is not an in-place patch")
        actual = v3_target[item.offset:end]
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
        for index, (before, after) in enumerate(zip(v3_target, target))
        if before != after and index not in allowed_offsets
    ]
    if unexpected:
        raise RuntimeError(f"unexpected v4 Mach-O change at {unexpected[0]:#x}")
    verify_target_contract(target)
    return target, reports


def build_target_plist(source: bytes) -> bytes:
    descriptor = plistlib.loads(source)
    if descriptor.get("CFBundleIdentifier") != v3.EXPECTED_BUNDLE_ID:
        raise RuntimeError("source CFBundleIdentifier mismatch")
    if descriptor.get("CFBundleShortVersionString") != v3.EXPECTED_SHORT_VERSION:
        raise RuntimeError("source CFBundleShortVersionString mismatch")
    if descriptor.get("CFBundleVersion") != v3.EXPECTED_SOURCE_BUILD:
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
    if after.get("CFBundleVersion") != TARGET_BUILD:
        raise RuntimeError("v4 build marker is missing")


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
            if v3.zipinfo_signature(source_info) != v3.zipinfo_signature(output_info):
                raise RuntimeError(f"ZIP metadata changed for {source_info.filename}")
            output_data = output_zip.read(output_info)
            if source_info.filename == v3.MACHO_MEMBER:
                if output_data != target_macho:
                    raise RuntimeError("output IPA Mach-O readback mismatch")
            elif source_info.filename == v3.INFO_PLIST_MEMBER:
                if output_data != target_plist:
                    raise RuntimeError("output IPA Info.plist readback mismatch")
            elif output_data != source_zip.read(source_info):
                raise RuntimeError(f"unexpected IPA member content change: {source_info.filename}")

        verify_target_contract(output_zip.read(v3.MACHO_MEMBER))
        verify_plist_contract(
            source_zip.read(v3.INFO_PLIST_MEMBER),
            output_zip.read(v3.INFO_PLIST_MEMBER),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Patch the vetted iOS final IPA with the v3 MemberView.draw slot repair "
            "plus null guards for retained-wrapper AIR implementation calls."
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

    source_ipa_hash = v3.sha256_file(source_path)
    if source_ipa_hash != v3.EXPECTED_SOURCE_IPA_SHA256:
        raise SystemExit(
            f"source IPA hash mismatch: {source_ipa_hash} != {v3.EXPECTED_SOURCE_IPA_SHA256}"
        )
    with zipfile.ZipFile(source_path, "r") as source_zip:
        names = source_zip.namelist()
        if names.count(v3.MACHO_MEMBER) != 1:
            raise SystemExit(f"expected exactly one {v3.MACHO_MEMBER} member")
        if names.count(v3.INFO_PLIST_MEMBER) != 1:
            raise SystemExit(f"expected exactly one {v3.INFO_PLIST_MEMBER} member")
        source_macho = source_zip.read(v3.MACHO_MEMBER)
        source_plist = source_zip.read(v3.INFO_PLIST_MEMBER)

    target_macho, patch_reports = apply_patch(source_macho)
    target_plist = build_target_plist(source_plist)
    verify_plist_contract(source_plist, target_plist)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    v3.write_output(source_path, output_path, target_macho, target_plist)
    verify_output(source_path, output_path, target_macho, target_plist)

    report = {
        "schemaVersion": 4,
        "status": "unsigned_device_test_required",
        "purpose": (
            "MemberView.draw slot repair plus retained-wrapper internal null guards "
            "and official draw fallback"
        ),
        "sourceIpa": str(source_path),
        "sourceIpaSha256": source_ipa_hash,
        "outputIpa": str(output_path),
        "outputIpaSha256": v3.sha256_file(output_path),
        "sourceMachoSha256": v3.sha256_bytes(source_macho),
        "outputMachoSha256": v3.sha256_bytes(target_macho),
        "sourceMachoUuid": v3.EXPECTED_SOURCE_MACHO_UUID,
        "outputMachoUuid": v3.macho_uuid(target_macho),
        "bundleIdentifier": v3.EXPECTED_BUNDLE_ID,
        "shortVersion": v3.EXPECTED_SHORT_VERSION,
        "sourceBuild": v3.EXPECTED_SOURCE_BUILD,
        "outputBuild": TARGET_BUILD,
        "observedV3Crash": {
            "ipsBuild": v3.TARGET_BUILD,
            "ipsMachoUuid": v3.TARGET_MACHO_UUID,
            "wrapperCallOffset": "0x3d69318",
            "wrapperReturnOffset": "0x3d6931c",
            "fault": (
                "the retained wrapper loaded a null implementation from "
                "MethodInfo+0x50 and executed BLR X8"
            ),
        },
        "routing": {
            "constructorSlotRepairDispatcher": hex(v3.SLOT_REPAIR_DISPATCH_VA),
            "retainedWrapper": hex(v3.SERIS_WRAPPER_VA),
            "sharedWrapperGuard": hex(WRAPPER_GUARD_VA),
            "nullFallbackCleanup": hex(WRAPPER_CLEANUP_VA),
            "officialContinuation": hex(v3.ORIGINAL_DRAW_VA),
            "nonNullPath": "BL guard -> BR implementation -> return to wrapper",
            "nullPath": "BL guard -> wrapper cleanup -> official MemberView.draw",
        },
        "guardedWrapperCalls": [hex(offset) for offset in UNSAFE_WRAPPER_CALL_OFFSETS],
        "codeCaveLayout": {
            "fantasySoulCave": [
                hex(v3.FANTASY_SOUL_CAVE_START),
                hex(v3.FANTASY_SOUL_CAVE_END),
            ],
            "v3DispatcherRange": [
                hex(v3.SLOT_REPAIR_DISPATCH_OFFSET),
                hex(
                    v3.SLOT_REPAIR_DISPATCH_OFFSET
                    + len(v3.SLOT_REPAIR_DISPATCH_TARGET)
                ),
            ],
            "v4GuardRange": [
                hex(WRAPPER_GUARD_OFFSET),
                hex(WRAPPER_GUARD_OFFSET + len(WRAPPER_GUARD_TARGET)),
            ],
            "fiveInOneProtectedRange": [
                hex(v3.FIVE_IN_ONE_CAVE_START),
                hex(v3.FIVE_IN_ONE_USED_END),
            ],
            "fiveInOnePixelArtTrampoline": "preserved",
        },
        "modCompatibility": {
            "serisDualFormWrapper": "preserved; bypassed only for a frame whose internal implementation is null",
            "renderScale": "unchanged",
            "fantasySoulAsyncTexture": "unchanged",
            "otherFiveInOnePatches": "unchanged",
        },
        "patches": patch_reports,
        "verification": [
            "all v3 source, layout, constructor repair, AOT table, and MOD preservation contracts",
            "exact source bytes for the shared guard host and five wrapper BLR X8 call sites",
            "ARM64 BL, CBZ, BR, and fallback B targets",
            "non-null calls preserve each wrapper call site's link return address",
            "null calls enter the wrapper's existing cleanup before official draw",
            "guard does not overlap fantasy-soul wrappers, v3 dispatcher, five-in-one trampoline, official draw, or AOT table",
            "only declared v4 Mach-O ranges changed after the verified v3 transform",
            "distinct CFBundleVersion and LC_UUID diagnostic markers",
            "all other Info.plist values unchanged",
            "all other IPA members and ZIP metadata unchanged",
            "output IPA full readback",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_report = report_path.with_name(report_path.name + ".tmp")
    temporary_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
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
