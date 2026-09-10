"""Restore thunder Laite's historical abyss exchange exception, locally only.

Default is a read-only dry run. --apply backs up sparse preimages, changes the
two server sources, and appends two common client resources after 1.4.105.
No runtime mirror, pristine CDN, SWF, or historical archive is written.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/lens-integration"))
import prepare_content as p

BASE, VERSION = "1.4.105", "1.4.106"
PATCH_ID = "abyss-laite-exchange-" + VERSION
ARCHIVE = f"pinball-{BASE}-{VERSION}-1-abyss-laite-exchange.zip"
MANIFEST = "assets/asset-patch/manifest.json"
AUDIT = "assets/asset-patch/audit/" + PATCH_ID
SERVER_FILES = ("assets/gacha.json", "assets/gacha_cnmod.json")
ODDS = "master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap"
NOTE = "rich_text/cnmod_abyss_limited_gacha_note.html.deflate"
ODDS_BEFORE_SHA = "886418ca6013d3d36031919d59a0a12e18602aec9c8239bebb032958ff8524a8"
OLD_NOTICE = "原有22名UP角色及池内联动角色可兑换，共37名★5、7名★4"
NEW_NOTICE = "原有22名UP角色、池内联动角色及雷属性莱特可兑换，共38名★5、7名★4"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def patch_server(raw):
    # Locate this top-level pool without reformatting the 28 MB base document.
    text = raw.decode("utf-8")
    start = re.search(r'(?m)^  "990001": ', text)
    require(start is not None, "abyss pool not found")
    pool, end = json.JSONDecoder().raw_decode(text[start.end():])
    rows = [r for r in pool["pool"]["1"] if r["id"] == 131182]
    require(len(rows) == 1, "Laite missing or duplicated")
    row = rows[0]
    require(row["rank"] == 5 and row["odds"] == 5212 and row["isRateUp"] is False,
            "Laite preimage changed")
    section = text[start.end():start.end() + end]
    section, count = re.subn(
        r'("id"\s*:\s*131182\b[^{}]*"isExchangeable"\s*:\s*)(false|true)',
        lambda match: match[1] + "true", section)
    require(count == 1, "exchange flag is missing or duplicated")
    output = (text[:start.end()] + section + text[start.end() + end:]).encode("utf-8")
    expected = json.loads(raw)
    next(r for r in expected["990001"]["pool"]["1"] if r["id"] == 131182)["isExchangeable"] = True
    require(json.loads(output) == expected, "unrelated server data changed")
    return output


def patch_odds(raw):
    outer = p.rawmap(raw)
    require(list(outer) == [Path(ODDS).stem], "unexpected odds table ID")
    table_id = next(iter(outer))
    rows = p.rawmap(outer[table_id])
    matches = [(key, value) for key, value in rows.items() if p.csvrows(value)[0][0] == "131182"]
    require(len(matches) == 1 and len(rows) == 255, "client pool membership changed")
    key, value = matches[0]
    fields = p.csvrows(value)[0]
    require(fields[:5] + fields[6:] == ["131182", "5", "5212", "false", "false", "false"],
            "client Laite preimage changed")
    if fields[5] == "true":
        return raw
    require(fields[5] == "false", "invalid exchange flag")
    before_text = zlib.decompress(value).decode("utf-8")
    fields[5] = "true"
    # Preserve this row's line ending as well as every other compressed row.
    updated = before_text.replace("131182,5,5212,false,false,false,false", ",".join(fields))
    require(updated != before_text, "unexpected Laite row encoding")
    rows[key] = zlib.compress(updated.encode("utf-8"), 9)
    outer[table_id] = p.packmap(rows)
    output = p.packmap(outer)
    before_rows = p.rawmap(p.rawmap(raw)[table_id])
    after_rows = p.rawmap(p.rawmap(output)[table_id])
    require(list(before_rows) == list(after_rows), "client row keys changed")
    require([k for k in before_rows if before_rows[k] != after_rows[k]] == [key],
            "unrelated compressed client row changed")
    require(p.csvrows(after_rows[key]) == [fields], "client flag did not round-trip")
    return output


def patch_notice(raw):
    text = zlib.decompress(raw, -15).decode("utf-8")
    if NEW_NOTICE in text:
        require(text.count(NEW_NOTICE) == 1 and OLD_NOTICE not in text, "ambiguous notice")
        return raw
    require(text.count(OLD_NOTICE) == 1, "notice preimage changed")
    output = text.replace(OLD_NOTICE, NEW_NOTICE)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    encoded = compressor.compress(output.encode("utf-8")) + compressor.flush()
    require(zlib.decompress(encoded, -15).decode("utf-8") == output, "notice round-trip failed")
    return encoded


def effective_gacha():
    script = "process.stdout.write(JSON.stringify(require('./out/lib/assets').getGachaSync(990001)))"
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                            check=True, encoding="utf-8", timeout=30)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work, repo, cdn = args.work.resolve(), ROOT.resolve(), (ROOT / ".cdn").resolve()
    require(work.is_relative_to(repo / "work") and not work.is_relative_to(cdn), "unsafe work path")
    chain = p.Chain()
    if chain.tail == VERSION:
        report = p.readj(ROOT / AUDIT / "report.json")
        require(chain.manifest["patches"][-1]["id"] == PATCH_ID, "version belongs to another patch")
        for rel, digest in report["output_sha256"].items():
            require(p.sha((ROOT / rel).read_bytes()) == digest, f"applied output drifted: {rel}")
        for logical in (ODDS, NOTE):
            key = ("common", p.hrel(logical))
            require(chain.get(key) == (ROOT / "assets/asset-patch" / p.member(key)).read_bytes(),
                    "applied chain differs from direct source")
        require(effective_gacha() == p.readj(ROOT / SERVER_FILES[1])["990001"], "runtime accessor drifted")
        print(json.dumps({"status": "already_applied_verified_no_writes", "version": VERSION}))
        return
    require(chain.tail == BASE, "resource tail changed; review the next edge before applying")
    originals = {rel: (ROOT / rel).read_bytes() for rel in SERVER_FILES}
    before_pool = json.loads(originals[SERVER_FILES[0]])["990001"]
    require(before_pool == json.loads(originals[SERVER_FILES[1]])["990001"] == effective_gacha(),
            "base, overlay, and public runtime accessor disagree")
    require("990001" not in p.readj(ROOT / "assets/gacha_rank_p5b.json"), "unexpected later abyss override")
    writes = {rel: patch_server(raw) for rel, raw in originals.items()}
    for rel, after in writes.items():
        require(patch_server(after) == after, f"server patch is not idempotent: {rel}")
    after_pool = json.loads(writes[SERVER_FILES[1]])["990001"]
    entries = [r for bucket in after_pool["pool"].values() for r in bucket]
    counts = {str(rank): sum(r["rank"] == rank and r["isExchangeable"] for r in entries) for rank in (5, 4, 3)}
    require(counts == {"5": 38, "4": 7, "3": 0}, "unexpected exchange roster")
    payloads = {}
    for logical, transform in ((ODDS, patch_odds), (NOTE, patch_notice)):
        key = ("common", p.hrel(logical))
        before = chain.get(key)
        require(before is not None, f"missing effective input: {logical}")
        if logical == ODDS:
            require(p.sha(before) == ODDS_BEFORE_SHA, "effective odds preimage changed")
            rows = [p.csvrows(raw)[0] for raw in p.rawmap(next(iter(p.rawmap(before).values()))).values()]
            expected = [[str(r["id"]), str(r["rank"]), str(r["odds"]),
                         str(r["isRateUp"]).lower(), str(r["isLimited"]).lower(),
                         str(r["isExchangeable"]).lower(), str(r["trialReadingForced"]).lower()]
                        for r in before_pool["pool"]["1"]]
            require(rows == expected, "effective client/server preimages disagree")
        member = p.member(key)
        rel = "assets/asset-patch/" + member
        require((ROOT / rel).read_bytes() == before, f"direct source drifted: {rel}")
        originals[rel] = before
        payloads[member] = transform(before)
        require(transform(payloads[member]) == payloads[member], f"non-idempotent transform: {logical}")
        writes[rel] = payloads[member]
    archive_rel = "assets/asset-patch/active/" + ARCHIVE
    require(not (ROOT / archive_rel).exists() and not (ROOT / AUDIT).exists(), "output already exists")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for member, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(member, (2026, 9, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    writes[archive_rel] = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(writes[archive_rel])) as archive:
        require(archive.testzip() is None and archive.namelist() == sorted(payloads), "ZIP members/CRC failed")
        require(all(archive.read(n) == raw for n, raw in payloads.items()), "ZIP readback failed")
    integrity = {"name": ARCHIVE, "size": len(writes[archive_rel]), "sha256": p.sha(writes[archive_rel]),
                 "members": len(payloads), "files": sorted(payloads)}
    entry = {"id": PATCH_ID, "type": "patch", "name": "补回雷属性莱特的深渊兑换资格",
             "description": "恢复131182的250点兑换资格，共38名五星及7名四星可兑换；抽取权重和其他角色资格保持原值。",
             "version": VERSION, "depends_on": BASE, "enabled": True,
             "archive": ARCHIVE, "archive_size": integrity["size"], "chain": [ARCHIVE],
             "archive_integrity": [integrity], "files": sorted(payloads), "created_at": "2026-09-09",
             "audit": {"directory": AUDIT, "report": "report.json"}}
    manifest_text = chain.manifest_bytes.decode("utf-8")
    ending = re.search(r"(\r?\n)  \]\r?\n\}\s*$", manifest_text)
    require(ending is not None, "unexpected manifest format")
    nl = ending[1]
    rendered = nl.join("    " + line for line in json.dumps(entry, ensure_ascii=False, indent=2).splitlines())
    manifest_text = manifest_text[:ending.start()] + "," + nl + rendered + manifest_text[ending.start():]
    manifest_text = manifest_text.replace(f'"cdn_version": "{BASE}"', f'"cdn_version": "{VERSION}"', 1)
    manifest_output = manifest_text.encode("utf-8")
    expected_manifest = json.loads(chain.manifest_bytes)
    expected_manifest["cdn_version"] = VERSION
    expected_manifest["patches"].append(entry)
    require(json.loads(manifest_output) == expected_manifest, "existing manifest entries changed")
    originals[MANIFEST] = chain.manifest_bytes
    writes[MANIFEST] = manifest_output  # Activate only after all payloads exist.
    contamination = []
    for path in (cdn / "cn").glob("archive-*-diff/*.zip"):
        match = re.match(r"pinball-\d+\.\d+\.\d+-(\d+\.\d+\.\d+)-", path.name)
        if match and tuple(map(int, match[1].split("."))) > (1, 4, 54):
            contamination.append(str(path.resolve()))
    report = {"status": "local_assets_verified_device_acceptance_pending", "base": BASE, "version": VERSION,
              "character_id": 131182, "gacha_id": 990001, "exchange_points": 250,
              "exchangeable_counts": counts, "exchangeable_total": sum(counts.values()),
              "only_server_change": "990001.pool.1[id=131182].isExchangeable: false -> true",
              "only_client_row_change": "131182 column 5: false -> true",
              "other_client_compressed_rows_preserved": 254, "probabilities_unchanged": True,
              "idempotent_transforms_verified": True, "archive": integrity, "source_reads": chain.reads,
              "manifest_before_sha256": p.sha(chain.manifest_bytes),
              "before_sha256": {rel: p.sha(raw) for rel, raw in originals.items()},
              "output_sha256": {rel: p.sha(raw) for rel, raw in writes.items()},
              "baseline_contamination_not_used_or_modified": sorted(contamination),
              "platforms": ["android", "ios"], "resource_root": "common",
              "runtime_delivered": False, "device_tested": False, "cloud_overlay_created": False,
              "backup_directory": str(work / "before")}
    for rel in [*writes, AUDIT + "/report.json"]:
        dest = (ROOT / rel).resolve()
        require(dest.is_relative_to(repo) and not dest.is_relative_to(cdn), f"unsafe output: {rel}")
    if args.apply:
        for rel, before in originals.items():
            backup = work / "before" / rel
            require(not backup.exists() or backup.read_bytes() == before, f"backup already differs: {rel}")
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(before)
        require(all((ROOT / rel).read_bytes() == before for rel, before in originals.items()),
                "inputs changed during preparation; no output applied")
        p.savej(ROOT / AUDIT / "report.json", report)
        for rel, raw in writes.items():
            dest = ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            require(dest.read_bytes() == raw, f"written bytes differ: {rel}")
        require(effective_gacha() == after_pool, "runtime accessor does not select the corrected pool")
    print(json.dumps({"applied": args.apply, "version": VERSION, "archive": integrity,
                      "exchangeable_total": sum(counts.values()), "backup_directory": str(work / "before")},
                     ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
