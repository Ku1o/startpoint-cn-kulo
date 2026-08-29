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

import patch_ios_memberview_draw_wrapper_guard_v4 as v4


TARGET_BUILD = "1.8.46"
TARGET_MACHO_UUID = "064f8e49-fdd9-532f-8445-439ab9f71e6c"
ACCEPTED_OUTPUT_IPA_SHA256 = (
    "c3e22d1e5db5c45b6864d4125a86ea194134ff3032af1a060f3b40f711f5848a"
)

# Verified against the official Android 1.8.1 AS3/P-code and the matching iOS
# embedded ABC/AOT image.  The descriptor table is PoolObject+0x198; the
# getCharacterAnimation MemberPeek interface descriptor is at table+0x804b8.
INTERFACE_RESOLVER_VA = 0x100A268C0
MEMBER_IMPL_GET_CHARACTER_ANIMATION_VA = 0x102B69AF8
MEMBER_PEEK_GET_CHARACTER_ANIMATION_DESCRIPTOR_OFFSET = 0x804B8
MEMBER_IMPL_SOURCE_OFFSET = 0x120
SOURCE_CHARACTER_TAGS_OFFSET = 0xC8
SOURCE_MAIN_CHARACTER_STRING_ID_OFFSET = 0xB0

# V4 ends at 0x30199e0.  V6 places the verified concrete-type gate immediately
# after it in the fantasy-soul patch's already-sacrificed debug method tail.
TYPE_GATE_OFFSET = 0x30199E0
TYPE_GATE_VA = v4.v3.IMAGE_BASE + TYPE_GATE_OFFSET
TYPE_GATE_SOURCE = bytes.fromhex(
    "015d40f9280840f9082940f900013fd61f0400718b500154d500a0527b00a052"
    "3c00a052f8031f2a15699a721bed8c721c7c9b72e0a30191e103182ae20317aa"
    "9c356897e10300aae0a3019160366897e82740f9f90300aa3a0b0091"
)
TYPE_GATE_TARGET = bytes.fromhex(
    "fe0f1ff8"  # str x30, [sp, #-0x10]!
    "a8ce40f9"  # ldr x8, [x21, #0x198]
    "480200b4"  # cbz x8, failure
    "0901a052"  # mov w9, #0x80000
    "09978072"  # movk w9, #0x4b8 -> 0x804b8
    "016969f8"  # ldr x1, [x8, x9]
    "c10100b4"  # cbz x1, failure
    "e0030291"  # add x0, sp, #0x80 (caller's MethodFrame at sp+0x70)
    "e20317aa"  # mov x2, x23
    "af336897"  # bl 0x100a268c0
    "400100b4"  # cbz x0, failure
    "080840f9"  # ldr x8, [x0, #0x10]
    "080100b4"  # cbz x8, failure
    "082940f9"  # ldr x8, [x8, #0x50]
    "89daff90"  # adrp x9, 0x102b69000
    "29e12b91"  # add x9, x9, #0xaf8
    "1f0109eb"  # cmp x8, x9
    "61000054"  # b.ne failure
    "fb9240f9"  # ldr x27, [x23, #0x120]
    "02000014"  # b restore
    "fb031faa"  # failure: mov x27, xzr
    "fe0741f8"  # restore: ldr x30, [sp], #0x10
    "c0035fd6"  # ret
)

WRAPPER_TYPE_GATE_CALL_OFFSET = 0x3D691D8
WRAPPER_TYPE_GATE_CALL_SOURCE = bytes.fromhex("fb9240f9")
WRAPPER_TYPE_GATE_CALL_TARGET = v4.v3.encode_branch(
    v4.v3.IMAGE_BASE + WRAPPER_TYPE_GATE_CALL_OFFSET,
    TYPE_GATE_VA,
    link=True,
)

WRAPPER_CHARACTER_TAGS_LOAD_OFFSET = 0x3D691E0
WRAPPER_CHARACTER_TAGS_LOAD_SOURCE = bytes.fromhex("788340f9")
WRAPPER_CHARACTER_TAGS_LOAD_TARGET = bytes.fromhex("786740f9")

