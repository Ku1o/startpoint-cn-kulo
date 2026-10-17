"""Run real-ABC overlimit port checks with explicit, private package inputs.

Usage: python -B test_overlimit_port.py --apk INPUT.apk --support-dir TOOLS
       [--report REPORT.json]
The small instruction harness executes the actual inserted blocks. It covers
the capability gates and item-list/text mutations, not the AVM2 verifier or UI.
"""
from __future__ import annotations

import argparse
import copy
import importlib
import json
from pathlib import Path
import sys
import zipfile

import overlimit_port as port


def execute_block(code, start, count, abc, locals_, stack=None):
    """Execute the actual O8-O12 insertions with controlled game objects."""
    stack = [] if stack is None else list(stack)
    pc, end, calls = start, start + count, []

    def prop(obj, index):
        return obj[abc.mn_name(index)]

    while pc < end:
        ins = code[pc]
        name, args = ins.name, ins.args
        pc += 1
        if name in ("label", "coerce"):
            pass
        elif name.startswith("getlocal"):
            i = int(name[-1]) if name[-2:-1] == "_" else args[0]
            stack.append(locals_.get(i))
        elif name.startswith("setlocal"):
            i = int(name[-1]) if name[-2:-1] == "_" else args[0]
            locals_[i] = stack.pop()
        elif name == "getproperty":
            stack.append(prop(stack.pop(), args[0]))
        elif name in ("pushbyte", "pushshort"):
            stack.append(args[0])
        elif name == "pushstring":
            stack.append(abc.strings[args[0]].decode("utf-8"))
        elif name == "convert_i":
            stack.append(int(stack.pop()))
        elif name == "newarray":
            assert args == [0]
            stack.append([])
        elif name in ("add", "multiply"):
            right, left = stack.pop(), stack.pop()
            stack.append(left + right if name == "add" else left * right)
        elif name in ("callproperty", "callpropvoid"):
            argc = args[1]
            values = [stack.pop() for _ in range(argc)][::-1]
            obj = stack.pop()
            method = abc.mn_name(args[0])
            calls.append(method)
            if method.endswith("::push"):
                obj.append(*values)
                value = len(obj)
            else:
                value = prop(obj, args[0])(*values)
            if name == "callproperty":
                stack.append(value)
        elif name == "findproperty":
            stack.append(locals_["scope"])
        elif name in ("iffalse", "iftrue"):
            value = bool(stack.pop())
            if value == (name == "iftrue"):
                pc = ins.target
        elif name in ("ifne", "iflt", "ifle", "ifgt", "ifnlt"):
            right, left = stack.pop(), stack.pop()
            take = {"ifne": left != right, "iflt": left < right,
                    "ifle": left <= right, "ifgt": left > right,
                    "ifnlt": not left < right}[name]
            if take:
                pc = ins.target
        else:
            raise AssertionError(f"Unsupported test instruction: {name}")
        assert start <= pc <= end, (name, pc, start, end)
    return locals_, stack, calls


