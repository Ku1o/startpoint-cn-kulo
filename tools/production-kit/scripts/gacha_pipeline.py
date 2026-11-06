#!/usr/bin/env python3
"""Offline gacha production: bound inputs -> art -> native Movies -> review -> handoff.

Never registers a patch, changes a database, launches a service or grants items.
See references/gacha-production-pipeline.md for the project contract.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = re.compile(r"^[a-zA-Z0-9_-]+$")
SHA = re.compile(r"^[0-9a-f]{64}$")


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def binding(path):
    p = Path(path).resolve()
    return {"file": str(p), "sha256": digest(p), "bytes": p.stat().st_size}


def inside(path, root):
    return path == root or root in path.parents


def resolve_files(value, base):
    if isinstance(value, list):
        return [resolve_files(x, base) for x in value]
    if not isinstance(value, dict):
        return value
    out = {k: resolve_files(v, base) for k, v in value.items()}
    if isinstance(out.get("file"), str):
        p = Path(out["file"])
        out["file"] = str((base / p).resolve() if not p.is_absolute() else p.resolve())
    return out


def input_bindings(value, result=None):
    result = [] if result is None else result
    if isinstance(value, dict):
        if "file" in value:
            if not isinstance(value["file"], str) or not SHA.fullmatch(str(value.get("sha256", ""))):
                raise ValueError("Every file input needs its exact SHA256: " + str(value.get("file")))
            p = Path(value["file"])
            if not p.is_file() or digest(p) != value["sha256"]:
                raise ValueError("Missing or changed bound input: " + str(p))
            if "bytes" in value and p.stat().st_size != value["bytes"]:
                raise ValueError("Byte count mismatch: " + str(p))
            result.append(binding(p))
        for v in value.values():
            input_bindings(v, result)
    elif isinstance(value, list):
        for v in value:
            input_bindings(v, result)
    return result


def safe_output(project_file, relative, spec):
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Output must be a project-relative directory without '..'")
    out = (project_file.parent / rel).resolve()
    if out == project_file.parent or not inside(out, project_file.parent):
        raise ValueError("Output must be a child of the project directory")
    blocked = [Path(x).resolve() for x in spec.get("protectedRoots", [])]
    blocked += [HERE, Path(spec["toolchain"]["supportRoot"]).resolve()]
    if any(inside(out, p) for p in blocked) or any(x.lower() in {".cdn", ".git"} for x in out.parts):
        raise ValueError("Output is in a protected source/input location")
    for inp in input_bindings(spec):
        if inside(Path(inp["file"]), out):
            raise ValueError("Output contains a bound input: " + inp["file"])
    return out


def load_project(path):
    path = Path(path).resolve()
    spec = resolve_files(read(path), path.parent)
    if spec.get("schemaVersion") != 1:
        raise ValueError("Unsupported project schemaVersion")
    project = spec.get("project", {})
    if spec.get('artReviewPolicy') not in (None, 'official-art-v1'):
        raise ValueError('Unsupported artReviewPolicy')
    if not KEY.fullmatch(str(project.get("key", ""))) or not project.get("name"):
        raise ValueError("project.key and project.name are required")
    if project.get("purpose") not in {"accepted-replay", "production", "engineering-variation"}:
        raise ValueError("Declare production, accepted-replay or engineering-variation purpose")
    pages = spec.get("nativePages", [])
    keys = [p.get("key") for p in pages]
    if not keys or len(set(keys)) != len(keys) or any(not KEY.fullmatch(str(k)) for k in keys):
        raise ValueError("Native page keys must be present, unique and path-safe")
    for p in pages:
        resources = p.get("native", {}).get("template_resources")
        if not isinstance(resources, list) or len(resources) != 4:
            raise ValueError("Every native page must bind its four resource inputs inline")
    characters = spec.get("characters", [])
    ids = [str(c["id"]) for c in characters]
    if len(ids) != len(set(ids)) or not characters:
        raise ValueError("Ordered character IDs must be present and unique")
    if any(str(c["posterPage"]) not in keys for c in characters):
        raise ValueError("Character posterPage does not exist")
    order = spec.get("preview", {}).get("pageOrder", keys)
    if set(order) != set(keys) or len(order) != len(keys):
        raise ValueError("Preview order must select every declared native page exactly once")
    for item in spec.get("featureOrder", []):
        if item.get("kind") == 0 and item.get("page") not in keys:
            raise ValueError("featureOrder refers to an unknown Movie")
        if item.get("kind") == 2 and not item.get("skillKey"):
            raise ValueError("kind2 requires an explicit skillKey")
        if item.get("kind") not in {0, 2}:
            raise ValueError("This template supports Movie/kind2 feature references")
    pay = spec.get("payment", {})
    if pay.get("mode") == "ticket-ten":
        if pay.get("cost") != 1 or pay.get("pulls") != 10 or pay.get("buttons") != ["ten"] or not isinstance(pay.get("itemId"), int) or pay["itemId"] <= 0 or not pay.get("name"):
            raise ValueError("ticket-ten requires a named item, cost1/pulls10 and only the ten button")
        shown = spec.get("preview", {}).get("overrides", {}).get("payment", {}).get("display", {})
        for k, expected in {"itemID": pay["itemId"], "name": pay["name"], "cost": 1, "pulls": 10, "pageKind": 4}.items():
            if k in shown and shown[k] != expected:
                raise ValueError("Preview payment conflicts with payment profile: " + k)
    elif pay.get("mode") != "unconfigured":
        raise ValueError("Payment mode needs a supported profile; do not guess native button rules")
    for field in ("supportRoot", "node"):
        tool = Path(spec["toolchain"][field])
        if not tool.exists():
            raise ValueError("Missing configured toolchain: " + str(tool))
    inputs = input_bindings(spec)
    if spec.get("skillPreview") is not None:
        import gacha_skills
        gacha_skills.validate(spec)
    return path, spec, {"status": "inputs_valid", "inputs": inputs, "pages": keys,
                        "characters": ids, "runtimeModified": False}


def replace_generated(value, art):
    if isinstance(value, dict):
        if "generated" in value:
            if set(value) != {"generated"} or value["generated"] not in art:
                raise ValueError("Unknown generated artwork: " + str(value))
            return binding(art[value["generated"]])
        return {k: replace_generated(v, art) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_generated(v, art) for v in value]
    return value


def build(project_file, run):
    project_file, spec, checked = load_project(project_file)
    if not KEY.fullmatch(run):
        raise ValueError("Run key must contain only letters, digits, '_' or '-'")
    out = safe_output(project_file, "builds/" + run, spec)
    if out.exists():
        raise ValueError("Refusing to overwrite an existing build: " + str(out))
    out.mkdir(parents=True)
    write(out / "input-check.json", checked)
    write(out / "project.resolved.json", spec)
    try:
        art = {}
        if spec.get("art", {}).get("artifacts"):
            from gacha_art import build_art
            build_art(spec["art"], output_dir=out / "art")
            art = {a["key"]: out / "art" / (a["key"] + ".png") for a in spec["art"]["artifacts"]}
        from gacha_native import build_native
        models, resources, native_receipts = {}, [], []
        for page in spec["nativePages"]:
            native = copy.deepcopy(page["native"])
            # An artwork binding fills only the declared texture's file/hash, never native slot IDs.
            for texture in native.get("textures", []):
                if "asset" in texture:
                    texture.update(replace_generated(texture.pop("asset"), art))
            dest = out / "native" / page["key"]
            build_native(native, support_root=Path(spec["toolchain"]["supportRoot"]), output_dir=dest)
            models[page["key"]] = dest / "model-data.json"
            resources += read(dest / "resources.json")
            native_receipts.append(str(dest / "receipt.json"))
        resources += spec.get("extraResources", [])
        for generated in spec.get("artResources", []):
            if generated.get("encoding") != "stored-png" or generated.get("key") not in art:
                raise ValueError("artResources require a generated key and stored-png encoding")
            from PIL import Image
            import wf_assets
            source = art[generated["key"]].read_bytes()
            encoded = wf_assets.png_encode(source)
            decoded = wf_assets.png_decode_stored(encoded)
            before = Image.open(io.BytesIO(source)).convert("RGBA")
            after = Image.open(io.BytesIO(decoded)).convert("RGBA")
            if before.size != after.size or before.tobytes() != after.tobytes():
                raise ValueError("Generated art failed native stored-PNG readback")
            dst = out / "encoded-art" / (generated["key"] + ".stored.png")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(encoded)
            resources.append({"logical": generated["logical"], **binding(dst)})
        logicals = [r["logical"] for r in resources]
        if len(set(logicals)) != len(logicals):
            raise ValueError("Duplicate logical resource in candidate handoff")
        for logical in logicals:
            parts = logical.replace("\\", "/").split("/")
            if any(x in {"", ".", ".."} for x in parts) or ":" in logical:
                raise ValueError("Unsafe logical resource name: " + logical)
        # Copy only the explicit closure. This is not an active CDN edge or full source tree.
        handoff = []
        for i, resource in enumerate(resources):
            input_bindings(resource)
            dst = out / "handoff" / "payload" / (str(i).zfill(3) + "-" + Path(resource["file"]).name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resource["file"], dst)
            handoff.append({"logical": resource["logical"], **binding(dst)})
        write(out / "handoff" / "resources.json", handoff)
        preview = replace_generated(copy.deepcopy(spec["preview"]), art)
        banners = [r for r in handoff if r["logical"].startswith("dynamic/gacha_list_banner/")]
        shown_banner = preview.get("overrides", {}).get("banner")
        if len(banners) != 1 or not isinstance(shown_banner, dict) or "file" not in shown_banner:
            raise ValueError("Bind one candidate list banner and the matching preview banner explicitly")
        from PIL import Image
        import wf_assets
        native_banner = Image.open(io.BytesIO(wf_assets.png_decode_stored(Path(banners[0]["file"]).read_bytes()))).convert("RGBA")
        preview_banner = Image.open(shown_banner["file"]).convert("RGBA")
        if native_banner.size != preview_banner.size or native_banner.tobytes() != preview_banner.tobytes():
            raise ValueError("Preview banner differs from the native candidate banner")
        payment_ui = preview.setdefault("overrides", {}).setdefault("payment", {})
        if spec["payment"]["mode"] == "ticket-ten":
            pay = spec["payment"]
            payment_ui.setdefault("display", {}).update(itemID=pay["itemId"], name=pay["name"], cost=pay["cost"], pulls=pay["pulls"], pageKind=4, deviceVerified=False)
        else:
            payment_ui["display"] = {"itemID": 0, "name": "模板券（支付待配置）", "cost": 1, "pulls": 10, "pageKind": 4, "deviceVerified": False}
            payment_ui["caption"] = "工程示意：按钮沿模板展示，当前项目支付尚未配置。"
        preview["schemaVersion"] = 1
        draft = spec["payment"]["mode"] == "unconfigured" or any("needs_" in v for v in spec.get("stageStatus", {}).values())
        preview["project"] = {"title": spec["project"]["name"],
                              "notice": "模板草稿 · 人物美术、技能或支付尚待适配 · 未启用游戏资源" if draft else "离线制作候选 · 未启用游戏资源",
                              "validationNotes": ["只回放原生Movie美术页；kind2技能战斗需另行原生验证。",
                                  "模板素材与支付规则的采用状态以项目清单为准。"]}
        preview["pages"] = [{"key": p["key"], "label": p.get("label", p["key"]),
                              "source": binding(models[p["key"]])} for p in spec["nativePages"]]
        # Cell rasters are bound to the freshly decoded model as well as their own SHA.
        preview["assetBindings"] = preview.get("assetBindings", []) + [binding(p) for p in sorted((out / "native").rglob("cells/*.png"))]
        preview["output"] = {"html": str(out / "review.html"), "receipt": str(out / "preview-receipt.json")}
        write(out / "preview-config.json", preview)
        completed = subprocess.run([spec["toolchain"]["node"], str(HERE / "gacha_preview.cjs"),
                                    "--config", str(out / "preview-config.json")],
                                   capture_output=True, text=True, encoding="utf-8", timeout=180, check=False)
        if completed.returncode:
            raise ValueError("Preview failed: " + completed.stderr[-4000:])
        preview_result = json.loads(completed.stdout)
        receipt = {"schemaVersion": 1, "status": "preparing_native_skills" if spec.get("skillPreview") is not None else "offline_candidate_built", "createdAt": datetime.now(timezone.utc).isoformat(),
                   "project": spec["project"], "projectInput": binding(project_file),
                   "sourceBindings": checked["inputs"],
                   "resolvedInput": binding(out / "project.resolved.json"), "review": binding(out / "review.html"),
                   "resourceManifest": binding(out / "handoff" / "resources.json"),
                   "resources": handoff, "nativeReceipts": native_receipts, "previewResult": preview_result,
                   "evidenceBindings": [binding(p) for p in [out / "input-check.json", out / "preview-config.json", out / "preview-receipt.json", *map(Path, native_receipts), *models.values()]],
                   "toolBindings": [binding(HERE / f) for f in ("gacha_pipeline.py", "gacha_native.py", "gacha_preview.cjs", "gacha_art.py")],
                   "stageStatus": spec.get("stageStatus", {}), "userAccepted": False,
                   "deviceVerified": False, "browserPlaybackVerified": False, "activated": False,
                   "databaseModified": False, "runtimeModified": False,
                   "limits": ["Template reuse does not certify a new composition, font or character skill.",
                              "HTML contains Movie art pages, not actual kind2 battle execution.",
                              "Business rows are explicitly bound inputs; new pool payment/feature rows require adaptation and tests."]}
        write(out / "BUILD.json", receipt)
        if spec.get("skillPreview") is not None:
            import gacha_skills
            return gacha_skills.start(project_file, spec, out / "BUILD.json")
        return {"status": receipt["status"], "build": str(out / "BUILD.json"), "review": str(out / "review.html"),
                "resources": len(handoff), "pages": len(models)}
    except Exception as exc:
        write(out / "FAILURE.json", {"status": "failed", "error": str(exc), "runtimeModified": False})
        raise


def verify_build(build_file):
    path = Path(build_file).resolve()
    data = read(path)
    if data.get("status") != "offline_candidate_built":
        raise ValueError("Not a successful pipeline build")
    # Verify actual artifacts and frozen source inputs. Tool hashes are historical
    # provenance: upgrading the installed tool must not invalidate an archived build.
    for field in ("projectInput", "resolvedInput", "review", "resourceManifest", "resources", "sourceBindings", "evidenceBindings"):
        input_bindings(data[field])
    resolved = read(data["resolvedInput"]["file"])
    if resolved.get("skillPreview") is not None and not data.get("skillStage"):
        raise ValueError("Configured native skills require a completed skillStage")
    for receipt in data["nativeReceipts"]:
        if not Path(receipt).is_file():
            raise ValueError("Native receipt missing: " + receipt)
        native = read(receipt)
        input_bindings(native["source_resources"])
        input_bindings(native["resources"])
    # pageBindings is descriptive metadata; inputs is the complete hash-bound list.
    preview = read(path.parent / "preview-receipt.json")
    input_bindings(preview["inputs"])
    if data.get("skillStage") is not None:
        import gacha_skills
        gacha_skills.verify(path, data)
    return path, data


def accept(build_file, expected_sha, scope):
    path, data = verify_build(build_file)
    import gacha_art_review
    gacha_art_review.require_for_accept(path, data)
    if data["review"]["sha256"] != expected_sha:
        raise ValueError("Approval must identify the exact review SHA256")
    if not scope.strip():
        raise ValueError("Describe the explicitly approved scope")
    dest = path.parent / "ACCEPTANCE.json"
    if dest.exists():
        raise ValueError("An acceptance record already exists")
    record = {"status": "user_accepted_offline_candidate", "createdAt": datetime.now(timezone.utc).isoformat(),
              "build": binding(path), "review": data["review"], "scope": scope,
              "deviceVerified": False, "activated": False, "runtimeModified": False}
    write(dest, record)
    return {"status": record["status"], "acceptance": str(dest)}


def init_project(template, destination, name, key, with_skills=False):
    _, spec, _ = load_project(template)
    if not KEY.fullmatch(key):
        raise ValueError("Invalid project key")
    dest = Path(destination).resolve()
    if dest.exists():
        raise ValueError("Refusing to overwrite an existing project")
    if any(inside(dest, Path(p).resolve()) for p in spec.get("protectedRoots", [])):
        raise ValueError("Project destination is protected")
    if any(x.lower() in {".cdn", ".git"} for x in dest.parts) or inside(dest, HERE) or inside(dest, Path(spec["toolchain"]["supportRoot"]).resolve()):
        raise ValueError("Project destination is protected")
    spec["project"] = {"name": name, "key": key, "purpose": "production"}
    spec['artReviewPolicy'] = 'official-art-v1'
    spec["stageStatus"] = {"artwork": "template_inherited_needs_composition", "business": "needs_adaptation",
                           "skills": "needs_character_review", "device": "not_tested"}
    spec["extraResources"] = []
    spec["businessInputs"] = []
    spec["skillInputs"] = []
    spec["evidence"] = []
    spec["payment"] = {"mode": "unconfigured"}
    spec["featureOrder"] = []
    # A new theme cannot inherit another pool's native scenes or visual approval.
    spec.pop("skillPreview", None)
    if with_skills:
        spec["skillPreview"] = {"schemaVersion": 1, "roles": [],
                                "limits": {"maxHtmlCharacters": 4500000, "fps": 60}, "keyframes": {}}
        spec["stageStatus"]["skills"] = "needs_native_capture_configuration"
        write(dest / "SKILLS-SETUP.json", {
            "schemaVersion": 1, "status": "needs_configuration",
            "roles": [{"roleId": c["id"], "posterPage": c["posterPage"]} for c in spec["characters"]],
            "required": ["Bind one validated native capture configuration per selected role",
                         "Declare kind2 roleId/page/skillKey entries in featureOrder",
                         "Run build, inspect generated full-UI evidence, review-skills, then resume"],
            "oldCaptureConfigurationsInherited": False,
        })
    for page in spec["nativePages"]:
        page["native"]["logical_prefix"] = "gacha/feature_movie/" + key + "/" + page["key"]
    for resource in spec.get("artResources", []):
        resource["logical"] = "dynamic/gacha_list_banner/" + key + ".png"
    write(dest / "project.json", spec)
    import gacha_art_review
    write(dest / 'ART-SETUP.json', {'schemaVersion': 1, 'policy': spec['artReviewPolicy'],
          'pageChecks': gacha_art_review.requirements(spec),
          'requiredEvidence': ['official references', 'transition full UI', 'settled full UI',
                               'final preview and native resource hashes'],
          'titleMayInnovate': True, 'preserveNativeNameplatesAndLimitedPlaques': True,
          'footerFollowsActualOfficialLayout': True, 'businessConfigurationIsSeparate': True,
          'automaticAestheticJudgment': False})
    return {"status": "draft_initialized", "project": str(dest / "project.json"),
            "notice": "Template characters/art remain visible as draft. Adapt composition, business, skills and preview payment before acceptance."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init"); p.add_argument("--template", required=True); p.add_argument("--output", required=True); p.add_argument("--name", required=True); p.add_argument("--key", required=True); p.add_argument("--with-skills", action="store_true")
    p = sub.add_parser("validate"); p.add_argument("project")
    p = sub.add_parser("build"); p.add_argument("project"); p.add_argument("--run", required=True)
    p = sub.add_parser("verify"); p.add_argument("build")
    p = sub.add_parser("review-skills"); p.add_argument("build"); p.add_argument("--review", required=True)
    p = sub.add_parser('review-art'); p.add_argument('build')
    art = p.add_mutually_exclusive_group(required=True)
    art.add_argument('--review'); art.add_argument('--template-output')
    p = sub.add_parser("resume"); p.add_argument("build"); p.add_argument("--reassemble", action="store_true")
    p = sub.add_parser("accept"); p.add_argument("build"); p.add_argument("--review-sha256", required=True); p.add_argument("--scope", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init": result = init_project(args.template, args.output, args.name, args.key, args.with_skills)
        elif args.command == "validate":
            _, _, result = load_project(args.project)
            result = {**result, "inputs": len(result["inputs"])}
        elif args.command == "build": result = build(args.project, args.run)
        elif args.command == "review-skills":
            import gacha_skills
            result = gacha_skills.review(args.build, args.review)
        elif args.command == 'review-art':
            import gacha_art_review
            result = (gacha_art_review.template(args.build, args.template_output)
                      if args.template_output else gacha_art_review.record(args.build, args.review))
        elif args.command == "resume":
            import gacha_skills
            result = gacha_skills.resume(args.build, args.reassemble)
        elif args.command == "verify":
            path, data = verify_build(args.build)
            result = {"status": "built_bytes_verified", "build": str(path), "review": data["review"], "activated": False}
        else: result = accept(args.build, args.review_sha256, args.scope)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    from gacha_guard import guarded_main
    raise SystemExit(guarded_main(main))
