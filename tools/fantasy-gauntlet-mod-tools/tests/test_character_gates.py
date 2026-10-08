# -*- coding: utf-8 -*-
"""新角色四道边界门禁的单元测试（纯逻辑 + 伪造 live store）。"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wf_character_gates as gates  # noqa: E402
import wf_character_flow as flow  # noqa: E402
import wf_mod_tool as core  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def table_bytes(rows: dict[str, str]) -> bytes:
    table = core.OrderedMap(
        "[gate-test]", list(rows),
        [zlib.compress(value.encode("utf-8")) for value in rows.values()],
        Path("[memory]"),
    )
    raw = core.build_orderedmap_raw_rows(table)
    assert core.read_orderedmap_file_from_bytes(raw) == rows
    return raw


class TestRepoBoundary(unittest.TestCase):
    def test_member_paths_accept_only_production_roots(self):
        good = "production/upload/ab/" + "c" * 40
        self.assertEqual([], gates.member_path_problems(good))
        self.assertEqual([], gates.member_path_problems(
            "production/medium_upload/ab/" + "d" * 40))
        for bad in (
            "production/production/upload/ab/x",
            "production/upload/../../x",
            "production/upload/C:/x",
            "production/other/ab/x",
            "production\\\\upload\\\\ab\\\\x",
            "/production/upload/ab/x",
        ):
            self.assertTrue(gates.member_path_problems(bad), bad)

    def test_cdn_component_detection_follows_resolved_parts(self):
        self.assertTrue(gates.resolved_parts_include_cdn(
            Path("F:/codex/startpoint-cn-private-clean/.cdn/cn")))
        self.assertTrue(gates.resolved_parts_include_cdn("F:/x/.CDN/cn"))
        self.assertFalse(gates.resolved_parts_include_cdn(
            "F:/codex/startpoint-cn-private-clean/assets/asset-patch/active"))

    def test_archive_member_report_counts_roots_and_duplicates(self):
        report = gates.archive_member_report(
            ["production/upload/aa/" + "1" * 40,
             "production/upload/aa/" + "1" * 40]
        )
        self.assertEqual(1, report["members"])
        self.assertTrue(any("重复" in item for item in report["problems"]))


class TestChainBoundary(unittest.TestCase):
    def test_outer_key_union_flags_removed_keys(self):
        report = gates.outer_key_union_report({"a": "r1", "b": "r2"}, {"a": "r1", "c": "r3"})
        self.assertEqual(["b"], report["removed"])
        self.assertEqual(["c"], report["added"])
        self.assertTrue(report["problems"])

    def test_declared_row_merge_reports_missing_declared_key(self):
        report = gates.declared_row_merge_report({"a": "r1"}, {"a": "r2"}, ["a", "missing"])
        self.assertEqual(1, len(report["declared"]))
        self.assertTrue(report["declared"][0]["changed"])
        self.assertTrue(report["problems"])

    def test_a_package_must_carry_every_live_outer_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            package = root / "package"
            store.mkdir()
            logical = "master/character/character.orderedmap"
            live = core.table_path(store, logical)
            live.parent.mkdir(parents=True)
            live.write_bytes(table_bytes({"596": "live-a", "597": "live-b"}))
            candidate = package / "roots/common" / Path(*logical.split("/"))
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(table_bytes({"596": "live-a"}))
            (package / "manifest.json").write_text(json.dumps({
                "roots": {"common": [{"logical_path": logical}], "server": []},
            }), encoding="utf-8")
            report = flow.production_key_union_report(
                package, stores=(store,), server_root=None,
            )
            self.assertTrue(report["problems"])
            self.assertIn("597", " ".join(report["problems"]))


class TestStructuralContract(unittest.TestCase):
    def test_timeline_requires_sounds_and_official_key_set(self):
        problems = gates.structural_problems(
            "character/x/pixelart/pixelart.timeline.amf3.deflate", {"sequences": []},
        )
        self.assertTrue(any("缺键" in item for item in problems))
        self.assertTrue(any("sounds" in item for item in problems))
        self.assertEqual([], gates.structural_problems(
            "character/x/pixelart/pixelart.timeline.amf3.deflate",
            {"sequences": [], "sounds": [], "points": [], "circles": []},
        ))

    def test_atlas_geometry_follows_client_draw_position(self):
        good = [{"n": "character/x/pixelart/pixelart0002", "w": 13, "h": 13,
                 "x": 1, "y": 1, "fx": -110, "fy": -103, "fw": 256, "fh": 256}]
        self.assertEqual([], gates.atlas_problems(
            "character/x/pixelart/sprite_sheet.atlas.amf3.deflate", good))
        broken = [dict(good[0], fx=98, fy=91)]  # (-fx,-fy)=(-98,-91) 为负
        problems = gates.atlas_problems(
            "character/x/pixelart/sprite_sheet.atlas.amf3.deflate", broken)
        self.assertTrue(any("负" in item for item in problems))

    def test_anchor_regression_catches_the_1_4_143_sign_error(self):
        before = [{"n": "character/x/pixelart/pixelart0002", "w": 37, "h": 25,
                   "x": 1, "y": 1, "fx": -110, "fy": -103, "fw": 256, "fh": 256}]
        wrong = [dict(before[0], w=13, h=13, fx=-98, fy=-91)]   # 1.4.143 实况
        report = gates.anchor_regression_report(before, wrong, dx=12, dy=12, label="fixture")
        self.assertTrue(report["problems"])
        self.assertEqual(-24, report["deviations"][0]["delta"][0] - 12)
        fixed = [dict(before[0], w=13, h=13, fx=-122, fy=-115)]  # v2 修正方向
        report = gates.anchor_regression_report(before, fixed, dx=12, dy=12, label="fixture")
        self.assertEqual([], report["problems"])
        self.assertEqual(0, report["max_deviation"])
        report = gates.anchor_regression_report(
            before, [dict(before[0])], dx=12, dy=12, keep_frames=[2], label="fixture")
        self.assertEqual([], report["problems"])

    def test_frame_and_parts_key_sets(self):
        self.assertEqual([], gates.structural_problems(
            "character/x/pixelart/pixelart.frame.amf3.deflate",
            {"name": "character/x/pixelart/pixelart", "x": -128, "y": -128,
             "scale": 6, "smoothing": False},
        ))
        problems = gates.structural_problems(
            "character/x/pixelart/pixelart.frame.amf3.deflate",
            {"name": "x", "x": 0, "y": 0, "scale": 6},
        )
        self.assertTrue(problems)


class TestParserContract(unittest.TestCase):
    def _blank_row(self, table_kind: str):
        layout = gates.wf_describe.layout(table_kind)
        row = [""] * layout["ncols"]
        blocks = layout["blocks"]
        row[blocks["precondition1"] - 1] = "0"
        for name in ("precondition1", "precondition2", "precondition3"):
            row[blocks[name]] = "0"
        row[blocks["instant_trigger"]] = "23"
        row[blocks["instant_precontent"]] = "(None)"
        row[blocks["instant_delay"]] = "0"
        return row, blocks

    def test_bool_and_enum_and_option_cells_are_fail_closed(self):
        row, blocks = self._blank_row("ability")
        base = blocks["instant_content"]
        row[base] = "24"
        row[base + 4] = row[base + 5] = "50000"
        row[base + 25] = ""                  # by_each_trigger_puller 空 -> C7101
        row[base + 28] = ""                  # multiply_trigger 空 -> C7050
        report = gates.typed_row_problems("ability", row)
        joined = " ".join(report["errors"])
        self.assertIn("C7101", joined)
        self.assertIn("C7050", joined)
        row[base + 25] = "false"
        row[base + 28] = "0"
        row[base + 14] = ""                  # max_accumulation 空 -> F1009 类
        row[base + 12] = ""                  # flip_limit 空 -> F1009 类
        report = gates.typed_row_problems("ability", row)
        joined = " ".join(report["errors"])
        self.assertIn("F1009", joined)
        self.assertIn("flip_limit", joined)

    def test_empty_initial_multiply_is_error_only_when_parser_reads_it(self):
        row, blocks = self._blank_row("ability")
        base = blocks["instant_content"]
        row[base] = "0"                      # kind 0：解析器读取 initial_multiply
        row[base + 4] = row[base + 5] = "10000"
        row[base + 25] = "false"
        row[base + 28] = "0"
        row[base + 14] = "(None)"
        report = gates.typed_row_problems("ability", row)
        self.assertTrue(any("initial_multiply" in item for item in report["errors"]))
        row[base + 14] = "12"                # max_accumulation>1 -> warning
        report = gates.typed_row_problems("ability", row)
        self.assertFalse(any("initial_multiply" in item for item in report["errors"]))
        self.assertTrue(any("initial_multiply" in item for item in report["warnings"]))

    def test_precedent_report_flags_zero_precedent_kind(self):
        row, blocks = self._blank_row("ability")
        row[blocks["instant_content"]] = "24"
        report = gates.precedent_report("ability", row)
        self.assertEqual([], report["problems"])
        self.assertEqual(1, report["groups"][-1]["official_count"])
        row[blocks["instant_content"]] = "999999"
        report = gates.precedent_report("ability", row)
        self.assertTrue(report["problems"])

    def test_real_bad_row_fixtures_are_rejected(self):
        fixture = FIXTURES / "liangyue-c7101-bool-rows.json"
        if not fixture.is_file():
            self.skipTest("fixture missing")
        data = json.loads(fixture.read_text(encoding="utf-8"))
        checked = 0
        for case in data["cases"]:
            checked += 1
            report = gates.typed_row_problems(case["kind"], case["preimage_row"])
            self.assertTrue(
                any("C7101" in item or "C7050" in item for item in report["errors"]),
                f"{case['kind']}:{case['key']} 坏行未被拒绝",
            )
        self.assertEqual(3, checked)


class TestFlowBoundaryGates(unittest.TestCase):
    def test_release_root_must_not_be_inside_pristine_cdn(self):
        with self.assertRaisesRegex(flow.FlowError, r"\.cdn"):
            flow.assert_writable_release_root(
                SimpleNamespace(cdn_root=Path("F:/repo/.cdn/cn")))
        with tempfile.TemporaryDirectory() as tmp:
            flow.assert_writable_release_root(SimpleNamespace(cdn_root=Path(tmp) / "cdn"))

    def test_live_store_drift_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            package = root / "package"
            store.mkdir()
            package.mkdir()
            logical = "master/ability/ability.orderedmap"
            live = core.table_path(store, logical)
            live.parent.mkdir(parents=True)
            live.write_bytes(table_bytes({"1": "row"}))
            (package / "manifest.json").write_text(json.dumps({
                "snapshot": {"runtime_rebase": {"tables": [{
                    "root": "common", "logical_path": logical,
                    "live_before_sha256": hashlib.sha256(live.read_bytes()).hexdigest(),
                }]}},
            }), encoding="utf-8")
            report = flow.live_store_drift_report(package, stores=(store,), server_root=None)
            self.assertEqual([], report["problems"])
            live.write_bytes(table_bytes({"1": "row", "2": "other-task"}))
            report = flow.live_store_drift_report(package, stores=(store,), server_root=None)
            self.assertTrue(report["problems"])
            self.assertIn("漂移", " ".join(report["problems"]))

    def test_base_state_composite_without_declaration_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            payload = {
                "animations": [
                    {"slot": "neutral", "variant": "composite"},
                    {"slot": "skill_ready", "variant": "composite",
                     "includesCompanion": True, "companionNote": "开大时出现"},
                ],
                "uiDeclarations": {"base:square": {"autoCrop": True, "mask": "none"}},
                "effects": [{"origin": "reuse"}],
            }
            (package / "declarations.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            report = flow.declaration_report(package)
            self.assertTrue(report["blocking"])
            self.assertIn("neutral", " ".join(report["blocking"]))
            self.assertTrue(any("UI 用途" in item for item in report["warnings"]))
            self.assertTrue(any("voiceDeclarations" in item for item in report["warnings"]))
            payload["animations"][0]["includesCompanion"] = True
            (package / "declarations.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            self.assertEqual([], flow.declaration_report(package)["blocking"])


class TestEdgeGateCli(unittest.TestCase):
    def test_edge_gate_cli_accepts_the_fixed_1_4_145_edge(self):
        repo = Path(__file__).resolve().parents[3]
        script = repo / "tools/lens-integration/check_character_edge.py"
        manifest = repo / "assets/asset-patch/manifest.json"
        entry_ok = manifest.is_file() and any(
            item.get("version") == "1.4.145" and item.get("enabled")
            for item in json.loads(manifest.read_text(encoding="utf-8")).get("patches", ())
        )
        if not entry_ok or not script.is_file():
            self.skipTest("1.4.145 edge or gate script unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.json"
            result = subprocess.run(
                [sys.executable, str(script), "--edge-version", "1.4.145",
                 "--receipt", str(receipt)],
                cwd=str(repo), capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            report = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual("passed", report["status"])
            roles = {row["role"]
                     for row in report["sections"]["structural_contract"]["members"]}
            self.assertIn("pixelart-atlas", roles)


if __name__ == "__main__":
    unittest.main()
