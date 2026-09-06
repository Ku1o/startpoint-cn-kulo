#!/usr/bin/env python3
"""Switch the cumulative CNtips_b-hidden public APK to the LAN endpoint."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import uuid

import build_navigation_apk as nav
from apk_build_common import BuildError, extract_swf, replace_apk, run, sha256, verify
from build_self_profile_public_apk import CONFIG_CLASS, CONFIG_BODY, export_constructor
from build_title_cntips_apk import export_title, extract_method, visibility_assignment

BASE_APK_SHA256 = "7990f9191ecf41bd35a4d886ced4d13248d13559284639c69bee5837bd682f0e"
BASE_SWF_SHA256 = "27bdd055f8ca15f0863f564f5b4d57aba7de18d65d5fb9cdec43e87f96740e64"
BASE_UUID = "10eb0c01-78a1-4a70-8c35-d524208b98b7"
PUBLIC_HOST = "175.178.160.158:8001"
LAN_HOST = "192.168.3.14:8001"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "out", "work", "java", "javac", "ffdec", "zipalign", "apksigner", "keystore"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--password-env", required=True)
    args = parser.parse_args()
    if sha256(args.base) != BASE_APK_SHA256:
        raise BuildError("input must be the cumulative CNtips_b-hidden public APK")
    if args.work.exists() or args.out.exists():
        raise BuildError("output/work already exists")
    if not os.environ.get(args.password_env):
        raise BuildError("missing signing environment variable")
    args.work.mkdir(parents=True)
    baseline = args.work / "baseline.swf"
    extract_swf(args.base, baseline)
    if sha256(baseline) != BASE_SWF_SHA256:
        raise BuildError("baseline embedded SWF mismatch")
    source = export_constructor(nav, args.java, args.ffdec, baseline, args.work / "source-config")
    old = f'pushstring "{PUBLIC_HOST}"'
    new = f'pushstring "{LAN_HOST}"'
    if source.count(old) != 1 or new in source:
        raise BuildError("expected exactly one public endpoint in configuration")
    patched = source.replace(old, new, 1)
    pcode = args.work / "DevConfig_gf_android-lan.pcode"
    pcode.write_text(patched, encoding="utf-8", newline="\n")
    helpers = args.work / "method-tools"
    helpers.mkdir()
    helper_src = Path(__file__).resolve().parents[1] / "character-carousel"
    run([args.javac, "-cp", args.ffdec, "-d", helpers,
         helper_src / "FindMethodBody.java", helper_src / "CompareMethodBodies.java"])
    cp = os.pathsep.join((str(helpers), str(args.ffdec)))
    located = run([args.java, "-cp", cp, "FindMethodBody", baseline,
                   CONFIG_CLASS, "<constructor>"], capture=True)
    if located.strip() != f"{CONFIG_CLASS}.<constructor>\tabc=284\tbody={CONFIG_BODY}":
        raise BuildError(f"unexpected config method location: {located}")
    candidate = args.work / "title-cntips-hidden-lan.swf"
    run([args.java, "-Xmx4g", "-jar", args.ffdec, "-air", "-onerror", "abort", "-replace",
         baseline, candidate, CONFIG_CLASS, pcode, str(CONFIG_BODY)])
    comparison = run([args.java, "-Xmx4g", "-cp", cp, "CompareMethodBodies", baseline, candidate], capture=True)
    if set(comparison.strip().splitlines()) != {
        "method_bodies=96397", "changed_count=1", "changed=284:92013",
    }:
        raise BuildError(f"unexpected SWF changes: {comparison}")
    (args.work / "method-comparison.txt").write_text(comparison, encoding="utf-8")
    actual_config = export_constructor(nav, args.java, args.ffdec, candidate, args.work / "final-config")
    if actual_config != patched:
        raise BuildError("final SWF config does not match intended LAN constructor")
    title = export_title(args, candidate, args.work / "final-title")
    refresh = extract_method(title, "refreshHealth")
    if refresh.count(visibility_assignment("copyrightImage", False)) != 2:
        raise BuildError("CNtips_b hidden-state regression")
    if visibility_assignment("copyrightImage", True) in refresh:
        raise BuildError("CNtips_b can still become visible")
    # The exact one-method delta also keeps all profile routes, follow
    # controls, CNtips_a, title version text and other cumulative fixes.
    new_uuid = str(uuid.uuid4())
    unsigned, aligned, signed = (args.work / name for name in ("unsigned.apk", "aligned.apk", "signed.apk"))
    replace_apk(args.base, candidate, unsigned, new_uuid, base_uuid=BASE_UUID)
    run([args.zipalign, "-p", "-f", "4", unsigned, aligned])
    unsigned.unlink()
    run([args.java, "-jar", args.apksigner, "sign", "--ks", args.keystore,
         "--ks-key-alias", "wf", "--ks-pass", f"env:{args.password_env}",
         "--key-pass", f"env:{args.password_env}", "--out", signed, aligned])
    aligned.unlink()
    run([args.zipalign, "-c", "-p", "4", signed])
    report = verify(args.base, signed, candidate, new_uuid, args.java, args.apksigner, base_uuid=BASE_UUID)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    signed.replace(args.out)
    report.update({
        "schema_version": 1, "status": "locally_verified_test_candidate",
        "runtime_or_device_verified": False,
        "base_apk": str(args.base.resolve()), "base_apk_sha256": BASE_APK_SHA256,
        "base_swf_sha256": BASE_SWF_SHA256, "base_uniqueappversionid": BASE_UUID,
        "apk": str(args.out.resolve()), "endpoint": f"http://{LAN_HOST}",
        "changed_methods": ["284:92013"], "CNtips_b_hidden_in_both_health_states": True,
        "self_profile_and_follow_fixes_preserved": True,
        "zipalign": True, "final_swf_config_and_title_reexport_verified": True,
    })
    (args.out.parent / "verification-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
