"""Sparse old-server compatibility guards for the final O2/O3 methods.

Requires the caller's existing common/perf2_core imports. Only these two method
bodies change: no methods, traits, pool entries, assets, endpoints or admission.
"""
from __future__ import annotations

import copy
import hashlib

from common import asm, bodies
from perf2_core import MAIN, Refused, check_body, splice_with_exits


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _require(condition, message):
    if not condition:
        raise Refused(message)


def _local(ins, index):
    return ((ins.name == "getlocal" and ins.args == [index]) or
            ins.name == "getlocal_" + str(index))


def _splice(body, at, source, exits, history):
    old = body[5]
    code, exceptions, _, count = splice_with_exits(body, at, source, exits)
    _require(asm.unsplice(code, at, count) == old, "Inverse splice differs")
    body[5], body[6] = code, exceptions
    history.append((at, count))


def _mode_anchor(abc, body):
    code = asm.decode(body[5])
    hits = []
    for i in range(len(code) - 5):
        window = code[i:i + 6]
        if ([x.name for x in window] == ["findproperty", "getproperty", "getproperty", "convert_i", "pushbyte", "iflt"]
                and abc.mn_name(window[0].args[0]) == "character"
                and abc.mn_name(window[1].args[0]) == "character"
                and abc.mn_name(window[2].args[0]) == "overLimitStep"
                and window[4].args == [4]):
            hits.append(i)
    _require(len(hits) == 1, "Missing or ambiguous overlimit-mode anchor")
    return code, hits[0]


def _add_cap_gate(abc, body, pool, history):
    code, at = _mode_anchor(abc, body)
    character = code[at].args[0]
    block = [("findproperty", character), ("getproperty", character),
             ("callproperty", pool.find("get_maxOverLimitStep", 7), 0),
             ("convert_i",), ("pushbyte", 4), ("ifle", "RETAIL")]
    _splice(body, at + 6, block, {"RETAIL": code[at + 5].target}, history)


def _finish_inverse(body, original, history):
    raw = body[5]
    for at, count in reversed(history):
        raw = asm.unsplice(raw, at, count)
    _require(raw == original, "Combined inverse differs from exact input")


def _o2(abc, index, pool):
    body = abc.bodies[index]
    _require(body[1:5] == [3, 12, 1, 2] and not body[6] and not body[7], "O2 header changed")
    original, history = body[5], []
    _add_cap_gate(abc, body, pool, history)
    _finish_inverse(body, original, history)
    return {"splices": history, "combined_inverse_exact": True,
            "inventory_fallback": False, "header": body[1:5]}


def _o3(abc, index, pool):
    body = abc.bodies[index]
    _require(body[1:5] == [3, 13, 1, 2] and not body[6] and not body[7], "O3 header changed")
    original, history = body[5], []
    _add_cap_gate(abc, body, pool, history)
    # Save precisely the candidates admitted by the original retail condition,
    # before the new mode/crystal filter can discard them. This is definition
    # based; an owned count of zero never activates this display fallback.
    code, at = _mode_anchor(abc, body)
    capture_at = at - 3
    _require(_local(code[capture_at], 1) and code[capture_at + 1].name == "pushbyte"
             and code[capture_at + 1].args == [5] and code[capture_at + 2].name == "ifne",
             "O3 original-candidate capture anchor changed")
    push = pool.find("http://adobe.com/AS3/2006/builtin::push", 7)
    fallback_local = 13
    _splice(body, capture_at, [("getlocal", fallback_local), ("getlocal", 5),
                              ("callpropvoid", push, 1)], {}, history)
    _splice(body, 2, [("newarray", 0), ("setlocal", fallback_local)], {}, history)
    code = asm.decode(body[5])
    sorts = [i for i, ins in enumerate(code) if ins.name == "callpropvoid"
             and abc.mn_name(ins.args[0]) == "http://adobe.com/AS3/2006/builtin::sort"]
    _require(len(sorts) == 1 and _local(code[sorts[0] - 4], 2), "O3 final sort anchor changed")
    character = pool.find("character", 7)
    block = [("getlocal_1",), ("pushbyte", 5), ("ifne", "KEEP"),
             ("findproperty", character), ("getproperty", character),
             ("getproperty", pool.find("overLimitStep", 7)), ("convert_i",),
             ("pushbyte", 4), ("iflt", "KEEP"),
             ("findproperty", character), ("getproperty", character),
             ("callproperty", pool.find("get_maxOverLimitStep", 7), 0), ("convert_i",),
             ("pushbyte", 4), ("ifle", "KEEP"),
             ("getlocal_2",), ("getproperty", pool.find("length", 7)), ("convert_i",),
             ("pushbyte", 0), ("ifne", "KEEP"),
             ("getlocal", fallback_local), ("setlocal_2",), ("label", "KEEP")]
    _splice(body, sorts[0] - 4, block, {}, history)
    body[2] = 14
    _finish_inverse(body, original, history)
    return {"splices": history, "combined_inverse_exact": True,
            "display_fallback_only": True, "new_body_local": fallback_local,
            "header": body[1:5]}


PATCHES = [
    {"id": "OC2", "tag": MAIN,
     "label": "OwnedOverLimitLogic/getOwnAwakingCrystalToOverLimit", "apply": _o2,
     "before": "2be9af1fa92ed8bb56a5ee90b9eb511f7f94c6941f38a223e406207e17be61b2",
     "after": "5683f86962cb16e6e44eb5c6586f9bd4ba4331ef4bb86a1d2b82028c5d81f7ab"},
    {"id": "OC3", "tag": MAIN,
     "label": "OwnedOverLimitLogic/getAwakingCrystalToOverLimit", "apply": _o3,
     "before": "2e584914a2f67e60a268e62502f8e7af84a6a6e1e38af444b8de79c446470b34",
     "after": "dbcce3ec29e494186f7930c538383a60e22359f9485db790d8f496b0d1444365"},
]


def apply(patch, abc, pool, support=None):
    """Apply one guarded body update; PATCHES also fits perf2_core.apply_patches."""
    patch_id = patch if isinstance(patch, str) else patch["id"]
    matches = [row for row in PATCHES if row["id"] == patch_id]
    _require(len(matches) == 1, "Unknown old-server compatibility patch")
    row = matches[0]
    _require(not getattr(pool, "allow_append", True), "Main pool must forbid appends")
    index = bodies.resolve(abc, row["label"])
    body = abc.bodies[index]
    current = _sha(body[5])
    if row["after"] is not None and current == row["after"]:
        return {"id": patch_id, "body": index, "status": "already_present", "sha256": current}
    _require(current == row["before"], "Unknown compatibility preimage: " + current)
    saved = copy.deepcopy(body)
    try:
        details = row["apply"](abc, index, pool)
        result = _sha(body[5])
        _require(row["after"] is None or result == row["after"], "Unexpected compatibility output")
        validation = check_body(abc, body)
    except Exception:
        abc.bodies[index] = saved
        raise
    return {"id": patch_id, "body": index, "status": "applied", "before": current,
            "after": result, "details": details, "validation": validation}
