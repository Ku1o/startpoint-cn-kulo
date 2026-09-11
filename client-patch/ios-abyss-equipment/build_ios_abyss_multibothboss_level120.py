#!/usr/bin/env python3
"""Build the accepted iOS Multi/BothBoss and level-120 abyss gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Sequence


MACHO_MEMBER = "Payload/worldflipper.app/worldflipper"
INFO_PLIST_MEMBER = "Payload/worldflipper.app/Info.plist"
EXPECTED_BUNDLE_ID = "com.kulo.wf"
EXPECTED_SHORT_VERSION = "1.8.4"
EXPECTED_BUILD = "1.8.46"
EXPECTED_IPA_MEMBER_COUNT = 3568
EXPECTED_SOURCE_IPA_SHA256 = (
    "a6fcf29f4e0dada2967d0a50e4da131473bd1f6ca76e11621bb3f3eb3b8d26b4"
)
EXPECTED_OUTPUT_IPA_SHA256 = (
    "4d54590d445e6aad0f189c6bb21ac896d634cdbb2e0e51c7a856317dc3ef694c"
)
EXPECTED_SOURCE_MACHO_SHA256 = (
    "9e6b567f2461c29fd5624ae5deffdfd3438876df71c7c203202400b6342fc84d"
)
EXPECTED_OUTPUT_MACHO_SHA256 = (
    "7758fd717cb4e38c5eb347677714a03eec55d92307e2e51838335cd7377e76b3"
)
EXPECTED_ANDROID_MERGED_SOURCE_SHA256 = (
    "f844f3a62fd12e32ad8ef62a1cc106b877a9e748a8c77fc44a5bb17cf9be6a97"
)

IMAGE_BASE = 0x100000000
GATE_HOOK_OFFSET = 0x49572FC
GATE_HOOK_VA = IMAGE_BASE + GATE_HOOK_OFFSET
EXPECTED_GATE_HOOK = bytes.fromhex("d948d097")
HELPER_OFFSET = 0x3D69660
HELPER_CAPACITY_END = 0x3D69974
EXPECTED_HELPER_CAPACITY_SHA256 = (
    "5de4bd9698a651c7be2d8e2c16da0db90a2fc82af0fc4516b0fcfe5a279c8f2f"
)
EXPECTED_HELPER_SHA256 = (
    "2ff8901d24ffb14d0c7bfa12e938326ef002059a7fa3791d1ea88164da79172e"
)
EXPECTED_MACHO_UUID = "064f8e49fdd9532f8445439ab9f71e6c"
ABILITY_SOUL_CLASS_CACHE_OFFSET = 0x139C0
EQUIPMENT_CLASS_CACHE_OFFSET = 0x0D8A0
IS_TYPE_ATOM_VA = 0x100A27480
ARRAY_GET_INDEXED_VA = 0x100491220
ATOM_TO_INT_VA = 0x100A27174
GATE_DENY_VA = 0x104957468
# MemberView v6 and five-in-one ranges that must survive byte-identically.
PRESERVED_RANGES = {
    "memberview_verified_gate": (0x30199E0, 0x30199E0 + 92),
    "five_in_one_protected": (0x3D694D0, 0x3D6965C),
    "wet_thunder_hook": (0x1FF7D48, 0x1FF7D48 + 4),
    "wet_thunder_helper": (0x6207F40, 0x6207F40 + 184),
    "old_stage3_helper": (0x62077D0, 0x62077D0 + 316),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_zipinfo(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    clone = zipfile.ZipInfo(info.filename, info.date_time)
    clone.compress_type = info.compress_type
    clone.comment = info.comment
    clone.extra = info.extra
    clone.create_system = info.create_system
    clone.create_version = info.create_version
    clone.extract_version = info.extract_version
    clone.flag_bits = info.flag_bits
    clone.volume = info.volume
    clone.internal_attr = info.internal_attr
    clone.external_attr = info.external_attr
    return clone


def load_assembler(dependency_path: Path | None) -> tuple[object, object, str]:
    if dependency_path is not None:
        dependency_path = dependency_path.resolve()
        if not dependency_path.is_dir():
            raise RuntimeError(f"dependency path does not exist: {dependency_path}")
        sys.path.insert(0, str(dependency_path))
    try:
        from capstone import CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN, Cs
        from keystone import KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, Ks
    except ImportError as exc:
        raise RuntimeError(
            "capstone and keystone-engine are required; install them or pass "
            "--dependency-path"
        ) from exc
    source = str(dependency_path) if dependency_path is not None else "python environment"
    return (
        Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN),
        Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN),
        source,
    )


def disassemble(disassembler: object, code: bytes, va: int) -> list[str]:
    return [
        (
            f"0x{instruction.address:x}: {instruction.mnemonic} "
            f"{instruction.op_str}"
        ).rstrip()
        for instruction in disassembler.disasm(code, va)
    ]


def load_cache_offset(register: str, offset: int) -> list[str]:
    upper = offset & 0xFFFF0000
    lower = offset & 0xFFFF
    lines = [f"mov w9, #{hex(upper)}"]
    if lower:
        lines.append(f"movk w9, #{hex(lower)}")
    lines.append(f"ldr {register}, [x20, x9]")
    return lines

def build_gate_helper()->str:
 lines=[
 'stp x19, x20, [sp, #-0x30]!',
 'stp x21, x30, [sp, #0x10]',
 'mov w21, w0',
 'mov x19, x22',
 'cbz x19, stock_result',
 'ldr x8, [x28, #0x18]',
 'ldr x8, [x8, #0x10]',
 'ldr x20, [x8, #0x30]',
 ]
 lines += load_cache_offset('x9',ABILITY_SOUL_CLASS_CACHE_OFFSET)
 lines += [
 'cbz x9, check_equipment',
 'ldr x9, [x9, #0x20]',
 'cbz x9, check_equipment',
 'add x0, sp, #0x98',
 'add x1, x19, #1',
 'add x2, x9, #1',
 f'bl {hex(IS_TYPE_ATOM_VA)}',
 'cbnz w0, have_soul_ability',
 'check_equipment:',
 ]
 lines += load_cache_offset('x9',EQUIPMENT_CLASS_CACHE_OFFSET)
 lines += [
 'cbz x9, stock_result',
 'ldr x9, [x9, #0x20]',
 'cbz x9, stock_result',
 'add x0, sp, #0x98',
 'add x1, x19, #1',
 'add x2, x9, #1',
 f'bl {hex(IS_TYPE_ATOM_VA)}',
 'cbz w0, stock_result',
 'ldr x19, [x19, #0x40]',
 'cbz x19, stock_result',
 'mov w20, #1',
 'str x19, [sp, #0x20]',
 'b have_soul',
 'have_soul_ability:',
 'mov w20, wzr',
 'have_soul:',
 'ldr w8, [x19, #0x2c]',
 'mov w9, #0x1200',
 'movk w9, #0x7a, lsl #16',
 'add w9, w9, #0x65',
 'cmp w8, w9',
 'b.lt stock_result',
 'add w9, w9, #14',
 'cmp w8, w9',
 'b.gt stock_result',
 # w20 is direct Equipment flag; after deep ID stock result no longer needed.
 'mov w21, w20',
 'ldr x19, [sp, #0x120]',
 'cbz x19, deny_deep',
 'ldr w8, [x19, #0x20]',
 'mov w20, w8',
 'cmp w20, #0',
 'b.eq parse_inner',
 'cmp w20, #1',
 'b.eq parse_inner',
 'b deny_or_exception',
 'parse_inner:',
 'ldr x0, [x19, #0x30]',
 'cbz x0, deny_deep',
 'mov w1, wzr',
 f'bl {hex(ARRAY_GET_INDEXED_VA)}',
 'and x19, x0, #0xfffffffffffffff8',
 'cbz x19, deny_deep',
 'ldr w8, [x19, #0x20]',
 'str w8, [sp, #0x28]',
 'ldr x0, [x19, #0x30]',
 'cbz x0, deny_deep',
 'mov w1, wzr',
 f'bl {hex(ARRAY_GET_INDEXED_VA)}',
 'mov x1, x0',
 f'bl {hex(ATOM_TO_INT_VA)}',
 'ldr w8, [sp, #0x28]',
 'cmp w20, #0',
 'b.eq check_single',
 'cmp w20, #1',
 'b.eq check_multi',
 'b deny_or_exception',
 'check_single:',
 'cmp w8, #8',
 'b.eq check_single_challenge',
 'cmp w8, #10',
 'b.eq check_single_practice',
 'cmp w8, #17',
 'b.eq check_single_rush',
 'b deny_or_exception',
 'check_single_challenge:',
 'mov w9, #2001',
 'cmp w0, w9',
 'b.eq allow_deep',
 'b deny_or_exception',
 'check_single_practice:',
 'cmp w0, #1',
 'b.lt deny_or_exception',
 'cmp w0, #97',
 'b.le allow_deep',
 'b deny_or_exception',
 'check_single_rush:',
 'mov w9, #1000',
 'sdiv w0, w0, w9',
 'mov w9, #0xaec3',
 'movk w9, #0xa, lsl #16',
 'cmp w0, w9',
 'b.eq allow_deep',
 'b deny_or_exception',
 'check_multi:',
 'cmp w8, #4',
 'b.ne deny_or_exception',
 'mov w9, #0xc4f9',
 'movk w9, #0x10c, lsl #16',
 'cmp w0, w9',
 'b.lt deny_or_exception',
 'add w9, w9, #2',
 'cmp w0, w9',
 'b.le allow_deep',
 'b deny_or_exception',
 # The Android merge uses this only after a deep whitelist miss.
 'deny_or_exception:',
 'cbz w21, deny_deep',
 'ldr x8, [x22, #0x38]',
 'cbz x8, deny_deep',
 'ldr w9, [x8, #0x20]',
 'cbnz w9, deny_deep',
 'ldr x0, [x8, #0x30]',
 'cbz x0, deny_deep',
 'mov w1, wzr',
 f'bl {hex(ARRAY_GET_INDEXED_VA)}',
 'and x8, x0, #0xfffffffffffffff8',
 'cbz x8, deny_deep',
 # EquipmentEnhancementAbilityLogic.currentLevel at +0x30 proven by AOT getter/ctor.
 'ldr w9, [x8, #0x30]',
 'cmp w9, #120',
 'b.lt deny_deep',
 # Match AS3 _loc13_ = abilitySoulAbility and keep caller number atom in sync.
 'ldr x22, [sp, #0x20]',
 'cbz x22, deny_deep',
 'orr x9, x22, #1',
 'str x9, [sp, #0x80]',
 'b allow_deep',
 'deny_deep:',
 'mov w0, wzr',
 'b finish',
 'stock_result:',
 'mov w0, w21',
 'b finish',
 'allow_deep:',
 'mov w0, #1',
 'finish:',
 'ldp x21, x30, [sp, #0x10]',
 'ldp x19, x20, [sp], #0x30',
 'cbnz w0, allow_return',
 f'b {hex(GATE_DENY_VA)}',
 'allow_return:',
 'ret',
 ]
 return '\n'.join(lines)

def changed_ranges(before: bytes, after: bytes) -> list[dict[str, object]]:
    if len(before) != len(after):
        raise RuntimeError("Mach-O size changed")
    ranges: list[dict[str, object]] = []
    start: int | None = None
    for index, (old, new) in enumerate(zip(before, after)):
        if old != new and start is None:
            start = index
        elif old == new and start is not None:
            ranges.append(
                {"start": hex(start), "end": hex(index), "size": index - start}
            )
            start = None
    if start is not None:
        ranges.append(
            {"start": hex(start), "end": hex(len(before)), "size": len(before) - start}
        )
    return ranges


def expected_deep(group: int, inner: int, quest: int) -> bool:
    if group == 0 and inner == 8:
        return quest == 2001
    if group == 0 and inner == 10:
        return 1 <= quest <= 97
    if group == 0 and inner == 17:
        return quest // 1000 == 700099
    if group == 1 and inner == 4:
        return 1099001 <= quest <= 1099003
    return False


def model_result(
    stock_result: bool,
    is_deep: bool,
    candidate_kind: str,
    group: int,
    inner: int,
    quest: int,
    enhancement_some: bool = False,
    enhancement_level: int | None = None,
) -> tuple[bool, str]:
    if not is_deep:
        return stock_result, "stock"
    if expected_deep(group, inner, quest):
        return True, "candidate_unchanged"
    if (
        candidate_kind == "Equipment"
        and enhancement_some
        and enhancement_level is not None
        and enhancement_level >= 120
    ):
        return True, "abilitySoulAbility_replacement"
    return False, "deny"


def verify_semantic_truth_table() -> list[dict[str, object]]:
    cases = [
        (True, False, "AbilitySoul", 0, 8, 2001, False, None, True, "stock"),
        (
            False,
            True,
            "AbilitySoul",
            0,
            8,
            2001,
            False,
            None,
            True,
            "candidate_unchanged",
        ),
        (True, True, "AbilitySoul", 0, 8, 2002, False, None, False, "deny"),
        (
            False,
            True,
            "AbilitySoul",
            0,
            10,
            1,
            False,
            None,
            True,
            "candidate_unchanged",
        ),
        (True, True, "AbilitySoul", 0, 10, 98, False, None, False, "deny"),
        (
            False,
            True,
            "AbilitySoul",
            0,
            17,
            700099001,
            False,
            None,
            True,
            "candidate_unchanged",
        ),
        (
            True,
            True,
            "AbilitySoul",
            0,
            17,
            700098001,
            False,
            None,
            False,
            "deny",
        ),
        (
            False,
            True,
            "AbilitySoul",
            1,
            4,
            1099001,
            False,
            None,
            True,
            "candidate_unchanged",
        ),
        (
            False,
            True,
            "AbilitySoul",
            1,
            4,
            1099003,
            False,
            None,
            True,
            "candidate_unchanged",
        ),
        (True, True, "AbilitySoul", 1, 4, 1099004, False, None, False, "deny"),
        (True, True, "AbilitySoul", 2, 4, 1099001, False, None, False, "deny"),
        (
            True,
            True,
            "Equipment",
            0,
            8,
            2002,
            True,
            120,
            True,
            "abilitySoulAbility_replacement",
        ),
        (True, True, "Equipment", 0, 8, 2002, True, 119, False, "deny"),
        (
            False,
            True,
            "Equipment",
            1,
            4,
            1099001,
            True,
            119,
            True,
            "candidate_unchanged",
        ),
        (False, False, "Equipment", 2, 4, 123, True, 120, False, "stock"),
    ]
    rows: list[dict[str, object]] = []
    for (
        stock,
        deep,
        kind,
        group,
        inner,
        quest,
        some,
        level,
        expected,
        route,
    ) in cases:
        actual, actual_route = model_result(
            stock, deep, kind, group, inner, quest, some, level
        )
        if actual != expected or actual_route != route:
            raise RuntimeError(
                f"semantic truth mismatch: {kind} {group}/{inner}/{quest} -> "
                f"{(actual, actual_route)} expected {(expected, route)}"
            )
        rows.append(
            {
                "candidate": kind,
                "deep": deep,
                "group_index": group,
                "inner_index": inner,
                "quest_id": quest,
                "enhancement_some": some,
                "enhancement_level": level,
                "result": actual,
                "route": actual_route,
            }
        )
    return rows


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


def verify_output(
    source_entries: list[tuple[zipfile.ZipInfo, bytes]],
    source_comment: bytes,
    output_path: Path,
    expected_macho: bytes,
) -> list[str]:
    source_by_name = {info.filename: data for info, data in source_entries}
    with zipfile.ZipFile(output_path, "r") as output_zip:
        if output_zip.testzip() is not None:
            raise RuntimeError("output IPA ZIP test failed")
        if output_zip.comment != source_comment:
            raise RuntimeError("output IPA ZIP comment changed")
        output_infos = output_zip.infolist()
        source_infos = [info for info, _ in source_entries]
        if [info.filename for info in output_infos] != [
            info.filename for info in source_infos
        ]:
            raise RuntimeError("output IPA member order changed")
        changed: list[str] = []
        for source_info, output_info in zip(source_infos, output_infos):
            if zipinfo_signature(source_info) != zipinfo_signature(output_info):
                raise RuntimeError(
                    f"output IPA metadata changed: {source_info.filename}"
                )
            output_data = output_zip.read(output_info)
            source_data = source_by_name[source_info.filename]
            if output_data != source_data:
                changed.append(source_info.filename)
            if source_info.filename == MACHO_MEMBER and output_data != expected_macho:
                raise RuntimeError("output IPA Mach-O readback mismatch")
    if changed != [MACHO_MEMBER]:
        raise RuntimeError(f"unexpected changed IPA members: {changed}")
    return changed


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the accepted iOS abyss Multi/BothBoss and level-120 gate "
            "from the exact cumulative Rush leaderboard v3 IPA."
        )
    )
    parser.add_argument("--ipa", required=True, type=Path, help="hash-locked source IPA")
    parser.add_argument("--out", required=True, type=Path, help="unsigned output IPA")
    parser.add_argument("--report", type=Path, help="verification report JSON")
    parser.add_argument(
        "--dependency-path",
        type=Path,
        help="directory containing capstone and keystone Python packages",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    source_path = args.ipa.resolve()
    output_path = args.out.resolve()
    report_path = (
        args.report.resolve()
        if args.report is not None
        else output_path.with_suffix(".json")
    )
    if not source_path.is_file():
        raise RuntimeError(f"source IPA does not exist: {source_path}")
    if source_path == output_path:
        raise RuntimeError("source and output IPA must be different files")
    if report_path in {source_path, output_path}:
        raise RuntimeError("report path must differ from source and output IPA")
    if output_path.exists():
        raise RuntimeError(f"refusing to overwrite output IPA: {output_path}")
    if report_path.exists():
        raise RuntimeError(f"refusing to overwrite report: {report_path}")

    source_ipa_hash = sha256_file(source_path)
    if source_ipa_hash != EXPECTED_SOURCE_IPA_SHA256:
        raise RuntimeError(
            f"source IPA hash drifted: {source_ipa_hash} != "
            f"{EXPECTED_SOURCE_IPA_SHA256}"
        )
    with zipfile.ZipFile(source_path, "r") as source_zip:
        source_infos = source_zip.infolist()
        if len(source_infos) != EXPECTED_IPA_MEMBER_COUNT:
            raise RuntimeError(
                f"source IPA member count drifted: {len(source_infos)} != "
                f"{EXPECTED_IPA_MEMBER_COUNT}"
            )
        names = [info.filename for info in source_infos]
        if names.count(MACHO_MEMBER) != 1:
            raise RuntimeError(f"expected exactly one {MACHO_MEMBER}")
        if names.count(INFO_PLIST_MEMBER) != 1:
            raise RuntimeError(f"expected exactly one {INFO_PLIST_MEMBER}")
        source_entries = [(info, source_zip.read(info)) for info in source_infos]
        source_comment = source_zip.comment
    source_by_name = {info.filename: data for info, data in source_entries}
    source_macho = source_by_name[MACHO_MEMBER]
    if sha256_bytes(source_macho) != EXPECTED_SOURCE_MACHO_SHA256:
        raise RuntimeError("source Mach-O hash drifted")
    source_plist = plistlib.loads(source_by_name[INFO_PLIST_MEMBER])
    if source_plist.get("CFBundleIdentifier") != EXPECTED_BUNDLE_ID:
        raise RuntimeError("unexpected bundle identifier")
    if source_plist.get("CFBundleShortVersionString") != EXPECTED_SHORT_VERSION:
        raise RuntimeError("unexpected short version")
    if source_plist.get("CFBundleVersion") != EXPECTED_BUILD:
        raise RuntimeError("unexpected build number")
    if source_macho[0xCE0:0xCF0].hex() != EXPECTED_MACHO_UUID:
        raise RuntimeError("source Mach-O UUID drifted")
    if (
        source_macho[GATE_HOOK_OFFSET : GATE_HOOK_OFFSET + 4]
        != EXPECTED_GATE_HOOK
    ):
        raise RuntimeError("source abyss helper hook drifted")
    if (
        sha256_bytes(source_macho[HELPER_OFFSET:HELPER_CAPACITY_END])
        != EXPECTED_HELPER_CAPACITY_SHA256
    ):
        raise RuntimeError("source abyss helper capacity drifted")

    assembler, disassembler, dependency_source = load_assembler(args.dependency_path)
    assembly = build_gate_helper()
    encoding, statement_count = assembler.asm(
        assembly, addr=IMAGE_BASE + HELPER_OFFSET, as_bytes=True
    )
    helper = bytes(encoding)
    if not helper or len(helper) % 4:
        raise RuntimeError("invalid ARM64 helper encoding")
    if HELPER_OFFSET + len(helper) > HELPER_CAPACITY_END:
        raise RuntimeError("ARM64 helper exceeds reserved capacity")
    if sha256_bytes(helper) != EXPECTED_HELPER_SHA256:
        raise RuntimeError("assembled ARM64 helper hash drifted")
    disassembly = disassemble(disassembler, helper, IMAGE_BASE + HELPER_OFFSET)
    markers = [
        "mov w20, #1",
        "str x19, [sp, #0x20]",
        "mov w21, w20",
        "cmp w20, #1",
        "cmp w8, #4",
        "mov w9, #0xc4f9",
        "movk w9, #0x10c, lsl #16",
        "ldr x8, [x22, #0x38]",
        "ldr w9, [x8, #0x30]",
        "cmp w9, #0x78",
        "ldr x22, [sp, #0x20]",
        "str x9, [sp, #0x80]",
        f"bl #{hex(IS_TYPE_ATOM_VA)}",
        f"b #{hex(GATE_DENY_VA)}",
    ]
    for marker in markers:
        if not any(marker in line for line in disassembly):
            raise RuntimeError(f"missing ARM64 helper marker: {marker}")
    if sum(
        f"bl #{hex(IS_TYPE_ATOM_VA)}" in line for line in disassembly
    ) != 2:
        raise RuntimeError("native istype call count changed")
    if any("#0xe8" in line for line in disassembly[:45]):
        raise RuntimeError("rejected guessed type discriminator returned")

    patched_macho_buffer = bytearray(source_macho)
    patched_macho_buffer[HELPER_OFFSET : HELPER_OFFSET + len(helper)] = helper
    patched_macho = bytes(patched_macho_buffer)
    if sha256_bytes(patched_macho) != EXPECTED_OUTPUT_MACHO_SHA256:
        raise RuntimeError("output Mach-O hash drifted")
    for index, (before, after) in enumerate(zip(source_macho, patched_macho)):
        if before != after and not (
            HELPER_OFFSET <= index < HELPER_OFFSET + len(helper)
        ):
            raise RuntimeError(f"unexpected Mach-O change at {index:#x}")
    for name, (start, end) in PRESERVED_RANGES.items():
        if source_macho[start:end] != patched_macho[start:end]:
            raise RuntimeError(f"preserved feature changed: {name}")

    truth_table = verify_semantic_truth_table()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output: Path | None = None
    published = False
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_output = Path(handle.name)
        with zipfile.ZipFile(temporary_output, "w", allowZip64=True) as output_zip:
            output_zip.comment = source_comment
            for info, data in source_entries:
                output_zip.writestr(
                    copy_zipinfo(info),
                    patched_macho if info.filename == MACHO_MEMBER else data,
                )
        changed_members = verify_output(
            source_entries, source_comment, temporary_output, patched_macho
        )
        output_ipa_hash = sha256_file(temporary_output)
        if output_ipa_hash != EXPECTED_OUTPUT_IPA_SHA256:
            raise RuntimeError(
                f"output IPA hash drifted: {output_ipa_hash} != "
                f"{EXPECTED_OUTPUT_IPA_SHA256}"
            )
        os.replace(temporary_output, output_path)
        temporary_output = None
        published = True
        if sha256_file(output_path) != EXPECTED_OUTPUT_IPA_SHA256:
            raise RuntimeError("published output IPA hash drifted")

        report: dict[str, object] = {
            "schemaVersion": 2,
            "status": "device_validated_unsigned_payload",
            "purpose": (
                "iOS native deep-equipment gate v2 with Multi/BothBoss "
                "1099001..1099003 and direct Equipment level >=120 exception"
            ),
            "acceptance": {
                "status": "accepted_by_user",
                "accepted_at": "2026-09-07",
                "basis": "用户明确确认 iOS 验收",
            },
            "source_ipa": str(source_path),
            "source_ipa_sha256": EXPECTED_SOURCE_IPA_SHA256,
            "output_ipa": str(output_path),
            "output_ipa_sha256": EXPECTED_OUTPUT_IPA_SHA256,
            "source_macho_sha256": EXPECTED_SOURCE_MACHO_SHA256,
            "output_macho_sha256": EXPECTED_OUTPUT_MACHO_SHA256,
            "cfbundleidentifier": EXPECTED_BUNDLE_ID,
            "short_version": EXPECTED_SHORT_VERSION,
            "build": EXPECTED_BUILD,
            "base_lineage": {
                "rush_leaderboard_v3_entryhook_sha256": EXPECTED_SOURCE_IPA_SHA256,
                "rush_leaderboard_v3_entryhook_macho_sha256": (
                    EXPECTED_SOURCE_MACHO_SHA256
                ),
                "macho_uuid": EXPECTED_MACHO_UUID,
            },
            "android_reference": {
                "merged_source_sha256": EXPECTED_ANDROID_MERGED_SOURCE_SHA256
            },
            "contract": {
                "deep_equipment_ids": "8000101..8000115",
                "quest_groups": {
                    "Single[8]": "2001",
                    "Single[10]": "1..97",
                    "Single[17]": "700099xxx",
                    "Multi/BothBoss": "1099001..1099003",
                },
                "level120_exception": (
                    "direct EquipmentAbilityLogic with enhancementAbility Some "
                    "and currentLevel >=120; replace candidate with abilitySoulAbility"
                ),
                "level119_exception": "deny when whitelist misses",
                "getAvailableAbilitiesWithCond": "untouched",
                "auto_lock": "untouched",
            },
            "aot_proof": {
                "EquipmentAbilityLogic.enhancementAbility_offset": "0x38",
                "EquipmentAbilityLogic.abilitySoulAbility_offset": "0x40",
                "EquipmentEnhancementAbilityLogic.currentLevel_offset": "0x30",
                "EquipmentEnhancementAbilityLogic.getCurrentLevel": "0x104075a9c",
                "EquipmentEnhancementAbilityLogic.constructor": "0x104078340",
            },
            "helper": {
                "offset": hex(HELPER_OFFSET),
                "va": hex(IMAGE_BASE + HELPER_OFFSET),
                "capacity_end": hex(HELPER_CAPACITY_END),
                "size": len(helper),
                "remaining_capacity": HELPER_CAPACITY_END
                - HELPER_OFFSET
                - len(helper),
                "sha256": sha256_bytes(helper),
                "assembler_statement_count": statement_count,
                "instruction_count": len(disassembly),
                "assembly": assembly.splitlines(),
                "disassembly": disassembly,
            },
            "inline_hook": {
                "offset": hex(GATE_HOOK_OFFSET),
                "va": hex(GATE_HOOK_VA),
                "unchanged": True,
                "hex": EXPECTED_GATE_HOOK.hex(),
            },
            "truth_table": truth_table,
            "changed_macho_ranges": changed_ranges(source_macho, patched_macho),
            "preserved_ranges": {
                name: {
                    "start": hex(start),
                    "end": hex(end),
                    "size": end - start,
                    "byte_identical": True,
                }
                for name, (start, end) in PRESERVED_RANGES.items()
            },
            "preserved": {
                "memberview_v6_verified_gate": True,
                "rush_leaderboard_v3_entryhook": True,
                "fantasy_soul_async_texture": True,
                "seris_dual_form": True,
                "render_scale": True,
                "title_and_ingame_takeover": True,
                "non_macho_members_byte_identical": True,
                "info_plist_byte_identical": True,
                "ipa_member_count": len(source_entries),
            },
            "changed_members": changed_members,
            "assembler_libraries": dependency_source,
            "offline_limits": (
                "AOT structure, assembly, truth table, ZIP integrity and byte "
                "preservation verified; accepted payload remains unsigned"
            ),
        }
        write_report(report_path, report)
    except BaseException:
        if temporary_output is not None:
            temporary_output.unlink(missing_ok=True)
        if published:
            output_path.unlink(missing_ok=True)
        raise

    print(
        json.dumps(
            {
                "output_ipa": str(output_path),
                "output_ipa_sha256": EXPECTED_OUTPUT_IPA_SHA256,
                "output_macho_sha256": EXPECTED_OUTPUT_MACHO_SHA256,
                "report": str(report_path),
                "helper_size": len(helper),
                "remaining_capacity": HELPER_CAPACITY_END
                - HELPER_OFFSET
                - len(helper),
                "changed_members": changed_members,
                "acceptance": "accepted_by_user",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
