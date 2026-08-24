# -*- coding: utf-8 -*-
"""Atomic, snapshot-bound publication regression tests."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wf_mod_tool as core  # noqa: E402
import wf_publish  # noqa: E402


class PublisherCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        self.store.mkdir()
        self.cdn = self.root / "cdn"
        self.server_root = self.root / "server"
        self.active = self.server_root / "assets" / "asset-patch" / "active"
        self.active.mkdir(parents=True)
        self.manifest = (
            self.server_root / "assets" / "asset-patch" / "manifest.json"
        )
        self.manifest.write_text(
            json.dumps({"cdn_version": "1.4.54", "patches": []}) + "\n",
            encoding="utf-8",
        )
        self.work = self.root / "work"
        self.work.mkdir()
        self.pending = self.work / "sync_pending.json"
        self.profile = core.VersionProfile(
            id="cn", label="CN", store=self.store, fallback=None
        )
        self.patchers = (
            mock.patch.object(wf_publish, "CDN_ROOT", self.cdn),
            mock.patch.object(
                wf_publish, "CDN_DIFF", self.cdn / "archive-common-diff"
            ),
            mock.patch.object(wf_publish, "SERVER_ROOT", self.server_root),
            mock.patch.object(wf_publish, "ACTIVE_PATCH", self.active),
            mock.patch.object(wf_publish, "PATCH_MANIFEST", self.manifest),
            mock.patch.object(wf_publish, "WORK", self.work),
            mock.patch.object(wf_publish, "PENDING", self.pending),
            mock.patch.object(wf_publish, "CHANGELOG", self.work / "changelog.jsonl"),
            mock.patch.object(wf_publish, "CHANGELOG_MD", self.work / "changelog.md"),
            mock.patch.object(wf_publish, "current_max_version", return_value="1.4.54"),
            mock.patch.object(wf_publish, "stamp_changelog", return_value=0),
            mock.patch.object(wf_publish.time, "strftime", return_value="modfixture"),
            # These tests exercise atomic publication behavior with deliberately
            # tiny stores.  The production final-table contract has its own
            # focused tests below and must not pre-empt the scenario under test.
            mock.patch.object(wf_publish, "verify_required_keys", return_value=[]),
            mock.patch.object(wf_publish.publish_guard, "check", return_value=[]),
            mock.patch.object(
                wf_publish.final_state_guard,
                "load_baseline",
                return_value={"base_version": "1.4.54", "current_version": "1.4.54"},
            ),
            mock.patch.object(
                wf_publish.final_state_guard,
                "preflight",
                return_value={"changes": {}},
            ),
            mock.patch.object(wf_publish.final_state_guard, "commit", return_value=None),
        )
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_logical(self, logical: str, payload: bytes) -> str:
        digest = core.sha1_path(logical)
        relative = f"{digest[:2]}/{digest[2:]}"
        path = self.store / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return relative

    def write_snapshot(
        self,
        logicals: list[str],
        *,
        store: Path | None = None,
        entries: list[dict[str, object]] | None = None,
    ) -> Path:
        if entries is None:
            entries = []
            for logical in logicals:
                digest = core.sha1_path(logical)
                relative = f"{digest[:2]}/{digest[2:]}"
                payload = (self.store / relative).read_bytes()
                entries.append(
                    {
                        "logical": logical,
                        "relative": relative,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "size": len(payload),
                    }
                )
        path = self.root / "release-snapshot.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile_id": "cn",
                    "store": str((store or self.store).resolve()),
                    "entries": entries,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def run_publish(
        self,
        args: list[str],
        *,
        profiles: list[core.VersionProfile] | None = None,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        profile_patch = (
            mock.patch.object(core, "resolve_profile", side_effect=profiles)
            if profiles is not None
            else mock.patch.object(core, "resolve_profile", return_value=self.profile)
        )
        with (
            profile_patch,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = wf_publish.main(args)
        return result, stdout.getvalue(), stderr.getvalue()

    def archives(self) -> list[Path]:
        return sorted(self.active.glob("*.zip")) if self.active.exists() else []


class TestRequiredKeysContract(unittest.TestCase):
    def test_gauntlet_hub_contract_tracks_folder_instead_of_removed_direct_entry(self):
        document = json.loads(
            wf_publish.REQUIRED_KEYS_CONTRACT.read_text(encoding="utf-8-sig")
        )
        tables = document["tables"]

        self.assertNotIn("master/quest/event/event_list.orderedmap", tables)
        self.assertEqual(
            ["2"],
            tables["master/quest/event/event_folder.orderedmap"]["required_keys"],
        )
        self.assertEqual(
            ["2"],
            tables[
                "master/quest/event/event_folder_events.orderedmap"
            ]["required_keys"],
        )


class TestStrictSnapshotPublisher(PublisherCase):
    def test_snapshot_success_archives_the_exact_prevalidated_bytes(self):
        logicals = ["master/test/one.orderedmap", "item/test/two.png"]
        expected: dict[str, bytes] = {}
        for index, logical in enumerate(logicals):
            payload = f"validated-{index}".encode()
            relative = self.write_logical(logical, payload)
            expected[f"production/upload/{relative}"] = payload
        snapshot = self.write_snapshot(logicals)

        result, stdout, _stderr = self.run_publish(
            ["--tables", ",".join(logicals), "--snapshot", str(snapshot)],
            profiles=[self.profile, self.profile],
        )

        self.assertEqual(0, result)
        self.assertIn("[OK]", stdout)
        self.assertEqual(1, len(self.archives()))
        with zipfile.ZipFile(self.archives()[0]) as archive:
            self.assertEqual(set(expected), set(archive.namelist()))
            for name, payload in expected.items():
                self.assertEqual(payload, archive.read(name))

    def test_snapshot_hash_mismatch_creates_no_archive_or_success(self):
        logical = "master/test/one.orderedmap"
        relative = self.write_logical(logical, b"validated")
        snapshot = self.write_snapshot([logical])
        (self.store / relative).write_bytes(b"changed-after-gate")

        result, stdout, stderr = self.run_publish(
            ["--tables", logical, "--snapshot", str(snapshot)]
        )

        self.assertNotEqual(0, result)
        self.assertIn("snapshot", stderr.lower())
        self.assertNotIn("[OK]", stdout)
        self.assertEqual([], self.archives())

    def test_snapshot_allowlist_order_mismatch_creates_no_archive(self):
        logicals = ["master/test/one.orderedmap", "master/test/two.orderedmap"]
        for logical in logicals:
            self.write_logical(logical, logical.encode())
        snapshot = self.write_snapshot(list(reversed(logicals)))

        result, stdout, _stderr = self.run_publish(
            ["--tables", ",".join(logicals), "--snapshot", str(snapshot)]
        )

        self.assertNotEqual(0, result)
        self.assertNotIn("[OK]", stdout)
        self.assertEqual([], self.archives())

    def test_profile_store_change_after_snapshot_check_creates_no_archive(self):
        logical = "master/test/one.orderedmap"
        self.write_logical(logical, b"validated")
        snapshot = self.write_snapshot([logical])
        changed_store = self.root / "changed-store"
        changed_store.mkdir()
        changed_profile = core.VersionProfile(
            id="cn", label="CN changed", store=changed_store, fallback=None
        )

        result, stdout, stderr = self.run_publish(
            ["--tables", logical, "--snapshot", str(snapshot)],
            profiles=[self.profile, changed_profile],
        )

        self.assertNotEqual(0, result)
        self.assertIn("store", stderr.lower())
        self.assertNotIn("[OK]", stdout)
        self.assertEqual([], self.archives())

    def test_profile_id_change_with_same_store_creates_no_archive(self):
        logical = "master/test/one.orderedmap"
        self.write_logical(logical, b"validated")
        snapshot = self.write_snapshot([logical])
        changed_profile = core.VersionProfile(
            id="global", label="Wrong profile", store=self.store, fallback=None
        )

        result, stdout, stderr = self.run_publish(
            ["--tables", logical, "--snapshot", str(snapshot)],
            profiles=[self.profile, changed_profile],
        )

        self.assertNotEqual(0, result)
        self.assertIn("profile", stderr.lower())
        self.assertNotIn("[OK]", stdout)
        self.assertEqual([], self.archives())

    def test_explicit_missing_entry_fails_before_any_partial_archive(self):
        present = "master/test/present.orderedmap"
        missing = "master/test/missing.orderedmap"
        self.write_logical(present, b"present")

        result, stdout, stderr = self.run_publish(
            ["--tables", f"{present},{missing}"]
        )

        self.assertNotEqual(0, result)
        self.assertIn("missing", stderr.lower())
        self.assertNotIn("[OK]", stdout)
        self.assertEqual([], self.archives())

    def test_archive_build_failure_removes_temporary_output_and_success(self):
        logical = "master/test/one.orderedmap"
        self.write_logical(logical, b"validated")
        snapshot = self.write_snapshot([logical])

        with mock.patch.object(
            wf_publish.zipfile,
            "ZipFile",
            side_effect=RuntimeError("fixture zip failure"),
        ):
            result, stdout, _stderr = self.run_publish(
                ["--tables", logical, "--snapshot", str(snapshot)],
                profiles=[self.profile, self.profile],
            )

        self.assertNotEqual(0, result)
        self.assertNotIn("[OK]", stdout)
        self.assertEqual([], self.archives())
        leftovers = list(self.cdn.rglob("*.tmp")) if self.cdn.exists() else []
        self.assertEqual([], leftovers)

    def test_committed_archive_stat_failure_is_warning_only(self):
        logical = "master/test/one.orderedmap"
        self.write_logical(logical, b"validated")
        snapshot = self.write_snapshot([logical])

        # 不能全局 patch Path.stat:3.11 的 Path.exists()/is_file() 也经由
        # Path.stat,会把 _build_archives 里的存在性检查一起弄坏(CI 实测
        # 走到 [ERR] preflight 退出 1);patch 专用 seam 才只影响告警路径。
        with mock.patch.object(
            wf_publish,
            "committed_archive_size",
            side_effect=OSError("fixture committed archive stat failure"),
        ):
            result, stdout, stderr = self.run_publish(
                ["--tables", logical, "--snapshot", str(snapshot)],
                profiles=[self.profile, self.profile],
            )

        self.assertEqual(0, result)
        self.assertIn("[OK]", stdout)
        self.assertIn("[WARN]", stderr)
        self.assertIn("committed", stderr.lower())
        self.assertIn("stat", stderr.lower())
        self.assertEqual(1, len(self.archives()))

    def test_committed_archive_changelog_failure_is_warning_only(self):
        logical = "master/test/one.orderedmap"
        self.write_logical(logical, b"validated")
        snapshot = self.write_snapshot([logical])

        with mock.patch.object(
            wf_publish,
            "stamp_changelog",
            side_effect=OSError("fixture changelog failure"),
        ):
            result, stdout, stderr = self.run_publish(
                ["--tables", logical, "--snapshot", str(snapshot)],
                profiles=[self.profile, self.profile],
            )

        self.assertEqual(0, result)
        self.assertIn("[OK]", stdout)
        self.assertIn("[WARN]", stderr)
        self.assertIn("committed", stderr.lower())
        self.assertIn("changelog", stderr.lower())
        self.assertEqual(1, len(self.archives()))


class TestPendingCompatibility(PublisherCase):
    def test_pending_mode_still_skips_missing_entries_and_publishes_existing(self):
        logical = "master/test/pending.orderedmap"
        relative = self.write_logical(logical, b"pending-bytes")
        self.pending.write_text(
            json.dumps([relative, "ff/missing-pending-entry"]), encoding="utf-8"
        )

        result, stdout, _stderr = self.run_publish([])

        self.assertEqual(0, result)
        self.assertIn("[OK]", stdout)
        self.assertEqual(1, len(self.archives()))
        with zipfile.ZipFile(self.archives()[0]) as archive:
            self.assertEqual(
                b"pending-bytes",
                archive.read(f"production/upload/{relative}"),
            )

    def test_active_archive_rename_failure_restores_previous_archive(self):
        logical = "master/test/pending.orderedmap"
        relative = self.write_logical(logical, b"common-bytes")
        medium_relative = "12/medium-fixture"
        medium_path = self.store.parent / "medium_upload" / medium_relative
        medium_path.parent.mkdir(parents=True, exist_ok=True)
        medium_path.write_bytes(b"medium-bytes")
        self.pending.write_text(
            json.dumps([relative, f"medium:{medium_relative}"]), encoding="utf-8"
        )
        archive_name = "pinball-1.4.54-1.4.55-1-modfixture.zip"
        final = self.active / archive_name
        final.write_bytes(b"previous-archive")
        real_replace = wf_publish.os.replace
        calls = 0

        def fail_second_replace(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("fixture second rename failure")
            return real_replace(source, destination)

        with mock.patch.object(
            wf_publish.os,
            "replace",
            side_effect=fail_second_replace,
        ):
            result, stdout, _stderr = self.run_publish([])

        self.assertNotEqual(0, result)
        self.assertNotIn("[OK]", stdout)
        self.assertEqual([final], self.archives())
        self.assertEqual(b"previous-archive", final.read_bytes())
        leftovers = list(self.active.glob("*.tmp"))
        self.assertEqual([], leftovers)

    def test_backup_cleanup_failure_cannot_roll_back_committed_archives(self):
        logical = "master/test/pending.orderedmap"
        relative = self.write_logical(logical, b"new-common")
        medium_relative = "12/medium-fixture"
        medium_path = self.store.parent / "medium_upload" / medium_relative
        medium_path.parent.mkdir(parents=True, exist_ok=True)
        medium_path.write_bytes(b"new-medium")
        self.pending.write_text(
            json.dumps([relative, f"medium:{medium_relative}"]), encoding="utf-8"
        )

        archive_name = "pinball-1.4.54-1.4.55-1-modfixture.zip"
        final = self.active / archive_name
        final.write_bytes(b"old-archive")

        real_unlink = Path.unlink

        def fail_populated_rollback_cleanup(path, *args, **kwargs):
            candidate = Path(path)
            if (
                candidate.suffix == ".rollback"
                and candidate.exists()
                and candidate.stat().st_size > 0
            ):
                raise OSError("fixture backup cleanup failure")
            return real_unlink(candidate, *args, **kwargs)

        with mock.patch.object(Path, "unlink", new=fail_populated_rollback_cleanup):
            result, stdout, _stderr = self.run_publish([])

        self.assertEqual(0, result)
        self.assertIn("[OK]", stdout)
        with zipfile.ZipFile(final) as archive:
            self.assertEqual(
                b"new-common",
                archive.read(f"production/upload/{relative}"),
            )
            self.assertEqual(
                b"new-medium",
                archive.read(f"production/medium_upload/{medium_relative}"),
            )
        self.assertEqual(1, len(list(self.active.glob("*.rollback"))))

    def test_pending_list_is_cleared_after_a_successful_publish(self):
        logical = "master/test/pending.orderedmap"
        relative = self.write_logical(logical, b"pending-bytes")
        self.pending.write_text(json.dumps([relative]), encoding="utf-8")

        result, stdout, _stderr = self.run_publish([])

        self.assertEqual(0, result)
        self.assertIn("[OK]", stdout)
        self.assertIn("pending 列表已清空", stdout)
        self.assertEqual([], json.loads(self.pending.read_text(encoding="utf-8")))

    def test_pending_list_survives_a_failed_publish(self):
        logical = "master/test/pending.orderedmap"
        relative = self.write_logical(logical, b"pending-bytes")
        self.pending.write_text(json.dumps([relative]), encoding="utf-8")

        with mock.patch.object(
            wf_publish.zipfile,
            "ZipFile",
            side_effect=RuntimeError("fixture zip failure"),
        ):
            result, stdout, _stderr = self.run_publish([])

        self.assertNotEqual(0, result)
        self.assertNotIn("[OK]", stdout)
        self.assertEqual([], self.archives())
        self.assertEqual(
            [relative], json.loads(self.pending.read_text(encoding="utf-8"))
        )

    def test_explicit_tables_publish_leaves_pending_untouched(self):
        """--tables 直发不碰 pending:清空只对 pending 来源生效(GUI 走逐表移除)。"""
        published = "master/test/published.orderedmap"
        self.write_logical(published, b"explicit-bytes")
        unrelated = "aa/unrelated-pending-entry"
        self.pending.write_text(json.dumps([unrelated]), encoding="utf-8")

        result, stdout, _stderr = self.run_publish(["--tables", published])

        self.assertEqual(0, result)
        self.assertIn("[OK]", stdout)
        self.assertNotIn("pending 列表已清空", stdout)
        self.assertEqual(
            [unrelated], json.loads(self.pending.read_text(encoding="utf-8"))
        )


class TestActivePatchOutput(PublisherCase):
    """Current Mode15 workflow: one active ZIP and opt-in dev catalog."""

    def _publish_pending(self, extra: list[str] | None = None):
        logical = "master/test/dual.orderedmap"
        relative = self.write_logical(logical, b"dual-bytes")
        self.pending.write_text(json.dumps([relative]), encoding="utf-8")
        return self.run_publish(list(extra or []))

    def test_new_names_match_dev_scanner_pattern(self):
        import wf_dev_catalog as devcat

        with mock.patch.object(
            wf_publish.time, "strftime", return_value="07261830"
        ):
            result, stdout, _stderr = self._publish_pending()
        self.assertEqual(0, result)
        names = [path.name for path in self.archives()]
        self.assertEqual(1, len(names))
        for name in names:
            self.assertRegex(name, devcat.DIFF_NAME_RE)

    def test_layer_placeholders_flag_is_rejected(self):
        result, stdout, stderr = self._publish_pending(["--layer-placeholders"])
        self.assertNotEqual(0, result)
        self.assertNotIn("[OK]", stdout)
        self.assertIn("incompatible", stderr)
        self.assertEqual([], self.archives())

    def test_dev_catalog_emitted_after_publish(self):
        result, stdout, _stderr = self._publish_pending(["--dev-catalog"])
        self.assertEqual(0, result)
        self.assertIn("dev catalog:", stdout)
        out_dir = self.cdn / "dev-catalog"
        manifests = sorted(out_dir.glob("catalog-cn-*.json"))
        self.assertEqual(1, len(manifests))
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(1, manifest["schemaVersion"])
        self.assertEqual("cn-1.4.54", manifest["baseline"])
        self.assertTrue((out_dir / "report.json").is_file())

    def test_no_dev_catalog_flag_skips_emit(self):
        result, stdout, _stderr = self._publish_pending(["--no-dev-catalog"])
        self.assertEqual(0, result)
        self.assertNotIn("dev catalog:", stdout)
        self.assertFalse((self.cdn / "dev-catalog").exists())


if __name__ == "__main__":
    unittest.main()
