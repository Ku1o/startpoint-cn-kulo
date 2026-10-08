# -*- coding: utf-8 -*-
"""客户端 master 行合法性门禁回归。

2026-10-06 凉月(159992)角色详情 C7101:三条能力行的
`by_each_trigger_puller`(ability c72 / leader_ability c70)是空串,而生成解析器
`AbilityValues$/parseAt47 -> parseAt72`、`LeaderAbilityValues$/parseAt45 -> parseAt70`
只接受 TRUE/True/true/FALSE/False/false,空串直接 throw ClientError 7101。
本测试用真实坏行夹具锁住该规则,并确认 composer 生成的条件类瞬发行不再留空。
"""
from __future__ import annotations

import json
import ast
import sys
import unittest
from pathlib import Path


MOD_TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MOD_TOOLS))

import wf_ability_composer  # noqa: E402
import wf_client_legality  # noqa: E402
import wf_describe  # noqa: E402

FIXTURE = (Path(__file__).resolve().parent / "fixtures"
           / "liangyue-c7101-bool-rows.json")
OPTION_FIXTURE = (Path(__file__).resolve().parent / "fixtures"
                  / "liangyue-f1009-option-rows.json")


def _bool_problems(kind: str, row: list[str]) -> list[str]:
    return [p for p in wf_client_legality.client_legality_problems(kind, row)
            if "by_each_trigger_puller" in p]


def _multiply_problems(kind: str, row: list[str]) -> list[str]:
    return [p for p in wf_client_legality.client_legality_problems(kind, row)
            if "multiply_trigger" in p]


def _option_problems(kind: str, row: list[str]) -> list[str]:
    return wf_client_legality.option_cell_problems(kind, row)


class InstantContentBoolLegalityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_real_preimage_rows_are_rejected(self) -> None:
        cases = self.fixture["cases"]
        self.assertEqual(3, len(cases))
        for case in cases:
            with self.subTest(key=case["key"], column=case["column"]):
                self.assertTrue(all(v == "" for v in case["preimage_values"].values()))
                problems = _bool_problems(case["kind"], case["preimage_row"])
                self.assertEqual(1, len(problems), problems)
                self.assertIn(f"c{case['column']}", problems[0])
                self.assertIn("C7101", problems[0])
                multiply = _multiply_problems(case["kind"], case["preimage_row"])
                self.assertEqual(1, len(multiply), multiply)
                self.assertIn("C7050", multiply[0])

    def test_real_fixed_rows_pass(self) -> None:
        for case in self.fixture["cases"]:
            with self.subTest(key=case["key"], column=case["column"]):
                self.assertEqual("false",
                                 case["fixed_row"][case["column"]])
                # 该夹具停在 1.4.135(C7101 修复后、描述 F1009 修复前),
                # 因此只断言 Bool/枚举两条规则通过;Option 列由
                # liangyue-f1009-option-rows.json 与下面的 Option 测试覆盖。
                self.assertEqual(
                    [], _bool_problems(case["kind"], case["fixed_row"]))
                self.assertEqual(
                    [], _multiply_problems(case["kind"], case["fixed_row"]))

    def test_invalid_literal_is_rejected(self) -> None:
        for case in self.fixture["cases"]:
            broken = list(case["fixed_row"])
            broken[case["column"]] = "yes"
            with self.subTest(key=case["key"]):
                self.assertEqual(1, len(_bool_problems(case["kind"], broken)))

    def test_uppercase_literals_are_accepted(self) -> None:
        for case in self.fixture["cases"]:
            for literal in ("TRUE", "True", "false", "False", "false"):
                row = list(case["fixed_row"])
                row[case["column"]] = literal
                with self.subTest(key=case["key"], literal=literal):
                    self.assertEqual([], _bool_problems(case["kind"], row))

    def test_non_condition_content_does_not_require_the_bool(self) -> None:
        row = [""] * int(wf_describe.layout("ability")["ncols"])
        base = int(wf_describe.layout("ability")["blocks"]["instant_content"])
        row[base] = "211"  # SkillGauge has no by_each_trigger_puller field
        self.assertEqual([], _bool_problems("ability", row))
        self.assertNotIn("211", wf_client_legality.INSTANT_CONTENT_BOOL_KINDS)
        self.assertIn("0", wf_client_legality.INSTANT_CONTENT_BOOL_KINDS)
        self.assertIn("489", wf_client_legality.INSTANT_CONTENT_BOOL_KINDS)
        self.assertNotIn("211", wf_client_legality.INSTANT_CONTENT_MULTIPLY_KINDS)
        self.assertIn("0", wf_client_legality.INSTANT_CONTENT_MULTIPLY_KINDS)
        self.assertIn("489", wf_client_legality.INSTANT_CONTENT_MULTIPLY_KINDS)

    def test_studio_copy_keeps_the_same_kind_set(self) -> None:
        """studio 是独立目录(本机 junction),它的 core 副本必须同集合。"""
        tools_dir = Path(__file__).resolve().parents[2]
        studio = tools_dir / "character-studio/core/wf_client_legality.py"
        self.assertTrue(studio.is_file(), studio)
        tree = ast.parse(studio.read_text(encoding="utf-8"))
        found = {}
        for node in tree.body:
            if (isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", "") in (
                        "INSTANT_CONTENT_BOOL_KINDS",
                        "INSTANT_CONTENT_LIMIT_KINDS",
                        "INSTANT_CONTENT_MAX_ACCUMULATION_KINDS")):
                found[getattr(node.targets[0], "id", "")] = \
                    ast.literal_eval(node.value.args[0])
        self.assertEqual(wf_client_legality.INSTANT_CONTENT_BOOL_KINDS,
                         frozenset(found["INSTANT_CONTENT_BOOL_KINDS"]))
        self.assertEqual(wf_client_legality.INSTANT_CONTENT_LIMIT_KINDS,
                         frozenset(found["INSTANT_CONTENT_LIMIT_KINDS"]))
        self.assertEqual(
            wf_client_legality.INSTANT_CONTENT_MAX_ACCUMULATION_KINDS,
            frozenset(found["INSTANT_CONTENT_MAX_ACCUMULATION_KINDS"]))


