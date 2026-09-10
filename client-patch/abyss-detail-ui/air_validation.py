"""Desktop AIR is opt-in; a cached result is valid only for identical inputs."""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text("utf8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf8")


def fingerprints(paths):
    return {name: sha(path) for name, path in paths.items()}


def matching_result(work, inputs):
    receipt_path, result_path = work / "air-test-receipt.json", work / "harness-result.json"
    if not receipt_path.exists() or not result_path.exists():
        return None
    receipt = read(receipt_path)
    if receipt.get("inputs") != inputs or receipt.get("result_sha256") != sha(result_path):
        return None
    result = read(result_path)
    return result if receipt.get("status") == "passed" and result.get("passed") else None


def validate(work, paths, *, run_air_tests=False, runner=None):
    work = Path(work)
    inputs = fingerprints(paths)
    state = {"status": "not_run", "inputs": inputs,
             "paths": {key: str(Path(value).resolve()) for key, value in paths.items()},
             "air_started": False}
    state_path = work / "air-validation.json"
    save(state_path, state)
    result = matching_result(work, inputs)
    if run_air_tests:
        if runner is None:
            raise ValueError("AIR runner required for an explicit test run")
        state.update(status="running", air_started=True)
        save(state_path, state)
        # A failed run must not leave an old result eligible for the next build.
        save(work / "air-test-receipt.json", {"status": "running", "inputs": inputs})
        runner()
        if fingerprints(paths) != inputs:
            raise ValueError("AIR test inputs changed while running")
        result = read(work / "harness-result.json")
        if result.get("passed") is not True:
            raise ValueError("AIR checks failed")
        save(work / "air-test-receipt.json", {"status": "passed", "inputs": inputs,
             "result_sha256": sha(work / "harness-result.json")})
        state["status"] = "passed"
    elif result is not None:
        state["status"] = "reused"
    state["checks"] = len(result.get("checks", [])) if result is not None else 0
    save(state_path, state)
    return state


def require_validated(work, expected_paths):
    """Packaging cannot silently call a skipped or stale test 'passed'."""
    work = Path(work)
    state = read(work / "air-validation.json")
    inputs = fingerprints(expected_paths)
    result = matching_result(work, inputs)
    if state.get("status") not in ("passed", "reused") or state.get("inputs") != inputs or result is None:
        raise ValueError("No matching AIR validation receipt; static build is ready but runtime validation is pending")
    return result
