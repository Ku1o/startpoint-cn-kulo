#!/usr/bin/env python3
"""Explicit push facts and an independent, pinned history secret scan."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

WORKFLOW = ".github/workflows/hygiene.yml"
QUERY = '''query($owner:String!,$name:String!,$qualified:String!){repo:repository(owner:$owner,name:$name){viewerPermission defaultBranchRef{name} ref(qualifiedName:$qualified){target{oid}}} scannerAction:repository(owner:"gitleaks",name:"gitleaks-action"){object(expression:"v3"){oid}}}'''
FULL_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class SupportError(Exception):
    pass


def run(args, *, env=None, timeout=120):
    child_env = (env if env is not None else os.environ).copy()
    child_env["GIT_OPTIONAL_LOCKS"] = "0"
    child_env["GIT_NO_LAZY_FETCH"] = "1"
    try:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=child_env, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        # Do not interpolate argv, URLs, environment, or subprocess output.
        raise SupportError("command unavailable or timed out: " + type(exc).__name__) from exc


def git(repo, *args, env=None):
    result = run(["git", "-C", str(repo), *args], env=env)
    if result.returncode:
        raise SupportError("git operation failed: " + args[0])
    return result.stdout


def txt(data):
    return data.decode("utf-8", errors="replace").strip()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repository(path):
    repo = Path(path).resolve()
    root = Path(txt(git(repo, "rev-parse", "--show-toplevel"))).resolve()
    if root != repo:
        raise SupportError("--repo must name the repository root")
    return repo


def output_path(repo, path):
    """Resolve immediately before writing, including linked-worktree metadata."""
    resolved = path.resolve()
    gitdir = Path(txt(git(repo, "rev-parse", "--absolute-git-dir"))).resolve()
    common = Path(txt(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))).resolve()
    if any(resolved.is_relative_to(root) for root in (repo, gitdir, common)):
        raise SupportError("output must remain outside the repository and its Git metadata")
    if resolved.exists():
        raise SupportError("output already exists; choose a new path to preserve earlier evidence")
    if not resolved.parent.is_dir():
        raise SupportError("output parent directory does not exist")
    return resolved


def commit(repo, value, require_full=False):
    if require_full and not FULL_SHA.fullmatch(value):
        raise SupportError("base and target must be lowercase full commit SHAs")
    resolved = txt(git(repo, "rev-parse", "--verify", "--end-of-options", value + "^{commit}"))
    if not FULL_SHA.fullmatch(resolved) or (require_full and value != resolved):
        raise SupportError("object is not the specified full commit SHA")
    return resolved


def read_lock(path):
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SupportError("scanner lock is missing, unreadable, or invalid JSON") from exc
    fields = ("version", "binary_relative_path", "binary_sha256", "archive_sha256",
              "verified_ci_action_sha", "verified_workflow_sha256", "verified_ci_run")
    if not isinstance(lock, dict) or any(not isinstance(lock.get(key), str) or not lock[key] for key in fields):
        raise SupportError("scanner lock has missing or invalid identity fields")
    if not re.fullmatch(r"\d+\.\d+\.\d+", lock["version"]):
        raise SupportError("scanner lock version is invalid")
    for key in ("binary_sha256", "archive_sha256", "verified_workflow_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", lock[key]):
            raise SupportError("scanner lock hash is invalid: " + key)
    if not FULL_SHA.fullmatch(lock["verified_ci_action_sha"]):
        raise SupportError("scanner lock action SHA is invalid")
    relative = Path(lock["binary_relative_path"])
    binary = (path.parent / relative).resolve()
    if relative.is_absolute() or not binary.is_relative_to(path.parent.resolve()):
        raise SupportError("scanner binary path must remain inside the lock directory")
    return lock, binary


def scanner_identity(lock_path):
    lock, binary = read_lock(lock_path)
    identity = {"lock": lock, "binary_path": str(binary), "binary_sha256": None,
                "observed_version": None, "identity_verified": False}
    try:
        identity["binary_sha256"] = file_hash(binary)
    except OSError as exc:
        raise SupportError("fixed scanner binary is missing or unreadable") from exc
    if identity["binary_sha256"] != lock["binary_sha256"]:
        raise SupportError("fixed scanner binary SHA256 differs from lock")
    result = run([str(binary), "version"])
    version = txt(result.stdout)
    if result.returncode or version not in (lock["version"], "v" + lock["version"]):
        raise SupportError("fixed scanner version differs from lock or version command failed")
    identity["observed_version"] = version.removeprefix("v")
    identity["identity_verified"] = True
    return identity


def remote_repository(repo, remote):
    urls = txt(git(repo, "remote", "get-url", "--push", "--all", remote)).splitlines()
    if len(urls) != 1:
        raise SupportError("exactly one push URL is required; multiple push URLs are unsupported")
    url = urls[0]
    match = re.fullmatch(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?", url)
    if match:
        owner, name = match.groups()
    else:
        try:
            parsed = urlsplit(url)
            standard_host = parsed.hostname == "github.com" and parsed.port is None
        except ValueError as exc:
            raise SupportError("push URL is malformed; URL withheld") from exc
        if parsed.scheme not in ("https", "ssh") or not standard_host:
            raise SupportError("push URL must be a standard github.com HTTPS or SSH URL")
        if parsed.query or parsed.fragment or parsed.password or (parsed.scheme == "https" and parsed.username):
            raise SupportError("credential-bearing or nonstandard push URLs are unsupported")
        if parsed.scheme == "ssh" and parsed.username != "git":
            raise SupportError("GitHub SSH URL must use the git user")
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2:
            raise SupportError("push URL does not identify one GitHub repository")
        owner, name = parts
        name = name.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise SupportError("push URL contains an invalid GitHub owner or repository name")
    return {"owner": owner, "name": name, "url": "https://github.com/" + owner + "/" + name}


def remote_facts(remote, branch):
    result = run(["gh", "api", "graphql", "-f", "query=" + QUERY,
                  "-F", "owner=" + remote["owner"], "-F", "name=" + remote["name"],
                  "-F", "qualified=refs/heads/" + branch])
    if result.returncode:
        raise SupportError("GitHub query failed (authentication, network, or API error); no fetch performed")
    try:
        payload = json.loads(result.stdout)
        if payload.get("errors"):
            raise ValueError("GraphQL errors")
        data = payload["data"]
        repo = data["repo"]
        base = repo["ref"]["target"]["oid"] if repo["ref"] else None
        action = data["scannerAction"]["object"]["oid"]
        permission = repo["viewerPermission"]
        default_branch = repo["defaultBranchRef"]["name"]
        if not permission or not default_branch or not FULL_SHA.fullmatch(action):
            raise ValueError("incomplete query")
        if base is not None and not FULL_SHA.fullmatch(base):
            raise ValueError("invalid branch object")
        return {"viewer_permission": permission, "default_branch": default_branch,
                "branch": branch, "base_sha": base, "scanner_action_v3_sha": action,
                "query_count": 1}
    except (ValueError, TypeError, KeyError) as exc:
        raise SupportError("GitHub query returned incomplete or invalid facts") from exc


def local_facts(repo, target):
    return {"head_sha": commit(repo, "HEAD"),
            "branch": txt(git(repo, "branch", "--show-current")) or None,
            "status_porcelain": git(repo, "status", "--porcelain=v1", "-z").decode("utf-8", errors="replace").split("\0")[:-1],
            "target_sha": commit(repo, target)}


def range_facts(repo, base, target):
    commit(repo, base, require_full=True)
    commit(repo, target, require_full=True)
    if txt(git(repo, "rev-parse", "--is-shallow-repository")) != "false":
        raise SupportError("shallow history cannot establish the complete added commit range; no fetch performed")
    result = run(["git", "-C", str(repo), "merge-base", "--is-ancestor", base, target])
    if result.returncode not in (0, 1):
        raise SupportError("git ancestry query failed")
    commits = txt(git(repo, "rev-list", base + ".." + target)).splitlines()
    paths = git(repo, "diff", "--name-only", "-z", base, target).decode("utf-8", errors="replace").split("\0")[:-1]
    return {"base_object_present": True, "base_is_ancestor": result.returncode == 0,
            "new_reachable_commits": commits, "new_reachable_commit_count": len(commits),
            "diff_paths": paths}


def workflow_facts(repo, target, lock):
    target_hash = sha256(git(repo, "show", target + ":" + WORKFLOW))
    worktree_path = repo / WORKFLOW
    worktree_hash = file_hash(worktree_path) if worktree_path.is_file() else None
    return {"path": WORKFLOW, "target_sha256": target_hash,
            "worktree_sha256": worktree_hash,
            "target_matches_lock": target_hash == lock["verified_workflow_sha256"],
            "worktree_matches_target": worktree_hash == target_hash}


def context(args):
    repo = repository(args.repo)
    result = {"command": "context", "repo": str(repo), "remote_name": args.remote,
              "remote": None, "local": None, "github": None,
              "range": {"base_object_present": None, "base_is_ancestor": None,
                        "new_reachable_commits": None, "new_reachable_commit_count": None,
                        "diff_paths": None}, "scanner": None, "errors": []}
    def error(area, exc):
        result["errors"].append({"area": area, "message": str(exc)})
    # Independent local work overlaps the single combined GitHub request.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {"local": pool.submit(local_facts, repo, args.target),
                "scanner": pool.submit(scanner_identity, args.lock),
                "remote": pool.submit(remote_repository, repo, args.remote)}
        try:
            result["remote"] = jobs["remote"].result()
            github_job = pool.submit(remote_facts, result["remote"], args.branch)
        except (SupportError, OSError, ValueError) as exc:
            error("remote", exc)
            github_job = None
        for area in ("local", "scanner"):
            try:
                result[area] = jobs[area].result()
            except (SupportError, OSError, ValueError) as exc:
                error(area, exc)
                if area == "scanner":
                    try:
                        lock, binary = read_lock(args.lock)
                        result["scanner"] = {"lock": lock, "binary_path": str(binary),
                                             "binary_sha256": None, "observed_version": None,
                                             "identity_verified": False}
                    except SupportError:
                        pass
        if github_job:
            try:
                result["github"] = github_job.result()
            except SupportError as exc:
                error("github", exc)
    if result["local"] and result["github"]:
        base = result["github"]["base_sha"]
        if base is None:
            error("range", SupportError("remote branch does not exist; its base and range are unknown"))
        else:
            try:
                result["range"] = range_facts(repo, base, result["local"]["target_sha"])
            except SupportError as exc:
                try:
                    commit(repo, base, require_full=True)
                except SupportError:
                    result["range"]["base_object_present"] = False
                error("range", exc)
    if result["scanner"]:
        scanner = result["scanner"]
        lock = scanner["lock"]
        scanner["action_matches_lock"] = None
        scanner["workflow"] = None
        if result["github"]:
            scanner["action_matches_lock"] = result["github"]["scanner_action_v3_sha"] == lock["verified_ci_action_sha"]
        if result["local"]:
            try:
                scanner["workflow"] = workflow_facts(repo, result["local"]["target_sha"], lock)
            except (SupportError, OSError) as exc:
                error("workflow", exc)
        scanner["needs_review"] = (not scanner["identity_verified"] or
                                    scanner["action_matches_lock"] is not True or
                                    not scanner["workflow"] or
                                    not scanner["workflow"]["target_matches_lock"] or
                                    not scanner["workflow"]["worktree_matches_target"])
    return result, 1 if result["errors"] else 0


def scan_rules(repo, target):
    rules = {}
    for name in (".gitleaks.toml", ".gitleaksignore"):
        path = repo / name
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise SupportError("required scanner rule file is missing or unreadable: " + name) from exc
        committed = git(repo, "show", target + ":" + name)
        rules[name] = {"worktree_sha256": sha256(current), "target_sha256": sha256(committed),
                       "matches_target": current == committed}
    return rules


def longpaths_env():
    env = os.environ.copy()
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
        if count < 0:
            raise ValueError("negative count")
    except ValueError as exc:
        raise SupportError("GIT_CONFIG_COUNT is invalid") from exc
    env["GIT_CONFIG_COUNT"] = str(count + 1)
    env["GIT_CONFIG_KEY_" + str(count)] = "core.longpaths"
    env["GIT_CONFIG_VALUE_" + str(count)] = "true"
    return env


def scan_diagnostics(data):
    output = data.decode("utf-8", errors="replace")
    categories = []
    # Keep only fixed categories and scanner counters; never expose source lines.
    patterns = {"filename_too_long": r"filename too long|file name too long",
                "partial_scan": r"partial(?:ly)? scan|scan.{0,30}incomplete|unable to scan|failed to scan|skipping.{0,30}(?:file|commit)",
                "git_error": r"fatal:|error running git|git.{0,40}(?:error|failed)|(?:error|failed).{0,40}git|bad object|unknown revision|invalid revision|ambiguous argument",
                "scanner_error": r"\b(?:ERR|FTL)\b|panic:|error(?:\s|:).*"}
    for category, pattern in patterns.items():
        if re.search(pattern, output, re.I):
            categories.append(category)
    counters = []
    for pattern in (r"\b\d+ commits? scanned\b", r"\bscanned ~?\d+(?:\.\d+)?\s?(?:bytes|KB|MB|GB)\b",
                    r"\bleaks found:\s*\d+\b", r"\bno leaks found\b"):
        counters.extend(re.findall(pattern, output, re.I))
    return {"error_categories": categories, "redacted_summary": counters,
            "raw_output_bytes": len(data), "source_lines_withheld": True}


def scan(args):
    repo = repository(args.repo)
    result = {"command": "scan", "repo": str(repo), "base_sha": args.base,
              "target_sha": args.target, "status": "error", "scan_executed": False,
              "scanner": None, "rules": None, "range": None,
              "report_path": str(args.report.resolve()), "report_written": False, "errors": []}
    try:
        identity = scanner_identity(args.lock)
        result["scanner"] = identity
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            history_job = pool.submit(range_facts, repo, args.base, args.target)
            rules_job = pool.submit(scan_rules, repo, args.target)
            result["range"] = history_job.result()
            result["rules"] = rules_job.result()
        if not all(rule["matches_target"] for rule in result["rules"].values()):
            raise SupportError("worktree scanner rules differ from target commit; review required before scanning")
        report = output_path(repo, args.report)
        if not result["range"]["new_reachable_commits"]:
            result["status"] = "empty_range"
            return result, 0
        command = [identity["binary_path"], "detect", "--source", str(repo), "--redact", "--exit-code=2",
                   "--report-format=json", "--report-path=" + str(report),
                   "--config", str(repo / ".gitleaks.toml"),
                   "--gitleaks-ignore-path", str(repo / ".gitleaksignore"),
                   "--log-opts=-m " + args.base + ".." + args.target]
        env = longpaths_env()
        result["scan_executed"] = True
        completed = run(command, env=env, timeout=1800)
        result["scanner_exit_code"] = completed.returncode
        result["diagnostics"] = scan_diagnostics(completed.stdout + b"\n" + completed.stderr)
        result["report_written"] = report.is_file()
        if completed.returncode not in (0, 2) or result["diagnostics"]["error_categories"]:
            raise SupportError("scanner failed or reported an incomplete scan; inspect fixed error categories")
        if not report.is_file():
            raise SupportError("scanner did not produce its JSON report")
        try:
            findings = json.loads(report.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as exc:
            raise SupportError("scanner report is unreadable or invalid JSON") from exc
        if not isinstance(findings, list):
            raise SupportError("scanner report is not a findings list")
        result["finding_count"] = len(findings)
        if (completed.returncode == 0 and findings) or (completed.returncode == 2 and not findings):
            raise SupportError("scanner exit code and report disagree")
        # Detect concurrent changes to the exact files passed to the scanner.
        if scan_rules(repo, args.target) != result["rules"]:
            raise SupportError("scanner rules changed during scan; result is incomplete")
        if file_hash(Path(identity["binary_path"])) != identity["binary_sha256"]:
            raise SupportError("scanner binary changed during scan; result is incomplete")
        result["status"] = "findings" if completed.returncode == 2 else "clean"
        return result, completed.returncode
    except (SupportError, OSError, ValueError) as exc:
        result["errors"].append(str(exc))
        return result, 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ctx = sub.add_parser("context", help="collect local and GitHub facts; no fetch or push")
    ctx.add_argument("--repo", required=True)
    ctx.add_argument("--remote", default="origin")
    ctx.add_argument("--branch", default="main")
    ctx.add_argument("--target", default="HEAD")
    ctx.add_argument("--output", type=Path)
    scn = sub.add_parser("scan", help="scan the complete added history with the pinned binary")
    scn.add_argument("--repo", required=True)
    scn.add_argument("--base", required=True)
    scn.add_argument("--target", required=True)
    scn.add_argument("--report", required=True, type=Path)
    for item in (ctx, scn):
        item.add_argument("--lock", type=Path, default=Path(__file__).resolve().with_name("scanner-lock.json"))
    args = parser.parse_args(argv)
    args.lock = args.lock.resolve()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    started = time.monotonic()
    try:
        result, code = context(args) if args.command == "context" else scan(args)
    except (SupportError, OSError, ValueError) as exc:
        result, code = {"command": args.command, "errors": [str(exc)]}, 1
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["started_at_utc"] = started_at
    result["finished_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.command == "context" and args.output:
        try:
            # Explicit output only; never overwrite a previous context snapshot.
            path = output_path(repository(args.repo), args.output)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
        except (SupportError, OSError) as exc:
            message = str(exc) if isinstance(exc, SupportError) else "context output could not be created"
            result.setdefault("errors", []).append(message)
            encoded, code = json.dumps(result, ensure_ascii=False, indent=2), 1
    print(encoded)
    return code


if __name__ == "__main__":
    sys.exit(main())
