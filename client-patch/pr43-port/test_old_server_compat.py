"""Actual O2/O3 instruction tests plus ABC preservation and refusal checks.

The instruction runner is a controlled dependency harness, not an AVM2 runtime.
Run with --swf pointing at the exact final functional SWF and --support-dir at
its existing perf-tools directory. Real AIR/device verification is separate.
"""
from __future__ import annotations
import argparse
import copy
import functools
import hashlib
import json
from pathlib import Path
import sys


def execute(asm, abc, body, receiver, arguments):
    code = asm.decode(body[5])
    locals_ = {0: receiver, **{i + 1: x for i, x in enumerate(arguments)}}
    stack, pc, steps = [], 0, 0
    def get(obj, name):
        if name == "length" and isinstance(obj, list):
            return len(obj)
        return obj[name]
    while pc < len(code):
        ins = code[pc]
        op, args = ins.name, ins.args
        pc += 1
        steps += 1
        assert steps < 10000, "instruction loop did not terminate"
        if op == "getlocal" or op.startswith("getlocal_"):
            stack.append(locals_.get(args[0] if op == "getlocal" else int(op[-1])))
        elif op == "setlocal" or op.startswith("setlocal_"):
            locals_[args[0] if op == "setlocal" else int(op[-1])] = stack.pop()
        elif op in ("pushscope", "pop"):
            stack.pop()
        elif op in ("avm_label", "label", "coerce", "coerce_a", "astype"):
            pass
        elif op == "findproperty":
            stack.append(receiver)
        elif op == "getproperty":
            if abc.multinames[args[0]][0] == 0x1b:
                key = stack.pop()
                stack.append(stack.pop()[key])
            else:
                stack.append(get(stack.pop(), abc.mn_name(args[0])))
        elif op in ("pushbyte", "pushshort"):
            stack.append(args[0])
        elif op == "pushtrue":
            stack.append(True)
        elif op == "pushfalse":
            stack.append(False)
        elif op == "pushnull":
            stack.append(None)
        elif op == "newarray":
            assert args == [0]
            stack.append([])
        elif op == "dup":
            stack.append(stack[-1])
        elif op == "convert_i":
            stack.append(int(stack.pop()))
        elif op == "convert_b":
            stack.append(bool(stack.pop()))
        elif op == "inclocal_i":
            locals_[args[0]] += 1
        elif op in ("equals", "lessthan"):
            right, left = stack.pop(), stack.pop()
            stack.append(left == right if op == "equals" else left < right)
        elif op in ("callproperty", "callpropvoid"):
            argc = args[1]
            values = [stack.pop() for _ in range(argc)][::-1]
            obj = stack.pop()
            name = abc.mn_name(args[0])
            if name.endswith("::push"):
                obj.extend(values)
                value = len(obj)
            elif name.endswith("::sort"):
                obj.sort(key=functools.cmp_to_key(values[0]))
                value = obj
            else:
                value = obj[name](*values)
            if op == "callproperty":
                stack.append(value)
        elif op == "lookupswitch":
            key = int(stack.pop())
            pc = ins.cases[key] if 0 <= key < len(ins.cases) else ins.default
        elif op == "jump":
            pc = ins.target
        elif op in ("iffalse", "iftrue"):
            value = bool(stack.pop())
            if value == (op == "iftrue"):
                pc = ins.target
        elif op in ("ifne", "ifstrictne", "iflt", "ifle", "ifeq"):
            right, left = stack.pop(), stack.pop()
            condition = {"ifne": left != right, "ifstrictne": left != right,
                         "iflt": left < right, "ifle": left <= right,
                         "ifeq": left == right}[op]
            if condition:
                pc = ins.target
        elif op == "returnvalue":
            result = stack.pop()
            assert not stack
            return result
        else:
            raise AssertionError("Unhandled real method opcode: " + op)
    raise AssertionError("Real method failed to return")


