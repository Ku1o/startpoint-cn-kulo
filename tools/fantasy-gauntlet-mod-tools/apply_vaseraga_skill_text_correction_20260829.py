#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Align Vaseraga's skill text and remove his leader skill-gauge refund."""

from __future__ import annotations

import argparse
import os

# Preserve every already staged character/table edit in the local overlay.
os.environ["WF_LIVE_CDN"] = "0"

import wf_gui
import wf_mod_tool as core
from wf_vaseraga_balance import (
    CHARACTER_ID,
    LEADER_ABILITY_LOGICAL,
    SKILL_DESCRIPTION_FIELDS,
    patch_leader_ability_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    args = parser.parse_args()
    dry_run = not args.apply

    table = core.load_table(LEADER_ABILITY_LOGICAL, wf_gui.TARGET_STORE, wf_gui.SOURCE_STORE)
    rows = core.read_csv_lines(table.text_rows()[CHARACTER_ID])
    _patched, leader_report = patch_leader_ability_rows(rows)

    result = wf_gui.save_char_fields(
        CHARACTER_ID,
        SKILL_DESCRIPTION_FIELDS,
        dry_run,
    )
    print(result["log"] or "Vaseraga skill text already aligned")
    if leader_report["changed"]:
        deletion = wf_gui.delete_line(
            "L:" + CHARACTER_ID,
            int(leader_report["removed_line"]),
            dry_run,
        )
        print(deletion["log"])
    else:
        print("Vaseraga leader skill-gauge refund already removed")
    print("dry-run complete" if dry_run else "Vaseraga text and leader ability aligned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
