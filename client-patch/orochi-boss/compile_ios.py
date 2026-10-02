from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"F:/codex/startpoint-cn-private-clean")
WORK = Path(r"F:/codex/work/client-public-20260926/build/ios-boss")
sys.path.insert(0, str(ROOT / "client-patch/ios-cumulative-login"))

import prepare  # type: ignore

prepare.WORK = WORK

import compile_native  # type: ignore

if __name__ == "__main__":
    sys.argv = ["compile_native", "--attempt", "compile-boss-r2", "--optimization", "1"]
    compile_native.main()