WRAPPER_MAIN_CHARACTER_ID_LOAD_OFFSET = 0x3D6938C
WRAPPER_MAIN_CHARACTER_ID_LOAD_SOURCE = bytes.fromhex("626340f9")
WRAPPER_MAIN_CHARACTER_ID_LOAD_TARGET = bytes.fromhex("625b40f9")


@dataclass(frozen=True)
class IncrementalPatch:
    name: str
    offset: int
    source: bytes
    target: bytes
    purpose: str


INCREMENTAL_CODE_PATCHES = (
    IncrementalPatch(
        name="SerisWrapper.verifiedMemberImplTypeGate",
        offset=TYPE_GATE_OFFSET,
        source=TYPE_GATE_SOURCE,
        target=TYPE_GATE_TARGET,
        purpose=(
            "resolve official MemberPeek.getCharacterAnimation and require the "
            "exact MemberImpl AOT implementation before reading MemberImpl fields"
        ),
    ),
    IncrementalPatch(
        name="SerisWrapper.callVerifiedTypeGate",
        offset=WRAPPER_TYPE_GATE_CALL_OFFSET,
        source=WRAPPER_TYPE_GATE_CALL_SOURCE,
        target=WRAPPER_TYPE_GATE_CALL_TARGET,
        purpose=(
            "replace the raw MemberImpl+0x120 source load with a linked call to "
            "the verified concrete-type gate"
        ),
    ),
    IncrementalPatch(
        name="SerisWrapper.loadVerifiedCharacterTags",
        offset=WRAPPER_CHARACTER_TAGS_LOAD_OFFSET,
        source=WRAPPER_CHARACTER_TAGS_LOAD_SOURCE,
        target=WRAPPER_CHARACTER_TAGS_LOAD_TARGET,
        purpose="load SquadMemberSource.characterTags from the verified +0xc8 field",
    ),
    IncrementalPatch(
        name="SerisWrapper.loadVerifiedMainCharacterStringId",
        offset=WRAPPER_MAIN_CHARACTER_ID_LOAD_OFFSET,
        source=WRAPPER_MAIN_CHARACTER_ID_LOAD_SOURCE,
        target=WRAPPER_MAIN_CHARACTER_ID_LOAD_TARGET,
        purpose=(
            "load SquadMemberSource.mainCharacterStringId from the verified +0xb0 "
            "field when constructing the special pixel-art path"
        ),
    ),
)


def ranges_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]


def decode_b_cond_target(instruction: bytes, source_va: int) -> int:
    word = int.from_bytes(instruction, "little")
    if word & 0xFF000010 != 0x54000000:
        raise ValueError(f"not an ARM64 B.cond instruction: {word:#x}")
    immediate = (word >> 5) & 0x7FFFF
    if immediate & (1 << 18):
        immediate -= 1 << 19
    return source_va + immediate * 4


def decode_cbz_family_target(instruction: bytes, source_va: int) -> int:
    word = int.from_bytes(instruction, "little")
    if word & 0x7E000000 != 0x34000000:
        raise ValueError(f"not an ARM64 CBZ/CBNZ instruction: {word:#x}")
    immediate = (word >> 5) & 0x7FFFF
    if immediate & (1 << 18):
        immediate -= 1 << 19
    return source_va + immediate * 4


def decode_ldr_x_unsigned_offset(
    instruction: bytes,
    expected_target_register: int,
    expected_base_register: int,
) -> int:
    word = struct.unpack("<I", instruction)[0]
    if word & 0xFFC00000 != 0xF9400000:
        raise ValueError(f"not an ARM64 LDR X unsigned-immediate instruction: {word:#x}")
    if word & 0x1F != expected_target_register:
        raise ValueError("unexpected ARM64 LDR target register")
    if (word >> 5) & 0x1F != expected_base_register:
        raise ValueError("unexpected ARM64 LDR base register")
    return ((word >> 10) & 0xFFF) * 8


