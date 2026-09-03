#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the 1.4.97 CDN recovery patch for the omitted greyupd0902 assets.

The author delivered 33 1.4.95 -> 1.4.96 CDN archives in the runtime mirror,
but the previous active cumulative archive did not include those bytes.  This
tool copies those entries byte-for-byte into a new active-chain archive and
generates the missing iOS ETC2 cut-in files from the source PNGs.  It does not
touch game tables or server data.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import wf_assets
import wf_atf
import wf_mod_tool


DEFAULT_SOURCE_CDN = Path(r"F:\startpoint-cn-main\.cdn\cn")
ARCHIVE_DIRS = (
    "archive-common-diff",
    "archive-medium-diff",
    "archive-android-diff",
)
OUTPUT_NAME = "pinball-1.4.96-1.4.97-1-greyupd0902-cdn-resource-recovery.zip"
AUDIT_DIR = REPO_ROOT / "assets" / "asset-patch" / "audit" / (
    "greyupd0902-cdn-resource-recovery-1.4.97"
)
MANIFEST_PATH = REPO_ROOT / "assets" / "asset-patch" / "manifest.json"
ACTIVE_DIR = REPO_ROOT / "assets" / "asset-patch" / "active"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _character_codes() -> set[str]:
    codes: set[str] = set()
    for path in (
        REPO_ROOT / "assets" / "cdndata" / "character.json",
        REPO_ROOT / "assets" / "cdndata" / "character_rank_p5b.json",
    ):
        data = _read_json(path)
        for value in data.values():
            rows = value if isinstance(value, list) else [value]
            for row in rows:
                if not isinstance(row, list) or not row:
                    continue
                # Datamined tables are normally [[code_name, ...]], while a
                # few local snapshots use a direct [code_name, ...] row.
                first = row[0]
                if isinstance(first, list):
                    first = first[0] if first else None
                if first:
                    codes.add(str(first))
    return codes


def _load_author_entries(source_cdn: Path):
    entries: dict[str, bytes] = {}
    origins: dict[str, str] = {}
    packages: list[dict] = []
    for dirname in ARCHIVE_DIRS:
        folder = source_cdn / dirname
        files = sorted(folder.glob("*greyupd0902*.zip"))
        if not files:
            raise RuntimeError(f"未找到作者包: {folder}")
        for archive in files:
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            count = 0
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    name = info.filename
                    if name.endswith("/"):
                        continue
                    if name.startswith("/") or ".." in Path(name).parts:
                        raise RuntimeError(f"作者包含非法成员路径: {archive.name}:{name}")
                    if not name.startswith((
                        "production/upload/",
                        "production/medium_upload/",
                        "production/android_upload/",
                    )):
                        raise RuntimeError(f"作者包含非资源成员: {archive.name}:{name}")
                    if name in entries:
                        raise RuntimeError(f"作者包重复资源路径: {name}")
                    entries[name] = zf.read(info)
                    origins[name] = archive.name
                    count += 1
            packages.append({
                "name": archive.name,
                "directory": dirname,
                "size": archive.stat().st_size,
                "sha256": digest,
                "members": count,
            })
    return entries, origins, packages


def _current_cumulative_member_names() -> set[str]:
    """Return members of the currently published cumulative edge only.

    Older active archives are historical edges.  Reintroducing a final
    greyupd resource may legitimately supersede one of those older bytes, but
    it must never collide with the already published 1.4.95 -> 1.4.96 edge.
    """
    names: set[str] = set()
    archive = ACTIVE_DIR / "pinball-1.4.95-1.4.96-1-cdn-consolidated-gerald0903.zip"
    if archive.is_file():
        with zipfile.ZipFile(archive) as zf:
            names.update(info.filename for info in zf.infolist() if not info.is_dir())
    return names


def _generated_ios(entries: dict[str, bytes]):
    medium = {
        name: payload
        for name, payload in entries.items()
        if name.startswith("production/medium_upload/")
    }
    android = {
        name: payload
        for name, payload in entries.items()
        if name.startswith("production/android_upload/")
    }
    candidates: dict[str, str] = {}
    for code in sorted(_character_codes()):
        for index in (0, 1):
            logical = f"character/{code}/ui/skill_cutin_{index}.atf.deflate"
            digest = wf_mod_tool.sha1_path(logical)
            android_name = f"production/android_upload/{digest[:2]}/{digest[2:]}"
            candidates[android_name] = logical

    ios: dict[str, bytes] = {}
    generated_logicals: list[str] = []
    unmatched: list[str] = []
    jobs = []
    for android_name, android_stored in sorted(android.items()):
        logical = candidates.get(android_name)
        if logical is None:
            unmatched.append(android_name)
            continue
        digest = wf_mod_tool.sha1_path(logical)
        png_logical = logical[:-len(".atf.deflate")] + ".png"
        png_digest = wf_mod_tool.sha1_path(png_logical)
        png_name = f"production/medium_upload/{png_digest[:2]}/{png_digest[2:]}"
        png_stored = medium.get(png_name)
        if png_stored is None:
            raise RuntimeError(f"找不到 cut-in 源 PNG: {logical} -> {png_name}")
        jobs.append((logical, android_stored, png_stored))
    if unmatched:
        raise RuntimeError(
            "作者 Android 资源中存在无法由角色表解析的 cut-in: "
            + ", ".join(unmatched)
        )
    # The ETC2 encoder is pure Python.  A small process pool keeps each worker
    # independent (and avoids sharing mutable encoder state) while reducing
    # the wall-clock time for the 90 1024x512 cut-ins substantially.
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        results = pool.map(_generate_ios_one, jobs)
        for logical, ios_name, ios_stored in results:
            if ios_name in entries or ios_name in ios:
                raise RuntimeError(f"iOS 资源路径冲突: {ios_name}")
            ios[ios_name] = ios_stored
            generated_logicals.append(logical)
    if len(generated_logicals) != len(android):
        raise RuntimeError(
            f"iOS cut-in 数量不完整: Android={len(android)}, iOS={len(generated_logicals)}"
        )
    return ios, generated_logicals


