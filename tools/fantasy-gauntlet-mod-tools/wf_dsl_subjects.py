"""Capability checks for native player-member skill and power-flip actions.

This is intentionally opt-in: enemy/custom executors have other subject bindings.
The player resolver binds -17 to the executing Member and -18 to its Ball.
BallImpl throws for condition ownership and condition queries; MemberImpl routes
mobility conditions to the shared squad slot. Position/effect commands may use Ball.
"""
from wf_dsl_sig import DslSignatureError


CONDITION_TARGET_COMMANDS = frozenset({
    "CreateCondition", "DeleteCondition", "ExtendCondition",
    "ConditionalsConditionExist", "ConsumeUniqueCondition",
})


def validate_player_action_subjects(tree) -> None:
    """Reject condition operations on the reserved physical-ball subject."""
    def walk(value, path):
        if not isinstance(value, list):
            return
        if (len(value) == 2 and value[0] == "Command"
                and isinstance(value[1], list) and value[1]):
            command = value[1]
            if (command[0] in CONDITION_TARGET_COMMANDS and len(command) > 1
                    and command[1] == -18):
                raise DslSignatureError(
                    f"{path}/{command[0]} p1: physical Ball (-18) does not "
                    "support native condition operations; resolve a Member target")
        for i, child in enumerate(value):
            walk(child, f"{path}[{i}]")
    walk(tree, "player-action")
