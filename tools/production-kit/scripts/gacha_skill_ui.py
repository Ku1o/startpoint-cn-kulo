"""Compare a bound native recording with all phases of its generated gacha UI."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def bind(base: Path, reference: dict) -> dict:
    path = (base / reference["file"]).resolve()
    data = path.read_bytes()
    result = {"file": str(path), "sha256": digest(data), "bytes": len(data)}
    if result["sha256"] != reference["sha256"] or reference.get("bytes", len(data)) != len(data):
        raise ValueError(f"Input identity changed for {path}")
    return result


def rgba(path, size):
    with Image.open(path) as source:
        if source.size != tuple(size):
            raise ValueError(f"Wrong dimensions for {path}: {source.size}")
        return source.convert("RGBA")


def ranges(rows, predicate):
    spans = []
    for row in rows:
        if not predicate(row):
            continue
        tick, frame = row["tick"], row["battleFrame"]
        if spans and spans[-1]["lastTick"] == tick - 1:
            spans[-1].update(lastTick=tick, lastBattleFrame=frame)
        else:
            spans.append(dict(firstTick=tick, lastTick=tick, firstBattleFrame=frame, lastBattleFrame=frame))
    return spans


def alpha_probe(ball, alpha, bounds, clip, viewport, radius):
    left, top, width, height = viewport
    x = round(left + ball["x"] - bounds[0] - clip[0])
    y = round(top + ball["y"] - bounds[1] - clip[1])
    right, bottom = left + width, top + height
    center = alpha.getpixel((x, y)) if left <= x < right and top <= y < bottom else None
    x1, x2 = max(x - radius, left), min(x + radius, right)
    y1, y2 = max(y - radius, top), min(y + radius, bottom)
    histogram = alpha.crop((x1, y1, x2, y2)).histogram() if x2 > x1 and y2 > y1 else [0] * 256
    area = (radius * 2) ** 2
    return dict(x=x, y=y, anchorAlpha=center, nearAnchorOpaque=sum(histogram[250:]) / area,
                nearAnchorClipped=1 - sum(histogram) / area)


def choose_ticks(frames, extra):
    selected = {min(12, len(frames)-1), max(0, len(frames)-8), *extra}
    if min(selected) < 0 or max(selected) >= len(frames):
        raise ValueError("Review tick falls outside captured frames")
    cutins = [index for index, frame in enumerate(frames) if frame["inSkillCutin"]]
    if cutins:
        selected.update({cutins[0], (cutins[0] + cutins[-1]) // 2, cutins[-1]})
    execution = next((i for i, frame in enumerate(frames) if any(
        member and member["skillExecutions"] > 0 for member in frame["members"])), None)
    if execution is not None:
        selected.update(min(execution + delta, len(frames)-1) for delta in (0, 4, 12, 24, 36, 60, 90))
    selected.add(min(range(len(frames)), key=lambda i: frames[i]["ball"]["x"]))
    selected.add(max(range(len(frames)), key=lambda i: frames[i]["ball"]["y"]))
    return selected


def terrain_bounds(base, capture, report, role):
    if "terrainBoundsWorld" in report["input"]:
        return report["input"]["terrainBoundsWorld"], None
    fixture = report["input"].get("fixtureBook")
    if fixture:
        reference = bind(base, {"file": fixture.get("file", fixture.get("path")), "sha256": fixture["sha256"]})
        document = read(Path(reference["file"]))
        scene = next(row for row in document["scenes"] if str(row["roleId"]) == role)
        row = scene["gachaRow"]
        if (scene["questId"], row["log"] + ".battle.amf3.deflate", [row["clip"]["left"], row["clip"]["top"]]) != (
                report["input"]["quest"], report["input"]["nativeLog"], report["input"]["clip"]):
            raise ValueError("Scene quest/log/crop differs from native evidence")
        return [round(value) * 6 for value in scene["terrainBounds"]], reference
    if "terrainBoundsWorld" in capture:
        return capture["terrainBoundsWorld"], None
    raise ValueError("Native evidence needs fixtureBook or terrainBoundsWorld")


def audit(config_path: Path, role: str):
    base = config_path.resolve().parent
    config = read(config_path)
    if config["schemaVersion"] != 1 or re.fullmatch(r"[1-9]\d*", role) is None:
        raise ValueError("Unsupported media configuration")
    capture, = (item for item in config["captures"] if str(item["roleId"]) == role)
    native = bind(base, capture["receipt"])
    report = read(Path(native["file"]))
    if (report["schemaVersion"], report["kind"], report["passed"], str(report["input"]["role"])) != (
            1, "native-gacha-capture", True, role):
        raise ValueError("Unverified or mismatched native capture")
    stage, viewport, fps = (report["presentation"][key] for key in ("stage", "viewport", "fps"))
    left, top, width, height = viewport
    if not (0 <= left < left + width <= stage[0] and 0 <= top < top + height <= stage[1]):
        raise ValueError("Native viewport lies outside stage")
    host = bind(base, report["captureReceipt"])
    source = read(Path(host["file"]))
    frames = source["nativeFrames"]
    if not source["passed"] or source["viewPhase"] != "native-finished" or not frames:
        raise ValueError("Native recording has no verified Finish")
    if (len(frames) != report["pngs"]["count"] or any(frame["tick"] != i for i, frame in enumerate(frames))
            or frames[-1]["previewStateTag"] != "Finish"):
        raise ValueError("Expected contiguous native frames through Finish")
    bounds, scene = terrain_bounds(base, capture, report, role)
    clip = report["input"]["clip"]
    packed = bind(base, config["movie"])
    layers_file = (base / config["output"]["uiLayersDir"] / "LAYERS.json").resolve()
    layers_data = layers_file.read_bytes()
    layers = json.loads(layers_data)
    if (layers["kind"], layers["packedMovie"]["sha256"], layers["stage"], layers["nativeMask"], layers["fps"]) != (
            "gacha-ui-layers", packed["sha256"], stage, viewport, fps):
        raise ValueError("UI layers do not bind the packed Movie and native geometry")
    background = rgba(bind(base, layers["background"])["file"], stage)
    overlays = [rgba(bind(base, item)["file"], stage) for item in layers["overlays"]]
    alphas = [overlay.getchannel("A") for overlay in overlays]
    if len(layers["tickLayers"]) < len(frames):
        raise ValueError("Incomplete layer timings")
    settings = capture.get("auditSettings", {})
    ticks = choose_ticks(frames, [*config.get("keyframes", {}).get(role, []), *settings.get("keyframeTicks", [])])
    output = (base / config["output"]["auditDir"] / role).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    pairs_dir = output / "pairs"
    pairs_dir.mkdir()
    proof = output / "full-ui-proof.mp4"
    ffmpeg = config.get("tools", {}).get("ffmpeg", "ffmpeg")
    size = tuple(max(2, round(value / 4) * 2) for value in stage)
    encoder = subprocess.Popen([
        ffmpeg, "-v", "error", "-n", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(proof),
    ], stdin=subprocess.PIPE)
    frames_dir = (base / capture["framesDir"]).resolve() if "framesDir" in capture else Path(host["file"]).parent / "frames"
    rows, pairs = [], []
    sequence = hashlib.sha256()
    manifest = report["pngs"]["frameManifest"]
    try:
        for frame in frames:
            tick = frame["tick"]
            name = f"{tick:04d}.png"
            file = frames_dir / name
            source_hash = digest(file.read_bytes())
            if manifest[tick] != {"name": name, "sha256": source_hash}:
                raise ValueError(f"Native frame identity changed at {file}")
            sequence.update(f"{name} {source_hash}\n".encode("ascii"))
            raw = rgba(file, (width, height))
            phase = layers["tickLayers"][tick]
            rows.append(dict(tick=tick, battleFrame=frame["frame"], state=frame["ball"]["stateTag"],
                             **alpha_probe(frame["ball"], alphas[phase], bounds, clip, viewport, 48)))
            stage_image = background.copy()
            stage_image.paste(raw, (left, top))
            composition = Image.alpha_composite(stage_image, overlays[phase]).convert("RGB")
            thumbnail = composition.resize(size, Image.Resampling.LANCZOS)
            encoder.stdin.write(thumbnail.tobytes())
            if tick not in ticks:
                continue
            pair = Image.new("RGB", (2*size[0], size[1]+30), "#151b26")
            pair.paste(stage_image.convert("RGB").resize(size, Image.Resampling.LANCZOS), (0, 30))
            pair.paste(thumbnail, (size[0], 30))
            label = ImageDraw.Draw(pair)
            label.text((10, 8), f"Native image | F{frame['frame']} / tick {tick}", fill="white")
            label.text((size[0]+10, 8), "Same frame | complete gacha UI", fill="white")
            pair_file = pairs_dir / f"{tick:04d}-F{frame['frame']}.webp"
            pair.save(pair_file, quality=92)
            pairs.append(dict(tick=tick, battleFrame=frame["frame"], comparison=str(pair_file),
                              sha256=digest(pair_file.read_bytes())))
        if sequence.hexdigest() != report["pngs"]["sequenceSHA256"] or len(manifest) != len(frames):
            raise ValueError("Original native PNG sequence changed")
        encoder.stdin.close()
        if encoder.wait(timeout=30):
            raise RuntimeError("Full UI proof video failed")
    except BaseException:
        if encoder.poll() is None:
            encoder.kill()
        encoder.wait()
        raise
    subprocess.run([ffmpeg, "-v", "error", "-i", str(proof), "-f", "null", "-"], check=True, timeout=120)
    result = {
        "schemaVersion": 1, "kind": "native-gacha-full-ui-audit", "roleId": role,
        "inputs": {"native": native, "host": host, "packedMovie": packed, "scene": scene,
                   "terrainSHA256": report["input"].get("terrain", {}).get("sha256"),
                   "nativePNGSequenceSHA256": sequence.hexdigest(),
                   "layers": {"file": str(layers_file), "sha256": digest(layers_data)}},
        "frames": len(frames), "fps": fps, "stage": stage, "nativeMask": viewport, "boundsWorld": bounds,
        "clipLeftTop": clip, "fullUIProofVideo": str(proof), "keyframeEvidence": pairs,
        "anchorOpaqueRanges": ranges(rows, lambda row: (row["anchorAlpha"] or 0) >= 250),
        "anchorOutsideMaskRanges": ranges(rows, lambda row: row["anchorAlpha"] is None),
        "anchorMethod": "Nominal terrain projection; camera shake and actor/FX bounds require visual review.",
        "humanReviewRequired": True, "framesByTick": rows,
    }
    path = output / "UI-AUDIT.json"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"roleId": role, "audit": {"file": str(path), "sha256": digest(path.read_bytes())}},
                     ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--role", required=True)
    args = parser.parse_args()
    audit(args.config, args.role)
