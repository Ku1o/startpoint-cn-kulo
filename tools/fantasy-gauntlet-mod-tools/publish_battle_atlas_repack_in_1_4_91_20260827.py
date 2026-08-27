#!/usr/bin/env python3
"""Fold Gerald/Seris battle-atlas fixes into the existing 1.4.91 patch.

This intentionally reuses the existing 1.4.90 -> 1.4.91 archive name.  The two
existing UI-fix payloads are retained byte-for-byte, seven atlases are safely
repacked, and Seris's largest transform effect is cloned under the client
layer1 namespace.  Both Seris skill DSLs are redirected to the clone so the
effect no longer competes with the boss and character sheets in layer0.  The
already-generated enhancement-shop orderedmap is folded into the same archive
so the matching server stages never become visible before the client table.
Ginovi is deliberately outside this publisher's scope.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

import wf_mod_tool as core
from wf_battle_atlas_repack import (
    RepackResult,
    content_signature,
    decode_atlas,
    decode_png,
    repack_atlas,
)
from wf_flatomo_layer_retarget import decode_payload, retarget_effect_layer


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ARCHIVE_NAME = "pinball-1.4.90-1.4.91-1-0827-four-character-ui-centering.zip"
ACTIVE_ARCHIVE = REPO / "assets" / "asset-patch" / "active" / ARCHIVE_NAME
AUDIT_DIR = REPO / "assets" / "asset-patch" / "audit" / "four-character-ui-centering-1.4.91"
WORK_DIR = REPO / "work" / "battle-atlas-repack-1.4.91-20260827"
CANDIDATE_ARCHIVE = WORK_DIR / "candidate" / ARCHIVE_NAME
CANDIDATE_AUDIT = WORK_DIR / "candidate" / "battle-atlas-repack-audit.json"
CANDIDATE_MARKDOWN = WORK_DIR / "candidate" / "battle-atlas-repack-audit.md"
BASELINE_ARCHIVE_SHA256 = "95e57dd663581d92247d22727efd4f17ce0590e18f56186df78a29bd0cd4d8d4"
BASELINE_ARCHIVE_SIZE = 524_962
PRIOR_ARCHIVE_SHA256 = "e7224040b26df3e94e09100f13fee5223fd18f4b5b2aeb2ef0d78c8d9f96cb4c"
PRIOR_ARCHIVE_SIZE = 3_148_030
# Deterministic atlas-only archive identity from the first local installation.
ATLAS_ONLY_ARCHIVE_SHA256 = "4e91cc24b6b0a2f566a49b859a84de9949b3e45eef8225851bfffdc95af04e05"
ATLAS_ONLY_ARCHIVE_SIZE = 4_527_246
# Deterministic final archive identity, filled after the 23-member candidate is
# generated once and then used as an idempotence guard for no-op rebuilds.
INSTALLED_ARCHIVE_SHA256 = "589d9a061d4d51067c338a4332025257f234fcac4fe87141a8fec66bbe14a401"
INSTALLED_ARCHIVE_SIZE = 4_537_230
CROP_SOURCE_ARCHIVE = "pinball-1.4.67-1.4.68-1-battle-atlas-crop-fix.zip"
MAX_ARCHIVE_SIZE = 5 * 1024 * 1024
ZIP_TIMESTAMP = (2026, 8, 27, 0, 0, 0)
LAYER_AREA = 4096 * 4096

ENHANCEMENT_LOGICAL = (
    "master/equipment_enhancement/equipment_enhancement_shop.orderedmap"
)
ENHANCEMENT_MEMBER = "production/upload/e3/ef959b85852427577252f1651c3a93a8d2dc1e"
ENHANCEMENT_SOURCE = REPO / "assets" / "asset-patch" / ENHANCEMENT_MEMBER
ENHANCEMENT_SIZE = 18_260
ENHANCEMENT_SHA256 = "ebc306d0bd8c562faff0203f05e64d0eab40623d34505581ad6f940f7ed421b9"

PRESERVED_UI = {
    "production/medium_upload/e4/7e910cab2e474dc674e053a1941f8995f5e421": {
        "size": 380_134,
        "sha256": "365d02600c028cd3c101bd9d9adfe1cac532acca9bd8c86dbb952ff9a67eed1a",
    },
    "production/upload/fb/ab4344a7456dca88f3ce06f01208922f37e395": {
        "size": 351_605,
        "sha256": "5e4f842df25b6d4cae790bc2918ba8499b1dbdafea2558e928baea280487ceea",
    },
}


@dataclass(frozen=True, slots=True)
class AtlasSpec:
    key: str
    character: str
    png_logical: str
    atlas_logical: str
    source_size: tuple[int, int]
    target_size: tuple[int, int]
    sort_mode: str
    png_input_sha256: str
    atlas_input_sha256: str
    content_signature: str
    png_member: str
    atlas_member: str
    png_source_archive: str
    atlas_source_archive: str


@dataclass(frozen=True, slots=True)
class ResourcePin:
    logical: str
    member: str
    sha256: str
    bytes: int
    archive: str


SPECS = (
    AtlasSpec(
        "gerald_sprite",
        "杰拉德",
        "character/white_wolf_gerald/pixelart/sprite_sheet.png",
        "character/white_wolf_gerald/pixelart/sprite_sheet.atlas.amf3.deflate",
        (504, 192),
        (258, 357),
        "height",
        "f213b64bec371e2cc73661c26092c6873d88025548533d2aac7ce5271a671fe4",
        "3b226eb2ad3738a9499e971b15921efe6c049f16ce9cdf7b4886098a0a9c4235",
        "dc8d74a0d0edadce65d4a03c1c2d250748331f8992b36201696fb91e1da2f48f",
        "production/upload/69/99fbf8c65bd253d79b3f8ed4acffbcc8d60f11",
        "production/upload/7f/cb0db8d2e27c3361d79a32e531339043bbda79",
        CROP_SOURCE_ARCHIVE,
        "pinball-1.4.60-1.4.61-5-post60-terminal-overlay-sixpack-v2.zip",
    ),
    AtlasSpec(
        "gerald_skill",
        "杰拉德",
        "battle/effect/skill_unique/white_wolf_gerald/white_wolf_gerald.png",
        "battle/effect/skill_unique/white_wolf_gerald/white_wolf_gerald.atlas.amf3.deflate",
        (1015, 1478),
        (1002, 1237),
        "height",
        "ec2c8d1f997a06880a87184f0acf492501bfda7ce5bd7229f325f24c87568885",
        "4472c581e92593006e2a33b60d1ed3a23b62be68e252f4ded1d80ac83a0c2179",
        "334671019a7aac585a61e814469505b37f0da9dbb894539cbbae912336cf94cc",
        "production/upload/5d/3f8974dbc211de057d487129bf99af4d0c3263",
        "production/upload/86/b84dca5658e54795616bbe0446ee8191afb64b",
        CROP_SOURCE_ARCHIVE,
        "pinball-1.4.60-1.4.61-5-post60-terminal-overlay-sixpack-v2.zip",
    ),
    AtlasSpec(
        "gerald_powerflip",
        "杰拉德",
        "battle/effect/powerflip/white_wolf_gerald_powerflip/white_wolf_gerald_powerflip.png",
        "battle/effect/powerflip/white_wolf_gerald_powerflip/white_wolf_gerald_powerflip.atlas.amf3.deflate",
        (485, 470),
        (360, 590),
        "area",
        "03c2ddfa7cae91748b10516aba90c8d7f93c67d09da71f7d74e014fc57ca64bb",
        "e403505d7ab8faab0eb209c698b65a42f3d91adef0c269c08a1401c3c8e74d27",
        "6a17755201c1dcd8beba509721f3cef3e207a8332d76c437cc18eb197da2f171",
        "production/upload/94/9da9e14e1cdc64730850e49fd68152d8f8d4d8",
        "production/upload/4b/c5b3ac0fc4711af9b2213fc79e2b609de74fb5",
        CROP_SOURCE_ARCHIVE,
        "pinball-1.4.60-1.4.61-5-post60-terminal-overlay-sixpack-v2.zip",
    ),
    AtlasSpec(
        "seris_sprite",
        "赛瑞斯",
        "character/seris_dragon_king/pixelart/sprite_sheet.png",
        "character/seris_dragon_king/pixelart/sprite_sheet.atlas.amf3.deflate",
        (995, 388),
        (468, 665),
        "height",
        "8d966343f13b18a0596dace70df775d7eb89fb4639424a9f9cc5608124d362ae",
        "1d20293a5d2ce624336d71c037fb2a71f559e9921a82a986c3de40d0daa1591b",
        "6c1a14e2b405939ac238212c40f5f96bbd46d64dea9e6097ffd166168fddeaf5",
        "production/upload/f3/8eb6bd15b1e6a8784b860d3c09dc108955d7c3",
        "production/upload/79/efc98b343e27ead45cdb3225cf28a2da528ae1",
        CROP_SOURCE_ARCHIVE,
        "pinball-1.4.60-1.4.61-5-post60-terminal-overlay-sixpack-v2.zip",
    ),
    AtlasSpec(
        "seris_effect",
        "赛瑞斯",
        "battle/effect/skill_unique/seris_dragon_king/seris_dragon_king.png",
        "battle/effect/skill_unique/seris_dragon_king/seris_dragon_king.atlas.amf3.deflate",
        (1980, 879),
        (1138, 1179),
        "area",
        "d2afd78f9df5abe91a0730ee101f60b3a417a4115140f3df5ba035289c344356",
        "4ed2bc9162bea9abc7df204e02c47ae77ed90ce78b14f565a7147e5624f90e43",
        "3138c590723ad2cd0aa31b230b629ceaf3d6fe39cb96b578de92a7d8472a6788",
        "production/upload/07/f2f32d54668200dea95cd503f9a1328120d4d2",
        "production/upload/1e/82c7126aa1b41cb3eaa0c7dbb703c3813ef52f",
        CROP_SOURCE_ARCHIVE,
        "pinball-1.4.60-1.4.61-4-post60-terminal-overlay-sixpack-v2.zip",
    ),
    AtlasSpec(
        "seris_special_sprite",
        "赛瑞斯",
        "character/seris_dragon_king/pixelart/special_sprite_sheet.png",
        "character/seris_dragon_king/pixelart/special_sprite_sheet.atlas.amf3.deflate",
        (1024, 1024),
        (575, 1351),
        "area",
        "dca2aa621d97eed85f80230d6457be6530818a1c00edfd047685bd42375f1a67",
        "8ee344cabb29caaf98e6d544d59ff68d3fc26297950e9a88ccb345f4b3a43260",
        "ec2460c4ee1057714d7b46f7abbdd69c713200c7b26a08ff339275aea7607e85",
        "production/upload/05/154f1e26f658fafb63af306af2e5e6de7f6249",
        "production/upload/80/1b253dc5488949b261cab7d4bf524b53cddd8f",
        "pinball-1.4.60-1.4.61-4-post60-terminal-overlay-sixpack-v2.zip",
        "pinball-1.4.60-1.4.61-5-post60-terminal-overlay-sixpack-v2.zip",
    ),
    AtlasSpec(
        "seris_tide_ring",
        "赛瑞斯",
        "battle/effect/skill_unique/seris_human_royal_tide_ring/seris_human_royal_tide_ring.png",
        "battle/effect/skill_unique/seris_human_royal_tide_ring/seris_human_royal_tide_ring.atlas.amf3.deflate",
        (512, 512),
        (294, 588),
        "area",
        "25165f308bdc5f670c9142f3cbd5cc56a5ed9bf1e25c97bbbc63e6845b82c669",
        "7d596c67d07254e362fae7dcf58d2ae48f94db73ef3d6e88f5ab45b17a4e6b59",
        "8d9626128eb15fbd7665d56f1d4b6332ce416fde18a55916f4f85e3b99ba2470",
        "production/upload/34/af6a9cd9f426fb1bd3b81e166c9884a61a30b3",
        "production/upload/2e/5e14a08f7eeb94d3bfb72d9117fde56aee4691",
        "pinball-1.4.60-1.4.61-4-post60-terminal-overlay-sixpack-v2.zip",
        "pinball-1.4.60-1.4.61-4-post60-terminal-overlay-sixpack-v2.zip",
    ),
)


OLD_SERIS_SHEET = "battle/effect/skill_unique/seris_dragon_king/seris_dragon_king.png"
NEW_SERIS_SHEET = "battle/uncommon/layer1/seris_dragon_king/seris_dragon_king.png"
OLD_SERIS_EFFECT = (
    "battle/effect/skill_unique/seris_dragon_king/seris_dragon_king_transform"
)
NEW_SERIS_EFFECT = "battle/uncommon/layer1/seris_dragon_king/seris_dragon_king_transform"

SERIS_PARTS = ResourcePin(
    OLD_SERIS_EFFECT + ".parts.amf3.deflate",
    "production/upload/55/8b474010212252b5eb28a76f0fde9e5351a034",
    "a1e97f3a1a9ad25135e71bbd366be0c7467a3196f854ae5f49398a0ad82b9e84",
    245,
    "pinball-1.4.60-1.4.61-5-post60-terminal-overlay-sixpack-v2.zip",
)
SERIS_TIMELINE = ResourcePin(
    OLD_SERIS_EFFECT + ".timeline.amf3.deflate",
    "production/upload/30/0343136476be3fd2974a1b9a764b78d1ccdd84",
    "7c563a0d90533aaa131b4de7584eafdcefb4ec3caf8d92e8069db10cfc2b2deb",
    145,
    "pinball-1.4.60-1.4.61-4-post60-terminal-overlay-sixpack-v2.zip",
)
SERIS_ACTIONS = (
    ResourcePin(
        "battle/action/skill/seris_dragon_king/seris_dragon_king.action.dsl.amf3.deflate",
        "production/upload/82/ae4e4b5bcba1ad1ee22d02ecf79e0bcc583294",
        "8374f69d6604a87bc03d79b4f101684e1adef345c0c128356b57bbaf1e2d2388",
        697,
        "pinball-1.4.60-1.4.61-5-post60-terminal-overlay-sixpack-v2.zip",
    ),
    ResourcePin(
        "battle/action/skill/seris_dragon_king/seris_dragon_king_2.action.dsl.amf3.deflate",
        "production/upload/58/62aedae1bdd0bccaf5b7057a794e2a941a79bb",
        "8374f69d6604a87bc03d79b4f101684e1adef345c0c128356b57bbaf1e2d2388",
        697,
        "pinball-1.4.60-1.4.61-5-post60-terminal-overlay-sixpack-v2.zip",
    ),
)

PRIOR_SPEC_KEYS = {
    "gerald_sprite",
    "gerald_skill",
    "gerald_powerflip",
    "seris_sprite",
    "seris_effect",
}
RELOCATED_MEMBER_PINS = {
    NEW_SERIS_SHEET: "production/upload/f1/7fc9fcb1554b9b574c2153aae4d50f8045cef6",
    NEW_SERIS_SHEET.removesuffix(".png") + ".atlas.amf3.deflate": (
        "production/upload/aa/806a10466e9166995a2dbdf7698bf32953f3b9"
    ),
    NEW_SERIS_EFFECT + ".parts.amf3.deflate": (
        "production/upload/e4/3556110c14d4f92fc5085e6c2a307c3afb99a9"
    ),
    NEW_SERIS_EFFECT + ".timeline.amf3.deflate": (
        "production/upload/d4/18c979a14d61f3723bafb48a63ee9f26519b35"
    ),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def expected_member(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def validate_specs() -> None:
    members: set[str] = set()
    for spec in SPECS:
        if spec.png_member != expected_member(spec.png_logical):
            raise AssertionError(f"wrong PNG member pin for {spec.key}")
        if spec.atlas_member != expected_member(spec.atlas_logical):
            raise AssertionError(f"wrong atlas member pin for {spec.key}")
        for member in (spec.png_member, spec.atlas_member):
            if member in members:
                raise AssertionError(f"duplicate output member: {member}")
            members.add(member)
    for pin in (SERIS_PARTS, SERIS_TIMELINE, *SERIS_ACTIONS):
        if pin.member != expected_member(pin.logical):
            raise AssertionError(f"wrong source member pin for {pin.logical}")
        if pin.bytes <= 0:
            raise AssertionError(f"invalid source byte pin for {pin.logical}")
    for logical, member in RELOCATED_MEMBER_PINS.items():
        if member != expected_member(logical):
            raise AssertionError(f"wrong relocated member pin for {logical}")
        if member in members:
            raise AssertionError(f"duplicate output member: {member}")
        members.add(member)
    for pin in SERIS_ACTIONS:
        if pin.member in members:
            raise AssertionError(f"duplicate output member: {pin.member}")
        members.add(pin.member)
    if len(members) != 20:
        raise AssertionError(f"expected 20 non-UI output members, got {len(members)}")
    if ENHANCEMENT_MEMBER != expected_member(ENHANCEMENT_LOGICAL):
        raise AssertionError("wrong enhancement-shop member pin")
    if ENHANCEMENT_MEMBER in members or ENHANCEMENT_MEMBER in PRESERVED_UI:
        raise AssertionError("enhancement-shop member overlaps another output")


def read_preserved_ui() -> dict[str, bytes]:
    raw = ACTIVE_ARCHIVE.read_bytes()
    identity = (len(raw), sha256(raw))
    allowed = {
        (BASELINE_ARCHIVE_SIZE, BASELINE_ARCHIVE_SHA256),
        (PRIOR_ARCHIVE_SIZE, PRIOR_ARCHIVE_SHA256),
        (ATLAS_ONLY_ARCHIVE_SIZE, ATLAS_ONLY_ARCHIVE_SHA256),
    }
    if INSTALLED_ARCHIVE_SIZE and INSTALLED_ARCHIVE_SHA256:
        allowed.add((INSTALLED_ARCHIVE_SIZE, INSTALLED_ARCHIVE_SHA256))
    if identity not in allowed:
        raise RuntimeError(
            "active 1.4.91 archive matches neither the pinned two-member baseline nor the "
            "installed battle-atlas result; "
            "refusing an ambiguous same-version rewrite"
        )
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        expected_members = set(PRESERVED_UI)
        if identity == (PRIOR_ARCHIVE_SIZE, PRIOR_ARCHIVE_SHA256):
            expected_members.update(
                member
                for spec in SPECS
                if spec.key in PRIOR_SPEC_KEYS
                for member in (spec.png_member, spec.atlas_member)
            )
        elif identity in {
            (ATLAS_ONLY_ARCHIVE_SIZE, ATLAS_ONLY_ARCHIVE_SHA256),
            (INSTALLED_ARCHIVE_SIZE, INSTALLED_ARCHIVE_SHA256),
        }:
            expected_members.update(
                member for spec in SPECS for member in (spec.png_member, spec.atlas_member)
            )
            expected_members.update(RELOCATED_MEMBER_PINS.values())
            expected_members.update(pin.member for pin in SERIS_ACTIONS)
            if identity == (INSTALLED_ARCHIVE_SIZE, INSTALLED_ARCHIVE_SHA256):
                expected_members.add(ENHANCEMENT_MEMBER)
        if set(archive.namelist()) != expected_members:
            raise RuntimeError("active 1.4.91 archive has an unexpected member set")
        result = {name: archive.read(name) for name in PRESERVED_UI}
    for name, expected in PRESERVED_UI.items():
        payload = result[name]
        if len(payload) != expected["size"] or sha256(payload) != expected["sha256"]:
            raise RuntimeError(f"existing UI payload changed: {name}")
    return result


def read_enhancement_payload() -> bytes:
    if ENHANCEMENT_SOURCE.is_file():
        payload = ENHANCEMENT_SOURCE.read_bytes()
    else:
        with zipfile.ZipFile(ACTIVE_ARCHIVE) as archive:
            try:
                payload = archive.read(ENHANCEMENT_MEMBER)
            except KeyError as exc:
                raise RuntimeError(
                    "enhancement-shop payload is absent from both the sparse production store "
                    "and the active archive"
                ) from exc
    if len(payload) != ENHANCEMENT_SIZE or sha256(payload) != ENHANCEMENT_SHA256:
        raise RuntimeError("enhancement-shop payload does not match the pinned generated table")
    return payload


def read_pinned_member(archive_name: str, member: str, expected_sha256: str) -> tuple[bytes, Path]:
    archive_path = REPO / "assets" / "asset-patch" / "active" / archive_name
    with zipfile.ZipFile(archive_path) as archive:
        payload = archive.read(member)
    actual = sha256(payload)
    if actual != expected_sha256:
        raise RuntimeError(
            f"pinned historical source changed: {archive_name}!{member}: {actual}"
        )
    return payload, archive_path


def read_resource_pin(pin: ResourcePin) -> tuple[bytes, Path]:
    payload, archive_path = read_pinned_member(pin.archive, pin.member, pin.sha256)
    if len(payload) != pin.bytes:
        raise RuntimeError(
            f"pinned historical source size changed: {pin.archive}!{pin.member}: {len(payload)}"
        )
    return payload, archive_path


def build_repacked_payloads() -> tuple[dict[str, bytes], list[dict], dict[str, RepackResult]]:
    payloads: dict[str, bytes] = {}
    audits: list[dict] = []
    results: dict[str, RepackResult] = {}
    for spec in SPECS:
        png_payload, png_archive = read_pinned_member(
            spec.png_source_archive, spec.png_member, spec.png_input_sha256
        )
        atlas_payload, atlas_archive = read_pinned_member(
            spec.atlas_source_archive, spec.atlas_member, spec.atlas_input_sha256
        )
        source_image = decode_png(png_payload)
        source_records = decode_atlas(atlas_payload)
        if source_image.size != spec.source_size:
            raise RuntimeError(f"unexpected source dimensions for {spec.key}: {source_image.size}")
        if content_signature(source_image, source_records) != spec.content_signature:
            raise RuntimeError(f"unexpected source frame semantics for {spec.key}")

        result = repack_atlas(
            png_payload,
            atlas_payload,
            target_width=spec.target_size[0],
            expected_height=spec.target_size[1],
            max_height=2048,
            gap=2,
            sort_mode=spec.sort_mode,
        )
        if result.content_signature != spec.content_signature:
            raise AssertionError(f"content signature changed for {spec.key}")
        payloads[spec.png_member] = result.png_payload
        payloads[spec.atlas_member] = result.atlas_payload
        results[spec.key] = result
        audits.append(
            {
                **asdict(spec),
                "source_size": list(spec.source_size),
                "target_size": list(spec.target_size),
                "source_png": {
                    "sha256": sha256(png_payload),
                    "bytes": len(png_payload),
                    "archive": str(png_archive),
                    "member": spec.png_member,
                    "source_kind": "pinned historical active archive",
                },
                "source_atlas": {
                    "sha256": sha256(atlas_payload),
                    "bytes": len(atlas_payload),
                    "archive": str(atlas_archive),
                    "member": spec.atlas_member,
                    "source_kind": "pinned historical active archive",
                },
                "output_png": {
                    "sha256": sha256(result.png_payload),
                    "bytes": len(result.png_payload),
                    "member": spec.png_member,
                },
                "output_atlas": {
                    "sha256": sha256(result.atlas_payload),
                    "bytes": len(result.atlas_payload),
                    "member": spec.atlas_member,
                },
                "records": result.record_count,
                "unique_regions": result.unique_region_count,
                "region_area": result.region_area,
                "source_area": result.source_area,
                "target_area": result.output_area,
                "saved_area": result.source_area - result.output_area,
                "saved_percent_of_layer0": round(
                    (result.source_area - result.output_area) * 100 / LAYER_AREA, 6
                ),
                "validation": {
                    "ordered_region_rgba_identical": True,
                    "record_names_and_order_unchanged": True,
                    "metadata_except_xy_unchanged": True,
                    "rotation_unchanged": True,
                    "two_pixel_gutter": True,
                    "nontransparent_pixels_outside_regions": 0,
                },
            }
        )
    return payloads, audits, results


def build_retargeted_payloads(
    repack_results: dict[str, RepackResult],
) -> tuple[dict[str, bytes], dict]:
    effect = repack_results["seris_effect"]
    parts_payload, parts_archive = read_resource_pin(SERIS_PARTS)
    timeline_payload, timeline_archive = read_resource_pin(SERIS_TIMELINE)
    action_sources: list[bytes] = []
    action_archives: list[Path] = []
    for pin in SERIS_ACTIONS:
        payload, archive_path = read_resource_pin(pin)
        action_sources.append(payload)
        action_archives.append(archive_path)

    result = retarget_effect_layer(
        png_payload=effect.png_payload,
        atlas_payload=effect.atlas_payload,
        parts_payload=parts_payload,
        timeline_payload=timeline_payload,
        action_payloads=tuple(action_sources),
        old_sheet_logical=OLD_SERIS_SHEET,
        new_sheet_logical=NEW_SERIS_SHEET,
        old_effect_reference=OLD_SERIS_EFFECT,
        new_effect_reference=NEW_SERIS_EFFECT,
    )
    if result.timeline_payload != timeline_payload:
        raise AssertionError("Seris transform timeline was not preserved byte-for-byte")

    new_atlas_logical = NEW_SERIS_SHEET.removesuffix(".png") + ".atlas.amf3.deflate"
    new_parts_logical = NEW_SERIS_EFFECT + ".parts.amf3.deflate"
    new_timeline_logical = NEW_SERIS_EFFECT + ".timeline.amf3.deflate"
    payloads = {
        expected_member(NEW_SERIS_SHEET): effect.png_payload,
        expected_member(new_atlas_logical): result.atlas_payload,
        expected_member(new_parts_logical): result.parts_payload,
        expected_member(new_timeline_logical): result.timeline_payload,
    }
    for pin, payload in zip(SERIS_ACTIONS, result.action_payloads, strict=True):
        payloads[pin.member] = payload

    if set(payloads) != set(RELOCATED_MEMBER_PINS.values()) | {
        pin.member for pin in SERIS_ACTIONS
    }:
        raise AssertionError("unexpected Seris layer-retarget output member set")

    audit = {
        "old_layer": "layer0",
        "new_layer": "layer1",
        "old_sheet_logical": OLD_SERIS_SHEET,
        "new_sheet_logical": NEW_SERIS_SHEET,
        "old_effect_reference": OLD_SERIS_EFFECT,
        "new_effect_reference": NEW_SERIS_EFFECT,
        "moved_sheet_size": list(effect.output_size),
        "moved_sheet_area": effect.output_area,
        "moved_percent_of_4096_sheet": round(effect.output_area * 100 / LAYER_AREA, 6),
        "atlas_records": result.atlas_records,
        "parts_images": result.parts_images,
        "action_replacements": list(result.action_replacements),
        "old_cell_prefix": result.old_cell_prefix,
        "new_cell_prefix": result.new_cell_prefix,
        "sources": {
            "parts": {
                **asdict(SERIS_PARTS),
                "archive_path": str(parts_archive),
            },
            "timeline": {
                **asdict(SERIS_TIMELINE),
                "archive_path": str(timeline_archive),
            },
            "actions": [
                {**asdict(pin), "archive_path": str(archive_path)}
                for pin, archive_path in zip(SERIS_ACTIONS, action_archives, strict=True)
            ],
        },
        "outputs": [
            {"member": member, "bytes": len(payload), "sha256": sha256(payload)}
            for member, payload in sorted(payloads.items())
        ],
        "validation": {
            "png_identical_to_repacked_layer0_sheet": True,
            "atlas_geometry_and_metadata_unchanged": True,
            "atlas_cell_prefix_only": True,
            "parts_cell_prefix_only": True,
            "timeline_byte_identical": True,
            "each_action_effect_reference_replaced_once": True,
            "layer1_common_plus_effect_fit": {
                "common_runtime_orientation": [508, 3841],
                "effect_runtime_orientation": list(effect.output_size),
                "combined_bounding_box": [508 + effect.output_size[0], 3841],
                "within_4096x4096": 508 + effect.output_size[0] <= 4096
                and max(3841, effect.output_size[1]) <= 4096,
            },
        },
    }
    if not audit["validation"]["layer1_common_plus_effect_fit"]["within_4096x4096"]:
        raise AssertionError("relocated Seris effect does not fit beside battle/common/layer1")
    return payloads, audit


def zip_bytes(payloads: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(
        stream,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for name in sorted(payloads):
            normalized = name.replace("\\", "/")
            if normalized.startswith("/") or ".." in Path(normalized).parts:
                raise ValueError(f"unsafe archive member: {name}")
            info = zipfile.ZipInfo(normalized, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, payloads[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return stream.getvalue()


def validate_archive(raw: bytes, payloads: dict[str, bytes]) -> None:
    if len(raw) > MAX_ARCHIVE_SIZE:
        raise RuntimeError(f"candidate archive exceeds 5 MiB: {len(raw)}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.testzip() is not None:
            raise RuntimeError(f"candidate archive CRC failed: {archive.testzip()}")
        if archive.namelist() != sorted(payloads):
            raise RuntimeError("candidate archive member order is not deterministic")
        if len(set(archive.namelist())) != len(payloads):
            raise RuntimeError("candidate archive contains duplicate members")
        for name, payload in payloads.items():
            if archive.read(name) != payload:
                raise RuntimeError(f"candidate payload mismatch: {name}")
    for name, expected in PRESERVED_UI.items():
        payload = payloads[name]
        if len(payload) != expected["size"] or sha256(payload) != expected["sha256"]:
            raise RuntimeError(f"candidate did not preserve existing UI payload: {name}")


def build_audit(
    raw: bytes,
    atlases: list[dict],
    payloads: dict[str, bytes],
    layer_retarget: dict,
) -> dict:
    characters = {}
    for character in ("杰拉德", "赛瑞斯"):
        selected = [item for item in atlases if item["character"] == character]
        original_layer0 = sum(item["source_area"] for item in selected)
        failed_first_attempt_layer0 = sum(
            item["target_area"] if item["key"] in PRIOR_SPEC_KEYS else item["source_area"]
            for item in selected
        )
        final_layer0 = sum(
            item["target_area"]
            for item in selected
            if not (character == "赛瑞斯" and item["key"] == "seris_effect")
        )
        final_layer1 = sum(
            item["target_area"]
            for item in selected
            if character == "赛瑞斯" and item["key"] == "seris_effect"
        )
        final_total = final_layer0 + final_layer1
        characters[character] = {
            "original_layer0_area": original_layer0,
            "failed_first_attempt_layer0_area": failed_first_attempt_layer0,
            "final_layer0_area": final_layer0,
            "final_layer1_area": final_layer1,
            "final_total_area": final_total,
            "original_layer0_percent": round(original_layer0 * 100 / LAYER_AREA, 6),
            "failed_first_attempt_layer0_percent": round(
                failed_first_attempt_layer0 * 100 / LAYER_AREA, 6
            ),
            "final_layer0_percent": round(final_layer0 * 100 / LAYER_AREA, 6),
            "final_layer1_percent": round(final_layer1 * 100 / LAYER_AREA, 6),
            "final_total_percent": round(final_total * 100 / LAYER_AREA, 6),
            "saved_from_original_layer0_area": original_layer0 - final_layer0,
            "saved_from_failed_attempt_layer0_area": failed_first_attempt_layer0
            - final_layer0,
        }
    original_layer0 = sum(item["original_layer0_area"] for item in characters.values())
    failed_first_attempt_layer0 = sum(
        item["failed_first_attempt_layer0_area"] for item in characters.values()
    )
    final_layer0 = sum(item["final_layer0_area"] for item in characters.values())
    final_layer1 = sum(item["final_layer1_area"] for item in characters.values())
    return {
        "schema": "startpoint-cn-battle-atlas-repack-and-layer-retarget-audit-v2",
        "created_at": "2026-08-28T00:00:00+08:00",
        "base_version": "1.4.90",
        "target_version": "1.4.91",
        "same_version_rebuild": True,
        "same_version_rebuild_reason": (
            "operator requested retaining 1.4.91 because the production client release has not "
            "been distributed; local clients that cached the earlier 1.4.91 must reset resources"
        ),
        "scope": ["杰拉德", "赛瑞斯"],
        "excluded": ["基诺维"],
        "observed_failure": {
            "code": "U_1d93f4",
            "message": "Failed to allocate packing rectangle: size exceeded.",
            "quest_id": 7002,
            "boss": "abyss_cloud",
            "resource_version": "1.4.91",
            "first_attempt_result": "failed with Seris in a high-load three-party composition",
            "root_cause_update": (
                "the first pass omitted Seris special_sprite_sheet and royal tide ring assets"
            ),
        },
        "archive": {
            "name": ARCHIVE_NAME,
            "bytes": len(raw),
            "sha256": sha256(raw),
            "members": len(payloads),
            "member_names": sorted(payloads),
        },
        "preserved_ui_payloads": [
            {"member": name, **expected} for name, expected in PRESERVED_UI.items()
        ],
        "client_tables": [
            {
                "logical": ENHANCEMENT_LOGICAL,
                "member": ENHANCEMENT_MEMBER,
                "bytes": ENHANCEMENT_SIZE,
                "sha256": ENHANCEMENT_SHA256,
                "validation": {
                    "generated_from_committed_server_shop": True,
                    "source_rows": 191,
                    "output_rows": 215,
                    "unrelated_rows_byte_identical": 189,
                    "target_equipment_ids": [5010070, 5020043],
                    "stages_per_equipment": 13,
                },
            }
        ],
        "packing_contract": {
            "moves_whole_regions_only": True,
            "per_frame_trimming": False,
            "resampling": False,
            "rotation": False,
            "gutter_pixels": 2,
            "only_atlas_fields_changed": ["x", "y"],
            "layer_retarget_changes_only_logical_prefixes": True,
            "action_dsl_changes_only_effect_reference": True,
        },
        "atlases": atlases,
        "layer_retarget": layer_retarget,
        "characters": characters,
        "total": {
            "original_layer0_area": original_layer0,
            "failed_first_attempt_layer0_area": failed_first_attempt_layer0,
            "final_layer0_area": final_layer0,
            "final_layer1_area": final_layer1,
            "original_layer0_percent": round(original_layer0 * 100 / LAYER_AREA, 6),
            "failed_first_attempt_layer0_percent": round(
                failed_first_attempt_layer0 * 100 / LAYER_AREA, 6
            ),
            "final_layer0_percent": round(final_layer0 * 100 / LAYER_AREA, 6),
            "final_layer1_percent": round(final_layer1 * 100 / LAYER_AREA, 6),
            "saved_from_original_layer0_area": original_layer0 - final_layer0,
            "saved_from_original_layer0_percent": round(
                (original_layer0 - final_layer0) * 100 / LAYER_AREA, 6
            ),
            "saved_from_failed_attempt_layer0_area": failed_first_attempt_layer0
            - final_layer0,
            "saved_from_failed_attempt_layer0_percent": round(
                (failed_first_attempt_layer0 - final_layer0) * 100 / LAYER_AREA, 6
            ),
        },
        "gameplay_verified": False,
    }


def audit_markdown(audit: dict) -> str:
    lines = [
        "# 1.4.91 杰拉德/赛瑞斯战斗图集安全重排审计",
        "",
        "完整 atlas 矩形重排仅修改 `x/y`；赛瑞斯最大变身特效另复制到 layer1，并只改资源路径。帧像素、顺序、尺寸和动画时序保持一致。基诺维未纳入。",
        "",
        "| 角色 | 原始 layer0 | 首轮失败包 layer0 | 最终 layer0 | 最终 layer1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for character, item in audit["characters"].items():
        lines.append(
            f"| {character} | {item['original_layer0_area']:,} "
            f"({item['original_layer0_percent']:.2f}%) | "
            f"{item['failed_first_attempt_layer0_area']:,} "
            f"({item['failed_first_attempt_layer0_percent']:.2f}%) | "
            f"{item['final_layer0_area']:,} ({item['final_layer0_percent']:.2f}%) | "
            f"{item['final_layer1_area']:,} ({item['final_layer1_percent']:.2f}%) |"
        )
    total = audit["total"]
    lines.extend(
        [
            f"| 合计 | {total['original_layer0_area']:,} "
            f"({total['original_layer0_percent']:.2f}%) | "
            f"{total['failed_first_attempt_layer0_area']:,} "
            f"({total['failed_first_attempt_layer0_percent']:.2f}%) | "
            f"{total['final_layer0_area']:,} ({total['final_layer0_percent']:.2f}%) | "
            f"{total['final_layer1_area']:,} ({total['final_layer1_percent']:.2f}%) |",
            "",
            f"- 相比首轮失败包，layer0 再减少 {total['saved_from_failed_attempt_layer0_area']:,} 像素（{total['saved_from_failed_attempt_layer0_percent']:.2f}%）。",
            f"- 归档：`{audit['archive']['name']}`",
            f"- SHA-256：`{audit['archive']['sha256']}`",
            f"- 成员数：{audit['archive']['members']}（原 UI 2 项逐字节保留，图集 14 项、layer1 效果 4 项、动作 DSL 2 项、强化商店表 1 项）。",
            "- 强化商店表：解放者与终结者各 13 阶；目标 26 行更新，其他 189 行逐字节不变。",
            "- 自动门禁：逐帧 RGBA 一致、atlas 除坐标/路径外一致、parts 仅路径变化、timeline 逐字节一致、每份动作 DSL 恰好替换一个效果引用。",
            "- 真机多人战验证：尚未执行。",
            "",
        ]
    )
    return "\n".join(lines)


def write_candidate(raw: bytes, audit: dict) -> None:
    CANDIDATE_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATE_ARCHIVE.write_bytes(raw)
    CANDIDATE_AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    CANDIDATE_MARKDOWN.write_text(audit_markdown(audit), encoding="utf-8")


def install_candidate() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = ACTIVE_ARCHIVE.with_name(f".{ACTIVE_ARCHIVE.name}.atlas-repack.tmp")
    shutil.copyfile(CANDIDATE_ARCHIVE, temporary)
    os.replace(temporary, ACTIVE_ARCHIVE)
    shutil.copyfile(CANDIDATE_AUDIT, AUDIT_DIR / CANDIDATE_AUDIT.name)
    shutil.copyfile(CANDIDATE_MARKDOWN, AUDIT_DIR / CANDIDATE_MARKDOWN.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        action="store_true",
        help="replace the active 1.4.91 archive and install tracked audit outputs after validation",
    )
    args = parser.parse_args(argv)
    validate_specs()
    payloads = read_preserved_ui()
    repacked, atlas_audits, repack_results = build_repacked_payloads()
    payloads.update(repacked)
    retargeted, retarget_audit = build_retargeted_payloads(repack_results)
    overlap = set(payloads) & set(retargeted)
    if overlap:
        raise AssertionError(f"layer-retarget members overlap existing payloads: {sorted(overlap)}")
    payloads.update(retargeted)
    if ENHANCEMENT_MEMBER in payloads:
        raise AssertionError("enhancement-shop member unexpectedly overlaps another payload")
    payloads[ENHANCEMENT_MEMBER] = read_enhancement_payload()
    if len(payloads) != 23:
        raise AssertionError(f"expected 23 unique members, got {len(payloads)}")
    raw = zip_bytes(payloads)
    validate_archive(raw, payloads)
    audit = build_audit(raw, atlas_audits, payloads, retarget_audit)
    write_candidate(raw, audit)
    if args.install:
        install_candidate()
    print(
        json.dumps(
            {
                "installed": args.install,
                "candidate": str(CANDIDATE_ARCHIVE),
                "active": str(ACTIVE_ARCHIVE),
                "archive_size": len(raw),
                "archive_sha256": sha256(raw),
                "members": len(payloads),
                "total": audit["total"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
