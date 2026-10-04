"""Run the headless arm64 AIR compiler for the cache-cleanup port.

Two build gates run here, before any linking:

* no ``Verify error`` for a method introduced by this port, and
* the static slot offsets of ``cn.mod::AuthorState`` are unchanged.  Its
  accessors stay linked from the accepted carrier, so a shifted class-object
  static slot would make them read the wrong object.  The 2026-10-04 candidate
  added ``periodicStarted``/``periodicTimer`` to that class and every iOS
  client raised TypeError #1009 from ``getGauge`` on entering a battle.
"""
from __future__ import annotations
import json
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

from common import LEGACY, REPO, SDK, WORK, dump, sha

sys.path[:0] = [str(REPO / "client-patch/ios-cumulative-login"),
                str(LEGACY),
                r"F:\codex\tools\ios-re-libs"]
import build_native as link  # type: ignore
import capstone  # type: ignore
import lief  # type: ignore

INFO_OFFSET = 104549248
# accessor method id -> accepted class-object slot offset of the field it reads
ACCESSOR_GUARD = {101323: 0x30, 101324: 0x30, 101325: 0x38, 101326: 0x38}
SLOT_MIN, SLOT_MAX = 0x30, 0x80


def verify_new_method_warnings(log_path: Path, tracked) -> list:
    lines = log_path.read_text("utf8", errors="replace").splitlines()
    verifier = [line for line in lines if "Verify error:" in line]
    unexpected = []
    for line in verifier:
        match = re.search(r"Verify error:\s*[^:]+:(\d+):", line)
        if match and int(match.group(1)) in tracked:
            unexpected.append(line)
    if unexpected:
        raise AssertionError(("verifier warnings for new methods", unexpected, str(log_path)))
    return verifier


def slot_immediates(code: bytes) -> list[int]:
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    found = []
    for ins in md.disasm(code, 0):
        if ins.mnemonic not in ("ldr", "str", "ldrb", "ldrh"):
            continue
        match = re.match(r"x\d+,\s*\[x0,\s*#(0x[0-9a-fA-F]+|\d+)\]", ins.op_str)
        if not match:
            continue
        value = int(match.group(1), 0)
        if SLOT_MIN <= value <= SLOT_MAX:
            found.append(value)
    return found


def frozen_accessor_immediates() -> dict:
    native = (WORK / "baseline-native").read_bytes()
    active_va = struct.unpack_from("<Q", native, INFO_OFFSET + 48)[0]
    active_off = link.file_offset(native, active_va)
    result = {}
    for mid in ACCESSOR_GUARD:
        va = struct.unpack_from("<Q", native, active_off + mid * 8)[0]
        off = link.file_offset(native, va, 4)
        found = slot_immediates(native[off:off + 0x60])
        if not found:
            raise AssertionError(("no slot immediate in frozen accessor", mid))
        result[mid] = found[0]
    return result


def compiled_accessor_immediates(directory: Path) -> dict:
    wanted = set(ACCESSOR_GUARD)
    result = {}
    for path in sorted(directory.glob("*.o")):
        obj = lief.parse(str(path))
        if obj is None:
            continue
        text = next(section for section in obj.sections if section.name == "__text")
        starts = sorted({s.value for s in obj.symbols
                         if re.search(r":\d+:", link.aot.text(s.name))
                         and text.virtual_address <= s.value
                         < text.virtual_address + text.size} | {text.virtual_address + text.size})
        for symbol in obj.symbols:
            match = re.search(r":(\d+):", link.aot.text(symbol.name))
            if not match or not symbol.numberof_sections:
                continue
            mid = int(match.group(1))
            if mid not in wanted or mid in result:
                continue
            end = next(value for value in starts if value > symbol.value)
            code = bytes(obj.get_content_from_virtual_address(symbol.value, end - symbol.value))
            found = slot_immediates(code)
            if not found:
                raise AssertionError(("no slot immediate in recompiled accessor", mid))
            result[mid] = found[0]
    return result


def main():
    port = json.loads((WORK / "port.json").read_text("utf8"))
    source = (WORK / port["full_abc_file"]).read_bytes()
    assert sha(source) == port["full_abc_sha256"]
    directory = WORK / "compile-cachefix-r1"
    directory.mkdir(exist_ok=True)
    cumulative = directory / "cumulative.abc"
    if cumulative.exists():
        assert cumulative.read_bytes() == source
    else:
        cumulative.write_bytes(source)
    compiler = SDK / "lib/aot/bin/compile-abc/compile-abc-64.exe"
    deps = sorted((LEGACY / "android-baseline/abc").glob("*.abc"))
    deps = [p for p in deps if not p.name.startswith("284-")]
    assert len(deps) == 284, len(deps)
    args = [str(compiler), "-mtriple=arm64-apple-ios",
            "-fields=" + str(SDK / "lib/aot/lib/air-fields.arm64-air.txt"),
            "-sdk=" + str(SDK / "lib/aot/lib/avmglue.abc"),
            "-O=1", "-verify-warnings", *[str(p) for p in deps], str(cumulative)]
    assert not list(directory.glob("*.o")), "refusing to overwrite compiler outputs"
    started = time.monotonic()
    log_path = WORK / "compile-cachefix-r1.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(args, cwd=directory, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=300)
            assert code == 0, ("compiler failed", code, str(log_path))
        finally:
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=15)
    tracked = set(port["new_method_ids"])
    verifier_warnings = verify_new_method_warnings(log_path, tracked)

    frozen = frozen_accessor_immediates()
    for mid, expected in ACCESSOR_GUARD.items():
        if frozen[mid] != expected:
            raise AssertionError(("carrier accessor slot moved", mid, hex(frozen[mid])))
    compiled = compiled_accessor_immediates(directory)
    missing = sorted(set(ACCESSOR_GUARD) - set(compiled))
    if missing:
        raise AssertionError(("recompiled accessor symbols missing", missing))
    for mid, expected in ACCESSOR_GUARD.items():
        if compiled[mid] != expected:
            raise AssertionError(("recompiled accessor would read a different slot",
                                  mid, hex(compiled[mid]), hex(expected)))

    result = dict(elapsed_seconds=round(time.monotonic() - started, 2), headless=True,
                  directory=str(directory), optimization="1",
                  verifier_warnings=verifier_warnings,
                  tracked_new_methods=sorted(tracked),
                  accessor_slot_guard={
                      "frozen": {str(mid): hex(value) for mid, value in sorted(frozen.items())},
                      "recompiled": {str(mid): hex(value) for mid, value in sorted(compiled.items())}},
                  objects=[dict(name=p.name, bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
                           for p in sorted(directory.glob("cumulative*.o"))])
    dump(WORK / "compile-cachefix-r1-report.json", result)
    print("Compiled native objects:", len(result["objects"]),
          "elapsed:", result["elapsed_seconds"],
          "accessor_slot_guard:", json.dumps(result["accessor_slot_guard"]))


if __name__ == "__main__":
    main()
