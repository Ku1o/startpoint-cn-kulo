from __future__ import annotations

import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import wf_live_cdn as live
import wf_assets
import wf_mod_tool as core
import wf_quest_lib as q


LOGICAL = "master/test/live_current.orderedmap"
OVERLAY_ONLY = "master/test/unpublished_overlay.orderedmap"
IOS_LOGICAL = "asset/test/ios_current.atf"


class LiveCdnReadCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.server = self.root / "server"
        self.cdn = self.server / ".cdn" / "cn"
        self.active = self.server / "assets" / "asset-patch" / "active"
        self.overlay = self.server / "assets" / "asset-patch" / "production" / "upload"
        self.active.mkdir(parents=True)
        self.overlay.mkdir(parents=True)
        for root in ("common", "medium", "android", "ios"):
            (self.cdn / f"archive-{root}-full").mkdir(parents=True)
            (self.cdn / f"archive-{root}-diff").mkdir(parents=True)
        self.member = "production/upload/" + q.hashed_rel(LOGICAL)
        self.ios_member = "production/ios_upload/" + q.hashed_rel(IOS_LOGICAL)
        self._zip(
            self.cdn / "archive-common-full" / "pinball-1.4.0-1-fixture.zip",
            self._table("base"),
        )
        self._zip(
            self.cdn / "archive-common-diff" / "pinball-1.4.0-1.4.1-1-cdn.zip",
            self._table("cdn"),
        )
        self._zip(
            self.active / "pinball-1.4.0-1.4.1-1-active.zip",
            self._table("active"),
        )
        self._zip(
            self.cdn / "archive-ios-full" / "pinball-1.4.0-1-fixture.zip",
            b"ios-base",
            member=self.ios_member,
        )
        self._zip(
            self.active / "pinball-1.4.0-1.4.1-2-ios-active.zip",
            b"ios-active",
            member=self.ios_member,
        )
        overlay_path = self.overlay / q.hashed_rel(LOGICAL)
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay_path.write_bytes(self._table("overlay"))
        overlay_only = self.overlay / q.hashed_rel(OVERLAY_ONLY)
        overlay_only.parent.mkdir(parents=True, exist_ok=True)
        overlay_only.write_bytes(self._table("unpublished"))
        self.env = mock.patch.dict(
            os.environ,
            {
                "WF_SERVER_DIR": str(self.server),
                "WF_CDN_DIR": str(self.cdn),
                "WF_TARGET_STORE": str(self.overlay),
            },
            clear=False,
        )
        self.env.start()
        live.clear_cache()

    def tearDown(self) -> None:
        live.clear_cache()
        self.env.stop()
        self.tmp.cleanup()

    @staticmethod
    def _table(value: str) -> bytes:
        return q.build_node({"key": value})

    def _zip(self, path: Path, data: bytes, *, member: str | None = None) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member or self.member, data)

    def test_active_terminal_state_beats_cdn_and_writable_overlay(self) -> None:
        self.assertEqual("active", q.load_table(LOGICAL)["key"])
        ordered = core.load_table(LOGICAL, self.overlay)
        self.assertEqual("active", ordered.text_rows()["key"])
        info = live.describe()
        self.assertEqual("1.4.1", info["tail"])
        self.assertEqual("live-cdn+active", info["source"])

    def test_ios_full_and_active_terminal_are_readable(self) -> None:
        current = live.read_relative(q.hashed_rel(IOS_LOGICAL), roots=("ios",))
        self.assertEqual("ios", current.root)
        self.assertEqual(b"ios-active", current.data)
        self.assertEqual("1.4.1", live.describe()["platform_tails"]["ios"])

    def test_asset_reader_uses_live_terminal_and_ignores_overlay_only(self) -> None:
        current = wf_assets.read_current(self.overlay, LOGICAL)
        self.assertIsNotNone(current)
        self.assertEqual("upload", current[0])
        self.assertEqual("active", q.parse_node(current[1])["key"])
        self.assertIn("active.zip", current[2])
        self.assertIsNone(wf_assets.read_current(self.overlay, OVERLAY_ONLY))

    def test_asset_root_reader_keeps_platform_roots_separate(self) -> None:
        current = wf_assets.read_current_root(
            self.overlay, IOS_LOGICAL, "ios")
        self.assertIsNotNone(current)
        self.assertEqual(("ios", b"ios-active"), current[:2])
        self.assertIsNone(wf_assets.read_current_root(
            self.overlay, IOS_LOGICAL, "android"))

    def test_new_active_edge_invalidates_long_running_cache(self) -> None:
        self.assertEqual("active", q.load_table(LOGICAL)["key"])
        self._zip(
            self.active / "pinball-1.4.1-1.4.2-1-later.zip",
            self._table("later"),
        )
        time.sleep(0.3)
        self.assertEqual("later", q.load_table(LOGICAL)["key"])
        self.assertEqual("1.4.2", live.describe()["tail"])

    def test_writing_overlay_does_not_change_live_read_truth(self) -> None:
        written = q.save_table(LOGICAL, {"key": "pending"}, backup=False)
        self.assertEqual("pending", q.parse_node(written.read_bytes())["key"])
        self.assertEqual("active", q.load_table(LOGICAL)["key"])

    def test_overlay_only_file_is_not_server_current(self) -> None:
        with self.assertRaises(live.LiveCdnEntryMissing):
            q.load_table(OVERLAY_ONLY)
        with self.assertRaises(live.LiveCdnEntryMissing):
            core.load_table(OVERLAY_ONLY, self.overlay)

    def test_replacing_active_archive_refreshes_current_bytes(self) -> None:
        self.assertEqual("active", q.load_table(LOGICAL)["key"])
        self._zip(
            self.active / "pinball-1.4.0-1.4.1-1-active.zip",
            self._table("active-replaced"),
        )
        time.sleep(0.3)
        self.assertEqual("active-replaced", q.load_table(LOGICAL)["key"])

    def test_explicit_path_still_reads_exact_backup(self) -> None:
        exact = self.root / "exact.orderedmap"
        exact.write_bytes(self._table("exact"))
        self.assertEqual("exact", q.load_table(LOGICAL, path=exact)["key"])


class StandaloneFallbackCase(unittest.TestCase):
    def test_store_fallback_remains_available_without_server_cdn(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "production" / "upload"
            target = store / q.hashed_rel(LOGICAL)
            target.parent.mkdir(parents=True)
            target.write_bytes(q.build_node({"key": "standalone"}))
            with mock.patch.dict(
                os.environ, {"WF_TARGET_STORE": str(store)}, clear=False
            ), mock.patch.object(
                core, "resolve_cdn_root", side_effect=ValueError("no live CDN")
            ):
                live.clear_cache()
                self.assertEqual("standalone", q.load_table(LOGICAL)["key"])


if __name__ == "__main__":
    unittest.main()
