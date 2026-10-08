#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新角色发布边的四道边界门禁（fail-closed，退出码 1 = 有阻断问题）。

门禁（2026-10-06 凉月制作复盘；纯逻辑在 ``wf_character_gates``）：

1. **仓库边界**：边归档必须位于 ``assets/asset-patch/active/``，不得落在
   ``.cdn``；成员必须是 ``production/<root>/<xx>/<hash>``（禁止
   ``production/production`` 双层前缀）；manifest 归档完整性回执逐项复算；
   ``audit/`` 目录与报告存在。
2. **链边界**：边内每张 orderedmap 表的 outer key 相对边前有效链状态
   不得减少（C8601 整表覆盖事故）；声明行合并审计。
3. **结构契约**：边内 timeline/atlas/frame/parts 载荷对官方/donor 逐键对齐
   （timeline 必须带 ``sequences/sounds/points/circles``；atlas 记录键集与
   客户端语义几何；frame/parts 键集）。
4. **解析器契约**：声明行的 Bool/枚举/数值/``(None)`` 强类型校验与官方
   先例统计（col47/col72/col75 类案例，见 ``wf_character_gates``）。

用法示例：

  python tools/lens-integration/check_character_edge.py \\
    --edge-version 1.4.145 --expect-tail 1.4.145 \\
    --declared declared-liangyue.json --receipt receipt.json

``--declared`` JSON 形如 ``{"master/ability/ability.orderedmap":
{"1599921": true, "1599922": [2]}}``（表逻辑路径 → 声明 key → true/行号数组）。

回执格式：``{"gate": "character-edge", "edge": ..., "sections": {...},
"problems": [...], "warnings": [...], "status": "passed|failed"}``。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/lens-integration"))
sys.path.insert(0, str(REPO / "tools/fantasy-gauntlet-mod-tools"))

import prepare_content as pc  # noqa: E402
import wf_character_gates as gates  # noqa: E402
import wf_mod_tool as core  # noqa: E402