class InstantContentOptionLegalityTest(unittest.TestCase):
    """2026-10-06 凉月角色详情 F1009:条件类瞬发的 Option 列不得留空。

    `parseAt{61..65}`(leader 为 `parseAt{59..63}`)只把字面量 '(None)' 读成
    Option.None;空串读成 Some(null)/Some(0),`resolveEndPowerFlipLevels` 对
    Some(0) 落空返回 undefined,描述生成器再对 null 取 .length 抛
    TypeError #1009。
    """

    def setUp(self) -> None:
        self.fixture = json.loads(OPTION_FIXTURE.read_text(encoding="utf-8"))

    def test_real_preimage_rows_are_rejected(self) -> None:
        cases = self.fixture["cases"]
        self.assertEqual(3, len(cases))
        for case in cases:
            with self.subTest(key=case["key"]):
                self.assertTrue(
                    all(v == "" for v in case["preimage_values"].values()))
                problems = _option_problems(case["kind"], case["preimage_row"])
                self.assertEqual(len(case["columns"]), len(problems), problems)
                for column in case["columns"]:
                    self.assertTrue(any(f"c{column} " in p for p in problems),
                                    (column, problems))

    def test_real_fixed_rows_pass(self) -> None:
        for case in self.fixture["cases"]:
            with self.subTest(key=case["key"]):
                self.assertEqual([], _option_problems(case["kind"],
                                                      case["fixed_row"]))
                self.assertEqual(
                    [], wf_client_legality.client_legality_problems(
                        case["kind"], case["fixed_row"]))

    def test_empty_option_cell_is_rejected_after_fix(self) -> None:
        for case in self.fixture["cases"]:
            for column in case["columns"]:
                broken = list(case["fixed_row"])
                broken[int(column)] = ""
                with self.subTest(key=case["key"], column=column):
                    self.assertEqual(
                        1, len(_option_problems(case["kind"], broken)))

    def test_end_power_flip_levels_value_table(self) -> None:
        for case in self.fixture["cases"]:
            levels_column = max(int(c) for c in case["columns"])
            if levels_column not in (65, 63):
                continue
            for value in ("(None)", "1", "2", "3", "11", "12"):
                row = list(case["fixed_row"])
                row[levels_column] = value
                with self.subTest(key=case["key"], value=value):
                    self.assertEqual([], _option_problems(case["kind"], row))
            for value in ("0", "4", "7", "13", "99"):
                row = list(case["fixed_row"])
                row[levels_column] = value
                with self.subTest(key=case["key"], value=value):
                    problems = _option_problems(case["kind"], row)
                    self.assertEqual(1, len(problems), problems)
                    self.assertIn("resolveEndPowerFlipLevels", problems[0])

    def test_kind_sets_match_parser_reachability(self) -> None:
        limits = wf_client_legality.INSTANT_CONTENT_LIMIT_KINDS
        self.assertEqual(78, len(limits))
        for value in ("0", "24", "26", "489", "718"):
            self.assertIn(value, limits)
        for value in ("32", "211", "226", "629"):
            self.assertNotIn(value, limits)
        accumulation = wf_client_legality.INSTANT_CONTENT_MAX_ACCUMULATION_KINDS
        self.assertEqual(95, len(accumulation))
        for value in ("0", "24", "28"):
            self.assertIn(value, accumulation)
        self.assertNotIn("489", accumulation)
        self.assertEqual(
            frozenset({"1", "2", "3", "11", "12"}),
            wf_client_legality.END_POWER_FLIP_LEVEL_VALUES)

    def test_composer_writes_none_for_option_cells(self) -> None:
        for kind in ("ability", "leader_ability"):
            layout = wf_describe.layout(kind)
            base = int(layout["blocks"]["instant_content"])
            for effect_kind in ("0", "24", "489"):
                with self.subTest(kind=kind, effect=effect_kind):
                    row = wf_ability_composer.generate(
                        dst_key="1599921", mode="instant", trigger_kind="20",
                        effect_kind=effect_kind, target="0", value=10,
                        value_max=10,
                        blank_factory=lambda key: {
                            "key": "fixture", "kind": kind, "line": None,
                            "ncols": int(layout["ncols"]),
                            "row": self._blank_row(layout), "desc": ""},
                        metadata=wf_ability_composer.composer_meta,
                        element_index=lambda key: 0)["row"]
                    for offset in (15, 16, 17, 18):
                        self.assertEqual("(None)", row[base + offset])
                    if effect_kind in ("0", "24"):
                        self.assertEqual("(None)", row[base + 14])
                    self.assertEqual(
                        [], _option_problems(kind, row))

    @staticmethod
    def _blank_row(layout: dict) -> list[str]:
        blocks = layout["blocks"]
        row = [""] * int(layout["ncols"])
        for name in ("precondition1", "precondition2", "precondition3"):
            row[int(blocks[name])] = "0"
        row[int(blocks["instant_precontent"])] = "(None)"
        row[int(blocks["instant_delay"])] = "0"
        return row


