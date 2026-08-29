from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import plistlib
import struct
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
EXPECTED_MACHO_UUID = "4c4c4408-5555-3144-a151-6203e95defe1"

IMAGE_BASE = 0x100000000
ORIGINAL_DRAW_OFFSET = 0x2B990D4
ORIGINAL_DRAW_VA = IMAGE_BASE + ORIGINAL_DRAW_OFFSET
ORIGINAL_DRAW_FIRST_INSTRUCTION = bytes.fromhex("eb2bb96d")

CONSTRUCTOR_DRAW_CALL_OFFSET = 0x2B9C084
CONSTRUCTOR_DRAW_RETURN_OFFSET = 0x2B9C088

SERIS_WRAPPER_OFFSET = 0x3D69180
SERIS_WRAPPER_VA = IMAGE_BASE + SERIS_WRAPPER_OFFSET
SERIS_WRAPPER_TAIL_OFFSET = 0x3D694C0
SERIS_WRAPPER_TAIL_VA = IMAGE_BASE + SERIS_WRAPPER_TAIL_OFFSET
SAFE_DISPATCH_OFFSET = 0x3D694C8
SAFE_DISPATCH_VA = IMAGE_BASE + SAFE_DISPATCH_OFFSET
EXPECTED_WRAPPER_SHA256 = (
    "bd66305e468fc193790d1c0f47e8fc514bb0376786362d9b2a6e4d2a8a97f11a"
)

DRAW_METHOD_TABLE_OFFSET = 0x6341BA8


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


def encode_cbnz_x8(source_va: int, target_va: int) -> bytes:
    delta = target_va - source_va
    if delta % 4:
        raise ValueError("ARM64 CBNZ target is not instruction-aligned")
    immediate = delta // 4
    if not -(1 << 18) <= immediate < (1 << 18):
        raise ValueError("ARM64 CBNZ target is outside the 19-bit range")
    return struct.pack("<I", 0xB5000000 | ((immediate & 0x7FFFF) << 5) | 8)


def decode_branch_target(instruction: bytes, source_va: int) -> tuple[bool, int]:
    word = struct.unpack("<I", instruction)[0]
    opcode = word & 0xFC000000
    if opcode not in (0x14000000, 0x94000000):
        raise ValueError(f"not an ARM64 B/BL instruction: {word:#x}")
    immediate = word & 0x03FFFFFF
    if immediate & (1 << 25):
        immediate -= 1 << 26
    return opcode == 0x94000000, source_va + immediate * 4


def decode_cbnz_target(instruction: bytes, source_va: int) -> int:
    word = struct.unpack("<I", instruction)[0]
    if word & 0xFF00001F != 0xB5000008:
        raise ValueError(f"not the expected ARM64 CBNZ X8 instruction: {word:#x}")
    immediate = (word >> 5) & 0x7FFFF
    if immediate & (1 << 18):
        immediate -= 1 << 19
    return source_va + immediate * 4


BR_X8 = struct.pack("<I", 0xD61F0100)


@dataclass(frozen=True)
class BinaryPatch:
    name: str
    offset: int
    source: bytes
    target: bytes
    purpose: str


DRAW_ENTRY_TARGET = encode_branch(ORIGINAL_DRAW_VA, SERIS_WRAPPER_VA)
CONSTRUCTOR_DRAW_CALL_TARGET = encode_branch(
    IMAGE_BASE + CONSTRUCTOR_DRAW_CALL_OFFSET,
    SAFE_DISPATCH_VA,
    link=True,
)
WRAPPER_TAIL_AND_GUARD_TARGET = b"".join(
    (
        ORIGINAL_DRAW_FIRST_INSTRUCTION,
        encode_branch(SERIS_WRAPPER_TAIL_VA + 4, ORIGINAL_DRAW_VA + 4),
        encode_cbnz_x8(SAFE_DISPATCH_VA, SAFE_DISPATCH_VA + 8),
        encode_branch(SAFE_DISPATCH_VA + 4, ORIGINAL_DRAW_VA),
        BR_X8,
    )
)
METHOD_TABLE_TARGET = struct.pack("<Q", ORIGINAL_DRAW_VA)


