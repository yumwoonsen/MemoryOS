"""Run the credential-free MemoryOS handoff verification suite."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPOSITORY_ROOT / "frontend"


def run(command: list[str], *, cwd: Path = REPOSITORY_ROOT) -> None:
    print(f"\n> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, env=_deterministic_environment(), check=True)


def _deterministic_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["MEMORYOS_PROVIDER"] = "deterministic"
    return environment


def main() -> int:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        print("npm was not found. Install Node.js 22 before running verification.", file=sys.stderr)
        return 2

    python = sys.executable
    commands = [
        ([python, "-m", "ruff", "check", "."], REPOSITORY_ROOT),
        ([python, "-m", "ruff", "format", "--check", "."], REPOSITORY_ROOT),
        ([python, "-m", "pytest"], REPOSITORY_ROOT),
        ([python, "-m", "pip", "check"], REPOSITORY_ROOT),
        ([python, "-m", "backend.evaluate", "--provider", "deterministic"], REPOSITORY_ROOT),
        ([python, "-m", "backend.evaluate_v2", "--provider", "deterministic"], REPOSITORY_ROOT),
        ([npm, "run", "audit:production"], FRONTEND_ROOT),
        ([npm, "run", "typecheck"], FRONTEND_ROOT),
        ([npm, "run", "lint"], FRONTEND_ROOT),
        ([npm, "test"], FRONTEND_ROOT),
    ]

    try:
        for command, cwd in commands:
            run(command, cwd=cwd)
    except subprocess.CalledProcessError as error:
        return error.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
