"""Tracked SWF tooling bridge for independent party client releases."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = Path(r"F:\codex\work\formal-client-20260923")
SDK = Path(r"F:\codex\ios-rush-leaderboard-port-20260830\AIRSDK_51.2.1.5")
JAVA = Path(r"D:\java\bin\java.exe")

spec = importlib.util.spec_from_file_location("independent_swf_tools", ROOT / "client-patch/startup-cache/build_swf.py")
s = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s
spec.loader.exec_module(s)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def run(command, label, timeout=180):
    WORK.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(x) for x in command], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout, check=False)
    (WORK / (label + ".log")).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(label + ": " + result.stdout.decode("utf8", "replace")[-5000:])
    return result.stdout.decode("utf8", "replace")
