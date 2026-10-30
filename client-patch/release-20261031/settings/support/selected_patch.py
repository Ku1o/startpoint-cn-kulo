"""Selected PR195 P1-P5 only. Fixed upstream reference preserved separately."""
from __future__ import annotations
import hashlib,json
import asm,bodies
from avm_interp import slice_method
P1_LABEL="BattleViewInputSettings/isOtherBattleActionVisible"
P2_LABEL="Battle/preparation"
P3_LABEL="BattleView/show"
P4_LABEL="EffectManagerImpl/canPlayEffect"
P5_LABEL="EffectManagerImpl/show"
TARGETS=(P1_LABEL,P2_LABEL,P3_LABEL,P4_LABEL,P5_LABEL)
EXACT_METHOD_LOCKS={
 P1_LABEL:{"sha":"d46ba2ae3f96d22aa71dfc7e38981756d9b300c18feaea381355b95b23095bff","header":[2,1,1,2]},
 P2_LABEL:{"sha":"4a8a50eb363cf8cb301f26b96073f65c2feb148f4a3ef05891e0f35077635f5b","header":[13,10,1,2]},
 P4_LABEL:{"sha":"a7e15c6d738a4435d599fad14075e1e40db060cd14f49bd2e73dcc6fd8fcfdf9","header":[2,3,1,2]}}
P3_HEADER_LOCK=[10,15,1,2]
P2B_CASE43_NORMALIZED_SHA256="446afca99926d1fdf2a8ffd94274b3664e126467b4539d236b4b0965ddb9ac76"
P3_CASE55_NORMALIZED_SHA256="da508a81f3fd933eefa05733df72609c33ea5b426472e72a493873f40d4200bc"
P3_CASE55_TAIL_RAW_SHA256="537f4a1e199881bc215621ae46a3d44067d1da354443cfbc994aa6ab3b942766"
P5_HEADER_LOCK=[11,9,1,2]
P5_CASE63_NATIVE_NORMALIZED_SHA256="59b13adc06f857d443c6911eb6f0242b5facebbdf87c7d4b75bde8f318dea4e2"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _short(abc, mn_index: int) -> str:
    return abc.mn_name(mn_index).split("::")[-1]

def _check_op_names(ins, expected: dict[int, str], context: str) -> None:
    for idx, op_name in expected.items():
        if idx >= len(ins) or ins[idx].name != op_name:
            actual = ins[idx].name if idx < len(ins) else "<out-of-range>"
            raise asm.AsmError(f"{context} anchor shape mismatch at #{idx}: {actual} != {op_name}")

def _normalize_slice_ins(abc, ins_item, base: int, epilogue: int) -> list:
    args = []
    for pos, val in enumerate(ins_item.args):
        kind = asm.opwalk.KIND.get((ins_item.op, pos))
        if kind == "multiname":
            mn = abc.multinames[val]
            args.append(f"rt:{mn[0]:02x}" if mn[0] in (0x1B, 0x1C) else abc.mn_name(val))
        elif kind == "string":
            args.append(abc.s(val))
        elif kind in ("int", "uint", "double"):
            args.append(getattr(abc, kind + "s")[val])
        else:
            args.append(val)
    tgt = None if ins_item.target is None else ("EPILOGUE" if ins_item.target == epilogue else ins_item.target - base)
    return [ins_item.name, args, tgt]

def _verify_single_switch_entry(ins, switch_idx: int, case_no: int, target_pc: int, label: str) -> None:
    incoming_branches = []
    for idx, item in enumerate(ins):
        if item.target == target_pc:
            incoming_branches.append(("branch", idx))
        if item.cases is not None:
            if item.default == target_pc:
                incoming_branches.append(("switch_default", idx))
            for c_no, target in enumerate(item.cases):
                if target == target_pc:
                    incoming_branches.append(("switch_case", idx, c_no))
    if incoming_branches != [("switch_case", switch_idx, case_no)]:
        raise asm.AsmError(
            f"{label} unexpected incoming branches to case {case_no} (#{target_pc}): {incoming_branches}"
        )