class ComposerBoolDefaultTest(unittest.TestCase):
    """composer 生成的条件类瞬发行必须自带合法 Bool(否则再次 C7101)。"""

    def _blank_factory(self, kind: str) -> dict:
        layout = wf_describe.layout(kind)
        blocks = layout["blocks"]
        row = [""] * int(layout["ncols"])
        for name in ("precondition1", "precondition2", "precondition3"):
            row[int(blocks[name])] = "0"
        row[int(blocks["instant_precontent"])] = "(None)"
        row[int(blocks["instant_delay"])] = "0"
        return {"key": "fixture", "kind": kind, "line": None,
                "ncols": int(layout["ncols"]), "row": row, "desc": ""}

    def _generate(self, kind: str, effect_kind: str) -> list[str]:
        result = wf_ability_composer.generate(
            dst_key="1599921", mode="instant", trigger_kind="20",
            effect_kind=effect_kind, target="0", value=10, value_max=10,
            blank_factory=lambda key: self._blank_factory(kind),
            metadata=wf_ability_composer.composer_meta,
            element_index=lambda key: 0)
        return result["row"]

    def test_condition_kinds_get_false(self) -> None:
        for kind, column in (("ability", 72), ("leader_ability", 70)):
            for effect_kind in ("0", "24", "489"):
                with self.subTest(kind=kind, effect=effect_kind):
                    row = self._generate(kind, effect_kind)
                    self.assertEqual("false", row[column])
                    self.assertEqual("0", row[column + 3])
                    self.assertEqual([], _bool_problems(kind, row))

    def test_non_condition_kind_stays_empty(self) -> None:
        row = self._generate("ability", "211")
        self.assertEqual("", row[72])
        self.assertEqual([], _bool_problems("ability", row))


if __name__ == "__main__":
    unittest.main()
