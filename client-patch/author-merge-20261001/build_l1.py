"""Apply the equipment-rule layer to a verified 1047 SWF.

The input must be the SWF extracted from the accepted public 1047 APK.  The
script writes ``public-l1.swf`` into the requested work directory and leaves
the input untouched.  APK packaging and signing are deliberately separate.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "battle-rules"))

spec = importlib.util.spec_from_file_location("core", HERE / "battle-rules" / "core.py")
core = importlib.util.module_from_spec(spec)
sys.modules["core"] = core
assert spec.loader is not None
spec.loader.exec_module(core)

spec = importlib.util.spec_from_file_location("equipment_rules", HERE / "equipment-rules" / "overlay.py")
rules = importlib.util.module_from_spec(spec)
sys.modules["equipment_rules"] = rules
assert spec.loader is not None
spec.loader.exec_module(rules)

locks = json.loads((HERE / "equipment-rules" / "baseline.json").read_text(encoding="utf-8"))


def install_locks(editor_cls):
    def init(self, swf):
        core.Editor.__init__(self, swf)
        self.locks = {}
        for label in locks:
            body = swf.abc.bodies[core.bodies.resolve(swf.abc, label)]
            self.locks[label] = {
                "sha": hashlib.sha256(body[5]).hexdigest(),
                "header": list(body[1:5]),
            }

    editor_cls.__init__ = init


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True, help="verified public 1047 SWF")
    ap.add_argument("--work-dir", type=Path, required=True)
    args = ap.parse_args()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source = args.input.resolve(strict=True)
    baseline = work / "public-base.swf"
    output = work / "public-l1.swf"
    baseline.write_bytes(source.read_bytes())
    install_locks(rules.EquipmentRulesEditor)
    swf = core.SwfAbc(baseline)
    editor, report = rules.patch_editor(swf)
    swf.save(output)
    result = {
        "status": "ok",
        "input": str(source),
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "report": report,
    }
    (work / "l1-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
