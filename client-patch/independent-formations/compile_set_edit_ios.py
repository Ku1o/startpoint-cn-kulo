import importlib.util
import sys
from pathlib import Path

ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
WORK = Path(r"F:\codex\work\set-edit-c8601-ios-public-20260924")
LEGACY = Path(r"F:\codex\ios-rush-leaderboard-port-20260830")
SDK = LEGACY / "AIRSDK_51.2.1.5"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    prep = load("prepare", ROOT / "client-patch/ios-cumulative-login/prepare.py")
    prep.WORK = WORK
    prep.LEGACY = LEGACY
    prep.SDK = SDK
    compiler = load("set_edit_compile_native", ROOT / "client-patch/ios-cumulative-login/compile_native.py")
    compiler.WORK = WORK
    compiler.LEGACY = LEGACY
    compiler.SDK = SDK
    sys.argv = ["compile_native", "--attempt", "compile-final", "--optimization", "1"]
    compiler.main()


if __name__ == "__main__":
    main()
