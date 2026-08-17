#!/usr/bin/env python3
"""Publish the approved swim-EX multi-root payload as one active patch.

The three input archives are build candidates only.  This publisher never
writes them to the CDN tree: it merges their common, medium and android
members into a single ``assets/asset-patch/active`` archive and updates the
normal patch manifest used by the CN server.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
DEPLOY_ROOT = Path(r"F:\startpoint-cn-main")
ACTIVE_NAME = "pinball-1.4.79-1.4.80-1-swimex139997-author-g.zip"
ACTIVE_SHA256 = "787ec40d277972770a56290e1a129cc31d9c0de2406c0f096c1c02af76bc5186"
ICON_NAME = "pinball-1.4.79-1.4.80-2-0817-fantasy-two-icon-refresh.zip"
ICON_SHA256 = "6b296d8a9194ab3d81c65e393fbf268e43005facac8e3d0dd28455cafdcc4527"
PATCH_ID = "swimex139997-fantasy-icons-1.4.80"
INPUT_RULES = {
    "common": ("production/upload/", 117, "552ea55716662a701afbeee06e9520823a9ab46b5fb60c0b9bd782ee43778ba0"),
    "medium": ("production/medium_upload/", 25, "864c512a13c64b482e5cd699605de0bea27ce389b07011c426dd333a806ad577"),
    "android": ("production/android_upload/", 2, "7624bbbfe9d44e6baa00a5554de985af9ec3ca4a4d9f3e92b687eaac56694e49"),
}


class PublishError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def checked_input(kind: str, path: Path) -> tuple[bytes, list[zipfile.ZipInfo]]:
    raw = path.read_bytes()
    prefix, count, expected_hash = INPUT_RULES[kind]
    if sha256(raw) != expected_hash:
        raise PublishError(f"{kind} candidate hash drifted: {path}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if archive.testzip() is not None or len(names) != count or len(names) != len(set(names)):
            raise PublishError(f"{kind} candidate inventory drifted: {path}")
        if any(not name.startswith(prefix) for name in names):
            raise PublishError(f"{kind} candidate contains a member outside {prefix}")
    return raw, infos


def build_active(inputs: dict[str, Path]) -> tuple[bytes, list[str]]:
    output = io.BytesIO()
    names: list[str] = []
    seen: set[str] = set()
    with zipfile.ZipFile(output, "w", allowZip64=True) as target:
        for kind in ("common", "medium", "android"):
            raw, _infos = checked_input(kind, inputs[kind])
            with zipfile.ZipFile(io.BytesIO(raw)) as source:
                for info in source.infolist():
                    if info.filename in seen:
                        raise PublishError(f"duplicate active member: {info.filename}")
                    seen.add(info.filename)
                    names.append(info.filename)
                    target.writestr(info, source.read(info.filename))
    active = output.getvalue()
    if sha256(active) != ACTIVE_SHA256:
        raise PublishError("merged active archive hash drifted")
    with zipfile.ZipFile(io.BytesIO(active)) as archive:
        if archive.testzip() is not None or archive.namelist() != names or len(names) != 144:
            raise PublishError("merged active archive verification failed")
    return active, names


def updated_manifest(root: Path, active: bytes, names: list[str]) -> bytes:
    path = root / "assets/asset-patch/manifest.json"
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    matches = [patch for patch in value.get("patches", []) if patch.get("id") == PATCH_ID]
    if len(matches) != 1:
        raise PublishError(f"integrated 1.4.80 manifest entry is missing: {path}")
    icon_path = root / "assets/asset-patch/active" / ICON_NAME
    icon = icon_path.read_bytes()
    if sha256(icon) != ICON_SHA256:
        raise PublishError(f"1.4.80 icon archive receipt drifted: {icon_path}")
    with zipfile.ZipFile(io.BytesIO(icon)) as archive:
        icon_names = archive.namelist()
    patch = matches[0]
    patch["chain"] = [ACTIVE_NAME, ICON_NAME]
    patch["archive_size"] = len(active) + len(icon)
    patch["files"] = list(dict.fromkeys(names + icon_names))
    patch["archive_integrity"] = [
        {"name": ACTIVE_NAME, "size": len(active), "sha256": sha256(active), "members": len(names)},
        {"name": ICON_NAME, "size": len(icon), "sha256": sha256(icon), "members": len(icon_names)},
    ]
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".swimex-active.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def validate_published(root: Path) -> dict[str, object]:
    archive_path = root / "assets/asset-patch/active" / ACTIVE_NAME
    raw = archive_path.read_bytes()
    if sha256(raw) != ACTIVE_SHA256:
        raise PublishError(f"published swim-EX archive drifted: {archive_path}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != 144:
            raise PublishError(f"published swim-EX archive is invalid: {archive_path}")
    manifest = json.loads((root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig"))
    matches = [patch for patch in manifest.get("patches", []) if patch.get("id") == PATCH_ID]
    if len(matches) != 1 or matches[0].get("chain") != [ACTIVE_NAME, ICON_NAME]:
        raise PublishError(f"published swim-EX manifest receipt drifted under {root}")
    return {"root": str(root), "archive": ACTIVE_NAME, "size": len(raw), "sha256": sha256(raw), "members": 144}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common", type=Path)
    parser.add_argument("--medium", type=Path)
    parser.add_argument("--android", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    inputs = {"common": args.common, "medium": args.medium, "android": args.android}
    if not args.apply:
        print(json.dumps([validate_published(root) for root in (SOURCE_ROOT, DEPLOY_ROOT)], ensure_ascii=False, indent=2))
        return 0
    if any(path is None for path in inputs.values()):
        raise PublishError("--apply requires --common, --medium and --android candidate archives")
    active, names = build_active(inputs)  # type: ignore[arg-type]
    source_manifest = updated_manifest(SOURCE_ROOT, active, names)
    deploy_manifest = updated_manifest(DEPLOY_ROOT, active, names)
    if source_manifest != deploy_manifest:
        raise PublishError("source and deployed manifests differ before publication")
    for root in (SOURCE_ROOT, DEPLOY_ROOT):
        atomic_write(active, root / "assets/asset-patch/active" / ACTIVE_NAME)
        atomic_write(source_manifest, root / "assets/asset-patch/manifest.json")
    print(json.dumps([validate_published(root) for root in (SOURCE_ROOT, DEPLOY_ROOT)], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, PublishError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)
