from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH_ROOT = ROOT / "assets" / "asset-patch"
MANIFEST_PATH = PATCH_ROOT / "manifest.json"
ACTIVE_ROOT = PATCH_ROOT / "active"
SOURCE_RELATIVE = Path("b6") / "595dedd9cfa79b7e6eccab25dd9a2a81b066a2"
SOURCE_PATH = PATCH_ROOT / "production" / "upload" / SOURCE_RELATIVE
ARCHIVE_NAME = "pinball-1.4.76-1.4.77-1-0812-abyss-floor24-fix.zip"
PATCH_ID = "abyss-floor24-rush-field-fix-1.4.77"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    patches = document.get("patches")
    if not isinstance(patches, list):
        raise ValueError("manifest patches must be an array")

    existing = next((item for item in patches if item.get("id") == PATCH_ID), None)
    if existing is not None:
        print(f"already published: {PATCH_ID}")
        return 0
    if document.get("cdn_version") != "1.4.76":
        raise ValueError(
            f"expected manifest tail 1.4.76, got {document.get('cdn_version')!r}"
        )
    if any(item.get("version") == "1.4.77" for item in patches):
        raise ValueError("manifest already contains another 1.4.77 patch")
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(SOURCE_PATH)

    payload = SOURCE_PATH.read_bytes()
    archive_path = ACTIVE_ROOT / ARCHIVE_NAME
    ACTIVE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_path = archive_path.with_suffix(".zip.tmp")
    temporary_path.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"production/upload/{SOURCE_RELATIVE.as_posix()}", payload
        )
    temporary_path.replace(archive_path)

    archive_payload = archive_path.read_bytes()
    entry = {
        "id": PATCH_ID,
        "type": "patch",
        "name": "深渊连战第24层场地兼容修复 1.4.77",
        "description": (
            "将第24层从塔楼专用暗属性支配者固定机关场地切换为官方连战专用暗属性支配者场地，"
            "修复进入该层时出现C14102；敌人等级、推荐属性、关卡修正和前后层连接保持不变。"
        ),
        "version": "1.4.77",
        "depends_on": "1.4.76",
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive_payload),
        "files": [SOURCE_RELATIVE.as_posix()],
        "changes": [
            "第24层改用官方Rush专用 administrator_another_dark_rush 场地。",
            "Boss仍为暗属性支配者连战形态，等级100及原关卡修正保持不变。",
            "取消个人通关或重置触发30层关卡重抽；个人进度重置功能保持不变。",
        ],
        "created_at": "2026-08-12",
        "archive_integrity": [
            {
                "name": ARCHIVE_NAME,
                "size": len(archive_payload),
                "sha256": sha256_bytes(archive_payload),
                "members": 1,
            }
        ],
    }
    patches.append(entry)
    document["cdn_version"] = "1.4.77"

    temporary_manifest = MANIFEST_PATH.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_manifest.replace(MANIFEST_PATH)

    with zipfile.ZipFile(archive_path) as archive:
        members = archive.namelist()
        if members != [f"production/upload/{SOURCE_RELATIVE.as_posix()}"]:
            raise ValueError(f"unexpected archive members: {members}")
        if archive.read(members[0]) != payload:
            raise ValueError("archive payload does not match final store")

    print(f"published: 1.4.76 -> 1.4.77")
    print(f"archive: {archive_path}")
    print(f"archive sha256: {sha256_bytes(archive_payload)}")
    print(f"table sha256: {sha256_bytes(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
