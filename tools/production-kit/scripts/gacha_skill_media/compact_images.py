import base64
import io
import json
import math
import sys

from PIL import Image


def encode(image, lossless, quality):
    result = io.BytesIO()
    image.save(result, format="WEBP", lossless=lossless, quality=quality, method=5, exact=True)
    return result.getvalue()


def pack(item):
    prefix, data = item["uri"].split(",", 1)
    assert prefix.startswith("data:image/") and prefix.endswith(";base64")
    raw = base64.b64decode(data, validate=True)
    with Image.open(io.BytesIO(raw)) as decoded:
        original = decoded.convert("RGBA")
    width, height = original.size
    small = max(width, height) <= 320
    ratio = min(1, max(0.3, item["ratio"]))
    if small or item.get("nativeSize"):
        ratio = 1
    reduced = original
    if ratio < 1:
        reduced = original.resize((max(1, round(width * ratio)), max(1, round(height * ratio))),
                                  Image.Resampling.LANCZOS)
    lossless = small or item.get("lossless", False)
    quality = 90 if lossless else item["quality"]
    webp = encode(reduced, lossless, quality)
    if ratio == 1 and len(raw) <= len(webp):
        return {"uri": item["uri"], "width": width, "height": height,
                "sampleWidth": width, "sampleHeight": height, "lossless": True}
    return {"uri": "data:image/webp;base64," + base64.b64encode(webp).decode("ascii"),
            "width": width, "height": height, "sampleWidth": reduced.width,
            "sampleHeight": reduced.height, "lossless": lossless}


inputs = json.load(sys.stdin)
json.dump([pack(item) for item in inputs], sys.stdout, separators=(",", ":"))
