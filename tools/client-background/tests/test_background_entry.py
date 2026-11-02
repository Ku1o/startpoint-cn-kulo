"""Exercise the external entry with unchanged subprocess calls in child scripts."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import quiet_process as qp
import run_background
from test_quiet_process import GUI_CHILD, assert_exited, desktop_name

ENTRY = Path(run_background.__file__)


@unittest.skipUnless(os.name == "nt", "Windows desktop/process tests")
class ExternalBackgroundEntryTests(unittest.TestCase):
    def test_context_streams_exit_and_orphan_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="CodexExternalQuiet_") as directory:
            source = ("import os,sys,json,subprocess; "
                      "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']); "
                      "print(json.dumps({'cwd':os.getcwd(),'env':os.getenv('CODEX_EXTERNAL_QUIET_TEST'),"
                      "'arg':sys.argv[1],'pid':c.pid},ensure_ascii=False),flush=True); "
                      "print('stderr 中文',file=sys.stderr,flush=True);sys.exit(7)")
            env = dict(os.environ, CODEX_EXTERNAL_QUIET_TEST="inherited", PYTHONIOENCODING="utf-8")
            result = qp.run([sys.executable, str(ENTRY), "--", sys.executable, "-u", "-c", source, "space 中文"],
                            cwd=directory, env=env, capture_output=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 7)
            data = json.loads(result.stdout)
            self.assertEqual(Path(data["cwd"]).resolve(), Path(directory).resolve())
            self.assertEqual(data["env"], "inherited")
            self.assertEqual(data["arg"], "space 中文")
            self.assertEqual(result.stderr, "stderr 中文\n")
            assert_exited(self, data["pid"])

    def test_unmodified_subprocess_gui_grandchild_inherits_desktop(self):
        before = desktop_name()
        source = ("import subprocess,sys; "
                  "r=subprocess.run([sys.executable,'-c',sys.argv[1]],capture_output=True); "
                  "sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);sys.exit(r.returncode)")
        result = qp.run([sys.executable, str(ENTRY), "--", sys.executable, "-u", "-c", source, GUI_CHILD],
                        capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["visible"])
        self.assertTrue(evidence["desktop"].startswith("CodexAIR_"))
        self.assertNotEqual(evidence["desktop"], before)
        self.assertEqual(desktop_name(), before)
        assert_exited(self, evidence["pid"])

    def test_cli_timeout_preserves_flushed_output_and_kills_tree(self):
        with tempfile.TemporaryDirectory(prefix="CodexExternalTimeout_") as directory:
            pid_file = Path(directory) / "pids.json"
            source = ("import os,sys,subprocess,time,json; "
                      "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']); "
                      "open(sys.argv[1],'w').write(json.dumps([os.getpid(),c.pid])); "
                      "print('before timeout',flush=True);print('tail stderr',file=sys.stderr,flush=True);time.sleep(120)")
            result = qp.run([sys.executable, str(ENTRY), "--timeout", "1", "--", sys.executable, "-u", "-c", source, str(pid_file)],
                            capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 124)
            self.assertEqual(result.stdout, "before timeout\n")
            self.assertIn("tail stderr\n", result.stderr)
            self.assertIn("command timed out", result.stderr)
            for pid in json.loads(pid_file.read_text()):
                assert_exited(self, pid)

    def test_entry_interrupt_returns_130(self):
        with mock.patch.object(qp, "run_gui", side_effect=KeyboardInterrupt):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(run_background.main(["--", sys.executable, "-c", "pass"]), 130)


if __name__ == "__main__":
    unittest.main(verbosity=2)
