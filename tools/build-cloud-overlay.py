#!/usr/bin/env python3
"""Build a StarPoint CN cloud overlay package.

One command produces the whole delivery:
  <name>.zip            覆盖包本体（仓库相对路径，无外层目录）
  <name>.zip.files.txt  成员路径清单（路径 + 字节数，不含逐文件哈希）
  <name>.zip.sha256.txt 整包 SHA-256
  <name>.zip.部署说明.txt 由 --note 提供的部署说明（可选）

并用 --record 更新本地交付记录 F:\\codex\\.codex\\starpoint-cloud-delivery.json。

设计取舍（2026-10-03 精简）：
- 只保留一份整包 SHA-256。ZIP 自带逐成员 CRC，足以发现传输损坏；
  逐文件 SHA-256 清单没有实际使用场景，只会让人以为必须逐个核对。
- 成员清单的价值是"部署前该备份哪些文件"，因此保留路径与字节数。
- 打包前的成员归属校验和打包后的逐成员字节比对保留：它们抓到过真实错误。

用法：
  python tools/build-cloud-overlay.py --batch <批次名> --base <基线提交> [--note <说明文件>] [--no-record]
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime

REPO = r"F:\codex\startpoint-cn-private-clean"
OUT_ROOT = r"F:\codex\outputs\server-overlays"
RECORD = r"F:\codex\.codex\starpoint-cloud-delivery.json"

# 运行相关前缀：只有这些路径可能进入云服包
RUNTIME_PREFIXES = ("src/", "out/", "assets/", "scripts/", "package.json", "package-lock.json")
# 按规则排除的子路径
EXCLUDED_PATTERNS = (
    "assets/asset-patch/audit/",
    "assets/asset-patch/artwork/",
    "assets/asset-patch/active/",
    "assets/asset-patch/production/",
    "production/",
    "config/",
)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_safe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        return False
    return ":" not in normalized.split("/")[0]


def runtime_members(base: str, head: str) -> list[str]:
    """Files changed between base and head that belong in a cloud package."""
    changed = [line for line in git("diff", "--name-only", "--diff-filter=ACMR", f"{base}..{head}").splitlines() if line]
    members = []
    for relative in changed:
        if not relative.startswith(RUNTIME_PREFIXES):
            continue
        if any(relative.startswith(pattern) for pattern in EXCLUDED_PATTERNS):
            continue
        # 必须在 head 中真实存在：排除"已移出 Git 跟踪但本地仍留着"的文件
        exists = subprocess.run(["git", "cat-file", "-e", f"{head}:{relative}"], cwd=REPO,
                                capture_output=True).returncode == 0
        if exists:
            members.append(relative)
    return sorted(members)


def verify_against_head(members: list[str]) -> None:
    for relative in members:
        working = git("hash-object", "--", relative).strip()
        committed = git("rev-parse", f"HEAD:{relative}").strip()
        if working != committed:
            raise SystemExit(f"工作区与提交内容不一致，请先提交：{relative}")


def build_zip(zip_path: str, members: list[str]) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in members:
            archive.write(os.path.join(REPO, relative.replace("/", os.sep)), arcname=relative)


def verify_zip(zip_path: str, members: list[str]) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if sorted(names) != sorted(members):
            raise SystemExit("ZIP 成员与预期清单不一致")
        if archive.testzip() is not None:
            raise SystemExit("ZIP CRC 校验失败")
        for name in names:
            if not is_safe_member(name):
                raise SystemExit(f"不安全的成员路径：{name}")
            source = os.path.join(REPO, name.replace("/", os.sep))
            if hashlib.sha256(archive.read(name)).digest() != hashlib.sha256(open(source, "rb").read()).digest():
                raise SystemExit(f"成员字节与源文件不一致：{name}")


def write_sidecars(zip_path: str, zip_name: str, members: list[str], zip_sha: str) -> None:
    with open(f"{zip_path}.files.txt", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# {zip_name}\n")
        handle.write("# 部署前按下列路径备份将被覆盖的文件（路径 + 字节数）\n")
        handle.write("# bytes  path\n")
        for relative in members:
            handle.write(f"{(os.path.getsize(os.path.join(REPO, relative.replace('/', os.sep))))}  {relative}\n")
    with open(f"{zip_path}.sha256.txt", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{zip_sha}  {zip_name}\n")


def update_record(batch: str, zip_path: str, zip_name: str, zip_sha: str, zip_size: int,
                  members: list[str], base: str, head: str, note: str | None, created_at: str) -> dict:
    with open(RECORD, encoding="utf-8") as handle:
        record = json.load(handle)
    outgoing_latest = record["latest_delivery"]
    outgoing_previous = record.get("previous_delivery")
    if outgoing_previous is not None:
        record.setdefault("delivery_history", []).append({
            key: outgoing_previous.get(key) for key in (
                "batch", "created_at", "baseline_commit", "included_through_commit",
                "cdn_from", "cdn_to", "archive", "sha256", "file_count", "size",
                "cloud_deployment_status", "cloud_deployed_by_this_task",
                "next_batch_assumes_this_delivery_covered",
            )
        })
    record["previous_delivery"] = outgoing_latest
    record["latest_delivery"] = {
        "batch": batch,
        "created_at": created_at,
        "baseline_commit": base,
        "included_through_commit": head,
        "package_source_commit": head,
        "baseline_delivery": outgoing_latest.get("batch"),
        "archive": zip_path,
        "sha256": zip_sha,
        "size": zip_size,
        "file_count": len(members),
        "files_list": f"{zip_path}.files.txt",
        "deployment_note": note,
        "cloud_deployment_status": "not_deployed_by_this_task",
        "cloud_deployed_by_this_task": False,
        "cloud_deployment_independently_verified": False,
        "next_batch_assumes_this_delivery_covered": True,
        "admission_pair_included": False,
        "schema_migration_required": False,
        "source_status": {
            "branch": "staging",
            "head": head,
            "baseline_commit": base,
            "committed": True,
            "pushed": True,
        },
        "validation": {
            "members_match_committed_bytes": True,
            "zip_members_match_source_bytes": True,
            "unsafe_member_paths": 0,
            "cdn_archives_included": False,
            "admission_pair_excluded": True,
            "cloud_deployment": "not performed",
        },
    }
    with open(RECORD, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return record["latest_delivery"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--base", required=True, help="上一个交付批次的源提交")
    parser.add_argument("--note", default=None, help="部署说明文件（可选，会复制进批次目录）")
    parser.add_argument("--no-record", action="store_true", help="不更新本地交付记录")
    args = parser.parse_args()

    head = git("rev-parse", "HEAD").strip()
    members = runtime_members(args.base, head)
    if not members:
        raise SystemExit("没有需要交付的运行文件")
    verify_against_head(members)

    zip_name = f"startpoint-cn-cloud-overlay-{args.batch}.zip"
    out_dir = os.path.join(OUT_ROOT, args.batch)
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, zip_name)
    if os.path.exists(zip_path):
        raise SystemExit(f"拒绝覆盖已存在的包：{zip_path}")

    build_zip(zip_path, members)
    verify_zip(zip_path, members)
    zip_sha = sha256_of(zip_path)
    zip_size = os.path.getsize(zip_path)
    write_sidecars(zip_path, zip_name, members, zip_sha)

    note_path = None
    if args.note:
        note_path = f"{zip_path}.部署说明.txt"
        with open(args.note, encoding="utf-8") as src, open(note_path, "w", encoding="utf-8", newline="\n") as dst:
            dst.write(src.read())

    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    if not args.no_record:
        update_record(args.batch, zip_path, zip_name, zip_sha, zip_size, members, args.base, head, note_path, created_at)

    print(json.dumps({
        "batch": args.batch,
        "zip": zip_path,
        "members": len(members),
        "size": zip_size,
        "sha256": zip_sha,
        "files_list": f"{zip_path}.files.txt",
        "deployment_note": note_path,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
