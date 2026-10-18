"""Retired historical abyss/sponsor/Laite candidate recipe.

This recipe depended on an unpublished resource-chain preimage and compact
sponsor artwork that have been superseded. Current content remains in the
active resource chain; rebuilding the obsolete candidate is unsupported.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.parse_args(argv)
    parser.error("This historical candidate recipe is retired. Use the current resource-chain tooling; no files were written.")


if __name__ == "__main__":
    main()
