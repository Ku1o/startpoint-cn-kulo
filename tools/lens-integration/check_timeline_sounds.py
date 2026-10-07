#!/usr/bin/env python3
"""Fail-closed release gate: every client timeline must carry a `sounds` array.

The 2026-10-05 liangyue F1009 showed that a timeline whose AMF3 payload omits
the `sounds` member survives packaging and manifest registration but crashes
the client: `PlayheadTimeline.sounds` is coerced to null and
`AssetPathCollectionBuilder/loadDynamicSoundEffect` dereferences
`sounds.length` (TypeError #1009).  Metadata checks alone cannot catch it, so
this gate inspects payload content:

1. every archive member of the target version edge that decodes as an AMF3
   object containing `sequences` must carry a `sounds` array;
2. every timeline logical reachable in the effective chain terminal state
   (pathlist names plus explicitly required logicals) must carry a `sounds`
   array; and
3. by default the whole terminal chain is scanned payload-by-payload for
   timeline-like objects (AMF3 dict with `sequences`), independent of naming.

Any missing/null/non-array `sounds` value fails the gate (exit code 1).  The
JSON receipt records the scanned scope, per-logical evidence and every problem.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import zipfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/lens-integration"))
sys.path.insert(0, str(REPO / "tools/fantasy-gauntlet-mod-tools"))

import prepare_content as pc  # noqa: E402
import wf_dsl  # noqa: E402

ROOT_ORDER = ("common", "medium", "android", "ios")
DEFAULT_PATHLIST = REPO / "tools/fantasy-gauntlet-mod-tools/WF_PATHLIST_recovered.txt"


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def decode_timeline_like(raw: bytes):
    """Return (tree, None) for AMF3 objects with `sequences`, else (None, reason)."""
    try:
        plain = zlib.decompress(raw, -15)
    except zlib.error:
        return None, "not-raw-deflate"
    try:
        tree = wf_dsl.parse_dsl(plain)["tree"]
    except Exception:  # noqa: BLE001 - arbitrary payloads are expected here
        return None, "not-amf3"
    if isinstance(tree, dict) and "sequences" in tree:
        return tree, None
    return None, None


def sounds_problem(tree):
    value = tree.get("sounds", "__ABSENT__")
    if value == "__ABSENT__":
        return "sounds-absent"
    if not isinstance(value, list):
        return f"sounds-not-array({type(value).__name__})"
    if any(item is None for item in value):
        return "sounds-null-entry"
    return None


def resolvable_roots(chain, logical):
    for root in ROOT_ORDER:
        key = (root, pc.hrel(logical))
        if key in chain.index:
            return root, key, chain.index[key]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-version", help="manifest patch version to inspect (e.g. 1.4.134)")
    parser.add_argument("--expect-tail", help="fail unless the effective chain tail equals this")
    parser.add_argument("--require-logical", action="append", default=[],
                        help="timeline logical path that must exist and carry sounds (repeatable)")
    parser.add_argument("--expect-edge", action="store_true",
                        help="required logicals must resolve inside the target edge archives")
    parser.add_argument("--pathlist", type=Path, default=DEFAULT_PATHLIST)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--no-chain-payload-scan", action="store_true",
                        help="skip the whole-chain payload scan (fast mode; edge scan still runs)")
    args = parser.parse_args()

    report = {
        "gate": "timeline-sounds",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "edge": None,
        "required_logicals": [],
        "pathlist_scan": None,
        "edge_member_scan": None,
        "chain_payload_scan": None,
        "problems": [],
    }
    problems = report["problems"]

    chain = pc.Chain()
    report["chain_tail"] = chain.tail
    report["expect_tail"] = args.expect_tail
    if args.expect_tail and chain.tail != args.expect_tail:
        problems.append({"scope": "chain", "reason": "tail mismatch",
                         "tail": chain.tail, "expected": args.expect_tail})

    edge_names: set[str] = set()
    if args.edge_version:
        entry = next((p for p in chain.manifest["patches"]
                      if p.get("version") == args.edge_version and p.get("enabled")), None)
        if entry is None:
            problems.append({"scope": "edge", "reason": "no enabled manifest patch",
                             "version": args.edge_version})
        else:
            edge_names = set(entry.get("chain") or [])
            report["edge"] = {
                "version": args.edge_version,
                "id": entry.get("id"),
                "archives": sorted(edge_names),
            }
            for name in sorted(edge_names):
                if not (REPO / "assets/asset-patch/active" / name).is_file():
                    problems.append({"scope": "edge", "reason": "archive missing", "name": name})
            if not edge_names:
                problems.append({"scope": "edge", "reason": "edge declares no archives",
                                 "version": args.edge_version})

    # Required logicals: presence, sounds array and (optionally) edge ownership.
    for logical in args.require_logical:
        row = {"logical": logical, "found": False}
        resolve = resolvable_roots(chain, logical)
        if resolve is None:
            problems.append({"scope": "required", "reason": "logical absent from chain",
                             "logical": logical})
        else:
            root, key, (archive, member) = resolve
            raw = chain.get(key)
            tree = None
            try:
                tree = wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
            except Exception as exc:  # noqa: BLE001
                problems.append({"scope": "required", "reason": "timeline undecodable",
                                 "logical": logical, "error": f"{type(exc).__name__}: {exc}"})
            row.update(found=True, root=root, archive=Path(archive).name, member=member,
                       sha256=sha_bytes(raw), bytes=len(raw))
            if tree is not None:
                row["keys"] = sorted(tree.keys()) if isinstance(tree, dict) else None
                problem = sounds_problem(tree) if isinstance(tree, dict) else "not-an-object"
                row["sounds_ok"] = problem is None
                if problem:
                    problems.append({"scope": "required", "reason": problem, "logical": logical})
            if args.expect_edge and Path(archive).name not in edge_names:
                problems.append({"scope": "required", "reason": "logical not served by the edge",
                                 "logical": logical, "archive": Path(archive).name,
                                 "edge": sorted(edge_names)})
        report["required_logicals"].append(row)

    # Pathlist scan: historical/official timeline names still reachable in the chain.
    pathlist_timelines = []
    if args.pathlist.is_file():
        lines = [line.strip() for line in
                 args.pathlist.read_text(encoding="utf-8", errors="replace").splitlines()]
        pathlist_timelines = [line for line in lines if ".timeline" in line]
    path_scan = {"pathlist": str(args.pathlist), "timelines": len(pathlist_timelines),
                 "found": 0, "missing_from_chain": [], "problems": 0}
    for logical in pathlist_timelines:
        resolve = resolvable_roots(chain, logical)
        if resolve is None:
            path_scan["missing_from_chain"].append(logical)
            continue
        path_scan["found"] += 1
        root, key, _ = resolve
        raw = chain.get(key)
        try:
            tree = wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
        except Exception as exc:  # noqa: BLE001
            path_scan["problems"] += 1
            problems.append({"scope": "pathlist", "reason": "timeline undecodable",
                             "logical": logical, "error": f"{type(exc).__name__}: {exc}"})
            continue
        problem = sounds_problem(tree)
        if problem:
            path_scan["problems"] += 1
            problems.append({"scope": "pathlist", "reason": problem, "logical": logical})
    report["pathlist_scan"] = path_scan

    # Edge member scan: payload-level, independent of logical names.
    edge_scan = {"members": 0, "timeline_like": [], "undecoded": 0}
    for name in sorted(edge_names):
        path = REPO / "assets/asset-patch/active" / name
        if not path.is_file():
            continue
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                raw = z.read(member)
                edge_scan["members"] += 1
                tree, reason = decode_timeline_like(raw)
                if tree is None:
                    if reason is None:
                        continue
                    if reason == "not-amf3":
                        edge_scan["undecoded"] += 1
                    continue
                problem = sounds_problem(tree)
                row = {"archive": name, "member": member, "sha256": sha_bytes(raw),
                       "keys": sorted(tree.keys())}
                if problem:
                    problems.append({"scope": "edge", "reason": problem, **row})
                else:
                    edge_scan["timeline_like"].append(row)
    report["edge_member_scan"] = edge_scan

    # Whole-chain terminal payload scan (content-based; catch anything unnamed).
    if not args.no_chain_payload_scan:
        by_archive: dict[str, list[tuple[str, str, str]]] = {}
        for (root, hrel), (path, member) in chain.index.items():
            by_archive.setdefault(str(path), []).append((root, hrel, member))
        scan = {"archives": len(by_archive), "members": 0, "timeline_like": 0,
                "timeline_like_ok": 0, "undecodable": 0, "missing_sounds": []}
        for archive_path, entries in sorted(by_archive.items()):
            with zipfile.ZipFile(archive_path) as z:
                for _root, _hrel, member in entries:
                    raw = z.read(member)
                    scan["members"] += 1
                    tree, reason = decode_timeline_like(raw)
                    if tree is None:
                        if reason == "not-amf3":
                            scan["undecodable"] += 1
                        continue
                    scan["timeline_like"] += 1
                    problem = sounds_problem(tree)
                    if problem:
                        row = {"archive": Path(archive_path).name, "member": member,
                               "reason": problem, "keys": sorted(tree.keys()),
                               "sha256": sha_bytes(raw)}
                        scan["missing_sounds"].append(row)
                        problems.append({"scope": "chain", **row})
                    else:
                        scan["timeline_like_ok"] += 1
        report["chain_payload_scan"] = scan

    report["status"] = "failed" if problems else "passed"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    summary = {
        "status": report["status"],
        "chain_tail": chain.tail,
        "edge_version": args.edge_version,
        "edge_archives": sorted(edge_names),
        "problems": len(problems),
        "required_logicals": len(report["required_logicals"]),
        "pathlist_found": path_scan["found"],
        "edge_members": edge_scan["members"],
        "edge_timeline_like": len(edge_scan["timeline_like"]),
        "chain_payload_scan": None if report["chain_payload_scan"] is None else {
            "members": report["chain_payload_scan"]["members"],
            "timeline_like": report["chain_payload_scan"]["timeline_like"],
            "ok": report["chain_payload_scan"]["timeline_like_ok"],
        },
        "receipt": str(args.receipt) if args.receipt else None,
        "problem_samples": problems[:8],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
