from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_dsl_sig  # noqa: E402


def fixed(value: float) -> list[dict[str, float]]:
    return [{"min": value, "max": value}]


def skill_tree() -> list:
    return [
        "ActionDsl", 2, ["None"], False, False, False, False, False,
        False, False, 0,
        ["Block", [["Command", ["AddSkillPoint", 20, fixed(0.20)]]]],
    ]


class DslSignatureGuardTest(unittest.TestCase):
    def test_ratio_edit_may_change_only_add_skill_point_parameter_two(self) -> None:
        before = skill_tree()
        after = copy.deepcopy(before)
        after[11][1][0][1][2] = fixed(0.15)
        wf_dsl_sig.assert_command_parameter_edits(
            before, after, {"AddSkillPoint": {2}})

    def test_target_id_edit_is_rejected_even_when_it_is_still_an_int(self) -> None:
        before = skill_tree()
        after = copy.deepcopy(before)
        after[11][1][0][1][1] = 15
        with self.assertRaisesRegex(
                wf_dsl_sig.DslSignatureError, "对象ID.*未经授权"):
            wf_dsl_sig.assert_command_parameter_edits(
                before, after, {"AddSkillPoint": {2}})

    def test_wrong_parameter_type_is_rejected_by_official_signature(self) -> None:
        tree = skill_tree()
        tree[11][1][0][1][1] = fixed(20)
        with self.assertRaisesRegex(
                wf_dsl_sig.DslSignatureError, "对象ID.*类型不符"):
            wf_dsl_sig.validate_action_dsl(tree)


if __name__ == "__main__":
    unittest.main()
