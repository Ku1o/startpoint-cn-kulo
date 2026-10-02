"""Link the formal iOS AOT candidate with a new platform admission id."""
import importlib.util, json, os, sys
from pathlib import Path

ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
WORK = Path(r"F:\codex\work\formal-ios-20260923")
OUT = Path(r"F:\codex\outputs\abyss-ex-independent-formations-20260923")
PRIVATE = Path(r"F:\codex\.codex\secrets\starpoint-client-admission")
NEW_ID = "ios-184-independent-party-20260923"


def main():
    os.environ["STARPOINT_EX_RELEASE_WORK"] = str(WORK)
    os.environ["STARPOINT_EX_RELEASE_OUT"] = str(OUT)
    sys.path.insert(0, str(ROOT / "client-patch/abyss-ex"))
    import release_common as rc
    rc.WORK = WORK
    rc.OUT = OUT
    rc.PAIR = PRIVATE
    rc.IDS = {"android": "android-181-independent-party-20260923", "ios": NEW_ID}
    spec = importlib.util.spec_from_file_location("formal_build_ios_impl", ROOT / "client-patch/abyss-ex/build_ios.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    # build_ios.py imports these values with `from release_common import *`.
    mod.WORK = WORK
    mod.OUT = OUT
    mod.PAIR = PRIVATE
    mod.IDS = rc.IDS
    mod.OLD_COUNT = 101287
    def formal_replacements(platform):
        old = "ios-184-abyss-ex-20260917"
        keys = json.loads((PRIVATE / "config/client-admission.keys.json").read_text(encoding="utf8"))
        return {
            old.encode(): NEW_ID.encode(),
            keys[old].encode(): keys[NEW_ID].encode(),
            ("SP-ADMISSION-1\n" + old + "\n").encode():
                ("SP-ADMISSION-1\n" + NEW_ID + "\n").encode(),
        }
    mod.replacements = formal_replacements
    OUT.mkdir(parents=True, exist_ok=True)
    mod.main()


if __name__ == "__main__": main()
