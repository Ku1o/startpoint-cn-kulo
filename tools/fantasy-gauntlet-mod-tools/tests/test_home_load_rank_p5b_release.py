from __future__ import annotations

import hashlib
import io
import json
import sys
import unittest
import zipfile
import zlib
from pathlib import Path

from PIL import Image


TOOL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOL_ROOT.parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import publish_home_load_rank_p5b_1_4_92_20260829 as release  # noqa: E402
import wf_assets  # noqa: E402
import wf_dsl  # noqa: E402
import wf_mod_tool as core  # noqa: E402


class HomeLoadRankP5BReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (REPO_ROOT / "assets/asset-patch/manifest.json").read_text(encoding="utf-8")
        )
        cls.entry = next(
            item for item in cls.manifest["patches"] if item["id"] == release.PATCH_ID
        )
        cls.archives = [
            REPO_ROOT / "assets/asset-patch/active" / item["name"]
            for item in cls.entry["archive_integrity"]
        ]

    def read_terminal_member(self, member: str) -> bytes:
        matches: list[bytes] = []
        for archive_path in self.archives:
            with zipfile.ZipFile(archive_path) as archive:
                if member in archive.namelist():
                    matches.append(archive.read(member))
        self.assertGreaterEqual(len(matches), 1, member)
        return matches[-1]

    def test_single_combined_version_and_archive_integrity(self) -> None:
        self.assertEqual("1.4.92", self.manifest["cdn_version"])
        enabled = [item for item in self.manifest["patches"] if item.get("enabled")]
        self.assertEqual(release.PATCH_ID, enabled[-1]["id"])
        self.assertEqual("1.4.92", enabled[-1]["version"])
        for archive_path, expected in zip(self.archives, self.entry["archive_integrity"]):
            raw = archive_path.read_bytes()
            self.assertEqual(expected["size"], len(raw))
            self.assertEqual(expected["sha256"], hashlib.sha256(raw).hexdigest())

    def test_restored_character_abilities_survive_p5b_merge(self) -> None:
        member = release.member_name("common", release.ABILITY_LOGICAL)
        raw = self.read_terminal_member(member)
        table = core.read_orderedmap_raw_rows_from_bytes(raw, release.ABILITY_LOGICAL)
        self.assertEqual(3110, len(table.keys))
        self.assertTrue(set(release.ABILITY_RESTORE_KEYS) <= set(table.keys))
        fold_report = json.loads(
            (REPO_ROOT / "assets/asset-patch/audit/home-load-rank-p5b-1.4.92/mod-character-balance-fold.json")
            .read_text(encoding="utf-8")
        )
        expected = next(
            item["output_sha256"]
            for item in fold_report["tables"]
            if item["logical"] == release.ABILITY_LOGICAL
        )
        self.assertEqual(expected, hashlib.sha256(raw).hexdigest())

    def test_abyss_gacha_cleanup_is_inside_combined_archives(self) -> None:
        for rank, logical in release.ABYSS_GACHA_LOGICALS.items():
            raw = self.read_terminal_member(release.member_name("common", logical))
            rows = release.parse_abyss_gacha_rows(raw, logical)
            self.assertEqual(release.ABYSS_GACHA_AFTER_COUNTS[rank], len(rows))
            self.assertEqual(
                release.ABYSS_GACHA_TOTALS[rank],
                sum(int(row["odds"]) for row in rows),
            )

    def test_ticket_item_references_have_two_pixel_backed_atlas_frames(self) -> None:
        item_raw = self.read_terminal_member(
            release.member_name("common", "master/item/item.orderedmap")
        )
        item_table = core.read_orderedmap_bytes(item_raw, "master/item/item.orderedmap")
        item_rows = dict(zip(item_table.keys, item_table.rows))
        sheet_raw = self.read_terminal_member(
            release.member_name("common", release.ITEM_SHEET_LOGICAL)
        )
        atlas_raw = self.read_terminal_member(
            release.member_name("common", release.ITEM_ATLAS_LOGICAL)
        )
        self.assertTrue(sheet_raw.startswith(wf_assets.PNG_FAKE))
        with Image.open(io.BytesIO(wf_assets.png_decode(sheet_raw))) as image:
            image.load()
            sheet = image.convert("RGBA")
        atlas = wf_dsl.parse_dsl(zlib.decompress(atlas_raw, -15))["tree"]

        self.assertEqual((505, 1704), sheet.size)
        for item_id, icon_name in zip(release.TARGET_ITEMS, release.TICKET_ICON_NAMES):
            csv_rows = core.read_csv_lines(item_rows[str(item_id)].decode("utf-8"))
            self.assertEqual(icon_name, csv_rows[0][3])
            frames = [row for row in atlas if row.get("n") == icon_name]
            self.assertEqual(1, len(frames), icon_name)
            frame = frames[0]
            crop = sheet.crop((
                frame["x"],
                frame["y"],
                frame["x"] + frame["w"],
                frame["y"] + frame["h"],
            ))
            self.assertEqual((20, 20), crop.size)
            self.assertIsNotNone(crop.getbbox(), icon_name)


if __name__ == "__main__":
    unittest.main()
