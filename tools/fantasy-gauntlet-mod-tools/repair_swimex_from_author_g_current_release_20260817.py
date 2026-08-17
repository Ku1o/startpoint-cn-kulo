#!/usr/bin/env python3
"""Apply the author's final swim-EX fixes to the existing ResVer 1.4.80 edge.

Only three author-owned common payloads are changed:

* the flat custom-ability description row used by the leader ability;
* ring hit timeline (reuses a stock bodysuit-trooper sound);
* ring slash timeline (reuses stock smash/prehit sounds).

All unrelated rows and archive members are preserved byte-for-byte.  The
temporary 1.4.80 release edge is repaired in place so a clean client download
is required to receive the new bytes.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
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
from wf_export_assets import decode as decode_asset


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
DEPLOY_ROOT = Path(r"F:\startpoint-cn-main")
BACKUP_ROOT = Path(r"F:\codex\local-deploy-backups")
AUTHOR_ZIP = Path(r"F:\wfshare-swimex0817g-1.4.347-to-1.4.348.zip")
AUTHOR_ZIP_SHA256 = "28001e2f1356a0153c67126e63160ec0ad55f03b25594462522c16bb97fa00d3"
AUTHOR_PREFIX = "wfshare-1.4.347-to-1.4.348-graft/"
AUTHOR_PAYLOAD = AUTHOR_PREFIX + "client-tables/client_tables_payload.json"
AUTHOR_PAYLOAD_SHA256 = "ee966dc0651fecc1401ed840f0a310d1c7e784734720b0b22addbf57396d34c2"

PACKAGE_DIR = (
    SOURCE_ROOT
    / "tools/fantasy-gauntlet-mod-tools/work/character_packs"
    / "resistance_princess_ex_139997/package"
)
ACTIVE_RELATIVE = Path(".cdn/cn/character-releases/active.json")
LIVE_RELATIVE = Path("assets/asset-patch/production/upload")
EXPECTED_BASE_VERSION = "1.4.79"
EXPECTED_VERSION = "1.4.80"
EXPECTED_PACKAGE_ID = "resistance_princess_ex_139997"
EXPECTED_PACKAGE_VERSION = "1.0.2"
REPAIRED_PACKAGE_VERSION = "1.0.3"
EXPECTED_CURRENT_ARCHIVE_SHA256 = (
    "194f0197d8d4abd25023a00bc1aedb3d5cff995744713f71d4d23c7a13a9ae98"
)

CUSTOM_LOGICAL = "master/string/custom_ability_string.orderedmap"
CUSTOM_KEY = "override_string_resistance_princess_ex"
TEMPORARY_TEXT = "赋予强化弹射特殊强化效果"
AUTHOR_TEXT = "追加「剑之斩击」与「拳之连突」两种特殊强化弹射"
AUTHOR_CUSTOM_ROW_SHA256 = (
    "683f7e64eb6a936c5e33423210447d561423336147b4a3e195c775c7e55a97e3"
)

HIT_TIMELINE = (
    "battle/effect/skill_unique/resistance_princess_ex/ring/"
    "resistance_princess_ex_ring_hit.timeline.amf3.deflate"
)
SLASH_TIMELINE = (
    "battle/effect/skill_unique/resistance_princess_ex/ring/"
    "resistance_princess_ex_ring_slash.timeline.amf3.deflate"
)
EXPECTED_TIMELINES = {
    HIT_TIMELINE: {
        "old_sha256": "2f624a980e2856eb7d9d0faa699ee24239224c407c9407e90794c6fb5c7fb33e",
        "author_sha256": "9b41cd3329280037030a3118793d42a2343d30585583cf845c59cb5b7332ac6a",
        "required_sounds": ["sound_effect/unique/se_bodysuit_trooper_hit"],
    },
    SLASH_TIMELINE: {
        "old_sha256": "e9fa80c4576c5bdd5c206acb7b80700b8f124ac557f829146b42a4cb38f371ad",
        "author_sha256": "5049f2728878b8e2f35e02e5e4fc2895a5d56890ca974aa16df9e12bd57ba7f8",
        "required_sounds": [
            "sound_effect/unique/se_bodysuit_trooper_smash",
            "sound_effect/unique/se_bodysuit_trooper_prehit",
        ],
    },
}
FORBIDDEN_SOUND_PREFIX = "sound_effect/unique/se_resistance_princess_ex_ring_"


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


def package_path(logical: str) -> Path:
    return PACKAGE_DIR / "roots/common" / Path(*logical.split("/"))


def load_author_payloads() -> dict[str, bytes]:
    if sha256_file(AUTHOR_ZIP) != AUTHOR_ZIP_SHA256:
        raise RepairError("author archive hash does not match the approved h2/g payload")
    found: dict[str, list[bytes]] = {logical: [] for logical in EXPECTED_TIMELINES}
    with zipfile.ZipFile(AUTHOR_ZIP) as outer:
        payload_raw = outer.read(AUTHOR_PAYLOAD)
        if sha256_bytes(payload_raw) != AUTHOR_PAYLOAD_SHA256:
            raise RepairError("author client-table payload receipt drifted")
        payload = json.loads(payload_raw.decode("utf-8"))
        custom_rows = payload.get(CUSTOM_LOGICAL)
        if not isinstance(custom_rows, dict) or set(custom_rows) < {CUSTOM_KEY}:
            raise RepairError("author custom-ability table lacks the swim-EX key")
        author_custom = base64.b64decode(custom_rows[CUSTOM_KEY], validate=True)
        if sha256_bytes(author_custom) != AUTHOR_CUSTOM_ROW_SHA256:
            raise RepairError("author custom-ability row drifted")
        if zlib.decompress(author_custom).decode("utf-8") != AUTHOR_TEXT:
            raise RepairError("author custom-ability text failed semantic verification")

        targets = {physical_member(logical): logical for logical in EXPECTED_TIMELINES}
        for outer_info in outer.infolist():
            if (
                "archive-common-diff/" not in outer_info.filename
                or not outer_info.filename.lower().endswith(".zip")
            ):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(outer_info))) as inner:
                for info in inner.infolist():
                    logical = targets.get(info.filename)
                    if logical is not None:
                        found[logical].append(inner.read(info))

    result = {CUSTOM_LOGICAL: author_custom}
    for logical, matches in found.items():
        if len(matches) != 1:
            raise RepairError(f"author archive must contain exactly one {logical}")
        raw = matches[0]
        expected = EXPECTED_TIMELINES[logical]
        if sha256_bytes(raw) != expected["author_sha256"]:
            raise RepairError(f"author timeline receipt drifted: {logical}")
        extension, decoded = decode_asset(raw)
        if extension != ".json":
            raise RepairError(f"author timeline is not valid AMF3: {logical}")
        timeline = json.loads(decoded.decode("utf-8"))
        sounds = [item.get("path") for item in timeline.get("sounds", [])]
        if sounds != expected["required_sounds"]:
            raise RepairError(f"author timeline sound references drifted: {logical}")
        if any(str(sound).startswith(FORBIDDEN_SOUND_PREFIX) for sound in sounds):
            raise RepairError(f"author timeline still references missing swim-EX MP3: {logical}")
        result[logical] = raw
    return result


def validate_stock_sounds() -> None:
    candidates = [
        DEPLOY_ROOT / ".cdn/cn/EntityLists/10939-android_medium.csv",
        DEPLOY_ROOT / ".cdn/cn/entities/10939-android_medium.csv",
    ]
    entity_path = next((path for path in candidates if path.is_file()), None)
    if entity_path is None:
        raise RepairError("cannot validate stock sound assets without an entity list")
    entity_text = entity_path.read_text(encoding="utf-8-sig", errors="replace")
    for logical in (
        "sound_effect/unique/se_bodysuit_trooper_hit.mp3",
        "sound_effect/unique/se_bodysuit_trooper_smash.mp3",
        "sound_effect/unique/se_bodysuit_trooper_prehit.mp3",
    ):
        if physical_member(logical) not in entity_text:
            raise RepairError(f"stock replacement sound is absent from the client catalog: {logical}")


def load_active(root: Path) -> tuple[Path, bytes, dict, Path]:
    path = root / ACTIVE_RELATIVE
    raw = path.read_bytes()
    active = json.loads(raw.decode("utf-8-sig"))
    releases = active.get("releases")
    if active.get("base_version") != EXPECTED_BASE_VERSION:
        raise RepairError(f"unexpected active base version: {path}")
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
        raise RepairError(f"active release has no unique common archive: {path}")
    entry = common[0]
    archive = root / ".cdn/cn" / str(entry["relative_path"])
    if not archive.is_file():
        raise RepairError(f"active common archive is missing: {archive}")
    if archive.stat().st_size != entry.get("size") or sha256_file(archive) != entry.get("sha256"):
        raise RepairError(f"active common archive receipt drifted: {archive}")
    return path, raw, active, archive


def build_author_table(current: bytes, author_row: bytes) -> bytes:
    ordered = core.read_orderedmap_raw_rows_from_bytes(current, CUSTOM_LOGICAL)
    if len(ordered.keys) != len(set(ordered.keys)):
        raise RepairError("current custom-ability table contains duplicate keys")
    rows = dict(zip(ordered.keys, ordered.rows))
    if CUSTOM_KEY not in rows:
        raise RepairError("current custom-ability table lacks the temporary swim-EX row")
    if zlib.decompress(rows[CUSTOM_KEY]).decode("utf-8") != TEMPORARY_TEXT:
        raise RepairError("current swim-EX custom-ability row is not the expected temporary text")
    preserved = {key: value for key, value in rows.items() if key != CUSTOM_KEY}
    index = ordered.keys.index(CUSTOM_KEY)
    ordered.rows[index] = author_row
    repaired = core.build_orderedmap_raw_rows(ordered)
    checked = core.read_orderedmap_raw_rows_from_bytes(repaired, CUSTOM_LOGICAL)
    after = dict(zip(checked.keys, checked.rows))
    if checked.keys != ordered.keys or after[CUSTOM_KEY] != author_row:
        raise RepairError("repaired custom-ability table failed row verification")
    if any(after[key] != value for key, value in preserved.items()):
        raise RepairError("repaired custom-ability table changed an unrelated row")
    return repaired


def rebuild_archive(source: Path, output: Path, replacements: dict[str, bytes]) -> None:
    member_replacements = {physical_member(logical): raw for logical, raw in replacements.items()}
    with zipfile.ZipFile(source, "r") as existing:
        infos = existing.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise RepairError("current common archive contains duplicate members")
        if any(names.count(member) != 1 for member in member_replacements):
            raise RepairError("current common archive lacks one of the three replaceable members")
        preserved = {
            info.filename: sha256_bytes(existing.read(info.filename))
            for info in infos
            if info.filename not in member_replacements
        }
        with zipfile.ZipFile(output, "w", allowZip64=True) as repaired:
            for info in infos:
                payload = member_replacements.get(info.filename, existing.read(info.filename))
                repaired.writestr(info, payload)
    with zipfile.ZipFile(output, "r") as repaired:
        if repaired.namelist() != names or len(repaired.namelist()) != len(set(repaired.namelist())):
            raise RepairError("repaired common archive member inventory changed")
        for name, digest in preserved.items():
            if sha256_bytes(repaired.read(name)) != digest:
                raise RepairError(f"repaired archive changed an unrelated member: {name}")
        for member, payload in member_replacements.items():
            if repaired.read(member) != payload:
                raise RepairError(f"repaired archive payload mismatch: {member}")


def updated_package_manifest(replacements: dict[str, bytes]) -> tuple[dict, bytes]:
    manifest_path = PACKAGE_DIR / "manifest.json"
    manifest = character_pack.load_manifest(manifest_path)
    errors = character_pack.validate_manifest(manifest, PACKAGE_DIR)
    if errors:
        raise RepairError("current character package invalid: " + "; ".join(errors))
    if (
        manifest.get("package_id") != EXPECTED_PACKAGE_ID
        or manifest.get("package_version") != EXPECTED_PACKAGE_VERSION
    ):
        raise RepairError("character package is not the expected pre-author-fix version")
    entries = {item["logical_path"]: item for item in manifest["roots"]["common"]}
    for logical, raw in replacements.items():
        entry = entries.get(logical)
        if entry is None:
            raise RepairError(f"character package lacks root entry: {logical}")
        entry["sha256"] = sha256_bytes(raw)
        entry["size"] = len(raw)
    manifest["package_version"] = REPAIRED_PACKAGE_VERSION
    manifest["qa"]["workspace_input_sha256"] = AUTHOR_ZIP_SHA256
    manifest["snapshot"]["source_outer_zip_sha256"] = AUTHOR_ZIP_SHA256
    manifest["snapshot"]["safe_merge_scope"] = "swimex0817g-author-completion"
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
    temporary = target.with_name(target.name + ".swimex-author-g.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".swimex-author-g.tmp")
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

    author = load_author_payloads()
    validate_stock_sounds()
    source_active_path, source_active_raw, source_active, source_archive = load_active(SOURCE_ROOT)
    deploy_active_path, deploy_active_raw, deploy_active, deploy_archive = load_active(DEPLOY_ROOT)
    if source_active_raw != deploy_active_raw or sha256_file(source_archive) != sha256_file(deploy_archive):
        raise RepairError("source and deployed active releases differ")
    if sha256_file(source_archive) != EXPECTED_CURRENT_ARCHIVE_SHA256:
        raise RepairError("current common archive is not the expected 1.4.80 pre-author-fix archive")

    with zipfile.ZipFile(source_archive) as current_zip:
        current_table = current_zip.read(physical_member(CUSTOM_LOGICAL))
        for logical, expected in EXPECTED_TIMELINES.items():
            current = current_zip.read(physical_member(logical))
            if sha256_bytes(current) != expected["old_sha256"]:
                raise RepairError(f"current timeline is not the expected broken revision: {logical}")
    repaired_table = build_author_table(current_table, author[CUSTOM_LOGICAL])
    replacements = {
        CUSTOM_LOGICAL: repaired_table,
        HIT_TIMELINE: author[HIT_TIMELINE],
        SLASH_TIMELINE: author[SLASH_TIMELINE],
    }

    package_manifest, package_manifest_raw = updated_package_manifest(replacements)
    package_manifest_sha256 = sha256_bytes(package_manifest_raw)
    with tempfile.TemporaryDirectory(prefix="swimex-author-g-") as temporary:
        repaired_archive = Path(temporary) / source_archive.name
        rebuild_archive(source_archive, repaired_archive, replacements)
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
            "author_archive": str(AUTHOR_ZIP),
            "author_archive_sha256": AUTHOR_ZIP_SHA256,
            "old_archive_sha256": sha256_file(source_archive),
            "new_archive_sha256": repaired_archive_sha256,
            "old_archive_size": source_archive.stat().st_size,
            "new_archive_size": repaired_archive_size,
            "package_version": REPAIRED_PACKAGE_VERSION,
            "package_manifest_sha256": package_manifest_sha256,
            "author_custom_ability_text": AUTHOR_TEXT,
            "replacements": {
                logical: {"size": len(raw), "sha256": sha256_bytes(raw)}
                for logical, raw in replacements.items()
            },
            "preserved": [
                "power_flip_action: author row already semantically identical",
                "custom_ability_power_up_string: author payload contains no swim-EX key",
                "server cdndata: preserved because author server payload contradicts its client EX row",
                "all unrelated archive members and table rows",
            ],
        }
        if not args.apply:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_ROOT / f"swimex-author-g-1.4.80-{stamp}"
        backup.mkdir(parents=True, exist_ok=False)
        package_manifest_path = PACKAGE_DIR / "manifest.json"
        targets: dict[str, Path] = {
            "source-active.json": source_active_path,
            "deploy-active.json": deploy_active_path,
            "source-common.zip": source_archive,
            "deploy-common.zip": deploy_archive,
            "package-manifest.json": package_manifest_path,
        }
        for logical in replacements:
            label = hashlib.sha1(logical.encode("utf-8")).hexdigest()[:12]
            targets[f"package-{label}"] = package_path(logical)
            targets[f"source-live-{label}"] = live_path(SOURCE_ROOT, logical)
            targets[f"deploy-live-{label}"] = live_path(DEPLOY_ROOT, logical)
        existed: dict[str, bool] = {}
        for name, path in targets.items():
            existed[name] = path.is_file()
            if existed[name]:
                shutil.copy2(path, backup / name)
        (backup / "existence.json").write_text(
            json.dumps(existed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        try:
            atomic_copy(repaired_archive, source_archive)
            atomic_copy(repaired_archive, deploy_archive)
            for logical, raw in replacements.items():
                atomic_write(raw, package_path(logical))
                atomic_write(raw, live_path(SOURCE_ROOT, logical))
                atomic_write(raw, live_path(DEPLOY_ROOT, logical))
            atomic_write(package_manifest_raw, package_manifest_path)
            atomic_write(repaired_active, source_active_path)
            atomic_write(repaired_active, deploy_active_path)

            errors = character_pack.validate_manifest(package_manifest, PACKAGE_DIR)
            if errors:
                raise RepairError("repaired character package invalid: " + "; ".join(errors))
            for archive_path in (source_archive, deploy_archive):
                if sha256_file(archive_path) != repaired_archive_sha256:
                    raise RepairError(f"archive post-write verification failed: {archive_path}")
            if source_active_path.read_bytes() != repaired_active:
                raise RepairError("source active manifest post-write verification failed")
            if deploy_active_path.read_bytes() != repaired_active:
                raise RepairError("deployed active manifest post-write verification failed")
            for logical, raw in replacements.items():
                if package_path(logical).read_bytes() != raw:
                    raise RepairError(f"package payload verification failed: {logical}")
                if live_path(SOURCE_ROOT, logical).read_bytes() != raw:
                    raise RepairError(f"source live payload verification failed: {logical}")
                if live_path(DEPLOY_ROOT, logical).read_bytes() != raw:
                    raise RepairError(f"deploy live payload verification failed: {logical}")
        except Exception:
            for name, path in targets.items():
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
