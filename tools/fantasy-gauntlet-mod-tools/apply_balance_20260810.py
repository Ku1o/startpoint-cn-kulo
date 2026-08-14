from __future__ import annotations

import argparse
import json
import shutil
import sys
import zlib
from pathlib import Path


MOD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOD_DIR))

import wf_dsl  # noqa: E402
import wf_mod_tool as core  # noqa: E402


ABILITY_LOGICAL = core.ABILITY_LOGICAL
LEADER_LOGICAL = "master/ability/leader_ability.orderedmap"

GINOVI_PF = {
    "lv1": {
        "logical": (
            "battle/action/power_flip/action/override/"
            "ginovi_pf$ginovi_pf_lv1.action.dsl.amf3.deflate"
        ),
        "attack_point": 20.0,
        "hit": 5.0,
        "hits": 4,
        "total": 40.0,
    },
    "lv2": {
        "logical": (
            "battle/action/power_flip/action/override/"
            "ginovi_pf$ginovi_pf_lv2.action.dsl.amf3.deflate"
        ),
        "attack_point": 30.0,
        "hit": 5.0,
        "hits": 6,
        "total": 60.0,
    },
    "lv3": {
        "logical": (
            "battle/action/power_flip/action/override/"
            "ginovi_pf$ginovi_pf_lv3.action.dsl.amf3.deflate"
        ),
        "attack_point": 40.0,
        "hit": 5.0,
        "hits": 10,
        "total": 90.0,
    },
}

DARKNESS_DRAGON_SKILL = (
    "battle/action/skill/action/rare4/"
    "darkness_dragon$darkness_dragon_1.action.dsl.amf3.deflate"
)
GOLDEN_DRAGON_JR_SKILL = (
    "battle/action/skill/action/rare5/"
    "golden_dragon_jr$golden_dragon_jr_1.action.dsl.amf3.deflate"
)


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def read_dsl(logical: str, target: Path, source: Path):
    target_path = core.table_path(target, logical)
    source_path = core.table_path(source, logical)
    path = target_path if target_path.exists() else source_path
    if not path.exists():
        raise FileNotFoundError(f"missing DSL: {logical}")
    tree = wf_dsl.parse_dsl(zlib.decompress(path.read_bytes(), -15))["tree"]
    return tree, path, target_path


def write_dsl(tree, target_path: Path, suffix: str) -> None:
    encoded = wf_dsl.encode_amf3(tree)
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    blob = comp.compress(encoded) + comp.flush()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        backup = target_path.with_name(target_path.name + suffix)
        if not backup.exists():
            shutil.copy2(target_path, backup)
    target_path.write_bytes(blob)


def set_range(node, value: float) -> None:
    if not isinstance(node, dict) or "min" not in node or "max" not in node:
        raise ValueError(f"not a numeric range: {node!r}")
    node["min"] = value
    node["max"] = value


def patch_ginovi_power_flip(target: Path, source: Path, write: bool) -> dict:
    report = {}
    for level, spec in GINOVI_PF.items():
        tree, source_path, target_path = read_dsl(spec["logical"], target, source)
        attack_nodes = [
            node
            for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "ACAttackPoint"
        ]
        hit_nodes = [
            node
            for node in walk(tree)
            if isinstance(node, list) and node and node[0] == "CreateNormalAttack"
        ]
        if len(attack_nodes) != 1 or len(hit_nodes) != spec["hits"]:
            raise ValueError(
                f"{level}: unexpected PF shape attack={len(attack_nodes)} "
                f"hits={len(hit_nodes)}"
            )
        set_range(attack_nodes[0][1][0], spec["attack_point"])
        for node in hit_nodes:
            set_range(node[6][0], spec["hit"])
        actual_total = spec["attack_point"] + spec["hit"] * len(hit_nodes)
        if actual_total != spec["total"]:
            raise AssertionError(f"{level}: total {actual_total} != {spec['total']}")
        if write:
            write_dsl(tree, target_path, ".bak-balance-20260810")
        report[level] = {
            "source": str(source_path),
            "target": str(target_path),
            "base": spec["attack_point"],
            "hit_count": len(hit_nodes),
            "per_hit": spec["hit"],
            "theoretical_total": actual_total,
        }
    return report


