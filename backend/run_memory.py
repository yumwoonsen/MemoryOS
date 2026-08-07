"""Command-line runner for a Memory Pack JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from backend.models.schemas import MemoryPack
from backend.pipeline import build_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Garena Next Chapter MemoryOS Phase 1 pipeline."
    )
    parser.add_argument("memory_pack", type=Path, help="Path to a Memory Pack JSON file")
    parser.add_argument(
        "--provider",
        choices=("deterministic", "openai", "groq"),
        default=None,
        help="Override MEMORYOS_PROVIDER for this run",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(args.memory_pack.read_text(encoding="utf-8"))
        memory_pack = MemoryPack.model_validate(payload)
        result = build_pipeline(args.provider).run(memory_pack)
    except (OSError, json.JSONDecodeError, ValidationError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"MemoryOS could not process the input: {exc}") from exc

    print(result.model_dump_json(indent=2, exclude_none=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
