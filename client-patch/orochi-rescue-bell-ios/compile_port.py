"""Run only the headless arm64 AIR compiler for the cache-cleanup port."""
from __future__ import annotations
import json
import re
import subprocess
import time
from pathlib import Path

from common import LEGACY, SDK, WORK, dump, sha


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


def main():
    port = json.loads((WORK / "port.json").read_text("utf8"))
    source = (WORK / port["full_abc_file"]).read_bytes()
    assert sha(source) == port["full_abc_sha256"]
    directory = WORK / "compile-cache-r1"
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
    log_path = WORK / "compile-cache-r1.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(args, cwd=directory, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=300)
            assert code == 0, ("compiler failed", code, str(log_path))
        finally:
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=15)
    tracked = set(port.get("compiled_helpers", []))
    tracked.add(port.get("hook_method"))
    for row in port.get("method_redirects", []):
        tracked.add(int(row["compiled"]))
    tracked.discard(None)
    verifier_warnings = verify_new_method_warnings(log_path, tracked)
    result = dict(elapsed_seconds=round(time.monotonic() - started, 2), headless=True,
                  directory=str(directory), optimization="1",
                  verifier_warnings=verifier_warnings,
                  tracked_new_methods=sorted(tracked),
                  objects=[dict(name=p.name, bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
                           for p in sorted(directory.glob("cumulative*.o"))])
    dump(WORK / "compile-cache-r1-report.json", result)
    print("Compiled native objects:", len(result["objects"]),
          "elapsed:", result["elapsed_seconds"])


if __name__ == "__main__":
    main()
