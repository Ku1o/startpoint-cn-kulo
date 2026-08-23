from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import wf_gui as gui
import wf_live_cdn as live


class GuiPendingStatusCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = self.root / "production" / "upload"
        self.pending_file = self.root / "work" / "sync_pending.json"
        self.store.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write(root: Path, relative: str, raw: bytes) -> None:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    def _pending(self, items: list[str]) -> None:
        self.pending_file.parent.mkdir(parents=True, exist_ok=True)
        self.pending_file.write_text(json.dumps(items), encoding="utf-8")

    def test_reconcile_removes_live_identical_and_keeps_real_differences(self) -> None:
        same = "aa/same"
        medium = "medium:bb/different"
        new = "cc/new"
        self._write(self.store, same, b"same")
        self._write(self.store.parent / "medium_upload", "bb/different", b"local")
        self._write(self.store, new, b"new")
        self._pending([same, medium, new])

        def read_relative(relative: str, *, roots: tuple[str, ...]):
            if relative == same:
                self.assertEqual(("common",), roots)
                return SimpleNamespace(data=b"same")
            if relative == "bb/different":
                self.assertEqual(("medium",), roots)
                return SimpleNamespace(data=b"server")
            raise live.LiveCdnEntryMissing(relative)

        with (
            mock.patch.object(gui, "TARGET_STORE", self.store),
            mock.patch.object(gui, "PENDING_FILE", self.pending_file),
            mock.patch.object(live, "enabled_for_store", return_value=True),
            mock.patch.object(live, "read_relative", side_effect=read_relative),
        ):
            status = gui.pending_status(reconcile=True)

        self.assertTrue(status["live_checked"])
        self.assertEqual([same], status["reconciled"])
        self.assertEqual([medium, new], status["pending"])
        self.assertEqual(
            [medium, new],
            json.loads(self.pending_file.read_text(encoding="utf-8")),
        )

    def test_missing_local_or_live_read_error_is_retained_fail_closed(self) -> None:
        missing = "aa/missing"
        unreadable = "bb/unreadable"
        self._write(self.store, unreadable, b"local")
        self._pending([missing, unreadable])

        with (
            mock.patch.object(gui, "TARGET_STORE", self.store),
            mock.patch.object(gui, "PENDING_FILE", self.pending_file),
            mock.patch.object(live, "enabled_for_store", return_value=True),
            mock.patch.object(live, "read_relative", side_effect=live.LiveCdnError("broken")),
        ):
            status = gui.pending_status(reconcile=True)

        self.assertEqual([missing, unreadable], status["pending"])
        self.assertEqual([], status["reconciled"])
        self.assertEqual(2, len(status["errors"]))
        self.assertEqual(
            [missing, unreadable],
            json.loads(self.pending_file.read_text(encoding="utf-8")),
        )

    def test_standalone_store_keeps_pending_without_claiming_live_check(self) -> None:
        item = "aa/local"
        self._pending([item, item, ""])
        with (
            mock.patch.object(gui, "TARGET_STORE", self.store),
            mock.patch.object(gui, "PENDING_FILE", self.pending_file),
            mock.patch.object(live, "enabled_for_store", return_value=False),
            mock.patch.object(live, "read_relative") as read_relative,
        ):
            status = gui.pending_status(reconcile=True)

        self.assertFalse(status["live_checked"])
        self.assertEqual([item], status["pending"])
        read_relative.assert_not_called()

    def test_publish_noops_after_all_pending_items_are_reconciled(self) -> None:
        state = {
            "pending": [],
            "reconciled": ["aa/old"],
            "errors": [],
            "live_checked": True,
            "raw_count": 1,
        }
        with (
            mock.patch.object(gui, "pending_status", return_value=state),
            mock.patch.object(gui.subprocess, "run") as run,
        ):
            result = gui.run_publish()

        self.assertFalse(result["ok"])
        self.assertIn("已清理 1 条", result["log"])
        run.assert_not_called()

    def test_publish_is_blocked_when_live_comparison_has_errors(self) -> None:
        state = {
            "pending": ["aa/unreadable"],
            "reconciled": [],
            "errors": [{"item": "aa/unreadable", "error": "broken"}],
            "live_checked": True,
            "raw_count": 1,
        }
        with (
            mock.patch.object(gui, "pending_status", return_value=state),
            mock.patch.object(gui.subprocess, "run") as run,
        ):
            result = gui.run_publish()

        self.assertFalse(result["ok"])
        self.assertIn("安全阻止发布", result["log"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
