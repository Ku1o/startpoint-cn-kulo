#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Align Siete's active-skill text and runtime damage bands.

The skill has one alternative branch for each Sword God level.  A level-N
branch contains N+1 CreateNormalAttack commands (one avatar strike and N
projectile strikes).  This migration keeps that hit topology and changes the
per-hit multiplier to 25x / 40x / 55x for levels 1-7 / 8-10 / 11-12.
"""

from __future__ import annotations

import argparse
import json

import wf_gui


CHARACTER_ID = "149995"
UNIQUE_CONDITION_ID = 149995
SKILL_DESCRIPTION = (
    "剑神双奏：无「剑神」时，原地召唤剑神——全体队员获得15%护盾，"
    "自身获得1级「剑神」与30%加速（10秒）；持有N级「剑神」时，"
    "剑神化身突进攻击1段，并向前方推出N把灵剑（每把攻击1段），共N+1段，"
    "随后消耗1级「剑神」。每段倍率：1～7级25倍，8～10级40倍，11～12级55倍。"
)


def expected_multiplier(layer: int) -> float:
    if 1 <= layer <= 7:
        return 25.0
    if 8 <= layer <= 10:
        return 40.0
    if 11 <= layer <= 12:
        return 55.0
    raise ValueError(f"unexpected Sword God layer: {layer}")


def rewrite_damage(tree: object) -> dict[int, int]:
    counts = {layer: 0 for layer in range(1, 13)}

    def walk(node: object, layer: int | None = None) -> None:
        if isinstance(node, list):
            if len(node) >= 2 and node[0] == "Command" and isinstance(node[1], list):
                command = node[1]
                if (
                    command
                    and command[0] == "ConditionalsConditionAccumulationNumber"
                    and command[1] == ["DCUnique", UNIQUE_CONDITION_ID]
                ):
                    layer = int(command[2])
                if command and command[0] == "CreateNormalAttack" and layer is not None:
                    multiplier = expected_multiplier(layer)
                    command[6][0]["min"] = multiplier
                    command[6][0]["max"] = multiplier
                    counts[layer] += 1
            for child in node:
                walk(child, layer)
        elif isinstance(node, dict):
            for child in node.values():
                walk(child, layer)

    walk(tree)
    expected_counts = {layer: layer + 1 for layer in range(1, 13)}
    if counts != expected_counts:
        raise RuntimeError(f"unexpected hit topology: {counts}; expected {expected_counts}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    args = parser.parse_args()
    dry_run = not args.apply

    text_result = wf_gui.save_char_fields(
        CHARACTER_ID,
        {
            "skill_desc": SKILL_DESCRIPTION,
            "skill_plus_desc": SKILL_DESCRIPTION,
            "skill_plusplus_desc": SKILL_DESCRIPTION,
        },
        dry_run,
    )
    print(text_result["log"] or "skill description already aligned")

    for level in ("1", "2"):
        current = wf_gui.get_skill_dsl_json(CHARACTER_ID, level)
        tree = json.loads(current["json_text"])
        counts = rewrite_damage(tree)
        result = wf_gui.save_skill_dsl_json(
            CHARACTER_ID,
            level,
            json.dumps(tree, ensure_ascii=False, indent=1),
            dry_run,
        )
        print(f"level {level}: {sum(counts.values())} damage nodes; {result['log']}")

    print("dry-run complete" if dry_run else "Siete active skill aligned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