ACTIVE = REPO / "assets/asset-patch/active"
DEFAULT_PATHLIST = REPO / "tools/fantasy-gauntlet-mod-tools/WF_PATHLIST_recovered.txt"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def version_key(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def enabled_patches(manifest: dict, upto: str | None = None) -> list[dict]:
    patches = [p for p in manifest.get("patches", ()) if p.get("enabled")]
    patches.sort(key=lambda p: version_key(p["version"]))
    if upto is not None:
        limit = version_key(upto)
        patches = [p for p in patches if version_key(p["version"]) <= limit]
    return patches


def build_index(manifest: dict, upto: str | None):
    """复刻 prepare_content.Chain 的索引构建（可按版本截断），返回 (index, reads)。"""
    index: dict[tuple[str, str], tuple[Path, str]] = {}
    ordered: list[Path] = []
    baseline = []
    for directory in (REPO / ".cdn/cn").resolve().glob("archive-*"):
        for path in directory.glob("*.zip"):
            if "-full" in directory.name:
                baseline.append((0, path.name, path))
            else:
                match = re.match(r"pinball-1\.4\.\d+-1\.4\.(\d+)-(\d+)-", path.name)
                if match and int(match.group(1)) <= 54:
                    baseline.append((int(match.group(1)), path.name, path))
    ordered.extend(path for _order, _name, path in sorted(baseline))
    for patch in enabled_patches(manifest, upto):
        for name in patch.get("chain") or [patch.get("archive", "")]:
            ordered.append(ACTIVE / name)
    for path in ordered:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                parts = name.split("/")
                if (
                    len(parts) == 4
                    and parts[0] == "production"
                    and parts[1] in pc.REVERSE_ROOTS
                ):
                    index[(pc.REVERSE_ROOTS[parts[1]], "/".join(parts[2:]))] = (path, name)
    return index


def read_indexed(index, key) -> bytes | None:
    location = index.get(key)
    if location is None:
        return None
    path, member = location
    with zipfile.ZipFile(path) as archive:
        return archive.read(member)


def load_hrel_map(pathlist: Path) -> dict[str, str]:
    """官方路径清单的 hrel → logical 反查表（MOD 新路径不在其中）。"""
    mapping: dict[str, str] = {}
    if not pathlist.is_file():
        return mapping
    for line in pathlist.read_text(encoding="utf-8", errors="replace").splitlines():
        logical = line.strip()
        if not logical or logical.startswith("#"):
            continue
        digest = core.sha1_path(logical)
        mapping[f"{digest[:2]}/{digest[2:]}"] = logical
    return mapping


def classify_payload(tree) -> str | None:
    return gates.infer_role(tree)


def repo_boundary_section(entry: dict, problems: list[dict], warnings: list[dict]) -> dict:
    section: dict = {"edge": entry.get("id"), "version": entry.get("version"), "archives": []}
    for name in entry.get("chain") or []:
        row: dict = {"name": name}
        path = ACTIVE / name
        row["path"] = str(path)
        if gates.resolved_parts_include_cdn(path.resolve() if path.exists() else path):
            problems.append({"gate": "repo", "reason": "archive-under-cdn", "archive": name})
        if not path.is_file():
            problems.append({"gate": "repo", "reason": "archive-missing", "archive": name})
            section["archives"].append(row)
            continue
        raw = path.read_bytes()
        row["sha256"] = sha256(raw)
        row["size"] = len(raw)
        receipt = next(
            (item for item in entry.get("archive_integrity", ())
             if item.get("name") == name),
            None,
        )
        if receipt is None:
            problems.append({"gate": "repo", "reason": "manifest-integrity-missing",
                             "archive": name})
        else:
            if receipt.get("sha256") != row["sha256"]:
                problems.append({"gate": "repo", "reason": "archive-sha256-mismatch",
                                 "archive": name, "manifest": receipt.get("sha256"),
                                 "actual": row["sha256"]})
            if receipt.get("size") != row["size"]:
                problems.append({"gate": "repo", "reason": "archive-size-mismatch",
                                 "archive": name, "manifest": receipt.get("size"),
                                 "actual": row["size"]})
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            row["members"] = len(names)
            member_report = gates.archive_member_report(names)
            row["member_roots"] = member_report["by_root"]
            for problem in member_report["problems"]:
                problems.append({"gate": "repo", "reason": "member-path", "archive": name,
                                 "detail": problem})
            if len(names) != len(set(names)):
                pass  # archive_member_report 已报重复
            if receipt is not None:
                if receipt.get("members") != len(names):
                    problems.append({"gate": "repo", "reason": "archive-member-count-mismatch",
                                     "archive": name, "manifest": receipt.get("members"),
                                     "actual": len(names)})
                declared_files = list(entry.get("files") or [])
                if sorted(receipt.get("files") or []) != sorted(declared_files):
                    problems.append({"gate": "repo", "reason": "archive-files-list-mismatch",
                                     "archive": name})
                if sorted(names) != sorted(declared_files):
                    problems.append({"gate": "repo", "reason": "members-vs-manifest-files",
                                     "archive": name,
                                     "members": sorted(names)[:4],
                                     "files": sorted(declared_files)[:4]})
            row["member_names"] = names
        section["archives"].append(row)
    audit = entry.get("audit") or {}
    audit_dir = REPO / str(audit.get("directory") or "")
    if not audit.get("directory"):
        problems.append({"gate": "repo", "reason": "audit-directory-undeclared",
                         "edge": entry.get("id")})
    else:
        report = gates.audit_receipt_report(audit_dir, audit.get("report"))
        section["audit"] = report
        for problem in report.get("problems", ()):
            problems.append({"gate": "repo", "reason": "audit-receipt", "detail": problem})
        if report.get("exists") and "verification.json" not in report.get("files", ()):
            warnings.append({"gate": "repo", "reason": "audit-verification-missing",
                             "directory": audit.get("directory")})
    if not entry.get("files"):
        problems.append({"gate": "repo", "reason": "manifest-files-undeclared",
                         "edge": entry.get("id")})
    return section


def chain_boundary_section(
    entry: dict,
    edge_names: list[str],
    pathlist_map: dict[str, str],
    declared: dict,
    problems: list[dict],
    warnings: list[dict],
) -> dict:
    before_index = build_index(pc.Chain().manifest, entry.get("depends_on"))
    section: dict = {"before_version": entry.get("depends_on"), "tables": [], "declared": []}
    table_logicals: set[str] = set()
    for name in edge_names:
        path = ACTIVE / name
        if not path.is_file():
            continue
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                parts = PurePosixPath(member).parts
                if len(parts) != 4 or parts[0] != "production":
                    continue
                root = pc.REVERSE_ROOTS.get(parts[1])
                if root is None:
                    continue
                hrel = f"{parts[2]}/{parts[3]}"
                logical = pathlist_map.get(hrel)
                after_raw = archive.read(member)
                try:
                    after_rows = core.read_orderedmap_file_from_bytes(after_raw)
                except Exception:  # noqa: BLE001 - 非表载荷跳过
                    continue
                if not after_rows:
                    continue
                before_raw = read_indexed(before_index, (root, hrel))
                before_rows: dict[str, str] = {}
                if before_raw is not None:
                    try:
                        before_rows = core.read_orderedmap_file_from_bytes(before_raw)
                    except Exception:  # noqa: BLE001
                        warnings.append({
                            "gate": "chain", "reason": "before-undecodable",
                            "member": member,
                        })
                union = gates.outer_key_union_report(before_rows, after_rows)
                row = {
                    "member": member,
                    "logical": logical,
                    "before_keys": union["before_keys"],
                    "after_keys": union["after_keys"],
                    "added": union["added"][:40],
                    "changed": union["changed"][:40],
                    "removed": union["removed"][:40],
                }
                if logical and logical in declared:
                    declared_keys = declared[logical]
                    keys = (list(declared_keys)
                            if isinstance(declared_keys, dict) else list(declared_keys))
                    merge = gates.declared_row_merge_report(before_rows, after_rows, keys)
                    row["declared"] = merge
                    for problem in merge["problems"]:
                        problems.append({"gate": "chain", "reason": "declared-row",
                                         "logical": logical, "detail": problem})
                section["tables"].append(row)
                if logical:
                    table_logicals.add(logical)
                for problem in union["problems"]:
                    problems.append({
                        "gate": "chain", "reason": "outer-key-removed",
                        "logical": logical or member, "detail": problem,
                    })
    missing_declared = sorted(set(declared) - table_logicals)
    for logical in missing_declared:
        problems.append({"gate": "chain", "reason": "declared-table-not-in-edge",
                         "logical": logical})
    return section


def structural_section(
    entry: dict,
    edge_names: list[str],
    pathlist_map: dict[str, str],
    donor_codes: list[str],
    problems: list[dict],
    warnings: list[dict],
    require_donor: bool,
    chain=None,
    frame_swaps: list[dict] | None = None,
    before_index=None,
) -> dict:
    donor_logicals: dict[str, str] = {}
    for code in donor_codes:
        donor_logicals.setdefault(
            "pixelart-timeline", f"character/{code}/pixelart/pixelart.timeline.amf3.deflate"
        )
        donor_logicals.setdefault(
            "frame", f"character/{code}/pixelart/pixelart.frame.amf3.deflate"
        )
        donor_logicals.setdefault(
            "pixelart-atlas", f"character/{code}/pixelart/sprite_sheet.atlas.amf3.deflate"
        )
        donor_logicals.setdefault(
            "special-timeline", f"character/{code}/pixelart/special.timeline.amf3.deflate"
        )
    chain = pc.Chain() if chain is None else chain
    donor_trees: dict[str, object] = {}
    for role, logical in donor_logicals.items():
        raw = chain.get(("common", pc.hrel(logical)))
        if raw is None:
            continue
        tree = gates.decode_amf3_deflate(raw)
        if tree is not None:
            donor_trees[role] = tree
            donor_logicals[role] = logical
    section: dict = {"donors": donor_logicals, "members": []}
    swap_specs = frame_swaps or []
    for name in edge_names:
        path = ACTIVE / name
        if not path.is_file():
            continue
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                raw = archive.read(member)
                tree = gates.decode_amf3_deflate(raw)
                if tree is None:
                    continue
                role = classify_payload(tree)
                if role is None:
                    continue
                parts = PurePosixPath(member).parts
                logical = None
                if len(parts) == 4:
                    logical = pathlist_map.get(f"{parts[2]}/{parts[3]}")
                row = {"archive": name, "member": member, "role": role,
                       "logical": logical, "sha256": sha256(raw)}
                local = gates.structural_problems(logical or member, tree)
                donor_role = role
                if role == "pixelart-timeline":
                    donor_role = "pixelart-timeline"
                elif role == "frame":
                    donor_role = "frame"
                elif role == "pixelart-atlas":
                    donor_role = "pixelart-atlas"
                elif role == "effect-timeline":
                    donor_role = "special-timeline" if "special" in (logical or "") else None
                donor = donor_trees.get(donor_role) if donor_role else None
                if donor is None and require_donor and role in (
                    "pixelart-timeline", "frame", "pixelart-atlas"
                ):
                    problems.append({
                        "gate": "structural", "reason": "donor-missing",
                        "member": member, "role": role,
                        "hint": "用 --donor-code 或 --donor-logical 指定官方参照",
                    })
                if donor is not None:
                    for message in gates.structural_problems(logical or member, tree, donor):
                        if message not in local:
                            local.append(message)
                    row["donor"] = donor_logicals.get(donor_role)
                for spec in swap_specs:
                    if spec.get("member") not in (None, member) and spec.get("logical") not in (None, logical):
                        continue
                    if spec.get("member") is not None and spec["member"] != member:
                        continue
                    parts = PurePosixPath(member).parts
                    before_raw = None
                    if before_index is not None and len(parts) == 4:
                        root = pc.REVERSE_ROOTS.get(parts[1])
                        if root is not None:
                            before_raw = read_indexed(before_index, (root, f"{parts[2]}/{parts[3]}"))
                    if before_raw is None:
                        problems.append({
                            "gate": "structural", "reason": "anchor-before-missing",
                            "member": member, "spec": spec,
                        })
                        continue
                    before_tree = gates.decode_amf3_deflate(before_raw)
                    if not isinstance(before_tree, list):
                        problems.append({
                            "gate": "structural", "reason": "anchor-before-undecodable",
                            "member": member, "spec": spec,
                        })
                        continue
                    anchor = gates.anchor_regression_report(
                        before_tree, tree,
                        dx=int(spec.get("dx", 0)), dy=int(spec.get("dy", 0)),
                        label=f"{name}:{member}",
                        keep_frames=spec.get("keep") or (),
                    )
                    row.setdefault("anchor_regression", []).append(anchor)
                    for message in anchor["problems"]:
                        problems.append({"gate": "structural", "reason": "anchor-drift",
                                         "member": member, "detail": message})
                row["problems"] = local
                section["members"].append(row)
                for message in local:
                    problems.append({"gate": "structural", "archive": name,
                                     "member": member, "detail": message})
    return section


def parser_section(
    declared: dict,
    problems: list[dict],
    warnings: list[dict],
    chain=None,
    edge_names: list[str] | None = None,
) -> dict:
    section: dict = {"tables": [], "declared_keys": {}}
    if not declared:
        return section
    chain = pc.Chain() if chain is None else chain
    edge_members: dict[str, bytes] = {}
    for name in edge_names or []:
        path = ACTIVE / name
        if not path.is_file():
            continue
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                edge_members[member] = archive.read(member)
    for logical, selection in sorted(declared.items()):
        table_kind = gates.table_kind_for_logical(logical)
        if table_kind is None:
            problems.append({"gate": "parser", "reason": "declared-table-unsupported",
                             "logical": logical})
            continue
        hrel = pc.hrel(logical)
        raw = edge_members.get(f"production/upload/{hrel}")
        served_by_edge = raw is not None
        if raw is None:
            raw = chain.get(("common", hrel))
        if raw is None:
            problems.append({"gate": "parser", "reason": "declared-table-missing",
                             "logical": logical})
            continue
        declared_rows: dict = {}
        if isinstance(selection, dict):
            for key, rows in selection.items():
                declared_rows[str(key)] = True if rows is True else set(rows or [])
        else:
            declared_rows = {str(key): True for key in selection}
        section["declared_keys"][logical] = sorted(declared_rows)
        report = gates.ability_table_problems(
            raw, logical,
            read_orderedmap=core.read_orderedmap_file_from_bytes,
            read_rows=core.read_csv_lines,
            declared_rows=declared_rows,
        )
        report["served_by_edge"] = served_by_edge
        section["tables"].append(report)
        for problem in report["problems"]:
            problems.append({"gate": "parser", "logical": logical, **problem})
        for warning in report["warnings"]:
            warnings.append({"gate": "parser", "logical": logical, **warning})
    return section


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-version", required=True)
    parser.add_argument("--expect-tail")
    parser.add_argument("--declared", type=Path,
                        help="声明行 JSON：逻辑表 → 声明 key → true/行号数组")
    parser.add_argument("--frame-swap", type=Path,
                        help="帧素材替换声明 JSON：[{\"member\"|\"logical\", \"dx\", \"dy\"}]；"
                             "用于锚点逐帧回归（1.4.143 事故专用；dx=dy=0 表示零变化）")
    parser.add_argument("--donor-code", action="append", default=[],
                        help="官方 donor 角色代码（默认 ekaki_girl）")
    parser.add_argument("--pathlist", type=Path, default=DEFAULT_PATHLIST)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--allow-spec-only", action="store_true",
                        help="donor 缺失时降级为 warning（仅在官方参照不可得时使用）")
    args = parser.parse_args()

    donor_codes = args.donor_code or ["ekaki_girl"]
    declared: dict = {}
    if args.declared:
        declared = json.loads(args.declared.read_text(encoding="utf-8"))
    frame_swaps: list[dict] = []
    if args.frame_swap:
        frame_swaps = json.loads(args.frame_swap.read_text(encoding="utf-8"))
        if not isinstance(frame_swaps, list):
            raise SystemExit("--frame-swap 必须是数组")
    report: dict = {
        "gate": "character-edge",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "edge_version": args.edge_version,
        "problems": [],
        "warnings": [],
        "sections": {},
    }
    problems: list[dict] = report["problems"]
    warnings: list[dict] = report["warnings"]

    chain = pc.Chain()
    report["chain_tail"] = chain.tail
    if args.expect_tail and chain.tail != args.expect_tail:
        problems.append({"gate": "chain", "reason": "tail-mismatch",
                         "tail": chain.tail, "expected": args.expect_tail})
    entry = next(
        (item for item in chain.manifest.get("patches", ())
         if item.get("version") == args.edge_version and item.get("enabled")),
        None,
    )
    if entry is None:
        report["status"] = "failed"
        problems.append({"gate": "chain", "reason": "no-enabled-edge",
                         "version": args.edge_version})
        print(json.dumps({"status": "failed", "problems": problems}, ensure_ascii=False))
        raise SystemExit(1)
    edge_names = list(entry.get("chain") or [])
    report["edge"] = {"id": entry.get("id"), "version": entry.get("version"),
                      "depends_on": entry.get("depends_on"), "archives": edge_names}

    pathlist_map = load_hrel_map(args.pathlist)
    report["sections"]["repo_boundary"] = repo_boundary_section(entry, problems, warnings)
    report["sections"]["chain_boundary"] = chain_boundary_section(
        entry, edge_names, pathlist_map, declared, problems, warnings,
    )
    before_index = build_index(chain.manifest, entry.get("depends_on"))
    report["sections"]["structural_contract"] = structural_section(
        entry, edge_names, pathlist_map, donor_codes, problems, warnings,
        require_donor=not args.allow_spec_only, chain=chain,
        frame_swaps=frame_swaps, before_index=before_index,
    )
    report["sections"]["parser_contract"] = parser_section(
        declared, problems, warnings, chain=chain, edge_names=edge_names,
    )

    report["status"] = "failed" if problems else "passed"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    summary = {
        "status": report["status"],
        "edge": report["edge"]["id"],
        "problems": len(problems),
        "warnings": len(warnings),
        "receipt": str(args.receipt) if args.receipt else None,
        "problem_samples": problems[:8],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