def verify_patch_layout() -> None:
    v4.verify_patch_layout()
    helper_range = (TYPE_GATE_OFFSET, TYPE_GATE_OFFSET + len(TYPE_GATE_TARGET))
    v4_guard_end = v4.WRAPPER_GUARD_OFFSET + len(v4.WRAPPER_GUARD_TARGET)
    if helper_range[0] != v4_guard_end:
        raise RuntimeError("v6 type gate is not immediately after the v4 guard")
    if not (
        v4.v3.FANTASY_SOUL_CAVE_START <= helper_range[0]
        and helper_range[1] <= v4.v3.FANTASY_SOUL_CAVE_END
    ):
        raise RuntimeError("v6 type gate exceeds the fantasy-soul reserved cave")

    protected_ranges = {
        "fantasy-soul existing wrappers": (
            v4.v3.FANTASY_SOUL_CAVE_START,
            v4.v3.FANTASY_SOUL_USED_END,
        ),
        "v3 slot repair dispatcher": (
            v4.v3.SLOT_REPAIR_DISPATCH_OFFSET,
            v4.v3.SLOT_REPAIR_DISPATCH_OFFSET
            + len(v4.v3.SLOT_REPAIR_DISPATCH_TARGET),
        ),
        "v4 shared null guard": (
            v4.WRAPPER_GUARD_OFFSET,
            v4_guard_end,
        ),
        "five-in-one PixelArt trampoline": (
            v4.v3.FIVE_IN_ONE_CAVE_START,
            v4.v3.FIVE_IN_ONE_USED_END,
        ),
        "Seris MemberView wrapper": (
            v4.v3.SERIS_WRAPPER_OFFSET,
            v4.v3.SERIS_WRAPPER_TAIL_OFFSET + 4,
        ),
        "official MemberView.draw entry": (
            v4.v3.ORIGINAL_DRAW_OFFSET,
            v4.v3.ORIGINAL_DRAW_OFFSET + 4,
        ),
        "MemberView.draw AOT table slot": (
            v4.v3.DRAW_METHOD_TABLE_OFFSET,
            v4.v3.DRAW_METHOD_TABLE_OFFSET + 8,
        ),
    }
    for name, protected in protected_ranges.items():
        if ranges_overlap(helper_range, protected):
            raise RuntimeError(f"v6 type gate overlaps {name}")

    wrapper_range = (
        v4.v3.SERIS_WRAPPER_OFFSET,
        v4.v3.SERIS_WRAPPER_TAIL_OFFSET,
    )
    for offset in (
        WRAPPER_TYPE_GATE_CALL_OFFSET,
        WRAPPER_CHARACTER_TAGS_LOAD_OFFSET,
        WRAPPER_MAIN_CHARACTER_ID_LOAD_OFFSET,
    ):
        if not (wrapper_range[0] <= offset and offset + 4 <= wrapper_range[1]):
            raise RuntimeError(f"v6 wrapper patch is outside the retained wrapper: {offset:#x}")

    patch_ranges = [
        (item.name, (item.offset, item.offset + len(item.target)))
        for item in INCREMENTAL_CODE_PATCHES
    ]
    for index, (name, current) in enumerate(patch_ranges):
        for other_name, other in patch_ranges[index + 1 :]:
            if ranges_overlap(current, other):
                raise RuntimeError(f"v6 patch ranges overlap: {name} and {other_name}")


def restore_v4_target(data: bytes) -> bytes:
    restored = bytearray(data)
    actual_uuid, uuid_offset = v4.v3.macho_uuid_location(data)
    if actual_uuid != TARGET_MACHO_UUID:
        raise RuntimeError("v6 Mach-O UUID marker is missing")
    restored[uuid_offset : uuid_offset + 16] = uuid.UUID(v4.TARGET_MACHO_UUID).bytes
    for item in INCREMENTAL_CODE_PATCHES:
        end = item.offset + len(item.target)
        if restored[item.offset:end] != item.target:
            raise RuntimeError(f"v6 patch bytes changed: {item.name}")
        restored[item.offset:end] = item.source
    return bytes(restored)


