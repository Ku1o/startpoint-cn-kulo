#!/usr/bin/env python3
"""Fold the approved swim-EX leader gauge adjustment into the existing 1.4.81 edge."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import publish_thunder_dragon_fantasy_v4_1_4_81_20260817 as release


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
DEPLOY_ROOT = Path(r"F:\startpoint-cn-main")
BACKUP_ROOT = Path(r"F:\codex\local-deploy-backups")

PATCH_ID = "thunder-dragon-fantasy-v4-1.4.81"
ARCHIVE_NAME = "pinball-1.4.80-1.4.81-1-0817-thunder-dragon-fantasy-v4.zip"
CURRENT_ARCHIVE_SHA256 = "6ae9b9837efcbcdd4b45723f286890dac0c9bfa83448fbae607d9eb7a09b6775"
LEADER_LOGICAL = "master/ability/leader_ability.orderedmap"
SWIM_EX_ID = "139997"


class FoldError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".swimex-leader-fold.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def archive_path(root: Path) -> Path:
    return root / "assets/asset-patch/active" / ARCHIVE_NAME


def manifest_path(root: Path) -> Path:
    return root / "assets/asset-patch/manifest.json"


def leader_live_path(root: Path) -> Path:
    return release.live_path(root, LEADER_LOGICAL)


def validate_current(root: Path) -> tuple[dict, bytes, bytes]:
    manifest_raw = manifest_path(root).read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8-sig"))
    if manifest.get("cdn_version") != "1.4.81":
        raise FoldError(f"manifest is not at 1.4.81: {manifest_path(root)}")
    matches = [patch for patch in manifest.get("patches", []) if patch.get("id") == PATCH_ID]
    if len(matches) != 1 or matches[0].get("archive") != ARCHIVE_NAME:
        raise FoldError(f"1.4.81 target patch entry drifted: {manifest_path(root)}")
    raw = archive_path(root).read_bytes()
    if sha256_bytes(raw) != CURRENT_ARCHIVE_SHA256:
        raise FoldError(f"existing 1.4.81 archive drifted: {archive_path(root)}")
    integrity = matches[0].get("archive_integrity")
    if (
        not isinstance(integrity, list)
        or len(integrity) != 1
        or integrity[0].get("sha256") != CURRENT_ARCHIVE_SHA256
        or integrity[0].get("size") != len(raw)
        or integrity[0].get("members") != 29
    ):
        raise FoldError(f"existing 1.4.81 archive receipt drifted: {manifest_path(root)}")
    member = release.member_name(LEADER_LOGICAL)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        leader_raw = archive.read(member)
    if leader_live_path(root).read_bytes() != leader_raw:
        raise FoldError(f"live leader table differs from the 1.4.81 archive: {root}")
    return manifest, manifest_raw, raw


def build_archive(current: bytes) -> tuple[bytes, bytes, list[str]]:
    leader_member = release.member_name(LEADER_LOGICAL)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(current)) as source:
        names = source.namelist()
        if len(names) != 29 or len(set(names)) != 29 or leader_member not in names:
            raise FoldError("existing 1.4.81 archive member list drifted")
        old_leader = source.read(leader_member)
        new_leader = release.patch_leader(old_leader)
        before = release.flat_rows(old_leader)
        after = release.flat_rows(new_leader)
        changed = sorted(key for key in before if before[key] != after.get(key))
        if changed != [SWIM_EX_ID] or before.keys() != after.keys():
            raise FoldError(f"leader table changed unexpected keys: {changed}")
        rows = release.core.read_csv_lines(after[SWIM_EX_ID])
        if (rows[6][49], rows[6][50]) != ("8000", "8000"):
            raise FoldError("swim-EX leader gauge patch verification failed")
        with zipfile.ZipFile(output, "w", allowZip64=True) as target:
            for info in source.infolist():
                payload = new_leader if info.filename == leader_member else source.read(info.filename)
                target.writestr(info, payload)
    rebuilt = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(rebuilt)) as archive:
        if archive.namelist() != names or archive.testzip() is not None:
            raise FoldError("rebuilt 1.4.81 archive verification failed")
        if archive.read(leader_member) != new_leader:
            raise FoldError("rebuilt leader payload verification failed")
    return rebuilt, new_leader, names


def update_manifest(manifest: dict, archive: bytes, member_count: int) -> bytes:
    value = json.loads(json.dumps(manifest))
    matches = [patch for patch in value["patches"] if patch.get("id") == PATCH_ID]
    patch = matches[0]
    patch["name"] = "雷龙、泳皇女 EX 平衡与幻想连战 V4 图标 1.4.81"
    patch["description"] = (
        "调整响彻碧海的雷龙（139998）的雷电增幅持续时间与能力3充能数值；"
        "调整泳皇女 EX（139997）雷属性共鸣队长技的技能槽回复；"
        "替换幻想连战11件装备图标，并为对应魂珠导入独立图标及精确裁切定义。"
    )
    change = "泳皇女 EX 队长技在雷属性共鸣时，雷角色发动技能后的雷属性全队技能槽回复由10%调整为8%。"
    changes = list(patch.get("changes", []))
    if change in changes:
        raise FoldError("swim-EX leader change is already recorded")
    changes.insert(2, change)
    patch["changes"] = changes
    patch["archive_size"] = len(archive)
    patch["archive_integrity"] = [{
        "name": ARCHIVE_NAME,
        "size": len(archive),
        "sha256": sha256_bytes(archive),
        "members": member_count,
    }]
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source_manifest, source_manifest_raw, source_archive = validate_current(SOURCE_ROOT)
    deploy_manifest, deploy_manifest_raw, deploy_archive = validate_current(DEPLOY_ROOT)
    if source_manifest != deploy_manifest or source_manifest_raw != deploy_manifest_raw:
        raise FoldError("source and deployed manifests differ")
    if source_archive != deploy_archive:
        raise FoldError("source and deployed 1.4.81 archives differ")

    archive, leader_raw, names = build_archive(source_archive)
    manifest_raw = update_manifest(source_manifest, archive, len(names))
    report = {
        "apply": args.apply,
        "version": "1.4.81",
        "archive": ARCHIVE_NAME,
        "before_size": len(source_archive),
        "after_size": len(archive),
        "before_sha256": sha256_bytes(source_archive),
        "after_sha256": sha256_bytes(archive),
        "members": len(names),
        "changed_table": LEADER_LOGICAL,
        "changed_keys": [SWIM_EX_ID],
        "leader_resonance_party_gauge": {"before": 10000, "after": 8000},
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    targets: dict[str, tuple[Path, bytes]] = {}
    for label, root in (("source", SOURCE_ROOT), ("deploy", DEPLOY_ROOT)):
        targets[f"{label}-archive"] = (archive_path(root), archive)
        targets[f"{label}-leader"] = (leader_live_path(root), leader_raw)
        targets[f"{label}-manifest"] = (manifest_path(root), manifest_raw)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_ROOT / f"swimex-leader-fold-into-1.4.81-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    for label, (path, _raw) in targets.items():
        if not path.is_file():
            raise FoldError(f"publication target is missing: {path}")
        shutil.copy2(path, backup / label)

    try:
        for label, (path, raw) in targets.items():
            if label.endswith("-manifest"):
                continue
            atomic_write(raw, path)
        for label, (path, raw) in targets.items():
            if label.endswith("-manifest"):
                atomic_write(raw, path)
        for label, (path, expected) in targets.items():
            if path.read_bytes() != expected:
                raise FoldError(f"publication readback failed: {label}")
        for root in (SOURCE_ROOT, DEPLOY_ROOT):
            written = json.loads(manifest_path(root).read_text(encoding="utf-8-sig"))
            patch = [entry for entry in written["patches"] if entry.get("id") == PATCH_ID]
            if written.get("cdn_version") != "1.4.81" or len(patch) != 1:
                raise FoldError(f"manifest version readback failed: {root}")
            receipt = patch[0]["archive_integrity"][0]
            if receipt["sha256"] != sha256_bytes(archive) or receipt["size"] != len(archive):
                raise FoldError(f"manifest archive receipt readback failed: {root}")
    except Exception:
        for label, (path, _raw) in reversed(list(targets.items())):
            atomic_write((backup / label).read_bytes(), path)
        raise

    report["backup"] = str(backup)
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
