#!/usr/bin/env python3
"""Append title conditions to the existing .99 -> .100 archive chain.

Run after publish_abyss_exchange_shop_1_4_100.py. Existing published ZIPs
remain immutable; only five condition cells change in one common master.
"""
from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

import publish_gacha_pool_cleanup_client_1_4_99 as codec

ROOT = Path(__file__).resolve().parents[2]
PARENT = "abyss-exchange-shop-banners-1.4.100"
AUDIT = "rank-title-conditions-1.4.100"
ARCHIVE = "pinball-1.4.99-1.4.100-2-rank-title-conditions.zip"
LOGICAL = "master/degree/degree.orderedmap"
IDS = [str(i) for i in range(9900007, 9900012)]


def fields(raw):
    return next(csv.reader([zlib.decompress(raw).decode("utf8")]))


def build(root):
    patch_root = root / "assets/asset-patch"
    manifest_raw = (patch_root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    release = next(p for p in manifest["patches"] if p["id"] == PARENT)
    assert manifest["cdn_version"] == release["version"] == "1.4.100"
    assert release["enabled"] and release["depends_on"] == "1.4.99"
    assert len(release["chain"]) == 1 and len(release["files"]) == 5
    assert not (patch_root / "active" / ARCHIVE).exists()
    assert not (patch_root / "audit" / AUDIT).exists()
    for entry in release["archive_integrity"]:
        raw = (patch_root / "active" / entry["name"]).read_bytes()
        assert len(raw) == entry["size"] and codec.sha256(raw) == entry["sha256"]
    plan = codec.store.build_read_only_plan((root / ".cdn/cn").resolve(), root, "1.4.100", False)
    assert plan.summary()["ok"] and not plan.health.unreachable
    before, source = codec._read_planned(plan, LOGICAL)
    registered = {name for p in manifest["patches"] if p.get("enabled") for name in (p.get("chain") or [p.get("archive")]) if name}
    assert Path(source["archive"]).parent == patch_root / "active"
    assert Path(source["archive"]).name in registered
    ordered = codec.core.read_orderedmap_raw_rows_from_bytes(before, LOGICAL)
    assert len(ordered.keys) == len(set(ordered.keys))
    before_rows = dict(zip(ordered.keys, ordered.rows))
    policy = json.loads((root / "assets/leaderboard_reward_policy.json").read_text(encoding="utf8"))
    condition = policy["titleCondition"]
    assert condition == "获得条件：赛季排行榜结算奖励，具体条件见排行报酬"
    result = subprocess.run(["node", "-e", "const {degreeDefinitions}=require('./out/lib/content-master'); process.stdout.write(JSON.stringify(degreeDefinitions))"], cwd=root, capture_output=True, text=True, encoding="utf8", check=True)
    server = json.loads(result.stdout)
    override = json.loads((root / "assets/degree_rank_p5b.json").read_text(encoding="utf8"))
    changes = []
    images = []
    for key in IDS:
        assert server[key] == override[key] and server[key]["condition"] == condition
        index = ordered.keys.index(key)
        row = fields(ordered.rows[index])
        assert len(row) == 9 and row[0] == server[key]["string_id"] and row[2] == server[key]["name"]
        assert row[4] != condition
        old = row[4]
        row[4] = condition
        output = io.StringIO()
        csv.writer(output, lineterminator="").writerow(row)
        ordered.rows[index] = zlib.compress(output.getvalue().encode("utf8"), 9)
        changes.append({"id": key, "name": row[2], "before_condition": old, "after_condition": condition})
        image_logical = row[8] + ".png"
        image, image_source = codec._read_planned(plan, image_logical)
        images.append({"logical": image_logical, "sha256": codec.sha256(image), "source": image_source})
    after = codec.core.build_orderedmap_raw_rows(ordered)
    check = codec.core.read_orderedmap_raw_rows_from_bytes(after, LOGICAL)
    assert check.keys == ordered.keys
    for key, raw in zip(check.keys, check.rows):
        if key in IDS:
            original, updated = fields(before_rows[key]), fields(raw)
            assert original[:4] + original[5:] == updated[:4] + updated[5:]
            assert updated[4] == condition
        else:
            assert raw == before_rows[key], key
    member = codec.member_name(LOGICAL)
    archive_raw = codec.deterministic_zip({member: after})
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        assert archive.namelist() == [member] and archive.read(member) == after
    integrity = {"name": ARCHIVE, "size": len(archive_raw), "sha256": codec.sha256(archive_raw), "members": 1, "files": [member]}
    updated_release = copy.deepcopy(release)
    updated_release["name"] = "深渊兑换、商店横幅与赛季称号说明 1.4.100"
    updated_release["description"] = "同步深渊兑换名单、两张商店横幅及本期五个赛季称号的获得条件。"
    updated_release["chain"].append(ARCHIVE)
    updated_release["archive_integrity"].append(integrity)
    updated_release["files"] = sorted([*release["files"], member])
    updated_release["changes"].append("同一1.4.100更新步骤追加9900007～9900011称号获得条件：" + condition + "；保留称号名称、图片及其他所有行。")
    updated_release["audit"]["rank_title_conditions"] = f"assets/asset-patch/audit/{AUDIT}/report.json"
    updated_release["audit"]["integrated_release"] = f"assets/asset-patch/audit/{PARENT}/integrated-release.json"
    text = manifest_raw.decode("utf8")
    marker = text.index(f'"id": "{PARENT}"')
    brace = text.rfind("{", 0, marker)
    start = text.rfind("\n", 0, brace) + 1
    _, length = json.JSONDecoder().raw_decode(text[brace:])
    newline = "\r\n" if text[brace + length:brace + length + 2] == "\r\n" else "\n"
    rendered = newline.join("    " + line for line in json.dumps(updated_release, ensure_ascii=False, indent=2).splitlines())
    manifest_output = (text[:start] + rendered + text[brace + length:]).encode("utf8")
    updated_manifest = json.loads(manifest_output)
    assert updated_manifest["cdn_version"] == "1.4.100"
    assert [p for p in updated_manifest["patches"] if p["id"] != PARENT] == [p for p in manifest["patches"] if p["id"] != PARENT]
    report = {"schema": "rank-title-conditions/v1", "version": "1.4.100", "depends_on": "1.4.99", "source": source,
              "logical": LOGICAL, "source_plan": plan.summary(), "rows": len(check.keys), "changed_rows": changes,
              "unchanged_rows": len(check.keys) - 5, "only_condition_column_changed": True,
              "images_preserved": images, "archive": integrity, "payload_sha256": codec.sha256(after),
              "source_files": {name: codec.sha256((root / name).read_bytes()) for name in ("assets/degree_rank_p5b.json", "assets/leaderboard_reward_policy.json")},
              "manifest_before_sha256": codec.sha256(manifest_raw), "manifest_after_sha256": codec.sha256(manifest_output),
              "prior_archives_preserved": release["archive_integrity"],
              "same_version_behavior": "Clients reporting res_ver=1.4.100 receive no diff; local .100 testers must explicitly reacquire resource data. No .101, client cache, or database mutation is performed."}
    integrated = {"version": "1.4.100", "depends_on": "1.4.99", "chain": updated_release["chain"],
                  "archive_integrity": updated_release["archive_integrity"], "total_bytes": sum(i["size"] for i in updated_release["archive_integrity"]),
                  "files": updated_release["files"], "manifest_sha256": codec.sha256(manifest_output),
                  "component_reports": [f"assets/asset-patch/audit/{PARENT}/report.json", f"assets/asset-patch/audit/{AUDIT}/report.json"],
                  "same_version_behavior": report["same_version_behavior"]}
    return before, after, archive_raw, manifest_raw, manifest_output, report, integrated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    before, after, archive, old_manifest, manifest, report, integrated = build(ROOT)
    print(json.dumps({"dry_run": not args.apply, "archive": report["archive"], "changed_rows": report["changed_rows"], "total_bytes": integrated["total_bytes"]}, ensure_ascii=False, indent=2))
    if not args.apply:
        return
    patch_root = ROOT / "assets/asset-patch"
    work = ROOT / "work/cdn-1.4.100-rank-titles"
    work.mkdir(parents=True, exist_ok=True)
    (work / "manifest.before.json").write_bytes(old_manifest)
    (work / "degree.before.orderedmap").write_bytes(before)
    loose = patch_root / codec.member_name(LOGICAL)
    if loose.exists():
        (work / "degree.loose-before.orderedmap").write_bytes(loose.read_bytes())
    loose.parent.mkdir(parents=True, exist_ok=True)
    loose.write_bytes(after)
    (patch_root / "active" / ARCHIVE).write_bytes(archive)
    audit = patch_root / "audit" / AUDIT
    audit.mkdir(parents=True)
    (audit / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    (patch_root / "audit" / PARENT / "integrated-release.json").write_text(json.dumps(integrated, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    (patch_root / "manifest.json").write_bytes(manifest)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    main()