def run_checks(apk, support_dir):
    sys.path.insert(0, str(support_dir.resolve()))
    common = importlib.import_module("common")
    support = importlib.import_module("perf2_core")
    with zipfile.ZipFile(apk) as archive:
        swf = archive.read(common.SWF_MEMBER)
    abc, _ = common.main_abc(swf)
    original = copy.deepcopy(abc)
    pool = support.Pool(abc, allow_append=False)
    receipts = [port.apply(d, abc, pool, support) for d in port.PATCHES]
    assert all(r["status"] == "applied" for r in receipts)
    touched = {r["body"] for r in receipts}
    assert touched == {i for i, (a, b) in enumerate(zip(original.bodies, abc.bodies))
                       if common.freeze(a) != common.freeze(b)}
    for field in vars(original):
        if field == "bodies":
            continue
        assert common.freeze(getattr(original, field)) == common.freeze(getattr(abc, field)), field
    assert not pool.added
    raw = abc.serialize()
    assert common.ABC(raw).serialize() == raw
    assert all(port.apply(d, abc, pool, support)["status"] == "already_present"
               for d in port.PATCHES)

    checks = 0
    by_id = {r["id"]: r for r in receipts}
    for rarity in (4, 5):
        for step in (3, 4, 8):
            for maximum in (4, 8):
                for core in (0, 1):
                    eligible = rarity == 5 and step >= 4 and maximum > 4
                    character = {"get_rarity": lambda: rarity, "overLimitStep": step,
                                 "get_maxOverLimitStep": lambda: maximum}
                    player = {"getItemNumber": lambda item: core if item == 10000302 else -999}
                    owner = {"targetCharacter": character, "character": character, "player": player}
                    for patch_id in ("O9", "O10", "O11", "O12"):
                        r = by_id[patch_id]
                        block = r["details"]
                        code = support.asm.decode(abc.bodies[r["body"]][5])
                        costs = [10001001]
                        locals_ = {0: owner, 2: costs, 4: costs,
                                   "scope": {"globalLogic": {"getItem": lambda item: {
                                       "get_name": lambda: "core" if item == 10000302 else "wrong"}}}}
                        locals_, stack, calls = execute_block(
                            code, block["inserted_at"], block["block_len"], abc, locals_,
                            ["crystal"] if patch_id == "O12" else None)
                        if patch_id == "O9":
                            assert locals_[2] == ([] if eligible and not core else [10001001])
                            assert ("getItemNumber" in calls) == eligible
                        elif patch_id in ("O10", "O11"):
                            assert costs == ([10001001, 10000302] if eligible else [10001001])
                        else:
                            assert stack == (["crystal＋core"] if eligible else ["crystal"])
                            assert ("getItem" in calls) == eligible
                        checks += 1

    # O5's actual inserted block clamps the existing crystal count by cores;
    # its unchanged following original instructions clamp that by remaining steps.
    r = by_id["O5"]
    block = r["details"]
    code = support.asm.decode(abc.bodies[r["body"]][5])
    for rarity in (4, 5):
        for step in (3, 4, 8):
            for crystals in (0, 2, 9):
                for cores in (0, 1, 10):
                    character = {"get_rarity": lambda: rarity, "overLimitStep": step}
                    player = {"getItemNumber": lambda item: cores if item == 10000302 else -999}
                    locals_, _, _ = execute_block(code, block["inserted_at"], block["block_len"], abc,
                                                  {0: character, 1: player, 3: crystals})
                    assert locals_[3] == (min(crystals, cores) if rarity == 5 and step >= 4 else crystals)
                    checks += 1

    r = by_id["O8"]
    block = r["details"]
    code = support.asm.decode(abc.bodies[r["body"]][5])
    general, owned = {"id": 42}, {"id": 42, "overLimitStep": 8}
    for player, expected in [(None, general),
                             ({"hasOwnedCharacter": lambda _: False}, general),
                             ({"hasOwnedCharacter": lambda _: True,
                               "getOwnedCharacter": lambda _: owned}, owned)]:
        locals_, _, _ = execute_block(code, block["inserted_at"], block["block_len"], abc,
                                      {0: {"player": player}, 3: general})
        assert locals_[3] is expected
        checks += 1

    # Fail closed: unknown preimage, append-enabled pool and post-check failure.
    definition = port.PATCHES[0]
    index = support.bodies.resolve(original, definition["label"])
    saved = original.bodies[index][5]
    original.bodies[index][5] += b"\x09"
    try:
        port.apply("O1", original, support.Pool(original, False), support)
        raise AssertionError("Unknown preimage accepted")
    except support.Refused:
        assert original.bodies[index][5] == saved + b"\x09"
    original.bodies[index][5] = saved
    try:
        port.apply("O1", original, support.Pool(original, True), support)
        raise AssertionError("Append-enabled pool accepted")
    except support.Refused:
        pass
    from types import SimpleNamespace
    def reject(*_):
        raise support.Refused("injected post-check failure")
    rejecting = SimpleNamespace(**{name: getattr(support, name) for name in
                                  ("asm", "bodies", "mn_at", "splice_with_exits", "Refused")},
                                check_body=reject)
    before = copy.deepcopy(original.bodies[index])
    try:
        port.apply("O1", original, support.Pool(original, False), rejecting)
        raise AssertionError("Post-check failure ignored")
    except support.Refused:
        assert original.bodies[index] == before
    return {"patches": receipts, "block_behavior_cases": checks,
            "exact_after_hashes": True, "unrelated_bodies_preserved": True,
            "nonbody_tables_preserved": True, "idempotent": True,
            "abc_roundtrip": True, "unknown_preimage_refused": True,
            "pool_append_refused": True, "failed_patch_body_restored": True,
            "avm2_verifier_run": False, "device_tested": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--support-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run_checks(args.apk, args.support_dir)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"12 exact method ports; {report['block_behavior_cases']} inserted-block cases passed")
