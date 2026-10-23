#!/usr/bin/env python3
"""Build authenticated-admin WebP assets from a verified PNG export (offline Pillow only).

This does not touch the source resource archives, CDN manifest or game image files.
The source export maps each presentation key to the PNG actually selected by the
existing reader. Repeated PNGs are encoded once and outputs are content addressed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat, features
import PIL

SHA = re.compile(r"^[0-9a-f]{64}$")
PNG_HEADER = b"\x89PNG\r\n\x1a\n"
STORED_HEADER = b"\x89png\r\n\x1a\n"
MAX_SIZE = (960, 360)
RECIPE = {"format": "webp", "quality": 92, "method": 6, "lossless": False,
          "exact": True, "alphaQuality": 100, "maxWidth": MAX_SIZE[0],
          "maxHeight": MAX_SIZE[1], "resize": "lanczos", "withoutEnlargement": True,
          "encoder": {"pillow": PIL.__version__, "libwebp": features.version("webp")}}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def guarded_output(candidate: Path, export_path: Path) -> Path:
    """Check every write destination before loading/encoding or creating output folders."""
    normalized = candidate.resolve()
    if any(part.rstrip(" .").casefold() == ".cdn" for part in (*candidate.parts, *normalized.parts)):
        raise ValueError("Output must not write to any .cdn directory")
    inventory = subprocess.run(['git', '-c', 'core.quotePath=false', 'worktree', 'list', '--porcelain'],
                               cwd=Path(__file__).resolve().parent.parent, check=True,
                               encoding='utf8', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    worktrees = [Path(line[9:]).resolve(strict=True) for line in inventory.stdout.splitlines()
                 if line.startswith('worktree ')]
    if not worktrees:
        raise ValueError('Cannot establish protected Git worktree inventory')
    protected_source = worktrees[0]
    if normalized == protected_source or normalized.is_relative_to(protected_source):
        raise ValueError("Output must not write to the protected source repository")
    export_directory = export_path.parent.resolve()
    if normalized == export_directory or normalized.is_relative_to(export_directory):
        raise ValueError("Output must not overwrite the source export or its original images")
    return normalized


def write_exact(file: Path, data: bytes) -> None:
    if file.exists():
        if file.read_bytes() != data:
            raise ValueError(f"Refusing to replace different existing output: {file}")
    else:
        file.write_bytes(data)


def load_sources(export_path: Path) -> tuple[dict, dict[str, dict]]:
    source = json.loads(export_path.read_text(encoding="utf-8"))
    if source.get("schemaVersion") != 1:
        raise ValueError("Unsupported source export schema")
    for key in ("manifestSha256", "presentationSha256"):
        if not SHA.fullmatch(source["source"][key]):
            raise ValueError("Invalid source identity")
    originals = {}
    for sha, record in sorted(source["originals"].items()):
        if not SHA.fullmatch(sha) or record["file"] != f"originals/{sha}.png":
            raise ValueError("Invalid source filename/hash")
        file = (export_path.parent / record["file"]).resolve(strict=True)
        if file.parent != (export_path.parent / "originals").resolve(strict=True):
            raise ValueError("Source path must stay in export originals")
        data = file.read_bytes()
        if len(data) != record["bytes"] or digest(data) != sha or not data.startswith(PNG_HEADER):
            raise ValueError("Source PNG bytes/hash mismatch")
        with Image.open(io.BytesIO(data)) as original:
            if original.format != "PNG" or original.size != (record["width"], record["height"]):
                raise ValueError("Source PNG dimensions/format mismatch")
            if min(original.size) < 1 or max(original.size) > 16384:
                raise ValueError("Invalid source PNG dimensions")
            image = original.convert("RGBA")
        resized = image.copy()
        resized.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS, reducing_gap=3.0)
        originals[sha] = {"bytes": data, "rawHashes": {sha, digest(STORED_HEADER + data[8:])},
                          "image": image, "resized": resized, "file": file,
                          "record": record}
    used = set()
    for key, row in source["rows"].items():
        if not isinstance(key, str) or not isinstance(row.get("sourceLogical"), str):
            raise ValueError("Invalid presentation row")
        sha = row["sourcePngSha256"]
        if sha not in originals or row["sourceRawSha256"] not in originals[sha]["rawHashes"]:
            raise ValueError(f"Source raw/PNG identity mismatch: {key}")
        used.add(sha)
    if used != set(originals):
        raise ValueError("Export must contain exactly the selected unique PNGs")
    return source, originals


def encode(image: Image.Image, quality: int = 92, lossless: bool = False) -> tuple[bytes, Image.Image]:
    stream = io.BytesIO()
    image.save(stream, "WEBP", quality=quality, method=6, lossless=lossless,
               exact=True, alpha_quality=100)
    data = stream.getvalue()
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("Invalid WebP output")
    with Image.open(io.BytesIO(data)) as stored:
        if stored.format != "WEBP" or stored.size != image.size:
            raise ValueError("WebP readback mismatch")
        decoded = stored.convert("RGBA")
    if image.getchannel("A").tobytes() != decoded.getchannel("A").tobytes():
        raise ValueError("WebP changed alpha; alpha_quality=100 must be lossless")
    return data, decoded


def composite(image: Image.Image, size: tuple[int, int], background=(16, 24, 39)) -> Image.Image:
    canvas = Image.new("RGB", size, background)
    scaled = image.copy()
    scaled.thumbnail(size, Image.Resampling.LANCZOS)
    canvas.paste(scaled, ((size[0] - scaled.width) // 2, (size[1] - scaled.height) // 2), scaled)
    return canvas


def psnr(reference: Image.Image, decoded: Image.Image) -> float | None:
    total = 0.0
    for background in [(16, 24, 39), (255, 255, 255)]:
        diff = ImageChops.difference(composite(reference, reference.size, background),
                                     composite(decoded, decoded.size, background))
        total += sum(v * v for v in ImageStat.Stat(diff).rms) / 3
    mse = total / 2
    return round(10 * math.log10(255 * 255 / mse), 3) if mse else None


def compare_samples(source: dict, originals: dict[str, dict], directory: Path, font_path: Path | None = None) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    candidates = [("small-text", "gacha:3"), ("illustration-alpha", "gacha:1704"),
                  ("pixel-art", "rush_event:700011")]
    large_key = next((key for key, row in sorted(source["rows"].items())
                      if originals[row["sourcePngSha256"]]["image"].width >= 1440), None)
    if large_key:
        candidates.append(("large-banner", large_key))
    if not candidates:
        candidates = [("sample", next(iter(source["rows"])))]
    # Labels are ASCII; Chinese game lettering stays in the original image pixels.
    # The bundled Pillow font keeps comparison sheets portable without inventing glyphs.
    font = ImageFont.truetype(str(font_path), 20) if font_path else ImageFont.load_default(20)
    small = ImageFont.truetype(str(font_path), 16) if font_path else ImageFont.load_default(16)
    width, row_height, margin = 2000, 250, 18
    board = Image.new("RGB", (width, (len(candidates) + 1) * row_height), "#e5e7eb")
    draw = ImageDraw.Draw(board)
    draw.text((margin, margin), "Admin banner comparison: same displayed size; small sources are never enlarged", fill="black", font=font)
    draw.text((margin, 55), "Columns: resized PNG reference | WebP q88 | WebP q92 | WebP lossless", fill="black", font=font)
    draw.text((margin, 92), "Transparent pixels are composited on the same dark background. Source exports stay unchanged.", fill="black", font=small)
    report = {"source": source["source"], "recipe": RECIPE, "samples": []}
    detail = Image.new("RGB", (1400, len(candidates) * 260), "#e5e7eb")
    detail_draw = ImageDraw.Draw(detail)
    for row_index, (name, key) in enumerate(candidates):
        selected = source["rows"][key]
        record = originals[selected["sourcePngSha256"]]
        reference = record["resized"]
        variants = [("PNG reference", record["bytes"], reference)]
        sample = {"category": name, "key": key, "sourceLogical": selected["sourceLogical"],
                  "sourceBytes": len(record["bytes"]), "sourceSize": list(record["image"].size),
                  "thumbnailSize": list(reference.size), "variants": {}}
        for label, quality, lossless in [("q88", 88, False), ("q92", 92, False), ("lossless", 100, True)]:
            data, decoded = encode(reference, quality, lossless)
            write_exact(directory / f"{name}-{label}.webp", data)
            sample["variants"][label] = {"bytes": len(data), "psnrCompositeDb": psnr(reference, decoded),
                "alphaExact": True, "reductionPercent": round((1 - len(data) / len(record["bytes"])) * 100, 3)}
            variants.append((label, data, decoded))
        y = (row_index + 1) * row_height
        for column, (label, data, image) in enumerate(variants):
            x = column * 500 + margin
            draw.text((x, y + 5), f"{name} / {label}", fill="black", font=font)
            draw.text((x, y + 34), f"{len(data):,} B  {image.width} x {image.height}", fill="black", font=small)
            board.paste(composite(image, (464, 172)), (x, y + 64))
        # A true 2x nearest-neighbor pixel crop makes text/artifact differences visible.
        crop_w, crop_h = min(320, reference.width), min(100, reference.height)
        crop_x, crop_y = (reference.width - crop_w) // 2, (reference.height - crop_h) // 2
        box = (crop_x, crop_y, crop_x + crop_w, crop_y + crop_h)
        for column, (_, _, image) in enumerate([variants[0], variants[2]]):
            x, dy = column * 700 + margin, row_index * 260
            detail_draw.text((x, dy + 5), f"{name}: {'PNG' if column == 0 else 'q92'} crop at 2x", fill="black", font=font)
            crop = image.crop(box).resize((crop_w * 2, crop_h * 2), Image.Resampling.NEAREST)
            detail.paste(composite(crop, crop.size), (x, dy + 42))
        report["samples"].append(sample)
    board.save(directory / "comparison-cards.png", optimize=True)
    detail.save(directory / "comparison-text-crops.png", optimize=True)
    write_exact(directory / "comparison.json", json_bytes(report))
    return report


def build(source: dict, originals: dict[str, dict], output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    mapping, images = {}, {}
    for sha, original in originals.items():
        encoded, _ = encode(original["resized"])
        target = digest(encoded)
        write_exact(output / f"{target}.webp", encoded)
        images[target] = {"file": f"{target}.webp", "bytes": len(encoded),
                          "width": original["resized"].width, "height": original["resized"].height}
        mapping[sha] = target
    rows = {key: {"image": mapping[row["sourcePngSha256"]], **row}
            for key, row in sorted(source["rows"].items())}
    totals = {"entries": len(rows), "uniqueSources": len(originals), "uniqueImages": len(images),
              "sourceRowBytes": sum(len(originals[row["sourcePngSha256"]]["bytes"]) for row in rows.values()),
              "thumbnailRowBytes": sum(images[row["image"]]["bytes"] for row in rows.values()),
              "sourceUniqueBytes": sum(len(record["bytes"]) for record in originals.values()),
              "thumbnailUniqueBytes": sum(row["bytes"] for row in images.values())}
    index = {"schemaVersion": 1, "source": source["source"], "recipe": RECIPE,
             "rows": rows, "images": images, "totals": totals}
    write_exact(output / "index.json", json_bytes(index))
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-export", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--comparison-dir", type=Path)
    parser.add_argument("--comparison-font", type=Path, help="Optional TrueType font for ASCII comparison labels")
    parser.add_argument("--compare-only", action="store_true")
    args = parser.parse_args()
    if not features.check("webp"):
        parser.error("Offline Pillow must have WebP support")
    export_path = args.source_export.resolve(strict=True)
    try:
        output = guarded_output(args.output, export_path)
        comparison_directory = guarded_output(args.comparison_dir, export_path) if args.comparison_dir else None
    except ValueError as error:
        parser.error(str(error))
    source, originals = load_sources(export_path)
    if comparison_directory:
        comparison = compare_samples(source, originals, comparison_directory, args.comparison_font)
        print(json.dumps({"comparison": comparison}, ensure_ascii=False), flush=True)
    if not args.compare_only:
        index = build(source, originals, output)
        print(json.dumps({"source": source["source"], "recipe": RECIPE, "totals": index["totals"],
                          "indexSha256": digest(json_bytes(index))}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
