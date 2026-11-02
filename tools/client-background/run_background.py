"""Run a complete local build command on a private, inactive Windows desktop."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

import quiet_process


def emit(stdout, stderr):
    if stdout:
        sys.stdout.buffer.write(stdout)
        sys.stdout.buffer.flush()
    if stderr:
        sys.stderr.buffer.write(stderr)
        sys.stderr.buffer.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, help="Whole-command timeout in seconds")
    parser.add_argument("--cwd", type=Path, help="Working directory; defaults to the caller's directory")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    try:
        result = quiet_process.run_gui(command, cwd=args.cwd, timeout=args.timeout, capture_output=True)
    except subprocess.TimeoutExpired as error:
        emit(error.output, error.stderr)
        print("run_background: command timed out", file=sys.stderr, flush=True)
        return 124
    except KeyboardInterrupt:
        print("run_background: interrupted", file=sys.stderr, flush=True)
        return 130
    emit(result.stdout, result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
