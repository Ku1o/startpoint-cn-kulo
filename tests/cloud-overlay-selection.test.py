#!/usr/bin/env python3
"""Selective overlays: isolated Git index, whole-commit scope and mixed ledger."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.dont_write_bytecode = True
TOOL = Path(__file__).resolve().parents[1] / "tools/build-cloud-overlay.py"


class SelectiveOverlayTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="overlay-selection-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Selection Fixture")
        self.git("config", "user.email", "selection@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write("src/runtime.txt", "baseline\n")
        self.write("src/optional.txt", "baseline optional\n")
        self.write("assets/asset-patch/manifest.json", '{"cdn_version":"1.4.136"}\n')
        self.write("assets/content.json", '{"content":"baseline"}\n')
        self.base = self.commit("base")
        self.write("src/runtime.txt", "repair\n")
        self.first = self.commit("first repair")
        self.write("assets/asset-patch/manifest.json", '{"cdn_version":"1.4.258"}\n')
        self.write("assets/asset-patch/active/new.zip", b"cdn archive bytes")
        self.write("assets/content.json", '{"content":"new"}\n')
        self.write("src/deferred.txt", "deferred server dependency\n")
        self.deferred = self.commit("deferred content and server feature")
        self.write("src/second.txt", b"binary repair\x00\xff")
        self.git("rm", "--", "src/optional.txt")
        self.write("tests/second.test.js", "// repair regression\n")
        self.head = self.commit("second repair with deletion")
        spec = importlib.util.spec_from_file_location("overlay_selection_under_test", TOOL)
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        self.tool.REPO = str(self.repo)
        self.tool.OUT_ROOT = str(self.root / "packages")
        self.tool.RECORD = str(self.root / "ledger.json")
        Path(self.tool.RECORD).write_text(json.dumps({"latest_delivery": {"batch": "old", "included_through_commit": self.base}}))
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps(self.plan_data()), encoding="utf-8")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.PIPE, text=True).strip()

    def write(self, name, data):
        target = self.repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode() if isinstance(data, str) else data)

    def commit(self, message):
        paths = self.git("ls-files", "--modified", "--others", "--exclude-standard").splitlines()
        if paths:
            self.git("add", "--", *paths)
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def plan_data(self, commits=None):
        return {"schema": 1, "kind": "server-fixes", "base_commit": self.base,
                "source_commit": self.head, "selected_commits": commits if commits is not None else [self.first, self.head]}

    def select(self, data=None):
        if data is not None:
            self.plan.write_text(json.dumps(data), encoding="utf-8")
        return self.tool.prepare_selection(str(self.plan), self.base, self.head)

    def invoke(self, *extra):
        output = io.StringIO()
        args = [str(TOOL), "--batch", "selected", "--base", self.base, "--source", self.head, *extra]
        with mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(output):
            self.tool.main()
        return json.loads(output.getvalue())

    def test_isolated_index_composes_patches_not_anchor_files(self):
        self.write("src/runtime.txt", "dirty worktree\n")
        self.git("add", "--", "src/runtime.txt")
        self.write("src/runtime.txt", "another dirty edit\n")
        index = (self.repo / ".git/index").read_bytes()
        status = self.git("status", "--porcelain")
        count = self.git("rev-list", "--all", "--count")
        recipe = self.select()
        tree = recipe["source_tree"]
        self.assertEqual(self.git("show", tree + ":src/runtime.txt"), "repair")
        self.assertEqual(self.tool.committed_bytes(tree, "src/second.txt"), b"binary repair\x00\xff")
        self.assertNotIn("src/deferred.txt", self.tool.tree_entries(tree))
        self.assertNotIn("src/optional.txt", self.tool.tree_entries(tree))
        self.assertEqual(self.tool.cdn_version(tree), "1.4.136")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.head)
        self.assertEqual(self.git("rev-list", "--all", "--count"), count)
        self.assertEqual((self.repo / ".git/index").read_bytes(), index)
        self.assertEqual(self.git("status", "--porcelain"), status)
        self.assertEqual(recipe, self.select())

    def test_unapproved_paths_and_partial_commits_are_rejected(self):
        with self.assertRaisesRegex(SystemExit, "未批准路径"):
            self.select(self.plan_data([self.deferred]))
        for name in ("assets/x.json", "config/x.json", "package.json", "package-lock.json", "client-patch/x.md", "scripts/x.js", "out/x.js"):
            with self.subTest(name=name):
                self.assertFalse(self.tool.validate_selection_path(name))
        for name in ("src/x.ts", "tests/x.cjs", "docs/guide.md", ".github/workflows/x.yml", ".env.example", "README.md"):
            self.assertTrue(self.tool.validate_selection_path(name))

    def test_order_duplicates_short_sha_and_unknown_fields_are_rejected(self):
        plans = [self.plan_data([self.head, self.first]), self.plan_data([self.first, self.first]),
                 self.plan_data([self.first[:8]]), self.plan_data([[]]),
                 {**self.plan_data(), "ignored": True}, {**self.plan_data(), "base_commit": self.head}]
        for data in plans:
            with self.subTest(data=data), self.assertRaises(SystemExit):
                self.select(data)

    def test_commit_from_unrelated_branch_is_rejected(self):
        self.git("checkout", "-b", "unrelated", self.base)
        self.write("src/other.txt", "other branch\n")
        other = self.commit("unrelated")
        self.git("checkout", "main")
        with self.assertRaisesRegex(SystemExit, "first-parent"):
            self.select(self.plan_data([other]))

    def test_missing_prerequisite_conflict_is_rejected_without_index_changes(self):
        self.write("src/deferred.txt", "requires deferred feature\n")
        self.head = self.commit("repair depends on deferred added file")
        before = (self.repo / ".git/index").read_bytes()
        with self.assertRaisesRegex(SystemExit, "无冲突"):
            self.select(self.plan_data([self.head]))
        self.assertEqual((self.repo / ".git/index").read_bytes(), before)

    def test_symlink_and_gitlink_are_rejected(self):
        blob = self.git("hash-object", "-w", "--stdin")
        self.git("update-index", "--add", "--cacheinfo", f"120000,{blob},src/symlink")
        self.git("commit", "-m", "symlink fixture")
        self.head = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(SystemExit, "非普通"):
            self.select(self.plan_data([self.head]))
        self.git("update-index", "--add", "--cacheinfo", f"160000,{self.base},src/submodule")
        self.git("commit", "-m", "submodule fixture")
        self.head = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(SystemExit, "非普通"):
            self.select(self.plan_data([self.head]))

    def test_package_sidecars_and_mixed_ledger_preserve_deferred_scope(self):
        result = self.invoke("--selection-plan", str(self.plan))
        with zipfile.ZipFile(result["zip"]) as archive:
            self.assertEqual(set(archive.namelist()), {"src/runtime.txt", "src/second.txt"})
            self.assertEqual(archive.read("src/runtime.txt"), b"repair\n")
        latest = json.loads(Path(self.tool.RECORD).read_text())["latest_delivery"]
        self.assertEqual(latest["included_through_commit"], self.base)
        self.assertEqual(latest["package_source_commit"], self.head)
        self.assertTrue(latest["scope_status"]["mixed"])
        self.assertEqual(latest["cdn_to"], "1.4.136")
        self.assertEqual(latest["deleted_files"], ["src/optional.txt"])
        pending = json.loads(Path(result["zip"] + ".pending.json").read_text())
        self.assertEqual(pending["cdn_from"], "1.4.136")
        self.assertEqual(pending["cdn_to"], "1.4.258")
        self.assertEqual([row["path"] for row in pending["groups"]["server"]], ["src/deferred.txt"])
        self.assertEqual([row["path"] for row in pending["groups"]["content"]], ["assets/content.json"])
        self.assertEqual(len(pending["groups"]["cdn"]), 2)
        self.assertTrue(pending["groups"]["server"][0]["source_blob"])
        recipe = json.loads(Path(result["zip"] + ".source-recipe.json").read_text())
        self.assertEqual(recipe, latest["selection"])
        self.assertEqual(self.tool.prepare_selection(result["zip"] + ".selection-plan.json", self.base, self.head), recipe)
        with self.assertRaisesRegex(SystemExit, "选择性交付"):
            self.invoke("--no-record")

    def test_default_package_retains_existing_behavior_before_selective_delivery(self):
        result = self.invoke("--no-record")
        with zipfile.ZipFile(result["zip"]) as archive:
            self.assertIn("assets/asset-patch/active/new.zip", archive.namelist())
            self.assertIn("src/deferred.txt", archive.namelist())

    def test_mixed_delivery_requires_cumulative_repairs_and_accepts_extension(self):
        previous = self.select()
        Path(self.tool.RECORD).write_text(json.dumps({"latest_delivery": {
            "batch": "previous-selected", "selection": previous, "scope_status": {"mixed": True}}}))
        previous_head = self.head
        self.write("src/next-repair.txt", "next repair\n")
        self.head = self.commit("next repair")
        with self.assertRaisesRegex(SystemExit, "遗漏或重排"):
            self.select(self.plan_data([self.head]))
        result = self.select(self.plan_data([self.first, previous_head, self.head]))
        tree = result["source_tree"]
        self.assertEqual(self.tool.committed_bytes(tree, "src/runtime.txt"), b"repair\n")
        self.assertEqual(self.tool.committed_bytes(tree, "src/second.txt"), b"binary repair\x00\xff")
        self.assertEqual(self.tool.committed_bytes(tree, "src/next-repair.txt"), b"next repair\n")
        self.assertNotIn("src/deferred.txt", self.tool.tree_entries(tree))
        self.assertEqual(self.tool.cdn_version(tree), "1.4.136")

    def test_mixed_delivery_rejects_reset_base_and_non_descendant_anchor(self):
        previous = self.select()
        Path(self.tool.RECORD).write_text(json.dumps({"latest_delivery": {"selection": previous}}))
        with self.assertRaisesRegex(SystemExit, "原始基线"):
            self.tool.validate_cumulative_selection(self.first, self.head, [self.first, self.head])
        with self.assertRaisesRegex(SystemExit, "source anchor"):
            self.tool.validate_cumulative_selection(self.base, self.first, [self.first, self.head])

    def test_helper_receives_anchor_and_effective_tree_and_checks_identity(self):
        recipe = self.select()
        tree = recipe["source_tree"]
        calls = []
        with mock.patch.object(self.tool, "uses_source_build", return_value=True), \
                mock.patch.object(self.tool.subprocess, "run") as run:
            run.side_effect = lambda command, **kwargs: (calls.append(command) or
                subprocess.CompletedProcess(command, 1, "", "intentional stop"))
            with self.assertRaisesRegex(SystemExit, "intentional stop"):
                self.tool.runtime_artifacts(self.head, self.root / "build", source_tree=tree)
        command = calls[0]
        self.assertEqual(command[command.index("--source") + 1], self.head)
        self.assertEqual(command[command.index("--source-tree") + 1], tree)

    def test_verification_directory_must_be_empty(self):
        directory = self.root / "build"
        directory.mkdir()
        (directory / "evidence.txt").write_text("preserve")
        with mock.patch.object(self.tool, "uses_source_build", return_value=True), \
                self.assertRaisesRegex(SystemExit, "空的专用目录"):
            self.tool.prepare_overlay(self.base, self.head, build_root=directory)
        self.assertEqual((directory / "evidence.txt").read_text(), "preserve")

    def test_selective_tag_annotation_records_tree_and_recipe(self):
        recipe = self.select()
        archive = self.root / "package.zip"
        archive.write_bytes(b"verified archive fixture")
        Path(str(archive) + ".source-recipe.json").write_text(json.dumps(recipe))
        tag = "release-2026.10.21-1"
        calls = []

        def fake_git(*args):
            calls.append(args)
            if args[:2] == ("ls-remote", "origin"):
                return (self.head + "\trefs/tags/" + tag + "^{}" if len(args) == 3 else
                        self.head + "\trefs/heads/main")
            return ""

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, json.dumps({"check_runs": [
                {"id": 3, "name": "hygiene", "head_sha": self.head, "status": "completed", "conclusion": "success"}]}), "")

        with mock.patch.object(self.tool, "git", side_effect=fake_git), \
                mock.patch.object(self.tool.subprocess, "run", side_effect=fake_run):
            result = self.tool.publish_release_tag(tag, self.head, self.base, str(archive),
                                                  self.tool.sha256_of(str(archive)), recipe)
        annotation = next(args[-1] for args in calls if args[:2] == ("tag", "-a"))
        self.assertIn("选择性交付", annotation)
        self.assertIn(recipe["source_tree"], annotation)
        self.assertIn(recipe["identity_sha256"], annotation)
        self.assertEqual(result["selection_tree"], recipe["source_tree"])


if __name__ == "__main__":
    unittest.main()
