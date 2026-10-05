#!/usr/bin/env python3
"""Read-only audit of the reported plum samurai / flying wing combination.

This inspects the local active patch chain, not an installed client or a live
server. It does not simulate battle scheduling or establish a freeze's cause.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

import wf_chain_squash as chain
import wf_describe as describe
import wf_mod_tool as core


SOUL_LOGICAL = "master/ability/ability_soul.orderedmap"
TABLES = (core.CHARACTER_LOGICAL, core.ABILITY_LOGICAL, SOUL_LOGICAL)


def read_local_tables(repo: Path) -> tuple[str, dict, dict]:
    graph = chain.VisibleGraph()
    chain._scan_zip_dir(
        graph, repo / "assets/asset-patch/active", "patch",
        "asset-patch/active", "asset-patch:active", False,
    )
    if graph.issues:
        raise ValueError("; ".join(graph.issues))
    tail, edges = chain.find_path(graph, "1.4.54")
    manifest = json.loads((repo / "assets/asset-patch/manifest.json").read_text())
    if tail != manifest["cdn_version"]:
        raise ValueError(f"Local active tail {tail} != manifest {manifest['cdn_version']}")
    if set(edges) != set(graph.edges):
        raise ValueError("Local active graph contains edges outside the selected path")
    archives = [
        archive
        for edge in edges
        for archive in sorted(graph.edges[edge], key=chain.VisibleArchive.order_key)
    ]
    pending = {}
    for logical in TABLES:
        digest = core.sha1_path(logical)
        pending[f"production/upload/{digest[:2]}/{digest[2:]}"] = logical
    tables, sources = {}, {}
    # Resolve the last whole-table writer; never silently skip a broken newer ZIP.
    for archive in reversed(archives):
        with zipfile.ZipFile(archive.path) as zipped:
            for member in list(pending):
                if member not in zipped.namelist():
                    continue
                logical = pending.pop(member)
                raw = zipped.read(member)
                ordered = core.read_orderedmap_bytes(raw, logical, archive.path)
                tables[logical] = {
                    key: core.read_csv_lines(value)
                    for key, value in ordered.text_rows().items()
                }
                sources[logical] = {
                    "archive": archive.path.relative_to(repo).as_posix(),
                    "member": member,
                    "table_sha256": hashlib.sha256(raw).hexdigest(),
                }
        if not pending:
            return tail, tables, sources
    raise ValueError(f"Tables missing from local active chain: {list(pending.values())}")


def select_rule(rows: list[list[str]], kind: str, trigger: str, effect: str) -> dict:
    layout = describe.layout(kind)
    blocks = layout["blocks"]
    t, c = blocks["instant_trigger"], blocks["instant_content"]
    mode = 5 if kind == "ability" else 2
    matches = [
        (index, row) for index, row in enumerate(rows)
        if len(row) == layout["ncols"]
        and row[mode] == "0" and row[t] == trigger and row[c] == effect
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one {kind} {trigger}->{effect} row, got {len(matches)}")
    index, row = matches[0]
    return {
        "row_index": index,
        "description": describe.describe_line(row, kind),
        "main_only": row[1] == "false" if kind == "ability" else None,
        "preconditions": [
            row[blocks[name]:blocks[name] + 7]
            for name in ("precondition1", "precondition2", "precondition3")
        ],
        "trigger": trigger,
        "trigger_puller": row[t + 1:t + 3],
        "threshold_raw": row[t + 3:t + 5],
        "trigger_limit_raw": row[t + 7],
        "cooldown_frames_raw": row[t + 8],
        "effect": effect,
        "target": row[c + 1:c + 3],
        "strength_raw": row[c + 4:c + 6],
        "raw_row": row,
    }


def audit(repo: Path) -> dict:
    tail, tables, sources = read_local_tables(repo)
    character = tables[core.CHARACTER_LOGICAL]["159998"][0]
    ability_id = character[core.CHARACTER_COLUMNS["ability_3"]]
    return {
        "scope": "local-active-only; not live CDN or installed APK verification",
        "status": "data evidence only; freeze not reproduced or fixed",
        "tail": tail,
        "sources": sources,
        "character_id": "159998",
        "code_name": character[core.CHARACTER_COLUMNS["code_name"]],
        "ability_id": ability_id,
        "gauge_to_combo": select_rule(
            tables[core.ABILITY_LOGICAL][ability_id], "ability", "141", "226",
        ),
        "combo_to_gauge": select_rule(
            tables[SOUL_LOGICAL]["100020"], "ability_soul", "12", "211",
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(audit(args.repo.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
