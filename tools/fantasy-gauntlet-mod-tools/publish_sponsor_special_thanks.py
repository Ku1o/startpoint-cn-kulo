"""Build the approved sponsor title against the recorded local 1.4.104 tail.

Only --apply writes repository assets. Never syncs, starts a server, or grants
real-player rewards. The preceding .104 entry-condition patch is on local hold;
this .105 append does not authorize publishing that separate change.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/lens-integration"))
import prepare_content as p
import wf_assets
import wf_dsl
from PIL import Image

BASE, VERSION = "1.4.104", "1.4.105"
PATCH_ID = "sponsor-special-thanks-1.4.105"
DEGREE_ID = "9900012"
DEGREE_LOGICAL = "master/degree/degree.orderedmap"
STRING_ID = "degree_mod_special_thanks"
IMAGE_LOGICAL = f"dynamic/degree/{STRING_ID}.png"
ART_REL = "assets/asset-patch/artwork/sponsor-special-thanks/degree_mod_special_thanks.png"
MANIFEST_REL = "assets/asset-patch/manifest.json"
AUDIT_REL = f"assets/asset-patch/audit/{PATCH_ID}"
ARCHIVE_NAME = f"pinball-{BASE}-{VERSION}-1-sponsor-special-thanks-cn.zip"
MANIFEST_SHA = "1ea0b2a34cffca4c52195fd508ab80b0a020c492b5a8101e4b2e27ed28c3d2b3"
DEGREE_SHA = "d9b8e363cf5370cf09586034437ce6dcdbf3477b7297bd533eba82879f90d857"
ART_SHA = "c2c4d06e1b386abfcf11a15a23ac2c72a01617fbed02c4a1d4cfca88ed0354ff"
DEFINITION = {
    "string_id": STRING_ID,
    "name": "特别鸣谢",
    "kana": "special_thanks",
    "condition": "感谢您对 StarPoint CN 的支持与赞助。",
    "category_id": 8,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def client_fields():
    return [STRING_ID, "9900011", DEFINITION["name"], DEFINITION["kana"],
            DEFINITION["condition"], "8", "dynamic/degree/background",
            "item/etc/degree", IMAGE_LOGICAL.removesuffix(".png")]


def build_degree(before):
    rows = p.rawmap(before)
    require(DEGREE_ID not in rows, "sponsor title ID already exists")
    require(not any(p.csvrows(raw)[0][0] == STRING_ID for raw in rows.values()),
            "sponsor title string ID already exists")
    rows[DEGREE_ID] = p.packcsv([client_fields()])
    after = p.packmap(rows)
    verify_degree(before, after)
    return after


def verify_degree(before, after):
    old, new = p.rawmap(before), p.rawmap(after)
    require(list(new) == [*old, DEGREE_ID], "unexpected title insertion/order")
    require(all(new[key] == raw for key, raw in old.items()), "existing title row changed")
    require(p.csvrows(new[DEGREE_ID]) == [client_fields()], "sponsor title fields differ")


def verify_stored_png(stored, formal):
    # The strict decoder rejects ordinary donor PNG headers on the CDN path.
    decoded = wf_assets.png_decode_stored(stored)
    require(decoded == formal, "PNG encoding changed the selected B artwork")
    require(decoded[:8] == wf_assets.PNG_REAL and decoded[24:26] == bytes([8, 6]),
            "expected standard 8-bit RGBA donor PNG")
    with Image.open(io.BytesIO(decoded)) as image:
        image.load()
        require(image.size == (320, 50) and image.mode == "RGBA", "invalid title PNG dimensions/mode")
        require(image.getchannel("A").getextrema() == (0, 255), "title alpha is missing")


def verify_archive(archive, before, formal):
    members = {p.member(("common", p.hrel(x))) for x in [DEGREE_LOGICAL, IMAGE_LOGICAL]}
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        require(z.testzip() is None and len(z.namelist()) == 2 and set(z.namelist()) == members,
                "unexpected/corrupt archive members")
        verify_degree(before, z.read(p.member(("common", p.hrel(DEGREE_LOGICAL)))))
        verify_stored_png(z.read(p.member(("common", p.hrel(IMAGE_LOGICAL)))), formal)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--work", type=Path, required=True)
    args = ap.parse_args()
    work = args.work.resolve()
    cdn = (ROOT / ".cdn").resolve()
    require(not work.is_relative_to(cdn), "work directory is inside pristine CDN")
    chain = p.Chain()
    require(chain.tail == BASE and p.sha(chain.manifest_bytes) == MANIFEST_SHA,
            "local manifest drifted; review/rebase before publishing")
    before = chain.get(("common", p.hrel(DEGREE_LOGICAL)))
    require(before is not None and p.sha(before) == DEGREE_SHA, "degree preimage drifted")
    require(chain.get(("common", p.hrel(IMAGE_LOGICAL))) is None, "image path already exists")
    definitions = p.readj(ROOT / "assets/degree_sponsor.json")
    require(definitions == {DEGREE_ID: DEFINITION}, "server sponsor definition differs")
    for rel in ["assets/degree.json", "assets/degree_rank_p5b.json"]:
        require(DEGREE_ID not in p.readj(ROOT / rel), f"duplicate title ID in {rel}")
    categories = p.rawmap(chain.get(("common", p.hrel("master/degree/degree_category.orderedmap"))))
    require(p.csvrows(categories["8"]) == [["etc", "其他"]], "title category changed")
    require(chain.get(("common", p.hrel("dynamic/degree/background.png"))) is not None,
            "shared degree background missing")
    atlas = chain.get(("common", p.hrel("item/sprite_sheet.atlas.amf3.deflate")))
    frames = wf_dsl.parse_dsl(zlib.decompress(atlas, -15))["tree"]
    icon_frames = [f for f in frames if f.get("n") == "item/etc/degree"]
    require(len(icon_frames) == 1, "shared title icon missing/duplicated in preloaded Item atlas")
    sheet = chain.get(("common", p.hrel("item/sprite_sheet.png")))
    with Image.open(io.BytesIO(wf_assets.png_decode_stored(sheet))) as image:
        image.load()
        frame = icon_frames[0]
        require(0 <= frame["x"] < frame["x"] + frame["w"] <= image.width and
                0 <= frame["y"] < frame["y"] + frame["h"] <= image.height,
                "shared title icon lies outside its texture")
    formal = (ROOT / ART_REL).read_bytes()
    require(p.sha(formal) == ART_SHA, "selected B artwork changed")
    after = build_degree(before)
    stored = wf_assets.png_encode(formal)
    verify_stored_png(stored, formal)
    payloads = {p.member(("common", p.hrel(DEGREE_LOGICAL))): after,
                p.member(("common", p.hrel(IMAGE_LOGICAL))): stored}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for member, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(member, (2026, 9, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    archive = buffer.getvalue()
    verify_archive(archive, before, formal)
    integrity = {"name": ARCHIVE_NAME, "size": len(archive), "sha256": p.sha(archive),
                 "members": 2, "files": sorted(payloads)}
    entry = {
        "id": PATCH_ID, "type": "patch", "name": "赞助者称号「特别鸣谢」",
        "description": "新增永久赞助者称号9900012，采用已选定的B款中国结图片，由管理员通过称号邮件定向发放。",
        "version": VERSION, "depends_on": BASE, "enabled": True,
        "archive": ARCHIVE_NAME, "archive_size": len(archive), "chain": [ARCHIVE_NAME],
        "archive_integrity": [integrity], "files": sorted(payloads),
        "created_at": "2026-09-09", "audit": {"directory": AUDIT_REL, "report": "report.json"},
    }
    manifest = json.loads(chain.manifest_bytes)
    manifest["patches"].append(entry)
    manifest["cdn_version"] = VERSION
    require(manifest["patches"][:-1] == chain.manifest["patches"], "preceding patches changed")
    report = {
        "status": "local_assets_verified_device_acceptance_pending",
        "degree_id": int(DEGREE_ID), "definition": DEFINITION, "client_fields": client_fields(),
        "base": BASE, "version": VERSION, "archive": integrity,
        "artwork": {"selected_variant": "B-锦绣中国结", "path": ART_REL, "sha256": ART_SHA,
                    "size": [320, 50], "mode": "RGBA", "pixels_preserved": True},
        "degree": {"logical": DEGREE_LOGICAL, "before_sha256": p.sha(before),
                   "after_sha256": p.sha(after), "preserved_rows": len(p.rawmap(before))},
        "icon": {"name": "item/etc/degree", "frame": icon_frames[0], "existing_item_atlas_reused": True},
        "source_reads": chain.reads, "platforms": ["android", "ios"], "root": "common",
        "mail": {"type": 13, "type_id": int(DEGREE_ID), "number": 0, "target": "admin_selected_player",
                 "ownership": "permanent", "eligibility": "administrator_confirms_sponsorship"},
        "manifest_before_sha256": p.sha(chain.manifest_bytes),
        "preceding_local_hold": "entry-condition-message-1.4.104; separate release authorization required",
        "device_tested": False, "runtime_delivered": False, "real_player_mails_sent": 0,
    }
    writes = {f"assets/asset-patch/active/{ARCHIVE_NAME}": archive,
              **{f"assets/asset-patch/{member}": raw for member, raw in payloads.items()},
              MANIFEST_REL: (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")}
    for rel in writes:
        dest = (ROOT / rel).resolve()
        require(dest.is_relative_to(ROOT.resolve()) and not dest.is_relative_to(cdn), "unsafe output path")
    for member in payloads:
        path = ROOT / "assets/asset-patch" / member
        expected = before if member == p.member(("common", p.hrel(DEGREE_LOGICAL))) else None
        require(not path.exists() or path.read_bytes() == expected, f"direct CDN preimage drifted: {member}")
    require(not (ROOT / f"assets/asset-patch/active/{ARCHIVE_NAME}").exists(), "archive already exists")
    if args.apply:
        work.mkdir(parents=True, exist_ok=True)
        for rel in writes:
            dest = ROOT / rel
            if dest.exists():
                snapshot = work / "before" / rel
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                require(not snapshot.exists() or snapshot.read_bytes() == dest.read_bytes(), "backup drifted")
                snapshot.write_bytes(dest.read_bytes())
        require((ROOT / MANIFEST_REL).read_bytes() == chain.manifest_bytes, "manifest changed during build")
        for rel, raw in writes.items():
            dest = ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            require(dest.read_bytes() == raw, f"write verification failed: {rel}")
        effective = p.Chain()
        require(effective.tail == VERSION, "new patch is not the effective local tail")
        for logical, expected in [(DEGREE_LOGICAL, after), (IMAGE_LOGICAL, stored)]:
            require(effective.get(("common", p.hrel(logical))) == expected, "effective CDN payload differs")
        report["manifest_after_sha256"] = p.sha(effective.manifest_bytes)
        report["effective_chain_and_direct_files_match"] = True
        p.savej(ROOT / AUDIT_REL / "report.json", report)
        p.savej(ROOT / AUDIT_REL / "manifest-entry.json", entry)
        p.savej(work / "report.json", report)
    print(json.dumps({"applied": args.apply, "degree_id": DEGREE_ID, "version": VERSION,
                      "archive": integrity, "preserved_rows": report["degree"]["preserved_rows"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
