#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将已确认的杰拉德平衡写入本地待发布覆盖层。"""

from __future__ import annotations

import argparse
import json
import os
import time

# 已有待发布ability表优先，避免覆盖其他角色共享表中的待发布改动。
os.environ["WF_LIVE_CDN"] = "0"

import wf_gui
import wf_live_cdn
import wf_mod_tool as core
import wf_gerald_balance as balance


def _relative(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"{digest[:2]}/{digest[2:]}"


def _source_payload(logical: str) -> tuple[bytes, str]:
    relative = _relative(logical)
    target = wf_gui.TARGET_STORE / relative
    if relative in set(wf_gui.read_pending()):
        if not target.is_file():
            raise FileNotFoundError(f"pending资产缺失: {target}")
        return target.read_bytes(), "local-pending"
    current = wf_live_cdn.read_logical(logical)
    return current.data, f"live:{current.tail}"


def _write_payload(
    logical: str,
    source: bytes,
    output: bytes,
    source_name: str,
    timestamp: str,
) -> bool:
    if output == source:
        return False
    target = wf_gui.TARGET_STORE / _relative(logical)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(target.name + f".bak-wfmod-gerald-{timestamp}")
    if not backup.exists():
        backup.write_bytes(source)
    target.write_bytes(output)
    wf_gui.add_pending(target)
    wf_gui.record_change(
        logical,
        "杰拉德平衡调整: 两档主动技双抗降低统一15%；能力2冲刺增益限1次；"
        "能力3 PF3追击10→3倍；能力4主位限定且10→1倍；"
        "能力5主位限定且六属性各5→3倍\n"
        f"source={source_name}",
        backup,
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="写入改动；默认仅预演")
    args = parser.parse_args()

    payloads: dict[str, tuple[bytes, bytes, str, dict]] = {}
    source, source_name = _source_payload(balance.ABILITY_LOGICAL)
    output, report = balance.patch_ability_table(source)
    payloads[balance.ABILITY_LOGICAL] = (source, output, source_name, report)

    for level, logical in balance.SKILL_DSL_LOGICALS.items():
        source, source_name = _source_payload(logical)
        output, report = balance.patch_skill_dsl(source, logical)
        report["level"] = level
        payloads[logical] = (source, output, source_name, report)

    print(
        json.dumps(
            {
                "dry_run": not args.apply,
                "assets": {
                    logical: {"source": source_name, **report}
                    for logical, (_source, _output, source_name, report) in payloads.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.apply:
        print("dry-run complete")
        return 0

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    changed = 0
    for logical, (source, output, source_name, _report) in payloads.items():
        changed += int(
            _write_payload(logical, source, output, source_name, timestamp)
        )
    print(f"Gerald balance staged: {changed} binary assets changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
