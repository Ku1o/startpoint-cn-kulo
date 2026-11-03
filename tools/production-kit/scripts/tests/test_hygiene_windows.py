"""Exercise the real CLI on synthetic Git repositories, optionally with Bash."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]
CHECKER = "tools/production-kit/scripts/check_hygiene_windows.py"
SHELL_CHECKER = "scripts/check-hygiene.sh"
LICENSE = "tools/player-save-extractor/NODE-LICENSE.txt"
EMAIL = "".join(["hygiene-fixture", "@", "gmail", ".com"])


class HygieneWindowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="sp-hygiene-windows-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo with spaces"
        self.root.mkdir()
        self.run_command(["git", "init", "-q"])
        for name in (CHECKER, SHELL_CHECKER):
            self.write(name, (REPO / name).read_bytes())

    def run_command(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args, cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=True,
        )

    def write(self, name: str, data: str | bytes, track: bool = True) -> None:
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        if track:
            self.run_command(["git", "add", "--", name])

    def check(self, expected: int, bash: bool = True) -> str:
        commands = [[sys.executable, "-B", CHECKER, "--repo", str(self.root)]]
        if bash and os.environ.get("HYGIENE_TEST_BASH"):
            commands.append([os.environ["HYGIENE_TEST_BASH"], SHELL_CHECKER, "--all"])
        before = self.run_command(["git", "status", "--porcelain", "-z"]).stdout
        output = ""
        for command in commands:
            result = subprocess.run(
                command, cwd=self.root, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            output += result.stdout + result.stderr
            self.assertEqual(result.returncode, expected, str(command) + "\n" + output)
        self.assertEqual(before, self.run_command(["git", "status", "--porcelain", "-z"]).stdout)
        return output

    def test_clean_tree_and_checker_examples(self) -> None:
        self.write("README.md", "Ordinary project documentation\n")
        self.check(0)

    def test_only_tracked_working_tree_files(self) -> None:
        self.write("local.txt", EMAIL, track=False)
        self.write("tracked.txt", "ordinary\n")
        self.check(0)
        self.write("tracked.txt", EMAIL, track=False)
        self.check(1)

    def test_unicode_filename_is_not_skipped_by_git_quoting(self) -> None:
        name = "资料/带 空格.txt"
        self.write(name, EMAIL)
        # The Bash implementation has legacy quoted-path handling. Verify the
        # portable checker separately for names that Git normally quotes.
        self.assertIn(name, self.check(1, bash=False))

    def test_private_examples_and_root_env_rejected(self) -> None:
        for name, text in (
            ("private.txt", "192.168." + "77.8"),
            ("private.txt", "/" + "Users/Fixture/file"),
            ("private.txt", EMAIL.upper()),
            (".env", "SYNTHETIC_SETTING=1"),
        ):
            with self.subTest(name=name, text=text):
                self.write(name, text)
                self.check(1)
                if name != ".env":
                    self.write(name, "ordinary\n")

    def test_exact_license_exception(self) -> None:
        original = (REPO / LICENSE).read_text("utf-8")
        self.write(LICENSE, original)
        self.check(0)
        self.write(LICENSE, original + "\n" + EMAIL.upper())
        self.check(1)
        self.write(LICENSE, original)
        attribution = next(line for line in original.splitlines()
                           if "Jean-Philippe Aumasson" in line and "@" in line)
        self.write("unapproved.txt", attribution)
        self.check(1)
        self.write("unapproved.txt", "ordinary\n")
        self.write(LICENSE, original.replace(attribution, attribution + " " + EMAIL))
        self.check(1)

    def test_checker_exclusion_is_exact_path_only(self) -> None:
        self.write("tools/production-kit/scripts/other.py", EMAIL)
        self.check(1)

    def test_cdn_and_large_file_rules(self) -> None:
        self.write("assets/asset-patch/active/example.zip", b"\0" * (1024 * 1024 + 1))
        self.write("data.json", b" " * (1024 * 1024 + 1))
        self.write("example.txt", "192.168." + "1.10")
        self.check(0)
        self.write("unexpected.bin", b"\0" * (1024 * 1024 + 1))
        self.check(1)
        self.write("unexpected.bin", b"\0")
        self.write(".cdn/cn/archive-example-diff/custom.zip", b"\0")
        self.check(1)

    def test_non_repository_is_an_error(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", str(REPO / CHECKER), "--repo", self.temporary.name],
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
