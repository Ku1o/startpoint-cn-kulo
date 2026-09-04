#!/usr/bin/env python3
"""Publish the client-side cleanup of the abyss and race gacha pools.

The server pool sources are authoritative for the final membership and
weights.  This publisher replays the source repository's current 1.4.99
terminal (based on the 1.4.98 CDN), rewrites only the six character-odds
orderedmaps, and adds the resulting ZIP as the third archive on the existing
1.4.98 -> 1.4.99 release chain.  The pristine CDN and the runtime mirror are
read-only inputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import struct
import sys
import zipfile
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_ROOT))

import wf_mod_tool as core  # noqa: E402
import wf_store_materialize as store  # noqa: E402


BASE_VERSION = "1.4.98"
TARGET_VERSION = "1.4.99"
PATCH_ID = "gacha-non-gacha-cleanup-client-1.4.99"
ARCHIVE_NAME = "pinball-1.4.98-1.4.99-3-gacha-non-gacha-cleanup.zip"
INTEGRATION_PARENT_ID = "siete-balance-visual-restore-1.4.99"
MANIFEST_PATH = ROOT / "assets" / "asset-patch" / "manifest.json"
ACTIVE_DIR = ROOT / "assets" / "asset-patch" / "active"
AUDIT_DIR = ROOT / "assets" / "asset-patch" / "audit" / PATCH_ID

REMOVED_IDS = (
    10, 113001, 141003, 153001, 163001,
    213001, 213013, 223001, 223007, 223013, 223019,
    233001, 233007, 233013, 243001, 243007, 243013, 243019,
    253001, 253007, 253013, 253019, 263001, 263002,
    323001, 333001,
)
REMOVED_SET = set(REMOVED_IDS)

POOL_SPECS = (
    {
        "gacha_id": "990001",
        "server_file": "gacha.json",
        "prefix": "cnmod_abyss_limited_gacha",
        "expected_before": {5: 258, 4: 125, 3: 76},
        "expected_after": {5: 253, 4: 125, 3: 76},
    },
    {
        "gacha_id": "990002",
        "server_file": "gacha_rank_p5b.json",
        "prefix": "cnmod_ashen_verdict_gacha",
        "expected_before": {5: 291, 4: 144, 3: 78},
        "expected_after": {5: 286, 4: 125, 3: 76},
    },
)

RARITY_LOGICALS = {
    "990001": "master/gacha_odds/cnmod_abyss_limited_gacha_rarity.orderedmap",
    "990002": "master/gacha_odds/cnmod_ashen_verdict_gacha_rarity.orderedmap",
}


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def deterministic_zip(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for member in sorted(payloads):
            info = zipfile.ZipInfo(member, date_time=(2026, 9, 4, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.testzip() is not None:
            raise PublishError("client gacha cleanup ZIP CRC 校验失败")
        if archive.namelist() != sorted(payloads):
            raise PublishError("client gacha cleanup ZIP member order drifted")
        for member, payload in payloads.items():
            if archive.read(member) != payload:
                raise PublishError(f"client gacha cleanup ZIP readback differs: {member}")
    return raw


def _read_planned(plan: store.MaterializePlan, logical: str) -> tuple[bytes, dict[str, object]]:
    digest = core.sha1_path(logical)
    relative = f"{digest[:2]}/{digest[2:]}"
    entry = plan.entries.get(("common", relative))
    if entry is None:
        raise PublishError(f"1.4.99 release terminal lacks {logical} ({relative})")
    try:
        with zipfile.ZipFile(entry.zip_path) as archive:
            raw = archive.read(entry.name)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise PublishError(f"cannot read planned CDN member {entry.zip_path}!{entry.name}: {exc}") from exc
    return raw, {
        "root": entry.root,
        "relative": entry.relative,
        "member": entry.name,
        "archive": str(entry.zip_path),
        "size": len(raw),
        "sha256": sha256(raw),
    }


def _csv_row(raw: bytes, label: str) -> list[str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PublishError(f"{label} is not UTF-8") from exc
    rows = list(csv.reader([text]))
    if len(rows) != 1:
        raise PublishError(f"{label} is not one CSV row")
    return rows[0]


def _client_row_fields(text: str, label: str, width: int = 7) -> list[str]:
    rows = list(csv.reader([text]))
    if len(rows) != 1 or len(rows[0]) != width:
        raise PublishError(f"{label} must have {width} CSV columns")
    return rows[0]


def _client_row(entry: dict[str, object]) -> str:
    fields = [
        str(entry["id"]),
        str(entry["rank"]),
        str(entry["odds"]),
        str(entry["isRateUp"]).lower(),
        str(entry["isLimited"]).lower(),
        str(entry["isExchangeable"]).lower(),
        str(entry["trialReadingForced"]).lower(),
    ]
    if any(value not in {"true", "false"} for value in fields[3:]):
        raise PublishError(f"server pool entry has non-boolean flags: {entry}")
    return ",".join(fields)


def _build_compressed_orderedmap(keys: list[str], blocks: list[bytes]) -> bytes:
    """Serialize an orderedmap whose rows are already zlib-compressed blocks."""
    if len(keys) != len(blocks):
        raise PublishError("orderedmap key/block count differs")
    key_blob = b""
    row_blob = b""
    pairs: list[tuple[int, int]] = []
    for key, block in zip(keys, blocks):
        if not isinstance(block, bytes):
            raise PublishError("orderedmap row block is not bytes")
        key_blob += key.encode("utf-8")
        row_blob += block
        pairs.append((len(key_blob), len(row_blob)))
    index = bytearray(struct.pack("<I", len(keys)))
    for key_end, row_end in pairs:
        index += struct.pack("<II", key_end, row_end)
    index += key_blob
    packed_index = zlib.compress(bytes(index))
    return struct.pack("<I", len(packed_index)) + packed_index + row_blob


def _parse_nested(
    raw: bytes, logical: str, *, width: int = 7
) -> tuple[str, list[str], list[bytes], list[list[str]]]:
    outer = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    if len(outer.keys) != 1 or len(outer.rows) != 1:
        raise PublishError(f"{logical} outer table shape drifted")
    odds_id = outer.keys[0]
    inner_logical = f"{logical}#{odds_id}"
    inner_raw = core.read_orderedmap_raw_rows_from_bytes(outer.rows[0], inner_logical)
    if inner_raw.keys != [str(index) for index in range(len(inner_raw.keys))]:
        raise PublishError(f"{logical} inner keys are not sequential")
    rows: list[list[str]] = []
    for index, block in enumerate(inner_raw.rows):
        try:
            text = zlib.decompress(block).decode("utf-8")
        except (UnicodeDecodeError, zlib.error) as exc:
            raise PublishError(f"{logical} row {index} is not compressed UTF-8 CSV") from exc
        rows.append(_client_row_fields(text, f"{logical} row {index}", width))
    return odds_id, inner_raw.keys, inner_raw.rows, rows


def _build_nested(
    logical: str,
    odds_id: str,
    current_blocks: dict[int, bytes],
    current_rows: dict[int, list[str]],
    target_entries: list[dict[str, object]],
) -> tuple[bytes, dict[str, object]]:
    target_ids = [int(entry["id"]) for entry in target_entries]
    current_ids = [int(fields[0]) for fields in current_rows.values()]
    if [value for value in current_ids if value not in REMOVED_SET] != target_ids:
        raise PublishError(
            f"{logical} server order differs from client order after removals"
        )
    if len(set(target_ids)) != len(target_ids):
        raise PublishError(f"{logical} target pool has duplicate IDs")
    target_by_id = {int(entry["id"]): entry for entry in target_entries}
    target_blocks: list[bytes] = []
    changed_ids: list[int] = []
    preserved_special: list[int] = []
    removed = sorted(set(current_ids) - set(target_ids))
    for index, character_id in enumerate(target_ids):
        entry = target_by_id[character_id]
        expected_text = _client_row(entry)
        expected_fields = expected_text.split(",")
        before_fields = current_rows[character_id]
        if before_fields[3] == "true" or before_fields[2] == "0":
            if before_fields != expected_fields:
                raise PublishError(
                    f"{logical} UP/zero-weight row changed unexpectedly: {character_id}"
                )
            preserved_special.append(character_id)
        if before_fields != expected_fields:
            changed_ids.append(character_id)
            target_blocks.append(zlib.compress(expected_text.encode("utf-8"), 9))
        else:
            # Preserve the exact compressed block for unchanged rows, including
            # all UP entries and zero-weight limited placeholders.
            target_blocks.append(current_blocks[character_id])

    inner = _build_compressed_orderedmap(
        [str(index) for index in range(len(target_entries))], target_blocks
    )
    output = core.build_orderedmap_raw_rows(
        core.OrderedMap(
            logical,
            [odds_id],
            [inner],
            Path("<gacha-pool-cleanup-client-1.4.99>"),
        )
    )
    check_outer = core.read_orderedmap_raw_rows_from_bytes(output, logical)
    check_inner = core.read_orderedmap_bytes(check_outer.rows[0], f"{logical}#readback")
    check_rows = [_client_row_fields(raw.decode("utf-8"), f"{logical} readback") for raw in check_inner.rows]
    if [int(row[0]) for row in check_rows] != target_ids:
        raise PublishError(f"{logical} readback ID order differs")
    expected_rows = [_client_row(entry) for entry in target_entries]
    if [",".join(row) for row in check_rows] != expected_rows:
        raise PublishError(f"{logical} readback rows differ from final server pool")
    return output, {
        "logical": logical,
        "odds_id": odds_id,
        "before_rows": len(current_rows),
        "after_rows": len(target_entries),
        "removed_ids": removed,
        "changed_weight_ids": changed_ids,
        "changed_weight_count": len(changed_ids),
        "preserved_up_or_zero_ids": preserved_special,
        "before_total_weight": sum(int(row[2]) for row in current_rows.values()),
        "after_total_weight": sum(int(entry["odds"]) for entry in target_entries),
        "output_sha256": sha256(output),
        "output_size": len(output),
    }


def _load_server_pools(repo_root: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for spec in POOL_SPECS:
        path = repo_root / "assets" / spec["server_file"]
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PublishError(f"cannot read server gacha source {path}: {exc}") from exc
        pool = document.get(spec["gacha_id"])
        if not isinstance(pool, dict) or not isinstance(pool.get("pool"), dict):
            raise PublishError(f"server gacha {spec['gacha_id']} is missing pool")
        result[spec["gacha_id"]] = pool
    return result


def _check_rarity_tables(
    plan: store.MaterializePlan,
    server_pools: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for gacha_id, logical in RARITY_LOGICALS.items():
        raw, source = _read_planned(plan, logical)
        odds_id, _keys, _blocks, rows = _parse_nested(raw, logical, width=2)
        parsed = {int(row[0]): int(row[1]) for row in rows}
        if len(parsed) != len(rows):
            raise PublishError(f"{logical} rarity table has duplicate keys")
        rates = server_pools[gacha_id].get("rankRates")
        if not isinstance(rates, dict) or not isinstance(rates.get("normal"), list):
            raise PublishError(f"server gacha {gacha_id} rankRates malformed")
        normal = rates["normal"]
        expected = {5: int(normal[0]), 4: int(normal[1]), 3: int(normal[2])}
        if parsed != expected:
            raise PublishError(
                f"{logical} rarity rates differ: client={parsed}, server={expected}"
            )
        checks.append({
            "gacha_id": gacha_id,
            "logical": logical,
            "odds_id": odds_id,
            "source_archive": source["archive"],
            "source_sha256": source["sha256"],
            "client_rows": rows,
            "server_rank_rates": rates,
            "matches_server": True,
        })
    return checks


def _check_master_refs(plan: store.MaterializePlan, server_pools: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    logical = "master/gacha/gacha.orderedmap"
    raw, source = _read_planned(plan, logical)
    table = core.read_orderedmap_bytes(raw, logical)
    rows = dict(zip(table.keys, table.rows))
    checks: list[dict[str, object]] = []
    for gacha_id, pool in server_pools.items():
        if gacha_id not in rows:
            raise PublishError(f"client gacha master lacks {gacha_id}")
        fields = _csv_row(rows[gacha_id], f"client gacha master {gacha_id}")
        refs = [fields[14], fields[15], fields[16]]
        # The server JSON intentionally does not carry the client odds IDs;
        # use the fixed IDs encoded by each pool's prefix instead.
        prefix = next(spec["prefix"] for spec in POOL_SPECS if spec["gacha_id"] == gacha_id)
        expected = [f"{prefix}_character_{rank}" for rank in (3, 4, 5)]
        if refs != expected:
            raise PublishError(f"client gacha master refs drifted for {gacha_id}: {refs}")
        checks.append({
            "gacha_id": gacha_id,
            "logical": logical,
            "source_archive": source["archive"],
            "source_sha256": source["sha256"],
            "character_odds_refs": refs,
            "matches_expected": True,
        })
    return checks


def build(repo_root: Path) -> tuple[bytes, dict[str, object], dict[str, object], bytes]:
    manifest_path = repo_root / "assets" / "asset-patch" / "manifest.json"
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishError(f"cannot read asset-patch manifest: {exc}") from exc
    manifest_version = manifest.get("cdn_version")
    if manifest_version not in {BASE_VERSION, TARGET_VERSION}:
        raise PublishError(
            f"manifest CDN tail is neither {BASE_VERSION} nor {TARGET_VERSION}: {manifest_version}"
        )
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        raise PublishError("manifest patches is not an array")
    if any(item.get("id") == PATCH_ID for item in patches):
        raise PublishError(f"patch already exists in manifest: {PATCH_ID}")
    enabled = [item for item in patches if item.get("enabled")]
    if not enabled or enabled[-1].get("version") not in {BASE_VERSION, TARGET_VERSION}:
        raise PublishError(f"enabled manifest tail is neither {BASE_VERSION} nor {TARGET_VERSION}")
    archive_path = repo_root / "assets" / "asset-patch" / "active" / ARCHIVE_NAME
    if archive_path.exists():
        raise PublishError(f"refusing to regenerate existing integrated archive: {ARCHIVE_NAME}")

    cdn_root = (repo_root / ".cdn" / "cn").resolve()
    # Build against the current .99 terminal: the existing Siete archives are
    # part of that terminal, while this cleanup archive is intentionally not
    # present yet.  Its six target tables are untouched by the Siete package.
    plan = store.build_read_only_plan(cdn_root, repo_root, TARGET_VERSION, False)
    if plan.tail != TARGET_VERSION or plan.health.gap(plan.tail) or plan.health.unreachable:
        raise PublishError(f"source CDN plan is unhealthy: {plan.summary()}")
    server_pools = _load_server_pools(repo_root)
    rarity_checks = _check_rarity_tables(plan, server_pools)
    master_checks = _check_master_refs(plan, server_pools)

    payloads: dict[str, bytes] = {}
    table_reports: list[dict[str, object]] = []
    pool_before_ids: dict[str, set[int]] = {spec["gacha_id"]: set() for spec in POOL_SPECS}
    pool_after_ids: dict[str, set[int]] = {spec["gacha_id"]: set() for spec in POOL_SPECS}
    for spec in POOL_SPECS:
        gacha_id = spec["gacha_id"]
        server_gacha = server_pools[gacha_id]
        for rank in (5, 4, 3):
            logical = f"master/gacha_odds/{spec['prefix']}_character_{rank}.orderedmap"
            raw, source = _read_planned(plan, logical)
            odds_id, inner_keys, inner_blocks, current_rows_list = _parse_nested(raw, logical)
            current_rows = {int(row[0]): row for row in current_rows_list}
            current_blocks = {
                int(row[0]): block for row, block in zip(current_rows_list, inner_blocks)
            }
            expected_before = spec["expected_before"][rank]
            expected_after = spec["expected_after"][rank]
            if len(current_rows) != expected_before:
                raise PublishError(f"{logical} before count drifted: {len(current_rows)}")
            target_entries = server_gacha["pool"][str({5: 1, 4: 2, 3: 3}[rank])]
            if not isinstance(target_entries, list) or len(target_entries) != expected_after:
                raise PublishError(f"server {gacha_id} rank {rank} target count drifted")
            pool_before_ids[gacha_id].update(current_rows)
            pool_after_ids[gacha_id].update(int(entry["id"]) for entry in target_entries)
            output, report = _build_nested(
                logical, odds_id, current_blocks, current_rows, target_entries
            )
            if report["before_total_weight"] != report["after_total_weight"]:
                raise PublishError(f"{logical} total weight changed")
            report.update({
                "gacha_id": gacha_id,
                "rank": rank,
                "member": member_name(logical),
                "source_archive": source["archive"],
                "source_member": source["member"],
                "source_sha256": source["sha256"],
                "source_size": source["size"],
                "before_sha256": source["sha256"],
            })
            payloads[report["member"]] = output
            table_reports.append(report)

    removed_by_pool: dict[str, list[int]] = {}
    already_absent_by_pool: dict[str, list[int]] = {}
    for spec in POOL_SPECS:
        removed: set[int] = set()
        for report in table_reports:
            if report["gacha_id"] == spec["gacha_id"]:
                removed.update(report["removed_ids"])
        gacha_id = spec["gacha_id"]
        expected_removed = REMOVED_SET & pool_before_ids[gacha_id]
        if removed != expected_removed:
            raise PublishError(
                f"{gacha_id} removed ID set drifted: actual={sorted(removed)}, "
                f"expected={sorted(expected_removed)}"
            )
        if REMOVED_SET & pool_after_ids[gacha_id]:
            raise PublishError(f"{gacha_id} final client pool still contains removed IDs")
        removed_by_pool[gacha_id] = sorted(removed)
        already_absent_by_pool[gacha_id] = sorted(REMOVED_SET - pool_before_ids[gacha_id])

    archive_raw = deterministic_zip(payloads)
    report = {
        "schema": "gacha-pool-cleanup-client/v1",
        "patch_id": PATCH_ID,
        "base_version": BASE_VERSION,
        "target_version": TARGET_VERSION,
        "source_tail": plan.tail,
        "source_plan": plan.summary(),
        "server_sources": {
            spec["gacha_id"]: {
                "path": str(repo_root / "assets" / spec["server_file"]),
                "sha256": sha256((repo_root / "assets" / spec["server_file"]).read_bytes()),
                "counts": {
                    str(rank): len(server_pools[spec["gacha_id"]]["pool"][str({5: 1, 4: 2, 3: 3}[rank])])
                    for rank in (5, 4, 3)
                },
            }
            for spec in POOL_SPECS
        },
        "tables": table_reports,
        "removed_ids_by_pool": removed_by_pool,
        "already_absent_ids_by_pool": already_absent_by_pool,
        "rarity_checks": rarity_checks,
        "master_reference_checks": master_checks,
        "archive": {
            "name": ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256(archive_raw),
            "members": len(payloads),
            "files": sorted(payloads),
        },
        "verification": {
            "archive_crc_ok": True,
            "client_rows_match_final_server_pool": True,
            "all_26_removed_from_each_pool": True,
            "rarity_tables_match_server_rank_rates": True,
            "gacha_master_character_odds_refs_unchanged": True,
            "up_rows_and_zero_weight_placeholders_preserved": True,
            "rarity_bucket_totals_preserved": True,
            "pristine_cdn_written": False,
        },
        "manifest_before_sha256": sha256(manifest_raw),
    }
    return archive_raw, report, manifest, manifest_raw


def update_manifest(manifest: dict[str, object], report: dict[str, object]) -> dict[str, object]:
    """Add the cleanup archive to the existing 1.4.99 Siete release entry."""
    updated = json.loads(json.dumps(manifest, ensure_ascii=False))
    patches = updated.get("patches")
    if not isinstance(patches, list):
        raise PublishError("manifest patches is not an array")
    parent = next((item for item in patches if item.get("id") == INTEGRATION_PARENT_ID), None)
    if not isinstance(parent, dict):
        raise PublishError(f"integration parent patch is missing: {INTEGRATION_PARENT_ID}")
    if parent.get("version") != TARGET_VERSION or parent.get("depends_on") != BASE_VERSION:
        raise PublishError("integration parent patch does not target the expected 1.4.98 -> 1.4.99 edge")

    chain = parent.get("chain")
    if not isinstance(chain, list):
        raise PublishError("integration parent patch chain is not an array")
    if ARCHIVE_NAME in chain:
        raise PublishError(f"archive already exists in integration parent: {ARCHIVE_NAME}")
    existing_files = parent.get("files")
    if not isinstance(existing_files, list):
        raise PublishError("integration parent patch files is not an array")
    new_files = list(report["archive"]["files"])
    if set(existing_files) & set(new_files):
        raise PublishError("cleanup archive file members overlap existing Siete members")

    # `archive`/`archive_size` identify the first archive on a multi-archive
    # release edge. Keep that anchor stable while appending this cleanup as
    # the third archive in the existing 1.4.99 chain.
    if not chain or parent.get("archive") != chain[0]:
        raise PublishError("integration parent archive must remain the first chain archive")
    integrity_entries = parent.get("archive_integrity")
    if not isinstance(integrity_entries, list) or not integrity_entries:
        raise PublishError("integration parent archive_integrity must contain the first archive")
    first_integrity = integrity_entries[0]
    if not isinstance(first_integrity, dict) or first_integrity.get("name") != chain[0]:
        raise PublishError("integration parent first archive integrity does not match chain")
    if parent.get("archive_size") != first_integrity.get("size"):
        raise PublishError("integration parent archive_size does not match first archive integrity")
    parent["files"] = existing_files + new_files
    parent.setdefault("changes", []).append(
        "同一1.4.99边追加竞速池与深渊池非扭蛋角色清理：两池各移除26名非扭蛋角色，UP、零权重占位和各星级总权重保持不变。"
    )
    audit = parent.setdefault("audit", {})
    if not isinstance(audit, dict):
        raise PublishError("integration parent audit is not an object")
    audit["gacha_cleanup"] = str(AUDIT_DIR.relative_to(ROOT)).replace("\\", "/") + "/report.json"
    integrity = parent.setdefault("archive_integrity", [])
    if not isinstance(integrity, list):
        raise PublishError("integration parent archive_integrity is not an array")
    integrity.append({
        "name": ARCHIVE_NAME,
        "size": report["archive"]["size"],
        "sha256": report["archive"]["sha256"],
        "members": report["archive"]["members"],
        "files": new_files,
    })
    chain.append(ARCHIVE_NAME)
    updated["cdn_version"] = TARGET_VERSION
    return updated


def merge_manifest_bytes(manifest_raw: bytes, updated: dict[str, object]) -> bytes:
    """Replace only the integration parent object, preserving all other bytes."""
    try:
        text = manifest_raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PublishError(f"manifest is not UTF-8: {exc}") from exc
    newline = "\r\n" if "\r\n" in text else "\n"
    marker = f'"id": "{INTEGRATION_PARENT_ID}"'
    marker_index = text.find(marker)
    if marker_index < 0:
        raise PublishError(f"manifest integration parent marker is missing: {INTEGRATION_PARENT_ID}")
    brace = text.rfind("{", 0, marker_index)
    if brace < 0:
        raise PublishError("manifest integration parent object start is missing")
    start = text.rfind(newline, 0, brace) + len(newline)
    if start < 0:
        start = 0
    try:
        _original, end = json.JSONDecoder().raw_decode(text[brace:])
    except json.JSONDecodeError as exc:
        raise PublishError(f"cannot decode integration parent manifest object: {exc}") from exc
    replacement = next(
        item for item in updated["patches"] if item.get("id") == INTEGRATION_PARENT_ID
    )
    rendered = json.dumps(replacement, ensure_ascii=False, indent=2).replace("\n", newline)
    rendered = newline.join("    " + line for line in rendered.split(newline))
    text = text[:start] + rendered + text[brace + end:]
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    archive_raw, report, manifest, manifest_raw = build(repo_root)
    print(json.dumps({
        "ok": True,
        "dry_run": not args.apply,
        "archive": report["archive"],
        "source_tail": report["source_tail"],
        "tables": [
            {
                "gacha_id": item["gacha_id"],
                "rank": item["rank"],
                "before_rows": item["before_rows"],
                "after_rows": item["after_rows"],
                "changed_weight_count": item["changed_weight_count"],
            }
            for item in report["tables"]
        ],
    }, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0
    updated = update_manifest(manifest, report)
    manifest_output = merge_manifest_bytes(manifest_raw, updated)
    active_dir = repo_root / "assets" / "asset-patch" / "active"
    audit_dir = repo_root / "assets" / "asset-patch" / "audit" / PATCH_ID
    archive_path = active_dir / ARCHIVE_NAME
    audit_path = audit_dir / "report.json"
    if archive_path.exists() or audit_path.exists():
        raise PublishError("refusing to overwrite existing client gacha cleanup output")
    active_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive_raw)
    report["manifest_after_sha256"] = sha256(manifest_output)
    audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = repo_root / "assets" / "asset-patch" / "manifest.json"
    manifest_path.write_bytes(manifest_output)
    print(f"wrote {archive_path}")
    print(f"wrote {audit_path}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
