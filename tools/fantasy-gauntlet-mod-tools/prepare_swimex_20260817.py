#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare the approved swimex0817 safe merge and the 139997 character package.

This importer is intentionally whitelist-based.  It consumes the audited logical
payload tree rather than installing the author's full-table archives, so unrelated
official balance, boss, shop and image rows cannot enter the live final state.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path


TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parent.parent
AUDIT_ROOT = Path(r"F:\codex\_inspect-wfshare-swimex0817e-20260817")
KNOWN_ROOT = AUDIT_ROOT / "package-logical-known"
INVENTORY_PATH = AUDIT_ROOT / "package-inventory.json"
OUTER_ZIP = Path(r"F:\wfshare-swimex0817e-1.4.347-to-1.4.348.zip")
OUTER_ZIP_SHA256 = "fca1282265605034fbb6fd87966ceed0492f5e08b2f62bdd13a054a540418e08"
SERVER_ROWS = (
    AUDIT_ROOT
    / "wfshare-1.4.347-to-1.4.348-full"
    / "server-data"
    / "swimex0817_rows.json"
)
STORE_ROOTS = {
    "common": REPO_ROOT / "assets/asset-patch/production/upload",
    "medium": REPO_ROOT / "assets/asset-patch/production/medium_upload",
    "android": REPO_ROOT / "assets/asset-patch/production/android_upload",
}
PENDING_PATH = TOOL_DIR / "work/sync_pending.json"
REPORT_PATH = TOOL_DIR / "work/swimex_20260817_prepare_report.json"
WORKSPACE_ROOT = TOOL_DIR / "work/character_packs/resistance_princess_ex_139997"
CHAR_PACKAGE = WORKSPACE_ROOT / "package"
CHAR_ID = "139997"
CHAR_CODE = "resistance_princess_ex"

sys.path.insert(0, str(TOOL_DIR))
import wf_character_workspace as character_workspace  # noqa: E402
import wf_mod_tool as core  # noqa: E402
import wf_quest_lib as quest_lib  # noqa: E402
import wf_store_materialize as materialize  # noqa: E402


class ImportError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def pkg_path(root: str, logical: str) -> Path:
    path = KNOWN_ROOT / root / Path(*logical.split("/"))
    if not path.is_file():
        raise ImportError(f"audited package payload is missing: {root}:{logical}")
    return path


def store_path(root: str, logical: str) -> Path:
    digest = core.sha1_path(logical)
    return STORE_ROOTS[root] / digest[:2] / digest[2:]


def pending_name(root: str, logical: str) -> str:
    digest = core.sha1_path(logical)
    prefix = {"common": "", "medium": "medium:", "android": "android:"}[root]
    return f"{prefix}{digest[:2]}/{digest[2:]}"


def raw_outer(raw: bytes, logical: str) -> tuple[list[str], list[bytes]]:
    table = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    return list(table.keys), list(table.rows)


def merge_outer_rows(
    current_raw: bytes,
    package_raw: bytes,
    logical: str,
    keys: list[str],
) -> bytes:
    current_keys, current_rows = raw_outer(current_raw, logical)
    package_keys, package_rows = raw_outer(package_raw, logical)
    package_map = dict(zip(package_keys, package_rows))
    positions = {key: index for index, key in enumerate(current_keys)}
    for key in keys:
        if key not in package_map:
            raise ImportError(f"package table lacks approved row: {logical}:{key}")
        if key in positions:
            current_rows[positions[key]] = package_map[key]
        else:
            positions[key] = len(current_keys)
            current_keys.append(key)
            current_rows.append(package_map[key])
    return core.build_orderedmap_raw_rows(
        core.OrderedMap(logical, current_keys, current_rows, Path("<safe-merge>"))
    )


def replace_compressed_text_row(
    table_raw: bytes,
    logical: str,
    key: str,
    text: str,
) -> bytes:
    keys, rows = raw_outer(table_raw, logical)
    try:
        index = keys.index(key)
    except ValueError as exc:
        raise ImportError(f"table lacks row to replace: {logical}:{key}") from exc
    rows[index] = zlib.compress(text.encode("utf-8"))
    return core.build_orderedmap_raw_rows(
        core.OrderedMap(logical, keys, rows, Path("<safe-merge>"))
    )


def detect_codec(raw: bytes, logical: str) -> str:
    try:
        core.read_orderedmap_file_from_bytes(raw)
    except Exception:
        raw_outer(raw, logical)
        return "raw_outer"
    return "flat"


def decode_row(raw: bytes, key: str) -> str:
    rows = core.read_orderedmap_file_from_bytes(raw)
    if key not in rows:
        raise ImportError(f"decoded table lacks row: {key}")
    return rows[key]


def csv_rows(text: str) -> list[list[str]]:
    if not text:
        return []
    return [row for row in csv.reader(io.StringIO(text)) if row]


