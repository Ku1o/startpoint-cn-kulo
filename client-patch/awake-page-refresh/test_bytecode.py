"""Replay the actual callback instructions against the observed client state contract.

This is a bounded AVM2 instruction interpreter, not a device or AIR runtime test.
Both the original failing payload and patched readback must exercise the model.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from patch_swf import s


def run(abc, body_index, scene, argument):
    code = s.m.asm.decode(abc.bodies[body_index][5])
    stack, locals_ = [], [scene, argument, None]
    pc = 0
    steps = 0
    while pc < len(code):
        steps += 1
        assert steps < 300
        ins = code[pc]
        pc += 1
        op, args = ins.op, ins.args
        name = abc.s(abc.multinames[args[0]][2]) if op in (0x5e, 0x66, 0x68, 0x46, 0x4f) else None
        if op in (0xd0, 0xd1, 0xd2):
            stack.append(locals_[op - 0xd0])
        elif op in (0xd5, 0xd6):
            locals_[op - 0xd4] = stack.pop()
        elif op == 0x30:
            assert stack.pop() is scene
        elif op == 0x5e:
            stack.append(scene)
        elif op == 0x66:
            stack.append(getattr(stack.pop(), name))
        elif op == 0x68:
            value = stack.pop()
            setattr(stack.pop(), name, value)
        elif op in (0x46, 0x4f):
            count = args[1]
            values = stack[-count:] if count else []
            if count:
                del stack[-count:]
            receiver = stack.pop()
            if isinstance(receiver, list) and name == "indexOf":
                value = receiver.index(values[0]) if values[0] in receiver else -1
            elif isinstance(receiver, list) and name == "splice":
                at, length = values
                value = receiver[at:at + length]
                del receiver[at:at + length]
            else:
                value = getattr(receiver, name)(*values)
            if op == 0x46:
                stack.append(value)
        elif op == 0x24:
            stack.append(args[0])
        elif op == 0x26:
            stack.append(True)
        elif op == 0x80:
            assert stack  # The patch retains preparation's original cast operands.
        elif op == 0x73:
            stack.append(int(stack.pop()))
        elif op in (0x15, 0x16):
            right, left = stack.pop(), stack.pop()
            if (left < right) if op == 0x15 else (left <= right):
                pc = ins.target
        elif op == 0x47:
            assert not stack
            return
        else:
            raise AssertionError(f"Unaudited callback opcode: {op:x}")
    raise AssertionError("Callback did not return")


class Owned:
    def __init__(self, save):
        self.map = save.map

    def getManaBoardAwakeLevel(self, board):
        return self.map.get(board, 0)


class Player:
    def __init__(self, save):
        self.save = save

    def getOwnedCharacter(self, character):
        assert character == 211002
        return Owned(self.save)


class Tabs:
    def __init__(self, level, current):
        self.disabledTabButtons = [2] if level == 0 else []
        self.states = {1: 2 if current == 1 else 1, 2: 4 if level == 0 else (2 if current == 2 else 1)}

    def enableOnlyActiveTab(self, current):
        for kind in [1, 2]:
            if kind not in self.disabledTabButtons:
                self.states[kind] = 2 if kind == current else 1


class Scene:
    def __init__(self, old, current):
        self.save = SimpleNamespace(map={1: old})
        player = Player(self.save)
        self.globalLogic = SimpleNamespace(get_player=lambda: player)
        self.characterId = 211002
        self.targetCharacter = player.getOwnedCharacter(self.characterId)
        self.boardAwakeLevel = old
        self.currentTabKind = current
        self.tabGroup = Tabs(old, current)
        self.hasRequestMissionList = False
        self.missionMap = None
        self.reloads = 0

    def reload(self):
        self.reloads += 1


def load(path):
    return [tag[3] for tag in s.parts(path)[2] if tag[0] == 82][290]


def main(source, candidate):
    original, patched = load(source), load(candidate)
    before = Scene(0, 1)
    before.save.map = {1: 1}
    run(original, 67327, before, {9: ["completed"]})
    assert before.boardAwakeLevel == before.targetCharacter.getManaBoardAwakeLevel(1) == 0
    assert 2 in before.tabGroup.disabledTabButtons
    cases = []
    for old, new, current in [(0, 1, 1), (0, 0, 1), (1, 1, 1), (1, 1, 2), (0, 2, 1)]:
        scene = Scene(old, current)
        scene.save.map = {1: new}  # Real common response replaces this map before the callback.
        mission_map = {9: ["server progress"]}
        for repeat in range(3):
            run(patched, 67327, scene, mission_map)
            assert scene.targetCharacter.getManaBoardAwakeLevel(1) == new
            assert scene.boardAwakeLevel == new
            assert scene.currentTabKind == current
            assert scene.missionMap is mission_map and scene.hasRequestMissionList
            assert scene.reloads == repeat + 1
            assert (2 in scene.tabGroup.disabledTabButtons) == (new == 0)
            assert scene.tabGroup.states[2] == (4 if new == 0 else (2 if current == 2 else 1))
        cases.append({"old": old, "new": new, "current_tab": current, "replays": 3})
    print(json.dumps({"original_bug_reproduced": True, "patched_callback_cases": cases,
                      "device_tested": False, "validation": "actual AVM2 callback instruction replay"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    main(args.source, args.candidate)
