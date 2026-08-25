"""基诺维 PF 与队长追加技能伤害的源级倍率规则。

本模块只负责把调用方提供的六个 Action DSL payload 改成确认值，不负责
写入 CDN、生成版本边或打包 ZIP。后续整合发布器应显式调用
``patch_payload``，再把返回字节纳入同一版本。
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping
import zlib

import wf_dsl


@dataclass(frozen=True)
class GinoviDamageSpec:
    family: str
    level: int
    logical: str
    damage_type: str
    engine_base: float
    expected_attack_nodes: int
    expected_weighted_hits: int
    accepted_before_totals: tuple[float, ...]
    target_total: float


def _pf_logical(level: int) -> str:
    return (
        "battle/action/power_flip/action/override/"
        f"ginovi_pf$ginovi_pf_lv{level}.action.dsl.amf3.deflate"
    )


def _leader_skill_logical(level: int) -> str:
    return (
        "battle/action/skill/action/ability_skill/"
        f"ability_skill_ginovi_pf_lv{level}$"
        f"ability_skill_ginovi_pf_lv{level}.action.dsl.amf3.deflate"
    )


PF_SPECS: dict[int, GinoviDamageSpec] = {
    1: GinoviDamageSpec(
        family="power_flip",
        level=1,
        logical=_pf_logical(1),
        damage_type="power_flip",
        engine_base=5.0,
        expected_attack_nodes=4,
        expected_weighted_hits=4,
        accepted_before_totals=(25.0,),
        target_total=25.0,
    ),
    2: GinoviDamageSpec(
        family="power_flip",
        level=2,
        logical=_pf_logical(2),
        damage_type="power_flip",
        engine_base=10.0,
        expected_attack_nodes=6,
        expected_weighted_hits=6,
        accepted_before_totals=(35.0,),
        target_total=35.0,
    ),
    3: GinoviDamageSpec(
        family="power_flip",
        level=3,
        logical=_pf_logical(3),
        damage_type="power_flip",
        engine_base=15.0,
        expected_attack_nodes=10,
        expected_weighted_hits=10,
        accepted_before_totals=(60.0, 45.0),
        target_total=45.0,
    ),
}


LEADER_SKILL_SPECS: dict[int, GinoviDamageSpec] = {
    1: GinoviDamageSpec(
        family="leader_skill_followup",
        level=1,
        logical=_leader_skill_logical(1),
        damage_type="skill",
        engine_base=0.0,
        expected_attack_nodes=2,
        expected_weighted_hits=22,
        accepted_before_totals=(60.0, 25.0),
        target_total=25.0,
    ),
    2: GinoviDamageSpec(
        family="leader_skill_followup",
        level=2,
        logical=_leader_skill_logical(2),
        damage_type="skill",
        engine_base=0.0,
        expected_attack_nodes=1,
        expected_weighted_hits=1,
        accepted_before_totals=(120.0, 35.0),
        target_total=35.0,
    ),
    3: GinoviDamageSpec(
        family="leader_skill_followup",
        level=3,
        logical=_leader_skill_logical(3),
        damage_type="skill",
        engine_base=0.0,
        expected_attack_nodes=1,
        expected_weighted_hits=7,
        accepted_before_totals=(240.0, 50.0),
        target_total=50.0,
    ),
}


ALL_SPECS: tuple[GinoviDamageSpec, ...] = tuple(PF_SPECS.values()) + tuple(
    LEADER_SKILL_SPECS.values()
)
SPECS_BY_LOGICAL: dict[str, GinoviDamageSpec] = {
    spec.logical: spec for spec in ALL_SPECS
}


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _decode_payload(raw: bytes, logical: str) -> Any:
    try:
        data = zlib.decompress(raw, -15)
        return wf_dsl.parse_dsl(data)["tree"]
    except Exception as error:
        raise ValueError(f"无法解析基诺维 Action DSL: {logical}: {error}") from error


def _encode_payload(tree: Any) -> bytes:
    encoded = wf_dsl.encode_amf3(tree)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(encoded) + compressor.flush()


def _read_attack_multiplier(node: list[Any], logical: str) -> float:
    if len(node) <= 6 or node[0] != "CreateNormalAttack":
        raise ValueError(f"攻击节点形状异常: {logical}: {node!r}")
    ranges = node[6]
    if (
        not isinstance(ranges, list)
        or len(ranges) != 1
        or not isinstance(ranges[0], dict)
        or "min" not in ranges[0]
        or "max" not in ranges[0]
    ):
        raise ValueError(f"攻击倍率字段形状异常: {logical}: {ranges!r}")
    minimum = float(ranges[0]["min"])
    maximum = float(ranges[0]["max"])
    if not math.isclose(minimum, maximum, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"攻击倍率不是固定值: {logical}: {minimum}/{maximum}")
    return minimum


def _write_attack_multiplier(node: list[Any], value: float) -> None:
    node[6][0]["min"] = value
    node[6][0]["max"] = value


def _damage_segments(tree: Any, spec: GinoviDamageSpec) -> list[tuple[int, list[Any]]]:
    all_attacks = [
        node
        for node in _walk(tree)
        if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
    ]
    if len(all_attacks) != spec.expected_attack_nodes:
        raise ValueError(
            f"{spec.logical}: 攻击节点数漂移: "
            f"{len(all_attacks)} != {spec.expected_attack_nodes}"
        )

    segments: list[tuple[int, list[Any]]] = []
    for area in _walk(tree):
        if not isinstance(area, list) or not area or area[0] != "CreateHitArea":
            continue
        attacks = [
            node
            for node in _walk(area)
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
        ]
        if not attacks:
            continue
        if len(attacks) != 1:
            raise ValueError(f"{spec.logical}: 单个判定区包含多个攻击节点")
        if (
            len(area) <= 14
            or not isinstance(area[14], list)
            or len(area[14]) != 2
            or area[14][0] != "CalculatedUsingMaxNumOfHits"
        ):
            raise ValueError(f"{spec.logical}: 判定区命中上限形状异常")
        max_hits = int(area[14][1])
        if max_hits <= 0:
            raise ValueError(f"{spec.logical}: 非法命中上限 {max_hits}")
        segments.append((max_hits, attacks[0]))

    if {id(node) for _, node in segments} != {id(node) for node in all_attacks}:
        raise ValueError(f"{spec.logical}: 存在未归属判定区的攻击节点")
    weighted_hits = sum(max_hits for max_hits, _ in segments)
    if weighted_hits != spec.expected_weighted_hits:
        raise ValueError(
            f"{spec.logical}: 加权命中数漂移: "
            f"{weighted_hits} != {spec.expected_weighted_hits}"
        )
    return segments


def _matches_any(value: float, candidates: Iterable[float]) -> bool:
    return any(
        math.isclose(value, candidate, rel_tol=0.0, abs_tol=1e-9)
        for candidate in candidates
    )


def patch_payload(raw: bytes, logical: str) -> tuple[bytes, dict[str, Any]]:
    """把一个当前基诺维 DSL payload 改到确认倍率并返回审计报告。"""
    try:
        spec = SPECS_BY_LOGICAL[logical]
    except KeyError as error:
        raise ValueError(f"不是受支持的基诺维倍率路径: {logical}") from error

    tree = _decode_payload(raw, logical)
    if not isinstance(tree, list) or len(tree) < 12 or tree[0] != "ActionDsl":
        raise ValueError(f"{logical}: ActionDsl 根节点形状异常")
    if tree[10] != 0:
        raise ValueError(f"{logical}: buffTargetAs 已漂移，拒绝误改伤害类型")

    segments = _damage_segments(tree, spec)
    before_total = spec.engine_base + sum(
        max_hits * _read_attack_multiplier(node, logical)
        for max_hits, node in segments
    )
    accepted = spec.accepted_before_totals + (spec.target_total,)
    if not _matches_any(before_total, accepted):
        raise ValueError(
            f"{logical}: 当前总倍率 {before_total:g} 不在允许前值 "
            f"{sorted(set(accepted))} 中"
        )

    dsl_target = spec.target_total - spec.engine_base
    if dsl_target <= 0:
        raise ValueError(f"{logical}: 目标 DSL 倍率必须大于零")
    per_hit = dsl_target / spec.expected_weighted_hits
    changed = False
    for _, node in segments:
        current = _read_attack_multiplier(node, logical)
        if not math.isclose(current, per_hit, rel_tol=0.0, abs_tol=1e-12):
            _write_attack_multiplier(node, per_hit)
            changed = True

    after_total = spec.engine_base + sum(
        max_hits * _read_attack_multiplier(node, logical)
        for max_hits, node in segments
    )
    if not math.isclose(after_total, spec.target_total, rel_tol=0.0, abs_tol=1e-9):
        raise AssertionError(
            f"{logical}: 调整后总倍率 {after_total:g} != {spec.target_total:g}"
        )

    output = _encode_payload(tree) if changed else raw
    return output, {
        "family": spec.family,
        "level": spec.level,
        "logical": spec.logical,
        "damage_type": spec.damage_type,
        "engine_base": spec.engine_base,
        "attack_nodes": spec.expected_attack_nodes,
        "weighted_hits": spec.expected_weighted_hits,
        "before_total": before_total,
        "target_total": spec.target_total,
        "per_hit": per_hit,
        "changed": changed,
    }


def patch_payloads(payloads: Mapping[str, bytes]) -> tuple[dict[str, bytes], dict[str, Any]]:
    """一次处理六个 payload；缺少任一路径即拒绝，避免发布半套倍率。"""
    missing = sorted(set(SPECS_BY_LOGICAL) - set(payloads))
    if missing:
        raise ValueError(f"缺少基诺维倍率 payload: {missing}")
    output: dict[str, bytes] = {}
    report: dict[str, Any] = {}
    for spec in ALL_SPECS:
        patched, detail = patch_payload(payloads[spec.logical], spec.logical)
        output[spec.logical] = patched
        report[f"{spec.family}_lv{spec.level}"] = detail
    return output, report
