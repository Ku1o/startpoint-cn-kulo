"""Verify the iOS twelve-method contract against explicit accepted ABC inputs."""
from __future__ import annotations
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import zipfile
from types import SimpleNamespace

import overlimit_ios as port


def run_checks(ios_abc, android_swf, *, source_revision='initial'):
    repo = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("overlimit_shared_model", repo / "client-patch/lens0907-0908/build_swf.py")
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
    sys.path.insert(0, str(repo / "client-patch/pr43-port/support"))
    import common
    target = model.View(SimpleNamespace(abc=model.abcfmt.ABC(ios_abc.read_bytes())), model.asm)
    source_abc, _ = common.main_abc(android_swf.read_bytes())
    source = model.View(SimpleNamespace(abc=source_abc), model.asm)
    importer = model.Importer(target, source)
    original = copy.deepcopy(target.a)
    plan = port.inspect(importer, source_revision=source_revision)
    assert all(row["status"] == "pending" for row in plan)
    report = port.import_methods(importer, verify_body=model.check_body, source_revision=source_revision)
    changed = {row["target_body_index"] for row in report["methods"]}
    assert len(changed) == 12
    assert changed == {i for i, (a, b) in enumerate(zip(original.bodies, target.a.bodies))
                       if model.freeze(a) != model.freeze(b)}
    for name in ("methods", "metadata", "instances", "classes", "scripts"):
        assert model.freeze(getattr(original, name)) == model.freeze(getattr(target.a, name)), name
    for name in ("ints", "uints", "doubles", "strings", "namespaces", "ns_sets", "multinames"):
        old = getattr(original, name)
        assert model.freeze(getattr(target.a, name)[:len(old)]) == model.freeze(old), name
    raw = target.a.serialize()
    assert model.abcfmt.ABC(raw).serialize() == raw
    assert all(row["status"] == "already_present" for row in port.import_methods(importer, source_revision=source_revision)["methods"])
    try:
        port.inspect(importer, source_revision='unknown')
        raise AssertionError('Unknown source revision accepted')
    except ValueError as error:
        assert 'Unknown source revision' in str(error)
    if source_revision == 'old-server-compat':
        try:
            port.inspect(importer)
            raise AssertionError('Compatibility donor accepted as initial donor')
        except ValueError as error:
            assert 'Android final-method identity drift' in str(error)
        source_index = plan[1]['source_body_index']
        source.a.bodies[source_index][2] += 1
        try:
            port.inspect(importer, source_revision=source_revision)
            raise AssertionError('Unknown compatibility header accepted')
        except ValueError as error:
            assert 'header drift' in str(error)
        finally:
            source.a.bodies[source_index][2] -= 1
    # A pool-level identical method can still be the wrong native entry: IDs and
    # signatures are independently pinned, and unknown stubs are rejected.
    first = plan[0]
    ti = first["target_body_index"]
    target.a.bodies[ti] = copy.deepcopy(original.bodies[ti])
    target.a.bodies[ti][5] += b"\x09"
    try:
        port.inspect(importer, source_revision=source_revision)
        raise AssertionError("Unknown iOS preimage accepted")
    except ValueError as error:
        assert "Unknown iOS preimage" in str(error)
    target.a.bodies[ti] = copy.deepcopy(original.bodies[ti])
    target.a.bodies[ti][0] += 1
    try:
        port.inspect(importer, source_revision=source_revision)
        raise AssertionError("Wrong native method accepted")
    except ValueError as error:
        assert "method identity" in str(error)
    report.update(abc_roundtrip=True, only_twelve_bodies_changed=True,
                  pool_prefixes_preserved=True, idempotent=True,
                  unknown_preimage_refused=True, native_id_drift_refused=True,
                  aot_compiled=False, native_linked=False, device_tested=False)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ios-abc", type=Path, required=True)
    parser.add_argument("--android-swf", type=Path, required=True)
    parser.add_argument("--source-revision", choices=sorted(port.SOURCE_REVISIONS), default='initial')
    parser.add_argument("--report", type=Path)
    parser.add_argument("--ipa", type=Path)
    parser.add_argument("--resources", type=Path)
    args = parser.parse_args()
    report = run_checks(args.ios_abc, args.android_swf, source_revision=args.source_revision)
    if args.ipa or args.resources:
        assert args.ipa and args.resources, "Pass both --ipa and --resources"
        with zipfile.ZipFile(args.ipa) as archive:
            replacements = port.resource_replacements(args.resources, archive.read)
            assert len(replacements) == 4
        try:
            port.resource_replacements(args.resources, lambda _: b"wrong")
            raise AssertionError("Unknown resource preimage accepted")
        except ValueError as error:
            assert "preimage mismatch" in str(error)
        report.update(four_sparse_resources_verified=True, unknown_resource_preimage_refused=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("12 exact iOS imports; traits/signatures/pool prefixes and unrelated bodies preserved")
