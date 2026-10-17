"""Extract the fixed PR43 Android inputs without unpacking either whole APK.

Only the audited APK pair is accepted. All identity, ZIP and payload checks
finish before the new output directory is created. No build or signing occurs.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import xml.etree.ElementTree as ET
import zipfile


HERE = Path(__file__).resolve().parent
BASE_APK_SHA256 = "4f62b899a89b0648f79d0dbaf20d8aab9b64ad91959d91706dc71af02cb6c335"
DONOR_APK_SHA256 = "572dd17256de6708b9cdcbe752e184a97b44781bce8fd5ffacf7be7413e0c331"
X86_TREE_SHA256 = "4dda31632d1f0294556d21cb24fc243c7abc9d8e4af5caf7ff09df91ae10c8e6"
X86_FILES = 1966
X86_BYTES = 43213364
SWF_MEMBER = "assets/worldflipper_android_release.swf"
EXTENSIONS = "assets/META-INF/AIR/extensions/"
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 96 * 1024 * 1024


class InputError(ValueError):
    """A fixed input, archive, or output boundary was not satisfied."""


def require(condition, message):
    if not condition:
        raise InputError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    parts = name.rstrip("/").split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    require(bool(name) and "\\" not in name and "\x00" not in name
            and ":" not in name and not PurePosixPath(name).is_absolute()
            and not any(p in ("", ".", "..") for p in parts)
            and not any(p.endswith((".", " ")) for p in parts)
            and not any(p.split(".", 1)[0].upper() in reserved for p in parts)
            and not any(ord(c) < 32 for c in name), "unsafe ZIP member name")
    return name


def zip_inventory(package):
    """Reject ambiguous/unsafe archives before CRC scans or extraction."""
    infos = package.infolist()
    names = [safe_name(i.filename) for i in infos]
    require(len(names) == len(set(names)), "duplicate ZIP member")
    require(len(names) == len({n.casefold() for n in names}),
            "ZIP names collide on a case-insensitive filesystem")
    require(all(not i.flag_bits & 1 for i in infos), "encrypted ZIP member")
    require(all(stat.S_IFMT(i.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR)
                for i in infos), "ZIP links/special files are forbidden")
    require(sum(i.file_size for i in infos) <= MAX_ARCHIVE_BYTES,
            "archive uncompressed size limit exceeded")
    require(package.testzip() is None, "ZIP CRC failure")
    return {i.filename: i for i in infos}


def output_boundary(output_dir, inputs):
    requested = Path(output_dir).absolute()
    output = requested.resolve()
    require(not output.exists(), "output directory must be new")
    require(not any(p.casefold() in (".cdn", ".git") for path in (requested, output) for p in path.parts),
            "output cannot enter .cdn or .git")
    # The source checkout is forbidden. A containing workspace may have its
    # own Git metadata; it is not the game's source checkout or a build target.
    source_root = HERE.parent.parent
    require(not output.is_relative_to(source_root), "output cannot enter the source repository")
    require(not any((p / ".git").exists() and not source_root.is_relative_to(p)
                    for p in (output, *output.parents)),
            "output cannot enter a Git checkout")
    for item in inputs:
        source = Path(item).resolve(strict=True)
        require(source.is_file(), "APK input must be a file")
        require(output != source and not source.is_relative_to(output),
                "output would contain an input APK")
    return output


def tree_hash(files):
    h = hashlib.sha256()
    # Match the audited WindowsPath traversal deterministically on every OS.
    order = lambda row: (tuple(part.casefold() for part in PurePosixPath(row[0]).parts), row[0])
    for name, data in sorted(files.items(), key=order):
        h.update(f"{name}\0{len(data)}\0{sha(data)}\n".encode("utf-8"))
    return h.hexdigest()


def x86_members(package, inventory):
    files = {n for n, i in inventory.items() if not i.is_dir()}
    libraries = {n for n in files if n.startswith("lib/x86_64/") and n.endswith(".so")}
    descriptors = {n for n in files if n.startswith(EXTENSIONS)
                   and n.endswith("/META-INF/ANE/extension.xml")}
    resources = {n for n in files if n.startswith(EXTENSIONS) and "/Android-x64/" in n}
    require(len(libraries) == 15 and len(descriptors) == 13,
            "expected 15 x86 libraries and 13 ANE descriptors")
    selected = libraries | descriptors | resources
    require(len(selected) == X86_FILES
            and sum(inventory[n].file_size for n in selected) == X86_BYTES,
            "x86 sparse input inventory differs")
    for name in sorted(descriptors):
        data = package.read(name)
        require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(),
                "ANE descriptor entities/DTD are forbidden")
        root = ET.fromstring(data)
        platforms = [e.get("name") for e in root.iter()
                     if e.tag.rsplit("}", 1)[-1] == "platform"]
        require(platforms.count("Android-x64") == 1 and "Android-ARM64" in platforms,
                "ANE descriptor platform inventory differs")
    result = {n: package.read(n) for n in sorted(selected)}
    require(tree_hash(result) == X86_TREE_SHA256, "x86 sparse input tree hash differs")
    return result


def bundle_members(package, resources, role):
    """Validate all four targets, materializing only their byte payloads."""
    with zipfile.ZipFile(io.BytesIO(package.read("assets/bundle.zip"))) as bundle:
        inventory = zip_inventory(bundle)
        result = {}
        prefix = "before" if role == "baseline" else "after"
        for row in resources:
            name = safe_name(row["member"])
            require(name in inventory and not inventory[name].is_dir(), "bundle target is missing")
            data = bundle.read(name)
            require(len(data) == row[prefix + "_size"]
                    and sha(data) == row[prefix + "_sha256"], "bundle target identity differs")
            result[row["logical"]] = data
        return result


def prepare(base_apk, donor_apk, output_dir):
    output = output_boundary(output_dir, (base_apk, donor_apk))
    game_plan = json.loads((HERE / "game-plan.json").read_text(encoding="utf-8"))
    plan = json.loads((HERE / "bundle-plan.json").read_text(encoding="utf-8"))
    resources = plan["resources"]
    require(len(resources) == 4 and len({r["member"] for r in resources}) == 4
            and len({r["logical"] for r in resources}) == 4, "invalid four-member bundle plan")
    for row in resources:
        safe_name(row["logical"])
        safe_name(row["member"])
    files = {}
    with ExitStack() as stack:
        opened = []
        for path, expected in ((base_apk, BASE_APK_SHA256), (donor_apk, DONOR_APK_SHA256)):
            handle = stack.enter_context(Path(path).open("rb"))
            require(hashlib.file_digest(handle, "sha256").hexdigest() == expected,
                    "unknown APK SHA256; output was not created")
            handle.seek(0)
            opened.append(handle)
        for role, handle, expected_swf in (
                ("baseline", opened[0], game_plan["base_swf_sha256"]),
                ("donor", opened[1], game_plan["donor_swf_sha256"])):
            with zipfile.ZipFile(handle) as package:
                inventory = zip_inventory(package)
                swf = package.read(SWF_MEMBER)
                require(sha(swf) == expected_swf, "SWF identity differs from game-plan.json")
                files["source.swf" if role == "baseline" else "donor.swf"] = swf
                targets = bundle_members(package, resources, role)
                if role == "donor":
                    files.update({"bundle-donor/" + n: data for n, data in targets.items()})
                    files.update({"x86-native-ane/" + n: data
                                  for n, data in x86_members(package, inventory).items()})
    total = sum(map(len, files.values()))
    require(total <= MAX_EXTRACTED_BYTES, "sparse extraction size limit exceeded")
    bundle_targets = {"resources": [dict(row, donor_file=str(output / "bundle-donor" / row["logical"]))
                                    for row in resources]}
    report = {
        "schema": 1, "passed": True, "base_apk_sha256": BASE_APK_SHA256,
        "donor_apk_sha256": DONOR_APK_SHA256,
        "base_swf_sha256": game_plan["base_swf_sha256"],
        "donor_swf_sha256": game_plan["donor_swf_sha256"],
        "x86_inputs_sha256": X86_TREE_SHA256, "x86_files": X86_FILES,
        "x86_bytes": X86_BYTES, "bundle_targets": 4,
        "extracted_files": len(files), "extracted_bytes": total,
        "duplicate_members": False, "zip_crc_ok": True,
        "built": False, "device_tested": False,
    }
    # These two generated JSON files are local inputs/receipts, never source.
    files["bundle-targets.json"] = (json.dumps(bundle_targets, indent=2) + "\n").encode("utf-8")
    files["prepare-inputs-report.json"] = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    require(sum(map(len, files.values())) <= MAX_EXTRACTED_BYTES,
            "sparse extraction size limit exceeded")
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = output / safe_name(name)
        require(target.resolve().is_relative_to(output), "output path escaped its root")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        require(sha(target.read_bytes()) == sha(data), "written input readback differs")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-apk", type=Path, required=True)
    parser.add_argument("--donor-apk", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.base_apk, args.donor_apk, args.output_dir)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