def server_mana_nodes_from_client(
    raw: bytes,
    logical: str,
    character_id: str,
) -> dict[str, dict[str, dict[str, object]]]:
    """Convert one character's final client mana-board row for server use."""
    tree = quest_lib.parse_node(raw)
    character = tree.get(character_id) if isinstance(tree, dict) else None
    if not isinstance(character, dict):
        raise ImportError(f"client mana table lacks character row: {character_id}")

    converted: dict[str, dict[str, dict[str, object]]] = {}
    for board_id, chunks in character.items():
        if not isinstance(chunks, dict):
            raise ImportError(
                f"client mana board is not a map: {character_id}:{board_id}"
            )
        nodes: dict[str, dict[str, object]] = {}
        for chunk in chunks.values():
            if not isinstance(chunk, str):
                raise ImportError(
                    f"client mana chunk is not text: {character_id}:{board_id}"
                )
            for node in csv_rows(chunk):
                if len(node) < 7:
                    raise ImportError(
                        f"client mana node is incomplete: {character_id}:{board_id}"
                    )
                item_ids = [item.strip() for item in node[2].split(",")]
                item_costs = [cost.strip() for cost in node[3].split(",")]
                if len(item_ids) != len(item_costs):
                    raise ImportError(
                        f"client mana item columns differ: {character_id}:{node[0]}"
                    )
                if node[0] in nodes:
                    raise ImportError(
                        f"duplicate client mana node: {character_id}:{node[0]}"
                    )
                nodes[node[0]] = {
                    "items": {
                        item_id: int(item_cost)
                        for item_id, item_cost in zip(item_ids, item_costs)
                    },
                    "manaCost": int(node[4]),
                    "field1": node[1],
                    "field5": node[5],
                    "field6": node[6],
                }
        converted[str(board_id)] = nodes
    return converted


def write_store(
    root: str,
    logical: str,
    raw: bytes,
    pending: set[str],
    changes: list[dict[str, object]],
) -> None:
    target = store_path(root, logical)
    before = target.read_bytes() if target.is_file() else None
    changed = before != raw
    if changed:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        pending.add(pending_name(root, logical))
    changes.append({
        "root": root,
        "logical_path": logical,
        "changed": changed,
        "before_sha256": hashlib.sha256(before).hexdigest() if before is not None else None,
        "after_sha256": hashlib.sha256(raw).hexdigest(),
        "size": len(raw),
    })


def copy_package_to_store(
    root: str,
    logical: str,
    pending: set[str],
    changes: list[dict[str, object]],
) -> None:
    write_store(root, logical, pkg_path(root, logical).read_bytes(), pending, changes)


def merge_store_table(
    logical: str,
    keys: list[str],
    pending: set[str],
    changes: list[dict[str, object]],
) -> None:
    target = store_path("common", logical)
    if not target.is_file():
        raise ImportError(f"current overlay lacks required table: {logical}")
    merged = merge_outer_rows(
        target.read_bytes(), pkg_path("common", logical).read_bytes(), logical, keys
    )
    write_store("common", logical, merged, pending, changes)


def current_full_table(logical: str) -> bytes:
    """Read the effective 1.4.78 table, including tables absent from the overlay."""
    target = store_path("common", logical)
    if target.is_file():
        return target.read_bytes()
    plan = materialize._build_plan(
        Path(r"F:\startpoint-cn-main\.cdn\cn"), REPO_ROOT, "1.4.78", False
    )
    digest = core.sha1_path(logical)
    relative = f"{digest[:2]}/{digest[2:]}"
    try:
        entry = plan.entries[("common", relative)]
    except KeyError as exc:
        raise ImportError(f"effective CDN chain lacks required table: {logical}") from exc
    with zipfile.ZipFile(entry.zip_path) as archive:
        return archive.read(entry.name)


def apply_white_wolf_ability_filter(
    pending: set[str], changes: list[dict[str, object]]
) -> dict[str, object]:
    logical = "master/ability/ability.orderedmap"
    current_raw = store_path("common", logical).read_bytes()
    package_raw = pkg_path("common", logical).read_bytes()
    current = core.read_orderedmap_file_from_bytes(current_raw)
    package = core.read_orderedmap_file_from_bytes(package_raw)

    current_a1 = csv_rows(current["1499991"])
    package_a1 = csv_rows(package["1499991"])
    if (current_a1[5][51:53], package_a1[5][51:53]) != (
        ["50000", "50000"], ["100000", "100000"]
    ):
        raise ImportError("white-wolf ability 1 exclusion precondition drifted")

    current_a3 = csv_rows(current["1499993"])
    package_a3 = csv_rows(package["1499993"])
    if len(current_a3) != 6 or len(package_a3) != 6:
        raise ImportError("white-wolf ability 3 must have exactly six effect rows")
    current_position_flags = [row[1] for row in current_a3]
    if current_position_flags not in (["true"] * 6, ["false"] * 6):
        raise ImportError("white-wolf live ability 3 has a mixed/unknown position state")
    if [row[1] for row in package_a3] != ["false"] * 6:
        raise ImportError("white-wolf package ability 3 is no longer six main-only rows")
    expected_pairs = {
        0: (["1000000", "1000000"], ["4000000", "4000000"]),
        1: (["3000", "3000"], ["10000", "10000"]),
        5: (["8000", "8000"], ["20000", "20000"]),
    }
    for row_index, (live_values, package_values) in expected_pairs.items():
        if current_a3[row_index][51:53] != live_values:
            raise ImportError(f"white-wolf live numeric exclusion drifted at row {row_index + 1}")
        if package_a3[row_index][51:53] != package_values:
            raise ImportError(f"white-wolf package numeric boost drifted at row {row_index + 1}")
        package_a3[row_index][51:53] = live_values

    merged = merge_outer_rows(
        current_raw,
        package_raw,
        logical,
        ["1310201", "1310202", "1310203"],
    )
    merged = replace_compressed_text_row(
        merged, logical, "1499993", core.write_csv_lines(package_a3)
    )
    # Deliberately do not replace 1499991: this keeps the 50% gauge row byte-for-byte.
    write_store("common", logical, merged, pending, changes)
    after = core.read_orderedmap_file_from_bytes(merged)
    after_a3 = csv_rows(after["1499993"])
    if [row[1] for row in after_a3] != ["false"] * 6:
        raise ImportError("white-wolf ability 3 main-only readback failed")
    for row_index, (live_values, _package_values) in expected_pairs.items():
        if after_a3[row_index][51:53] != live_values:
            raise ImportError("white-wolf excluded numeric boost leaked into final table")
    if after["1499991"] != current["1499991"]:
        raise ImportError("white-wolf ability 1 changed despite explicit exclusion")
    return {
        "ability_1_gauge_kept": "50%",
        "ability_3_main_only_rows": 6,
        "ability_3_kept_values": ["1000%", "3%", "8%"],
    }


