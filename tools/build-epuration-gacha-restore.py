"""Restore Epuration in the two existing pools on the fixed 1.4.355 resource chain.

The historical Boss-removal recipe remains immutable. Only character 179981 is
restored; every other native row keeps its key, order and compressed bytes.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import zipfile
import io

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gacha_codec", ROOT / "tools/build-gerald-fever-toggle.py")
codec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codec)

BASE = "1.4.355"
VERSION = "1.4.356"
ARCHIVE = "pinball-1.4.355-1.4.356-1-epuration-gacha-restore.zip"
TARGET = 179981
SPECS = (
    ("990001", "gacha_cnmod.json", "cnmod_abyss_limited_gacha", 1000, 150000),
    ("990002", "gacha_rank_p5b.json", "cnmod_ashen_verdict_gacha", 10000, 950000),
)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def cells(row):
    return [str(row["id"]), str(row["rank"]), str(row["odds"]),
            *(str(row[key]).lower() for key in
              ("isRateUp", "isLimited", "isExchangeable", "trialReadingForced"))]


def leaf(raw):
    rows = codec.parse_csv(codec.decode_leaf(raw))
    if len(rows) != 1 or len(rows[0]) != 7:
        raise ValueError("Expected exactly one seven-column gacha odds row")
    row = rows[0]
    if any(value not in ("true", "false") for value in row[3:]):
        raise ValueError("Invalid native Boolean column")
    if int(row[0]) <= 0 or int(row[1]) != 5 or int(row[2]) < 0:
        raise ValueError("Invalid native gacha odds identity/weight")
    return row


def base_manifest(manifest):
    result = copy.deepcopy(manifest)
    matches = [i for i, patch in enumerate(result["patches"]) if patch["version"] == VERSION]
    if matches:
        if len(matches) != 1:
            raise ValueError("Ambiguous repair edge")
        result["patches"] = result["patches"][:matches[0]]
        result["cdn_version"] = BASE
    if result["cdn_version"] != BASE or result["patches"][-1]["version"] != BASE:
        raise ValueError("Expected the reviewed 1.4.355 chain")
    return result


def prepare(root, manifest):
    base = base_manifest(manifest)
    before_removal = copy.deepcopy(base)
    index = next(i for i, p in enumerate(base["patches"]) if p["version"] == "1.4.344")
    before_removal["patches"] = before_removal["patches"][:index]
    documents = {name: json.loads((root / "assets" / name).read_bytes())
                 for name in ("gacha.json", "gacha_cnmod.json", "gacha_rank_p5b.json")}
    entries, audit = {}, []
    for gid, filename, prefix, weight, total in SPECS:
        logical = f"master/gacha_odds/{prefix}_character_5.orderedmap"
        outer_key = prefix + "_character_5"
        before = codec.read_effective(root, base, logical)
        outer = codec.rawmap(before)
        if list(outer) != [outer_key]:
            raise ValueError("Unexpected gacha outer keys")
        current = codec.rawmap(outer[outer_key])
        if any(int(leaf(raw)[0]) == TARGET for raw in current.values()):
            raise ValueError("Base already contains Epuration")
        historical = codec.rawmap(codec.rawmap(codec.read_effective(root, before_removal, logical))[outer_key])
        targets = [(key, raw) for key, raw in historical.items() if int(leaf(raw)[0]) == TARGET]
        if len(targets) != 1:
            raise ValueError("Missing/ambiguous historical Epuration slot")
        key, restored = targets[0]
        expected = [str(TARGET), "5", str(weight), "true", "true", "true", "false"]
        if key in current or leaf(restored) != expected:
            raise ValueError("Historical Epuration row differs from the reviewed contract")
        updated = {}
        for old_key in historical:
            if old_key in current:
                updated[old_key] = current[old_key]
            elif old_key == key:
                updated[key] = restored
        if list(k for k in updated if k != key) != list(current):
            raise ValueError("Unrelated native keys or order changed")
        client_rows = [leaf(raw) for raw in updated.values()]
        gacha = copy.deepcopy(documents[filename][gid])
        existing = [row for row in gacha["pool"]["1"] if row["id"] != TARGET]
        if [cells(row) for row in existing] != [leaf(raw) for raw in current.values()]:
            raise ValueError("Effective server pool differs from the native base")
        target = {"id": TARGET, "rank": 5, "odds": weight, "isRateUp": True,
                  "isLimited": True, "isExchangeable": True, "rarity": weight / total * 1000,
                  "trialReadingForced": False}
        by_id = {row["id"]: row for row in existing}
        by_id[TARGET] = target
        gacha["pool"]["1"] = [by_id[int(row[0])] for row in client_rows]
        if sum(row["odds"] for row in gacha["pool"]["1"]) != total:
            raise ValueError("Unexpected restored total weight")
        for row in gacha["pool"]["1"]:
            row["rarity"] = row["odds"] / total * 1000
        if [cells(row) for row in gacha["pool"]["1"]] != client_rows:
            raise ValueError("Restored server/native rows differ")
        documents[filename][gid] = gacha
        # The old base mirror still contains closed zero-weight placeholders.
        # Mirror the actual winning pool, keeping those closed entries absent.
        documents["gacha.json"][gid] = copy.deepcopy(gacha)
        entries[codec.member(logical)] = codec.packmap({outer_key: codec.packmap(updated)})
        audit.append({"gachaId": int(gid), "logical": logical, "restoredKey": key,
                      "weight": weight, "fiveStarTotal": total, "exchangePoints": 250,
                      "preservedRows": len(current), "beforeSha256": codec.sha(before),
                      "afterSha256": codec.sha(entries[codec.member(logical)])})
    return documents, entries, audit


def verify(root):
    manifest = json.loads((root / "assets/asset-patch/manifest.json").read_bytes())
    documents, expected, audit = prepare(root, manifest)
    patch = next(p for p in manifest["patches"] if p["version"] == VERSION)
    raw = (root / "assets/asset-patch/active" / ARCHIVE).read_bytes()
    names = sorted(expected)
    receipt = {"name": ARCHIVE, "size": len(raw), "sha256": codec.sha(raw), "members": 2, "files": names}
    if (patch["depends_on"] != BASE or not patch["enabled"] or patch["chain"] != [ARCHIVE]
            or patch["archive"] != ARCHIVE or patch["archive_size"] != len(raw)
            or patch["files"] != names or patch["archive_integrity"] != [receipt]):
        raise ValueError("Repair manifest/integrity mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != names or archive.testzip():
            raise ValueError("Invalid repair archive")
        for name in names:
            a, b = codec.rawmap(archive.read(name)), codec.rawmap(expected[name])
            if list(a) != list(b):
                raise ValueError("Outer keys differ")
            a, b = codec.rawmap(next(iter(a.values()))), codec.rawmap(next(iter(b.values())))
            if a != b or list(a) != list(b):
                raise ValueError("Native row bytes or order differ")
    for name, expected_document in documents.items():
        if json.loads((root / "assets" / name).read_bytes()) != expected_document:
            raise ValueError("Server mirror/normalization mismatch: " + name)
    return {"version": VERSION, "archive": receipt, "pools": audit, "deviceTested": False}


def write(root):
    manifest_path = root / "assets/asset-patch/manifest.json"
    before = manifest_path.read_bytes()
    manifest = json.loads(before)
    if any(p["version"] == VERSION for p in manifest["patches"]):
        raise ValueError("Repair version is already reserved")
    documents, entries, _ = prepare(root, manifest)
    raw = codec.archive_bytes(entries)
    names = sorted(entries)
    with (root / "assets/asset-patch/active" / ARCHIVE).open("xb") as output:
        output.write(raw)
    if manifest_path.read_bytes() != before:
        raise ValueError("Manifest changed during generation")
    for name, document in documents.items():
        (root / "assets" / name).write_bytes(encoded(document))
    manifest["cdn_version"] = VERSION
    manifest["patches"].append({
        "id": "epuration-gacha-restore-" + VERSION, "type": "patch",
        "name": "歼灭者两池抽取与250点兑换恢复",
        "description": "恢复179981深渊0.100%、竞速1.000%抽取及两池250点兑换；保留其他角色权重、兑换限制和所有旧资源边。",
        "version": VERSION, "depends_on": BASE, "enabled": True, "candidate_only": True,
        "archive": ARCHIVE, "archive_size": len(raw), "chain": [ARCHIVE],
        "archive_integrity": [{"name": ARCHIVE, "size": len(raw), "sha256": codec.sha(raw),
                               "members": len(names), "files": names}],
        "files": names, "created_at": "2026-11-02",
    })
    manifest_path.write_bytes(encoded(manifest))
    report = verify(root)
    audit_dir = root / "assets/asset-patch/audit/epuration-gacha-1.4.356"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "report.json").write_bytes(encoded(report))
    return report


def sync_loose(root):
    report = verify(root)
    patch_root = (root / "assets/asset-patch").resolve()
    with zipfile.ZipFile(patch_root / "active" / ARCHIVE) as archive:
        for name in archive.namelist():
            destination = (patch_root / name).resolve()
            if not destination.is_relative_to(patch_root) or ".cdn" in destination.parts:
                raise ValueError("Loose mirror escapes the patch root")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
            if destination.read_bytes() != archive.read(name):
                raise ValueError("Loose mirror differs from archive")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--sync-loose", action="store_true", help="Sync only the two local ignored mirrors after verification")
    args = parser.parse_args()
    result = write(ROOT) if args.write else verify(ROOT)
    if args.sync_loose:
        result = sync_loose(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