def patch_element_debuff(
    logical: str,
    target: Path,
    source: Path,
    value: float,
    stack_cap: int,
    write: bool,
) -> dict:
    tree, source_path, target_path = read_dsl(logical, target, source)
    nodes = [
        node
        for node in walk(tree)
        if isinstance(node, list)
        and node
        and node[0] == "ACToleranceOfElement"
        and len(node) >= 5
        and node[2] in (5, 6)
    ]
    elements = sorted(int(node[2]) for node in nodes)
    if elements != [5, 6]:
        raise ValueError(f"unexpected element resistance nodes: {elements}")
    before = []
    for node in nodes:
        before.append(
            {
                "element": int(node[2]),
                "value": node[3][0]["min"],
                "stack_cap": node[4][0]["max"],
            }
        )
        set_range(node[3][0], value)
        set_range(node[4][0], stack_cap)
    if write:
        write_dsl(tree, target_path, ".bak-balance-20260810")
    return {
        "source": str(source_path),
        "target": str(target_path),
        "before": before,
        "after": {"value": value, "stack_cap": stack_cap},
    }


def patch_leader(target: Path, source: Path, write: bool) -> dict:
    table = core.load_table(LEADER_LOGICAL, target, source)
    row_map = table.text_rows()
    lines = core.read_csv_lines(row_map["169999"])
    matches = []
    for line_index, row in enumerate(lines):
        for column, value in enumerate(row):
            if value == "36000000":
                matches.append((line_index, column))
    if (
        len(matches) != 2
        or matches[0][0] != matches[1][0]
        or matches[1][1] != matches[0][1] + 1
    ):
        context = [
            {
                "line": line_index + 1,
                "column": column,
                "trigger": lines[line_index][25] if len(lines[line_index]) > 25 else None,
                "effect": lines[line_index][45] if len(lines[line_index]) > 45 else None,
                "target": lines[line_index][46] if len(lines[line_index]) > 46 else None,
            }
            for line_index, column in matches
        ]
        raise ValueError(
            f"169999 leader 6-second field count={len(matches)} context={context}"
        )
    for line_index, column in matches:
        lines[line_index][column] = "24000000"
    table.set_text_rows({"169999": core.write_csv_lines(lines)})
    output = core.table_path(target, LEADER_LOGICAL)
    if write:
        output = core.write_table(table, target, ".bak-balance-20260810")
    return {
        "row": "169999",
        "fields": [[line + 1, column] for line, column in matches],
        "before_seconds": 6,
        "after_seconds": 4,
        "output": str(output),
    }


def set_ability_effect(
    row_map: dict[str, str],
    key: str,
    line_number: int,
    effect: str,
    old: int,
    new: int,
) -> dict:
    lines = core.read_csv_lines(row_map[key])
    row = lines[line_number - 1]
    cbase = 47
    if row[cbase] != effect:
        raise ValueError(
            f"{key} line {line_number}: effect {row[cbase]} != expected {effect}"
        )
    old_scaled = str(old * 1000)
    new_scaled = str(new * 1000)
    if row[cbase + 4] != old_scaled or row[cbase + 5] != old_scaled:
        raise ValueError(
            f"{key} line {line_number}: value "
            f"{row[cbase + 4]}/{row[cbase + 5]} != {old_scaled}"
        )
    row[cbase + 4] = new_scaled
    row[cbase + 5] = new_scaled
    row_map[key] = core.write_csv_lines(lines)
    return {
        "key": key,
        "line": line_number,
        "effect": effect,
        "before": old,
        "after": new,
    }


