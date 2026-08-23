#!/usr/bin/env python3
"""Add the reviewed Mana-priced four-star steel product to the unified 1.4.87 edge."""
from __future__ import annotations

import argparse
import copy
import csv
import importlib.util
import io
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


TOOL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_ROOT))

import wf_dev_catalog  # noqa: E402


def load_module(name: str, filename: str):
    path = TOOL_ROOT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


publisher = load_module("lion_1_4_87_shop_publisher", "publish_lion_balance_1_4_87_20260823.py")
reroll = load_module("abyss_reroll_1_4_87_shop_helper", "merge_abyss_reroll_1_4_87_20260823.py")

SOURCE_ROOT = publisher.SOURCE_ROOT
RUNTIME_ROOT = publisher.RUNTIME_ROOT
PATCH_ID = publisher.PATCH_ID
PATCH_VERSION = publisher.PATCH_VERSION
ARCHIVE_NAME = publisher.ARCHIVE_NAME

SHOP_LOGICAL = "master/shop/general_shop.orderedmap"
SHOP_MEMBER = publisher.member_name(SHOP_LOGICAL)
PRODUCT_ID = "9100012"
PRODUCT_ID_INT = int(PRODUCT_ID)
PRODUCT_NAME = "老登专用"
REWARD_ITEM_ID = 12001
MANA_COST_TYPE = 1
MANA_COST = 10_000_000
STOCK = 999
MANIFEST_CHANGE = (
    "交易所新增商品9100012“老登专用”：消耗Mana×1000万，获得★4星铁钢（12001）×1，"
    "客户端单次/累计上限与服务端库存均为999。"
)
CHANGELOG_ROW = (
    "| 2026-08-23 | general_shop | 9100012 | 新增“老登专用”："
    "1000万Mana兑换★4星铁钢1个，库存999 | 1.4.87 | active统一增量包 |"
)


class ShopMergeError(RuntimeError):
    pass


