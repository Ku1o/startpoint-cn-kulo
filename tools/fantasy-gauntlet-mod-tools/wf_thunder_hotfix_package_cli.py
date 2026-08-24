#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixed-input, dry-run-default assembler for thunder hotfix 1.1.6."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import wf_thunder_hotfix_package as package
import wf_thunder_hotfix_package_sources as source_io
import wf_thunder_hotfix_package_workspace as workspace
import wf_abyss_gacha_banner_compile as banner_compile
import wf_mod_tool as core


TOOL_ROOT = Path(__file__).resolve().parent


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "雷龙 1.1.6 完整替换热修包；默认只读 dry-run，"
            "把泳皇女EX（139997）并入深渊限定池：9名限定角色合计1%，"
            "该角色不可兑换，横幅资产零改动。"
        )
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="write only the fixed fresh formal workspace",
    )
    parser.add_argument(
        "--confirm", metavar="PHRASE",
        help=f"--apply requires exactly: {package.CONFIRMATION}",
    )
    return parser.parse_args(arguments)


def _git_head(tool_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tool_root,
        capture_output=True,
        text=True,
        check=False,
    )
    head = result.stdout.strip().lower()
    if (
        result.returncode != 0
        or len(head) != 40
        or any(ch not in "0123456789abcdef" for ch in head)
    ):
        raise package.PackageAssemblyError(
            "cannot bind hotfix package to an exact generator git HEAD"
        )
    return head


def _fixed_paths(tool_root: Path) -> tuple[Path, Path, Path]:
    work = tool_root / "work"
    source = (
        work / "character_packs"
        / "cnmod_thunder_dragon_ascendant_abyss_gacha"
    )
    build_root = work / "builds" / "cnmod_thunder_dragon_ascendant"
    output = work / "character_packs" / workspace.WORKSPACE_NAME
    return source, build_root, output


def _compile_fixed(tool_root: Path) -> package.PackageImage:
    source_path, build_root, _output = _fixed_paths(tool_root)
    head = _git_head(tool_root)
    try:
        current_store = core.require_active_store(tool_root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise package.PackageAssemblyError(
            f"cannot resolve current CDN/active store context: {exc}"
        ) from exc
    first_source = source_io.load_sealed_source_workspace(source_path)
    first_donor = source_io.load_locked_donor_template(build_root)
    try:
        first_banners = banner_compile.load_current_banner_payloads(current_store)
    except (OSError, ValueError) as exc:
        raise package.PackageAssemblyError(
            f"cannot read current CDN/active banners: {exc}"
        ) from exc
    first = package.compile_hotfix_package(
        first_source, first_donor, first_banners, generator_git_head=head
    )
    second_source = source_io.load_sealed_source_workspace(source_path)
    second_donor = source_io.load_locked_donor_template(build_root)
    try:
        second_banners = banner_compile.load_current_banner_payloads(current_store)
    except (OSError, ValueError) as exc:
        raise package.PackageAssemblyError(
            f"cannot re-read current CDN/active banners: {exc}"
        ) from exc
    second = package.compile_hotfix_package(
        second_source, second_donor, second_banners, generator_git_head=head
    )
    if (
        first_source != second_source
        or first_donor != second_donor
        or first_banners != second_banners
        or first != second
    ):
        raise package.PackageAssemblyError(
            "hotfix production inputs changed during double-read compilation"
        )
    return first


def run(arguments: argparse.Namespace) -> dict:
    if arguments.apply and arguments.confirm != package.CONFIRMATION:
        raise package.PackageAssemblyError(
            f"exact confirmation required: {package.CONFIRMATION}"
        )
    if not arguments.apply and arguments.confirm is not None:
        raise package.PackageAssemblyError(
            "--confirm is only valid together with --apply"
        )
    tool_root = Path(TOOL_ROOT)
    _source, _build, output = _fixed_paths(tool_root)
    workspace.inspect_fresh_target(output)
    image = _compile_fixed(tool_root)
    return workspace.execute_fresh_workspace(
        output,
        image,
        apply=bool(arguments.apply),
        confirmation=arguments.confirm,
    )


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        report = run(parse_args(arguments))
    except package.PackageAssemblyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["TOOL_ROOT", "parse_args", "run", "main"]
