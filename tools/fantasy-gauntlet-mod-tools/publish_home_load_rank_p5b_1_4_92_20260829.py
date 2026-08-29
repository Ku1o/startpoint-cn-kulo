#!/usr/bin/env python3
"""Publish the home-load fix and reviewed rank-P5B content as one 1.4.92 edge.

The shared bundle was built against an unrelated 1.4.353+ chain and contains
many tables that also carry other authors' rows.  This publisher therefore
copies target-specific resources, but grafts only explicitly approved rows
onto this repository's real 1.4.91 terminal tables.  It also removes only
feature-banner row 10010, preserving the already accepted 46.5% load fix in
the same release.  Untouched rows retain their original compressed bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import struct
import sys
import zipfile
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

import wf_mod_tool as core
import wf_store_materialize as store
import wf_abyss_gacha_contract as abyss_gacha_contract
import wf_abyss_gacha_pool as abyss_gacha_pool
import wf_assets
import wf_dsl


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE_ROOT = Path(r"F:\codex\reviews\wf-rank-p5b-gray-20260829")
BASE_VERSION = "1.4.91"
PATCH_VERSION = "1.4.92"
PATCH_ID = "home-load-rank-p5b-1.4.92"
REPLACED_PATCH_ID = "feature-banner-10010-home-load-hotfix-1.4.92"
ARCHIVE_STEM = "pinball-1.4.91-1.4.92"
ARCHIVE_SUFFIX = "0829-home-load-rank-p5b"
MAX_RAW_ARCHIVE_BYTES = 18 * 1024 * 1024
FIXED_ZIP_TIME = (2026, 8, 29, 18, 0, 0)
ROOT_FOLDERS = {
    "common": "upload",
    "medium": "medium_upload",
    "android": "android_upload",
}
TARGET_CHARACTER_IDS = (169980, 169994, 169995, 179981)
TARGET_CODE_NAMES = (
    "abyss_beast_playable",
    "white_tiger_ghost_playable",
    "maou2_playable",
    "cnmod_epuration_empress",
)
TARGET_DEGREES = (9900002, 9900003, 9900004, 9900005, 9900006)
TARGET_ITEMS = (999015, 999016)
ITEM_SHEET_LOGICAL = "item/sprite_sheet.png"
ITEM_ATLAS_LOGICAL = "item/sprite_sheet.atlas.amf3.deflate"
TICKET_ICON_NAMES = (
    "item/spends/tickets/ashen_verdict_once_gacha_character_ticket",
    "item/spends/tickets/ashen_verdict_ten_times_gacha_character_ticket",
)
TICKET_FULL_ASSET_SHA256 = {
    ITEM_SHEET_LOGICAL: "0f3c6d7c356196c688cb914eb7e8a85cd32506f72a86a361e5dffc25d2852b92",
    ITEM_ATLAS_LOGICAL: "c9ede674ccbf3da1f4403734e909a3407afbf7f10dc4f2c35f631f2c89ea1b01",
}
TARGET_SHOP_ROWS = (9700118,)
TARGET_GACHA_ROWS = (990002,)
TARGET_RICH_TEXT_ROWS = ("rich_text/cnmod_ashen_verdict_gacha_note",)
CHARACTER_ASSERTION_PREFIX = "boss-character-package-"
GACHA_ASSERTION_ID = "gacha-990002-client"
FEATURE_BANNER_LOGICAL = "master/feature_banner/feature_banner.orderedmap"
REMOVED_FEATURE_BANNER_ID = "10010"
ABILITY_LOGICAL = "master/ability/ability.orderedmap"
ABILITY_RESTORE_ARCHIVE = (
    "pinball-1.4.87-1.4.88-1-0825-integrated-ginovi-spgirl-trio-rogue.zip"
)
ABILITY_RESTORE_PAYLOAD_SHA256 = (
    "85206e103d5916c0abb0469cf5678949a59a8afd0929b5aeb92283f739c1ead3"
)
ABILITY_RESTORE_KEYS = tuple(
    str(character_id * 10 + slot)
    for character_id in (149995, 169996, 169997)
    for slot in range(1, 7)
)
ABYSS_GACHA_ID = "990001"
ABYSS_GACHA_LOGICALS = {
    5: abyss_gacha_contract.CHARACTER_5_ODDS_LOGICAL,
    4: abyss_gacha_contract.CHARACTER_4_ODDS_LOGICAL,
    3: abyss_gacha_contract.CHARACTER_3_ODDS_LOGICAL,
}
ABYSS_GACHA_BEFORE_COUNTS = {5: 253, 4: 144, 3: 78}
ABYSS_GACHA_AFTER_COUNTS = {5: 248, 4: 125, 3: 76}
ABYSS_GACHA_TOTALS = {5: 1_593_000, 4: 2_184, 3: 1_113}
ABYSS_GACHA_RETAINED_EXCEPTIONS = (123001, 131182, 213007, 263003, 263009, 263015)


class PublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceEntry:
    archive: Path
    member: str
    size: int
    crc: int


@dataclass(frozen=True)
class TableSpec:
    logical: str
    keys: tuple[str, ...]


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def member_name(root: str, logical: str) -> str:
    try:
        folder = ROOT_FOLDERS[root]
    except KeyError as error:
        raise PublishError(f"unsupported CDN root: {root}") from error
    digest = core.sha1_path(logical)
    return f"production/{folder}/{digest[:2]}/{digest[2:]}"


def relative_name(root: str, logical: str) -> str:
    return member_name(root, logical).split("/", 2)[2]


def exact_keys(character_tables: set[str]) -> list[TableSpec]:
    character_ids = tuple(str(value) for value in TARGET_CHARACTER_IDS)
    ability_ids = tuple(
        str(character_id * 10 + slot)
        for character_id in TARGET_CHARACTER_IDS
        for slot in range(1, 7)
    )
    character_id_tables = {
        "master/ability/leader_ability.orderedmap",
        "master/character/character.orderedmap",
        "master/character/character_awake_status.orderedmap",
        "master/character/character_speech.orderedmap",
        "master/character/character_status.orderedmap",
        "master/character/character_text.orderedmap",
        "master/character/full_shot_image_attribute.orderedmap",
        "master/generated/character_image.orderedmap",
        "master/generated/mana_board.orderedmap",
        "master/mana_board/mana_board2_open_condition.orderedmap",
        "master/mana_board/mana_node.orderedmap",
        "master/mana_board/upskill.orderedmap",
        "master/skill_preview/skill_preview_character.orderedmap",
        "master/stance_detail/character_stance_detail.orderedmap",
    }
    specs: dict[str, tuple[str, ...]] = {
        "master/ability/ability.orderedmap": ability_ids,
        "master/character/character_gacha_sound.orderedmap": (
            "169980", "169995", "179981",
        ),
        "master/character/unique_condition.orderedmap": (
            "1699950", "1699940", "1799810", "180001",
        ),
        "master/generated/trimmed_image.orderedmap": tuple(
            f"character/{code}/ui/{asset}"
            for code in (
                "maou2_playable",
                "white_tiger_ghost_playable",
                "cnmod_epuration_empress",
                "abyss_beast_playable",
            )
            for asset in (
                "full_shot_1440_1920_0",
                "full_shot_1440_1920_1",
                "skill_cutin_0",
                "skill_cutin_1",
            )
        ),
        "master/skill/action_skill.orderedmap": (
            "maou2_playable",
            "white_tiger_ghost_playable",
            "cnmod_epuration_empress",
            "abyss_beast_playable",
        ),
        "master/skill/power_flip_action.orderedmap": (
            "maou2_playable_pf",
            "white_tiger_ghost_playable_pf",
            "cnmod_epuration_empress_pf",
            "abyss_beast_playable_pf",
        ),
        "master/string/custom_ability_string.orderedmap": (
            "ability_skill_maou2_playable_followup",
            "ability_skill_maou2_playable_pf_lv2",
            "ability_skill_maou2_playable_pf_lv3",
            "ability_skill_maou2_playable_dash",
            "ability_skill_maou2_playable_eye",
            "ability_skill_maou2_playable_meteor",
            "ability_skill_maou2_playable_ring",
            "override_string_white_tiger_ghost_playable_pf",
            "ability_skill_white_tiger_ghost_pf_lv1_followup",
            "ability_skill_white_tiger_ghost_pf_lv2_followup",
            "ability_skill_white_tiger_ghost_pf_lv3_followup",
            "ability_skill_white_tiger_ghost_twin_followup",
            "ability_skill_white_tiger_ghost_pf_lv3_ex_followup",
            "ability_skill_cnmod_epuration_empress_a6_chase",
            "power_flip_abyss_beast_playable",
            "ability_skill_abyss_beast_familiar",
            "ability_skill_abyss_beast_awaken",
            "ability_skill_cnmod_epuration_empress_sword",
            "ability_skill_cnmod_epuration_empress_purge",
            "ability_skill_cnmod_epuration_empress_final",
            "override_string_cnmod_epuration_empress_pf",
        ),
        "master/degree/degree.orderedmap": tuple(map(str, TARGET_DEGREES)),
        "master/item/item.orderedmap": tuple(map(str, TARGET_ITEMS)),
        "master/shop/event_item_shop.orderedmap": tuple(map(str, TARGET_SHOP_ROWS)),
        "master/gacha/gacha.orderedmap": tuple(map(str, TARGET_GACHA_ROWS)),
        "master/gacha/gacha_feature_content.orderedmap": tuple(map(str, TARGET_GACHA_ROWS)),
        "master/rich_text/rich_text_html.orderedmap": TARGET_RICH_TEXT_ROWS,
    }
    for logical in character_id_tables:
        specs[logical] = character_ids
    missing = sorted(character_tables - specs.keys())
    unexpected = sorted(specs.keys() & character_tables - character_tables)
    if missing or unexpected:
        raise PublishError(
            f"character table selection is incomplete: missing={missing}, unexpected={unexpected}"
        )
    return [TableSpec(logical, specs[logical]) for logical in sorted(specs)]


def load_contract(bundle_root: Path) -> tuple[dict, dict]:
    contract_path = bundle_root / "verify" / "content-contract.json"
    requires_path = bundle_root / "cdn" / "content-only" / "requires.json"
    if not contract_path.is_file() or not requires_path.is_file():
        raise PublishError(f"reviewed bundle is incomplete: {bundle_root}")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    requires = json.loads(requires_path.read_text(encoding="utf-8-sig"))
    if contract.get("contractProfile") != "rank-p5b-gray-v1":
        raise PublishError("unexpected content contract profile")
    if requires.get("pack", {}).get("variant") != "content-only":
        raise PublishError("the content-only source manifest is missing")
    return contract, requires


def load_variant_requires(bundle_root: Path, variant: str) -> dict:
    path = bundle_root / "cdn" / variant / "requires.json"
    if not path.is_file():
        raise PublishError(f"reviewed bundle lacks {variant} requires.json")
    requires = json.loads(path.read_text(encoding="utf-8-sig"))
    if requires.get("pack", {}).get("variant") != variant:
        raise PublishError(f"reviewed bundle has an invalid {variant} source manifest")
    return requires


def selected_contract_members(contract: dict) -> tuple[dict[tuple[str, str], dict], set[str]]:
    selected: dict[tuple[str, str], dict] = {}
    character_tables: set[str] = set()
    wanted_ids = {
        *(f"{CHARACTER_ASSERTION_PREFIX}{value}" for value in TARGET_CHARACTER_IDS),
        GACHA_ASSERTION_ID,
    }
    assertions = {item.get("id"): item for item in contract.get("assertions", [])}
    missing = sorted(wanted_ids - assertions.keys())
    if missing:
        raise PublishError(f"contract assertions are missing: {missing}")
    for assertion_id in sorted(wanted_ids):
        assertion = assertions[assertion_id]
        for item in assertion.get("members", []):
            key = (item["root"], item["logicalPath"])
            previous = selected.get(key)
            if previous is not None and previous["variants"]["content-only"] != item["variants"]["content-only"]:
                raise PublishError(f"contract collision for {key}")
            selected[key] = item
            if assertion_id.startswith(CHARACTER_ASSERTION_PREFIX) and item["logicalPath"].startswith("master/"):
                character_tables.add(item["logicalPath"])
    return selected, character_tables


def source_index(
    bundle_root: Path,
    requires: dict,
    wanted_members: set[str],
    variant: str = "content-only",
) -> dict[str, SourceEntry]:
    result: dict[str, SourceEntry] = {}
    archive_paths = requires.get("pack", {}).get("archives", [])
    for relative in archive_paths:
        archive_path = bundle_root / "cdn" / variant / relative
        if not archive_path.is_file():
            raise PublishError(f"content-only archive is missing: {archive_path}")
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for info in archive.infolist():
                    if info.filename in wanted_members:
                        result[info.filename] = SourceEntry(
                            archive_path, info.filename, info.file_size, info.CRC
                        )
        except (OSError, zipfile.BadZipFile) as error:
            raise PublishError(f"cannot scan source archive {archive_path}: {error}") from error
    missing = sorted(wanted_members - result.keys())
    if missing:
        raise PublishError(f"source archives lack {len(missing)} selected members: {missing[:5]}")
    return result


def decode_item_sheet(raw: bytes, label: str) -> Image.Image:
    if not isinstance(raw, bytes) or not raw.startswith(wf_assets.PNG_FAKE):
        raise PublishError(f"{label}: item sprite sheet is not a client-storage PNG")
    try:
        with Image.open(io.BytesIO(wf_assets.png_decode(raw))) as image:
            image.load()
            return image.convert("RGBA")
    except UnidentifiedImageError as error:
        raise PublishError(f"{label}: item sprite sheet is not a valid PNG") from error


def decode_item_atlas(raw: bytes, label: str) -> list[dict]:
    try:
        atlas = wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
    except (TypeError, ValueError, zlib.error, EOFError, KeyError) as error:
        raise PublishError(f"{label}: item atlas is not valid raw-deflate AMF3") from error
    if not isinstance(atlas, list) or not all(isinstance(row, dict) for row in atlas):
        raise PublishError(f"{label}: item atlas root must be an object array")
    return atlas


def verify_ticket_item_icon_names(item_table_raw: bytes) -> None:
    table = core.read_orderedmap_bytes(item_table_raw, "master/item/item.orderedmap")
    rows = dict(zip(table.keys, table.rows))
    for item_id, icon_name in zip(TARGET_ITEMS, TICKET_ICON_NAMES):
        raw = rows.get(str(item_id))
        if raw is None:
            raise PublishError(f"ticket item row is missing: {item_id}")
        csv_rows = core.read_csv_lines(raw.decode("utf-8"))
        if len(csv_rows) != 1 or len(csv_rows[0]) <= 3:
            raise PublishError(f"ticket item row has an invalid shape: {item_id}")
        if csv_rows[0][3] != icon_name:
            raise PublishError(
                f"ticket item icon path differs: {item_id} -> {csv_rows[0][3]}"
            )


def graft_ticket_icon_assets(
    baseline_sheet_raw: bytes,
    baseline_atlas_raw: bytes,
    donor_sheet_raw: bytes,
    donor_atlas_raw: bytes,
    item_table_raw: bytes,
) -> tuple[bytes, bytes, dict]:
    """Accept the full-pack pair only when it is exactly our sheet plus two frames."""
    for logical, raw in (
        (ITEM_SHEET_LOGICAL, donor_sheet_raw),
        (ITEM_ATLAS_LOGICAL, donor_atlas_raw),
    ):
        if sha256_bytes(raw) != TICKET_FULL_ASSET_SHA256[logical]:
            raise PublishError(f"reviewed full-pack ticket asset drifted: {logical}")

    verify_ticket_item_icon_names(item_table_raw)
    baseline_sheet = decode_item_sheet(baseline_sheet_raw, "1.4.91 baseline")
    donor_sheet = decode_item_sheet(donor_sheet_raw, "reviewed full pack")
    baseline_atlas = decode_item_atlas(baseline_atlas_raw, "1.4.91 baseline")
    donor_atlas = decode_item_atlas(donor_atlas_raw, "reviewed full pack")

    if donor_sheet.size != (baseline_sheet.width, baseline_sheet.height + 22):
        raise PublishError(
            "reviewed full-pack item sheet is not a 22-pixel extension of the baseline"
        )
    if donor_sheet.crop((0, 0, baseline_sheet.width, baseline_sheet.height)).tobytes() \
            != baseline_sheet.tobytes():
        raise PublishError("reviewed full-pack item sheet changed baseline pixels")
    if donor_atlas[:len(baseline_atlas)] != baseline_atlas:
        raise PublishError("reviewed full-pack item atlas changed baseline rows")

    expected_frames = [
        {
            "n": icon_name,
            "w": 20,
            "h": 20,
            "x": 1 + index * 21,
            "y": baseline_sheet.height + 1,
        }
        for index, icon_name in enumerate(TICKET_ICON_NAMES)
    ]
    if donor_atlas[len(baseline_atlas):] != expected_frames:
        raise PublishError("reviewed full-pack item atlas adds more than the two ticket frames")
    if any(row.get("n") in TICKET_ICON_NAMES for row in baseline_atlas):
        raise PublishError("ticket icon frame already exists in the 1.4.91 baseline")

    allowed = set()
    frame_reports: list[dict] = []
    for item_id, frame in zip(TARGET_ITEMS, expected_frames):
        x = int(frame["x"])
        y = int(frame["y"])
        allowed.update(
            (pixel_x, pixel_y)
            for pixel_y in range(y, y + 20)
            for pixel_x in range(x, x + 20)
        )
        crop = donor_sheet.crop((x, y, x + 20, y + 20))
        if crop.getbbox() is None:
            raise PublishError(f"ticket icon frame is fully transparent: {item_id}")
        frame_reports.append({
            "item_id": item_id,
            "logical_name": frame["n"],
            "rect": [x, y, 20, 20],
            "rgba_sha256": sha256_bytes(crop.tobytes()),
        })
    for y in range(baseline_sheet.height, donor_sheet.height):
        for x in range(donor_sheet.width):
            if (x, y) not in allowed and donor_sheet.getpixel((x, y))[3] != 0:
                raise PublishError("reviewed full-pack item sheet adds non-ticket pixels")

    return donor_sheet_raw, donor_atlas_raw, {
        "source_variant": "full",
        "sheet_logical": ITEM_SHEET_LOGICAL,
        "atlas_logical": ITEM_ATLAS_LOGICAL,
        "baseline_sheet_sha256": sha256_bytes(baseline_sheet_raw),
        "output_sheet_sha256": sha256_bytes(donor_sheet_raw),
        "baseline_atlas_sha256": sha256_bytes(baseline_atlas_raw),
        "output_atlas_sha256": sha256_bytes(donor_atlas_raw),
        "baseline_dimensions": list(baseline_sheet.size),
        "output_dimensions": list(donor_sheet.size),
        "baseline_pixels_preserved": True,
        "baseline_atlas_rows_preserved": len(baseline_atlas),
        "added_frames": frame_reports,
        "item_reference_closure_verified": True,
    }


def read_source_payloads(index: dict[str, SourceEntry]) -> dict[str, bytes]:
    grouped: dict[Path, list[SourceEntry]] = defaultdict(list)
    for entry in index.values():
        grouped[entry.archive].append(entry)
    result: dict[str, bytes] = {}
    for archive_path, entries in grouped.items():
        with zipfile.ZipFile(archive_path) as archive:
            for entry in entries:
                info = archive.getinfo(entry.member)
                if info.file_size != entry.size or info.CRC != entry.crc:
                    raise PublishError(f"source archive changed during scan: {archive_path}!{entry.member}")
                result[entry.member] = archive.read(info)
    return result


def read_planned_entry(plan: store.MaterializePlan, root: str, logical: str) -> bytes:
    key = (root, relative_name(root, logical))
    try:
        entry = plan.entries[key]
    except KeyError as error:
        raise PublishError(f"1.4.92 baseline lacks required table: {root}/{logical}") from error
    try:
        with zipfile.ZipFile(entry.zip_path) as archive:
            info = archive.getinfo(entry.name)
            if info.file_size != entry.size or info.CRC != entry.crc:
                raise PublishError(f"baseline archive changed after planning: {entry.zip_path}!{entry.name}")
            return archive.read(info)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise PublishError(f"cannot read baseline entry {root}/{logical}: {error}") from error


def read_ability_restore_source(repo_root: Path) -> bytes:
    archive_path = repo_root / "assets" / "asset-patch" / "active" / ABILITY_RESTORE_ARCHIVE
    member = member_name("common", ABILITY_LOGICAL)
    if not archive_path.is_file():
        raise PublishError(f"ability restore archive is missing: {archive_path}")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            raw = archive.read(member)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise PublishError(f"cannot read ability restore source: {error}") from error
    if sha256_bytes(raw) != ABILITY_RESTORE_PAYLOAD_SHA256:
        raise PublishError("ability restore source payload drifted")
    source = core.read_orderedmap_raw_rows_from_bytes(raw, ABILITY_LOGICAL)
    missing = sorted(set(ABILITY_RESTORE_KEYS) - set(source.keys))
    if missing:
        raise PublishError(f"ability restore source lacks keys: {missing}")
    return raw


def restore_ability_rows(current_raw: bytes, source_raw: bytes) -> tuple[bytes, dict]:
    current = core.read_orderedmap_raw_rows_from_bytes(current_raw, ABILITY_LOGICAL)
    source = core.read_orderedmap_raw_rows_from_bytes(source_raw, ABILITY_LOGICAL)
    current_rows = dict(zip(current.keys, current.rows))
    source_rows = dict(zip(source.keys, source.rows))
    collisions = sorted(set(ABILITY_RESTORE_KEYS) & set(current_rows))
    if collisions:
        raise PublishError(f"ability restore keys already exist in 1.4.91 baseline: {collisions}")
    output = core.OrderedMap(
        ABILITY_LOGICAL,
        current.keys + list(ABILITY_RESTORE_KEYS),
        current.rows + [source_rows[key] for key in ABILITY_RESTORE_KEYS],
        Path("<restore-integrated-character-abilities>"),
    )
    built = core.build_orderedmap_raw_rows(output)
    check = core.read_orderedmap_raw_rows_from_bytes(built, ABILITY_LOGICAL)
    check_rows = dict(zip(check.keys, check.rows))
    if check.keys[:len(current.keys)] != current.keys:
        raise PublishError("ability restore changed baseline key order")
    for key, raw in current_rows.items():
        if check_rows.get(key) != raw:
            raise PublishError(f"ability restore changed existing row: {key}")
    for key in ABILITY_RESTORE_KEYS:
        if check_rows.get(key) != source_rows[key]:
            raise PublishError(f"ability restore row differs from integrated source: {key}")
    return built, {
        "logical": ABILITY_LOGICAL,
        "source_archive": ABILITY_RESTORE_ARCHIVE,
        "source_payload_sha256": sha256_bytes(source_raw),
        "baseline_before_sha256": sha256_bytes(current_raw),
        "baseline_before_rows": len(current.keys),
        "baseline_after_sha256": sha256_bytes(built),
        "baseline_after_rows": len(check.keys),
        "restored_keys": list(ABILITY_RESTORE_KEYS),
        "existing_rows_byte_identical": len(current.keys),
    }


def parse_abyss_gacha_rows(raw: bytes, logical: str) -> list[dict[str, object]]:
    outer = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    expected_key = Path(logical).stem
    if outer.keys != [expected_key] or len(outer.rows) != 1:
        raise PublishError(f"{logical}: unexpected abyss-gacha outer shape")
    inner = core.read_orderedmap_file_from_bytes(outer.rows[0])
    if list(inner) != [str(index) for index in range(len(inner))]:
        raise PublishError(f"{logical}: abyss-gacha inner keys are not contiguous")
    rows: list[dict[str, object]] = []
    for key, text in inner.items():
        csv_rows = core.read_csv_lines(text)
        if len(csv_rows) != 1 or len(csv_rows[0]) != 7:
            raise PublishError(f"{logical}:{key}: expected one seven-column row")
        row = csv_rows[0]
        if any(value not in {"true", "false"} for value in row[3:7]):
            raise PublishError(f"{logical}:{key}: invalid boolean fields")
        rows.append({
            "id": int(row[0]),
            "rank": int(row[1]),
            "odds": int(row[2]),
            "isRateUp": row[3] == "true",
            "isLimited": row[4] == "true",
            "isExchangeable": row[5] == "true",
            "trialReadingForced": row[6] == "true",
        })
    return rows


def abyss_gacha_server_rows(pool: dict[str, object], rank: int) -> list[dict[str, object]]:
    bucket = {5: "1", 4: "2", 3: "3"}[rank]
    entries = pool.get(bucket)
    if not isinstance(entries, list):
        raise PublishError(f"abyss-gacha server bucket is missing: {bucket}")
    fields = (
        "id", "rank", "odds", "isRateUp", "isLimited",
        "isExchangeable", "trialReadingForced",
    )
    rows: list[dict[str, object]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise PublishError(f"abyss-gacha server row is not an object: {bucket}:{index}")
        row = {field: entry.get(field) for field in fields}
        if row["rank"] != rank or any(row[field] is None for field in fields):
            raise PublishError(f"abyss-gacha server row drifted: {bucket}:{index}")
        rows.append(row)
    return rows


def load_abyss_gacha_server_pool(repo_root: Path) -> dict[str, object]:
    documents = [
        json.loads((repo_root / relative).read_text(encoding="utf-8"))
        for relative in ("assets/gacha.json", "assets/gacha_cnmod.json")
    ]
    entries = [document.get(ABYSS_GACHA_ID) for document in documents]
    if not all(isinstance(entry, dict) for entry in entries) or entries[0] != entries[1]:
        raise PublishError("server abyss-gacha mirrors are missing or different")
    pool = entries[0].get("pool")
    if not isinstance(pool, dict):
        raise PublishError("server abyss-gacha pool is missing")
    counts = {rank: len(abyss_gacha_server_rows(pool, rank)) for rank in (5, 4, 3)}
    if counts != ABYSS_GACHA_AFTER_COUNTS:
        raise PublishError(f"server abyss-gacha counts drifted: {counts}")
    return pool


def build_abyss_gacha_table(
    current_raw: bytes, logical: str, pool: dict[str, object], rank: int
) -> bytes:
    outer = core.read_orderedmap_raw_rows_from_bytes(current_raw, logical)
    expected_key = Path(logical).stem
    if outer.keys != [expected_key] or len(outer.rows) != 1:
        raise PublishError(f"{logical}: cannot fold cleanup into unexpected table shape")
    rows = abyss_gacha_pool.build_character_rows(pool, rank)
    inner = core.build_orderedmap(core.OrderedMap(
        logical,
        list(rows),
        [text.encode("utf-8") for text in rows.values()],
        Path("<fold-abyss-gacha-cleanup-into-1.4.92>"),
    ))
    output = core.build_orderedmap_raw_rows(core.OrderedMap(
        logical,
        [expected_key],
        [inner],
        Path("<fold-abyss-gacha-cleanup-into-1.4.92>"),
    ))
    if parse_abyss_gacha_rows(output, logical) != abyss_gacha_server_rows(pool, rank):
        raise PublishError(f"{logical}: folded client rows differ from server")
    return output


def fold_abyss_gacha_cleanup(
    payloads_by_logical: dict[tuple[str, str], bytes], repo_root: Path
) -> dict:
    pool = load_abyss_gacha_server_pool(repo_root)
    before: dict[int, list[dict[str, object]]] = {}
    after: dict[int, list[dict[str, object]]] = {}
    hashes: dict[str, dict[str, str]] = {}
    for rank, logical in ABYSS_GACHA_LOGICALS.items():
        key = ("common", logical)
        try:
            current_raw = payloads_by_logical[key]
        except KeyError as error:
            raise PublishError(f"1.4.92 payload lacks abyss-gacha table: {logical}") from error
        before[rank] = parse_abyss_gacha_rows(current_raw, logical)
        output = build_abyss_gacha_table(current_raw, logical, pool, rank)
        after[rank] = parse_abyss_gacha_rows(output, logical)
        payloads_by_logical[key] = output
        hashes[logical] = {
            "before_sha256": sha256_bytes(current_raw),
            "after_sha256": sha256_bytes(output),
        }
    before_counts = {rank: len(before[rank]) for rank in (5, 4, 3)}
    after_counts = {rank: len(after[rank]) for rank in (5, 4, 3)}
    if before_counts != ABYSS_GACHA_BEFORE_COUNTS or after_counts != ABYSS_GACHA_AFTER_COUNTS:
        raise PublishError(
            f"abyss-gacha fold counts drifted: before={before_counts}, after={after_counts}"
        )
    before_totals = {
        rank: sum(int(row["odds"]) for row in before[rank]) for rank in (5, 4, 3)
    }
    after_totals = {
        rank: sum(int(row["odds"]) for row in after[rank]) for rank in (5, 4, 3)
    }
    if before_totals != ABYSS_GACHA_TOTALS or after_totals != ABYSS_GACHA_TOTALS:
        raise PublishError(
            f"abyss-gacha fold changed rarity totals: before={before_totals}, after={after_totals}"
        )
    before_ids = {int(row["id"]) for rows in before.values() for row in rows}
    after_ids = {int(row["id"]) for rows in after.values() for row in rows}
    removed = sorted(before_ids - after_ids)
    expected_removed = sorted(abyss_gacha_contract.NON_GACHA_CHARACTER_IDS)
    if removed != expected_removed:
        raise PublishError(f"abyss-gacha fold removed unexpected IDs: {removed}")
    if not set(ABYSS_GACHA_RETAINED_EXCEPTIONS) <= after_ids:
        raise PublishError("abyss-gacha fold removed an approved exception")
    return {
        "included_in_combined_release": True,
        "version": PATCH_VERSION,
        "before_counts": {str(rank): before_counts[rank] for rank in (5, 4, 3)},
        "after_counts": {str(rank): after_counts[rank] for rank in (5, 4, 3)},
        "bucket_totals": {str(rank): after_totals[rank] for rank in (5, 4, 3)},
        "removed_character_ids": removed,
        "retained_exception_ids": list(ABYSS_GACHA_RETAINED_EXCEPTIONS),
        "client_server_membership_equal": True,
        "tables": hashes,
    }


def verify_contract_payloads(
    contract_members: dict[tuple[str, str], dict], source_payloads: dict[str, bytes]
) -> None:
    for (root, logical), item in contract_members.items():
        raw = source_payloads[member_name(root, logical)]
        expected = item["variants"]["content-only"]
        if len(raw) != expected["size"] or sha256_bytes(raw) != expected["sha256"]:
            raise PublishError(f"contract payload differs: {root}/{logical}")


def merge_table(current_raw: bytes, source_raw: bytes, spec: TableSpec) -> tuple[bytes, dict]:
    current = core.read_orderedmap_raw_rows_from_bytes(current_raw, spec.logical)
    source = core.read_orderedmap_raw_rows_from_bytes(source_raw, spec.logical)
    current_rows = dict(zip(current.keys, current.rows))
    source_rows = dict(zip(source.keys, source.rows))
    missing_source = [key for key in spec.keys if key not in source_rows]
    collisions = [key for key in spec.keys if key in current_rows]
    if missing_source:
        raise PublishError(f"source table lacks approved keys in {spec.logical}: {missing_source}")
    if collisions:
        raise PublishError(f"approved keys already exist at 1.4.92 in {spec.logical}: {collisions}")
    output = core.OrderedMap(
        spec.logical,
        current.keys + list(spec.keys),
        current.rows + [source_rows[key] for key in spec.keys],
        Path("<rank-p5b-merge>"),
    )
    built = core.build_orderedmap_raw_rows(output)
    check = core.read_orderedmap_raw_rows_from_bytes(built, spec.logical)
    check_rows = dict(zip(check.keys, check.rows))
    if check.keys[:len(current.keys)] != current.keys:
        raise PublishError(f"baseline key order changed in {spec.logical}")
    for key, raw in current_rows.items():
        if check_rows.get(key) != raw:
            raise PublishError(f"baseline row changed in {spec.logical}: {key}")
    for key in spec.keys:
        if check_rows.get(key) != source_rows[key]:
            raise PublishError(f"approved source row changed in {spec.logical}: {key}")
    return built, {
        "logical": spec.logical,
        "baseline_sha256": sha256_bytes(current_raw),
        "output_sha256": sha256_bytes(built),
        "baseline_rows_preserved": len(current.keys),
        "added_keys": list(spec.keys),
    }


def remove_feature_banner(current_raw: bytes) -> tuple[bytes, dict]:
    current = core.read_orderedmap_raw_rows_from_bytes(
        current_raw, FEATURE_BANNER_LOGICAL
    )
    current_rows = dict(zip(current.keys, current.rows))
    removed = current_rows.get(REMOVED_FEATURE_BANNER_ID)
    if removed is None:
        raise PublishError(
            f"1.4.91 feature-banner table lacks row {REMOVED_FEATURE_BANNER_ID}"
        )
    output = core.OrderedMap(
        FEATURE_BANNER_LOGICAL,
        [key for key in current.keys if key != REMOVED_FEATURE_BANNER_ID],
        [row for key, row in zip(current.keys, current.rows)
         if key != REMOVED_FEATURE_BANNER_ID],
        Path("<home-load-fix>"),
    )
    built = core.build_orderedmap_raw_rows(output)
    check = core.read_orderedmap_raw_rows_from_bytes(built, FEATURE_BANNER_LOGICAL)
    check_rows = dict(zip(check.keys, check.rows))
    if REMOVED_FEATURE_BANNER_ID in check_rows:
        raise PublishError("feature-banner row 10010 survived removal")
    if check.keys != output.keys:
        raise PublishError("feature-banner key order changed")
    for key, raw in current_rows.items():
        if key == REMOVED_FEATURE_BANNER_ID:
            continue
        if check_rows.get(key) != raw:
            raise PublishError(f"unrelated feature-banner row changed: {key}")
    removed_text = zlib.decompress(removed).decode("utf-8") if removed else ""
    if (
        "feature_banner_10010" not in removed_text
        or "side_story_event_home_banner" not in removed_text
    ):
        raise PublishError("feature-banner row 10010 is not the SideStory shortcut")
    return built, {
        "logical": FEATURE_BANNER_LOGICAL,
        "removed_id": int(REMOVED_FEATURE_BANNER_ID),
        "removed_link": "SideStory",
        "rows_before": len(current.keys),
        "rows_after": len(check.keys),
        "other_rows_byte_identical": len(check.keys),
        "baseline_sha256": sha256_bytes(current_raw),
        "output_sha256": sha256_bytes(built),
    }


def verify_bound_rows(contract: dict, merged: dict[str, bytes]) -> None:
    assertions = {item.get("id"): item for item in contract.get("assertions", [])}
    for degree_id in TARGET_DEGREES:
        assertion = assertions[f"degree-{degree_id}"]
        table = core.read_orderedmap_bytes(
            merged[assertion["tableLogicalPath"]], assertion["tableLogicalPath"]
        )
        row = dict(zip(table.keys, table.rows))[str(degree_id)]
        if sha256_bytes(row) != assertion["variants"]["content-only"]["rowSha256"]:
            raise PublishError(f"degree row contract differs: {degree_id}")
    for item_id in TARGET_ITEMS:
        assertion = assertions[f"ticket-{item_id}"]
        table = core.read_orderedmap_bytes(merged[assertion["logicalPath"]], assertion["logicalPath"])
        row = dict(zip(table.keys, table.rows))[str(item_id)]
        if sha256_bytes(row) != assertion["variants"]["content-only"]["rowSha256"]:
            raise PublishError(f"ticket row contract differs: {item_id}")
    assertion = assertions["shop-9700118-client"]
    table = core.read_orderedmap_bytes(merged[assertion["logicalPath"]], assertion["logicalPath"])
    row = dict(zip(table.keys, table.rows))[assertion["key"]]
    if sha256_bytes(row) != assertion["variants"]["content-only"]["rowSha256"]:
        raise PublishError("shop row contract differs: 9700118")


def validate_degree_pngs(contract: dict, payloads: dict[tuple[str, str], bytes]) -> list[dict]:
    assertions = {item.get("id"): item for item in contract.get("assertions", [])}
    report: list[dict] = []
    for degree_id in TARGET_DEGREES:
        assertion = assertions[f"degree-{degree_id}"]
        logical = f"dynamic/degree/{assertion['stringId']}.png"
        raw = payloads[(assertion["root"], logical)]
        expected = assertion["variants"]["content-only"]
        if (
            len(raw) != expected["pngSize"]
            or sha256_bytes(raw) != expected["pngSha256"]
            or raw[:8] != b"\x89png\r\n\x1a\n"
            or len(raw) < 24
            or struct.unpack(">II", raw[16:24]) != (320, 50)
        ):
            raise PublishError(f"degree PNG contract differs: {degree_id}")
        report.append({
            "degree_id": degree_id,
            "logical": logical,
            "size": len(raw),
            "sha256": sha256_bytes(raw),
            "dimensions": [320, 50],
            "cdn_png_signature": "89 70 6e 67",
        })
    return report


def split_payloads(payloads: dict[str, bytes]) -> list[dict[str, bytes]]:
    chunks: list[dict[str, bytes]] = []
    current: dict[str, bytes] = {}
    current_size = 0
    for member in sorted(payloads):
        raw = payloads[member]
        if current and current_size + len(raw) > MAX_RAW_ARCHIVE_BYTES:
            chunks.append(current)
            current = {}
            current_size = 0
        current[member] = raw
        current_size += len(raw)
    if current:
        chunks.append(current)
    if not chunks:
        raise PublishError("refusing to publish an empty patch")
    return chunks


def build_archive(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True
    ) as archive:
        for member in sorted(payloads):
            info = zipfile.ZipInfo(member, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(payloads):
            raise PublishError("archive member order differs")
        for member, payload in payloads.items():
            if archive.read(member) != payload:
                raise PublishError(f"archive readback differs: {member}")
    return raw


def archive_name(index: int) -> str:
    return f"{ARCHIVE_STEM}-{index}-{ARCHIVE_SUFFIX}.zip"


def validate_manifest(repo_root: Path) -> tuple[dict, bytes, bool]:
    manifest_path = repo_root / "assets" / "asset-patch" / "manifest.json"
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8-sig"))
    enabled = [item for item in manifest.get("patches", []) if item.get("enabled")]
    if not enabled:
        raise PublishError("manifest has no enabled patch")
    last = enabled[-1]
    combined = [item for item in manifest.get("patches", []) if item.get("id") == PATCH_ID]
    already_applied = len(combined) == 1
    if len(combined) > 1:
        raise PublishError("combined 1.4.92 patch is not unique")
    if (
        last.get("id") not in {REPLACED_PATCH_ID, PATCH_ID}
        or last.get("version") != PATCH_VERSION
        or last.get("depends_on") != BASE_VERSION
        or manifest.get("cdn_version") != PATCH_VERSION
    ):
        raise PublishError(
            "last enabled manifest patch is neither the original nor combined 1.4.92 edge"
        )
    if already_applied != (last.get("id") == PATCH_ID):
        raise PublishError("combined 1.4.92 patch exists away from the enabled chain tail")
    active = repo_root / "assets" / "asset-patch" / "active"
    existing_names = {
        item.get("archive")
        for item in manifest.get("patches", [])
        if item.get("archive")
    }
    for item in manifest.get("patches", []):
        existing_names.update(item.get("chain", []))
    if not already_applied:
        collisions = sorted(
            path.name for path in active.glob(f"{ARCHIVE_STEM}-*-{ARCHIVE_SUFFIX}.zip")
            if path.name in existing_names or path.exists()
        )
        if collisions:
            raise PublishError(f"target archive names already exist: {collisions}")
    audit_dir = repo_root / "assets" / "asset-patch" / "audit" / PATCH_ID
    if not already_applied and audit_dir.exists():
        raise PublishError(f"target audit directory already exists: {audit_dir}")
    if already_applied and not (audit_dir / "report.json").is_file():
        raise PublishError("combined 1.4.92 audit report is missing")
    return manifest, manifest_raw, already_applied


def update_manifest(manifest: dict, archives: list[tuple[str, bytes]], files: list[str]) -> bytes:
    value = json.loads(json.dumps(manifest))
    names = [name for name, _raw in archives]
    entry = {
        "id": PATCH_ID,
        "type": "patch",
        "name": "主页加载热修与深渊连战排行榜内容",
        "description": (
            "在本服1.4.91真实链尾上形成单一1.4.92：保留删除主页外传故事横幅的46.5%加载热修，"
            "并稀疏移植4名Boss角色、灰烬裁决卡池、2张裁定券及其图标、5个排行榜称号及称号商店条目；"
            "共享客户端表仅追加审核通过的目标键。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": names[0],
        "archive_size": sum(len(raw) for _name, raw in archives),
        "files": files,
        "changes": [
            "feature_banner表仅删除ID 10010（link=SideStory）的主页快捷横幅，其他602行保持原始字节一致；外传活动内容与活动页入口不变。",
            "用户真机确认该横幅热修解决登录加载46.5%停顿；本次与排行榜内容共同归并在唯一1.4.92中。",
            "新增169980、169994、169995、179981四名Boss角色的客户端资源与目标表行。",
            "新增卡池990002、裁定券999015/999016及对应图标、卡池横幅、概率表和说明；共享item图集仅追加两个20×20帧。",
            "新增排行榜称号9900002至9900006及320×50称号图；CDN存储态保留官方小写png魔数。",
            "新增商店条目9700118；保留本服700099与15件既有装备的全部现行内容。",
            "恢复149995、169996、169997三名既有角色各6条能力记录，修复角色记录存在但进入战斗时能力Key缺失的C8601。",
            "深渊池客户端三星、四星、五星表在同一1.4.92中清理为248/125/76项，不另拆客户端资源版本。",
            "所有共享orderedmap仅追加明确白名单键，1.4.91原有非目标行保持原始压缩字节不变。",
        ],
        "created_at": "2026-08-29",
        "audit": {
            "directory": f"assets/asset-patch/audit/{PATCH_ID}",
            "base_version": BASE_VERSION,
            "target_version": PATCH_VERSION,
            "home_load_fix_in_same_release": True,
            "sparse_row_graft": True,
            "preserves_rush_700099": True,
            "preserves_existing_equipment": True,
        },
        "archive_integrity": [
            {
                "name": name,
                "size": len(raw),
                "sha256": sha256_bytes(raw),
                "members": len(zipfile.ZipFile(io.BytesIO(raw)).infolist()),
            }
            for name, raw in archives
        ],
    }
    if len(names) > 1:
        entry["chain"] = names
    replacement_indexes = [
        index for index, item in enumerate(value["patches"])
        if item.get("id") in {REPLACED_PATCH_ID, PATCH_ID}
    ]
    if len(replacement_indexes) != 1:
        raise PublishError("cannot locate exactly one original or combined 1.4.92 patch")
    value["patches"][replacement_indexes[0]] = entry
    value["cdn_version"] = PATCH_VERSION
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write_new(raw: bytes, target: Path, suffix: str) -> None:
    if target.exists():
        raise PublishError(f"refusing to overwrite: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + suffix)
    if temporary.exists():
        raise PublishError(f"stale temporary file exists: {temporary}")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def atomic_replace(raw: bytes, target: Path, suffix: str) -> None:
    temporary = target.with_name(target.name + suffix)
    if temporary.exists():
        raise PublishError(f"stale temporary file exists: {temporary}")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=DEFAULT_BUNDLE_ROOT)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--repair-published",
        action="store_true",
        help="preview rebuilding the existing 1.4.92 archives; combine with --apply to replace them",
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    bundle_root = args.bundle_root.resolve()
    manifest, manifest_raw, already_applied = validate_manifest(repo_root)
    if args.repair_published and not already_applied:
        raise PublishError("--repair-published requires an existing combined 1.4.92")
    if already_applied and args.apply and not args.repair_published:
        raise PublishError(
            "combined 1.4.92 patch is already published; use --repair-published for the reviewed repair"
        )
    contract, requires = load_contract(bundle_root)
    full_requires = load_variant_requires(bundle_root, "full")
    contract_members, character_tables = selected_contract_members(contract)
    table_specs = exact_keys(character_tables)
    table_logicals = {spec.logical for spec in table_specs}

    degree_logicals = {
        (
            assertion["root"],
            f"dynamic/degree/{assertion['stringId']}.png",
        )
        for assertion in contract["assertions"]
        if assertion.get("id") in {f"degree-{value}" for value in TARGET_DEGREES}
    }
    selected_logicals = set(contract_members) | degree_logicals
    selected_logicals.update(("common", spec.logical) for spec in table_specs)
    wanted_members = {member_name(root, logical) for root, logical in selected_logicals}
    index = source_index(bundle_root, requires, wanted_members)
    source_payloads = read_source_payloads(index)
    verify_contract_payloads(contract_members, source_payloads)
    ticket_asset_members = {
        member_name("common", logical)
        for logical in (ITEM_SHEET_LOGICAL, ITEM_ATLAS_LOGICAL)
    }
    ticket_asset_index = source_index(
        bundle_root,
        full_requires,
        ticket_asset_members,
        "full",
    )
    ticket_asset_sources = read_source_payloads(ticket_asset_index)

    plan = store.build_read_only_plan(repo_root / ".cdn" / "cn", repo_root, BASE_VERSION, False)
    if not plan.summary().get("ok") or plan.tail != BASE_VERSION:
        raise PublishError(f"baseline CDN plan is unhealthy: {plan.summary()}")

    payloads_by_logical: dict[tuple[str, str], bytes] = {}
    direct_logicals: set[tuple[str, str]] = set()
    for root, logical in selected_logicals:
        if logical in table_logicals:
            continue
        payloads_by_logical[(root, logical)] = source_payloads[member_name(root, logical)]
        direct_logicals.add((root, logical))

    feature_banner_raw = read_planned_entry(
        plan, "common", FEATURE_BANNER_LOGICAL
    )
    feature_banner_output, feature_banner_report = remove_feature_banner(
        feature_banner_raw
    )
    payloads_by_logical[("common", FEATURE_BANNER_LOGICAL)] = feature_banner_output

    char_direct = {
        (root, logical)
        for (root, logical) in contract_members
        if not logical.startswith("master/") and any(token in logical for token in TARGET_CODE_NAMES)
    }
    collisions = sorted(
        f"{root}/{logical}"
        for root, logical in char_direct
        if (root, relative_name(root, logical)) in plan.entries
    )
    if collisions:
        raise PublishError(f"character-specific resources unexpectedly exist at 1.4.91: {collisions[:5]}")

    table_reports: list[dict] = []
    merged_tables: dict[str, bytes] = {}
    ability_restore_source = read_ability_restore_source(repo_root)
    ability_restore_report: dict | None = None
    for spec in table_specs:
        current_raw = read_planned_entry(plan, "common", spec.logical)
        if spec.logical == ABILITY_LOGICAL:
            current_raw, ability_restore_report = restore_ability_rows(
                current_raw, ability_restore_source
            )
        source_raw = source_payloads[member_name("common", spec.logical)]
        merged, report = merge_table(current_raw, source_raw, spec)
        merged_tables[spec.logical] = merged
        payloads_by_logical[("common", spec.logical)] = merged
        table_reports.append(report)
    if ability_restore_report is None:
        raise PublishError("ability restore did not run")
    verify_bound_rows(contract, merged_tables)
    baseline_item_sheet = read_planned_entry(
        plan, "common", ITEM_SHEET_LOGICAL
    )
    baseline_item_atlas = read_planned_entry(
        plan, "common", ITEM_ATLAS_LOGICAL
    )
    item_sheet_output, item_atlas_output, ticket_icon_report = graft_ticket_icon_assets(
        baseline_item_sheet,
        baseline_item_atlas,
        ticket_asset_sources[member_name("common", ITEM_SHEET_LOGICAL)],
        ticket_asset_sources[member_name("common", ITEM_ATLAS_LOGICAL)],
        merged_tables["master/item/item.orderedmap"],
    )
    payloads_by_logical[("common", ITEM_SHEET_LOGICAL)] = item_sheet_output
    payloads_by_logical[("common", ITEM_ATLAS_LOGICAL)] = item_atlas_output
    degree_reports = validate_degree_pngs(contract, payloads_by_logical)
    for logical in ABYSS_GACHA_LOGICALS.values():
        key = ("common", logical)
        if key not in payloads_by_logical:
            payloads_by_logical[key] = read_planned_entry(plan, "common", logical)
    abyss_gacha_cleanup_report = fold_abyss_gacha_cleanup(
        payloads_by_logical, repo_root
    )

    prohibited = sorted(
        f"{root}/{logical}"
        for root, logical in payloads_by_logical
        if "80001" in logical or "700099" in logical or "equipment/" in logical
    )
    if prohibited:
        raise PublishError(f"prohibited existing content entered sparse payload: {prohibited}")

    member_payloads = {
        member_name(root, logical): raw
        for (root, logical), raw in payloads_by_logical.items()
    }
    chunks = split_payloads(member_payloads)
    archives = [(archive_name(index + 1), build_archive(chunk)) for index, chunk in enumerate(chunks)]
    files = sorted(member_payloads)
    manifest_output = update_manifest(manifest, archives, files)
    audit = {
        "schema_version": 1,
        "patch_id": PATCH_ID,
        "dry_run": not args.apply,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "baseline_plan": plan.summary(),
        "source_bundle": str(bundle_root),
        "source_contract_profile": contract["contractProfile"],
        "selected_logical_files": len(payloads_by_logical),
        "selected_archive_members": len(member_payloads),
        "direct_resources": len(direct_logicals),
        "feature_banner": feature_banner_report,
        "ability_restore": ability_restore_report,
        "abyss_gacha_client_cleanup": abyss_gacha_cleanup_report,
        "ticket_icons": ticket_icon_report,
        "tables": table_reports,
        "degrees": degree_reports,
        "archives": [
            {
                "name": name,
                "size": len(raw),
                "sha256": sha256_bytes(raw),
                "members": len(zipfile.ZipFile(io.BytesIO(raw)).infolist()),
            }
            for name, raw in archives
        ],
        "manifest_before_sha256": sha256_bytes(manifest_raw),
        "manifest_after_sha256": sha256_bytes(manifest_output),
        "preservation": {
            "rush_event_700099_not_selected": True,
            "equipment_8000101_through_8000115_not_selected": True,
            "restored_legacy_character_ability_rows": len(ABILITY_RESTORE_KEYS),
            "single_combined_release_1_4_92": True,
            "ticket_icon_reference_closure": True,
            "baseline_table_rows_byte_identical": sum(
                item["baseline_rows_preserved"] for item in table_reports
            ),
            "feature_banner_other_rows_byte_identical": (
                feature_banner_report["other_rows_byte_identical"]
            ),
            "client_cdn_png_signature": "official obfuscated 89 70 6e 67 retained",
        },
    }
    audit_raw = (json.dumps(audit, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    if already_applied and not args.repair_published:
        if manifest_output != manifest_raw:
            raise PublishError("published manifest differs from the reproducible 1.4.92 result")
        active = repo_root / "assets" / "asset-patch" / "active"
        for name, raw in archives:
            path = active / name
            if not path.is_file():
                raise PublishError(f"published archive is missing: {path}")
            if path.stat().st_size != len(raw) or sha256_file(path) != sha256_bytes(raw):
                raise PublishError(f"published archive differs from reproducible bytes: {path}")
        published_audit = json.loads(
            (repo_root / "assets" / "asset-patch" / "audit" / PATCH_ID / "report.json")
            .read_text(encoding="utf-8")
        )
        stable_audit_keys = (
            "schema_version",
            "patch_id",
            "from_version",
            "version",
            "source_contract_profile",
            "selected_logical_files",
            "selected_archive_members",
            "direct_resources",
            "feature_banner",
            "ability_restore",
            "abyss_gacha_client_cleanup",
            "ticket_icons",
            "tables",
            "degrees",
            "archives",
            "preservation",
        )
        for key in stable_audit_keys:
            if published_audit.get(key) != audit.get(key):
                raise PublishError(f"published audit differs at {key}")

    if args.apply:
        active = repo_root / "assets" / "asset-patch" / "active"
        for name, raw in archives:
            path = active / name
            if args.repair_published:
                if not path.is_file():
                    raise PublishError(f"published archive is missing for repair: {path}")
                atomic_replace(raw, path, f".{PATCH_ID}.tmp")
            else:
                atomic_write_new(raw, path, f".{PATCH_ID}.tmp")
        audit_path = repo_root / "assets" / "asset-patch" / "audit" / PATCH_ID / "report.json"
        if args.repair_published:
            if not audit_path.is_file():
                raise PublishError(f"published audit is missing for repair: {audit_path}")
            atomic_replace(audit_raw, audit_path, f".{PATCH_ID}.tmp")
        else:
            atomic_write_new(audit_raw, audit_path, f".{PATCH_ID}.tmp")
        atomic_replace(
            manifest_output,
            repo_root / "assets" / "asset-patch" / "manifest.json",
            f".{PATCH_ID}.tmp",
        )
        for name, raw in archives:
            path = active / name
            if path.stat().st_size != len(raw) or sha256_file(path) != sha256_bytes(raw):
                raise PublishError(f"published archive readback differs: {path}")
        if sha256_file(audit_path) != sha256_bytes(audit_raw):
            raise PublishError("published audit readback differs")

    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