def _generate_ios_one(job: tuple[str, bytes, bytes]) -> tuple[str, str, bytes]:
    """Worker-safe single cut-in conversion."""
    logical, android_stored, png_stored = job
    digest = wf_mod_tool.sha1_path(logical)
    png = wf_assets.png_decode(png_stored)
    android_plain = wf_atf.inflate(android_stored)
    ios_plain = wf_atf.build_cutin_atf_ios(png, ref_atf=android_plain)
    wf_atf.validate_cutin_platform_pair(android_plain, ios_plain, png)
    ios_stored = wf_atf.deflate(ios_plain)
    ios_name = f"production/ios_upload/{digest[:2]}/{digest[2:]}"
    return logical, ios_name, ios_stored


def _zip_write(path: Path, entries: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fixed_time = (2026, 9, 3, 0, 0, 0)
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=False,
    ) as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            zf.writestr(info, entries[name])


def _update_manifest(archive_path: Path, entries: dict[str, bytes], audit_rel: str,
                     generated_logicals: list[str]) -> dict:
    manifest = _read_json(MANIFEST_PATH)
    patches = manifest.setdefault("patches", [])
    patch_id = "greyupd0902-cdn-resource-recovery-1.4.97"
    patches[:] = [p for p in patches if p.get("id") != patch_id]
    archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    entry = {
        "id": patch_id,
        "type": "patch",
        "name": "greyupd0902 CDN 资源补缺与 iOS 配对",
        "description": (
            "补入上一版漏出的 .cdn/cn greyupd0902 资源，并由同源 PNG 独立生成 iOS ETC2 cut-in；"
            "只补客户端资源，不改服务端数据、角色觉醒、称号、代币或玩法规则。"
        ),
        "version": "1.4.97",
        "depends_on": "1.4.96",
        "enabled": True,
        "archive": archive_path.name,
        "archive_size": archive_path.stat().st_size,
        "files": sorted(entries),
        "changes": [
            "从 .cdn/cn/archive-common-diff、archive-medium-diff、archive-android-diff 纳入 33 个作者包，共 2770 个原始资源，逐项保留原字节。",
            f"对 {len(generated_logicals)} 个 Android skill cut-in 按源 PNG 独立生成 iOS ETC2 RGBA 槽 3，禁止复制 Android 文件。",
            "该补丁作为 1.4.96 后的 1.4.97 资源补缺边，不启用或覆盖此前保留的称号、代币及连战塔备用补丁。",
        ],
        "created_at": "2026-09-03",
        "audit": {"directory": audit_rel, "report": "report.json"},
        "archive_integrity": [{
            "name": archive_path.name,
            "size": archive_path.stat().st_size,
            "sha256": archive_sha,
            "members": len(entries),
        }],
        "chain": [archive_path.name],
    }
    patches.append(entry)
    manifest["cdn_version"] = "1.4.97"
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-cdn", type=Path, default=Path(
        os.environ.get("WF_GREYUPD_SOURCE_CDN", str(DEFAULT_SOURCE_CDN))
    ))
    parser.add_argument("--no-manifest", action="store_true")
    args = parser.parse_args()
    source_cdn = args.source_cdn.resolve()
    if not source_cdn.is_dir():
        raise SystemExit(f"CDN 源目录不存在: {source_cdn}")

    raw, origins, packages = _load_author_entries(source_cdn)
    collision = sorted(set(raw) & _current_cumulative_member_names())
    if collision:
        raise SystemExit(
            "作者资源与 active 已有成员发生路径重叠，已停止以避免覆盖既有玩法: "
            + ", ".join(collision[:10])
            + (" ..." if len(collision) > 10 else "")
        )
    ios, generated_logicals = _generated_ios(raw)
    merged = dict(raw)
    merged.update(ios)
    archive = ACTIVE_DIR / OUTPUT_NAME
    _zip_write(archive, merged)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    audit = {
        "task": "greyupd0902-cdn-resource-recovery-1.4.97",
        "source_cdn": str(source_cdn),
        "source_packages": packages,
        "raw_member_count": len(raw),
        "raw_member_bytes": sum(len(v) for v in raw.values()),
        "generated_ios_member_count": len(ios),
        "generated_ios_logical_paths": generated_logicals,
        "output": {
            "archive": archive.name,
            "size": archive.stat().st_size,
            "sha256": archive_sha,
            "members": len(merged),
            "prefix_counts": {
                prefix: sum(name.startswith(prefix) for name in merged)
                for prefix in (
                    "production/upload/",
                    "production/medium_upload/",
                    "production/android_upload/",
                    "production/ios_upload/",
                )
            },
        },
        "safety": {
            "raw_author_bytes_preserved": True,
            "ios_generated_from_source_png": True,
            "android_ios_pair_validation": "wf_atf.validate_cutin_platform_pair",
            "table_or_server_data_changed": False,
        },
    }
    (AUDIT_DIR / "report.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not args.no_manifest:
        _update_manifest(archive, merged,
                         "assets/asset-patch/audit/greyupd0902-cdn-resource-recovery-1.4.97",
                         generated_logicals)
    print(json.dumps({
        "archive": str(archive),
        "members": len(merged),
        "raw_members": len(raw),
        "ios_members": len(ios),
        "archive_size": archive.stat().st_size,
        "archive_sha256": archive_sha,
        "audit": str(AUDIT_DIR / "report.json"),
        "manifest_updated": not args.no_manifest,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
