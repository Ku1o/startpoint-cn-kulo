from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wf_dsl_sig import DslSignatureError
from wf_dsl_subjects import validate_player_action_subjects


class PlayerActionSubjectTests(unittest.TestCase):
    def test_skill_and_pf_condition_commands_reject_physical_ball(self):
        # Values following the target are immaterial to this capability gate.
        # Full serialization signatures are checked by the separate type guard.
        for name in ("CreateCondition", "DeleteCondition", "ExtendCondition",
                     "ConditionalsConditionExist", "ConsumeUniqueCondition"):
            with self.subTest(command=name):
                tree = ["Block", [["Event", ["Wait", 60, "*",
                    ["Block", [["Command", [name, -18]]]]]]]]
                with self.assertRaisesRegex(DslSignatureError, "physical Ball"):
                    validate_player_action_subjects(tree)

    def test_member_and_found_targets_allow_condition_commands(self):
        for target in (-17, 5, 6):
            validate_player_action_subjects(
                ["Command", ["CreateCondition", target]])

    def test_effect_follow_and_pf_end_keep_the_ball_target(self):
        for name in ("ShowEffect", "NotifyPowerflipEnd"):
            validate_player_action_subjects(["Command", [name, -18]])


if __name__ == "__main__":
    unittest.main()
