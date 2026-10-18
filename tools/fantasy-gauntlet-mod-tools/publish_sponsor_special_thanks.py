"""Sponsor-title definitions and validators shared by resource tools.

The historical initial publisher is retired. The compact title artwork and its
unreferenced candidate package are no longer maintained. Current title art is
read from the registered active CDN package by artwork_sources.read_artwork.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/lens-integration"))
import prepare_content as p
import wf_assets
from PIL import Image

DEGREE_ID = "9900012"
DEGREE_LOGICAL = "master/degree/degree.orderedmap"
STRING_ID = "degree_mod_special_thanks"
IMAGE_LOGICAL = f"dynamic/degree/{STRING_ID}.png"
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
    require(decoded == formal, "PNG encoding changed the supplied artwork")
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.parse_args(argv)
    parser.error("This historical publisher is retired. Use the current resource-chain tooling; no files were written.")


if __name__ == "__main__":
    main()
