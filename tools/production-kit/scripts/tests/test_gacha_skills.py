"""Offline stage-gate regressions. Native capture and media are fixture boundaries."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gacha_capture as capture
import gacha_pipeline as pipeline
import gacha_skills as skills


class SkillPipelineTests(unittest.TestCase):
    role = 169989
    pool = 990006
    reviewed_frames = [110, 171, 240]

    def setUp(self):
        output = os.environ.get("GACHA_SKILL_TEST_OUTPUT")
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="gacha-skill-", dir=output)))
        self.config = self.root / "native.json"
        self.manifest = self.root / "native-manifest.json"
        pipeline.write(self.manifest, {"files": []})
        pipeline.write(self.config, {
            "preview": {"roleId": self.role, "poolId": self.pool},
            "assetManifest": pipeline.binding(self.manifest),
        })
        self.enterContext(patch.object(capture, "validate", side_effect=self.validate_capture))
        movie_input = self.root / "movie-resource.txt"
        movie_input.write_text("Movie input", encoding="utf-8")
        self.spec = {
            "schemaVersion": 1,
            "project": {"key": "test_pool", "name": "Test pool", "purpose": "production", "poolId": self.pool},
            "toolchain": {"supportRoot": str(Path(__file__).parent), "node": sys.executable},
            "nativePages": [{"key": "cover", "native": {"template_resources": [pipeline.binding(movie_input)] * 4}}],
            "characters": [{"id": self.role, "posterPage": "cover"}],
            "payment": {"mode": "unconfigured"},
            "featureOrder": [{"kind": 0, "page": "cover"},
                             {"kind": 2, "page": "skill-169989", "roleId": self.role, "skillKey": "skill_neftim"}],
            "skillPreview": {"schemaVersion": 1, "roles": [{"roleId": self.role, "native": pipeline.binding(self.config)}]},
        }
        self.project = self.root / "project.json"
        self.build = self.root / "build" / "BUILD.json"
        self.review = self.root / "visual-review.json"
        self.media_calls = []

    def validate_capture(self, file):
        config = pipeline.read(file)
        pipeline.input_bindings(config)
        return {"preview": config["preview"], "configSHA256": pipeline.digest(file)}

    def capture_role(self, config, run):
        if not run.parent.is_dir() or run.exists():
            raise ValueError("Capture requires a new directory in an existing workspace")
        native_config = pipeline.read(config)
        preview = native_config["preview"]
        result = run / "results/host-result.json"
        frames = [{"tick": n - 1, "frame": n, "replayFrame": n} for n in range(1, 322)]
        frames.append({**frames[-1], "tick": 321})
        pipeline.write(result, {"passed": True, "nativeFrames": frames})
        return {"schemaVersion": 1, "kind": "native-gacha-capture", "run": str(run), "passed": True,
                "input": {"role": preview["roleId"], "pool": preview["poolId"], "sourceWindow": [0, 320],
                          "config": pipeline.binding(config), "assetManifest": native_config["assetManifest"]},
                "captureReceipt": pipeline.binding(result), "trace": {"nativeFinish": 321, "engineWindow": [1, 321]},
                "pngs": {"count": 322}}

    def audit_role(self, config, role):
        directory = Path(pipeline.read(config)["output"]["auditDir"]) / role
        report = directory / "UI-AUDIT.json"
        frames = []
        for frame in self.reviewed_frames:
            screenshot = directory / f"frame-{frame}.webp"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (8, 8), (frame, 32, 48)).save(screenshot, "WEBP")
            frames.append({"tick": frame - 1, "battleFrame": frame, "comparison": screenshot.name,
                           "sha256": pipeline.digest(screenshot)})
        pipeline.write(report, {"roleId": int(role), "kind": "native-gacha-full-ui-audit", "keyframeEvidence": frames})
        return {"passed": True}

    def media_stage(self, command, file, node):
        self.media_calls.append(command)
        config = pipeline.read(file)
        output = config["output"]
        if command == "prepare":
            return {"movie": config["movie"]}
        if command == "assemble":
            html = Path(output["html"])
            html.write_text("<html>Mocked offline preview</html>", encoding="utf-8")
            pipeline.write(output["receipt"], {"passed": True, "html": pipeline.binding(html)})
        if command in {"browser", "record"}:
            directory = Path(output["browserDir" if command == "browser" else "recordDir"])
            pipeline.write(directory / "browser-receipt.json", {
                "sourceSHA256": pipeline.digest(output["html"]), "exceptions": [], "network": [],
            })
        return {"passed": True}

    def load(self, spec=None):
        pipeline.write(self.project, self.spec if spec is None else spec)
        return pipeline.load_project(self.project)

    def prepare_pending(self):
        _, spec, validated = self.load()
        out = self.build.parent
        out.mkdir()
        movie = out / "review.html"
        movie.write_text("<html>Mocked Movie</html>", encoding="utf-8")
        resolved = out / "project.resolved.json"
        pipeline.write(resolved, spec)
        pipeline.write(out / "preview-receipt.json", {"inputs": [pipeline.binding(movie)]})
        resources = out / "handoff/resources.json"
        pipeline.write(resources, {"resources": []})
        pipeline.write(self.build, {
            "status": "preparing_native_skills", "projectInput": pipeline.binding(self.project),
            "resolvedInput": pipeline.binding(resolved), "review": pipeline.binding(movie),
            "resourceManifest": pipeline.binding(resources), "resources": [], "nativeReceipts": [],
            "sourceBindings": validated["inputs"], "evidenceBindings": [], "toolBindings": [], "limits": [],
        })
        return spec

    def start(self):
        spec = self.prepare_pending()
        self.capture_mock = self.enterContext(patch.object(capture, "capture", side_effect=self.capture_role))
        self.enterContext(patch.object(skills, "audit", side_effect=self.audit_role))
        self.enterContext(patch.object(skills, "media", side_effect=self.media_stage))
        self.assertEqual(skills.start(self.project, spec, self.build)["status"], "needs_visual_review")
        self.capture_mock.assert_called_once()
        self.assertEqual(self.media_calls, ["prepare", "layers"])

    def visual_input(self):
        stage = pipeline.read(self.build)["skillStage"]
        return {"schemaVersion": 1, "reviewManifest": stage["requiredReview"], "roles": [{
            "roleId": self.role, "decision": "accept", "audit": stage["captures"][0]["audit"],
            "coverage": sorted(skills.COVERAGE), "reviewedFrames": self.reviewed_frames.copy(),
            "observations": "Setup, main action, hit feedback and final rebound are visible.",
        }]}

    def apply_visual_review(self):
        pipeline.write(self.review, self.visual_input())
        return skills.review(self.build, self.review)

    def test_feature_order_rejects_wrong_or_duplicate_roles(self):
        self.load()
        for invalid in ("wrong-role", "same-role-twice", "missing-movie", "duplicate-movie"):
            with self.subTest(invalid=invalid):
                spec = deepcopy(self.spec)
                order = spec["featureOrder"]
                if invalid == "wrong-role":
                    order[1]["roleId"] = 123
                elif invalid == "same-role-twice":
                    order.append({**order[1], "page": "second-skill"})
                elif invalid == "missing-movie":
                    del order[0]
                else:
                    order.append(deepcopy(order[0]))
                with self.assertRaises(ValueError):
                    self.load(spec)

    def test_feature_order_rejects_duplicate_or_path_unsafe_pages(self):
        for page in ("cover", "../skill"):
            with self.subTest(page=page):
                spec = deepcopy(self.spec)
                spec["featureOrder"][1]["page"] = page
                with self.assertRaises(ValueError):
                    self.load(spec)

    def test_feature_order_rejects_missing_or_nonstring_page(self):
        for page in (None, 123, True, [], {}):
            with self.subTest(page=page):
                spec = deepcopy(self.spec)
                spec["featureOrder"][1]["page"] = page
                with self.assertRaises(ValueError):
                    self.load(spec)

    def test_native_config_must_match_project_role_and_pool(self):
        for field in ("roleId", "poolId"):
            with self.subTest(field=field):
                config = pipeline.read(self.config)
                prior = deepcopy(config)
                config["preview"][field] = 123
                pipeline.write(self.config, config)
                spec = deepcopy(self.spec)
                spec["skillPreview"]["roles"][0]["native"] = pipeline.binding(self.config)
                with self.assertRaises(ValueError):
                    self.load(spec)
                pipeline.write(self.config, prior)

    def test_init_discards_template_skill_preview_and_approval(self):
        self.load()
        draft = pipeline.init_project(self.project, self.root / "draft", "Next pool", "next_pool")
        spec = pipeline.read(draft["project"])
        self.assertNotIn("skillPreview", spec)
        self.assertEqual(spec["skillInputs"], [])
        self.assertEqual(spec["evidence"], [])
        self.assertEqual(spec["featureOrder"], [])
        self.assertEqual(spec["stageStatus"]["skills"], "needs_character_review")
        self.assertIn("skillPreview", pipeline.read(self.project))

    def test_init_with_skills_cli_requires_fresh_native_configuration(self):
        self.load()
        old_template = pipeline.binding(self.project)
        draft = self.root / "draft-with-skills"
        output = StringIO()
        with patch.object(sys, "argv", ["gacha_pipeline", "init", "--template", str(self.project),
                                         "--output", str(draft), "--name", "Next pool", "--key", "next_pool",
                                         "--with-skills"]), redirect_stdout(output):
            self.assertEqual(pipeline.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "draft_initialized")
        project = draft / "project.json"
        spec = pipeline.read(project)
        setup = pipeline.read(draft / "SKILLS-SETUP.json")
        self.assertEqual(spec["skillPreview"]["roles"], [])
        self.assertEqual(spec["featureOrder"], [])
        self.assertEqual(spec["stageStatus"]["skills"], "needs_native_capture_configuration")
        self.assertEqual(setup["status"], "needs_configuration")
        self.assertEqual(setup["roles"], [{"roleId": self.role, "posterPage": "cover"}])
        self.assertFalse(setup["oldCaptureConfigurationsInherited"])
        self.assertEqual(pipeline.binding(self.project), old_template)
        error = StringIO()
        with patch.object(sys, "argv", ["gacha_pipeline", "validate", str(project)]), redirect_stderr(error):
            self.assertEqual(pipeline.main(), 1)
        self.assertIn("skillPreview.roles", json.loads(error.getvalue())["error"])
        with self.assertRaisesRegex(ValueError, "skillPreview.roles"):
            pipeline.build(project, "no-movie-only-fallback")
        self.assertFalse((draft / "builds").exists())

    def test_pending_capture_cannot_resume_or_accept(self):
        self.start()
        with self.assertRaises(ValueError):
            skills.resume(self.build)
        with self.assertRaises(ValueError):
            pipeline.accept(self.build, pipeline.read(self.build)["review"]["sha256"], "Test approval")
        self.assertFalse((self.build.parent / "ACCEPTANCE.json").exists())
        self.assertEqual(self.media_calls, ["prepare", "layers"])

    def test_missing_and_pending_visual_decisions_are_rejected(self):
        self.start()
        for state in ("missing", "pending"):
            with self.subTest(state=state):
                draft = self.visual_input()
                if state == "missing":
                    draft["roles"] = []
                else:
                    draft["roles"][0]["decision"] = state
                pipeline.write(self.review, draft)
                with self.assertRaises(ValueError):
                    skills.review(self.build, self.review)
        self.assertEqual(pipeline.read(self.build)["status"], "needs_visual_review")

    def test_review_requires_current_manifest_and_audit(self):
        self.start()
        older = self.root / "older.json"
        pipeline.write(older, {"status": "stale"})
        for field in ("reviewManifest", "audit"):
            with self.subTest(field=field):
                draft = self.visual_input()
                target = draft if field == "reviewManifest" else draft["roles"][0]
                target[field] = pipeline.binding(older)
                pipeline.write(self.review, draft)
                with self.assertRaises(ValueError):
                    skills.review(self.build, self.review)

    def test_review_rejects_impossible_native_frame_claims(self):
        self.start()
        for frames in ([999998, 999999, 1000000], [110, 171, []], [110, 171, 241]):
            with self.subTest(frames=frames):
                draft = self.visual_input()
                draft["roles"][0]["reviewedFrames"] = frames
                pipeline.write(self.review, draft)
                with self.assertRaises(ValueError):
                    skills.review(self.build, self.review)

    def test_visual_review_requires_text_observations(self):
        self.start()
        for observations in (None, 123, " "):
            with self.subTest(observations=observations):
                draft = self.visual_input()
                draft["roles"][0]["observations"] = observations
                pipeline.write(self.review, draft)
                with self.assertRaises(ValueError):
                    skills.review(self.build, self.review)

    def test_review_rejects_tampered_audit_or_review_manifest(self):
        self.start()
        draft = self.visual_input()
        pipeline.write(self.review, draft)
        for evidence in (draft["roles"][0]["audit"], draft["reviewManifest"]):
            with self.subTest(file=evidence["file"]):
                path = Path(evidence["file"])
                prior = path.read_bytes()
                path.write_bytes(prior + b" ")
                try:
                    with self.assertRaises(ValueError):
                        skills.review(self.build, self.review)
                finally:
                    path.write_bytes(prior)

    def test_review_rejects_tampered_bound_comparison_image(self):
        self.start()
        draft = self.visual_input()
        pipeline.write(self.review, draft)
        audit = Path(draft["roles"][0]["audit"]["file"])
        image = audit.parent / pipeline.read(audit)["keyframeEvidence"][0]["comparison"]
        image.write_bytes(image.read_bytes() + b"tampered")
        with self.assertRaises(ValueError):
            skills.review(self.build, self.review)

    def test_resume_checks_review_and_source_before_media(self):
        self.start()
        self.apply_visual_review()
        for path in (self.review, self.config, Path(pipeline.read(self.build)["resolvedInput"]["file"])):
            with self.subTest(file=path):
                prior = path.read_bytes()
                path.write_bytes(prior + b" ")
                try:
                    with self.assertRaises(ValueError):
                        skills.resume(self.build)
                finally:
                    path.write_bytes(prior)
        self.assertEqual(self.media_calls, ["prepare", "layers"])

    def test_skill_project_cannot_accept_movie_only_build_status(self):
        self.start()
        build = pipeline.read(self.build)
        del build["skillStage"]
        build["status"] = "offline_candidate_built"
        for incomplete in (build, {**build, "skillStage": {}}):
            with self.subTest(stage=incomplete.get("skillStage")):
                pipeline.write(self.build, incomplete)
                with self.assertRaises(ValueError):
                    pipeline.accept(self.build, build["review"]["sha256"], "Test approval")
                self.assertFalse((self.build.parent / "ACCEPTANCE.json").exists())

    def test_visual_review_is_distinct_from_final_acceptance(self):
        self.start()
        reviewed = self.apply_visual_review()
        self.assertEqual(reviewed["status"], "ready_for_skill_assembly")
        self.assertFalse(reviewed["userAccepted"])
        with self.assertRaises(ValueError):
            pipeline.accept(self.build, pipeline.read(self.build)["review"]["sha256"], "Test approval")
        final = skills.resume(self.build)
        self.assertEqual(final["status"], "offline_candidate_built")
        self.assertEqual(self.media_calls, ["prepare", "layers", "encode", "assemble", "browser", "record"])
        sha = pipeline.digest(final["review"])
        with self.assertRaises(ValueError):
            pipeline.accept(self.build, "0" * 64, "Test approval")
        accepted = pipeline.accept(self.build, sha, "Offline fixture")
        acceptance = pipeline.read(accepted["acceptance"])
        self.assertEqual(acceptance["review"]["sha256"], sha)
        self.assertFalse(acceptance["deviceVerified"])
        self.assertFalse(acceptance["activated"])

    def test_resume_rejects_changed_native_source_manifest(self):
        self.start()
        self.apply_visual_review()
        self.manifest.write_bytes(self.manifest.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            skills.resume(self.build)
        self.assertEqual(self.media_calls, ["prepare", "layers"])

    def test_changed_review_image_is_rejected_before_assembly(self):
        self.start()
        self.apply_visual_review()
        audit = Path(self.visual_input()["roles"][0]["audit"]["file"])
        image = audit.parent / pipeline.read(audit)["keyframeEvidence"][0]["comparison"]
        image.write_bytes(image.read_bytes() + b"tampered")
        with self.assertRaises(ValueError):
            skills.resume(self.build)
        self.assertEqual(self.media_calls, ["prepare", "layers"])

    def test_final_html_change_invalidates_acceptance(self):
        self.start()
        self.apply_visual_review()
        final = skills.resume(self.build)
        html = Path(final["review"])
        sha = pipeline.digest(html)
        html.write_bytes(html.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            pipeline.accept(self.build, sha, "Test approval")
        self.assertFalse((self.build.parent / "ACCEPTANCE.json").exists())

    def test_retry_after_browser_failure_uses_a_fresh_assembly_attempt(self):
        self.start()
        self.apply_visual_review()

        def fail_browser(command, file, node):
            if command == "browser":
                self.media_calls.append(command)
                raise ValueError("Mock browser failure")
            return self.media_stage(command, file, node)

        with patch.object(skills, "media", side_effect=fail_browser):
            with self.assertRaisesRegex(ValueError, "Mock browser failure"):
                skills.resume(self.build)
        self.assertEqual(pipeline.read(self.build)["status"], "ready_for_skill_assembly")
        first = self.build.parent / "skills/assembly/attempt-01"
        failure = pipeline.binding(first / "FAILURE.json")
        old_html = pipeline.binding(first / "review.html")
        final = skills.resume(self.build)
        second = first.parent / "attempt-02"
        self.assertEqual(Path(final["review"]), second / "review.html")
        self.assertEqual(pipeline.binding(first / "FAILURE.json"), failure)
        self.assertEqual(pipeline.binding(first / "review.html"), old_html)
        self.assertEqual(pipeline.read(self.build)["skillStage"]["failedAssemblyAttempts"], [failure])
        self.capture_mock.assert_called_once()
        self.assertEqual(self.media_calls, ["prepare", "layers", "encode", "assemble", "browser",
                                            "encode", "assemble", "browser", "record"])

    def test_pending_capture_recovery_reuses_success_and_retries_in_new_directory(self):
        second_role = 149999
        second_config = self.root / "second-native.json"
        config = pipeline.read(self.config)
        config["preview"]["roleId"] = second_role
        pipeline.write(second_config, config)
        self.spec["characters"].append({"id": second_role, "posterPage": "cover"})
        self.spec["skillPreview"]["roles"].append({"roleId": second_role, "native": pipeline.binding(second_config)})
        self.spec["featureOrder"].append({"kind": 2, "page": "skill-149999", "roleId": second_role, "skillKey": "second"})
        spec = self.prepare_pending()
        native = self.build.parent / "skills/native"

        def interrupted_capture(config_path, run):
            if run.name == str(second_role):
                pipeline.write(run / "partial.json", {"status": "interrupted"})
                raise ValueError("Mock native interruption")
            return self.capture_role(config_path, run)

        with patch.object(capture, "capture", side_effect=interrupted_capture) as record, \
             patch.object(skills, "audit", side_effect=self.audit_role), \
             patch.object(skills, "media", side_effect=self.media_stage):
            with self.assertRaisesRegex(ValueError, "Mock native interruption"):
                skills.start(self.project, spec, self.build)
            self.assertEqual(pipeline.read(self.build)["status"], "preparing_native_skills")
            receipt = native.parent / "receipts" / f"{self.role}.json"
            first = pipeline.binding(receipt)
            partial = pipeline.binding(native / str(second_role) / "partial.json")
            resumed = skills.resume(self.build)
        self.assertEqual(resumed["status"], "needs_visual_review")
        self.assertEqual(pipeline.binding(receipt), first)
        self.assertEqual(pipeline.binding(Path(partial["file"])), partial)
        self.assertEqual([call.args[1].name for call in record.call_args_list],
                         [str(self.role), str(second_role), f"{second_role}-02"])
        selected = pipeline.read(self.build)["skillStage"]["captures"]
        self.assertEqual([row["roleId"] for row in selected], [self.role, second_role])
        self.assertEqual(self.media_calls, ["prepare", "layers"])

    def test_completed_native_build_reassembly_verifies_and_preserves_original(self):
        caption = "十连抽消耗专用扭蛋券 ×1。卡池尚未接入游戏，预览不会消耗道具。"
        self.spec["payment"] = {"mode": "ticket-ten", "itemId": 999023, "name": "专用扭蛋券",
                                "cost": 1, "pulls": 10, "buttons": ["ten"]}
        self.spec["preview"] = {"overrides": {"payment": {"caption": caption}}}
        self.start()
        self.apply_visual_review()
        first = skills.resume(self.build)
        old_html = Path(first["review"])
        old_html_bytes = old_html.read_bytes()
        old_build_bytes = self.build.read_bytes()
        old_build_sha = pipeline.digest(self.build)
        history = self.build.parent / "skills/completed-builds"
        attempt = old_html.parent.parent / "attempt-02"
        commands_before_reassembly = self.media_calls.copy()
        args = ["gacha_pipeline", "resume", str(self.build), "--reassemble"]

        with patch.object(pipeline, "verify_build", wraps=pipeline.verify_build) as verify:
            old_html.write_bytes(old_html_bytes + b"tampered")
            error = StringIO()
            with patch.object(sys, "argv", args), redirect_stderr(error):
                self.assertEqual(pipeline.main(), 1)
            self.assertIn("changed bound input", json.loads(error.getvalue())["error"])
            self.assertFalse(history.exists())
            self.assertFalse(attempt.exists())
            self.assertEqual(self.build.read_bytes(), old_build_bytes)
            self.assertEqual(self.media_calls, commands_before_reassembly)

            old_html.write_bytes(old_html_bytes)
            output = StringIO()
            with patch.object(sys, "argv", args), redirect_stdout(output):
                self.assertEqual(pipeline.main(), 0)
            self.assertEqual([call.args for call in verify.call_args_list], [(self.build,), (self.build,)])

        reassembled = json.loads(output.getvalue())
        self.assertEqual(reassembled["status"], "offline_candidate_built")
        self.assertEqual(Path(reassembled["review"]), attempt / "review.html")
        self.assertEqual(old_html.read_bytes(), old_html_bytes)
        saved = history / f"{old_build_sha}.json"
        self.assertEqual(saved.read_bytes(), old_build_bytes)
        stage = pipeline.read(self.build)["skillStage"]
        self.assertEqual(stage["previousCompletedBuilds"], [pipeline.binding(saved)])
        media_config = pipeline.read(stage["assembledConfig"]["file"])
        self.assertEqual(media_config["presentation"]["notes"].count(caption), 1)
        self.assertEqual(self.media_calls[len(commands_before_reassembly):], ["encode", "assemble", "browser", "record"])
        self.capture_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
