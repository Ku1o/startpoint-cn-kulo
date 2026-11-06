from hashlib import sha256
from io import BytesIO
from math import isfinite
from PIL import Image


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return sha256(data).hexdigest()


def ranges(frames):
    spans = []
    for frame in sorted(set(frames)):
        if not spans or frame > spans[-1][1] + 1:
            spans.append([frame, frame])
        else:
            spans[-1][1] = frame
    return spans


def verify_trace(trace, expected):
    require(trace and [row["tick"] for row in trace] == list(range(len(trace))), "Capture ticks are not contiguous")
    config = expected["replay"]["config"]
    first, last = config["start_frame"] + 1, config["end_frame"] + 1
    replay_frames = [row["replayFrame"] for row in trace]
    engine_frames = [row["frame"] for row in trace]
    require(set(replay_frames) == set(range(first, last + 1)), "Native replay coverage differs from the source window")
    for key, values in (("replay", replay_frames), ("engine", engine_frames)):
        require(all(0 <= b - a <= 1 for a, b in zip(values, values[1:])), f"{key} clock skipped or regressed")
    require(all(row["previewStateTag"] == "Playing" for row in trace[:-1]) and
            trace[-1]["previewStateTag"] == "Finish" and replay_frames[-1] == last, "Native Finish sequence differs")
    require(engine_frames[-1] > engine_frames[0], "Native engine clock never advanced")
    cutins = ranges(row["replayFrame"] for row in trace if row["inSkillCutin"])
    raw_requests = [c["f"] for c in expected["replay"]["log_parts"] if c["c"][0] == 2]
    counters = [row["members"][0]["skillExecutions"] for row in trace]
    executions = [row["replayFrame"] for a, n, row in zip(counters, counters[1:], trace[1:]) for _ in range(n - a)]
    require(counters[0] == 0 and all(a <= b for a, b in zip(counters, counters[1:])), "Native execution counter regressed or started after execution")
    require(len(executions) == len(raw_requests) and len(executions) > 0, "Native execution count differs from recorded invokes")
    require(len(cutins) == len(executions) and all(end - start + 1 == 60 for start, end in cutins),
            "Native skill preparation is not one complete 60-frame cut-in per execution")
    require(all(request <= start and end < execution for request, (start, end), execution in zip(raw_requests, cutins, executions)),
            "Native request, cut-in and execution order differs")

    positions, target_hp, damaged = set(), {}, {}
    for row in trace:
        ball = row["ball"]
        require(all(isfinite(ball[k]) for k in ("x", "y", "vx", "vy")), "Non-finite native ball sample")
        positions.add((round(ball["x"], 6), round(ball["y"], 6)))
        targets = {}
        for target in row["targets"]:
            key = target["id"]
            hp = target["hp"]
            require(key and isfinite(hp), "Invalid native target ID or HP")
            require(key not in targets or targets[key] == hp, f"Duplicate target HP disagrees for {key}")
            targets[key] = hp
        for key, hp in targets.items():
            old = target_hp.get(key, hp)
            if hp < old and key not in damaged:
                damaged[key] = {"frame": row["replayFrame"], "before": old, "after": hp}
            target_hp[key] = hp

    return {"samples": len(trace), "firstPlaying": replay_frames[0], "nativeFinish": replay_frames[-1],
            "engineWindow": [engine_frames[0], engine_frames[-1]], "rawInvokeFrames": raw_requests,
            "nativeCutInSpans": cutins, "nativeExecutionFrames": executions,
            "nativeExecutionCount": counters[-1], "distinctBallPositions": len(positions),
            "uniqueTargets": len(target_hp), "targetHPReductionByID": damaged}


def verify_pngs(run, frame_count):
    folder = run / "results/frames"
    paths = sorted(folder.glob("*.png"))
    require([p.name for p in paths] == [f"{i:04d}.png" for i in range(frame_count)], "PNG filenames are not one continuous frame per trace tick")
    nonuniform = 0
    manifest = []
    for path in paths:
        data = path.read_bytes()
        with Image.open(BytesIO(data)) as image:
            require(image.format == "PNG" and image.size == (1080, 1560), f"Unexpected PNG size or format: {path.name}")
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            if any(lo != hi for lo, hi in image.convert("RGB").getextrema()):
                nonuniform += 1
        manifest.append({"name": path.name, "sha256": digest(data)})
    hashes = {entry["sha256"] for entry in manifest}
    require(nonuniform > 1 and len(hashes) > 1, "Native sequence contains no changing visible imagery")
    sequence = "".join(f"{entry['name']} {entry['sha256']}\n" for entry in manifest).encode("ascii")
    return {"count": len(paths), "dimensions": [1080, 1560], "nonUniformFrames": nonuniform, "distinctPNGFiles": len(hashes),
            "sequenceSHA256": digest(sequence), "frameManifest": manifest}
