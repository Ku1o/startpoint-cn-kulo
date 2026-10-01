"""Publish the Five Boss stage reward preview against the effective CDN chain."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
import zlib
from pathlib import Path

import prepare_content as p


LOGICAL_SCORE = "master/reward/score_reward.orderedmap"
LOGICAL_QUEST = "master/quest/boss_battle_quest.orderedmap"
PREVIEW_GROUP = "590010000"
# 1099001 is the public Five Boss entry. 1099002/1099003 are internal scene
# rows and the remaining IDs belong to unrelated boss-battle content.
QUEST_IDS = (1099001,)
PREVIEW_ROWS = (
    ("five_boss_blueprint_fragment", 10000144, 1),
    ("five_boss_deep_crystal", 10000145, 10),
    ("five_boss_first_clear_badge", 10000146, 1),
    ("five_boss_five_king_core", 10000147, 1),
    ("five_boss_king_coin", 10000310, 10),
)


def pack_csv(row: str) -> bytes:
    return zlib.compress((row + "\n").encode("utf-8"))


def raw_rows(raw: bytes) -> dict[str, bytes]:
    parsed = p.core.read_orderedmap_raw_rows_from_bytes(raw)
    return dict(zip(parsed.keys, parsed.rows))


def pack_map(rows: dict[str, bytes]) -> bytes:
    return p.core.build_orderedmap_raw_rows(
        p.core.OrderedMap("[five-boss-preview]", list(rows), list(rows.values()), Path("[memory]"))
    )


def build_score_table(before: bytes) -> tuple[bytes, dict[str, list[str]]]:
    outer = raw_rows(before)
    if PREVIEW_GROUP in outer:
        raise RuntimeError(f"score reward group {PREVIEW_GROUP} already exists")
    inner = {
        str(index): pack_csv(f"{name},0,0,{item_id},{count},0,,")
        for index, (name, item_id, count) in enumerate(PREVIEW_ROWS, 1)
    }
    outer[PREVIEW_GROUP] = pack_map(inner)
    return p.packmap(outer), {PREVIEW_GROUP: [f"{item_id}:{count}" for _, item_id, count in PREVIEW_ROWS]}


def build_quest_table(before: bytes) -> tuple[bytes, list[int]]:
    outer = raw_rows(before)
    chapter = raw_rows(outer["1"])
    stages = raw_rows(chapter["99"])
    changed: list[int] = []
    for key, raw in stages.items():
        rows = list(csv.reader(io.StringIO(zlib.decompress(raw).decode("utf-8"))))
        if len(rows) != 1 or not rows[0]:
            continue
        row = rows[0]
        quest_id = int(row[0])
        if quest_id not in QUEST_IDS:
            continue
        if len(row) <= 70:
            raise RuntimeError(f"quest {quest_id} has no score reward column")
        row[70] = PREVIEW_GROUP
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerow(row)
        stages[key] = zlib.compress(output.getvalue().encode("utf-8"))
        changed.append(quest_id)
    if tuple(sorted(changed)) != QUEST_IDS:
        raise RuntimeError(f"unexpected Five Boss quest ids: {sorted(changed)}")
    chapter["99"] = pack_map(stages)
    outer["1"] = pack_map(chapter)
    return p.packmap(outer), changed


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)

    chain = p.Chain()
    if chain.tail != "1.4.129":
        raise RuntimeError(f"expected current CDN tail 1.4.129, got {chain.tail}")
    score_before = chain.get(("common", p.hrel(LOGICAL_SCORE)))
    quest_before = chain.get(("common", p.hrel(LOGICAL_QUEST)))
    if score_before is None or quest_before is None:
        raise RuntimeError("effective score/quest resources are missing")
    score_after, preview = build_score_table(score_before)
    quest_after, quest_ids = build_quest_table(quest_before)

    # Update the server mirrors with the same group and quest references.
    score_path = p.REPO / "assets/score_reward.json"
    score_data = json.loads(score_path.read_text("utf-8"))
    expected_score_rows = [
        {
            "position": index,
            "name": name,
            "type": 0,
            "reward_type": 0,
            "count": count,
            "field5": 0,
            "id": item_id,
        }
        for index, (name, item_id, count) in enumerate(PREVIEW_ROWS, 1)
    ]
    if PREVIEW_GROUP in score_data:
        if score_data[PREVIEW_GROUP] != expected_score_rows:
            raise RuntimeError(f"server score_reward group {PREVIEW_GROUP} already differs")
    else:
        score_data[PREVIEW_GROUP] = expected_score_rows
        score_path.write_bytes((json.dumps(score_data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    quest_path = p.REPO / "assets/boss_battle_quest.json"
    quest_text = quest_path.read_bytes().decode("utf-8-sig")
    for quest_id in QUEST_IDS:
        needle = f'"{quest_id}": {{'
        start = quest_text.find(needle)
        if start < 0:
            raise RuntimeError(f"server quest {quest_id} is missing")
        pattern = re.compile(
            rf'("{quest_id}"\s*:\s*\{{.*?"scoreRewardGroupId"\s*:\s*)\d+',
            re.S,
        )
        block_new, count = pattern.subn(r'\g<1>' + PREVIEW_GROUP, quest_text, count=1)
        if count != 1:
            raise RuntimeError(f"server quest {quest_id} score reward field missing")
        quest_text = block_new
    # Preserve the source file's CRLF layout so this focused data change does
    # not rewrite the unrelated quest rows.
    quest_path.write_bytes(quest_text.encode("utf-8"))

    version = "1.4.130"
    archive_name = f"pinball-1.4.129-{version}-1-five-boss-reward-preview.zip"
    archive_path = p.REPO / "assets/asset-patch/active" / archive_name
    if archive_path.exists():
        raise RuntimeError(f"archive already exists: {archive_path}")
    payloads = {
        f"production/upload/{p.hrel(LOGICAL_SCORE)}": score_after,
        f"production/upload/{p.hrel(LOGICAL_QUEST)}": quest_after,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for member, data in sorted(payloads.items()):
            info = zipfile.ZipInfo(member, (2026, 10, 2, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    archive_bytes = buffer.getvalue()
    archive_path.write_bytes(archive_bytes)

    manifest_path = p.REPO / "assets/asset-patch/manifest.json"
    manifest_before = manifest_path.read_bytes()
    manifest = json.loads(manifest_before)
    if manifest.get("cdn_version") != "1.4.129":
        raise RuntimeError(f"manifest tail changed: {manifest.get('cdn_version')}")
    integrity = {
        "name": archive_name,
        "size": len(archive_bytes),
        "sha256": sha(archive_bytes),
        "members": len(payloads),
        "files": sorted(payloads),
    }
    manifest["patches"].append({
        "id": "five-boss-reward-preview-1.4.130",
        "type": "patch",
        "name": "五重决战关卡奖励预览修正",
        "description": "将五重决战关卡预览切换到专用奖励组，移除旧维·索拉斯奖励池显示。",
        "version": version,
        "depends_on": "1.4.129",
        "enabled": True,
        "archive": archive_name,
        "archive_size": len(archive_bytes),
        "chain": [archive_name],
        "archive_integrity": [integrity],
        "files": sorted(payloads),
        "created_at": "2026-10-02",
        "audit": {"directory": "assets/asset-patch/audit/five-boss-reward-preview-1.4.130", "report": "report.json"},
    })
    manifest["cdn_version"] = version
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")

    audit_dir = p.REPO / "assets/asset-patch/audit/five-boss-reward-preview-1.4.130"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "manifest.before.json").write_bytes(manifest_before)
    report = {
        "status": "prepared_local_resource_update",
        "base_version": chain.tail,
        "target_version": version,
        "archive": integrity,
        "source_changes": {
            "score_reward_group": PREVIEW_GROUP,
            "quest_ids": quest_ids,
            "preview_rows": list(preview[PREVIEW_GROUP]),
        },
        "before_resources": {
            LOGICAL_SCORE: {"sha256": sha(score_before), "size": len(score_before)},
            LOGICAL_QUEST: {"sha256": sha(quest_before), "size": len(quest_before)},
        },
        "after_resources": {
            LOGICAL_SCORE: {"sha256": sha(score_after), "size": len(score_after)},
            LOGICAL_QUEST: {"sha256": sha(quest_after), "size": len(quest_after)},
        },
        "runtime_deployed": False,
        "device_tested": False,
    }
    (audit_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"version": version, "archive": integrity, "quest_ids": quest_ids}, ensure_ascii=False))


if __name__ == "__main__":
    main()