PATCHES = (
    BinaryPatch(
        name="MemberView.draw.officialEntryRouter",
        offset=ORIGINAL_DRAW_OFFSET,
        source=ORIGINAL_DRAW_FIRST_INSTRUCTION,
        target=DRAW_ENTRY_TARGET,
        purpose="route the official AOT entry through the retained Seris wrapper",
    ),
    BinaryPatch(
        name="MemberView.constructor.safeDrawDispatch",
        offset=CONSTRUCTOR_DRAW_CALL_OFFSET,
        source=bytes.fromhex("00013fd6"),
        target=CONSTRUCTOR_DRAW_CALL_TARGET,
        purpose="guard the observed BLR X8 crash site and fall back to the official entry",
    ),
    BinaryPatch(
        name="MemberView.draw.wrapperTailAndNullGuard",
        offset=SERIS_WRAPPER_TAIL_OFFSET,
        source=bytes.fromhex(
            "05bfb817210d0a8be00308aa88f73297ff030bd1"
        ),
        target=WRAPPER_TAIL_AND_GUARD_TARGET,
        purpose="replay the displaced stock prologue, continue at draw+4, and host the safe dispatcher",
    ),
    BinaryPatch(
        name="MemberView.draw.restoreAotMethodTable",
        offset=DRAW_METHOD_TABLE_OFFSET,
        source=struct.pack("<Q", SERIS_WRAPPER_VA),
        target=METHOD_TABLE_TARGET,
        purpose="restore the stock AOT method-table target so runtime MethodInfo initialization stays canonical",
    ),
)


def macho_uuid(data: bytes) -> str:
    if len(data) < 32 or struct.unpack_from("<I", data, 0)[0] != 0xFEEDFACF:
        raise RuntimeError("expected a thin little-endian ARM64 Mach-O")
    command_count = struct.unpack_from("<I", data, 16)[0]
    cursor = 32
    for _ in range(command_count):
        command, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or cursor + size > len(data):
            raise RuntimeError("invalid Mach-O load command")
        if command == 0x1B:
            raw = data[cursor + 8 : cursor + 24].hex()
            return (
                f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-"
                f"{raw[16:20]}-{raw[20:]}"
            )
        cursor += size
    raise RuntimeError("Mach-O has no LC_UUID")


