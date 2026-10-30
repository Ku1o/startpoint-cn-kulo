"""Explicit private carriers, repository sources and external build outputs."""
from pathlib import Path
import hashlib
import sys

RECIPE_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = RECIPE_ROOT.parents[1]
sys.path.insert(0, str(RELEASE_ROOT))
from release_config import input_path, repo_path, source_path, work_path

ROOT = work_path('android/capabilities')
REFERENCES = source_path('android/upstream')
CONTRACTS = source_path('android/contracts')
BASE = input_path('android.inputs.r11_swf.path')
BASE_SHA = '9c672e56e5911679848047daece874e139255b2d128f67ab11e605c5db2bb951'
DONOR = input_path('android.inputs.donor_swf.path')
REPOSITORY = repo_path()
sys.dont_write_bytecode = True


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require_hash(path, expected):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError('Explicit input hash differs')


def output_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Output leaves external capabilities work directory')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
