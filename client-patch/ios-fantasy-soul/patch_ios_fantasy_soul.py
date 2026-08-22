#!/usr/bin/env python3
"""Port the fantasy-soul asynchronous texture load fix to the vetted iOS IPA."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path


DEPENDENCY_PATH: Path | None = None
IMAGE_BASE = 0x100000000
MACHO_MEMBER = "Payload/worldflipper.app/worldflipper"

# This patch intentionally accepts only the already-vetted five-in-one unsigned IPA.
SOURCE_IPA_SHA256 = "ef95265c81adc0c391ba4ab4df4f8f8456b0aa9485a572a0aeb822d286ed94f2"
SOURCE_MEMBER_COUNT = 3568
SOURCE_MACHO_SIZE = 108757200
SOURCE_MACHO_SHA256 = "9e7d6568d71e80cd6913f8f335b52e9ef1ea7731724f16372a1afc3bb05ef895"
TARGET_IPA_SHA256 = "fcba08d30702bb941d412ca1d650d0573481873489c4f94a38682d46e279ec88"
TARGET_MACHO_SHA256 = "08db334f41ac994b5076e0154357639e631849a4339249fd46ab288f14c41c1e"

# PartyCarouselAbilitySoulView.run/present entries in the main AOT method table.
RUN_METHOD_INDEX = 73150
PRESENT_METHOD_INDEX = 73151
METHOD_TABLE_OFF = 0x62C0780
RUN_POINTER_OFF = METHOD_TABLE_OFF + RUN_METHOD_INDEX * 8
PRESENT_POINTER_OFF = METHOD_TABLE_OFF + PRESENT_METHOD_INDEX * 8
ORIGINAL_RUN_VA = 0x102EFFD04
ORIGINAL_PRESENT_VA = 0x102EFFA70

# Production-inaccessible debug sound-test method used as executable storage.
# Invoking that debug action in this patched build is unsupported.
CAVE_OFF = 0x301980C
CAVE_VA = IMAGE_BASE + CAVE_OFF
CAVE_VERIFY_SIZE = 0x400
CAVE_SHA256 = "0aa6f9d1b300ea15bacfbe0667ef0ab8519fedc38f6e5b8b79720f4856e44f2f"
PRESENT_WRAPPER_OFF = 0x20
PRESENT_WRAPPER_VA = CAVE_VA + PRESENT_WRAPPER_OFF

# AIR/AVM AOT runtime helpers copied from compiler-generated methods in this binary.
ENTER_OR_LEAVE_GC_VA = 0x100A26814
FAILURE_VA = 0x100A2676C
BOUNDS_FAILURE_VA = 0x100A26780
RESOLVE_GLOBAL_VA = 0x10050A8E8
WRITE_BARRIER_VA = 0x10054A400
GET_ARRAY_ELEMENT_VA = 0x100A27088
GET_MULTINAME_PROPERTY_VA = 0x100A26EEC
UNTAG_POINTER_VA = 0x100A273AC


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def configure_dependencies(path: Path | None) -> None:
    global DEPENDENCY_PATH
    DEPENDENCY_PATH = path
    if path is not None:
        sys.path.insert(0, str(path.resolve()))


def assemble(source: str, address: int) -> bytes:
    try:
        from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN
    except ImportError as exc:
        raise RuntimeError(
            "keystone-engine is required; install it or pass --dependency-path"
        ) from exc

    engine = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
    encoded, count = engine.asm(source, address)
    if not encoded or count <= 0:
        raise RuntimeError("ARM64 assembler returned no code")
    return bytes(encoded)


def verify_direct_branches(
    code: bytes,
    address: int,
    allowed_external_targets: set[int],
) -> None:
    """Reject silently wrapped ARM64 branch immediates from permissive assemblers."""
    try:
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
    except ImportError as exc:
        raise RuntimeError(
            "capstone is required; install it or pass --dependency-path"
        ) from exc

    instructions = list(Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN).disasm(code, address))
    if sum(instruction.size for instruction in instructions) != len(code):
        raise RuntimeError(f"wrapper at 0x{address:x} did not fully disassemble")
    local_end = address + len(code)
    for instruction in instructions:
        if not (
            instruction.mnemonic in {"b", "bl", "cbz", "cbnz"}
            or instruction.mnemonic.startswith("b.")
        ):
            continue
        target_text = instruction.op_str.rsplit(",", 1)[-1].strip().lstrip("#")
        try:
            target = int(target_text, 0)
        except ValueError as exc:
            raise RuntimeError(
                f"cannot parse branch target at 0x{instruction.address:x}: "
                f"{instruction.mnemonic} {instruction.op_str}"
            ) from exc
        if not (address <= target < local_end) and target not in allowed_external_targets:
            raise RuntimeError(
                f"unexpected branch target 0x{target:x} at 0x{instruction.address:x}"
            )


def build_run_wrapper() -> bytes:
    # The normal gear run happens before abilitySoul exists. Later calls are the
    # setTexture completion callback and can safely reuse the original synchronous
    # present method because the requested texture is now resident in the cache.
    return assemble(
        f"""
            ldr x8, [x0, #0x78]
            cbnz x8, completion
            b 0x{ORIGINAL_RUN_VA:x}
        completion:
            mov x2, x1
            ldr x1, [x0, #0x48]
            b 0x{ORIGINAL_PRESENT_VA:x}
        """,
        CAVE_VA,
    )


def build_present_wrapper() -> bytes:
    # This mirrors PartyItemThumbnailView.setItemImage from the same iOS binary:
    # resolve AssetGroupKind.ItemThumbnail, create a bound method closure, then
    # dispatch ViewAssetContainer.setTexture(group, path, callback).
    return assemble(
        f"""
            stp x26, x25, [sp, #-0x50]!
            stp x24, x23, [sp, #0x10]
            stp x22, x21, [sp, #0x20]
            stp x20, x19, [sp, #0x30]
            stp x29, x30, [sp, #0x40]
            add x29, sp, #0x40
            sub sp, sp, #0x20
            mov x20, x2
            ldr x8, [x20, #0x10]
            mov x21, x0
            mov x22, x1
            ldr x23, [x8, #0x30]
            ldr x19, [x23, #0x8]
            mov x0, x19
            bl 0x{ENTER_OR_LEAVE_GC_VA:x}
            str x20, [sp, #0x10]
            ldr x8, [x19, #0x60]
            add x9, sp, #0x8
            str x8, [sp, #0x8]
            str x9, [x19, #0x60]

            ldr x0, [x19, #0xb8]
            mov x1, x21
            add x2, x21, #0x48
            mov x3, x22
            bl 0x{WRITE_BARRIER_VA:x}

            cbz x22, failure
            ldr w8, [x22, #0x20]
            cbnz w8, synchronous_fallback

            ldr x2, [x22, #0x30]
            cbz x2, failure
            mov w1, wzr
            add x0, sp, #0x8
            bl 0x{GET_ARRAY_ELEMENT_VA:x}
            mov x8, x0
            cmp x8, #5
            b.lo bounds_failure
            ldr x9, [x23, #0x108]
            mov w10, #0x20000
            movk w10, #0xd0a8
            add x1, x9, x10
            add x0, sp, #0x8
            mov x2, x8
            bl 0x{GET_MULTINAME_PROPERTY_VA:x}
            mov x1, x0
            add x0, sp, #0x8
            bl 0x{UNTAG_POINTER_VA:x}
            mov x26, x0

            ldr x8, [x20, #0x18]
            ldr x8, [x8, #0x10]
            ldr x8, [x8, #0x30]
            mov w9, #0x5c30
            add x0, x8, x9
            ldr x8, [x0]
            cbnz x8, item_thumbnail_ready
            add x1, sp, #0x8
            bl 0x{RESOLVE_GLOBAL_VA:x}
            mov x8, x0
        item_thumbnail_ready:
            ldr x8, [x8, #0x20]
            cbz x8, failure
            ldr x24, [x8, #0x1d8]

            ldr x8, [x23, #0x108]
            mov w9, #0x20000
            movk w9, #0x1b70
            add x1, x8, x9
            add x0, sp, #0x8
            add x2, x21, #0x1
            bl 0x{GET_MULTINAME_PROPERTY_VA:x}
            mov x25, x0

            ldr x22, [x21, #0x70]
            cbz x22, failure
            ldr x8, [x22, #0x10]
            and x3, x25, #0xfffffffffffffff8
            mov x0, x22
            mov x1, x24
            mov x2, x26
            ldr x4, [x8, #0x100]
            ldr x8, [x4, #0x10]
            ldr x8, [x8, #0x50]
            blr x8
            b success

        synchronous_fallback:
            mov x0, x21
            mov x1, x22
            mov x2, x20
            bl 0x{ORIGINAL_PRESENT_VA:x}

        success:
            mov x0, x19
            bl 0x{ENTER_OR_LEAVE_GC_VA:x}
            ldr x8, [sp, #0x8]
            mov w0, #4
            str x8, [x19, #0x60]
            sub sp, x29, #0x40
            ldp x29, x30, [sp, #0x40]
            ldp x20, x19, [sp, #0x30]
            ldp x22, x21, [sp, #0x20]
            ldp x24, x23, [sp, #0x10]
            ldp x26, x25, [sp], #0x50
            ret

        failure:
            mov x0, x20
            bl 0x{FAILURE_VA:x}
        bounds_failure:
            mov x0, x20
            mov x1, x8
            bl 0x{BOUNDS_FAILURE_VA:x}
        """,
        PRESENT_WRAPPER_VA,
    )


def patch_macho(original: bytes) -> tuple[bytes, dict[str, object]]:
    if len(original) != SOURCE_MACHO_SIZE:
        raise ValueError(f"Mach-O size mismatch: {len(original)} != {SOURCE_MACHO_SIZE}")
    if sha256_bytes(original) != SOURCE_MACHO_SHA256:
        raise ValueError("Mach-O SHA-256 mismatch")

    expected_pointers = struct.pack("<QQ", ORIGINAL_RUN_VA, ORIGINAL_PRESENT_VA)
    if original[RUN_POINTER_OFF : PRESENT_POINTER_OFF + 8] != expected_pointers:
        raise ValueError("PartyCarouselAbilitySoulView AOT pointer signature mismatch")
    cave = original[CAVE_OFF : CAVE_OFF + CAVE_VERIFY_SIZE]
    if sha256_bytes(cave) != CAVE_SHA256:
        raise ValueError("debug cave signature mismatch")

    run_wrapper = build_run_wrapper()
    present_wrapper = build_present_wrapper()
    verify_direct_branches(
        run_wrapper,
        CAVE_VA,
        {ORIGINAL_RUN_VA, ORIGINAL_PRESENT_VA},
    )
    verify_direct_branches(
        present_wrapper,
        PRESENT_WRAPPER_VA,
        {
            ENTER_OR_LEAVE_GC_VA,
            FAILURE_VA,
            BOUNDS_FAILURE_VA,
            RESOLVE_GLOBAL_VA,
            WRITE_BARRIER_VA,
            GET_ARRAY_ELEMENT_VA,
            GET_MULTINAME_PROPERTY_VA,
            UNTAG_POINTER_VA,
            ORIGINAL_PRESENT_VA,
        },
    )
    if len(run_wrapper) > PRESENT_WRAPPER_OFF:
        raise ValueError(f"run wrapper is unexpectedly large: 0x{len(run_wrapper):x}")
    if PRESENT_WRAPPER_OFF + len(present_wrapper) > CAVE_VERIFY_SIZE:
        raise ValueError(
            f"present wrapper exceeds reserved cave: 0x{len(present_wrapper):x}"
        )

    data = bytearray(original)
    data[CAVE_OFF : CAVE_OFF + len(run_wrapper)] = run_wrapper
    present_off = CAVE_OFF + PRESENT_WRAPPER_OFF
    data[present_off : present_off + len(present_wrapper)] = present_wrapper
    data[RUN_POINTER_OFF : RUN_POINTER_OFF + 8] = struct.pack("<Q", CAVE_VA)
    data[PRESENT_POINTER_OFF : PRESENT_POINTER_OFF + 8] = struct.pack(
        "<Q", PRESENT_WRAPPER_VA
    )
    result = bytes(data)
    if sha256_bytes(result) != TARGET_MACHO_SHA256:
        raise RuntimeError("patched Mach-O SHA-256 mismatch")

    allowed = (
        (CAVE_OFF, CAVE_OFF + len(run_wrapper)),
        (present_off, present_off + len(present_wrapper)),
        (RUN_POINTER_OFF, RUN_POINTER_OFF + 8),
        (PRESENT_POINTER_OFF, PRESENT_POINTER_OFF + 8),
    )
    changed = [
        index
        for index, (before, after) in enumerate(zip(original, result))
        if before != after
    ]
    if not changed or any(
        not any(start <= index < end for start, end in allowed) for index in changed
    ):
        raise RuntimeError("unexpected Mach-O change outside the reserved patch ranges")

    return result, {
        "input_macho_sha256": sha256_bytes(original),
        "output_macho_sha256": sha256_bytes(result),
        "run_method_index": RUN_METHOD_INDEX,
        "present_method_index": PRESENT_METHOD_INDEX,
        "run_pointer_offset": hex(RUN_POINTER_OFF),
        "present_pointer_offset": hex(PRESENT_POINTER_OFF),
        "run_wrapper_va": hex(CAVE_VA),
        "run_wrapper_size": len(run_wrapper),
        "present_wrapper_va": hex(PRESENT_WRAPPER_VA),
        "present_wrapper_size": len(present_wrapper),
        "cave_offset": hex(CAVE_OFF),
        "changed_byte_count": len(changed),
    }


def patch_ipa(source: Path, output: Path, manifest_path: Path | None) -> dict[str, object]:
    if source.resolve() == output.resolve():
        raise ValueError("source and output IPA paths must differ")
    actual_source_hash = sha256_file(source)
    if actual_source_hash != SOURCE_IPA_SHA256:
        raise ValueError(
            f"source IPA SHA-256 mismatch: {actual_source_hash} != {SOURCE_IPA_SHA256}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    patched_members = 0
    manifest: dict[str, object] = {}
    try:
        with zipfile.ZipFile(source, "r") as src, zipfile.ZipFile(output, "w") as dst:
            if len(src.infolist()) != SOURCE_MEMBER_COUNT:
                raise ValueError(
                    f"source member count mismatch: {len(src.infolist())} != {SOURCE_MEMBER_COUNT}"
                )
            dst.comment = src.comment
            for info in src.infolist():
                payload = src.read(info)
                if info.filename == MACHO_MEMBER:
                    payload, manifest = patch_macho(payload)
                    patched_members += 1
                dst.writestr(
                    info,
                    payload,
                    compress_type=info.compress_type,
                    compresslevel=6,
                )
        if patched_members != 1:
            raise ValueError(f"expected one Mach-O member, patched {patched_members}")
    except Exception:
        output.unlink(missing_ok=True)
        raise

    output_hash = sha256_file(output)
    if output_hash != TARGET_IPA_SHA256:
        output.unlink(missing_ok=True)
        raise RuntimeError(
            f"patched IPA SHA-256 mismatch: {output_hash} != {TARGET_IPA_SHA256}"
        )

    manifest.update(
        {
            "source_ipa": str(source.resolve()),
            "source_ipa_sha256": actual_source_hash,
            "output_ipa": str(output.resolve()),
            "output_ipa_sha256": output_hash,
            "unsigned": True,
        }
    )
    if manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipa", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--dependency-path",
        type=Path,
        help="optional directory containing capstone and keystone packages",
    )
    args = parser.parse_args()
    configure_dependencies(args.dependency_path)
    print(
        json.dumps(
            patch_ipa(args.ipa, args.out, args.manifest),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