def character_code_map() -> dict[str, str]:
    logical = "master/character/character.orderedmap"
    rows = core.read_orderedmap_file_from_bytes(pkg_path("common", logical).read_bytes())
    result: dict[str, str] = {}
    for character_id in (
        "129999", "139997", "139998", "139999", "149998", "149999",
        "169998", "169999", "179999",
    ):
        parsed = csv_rows(rows[character_id])
        if len(parsed) != 1 or not parsed[0][0]:
            raise ImportError(f"cannot derive code name for image whitelist ID {character_id}")
        result[character_id] = parsed[0][0]
    return result


def apply_general_client() -> tuple[set[str], list[dict[str, object]], dict[str, object]]:
    pending: set[str] = set()
    changes: list[dict[str, object]] = []
    assertions: dict[str, object] = {}

    assertions["white_wolf"] = apply_white_wolf_ability_filter(pending, changes)
    # 夏日雷龙的六能力整组按包接收。
    merge_store_table(
        "master/ability/ability.orderedmap",
        [f"139998{index}" for index in range(1, 7)],
        pending,
        changes,
    )
    merge_store_table(
        "master/ability/leader_ability.orderedmap",
        ["131020", "149999", "139998"],
        pending,
        changes,
    )
    merge_store_table(
        "master/character/character_speech.orderedmap",
        ["149999", "139998"],
        pending,
        changes,
    )

    # Deep-abyss pool: row merge for shared tables, whole-file copy for pool-private odds.
    feature_logical = "master/gacha/gacha_feature_content.orderedmap"
    feature_before_keys, feature_before_rows = raw_outer(
        store_path("common", feature_logical).read_bytes(), feature_logical
    )
    feature_before = dict(zip(feature_before_keys, feature_before_rows))
    preserved_1615 = feature_before.get("1615")
    if preserved_1615 is None:
        raise ImportError("live gacha_feature_content lacks protected key 1615")
    merge_store_table("master/gacha/gacha.orderedmap", ["990001"], pending, changes)
    merge_store_table(feature_logical, ["990001"], pending, changes)
    feature_after_keys, feature_after_rows = raw_outer(
        store_path("common", feature_logical).read_bytes(), feature_logical
    )
    feature_after = dict(zip(feature_after_keys, feature_after_rows))
    if feature_after.get("1615") != preserved_1615:
        raise ImportError("protected gacha_feature_content[1615] changed")
    assertions["gacha_feature_content_1615_preserved"] = True
    merge_store_table(
        "master/item/item.orderedmap", ["999013", "999014"], pending, changes
    )
    merge_store_table(
        "master/shop/event_item_shop.orderedmap",
        ["9700116", "9700117"],
        pending,
        changes,
    )
    merge_store_table(
        "master/rich_text/rich_text_html.orderedmap",
        ["rich_text/cnmod_abyss_limited_gacha_note"],
        pending,
        changes,
    )
    for logical in (
        "master/gacha_odds/cnmod_abyss_limited_gacha_character_3.orderedmap",
        "master/gacha_odds/cnmod_abyss_limited_gacha_character_4.orderedmap",
        "master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap",
        "master/gacha_odds/cnmod_abyss_limited_gacha_rarity.orderedmap",
    ):
        copy_package_to_store("common", logical, pending, changes)
    for root, logical in (
        ("common", "dynamic/gacha_banner/cnmod_abyss_limited_gacha"),
        ("medium", "dynamic/gacha_banner/cnmod_abyss_limited_gacha.png"),
        ("common", "dynamic/gacha_list_banner/cnmod_abyss_limited_gacha"),
        ("common", "dynamic/gacha_list_banner/cnmod_abyss_limited_gacha.png"),
        ("common", "rich_text/cnmod_abyss_limited_gacha_note.html.deflate"),
        ("common", "item/sprite_sheet.atlas.amf3.deflate"),
        ("common", "item/sprite_sheet.png"),
    ):
        copy_package_to_store(root, logical, pending, changes)

    # Regis active-skill terminal uses the actual package row (680/680 and 680/630)
    # and the two package DSLs; no value is invented from the prose checklist.
    action_logical = "master/skill/action_skill.orderedmap"
    # The author's action_skill rows decode identically to the current terminal
    # (Regis remains 680/680 and 680/630).  Do not publish recompression-only row
    # changes; the actual active-skill reinforcement is carried by the two DSLs.
    for code in ("rec_android_1anv", "cnmod_thunder_dragon_ascendant"):
        for form in (1, 2):
            logical = (
                f"battle/action/skill/action/rare5/{code}${code}_{form}"
                ".action.dsl.amf3.deflate"
            )
            copy_package_to_store("common", logical, pending, changes)

    # Summer thunder dragon is accepted as a complete package-owned character.
    thunder_specs = {
        "master/character/character.orderedmap": ["139998"],
        "master/character/character_text.orderedmap": ["139998"],
        "master/character/character_gacha_sound.orderedmap": ["139998"],
        "master/character/unique_condition.orderedmap": ["139998"],
        "master/generated/character_image.orderedmap": ["139998"],
        "master/generated/mana_board.orderedmap": ["139998"],
        "master/mana_board/mana_node.orderedmap": ["139998"],
        "master/mana_board/upskill.orderedmap": ["139998"],
        "master/skill_preview/skill_preview_character.orderedmap": ["139998"],
        "master/character/full_shot_image_attribute.orderedmap": ["139998"],
        "master/mana_board/mana_board2_open_condition.orderedmap": ["139998"],
        "master/stance_detail/character_stance_detail.orderedmap": ["139998"],
        "master/character/character_status.orderedmap": ["139998"],
    }
    for logical, keys in thunder_specs.items():
        merge_store_table(logical, keys, pending, changes)

    codes = character_code_map()
    general_image_ids = [
        "129999", "139998", "139999", "149998", "149999", "169998",
        "169999", "179999",
    ]
    merge_store_table(
        "master/generated/character_image.orderedmap",
        general_image_ids,
        pending,
        changes,
    )
    merge_store_table(
        "master/character/full_shot_image_attribute.orderedmap",
        general_image_ids,
        pending,
        changes,
    )
    trim_keys = [
        f"character/{codes[character_id]}/ui/full_shot_1440_1920_{form}"
        for character_id in general_image_ids
        for form in (0, 1)
    ]
    # The accepted full thunder role also owns its skill-cutin trim rows.
    trim_keys.extend([
        f"character/{codes['139998']}/ui/skill_cutin_0",
        f"character/{codes['139998']}/ui/skill_cutin_1",
    ])
    merge_store_table(
        "master/generated/trimmed_image.orderedmap", trim_keys, pending, changes
    )
    for character_id in general_image_ids:
        code = codes[character_id]
        for form in (0, 1):
            copy_package_to_store(
                "medium",
                f"character/{code}/ui/full_shot_1440_1920_{form}.png",
                pending,
                changes,
            )
        copy_package_to_store(
            "medium",
            f"character/{code}/ui/illustration_setting_sprite_sheet.png",
            pending,
            changes,
        )
        copy_package_to_store(
            "common",
            f"character/{code}/ui/illustration_setting_sprite_sheet.atlas.amf3.deflate",
            pending,
            changes,
        )

    # Copy every mapped package-owned summer-thunder resource.  Identical resources
    # remain out of pending automatically, while any real package difference is kept.
    thunder_code = codes["139998"]
    for root in ("common", "medium", "android"):
        base = KNOWN_ROOT / root
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            logical = path.relative_to(base).as_posix()
            if (
                logical.startswith(f"character/{thunder_code}/")
                or thunder_code in logical and logical.startswith("battle/")
            ):
                copy_package_to_store(root, logical, pending, changes)

    # Story/word fragments are intentionally outside the formal character-package
    # schema, so they are published in this general patch exactly as the package ships.
    words_root = KNOWN_ROOT / "common" / f"character/{CHAR_CODE}/voice/words"
    word_count = 0
    for path in sorted(words_root.glob("*.mp3")):
        logical = path.relative_to(KNOWN_ROOT / "common").as_posix()
        copy_package_to_store("common", logical, pending, changes)
        word_count += 1
    if word_count != 87:
        raise ImportError(f"expected 87 EX word voices, found {word_count}")
    assertions["ex_word_voice_count_general_patch"] = word_count
    assertions["image_whitelist_ids"] = general_image_ids + [CHAR_ID]
    return pending, changes, assertions


