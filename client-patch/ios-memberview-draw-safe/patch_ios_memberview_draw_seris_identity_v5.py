from __future__ import annotations

import argparse
import copy
import json
import os
import plistlib
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

import patch_ios_memberview_draw_wrapper_guard_v4 as v4


TARGET_BUILD = "1.8.45"
TARGET_MACHO_UUID = "aebb8a31-a995-5526-9217-37bee03da380"
SERIS_CHARACTER_ID = 129999

# V4 occupies 0x30199d4..0x30199e0.  V5 immediately follows it in the
# fantasy-soul patch's already-sacrificed debug method tail.
SERIS_IDENTITY_GATE_OFFSET = 0x30199E0
SERIS_IDENTITY_GATE_VA = v4.v3.IMAGE_BASE + SERIS_IDENTITY_GATE_OFFSET
SERIS_IDENTITY_GATE_SOURCE = bytes.fromhex(
    "015d40f9280840f9082940f900013fd61f0400718b500154d500a0527b00a052"
    "3c00a052f8031f2a15699a721bed8c721c7c9b72e0a30191e103182ae20317aa"
    "9c356897"
)

# The assembled gate performs these operations without calling through AIR:
#   - require x27 and x27+0x48 to be canonical, 8-byte-aligned pointers;
#   - read character identity from [x27+0x48]+0x78;
#   - continue the Seris wrapper only for character 129999;
#   - otherwise enter the wrapper's existing cleanup and official draw.
SERIS_IDENTITY_GATE_TARGET = bytes.fromhex(
    "69ff70d3"  # lsr x9, x27, #48
    "e90100b5"  # cbnz x9, fallback
    "7f0b40f2"  # tst x27, #7
    "a1010054"  # b.ne fallback
    "682740f9"  # ldr x8, [x27, #0x48]
    "680100b4"  # cbz x8, fallback
    "09fd70d3"  # lsr x9, x8, #48
    "290100b5"  # cbnz x9, fallback
    "1f0940f2"  # tst x8, #7
    "e1000054"  # b.ne fallback
    "097940b9"  # ldr w9, [x8, #0x78]
    "e8799f52"  # mov w8, #0xfbcf
    "2800a072"  # movk w8, #1, lsl #16
    "3f01086b"  # cmp w9, w8
    "41000054"  # b.ne fallback
    "423e3514"  # b Seris continuation
    "9b3e3514"  # fallback: b wrapper cleanup
)

WRAPPER_TAG_GATE_REDIRECT_OFFSET = 0x3D691E0
WRAPPER_TAG_GATE_REDIRECT_SOURCE = bytes.fromhex("788340f9")
SERIS_CONTINUATION_OFFSET = 0x3D69324
SERIS_CONTINUATION_VA = v4.v3.IMAGE_BASE + SERIS_CONTINUATION_OFFSET
EXPECTED_SERIS_CONTINUATION_HEAD = bytes.fromhex(
    "e0031faac1028052e20314aa4f4d3094e10300aae80a40f902fd40f9620a00b4"
    "480840f9082940f90971ffd0299129911f0109eba1090054e00317aa00013fd6"
    "fa03002a785240f9794e40f9"
)


@dataclass(frozen=True)
class IncrementalPatch:
    name: str
    offset: int
    source: bytes
    target: bytes
    purpose: str


WRAPPER_TAG_GATE_REDIRECT_TARGET = v4.v3.encode_branch(
    v4.v3.IMAGE_BASE + WRAPPER_TAG_GATE_REDIRECT_OFFSET,
    SERIS_IDENTITY_GATE_VA,
    link=True,
)

