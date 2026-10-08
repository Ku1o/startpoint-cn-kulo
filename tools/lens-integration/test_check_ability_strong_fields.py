# -*- coding: utf-8 -*-
"""check_ability_strong_fields.py 的最小自测（真实坏行夹具 + 合成表）。"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/fantasy-gauntlet-mod-tools"))

import wf_mod_tool as core  # noqa: E402

FIXTURE = (
    REPO / "tools/fantasy-gauntlet-mod-tools/tests/fixtures/"
    "liangyue-c7101-bool-rows.json"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def orderedmap(rows: dict[str, str]) -> bytes:
    keys = list(rows)
    payloads = [
        zlib.compress(rows[key].encode("utf-8"))
        for key in keys
    ]
    table = core.OrderedMap("[fixture]", keys, payloads, Path("[memory]"))
    return core.build_orderedmap_raw_rows(table)


class AbilityStrongFieldsGateTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module(
            "check_ability_strong_fields_under_test",
            Path(__file__).resolve().parent / "check_ability_strong_fields.py",
        )
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.cases = {case["kind"]: case for case in data["cases"]}

    def _check(self, kind: str, row: list[str], expected_cells=None, key="fixture",
               row_index=0):
        module = self.module
        logical = (
            "master/ability/leader_ability.orderedmap"
            if kind == "leader_ability" else "master/ability/ability.orderedmap"
        )
        tables = {entry[0]: entry for entry in module.TABLES}
        _, _, dispatch_col, bool_col, during_col, multiply_col, trigger_col = tables[kind]
        problems: list[dict] = []
        filler = ["0"] * len(row)
        filler[trigger_col] = "2"          # 开幕模式：全表扫描跳过的占位行
        lines = [",".join(filler)] * row_index + [",".join(row)]
        report = module.check_table(
            orderedmap({key: "\n".join(lines)}), logical, kind,
            dispatch_col, bool_col, during_col, multiply_col, trigger_col,
            problems, "fixture", expected_cells=expected_cells,
        )
        return report, problems

    def test_real_preimage_rows_are_rejected(self):
        for kind, case in self.cases.items():
            _, problems = self._check(kind, case["preimage_row"])
            reasons = {item["reason"] for item in problems}
            self.assertIn("illegal-bool", reasons, kind)
            self.assertIn("illegal-enum", reasons, kind)

    def test_fixed_rows_pass_and_expected_cells_are_checked(self):
        for kind, case in self.cases.items():
            row = list(case["preimage_row"])
            for column, value in case["columns"].items():
                row[int(column)] = value
            # 该夹具行同时属于 1.4.136 的 Option 空串类（flip_limit 族 +
            # max_accumulation）：按真实修复值补 (None) 后整行才干净。
            dispatch = 45 if kind == "leader_ability" else 47
            row[dispatch + 14] = "(None)"
            for offset in (15, 16, 17, 18):
                row[dispatch + offset] = "(None)"
            _, problems = self._check(kind, row)
            self.assertEqual([], problems, kind)
            expected = {
                case["key"]: {case["row"]: {72: "false", 75: "0"}}
            }
            if kind == "leader_ability":
                expected = {case["key"]: {case["row"]: {70: "false", 73: "0"}}}
            _, problems = self._check(
                kind, row, expected_cells=expected, key=case["key"],
                row_index=case["row"])
            self.assertEqual([], problems, kind)
            wrong = {
                case["key"]: {case["row"]: {
                    (70 if kind == "leader_ability" else 72): "true"}}
            }
            _, problems = self._check(
                kind, row, expected_cells=wrong, key=case["key"],
                row_index=case["row"])
            reasons = {item["reason"] for item in problems}
            self.assertIn("expected-cell-mismatch", reasons, kind)

    def test_tab_le_contract_matches_parser_provenance(self):
        module = self.module
        for kind, logical, dispatch, bool_col, during, multiply, trigger in module.TABLES:
            self.assertEqual(dispatch + 25, bool_col)
            self.assertEqual(dispatch + 28, multiply)
            self.assertEqual(
                module.wf_client_legality.INSTANT_CONTENT_BOOL_KINDS,
                module.INSTANT_CONTENT_BOOL_KINDS,
            )


if __name__ == "__main__":
    unittest.main()