def _verify_p1(abc) -> dict:
    body = abc.bodies[bodies.resolve(abc, P1_LABEL)]
    lock = EXACT_METHOD_LOCKS[P1_LABEL]
    if _sha(body[5]) != lock["sha"] or body[1:5] != lock["header"]:
        raise asm.AsmError(f"{P1_LABEL} method lock mismatch: sha={_sha(body[5])} header={body[1:5]}")
    ins = asm.decode(body[5])
    if len(ins) != 9:
        raise asm.AsmError(f"{P1_LABEL} expected 9 instructions, got {len(ins)}")
    _check_op_names(
        ins,
        {
            0: "getlocal_0",
            1: "pushscope",
            2: "findproperty",
            3: "getproperty",
            4: "getlex",
            5: "getproperty",
            6: "callproperty",
            7: "convert_b",
            8: "returnvalue",
        },
        P1_LABEL,
    )
    if _short(abc, ins[2].args[0]) != "battle" or _short(abc, ins[3].args[0]) != "battle":
        raise asm.AsmError(f"{P1_LABEL} expected battle property at #2/#3")
    if abc.mn_name(ins[4].args[0]) != "pinball.scene.battle.battle::SkippableLogicKind":
        raise asm.AsmError(f"{P1_LABEL} expected SkippableLogicKind at #4")
    if _short(abc, ins[5].args[0]) != "Action" or _short(abc, ins[6].args[0]) != "isRichMode":
        raise asm.AsmError(f"{P1_LABEL} expected isRichMode(SkippableLogicKind.Action) at #5/#6")
    return {"insert_at": 2, "incoming": asm.FORBID, "before_sha256": _sha(body[5])}

def _verify_p2(abc) -> dict:
    """Unique original flag window, independent of inserted capability code elsewhere."""
    body=abc.bodies[bodies.resolve(abc,P2_LABEL)]
    info=abc.methods[body[0]]
    if [abc.mn_name(t) for t in info[1]]!=['jp.sipo.gipo.core::GearPreparationTool'] or abc.mn_name(info[0])!='void' or info[3]!=0 or body[3:5]!=[1,2]:
        raise asm.AsmError('Battle/preparation signature/flags/scope contract mismatch')
    ins=asm.decode(body[5])
    writes=[i for i,x in enumerate(ins) if x.name in ('initproperty','setproperty') and _short(abc,x.args[0])=='showOthersMultiball']
    if len(writes)!=1:raise asm.AsmError('showOthersMultiball write must be unique; refuses duplicate/repeated patch')
    at=writes[0]+1;start=at-54
    if start<0 or ins[at].name!='findproperty' or _short(abc,ins[at].args[0])!='xdebugSettings':raise asm.AsmError('native flag tail anchor missing')
    normalized=[_normalize_slice_ins(abc,ins[i],start,at) for i in range(start,at)]
    digest=_sha(json.dumps(normalized,separators=(',',':'),ensure_ascii=False).encode('utf-8'))
    expected='e8a93f403119d4dc7ec997f609563a4c11f4df2dea77a48f0aa0397db4a918a2'
    if digest!=expected:raise asm.AsmError('native flags window mismatch: '+digest)
    return {'insert_at':at,'incoming':asm.FORBID,'show_others_multiball_mn':ins[at-1].args[0],'before_sha256':_sha(body[5]),'native_window_start':start,'native_window_end':at,'native_window_sha256':digest,'whole_body_exact_r11':_sha(body[5])==EXACT_METHOD_LOCKS[P2_LABEL]['sha']}


def _normalize_p3_ins(abc, ins_item, base: int, epilogue: int) -> list:
    args = []
    for pos, val in enumerate(ins_item.args):
        kind = asm.opwalk.KIND.get((ins_item.op, pos))
        if kind == "multiname":
            mn = abc.multinames[val]
            args.append(f"rt:{mn[0]:02x}" if mn[0] in (0x1B, 0x1C) else abc.mn_name(val))
        else:
            args.append(val)
    tgt = None if ins_item.target is None else ("EPILOGUE" if ins_item.target == epilogue else ins_item.target - base)
    return [ins_item.name, args, tgt]

