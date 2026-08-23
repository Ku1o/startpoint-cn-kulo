#!/usr/bin/env python3
"""Dedicated HP read/replace channel for ``orochi_ex`` family bosses.

Orochi EX is not a normal ``boss_level``-only boss.  Its first and third
phase HP live in columns 24/25 of ``orochi_ex.orderedmap`` while the middle
bar still uses ``boss_level``.  Keeping this adapter separate makes callers
handle all three bars deliberately instead of silently scaling only one.
"""
from __future__ import annotations

import copy
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


MOD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOD_DIR))
import wf_mod_tool as core  # noqa: E402


OROCHI_EX_LOGICAL = "master/battle/boss/orochi_ex.orderedmap"
BOSS_LEVEL_LOGICAL = "master/battle/boss/boss_level.orderedmap"
PHASE1_HP_COLUMN = 24
PHASE3_HP_COLUMN = 25
PARENT_COLUMNS = 128
BOSS_LEVEL_COLUMNS = 13


class OrochiExHpError(ValueError):
    """The dedicated Orochi EX HP channel cannot prove a safe operation."""


@dataclass(frozen=True, slots=True)
class FixedPhaseHp:
    code: str
    requested_level: int
    selected_level: int
    phase1_hp: float
    phase3_hp: float

    @property
    def total(self) -> float:
        return math.fsum((self.phase1_hp, self.phase3_hp))

    def evidence(self) -> dict[str, Any]:
        return dict(asdict(self), total_fixed_hp=self.total)


def _cells(leaf: str | bytes | bytearray, *, label: str, size: int) -> list[str]:
    if isinstance(leaf, (bytes, bytearray)):
        text = bytes(leaf).decode("utf-8")
    elif isinstance(leaf, str):
        text = leaf
    else:
        raise OrochiExHpError(f"{label} is not a CSV leaf")
    rows = core.read_csv_lines(text)
    if len(rows) != 1 or len(rows[0]) != size:
        raise OrochiExHpError(
            f"{label} has an invalid CSV shape: "
            f"rows={len(rows)} columns={len(rows[0]) if rows else 0}"
        )
    return rows[0]


def _leaf(row: list[str]) -> str:
    return core.write_csv_lines([row])


