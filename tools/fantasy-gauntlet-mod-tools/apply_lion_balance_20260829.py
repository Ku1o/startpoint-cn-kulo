#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将已确认的玛格诺斯能力平衡写入本地待发布覆盖层。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

# 已有待发布 ability 表优先，避免覆盖同一张表中的希耶提／西蒙改动。
os.environ["WF_LIVE_CDN"] = "0"

import wf_gui
import wf_live_cdn
import wf_mod_tool as core
import wf_lion_balance as balance


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
    backup = target.with_name(target.name + f".bak-wfmod-lion-{timestamp}")
    if not backup.exists():
        backup.write_bytes(source)
    target.write_bytes(output)
    wf_gui.add_pending(target)
    wf_gui.record_change(
        logical,
        "玛格诺斯平衡调整: 能力3冲刺／强化弹射追击10→5倍，"
        "FEVER攻击与能力伤害加成改为自身；能力6技能追击50→30倍\n"
        f"source={source_name}",
        backup,
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="写入改动；默认仅预演")
    args = parser.parse_args()

    source, source_name = _source_payload(balance.ABILITY_LOGICAL)
    output, report = balance.patch_ability_table(source)
    print(
        json.dumps(
            {
                "dry_run": not args.apply,
                "source": source_name,
                **report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.apply:
        print("dry-run complete")
        return 0

    changed = _write_payload(
        balance.ABILITY_LOGICAL,
        source,
        output,
        source_name,
        time.strftime("%Y%m%d-%H%M%S"),
    )
    print(f"Magnus balance staged: {int(changed)} binary asset changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
