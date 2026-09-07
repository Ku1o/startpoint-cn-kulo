#!/usr/bin/env python3
"""Append 1.4.99 -> 1.4.100 using sparse, verified effective resources.

This is the immutable first archive. The final .100 release additionally
runs publish_rank_title_conditions_1_4_100.py to append its second archive
to this same version edge, preserving the first archive's original bytes.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

import publish_gacha_pool_cleanup_client_1_4_99 as previous

ROOT = Path(__file__).resolve().parents[2]
PATCH_ID = "abyss-exchange-shop-banners-1.4.100"
ARCHIVE = "pinball-1.4.99-1.4.100-1-abyss-exchange-shop-banners.zip"
LOCKED = {129952, 169980, 169994, 169995, 179981}
NOTE = "rich_text/cnmod_abyss_limited_gacha_note.html.deflate"
BANNERS = (
    ("af/6ad4e513edc45a835d26ae8482ec384ff62ce7", "外层商店入口横幅", (1000, 184),
     "157a2af894b4500cb373ac7af56b34c74e70be757e17a2614058aae5af7d8ca3"),
    ("35/937c7ff9d7006ffa407887910bbec9fc41bc06", "内层觉醒强化页头", (1440, 556),
     "19bef4da76737ab0bdad1cf81d3d5d50759a3a8059dd43ed86d882483d46ec3c"),
)


def build(root: Path):
    patch_root = root / "assets/asset-patch"
    manifest_raw = (patch_root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    assert manifest["cdn_version"] == "1.4.99", "release tail changed"
    assert not (patch_root / "active" / ARCHIVE).exists(), "archive already published"
    assert not (patch_root / "audit" / PATCH_ID).exists(), "audit already published"
    enabled = [p for p in manifest["patches"] if p.get("enabled") and p.get("type") == "patch"]
    assert enabled[-1]["version"] == "1.4.99"
    registered = {name for p in enabled for name in (p.get("chain") or [p.get("archive")]) if name}
    plan = previous.store.build_read_only_plan((root / ".cdn/cn").resolve(), root, "1.4.99", False)
    assert plan.summary()["ok"] and not plan.health.unreachable

    # Match the public accessor actually used by the exchange route, including overlays.
    result = subprocess.run([
        "node", "-e",
        "const {getGachaSync}=require('./out/lib/assets');process.stdout.write(JSON.stringify(Object.fromEntries([990001,990002].map(id=>[id,getGachaSync(id)]))))",
    ], cwd=root, check=True, capture_output=True, encoding="utf8")
    pools = json.loads(result.stdout)
    for source in ("gacha.json", "gacha_cnmod.json"):
        assert json.loads((root / "assets" / source).read_text(encoding="utf8"))["990001"] == pools["990001"]
    assert json.loads((root / "assets/gacha_rank_p5b.json").read_text(encoding="utf8"))["990002"] == pools["990002"]
    collab = {int(c["code_number"]) for c in json.loads((root / "data/character_table.json").read_text(encoding="utf8")) if c.get("source") == "联动"}
    entries = [e for bucket in pools["990001"]["pool"].values() for e in bucket]
    for entry in entries:
        assert entry["isExchangeable"] == (entry["id"] not in LOCKED and (entry["isRateUp"] or entry["id"] in collab))
    assert sum(e["isExchangeable"] for e in entries) == 39

    snapshots = {}
    payloads = {}
    inputs = []

    def read_member(relative):
        entry = plan.entries[("common", relative)]
        # Never use a stray custom archive in .cdn or an unregistered active ZIP.
        if entry.zip_path.is_relative_to(patch_root / "active"):
            assert entry.zip_path.name in registered, entry.zip_path
        else:
            match = re.match(r"pinball-\d+\.\d+\.\d+-(\d+\.\d+\.\d+)-", entry.zip_path.name)
            assert match and tuple(map(int, match[1].split("."))) <= (1, 4, 54), entry.zip_path
        with zipfile.ZipFile(entry.zip_path) as archive:
            raw = archive.read(entry.name)
        inputs.append({"archive": str(entry.zip_path), "member": entry.name, "sha256": previous.sha256(raw), "size": len(raw)})
        return raw

    def read_logical(logical):
        return read_member(previous.member_name(logical).removeprefix("production/upload/"))

    checks = []
    for gacha_id, prefix in (("990001", "cnmod_abyss_limited_gacha"), ("990002", "cnmod_ashen_verdict_gacha")):
        for rank, bucket in ((5, "1"), (4, "2"), (3, "3")):
            logical = f"master/gacha_odds/{prefix}_character_{rank}.orderedmap"
            raw = read_logical(logical)
            odds_id, keys, blocks, rows = previous._parse_nested(raw, logical)
            expected = [previous._client_row(e).split(",") for e in pools[gacha_id]["pool"][bucket]]
            assert len(rows) == len(expected)
            changed = []
            output_blocks = []
            for before, after, block in zip(rows, expected, blocks):
                assert before[:5] + before[6:] == after[:5] + after[6:], f"unexpected non-exchange change {logical}/{before[0]}"
                if before != after:
                    assert gacha_id == "990001", "race policy must remain unchanged"
                    changed.append(int(before[0]))
                    block = zlib.compress(",".join(after).encode("utf8"), 9)
                output_blocks.append(block)
            if changed:
                inner = previous._build_compressed_orderedmap(keys, output_blocks)
                output = previous.core.build_orderedmap_raw_rows(previous.core.OrderedMap(logical, [odds_id], [inner], Path("<1.4.100>")))
                assert previous._parse_nested(output, logical)[3] == expected
                member = previous.member_name(logical)
                payloads[member] = output
                snapshots[member] = raw
            checks.append({"gacha_id": gacha_id, "rank": rank, "logical": logical, "rows": len(rows),
                           "exchangeable_before": sum(r[5] == "true" for r in rows), "exchangeable_after": sum(r[5] == "true" for r in expected),
                           "changed_exchange_ids": changed, "weights_and_other_columns_preserved": True})
    assert [len(c["changed_exchange_ids"]) for c in checks] == [216, 7, 0, 0, 0, 0]

    raw = read_logical(NOTE)
    note = zlib.decompress(raw, -15).decode("utf8")
    old_exchange = "每次抽取累计1点兑换点数；5名首领角色不可兑换，其余★5角色各需250点兑换。"
    new_exchange = "每次抽取累计1点兑换点数；除水魔女、深渊之兽、白虎、魔王、歼灭者外，其余UP角色及池内联动角色可兑换，每名需250点；其余角色不可兑换。"
    old_rates = "其余236名★5角色各为0.050%，合计11.8%。"
    new_rates = "其余231名★5角色的总出现概率为11.8%，各角色具体概率以提供比例页为准。"
    assert note.count(old_exchange) == note.count(old_rates) == 1
    five_star = pools["990001"]["pool"]["1"]
    ordinary = [e for e in five_star if not e["isRateUp"]]
    assert len(ordinary) == 231 and sum(e["odds"] for e in ordinary) == 1180000
    note = note.replace(old_exchange, new_exchange).replace(old_rates, new_rates)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    encoded = compressor.compress(note.encode("utf8")) + compressor.flush()
    assert zlib.decompress(encoded, -15).decode("utf8") == note
    payloads[previous.member_name(NOTE)] = encoded
    snapshots[previous.member_name(NOTE)] = raw

    banner_checks = []
    for relative, label, dimensions, expected_hash in BANNERS:
        member = "production/upload/" + relative
        raw = read_member(relative)
        output = (patch_root / member).read_bytes()
        assert previous.sha256(output) == expected_hash, label
        assert raw[:8] in (b"\x89PNG\r\n\x1a\n", b"\x89png\r\n\x1a\n")
        assert output[:8] == b"\x89PNG\r\n\x1a\n"
        for image in (raw, output):
            assert struct.unpack(">II", image[16:24]) == dimensions
        payloads[member] = output
        snapshots[member] = raw
        banner_checks.append({"label": label, "member": member, "dimensions": dimensions, "sha256": expected_hash,
                              "shared_android_ios_png": True, "donor_bytes_preserved": True})

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for member, payload in sorted(payloads.items()):
            assert member.startswith("production/upload/") and ".." not in Path(member).parts
            info = zipfile.ZipInfo(member, (2026, 9, 6, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    archive_raw = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        assert archive.testzip() is None and archive.namelist() == sorted(payloads)
        assert all(archive.read(name) == raw for name, raw in payloads.items())
    integrity = {"name": ARCHIVE, "size": len(archive_raw), "sha256": previous.sha256(archive_raw), "members": len(payloads), "files": sorted(payloads)}
    record = {"id": PATCH_ID, "type": "patch", "name": "深渊兑换名单与商店横幅 1.4.100",
              "description": "同步深渊池客户端与服务端兑换资格，并更新商店入口及觉醒强化页头横幅。",
              "version": "1.4.100", "depends_on": "1.4.99", "enabled": True,
              "archive": ARCHIVE, "archive_size": len(archive_raw), "chain": [ARCHIVE], "archive_integrity": [integrity],
              "files": sorted(payloads), "changes": [new_exchange, "可兑换39名：17名UP及22名联动（32名五星、7名四星）。", "同步说明页剩余五星数量；卡池成员、权重和竞速池保持原值。", "替换两张已确认的商店横幅，共通PNG供Android与iOS使用。"],
              "created_at": "2026-09-06", "audit": {"directory": f"assets/asset-patch/audit/{PATCH_ID}", "report": "report.json"}}
    # Preserve all published manifest records and their original formatting.
    text = manifest_raw.decode("utf8")
    ending = re.search(r"(\r?\n)  \]\r?\n\}\s*$", text)
    assert ending, "manifest closing structure changed"
    newline = ending[1]
    pos = ending.start()
    rendered = newline.join("    " + line for line in json.dumps(record, ensure_ascii=False, indent=2).splitlines())
    text = text[:pos] + "," + newline + rendered + text[pos:]
    text = text.replace('"cdn_version": "1.4.99"', '"cdn_version": "1.4.100"', 1)
    manifest_output = text.encode("utf8")
    updated = json.loads(manifest_output)
    assert updated["patches"][:-1] == manifest["patches"]
    prior_archives = []
    for item in enabled[-1]["archive_integrity"]:
        path = patch_root / "active" / item["name"]
        assert previous.sha256(path.read_bytes()) == item["sha256"] and path.stat().st_size == item["size"]
        prior_archives.append(item)
    contamination = []
    for path in (root / ".cdn/cn").glob("archive-*-diff/*.zip"):
        match = re.match(r"pinball-\d+\.\d+\.\d+-(\d+\.\d+\.\d+)-", path.name)
        if match and tuple(map(int, match[1].split("."))) > (1, 4, 54):
            contamination.append(str(path.resolve()))
    report = {"schema": "abyss-exchange-shop/v1", "patch_id": PATCH_ID, "base_version": "1.4.99", "target_version": "1.4.100",
              "source_plan": plan.summary(), "source_inputs": inputs, "tables": checks, "banners": banner_checks,
              "rarity_checks": previous._check_rarity_tables(plan, pools), "master_reference_checks": previous._check_master_refs(plan, pools),
              "archive": integrity, "previous_release_integrity": prior_archives,
              "manifest_before_sha256": previous.sha256(manifest_raw), "manifest_after_sha256": previous.sha256(manifest_output),
              "baseline_contamination_not_used_or_modified": contamination,
              "unregistered_active_not_used_or_modified": sorted(p.name for p in (patch_root / "active").glob("*.zip") if p.name not in registered),
              "server_sources": {name: previous.sha256((root / "assets" / name).read_bytes()) for name in ("gacha.json", "gacha_cnmod.json", "gacha_rank_p5b.json")},
              "payloads": [{"member": name, "sha256": previous.sha256(raw), "size": len(raw)} for name, raw in sorted(payloads.items())]}
    return archive_raw, manifest_raw, manifest_output, payloads, snapshots, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    archive, before_manifest, manifest, payloads, snapshots, report = build(ROOT)
    print(json.dumps({"dry_run": not args.apply, "archive": report["archive"], "tables": report["tables"]}, ensure_ascii=False, indent=2))
    if args.apply:
        patch_root = ROOT / "assets/asset-patch"
        scratch = ROOT / "work/cdn-1.4.100"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "manifest.before.json").write_bytes(before_manifest)
        for name, raw in snapshots.items():
            path = scratch / "effective-before" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        for name, raw in payloads.items():
            path = patch_root / name
            if path.exists():
                backup = scratch / "loose-before" / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(path.read_bytes())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (patch_root / "active" / ARCHIVE).write_bytes(archive)
        audit = patch_root / "audit" / PATCH_ID
        audit.mkdir(parents=True)
        (audit / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        (patch_root / "manifest.json").write_bytes(manifest)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    main()