def pending_against_effective_chain(
    changes: list[dict[str, object]],
) -> set[str]:
    """Recompute pending against the published 1.4.78 chain, not prior script runs."""
    plan = materialize._build_plan(
        Path(r"F:\startpoint-cn-main\.cdn\cn"), REPO_ROOT, "1.4.78", False
    )
    archive_cache: dict[Path, zipfile.ZipFile] = {}
    pending: set[str] = set()
    seen: set[tuple[str, str]] = set()
    try:
        for item in changes:
            root = str(item["root"])
            logical = str(item["logical_path"])
            marker = (root, logical)
            if marker in seen:
                continue
            seen.add(marker)
            digest = core.sha1_path(logical)
            relative = f"{digest[:2]}/{digest[2:]}"
            entry = plan.entries.get((root, relative))
            baseline = None
            if entry is not None:
                archive = archive_cache.get(entry.zip_path)
                if archive is None:
                    archive = zipfile.ZipFile(entry.zip_path)
                    archive_cache[entry.zip_path] = archive
                baseline = archive.read(entry.name)
            target = store_path(root, logical)
            if not target.is_file():
                raise ImportError(f"approved target vanished before pending audit: {root}:{logical}")
            if target.read_bytes() != baseline:
                pending.add(pending_name(root, logical))
    finally:
        for archive in archive_cache.values():
            archive.close()
    return pending