def verify_target_contract(data: bytes) -> None:
    verify_patch_layout()
    v4.verify_target_contract(restore_v4_target(data))

    helper = data[TYPE_GATE_OFFSET : TYPE_GATE_OFFSET + len(TYPE_GATE_TARGET)]
    if helper != TYPE_GATE_TARGET:
        raise RuntimeError("v6 concrete-type gate bytes changed")

    failure_va = TYPE_GATE_VA + 0x50
    for offset in (0x08, 0x18, 0x28, 0x30):
        target = decode_cbz_family_target(
            helper[offset : offset + 4], TYPE_GATE_VA + offset
        )
        if target != failure_va:
            raise RuntimeError(f"v6 type-gate null branch misses failure: {offset:#x}")
    if decode_b_cond_target(helper[0x44:0x48], TYPE_GATE_VA + 0x44) != failure_va:
        raise RuntimeError("v6 type-gate implementation mismatch misses failure")

    is_link, target = v4.v3.decode_branch_target(
        helper[0x24:0x28], TYPE_GATE_VA + 0x24
    )
    if not is_link or target != INTERFACE_RESOLVER_VA:
        raise RuntimeError("v6 type gate does not call the official interface resolver")
    is_link, target = v4.v3.decode_branch_target(
        helper[0x4C:0x50], TYPE_GATE_VA + 0x4C
    )
    if is_link or target != TYPE_GATE_VA + 0x54:
        raise RuntimeError("v6 type-gate success does not restore its stack frame")

    is_link, target = v4.v3.decode_branch_target(
        data[
            WRAPPER_TYPE_GATE_CALL_OFFSET : WRAPPER_TYPE_GATE_CALL_OFFSET + 4
        ],
        v4.v3.IMAGE_BASE + WRAPPER_TYPE_GATE_CALL_OFFSET,
    )
    if not is_link or target != TYPE_GATE_VA:
        raise RuntimeError("wrapper does not link to the v6 concrete-type gate")

    tags_instruction = data[
        WRAPPER_CHARACTER_TAGS_LOAD_OFFSET : WRAPPER_CHARACTER_TAGS_LOAD_OFFSET + 4
    ]
    if (
        decode_ldr_x_unsigned_offset(tags_instruction, 24, 27)
        != SOURCE_CHARACTER_TAGS_OFFSET
    ):
        raise RuntimeError("wrapper does not load characterTags from source+0xc8")

    main_id_instruction = data[
        WRAPPER_MAIN_CHARACTER_ID_LOAD_OFFSET : WRAPPER_MAIN_CHARACTER_ID_LOAD_OFFSET
        + 4
    ]
    if (
        decode_ldr_x_unsigned_offset(main_id_instruction, 2, 27)
        != SOURCE_MAIN_CHARACTER_STRING_ID_OFFSET
    ):
        raise RuntimeError(
            "wrapper does not load mainCharacterStringId from source+0xb0"
        )

    if v4.v3.macho_uuid(data) != TARGET_MACHO_UUID:
        raise RuntimeError("v6 Mach-O UUID marker is missing")


def apply_patch(source: bytes) -> tuple[bytes, list[dict[str, object]]]:
    v4_target, v4_reports = v4.apply_patch(source)
    v4.verify_target_contract(v4_target)
    verify_patch_layout()

    actual_uuid, uuid_offset = v4.v3.macho_uuid_location(v4_target)
    if actual_uuid != v4.TARGET_MACHO_UUID:
        raise RuntimeError("v4 intermediate Mach-O UUID marker is missing")
    patches = INCREMENTAL_CODE_PATCHES + (
        IncrementalPatch(
            name="MachO.v6AcceptedBuildUuidMarker",
            offset=uuid_offset,
            source=uuid.UUID(v4.TARGET_MACHO_UUID).bytes,
            target=uuid.UUID(TARGET_MACHO_UUID).bytes,
            purpose="give v6 a distinct LC_UUID so a later IPS proves which binary ran",
        ),
    )

    patched = bytearray(v4_target)
    reports = list(v4_reports)
    allowed_offsets: set[int] = set()
    for item in patches:
        end = item.offset + len(item.source)
        if len(item.source) != len(item.target):
            raise RuntimeError(f"{item.name} is not an in-place patch")
        actual = v4_target[item.offset:end]
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
        for index, (before, after) in enumerate(zip(v4_target, target))
        if before != after and index not in allowed_offsets
    ]
    if unexpected:
        raise RuntimeError(f"unexpected v6 Mach-O change at {unexpected[0]:#x}")
    verify_target_contract(target)
    return target, reports


