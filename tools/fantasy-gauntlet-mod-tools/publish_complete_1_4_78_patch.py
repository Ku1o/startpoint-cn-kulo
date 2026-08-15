#!/usr/bin/env python3
"""Publish the unreleased, consolidated 1.4.77 -> 1.4.78 client patch.

The working store was built by key-merging the Thunder Dragon/Abyss-gacha
release onto the local 1.4.78 draft, then adding the reward-preview and
Fantasy-shop changes.  This publisher proves that every touched master table
preserves its 1.4.77 rows before replacing the unpublished icon-only edge.
It reads the large CDN only to resolve the 1.4.77 preimages and never writes
there; output is limited to assets/asset-patch/active and manifest.json.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))
import wf_mod_tool as core  # noqa: E402
import wf_quest_lib as quest  # noqa: E402
import wf_store_materialize as materialize  # noqa: E402
import publish_fantasy_icon_trim_patch as icon_trim  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
PATCH_ROOT = ROOT / "assets" / "asset-patch"
STAGED_ROOT = PATCH_ROOT / "production"
ACTIVE_ROOT = PATCH_ROOT / "active"
MANIFEST_PATH = PATCH_ROOT / "manifest.json"
IMPORT_REPORT = STAGED_ROOT / "thunder-dragon-abyss-gacha-draft-report.json"
WORK_ROOT = MODULE_DIR / "work" / "complete-1.4.78"

BASE_VERSION = "1.4.77"
PATCH_VERSION = "1.4.78"
OLD_PATCH_ID = "fantasy-equipment-icon-trim-1.4.78"
PATCH_ID = "complete-content-1.4.78"
TAG = "0816-thunder-abyss-fantasy"
CREATED_AT = "2026-08-16"
CI_ARCHIVE_BYTES = 5 << 20
MAX_ARCHIVE_BYTES = CI_ARCHIVE_BYTES
ZIP_TIMESTAMP = (2026, 8, 16, 0, 0, 0)

ROOT_DIRECTORY = {
    "common": "upload",
    "medium": "medium_upload",
    "android": "android_upload",
}
ROOT_ORDER = ("common", "medium", "android")
MEMBER_RE = re.compile(
    r"^production/(upload|medium_upload|android_upload)/[0-9a-f]{2}/[0-9a-f]{38}$"
)

FOLDER_LOGICAL = "master/quest/event/rush_event_quest_folder.orderedmap"
SHOP_LOGICAL = "master/shop/event_item_shop.orderedmap"
TRIM_LOGICAL = "master/generated/trimmed_image.orderedmap"
FANTASY_TICKET_SHOP_IDS = ("9700212", "9700312")
ABYSS_TICKET_SHOP_IDS = ("9700116", "9700117")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _archive_names(patch: dict) -> list[str]:
    chain = patch.get("chain")
    if isinstance(chain, list) and all(isinstance(name, str) for name in chain):
        return list(chain)
    archive = patch.get("archive")
    return [archive] if isinstance(archive, str) else []


def _read_plan_payload(entry: materialize.PlannedEntry) -> bytes:
    with zipfile.ZipFile(entry.zip_path) as archive:
        info = archive.getinfo(entry.name)
        if info.file_size != entry.size or info.CRC != entry.crc:
            raise RuntimeError(f"1.4.77 preimage changed after planning: {entry.name}")
        return archive.read(info)


def collect_staged() -> dict[tuple[str, str], bytes]:
    staged: dict[tuple[str, str], bytes] = {}
    for root in ROOT_ORDER:
        directory = STAGED_ROOT / ROOT_DIRECTORY[root]
        if not directory.is_dir():
            raise FileNotFoundError(f"staged store root is missing: {directory}")
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(directory).as_posix()
            if re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{38}", relative) is None:
                raise ValueError(f"unexpected staged path: {path}")
            staged[(root, relative)] = path.read_bytes()
    if len(staged) != 97:
        raise ValueError(f"expected 97 staged client files, found {len(staged)}")
    return staged


def member_name(root: str, relative: str) -> str:
    return f"production/{ROOT_DIRECTORY[root]}/{relative}"


def staged_table(staged: dict[tuple[str, str], bytes], logical: str) -> bytes:
    key = ("common", quest.hashed_rel(logical))
    try:
        return staged[key]
    except KeyError as error:
        raise ValueError(f"staged master table is missing: {logical} ({key[1]})") from error


def audit_append_only_table(
    logical: str,
    base_payload: bytes | None,
    final_payload: bytes,
    added_keys: list[str],
) -> dict:
    final = core.read_orderedmap_raw_rows_from_bytes(final_payload, logical)
    if base_payload is None:
        base_keys: tuple[str, ...] = ()
        base_rows: tuple[bytes, ...] = ()
    else:
        base = core.read_orderedmap_raw_rows_from_bytes(base_payload, logical)
        base_keys = tuple(base.keys)
        base_rows = tuple(base.rows)
    if tuple(final.keys[: len(base_keys)]) != base_keys:
        raise ValueError(f"base key order rolled back/reordered: {logical}")
    if tuple(final.rows[: len(base_rows)]) != base_rows:
        raise ValueError(f"base rows changed while merging: {logical}")
    if tuple(final.keys[len(base_keys) :]) != tuple(added_keys):
        raise ValueError(
            f"unexpected additions in {logical}: "
            f"{final.keys[len(base_keys):]!r} != {added_keys!r}"
        )
    if len(set(final.keys)) != len(final.keys):
        raise ValueError(f"duplicate orderedmap keys: {logical}")
    return {
        "logical": logical,
        "baseRows": len(base_keys),
        "addedKeys": list(added_keys),
        "finalRows": len(final.keys),
        "sha256": sha256_bytes(final_payload),
    }


def _csv_row(leaf: str | bytes) -> list[str]:
    if isinstance(leaf, bytes):
        leaf = leaf.decode("utf-8")
    rows = core.read_csv_lines(leaf)
    if len(rows) != 1:
        raise ValueError("expected exactly one CSV row")
    return rows[0]


def audit_folder_table(base_payload: bytes, final_payload: bytes) -> dict:
    logical = FOLDER_LOGICAL
    base_raw = core.read_orderedmap_raw_rows_from_bytes(base_payload, logical)
    final_raw = core.read_orderedmap_raw_rows_from_bytes(final_payload, logical)
    if base_raw.keys != final_raw.keys:
        raise ValueError("rush folder outer keys changed")
    target = "700099"
    if target not in base_raw.keys:
        raise ValueError("1.4.77 has no Deep Abyss folder")
    changed = []
    for key, before, after in zip(base_raw.keys, base_raw.rows, final_raw.rows):
        if before != after:
            changed.append(key)
    if changed != [target]:
        raise ValueError(f"rush folder changed unexpected outer rows: {changed}")

    base = quest.parse_node(base_payload)
    final = quest.parse_node(final_payload)
    if not isinstance(base, dict) or not isinstance(final, dict):
        raise ValueError("rush folder is not an orderedmap")
    if list(base[target]) != list(final[target]):
        raise ValueError("Deep Abyss folder keys changed")
    for key in base[target]:
        if key != "1" and base[target][key] != final[target][key]:
            raise ValueError(f"Deep Abyss non-target folder changed: {key}")
    before = _csv_row(base[target]["1"])
    after = _csv_row(final[target]["1"])
    if len(before) != 37 or len(after) != 37:
        raise ValueError("Deep Abyss folder row must have 37 columns")
    if before[:7] != after[:7]:
        raise ValueError("Deep Abyss folder metadata changed")
    if after[7:16] != ["0", "99", "1500", "0", "2370099", "50", "0", "11003", "2"]:
        raise ValueError(f"Deep Abyss fixed preview mismatch: {after[7:16]}")
    if any(after[index:index + 3] != ["(None)", "", "(None)"] for index in range(16, 37, 3)):
        raise ValueError("Deep Abyss unused reward slots are not empty")
    return {
        "logical": logical,
        "changedOuterKeys": [target],
        "fixedPreview": [[99, 1500], [2370099, 50], [11003, 2]],
        "sha256": sha256_bytes(final_payload),
    }


def audit_shop_rows(final_payload: bytes) -> None:
    table = core.read_orderedmap_file_from_bytes(final_payload)
    expected = {
        "9700212": ("0", "300098"),
        "9700312": ("6", "700098"),
    }
    for shop_id, (kind, event_id) in expected.items():
        row = _csv_row(table[shop_id])
        checks = {
            0: kind,
            1: event_id,
            7: "深渊十连券×3",
            8: shop_id,
            10: "12",
            18: "2370097",
            19: "1",
            29: "9999",
            30: "9999",
            32: "0",
            33: "999014",
            34: "3",
        }
        for index, value in checks.items():
            if row[index] != value:
                raise ValueError(f"Fantasy ticket shop {shop_id} c{index}: {row[index]!r} != {value!r}")


def audit_trim_rows(final_payload: bytes) -> None:
    table = core.read_orderedmap_raw_rows_from_bytes(final_payload, TRIM_LOGICAL)
    rows = dict(zip(table.keys, table.rows))
    expected = icon_trim.TRIM_ROW.encode("utf-8")
    for key in icon_trim.icon_trim_keys():
        row = rows.get(key)
        if row is None or zlib.decompress(row) != expected:
            raise ValueError(f"Fantasy trim row is missing or wrong: {key}")


def audit_against_base(
    staged: dict[tuple[str, str], bytes],
    plan: materialize.MaterializePlan,
    import_report: dict,
) -> dict:
    if plan.tail != BASE_VERSION or plan.health.issues or plan.health.unreachable:
        raise ValueError(
            f"unsafe base plan: tail={plan.tail} issues={plan.health.issues} "
            f"unreachable={plan.health.unreachable}"
        )
    changed = 0
    base_hits = 0
    new_files = 0
    preimages: dict[tuple[str, str], bytes] = {}
    for key, payload in staged.items():
        entry = plan.entries.get(key)
        if entry is None:
            new_files += 1
            continue
        base_hits += 1
        base_payload = _read_plan_payload(entry)
        preimages[key] = base_payload
        if base_payload == payload:
            raise ValueError(f"staged file is unchanged from 1.4.77: {key}")
        changed += 1
    changed += new_files
    if changed != len(staged) or base_hits != 26 or new_files != 71:
        raise ValueError(
            f"unexpected staged/base split: changed={changed} baseHits={base_hits} new={new_files}"
        )

    tables = import_report.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("import report tables are missing")
    table_audits = []
    for logical, metadata in tables.items():
        if not isinstance(metadata, dict):
            raise ValueError(f"bad table report: {logical}")
        additions = list(metadata.get("addedKeys") or [])
        if logical == TRIM_LOGICAL:
            additions = list(icon_trim.icon_trim_keys()) + additions
        elif logical == SHOP_LOGICAL:
            additions += list(FANTASY_TICKET_SHOP_IDS)
        relative = quest.hashed_rel(logical)
        table_audits.append(
            audit_append_only_table(
                logical,
                preimages.get(("common", relative)),
                staged_table(staged, logical),
                additions,
            )
        )

    folder_relative = quest.hashed_rel(FOLDER_LOGICAL)
    folder_base = preimages.get(("common", folder_relative))
    if folder_base is None:
        raise ValueError("1.4.77 Deep Abyss folder preimage is missing")
    folder_audit = audit_folder_table(folder_base, staged_table(staged, FOLDER_LOGICAL))
    audit_shop_rows(staged_table(staged, SHOP_LOGICAL))
    audit_trim_rows(staged_table(staged, TRIM_LOGICAL))
    return {
        "baseVersion": BASE_VERSION,
        "basePlanFiles": len(plan.entries),
        "basePlanBytes": sum(entry.size for entry in plan.entries.values()),
        "stagedFiles": len(staged),
        "changedExistingFiles": base_hits,
        "newFiles": new_files,
        "tables": table_audits,
        "folder": folder_audit,
    }


def _deflated_size(payload: bytes) -> int:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return len(compressor.compress(payload) + compressor.flush())


def _estimated_zip_size(entries: list[tuple[str, bytes]]) -> int:
    # Local header + central directory entry + EOCD. writestr(bytes) writes no
    # data descriptor, so this is exact for non-ZIP64 archives.
    return 22 + sum(
        _deflated_size(payload) + 76 + 2 * len(name.encode("utf-8"))
        for name, payload in entries
    )


def plan_parts(staged: dict[tuple[str, str], bytes]) -> list[list[tuple[str, bytes]]]:
    parts: list[list[tuple[str, bytes]]] = []
    for root in ROOT_ORDER:
        candidates = [
            (member_name(root, relative), payload)
            for (member_root, relative), payload in sorted(staged.items())
            if member_root == root
        ]
        current: list[tuple[str, bytes]] = []
        for entry in candidates:
            proposed = current + [entry]
            if current and _estimated_zip_size(proposed) > MAX_ARCHIVE_BYTES:
                parts.append(current)
                current = [entry]
            else:
                current = proposed
            if _estimated_zip_size(current) > MAX_ARCHIVE_BYTES:
                raise ValueError(f"single client asset exceeds archive cap: {entry[0]}")
        if current:
            parts.append(current)
    return parts


def build_zip(entries: list[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in entries:
            if MEMBER_RE.fullmatch(name) is None or ".cdn" in name.lower() or name.lower().endswith(".apk"):
                raise ValueError(f"unsafe archive member: {name}")
            info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    result = output.getvalue()
    if len(result) > MAX_ARCHIVE_BYTES or len(result) > CI_ARCHIVE_BYTES:
        raise ValueError(f"archive exceeds size cap: {len(result)}")
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        if archive.namelist() != [name for name, _payload in entries]:
            raise RuntimeError("archive member order changed")
        for name, payload in entries:
            if archive.read(name) != payload:
                raise RuntimeError(f"archive readback mismatch: {name}")
    return result


def archive_name(sequence: int) -> str:
    return f"pinball-{BASE_VERSION}-{PATCH_VERSION}-{sequence}-{TAG}.zip"


def build_archives(staged: dict[tuple[str, str], bytes]) -> list[tuple[str, bytes, list[str]]]:
    result = []
    for sequence, entries in enumerate(plan_parts(staged), start=1):
        payload = build_zip(entries)
        result.append((archive_name(sequence), payload, [name for name, _ in entries]))
    names = [member for _name, _payload, members in result for member in members]
    expected = sorted(member_name(root, relative) for root, relative in staged)
    if sorted(names) != expected or len(names) != len(set(names)):
        raise RuntimeError("archive parts do not exactly cover the staged working store")
    return result


def build_patch_entry(archives: list[tuple[str, bytes, list[str]]]) -> dict:
    names = [name for name, _payload, _members in archives]
    members = sorted(member for _name, _payload, group in archives for member in group)
    return {
        "id": PATCH_ID,
        "type": "patch",
        "name": "雷龙、深渊扭蛋与幻想连战完整更新 1.4.78",
        "description": (
            "以未发布的1.4.77终态为基线，逐键合并雷龙拉姆斯、深渊限定扭蛋、"
            "新券与幻想连战兑换商品，并保留幻想装备图标生命周期修复；不覆盖既有玩法。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "chain": names,
        "archive_size": sum(len(payload) for _name, payload, _members in archives),
        "files": members,
        "changes": [
            "保留11张幻想装备图标的完整画布裁剪记录，修复长时间游玩后图标消失。",
            "新增雷属性角色拉姆斯（139998）及其角色、技能、语音、立绘和战斗资源。",
            "新增深渊限定扭蛋（990001）、深渊单抽券（999013）与深渊十连券（999014）。",
            "深渊连战固定通关展示统一为梦境纹章×1500、深渊代币×50、★5破星结晶碎片×2。",
            "幻想连战单人/多人商店新增究极图腾×1兑换深渊十连券×3，库存9999且共用购买记录。",
            "全部主表按1.4.77逐键合并；未归属行保持原键序与原始压缩字节，不回滚既有玩法。",
            "不包含.cdn目录、APK或未修改资源。",
        ],
        "created_at": CREATED_AT,
        "archive_integrity": [
            {
                "name": name,
                "size": len(payload),
                "sha256": sha256_bytes(payload),
                "members": len(members_in_archive),
            }
            for name, payload, members_in_archive in archives
        ],
    }


def replace_manifest_entry(manifest: dict, patch_entry: dict) -> tuple[dict, list[str]]:
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        raise ValueError("manifest patches must be an array")
    if manifest.get("cdn_version") != PATCH_VERSION:
        raise ValueError(f"manifest tail must already be {PATCH_VERSION}")
    indexes = [
        index for index, patch in enumerate(patches)
        if isinstance(patch, dict) and patch.get("id") in {OLD_PATCH_ID, PATCH_ID}
    ]
    if len(indexes) != 1:
        raise ValueError(f"expected one replaceable 1.4.78 patch, found {indexes}")
    index = indexes[0]
    current = patches[index]
    if current.get("version") != PATCH_VERSION or current.get("depends_on") != BASE_VERSION:
        raise ValueError("replaceable patch is not the 1.4.77 -> 1.4.78 edge")
    old_names = _archive_names(current)
    result = copy.deepcopy(manifest)
    result["patches"][index] = patch_entry
    result["cdn_version"] = PATCH_VERSION
    return result, old_names


def validate_manifest_archives(manifest: dict, active_root: Path) -> None:
    matches = [patch for patch in manifest.get("patches", []) if patch.get("id") == PATCH_ID]
    if len(matches) != 1:
        raise ValueError("published complete 1.4.78 entry is missing or duplicated")
    patch = matches[0]
    chain = _archive_names(patch)
    receipts = patch.get("archive_integrity")
    if not isinstance(receipts, list) or len(receipts) != len(chain):
        raise ValueError("archive integrity list mismatch")
    final: dict[str, bytes] = {}
    total_size = 0
    for name, receipt in zip(chain, receipts):
        path = active_root / name
        payload = path.read_bytes()
        total_size += len(payload)
        if len(payload) != receipt.get("size") or sha256_bytes(payload) != receipt.get("sha256"):
            raise ValueError(f"archive receipt mismatch: {name}")
        if len(payload) > CI_ARCHIVE_BYTES:
            raise ValueError(f"archive exceeds 5MiB: {name}")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if any(info.is_dir() or MEMBER_RE.fullmatch(info.filename) is None for info in infos):
                raise ValueError(f"archive has invalid member: {name}")
            if len(infos) != receipt.get("members"):
                raise ValueError(f"archive member receipt mismatch: {name}")
            for info in infos:
                if info.filename in final:
                    raise ValueError(f"duplicate archive member: {info.filename}")
                final[info.filename] = archive.read(info)
    if total_size != patch.get("archive_size"):
        raise ValueError("combined archive size mismatch")
    if sorted(final) != sorted(patch.get("files") or []):
        raise ValueError("manifest files do not match archive members")


def write_report(report: dict) -> None:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    target = WORK_ROOT / "report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish(cdn_root: Path) -> dict:
    staged = collect_staged()
    import_report = load_json(IMPORT_REPORT)
    plan = materialize._build_plan(cdn_root.resolve(), ROOT.resolve(), BASE_VERSION, False)
    audit = audit_against_base(staged, plan, import_report)
    archives = build_archives(staged)
    patch_entry = build_patch_entry(archives)
    original_manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest = json.loads(original_manifest_bytes.decode("utf-8-sig"))
    updated_manifest, old_names = replace_manifest_entry(manifest, patch_entry)

    new_names = [name for name, _payload, _members in archives]
    stale_names = sorted(set(old_names) - set(new_names))
    if any(Path(name).name != name for name in old_names + new_names):
        raise ValueError("archive names must not contain directories")
    old_payloads = {
        name: (ACTIVE_ROOT / name).read_bytes()
        for name in old_names
        if (ACTIVE_ROOT / name).is_file()
    }

    ACTIVE_ROOT.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".complete-1.4.78-", dir=ACTIVE_ROOT))
    manifest_tmp = MANIFEST_PATH.with_name(".manifest.complete-1.4.78.tmp")
    moved: list[str] = []
    try:
        for name, payload, _members in archives:
            (staging / name).write_bytes(payload)
        manifest_tmp.write_text(
            json.dumps(updated_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for name in new_names:
            os.replace(staging / name, ACTIVE_ROOT / name)
            moved.append(name)
        os.replace(manifest_tmp, MANIFEST_PATH)
        for name in stale_names:
            path = ACTIVE_ROOT / name
            if path.is_file():
                path.unlink()
        validate_manifest_archives(load_json(MANIFEST_PATH), ACTIVE_ROOT)
    except BaseException:
        MANIFEST_PATH.write_bytes(original_manifest_bytes)
        for name in moved:
            path = ACTIVE_ROOT / name
            if path.is_file():
                path.unlink()
        for name, payload in old_payloads.items():
            (ACTIVE_ROOT / name).write_bytes(payload)
        raise
    finally:
        manifest_tmp.unlink(missing_ok=True)
        if staging.is_dir():
            try:
                staging.rmdir()
            except OSError:
                pass

    output_report = {
        "schemaVersion": 1,
        "published": True,
        "from": BASE_VERSION,
        "to": PATCH_VERSION,
        "audit": audit,
        "archives": patch_entry["archive_integrity"],
        "archiveBytes": patch_entry["archive_size"],
        "files": len(patch_entry["files"]),
        "removedUnpublishedArchives": stale_names,
        "manifestSha256": sha256_bytes(MANIFEST_PATH.read_bytes()),
    }
    write_report(output_report)
    return output_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cdn", type=Path, required=True, help="read-only CN CDN root")
    args = parser.parse_args()
    report = publish(args.cdn)
    print(
        f"published {report['from']} -> {report['to']}: "
        f"files={report['files']} archives={len(report['archives'])} "
        f"bytes={report['archiveBytes']}"
    )
    for receipt in report["archives"]:
        print(
            f"  {receipt['name']} size={receipt['size']} "
            f"members={receipt['members']} sha256={receipt['sha256']}"
        )
    print(f"manifest sha256={report['manifestSha256']}")
    print(f"audit report={WORK_ROOT / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
