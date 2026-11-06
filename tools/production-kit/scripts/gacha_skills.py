"""Configurable offline native-skill stages used by gacha_pipeline.

Capture, visual review and final assembly have separate receipts. This module
never edits game resources or treats geometric checks as aesthetic acceptance.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COVERAGE = {"setup", "main-action", "feedback", "rebound-and-tail"}


def core():
    import gacha_pipeline
    return gacha_pipeline


def check_capture(row, *, visual=False):
    p = core()
    p.input_bindings(row)
    native = p.read(row["receipt"]["file"])
    p.input_bindings(native["captureReceipt"])
    p.input_bindings(native["input"])
    if not native.get("passed") or str(native["input"]["role"]) != str(row["roleId"]):
        raise ValueError("Native receipt role or status differs")
    if visual:
        decision = p.read(row["visual"]["file"])
        p.input_bindings(decision)
        if decision.get("decision") != "accept" or decision["audit"] != row["audit"]:
            raise ValueError("A selected role has no matching full-UI review")
    return native


def validate(spec):
    p = core()
    cfg = spec.get("skillPreview")
    if cfg is None:
        return
    if not isinstance(cfg, dict) or cfg.get("schemaVersion") != 1:
        raise ValueError("skillPreview requires schemaVersion 1")
    if set(cfg) - {"schemaVersion", "roles", "limits", "keyframes", "notes"}:
        raise ValueError("Unknown skillPreview configuration field")
    roles = cfg.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ValueError("skillPreview.roles must contain native capture configurations")
    character_ids = {str(c["id"]) for c in spec["characters"]}
    ids = [str(r.get("roleId", "")) for r in roles]
    if len(set(ids)) != len(ids) or any(r not in character_ids for r in ids):
        raise ValueError("Skill roles must uniquely identify configured characters")
    for role in roles:
        if set(role) - {"roleId", "native", "reuseRun"}:
            raise ValueError("Unknown skill role configuration field")
        p.input_bindings(role["native"])
        if not isinstance(role["native"], dict) or set(role["native"]) - {"file", "sha256", "bytes"}:
            raise ValueError("native must bind a capture configuration file")
        reuse = role.get("reuseRun")
        if reuse is not None:
            if set(reuse) != {"build", "result"}:
                raise ValueError("reuseRun requires bound build and result files")
            p.input_bindings(reuse)
            root = Path(reuse["build"]["file"]).resolve().parent
            if Path(reuse["result"]["file"]).resolve() != root / "results/host-result.json":
                raise ValueError("Reused build and native result must identify the same run")
        import gacha_capture
        native_plan = gacha_capture.validate(Path(role["native"]["file"]))
        if str(native_plan["preview"]["roleId"]) != str(role["roleId"]):
            raise ValueError("Capture configuration role differs from the selected character")
        if native_plan["preview"]["poolId"] != spec["project"].get("poolId"):
            raise ValueError("Capture configuration pool differs from the project")
    movies = {x["key"] for x in spec["nativePages"]}
    order = spec.get("featureOrder", [])
    movie_entries = [x["page"] for x in order if x.get("kind") == 0]
    skills = [x for x in order if x.get("kind") == 2]
    skill_ids = [str(x.get("roleId", "")) for x in skills]
    if len(movie_entries) != len(movies) or set(movie_entries) != movies:
        raise ValueError("Complete featureOrder must contain every Movie exactly once")
    if len(skill_ids) != len(ids) or set(skill_ids) != set(ids):
        raise ValueError("Every skill role must occur exactly once in featureOrder")
    pages = [x.get("page") for x in order]
    if any(not isinstance(x, str) or not p.KEY.fullmatch(x) for x in pages) or len(set(pages)) != len(pages):
        raise ValueError("Feature page keys must be unique and path-safe")
    limits = cfg.get("limits", {})
    if set(limits) - {"maxHtmlCharacters", "maxVideoBytes", "width", "fps"}:
        raise ValueError("Unknown native media limit")
    if limits.get("fps", 60) != 60:
        raise ValueError("Native playback must preserve 60 fps")
    for key, value in limits.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("Media limits must be positive integers: " + key)
    keyframes = cfg.get("keyframes", {})
    if set(keyframes) - set(ids):
        raise ValueError("Keyframe selection refers to an unconfigured skill role")
    for ticks in keyframes.values():
        if not isinstance(ticks, list) or any(isinstance(t, bool) or not isinstance(t, int) or t < 0 for t in ticks):
            raise ValueError("Keyframe ticks must be nonnegative integers")
    if not isinstance(cfg.get("notes", []), list) or any(not isinstance(x, str) for x in cfg.get("notes", [])):
        raise ValueError("Skill notes must be a list of display strings")


def media(command, config, node):
    r = subprocess.run([node, str(HERE / "gacha_skill_media.cjs"), command,
                        "--config", str(config)], capture_output=True, text=True,
                       encoding="utf-8", timeout=900)
    if r.returncode:
        raise ValueError(f"Skill media {command} failed: " + (r.stderr or r.stdout)[-5000:])
    return json.loads(r.stdout)


def audit(config, role):
    r = subprocess.run([sys.executable, "-X", "utf8", "-B", str(HERE / "gacha_skill_ui.py"),
                        "--config", str(config), "--role", str(role)],
                       capture_output=True, text=True, encoding="utf-8", timeout=600)
    if r.returncode:
        raise ValueError("Full UI audit failed: " + (r.stderr or r.stdout)[-5000:])
    return json.loads(r.stdout)


def start(project_file, spec, build_file):
    """Run capture and UI audit, then stop at an explicit visual review stage."""
    p = core()
    import gacha_capture
    build_file = Path(build_file).resolve()
    build = p.read(build_file)
    if build.get("status") != "preparing_native_skills":
        raise ValueError("Native preparation requires a matching pending pipeline build")
    for field in ("projectInput", "resolvedInput", "review", "sourceBindings"):
        p.input_bindings(build[field])
    out = build_file.parent / "skills"
    out.mkdir(exist_ok=True)
    receipts = out / "receipts"
    receipts.mkdir(exist_ok=True)
    (out / "native").mkdir(exist_ok=True)
    selected = []
    for role in spec["skillPreview"]["roles"]:
        rid = str(role["roleId"])
        native_config = Path(role["native"]["file"])
        receipt = receipts / (rid + ".json")
        if receipt.exists():
            # Only complete, exact-input receipts are reusable after interruption.
            evidence = check_capture({"roleId": role["roleId"], "receipt": p.binding(receipt)})
            if evidence["input"]["config"]["sha256"] != role["native"]["sha256"]:
                raise ValueError("Pending native receipt belongs to a different input configuration")
        elif role.get("reuseRun"):
            p.input_bindings(role["reuseRun"])
            run = Path(role["reuseRun"]["build"]["file"]).resolve().parent
            evidence = gacha_capture.verify(native_config, run)
        else:
            run = out / "native" / rid
            suffix = 2
            while run.exists():
                run = out / "native" / (rid + f"-{suffix:02d}")
                suffix += 1
            evidence = gacha_capture.capture(native_config, run)
        if not evidence.get("passed") or str(evidence["input"]["role"]) != rid:
            raise ValueError("Native capture does not prove the selected role")
        if evidence["input"]["pool"] != spec["project"].get("poolId"):
            raise ValueError("Native capture pool differs from this project")
        if not receipt.exists():
            p.write(receipt, evidence)
        selected.append({"roleId": role["roleId"], "receipt": p.binding(receipt)})
    # Retain failed preparation output and resume in a fresh presentation folder.
    preparation = out / "preparation"
    number = 1
    while (preparation / f"attempt-{number:02d}").exists():
        number += 1
    presentation = preparation / f"attempt-{number:02d}"
    presentation.mkdir(parents=True)
    config = {
        "schemaVersion": 1,
        "movie": {**build["review"], "receipt": p.binding(build_file.parent / "preview-receipt.json")},
        "characters": spec["characters"], "featureOrder": spec["featureOrder"],
        "captures": selected,
        "presentation": {"notes": ["技能使用客户端离线原生录制；卡池尚未接入游戏。", *spec.get("skillPreview", {}).get("notes", [])]},
        "limits": spec["skillPreview"].get("limits", {"maxHtmlCharacters": 4500000, "fps": 60}),
        "keyframes": spec["skillPreview"].get("keyframes", {}),
        "output": {"movieDir": str(presentation / "movie"), "uiLayersDir": str(presentation / "ui-layers"),
                   "auditDir": str(presentation / "audit"), "mediaDir": str(out / "media"),
                   "html": str(build_file.parent / "review-complete.html"),
                   "receipt": str(out / "complete-receipt.json"),
                   "browserDir": str(out / "browser"), "recordDir": str(out / "record")},
    }
    config_file = presentation / "media-config.json"
    p.write(config_file, config)
    prepared = media("prepare", config_file, spec["toolchain"]["node"])
    config["movie"] = prepared["movie"]
    p.input_bindings(config["movie"])
    p.write(config_file, config)
    media("layers", config_file, spec["toolchain"]["node"])
    review_roles = []
    for selected_role in selected:
        rid = str(selected_role["roleId"])
        audit(config_file, rid)
        report_path = presentation / "audit" / rid / "UI-AUDIT.json"
        report = p.read(report_path)
        selected_role["audit"] = p.binding(report_path)
        review_roles.append({"roleId": selected_role["roleId"], "native": selected_role["receipt"],
                             "audit": p.binding(report_path),
                             "keyframeEvidence": report.get("keyframeEvidence", report.get("keyframes", [])),
                             "decision": "pending"})
    p.write(config_file, config)
    required = out / "REVIEW-REQUIRED.json"
    p.write(required, {"schemaVersion": 1, "status": "needs_visual_review",
                       "mediaConfig": p.binding(config_file), "roles": review_roles,
                       "requiredCoverage": sorted(COVERAGE),
                       "instruction": "Inspect raw/full-UI pairs and complete motion; geometry alone is not acceptance."})
    build.update(status="needs_visual_review", movieReview=build["review"],
                 skillStage={"status": "needs_visual_review", "mediaConfig": p.binding(config_file),
                             "requiredReview": p.binding(required), "captures": selected},
                 browserPlaybackVerified=False)
    p.write(build_file, build)
    return {"status": build["status"], "build": str(build_file), "reviewRequired": str(required),
            "review": str(build_file.parent / "review.html"), "activated": False}


def review(build_file, review_file):
    p = core()
    path = Path(build_file).resolve()
    build = p.read(path)
    if build.get("status") != "needs_visual_review":
        raise ValueError("Build is not waiting for full-UI review")
    stage = build["skillStage"]
    p.input_bindings(stage)
    supplied = p.resolve_files(p.read(review_file), Path(review_file).resolve().parent)
    if supplied.get("schemaVersion") != 1 or supplied.get("reviewManifest") != stage["requiredReview"]:
        raise ValueError("Visual decisions must bind the current exact review manifest")
    rows = supplied.get("roles", [])
    decisions = {str(x["roleId"]): x for x in rows}
    expected = {str(x["roleId"]): x for x in stage["captures"]}
    if len(decisions) != len(rows) or set(decisions) != set(expected):
        raise ValueError("Visual review must cover each configured skill exactly once")
    for rid, decision in decisions.items():
        if decision.get("decision") != "accept":
            raise ValueError("Rejected or pending scenes cannot be assembled: " + rid)
        if decision.get("audit") != expected[rid]["audit"]:
            raise ValueError("Visual review refers to a stale or different UI audit: " + rid)
        if set(decision.get("coverage", [])) != COVERAGE:
            raise ValueError("Review must cover setup, main action, feedback and rebound/tail")
        frames = decision.get("reviewedFrames", [])
        if not isinstance(frames, list) or any(isinstance(f, bool) or not isinstance(f, int) or f < 0 for f in frames) or len(set(frames)) < 3:
            raise ValueError("List at least three distinct actually reviewed native frames")
        if not isinstance(decision.get("observations"), str) or not decision["observations"].strip():
            raise ValueError("Visual observations are required")
        report_file = Path(expected[rid]["audit"]["file"])
        report = p.read(report_file)
        evidence = {x["battleFrame"]: x for x in report.get("keyframeEvidence", [])}
        native = check_capture(expected[rid])
        original = p.read(native["captureReceipt"]["file"])
        actual_frames = {x["frame"] for x in original["nativeFrames"]}
        reviewed_images = []
        for frame in frames:
            if frame not in actual_frames or frame not in evidence:
                raise ValueError("Reviewed frame is outside the actual capture or lacks a UI pair")
            image = evidence[frame]
            file = Path(image["comparison"])
            if not file.is_absolute():
                file = report_file.parent / file
            if not file.resolve().is_relative_to(report_file.resolve().parent):
                raise ValueError("Reviewed image must belong to this full-UI audit")
            bound_image = {"file": str(file.resolve()), "sha256": image["sha256"]}
            p.input_bindings(bound_image)
            reviewed_images.append(bound_image)
        decision["reviewedImages"] = reviewed_images
    root = path.parent / "skills/visual"
    root.mkdir()
    config = p.read(stage["mediaConfig"]["file"])
    for row in config["captures"]:
        rid = str(row["roleId"])
        dst = root / (rid + ".json")
        p.write(dst, {"schemaVersion": 1, **decisions[rid],
                      "sourceReview": p.binding(review_file), "userAccepted": False})
        row["visual"] = p.binding(dst)
    config_file = path.parent / "skills/media-reviewed.json"
    p.write(config_file, config)
    stage.update(status="visual_reviewed", reviewedConfig=p.binding(config_file),
                 visualReview=p.binding(review_file))
    build["status"] = "ready_for_skill_assembly"
    p.write(path, build)
    return {"status": build["status"], "build": str(path), "userAccepted": False, "activated": False}


def resume(build_file, reassemble=False):
    p = core()
    path = Path(build_file).resolve()
    build = p.read(path)
    if reassemble:
        if build.get("status") != "offline_candidate_built" or not build.get("skillStage"):
            raise ValueError("Reassembly requires a completed native-skill build")
        p.verify_build(path)
        history = path.parent / "skills/completed-builds"
        history.mkdir(exist_ok=True)
        prior = history / (p.digest(path) + ".json")
        if not prior.exists():
            prior.write_bytes(path.read_bytes())
        build["skillStage"].setdefault("previousCompletedBuilds", []).append(p.binding(prior))
        build["skillStage"]["status"] = "visual_reviewed"
        build["status"] = "ready_for_skill_assembly"
        p.write(path, build)
    if build.get("status") == "preparing_native_skills":
        p.input_bindings(build["resolvedInput"])
        spec = p.read(build["resolvedInput"]["file"])
        return start(Path(build["projectInput"]["file"]), spec, path)
    if build.get("status") != "ready_for_skill_assembly":
        raise ValueError("Complete native skills need a recorded full-UI review before assembly")
    p.input_bindings(build["skillStage"])
    p.input_bindings(build["projectInput"])
    p.input_bindings(build["resolvedInput"])
    spec = p.read(build["resolvedInput"]["file"])
    p.input_bindings(build["sourceBindings"])
    config_file = Path(build["skillStage"]["reviewedConfig"]["file"])
    config = p.read(config_file)
    p.input_bindings(config)
    for row in config["captures"]:
        check_capture(row, visual=True)
    node = spec["toolchain"]["node"]
    attempt_root = path.parent / "skills/assembly"
    number = 1
    while (attempt_root / f"attempt-{number:02d}").exists():
        number += 1
    attempt = attempt_root / f"attempt-{number:02d}"
    attempt.mkdir(parents=True)
    config = copy.deepcopy(config)
    caption = spec.get("preview", {}).get("overrides", {}).get("payment", {}).get("caption")
    if caption:
        notes = config.setdefault("presentation", {}).setdefault("notes", [])
        if caption not in notes:
            notes.append(caption)
    config["output"].update(mediaDir=str(attempt / "media"), html=str(attempt / "review.html"),
                            receipt=str(attempt / "complete-receipt.json"),
                            browserDir=str(attempt / "browser"), recordDir=str(attempt / "record"))
    config_file = attempt / "media-config.json"
    p.write(config_file, config)
    try:
        media("encode", config_file, node)
        media("assemble", config_file, node)
        media("browser", config_file, node)
        media("record", config_file, node)
    except Exception as exc:
        failure = attempt / "FAILURE.json"
        p.write(failure, {"status": "failed", "error": str(exc), "config": p.binding(config_file)})
        build["skillStage"].setdefault("failedAssemblyAttempts", []).append(p.binding(failure))
        p.write(path, build)
        raise
    output = config["output"]
    final_html = Path(output["html"])
    receipt_path = Path(output["receipt"])
    browser_path = Path(output["browserDir"]) / "browser-receipt.json"
    record_path = Path(output["recordDir"]) / "browser-receipt.json"
    browser, recording = p.read(browser_path), p.read(record_path)
    final_sha = p.digest(final_html)
    if browser["sourceSHA256"] != final_sha or recording["sourceSHA256"] != final_sha:
        raise ValueError("Browser/recording evidence belongs to another HTML")
    if browser["exceptions"] or browser["network"] or recording["exceptions"] or recording["network"]:
        raise ValueError("Offline preview made external requests or raised an error")
    stage = build["skillStage"]
    stage.update(status="offline_native_full_ui_verified",
                 assembledConfig=p.binding(config_file),
                 finalReceipt=p.binding(receipt_path),
                 browser=p.binding(browser_path), recording=p.binding(record_path))
    build.update(status="offline_candidate_built", review=p.binding(final_html),
                 browserPlaybackVerified=True)
    build["evidenceBindings"] += [p.binding(receipt_path), p.binding(browser_path), p.binding(record_path)]
    build["toolBindings"] += [p.binding(f) for f in [HERE / "gacha_skills.py", HERE / "gacha_capture.py",
                            HERE / "gacha_skill_media.cjs", HERE / "gacha_skill_ui.py"]]
    build["toolBindings"] += [p.binding(f) for folder in [HERE / "gacha_capture", HERE / "gacha_skill_media"]
                             for f in sorted(folder.rglob("*"))
                             if f.is_file() and f.suffix in {".py", ".as", ".js", ".cjs", ".json"}]
    build["limits"] = [x for x in build["limits"] if "HTML contains Movie art pages" not in x]
    build["limits"] += ["Native captures require the configured client adapter and exact character inputs.",
                         "Full-UI review and desktop playback do not establish mobile or user acceptance."]
    p.write(path, build)
    verify(path, build)
    return {"status": build["status"], "build": str(path), "review": str(final_html),
            "recording": str(record_path), "activated": False}


def verify(path, data):
    p = core()
    stage = data.get("skillStage")
    if stage is None:
        return
    if stage.get("status") != "offline_native_full_ui_verified":
        raise ValueError("Native skills have not completed capture, full-UI review and assembly")
    p.input_bindings(stage)
    config = p.read(stage.get("assembledConfig", stage["reviewedConfig"])["file"])
    p.input_bindings(config)
    for row in config["captures"]:
        check_capture(row, visual=True)
    browser = p.read(stage["browser"]["file"])
    if browser["sourceSHA256"] != data["review"]["sha256"] or browser["exceptions"] or browser["network"]:
        raise ValueError("Final skill playback evidence mismatch")