def _positive(value: str, *, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise OrochiExHpError(f"{label} is not numeric: {value!r}") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise OrochiExHpError(f"{label} must be finite and positive: {parsed!r}")
    return parsed


def _factor(value: float, *, label: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise OrochiExHpError(f"{label} must be finite and positive: {parsed!r}")
    return parsed


def select_parent_row(
    dedicated: dict[str, Any], code: str, level: int,
) -> tuple[int, list[str]]:
    """Select the first dedicated row whose numeric key is ``>= level``."""
    node = dedicated.get(str(code))
    if not isinstance(node, dict):
        raise OrochiExHpError(f"{code} is missing from the Orochi EX table")
    requested = int(level)
    eligible = sorted(
        int(key) for key in node
        if str(key).isdigit() and int(key) >= requested
    )
    if not eligible:
        raise OrochiExHpError(f"{code} has no dedicated row for level {requested}")
    selected = eligible[0]
    return selected, _cells(
        node[str(selected)], label=f"orochi_ex[{code}][{selected}]",
        size=PARENT_COLUMNS,
    )


def read_fixed_phase_hp(
    dedicated: dict[str, Any], code: str, level: int,
) -> FixedPhaseHp:
    """Read the two HP bars that bypass ordinary quest HP correction."""
    selected, row = select_parent_row(dedicated, code, level)
    return FixedPhaseHp(
        code=str(code),
        requested_level=int(level),
        selected_level=selected,
        phase1_hp=_positive(
            row[PHASE1_HP_COLUMN], label=f"{code}.phase1_health_point"
        ),
        phase3_hp=_positive(
            row[PHASE3_HP_COLUMN], label=f"{code}.phase3_health_point"
        ),
    )


def hp_components(profile: FixedPhaseHp, middle_hp: float, *,
                  middle_evidence_kind: str = "absolute") -> tuple[dict[str, Any], ...]:
    """Return three auditable components with their quest-correction policy."""
    middle = _positive(str(middle_hp), label=f"{profile.code}.middle_hp")
    return (
        {
            "code": profile.code,
            "kind": "orochi_ex_phase1",
            "phase": 1,
            "evidence_kind": "absolute",
            "apply_quest_hp_correction": False,
            "native_hp": profile.phase1_hp,
            "selected_level": profile.selected_level,
        },
        {
            "code": profile.code,
            "kind": "orochi_ex_middle",
            "phase": 2,
            "evidence_kind": str(middle_evidence_kind),
            "apply_quest_hp_correction": True,
            "native_hp": middle,
            "selected_level": profile.selected_level,
        },
        {
            "code": profile.code,
            "kind": "orochi_ex_phase3",
            "phase": 3,
            "evidence_kind": "absolute",
            "apply_quest_hp_correction": False,
            "native_hp": profile.phase3_hp,
            "selected_level": profile.selected_level,
        },
    )


def _scaled_text(value: str, factor: float, *, label: str) -> str:
    scaled = _positive(value, label=label) * factor
    if not math.isfinite(scaled) or scaled <= 0:
        raise OrochiExHpError(f"{label} scaled to an invalid value: {scaled!r}")
    rounded = int(round(scaled))
    if rounded <= 0:
        raise OrochiExHpError(f"{label} rounded to a non-positive value: {rounded}")
    return str(rounded)


def build_scaled_hp_rows(
    dedicated: dict[str, Any], boss_level: dict[str, Any],
    source_code: str, target_code: str, *,
    fixed_phase_scale: float, middle_scale: float,
    allow_replace: bool = False,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Build, but do not install, a complete dedicated+middle HP replacement.

    The returned dedicated node and ``boss_level`` leaf are safe to install
    together.  Callers cloning to a new code still own zone/head references;
    this function deliberately covers only the three HP bars.
    """
    source = str(source_code)
    target = str(target_code)
    fixed_factor = _factor(fixed_phase_scale, label="fixed_phase_scale")
    middle_factor = _factor(middle_scale, label="middle_scale")
    source_node = dedicated.get(source)
    if not isinstance(source_node, dict) or not source_node:
        raise OrochiExHpError(f"source dedicated row is missing: {source}")
    if target in dedicated and not allow_replace:
        raise OrochiExHpError(f"target dedicated row already exists: {target}")

    level_leaf = boss_level.get(source)
    level_row = _cells(
        level_leaf, label=f"boss_level[{source}]", size=BOSS_LEVEL_COLUMNS
    )
    if level_row[0] != "0":
        raise OrochiExHpError(
            f"boss_level[{source}] is not Hit HP and cannot scale c2 safely"
        )

    target_node = copy.deepcopy(source_node)
    phase_before: dict[str, tuple[int, int]] = {}
    phase_after: dict[str, tuple[int, int]] = {}
    for level_key, leaf in target_node.items():
        row = _cells(
            leaf, label=f"orochi_ex[{source}][{level_key}]", size=PARENT_COLUMNS
        )
        before = (
            int(_positive(row[PHASE1_HP_COLUMN], label=f"{source}.phase1")),
            int(_positive(row[PHASE3_HP_COLUMN], label=f"{source}.phase3")),
        )
        row[PHASE1_HP_COLUMN] = _scaled_text(
            row[PHASE1_HP_COLUMN], fixed_factor, label=f"{source}.phase1"
        )
        row[PHASE3_HP_COLUMN] = _scaled_text(
            row[PHASE3_HP_COLUMN], fixed_factor, label=f"{source}.phase3"
        )
        target_node[level_key] = _leaf(row)
        phase_before[str(level_key)] = before
        phase_after[str(level_key)] = (
            int(row[PHASE1_HP_COLUMN]), int(row[PHASE3_HP_COLUMN])
        )

    old_middle = _positive(level_row[2], label=f"boss_level[{source}].c2")
    level_row[2] = _scaled_text(
        level_row[2], middle_factor, label=f"boss_level[{source}].c2"
    )
    report = {
        "source_code": source,
        "target_code": target,
        "fixed_phase_scale": fixed_factor,
        "middle_scale": middle_factor,
        "phase_hp_before": phase_before,
        "phase_hp_after": phase_after,
        "middle_c2_before": old_middle,
        "middle_c2_after": float(level_row[2]),
    }
    return target_node, _leaf(level_row), report


def replace_hp_profile(
    dedicated: dict[str, Any], boss_level: dict[str, Any], code: str, *,
    fixed_phase_scale: float, middle_scale: float,
) -> dict[str, Any]:
    """Atomically replace all three HP channels of one existing code in memory."""
    node, level_leaf, report = build_scaled_hp_rows(
        dedicated, boss_level, code, code,
        fixed_phase_scale=fixed_phase_scale,
        middle_scale=middle_scale,
        allow_replace=True,
    )
    dedicated[str(code)] = node
    boss_level[str(code)] = level_leaf
    return report