def build_target_plist(source: bytes) -> bytes:
    descriptor = plistlib.loads(source)
    if descriptor.get("CFBundleIdentifier") != v4.v3.EXPECTED_BUNDLE_ID:
        raise RuntimeError("source CFBundleIdentifier mismatch")
    if descriptor.get("CFBundleShortVersionString") != v4.v3.EXPECTED_SHORT_VERSION:
        raise RuntimeError("source CFBundleShortVersionString mismatch")
    if descriptor.get("CFBundleVersion") != v4.v3.EXPECTED_SOURCE_BUILD:
        raise RuntimeError("source CFBundleVersion mismatch")
    descriptor["CFBundleVersion"] = TARGET_BUILD
    output_format = (
        plistlib.FMT_BINARY if source.startswith(b"bplist00") else plistlib.FMT_XML
    )
    return plistlib.dumps(descriptor, fmt=output_format, sort_keys=False)


def verify_plist_contract(source: bytes, target: bytes) -> None:
    before = plistlib.loads(source)
    after = plistlib.loads(target)
    expected = copy.deepcopy(before)
    expected["CFBundleVersion"] = TARGET_BUILD
    if after != expected:
        raise RuntimeError("Info.plist changed outside CFBundleVersion")
    if after.get("CFBundleVersion") != TARGET_BUILD:
        raise RuntimeError("v6 build marker is missing")


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
        if [info.filename for info in output_infos] != [
            info.filename for info in source_infos
        ]:
            raise RuntimeError("output IPA member order or names changed")
        if output_zip.comment != source_zip.comment:
            raise RuntimeError("output IPA ZIP comment changed")
        for source_info, output_info in zip(source_infos, output_infos):
            if v4.v3.zipinfo_signature(source_info) != v4.v3.zipinfo_signature(
                output_info
            ):
                raise RuntimeError(f"ZIP metadata changed for {source_info.filename}")
            output_data = output_zip.read(output_info)
            if source_info.filename == v4.v3.MACHO_MEMBER:
                if output_data != target_macho:
                    raise RuntimeError("output IPA Mach-O readback mismatch")
            elif source_info.filename == v4.v3.INFO_PLIST_MEMBER:
                if output_data != target_plist:
                    raise RuntimeError("output IPA Info.plist readback mismatch")
            elif output_data != source_zip.read(source_info):
                raise RuntimeError(
                    f"unexpected IPA member content change: {source_info.filename}"
                )

        verify_target_contract(output_zip.read(v4.v3.MACHO_MEMBER))
        verify_plist_contract(
            source_zip.read(v4.v3.INFO_PLIST_MEMBER),
            output_zip.read(v4.v3.INFO_PLIST_MEMBER),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the v4 MemberView-protected IPA plus the v6 verified "
            "MemberImpl type/layout gate while retaining the existing MOD wrapper."
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
        args.report.resolve()
        if args.report is not None
        else output_path.with_suffix(".json")
    )
    if not source_path.is_file():
        raise SystemExit(f"source IPA does not exist: {source_path}")
    if output_path.exists():
        raise SystemExit(f"refusing to overwrite output IPA: {output_path}")
    if report_path.exists():
        raise SystemExit(f"refusing to overwrite report: {report_path}")
    if source_path == output_path:
        raise SystemExit("source and output IPA must be different files")

    source_ipa_hash = v4.v3.sha256_file(source_path)
    if source_ipa_hash != v4.v3.EXPECTED_SOURCE_IPA_SHA256:
        raise SystemExit(
            f"source IPA hash mismatch: {source_ipa_hash} != "
            f"{v4.v3.EXPECTED_SOURCE_IPA_SHA256}"
        )
    with zipfile.ZipFile(source_path, "r") as source_zip:
        names = source_zip.namelist()
        if names.count(v4.v3.MACHO_MEMBER) != 1:
            raise SystemExit(f"expected exactly one {v4.v3.MACHO_MEMBER} member")
        if names.count(v4.v3.INFO_PLIST_MEMBER) != 1:
            raise SystemExit(f"expected exactly one {v4.v3.INFO_PLIST_MEMBER} member")
        source_macho = source_zip.read(v4.v3.MACHO_MEMBER)
        source_plist = source_zip.read(v4.v3.INFO_PLIST_MEMBER)

    target_macho, patch_reports = apply_patch(source_macho)
    target_plist = build_target_plist(source_plist)
    verify_plist_contract(source_plist, target_plist)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    v4.v3.write_output(source_path, output_path, target_macho, target_plist)
    verify_output(source_path, output_path, target_macho, target_plist)
    output_ipa_hash = v4.v3.sha256_file(output_path)
    if output_ipa_hash != ACCEPTED_OUTPUT_IPA_SHA256:
        raise SystemExit(
            f"output IPA hash mismatch: {output_ipa_hash} != "
            f"{ACCEPTED_OUTPUT_IPA_SHA256}"
        )

    report = {
        "schemaVersion": 6,
        "status": "device_validated_unsigned_payload",
        "purpose": (
            "MemberView.draw stabilization with the retained MOD wrapper, an "
            "official interface-resolution type gate, verified source-field "
            "offsets, and official draw fallback"
        ),
        "sourceIpa": str(source_path),
        "sourceIpaSha256": source_ipa_hash,
        "outputIpa": str(output_path),
        "outputIpaSha256": output_ipa_hash,
        "sourceMachoSha256": v4.v3.sha256_bytes(source_macho),
        "outputMachoSha256": v4.v3.sha256_bytes(target_macho),
        "sourceMachoUuid": v4.v3.EXPECTED_SOURCE_MACHO_UUID,
        "outputMachoUuid": v4.v3.macho_uuid(target_macho),
        "bundleIdentifier": v4.v3.EXPECTED_BUNDLE_ID,
        "shortVersion": v4.v3.EXPECTED_SHORT_VERSION,
        "sourceBuild": v4.v3.EXPECTED_SOURCE_BUILD,
        "outputBuild": TARGET_BUILD,
        "deviceValidation": {
            "status": "passed",
            "evidence": "user-confirmed iOS device acceptance",
            "acceptedIpaSha256": ACCEPTED_OUTPUT_IPA_SHA256,
        },
        "observedV5Crash": {
            "ipsBuild": "1.8.45",
            "ipsMachoUuid": "aebb8a31-a995-5526-9217-37bee03da380",
            "faultAddress": "0x6d0",
            "registerX8": "0x658",
            "faultingRead": "[x8+0x78]",
            "diagnosis": (
                "v5 treated SquadMemberSource.atk at source+0x48 as a metadata "
                "pointer; atk was 1624 (0x658), so the subsequent +0x78 read "
                "faulted at 0x6d0"
            ),
        },
        "verifiedEvidence": {
            "officialAndroidApkSha256": (
                "1adba913eb662bc21d5623b797c82c1df82ffe4120920384949e730335b3540e"
            ),
            "officialMainSwfSha256": (
                "0c4cb4aa35d78234dc998df613869aef4830fe7de30306a54e6dfc41375c215f"
            ),
            "iosAotAbcSha1": "a6396dfd3fee07083d4e139caac5216738cdcce2",
            "interfaceDescriptorTableOffset": hex(
                MEMBER_PEEK_GET_CHARACTER_ANIMATION_DESCRIPTOR_OFFSET
            ),
            "interfaceResolver": hex(INTERFACE_RESOLVER_VA),
            "requiredImplementation": hex(MEMBER_IMPL_GET_CHARACTER_ANIMATION_VA),
            "memberImplSourceOffset": hex(MEMBER_IMPL_SOURCE_OFFSET),
            "sourceCharacterTagsOffset": hex(SOURCE_CHARACTER_TAGS_OFFSET),
            "sourceMainCharacterStringIdOffset": hex(
                SOURCE_MAIN_CHARACTER_STRING_ID_OFFSET
            ),
            "sourcePixelArtAnimationPathOffset": "0xa0 (retained)",
            "arrayIndexOfAbi": "x0=Array, x1=string Atom, w2=6, x3=MethodEnv",
        },
        "routing": {
            "constructorSlotRepairDispatcher": hex(v4.v3.SLOT_REPAIR_DISPATCH_VA),
            "retainedWrapper": hex(v4.v3.SERIS_WRAPPER_VA),
            "verifiedTypeGate": hex(TYPE_GATE_VA),
            "officialInterfaceResolver": hex(INTERFACE_RESOLVER_VA),
            "typeOrLayoutFailure": hex(v4.WRAPPER_CLEANUP_VA),
            "officialContinuation": hex(v4.v3.ORIGINAL_DRAW_VA),
        },
        "removedV5Path": (
            "source+0x48 -> alleged metadata+0x78 character identity"
        ),
        "modCompatibility": {
            "serisDualFormWrapper": (
                "preserved after exact MemberImpl implementation and layout proof"
            ),
            "modDualFormTagGate": (
                "preserved with verified characterTags+0xc8 and official indexOf ABI"
            ),
            "renderScale": "unchanged",
            "fantasySoulAsyncTexture": "unchanged",
            "otherFiveInOnePatches": "unchanged",
        },
        "codeCaveLayout": {
            "fantasySoulCave": [
                hex(v4.v3.FANTASY_SOUL_CAVE_START),
                hex(v4.v3.FANTASY_SOUL_CAVE_END),
            ],
            "v3DispatcherRange": [
                hex(v4.v3.SLOT_REPAIR_DISPATCH_OFFSET),
                hex(
                    v4.v3.SLOT_REPAIR_DISPATCH_OFFSET
                    + len(v4.v3.SLOT_REPAIR_DISPATCH_TARGET)
                ),
            ],
            "v4NullGuardRange": [
                hex(v4.WRAPPER_GUARD_OFFSET),
                hex(v4.WRAPPER_GUARD_OFFSET + len(v4.WRAPPER_GUARD_TARGET)),
            ],
            "v6VerifiedTypeGateRange": [
                hex(TYPE_GATE_OFFSET),
                hex(TYPE_GATE_OFFSET + len(TYPE_GATE_TARGET)),
            ],
            "fiveInOneProtectedRange": [
                hex(v4.v3.FIVE_IN_ONE_CAVE_START),
                hex(v4.v3.FIVE_IN_ONE_USED_END),
            ],
        },
        "patches": patch_reports,
        "verification": [
            "all v4 source, layout, slot repair, null-call guard, AOT table, and MOD preservation contracts",
            "official MemberPeek.getCharacterAnimation descriptor lookup and resolver BL target",
            "exact MemberImpl.getCharacterAnimation implementation-address comparison",
            "all type-gate null and implementation-mismatch branches enter fail-closed return",
            "wrapper reads MemberImpl.source only after the concrete implementation proof",
            "verified characterTags+0xc8 and mainCharacterStringId+0xb0 LDR encodings",
            "normal pixelArtAnimationPath+0xa0 path, matchCondition proof, and Array.indexOf ABI retained",
            "v5 source+0x48 identity path absent",
            "only declared v6 Mach-O ranges changed after the verified v4 transform",
            "distinct CFBundleVersion and LC_UUID diagnostic markers",
            "all other Info.plist values unchanged",
            "all other IPA members and ZIP metadata unchanged",
            "output IPA full readback",
            "output IPA matches the device-validated SHA-256",
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
    print(
        "status: accepted device-validated payload reproduced; "
        "output is unsigned and requires signing"
    )


if __name__ == "__main__":
    main()