def patch_darkness_dragon_abilities(target: Path, source: Path, write: bool) -> dict:
    table = core.load_table(ABILITY_LOGICAL, target, source)
    row_map = table.text_rows()
    changes = []
    # Attack total: 750% -> 450% (-300%).
    for key, line, old, new in (
        ("2610891", 1, 100, 60),
        ("2610891", 3, 100, 60),
        ("2610891", 4, 100, 60),
        ("2610891", 5, 100, 60),
        ("2610893", 2, 200, 120),
        ("2610893", 6, 150, 90),
    ):
        changes.append(set_ability_effect(row_map, key, line, "32", old, new))
    # Skill-damage total: 690% -> 390% (-300%).
    for key, line, old, new in (
        ("2610891", 2, 120, 60),
        ("2610893", 1, 250, 150),
        ("2610893", 5, 200, 120),
        ("2610895", 1, 120, 60),
    ):
        changes.append(set_ability_effect(row_map, key, line, "34", old, new))
    # Ability 6: independent skill-damage multiplier +30% -> +10%.
    # Effect 693 is independent direct-attack damage and remains +20%.
    changes.append(set_ability_effect(row_map, "2610896", 1, "694", 30, 10))
    table.set_text_rows({key: row_map[key] for key in {c["key"] for c in changes}})
    output = core.table_path(target, ABILITY_LOGICAL)
    if write:
        output = core.write_table(table, target, ".bak-balance-20260810")
    return {
        "changes": changes,
        "attack_total": {"before": 750, "after": 450},
        "skill_damage_total": {"before": 690, "after": 390},
        "output": str(output),
    }


def repair_darkness_dragon_ability6(
    target: Path, source: Path, write: bool
) -> dict:
    """Idempotently repair only Almadeus ability 6.

    Effect 694 is the independent skill-damage multiplier and must be +10%.
    Effect 693 is the separate independent direct-attack multiplier and must
    remain +20%.  This narrow entry point is safe to rerun after the larger
    balance batch has already been applied.
    """
    table = core.load_table(ABILITY_LOGICAL, target, source)
    row_map = table.text_rows()
    lines = core.read_csv_lines(row_map["2610896"])
    cbase = 47
    wanted = ((1, "694", "10000"), (2, "693", "20000"))
    changes = []
    for line_number, effect, value in wanted:
        row = lines[line_number - 1]
        if row[cbase] != effect:
            raise ValueError(
                f"2610896 line {line_number}: effect {row[cbase]} != {effect}"
            )
        before = [row[cbase + 4], row[cbase + 5]]
        row[cbase + 4] = value
        row[cbase + 5] = value
        changes.append(
            {
                "line": line_number,
                "effect": effect,
                "before": before,
                "after": [value, value],
            }
        )
    table.set_text_rows({"2610896": core.write_csv_lines(lines)})
    output = core.table_path(target, ABILITY_LOGICAL)
    if write:
        output = core.write_table(
            table, target, ".bak-almadeus-ability6-20260810"
        )
    return {"changes": changes, "output": str(output)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply 2026-08-10 balance batch")
    parser.add_argument("--target-store", type=Path, required=True)
    parser.add_argument("--source-store", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--only",
        choices=("almadeus-ability6",),
        help="run one idempotent targeted repair instead of the full batch",
    )
    args = parser.parse_args()

    target = args.target_store.resolve()
    source = args.source_store.resolve()
    if args.only == "almadeus-ability6":
        report = {
            "write": args.write,
            "261089": {
                "ability6": repair_darkness_dragon_ability6(
                    target, source, args.write
                )
            },
        }
    else:
        report = {
            "write": args.write,
            "169999": {
                "power_flip": patch_ginovi_power_flip(target, source, args.write),
                "leader": patch_leader(target, source, args.write),
            },
            "151159": patch_element_debuff(
                GOLDEN_DRAGON_JR_SKILL,
                target,
                source,
                value=-0.075,
                stack_cap=2,
                write=args.write,
            ),
            "261089": {
                "skill": patch_element_debuff(
                    DARKNESS_DRAGON_SKILL,
                    target,
                    source,
                    value=-0.05,
                    stack_cap=2,
                    write=args.write,
                ),
                "abilities": patch_darkness_dragon_abilities(
                    target, source, args.write
                ),
            },
        }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
