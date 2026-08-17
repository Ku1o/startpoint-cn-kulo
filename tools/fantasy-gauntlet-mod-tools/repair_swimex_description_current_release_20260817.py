#!/usr/bin/env python3
"""Repair swim-EX's missing flat ability-description key in ResVer 1.4.80.

The first in-place repair mistakenly added a nested
custom_ability_power_up_string table.  Character detail actually reads the
flat custom_ability_string table.  This transaction replaces the orphaned
member, updates the live payload and character package, and keeps the existing
1.4.79 -> 1.4.80 release edge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
import zlib
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
CORRECT_LOGICAL = "master/string/custom_ability_string.orderedmap"
WRONG_LOGICAL = "master/string/custom_ability_power_up_string.orderedmap"
DESCRIPTION_KEY = "override_string_resistance_princess_ex"
DESCRIPTION_TEXT = "赋予强化弹射特殊强化效果"
EXPECTED_BASE_VERSION = "1.4.79"
EXPECTED_VERSION = "1.4.80"
EXPECTED_PACKAGE_ID = "resistance_princess_ex_139997"
EXPECTED_PACKAGE_VERSION = "1.0.1"
REPAIRED_PACKAGE_VERSION = "1.0.2"
EXPECTED_BASE_TABLE_SHA256 = (
    "8313976e0a6251d8c338d88e77fb023bd939bdac7179cfcbc71b705314e858a7"
)
EXPECTED_CURRENT_ARCHIVE_SHA256 = (
    "ab87fb2da846c066895f700a315980b300593f30dd00ea1976b2ba65d8e7f156"
)


class RepairError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def physical_member(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def live_path(root: Path, logical: str) -> Path:
    digest = core.sha1_path(logical)
    return root / LIVE_RELATIVE / digest[:2] / digest[2:]


def load_active(root: Path) -> tuple[Path, bytes, dict, Path]:
    path = root / ACTIVE_RELATIVE
    raw = path.read_bytes()
    active = json.loads(raw.decode("utf-8-sig"))
    if active.get("base_version") != EXPECTED_BASE_VERSION:
        raise RepairError(f"unexpected active base version: {path}")
    releases = active.get("releases")
    if not isinstance(releases, list) or len(releases) != 1:
        raise RepairError(f"unexpected active release count: {path}")
    release = releases[0]
    if (
        release.get("from_version") != EXPECTED_BASE_VERSION
        or release.get("version") != EXPECTED_VERSION
        or release.get("package_id") != EXPECTED_PACKAGE_ID
    ):
        raise RepairError(f"unexpected active swim-EX release: {path}")
    common = [item for item in release.get("archives", []) if item.get("root") == "common"]
    if len(common) != 1:
        raise RepairError(f"active release must have exactly one common archive: {path}")
    entry = common[0]
    archive = root / ".cdn/cn" / Path(str(entry["relative_path"]))
    if not archive.is_file():
        raise RepairError(f"active common archive is missing: {archive}")
    if archive.stat().st_size != entry.get("size") or sha256_file(archive) != entry.get("sha256"):
        raise RepairError(f"active common archive receipt drifted: {archive}")
    return path, raw, active, archive


def build_correct_table(base: bytes) -> bytes:
    if sha256_bytes(base) != EXPECTED_BASE_TABLE_SHA256:
        raise RepairError("live custom_ability_string base table drifted")
    table = core.read_orderedmap_raw_rows_from_bytes(base, CORRECT_LOGICAL)
    if len(table.keys) != 91 or len(table.keys) != len(set(table.keys)):
        raise RepairError("unexpected custom_ability_string base key set")
    if DESCRIPTION_KEY in table.keys:
        raise RepairError("description key already exists in the expected base table")
    before = dict(zip(table.keys, table.rows))
    table.keys.append(DESCRIPTION_KEY)
    table.rows.append(zlib.compress(DESCRIPTION_TEXT.encode("utf-8")))
    repaired = core.build_orderedmap_raw_rows(table)
    verified = core.read_orderedmap_raw_rows_from_bytes(repaired, CORRECT_LOGICAL)
    if len(verified.keys) != 92 or verified.keys[-1] != DESCRIPTION_KEY:
        raise RepairError("repaired custom_ability_string key set is invalid")
    after = dict(zip(verified.keys, verified.rows))
    if any(after[key] != row for key, row in before.items()):
        raise RepairError("repaired table changed an existing row")
    text = zlib.decompress(after[DESCRIPTION_KEY]).decode("utf-8")
    if text != DESCRIPTION_TEXT:
        raise RepairError("repaired description text failed round-trip verification")
    return repaired


def rebuild_archive(source: Path, output: Path, payload: bytes) -> None:
    wrong_member = physical_member(WRONG_LOGICAL)
    correct_member = physical_member(CORRECT_LOGICAL)
    with zipfile.ZipFile(source, "r") as existing:
        infos = existing.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise RepairError("source common archive contains duplicate members")
        if names.count(wrong_member) != 1 or correct_member in names:
            raise RepairError("source common archive is not the expected first-hotfix state")
        preserved = {
            info.filename: sha256_bytes(existing.read(info.filename))
            for info in infos
            if info.filename != wrong_member
        }
        with zipfile.ZipFile(output, "w", allowZip64=True) as repaired:
            for info in infos:
                if info.filename == wrong_member:
                    continue
                repaired.writestr(info, existing.read(info.filename))
            info = zipfile.ZipInfo(correct_member, date_time=(2026, 8, 17, 15, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            repaired.writestr(info, payload)
    with zipfile.ZipFile(output, "r") as repaired:
        names = repaired.namelist()
        if len(names) != len(preserved) + 1 or len(names) != len(set(names)):
            raise RepairError("repaired common archive member count is invalid")
        if wrong_member in names or names.count(correct_member) != 1:
            raise RepairError("repaired common archive string-table members are invalid")
        for name, digest in preserved.items():
            if sha256_bytes(repaired.read(name)) != digest:
                raise RepairError(f"repaired archive changed an unrelated member: {name}")
        if repaired.read(correct_member) != payload:
            raise RepairError("repaired archive description payload mismatch")


def updated_package(payload: bytes) -> tuple[dict, bytes]:
    manifest_path = PACKAGE_DIR / "manifest.json"
    manifest = character_pack.load_manifest(manifest_path)
    errors = character_pack.validate_manifest(manifest, PACKAGE_DIR)
    if errors:
        raise RepairError("current character package invalid: " + "; ".join(errors))
    if (
        manifest.get("package_id") != EXPECTED_PACKAGE_ID
        or manifest.get("package_version") != EXPECTED_PACKAGE_VERSION
    ):
        raise RepairError("character package is not the expected first-hotfix package")

    common = manifest["roots"]["common"]
    wrong_entries = [item for item in common if item.get("logical_path") == WRONG_LOGICAL]
    if len(wrong_entries) != 1 or any(item.get("logical_path") == CORRECT_LOGICAL for item in common):
        raise RepairError("character package string-table root entries drifted")
    index = common.index(wrong_entries[0])
    common[index] = {
        "logical_path": CORRECT_LOGICAL,
        "sha256": sha256_bytes(payload),
        "size": len(payload),
    }

    claims = manifest["tables"]
    wrong_claims = [item for item in claims if item.get("logical_path") == WRONG_LOGICAL]
    if len(wrong_claims) != 1 or any(item.get("logical_path") == CORRECT_LOGICAL for item in claims):
        raise RepairError("character package string-table claims drifted")
    claim = wrong_claims[0]
    claim["logical_path"] = CORRECT_LOGICAL
    claim["codec_id"] = "flat"
    claim["outer_keys"] = [DESCRIPTION_KEY]
    claim["inner_keys"] = []
    manifest["package_version"] = REPAIRED_PACKAGE_VERSION
    return manifest, character_pack.canonical_manifest_bytes(manifest)


def updated_active(active: dict, archive_sha256: str, archive_size: int,
                   package_manifest_sha256: str) -> bytes:
    value = json.loads(json.dumps(active))
    release = value["releases"][0]
    release["package_manifest_sha256"] = package_manifest_sha256
    common = [item for item in release["archives"] if item["root"] == "common"]
    common[0]["sha256"] = archive_sha256
    common[0]["size"] = archive_size
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".swimex-description-repair.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".swimex-description-repair.tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def safe_unlink(path: Path, allowed_root: Path) -> None:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(allowed_root.resolve(strict=True))
    except ValueError as exc:
        raise RepairError(f"refusing to delete outside allowed root: {resolved}") from exc
    if path.exists():
        if not path.is_file():
            raise RepairError(f"refusing to delete non-file path: {path}")
        path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source_active_path, source_active_raw, source_active, source_archive = load_active(SOURCE_ROOT)
    deploy_active_path, deploy_active_raw, deploy_active, deploy_archive = load_active(DEPLOY_ROOT)
    if source_active_raw != deploy_active_raw or sha256_file(source_archive) != sha256_file(deploy_archive):
        raise RepairError("source and deployed active release differ")
    if sha256_file(source_archive) != EXPECTED_CURRENT_ARCHIVE_SHA256:
        raise RepairError("current common archive is not the expected first-hotfix archive")

    source_correct = live_path(SOURCE_ROOT, CORRECT_LOGICAL)
    deploy_correct = live_path(DEPLOY_ROOT, CORRECT_LOGICAL)
    source_wrong = live_path(SOURCE_ROOT, WRONG_LOGICAL)
    deploy_wrong = live_path(DEPLOY_ROOT, WRONG_LOGICAL)
    if source_correct.exists():
        raise RepairError("source correct-table live payload unexpectedly exists")
    if not deploy_correct.is_file() or sha256_file(deploy_correct) != EXPECTED_BASE_TABLE_SHA256:
        raise RepairError("deployed correct-table base payload drifted")
    if not source_wrong.is_file() or not deploy_wrong.is_file():
        raise RepairError("first-hotfix orphan payload is missing")
    if sha256_file(source_wrong) != sha256_file(deploy_wrong):
        raise RepairError("source and deployed orphan payloads differ")

    payload = build_correct_table(deploy_correct.read_bytes())
    package_manifest, package_manifest_raw = updated_package(payload)
    package_manifest_sha256 = sha256_bytes(package_manifest_raw)

    with tempfile.TemporaryDirectory(prefix="swimex-description-repair-") as temporary:
        repaired_archive = Path(temporary) / source_archive.name
        rebuild_archive(source_archive, repaired_archive, payload)
        repaired_archive_sha256 = sha256_file(repaired_archive)
        repaired_archive_size = repaired_archive.stat().st_size
        repaired_active = updated_active(
            source_active,
            repaired_archive_sha256,
            repaired_archive_size,
            package_manifest_sha256,
        )
        report = {
            "apply": args.apply,
            "from_version": EXPECTED_BASE_VERSION,
            "version": EXPECTED_VERSION,
            "removed_member": physical_member(WRONG_LOGICAL),
            "added_member": physical_member(CORRECT_LOGICAL),
            "description_key": DESCRIPTION_KEY,
            "description_text": DESCRIPTION_TEXT,
            "description_table_keys": 92,
            "description_payload_sha256": sha256_bytes(payload),
            "old_archive_sha256": sha256_file(source_archive),
            "new_archive_sha256": repaired_archive_sha256,
            "old_archive_size": source_archive.stat().st_size,
            "new_archive_size": repaired_archive_size,
            "package_version": REPAIRED_PACKAGE_VERSION,
            "package_manifest_sha256": package_manifest_sha256,
        }
        if not args.apply:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = Path(r"F:\codex\local-deploy-backups") / f"swimex-1.4.80-description-{stamp}"
        backup.mkdir(parents=True, exist_ok=False)
        package_manifest_path = PACKAGE_DIR / "manifest.json"
        package_correct = PACKAGE_DIR / "roots/common" / Path(*CORRECT_LOGICAL.split("/"))
        package_wrong = PACKAGE_DIR / "roots/common" / Path(*WRONG_LOGICAL.split("/"))
        tracked = {
            "source-active.json": source_active_path,
            "deploy-active.json": deploy_active_path,
            "source-common.zip": source_archive,
            "deploy-common.zip": deploy_archive,
            "package-manifest.json": package_manifest_path,
            "package-wrong-table.orderedmap": package_wrong,
            "package-correct-table.orderedmap": package_correct,
            "source-live-wrong": source_wrong,
            "deploy-live-wrong": deploy_wrong,
            "source-live-correct": source_correct,
            "deploy-live-correct": deploy_correct,
        }
        existed: dict[str, bool] = {}
        for name, path in tracked.items():
            existed[name] = path.is_file()
            if existed[name]:
                shutil.copy2(path, backup / name)
        (backup / "existence.json").write_text(
            json.dumps(existed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        try:
            atomic_copy(repaired_archive, source_archive)
            atomic_copy(repaired_archive, deploy_archive)
            atomic_write(payload, source_correct)
            atomic_write(payload, deploy_correct)
            atomic_write(payload, package_correct)
            atomic_write(package_manifest_raw, package_manifest_path)
            safe_unlink(source_wrong, SOURCE_ROOT)
            safe_unlink(deploy_wrong, DEPLOY_ROOT)
            safe_unlink(package_wrong, PACKAGE_DIR)
            atomic_write(repaired_active, source_active_path)
            atomic_write(repaired_active, deploy_active_path)

            errors = character_pack.validate_manifest(package_manifest, PACKAGE_DIR)
            if errors:
                raise RepairError("repaired character package invalid: " + "; ".join(errors))
            if sha256_file(source_archive) != repaired_archive_sha256:
                raise RepairError("source archive post-write verification failed")
            if sha256_file(deploy_archive) != repaired_archive_sha256:
                raise RepairError("deployed archive post-write verification failed")
            if source_active_path.read_bytes() != repaired_active:
                raise RepairError("source active manifest post-write verification failed")
            if deploy_active_path.read_bytes() != repaired_active:
                raise RepairError("deployed active manifest post-write verification failed")
            if source_correct.read_bytes() != payload or deploy_correct.read_bytes() != payload:
                raise RepairError("live correct-table payload verification failed")
            if source_wrong.exists() or deploy_wrong.exists() or package_wrong.exists():
                raise RepairError("orphan wrong-table payload was not removed")
        except Exception:
            for name, path in tracked.items():
                if existed[name]:
                    atomic_copy(backup / name, path)
                elif path.exists():
                    safe_unlink(path, path.parent)
            raise

        report["backup"] = str(backup)
        (backup / "receipt.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
