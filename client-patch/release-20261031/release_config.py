"""Repository-relative source locations and explicit private build inputs.

No machine path or binary payload is a source dependency. Set SP_CLIENT_INPUTS
to an untracked JSON file. Relative input paths are relative to that file;
generated outputs must stay in its external work_dir.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_CONFIG = None
_CONFIG_FILE = None


def source_path(relative=""):
    root = Path(__file__).resolve().parent
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError("Source path leaves the release source directory")
    return result


def repo_path(relative=""):
    root = source_path().parents[1]
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError("Repository path leaves the checkout")
    return result


def configuration():
    global _CONFIG, _CONFIG_FILE
    if _CONFIG is None:
        value = os.environ.get("SP_CLIENT_INPUTS")
        if not value:
            raise ValueError("Set SP_CLIENT_INPUTS to the private input JSON file")
        path = Path(value).resolve()
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError("Private input JSON is missing or exceeds1MiB")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("Private input JSON must be an object")
        _CONFIG, _CONFIG_FILE = data, path
    return _CONFIG


def input_value(key):
    value = configuration()
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError("Missing private input role: " + key)
        value = value[part]
    return value


def input_path(key, *, required=True):
    value = input_value(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Private input role must be a path: " + key)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = _CONFIG_FILE.parent / path
    path = path.resolve()
    if required and not path.exists():
        raise ValueError("Private input path is missing: " + key)
    return path


def work_path(relative=""):
    root = input_path("work_dir", required=False)
    if root.is_relative_to(repo_path()):
        raise ValueError("work_dir must be outside the source checkout")
    child = Path(relative)
    if child.is_absolute():
        raise ValueError("Output name must be relative to work_dir")
    result = (root / child).resolve()
    if not result.is_relative_to(root):
        raise ValueError("Output path leaves work_dir")
    if result.is_relative_to(repo_path()):
        raise ValueError("Output path enters the source checkout")
    return result


def require_sha(path, expected):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("Pinned input SHA-256 differs")
    return Path(path)
