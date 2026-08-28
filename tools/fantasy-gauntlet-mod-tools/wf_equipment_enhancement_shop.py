#!/usr/bin/env python3
"""Build the client enhancement-shop rows from the server shop JSON.

The live CDN remains the read source. Only Liberator (5010070) and Terminator
(5020043) rows are rebuilt; every unrelated orderedmap row is preserved byte
for byte.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import wf_mod_tool as core


ROOT = Path(__file__).resolve().parents[2]
SHOP_JSON = ROOT / "assets" / "equipment_enhancement_shop.json"
LOGICAL_PATH = "master/equipment_enhancement/equipment_enhancement_shop.orderedmap"

TARGETS = {
    5010070: ("1001", tuple(["1001", *map(str, range(1003, 1015))])),
    5020043: ("1002", tuple(["1002", *map(str, range(1015, 1027))])),
}
EXPECTED_CAPS = (1, 12, 23, 34, 45, 56, 69, 70, 77, 84, 91, 98, 99)

SHOP_CATEGORY_COLUMN = 0
GROUP_ID_COLUMN = 2
STAGE_COLUMN = 3
COST_ID_COLUMN = 14
COST_AMOUNT_COLUMN = 15
AVAILABLE_FROM_COLUMN = 22
EQUIPMENT_ID_COLUMN = 29
MAX_LEVEL_COLUMN = 30
REQUIRED_AWAKENING_COLUMN = 31
MINIMUM_COLUMN_COUNT = 32


def _single_csv_row(text: str, label: str) -> list[str]:
    rows = core.read_csv_lines(text)
    if len(rows) != 1 or len(rows[0]) < MINIMUM_COLUMN_COUNT:
        raise ValueError(f"{label} is not a supported enhancement-shop row")
    return rows[0]


def _target_server_rows(document: dict[str, dict]) -> dict[int, list[tuple[str, dict]]]:
    result: dict[int, list[tuple[str, dict]]] = {}
    for equipment_id, (_base_key, expected_keys) in TARGETS.items():
        rows = sorted(
            (
                (str(shop_item_id), row)
                for shop_item_id, row in document.items()
                if int(row.get("equipmentId", 0)) == equipment_id
            ),
            key=lambda entry: int(entry[1]["stage"]),
        )
        if tuple(key for key, _row in rows) != expected_keys:
            raise ValueError(f"equipment {equipment_id} shop item ids drifted")
        if tuple(int(row["stage"]) for _key, row in rows) != tuple(range(1, 14)):
            raise ValueError(f"equipment {equipment_id} stages must be 1..13")
        if tuple(int(row["enhancementMaxLevel"]) for _key, row in rows) != EXPECTED_CAPS:
            raise ValueError(f"equipment {equipment_id} stage caps drifted")
        for _key, row in rows:
            if row.get("costs") != [{"id": 40313, "amount": 1}]:
                raise ValueError(f"equipment {equipment_id} must cost one Pina crystal per stage")
        result[equipment_id] = rows
    return result


def build_client_table(
    source: core.OrderedMap,
    shop_document: dict[str, dict],
) -> core.OrderedMap:
    configured = _target_server_rows(shop_document)
    source_pairs = list(zip(source.keys, source.rows))
    source_rows = source.text_rows()
    all_target_keys = {
        key
        for _equipment_id, (_base_key, keys) in TARGETS.items()
        for key in keys
    }

    generated: dict[str, bytes] = {}
    for equipment_id, (base_key, expected_keys) in TARGETS.items():
        if base_key not in source_rows:
            raise ValueError(f"client base row {base_key} is missing")
        template = _single_csv_row(source_rows[base_key], base_key)
        rows = configured[equipment_id]
        for (shop_item_id, server_row), expected_key in zip(rows, expected_keys):
            if shop_item_id != expected_key:
                raise ValueError(f"equipment {equipment_id} row order drifted")
            client_row = list(template)
            client_row[SHOP_CATEGORY_COLUMN] = str(server_row["shopCategoryId"])
            client_row[GROUP_ID_COLUMN] = str(server_row["groupId"])
            client_row[STAGE_COLUMN] = str(server_row["stage"])
            client_row[COST_ID_COLUMN] = str(server_row["costs"][0]["id"])
            client_row[COST_AMOUNT_COLUMN] = str(server_row["costs"][0]["amount"])
            client_row[AVAILABLE_FROM_COLUMN] = str(server_row["availableFrom"])
            client_row[EQUIPMENT_ID_COLUMN] = str(server_row["equipmentId"])
            client_row[MAX_LEVEL_COLUMN] = str(server_row["enhancementMaxLevel"])
            client_row[REQUIRED_AWAKENING_COLUMN] = str(server_row["requireAwakeningLevel"])
            generated[shop_item_id] = core.write_csv_lines([client_row]).encode("utf-8")

    output_keys: list[str] = []
    output_rows: list[bytes] = []
    inserted_bases: set[str] = set()
    for key, row in source_pairs:
        if key in all_target_keys:
            for _equipment_id, (base_key, keys) in TARGETS.items():
                if key == base_key:
                    output_keys.extend(keys)
                    output_rows.extend(generated[target_key] for target_key in keys)
                    inserted_bases.add(base_key)
            continue
        output_keys.append(key)
        output_rows.append(row)

    expected_bases = {base_key for base_key, _keys in TARGETS.values()}
    if inserted_bases != expected_bases:
        raise ValueError("not every target base row was inserted")

    output = core.OrderedMap(LOGICAL_PATH, output_keys, output_rows, source.source_path)
    verify_client_table(source, output, shop_document)
    return output


def verify_client_table(
    source: core.OrderedMap,
    output: core.OrderedMap,
    shop_document: dict[str, dict],
) -> None:
    configured = _target_server_rows(shop_document)
    source_map = dict(zip(source.keys, source.rows))
    output_map = dict(zip(output.keys, output.rows))
    all_target_keys = {
        key
        for _equipment_id, (_base_key, keys) in TARGETS.items()
        for key in keys
    }
    if len(output.keys) != len(source.keys) + 24 or len(set(output.keys)) != len(output.keys):
        raise ValueError("client enhancement-shop key count is invalid")
    for key, row in source_map.items():
        if key not in all_target_keys and output_map.get(key) != row:
            raise ValueError(f"unrelated client row changed: {key}")

    for equipment_id, rows in configured.items():
        for shop_item_id, server_row in rows:
            client_row = _single_csv_row(
                output_map[shop_item_id].decode("utf-8"), shop_item_id
            )
            expected = {
                SHOP_CATEGORY_COLUMN: server_row["shopCategoryId"],
                GROUP_ID_COLUMN: server_row["groupId"],
                STAGE_COLUMN: server_row["stage"],
                COST_ID_COLUMN: 40313,
                COST_AMOUNT_COLUMN: 1,
                EQUIPMENT_ID_COLUMN: equipment_id,
                MAX_LEVEL_COLUMN: server_row["enhancementMaxLevel"],
                REQUIRED_AWAKENING_COLUMN: server_row["requireAwakeningLevel"],
            }
            for column, value in expected.items():
                if client_row[column] != str(value):
                    raise ValueError(f"client row {shop_item_id} column {column} drifted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-store",
        type=Path,
        help="Writable hashed store; defaults to the active profile overlay store.",
    )
    args = parser.parse_args()

    profile = core.resolve_profile("cn")
    if profile is None:
        raise ValueError("CN profile is unavailable")
    source = core.load_table(LOGICAL_PATH, profile.store, profile.fallback)
    shop_document = json.loads(SHOP_JSON.read_text(encoding="utf-8"))
    output = build_client_table(source, shop_document)
    output_store = (args.output_store or profile.store).resolve()
    path = core.write_table(output, output_store, ".bak-wfmod-enhancement-13-stage")
    print(f"source: {source.source_path}")
    print(f"output: {path}")
    print(f"rows: {len(source.keys)} -> {len(output.keys)}")
    print("equipment 5010070/5020043: 13 stages, Pina crystal x1 per stage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