def deep_upsert(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_upsert(target[key], value)
        else:
            target[key] = value


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ImportError(f"JSON root must be an object: {path}")
    return value


def write_json_if_changed(path: Path, value: dict, changes: list[dict[str, object]]) -> None:
    # Match each legacy server table's established formatting so a two-row upsert
    # does not create a repository-wide whitespace diff.
    if path.name == "event_item_shop.json":
        raw = (json.dumps(value, ensure_ascii=False, indent=4) + "\n").encode("utf-8")
    elif path.name in {"gacha.json", "gacha_cnmod.json"} \
            and path.parent.name == "assets":
        raw = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    else:
        raw = canonical_json(value)
    before = path.read_bytes()
    changed = before != raw
    if changed:
        path.write_bytes(raw)
    changes.append({
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "changed": changed,
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(raw).hexdigest(),
    })


def apply_general_server() -> list[dict[str, object]]:
    rows = load_json(SERVER_ROWS)
    changes: list[dict[str, object]] = []
    specs = {
        "character.json": {"139998": rows["character.json"]["139998"]},
        "cdndata/character.json": {
            "139998": rows["cdndata/character.json"]["139998"]
        },
        "cdndata/character_text.json": {
            "139998": rows["cdndata/character_text.json"]["139998"]
        },
        "gacha.json": {"990001": rows["gacha.json"]["990001"]},
        # Runtime lookup overlays gacha_cnmod.json on top of gacha.json, so the
        # accepted whole abyss pool must be terminal in both authorities.
        "gacha_cnmod.json": {"990001": rows["gacha.json"]["990001"]},
        "cdndata/gacha.json": {
            "990001": rows["cdndata/gacha.json"]["990001"]
        },
        "cdndata/gacha_feature_content.json": {
            "990001": rows["cdndata/gacha_feature_content.json"]["990001"]
        },
        "event_item_shop.json": rows["event_item_shop.json"],
    }
    for relative, updates in specs.items():
        path = REPO_ROOT / "assets" / Path(*relative.split("/"))
        value = load_json(path)
        protected_1615 = None
        if relative == "cdndata/gacha_feature_content.json":
            protected_1615 = json.dumps(value.get("1615"), ensure_ascii=False, sort_keys=True)
            if protected_1615 == "null":
                raise ImportError("server gacha_feature_content lacks protected key 1615")
        deep_upsert(value, updates)
        if relative == "cdndata/gacha_feature_content.json":
            after_1615 = json.dumps(value.get("1615"), ensure_ascii=False, sort_keys=True)
            if after_1615 != protected_1615:
                raise ImportError("server gacha_feature_content[1615] changed")
        write_json_if_changed(path, value, changes)
    return changes


def copy_char_payload(root: str, logical: str) -> None:
    source = pkg_path(root, logical)
    target = CHAR_PACKAGE / "roots" / root / Path(*logical.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def build_char_table(
    logical: str,
    keys: list[str],
    codec_id: str | None = None,
) -> tuple[str, bytes]:
    package_raw = pkg_path("common", logical).read_bytes()
    base_raw = current_full_table(logical)
    actual_codec = codec_id or detect_codec(package_raw, logical)
    if actual_codec == "action_nested":
        merged = merge_outer_rows(base_raw, package_raw, logical, keys)
    elif actual_codec in {"flat", "raw_outer"}:
        detected = detect_codec(package_raw, logical)
        if detected != actual_codec:
            raise ImportError(
                f"table codec mismatch for {logical}: expected {actual_codec}, got {detected}"
            )
        merged = merge_outer_rows(base_raw, package_raw, logical, keys)
    else:
        raise ImportError(f"unsupported character table codec: {actual_codec}")
    return actual_codec, merged


def package_file_entries() -> dict[str, list[dict[str, object]]]:
    roots: dict[str, list[dict[str, object]]] = {
        "common": [], "medium": [], "android": [], "server": []
    }
    for root in roots:
        base = CHAR_PACKAGE / "roots" / root
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            logical = path.relative_to(base).as_posix()
            roots[root].append({
                "logical_path": logical,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            })
    return roots


def prepare_character_package() -> dict[str, object]:
    if WORKSPACE_ROOT.resolve() != (
        TOOL_DIR / "work/character_packs/resistance_princess_ex_139997"
    ).resolve():
        raise ImportError("character workspace path identity check failed")
    if not (WORKSPACE_ROOT / "workspace.json").is_file():
        raise ImportError("formal character workspace was not initialized")

    # Character-owned assets: 37 mandatory files, 21 ally/battle/home voices, skill/PF
    # programs, unique-condition icon, and every mapped EX effect resource.
    for root in ("common", "medium", "android"):
        base = KNOWN_ROOT / root
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            logical = path.relative_to(base).as_posix()
            include = logical.startswith(f"character/{CHAR_CODE}/")
            if "/voice/words/" in f"/{logical}":
                include = False
            if (
                CHAR_CODE in logical
                and logical.startswith(("battle/action/", "battle/effect/"))
            ):
                include = True
            if logical == "battle/common/unique_condition/unique_swim_ex_blade_ring.png":
                include = True
            if include:
                copy_char_payload(root, logical)

    table_specs: list[tuple[str, list[str], str | None]] = [
        ("master/ability/ability.orderedmap", [f"139997{i}" for i in range(1, 7)], "flat"),
        ("master/ability/leader_ability.orderedmap", [CHAR_ID], "flat"),
        ("master/character/character.orderedmap", [CHAR_ID], "flat"),
        ("master/character/character_text.orderedmap", [CHAR_ID], "flat"),
        ("master/character/character_speech.orderedmap", [CHAR_ID], "flat"),
        ("master/character/character_gacha_sound.orderedmap", [CHAR_ID], "raw_outer"),
        ("master/character/unique_condition.orderedmap", [CHAR_ID], "flat"),
        ("master/generated/character_image.orderedmap", [CHAR_ID], "raw_outer"),
        ("master/generated/mana_board.orderedmap", [CHAR_ID], "raw_outer"),
        ("master/mana_board/mana_node.orderedmap", [CHAR_ID], "raw_outer"),
        ("master/mana_board/upskill.orderedmap", [CHAR_ID], "flat"),
        ("master/skill_preview/skill_preview_character.orderedmap", [CHAR_ID], "flat"),
        ("master/character/full_shot_image_attribute.orderedmap", [CHAR_ID], "raw_outer"),
        ("master/mana_board/mana_board2_open_condition.orderedmap", [CHAR_ID], "flat"),
        ("master/stance_detail/character_stance_detail.orderedmap", [CHAR_ID], "flat"),
        ("master/character/character_status.orderedmap", [CHAR_ID], "raw_outer"),
        ("master/skill/action_skill.orderedmap", [CHAR_CODE], "action_nested"),
    ]
    trim_logical = "master/generated/trimmed_image.orderedmap"
    trim_package = core.read_orderedmap_file_from_bytes(pkg_path("common", trim_logical).read_bytes())
    trim_keys = sorted(key for key in trim_package if key.startswith(f"character/{CHAR_CODE}/"))
    if trim_keys != [
        f"character/{CHAR_CODE}/ui/full_shot_1440_1920_0",
        f"character/{CHAR_CODE}/ui/full_shot_1440_1920_1",
        f"character/{CHAR_CODE}/ui/skill_cutin_0",
        f"character/{CHAR_CODE}/ui/skill_cutin_1",
    ]:
        raise ImportError(f"unexpected EX trimmed-image ownership: {trim_keys}")
    table_specs.append((trim_logical, trim_keys, "flat"))

    tables: list[dict[str, object]] = []
    for logical, keys, codec in table_specs:
        codec_id, raw = build_char_table(logical, keys, codec)
        target = CHAR_PACKAGE / "roots/common" / Path(*logical.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        inner_keys: list[dict[str, object]] = []
        if codec_id == "action_nested":
            outer = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
            outer_map = dict(zip(outer.keys, outer.rows))
            inner = core.read_orderedmap_file_from_bytes(outer_map[CHAR_CODE])
            inner_keys = [{"outer_key": CHAR_CODE, "keys": list(inner)}]
        tables.append({
            "root": "common",
            "logical_path": logical,
            "codec_id": codec_id,
            "outer_keys": keys,
            "inner_keys": inner_keys,
            "semantic_claims": [],
        })

    # The source archive ships the three PF programs but omitted their dispatch row.
    # Add the minimal row required by leader ability 722; preserve the effective chain.
    pf_logical = "master/skill/power_flip_action.orderedmap"
    pf_base = current_full_table(pf_logical)
    pf_rows = core.read_orderedmap_file_from_bytes(pf_base)
    pf_key = f"{CHAR_CODE}_pf"
    pf_expected = ",".join(
        f"battle/action/power_flip/action/override/{pf_key}${pf_key}_lv{level}"
        for level in (1, 2, 3)
    )
    base_order = list(core.read_orderedmap_file_from_bytes(pf_base))
    if pf_key in pf_rows:
        if pf_rows[pf_key] != pf_expected:
            raise ImportError(f"power-flip dispatch row drifted: {pf_key}")
        pf_order = base_order
    else:
        pf_order = base_order + [pf_key]
    pf_rows[pf_key] = pf_expected
    pf_table = core.OrderedMap(
        pf_logical,
        pf_order,
        [pf_rows[key].encode("utf-8") for key in pf_order],
        Path("<safe-merge>"),
    )
    pf_raw = core.build_orderedmap(pf_table)
    pf_target = CHAR_PACKAGE / "roots/common" / Path(*pf_logical.split("/"))
    pf_target.parent.mkdir(parents=True, exist_ok=True)
    pf_target.write_bytes(pf_raw)
    tables.append({
        "root": "common",
        "logical_path": pf_logical,
        "codec_id": "flat",
        "outer_keys": [pf_key],
        "inner_keys": [],
        "semantic_claims": [],
    })

    # The leader-ability row also references a custom description ID that the
    # source archive omitted.  PowerFlipOverride reads the flat custom-ability
    # string table (not the nested power-up-by-level table), so preserve every
    # existing compressed row and append exactly one flat description row.
    description_logical = "master/string/custom_ability_string.orderedmap"
    description_key = f"override_string_{CHAR_CODE}"
    description_text = "赋予强化弹射特殊强化效果"
    description_base = current_full_table(description_logical)
    description_outer = core.read_orderedmap_raw_rows_from_bytes(
        description_base, description_logical
    )
    description_keys = list(description_outer.keys)
    description_rows = list(description_outer.rows)
    description_row = zlib.compress(description_text.encode("utf-8"))
    if description_key in description_keys:
        description_index = description_keys.index(description_key)
        if zlib.decompress(description_rows[description_index]).decode("utf-8") != description_text:
            raise ImportError(
                f"power-flip description row drifted: {description_key}"
            )
        description_rows[description_index] = description_row
    else:
        description_keys.append(description_key)
        description_rows.append(description_row)
    description_raw = core.build_orderedmap_raw_rows(
        core.OrderedMap(
            description_logical,
            description_keys,
            description_rows,
            Path("<safe-merge>"),
        )
    )
    description_target = (
        CHAR_PACKAGE / "roots/common" / Path(*description_logical.split("/"))
    )
    description_target.parent.mkdir(parents=True, exist_ok=True)
    description_target.write_bytes(description_raw)
    description_verified_outer = core.read_orderedmap_raw_rows_from_bytes(
        description_raw, description_logical
    )
    description_verified = zlib.decompress(
        description_verified_outer.rows[
            description_verified_outer.keys.index(description_key)
        ]
    ).decode("utf-8")
    if description_verified != description_text:
        raise ImportError("power-flip description table failed round-trip verification")
    tables.append({
        "root": "common",
        "logical_path": description_logical,
        "codec_id": "flat",
        "outer_keys": [description_key],
        "inner_keys": [],
        "semantic_claims": [],
    })

    # Four exact server-layer tables, corrected from the client terminal rows rather
    # than the stale light-element text bundled in server-data.
    server_rows = load_json(SERVER_ROWS)
    character_text_logical = "master/character/character_text.orderedmap"
    character_logical = "master/character/character.orderedmap"
    client_text = decode_row(pkg_path("common", character_text_logical).read_bytes(), CHAR_ID)
    client_character = decode_row(pkg_path("common", character_logical).read_bytes(), CHAR_ID)
    text_rows = csv_rows(client_text)
    character_rows = csv_rows(client_character)
    if len(text_rows) != 1 or len(character_rows) != 1:
        raise ImportError("EX client character/text row is not a single CSV record")
    if text_rows[0][3] != "雷雨的夏日公主":
        raise ImportError("EX title correction is missing from client terminal row")
    if text_rows[0][4] != "雷潮加冕·环刃变生":
        raise ImportError("EX skill-name correction is missing from client terminal row")
    if character_rows[0][18] != "背水雷冠·女王凯歌":
        raise ImportError("EX leader-title correction is missing from client terminal row")

    server_values = {
        "cdndata/character.json": load_json(REPO_ROOT / "assets/cdndata/character.json"),
        "cdndata/character_text.json": load_json(
            REPO_ROOT / "assets/cdndata/character_text.json"
        ),
        "character.json": load_json(REPO_ROOT / "assets/character.json"),
        "mana_node.json": load_json(REPO_ROOT / "assets/mana_node.json"),
    }
    server_values["cdndata/character.json"][CHAR_ID] = [character_rows[0]]
    server_values["cdndata/character_text.json"][CHAR_ID] = [text_rows[0]]
    server_values["character.json"][CHAR_ID] = server_rows["character.json"][CHAR_ID]
    mana_logical = "master/mana_board/mana_node.orderedmap"
    client_mana_nodes = server_mana_nodes_from_client(
        pkg_path("common", mana_logical).read_bytes(),
        mana_logical,
        CHAR_ID,
    )
    if sum(len(nodes) for nodes in client_mana_nodes.values()) != 41:
        raise ImportError("EX client mana table does not contain exactly 41 nodes")
    server_values["mana_node.json"][CHAR_ID] = client_mana_nodes
    for logical, value in server_values.items():
        target = CHAR_PACKAGE / "roots/server" / Path(*logical.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(canonical_json(value))
        tables.append({
            "root": "server",
            "logical_path": logical,
            "codec_id": "json_object",
            "outer_keys": [CHAR_ID],
            "inner_keys": [],
            "semantic_claims": [],
        })

    roots = package_file_entries()
    manifest = {
        "schema_version": 1,
        "package_id": "resistance_princess_ex_139997",
        "character_id": 139997,
        "code_name": CHAR_CODE,
        "package_version": "1.0.1",
        "requires_client_base": "1.4.79",
        "required_capabilities": [],
        "roots": roots,
        "tables": sorted(tables, key=lambda item: (str(item["root"]), str(item["logical_path"]))),
        "skills": {
            "skill_program_forms": 2,
            "power_flip_override_levels": 3,
        },
        "unique_condition": {
            "id": 139997,
            "icon": "battle/common/unique_condition/unique_swim_ex_blade_ring.png",
        },
        "qa": {
            "delivery_mode": "production",
            "release_ready": True,
            "required_assets_total": 37,
            "required_assets_present": 37,
            "workspace_input_sha256": "0" * 64,
        },
        "snapshot": {
            "source_outer_zip_sha256": OUTER_ZIP_SHA256,
            "author_package_version": "1.4.347-to-1.4.348",
            "safe_merge_scope": "swimex0817-approved-whitelist",
        },
    }
    (CHAR_PACKAGE / "manifest.json").write_bytes(canonical_json(manifest))
    sealed = character_workspace.seal_workspace(WORKSPACE_ROOT)
    if not sealed.release_ready:
        raise ImportError("formal EX workspace did not seal as release-ready")
    if sealed.requirement_report.get("required_present") != 37:
        raise ImportError("formal EX workspace is not 37/37")

    voice_count = sum(
        1
        for item in roots["common"]
        if str(item["logical_path"]).startswith(f"character/{CHAR_CODE}/voice/")
    )
    if voice_count != 21:
        raise ImportError(f"expected 21 formal EX voices, found {voice_count}")
    return {
        "workspace": str(WORKSPACE_ROOT),
        "release_ready": sealed.release_ready,
        "required_assets": "37/37",
        "formal_voice_count": voice_count,
        "table_claim_count": len(tables),
        "root_counts": {root: len(entries) for root, entries in roots.items()},
        "input_digest": sealed.input_digest,
    }


def validate_inventory() -> dict[str, object]:
    inventory = load_json(INVENTORY_PATH)
    if inventory.get("total") != 355 or inventory.get("mapped") != 337:
        raise ImportError("audited package inventory totals drifted")
    if inventory.get("unmapped") != 18:
        raise ImportError("audited package unmapped count drifted")
    unmapped = [item for item in inventory["records"] if not item.get("logical_paths")]
    if len(unmapped) != 18 or any(item.get("root") != "medium" for item in unmapped):
        raise ImportError("unmapped payload classification drifted")
    return {
        "total": 355,
        "mapped": 337,
        "excluded_unmapped": 18,
        "excluded_reason": "15 abyss weapon icons, 2 official illustration sheets, 1 tiny mask",
    }


def main() -> int:
    if not OUTER_ZIP.is_file():
        raise ImportError(f"source archive is missing: {OUTER_ZIP}")
    actual_zip_hash = sha256_file(OUTER_ZIP)
    if actual_zip_hash.lower() != OUTER_ZIP_SHA256:
        raise ImportError(
            f"source archive SHA256 mismatch: expected {OUTER_ZIP_SHA256}, got {actual_zip_hash}"
        )
    inventory_report = validate_inventory()
    old_pending = []
    if PENDING_PATH.is_file():
        value = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
        if isinstance(value, list):
            old_pending = value

    _write_pending, client_changes, assertions = apply_general_client()
    pending = pending_against_effective_chain(client_changes)
    server_changes = apply_general_server()
    for item in client_changes:
        item["differs_from_effective_1_4_78"] = (
            pending_name(str(item["root"]), str(item["logical_path"])) in pending
        )
    for item in server_changes:
        relative = str(item["path"])
        try:
            head_raw = subprocess.check_output(
                ["git", "show", f"HEAD:{relative}"], cwd=REPO_ROOT
            )
        except subprocess.CalledProcessError as exc:
            raise ImportError(f"cannot audit server file against git HEAD: {relative}") from exc
        item["differs_from_git_head"] = (
            (REPO_ROOT / Path(*relative.split("/"))).read_bytes() != head_raw
        )
    character_report = prepare_character_package()
    pending_list = sorted(pending)
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(
        json.dumps(pending_list, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "source_archive": str(OUTER_ZIP),
        "source_sha256": actual_zip_hash,
        "inventory": inventory_report,
        "general_client": {
            "pending_count": len(pending_list),
            "changed_count": len(pending_list),
            "examined_count": len(client_changes),
            "changes": client_changes,
            "assertions": assertions,
        },
        "general_server": {
            "changed_count": sum(
                bool(item["differs_from_git_head"]) for item in server_changes
            ),
            "changes": server_changes,
        },
        "character_package": character_report,
        "pending_replaced": {
            "before": old_pending,
            "after": pending_list,
            "reason": "publish only the approved swimex whitelist",
        },
        "explicit_exclusions": [
            "white-wolf ability 1 gauge 50%->100%",
            "white-wolf ability 3 1000%->4000%",
            "white-wolf ability 3 3%->10%",
            "white-wolf ability 3 8%->20%",
            "official/global balance rows",
            "white-tiger row 10 and boss HP history",
            "official image IDs 700016 and 111002",
            "unrelated item/shop/current-gacha mappings",
        ],
    }
    REPORT_PATH.write_bytes(canonical_json(report))
    print(json.dumps({
        "ok": True,
        "general_pending": len(pending_list),
        "server_files_changed": report["general_server"]["changed_count"],
        "character_release_ready": character_report["release_ready"],
        "character_required_assets": character_report["required_assets"],
        "report": str(REPORT_PATH),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, IndexError, zlib.error, ImportError) as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        raise SystemExit(2)