def verify_instruction_contract(data: bytes) -> None:
    is_link, target = decode_branch_target(
        data[ORIGINAL_DRAW_OFFSET : ORIGINAL_DRAW_OFFSET + 4],
        ORIGINAL_DRAW_VA,
    )
    if is_link or target != SERIS_WRAPPER_VA:
        raise RuntimeError("official draw entry does not branch to the retained wrapper")

    is_link, target = decode_branch_target(
        data[CONSTRUCTOR_DRAW_CALL_OFFSET : CONSTRUCTOR_DRAW_CALL_OFFSET + 4],
        IMAGE_BASE + CONSTRUCTOR_DRAW_CALL_OFFSET,
    )
    if not is_link or target != SAFE_DISPATCH_VA:
        raise RuntimeError("constructor draw call does not link to the safe dispatcher")

    if (
        data[SERIS_WRAPPER_TAIL_OFFSET : SERIS_WRAPPER_TAIL_OFFSET + 4]
        != ORIGINAL_DRAW_FIRST_INSTRUCTION
    ):
        raise RuntimeError("wrapper tail does not replay the displaced stock prologue")

    is_link, target = decode_branch_target(
        data[SERIS_WRAPPER_TAIL_OFFSET + 4 : SERIS_WRAPPER_TAIL_OFFSET + 8],
        SERIS_WRAPPER_TAIL_VA + 4,
    )
    if is_link or target != ORIGINAL_DRAW_VA + 4:
        raise RuntimeError("wrapper tail does not continue at stock draw+4")

    if (
        decode_cbnz_target(
            data[SAFE_DISPATCH_OFFSET : SAFE_DISPATCH_OFFSET + 4],
            SAFE_DISPATCH_VA,
        )
        != SAFE_DISPATCH_VA + 8
    ):
        raise RuntimeError("safe dispatcher non-null branch is invalid")

    is_link, target = decode_branch_target(
        data[SAFE_DISPATCH_OFFSET + 4 : SAFE_DISPATCH_OFFSET + 8],
        SAFE_DISPATCH_VA + 4,
    )
    if is_link or target != ORIGINAL_DRAW_VA:
        raise RuntimeError("safe dispatcher null fallback does not use the official entry")
    if data[SAFE_DISPATCH_OFFSET + 8 : SAFE_DISPATCH_OFFSET + 12] != BR_X8:
        raise RuntimeError("safe dispatcher normal path is not BR X8")

    method_target = struct.unpack_from("<Q", data, DRAW_METHOD_TABLE_OFFSET)[0]
    if method_target != ORIGINAL_DRAW_VA:
        raise RuntimeError("MemberView.draw AOT method-table entry is not stock")


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
    actual_uuid = macho_uuid(source)
    if actual_uuid != EXPECTED_MACHO_UUID:
        raise RuntimeError(
            f"source Mach-O UUID mismatch: {actual_uuid} != {EXPECTED_MACHO_UUID}"
        )
    wrapper_hash = sha256_bytes(
        source[SERIS_WRAPPER_OFFSET : SERIS_WRAPPER_TAIL_OFFSET + 4]
    )
    if wrapper_hash != EXPECTED_WRAPPER_SHA256:
        raise RuntimeError(
            f"Seris wrapper hash mismatch: {wrapper_hash} != {EXPECTED_WRAPPER_SHA256}"
        )

    patched = bytearray(source)
    reports: list[dict[str, object]] = []
    allowed_offsets: set[int] = set()
    for item in PATCHES:
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
    for item in PATCHES:
        end = item.offset + len(item.target)
        if target[item.offset:end] != item.target:
            raise RuntimeError(f"{item.name} target verification failed")
    if macho_uuid(target) != EXPECTED_MACHO_UUID:
        raise RuntimeError("patch unexpectedly changed the Mach-O UUID")
    verify_instruction_contract(target)
    return target, reports


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
                data = (
                    patched_macho
                    if source_info.filename == MACHO_MEMBER
                    else source_zip.read(source_info)
                )
                output_zip.writestr(copy.copy(source_info), data)
        os.replace(temporary, output_path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def verify_output(source_path: Path, output_path: Path, target_macho: bytes) -> None:
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
            if zipinfo_signature(source_info) != zipinfo_signature(output_info):
                raise RuntimeError(
                    f"ZIP metadata changed for {source_info.filename}"
                )
            output_data = output_zip.read(output_info)
            if source_info.filename == MACHO_MEMBER:
                if output_data != target_macho:
                    raise RuntimeError("output IPA Mach-O readback mismatch")
            elif output_data != source_zip.read(source_info):
                raise RuntimeError(
                    f"unexpected IPA member content change: {source_info.filename}"
                )

        descriptor = plistlib.loads(output_zip.read(INFO_PLIST_MEMBER))
        if descriptor.get("CFBundleIdentifier") != "com.kulo.wf":
            raise RuntimeError("CFBundleIdentifier changed unexpectedly")
        verify_instruction_contract(output_zip.read(MACHO_MEMBER))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Patch the vetted iOS final IPA so MemberView.draw uses the stock AOT "
            "method-table entry, an official-entry router, and a null-safe constructor dispatch."
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

    source_ipa_hash = sha256_file(source_path)
    if source_ipa_hash != EXPECTED_SOURCE_IPA_SHA256:
        raise SystemExit(
            f"source IPA hash mismatch: {source_ipa_hash} != {EXPECTED_SOURCE_IPA_SHA256}"
        )

    with zipfile.ZipFile(source_path, "r") as source_zip:
        names = source_zip.namelist()
        if names.count(MACHO_MEMBER) != 1:
            raise SystemExit(f"expected exactly one {MACHO_MEMBER} member")
        source_macho = source_zip.read(MACHO_MEMBER)

    target_macho, patch_reports = apply_patch(source_macho)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_output(source_path, output_path, target_macho)
    verify_output(source_path, output_path, target_macho)

    report = {
        "schemaVersion": 1,
        "status": "unsigned_device_test_required",
        "purpose": "MemberView.draw official-entry router with retained MOD wrapper and null fallback",
        "sourceIpa": str(source_path),
        "sourceIpaSha256": source_ipa_hash,
        "outputIpa": str(output_path),
        "outputIpaSha256": sha256_file(output_path),
        "sourceMachoSha256": sha256_bytes(source_macho),
        "outputMachoSha256": sha256_bytes(target_macho),
        "machoUuid": macho_uuid(target_macho),
        "observedCrash": {
            "callOffset": hex(CONSTRUCTOR_DRAW_CALL_OFFSET),
            "returnOffset": hex(CONSTRUCTOR_DRAW_RETURN_OFFSET),
            "fault": "BLR X8 with X8 == 0",
        },
        "routing": {
            "methodTableTarget": hex(ORIGINAL_DRAW_VA),
            "officialEntry": hex(ORIGINAL_DRAW_VA),
            "retainedWrapper": hex(SERIS_WRAPPER_VA),
            "stockContinuation": hex(ORIGINAL_DRAW_VA + 4),
            "safeDispatcher": hex(SAFE_DISPATCH_VA),
            "normalPath": "BR X8",
            "nullPath": "official MemberView.draw entry -> retained wrapper -> stock draw body",
        },
        "modCompatibility": {
            "serisDualFormWrapper": "preserved",
            "renderScale": "unchanged",
            "fantasySoulAsyncTexture": "unchanged",
            "otherFiveInOnePatches": "unchanged",
        },
        "patches": patch_reports,
        "verification": [
            "exact input IPA/Mach-O hash and LC_UUID",
            "exact source bytes and retained Seris wrapper hash",
            "ARM64 branch targets and stock-prologue replay",
            "stock AOT MemberView.draw method-table target",
            "only declared Mach-O ranges changed",
            "all non-Mach-O IPA members and ZIP metadata unchanged",
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
    print(f"report: {report_path}")
    print("status: unsigned; device signing and regression testing are required")


if __name__ == "__main__":
    main()