INCREMENTAL_CODE_PATCHES = (
    IncrementalPatch(
        name="SerisWrapper.characterIdentityGate",
        offset=SERIS_IDENTITY_GATE_OFFSET,
        source=SERIS_IDENTITY_GATE_SOURCE,
        target=SERIS_IDENTITY_GATE_TARGET,
        purpose=(
            "validate canonical aligned character metadata and require identity "
            "129999 before entering any Seris-only dynamic draw logic"
        ),
    ),
    IncrementalPatch(
        name="SerisWrapper.replaceGenericTagGate",
        offset=WRAPPER_TAG_GATE_REDIRECT_OFFSET,
        source=WRAPPER_TAG_GATE_REDIRECT_SOURCE,
        target=WRAPPER_TAG_GATE_REDIRECT_TARGET,
        purpose=(
            "replace the broad characterTags/indexOf path with the native Seris "
            "identity gate; non-Seris MemberViews go directly to official draw"
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


def verify_patch_layout() -> None:
    v4.verify_patch_layout()
    gate_range = (
        SERIS_IDENTITY_GATE_OFFSET,
        SERIS_IDENTITY_GATE_OFFSET + len(SERIS_IDENTITY_GATE_TARGET),
    )
    v4_guard_end = v4.WRAPPER_GUARD_OFFSET + len(v4.WRAPPER_GUARD_TARGET)
    if gate_range[0] != v4_guard_end:
        raise RuntimeError("v5 identity gate is not immediately after the v4 guard")
    if not (
        v4.v3.FANTASY_SOUL_CAVE_START <= gate_range[0]
        and gate_range[1] <= v4.v3.FANTASY_SOUL_CAVE_END
    ):
        raise RuntimeError("v5 identity gate exceeds the fantasy-soul reserved cave")

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
        if ranges_overlap(gate_range, protected):
            raise RuntimeError(f"v5 identity gate overlaps {name}")

    redirect_range = (
        WRAPPER_TAG_GATE_REDIRECT_OFFSET,
        WRAPPER_TAG_GATE_REDIRECT_OFFSET + 4,
    )
    wrapper_range = (
        v4.v3.SERIS_WRAPPER_OFFSET,
        v4.v3.SERIS_WRAPPER_TAIL_OFFSET,
    )
    if not (
        wrapper_range[0] <= redirect_range[0]
        and redirect_range[1] <= wrapper_range[1]
    ):
        raise RuntimeError("v5 identity redirect is outside the retained wrapper")

    patch_ranges = [
        (item.name, (item.offset, item.offset + len(item.target)))
        for item in INCREMENTAL_CODE_PATCHES
    ]
    for index, (name, current) in enumerate(patch_ranges):
        for other_name, other in patch_ranges[index + 1 :]:
            if ranges_overlap(current, other):
                raise RuntimeError(f"v5 patch ranges overlap: {name} and {other_name}")


def restore_v4_target(data: bytes) -> bytes:
    restored = bytearray(data)
    actual_uuid, uuid_offset = v4.v3.macho_uuid_location(data)
    if actual_uuid != TARGET_MACHO_UUID:
        raise RuntimeError("v5 Mach-O UUID marker is missing")
    restored[uuid_offset : uuid_offset + 16] = uuid.UUID(v4.TARGET_MACHO_UUID).bytes
    for item in INCREMENTAL_CODE_PATCHES:
        end = item.offset + len(item.target)
        if restored[item.offset:end] != item.target:
            raise RuntimeError(f"v5 patch bytes changed: {item.name}")
        restored[item.offset:end] = item.source
    return bytes(restored)


def verify_target_contract(data: bytes) -> None:
    verify_patch_layout()
    v4.verify_target_contract(restore_v4_target(data))

    gate = data[
        SERIS_IDENTITY_GATE_OFFSET : SERIS_IDENTITY_GATE_OFFSET
        + len(SERIS_IDENTITY_GATE_TARGET)
    ]
    if gate != SERIS_IDENTITY_GATE_TARGET:
        raise RuntimeError("v5 identity gate bytes changed")

    fallback_va = SERIS_IDENTITY_GATE_VA + len(SERIS_IDENTITY_GATE_TARGET) - 4
    conditional_offsets = (4, 12, 20, 28, 36, 56)
    for offset in conditional_offsets:
        instruction = gate[offset : offset + 4]
        source_va = SERIS_IDENTITY_GATE_VA + offset
        if offset in (4, 20, 28):
            target = decode_cbz_family_target(instruction, source_va)
        else:
            target = decode_b_cond_target(instruction, source_va)
        if target != fallback_va:
            raise RuntimeError(
                f"v5 identity-gate failure branch misses fallback: {offset:#x}"
            )

    is_link, target = v4.v3.decode_branch_target(
        gate[60:64], SERIS_IDENTITY_GATE_VA + 60
    )
    if is_link or target != SERIS_CONTINUATION_VA:
        raise RuntimeError("v5 identity success does not enter the Seris continuation")
    is_link, target = v4.v3.decode_branch_target(
        gate[64:68], SERIS_IDENTITY_GATE_VA + 64
    )
    if is_link or target != v4.WRAPPER_CLEANUP_VA:
        raise RuntimeError("v5 identity failure does not enter wrapper cleanup")

    is_link, target = v4.v3.decode_branch_target(
        data[
            WRAPPER_TAG_GATE_REDIRECT_OFFSET : WRAPPER_TAG_GATE_REDIRECT_OFFSET + 4
        ],
        v4.v3.IMAGE_BASE + WRAPPER_TAG_GATE_REDIRECT_OFFSET,
    )
    if not is_link or target != SERIS_IDENTITY_GATE_VA:
        raise RuntimeError("wrapper does not link to the v5 identity gate")

    continuation_head = data[
        SERIS_CONTINUATION_OFFSET : SERIS_CONTINUATION_OFFSET
        + len(EXPECTED_SERIS_CONTINUATION_HEAD)
    ]
    if continuation_head != EXPECTED_SERIS_CONTINUATION_HEAD:
        raise RuntimeError("Seris continuation head changed")
    if v4.v3.macho_uuid(data) != TARGET_MACHO_UUID:
        raise RuntimeError("v5 Mach-O UUID marker is missing")


def apply_patch(source: bytes) -> tuple[bytes, list[dict[str, object]]]:
    v4_target, v4_reports = v4.apply_patch(source)
    v4.verify_target_contract(v4_target)
    verify_patch_layout()

    actual_uuid, uuid_offset = v4.v3.macho_uuid_location(v4_target)
    if actual_uuid != v4.TARGET_MACHO_UUID:
        raise RuntimeError("v4 intermediate Mach-O UUID marker is missing")
    patches = INCREMENTAL_CODE_PATCHES + (
        IncrementalPatch(
            name="MachO.v5TestBuildUuidMarker",
            offset=uuid_offset,
            source=uuid.UUID(v4.TARGET_MACHO_UUID).bytes,
            target=uuid.UUID(TARGET_MACHO_UUID).bytes,
            purpose="give v5 a distinct LC_UUID so a later IPS proves which binary ran",
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
        raise RuntimeError(f"unexpected v5 Mach-O change at {unexpected[0]:#x}")
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
        raise RuntimeError("v5 build marker is missing")


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
            if v4.v3.zipinfo_signature(source_info) != v4.v3.zipinfo_signature(output_info):
                raise RuntimeError(f"ZIP metadata changed for {source_info.filename}")
            output_data = output_zip.read(output_info)
            if source_info.filename == v4.v3.MACHO_MEMBER:
                if output_data != target_macho:
                    raise RuntimeError("output IPA Mach-O readback mismatch")
            elif source_info.filename == v4.v3.INFO_PLIST_MEMBER:
                if output_data != target_plist:
                    raise RuntimeError("output IPA Info.plist readback mismatch")
            elif output_data != source_zip.read(source_info):
                raise RuntimeError(f"unexpected IPA member content change: {source_info.filename}")

        verify_target_contract(output_zip.read(v4.v3.MACHO_MEMBER))
        verify_plist_contract(
            source_zip.read(v4.v3.INFO_PLIST_MEMBER),
            output_zip.read(v4.v3.INFO_PLIST_MEMBER),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Patch the vetted iOS final IPA with the v4 MemberView protections "
            "plus a native Seris identity gate that bypasses generic tag dispatch."
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

    source_ipa_hash = v4.v3.sha256_file(source_path)
    if source_ipa_hash != v4.v3.EXPECTED_SOURCE_IPA_SHA256:
        raise SystemExit(
            f"source IPA hash mismatch: {source_ipa_hash} != {v4.v3.EXPECTED_SOURCE_IPA_SHA256}"
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

    report = {
        "schemaVersion": 5,
        "status": "unsigned_device_test_required",
        "purpose": (
            "MemberView.draw stabilization with a native Seris-only identity gate, "
            "retained MOD wrapper, and official draw fallback"
        ),
        "sourceIpa": str(source_path),
        "sourceIpaSha256": source_ipa_hash,
        "outputIpa": str(output_path),
        "outputIpaSha256": v4.v3.sha256_file(output_path),
        "sourceMachoSha256": v4.v3.sha256_bytes(source_macho),
        "outputMachoSha256": v4.v3.sha256_bytes(target_macho),
        "sourceMachoUuid": v4.v3.EXPECTED_SOURCE_MACHO_UUID,
        "outputMachoUuid": v4.v3.macho_uuid(target_macho),
        "bundleIdentifier": v4.v3.EXPECTED_BUNDLE_ID,
        "shortVersion": v4.v3.EXPECTED_SHORT_VERSION,
        "sourceBuild": v4.v3.EXPECTED_SOURCE_BUILD,
        "outputBuild": TARGET_BUILD,
        "observedV4Crash": {
            "ipsBuild": v4.TARGET_BUILD,
            "ipsMachoUuid": v4.TARGET_MACHO_UUID,
            "wrapperReturnOffset": "0x3d6931c",
            "calleeEntryOffset": "0x1f18058",
            "faultOffset": "0x1f18078",
            "faultInstruction": "LDR X8, [X8, #0x30]",
            "faultPointer": "0x0650000000000000",
            "diagnosis": (
                "the generic characterTags/indexOf VTable slot resolved to a "
                "non-null function whose ABI expected MethodEnv in X1, while the "
                "wrapper supplied a tagged AS3 Atom in X1 and MethodEnv in X3"
            ),
        },
        "routing": {
            "wrapperRedirect": hex(v4.v3.IMAGE_BASE + WRAPPER_TAG_GATE_REDIRECT_OFFSET),
            "nativeIdentityGate": hex(SERIS_IDENTITY_GATE_VA),
            "serisCharacterId": SERIS_CHARACTER_ID,
            "serisContinuation": hex(SERIS_CONTINUATION_VA),
            "nonSerisFallback": hex(v4.WRAPPER_CLEANUP_VA),
            "officialContinuation": hex(v4.v3.ORIGINAL_DRAW_VA),
            "removedRuntimeDependency": "characterTags.indexOf('ModDualForm')",
        },
        "identityChecks": [
            "character logic pointer has zero upper 16 bits",
            "character logic pointer is 8-byte aligned",
            "character metadata pointer is non-null with zero upper 16 bits",
            "character metadata pointer is 8-byte aligned",
            "character identity at metadata+0x78 equals 129999",
        ],
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
            "v5IdentityGateRange": [
                hex(SERIS_IDENTITY_GATE_OFFSET),
                hex(SERIS_IDENTITY_GATE_OFFSET + len(SERIS_IDENTITY_GATE_TARGET)),
            ],
            "fiveInOneProtectedRange": [
                hex(v4.v3.FIVE_IN_ONE_CAVE_START),
                hex(v4.v3.FIVE_IN_ONE_USED_END),
            ],
            "fiveInOnePixelArtTrampoline": "preserved",
        },
        "modCompatibility": {
            "serisDualFormWrapper": (
                "preserved for character 129999; the generic ModDualForm tag gate "
                "is replaced by the server's authoritative Seris identity"
            ),
            "renderScale": "unchanged",
            "fantasySoulAsyncTexture": "unchanged",
            "otherFiveInOnePatches": "unchanged",
            "v4InternalNullGuards": "preserved for later Seris-only dynamic calls",
        },
        "patches": patch_reports,
        "verification": [
            "all v4 source, layout, slot repair, null guards, AOT table, and MOD preservation contracts",
            "exact source bytes for the identity-gate host and wrapper redirect",
            "ARM64 BL, CBZ/CBNZ, B.cond, Seris-success B, and official-fallback B targets",
            "pointer checks precede every v5 identity metadata dereference",
            "non-Seris objects cannot reach the former characterTags/indexOf call",
            "Seris continuation does not consume skipped x24/x28 temporary values before redefining them",
            "identity gate does not overlap fantasy-soul wrappers, v3/v4 blocks, five-in-one trampoline, official draw, or AOT table",
            "only declared v5 Mach-O ranges changed after the verified v4 transform",
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
