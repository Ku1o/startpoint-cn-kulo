# -*- coding: utf-8 -*-
"""Regression coverage for the 11 Fantasy equipment trim records."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zlib
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import publish_fantasy_icon_trim_patch as publisher  # noqa: E402
import wf_mod_tool as core  # noqa: E402


def orderedmap(rows: list[tuple[str, bytes]]) -> bytes:
    return core.build_orderedmap(
        core.OrderedMap(
            publisher.TRIMMED_LOGICAL,
            [key for key, _row in rows],
            [row for _key, row in rows],
            Path("<fixture>"),
        )
    )


class FantasyIconTrimPatchTests(unittest.TestCase):
    def test_patch_preserves_every_existing_key_and_raw_row(self):
        original = [
            ("ui/example/one", b"1,2,30,40"),
            ("ui/example/two", b"-3,4,50,60"),
        ]
        base = orderedmap(original)
        base_decoded = core.read_orderedmap_raw_rows_from_bytes(
            base, publisher.TRIMMED_LOGICAL
        )

        result = publisher.patch_trimmed_image(base)
        decoded = core.read_orderedmap_raw_rows_from_bytes(
            result.payload, publisher.TRIMMED_LOGICAL
        )

        self.assertEqual([key for key, _row in original], decoded.keys[:2])
        self.assertEqual(base_decoded.rows, decoded.rows[:2])
        self.assertEqual(list(publisher.icon_trim_keys()), decoded.keys[2:])
        self.assertEqual(
            [publisher.TRIM_ROW.encode()] * len(publisher.icon_trim_keys()),
            [zlib.decompress(row) for row in decoded.rows[2:]],
        )
        self.assertEqual(2, result.original_rows)
        self.assertEqual(publisher.icon_trim_keys(), result.added_keys)

    def test_patch_is_idempotent_when_all_rows_are_already_correct(self):
        rows = [
            (key, publisher.TRIM_ROW.encode())
            for key in publisher.icon_trim_keys()
        ]
        base = orderedmap(rows)

        result = publisher.patch_trimmed_image(base)

        self.assertEqual((), result.added_keys)
        self.assertEqual(base, result.payload)

    def test_patch_rejects_a_conflicting_existing_row(self):
        key = publisher.icon_trim_keys()[0]
        with self.assertRaisesRegex(ValueError, "conflicting trim row"):
            publisher.patch_trimmed_image(orderedmap([(key, b"0,0,19,20")]))

    def test_manifest_order_selects_the_last_trim_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            active = Path(temp)
            first = orderedmap([("old", b"0,0,1,1")])
            second = orderedmap([("new", b"0,0,2,2")])
            for name, payload in (("first.zip", first), ("second.zip", second)):
                with zipfile.ZipFile(active / name, "w") as archive:
                    archive.writestr(publisher.TRIMMED_MEMBER, payload)
            manifest = {
                "patches": [
                    {"id": "first", "enabled": True, "archive": "first.zip"},
                    {
                        "id": "second",
                        "enabled": True,
                        "archive_integrity": [{"name": "second.zip"}],
                    },
                ]
            }

            payload, patch_id, archive_name = publisher.find_latest_trim_payload(
                manifest, active
            )

        self.assertEqual(second, payload)
        self.assertEqual("second", patch_id)
        self.assertEqual("second.zip", archive_name)

    def test_archive_is_deterministic_and_contains_only_the_trim_table(self):
        payload = orderedmap([("fixture", b"0,0,20,20")])

        first = publisher.build_archive(payload)
        second = publisher.build_archive(payload)

        self.assertEqual(first, second)
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertEqual([publisher.TRIMMED_MEMBER], archive.namelist())
            self.assertEqual(payload, archive.read(publisher.TRIMMED_MEMBER))

    def test_patch_entry_receipt_matches_archive(self):
        archive = publisher.build_archive(b"fixture")
        entry = publisher.build_patch_entry(
            archive, publisher.icon_trim_keys()
        )

        self.assertEqual(publisher.PATCH_VERSION, entry["version"])
        self.assertEqual(publisher.BASE_VERSION, entry["depends_on"])
        self.assertEqual([publisher.TRIMMED_MEMBER], entry["files"])
        self.assertEqual(len(archive), entry["archive_size"])
        receipt = entry["archive_integrity"][0]
        self.assertEqual(publisher.sha256_bytes(archive), receipt["sha256"])
        # Also guarantees the entry remains JSON serializable for manifest write.
        json.dumps(entry, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
