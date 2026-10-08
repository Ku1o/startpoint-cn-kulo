# -*- coding: utf-8 -*-
"""check_timeline_sounds.py 的最小自测（合成链 + 合成边归档）。"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/lens-integration"))
sys.path.insert(0, str(REPO / "tools/fantasy-gauntlet-mod-tools"))

import wf_dsl  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def deflate_tree(tree) -> bytes:
    compressor = zlib.compressobj(level=9, wbits=-15)
    return compressor.compress(wf_dsl.encode_amf3(tree)) + compressor.flush()


class TimelineSoundsGateTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module(
            "check_timeline_sounds_under_test",
            Path(__file__).resolve().parent / "check_timeline_sounds.py",
        )
        self.good = deflate_tree(
            {"sequences": [], "sounds": [], "points": [], "circles": []}
        )
        self.bad = deflate_tree({"sequences": []})
        self.logical = "character/x/pixelart/pixelart.timeline.amf3.deflate"

    def test_sounds_problem_covers_the_f1009_shapes(self):
        module = self.module
        self.assertEqual("sounds-absent", module.sounds_problem({"sequences": []}))
        self.assertEqual("sounds-not-array(dict)", module.sounds_problem({"sounds": {}}))
        self.assertEqual("sounds-null-entry", module.sounds_problem({"sounds": [None]}))
        self.assertIsNone(module.sounds_problem({"sounds": []}))

    def test_decode_timeline_like_ignores_non_amf3_payloads(self):
        module = self.module
        tree, reason = module.decode_timeline_like(self.bad)
        self.assertEqual({"sequences": []}, tree)
        self.assertIsNone(reason)
        tree, reason = module.decode_timeline_like(b"\x89PNG\r\n\x1a\n")
        self.assertIsNone(tree)
        self.assertEqual("not-raw-deflate", reason)
        compressor = zlib.compressobj(level=9, wbits=-15)
        raw = compressor.compress(b"plain") + compressor.flush()
        tree, reason = module.decode_timeline_like(raw)
        self.assertIsNone(tree)
        self.assertEqual("not-amf3", reason)

    def _run(self, repo: Path, edge: Path, logical: str, receipt: Path) -> int:
        module = self.module
        rel = module.pc.hrel(logical)
        fake_chain = SimpleNamespace(
            tail="1.4.999",
            manifest={"patches": [{
                "id": "fixture-edge", "version": "1.4.999", "enabled": True,
                "depends_on": "1.4.998", "chain": [edge.name],
            }]},
            index={("common", rel): (edge, "production/upload/aa/member")},
            reads={},
            get=lambda key: self.good,
        )
        argv = [
            "check_timeline_sounds.py", "--edge-version", "1.4.999",
            "--expect-tail", "1.4.999", "--require-logical", logical,
            "--expect-edge", "--pathlist", str(repo / "missing-pathlist.txt"),
            "--receipt", str(receipt), "--no-chain-payload-scan",
        ]
        stdout = io.StringIO()
        code = 0
        try:
            with patch.object(module.pc, "Chain", return_value=fake_chain), \
                    patch.object(module, "REPO", repo), \
                    patch.object(sys, "argv", argv), \
                    contextlib.redirect_stdout(stdout):
                module.main()
        except SystemExit as exc:
            code = exc.code or 0
        return code

    def test_edge_scan_passes_with_sounds_and_fails_without(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            active = repo / "assets/asset-patch/active"
            active.mkdir(parents=True)
            edge = active / "pinball-1.4.998-1.4.999-1-fixture-common.zip"
            with zipfile.ZipFile(edge, "w") as archive:
                archive.writestr("production/upload/aa/member", self.good)
            receipt = repo / "receipt-good.json"
            self.assertEqual(0, self._run(repo, edge, self.logical, receipt))
            report = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual("passed", report["status"])
            self.assertEqual(1, len(report["edge_member_scan"]["timeline_like"]))
            with zipfile.ZipFile(edge, "w") as archive:
                archive.writestr("production/upload/aa/member", self.bad)
            receipt = repo / "receipt-bad.json"
            self.assertEqual(1, self._run(repo, edge, self.logical, receipt))
            report = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual("failed", report["status"])
            reasons = {item["reason"] for item in report["problems"]}
            self.assertIn("sounds-absent", reasons)

    def test_donor_edge_archive_missing_is_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            active = repo / "assets/asset-patch/active"
            active.mkdir(parents=True)
            edge = active / "absent.zip"
            receipt = repo / "receipt.json"
            self.assertEqual(1, self._run(repo, edge, self.logical, receipt))
            report = json.loads(receipt.read_text(encoding="utf-8"))
            reasons = {item["reason"] for item in report["problems"]}
            self.assertIn("archive missing", reasons)


if __name__ == "__main__":
    unittest.main()
