#!/usr/bin/env python3
"""Build a StarPoint CN cloud overlay package.

One command produces the whole delivery:
  <name>.zip            覆盖包本体（仓库相对路径，无外层目录）
  <name>.zip.files.txt  成员路径清单（路径 + 字节数，不含逐文件哈希）
  <name>.zip.sha256.txt 整包 SHA-256
  <name>.zip.部署说明.txt 由 --note 提供的部署说明（可选）

默认更新本地交付记录；--no-record 仅生成交付文件。

设计取舍（2026-10-03 精简）：
- 只保留一份整包 SHA-256。ZIP 自带逐成员 CRC，足以发现传输损坏；
  逐文件 SHA-256 清单没有实际使用场景，只会让人以为必须逐个核对。
- 成员清单的价值是"部署前该备份哪些文件"，因此保留路径与字节数。
- 打包前的成员归属校验和打包后的逐成员字节比对保留：它们抓到过真实错误。

用法：
  python tools/build-cloud-overlay.py --release-tag release-YYYY.MM.DD-N --base <基线提交> [--publish-tag]
  python tools/build-cloud-overlay.py --batch <批次名> --base <当前版本> --source <目标标签> [--no-record]
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[1])
OUT_ROOT = str(Path(REPO).parent / "outputs" / "server-overlays")
RECORD = str(Path(REPO).parent / ".codex" / "starpoint-cloud-delivery.json")
DELIVERY_TIMEZONE = timezone(timedelta(hours=8))
BUILD_POLICY = "tools/runtime-build-policy.json"
RUNTIME_EXACT_PATHS = {
    "docs/generated/character_table.json",
    "docs/systems/time-content-deployment.md",
    "tools/build-content-discovery-gacha.py",
    "tools/build-content-discovery-rewards.cjs",
    "tools/build-content-discovery.cjs",
}
DISCOVERY_GENERATORS = {
    "tools/build-content-discovery-gacha.py",
    "tools/build-content-discovery-rewards.cjs",
    "tools/build-content-discovery.cjs",
}

# 运行相关前缀：只有这些路径可能进入云服包
RUNTIME_PREFIXES = ("src/", "out/", "assets/", "scripts/", "package.json", "package-lock.json")
# 按规则排除的子路径
EXCLUDED_PATTERNS = (
    "assets/asset-patch/audit/",
    "assets/asset-patch/artwork/",
    "assets/asset-patch/production/",
    "production/",
    "config/",
)


def validate_selection_path(name: str) -> bool:
    """A repair commit must be wholly in scope, never silently filtered."""
    return (is_safe_member(name) and "\\" not in name and name not in RUNTIME_EXACT_PATHS
            and (name.startswith(("src/", "tests/", "docs/", ".github/"))
                 or name == ".env.example" or ("/" not in name and name.endswith(".md"))))


def validate_cumulative_selection(base: str, source: str, commits: list[str]) -> None:
    """Do not rebuild a mixed deployment without its previously delivered repairs."""
    if not os.path.isfile(RECORD):
        return
    with open(RECORD, encoding="utf-8") as handle:
        latest = json.load(handle).get("latest_delivery", {})
    previous = latest.get("selection")
    if not previous and not latest.get("scope_status", {}).get("mixed"):
        return
    if not isinstance(previous, dict):
        raise SystemExit("混合交付缺少可核验的累计选择配方；拒绝重建运行基线")
    previous_commits = previous.get("selected_commits")
    previous_source = previous.get("source_commit")
    if (not isinstance(previous_commits, list) or not previous_commits
            or any(not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha) for sha in previous_commits)
            or not isinstance(previous_source, str) or not re.fullmatch(r"[0-9a-f]{40}", previous_source)):
        raise SystemExit("既有混合交付的累计选择身份不完整；拒绝重建运行基线")
    if previous.get("base_commit") != base:
        raise SystemExit("累计选择必须保留既有混合交付的原始基线，不能重置 whole-repository base")
    if [sha for sha in commits if sha in set(previous_commits)] != previous_commits:
        raise SystemExit("累计选择遗漏或重排已交付修复；新计划必须保留此前全部 selected_commits")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", previous_source, source],
                              cwd=REPO, capture_output=True)
    if ancestor.returncode:
        raise SystemExit("累计选择的来源必须继承此前已交付的 source anchor，不能回退或切换历史")


def prepare_selection(plan_path: str, base: str, source: str) -> dict:
    with open(plan_path, encoding="utf-8") as handle:
        plan = json.load(handle)
    if (not isinstance(plan, dict) or plan.get("schema") != 1 or plan.get("kind") != "server-fixes"
            or set(plan) != {"schema", "kind", "base_commit", "source_commit", "selected_commits"}):
        raise SystemExit("选择计划必须使用 schema=1、kind=server-fixes 和完整来源字段")
    commits = plan["selected_commits"]
    if (plan["base_commit"] != base or plan["source_commit"] != source
            or not isinstance(commits, list) or not commits
            or any(not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha) for sha in commits)
            or len(set(commits)) != len(commits)):
        raise SystemExit("选择计划基线、来源或完整提交 SHA 清单无效")
    # Requiring the source's first-parent chain makes each patch's meaning and
    # application order explicit, including a merge commit's first-parent diff.
    chain = git("rev-list", "--first-parent", source).splitlines()
    if base not in chain:
        raise SystemExit("选择计划基线必须属于来源的 first-parent 历史")
    eligible = list(reversed(chain[:chain.index(base)]))
    selected = set(commits)
    if [sha for sha in eligible if sha in selected] != commits:
        raise SystemExit("选择提交必须来自基线之后的来源 first-parent 历史并按先后顺序排列")
    validate_cumulative_selection(base, source, commits)
    patches = []
    for sha in commits:
        parent = git("rev-parse", f"{sha}^1").strip()
        names = [name for name in git("diff", "--name-only", "--no-renames", "-z", parent, sha, "--").split("\0") if name]
        rejected = [name for name in names if not validate_selection_path(name)]
        if rejected:
            raise SystemExit(f"选择提交 {sha} 包含未批准路径：{', '.join(rejected)}")
        if not names:
            raise SystemExit(f"选择提交没有差异：{sha}")
        # A submodule/symlink in an otherwise approved directory is not source.
        for revision in (parent, sha):
            for row in git("ls-tree", "-rz", revision, "--", *names).split("\0"):
                if row and row.split(" ", 1)[0] not in {"100644", "100755"}:
                    raise SystemExit(f"选择提交包含非普通源文件：{row.split(chr(9), 1)[-1]}")
        patches.append((sha, parent))
    with tempfile.TemporaryDirectory(prefix="starpoint-selection-index-") as temporary:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
        subprocess.run(["git", "read-tree", base], cwd=REPO, env=env, capture_output=True, check=True)
        for sha, parent in patches:
            patch = subprocess.run(["git", "diff", "--binary", "--full-index", "--no-renames", "--no-ext-diff", "--no-textconv",
                                    parent, sha, "--"], cwd=REPO, capture_output=True, check=True).stdout
            applied = subprocess.run(["git", "apply", "--cached", "--3way", "--whitespace=nowarn", "-"],
                                     cwd=REPO, env=env, input=patch, capture_output=True)
            if applied.returncode:
                raise SystemExit(f"选择提交无法无冲突应用，拒绝封包：{sha}\n{applied.stderr.decode('utf-8', errors='replace').strip()}")
        source_tree = subprocess.run(["git", "write-tree"], cwd=REPO, env=env,
                                     capture_output=True, check=True, text=True).stdout.strip()
    recipe = {**plan, "source_tree": source_tree, "application": "first-parent-binary-patches"}
    recipe["identity_sha256"] = hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return recipe


def refuse_implicit_mixed_baseline() -> None:
    if not os.path.isfile(RECORD):
        return
    with open(RECORD, encoding="utf-8") as handle:
        latest = json.load(handle).get("latest_delivery", {})
    if latest.get("selection") or latest.get("scope_status", {}).get("mixed"):
        raise SystemExit("上次为选择性交付，存在延后范围；须提供明确 --selection-plan，不能用普通提交基线跳过未交付内容")


def cdn_version(source: str) -> str | None:
    if subprocess.run(["git", "cat-file", "-e", f"{source}:assets/asset-patch/manifest.json"],
                      cwd=REPO, capture_output=True).returncode:
        return None
    return json.loads(committed_bytes(source, "assets/asset-patch/manifest.json")).get("cdn_version")


def pending_selection(recipe: dict) -> dict:
    """The unshipped runtime delta, with Git object references rather than hashes."""
    tree, anchor = recipe["source_tree"], recipe["source_commit"]
    before, after = tree_entries(tree), tree_entries(anchor)
    groups = {"server": [], "content": [], "cdn": []}
    for name in sorted(before.keys() | after.keys()):
        if not is_runtime_path(name) or before.get(name) == after.get(name):
            continue
        category = ("cdn" if name.startswith("assets/asset-patch/") else
                    "content" if name.startswith("assets/") or name in RUNTIME_EXACT_PATHS else "server")
        groups[category].append({"path": name,
                                 "delivered_blob": before.get(name, (None, None))[1],
                                 "source_blob": after.get(name, (None, None))[1],
                                 "status": "modified" if name in before and name in after else "added" if name in after else "deleted"})
    return {"schema": 1, "effective_tree": tree, "source_commit": anchor,
            "whole_repository_baseline_commit": recipe["base_commit"],
            "cdn_from": cdn_version(tree), "cdn_to": cdn_version(anchor),
            "scope": "runtime-delta-to-source-anchor", "groups": groups,
            "file_count": sum(map(len, groups.values()))}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout


def committed_bytes(source: str, relative: str) -> bytes:
    return subprocess.run(["git", "show", f"{source}:{relative}"], cwd=REPO,
                          capture_output=True, check=True).stdout


def uses_source_build(source: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{source}:{BUILD_POLICY}"],
                          cwd=REPO, capture_output=True).returncode == 0


def tree_entries(source: str) -> dict[str, tuple[str, str]]:
    entries = {}
    for row in git("ls-tree", "-rz", "--full-tree", source).split("\0"):
        if not row:
            continue
        header, name = row.split("\t", 1)
        mode, kind, oid = header.split(" ")
        if kind == "blob":
            entries[name] = (mode, oid)
    return entries


def committed_out_bytes(source: str) -> dict[str, bytes]:
    """Export all historical out blobs with one batch, preserving exact bytes."""
    entries = {name: entry for name, entry in tree_entries(source).items() if name.startswith("out/")}
    if any(not is_safe_member(name) or mode not in {"100644", "100755"}
           for name, (mode, _) in entries.items()):
        raise SystemExit("历史运行产物必须为安全的普通 Git blob")
    oids = list(dict.fromkeys(oid for _, oid in entries.values()))
    if not oids:
        return {}
    request = ("\n".join(oids) + "\n").encode("ascii")
    check = subprocess.run(["git", "cat-file", "--batch-check"], input=request, cwd=REPO,
                           capture_output=True, check=True).stdout.decode("ascii").splitlines()
    sizes = []
    for oid, row in zip(oids, check):
        actual, kind, size = row.split(" ")
        if actual != oid or kind != "blob" or not size.isdigit():
            raise SystemExit("历史运行 Git blob 身份不一致")
        sizes.append(int(size))
    if len(check) != len(oids) or sum(sizes) > 512 * 1024 * 1024:
        raise SystemExit("历史运行 Git blob 清单不完整或超过导出限制")
    raw = subprocess.run(["git", "cat-file", "--batch"], input=request, cwd=REPO,
                         capture_output=True, check=True).stdout
    blobs, offset = {}, 0
    for oid, size in zip(oids, sizes):
        end = raw.find(b"\n", offset)
        expected = f"{oid} blob {size}".encode("ascii")
        if end < 0 or raw[offset:end] != expected:
            raise SystemExit("历史运行 Git batch header 身份不一致")
        offset = end + 1
        payload_end = offset + size
        if raw[payload_end:payload_end + 1] != b"\n":
            raise SystemExit("历史运行 Git batch 字节不完整")
        blobs[oid] = raw[offset:payload_end]
        offset = payload_end + 1
    if offset != len(raw):
        raise SystemExit("历史运行 Git batch 含额外字节")
    return {name: blobs[oid] for name, (_, oid) in entries.items()}


def compile_input_entries(source: str) -> dict[str, tuple[str, str]]:
    """Mirror helper inputs, excluding policy metadata introduced by migration."""
    return {name: entry for name, entry in tree_entries(source).items()
            if name in {"package.json", "package-lock.json", "tsconfig.json", "docs/generated/character_table.json"}
            or re.fullmatch(r"src/.*\.(?:tsx?|json)", name)
            or name in {"admin/package.json", "admin/package-lock.json", "admin/index.html",
                        "admin/tsconfig.json", "admin/vite.config.ts"}
            or re.fullmatch(r"admin/(?:src|public)/[A-Za-z0-9_./-]+\.(?:tsx?|css|html|json|svg|png|jpe?g|webp|gif|ico|woff2?|ttf)", name)
            or (name.startswith("assets/") and name.endswith(".json") and not name.startswith("assets/asset-patch/"))}


def complete_legacy_target(base: str, head: str, before: dict[str, bytes], after: dict[str, bytes],
                           base_identity: dict, identity: dict) -> tuple[dict[str, bytes], dict]:
    """Git absence is not proof that a historical deployed output was absent."""
    base_inputs, target_inputs = compile_input_entries(base), compile_input_entries(head)
    missing = sorted(before.keys() - after.keys())
    if base_inputs == target_inputs:
        # The complete current build is valid for the exact same compile inputs.
        # Preserve these files in place; do not call them historical Git blobs.
        if missing:
            after = {**after, **{name: before[name] for name in missing}}
            identity = {**identity, "mode": "git-blobs-with-preserved-generated",
                        "git_blob_files": identity["files"], "files": sorted(after),
                        "preserved_generated_files": missing, "preserved_from_build_commit": base,
                        "compile_inputs_identical": True}
        return after, identity
    # Only a stable, compiler-confirmed source/output layout permits deletion inference.
    if (base_inputs.get("tsconfig.json") != target_inputs.get("tsconfig.json")
            or base_identity.get("root_dir") != "src"):
        raise SystemExit("历史运行输出映射或编译配置不确定；需要历史实际产物，拒绝回滚封包")
    for name in target_inputs:
        if name.startswith("src/") and name.endswith(".tsx"):
            raise SystemExit(f"历史 JSX 输出扩展映射不确定，需要历史实际产物：{name}")
        if name.startswith("src/") and name.endswith(".json") and "out/" + name[4:] not in after:
            raise SystemExit(f"历史 JSON 未记录运行产物，需要历史实际产物：{name}")
        if not name.startswith("src/") or not name.endswith((".ts", ".tsx")) or name.endswith(".d.ts"):
            continue
        runtime_name = "out/" + re.sub(r"\.tsx?$", ".js", name[4:])
        if runtime_name not in after:
            raise SystemExit(f"历史源码存在但未记录运行产物，需要历史实际产物：{runtime_name}")
    for name in missing:
        if name.endswith(".js"):
            stem = "src/" + name[4:-3]
            source_names = {stem + ".ts", stem + ".tsx"}
        elif name.endswith(".json"):
            source_names = {"src/" + name[4:]}
        else:
            raise SystemExit(f"历史运行输出来源映射未知，需要历史实际产物：{name}")
        if source_names & target_inputs.keys():
            raise SystemExit(f"历史源码存在但未记录运行产物，需要历史实际产物：{name}")
    return after, identity


def runtime_artifacts(source: str, scratch: Path, dependency_root: str | None = None,
                      source_tree: str | None = None) -> tuple[dict[str, bytes], dict]:
    """Read historical blobs or build the complete runtime from this exact SHA."""
    effective = source_tree or source
    if not uses_source_build(effective):
        artifacts = committed_out_bytes(effective)
        return artifacts, {
            "mode": "git-blobs", "source_commit": source, "source_tree": source_tree, "files": sorted(artifacts),
        }
    helper = Path(__file__).resolve().with_name("build-runtime-artifact.cjs")
    command = ["node", str(helper), "--repo", REPO, "--source", source, "--output", str(scratch)]
    if source_tree:
        command.extend(["--source-tree", source_tree])
    if dependency_root:
        command.extend(["--dependency-root", dependency_root])
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise SystemExit(f"固定提交运行构建失败（{source}）：{result.stderr.strip()}")
    try:
        identity = json.loads(result.stdout)
        files = identity["files"]
        expected_lock = hashlib.sha256(committed_bytes(effective, "package-lock.json")).hexdigest()
        if (identity.get("schema") != 1 or identity.get("source_commit") != source
                or (source_tree is not None and identity.get("source_tree") != source_tree)
                or identity.get("lockfile_sha256") != expected_lock
                or not isinstance(identity.get("node_version"), str) or not identity["node_version"]
                or not isinstance(identity.get("typescript_version"), str) or not identity["typescript_version"]
                or not isinstance(files, list) or not files):
            raise ValueError("构建身份或产物清单不完整")
        if any(not isinstance(name, str) or not name.startswith(("out/", "web/dist/"))
               or "\\" in name or not is_safe_member(name) for name in files):
            raise ValueError("构建产物路径不安全")
        if len(files) != len(set(files)):
            raise ValueError("构建产物清单存在重复路径")
        policy = json.loads(committed_bytes(effective, BUILD_POLICY))
        required = policy.get("required_outputs")
        if (policy.get("schema") != 1 or not isinstance(required, list) or not required
                or any(not isinstance(name, str) or not name.startswith("out/")
                       or "\\" in name or not is_safe_member(name) for name in required)):
            raise ValueError("运行构建策略缺少有效的必需入口清单")
        if set(required) - set(files):
            raise ValueError("构建产物缺少必需运行入口")
        emitted = []
        for prefix in ("out", "web/dist"):
            directory = scratch / prefix
            if not directory.exists():
                continue
            for file in directory.rglob("*"):
                if file.is_symlink():
                    raise ValueError("构建产物不能为符号链接")
                if file.is_file():
                    emitted.append(file.relative_to(scratch).as_posix())
        if sorted(emitted) != sorted(files):
            raise ValueError("构建产物与完整输出清单不一致")
        if any(name.startswith("web/dist/") for name in files) and "web/dist/index.html" not in files:
            raise ValueError("管理后台完整构建缺少 index.html")
        payloads = {name: (scratch / name).read_bytes() for name in files}
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"拒绝未知或不完整运行构建（{source}）：{error}") from error
    return payloads, {"mode": "source-build", **identity}


def prepare_overlay(base: str, head: str, dependency_root: str | None = None,
                    source_tree: str | None = None, build_root: Path | None = None) -> tuple[list[str], list[str], dict[str, bytes] | None, dict | None]:
    """Separate runtime deletions from Git untracking during source-only migration."""
    effective = source_tree or head
    members, deleted = runtime_members(base, effective), deleted_runtime_members(base, effective)
    verify_discovery_source_closure(base, effective, members)
    if not uses_source_build(base) and not uses_source_build(effective):
        return members, deleted, None, None
    if build_root is not None:
        build_root = Path(build_root).resolve()
        if build_root.exists() and (not build_root.is_dir() or any(build_root.iterdir())):
            raise SystemExit("verification-root 必须为不存在或空的专用目录")
        build_root.mkdir(parents=True, exist_ok=True)
    with (nullcontext(str(build_root)) if build_root is not None else
          tempfile.TemporaryDirectory(prefix="starpoint-overlay-build-")) as temporary:
        scratch = Path(temporary)
        before, base_identity = runtime_artifacts(base, scratch / "base", dependency_root)
        after, source_identity = (runtime_artifacts(head, scratch / "source", dependency_root, source_tree)
                                  if source_tree else runtime_artifacts(head, scratch / "source", dependency_root))
        if build_root is not None:
            for name, identity in (("base", base_identity), ("source", source_identity)):
                (scratch / f"{name}.identity.json").write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if base_identity["mode"] == "source-build" and source_identity["mode"] == "git-blobs":
        after, source_identity = complete_legacy_target(base, effective, before, after, base_identity, source_identity)
    # A legacy baseline without any committed runtime is not evidence of an empty deployment.
    if not before or not after:
        raise SystemExit("无法确认完整运行基线或目标运行产物；拒绝封包")
    static = [name for name in members if not name.startswith("out/")]
    changed = [name for name, value in after.items() if before.get(name) != value]
    members = sorted(static + changed)
    deleted = sorted([name for name in deleted if not name.startswith("out/")] + list(before.keys() - after.keys()))
    payloads = {name: committed_bytes(effective, name) for name in static}
    payloads.update({name: after[name] for name in changed})
    return members, deleted, payloads, {"baseline": base_identity, "source": source_identity}


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_safe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        return False
    return ":" not in normalized.split("/")[0]


def is_runtime_path(relative: str) -> bool:
    return ((relative.startswith(RUNTIME_PREFIXES) or relative in RUNTIME_EXACT_PATHS)
            and not any(relative.startswith(pattern) for pattern in EXCLUDED_PATTERNS)
            and is_safe_member(relative))


def runtime_members(base: str, head: str) -> list[str]:
    """Files changed between base and head that belong in a cloud package."""
    changed = [name for name in git("diff", "--name-only", "--no-renames",
                                   "--diff-filter=ACM", "-z", base, head, "--").split("\0") if name]
    members = []
    for relative in changed:
        if not is_runtime_path(relative):
            continue
        # 必须在 head 中真实存在：排除"已移出 Git 跟踪但本地仍留着"的文件
        exists = subprocess.run(["git", "cat-file", "-e", f"{head}:{relative}"], cwd=REPO,
                                capture_output=True).returncode == 0
        if exists:
            members.append(relative)
    return sorted(members)


def verify_discovery_source_closure(base: str, head: str, members: list[str]) -> None:
    """Changed discovery inputs must match every bound byte in this exact Git tree."""
    index_path = "assets/content_discovery_runtime.json"
    after = tree_entries(head)
    if index_path not in after:
        return
    try:
        index = json.loads(committed_bytes(head, index_path))
        inputs = index["sourceInputs"] if isinstance(index, dict) else None
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"关联资料索引无法读取：{error}") from error
    if not isinstance(index, dict) or index.get("schemaVersion") != 2 or not isinstance(inputs, dict) or not inputs:
        raise SystemExit("关联资料索引缺少有效的完整来源清单")
    before = tree_entries(base)
    if index_path not in members and not any(before.get(name) != after.get(name) for name in inputs):
        return
    if any(not isinstance(name, str) for name in inputs):
        raise SystemExit("关联资料索引来源路径无效")
    if {name for name in inputs if name.startswith("tools/")} != DISCOVERY_GENERATORS:
        raise SystemExit("关联资料索引绑定的生成器与云包精确白名单不一致")
    for name, expected in inputs.items():
        if (not isinstance(name, str) or "\\" in name or not is_runtime_path(name)
                or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)):
            raise SystemExit(f"关联资料索引来源路径或摘要无效：{name}")
        if name not in after or after[name][0] not in {"100644", "100755"}:
            raise SystemExit(f"关联资料索引来源不是目标提交的普通文件：{name}")
        if before.get(name) != after.get(name) and name not in members:
            raise SystemExit(f"关联资料索引来源已更新但未进入云包：{name}")
        try:
            actual = hashlib.sha256(committed_bytes(head, name)).hexdigest()
        except subprocess.CalledProcessError as error:
            raise SystemExit(f"关联资料索引来源在目标提交中不存在：{name}") from error
        if actual != expected:
            raise SystemExit(f"关联资料索引来源与目标提交字节不符：{name}")


def deleted_runtime_members(base: str, head: str) -> list[str]:
    return sorted(name for name in git("diff", "--name-only", "--no-renames",
                                      "--diff-filter=D", "-z", base, head, "--").split("\0")
                  if name and is_runtime_path(name))


def verify_against_head(members: list[str], head: str = "HEAD") -> None:
    for relative in members:
        working = git("hash-object", "--", relative).strip()
        committed = git("rev-parse", f"{head}:{relative}").strip()
        if working != committed:
            raise SystemExit(f"工作区与提交内容不一致，请先提交：{relative}")


def build_zip(zip_path: str, members: list[str], source: str = "HEAD", payloads: dict[str, bytes] | None = None) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in members:
            archive.writestr(relative, payloads[relative] if payloads is not None else committed_bytes(source, relative))


def verify_zip(zip_path: str, members: list[str], source: str = "HEAD", payloads: dict[str, bytes] | None = None) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if sorted(names) != sorted(members):
            raise SystemExit("ZIP 成员与预期清单不一致")
        if archive.testzip() is not None:
            raise SystemExit("ZIP CRC 校验失败")
        for name in names:
            if not is_safe_member(name):
                raise SystemExit(f"不安全的成员路径：{name}")
            expected = payloads[name] if payloads is not None else committed_bytes(source, name)
            if archive.read(name) != expected:
                raise SystemExit(f"成员字节与目标提交不一致：{name}")


def write_sidecars(zip_path: str, zip_name: str, members: list[str], zip_sha: str,
                   deleted: list[str] | None = None) -> None:
    with open(f"{zip_path}.files.txt", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# {zip_name}\n")
        handle.write("# 部署前按下列路径备份将被覆盖的文件（路径 + 字节数）\n")
        handle.write("# bytes  path\n")
        with zipfile.ZipFile(zip_path) as archive:
            for relative in members:
                handle.write(f"{archive.getinfo(relative).file_size}  {relative}\n")
        if deleted:
            handle.write("\n# 下列路径须备份后显式删除；解压 ZIP 不会自动删除\n")
            for relative in deleted:
                handle.write(f"DELETE  {relative}\n")
    with open(f"{zip_path}.sha256.txt", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{zip_sha}  {zip_name}\n")
    if deleted:
        with open(f"{zip_path}.delete-files.txt", "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# 从基线回退/更新到目标提交时，备份后显式删除以下路径\n")
            handle.write("# 本工具不连接云服，也不执行删除；先确认实际版本和部署目录\n")
            for relative in deleted:
                handle.write(f"{relative}\n")


def validate_release_tag(tag: str) -> None:
    match = re.fullmatch(r"release-(\d{4}\.\d{2}\.\d{2})-([1-9]\d*)", tag)
    if not match:
        raise SystemExit("标签须使用 release-YYYY.MM.DD-N，序号从 1 开始")
    try:
        datetime.strptime(match.group(1), "%Y.%m.%d")
    except ValueError as error:
        raise SystemExit("标签日期无效") from error


def publish_release_tag(tag: str, head: str, base: str, zip_path: str, zip_sha: str,
                        selection: dict | None = None) -> dict:
    """Publish only this tag after checking the exact source and package identity."""
    validate_release_tag(tag)
    if selection:
        identity = {key: value for key, value in selection.items() if key != "identity_sha256"}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (selection.get("source_commit") != head or selection.get("base_commit") != base
                or selection.get("identity_sha256") != digest):
            raise SystemExit("选择配方身份与标签来源不符")
        with open(f"{zip_path}.source-recipe.json", encoding="utf-8") as handle:
            if json.load(handle) != selection:
                raise SystemExit("选择配方 sidecar 与标签身份不符")
    if git("tag", "--list", tag).strip():
        raise SystemExit(f"标签已存在，拒绝重用或修改指向：{tag}")
    refs = {}
    for line in git("ls-remote", "origin", "refs/heads/main", f"refs/tags/{tag}").splitlines():
        sha, ref = line.split("\t", 1)
        refs[ref] = sha
    if f"refs/tags/{tag}" in refs:
        raise SystemExit(f"远端标签已存在，拒绝重用：{tag}")
    remote_main = refs.get("refs/heads/main")
    if not remote_main:
        raise SystemExit("远端 main 不存在，不能发布正式交付标签")
    ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", head, remote_main],
                              cwd=REPO, capture_output=True)
    if ancestry.returncode != 0:
        raise SystemExit("源提交尚未整合到远端 main，或远端对象未拉取；先核对并同步 main")
    result = subprocess.run(
        ["gh", "api", f"repos/{{owner}}/{{repo}}/commits/{head}/check-runs?per_page=100"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", check=True)
    checks = [check for check in json.loads(result.stdout).get("check_runs", [])
              if check.get("name") == "hygiene" and check.get("head_sha") == head]
    latest = max(checks, key=lambda check: check.get("id", 0)) if checks else {}
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise SystemExit(f"源提交 {head} 的 hygiene 尚未成功，不能发布标签")
    if sha256_of(zip_path) != zip_sha:
        raise SystemExit("整合包在核验后发生变化，不能发布标签")
    message = (f"云服交付 {tag}\n\n源提交：{head}\n基线提交：{base}\n"
               f"整合包：{os.path.basename(zip_path)}\n整包 SHA-256：{zip_sha}\n")
    if selection:
        message += (f"\n选择性交付：server-fixes（不代表源提交全部内容已交付）\n"
                    f"有效源码 tree：{selection['source_tree']}\n"
                    f"选择配方 SHA-256：{selection['identity_sha256']}\n"
                    f"选择提交：{','.join(selection['selected_commits'])}\n")
    git("tag", "-a", tag, head, "-m", message)
    git("push", "origin", f"refs/tags/{tag}:refs/tags/{tag}")
    peeled = git("ls-remote", "origin", f"refs/tags/{tag}^{{}}")
    if not peeled or peeled.split("\t", 1)[0] != head:
        raise SystemExit("远端标签读回未指向预期提交，请保留包和本地标签并核对远端")
    return {"name": tag, "source_commit": head, "pushed": True,
            "source_on_remote_main": True, "hygiene_run_id": latest.get("id"),
            **({"selection_tree": selection["source_tree"], "selection_identity_sha256": selection["identity_sha256"]} if selection else {})}


def update_record(batch: str, zip_path: str, zip_name: str, zip_sha: str, zip_size: int,
                  members: list[str], base: str, head: str, note: str | None, created_at: str,
                  release_tag: str | None = None, source_ref: str = "HEAD",
                  deleted: list[str] | None = None, publication: dict | None = None,
                  runtime_build: dict | None = None, selection: dict | None = None,
                  pending: dict | None = None) -> dict:
    with open(RECORD, encoding="utf-8") as handle:
        record = json.load(handle)
    outgoing_latest = record["latest_delivery"]
    outgoing_previous = record.get("previous_delivery")
    if outgoing_previous is not None:
        record.setdefault("delivery_history", []).append({
            key: outgoing_previous.get(key) for key in (
                "batch", "created_at", "baseline_commit", "included_through_commit",
                "cdn_from", "cdn_to", "archive", "sha256", "file_count", "size",
                "cloud_deployment_status", "cloud_deployed_by_this_task",
                "next_batch_assumes_this_delivery_covered", "release_tag", "tag_publication",
                "source_ref", "deleted_files", "delete_files_list", "runtime_build",
                "selection", "scope_status", "pending", "selection_plan", "selection_recipe", "pending_files_list",
                "package_source_commit", "package_source_tree",
            )
        })
    record["previous_delivery"] = outgoing_latest
    record["latest_delivery"] = {
        "batch": batch,
        "created_at": created_at,
        "baseline_commit": base,
        "included_through_commit": base if selection else head,
        "package_source_commit": head,
        "package_source_tree": selection["source_tree"] if selection else git("rev-parse", f"{head}^{{tree}}").strip(),
        "source_ref": source_ref,
        "runtime_build": runtime_build,
        "release_tag": release_tag,
        "tag_publication": publication or {"name": release_tag, "pushed": False},
        "baseline_delivery": outgoing_latest.get("batch"),
        "archive": zip_path,
        "sha256": zip_sha,
        "size": zip_size,
        "file_count": len(members),
        "files_list": f"{zip_path}.files.txt",
        "deleted_files": deleted or [],
        "delete_files_list": f"{zip_path}.delete-files.txt" if deleted else None,
        "deployment_note": note,
        "cloud_deployment_status": "not_deployed_by_this_task",
        "cloud_deployed_by_this_task": False,
        "cloud_deployment_independently_verified": False,
        "next_batch_assumes_this_delivery_covered": True,
        "admission_pair_included": False,
        "schema_migration_required": None if selection else any(name in {
            "assets/content_deployment_review_plan.json", "assets/content_box_exchange_review.json", "scripts/time-content-deployment.cjs",
            "scripts/migrate-time-content.ps1",
        } for name in members),
        "source_status": {
            "branch": git("branch", "--show-current").strip() or "detached",
            "head": head,
            "baseline_commit": base,
            "committed": True,
            "effective_source_kind": "selected-tree" if selection else "commit",
            "anchor_committed": True,
            "effective_tree_is_new_commit": False if selection else None,
            "effective_tree": selection["source_tree"] if selection else None,
            "pushed": True if publication else None,
        },
        "validation": {
            "members_match_committed_bytes": runtime_build is None or runtime_build["source"]["mode"] in {"git-blobs", "git-blobs-with-preserved-generated"} or not any(name.startswith(("out/", "web/dist/")) for name in members),
            "static_members_match_committed_bytes": True,
            "runtime_artifact_origins_verified": True,
            "generated_members_match_fixed_source_build": runtime_build is not None and runtime_build["source"]["mode"] == "source-build",
            "zip_members_match_source_bytes": True,
            "unsafe_member_paths": 0,
            "cdn_archives_included": any(name.startswith("assets/asset-patch/active/") for name in members),
            "admission_pair_excluded": True,
            "cloud_deployment": "not performed",
        },
    }
    if selection:
        if pending is None:
            pending = pending_selection(selection)
        record["latest_delivery"].update({
            "selection": selection,
            "selection_plan": f"{zip_path}.selection-plan.json",
            "selection_recipe": f"{zip_path}.source-recipe.json",
            "pending_files_list": f"{zip_path}.pending.json",
            "pending": pending,
            "cdn_from": pending["cdn_from"], "cdn_to": pending["cdn_from"],
            "scope_status": {
                "mixed": True,
                "whole_repository_baseline_commit": base,
                "server": {"status": "selected_repairs_delivered", "effective_tree": selection["source_tree"],
                           "source_anchor_commit": head, "selected_commits": selection["selected_commits"]},
                "content": {"status": "unchanged", "baseline_commit": base},
                "cdn": {"status": "unchanged", "baseline_commit": base, "version": pending["cdn_from"]},
                "pending_scope": {"source_anchor_commit": head, "runtime_file_count": pending["file_count"],
                                  "cdn_target": pending["cdn_to"]},
            },
        })
    with open(RECORD, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return record["latest_delivery"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", help="批次名；提供 --release-tag 时默认使用标签名")
    parser.add_argument("--base", required=True, help="上一个交付批次的源提交")
    parser.add_argument("--source", default="HEAD", help="目标提交/标签；回退时无需切换工作区")
    parser.add_argument("--release-tag", help="正式交付版本 release-YYYY.MM.DD-N")
    parser.add_argument("--publish-tag", action="store_true", help="包核验后创建并推送指定标签（须有推送授权）")
    parser.add_argument("--note", default=None, help="部署说明文件（可选，会复制进批次目录）")
    parser.add_argument("--no-record", action="store_true", help="不更新本地交付记录")
    parser.add_argument("--dependency-root", help="由构建器核验的锁定依赖安装目录；默认隔离 npm ci")
    parser.add_argument("--selection-plan", help="明确选择的 server-fixes JSON 配方；保留未选择范围")
    parser.add_argument("--verification-root", help="空的专用目录，保留两端完整编译输出供本次核验")
    args = parser.parse_args()

    if args.release_tag:
        validate_release_tag(args.release_tag)
    if args.publish_tag and not args.release_tag:
        parser.error("--publish-tag 必须同时指定 --release-tag")
    batch = args.batch or args.release_tag
    if not batch or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", batch):
        parser.error("须指定安全批次名或 --release-tag")
    head = git("rev-parse", "--verify", "--end-of-options", f"{args.source}^{{commit}}").strip()
    base = git("rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}").strip()
    selection = prepare_selection(args.selection_plan, base, head) if args.selection_plan else None
    if not selection:
        refuse_implicit_mixed_baseline()
    effective = selection["source_tree"] if selection else head
    pending = pending_selection(selection) if selection else None
    if selection or args.verification_root:
        members, deleted, payloads, runtime_build = prepare_overlay(
            base, head, args.dependency_root, selection["source_tree"] if selection else None,
            Path(args.verification_root) if args.verification_root else None)
    else:
        members, deleted, payloads, runtime_build = prepare_overlay(base, head, args.dependency_root)
    if not members and not deleted:
        raise SystemExit("没有需要交付的运行文件")
    if not selection and head == git("rev-parse", "HEAD").strip():
        verify_against_head([name for name in members if payloads is None or not name.startswith(("out/", "web/dist/"))], head)

    zip_name = f"startpoint-cn-cloud-overlay-{batch}.zip"
    out_dir = os.path.join(OUT_ROOT, batch)
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, zip_name)
    if os.path.exists(zip_path):
        raise SystemExit(f"拒绝覆盖已存在的包：{zip_path}")

    # A readable but incomplete ZIP must never acquire the formal delivery name.
    # Hard-link publication is atomic and refuses an existing destination on
    # both Windows and POSIX; rename/replace would overwrite it on POSIX.
    descriptor, pending_zip = tempfile.mkstemp(prefix=".pending-", suffix=".zip", dir=out_dir)
    os.close(descriptor)
    try:
        if payloads is None:
            build_zip(pending_zip, members, effective)
            verify_zip(pending_zip, members, effective)
        else:
            build_zip(pending_zip, members, effective, payloads)
            verify_zip(pending_zip, members, effective, payloads)
        try:
            os.link(pending_zip, zip_path)
        except FileExistsError as error:
            raise SystemExit(f"拒绝覆盖已存在的包：{zip_path}") from error
    finally:
        os.unlink(pending_zip)
    zip_sha = sha256_of(zip_path)
    zip_size = os.path.getsize(zip_path)
    write_sidecars(zip_path, zip_name, members, zip_sha, deleted)
    if selection:
        plan = {key: selection[key] for key in ("schema", "kind", "base_commit", "source_commit", "selected_commits")}
        for suffix, data in (("selection-plan.json", plan), ("source-recipe.json", selection), ("pending.json", pending)):
            with open(f"{zip_path}.{suffix}", "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")

    note_path = None
    if args.note:
        note_path = f"{zip_path}.部署说明.txt"
        with open(args.note, encoding="utf-8") as src, open(note_path, "w", encoding="utf-8", newline="\n") as dst:
            dst.write(src.read())

    publication = None
    publication_error = None
    if args.publish_tag:
        try:
            publication = (publish_release_tag(args.release_tag, head, base, zip_path, zip_sha, selection)
                           if selection else publish_release_tag(args.release_tag, head, base, zip_path, zip_sha))
        except (SystemExit, subprocess.CalledProcessError) as error:
            publication_error = str(error)
    created_at = datetime.now(DELIVERY_TIMEZONE).isoformat(timespec="seconds")
    if not args.no_record and not publication_error:
        update_record(batch, zip_path, zip_name, zip_sha, zip_size, members, base, head,
                      note_path, created_at, args.release_tag, args.source, deleted, publication, runtime_build,
                      selection, pending)

    receipt = {
        "release_tag": args.release_tag,
        "batch": batch,
        "source_commit": head,
        "source_tree": effective if selection else git("rev-parse", f"{head}^{{tree}}").strip(),
        "baseline_commit": base,
        "selection": selection,
        "selection_plan": f"{zip_path}.selection-plan.json" if selection else None,
        "selection_recipe": f"{zip_path}.source-recipe.json" if selection else None,
        "pending_files_list": f"{zip_path}.pending.json" if selection else None,
        "runtime_build": runtime_build,
        "archive": zip_name,
        "sha256": zip_sha,
        "deleted_files": deleted,
        "created_at": created_at,
        "tag_publication": publication or {"name": args.release_tag, "pushed": False},
        "publication_error": publication_error,
    }
    with open(f"{zip_path}.release.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(json.dumps({
        "batch": batch,
        "zip": zip_path,
        "members": len(members),
        "size": zip_size,
        "sha256": zip_sha,
        "files_list": f"{zip_path}.files.txt",
        "deployment_note": note_path,
        "release_receipt": f"{zip_path}.release.json",
        "delete_files_list": f"{zip_path}.delete-files.txt" if deleted else None,
        "tag_publication": receipt["tag_publication"],
    }, ensure_ascii=False, indent=2))
    if publication_error:
        raise SystemExit(f"整合包已生成并保存；标签尚未确认发布：{publication_error}")


if __name__ == "__main__":
    main()