def run(swf, support_dir):
    sys.path.insert(0, str(support_dir.resolve()))
    import common
    import perf2_core as core
    import old_server_compat as patch
    original_swf = swf.read_bytes()
    assert hashlib.sha256(original_swf).hexdigest() == "ee871b6bdaa339afe4e4bea755bded1d26d828f2884e0fe17c481c627898c6b6"
    abc, _ = common.main_abc(original_swf)
    original = copy.deepcopy(abc)
    pool = core.Pool(abc, False)
    receipts = [patch.apply(d, abc, pool, core) for d in patch.PATCHES]
    assert all(isinstance(d["after"], str) and len(d["after"]) == 64 for d in patch.PATCHES)
    changed = {r["body"] for r in receipts}
    assert changed == {i for i, (a, b) in enumerate(zip(original.bodies, abc.bodies))
                       if common.freeze(a) != common.freeze(b)}
    for name in vars(original):
        if name != "bodies":
            assert common.freeze(getattr(original, name)) == common.freeze(getattr(abc, name)), name
    assert not pool.added
    assert all(patch.apply(d, abc, pool, core)["status"] == "already_present" for d in patch.PATCHES)
    for r in receipts:
        raw = abc.bodies[r["body"]][5]
        for at, count in reversed(r["details"]["splices"]):
            raw = common.asm.unsplice(raw, at, count)
        assert raw == original.bodies[r["body"]][5]
    raw = abc.serialize()
    assert common.ABC(raw).serialize() == raw
    o2, o3 = [abc.bodies[r["body"]] for r in receipts]
    cases = []
    for rarity in (4, 5):
        for step in (0, 3, 4, 5, 8):
            for growth120 in (False, True):
                for definition in (False, True):
                    for old_count in (0, 2):
                        for new_count in (0, 1, 4):
                            maximum = 6 if rarity == 4 else (8 if growth120 and step >= 4 else 4)
                            extended = rarity == 5 and step >= 4 and maximum > 4
                            character = {"overLimitStep": step, "get_rarity": lambda: rarity,
                                         "get_maxOverLimitStep": lambda: maximum}
                            def effect(r, allow):
                                return {"index": 4, "params": [{"target_character_rarity": r,
                                                               "is_allow_below_rarity": allow}]}
                            table = {10002: {"effect_kind": effect(4, False)},
                                     10003: {"effect_kind": effect(5, False)}}
                            inventory = []
                            for item, r in ((10002, 4), (10003, 5)):
                                e = effect(r, False)
                                inventory.append({"id": item, "number": old_count,
                                                  "get_effect": lambda e=e: e})
                            if definition:
                                e = effect(5, True)
                                table[10000320] = {"effect_kind": e}
                                inventory.append({"id": 10000320, "number": new_count,
                                                  "get_effect": lambda e=e: e})
                            table_model = {"pinball.master.runtime:MasterMap::keys": lambda: list(table),
                                           "pinball.master.runtime:MasterMap::get": lambda key: table[key]}
                            receiver = {"character": character, "get_itemTable": lambda: table_model,
                                        "compareTargetRarityByOwnItemLogic": lambda a, b: 0,
                                        "compareTargetRarityByItemId": lambda a, b: 0}
                            owned = execute(common.asm, abc, o2, receiver, [inventory])
                            displayed = execute(common.asm, abc, o3, receiver, [])
                            retail_id = 10002 if rarity == 4 else 10003
                            expected_display = [10000320] if extended and definition else [retail_id]
                            assert displayed == expected_display
                            expected_owned = ([10000320] if definition and new_count else []) if extended else ([retail_id] if old_count else [])
                            assert [x["id"] for x in owned] == expected_owned
                            cases.append({"rarity": rarity, "step": step, "growth120": growth120,
                                          "definition": definition, "old_count": old_count,
                                          "new_count": new_count, "display": displayed,
                                          "owned": [x["id"] for x in owned]})
    first = patch.PATCHES[0]
    index = common.bodies.resolve(original, first["label"])
    original.bodies[index][5] += b"\x09"
    damaged = copy.deepcopy(original.bodies[index])
    try:
        patch.apply(first, original, core.Pool(original, False), core)
        raise AssertionError("Unknown body accepted")
    except core.Refused:
        assert original.bodies[index] == damaged
    try:
        patch.apply("unknown", abc, pool, core)
        raise AssertionError("Unknown selection accepted")
    except core.Refused:
        pass
    return {"passed": True, "source_swf_sha256": hashlib.sha256(original_swf).hexdigest(),
            "patches": receipts, "full_real_instruction_cases": len(cases), "cases": cases,
            "only_two_bodies_changed": True, "all_nonbody_tables_preserved": True,
            "combined_inverse_exact": True, "idempotent": True, "unknown_preimage_refused": True,
            "unknown_patch_refused": True, "abc_roundtrip": True,
            "runtime": "controlled actual-instruction runner; real AVM2 verification separate",
            "device_tested": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--swf", type=Path, required=True)
    parser.add_argument("--support-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run(args.swf, args.support_dir)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print("Two exact body patches and %d actual-instruction cases passed" % report["full_real_instruction_cases"])
