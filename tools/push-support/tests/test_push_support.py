"""Independent behavior checks; fixtures remain outside any real source repository.

Run with Python's standard unittest runner. All token material is synthetic and
created deterministically in fixture repositories; no token is written to logs.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import string
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from types import SimpleNamespace
from contextlib import redirect_stdout

# Dynamic imports must not create cache files beside the implementation.
sys.dont_write_bytecode = True


TOOL = Path(__file__).resolve().parents[1] / "push_support.py"
LOCK = TOOL.with_name("scanner-lock.json")
ROOT = Path(os.environ.get("PUSH_SUPPORT_TEST_ROOT", tempfile.gettempdir())) / "push-support-tests"
STRICT_CONFIG = '[extend]\nuseDefault = true\n'


class PushSupportBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = ROOT / ("run-" + time.strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid()))
        cls.session.mkdir(parents=True, exist_ok=False)
        cls.evidence = []
        if not TOOL.is_file() or not LOCK.is_file():
            raise unittest.SkipTest("Implementation or fixed scanner lock is not yet available")

    @classmethod
    def tearDownClass(cls):
        (cls.session / "execution-summary.json").write_text(
            json.dumps(cls.evidence, indent=2), encoding="utf-8"
        )

    def setUp(self):
        self.repo = self.session / self._testMethodName
        self.repo.mkdir()
        self.env = os.environ.copy()
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_CONFIG_COUNT"):
            self.env.pop(name, None)
        self.env.update({
            "GIT_AUTHOR_NAME": "Synthetic Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Synthetic Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        })
        self.counter = 0
        self.git("init", "--initial-branch=main")
        (self.repo / ".gitleaks.toml").write_text(STRICT_CONFIG, encoding="utf-8")
        (self.repo / ".gitleaksignore").write_text("", encoding="utf-8")
        (self.repo / "readme.txt").write_text("public fixture\n", encoding="utf-8")
        self.git("add", ".gitleaks.toml", ".gitleaksignore", "readme.txt")
        self.commit("base")
        self.base = self.git("rev-parse", "HEAD").strip()
        rng = random.Random(19382745)
        self.token = "ghp_" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(36))

    def git(self, *args):
        result = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", "-C", str(self.repo), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.env,
        )
        self.assertEqual(result.returncode, 0, "Fixture Git command failed: " + result.stderr[:1000])
        return result.stdout

    def commit(self, message):
        self.counter += 1
        self.env["GIT_AUTHOR_DATE"] = self.env["GIT_COMMITTER_DATE"] = f"2026-01-01T00:00:{self.counter:02d}+00:00"
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def repository_state(self):
        return {
            "head": self.git("rev-parse", "HEAD"),
            "status": self.git("status", "--porcelain=v1", "--untracked-files=all"),
            "refs": self.git("show-ref"),
            "config_sha256": hashlib.sha256((self.repo / ".git" / "config").read_bytes()).hexdigest(),
            "index_sha256": hashlib.sha256((self.repo / ".git" / "index").read_bytes()).hexdigest(),
        }

    def invoke(self, command, *, base=None, target=None, lock=None, report_name="report.json"):
        report = self.session / (self._testMethodName + "-" + report_name)
        argv = [sys.executable, str(TOOL), command, "--repo", str(self.repo), "--lock", str(lock or LOCK)]
        if command == "scan":
            argv.extend(["--base", base or self.base, "--target", target or self.git("rev-parse", "HEAD").strip(), "--report", str(report)])
        before = self.repository_state()
        result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.env, timeout=60)
        self.assertTrue(self.token not in result.stdout + result.stderr, "CLI exposed a synthetic secret")
        self.assertEqual(self.repository_state(), before, "Helper changed fixture repository state")
        try:
            summary = json.loads(result.stdout)
        except ValueError:
            self.fail("CLI did not return JSON on stdout; exit=" + str(result.returncode))
        report_data = None
        if report.exists():
            report_text = report.read_text(encoding="utf-8-sig")
            self.assertTrue(self.token not in report_text, "Report exposed a synthetic secret")
            report_data = json.loads(report_text)
        self.evidence.append({"test": self._testMethodName, "exit": result.returncode, "summary": summary, "report": str(report) if report.exists() else None})
        return result.returncode, summary, report_data

    def add_secret(self):
        (self.repo / "historical.txt").write_text("access_token=" + self.token + "\n", encoding="utf-8")
        self.git("add", "historical.txt")
        return self.commit("synthetic sensitive fixture")

    def test_clean_new_history(self):
        (self.repo / "readme.txt").write_text("public fixture with another line\n", encoding="utf-8")
        self.git("add", "readme.txt")
        self.commit("clean update")
        code, summary, report = self.invoke("scan")
        self.assertEqual(code, 0)
        self.assertIsInstance(summary, dict)
        self.assertEqual(report, [], "Clean scan must produce an empty native findings array")

    def test_deleted_secret_in_merged_history_is_found_and_redacted(self):
        self.git("switch", "-c", "feature")
        sensitive_commit = self.add_secret()
        self.git("rm", "historical.txt")
        self.commit("remove synthetic sensitive fixture")
        self.git("switch", "main")
        (self.repo / "main.txt").write_text("mainline change\n", encoding="utf-8")
        self.git("add", "main.txt")
        self.commit("mainline divergence")
        self.git("merge", "--no-ff", "feature", "-m", "merge fixture history")
        self.assertNotIn("historical.txt", self.git("ls-tree", "-r", "--name-only", "HEAD"))
        code, summary, report = self.invoke("scan")
        self.assertEqual(code, 2, "Final-tree-only scans miss this removed merge-side secret")
        self.assertIsInstance(report, list)
        self.assertTrue(report)
        self.assertTrue(any(item.get("Commit") == sensitive_commit for item in report))
        self.assertTrue(all(item.get("Secret") != self.token for item in report))

    def test_secret_created_only_by_merge_commit_is_found(self):
        self.git("switch", "-c", "feature")
        (self.repo / "feature.txt").write_text("public feature\n", encoding="utf-8")
        self.git("add", "feature.txt")
        self.commit("clean feature")
        self.git("switch", "main")
        (self.repo / "main.txt").write_text("public mainline\n", encoding="utf-8")
        self.git("add", "main.txt")
        self.commit("clean mainline divergence")
        self.git("merge", "--no-commit", "--no-ff", "feature")
        # Neither parent has this file; only the merge resolution introduces it.
        merge_commit = self.add_secret()
        self.assertEqual(len(self.git("show", "-s", "--format=%P", merge_commit).split()), 2)
        self.git("rm", "historical.txt")
        self.commit("remove merge-only synthetic sensitive fixture")
        # Negative control reproduces the previous default-log coverage gap.
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        negative_report = self.session / "merge-default-log-negative-control.json"
        negative = subprocess.run([
            str(LOCK.parent / lock["binary_relative_path"]), "detect", "--source", str(self.repo),
            "--redact", "--exit-code=2", "--report-format=json", "--report-path=" + str(negative_report),
            "--config", str(self.repo / ".gitleaks.toml"),
            "--gitleaks-ignore-path", str(self.repo / ".gitleaksignore"),
            "--log-opts=" + self.base + ".." + self.git("rev-parse", "HEAD").strip(),
        ], capture_output=True, env=self.env, timeout=60)
        self.assertTrue(self.token.encode() not in negative.stdout + negative.stderr, "Negative control exposed synthetic secret")
        self.assertEqual(negative.returncode, 0, "Negative control should reproduce the original missed merge patch")
        self.assertEqual(json.loads(negative_report.read_text(encoding="utf-8-sig")), [])
        self.evidence.append({"test": self._testMethodName, "negative_control": "default git log without -m", "exit": 0, "finding_count": 0})
        code, summary, report = self.invoke("scan")
        self.assertEqual(code, 2, "Git default log skips merge patches and misses merge-only additions")
        self.assertTrue(any(item.get("Commit") == merge_commit for item in report))

    def test_worktree_config_cannot_silently_relax_target_rules(self):
        self.add_secret()
        (self.repo / ".gitleaks.toml").write_text(STRICT_CONFIG + '\n[allowlist]\npaths = [".*"]\n', encoding="utf-8")
        code, summary, report = self.invoke("scan")
        self.assertEqual(code, 1, "Uncommitted permissive config must require review")
        self.assertFalse(summary["scan_executed"])
        self.assertIsNone(report)

    def test_worktree_ignore_cannot_silently_suppress_target_finding(self):
        self.add_secret()
        code, summary, report = self.invoke("scan", report_name="reference.json")
        self.assertEqual(code, 2)
        fingerprints = [item["Fingerprint"] for item in report]
        self.assertTrue(fingerprints)
        (self.repo / ".gitleaksignore").write_text("\n".join(fingerprints) + "\n", encoding="utf-8")
        code, summary, report = self.invoke("scan")
        self.assertEqual(code, 1, "Uncommitted ignore must require review")
        self.assertFalse(summary["scan_executed"])
        self.assertIsNone(report)

    def test_binary_digest_mismatch_is_error(self):
        bad_lock = json.loads(LOCK.read_text(encoding="utf-8-sig"))
        # A checksum failure must happen before this non-executable is launched.
        bad_lock["binary_relative_path"] = "never-run-scanner.exe"
        (self.session / "never-run-scanner.exe").write_bytes(b"synthetic invalid executable fixture\n")
        bad_lock["binary_sha256"] = "0" * 64
        lock = self.session / "invalid-binary-lock.json"
        lock.write_text(json.dumps(bad_lock), encoding="utf-8")
        code, summary, report = self.invoke("scan", lock=lock)
        self.assertEqual(code, 1)
        diagnostic = json.dumps(summary).lower()
        self.assertTrue(any(word in diagnostic for word in ("sha256", "digest", "hash", "checksum")), diagnostic)
        spec = importlib.util.spec_from_file_location("digest_preflight_test_module", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.object(module, "run", side_effect=AssertionError("Unverified binary was executed")) as runner:
            with self.assertRaises(module.SupportError):
                module.scanner_identity(lock)
        runner.assert_not_called()

    def test_short_and_invalid_commit_ids_are_errors(self):
        for value in (self.base[:12], "z" * 40, "f" * 40):
            with self.subTest(value_kind="short" if len(value) < 40 else "invalid-or-absent"):
                code, summary, report = self.invoke("scan", base=value)
                self.assertEqual(code, 1)

    def test_equal_base_target_is_explicitly_empty(self):
        code, summary, report = self.invoke("scan", base=self.base, target=self.base)
        self.assertEqual(code, 0)
        self.assertIn("empty", json.dumps(summary).lower(), "Empty range must be distinguishable from an executed clean scan")
        self.assertFalse(summary.get("scan_executed", True))
        self.assertIsNone(report, "An empty range must not create a fake scanner report")

    def context_with_mocked_github(self, *, missing_object=False):
        self.git("remote", "add", "origin", "https://github.com/example/synthetic-fixture.git")
        spec = importlib.util.spec_from_file_location("independent_push_support_test_module", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original_run = module.run
        calls = []
        lock = json.loads(LOCK.read_text(encoding="utf-8"))

        def controlled_run(argv, **kwargs):
            if argv[0] == "gh":
                calls.append("github-query-intercepted")
                if not missing_object:
                    return subprocess.CompletedProcess(argv, 1, b"", b"synthetic API failure")
                payload = {"data": {
                    "repo": {"viewerPermission": "ADMIN", "defaultBranchRef": {"name": "main"},
                             "ref": {"target": {"oid": "f" * 40}}},
                    "scannerAction": {"object": {"oid": lock["verified_ci_action_sha"]}},
                }}
                return subprocess.CompletedProcess(argv, 0, json.dumps(payload).encode(), b"")
            self.assertIn(Path(argv[0]).name.lower(), ("git", "git.exe", "gitleaks.exe"))
            return original_run(argv, **kwargs)

        before = self.repository_state()
        with mock.patch.object(module, "run", side_effect=controlled_run), mock.patch.dict(os.environ, self.env, clear=True):
            summary, code = module.context(SimpleNamespace(repo=str(self.repo), target="HEAD", remote="origin", branch="main", lock=LOCK))
        self.assertEqual(self.repository_state(), before)
        self.assertEqual(calls, ["github-query-intercepted"], "Only the mocked combined GitHub query should run")
        self.evidence.append({"test": self._testMethodName, "exit": code, "summary": summary})
        return code, summary

    def test_failed_github_query_keeps_range_unknown(self):
        code, summary = self.context_with_mocked_github()
        self.assertEqual(code, 1)
        self.assertIsNone(summary["github"])
        self.assertIsNone(summary["range"]["new_reachable_commit_count"])
        self.assertIsNone(summary["range"]["base_object_present"])
        self.assertTrue(any(item["area"] == "github" for item in summary["errors"]))

    def test_remote_object_absent_locally_keeps_commit_count_unknown(self):
        code, summary = self.context_with_mocked_github(missing_object=True)
        self.assertEqual(code, 1)
        self.assertFalse(summary["range"]["base_object_present"])
        self.assertIsNone(summary["range"]["new_reachable_commit_count"])
        self.assertIsNone(summary["range"]["new_reachable_commits"])

    def test_all_subprocesses_disable_git_optional_writes_and_lazy_fetch(self):
        spec = importlib.util.spec_from_file_location("readonly_environment_test_module", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        caller_env = {"UNRELATED_MARKER": "retained", "GIT_OPTIONAL_LOCKS": "1", "GIT_NO_LAZY_FETCH": "0"}
        original = dict(caller_env)
        with mock.patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as runner:
            for argv in (["git", "status"], ["gitleaks.exe", "detect"]):
                module.run(argv, env=caller_env)
                actual_env = runner.call_args.kwargs["env"]
                self.assertEqual(actual_env["GIT_OPTIONAL_LOCKS"], "0")
                self.assertEqual(actual_env["GIT_NO_LAZY_FETCH"], "1")
                self.assertEqual(actual_env["UNRELATED_MARKER"], "retained")
            with mock.patch.dict(os.environ, {"GIT_OPTIONAL_LOCKS": "1", "GIT_NO_LAZY_FETCH": "0"}):
                module.run(["git", "status"])
            actual_env = runner.call_args.kwargs["env"]
            self.assertEqual(actual_env["GIT_OPTIONAL_LOCKS"], "0")
            self.assertEqual(actual_env["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(caller_env, original, "Helper must not mutate its caller's environment")
        self.evidence.append({"test": self._testMethodName, "result": "Git optional locks disabled; lazy fetch disabled for inherited and explicit environments"})

    def test_context_output_rejects_source_gitdir_and_external_common_dir(self):
        spec = importlib.util.spec_from_file_location("context_output_boundary_test_module", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        linked = self.session / "linked-worktree-output-boundary"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        # The linked worktree's actual gitdir and common dir are both outside it.
        gitdir = Path(subprocess.check_output(["git", "-C", str(linked), "rev-parse", "--absolute-git-dir"], env=self.env, text=True).strip())
        common = self.repo / ".git"
        cases = (
            (self.repo, self.repo / "forbidden-context.json"),
            (self.repo, common / "forbidden-context.json"),
            (linked, linked / "forbidden-context.json"),
            (linked, gitdir / "forbidden-context.json"),
            (linked, common / "forbidden-common-context.json"),
        )
        for repo, output in cases:
            with self.subTest(boundary="external-git-metadata" if not output.is_relative_to(repo) else "source"):
                with mock.patch.object(module, "context", return_value=({"command": "context", "errors": []}, 0)), redirect_stdout(io.StringIO()) as captured:
                    code = module.main(["context", "--repo", str(repo), "--output", str(output), "--lock", str(LOCK)])
                self.assertEqual(code, 1)
                self.assertFalse(output.exists(), "Context output wrote into a protected repository path")
                self.assertTrue(json.loads(captured.getvalue())["errors"])
        allowed = self.session / "allowed-external-context.json"
        with mock.patch.object(module, "context", return_value=({"command": "context", "errors": []}, 0)), redirect_stdout(io.StringIO()):
            code = module.main(["context", "--repo", str(linked), "--output", str(allowed), "--lock", str(LOCK)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(allowed.read_text(encoding="utf-8"))["command"], "context")
        self.evidence.append({"test": self._testMethodName, "protected_paths_rejected": len(cases), "external_output_allowed": True})

    def test_empty_range_does_not_bypass_report_path_protection(self):
        spec = importlib.util.spec_from_file_location("empty_report_boundary_test_module", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for output in (self.repo / "forbidden-report.json", self.repo / ".git" / "forbidden-report.json"):
            with self.subTest(boundary=output.parent.name):
                summary, code = module.scan(SimpleNamespace(repo=str(self.repo), base=self.base, target=self.base, lock=LOCK, report=output))
                self.assertEqual(code, 1)
                self.assertFalse(summary["scan_executed"])
                self.assertFalse(output.exists())
        self.evidence.append({"test": self._testMethodName, "empty_range_protected_report_paths_rejected": 2})


if __name__ == "__main__":
    unittest.main(verbosity=2)
