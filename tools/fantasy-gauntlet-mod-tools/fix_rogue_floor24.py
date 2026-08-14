#!/usr/bin/env python
"""Replace only Deep Abyss floor 24's tower-only boss field with its official Rush field."""

from __future__ import annotations

import csv
import io

import wf_quest_lib as q


QUEST_TABLE = "master/quest/event/rush_event_quest.orderedmap"
EVENT_ID = "700099"
ROUND_ID = "24"

OLD_FIELD = "tower_dungeon_area_9_7_3"
NEW_FIELD = "administrator_another_dark_rush"


def parse_row(raw: str) -> list[str]:
    return next(csv.reader(io.StringIO(raw)))


def encode_row(row: list[str]) -> str:
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="").writerow(row)
    return stream.getvalue()


def main() -> None:
    table = q.load_table(QUEST_TABLE)
    row = parse_row(table[EVENT_ID][ROUND_ID])
    if len(row) != 103:
        raise RuntimeError(f"unexpected floor 24 column count: {len(row)}")
    if row[98] not in {OLD_FIELD, NEW_FIELD}:
        raise RuntimeError(f"unexpected floor 24 field: {row[98]}")

    previous = row[98]
    row[98] = NEW_FIELD
    table[EVENT_ID][ROUND_ID] = encode_row(row)
    q.save_table(QUEST_TABLE, table)

    check = parse_row(q.load_table(QUEST_TABLE)[EVENT_ID][ROUND_ID])
    if check[98] != NEW_FIELD or len(check) != 103:
        raise RuntimeError("floor 24 round-trip validation failed")
    print(f"floor 24 field: {previous} -> {check[98]}")
    print(f"columns: {len(check)}; enemy level: {check[95]}; recommended element: {check[69]}")


if __name__ == "__main__":
    main()
