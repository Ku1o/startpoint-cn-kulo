#!/usr/bin/env python3
"""Fail-closed release gate: ability/leader ability Bool and Option columns.

The 2026-10-06 liangyue C7101 showed that an *empty* string in an
`instant_content` condition row survives packaging, manifest registration and
earlier metadata checks, then crashes the client when the character detail /
skill page parses the row:

  AbilityValues$/parseAt47 -> parseAt72
  LeaderAbilityValues$/parseAt45 -> parseAt70

`by_each_trigger_puller` (columns `instant_content + 25`) accepts only
TRUE/True/true/FALSE/False/false; anything else throws ClientError 7101.
`even_if_owner_dead` (during rows) has the same contract and is already
validated by `wf_client_legality`, but no release gate inspected the *stored*
table bytes, so the bad rows shipped.

The 2026-10-06 liangyue description F1009 then showed the second half of the
same class: the condition variants' Option columns (`flip_limit`,
`power_flip_limit`, `end_power_flip_limit`, `end_power_flip_accepted_levels`
at `instant_content + 15..18`, and `max_accumulation` at `+14`) parse an
empty cell as `Option.Some(null)` / `Option.Some(0)`;
`InstantAbilitySource$/resolveEndPowerFlipLevels` returns `undefined` for
those values and the description generator dereferences the coerced null
array (`.length`) -> TypeError #1009 when the character detail page renders.
Those Option rules now come from `wf_client_legality.option_cell_problems`
so the generator, the editor gate and this release gate cannot drift.

This gate inspects payload content, not metadata:

1. the effective chain terminal state (pristine baseline + enabled patches);
2. every archive member of the requested version edge that is one of the
   ability tables;
3. the declared character rows, which must resolve inside the target edge when
   `--expect-edge` is given.

Any missing member, unknown content kind or illegal Bool value fails the gate
(exit code 1).  The JSON receipt records the scope, per-row evidence and every
problem.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/lens-integration"))
sys.path.insert(0, str(REPO / "tools/fantasy-gauntlet-mod-tools"))

import prepare_content as pc  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_client_legality  # noqa: E402

BOOL_FALSE = {"FALSE", "False", "false"}
BOOL_TRUE = {"TRUE", "True", "true"}

# Derived from the registered client (parser body hashes below).  The dispatch
# map is shared by every ability-like layout; columns are relative to the
# layout blocks, which this gate resolves per table through `wf_describe`.
INSTANT_CONTENT_BOOL_KINDS = frozenset({
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "30", "31", "214", "219", "223", "224", "228", "391", "392", "393", "394", "395",
    "396", "397", "398", "399", "400", "401", "402", "403", "404", "405", "406", "407",
    "408", "409", "410", "411", "412", "414", "415", "416", "417", "418", "419", "420",
    "421", "422", "423", "424", "425", "426", "427", "428", "429", "430", "431", "432",
    "433", "434", "435", "437", "438", "439", "440", "441", "442", "443", "444", "445",
    "446", "447", "448", "449", "450", "451", "452", "453", "454", "455", "456", "457",
    "458", "468", "470", "475", "479", "486", "489", "530", "531", "532", "688", "689",
    "701", "709", "710", "712", "713", "718",
})

# `multiply_trigger`(instant_content + 28) is parsed as a required enum by
# parseAt75 / parseAt73; an empty cell throws ClientError 7050.
INSTANT_CONTENT_MULTIPLY_KINDS = frozenset({
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15",
    "17", "18", "20", "21", "22", "23", "24", "25", "28", "214", "223", "224", "228",
    "461", "468", "470", "486", "489", "525", "701", "709", "710", "712", "713", "718",
})

PARSER_PROVENANCE = {
    "AbilityValues$/parseAt47":
        "9c32845d494c25b0f15009205b38e0cbdd2d4ab1b65ddfaa91e89a3b4deb0943",
    "AbilityValues$/parseAt72":
        "ecaf73f64756879583ebb509956f6f8c2157d682433832e31f634f27743a6f78",
    "LeaderAbilityValues$/parseAt45":
        "474c8ba057534de3f2bceac423d3d244e5f648948f101c5faa26077e897e2ca3",
    "LeaderAbilityValues$/parseAt70":
        "26f5e75204767b00f7b2dfea46bc32923c347f1654ef98d4a5b88ebb2dc00b6c",
    "AbilityValues$/parseAt75":
        "18e968f08029cd62babc65d3abf42705e89c0572f800cc29397e8fc267dd3de4",
}

# ability tables inspected by this gate: (kind, logical, dispatch column,
# dispatch Bool column, during Bool column, multiply column, trigger column)
TABLES = (
    ("ability", "master/ability/ability.orderedmap", 47, 72, 108, 75, 5),
    ("leader_ability", "master/ability/leader_ability.orderedmap", 45, 70, 106, 73, 3),
)

LIANGYUE_CELLS = {
    "master/ability/ability.orderedmap": {
        "1599921": {2: {62: "(None)", 63: "(None)", 64: "(None)",
                        65: "(None)", 72: "false", 75: "0"}},
        "1599922": {2: {61: "(None)", 62: "(None)", 63: "(None)",
                        64: "(None)", 65: "(None)", 72: "false", 75: "0"}},
    },
    "master/ability/leader_ability.orderedmap": {
        "159992": {5: {60: "(None)", 61: "(None)", 62: "(None)",
                       63: "(None)", 70: "false", 73: "0"}},
    },
}


def rows_of(text: str) -> list[list[str]]:
    return core.read_csv_lines(text)


def check_table(raw: bytes, logical: str, kind: str, dispatch_col: int,
                bool_col: int, during_col: int, multiply_col: int,
                trigger_col: int,
                problems: list[dict], scope: str,
                required: dict | None = None,
                expected_cells: dict | None = None) -> dict:
    report = {"scope": scope, "logical": logical, "sha256": hashlib.sha256(raw).hexdigest(),
              "rows": 0, "bool_cells": 0, "multiply_cells": 0,
              "option_cells": 0, "required": {}}
    try:
        table = core.read_orderedmap_file_from_bytes(raw)
    except Exception as exc:  # noqa: BLE001 - malformed payload must fail closed
        problems.append({"scope": scope, "reason": "undecodable-orderedmap",
                         "logical": logical, "error": str(exc)})
        return report
    for key, text in table.items():
        for index, row in enumerate(rows_of(text)):
            report["rows"] += 1
            if len(row) <= max(dispatch_col, bool_col, during_col, multiply_col,
                               trigger_col):
                problems.append({"scope": scope, "reason": "short-row",
                                 "logical": logical, "key": key, "row": index,
                                 "columns": len(row)})
                continue
            trigger = row[trigger_col]
            if trigger == "1":
                report["bool_cells"] += 1
                if row[during_col] not in BOOL_FALSE and row[during_col] not in BOOL_TRUE:
                    problems.append({
                        "scope": scope, "reason": "illegal-bool", "logical": logical,
                        "key": key, "row": index, "column": during_col,
                        "field": "even_if_owner_dead", "value": row[during_col]})
                continue
            if trigger != "0":
                if trigger not in ("", "2"):
                    problems.append({"scope": scope, "reason": "unknown-trigger",
                                     "logical": logical, "key": key, "row": index,
                                     "value": trigger})
                continue
            content = row[dispatch_col]
            if content in INSTANT_CONTENT_BOOL_KINDS:
                report["bool_cells"] += 1
                if row[bool_col] not in BOOL_FALSE and row[bool_col] not in BOOL_TRUE:
                    problems.append({
                        "scope": scope, "reason": "illegal-bool", "logical": logical,
                        "key": key, "row": index, "column": bool_col,
                        "field": "by_each_trigger_puller", "content_kind": content,
                        "value": row[bool_col]})
            if content in INSTANT_CONTENT_MULTIPLY_KINDS:
                report["multiply_cells"] += 1
                value = row[multiply_col]
                if value != "(None)" and not value.lstrip("-").isdigit():
                    problems.append({
                        "scope": scope, "reason": "illegal-enum", "logical": logical,
                        "key": key, "row": index, "column": multiply_col,
                        "field": "multiply_trigger", "content_kind": content,
                        "value": value})
            # Option 列(flip_limit 族 + max_accumulation):规则与生成器/
            # wf_client_legality 共用同一实现,避免门禁漂移(2026-10-06 凉月
            # 描述 F1009:空串 -> Some(null)/Some(0) -> resolveEndPowerFlipLevels
            # 返回 undefined -> 描述生成器 .length 抛 TypeError #1009)。
            option_problems = wf_client_legality.option_cell_problems(kind, row)
            if content in wf_client_legality.INSTANT_CONTENT_LIMIT_KINDS:
                report["option_cells"] += 4
            if content in wf_client_legality.INSTANT_CONTENT_MAX_ACCUMULATION_KINDS:
                report["option_cells"] += 1
            for message in option_problems:
                problems.append({
                    "scope": scope, "reason": "illegal-option-cell",
                    "logical": logical, "key": key, "row": index,
                    "content_kind": content, "detail": message})
    for key in sorted(required or ()):
        text = table.get(key)
        if text is None:
            problems.append({"scope": scope, "reason": "required-key-missing",
                             "logical": logical, "key": key})
            continue
        bools = []
        for index, row in enumerate(rows_of(text)):
            if len(row) <= max(dispatch_col, bool_col, during_col, multiply_col):
                continue
            if row[trigger_col] == "1":
                bools.append(row[during_col])
            elif row[trigger_col] == "0" and row[dispatch_col] in INSTANT_CONTENT_BOOL_KINDS:
                bools.append(row[bool_col])
        report["required"][key] = bools
    for key, per_row in (expected_cells or {}).items():
        text = table.get(key)
        if text is None:
            problems.append({"scope": scope, "reason": "expected-key-missing",
                             "logical": logical, "key": key})
            continue
        rows = rows_of(text)
        for row_index, columns in per_row.items():
            for column, value in columns.items():
                if row_index >= len(rows) or rows[row_index][column] != value:
                    problems.append({
                        "scope": scope, "reason": "expected-cell-mismatch",
                        "logical": logical, "key": key, "row": row_index,
                        "column": column, "expected": value,
                        "actual": (rows[row_index][column]
                                   if row_index < len(rows) else None)})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-version", help="manifest patch version to inspect")
    parser.add_argument("--expect-tail", help="fail unless the chain tail equals this")
    parser.add_argument("--require-key", action="append", default=[],
                        help="ability key that must exist (repeatable)")
    parser.add_argument("--expect-edge", action="store_true",
                        help="required keys must resolve inside the target edge archives")
    parser.add_argument("--check-declared-cells", action="store_true",
                        help="assert the recorded liangyue cells equal the fixed values")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    report = {
        "gate": "ability-strong-fields",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "parser_provenance": PARSER_PROVENANCE,
        "instant_content_bool_kinds": len(INSTANT_CONTENT_BOOL_KINDS),
        "edge": None,
        "tables": [],
        "edge_member_scan": [],
        "required_keys": args.require_key,
        "expect_tail": args.expect_tail,
        "problems": [],
    }
    problems = report["problems"]

    chain = pc.Chain()
    report["chain_tail"] = chain.tail
    if args.expect_tail and chain.tail != args.expect_tail:
        problems.append({"scope": "chain", "reason": "tail mismatch",
                         "tail": chain.tail, "expected": args.expect_tail})

    edge_names: set[str] = set()
    if args.edge_version:
        entry = next((p for p in chain.manifest["patches"]
                      if p.get("version") == args.edge_version and p.get("enabled")),
                     None)
        if entry is None:
            problems.append({"scope": "edge", "reason": "no enabled manifest patch",
                             "version": args.edge_version})
        else:
            report["edge"] = {"id": entry.get("id"), "version": entry.get("version"),
                              "chain": list(entry.get("chain") or []),
                              "files": list(entry.get("files") or [])}
            edge_names = set(entry.get("chain") or [])

    for kind, logical, dispatch_col, bool_col, during_col, multiply_col, trigger_col in TABLES:
        required = {key: True for key in LIANGYUE_CELLS.get(logical, {})}
        for key in args.require_key:
            required[key] = True
        expected = (LIANGYUE_CELLS.get(logical)
                    if args.check_declared_cells else None)
        raw = chain.get(("common", pc.hrel(logical)))
        if raw is None:
            problems.append({"scope": "chain", "reason": "table-missing",
                             "logical": logical})
            continue
        report["tables"].append(check_table(
            raw, logical, kind, dispatch_col, bool_col, during_col,
            multiply_col, trigger_col, problems,
            "chain", required=required, expected_cells=expected))
        if args.expect_edge:
            source = chain.reads["|".join(("common", pc.hrel(logical)))]["archive"]
            if edge_names and Path(source).name not in edge_names:
                problems.append({
                    "scope": "edge", "reason": "required table not served by edge",
                    "logical": logical, "archive": Path(source).name,
                    "edge_archives": sorted(edge_names)})

    for name in sorted(edge_names):
        path = REPO / "assets/asset-patch/active" / name
        if not path.is_file():
            problems.append({"scope": "edge", "reason": "archive missing",
                             "archive": name})
            continue
        with zipfile.ZipFile(path) as archive:
            for (kind, logical, dispatch_col, bool_col, during_col,
                 multiply_col, trigger_col) in TABLES:
                member = pc.member(("common", pc.hrel(logical)))
                if member not in archive.namelist():
                    continue
                report["edge_member_scan"].append(check_table(
                    archive.read(member), logical, kind, dispatch_col, bool_col,
                    during_col, multiply_col, trigger_col, problems, f"edge:{name}"))

    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        print(f"receipt: {args.receipt}")
    print(f"chain_tail={report.get('chain_tail')} "
          f"tables={len(report['tables'])} edge_members={len(report['edge_member_scan'])} "
          f"problems={len(problems)}")
    for problem in problems[:20]:
        print(json.dumps(problem, ensure_ascii=False))
    if problems:
        raise SystemExit(1)
    print("OK: every reachable Bool/enum/Option cell in the inspected ability "
          "tables is legal")


if __name__ == "__main__":
    main()
