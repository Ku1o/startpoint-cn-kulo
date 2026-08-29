#!/usr/bin/env python3
"""Reconcile the integrated candidate with the shared-terminal rogue result.

This does not rebuild or publish the client payload.  It runs only the three
rogue regression modules against the current shared local terminal, records the
known conductor fixture collision as the sole non-green item, and rehashes the
candidate audit/manifest/server coordination archive.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = Path(__file__).resolve().parent
CANDIDATE = (
    SOURCE_ROOT / "work"
    / "integrated-cloudbase-1.4.87-to-1.4.88-seed-2026082508-20260825a"
    / "candidate"
)
EVIDENCE = CANDIDATE / "evidence"
PATCH_AUDIT = EVIDENCE / "patch-audit.json"
CANDIDATE_MANIFEST = EVIDENCE / "candidate-manifest.json"
TOWER_AUDIT = EVIDENCE / "hp-audit.json"
SERVER_ARCHIVE = CANDIDATE / "server-files-coordinated.zip"
CLIENT_ARCHIVE = (
    CANDIDATE
    / "pinball-1.4.87-1.4.88-1-0825-integrated-ginovi-spgirl-trio-rogue.zip"
)
CHINESE_REPORT = EVIDENCE / "整合候选验收报告.md"


class ReconcileError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run_shared_terminal_rogue_tests() -> tuple[bytes, dict]:
    previous_log = EVIDENCE / "rogue_tests.log"
    baseline_log = EVIDENCE / "rogue_tests_cloud_baseline_1.4.87.log"
    previous_raw = previous_log.read_bytes()
    previous_text = previous_raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if "Ran 315 tests" not in previous_text or "\nOK\n" not in previous_text:
        raise ReconcileError("the preserved 1.4.87 supplementary regression is not green")
    baseline_log.write_bytes(previous_raw)

    command = [
        sys.executable, "-X", "utf8", "-m", "unittest",
        "tests.test_rogue_build",
        "tests.test_rogue_chain_gate",
        "tests.test_orochi_ex_hp_channel",
    ]
    env = os.environ.copy()
    for key in ("WF_SERVER_DIR", "WF_CDN_DIR", "WF_LIVE_CDN", "WF_TARGET_STORE"):
        env.pop(key, None)
    completed = subprocess.run(
        command,
        cwd=TOOL_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    raw = completed.stdout
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    required = (
        "Ran 315 tests",
        "FAILED (failures=1)",
        "test_single_bar_special_clone_has_one_auditable_victory_component",
        "target key conflict:mod_rogue_conductor28 in conductor,boss_level",
    )
    if completed.returncode == 0 or not all(token in text for token in required):
        raise ReconcileError(
            "shared-terminal rogue result is not the single locked conductor fixture conflict"
        )
    if text.count("\nFAIL:") != 1 or "\nERROR:" in text:
        raise ReconcileError("shared-terminal rogue regression has an unexpected failure set")
    previous_log.write_bytes(raw)
    return raw, {
        "command": command,
        "cwd": str(TOOL_ROOT),
        "exit_code": completed.returncode,
        "log": str(previous_log),
        "log_sha256": sha256_bytes(raw),
        "passed": False,
        "tests_total": 315,
        "tests_passed": 314,
        "tests_failed": 1,
        "failure_classification": "known_shared_terminal_fixture_conflict",
        "failure": (
            "conductor fixture target key mod_rogue_conductor28 already exists in the "
            "withdrawn shared local terminal"
        ),
        "candidate_gameplay_impact_inferred": False,
        "supplementary_cloud_baseline_run": {
            "log": str(baseline_log),
            "log_sha256": sha256_bytes(previous_raw),
            "tests_total": 315,
            "tests_passed": 315,
            "exit_code": 0,
            "passed": True,
            "baseline": "sealed 1.4.87 terminal",
        },
    }


def floor28_evidence() -> dict:
    audit = json.loads(TOWER_AUDIT.read_bytes())
    floor = next((row for row in audit["floors"] if int(row["round"]) == 28), None)
    if floor is None:
        raise ReconcileError("candidate tower floor 28 is missing")
    adapter = floor.get("adapter") or {}
    components = adapter.get("components") or []
    if (
        floor.get("verified") is not True
        or floor.get("absolute_verified") is not True
        or adapter.get("family") != "conductor"
        or adapter.get("absolute_verified") is not True
        or adapter.get("within_tolerance") is not True
        or adapter.get("final_c86") != 1.0
        or len(components) != 1
        or components[0].get("evidence_kind") != "absolute"
        or components[0].get("readback_code") != "mod_rogue_conductor28"
    ):
        raise ReconcileError("candidate floor-28 conductor static evidence drifted")
    return {
        "round": 28,
        "family": "conductor",
        "runtime_boss": "mod_rogue_conductor28",
        "absolute_verified": True,
        "within_tolerance": True,
        "final_c86": 1.0,
        "final_target_hp": adapter["final_target_hp"],
        "final_readback_hp": adapter["final_readback_hp"],
        "final_error_hp": adapter["final_error_hp"],
        "evidence_kind": "absolute",
        "chain_report_scope": "candidate hp-audit: 31/31, chain_failures=0",
        "gameplay_verified": False,
    }


def rewrite_server_archive(rogue: dict, floor28: dict) -> dict:
    with zipfile.ZipFile(SERVER_ARCHIVE) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "server-file-audit.json" not in names:
            raise ReconcileError("server coordination archive structure drifted")
        members = {name: archive.read(name) for name in names}
    internal = json.loads(members["server-file-audit.json"])
    internal["validation"] = {
        "rogue_regression": {
            key: value
            for key, value in rogue.items()
            if key not in {"log", "supplementary_cloud_baseline_run"}
        },
        "candidate_floor28_static_chain": floor28,
        "unique_non_green_item": "shared-terminal conductor fixture conflict",
    }
    internal_raw = (json.dumps(internal, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    members["server-file-audit.json"] = internal_raw
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, (2026, 8, 26, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, members[name])
    raw = output.getvalue()
    SERVER_ARCHIVE.write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(members):
            raise ReconcileError("rebuilt server archive ordering drifted")
        if any(archive.read(name) != data for name, data in members.items()):
            raise ReconcileError("rebuilt server archive readback failed")
    return {
        "archive": str(SERVER_ARCHIVE),
        "archive_size": len(raw),
        "archive_sha256": sha256_bytes(raw),
        "archive_members": len(members),
        "audit_sha256": sha256_bytes(internal_raw),
    }


def update_patch_audit(rogue: dict, floor28: dict, server: dict) -> tuple[dict, str]:
    audit = json.loads(PATCH_AUDIT.read_bytes())
    audit["validation_commands"]["rogue_tests"] = rogue
    audit["validation_summary"] = {
        "all_commands_green": False,
        "unique_non_green_item": "shared-terminal conductor fixture conflict",
        "rogue_tests_passed": 314,
        "rogue_tests_total": 315,
        "candidate_floor28_static_chain_verified": True,
        "candidate_gameplay_verified": False,
    }
    audit["candidate_floor28_static_chain"] = floor28
    audit["server_files"].update(server)
    raw = (json.dumps(audit, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    PATCH_AUDIT.write_bytes(raw)
    return audit, sha256_bytes(raw)


def update_candidate_manifest(patch_audit_sha: str, rogue: dict, floor28: dict) -> str:
    manifest = json.loads(CANDIDATE_MANIFEST.read_bytes())
    patch = manifest["patches"][-1]
    if patch.get("version") != "1.4.88" or patch.get("depends_on") != "1.4.87":
        raise ReconcileError("candidate manifest edge drifted")
    patch.setdefault("audit", {}).update({
        "patch_audit_sha256": patch_audit_sha,
        "rogue_regression_tests_passed": 314,
        "rogue_regression_tests_total": 315,
        "rogue_regression_passed": False,
        "rogue_regression_known_fixture_conflict": True,
        "candidate_floor28_static_chain_verified": floor28["absolute_verified"],
    })
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    CANDIDATE_MANIFEST.write_bytes(raw)
    return sha256_bytes(raw)


def update_chinese_report(server: dict) -> str:
    text = CHINESE_REPORT.read_text(encoding="utf-8")
    old = (
        "- 深渊工具回归：315/315 通过；为避免已撤回的本地旧终态中 conductor 测试键污染结果，"
        "本轮在封存的 1.4.87 基线上执行。"
    )
    new = (
        "- 深渊工具主回归（已撤回的共享本地旧终态）：314/315；唯一失败为 conductor 测试夹具目标键 "
        "`mod_rogue_conductor28` 已存在。该项记录为非全绿，不能写成完整回归通过。\n"
        "- 补充隔离回归（封存 1.4.87 基线）：315/315 通过。候选第28关 conductor 另由最终塔审计证明："
        "absolute、c86=1、误差在容差内，且整塔引用链31/31；这仍不等于真机玩法通过。"
    )
    if old not in text:
        raise ReconcileError("Chinese report rogue validation paragraph drifted")
    text = text.replace(old, new, 1)
    text = text.replace(
        "- SHA-256：`a297a80717d9444b832e5d3ca1382a7fc54b36a857510c7728deda9ad77eaccf`。",
        f"- SHA-256：`{server['archive_sha256']}`。",
        1,
    ).replace(
        "- 大小：895,435 字节。",
        f"- 大小：{server['archive_size']:,} 字节。",
        1,
    )
    CHINESE_REPORT.write_text(text, encoding="utf-8")
    return sha256_file(CHINESE_REPORT)


def main() -> int:
    rogue_raw, rogue = run_shared_terminal_rogue_tests()
    floor28 = floor28_evidence()
    server = rewrite_server_archive(rogue, floor28)
    audit, audit_sha = update_patch_audit(rogue, floor28, server)
    manifest_sha = update_candidate_manifest(audit_sha, rogue, floor28)
    report_sha = update_chinese_report(server)

    client_sha = sha256_file(CLIENT_ARCHIVE)
    if client_sha != audit["archive_sha256"]:
        raise ReconcileError("client archive changed during audit reconciliation")
    with zipfile.ZipFile(CLIENT_ARCHIVE) as archive:
        if len(archive.namelist()) != 655 or len(set(archive.namelist())) != 655:
            raise ReconcileError("client archive member count/uniqueness drifted")
    with zipfile.ZipFile(SERVER_ARCHIVE) as archive:
        if len(archive.namelist()) != server["archive_members"]:
            raise ReconcileError("server archive member count drifted after final write")

    result = {
        "status": "reconciled-not-published",
        "rogue_tests": {
            "exit_code": rogue["exit_code"],
            "passed": rogue["passed"],
            "tests_passed": 314,
            "tests_total": 315,
            "log_sha256": sha256_bytes(rogue_raw),
        },
        "candidate_floor28_static_chain": floor28,
        "client_archive": {
            "path": str(CLIENT_ARCHIVE),
            "size": CLIENT_ARCHIVE.stat().st_size,
            "sha256": client_sha,
            "members": 655,
        },
        "server_archive": server,
        "patch_audit": {"path": str(PATCH_AUDIT), "sha256": audit_sha},
        "candidate_manifest": {"path": str(CANDIDATE_MANIFEST), "sha256": manifest_sha},
        "chinese_report": {"path": str(CHINESE_REPORT), "sha256": report_sha},
        "cloud_modified": False,
        "runtime_mirror_modified": False,
    }
    output = EVIDENCE / "rogue-audit-reconciliation.json"
    raw = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output.write_bytes(raw)
    result["reconciliation_report"] = {
        "path": str(output), "sha256": sha256_bytes(raw)
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
