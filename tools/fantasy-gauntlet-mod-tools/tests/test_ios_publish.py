# -*- coding: utf-8 -*-
"""iOS ETC2 cut-in automatic publication regression tests."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wf_assets  # noqa: E402
import wf_atf  # noqa: E402
import wf_gui  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_publish  # noqa: E402


def _gradient_png(width: int = 16, height: int = 8) -> bytes:
    rgba = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 4
            rgba[offset:offset + 4] = bytes((
                x * 255 // max(width - 1, 1),
                y * 255 // max(height - 1, 1),
                120,
                (x + y) * 255 // max(width + height - 2, 1),
            ))
    return wf_atf.png_encode_rgba(width, height, bytes(rgba))


class IosPublishCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "production" / "upload"
        self.store.mkdir(parents=True)
        self.server = self.root / "server"
        cdndata = self.server / "assets" / "cdndata"
        cdndata.mkdir(parents=True)
        (cdndata / "character.json").write_text(
            json.dumps({"999999": [["fixture_ios"]]}), encoding="utf-8"
        )
        self.png_logical = "character/fixture_ios/ui/skill_cutin_0.png"
        self.atf_logical = self.png_logical[:-4] + ".atf.deflate"
        digest = core.sha1_path(self.atf_logical)
        self.relative = f"{digest[:2]}/{digest[2:]}"
        self.png = _gradient_png()
        png_path = wf_assets.path_in_root(
            self.store, "medium", self.png_logical
        )
        png_path.parent.mkdir(parents=True)
        png_path.write_bytes(wf_assets.png_encode(self.png))
        self.android_plain = wf_atf.build_cutin_atf(self.png)
        self.android_stored = wf_atf.deflate(self.android_plain)
        self.android_entry = wf_publish.PreparedFile(
            archive_name=f"production/android_upload/{self.relative}",
            payload=self.android_stored,
            prefix="android:",
        )

    def complete(self, entries):
        with mock.patch.object(wf_publish, "SERVER_ROOT", self.server):
            return wf_publish._complete_ios_cutin_files(entries, self.store)


class TestIosCutinCompletion(IosPublishCase):
    def test_android_cutin_automatically_adds_ios_etc2_to_same_file_set(self):
        prepared, reports = self.complete([self.android_entry])
        by_name = {entry.archive_name: entry for entry in prepared}
        ios_name = f"production/ios_upload/{self.relative}"
        self.assertIn(self.android_entry.archive_name, by_name)
        self.assertIn(ios_name, by_name)
        self.assertEqual(1, len(reports))
        ios_plain = wf_atf.inflate(by_name[ios_name].payload)
        report = wf_atf.validate_cutin_platform_pair(
            self.android_plain, ios_plain, self.png
        )
        self.assertEqual(3, report["ios_slot"])
        self.assertNotEqual(self.android_entry.payload, by_name[ios_name].payload)
        self.assertEqual(
            [
                f"production/android_upload/{self.relative}",
                f"production/ios_upload/{self.relative}",
            ],
            wf_publish._manifest_files(prepared),
        )

    def test_missing_source_png_fails_closed(self):
        source = wf_assets.path_in_root(
            self.store, "medium", self.png_logical
        )
        source.unlink()
        with self.assertRaisesRegex(ValueError, "找不到.*源 PNG"):
            self.complete([self.android_entry])

    def test_copied_android_payload_in_ios_root_is_rejected(self):
        copied = wf_publish.PreparedFile(
            archive_name=f"production/ios_upload/{self.relative}",
            payload=self.android_stored,
            prefix="ios:",
        )
        with self.assertRaisesRegex(ValueError, "平台槽错误"):
            self.complete([self.android_entry, copied])

    def test_built_active_zip_contains_files_only_and_both_platforms(self):
        prepared, _reports = self.complete([self.android_entry])
        active = self.root / "active"
        with (
            mock.patch.object(wf_publish, "ACTIVE_PATCH", active),
            mock.patch.object(wf_publish.time, "strftime", return_value="fixture"),
        ):
            outputs = wf_publish._build_archives(
                prepared, "1.4.59", "1.4.60"
            )
        self.assertEqual(1, len(outputs))
        with zipfile.ZipFile(outputs[0]) as archive:
            infos = archive.infolist()
            self.assertTrue(all(not info.is_dir() for info in infos))
            self.assertEqual(
                {
                    f"production/android_upload/{self.relative}",
                    f"production/ios_upload/{self.relative}",
                },
                {info.filename for info in infos},
            )

    def test_manifest_keeps_legacy_shape_and_full_member_paths(self):
        prepared, _reports = self.complete([self.android_entry])
        active = self.root / "active"
        manifest = self.root / "manifest.json"
        manifest.write_text(
            json.dumps({"cdn_version": "1.4.59", "patches": []}),
            encoding="utf-8",
        )
        with (
            mock.patch.object(wf_publish, "ACTIVE_PATCH", active),
            mock.patch.object(wf_publish, "PATCH_MANIFEST", manifest),
            mock.patch.object(wf_publish.time, "strftime", return_value="fixture"),
        ):
            output = wf_publish._build_archives(
                prepared, "1.4.59", "1.4.60"
            )[0]
            wf_publish._register_active_patch(
                output, prepared, "1.4.59", "1.4.60"
            )
        entry = json.loads(manifest.read_text(encoding="utf-8"))["patches"][0]
        self.assertNotIn("platforms", entry)
        self.assertNotIn("archive_integrity", entry)
        self.assertEqual(output.stat().st_size, entry["archive_size"])
        self.assertEqual(
            [
                f"production/android_upload/{self.relative}",
                f"production/ios_upload/{self.relative}",
            ],
            entry["files"],
        )

    def test_android_emulator_sync_preserves_ios_pair_pending(self):
        pending = [
            f"android:{self.relative}",
            f"ios:{self.relative}",
        ]
        android_path = self.store.parent / "android_upload" / self.relative
        android_path.parent.mkdir(parents=True)
        android_path.write_bytes(self.android_stored)
        with (
            mock.patch.object(wf_gui, "TARGET_STORE", self.store),
            mock.patch.object(wf_gui, "find_adb", return_value="adb"),
            mock.patch.object(wf_gui, "adb_run", return_value=(0, "ok")) as adb_run,
            mock.patch.object(wf_gui, "read_pending", return_value=pending),
            mock.patch.object(wf_gui, "clear_pending") as clear_pending,
        ):
            result = wf_gui.sync_to_emulator(restart=False)
        self.assertTrue(result["ok"])
        clear_pending.assert_not_called()
        self.assertIn("保留完整待发布清单", result["log"])
        pushes = [call for call in adb_run.call_args_list if "push" in call.args]
        self.assertEqual(1, len(pushes))

    def test_gui_png_replacement_writes_and_queues_both_platform_atfs(self):
        source = wf_assets.path_in_root(
            self.store, "medium", self.png_logical
        )
        android = self.store.parent / "android_upload" / self.relative
        android.parent.mkdir(parents=True)
        android.write_bytes(self.android_stored)
        pending_file = self.root / "sync_pending.json"
        changed_png = _gradient_png()
        with (
            mock.patch.object(wf_gui, "TARGET_STORE", self.store),
            mock.patch.object(wf_gui, "PENDING_FILE", pending_file),
            mock.patch.object(wf_gui, "WORK_DIR", self.root),
            mock.patch.object(wf_gui, "record_change"),
        ):
            result = wf_gui.replace_asset(
                self.png_logical, changed_png, force=False, dry_run=False
            )
        ios = self.store.parent / "ios_upload" / self.relative
        self.assertTrue(source.is_file())
        self.assertTrue(android.is_file())
        self.assertTrue(ios.is_file())
        android_plain = wf_atf.inflate(android.read_bytes())
        ios_plain = wf_atf.inflate(ios.read_bytes())
        self.assertEqual(2, wf_atf.parse_atf(android_plain)["slot"])
        self.assertEqual(3, wf_atf.parse_atf(ios_plain)["slot"])
        self.assertNotEqual(android_plain, ios_plain)
        self.assertEqual(
            {
                f"medium:{source.parent.name}/{source.name}",
                f"android:{self.relative}",
                f"ios:{self.relative}",
            },
            set(json.loads(pending_file.read_text(encoding="utf-8"))),
        )
        self.assertIn("iOS ETC2", result["log"])

    def test_gui_replacement_backs_up_live_atfs_without_local_overlay(self):
        android = self.store.parent / "android_upload" / self.relative
        ios = self.store.parent / "ios_upload" / self.relative
        ios_stored = wf_atf.deflate(wf_atf.build_cutin_atf_ios(self.png))

        def current_root(_store, logical, root_name):
            self.assertEqual(self.atf_logical, logical)
            stored = self.android_stored if root_name == "android" else ios_stored
            return root_name, stored, f"active.zip!{root_name}"

        with (
            mock.patch.object(wf_gui, "TARGET_STORE", self.store),
            mock.patch.object(wf_gui, "PENDING_FILE", self.root / "pending.json"),
            mock.patch.object(wf_gui, "WORK_DIR", self.root),
            mock.patch.object(wf_gui, "record_change"),
            mock.patch.object(
                wf_assets, "read_current_root", side_effect=current_root
            ),
        ):
            wf_gui.replace_asset(
                self.png_logical, _gradient_png(), force=False, dry_run=False
            )

        android_backups = list(android.parent.glob(
            android.name + ".bak-wfmod-asset-*"))
        ios_backups = list(ios.parent.glob(ios.name + ".bak-wfmod-asset-*"))
        self.assertEqual([self.android_stored],
                         [path.read_bytes() for path in android_backups])
        self.assertEqual([ios_stored],
                         [path.read_bytes() for path in ios_backups])


if __name__ == "__main__":
    unittest.main(verbosity=2)
