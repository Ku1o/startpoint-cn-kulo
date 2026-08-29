#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Make all three Simoun skill descriptions match the reviewed balance."""

from __future__ import annotations

import argparse

import wf_gui
from wf_simoun_balance import SKILL_DESCRIPTION


CHARACTER_ID = "169996"
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    args = parser.parse_args()
    result = wf_gui.save_char_fields(
        CHARACTER_ID,
        {
            "skill_desc": SKILL_DESCRIPTION,
            "skill_plus_desc": SKILL_DESCRIPTION,
            "skill_plusplus_desc": SKILL_DESCRIPTION,
        },
        not args.apply,
    )
    print(result["log"] or "Simoun skill text already aligned")
    print("dry-run complete" if not args.apply else "Simoun skill text aligned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
