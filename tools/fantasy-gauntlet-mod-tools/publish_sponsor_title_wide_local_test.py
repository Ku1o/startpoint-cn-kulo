"""Shared JSON/file helpers from the retired wide-title test publisher.

The old isolated test-chain and retired runtime-mirror publication recipe has
been removed. Current title art is already part of the active resource chain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

def sha(raw):return hashlib.sha256(raw).hexdigest()

def readj(path):return json.loads(path.read_text('utf8'))

def save(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    assert path.read_bytes()==raw

def jsonbytes(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def savej(path,value):save(path,jsonbytes(value))


def main(work=None, apply=False):
    raise SystemExit("This historical publisher is retired. Use the current resource-chain tooling; no files were written.")


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    main(args.work, args.apply)


if __name__ == "__main__":
    cli()
