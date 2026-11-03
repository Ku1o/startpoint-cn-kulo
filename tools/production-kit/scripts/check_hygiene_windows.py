#!/usr/bin/env python3
"""Read-only Windows preflight for scripts/check-hygiene.sh --all.

Only tracked working-tree files are scanned. This does not stage files, inspect
commit history, or replace GitHub hygiene and Gitleaks checks.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path


IP_RE = re.compile(r"192\.168\.[0-9]+\.[0-9]+")
HOME_RE = re.compile(r"/Users/[A-Za-z0-9_]+")
EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@(qq|gmail|163|126|outlook|hotmail|foxmail|yahoo)\.com",
    re.IGNORECASE,
)


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [root / name for name in result.stdout.split("\0") if name]


def allowed_line(kind: str, path: str, line: str) -> bool:
    normalized = line.strip()
    if kind == "ip" and "192.168.1.10" in line:
        return True
    allowed = {
        ("ip", "tools/fantasy-gauntlet-mod-tools/wf_release_v1/_loopback_http.py", 'ipaddress.ip_network("192.168.0.0/16"),'),
        ("ip", "tools/fantasy-gauntlet-mod-tools/wf_release_v1/platform.py", 'ipaddress.ip_network("192.168.0.0/16"),'),
        ("ip", "tools/fantasy-gauntlet-mod-tools/wf_release_v1/target.py", 'ipaddress.ip_network("192.168.0.0/16"),'),
        ("home", "tools/fantasy-gauntlet-mod-tools/tests/test_release_v1_canonical.py", 'r"C:\\Users\\Alice\\secret.json",'),
        ("home", "tools/fantasy-gauntlet-mod-tools/tests/test_release_v1_canonical.py", '"C:/Users/Alice/secret.json",'),
        ("home", "tools/fantasy-gauntlet-mod-tools/tests/test_release_v1_canonical.py", '"/Users/Alice/secret.json",'),
        ("email", "tools/player-save-extractor/NODE-LICENSE.txt", "Copyright (c) 2016 Jean-Philippe Aumasson <jeanphilippe.aumasson@gmail.com>"),
    }
    return (kind, path, normalized) in allowed


def should_skip(path: str) -> bool:
    return path in {
        "scripts/check-hygiene.sh",
        ".github/workflows/hygiene.yml",
        "tools/production-kit/scripts/check_hygiene_windows.py",
        "tools/fantasy-gauntlet-mod-tools/scripts/check-hygiene.sh",
        "tools/fantasy-gauntlet-mod-tools/scripts/tests/test-hygiene.sh",
    } or path.startswith("scripts/hooks/")


def scan(root: Path) -> list[str]:
    failures: list[str] = []
    for path in tracked_files(root):
        relative = path.relative_to(root).as_posix()
        if should_skip(relative) or not path.is_file():
            continue
        if relative == ".env":
            failures.append(".env must not be tracked")
            continue
        if fnmatch.fnmatch(relative, ".cdn/cn/archive-*-diff/*.zip"):
            failures.append(f"custom CDN archive under .cdn: {relative}")
            continue
        if path.stat().st_size > 1024 * 1024:
            allowed_large = (
                fnmatch.fnmatch(relative, "assets/asset-patch/active/*.zip")
                or relative == "tools/fantasy-gauntlet-mod-tools/WF_PATHLIST_recovered.txt"
                or path.suffix in {".json", ".csv", ".md"}
            )
            if not allowed_large:
                failures.append(f"large non-approved file: {relative}")
        raw = path.read_bytes()
        if not raw or b"\x00" in raw:
            continue
        text = raw.decode("utf-8", errors="ignore")
        for number, line in enumerate(text.splitlines(), 1):
            for kind, pattern in (("ip", IP_RE), ("home", HOME_RE), ("email", EMAIL_RE)):
                if pattern.search(line) and not allowed_line(kind, relative, line):
                    failures.append(f"{kind} at {relative}:{number}")
    return failures


def main() -> int:
    # Keep Chinese filenames readable when Windows redirects output to a pipe.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    failures = scan(args.repo.resolve())
    if failures:
        print("hygiene preflight failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("hygiene preflight passed: tracked working-tree files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
