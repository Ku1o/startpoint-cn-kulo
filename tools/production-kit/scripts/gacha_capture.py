"""Capture or import a real offline Gacha battle using the pinned C8601 AIR adapter."""

from __future__ import annotations

import argparse
from copy import deepcopy
from functools import lru_cache
from hashlib import sha1, sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
import json
from math import isfinite
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from uuid import uuid4
from zipfile import ZipFile
import zlib

import gacha_native

INTERNAL = Path(__file__).resolve().with_name("gacha_capture")
spec = spec_from_file_location("_gacha_capture_frames", INTERNAL / "frames.py")
frames = module_from_spec(spec)
spec.loader.exec_module(frames)

ADAPTER = "c8601-air-v1"
SOURCE_SHA = "1d9dbd353c429570833ccad106ab93b76794226e66087a9fc5c3fff80fd2ae10"
BOOT_SHA = "1a813e9c0626c7683424a9dd4f263d750204e8dd7cf28d8e11829aa0f09ee30b"
BOOT_OFFSET = 5489738
BOOT_BEFORE = bytes.fromhex("60dc014fdf0100")
BOOT_AFTER = b"\x02" * 7
SALT = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy"
ROOTS = {"common": "bundle", "medium": "medium_bundle", "android": "android_bundle", "apk": "bundle"}
LOG_SUFFIX = ".battle.amf3.deflate"
TERRAIN_SUFFIX = ".amf3.deflate"
PRESENTATION = {"fps": 60, "stage": [1080, 1920], "viewport": [0, 60, 1080, 1560], "defaultState": "native-replay"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return sha256(data).hexdigest()


def dump(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def resolved(base, value):
    require(isinstance(value, str) and value, "Expected a non-empty filesystem path")
    return (base / value).resolve(strict=True)


def binding(base, value):
    require(set(value) <= {"file", "sha256", "bytes"} and {"file", "sha256"} <= set(value), "Invalid file binding")
    path = resolved(base, value["file"])
    data = path.read_bytes()
    require(digest(data) == value["sha256"] and len(data) == value.get("bytes", len(data)), f"File binding differs: {path}")
    return path, data


@lru_cache(maxsize=1)
def nested_zip(path, member, expected):
    with ZipFile(path) as archive:
        data = archive.read(member)
    require(digest(data) == expected, "Embedded archive digest differs")
    return data


def archive_member(base, row):
    require(row["member"].endswith("/" + cdn_key(row["logical"])), "Archive member logical key differs")
    archive = resolved(base, row["archive"])
    if "outerMember" in row:
        archive = BytesIO(nested_zip(archive, row["outerMember"], row["outerMemberSHA256"]))
    with ZipFile(archive) as source:
        data = source.read(row["member"])
    require(digest(data) == row["sha256"] and len(data) == row.get("bytes", len(data)), f"Archive member differs: {row['logical']}")
    return data


def cdn_key(logical):
    key = sha1((logical + SALT).encode()).hexdigest()
    return key[:2] + "/" + key[2:]


def decode(raw, core):
    inflater = zlib.decompressobj(-15)
    plain = inflater.decompress(raw, 24 * 1024 * 1024)
    require(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail, "Incomplete, oversized or trailing raw deflate")
    reader = core.AMF3Reader(plain)
    value = reader.read_value()
    require(reader.pos == len(plain), "AMF has trailing bytes")
    return value


def typed_equal(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def restore_candidate(base, row, data, core):
    source = row["sourceProof"]
    original = archive_member(base, source)
    original_tree = decode(original, core)
    new = decode(data, core)
    restored = deepcopy(new)
    allowed = row["allowedChanges"]
    require(isinstance(allowed, list) and len(set(allowed)) == len(allowed) and allowed, "Invalid candidate allowlist")
    if row["kind"] == "replay":
        limits = {"config.ball.x", "config.ball.y", "config.ball.vx", "config.ball.vy", "config.end_frame"}
        require(set(allowed) <= limits and source["logical"].endswith(LOG_SUFFIX), "Unsupported replay change")
        for name in allowed:
            if name == "config.end_frame":
                before, after = original_tree["config"]["end_frame"], new["config"]["end_frame"]
                last_command = max(part["f"] for part in original_tree["log_parts"])
                require(type(after) is int and last_command < after < before, "Replay trim must shorten the tail after all commands")
                restored["config"]["end_frame"] = before
            else:
                prop = name.rsplit(".", 1)[1]
                before, after = original_tree["config"]["ball"][prop], new["config"]["ball"][prop]
                require(type(after) in (int, float) and isfinite(after) and before != after, "Invalid ball edit")
                restored["config"]["ball"][prop] = before
    elif row["kind"] == "terrain":
        require(row["logical"] == source["logical"], "Terrain override must retain its source logical name")
        changes = row["changes"]
        require([item["path"] for item in changes] == allowed, "Terrain proof paths differ from the allowlist")
        for change in changes:
            layer, index, prop = change["layerIndex"], change["objectIndex"], change["property"]
            require(type(layer) is int and layer >= 0 and type(index) is int and index >= 0 and prop in ("x", "y"),
                    "Terrain edits must identify an existing object coordinate")
            require(change["path"] == f"layers[{layer}].objects[{index}].{prop}", "Terrain proof object path differs")
            old = original_tree["layers"][layer]["objects"][index]
            target = restored["layers"][layer]["objects"][index]
            kind = old["type"]
            require((kind.startswith("BLOCK#") or kind in {"SPAWN1", "SPAWN2", "CUSTOM_POSITION"}) and
                    old["id"] == target["id"] == change["objectId"], "Unsupported or mismatched terrain object")
            before, after = old[prop], target[prop]
            require(type(after) in (int, float) and isfinite(after) and before != after and
                    typed_equal([before, after], [change["before"], change["after"]]), "Terrain proof coordinates differ")
            target[prop] = before
    else:
        raise ValueError("Unknown candidate kind")
    require(typed_equal(restored, original_tree), "Candidate changed data beyond the allowed edits")
    return new


def read_asset(base, row, core):
    if "candidateFile" not in row:
        return archive_member(base, row), None
    _, data = binding(base, {"file": row["candidateFile"], "sha256": row["sha256"], "bytes": row["bytes"]})
    logical = row["logical"]
    if row.get("kind") == "replay":
        require(logical.startswith("gacha/feature_battle_preview/") and logical.endswith(LOG_SUFFIX), "Invalid replay override logical name")
    elif row.get("kind") == "terrain":
        require(logical.startswith("battle/terrain/skill_preview/") and logical.endswith(TERRAIN_SUFFIX), "Invalid terrain override logical name")
    elif logical.startswith("master/") and logical.endswith(".orderedmap") and row.get("terminalWholeTable") is False:
        require(row.get("base") and row.get("publicRowsSource") and row.get("rows"), "Missing scoped master provenance")
        reference = row["base"]
        require(reference["logical"] == logical, "Scoped master parent name differs")
        original = core.read_orderedmap_raw_rows_from_bytes(archive_member(base, reference), logical)
        candidate = core.read_orderedmap_raw_rows_from_bytes(data, logical)
        before = dict(zip(original.keys, original.rows))
        after = dict(zip(candidate.keys, candidate.rows))
        declared = {entry["id"]: entry["installedStoredRowSHA256"] for entry in row["rows"]}
        public = row["publicRowsSource"]
        public_bytes = archive_member(base, {**public, "logical": logical, "sha256": public["memberSHA256"]})
        if row.get("wholePublicTable") is True:
            require(data == public_bytes, "Declared whole-public table differs from its original")
            before = after
        else:
            public_table = core.read_orderedmap_raw_rows_from_bytes(public_bytes, logical)
            public_rows = dict(zip(public_table.keys, public_table.rows))
            require(all(entry["id"] in public_rows and digest(public_rows[entry["id"]]) == declared[entry["id"]]
                        for entry in row["rows"] if entry.get("origin") == "public native orderedmap row"),
                    "Scoped table public source row differs")
        require(len(declared) == len(row["rows"]) and declared.keys() <= after.keys() and
                all(digest(after[key]) == sha for key, sha in declared.items()) and
                {key: value for key, value in before.items() if key not in declared} ==
                {key: value for key, value in after.items() if key not in declared},
                "Scoped master modified an undeclared row or disagrees with its installed-row receipt")
        return data, None
    else:
        raise ValueError(f"Unsupported candidate asset: {logical}")
    require(row["root"] == "common", "Replay and terrain candidates must use the common root")
    return data, restore_candidate(base, row, data, core)


def load_plan(config_path, *, stage=None):
    config_path = Path(config_path).resolve(strict=True)
    config_raw = config_path.read_bytes()
    config = json.loads(config_raw)
    require(set(config) == {"schemaVersion", "adapter", "clientSwf", "toolchain", "assets", "preview", "protectedRoots"},
            "Unexpected native capture config fields")
    require(config["schemaVersion"] == 1 and config["adapter"] == ADAPTER, "Unsupported capture adapter")
    base = config_path.parent
    source_path, source = binding(base, config["clientSwf"])
    require(digest(source) == SOURCE_SHA, "SWF is outside the pinned C8601 adapter")
    tool = config["toolchain"]
    require(set(tool) == {"java", "compiler", "adl", "backgroundRunner", "supportRoot"}, "Unexpected capture toolchain fields")
    tool_paths = {name: binding(base, tool[name])[0] for name in ("java", "compiler", "adl", "backgroundRunner")}
    require(tool_paths["java"].name.lower() == "java.exe" and tool_paths["compiler"].name == "mxmlc-cli.jar" and
            tool_paths["adl"].name.lower() == "adl.exe" and tool_paths["backgroundRunner"].name == "run_background.py",
            "Unexpected executable names for the C8601 AIR adapter")
    support = resolved(base, tool["supportRoot"])
    _, (core, *_) = gacha_native._support(support)
    manifest_path, manifest = binding(base, config["assets"])
    records = json.loads(manifest)
    require(records["schemaVersion"] == 1 and isinstance(records["files"], list), "Unsupported native asset manifest")
    preview = config["preview"]
    require(set(preview) == {"roleId", "poolId", "questId", "log", "clip", "enablesAbility", "enablesPowerFlip", "terrain",
                             "fieldData", "field", "zone"}, "Unexpected preview config fields")
    require(all(type(preview[k]) is int and 0 < preview[k] <= 2147483647 for k in ("roleId", "poolId", "questId")) and
            all(type(preview[k]) is bool for k in ("enablesAbility", "enablesPowerFlip")) and
            isinstance(preview["clip"], list) and len(preview["clip"]) == 2 and
            all(type(x) is int and abs(x) <= 8192 for x in preview["clip"]), "Invalid native Gacha preview values")
    require(preview["log"].startswith("gacha/feature_battle_preview/") and
            preview["terrain"].startswith("battle/terrain/skill_preview/") and preview["terrain"].endswith(TERRAIN_SUFFIX),
            "Invalid native Gacha logical path")
    protected = [resolved(base, item) for item in config["protectedRoots"]]
    require(protected and all(path.is_dir() for path in protected), "Capture requires protected source roots")
    protected += [support, INTERNAL.parent, tool_paths["compiler"].parent.parent, source_path.parent, config_path.parent]
    rows, replay, bounds, destinations = {}, None, None, set()
    bundle = stage / "bundle" if stage is not None else None
    normalized_rows = []
    replay_key = preview["log"] + LOG_SUFFIX
    terrain_key = preview["terrain"]
    for row in records["files"]:
        logical, root = row["logical"], row["root"]
        require(logical not in rows and root in ROOTS and type(row["bytes"]) is int and row["bytes"] > 0 and
                re.fullmatch(r"[A-Za-z0-9_.$@#/-]+", logical) and ".." not in logical.split("/") and not logical.startswith("/"),
                f"Invalid or duplicate resource logical path: {logical}")
        data, tree = read_asset(manifest_path.parent, row, core)
        if row.get("kind") in ("terrain", "replay"):
            require(logical == (terrain_key if row["kind"] == "terrain" else replay_key), "Candidate does not belong to this preview")
        if logical == replay_key:
            replay = tree if tree is not None else decode(data, core)
        if logical == terrain_key:
            terrain = tree if tree is not None else decode(data, core)
            markers = [item for layer in terrain["layers"] for item in layer["objects"] if item["type"] == "BOUNDS"]
            require(len(markers) == 1, "Expected exactly one native terrain BOUNDS rectangle")
            bounds = [markers[0][name] for name in ("x", "y", "width", "height")]
            require(all(type(value) in (int, float) and isfinite(value) for value in bounds) and
                    bounds[2] > 0 and bounds[3] > 0, "Invalid native terrain BOUNDS rectangle")
            bounds = [value * 6 for value in bounds]
        relative = ROOTS[root] + "/" + cdn_key(logical)
        require(relative not in destinations, "Native bundle destination collision")
        destinations.add(relative)
        rows[logical] = row
        normalized_rows.append({**row, "bundlePath": "asset/bundle/production/" + relative})
        if bundle is not None:
            path = bundle / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as file:
                file.write(data)
    require(replay is not None and bounds is not None, "Selected replay or terrain is absent from the native manifest")
    record = replay["config"]
    start, end = record["start_frame"], record["end_frame"]
    require(type(start) is int and type(end) is int and 0 <= start < end <= start + 1680, "Unsupported replay window")
    commands = replay["log_parts"]
    require(isinstance(commands, list) and commands and
            all(type(item["f"]) is int and start <= item["f"] <= end and isinstance(item["c"], list) and item["c"] and
                type(item["c"][0]) is int and 0 <= item["c"][0] <= 25 for item in commands) and
            any(item["c"][0] == 2 for item in commands) and
            [item["f"] for item in commands] == sorted(item["f"] for item in commands),
            "Invalid native replay command schedule")
    left, top = preview["clip"]
    fixture = {**preview, "previewKind": "gacha", "replay": replay,
               "replayProof": {"logical": replay_key}, "terrainProof": {"logical": terrain_key},
               "gachaRow": {"quest_id": preview["questId"], "log": preview["log"], "clip": {"left": left, "top": top},
                            "enables_ability": preview["enablesAbility"], "enables_powerflip": preview["enablesPowerFlip"]}}
    if bundle is not None:
        filelist = "bundle/" + cdn_key("bundle_amf.filelist")
        path = bundle / filelist
        path.parent.mkdir(parents=True, exist_ok=True)
        require(filelist not in destinations, "Source manifest shadows the generated native file list")
        path.write_bytes(("\n".join(sorted({cdn_key(name) for name in rows})) + "\n").encode("ascii"))
        dump(bundle / "files.json", sorted(destinations | {filelist}))
        dump(stage / "bundle-source-proof.json", normalized_rows)
    return {"config": config_path, "configSHA256": digest(config_raw), "source": source, "sourcePath": source_path,
            "tools": tool_paths, "manifest": manifest_path, "manifestSHA256": digest(manifest), "preview": preview,
            "fixture": fixture, "rows": rows, "bounds": bounds, "protected": protected}


def validate(config_path):
    plan = load_plan(config_path)
    return {"adapter": ADAPTER, "configSHA256": plan["configSHA256"], "assets": len(plan["rows"]),
            "assetManifestSHA256": plan["manifestSHA256"], "preview": plan["preview"]}


def swf_body(raw):
    require(raw[:3] in (b"CWS", b"FWS"), "Unsupported SWF envelope")
    body = zlib.decompress(raw[8:]) if raw[:3] == b"CWS" else raw[8:]
    require(len(body) + 8 == struct.unpack_from("<I", raw, 4)[0], "SWF length differs from header")
    return body


def tags(body):
    pos = (5 + 4 * (body[0] >> 3) + 7) // 8 + 4
    while pos < len(body):
        start = pos
        word, = struct.unpack_from("<H", body, pos)
        pos += 2
        size = word & 63
        if size == 63:
            size, = struct.unpack_from("<I", body, pos)
            pos += 4
        require(pos + size <= len(body), "Truncated SWF tag")
        yield word >> 6, start, body[pos:pos + size]
        pos += size


def encode_tag(code, data):
    return struct.pack("<HI", code << 6 | 63, len(data)) + data


def native_tags(source):
    abc, symbols = [], []
    patched = 0
    for kind, _, data in tags(swf_body(source)):
        if kind == 82:
            end = data.index(b"\0", 4)
            if data[4:end] == b"boot_ffc6":
                code = data[end + 1:]
                start, stop = BOOT_OFFSET, BOOT_OFFSET + len(BOOT_BEFORE)
                require(digest(code) == BOOT_SHA and code[start:stop] == BOOT_BEFORE and code[stop] == 0x47,
                        "Pinned static initializer tail differs")
                data = data[:end + 1] + code[:start] + BOOT_AFTER + code[stop:]
                patched += 1
            abc.append(b"\x01\0\0\0" + data[4:])
        elif kind in (75, 88, 91, 87, 10, 48, 21, 73):
            symbols.append(encode_tag(kind, data))
        elif kind == 76:
            rows, pos = [], 2
            for _ in range(struct.unpack_from("<H", data)[0]):
                item, = struct.unpack_from("<H", data, pos)
                stop = data.index(b"\0", pos + 2) + 1
                if item:
                    rows.append(data[pos:stop])
                pos = stop
            if rows:
                symbols.append(encode_tag(kind, struct.pack("<H", len(rows)) + b"".join(rows)))
    require(len(abc) == 306 and patched == 1, "Native C8601 ABC set differs")
    return abc, symbols


def build_harness(source, template):
    native, symbols = native_tags(source)
    body = swf_body(template)
    first = next(pos for kind, pos, _ in tags(body) if kind == 82)
    combined = body[:first] + b"".join(encode_tag(82, item) for item in native) + b"".join(symbols) + body[first:]
    return b"CWS" + template[3:4] + struct.pack("<I", len(combined) + 8) + zlib.compress(combined, 6)


def safe_output(config, output):
    plan = load_plan(config)
    output = Path(output).resolve()
    require(output.parent.is_dir() and not output.exists(), "Capture requires a new directory in an existing workspace")
    require(not any(output.is_relative_to(root) or root.is_relative_to(output) for root in plan["protected"]),
            "Capture output overlaps a protected input or tool directory")
    return plan, output


def record(config_path, output):
    plan, output = safe_output(config_path, output)
    output.mkdir()
    app, results, host = (output / name for name in ("app", "results", "src"))
    for path in (app, results, host):
        path.mkdir()
    staged = load_plan(config_path, stage=app / "resource-probe")
    require((staged["configSHA256"], staged["manifestSHA256"]) == (plan["configSHA256"], plan["manifestSHA256"]),
            "Capture inputs changed while staging")
    dump(app / "preview-fixture.json", plan["fixture"])
    for template in (INTERNAL / "host").glob("*.as"):
        shutil.copyfile(template, host / template.name)
    sdk = plan["tools"]["compiler"].parent.parent
    require(plan["tools"]["adl"].parent.parent == sdk, "AIR runtime and compiler must belong to the same SDK")
    template = output / "template.swf"
    compile_command = [str(plan["tools"]["java"]), "-Xmx1g", "-Dflexlib=" + str(sdk / "frameworks"), "-jar",
                       str(plan["tools"]["compiler"]), "+configname=air", "-compiler.float=false",
                       "-swf-version=44", "-target-player=32.0", "-debug=true", "-compress=false",
                       "-default-size=1080,1920", "-default-frame-rate=60", "-output=" + str(template), str(host / "NativeHost.as")]
    with (output / "compile.log").open("xb") as log:
        subprocess.run(compile_command, cwd=output, stdout=log, stderr=subprocess.STDOUT, timeout=90, check=True)
    (app / "Harness.swf").write_bytes(build_harness(plan["source"], template.read_bytes()))
    private_id = "local.starpoint.offlinenative.cap-" + uuid4().hex
    descriptor = app / "application.xml"
    descriptor.write_text(
        '<application xmlns="http://ns.adobe.com/air/application/51.2">'
        f'<id>{private_id}</id><versionNumber>1.0.0</versionNumber><filename>offline-native</filename>'
        '<initialWindow><content>Harness.swf</content><visible>false</visible><width>1080</width><height>1920</height>'
        '<renderMode>direct</renderMode></initialWindow></application>', encoding="utf-8")
    dump(output / "build.json", {"adapter": ADAPTER, "configSHA256": plan["configSHA256"],
                                "assetManifestSHA256": plan["manifestSHA256"], "sourceSHA256": SOURCE_SHA,
                                "nativeABCUnits": 306, "battleCodeModified": False, "privateApplicationId": private_id,
                                "hostSources": {f"src/{f.name}": digest(f.read_bytes()) for f in host.glob("*.as")}})
    with (output / "runtime.log").open("xb") as log:
        subprocess.run([str(plan["tools"]["adl"]), str(descriptor), "--", str(results)],
                       cwd=output, stdout=log, stderr=subprocess.STDOUT, timeout=300, check=True)


def capture(config_path, output):
    plan, output = safe_output(config_path, output)
    launcher = plan["tools"]["backgroundRunner"]
    command = [sys.executable, "-B", str(launcher), "--timeout", "420", "--",
               sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), "_record", str(plan["config"]), str(output)]
    subprocess.run(command, timeout=430, check=True)
    report = verify(config_path, output)
    dump(output / "CAPTURE.json", report)
    return report


def read_json(path):
    return json.loads(path.read_bytes())


def verify(config_path, run_dir):
    plan = load_plan(config_path)
    run = Path(run_dir).resolve(strict=True)
    build = read_json(run / "build.json")
    require(build["sourceSHA256"] == SOURCE_SHA and build["nativeABCUnits"] == 306, "Different native source build")
    if "configSHA256" in build:
        require(build["adapter"] == ADAPTER and build["configSHA256"] == plan["configSHA256"] and
                build["assetManifestSHA256"] == plan["manifestSHA256"], "Capture build is not bound to this config")
    legacy_book = None
    if "fixtureBook" in build:
        legacy_book = Path(build["fixtureBook"]).resolve(strict=True)
        require(digest(legacy_book.read_bytes()) == build["fixtureBookSHA256"], "Legacy scene-book SHA differs")
        fixture = read_json(run / "app/preview-fixture.json")
        matches = [row for row in read_json(legacy_book)["scenes"] if row["roleId"] == plan["preview"]["roleId"]]
        require(matches == [fixture], "Legacy run fixture differs from the bound scene book")
    for relative, expected in build["hostSources"].items():
        file = (run / relative.replace("\\", "/")).resolve(strict=True)
        require(file.parent == run / "src" and digest(file.read_bytes()) == expected, "Host source snapshot differs")
    harness = (run / "app/Harness.swf").read_bytes()
    source_abc, _ = native_tags(plan["source"])
    host_abc = [data for kind, _, data in tags(swf_body((run / "template.swf").read_bytes())) if kind == 82]
    installed = [data for kind, _, data in tags(swf_body(harness)) if kind == 82]
    require(installed == source_abc + host_abc, "Installed ABCs differ beyond the pinned seven-byte entry change")
    receipt_path = run / "results/host-result.json"
    receipt = receipt_path.read_bytes()
    native = json.loads(receipt)
    require(native["passed"] is True and native["nativeMainCalled"] is False and native["nativeGraphicsReady"] is True and
            native["battleStarted"] is True and native["battlePrepared"] is True and native["viewPhase"] == "native-finished",
            "Missing native Battle Finish")
    state = native["battleBootstrap"]
    require((state["previewSceneType"], state["previewBattleType"]) ==
            ("pinball.scene.battle::SkillPreviewBattle", "pinball.scene.battle.battle::Battle"), "Unexpected native scene classes")
    source, replay = state["previewSource"], state["loadedNativeReplay"]
    p, raw = plan["preview"], plan["fixture"]["replay"]
    left, top = p["clip"]
    require((source["character"], source["pool"], source["quest"], source["log"], source["clipLeft"], source["clipTop"],
             source["enablesAbility"], source["enablesPowerFlip"], source["evolution"]) ==
            (p["roleId"], p["poolId"], p["questId"], p["log"], left, top, p["enablesAbility"], p["enablesPowerFlip"], 1),
            "Native source differs from configured preview")
    if "selectedRole" in state:
        selected = state["selectedRole"]
        require(tuple(selected[key] for key in ("fieldData", "field", "terrain", "zone")) ==
                tuple(p[key] for key in ("fieldData", "field", "terrain", "zone")), "Native field binding differs")
    c = raw["config"]
    expected = (p["log"], c["start_frame"], c["end_frame"], c["ball"], c["hp_ratio"], c["skill_gauge_ratio"], c["power_flip_level"],
                [item["f"] for item in raw["log_parts"]])
    require(tuple(replay[key] for key in ("logical", "startFrame", "endFrame", "ball", "hpRatio", "skillGaugeRatio", "powerFlipLevel",
                                        "commandFrames")) == expected, "Native replay cache differs from decoded input")
    asset_folder = run / "app/resource-probe"
    listed = read_json(asset_folder / "bundle/files.json")
    actual = read_json(asset_folder / "bundle-source-proof.json")
    by_name = {item["logical"]: item for item in actual}
    require(len(by_name) == len(actual), "Duplicate staged asset name")
    keys = (asset_folder / "bundle" / "bundle" / cdn_key("bundle_amf.filelist")).read_bytes()
    require(keys == ("\n".join(sorted(cdn_key(name) for name in by_name)) + "\n").encode("ascii"),
            "The native file list differs from the staged asset names")
    if "configSHA256" in build:
        require(set(by_name) == set(plan["rows"]) and read_json(run / "app/preview-fixture.json") == plan["fixture"],
                "The new capture staged a different asset closure or fixture")
        require(re.fullmatch(r"local\.starpoint\.offlinenative\.cap-[0-9a-f]{32}", build["privateApplicationId"]) and
                f"<id>{build['privateApplicationId']}</id>" in (run / "app/application.xml").read_text("utf-8"),
                "The build does not declare its fresh private AIR application")
    probe = native["resourceProbe"]
    require(probe["passed"] is True and probe["nativeFileReader"] is True and probe["readMode"] == 1 and
            probe["stagedBundleMembers"] == len(listed), "Private native bundle copy did not complete")
    for logical, wanted in plan["rows"].items():
        item = by_name[logical]
        path = ROOTS[wanted["root"]] + "/" + cdn_key(logical)
        require(item["bundlePath"] == "asset/bundle/production/" + path and listed.count(path) == 1 and
                item["sha256"] == wanted["sha256"] and digest((asset_folder / "bundle" / path).read_bytes()) == wanted["sha256"],
                f"Native cache binding differs: {logical}")
    asset_part = state["partRequestsAfterFollowing"]["leading"]
    require(p["terrain"].removesuffix(TERRAIN_SUFFIX) in asset_part["terrain"], "Native builder did not request the configured terrain")
    actions = {key.rsplit(":", 1)[0] + ".action.dsl.amf3.deflate" for key in asset_part["action"] + asset_part["actionWithoutView"]}
    require(actions <= plan["rows"].keys() and all("archive" in plan["rows"][name] for name in actions),
            "Native action DSL closure is missing archived sources")
    report_input = {"role": p["roleId"], "pool": p["poolId"], "quest": p["questId"], "nativeLog": p["log"] + LOG_SUFFIX,
                    "logSHA256": plan["rows"][p["log"] + LOG_SUFFIX]["sha256"], "clip": p["clip"],
                    "sourceWindow": [c["start_frame"], c["end_frame"]], "config": {"file": str(plan["config"]), "sha256": plan["configSHA256"]},
                    "assetManifest": {"file": str(plan["manifest"]), "sha256": plan["manifestSHA256"]},
                    "terrain": {"logical": p["terrain"], "sha256": plan["rows"][p["terrain"]]["sha256"]},
                    "terrainBoundsWorld": plan["bounds"],
                    "nativeActionDSL": {name: plan["rows"][name]["sha256"] for name in sorted(actions)}}
    if legacy_book is not None:
        report_input["fixtureBook"] = {"path": str(legacy_book), "sha256": build["fixtureBookSHA256"]}
    return {"schemaVersion": 1, "kind": "native-gacha-capture", "adapter": ADAPTER, "run": str(run), "passed": True,
            "deviceAcceptance": False, "captureReceipt": {"file": str(receipt_path), "sha256": digest(receipt)},
            "sourceSWFSHA256": SOURCE_SHA, "harnessSHA256": digest(harness), "input": report_input, "presentation": PRESENTATION,
            "trace": frames.verify_trace(native["nativeFrames"], {"replay": raw}),
            "pngs": frames.verify_pngs(run, len(native["nativeFrames"]))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "capture", "verify", "_record"])
    parser.add_argument("config", type=Path)
    parser.add_argument("run", type=Path, nargs="?")
    args = parser.parse_args()
    if args.command == "validate":
        result = validate(args.config)
    elif args.command == "_record":
        record(args.config, args.run)
        return
    else:
        if args.run is None:
            parser.error("capture and verify require a run directory")
        result = capture(args.config, args.run) if args.command == "capture" else verify(args.config, args.run)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
