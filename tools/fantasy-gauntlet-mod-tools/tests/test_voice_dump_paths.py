# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wf_assets


class VoiceDumpPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_vocab_cache = wf_assets._voice_vocab_cache
        self.previous_pathlist_cache = wf_assets._pathlist_cache
        self.previous_harvest_cache = wf_assets._harvest_voice_cache
        wf_assets._voice_vocab_cache = None
        wf_assets._pathlist_cache = None
        wf_assets._harvest_voice_cache = None

    def tearDown(self) -> None:
        wf_assets._voice_vocab_cache = self.previous_vocab_cache
        wf_assets._pathlist_cache = self.previous_pathlist_cache
        wf_assets._harvest_voice_cache = self.previous_harvest_cache

    @staticmethod
    def _write_voice(root: Path, code_name: str, category: str, filename: str) -> None:
        voice_dir = root / code_name / category
        voice_dir.mkdir(parents=True)
        (voice_dir / filename).write_bytes(b"mp3-fixture")
        (root / code_name / "voiceLines.json").write_text(
            json.dumps({f"{category}/{filename[:-4]}": filename}, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_resolve_voice_dump_accepts_explicit_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"WF_VOICE_DUMP": td}, clear=True
        ):
            self.assertEqual(Path(td).resolve(), wf_assets.resolve_voice_dump())

    def test_resolve_voice_dump_defaults_to_checkout_local_directory_when_unset(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                (Path(wf_assets.__file__).resolve().parent / "voice-dump").resolve(),
                wf_assets.resolve_voice_dump(),
            )

    def test_resolve_voice_dump_rejects_invalid_explicit_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / "not-a-directory"
            file_path.write_bytes(b"")
            invalid_values = (
                "",
                "relative-voices",
                str(Path(td) / "missing"),
                str(file_path),
            )
            for value in invalid_values:
                with self.subTest(value=value), mock.patch.dict(
                    os.environ, {"WF_VOICE_DUMP": value}, clear=True
                ), self.assertRaisesRegex(ValueError, "WF_VOICE_DUMP"):
                    wf_assets.resolve_voice_dump()

    def test_dump_voices_observes_explicit_root_changes_without_reimport(self) -> None:
        with tempfile.TemporaryDirectory() as first_td, tempfile.TemporaryDirectory() as second_td:
            first = Path(first_td)
            second = Path(second_td)
            self._write_voice(first, "hero", "ally", "first.mp3")
            self._write_voice(second, "hero", "ally", "second.mp3")

            with mock.patch.object(wf_assets, "VOICE_DUMP", first):
                with mock.patch.dict(os.environ, {"WF_VOICE_DUMP": str(first)}, clear=True):
                    self.assertEqual(
                        [("ally", "first.mp3", "first.mp3")],
                        wf_assets.dump_voices("hero"),
                    )
                with mock.patch.dict(os.environ, {"WF_VOICE_DUMP": str(second)}, clear=True):
                    self.assertEqual(
                        [("ally", "second.mp3", "second.mp3")],
                        wf_assets.dump_voices("hero"),
                    )

    def test_voice_vocab_cache_is_bound_to_the_resolved_root(self) -> None:
        with tempfile.TemporaryDirectory() as first_td, tempfile.TemporaryDirectory() as second_td:
            first = Path(first_td)
            second = Path(second_td)
            self._write_voice(first, "first", "ally", "only-first.mp3")
            self._write_voice(second, "second", "battle", "only-second.mp3")

            with mock.patch.object(wf_assets, "VOICE_DUMP", first):
                with mock.patch.dict(os.environ, {"WF_VOICE_DUMP": str(first)}, clear=True):
                    first_vocab = wf_assets._voice_vocab()
                with mock.patch.dict(os.environ, {"WF_VOICE_DUMP": str(second)}, clear=True):
                    second_vocab = wf_assets._voice_vocab()

            self.assertIn("ally/only-first.mp3", first_vocab)
            self.assertNotIn("battle/only-second.mp3", first_vocab)
            self.assertIn("battle/only-second.mp3", second_vocab)
            self.assertNotIn("ally/only-first.mp3", second_vocab)

    def test_voice_vocab_cache_refreshes_when_names_change_in_same_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_voice(root, "hero", "ally", "first.mp3")
            with mock.patch.dict(
                    os.environ, {"WF_VOICE_DUMP": str(root)}, clear=True):
                first_vocab = wf_assets._voice_vocab()
                (root / "hero" / "ally" / "second-longer.mp3").write_bytes(b"voice")
                second_vocab = wf_assets._voice_vocab()

            self.assertIn("ally/first.mp3", first_vocab)
            self.assertNotIn("ally/second-longer.mp3", first_vocab)
            self.assertIn("ally/second-longer.mp3", second_vocab)

    def test_path_indexes_refresh_when_generated_files_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pathlist = root / "WF_PATHLIST_recovered.txt"
            harvested = root / "HarvestedPaths.csv"
            pathlist.write_text(
                "character/first/voice/ally/join.mp3\n", encoding="utf-8")
            harvested.write_text(
                "character/first/voice/ally/join.mp3\n", encoding="utf-8")
            with mock.patch.object(wf_assets, "HERE", root):
                self.assertIn("first", wf_assets._pathlist_char_index())
                self.assertIn("first", wf_assets._harvest_voice_index())
                pathlist.write_text(
                    "character/second/voice/battle/skill_0.mp3\n",
                    encoding="utf-8")
                harvested.write_text(
                    "character/second/voice/battle/skill_0.mp3\n",
                    encoding="utf-8")
                self.assertIn("second", wf_assets._pathlist_char_index())
                self.assertIn("second", wf_assets._harvest_voice_index())

    def test_manifest_discovers_dynamic_assets_from_live_terminal(self) -> None:
        code = "hero"
        dump_voice = f"character/{code}/voice/ally/dump.mp3"
        vocab_voice = f"character/{code}/voice/battle/vocab.mp3"
        harvest_voice = f"character/{code}/voice/home/harvest.mp3"
        path_voice = f"character/{code}/voice/words_1/path.mp3"
        story_png = f"character/{code}/ui/story/smile.png"
        missing_voice = f"character/{code}/voice/login/missing.mp3"
        current = {
            dump_voice: ("upload", b"dump", "active.zip!dump"),
            vocab_voice: ("upload", b"vocab", "active.zip!vocab"),
            harvest_voice: ("upload", b"harvest", "active.zip!harvest"),
            path_voice: ("upload", b"path", "active.zip!path"),
            story_png: ("medium", wf_assets.PNG_FAKE + b"story", "active.zip!story"),
        }

        with mock.patch.object(wf_assets, "char_asset_requirements", return_value=[]), \
                mock.patch.object(
                    wf_assets, "dump_voices",
                    return_value=[("ally", "dump.mp3", "台词")]), \
                mock.patch.object(
                    wf_assets, "_voice_vocab",
                    return_value=["battle/vocab.mp3", "login/missing.mp3"]), \
                mock.patch.object(
                    wf_assets, "_harvest_voice_index",
                    return_value={code: [harvest_voice]}), \
                mock.patch.object(
                    wf_assets, "_pathlist_char_index",
                    return_value={code: [path_voice, story_png]}), \
                mock.patch.object(
                    wf_assets, "read_current",
                    side_effect=lambda _store, logical: current.get(logical)), \
                mock.patch.object(
                    wf_assets, "locate",
                    side_effect=AssertionError("manifest must not inspect overlay")), \
                mock.patch.object(wf_assets, "png_dims", return_value=(8, 9)):
            assets = wf_assets.char_asset_manifest(Path("unused"), code)

        by_logical = {item["logical"]: item for item in assets}
        self.assertEqual(set(current), set(by_logical))
        self.assertNotIn(missing_voice, by_logical)
        self.assertEqual("台词", by_logical[dump_voice]["text"])
        self.assertEqual("active.zip!path", by_logical[path_voice]["source"])
        self.assertEqual((8, 9), by_logical[story_png]["dims"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