def _verify_p3(abc) -> dict:
    body = abc.bodies[bodies.resolve(abc, P3_LABEL)]
    if body[1:5] != P3_HEADER_LOCK:
        raise asm.AsmError(f"{P3_LABEL} header lock mismatch: {body[1:5]} != {P3_HEADER_LOCK}")
    ins = asm.decode(body[5])
    _check_op_names(
        ins,
        {
            41: "setlocal",
            42: "getlocal_1",
            43: "pushbyte",
            44: "ifne",
            45: "getlocal_2",
            46: "getproperty",
            47: "lookupswitch",
        },
        f"{P3_LABEL} prologue",
    )
    if ins[41].args != [5] or ins[43].args != [255]:
        raise asm.AsmError(f"{P3_LABEL} prologue removeKey/owner check mismatch")
    mine_sw = ins[47]
    if len(mine_sw.cases) != 106:
        raise asm.AsmError(f"{P3_LABEL} primary switch case count mismatch: {len(mine_sw.cases)}")
    mine_c43 = mine_sw.cases[43]
    if "BallView" not in abc.mn_name(ins[mine_c43 + 2].args[0]):
        raise asm.AsmError(f"{P3_LABEL} primary case 43 is not BallView")
    mine_c55 = mine_sw.cases[55]
    if "CutinActionSkillView1" not in abc.mn_name(ins[mine_c55 + 2].args[0]):
        raise asm.AsmError(f"{P3_LABEL} primary case 55 is not CutinActionSkillView1")

    else_entry = ins[44].target
    _check_op_names(
        ins,
        {
            else_entry: "getlocal_2",
            else_entry + 1: "getproperty",
            else_entry + 2: "lookupswitch",
        },
        f"{P3_LABEL} other-branch dispatch",
    )
    other_sw = ins[else_entry + 2]
    if len(other_sw.cases) != 106:
        raise asm.AsmError(f"{P3_LABEL} other-branch switch case count mismatch: {len(other_sw.cases)}")
    epilogue = len(ins) - 2

    # --- P2b: other-branch case 43 (BallView) ---
    c43 = other_sw.cases[43]
    if c43 == mine_c43:
        raise asm.AsmError(f"{P3_LABEL} other-branch case 43 collides with primary case 43")
    if ins[c43 - 1].name != "jump" or ins[c43 - 1].target != epilogue:
        raise asm.AsmError(f"{P3_LABEL} instruction before case 43 is not break jump to epilogue")
    _verify_single_switch_entry(ins, else_entry + 2, 43, c43, P3_LABEL)

    c43_norm_repr = [_normalize_slice_ins(abc, ins[i], c43, epilogue) for i in range(c43, c43 + 22)]
    c43_norm_sha = _sha(json.dumps(c43_norm_repr, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    if c43_norm_sha != P2B_CASE43_NORMALIZED_SHA256:
        raise asm.AsmError(f"{P3_LABEL} case 43 normalized anchor sha mismatch: {c43_norm_sha}")

    m_params = ins[c43 + 9].args[0]
    rt = ins[c43 + 11].args[0]
    m_ball_peek = ins[c43 + 12].args[0]
    if _short(abc, m_params) != "params" or abc.multinames[rt][0] != 0x1B:
        raise asm.AsmError(f"{P3_LABEL} case 43 params/rt operand mismatch")
    if abc.mn_name(m_ball_peek) != "pinball.scene.battle.battle.squad.ball::BallPeek":
        raise asm.AsmError(f"{P3_LABEL} case 43 coerce is not BallPeek: {abc.mn_name(m_ball_peek)}")

    bv_is_primary_ins = asm.decode(abc.bodies[bodies.resolve(abc, "BallView/isPrimary")][5])
    _check_op_names(bv_is_primary_ins, {4: "callproperty", 5: "convert_b", 6: "returnvalue"}, "BallView/isPrimary")
    m_ball_is_primary = bv_is_primary_ins[4].args[0]
    if abc.mn_name(m_ball_is_primary) != "pinball.scene.battle.battle.squad.ball:BallPeek::isPrimary":
        raise asm.AsmError(f"BallView/isPrimary unexpected multiname: {abc.mn_name(m_ball_is_primary)}")

    # --- P3: other-branch case 55 (CutinActionSkill) ---
    c55 = other_sw.cases[55]
    if c55 == mine_c55:
        raise asm.AsmError(f"{P3_LABEL} other-branch case 55 collides with primary case 55")
    if ins[c55 - 1].name != "jump" or ins[c55 - 1].target != epilogue:
        raise asm.AsmError(f"{P3_LABEL} instruction before case 55 is not break jump to epilogue")
    _verify_single_switch_entry(ins, else_entry + 2, 55, c55, P3_LABEL)

    slice_repr = {
        "case55": [_normalize_p3_ins(abc, ins[i], c55, epilogue) for i in range(c55, c55 + 17)],
        "epilogue": [_normalize_p3_ins(abc, ins[i], epilogue, epilogue) for i in range(epilogue, epilogue + 2)],
    }
    norm_raw = json.dumps(slice_repr, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    norm_sha = _sha(norm_raw)
    if norm_sha != P3_CASE55_NORMALIZED_SHA256:
        raise asm.AsmError(f"{P3_LABEL} case 55 normalized anchor sha mismatch: {norm_sha}")

    tail_raw = asm.encode(slice_method(ins, c55, len(ins), ()))[0]
    tail_sha = _sha(tail_raw)
    if tail_sha != P3_CASE55_TAIL_RAW_SHA256:
        raise asm.AsmError(f"{P3_LABEL} case 55 tail bytecode sha mismatch: {tail_sha}")

    return {
        "case43_insert_at": c43,
        "case43_incoming": asm.ENTER,
        "case43_normalized_sha256": c43_norm_sha,
        "params_mn": m_params,
        "rt_mn": rt,
        "ball_peek_mn": m_ball_peek,
        "ball_is_primary_mn": m_ball_is_primary,
        "insert_at": c55,
        "incoming": asm.ENTER,
        "return_local": ins[epilogue].args[0],
        "else_switch_at": else_entry + 2,
        "epilogue_at": epilogue,
        "case55_normalized_sha256": norm_sha,
        "case55_tail_raw_sha256": tail_sha,
        "before_sha256": _sha(body[5]),
    }

def _verify_p4(abc) -> dict:
    body = abc.bodies[bodies.resolve(abc, P4_LABEL)]
    lock = EXACT_METHOD_LOCKS[P4_LABEL]
    if _sha(body[5]) != lock["sha"] or body[1:5] != lock["header"]:
        raise asm.AsmError(f"{P4_LABEL} method lock mismatch: sha={_sha(body[5])} header={body[1:5]}")
    ins = asm.decode(body[5])
    if len(ins) != 33:
        raise asm.AsmError(f"{P4_LABEL} expected 33 instructions, got {len(ins)}")
    _check_op_names(
        ins,
        {
            0: "getlocal_0",
            1: "pushscope",
            2: "getlocal_1",
            3: "iffalse",
            4: "pushtrue",
            5: "returnvalue",
            6: "getlocal_2",
            7: "getproperty",
            8: "pushbyte",
            9: "ifne",
            16: "lookupswitch",
            18: "findproperty",
            25: "findproperty",
            31: "pushfalse",
            32: "returnvalue",
        },
        P4_LABEL,
    )
    if ins[3].target != 6 or ins[9].target != 31:
        raise asm.AsmError(f"{P4_LABEL} branch target mismatch: #3->{ins[3].target}, #9->{ins[9].target}")
    if ins[16].cases[33] != 18 or ins[16].cases[34] != 25:
        raise asm.AsmError(f"{P4_LABEL} SimpleEffectKind 33/34 switch targets mismatch")
    if _short(abc, ins[19].args[0]) != "battle" or _short(abc, ins[20].args[0]) != "lightweightModeLevel":
        raise asm.AsmError(f"{P4_LABEL} expected battle.lightweightModeLevel at #19/#20")
    return {
        "insert_at": 6,
        "incoming": asm.ENTER,
        "battle_mn": ins[19].args[0],
        "lightweight_mode_level_mn": ins[20].args[0],
        "before_sha256": _sha(body[5]),
    }

def _verify_p5(abc) -> dict:
    body = abc.bodies[bodies.resolve(abc, P5_LABEL)]
    if body[1:5] != P5_HEADER_LOCK:
        raise asm.AsmError(f"{P5_LABEL} header lock mismatch: {body[1:5]} != {P5_HEADER_LOCK}")
    ins = asm.decode(body[5])
    _check_op_names(
        ins,
        {
            20: "findproperty",
            24: "callproperty",
            27: "iffalse",
            28: "returnvoid",
            29: "getlocal_1",
            30: "getproperty",
            31: "lookupswitch",
            33: "getlocal_1",
            39: "setlocal_2",
            40: "getlocal_2",
            41: "getproperty",
            42: "lookupswitch",
        },
        f"{P5_LABEL} prologue",
    )
    if _short(abc, ins[24].args[0]) != "canPlayEffect":
        raise asm.AsmError(f"{P5_LABEL} expected canPlayEffect at #24")
    outer_sw = ins[31]
    inner_sw = ins[42]
    if len(outer_sw.cases) != 9 or outer_sw.cases[0] != 33:
        raise asm.AsmError(f"{P5_LABEL} outer switch mismatch")
    if len(inner_sw.cases) != 96:
        raise asm.AsmError(f"{P5_LABEL} inner SimpleEffectKind switch case count mismatch: {len(inner_sw.cases)}")

    c63 = inner_sw.cases[63]
    _verify_single_switch_entry(ins, 42, 63, c63, P5_LABEL)

    has_hitbudget = (
        ins[c63].name == "getlocal_0"
        and ins[c63 + 1].name == "callproperty"
        and _short(abc, ins[c63 + 1].args[0]) == "wfxHitAllow"
    )
    if has_hitbudget:
        _check_op_names(
            ins,
            {
                c63: "getlocal_0",
                c63 + 1: "callproperty",
                c63 + 2: "iftrue",
                c63 + 3: "getlocal_2",
                c63 + 4: "getproperty",
                c63 + 5: "pushbyte",
                c63 + 6: "getproperty",
                c63 + 7: "convert_b",
                c63 + 8: "iffalse",
                c63 + 9: "getlocal_0",
                c63 + 10: "callproperty",
                c63 + 11: "pop",
                c63 + 12: "returnvoid",
            },
            f"{P5_LABEL} hitbudget prefix",
        )
        if ins[c63 + 2].target != c63 + 13 or ins[c63 + 8].target != c63 + 12:
            raise asm.AsmError(f"{P5_LABEL} hitbudget internal branch targets mismatch")
        native_c63 = c63 + 13
    else:
        native_c63 = c63

    break_jump = ins[native_c63 + 76]
    if break_jump.name != "jump" or ins[c63 - 1].name != "jump" or ins[c63 - 1].target != break_jump.target:
        raise asm.AsmError(f"{P5_LABEL} case 63 break jump mismatch")
    exit_pc = break_jump.target
    while ins[exit_pc].name == "jump":
        exit_pc = ins[exit_pc].target
    if ins[exit_pc].name != "returnvoid":
        raise asm.AsmError(f"{P5_LABEL} case 63 break exit does not resolve to returnvoid")

    c63_norm_repr = [
        _normalize_slice_ins(abc, ins[i], native_c63, break_jump.target)
        for i in range(native_c63, native_c63 + 77)
    ]
    c63_norm_sha = _sha(json.dumps(c63_norm_repr, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    if c63_norm_sha != P5_CASE63_NATIVE_NORMALIZED_SHA256:
        raise asm.AsmError(f"{P5_LABEL} case 63 native slice sha mismatch: {c63_norm_sha}")

    m_params = ins[native_c63 + 1].args[0]
    rt = ins[native_c63 + 3].args[0]
    m_rot = ins[native_c63 + 33].args[0]
    if _short(abc, m_params) != "params" or abc.multinames[rt][0] != 0x1B or _short(abc, m_rot) != "getRandomRotation":
        raise asm.AsmError(f"{P5_LABEL} case 63 operand mismatch")

    p4_info = _verify_p4(abc)
    return {
        "insert_at": c63,
        "incoming": asm.ENTER,
        "has_v35n_hitbudget": has_hitbudget,
        "native_case63_at": native_c63,
        "case63_native_normalized_sha256": c63_norm_sha,
        "battle_mn": p4_info["battle_mn"],
        "lightweight_mode_level_mn": p4_info["lightweight_mode_level_mn"],
        "params_mn": m_params,
        "rt_mn": rt,
        "get_random_rotation_mn": m_rot,
        "before_sha256": _sha(body[5]),
    }

def verify_anchors(abc):
 return {label: fn(abc) for label,fn in zip(TARGETS,(_verify_p1,_verify_p2,_verify_p3,_verify_p4,_verify_p5))}