def load_manifest(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    value = json.loads(
        (root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
    )
    matches = [entry for entry in value.get("patches", []) if entry.get("id") == PATCH_ID]
    if value.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
        raise ShopMergeError(f"{root}: unified 1.4.87 manifest entry is missing or ambiguous")
    return value, matches[0]


def client_row_from_template(template_raw: bytes) -> bytes:
    rows = publisher.flat_row(template_raw, SHOP_LOGICAL, "210001")
    if len(rows) != 1 or len(rows[0]) != 47:
        raise ShopMergeError("general_shop 210001 template shape drifted")
    row = list(rows[0])
    if row[29:32] != ["0", "12002", "1"] or row[7] != (
        "item/materials/awaking_crystal/general/equipment_awaking_crystal_5"
    ):
        raise ShopMergeError("general_shop 210001 is no longer the direct five-star steel template")
    row[0] = "(None)"
    row[1] = PRODUCT_NAME
    row[2] = PRODUCT_ID
    row[3] = "1"
    # Reuse the recognized direct-steel GeneralShopProductId.  The key and
    # reward/item fields remain authoritative for listing and fulfillment.
    row[4] = "49"
    row[5] = "★4星铁钢 × 1"
    row[6] = "(None)"
    row[7] = "item/materials/awaking_crystal/general/equipment_awaking_crystal_4"
    row[8] = "4"
    row[9] = str(MANA_COST_TYPE)
    row[10] = str(MANA_COST)
    row[11] = "(None)"
    for offset in range(12, 20, 2):
        row[offset] = "(None)"
        row[offset + 1] = ""
    row[20] = "2015-12-31 23:59:59"
    row[21] = "(None)"
    row[22] = "1"
    row[23] = str(STOCK)
    row[24] = str(STOCK)
    for index in range(25, 29):
        row[index] = "(None)"
    row[29:32] = ["0", str(REWARD_ITEM_ID), "1"]
    for offset in range(32, 47, 3):
        row[offset] = "(None)"
        row[offset + 1] = ""
        row[offset + 2] = ""
    return publisher.build_flat_row([row])


def build_client_shop(terminal_raw: bytes) -> tuple[bytes, bytes]:
    _ordered, raw_rows = publisher.raw_rows(terminal_raw, SHOP_LOGICAL)
    if PRODUCT_ID in raw_rows:
        raise ShopMergeError(f"client general_shop already contains {PRODUCT_ID}")
    template = raw_rows.get("210001")
    if template is None:
        raise ShopMergeError("client general_shop lacks template 210001")
    new_row = client_row_from_template(template)
    output, added, changed = publisher.base.upsert_table_rows(
        terminal_raw, SHOP_LOGICAL, {PRODUCT_ID: new_row}
    )
    if added != [PRODUCT_ID] or changed:
        raise ShopMergeError(f"client general_shop graft drifted: added={added}, changed={changed}")
    return output, new_row


def update_manifest(
    manifest: dict[str, Any], payloads: dict[str, bytes], archive_raw: bytes
) -> bytes:
    value = copy.deepcopy(manifest)
    entry = next(item for item in value["patches"] if item.get("id") == PATCH_ID)
    entry["name"] = "玛格诺斯、角色平衡、战阵奖励、深渊横幅与交易所商品 1.4.87"
    if "交易所商品9100012" not in entry.get("description", ""):
        entry["description"] = entry.get("description", "").rstrip("。") + (
            "；交易所新增Mana购买的★4星铁钢商品9100012，显示名为“老登专用”。"
        )
    changes = entry.setdefault("changes", [])
    if MANIFEST_CHANGE not in changes:
        changes.append(MANIFEST_CHANGE)
    entry["archive_size"] = len(archive_raw)
    entry["files"] = sorted(payloads)
    entry["archive_integrity"] = [{
        "name": ARCHIVE_NAME,
        "size": len(archive_raw),
        "sha256": reroll.sha256_bytes(archive_raw),
        "members": len(payloads),
    }]
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def update_changelog(raw: bytes) -> bytes:
    text = raw.decode("utf-8-sig")
    if CHANGELOG_ROW in text.splitlines():
        return raw
    newline = "\r\n" if "\r\n" in text else "\n"
    marker = f"|---|---|---|---|---|---|{newline}"
    if marker not in text:
        raise ShopMergeError("asset-patch changelog table header drifted")
    return text.replace(marker, marker + CHANGELOG_ROW + newline, 1).encode("utf-8")


def desired_server_item() -> dict[str, Any]:
    return {
        "costs": [],
        "rewards": [{"type": 0, "id": REWARD_ITEM_ID, "count": 1}],
        "availableFrom": "2015-12-31 23:59:59",
        "availableUntil": None,
        "stock": STOCK,
        "userCost": {"type": MANA_COST_TYPE, "amount": MANA_COST},
    }


def build_json_targets() -> dict[str, bytes]:
    shop_path = SOURCE_ROOT / "assets/general_shop.json"
    shop_raw = shop_path.read_bytes()
    shop = json.loads(shop_raw.decode("utf-8-sig"))
    if PRODUCT_ID in shop:
        raise ShopMergeError(f"server general_shop already contains {PRODUCT_ID}")
    shop[PRODUCT_ID] = desired_server_item()

    whitelist_path = SOURCE_ROOT / "assets/cdn_general_shop_whitelist.json"
    whitelist_raw = whitelist_path.read_bytes()
    whitelist = json.loads(whitelist_raw.decode("utf-8-sig"))
    if PRODUCT_ID_INT in whitelist:
        raise ShopMergeError(f"general-shop whitelist already contains {PRODUCT_ID}")
    whitelist = sorted({int(value) for value in whitelist} | {PRODUCT_ID_INT})

    required_path = TOOL_ROOT / "publish_required_keys.json"
    required_raw = required_path.read_bytes()
    required = json.loads(required_raw.decode("utf-8-sig"))
    required_keys = required["tables"][SHOP_LOGICAL]["required_keys"]
    if PRODUCT_ID in required_keys:
        raise ShopMergeError(f"publish required-key policy already contains {PRODUCT_ID}")
    required_keys.append(PRODUCT_ID)
    required_keys.sort(key=int)
    return {
        "assets/general_shop.json": publisher.json_output(shop_raw, shop),
        "assets/cdn_general_shop_whitelist.json": publisher.json_output(whitelist_raw, whitelist),
        "tools/fantasy-gauntlet-mod-tools/publish_required_keys.json": publisher.json_output(
            required_raw, required
        ),
    }


def build_source_candidate() -> tuple[dict[str, bytes], dict[str, bytes], bytes, dict[str, Any]]:
    publisher.verify_existing_release()
    manifest, entry = load_manifest(SOURCE_ROOT)
    if len(entry["files"]) != 120:
        raise ShopMergeError(f"expected the 120-member pre-shop build, got {len(entry['files'])}")
    archive_path = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
    with zipfile.ZipFile(archive_path) as archive:
        old_payloads = {name: archive.read(name) for name in archive.namelist()}
    if SHOP_MEMBER in old_payloads:
        raise ShopMergeError("unified archive already contains general_shop")
    terminal, sources = publisher.base.terminal_members(SOURCE_ROOT, manifest, {SHOP_MEMBER})
    if SHOP_MEMBER not in terminal:
        raise ShopMergeError("source chain lacks terminal general_shop")
    shop_payload, client_row = build_client_shop(terminal[SHOP_MEMBER])
    payloads = {**old_payloads, SHOP_MEMBER: shop_payload}
    if len(payloads) != 121:
        raise ShopMergeError(f"unified member count drifted: {len(payloads)}")
    archive_raw = publisher.zip_payloads(payloads)
    targets = build_json_targets()
    targets.update({
        f"assets/asset-patch/production/upload/{SHOP_MEMBER.split('/', 2)[2]}": shop_payload,
        f"assets/asset-patch/active/{ARCHIVE_NAME}": archive_raw,
        "assets/asset-patch/changelog.md": update_changelog(
            (SOURCE_ROOT / "assets/asset-patch/changelog.md").read_bytes()
        ),
        "assets/asset-patch/manifest.json": update_manifest(manifest, payloads, archive_raw),
    })
    return targets, old_payloads, terminal[SHOP_MEMBER], {
        "terminal_source": sources[SHOP_MEMBER],
        "client_row_sha256": reroll.sha256_bytes(client_row),
        "archive_size": len(archive_raw),
        "archive_sha256": reroll.sha256_bytes(archive_raw),
        "members": len(payloads),
    }


def verify_source(
    old_payloads: dict[str, bytes] | None = None,
    old_shop_payload: bytes | None = None,
) -> dict[str, Any]:
    base_report = publisher.verify_existing_release()
    manifest, entry = load_manifest(SOURCE_ROOT)
    member_count = len(entry["files"])
    if member_count not in {121, 134} or SHOP_MEMBER not in entry["files"]:
        raise ShopMergeError("published unified archive does not register the general_shop member")
    archive_path = SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None or archive.namelist() != entry["files"]:
            raise ShopMergeError("published unified archive integrity/order drifted")
        payloads = {name: archive.read(name) for name in archive.namelist()}
    if old_payloads is not None:
        for member, expected in old_payloads.items():
            if payloads.get(member) != expected:
                raise ShopMergeError(f"pre-existing unified member changed: {member}")
    _ordered, rows = publisher.raw_rows(payloads[SHOP_MEMBER], SHOP_LOGICAL)
    if PRODUCT_ID not in rows:
        raise ShopMergeError("client general_shop row 9100012 is missing")
    row = publisher.flat_row(rows[PRODUCT_ID], SHOP_LOGICAL, PRODUCT_ID)
    if len(row) != 1:
        raise ShopMergeError("client product row is not flat")
    values = row[0]
    if (
        values[1] != PRODUCT_NAME
        or values[2] != PRODUCT_ID
        or values[7] != "item/materials/awaking_crystal/general/equipment_awaking_crystal_4"
        or values[8:11] != ["4", "1", str(MANA_COST)]
        or values[12:20] != ["(None)", "", "(None)", "", "(None)", "", "(None)", ""]
        or values[23:25] != [str(STOCK), str(STOCK)]
        or values[29:32] != ["0", str(REWARD_ITEM_ID), "1"]
    ):
        raise ShopMergeError(f"client product row drifted: {values}")
    if old_shop_payload is not None:
        before_ordered, before_rows = publisher.raw_rows(old_shop_payload, SHOP_LOGICAL)
        if list(rows) != list(before_rows) + [PRODUCT_ID]:
            raise ShopMergeError("client general_shop key order changed beyond appending 9100012")
        for key, expected in before_rows.items():
            if rows.get(key) != expected:
                raise ShopMergeError(f"existing client general_shop row changed: {key}")

    server = json.loads((SOURCE_ROOT / "assets/general_shop.json").read_text(encoding="utf-8-sig"))
    whitelist = json.loads(
        (SOURCE_ROOT / "assets/cdn_general_shop_whitelist.json").read_text(encoding="utf-8-sig")
    )
    required = json.loads((TOOL_ROOT / "publish_required_keys.json").read_text(encoding="utf-8-sig"))
    if server.get(PRODUCT_ID) != desired_server_item():
        raise ShopMergeError("server general_shop product drifted")
    if whitelist.count(PRODUCT_ID_INT) != 1:
        raise ShopMergeError("general-shop whitelist product is missing or duplicated")
    if required["tables"][SHOP_LOGICAL]["required_keys"].count(PRODUCT_ID) != 1:
        raise ShopMergeError("publish required-key policy product is missing or duplicated")
    changelog = (SOURCE_ROOT / "assets/asset-patch/changelog.md").read_text(encoding="utf-8-sig")
    if changelog.splitlines().count(CHANGELOG_ROW) != 1 or entry["changes"].count(MANIFEST_CHANGE) != 1:
        raise ShopMergeError("shop changelog/manifest registration is not unique")
    reroll_present = member_count == 134
    if reroll_present:
        reroll_report = reroll.verify_release()
    elif set(payloads) & reroll.NEW_MEMBERS:
        raise ShopMergeError("direct-rollback build still contains abyss reroll members")
    return {
        **base_report,
        "members": len(payloads),
        "archive_size": archive_path.stat().st_size,
        "archive_sha256": reroll.sha256_file(archive_path),
        "product": {
            "id": PRODUCT_ID_INT,
            "name": PRODUCT_NAME,
            "mana_cost": MANA_COST,
            "reward_item_id": REWARD_ITEM_ID,
            "reward_count": 1,
            "stock": STOCK,
        },
        "reroll_chain": reroll_report["chain"] if reroll_present else None,
        "reroll_removed_members": 0 if reroll_present else len(reroll.NEW_MEMBERS),
    }


def apply_source() -> dict[str, Any]:
    targets, old_payloads, old_shop_payload, report = build_source_candidate()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TOOL_ROOT / "work" / f"general-shop-1.4.87-backup-{stamp}"
    reroll.apply_file_targets(
        SOURCE_ROOT, targets, backup, "assets/asset-patch/manifest.json"
    )
    try:
        verification = verify_source(old_payloads, old_shop_payload)
    except Exception:
        existence = json.loads((backup / "existence.json").read_text(encoding="utf-8"))
        for relative in reversed(list(targets)):
            target = SOURCE_ROOT / relative
            if existence[relative]:
                reroll.atomic_write(target, (backup / relative).read_bytes())
            elif target.is_file():
                target.unlink()
        raise
    report.update({"backup": str(backup), "verification": verification})
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def verify_runtime_catalog(out_dir: Path, expected_size: int) -> dict[str, Any]:
    return reroll.verify_runtime_catalog(out_dir, expected_size)


def sync_runtime() -> dict[str, Any]:
    verification = verify_source()
    _source_manifest, source_entry = load_manifest(SOURCE_ROOT)
    runtime_manifest, _runtime_entry = load_manifest(RUNTIME_ROOT)
    merged_manifest = copy.deepcopy(runtime_manifest)
    merged_manifest["patches"] = [
        copy.deepcopy(source_entry) if item.get("id") == PATCH_ID else item
        for item in merged_manifest["patches"]
    ]
    merged_manifest["cdn_version"] = PATCH_VERSION
    targets = {
        "assets/asset-patch/manifest.json": (
            json.dumps(merged_manifest, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8"),
        "assets/asset-patch/changelog.md": update_changelog(
            (RUNTIME_ROOT / "assets/asset-patch/changelog.md").read_bytes()
        ),
        f"assets/asset-patch/active/{ARCHIVE_NAME}": (
            SOURCE_ROOT / "assets/asset-patch/active" / ARCHIVE_NAME
        ).read_bytes(),
        f"assets/asset-patch/{SHOP_MEMBER}": (
            SOURCE_ROOT / "assets/asset-patch" / SHOP_MEMBER
        ).read_bytes(),
        "assets/general_shop.json": (SOURCE_ROOT / "assets/general_shop.json").read_bytes(),
        "assets/cdn_general_shop_whitelist.json": (
            SOURCE_ROOT / "assets/cdn_general_shop_whitelist.json"
        ).read_bytes(),
        "tools/fantasy-gauntlet-mod-tools/publish_required_keys.json": (
            TOOL_ROOT / "publish_required_keys.json"
        ).read_bytes(),
    }
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = RUNTIME_ROOT / ".codex-backups" / f"{stamp}-general-shop-1.4.87"
    catalog_dir = RUNTIME_ROOT / "assets/asset-patch/dev-catalog"
    catalog_backup = backup / "catalog-before"
    cache_path = RUNTIME_ROOT / ".cdn/dev-catalog-digest-cache.json"
    cache_existed = cache_path.is_file()
    reroll.apply_file_targets(
        RUNTIME_ROOT, targets, backup / "files", "assets/asset-patch/manifest.json"
    )
    catalog_existing = reroll.snapshot_tree(catalog_dir, catalog_backup)
    if cache_existed:
        cache_backup = backup / "dev-catalog-digest-cache.json"
        cache_backup.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(cache_path, cache_backup)
    try:
        manifest_path, issues, summary = wf_dev_catalog.emit_dev_catalog(
            RUNTIME_ROOT / ".cdn/cn",
            RUNTIME_ROOT / "assets/asset-patch/active",
            catalog_dir,
            digest_mode="cache",
            allow_issues=True,
        )
        if manifest_path is None:
            raise ShopMergeError("runtime dev catalog was not emitted")
        catalog = verify_runtime_catalog(catalog_dir, verification["archive_size"])
        _runtime_value, runtime_entry = load_manifest(RUNTIME_ROOT)
        if runtime_entry != source_entry:
            raise ShopMergeError("runtime unified manifest entry differs from source")
        for relative, expected in targets.items():
            if (RUNTIME_ROOT / relative).read_bytes() != expected:
                raise ShopMergeError(f"runtime readback drifted: {relative}")
    except Exception:
        existence = json.loads(
            (backup / "files/existence.json").read_text(encoding="utf-8")
        )
        for relative in reversed(list(targets)):
            target = RUNTIME_ROOT / relative
            if existence[relative]:
                reroll.atomic_write(target, (backup / "files" / relative).read_bytes())
            elif target.is_file():
                target.unlink()
        reroll.restore_tree_files(catalog_dir, catalog_backup, catalog_existing)
        if cache_existed:
            reroll.atomic_write(cache_path, (backup / "dev-catalog-digest-cache.json").read_bytes())
        elif cache_path.is_file():
            cache_path.unlink()
        raise
    report = {
        "runtime_root": str(RUNTIME_ROOT),
        "backup": str(backup),
        "paths": len(targets),
        "catalog": catalog,
        "catalog_issues": len(issues),
        "catalog_summary": summary,
        "verification": verification,
    }
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--audit", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--verify-existing", action="store_true")
    modes.add_argument("--sync-runtime", action="store_true")
    args = parser.parse_args()
    if args.audit:
        targets, _old_payloads, _old_shop, report = build_source_candidate()
        result = {**report, "target_paths": len(targets), "mode": "audit"}
    elif args.apply:
        result = apply_source()
    elif args.verify_existing:
        result = verify_source()
    else:
        result = sync_runtime()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
