#!/usr/bin/env python3
"""Append .100 -> .101 to repair the two shop banners' C8105 signature error.

Only the stored PNG headers change. Published archives and pristine CDN inputs
are immutable; default execution validates a sparse plan without writing files.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

from PIL import Image

import publish_gacha_pool_cleanup_client_1_4_99 as codec
import wf_assets

ROOT = Path(__file__).resolve().parents[2]
BASE = "1.4.100"
TARGET = "1.4.101"
PATCH_ID = "shop-banner-png-encoding-1.4.101"
ARCHIVE = "pinball-1.4.100-1.4.101-1-shop-banner-png-encoding.zip"
SOURCE_ARCHIVE = "pinball-1.4.99-1.4.100-1-abyss-exchange-shop-banners.zip"
BANNERS = (
    ("af/6ad4e513edc45a835d26ae8482ec384ff62ce7", "商店入口横幅", (1000, 184), "RGB",
     "157a2af894b4500cb373ac7af56b34c74e70be757e17a2614058aae5af7d8ca3"),
    ("35/937c7ff9d7006ffa407887910bbec9fc41bc06", "觉醒强化页头", (1440, 556), "RGBA",
     "19bef4da76737ab0bdad1cf81d3d5d50759a3a8059dd43ed86d882483d46ec3c"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def repair_banner(raw: bytes, size: tuple[int, int], mode: str) -> bytes:
    """Encode an ordinary donor and prove exact decoded bytes and pixels survive."""
    stored = wf_assets.png_encode(raw)
    decoded = wf_assets.png_decode_stored(stored)
    require(decoded == raw, "PNG decoded bytes changed")
    require([i for i, (a, b) in enumerate(zip(raw, stored)) if a != b] == [1, 2, 3],
            "repair changed bytes outside the stored signature")
    for payload in (raw, decoded):
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            require(image.format == "PNG" and image.size == size and image.mode == mode,
                    "PNG format, dimensions or mode drifted")
    return stored


def checked_output(root: Path, relative: str) -> Path:
    """Reject output escapes, including junctions into the pristine CDN."""
    path = root / relative
    resolved = path.resolve()
    require(resolved.is_relative_to(root.resolve()), f"output escapes source: {path}")
    require(not resolved.is_relative_to((root / ".cdn").resolve()), f"CDN is read-only: {path}")
    require(".cdn" not in Path(relative).parts, f"CDN is read-only: {path}")
    return path


def build(root: Path):
    patch_root = root / "assets/asset-patch"
    before_manifest = (patch_root / "manifest.json").read_bytes()
    manifest = json.loads(before_manifest)
    enabled = [p for p in manifest["patches"] if p.get("enabled")]
    require(manifest["cdn_version"] == enabled[-1]["version"] == BASE, "current tail must be .100")
    require(not (patch_root / "active" / ARCHIVE).exists(), "published ZIP is immutable")
    require(not (patch_root / "audit" / PATCH_ID).exists(), "audit already exists")
    prior_archives = []
    for item in enabled[-1]["archive_integrity"]:
        raw = (patch_root / "active" / item["name"]).read_bytes()
        require(len(raw) == item["size"] and codec.sha256(raw) == item["sha256"],
                f"published source archive drift: {item['name']}")
        prior_archives.append(item)
    plan = codec.store.build_read_only_plan((root / ".cdn/cn").resolve(), root, BASE, False)
    require(plan.summary()["ok"] and not plan.health.unreachable, "invalid source chain")
    require(SOURCE_ARCHIVE in enabled[-1]["chain"], "source ZIP not in active terminal")
    snapshots, payloads, banners = {}, {}, []
    for relative, label, size, mode, expected_hash in BANNERS:
        member = "production/upload/" + relative
        entry = plan.entries[("common", relative)]
        require(Path(entry.zip_path).resolve() == (patch_root / "active" / SOURCE_ARCHIVE).resolve(),
                f"unexpected effective source: {member}")
        require(entry.name == member, f"source member drift: {member}")
        with zipfile.ZipFile(entry.zip_path) as archive:
            raw = archive.read(entry.name)
        require(codec.sha256(raw) == expected_hash, f"donor drift: {label}")
        require((patch_root / member).read_bytes() == raw, f"loose source drift: {label}")
        try:
            wf_assets.png_decode_stored(raw)
        except ValueError as error:
            before_error = str(error)
        else:
            raise ValueError(f"source no longer reproduces C8105: {label}")
        stored = repair_banner(raw, size, mode)
        snapshots[member], payloads[member] = raw, stored
        with Image.open(io.BytesIO(raw)) as image:
            pixel_sha = codec.sha256(image.tobytes())
        banners.append({"label": label, "member": member, "source_archive": str(entry.zip_path),
                        "size": list(size), "mode": mode, "before_sha256": expected_hash,
                        "after_sha256": codec.sha256(stored), "before_client_error": before_error,
                        "changed_byte_offsets": [1, 2, 3], "strict_decode_byte_identical": True,
                        "pixel_sha256": pixel_sha, "shared_android_ios": True})
    archive_raw = codec.deterministic_zip(payloads)
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        require(archive.namelist() == sorted(payloads), "archive member set changed")
        for member, raw in snapshots.items():
            require(wf_assets.png_decode_stored(archive.read(member)) == raw,
                    f"archive strict PNG readback failed: {member}")
    integrity = {"name": ARCHIVE, "size": len(archive_raw), "sha256": codec.sha256(archive_raw),
                 "members": len(payloads), "files": sorted(payloads)}
    record = {"id": PATCH_ID, "type": "patch", "name": "商店横幅 PNG 存储格式修复 1.4.101",
              "description": "修复进入特殊装备强化时的 C8105，保留两张横幅原画。",
              "version": TARGET, "depends_on": BASE, "enabled": True,
              "archive": ARCHIVE, "archive_size": len(archive_raw), "chain": [ARCHIVE],
              "archive_integrity": [integrity], "files": sorted(payloads),
              "changes": ["两张共通横幅由标准 PNG 转为客户端要求的 fileFaker 存储格式，仅修改文件头三个字节。",
                          "保留原图尺寸、色彩模式和所有像素；Android 与 iOS 共用这两份资源。",
                          "追加 .100→.101 更新，保留 .100 的兑换、称号和既有资源内容。"],
              "created_at": "2026-09-06",
              "audit": {"directory": f"assets/asset-patch/audit/{PATCH_ID}", "report": "report.json"}}
    text = before_manifest.decode("utf8")
    ending = re.search(r"(\r?\n)  \]\r?\n\}\s*$", text)
    require(ending is not None, "manifest closing structure drifted")
    newline, pos = ending[1], ending.start()
    rendered = newline.join("    " + line for line in json.dumps(record, ensure_ascii=False, indent=2).splitlines())
    text = text[:pos] + "," + newline + rendered + text[pos:]
    text = text.replace(f'"cdn_version": "{BASE}"', f'"cdn_version": "{TARGET}"', 1)
    after_manifest = text.encode("utf8")
    updated = json.loads(after_manifest)
    require(updated["patches"][:-1] == manifest["patches"] and updated["cdn_version"] == TARGET,
            "previous manifest records changed")
    registered = {name for p in enabled for name in (p.get("chain") or [p.get("archive")]) if name}
    contamination = []
    for path in (root / ".cdn/cn").glob("archive-*-diff/*.zip"):
        match = re.match(r"pinball-\d+\.\d+\.\d+-(\d+\.\d+\.\d+)-", path.name)
        if match and tuple(map(int, match[1].split("."))) > (1, 4, 54):
            contamination.append(str(path.resolve()))
    report = {"schema": "shop-banner-png-encoding/v1", "base_version": BASE, "target_version": TARGET,
              "source_plan": plan.summary(), "banners": banners, "archive": integrity,
              "prior_archives_preserved": prior_archives,
              "manifest_before_sha256": codec.sha256(before_manifest),
              "manifest_after_sha256": codec.sha256(after_manifest),
              "baseline_contamination_not_used_or_modified": sorted(contamination),
              "unregistered_active_not_used_or_modified": sorted(p.name for p in (patch_root / "active").glob("*.zip") if p.name not in registered),
              "client_reader": "FileReader.convertEncryptedFile -> fileFaker.converter.PNGConverter.decode",
              "root_cause": "The .100 publisher required ordinary PNG signatures and preserved donor bytes; it omitted the client's strict stored-signature check.",
              "device_ui_verification": "pending user testing"}
    return before_manifest, after_manifest, archive_raw, snapshots, payloads, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    before, after, archive, snapshots, payloads, report = build(ROOT)
    print(json.dumps({"dry_run": not args.apply, "archive": report["archive"], "banners": report["banners"]},
                     ensure_ascii=False, indent=2))
    if not args.apply:
        return
    work = "work/cdn-1.4.101-shop-png"
    files = {f"{work}/manifest.before.json": before,
             f"assets/asset-patch/active/{ARCHIVE}": archive,
             f"assets/asset-patch/audit/{PATCH_ID}/report.json":
                 (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf8")}
    for member, raw in snapshots.items():
        files[f"{work}/effective-before/{member}"] = raw
        files[f"assets/asset-patch/{member}"] = payloads[member]
    files["assets/asset-patch/manifest.json"] = after  # Activate only after payloads are written.
    outputs = [(checked_output(ROOT, name), raw) for name, raw in files.items()]
    require((ROOT / "assets/asset-patch/manifest.json").read_bytes() == before, "manifest changed during build")
    for path, raw in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        require(path.read_bytes() == raw, f"write readback failed: {path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    main()
