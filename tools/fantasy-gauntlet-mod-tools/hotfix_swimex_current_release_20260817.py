#!/usr/bin/env python3
"""Repair the existing 1.4.80 swim-EX archive without bumping ResVer.

This is intentionally an in-place release repair for clean-client testing.  It
keeps the active 1.4.79 -> 1.4.80 edge and archive name, adds the missing
custom ability description table, and updates the active archive/hash receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import wf_character_pack as character_pack
import wf_mod_tool as core


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
DEPLOY_ROOT = Path(r"F:\startpoint-cn-main")
PACKAGE_DIR = (
    SOURCE_ROOT
    / "tools/fantasy-gauntlet-mod-tools/work/character_packs"
    / "resistance_princess_ex_139997/package"
)
ACTIVE_RELATIVE = Path(".cdn/cn/character-releases/active.json")
LIVE_RELATIVE = Path("assets/asset-patch/production/upload")
DESCRIPTION_LOGICAL = "master/string/custom_ability_power_up_string.orderedmap"
DESCRIPTION_KEY = "override_string_resistance_princess_ex"
EXPECTED_BASE_VERSION = "1.4.79"
EXPECTED_VERSION = "1.4.80"
EXPECTED_PACKAGE_ID = "resistance_princess_ex_139997"


class HotfixError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_active(root: Path) -> tuple[Path, bytes, dict]:
    path = root / ACTIVE_RELATIVE
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if value.get("base_version") != EXPECTED_BASE_VERSION:
        raise HotfixError(f"unexpected active base version in {path}")
    releases = value.get("releases")
    if not isinstance(releases, list) or len(releases) != 1:
        raise HotfixError(f"unexpected active release count in {path}")
    release = releases[0]
    if (
        release.get("from_version") != EXPECTED_BASE_VERSION
        or release.get("version") != EXPECTED_VERSION
        or release.get("package_id") != EXPECTED_PACKAGE_ID
    ):
        raise HotfixError(f"unexpected active swim-EX release in {path}")
    return path, raw, value


def common_archive(root: Path, active: dict) -> tuple[Path, dict]:
    archives = active["releases"][0].get("archives")
    common = [item for item in archives if item.get("root") == "common"]
    if len(common) != 1:
        raise HotfixError("active release must contain exactly one common archive")
    entry = common[0]
    path = root / ".cdn/cn" / Path(str(entry["relative_path"]))
    if not path.is_file():
        raise HotfixError(f"active common archive is missing: {path}")
    if path.stat().st_size != entry.get("size") or sha256_file(path) != entry.get("sha256"):
        raise HotfixError(f"active common archive receipt drifted: {path}")
    return path, entry


def description_payload() -> tuple[bytes, str, str]:
    manifest = character_pack.load_manifest(PACKAGE_DIR / "manifest.json")
    errors = character_pack.validate_manifest(manifest, PACKAGE_DIR)
    if errors:
        raise HotfixError("character package invalid: " + "; ".join(errors))
    if (
        manifest.get("package_id") != EXPECTED_PACKAGE_ID
        or manifest.get("package_version") != "1.0.1"
    ):
        raise HotfixError("character package is not the expected repaired package")
    package_manifest_sha256 = sha256_bytes(
        character_pack.canonical_manifest_bytes(manifest)
    )
    path = PACKAGE_DIR / "roots/common" / Path(*DESCRIPTION_LOGICAL.split("/"))
    raw = path.read_bytes()
    outer = core.read_orderedmap_raw_rows_from_bytes(raw, DESCRIPTION_LOGICAL)
    if len(outer.keys) != 35 or outer.keys.count(DESCRIPTION_KEY) != 1:
        raise HotfixError("custom description outer table is not the expected 34+1 merge")
    inner = core.read_orderedmap_file_from_bytes(
        outer.rows[outer.keys.index(DESCRIPTION_KEY)]
    )
    if list(inner) != [str(level) for level in range(1, 7)]:
        raise HotfixError("custom description row does not cover levels 1 through 6")
    if len(set(inner.values())) != 1:
        raise HotfixError("custom description level text drifted")
    digest = core.sha1_path(DESCRIPTION_LOGICAL)
    member = f"production/upload/{digest[:2]}/{digest[2:]}"
    return raw, member, package_manifest_sha256


def rebuild_archive(source: Path, output: Path, member: str, payload: bytes) -> None:
    with zipfile.ZipFile(source, "r") as existing:
        infos = existing.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise HotfixError("source common archive contains duplicate members")
        if member in names:
            raise HotfixError("source common archive already contains the hotfix member")
        before = {info.filename: sha256_bytes(existing.read(info.filename)) for info in infos}
        with zipfile.ZipFile(output, "w", allowZip64=True) as repaired:
            for info in infos:
                repaired.writestr(info, existing.read(info.filename))
            info = zipfile.ZipInfo(member, date_time=(2026, 8, 17, 14, 30, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            repaired.writestr(info, payload)
    with zipfile.ZipFile(output, "r") as repaired:
        names = repaired.namelist()
        if len(names) != len(before) + 1 or len(names) != len(set(names)):
            raise HotfixError("repaired common archive member count is invalid")
        for name, digest in before.items():
            if sha256_bytes(repaired.read(name)) != digest:
                raise HotfixError(f"repaired archive changed an existing member: {name}")
        if repaired.read(member) != payload:
            raise HotfixError("repaired archive description payload mismatch")


def active_bytes(active: dict, archive_sha256: str, archive_size: int,
                 package_manifest_sha256: str) -> bytes:
    value = json.loads(json.dumps(active))
    release = value["releases"][0]
    release["package_manifest_sha256"] = package_manifest_sha256
    for entry in release["archives"]:
        if entry["root"] == "common":
            entry["sha256"] = archive_sha256
            entry["size"] = archive_size
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".swimex-hotfix.tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".swimex-hotfix.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    raise HotfixError(
        "superseded: use repair_swimex_description_current_release_20260817.py; "
        "this historical hotfix targeted the wrong string table"
    )

    source_active_path, source_active_raw, source_active = load_active(SOURCE_ROOT)
    deploy_active_path, deploy_active_raw, deploy_active = load_active(DEPLOY_ROOT)
    if source_active_raw != deploy_active_raw:
        raise HotfixError("source and deployed active character manifests differ")
    source_archive, _source_entry = common_archive(SOURCE_ROOT, source_active)
    deploy_archive, _deploy_entry = common_archive(DEPLOY_ROOT, deploy_active)
    if sha256_file(source_archive) != sha256_file(deploy_archive):
        raise HotfixError("source and deployed common archives differ")

    payload, member, package_manifest_sha256 = description_payload()
    digest = core.sha1_path(DESCRIPTION_LOGICAL)
    source_live = SOURCE_ROOT / LIVE_RELATIVE / digest[:2] / digest[2:]
    deploy_live = DEPLOY_ROOT / LIVE_RELATIVE / digest[:2] / digest[2:]
    if source_live.exists() or deploy_live.exists():
        raise HotfixError("custom description live payload already exists")

    with tempfile.TemporaryDirectory(prefix="swimex-1.4.80-hotfix-") as temporary:
        repaired_archive = Path(temporary) / source_archive.name
        rebuild_archive(source_archive, repaired_archive, member, payload)
        repaired_sha256 = sha256_file(repaired_archive)
        repaired_size = repaired_archive.stat().st_size
        repaired_active = active_bytes(
            source_active,
            repaired_sha256,
            repaired_size,
            package_manifest_sha256,
        )
        report = {
            "apply": args.apply,
            "from_version": EXPECTED_BASE_VERSION,
            "version": EXPECTED_VERSION,
            "archive": source_archive.name,
            "old_archive_sha256": sha256_file(source_archive),
            "new_archive_sha256": repaired_sha256,
            "old_archive_size": source_archive.stat().st_size,
            "new_archive_size": repaired_size,
            "added_member": member,
            "added_payload_sha256": sha256_bytes(payload),
            "package_manifest_sha256": package_manifest_sha256,
        }
        if not args.apply:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = Path(r"F:\codex\local-deploy-backups") / f"swimex-1.4.80-inplace-{stamp}"
        backup.mkdir(parents=True, exist_ok=False)
        targets = [
            ("source-active.json", source_active_path, source_active_raw),
            ("deploy-active.json", deploy_active_path, deploy_active_raw),
            ("source-common.zip", source_archive, source_archive.read_bytes()),
            ("deploy-common.zip", deploy_archive, deploy_archive.read_bytes()),
        ]
        for name, _target, raw in targets:
            (backup / name).write_bytes(raw)

        written: list[Path] = []
        try:
            atomic_copy(repaired_archive, source_archive)
            written.append(source_archive)
            atomic_copy(repaired_archive, deploy_archive)
            written.append(deploy_archive)
            atomic_write(repaired_active, source_active_path)
            written.append(source_active_path)
            atomic_write(repaired_active, deploy_active_path)
            written.append(deploy_active_path)
            atomic_write(payload, source_live)
            written.append(source_live)
            atomic_write(payload, deploy_live)
            written.append(deploy_live)

            if sha256_file(source_archive) != repaired_sha256:
                raise HotfixError("source archive post-write verification failed")
            if sha256_file(deploy_archive) != repaired_sha256:
                raise HotfixError("deployed archive post-write verification failed")
            if source_active_path.read_bytes() != repaired_active:
                raise HotfixError("source active manifest post-write verification failed")
            if deploy_active_path.read_bytes() != repaired_active:
                raise HotfixError("deployed active manifest post-write verification failed")
            if source_live.read_bytes() != payload or deploy_live.read_bytes() != payload:
                raise HotfixError("live description payload post-write verification failed")
        except Exception:
            atomic_write((backup / "source-active.json").read_bytes(), source_active_path)
            atomic_write((backup / "deploy-active.json").read_bytes(), deploy_active_path)
            atomic_copy(backup / "source-common.zip", source_archive)
            atomic_copy(backup / "deploy-common.zip", deploy_archive)
            source_live.unlink(missing_ok=True)
            deploy_live.unlink(missing_ok=True)
            raise

        report["backup"] = str(backup)
        report["written"] = [str(path) for path in written]
        (backup / "receipt.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, HotfixError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)
