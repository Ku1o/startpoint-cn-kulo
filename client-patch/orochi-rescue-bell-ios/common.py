"""Pinned inputs and paths for the rescue-bell iOS port."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = Path(os.environ.get("OROCHI_IOS_PORT_WORK",
                           r"F:/codex/work/orochi-ios-cachefix-20261004"))
OUT = Path(os.environ.get("OROCHI_IOS_PORT_OUT",
                          r"F:/codex/outputs/orochi-rescue-bell-ios-fix-20261004"))
LEGACY = Path(r"F:/codex/ios-rush-leaderboard-port-20260830")
SDK = LEGACY / "AIRSDK_51.2.1.5"
JAVA = Path(r"D:/java/bin/java.exe")

IPA = Path(r"F:/codex/outputs/ios-equipment-f1009-fix-20261002/ios/"
           r"StarPoint-iOS-1.8.4-author-equipment-standalone-20261002-unsigned.ipa")
IPA_SHA = "4ce93ffe967331b088032fa4d3e169c7d58b2c1cef4b10cf727e28906811bf40"
NATIVE_MEMBER = "Payload/worldflipper.app/worldflipper"
SWF_MEMBER = "Payload/worldflipper.app/worldflipper_ios_release.swf"
NATIVE_SHA = "1a427b648fc62297effb0dbc9982611b7f0e6e9d0e0623d46cebdbe72872b1dc"
SWF_SHA = "7e7e3642f19d59b3471bd6b09f344cf83b097924bc7a4bd094780deb7b793e72"
RUNTIME_ABC_SHA = "7a7504c5d50200613ebdf892f512d736a37eeda402441981c37e4f56e3fd0d4a"
FULL_ABC = Path(r"F:/codex/work/f1009-fullfix/equipment-ios-full.abc")
FULL_ABC_SHA = "83149cffbef675fb0661a3072725473e4c49817c645bc069516124dc094b1097"
OLD_METHODS = 101458

EMBEDDED_MEMBER = ("Payload/worldflipper.app/asset/production/ios_bundle/dc/"
                   "bcccb129122c0189c8eab004ecc4516a077f3e")
EMBEDDED_OFFICIAL_SHA = "bf37fe2fa8b7f25b2924bed0093f8f2b53970dd62162532099d04d3aa01885cc"
EMBEDDED_COMPACT_SHA = "f9cba755d3c5d63f334989fd0a0a21b7f169f0fbede9e77e3178f4efa5568125"
EMBEDDED_COMPACT_BYTES = 480

BUILD_ID = "ios-184-orochi-rescue-bell-cache-10m-fix-20261004"
IPA_NAME = "StarPoint-iOS-1.8.4-orochi-rescue-bell-cache-10m-fix-20261004-unsigned.ipa"
PREVIOUS_BUILD_ID = "ios-184-author-1047-public-20261001"
PRIVATE = Path(r"F:/codex/.codex/secrets/starpoint-client-admission")
PAIR = PRIVATE / "releases/author-1047-public-20261001"
# No admission rotation in this port: the accepted public id and key stay in
# place, so both maps resolve to the current identifiers.
OLD_IDS = {"ios": "ios-184-author-1047-public-20261001"}
IDS = {"ios": "ios-184-author-1047-public-20261001"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")


def view(module, abc):
    return module.View(types.SimpleNamespace(abc=abc), module.asm)


def pair():
    policy = json.loads((PAIR / "config/client-admission.json").read_text("utf-8-sig"))
    keys = json.loads((PAIR / "config/client-admission.keys.json").read_text("utf-8-sig"))
    return policy, keys
