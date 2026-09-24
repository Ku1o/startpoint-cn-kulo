"""Link the SET C8601 hook onto the previous independent-formations IPA."""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
WORK = Path(r"F:\codex\work\set-edit-c8601-ios-public-20260924")
OUT = Path(r"F:\codex\outputs\set-edit-c8601-ios-public-20260924")
LEGACY = Path(r"F:\codex\ios-rush-leaderboard-port-20260830")
SDK = LEGACY / "AIRSDK_51.2.1.5"
# The complete admission pair contains the existing iOS independent-party key;
# the historical release snapshot only recorded the Android half.
PAIR = Path(r"F:\codex\.codex\secrets\starpoint-client-admission")
IDS = {"android": "android-181-independent-party-20260923",
       "ios": "ios-184-independent-party-20260923"}
INFO_OFFSET = 104549248
OLD_COUNT = 101314
PREP_DIR = WORK


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    # Build the release-common namespace expected by the historical linker,
    # overriding only the work paths and keeping the existing admission pair.
    rc = load("release_common", ROOT / "client-patch/abyss-ex/release_common.py")
    rc.WORK = WORK
    rc.OUT = OUT
    rc.PREP = PREP_DIR
    rc.PAIR = PAIR
    rc.IDS = IDS
    rc.OLD_COUNT = OLD_COUNT
    rc.INFO_OFFSET = INFO_OFFSET
    rc.LEGACY = LEGACY
    rc.SDK = SDK
    rc.replacements = lambda platform: {}
    prep = load("prepare", ROOT / "client-patch/ios-cumulative-login/prepare.py")
    prep.WORK = WORK
    prep.LEGACY = LEGACY
    prep.SDK = SDK
    link = load("set_edit_build_ios", ROOT / "client-patch/abyss-ex/build_ios.py")
    for name, value in {
        "WORK": WORK, "OUT": OUT, "PAIR": PAIR, "IDS": IDS,
        "OLD_COUNT": OLD_COUNT, "INFO_OFFSET": INFO_OFFSET,
        "LEGACY": LEGACY, "SDK": SDK, "PREP": PREP_DIR,
    }.items():
        setattr(link, name, value)
    link.main()
    source_ipa = OUT / "StarPoint-iOS-1.8.4-independent-formations-public-20260923-unsigned.ipa"
    target_ipa = OUT / "StarPoint-iOS-1.8.4-independent-formations-set-edit-c8601-public-20260924-unsigned.ipa"
    shutil.copyfile(source_ipa, target_ipa)
    shutil.copyfile(WORK / "formal-set-edit-full.abc", OUT / "formal-set-edit-full.abc")


if __name__ == "__main__":
    main()
