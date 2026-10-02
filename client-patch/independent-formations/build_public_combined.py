"""Build the formal Android SWF from the accepted public EX baseline.

The generic-damage helper is first applied without its prototype disk logger;
the independent Rush party helper is then applied to that cumulative SWF.
"""
import importlib.util
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
WORK = Path(r"F:\codex\work\formal-client-20260923")
REGISTRY = ROOT / "client-patch" / "android-accepted.json"
KEYS = Path(r"F:\codex\.codex\secrets\starpoint-client-admission\config\client-admission.keys.json")
BUILD_ID = "android-181-independent-party-20260923"
PREVIOUS_BUILD_ID = "android-181-abyss-ex-20260917"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    record = json.loads(REGISTRY.read_text(encoding="utf8"))["variants"]["public"]
    source_apk = Path(record["apk"])
    assert source_apk.exists()
    assert record["apk_sha256"] == __import__("hashlib").sha256(source_apk.read_bytes()).hexdigest()
    WORK.mkdir(parents=True, exist_ok=True)
    input_swf = WORK / "input.swf"
    with zipfile.ZipFile(source_apk) as apk:
        swf = apk.read("assets/worldflipper_android_release.swf")
    assert __import__("hashlib").sha256(swf).hexdigest() == record["swf_sha256"]
    input_swf.write_bytes(swf)
    (WORK / "input-identity.json").write_text(
        json.dumps({"swf_sha256": record["swf_sha256"], "source_apk": str(source_apk)}, indent=2),
        encoding="utf8",
    )

    generic_dir = ROOT / "client-patch" / "generic-damage"
    if str(generic_dir) not in sys.path:
        sys.path.insert(0, str(generic_dir))
    generic_path = generic_dir / "build_swf.py"
    generic = load("formal_generic_build", generic_path)
    generic.WORK = WORK
    common = sys.modules["common"]
    common.WORK = WORK
    common.OUT = WORK
    generic.main()
    generic_swf = WORK / "generic-damage.swf"
    generic_report = json.loads((WORK / "swf-report.json").read_text(encoding="utf8"))
    generic_body_ids = {int(row["body"]) for row in generic_report["changes"]}

    independent_path = ROOT / "client-patch" / "independent-formations" / "build_swf.py"
    independent = load("formal_independent_build", independent_path)
    independent.INPUT = generic_swf
    independent.INPUT_SHA = __import__("hashlib").sha256(generic_swf.read_bytes()).hexdigest()
    independent.WORK = WORK
    common.WORK = WORK
    common.OUT = WORK
    independent.ADMISSION_KEYS = KEYS
    independent.OLD_BUILD_ID = PREVIOUS_BUILD_ID
    independent.BUILD_ID = BUILD_ID
    independent.PRECHANGED_BODY_IDS = generic_body_ids
    independent.main()

    report = json.loads((WORK / "swf-report.json").read_text(encoding="utf8"))
    report.update({
        "status": "formal_android_swf_candidate",
        "source_apk": str(source_apk),
        "source_apk_sha256": record["apk_sha256"],
        "source_swf_sha256": record["swf_sha256"],
        "generic_damage_logger_removed": True,
        "generic_damage_log_path_absent": True,
        "generic_damage_changed_bodies": sorted(generic_body_ids),
        "cumulative_stages": ["generic-damage-without-disk-logging", "independent-rush-formations"],
        "device_tested": False,
    })
    (WORK / "swf-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"swf": str(WORK / "independent-formations.swf"), **{k: report[k] for k in ("output_swf_sha256", "admission_build_id")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
