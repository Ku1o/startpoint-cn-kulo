#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage the reviewed Simoun balance into the local unpublished overlay."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

# The writable Git overlay is authoritative for already staged assets.  Live
# data is fetched explicitly only when a target asset has no pending local row.
os.environ["WF_LIVE_CDN"] = "0"

import wf_gui
import wf_live_cdn
import wf_mod_tool as core
import wf_simoun_balance as balance


def _relative(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"{digest[:2]}/{digest[2:]}"


def _source_payload(logical: str) -> tuple[bytes, str]:
    relative = _relative(logical)
    target = wf_gui.TARGET_STORE / relative
    pending = set(wf_gui.read_pending())
    if relative in pending:
        if not target.is_file():
            raise FileNotFoundError(f"pending 资产缺失: {target}")
        return target.read_bytes(), "local-pending"
    current = wf_live_cdn.read_logical(logical)
    return current.data, f"live:{current.tail}"


def _write_payload(
    logical: str,
    source: bytes,
    output: bytes,
    source_name: str,
    summary: str,
    timestamp: str,
) -> bool:
    if output == source:
        return False
    target = wf_gui.TARGET_STORE / _relative(logical)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(target.name + f".bak-wfmod-simoun-{timestamp}")
    if not backup.exists():
        backup.write_bytes(source)
    target.write_bytes(output)
    wf_gui.add_pending(target)
    wf_gui.record_change(logical, f"{summary}\nsource={source_name}", backup)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    args = parser.parse_args()
    dry_run = not args.apply

    payloads: dict[str, tuple[bytes, bytes, str, dict]] = {}

    for logical, patcher in (
        (balance.ABILITY_LOGICAL, balance.patch_ability_table),
        (balance.LEADER_ABILITY_LOGICAL, balance.patch_leader_ability_table),
    ):
        source, source_name = _source_payload(logical)
        output, report = patcher(source)
        payloads[logical] = (source, output, source_name, report)

    for level, logical in balance.SKILL_DSL_LOGICALS.items():
        source, source_name = _source_payload(logical)
        output, report = balance.patch_skill_dsl(source, logical)
        report["level"] = level
        payloads[logical] = (source, output, source_name, report)

    text_preview = wf_gui.save_char_fields(
        balance.CHARACTER_ID,
        {
            "skill_desc": balance.SKILL_DESCRIPTION,
            "skill_plus_desc": balance.SKILL_DESCRIPTION,
            "skill_plusplus_desc": balance.SKILL_DESCRIPTION,
        },
        True,
    )

    print(json.dumps(
        {
            "dry_run": dry_run,
            "assets": {
                logical: {"source": source_name, **report}
                for logical, (_source, _output, source_name, report) in payloads.items()
            },
            "description": balance.SKILL_DESCRIPTION,
            "text_preview": text_preview.get("log", ""),
        },
        ensure_ascii=False,
        indent=2,
    ))

    if dry_run:
        print("dry-run complete")
        return 0

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    changed = 0
    for logical, (source, output, source_name, report) in payloads.items():
        if _write_payload(
            logical,
            source,
            output,
            source_name,
            "西蒙平衡调整: 队长技与能力1～3团队增益减半、自身专属增益保留75%；"
            "能力4～6不变；主动技能全队技能槽15%、结算后羊群清零",
            timestamp,
        ):
            changed += 1

    text_result = wf_gui.save_char_fields(
        balance.CHARACTER_ID,
        {
            "skill_desc": balance.SKILL_DESCRIPTION,
            "skill_plus_desc": balance.SKILL_DESCRIPTION,
            "skill_plusplus_desc": balance.SKILL_DESCRIPTION,
        },
        False,
    )
    print(text_result.get("log") or "西蒙三档主动技能文案已是目标值")
    print(f"Simoun balance staged: {changed} binary assets changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
