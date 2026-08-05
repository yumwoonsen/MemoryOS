"""Opt-in evaluation harness for deterministic or live MemoryOS generation."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from backend.models.schemas import (
    HistoricalDiscoveryRequest,
    MemoryPack,
    MemoryPackV11,
    PipelineStatusV11,
)
from backend.pipeline import build_pipeline
from backend.services.identity import contains_identity

DATA_DIR = Path(__file__).resolve().parent / "data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the MemoryOS historical pipeline.")
    parser.add_argument(
        "--provider",
        choices=("deterministic", "openai"),
        default="deterministic",
        help="OpenAI is opt-in and may incur API usage.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DATA_DIR / "historical_memory_packs.json",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=DATA_DIR / "historical_eval_labels.json",
    )
    return parser.parse_args()


def evaluate(provider: str, fixture_path: Path, labels_path: Path) -> dict[str, Any]:
    packs = [
        (MemoryPackV11 if item.get("schema_version") == "1.1" else MemoryPack).model_validate(item)
        for item in json.loads(fixture_path.read_text(encoding="utf-8"))
    ]
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    relevant = set(labels["relevant_pack_ids"])
    should_abstain = set(labels["should_abstain_pack_ids"])
    pipeline = build_pipeline(provider)

    started = time.perf_counter()
    discovery = pipeline.discover_history(HistoricalDiscoveryRequest(memory_packs=packs))
    selected_ids = [candidate.pack_id for candidate in discovery.candidates]
    precision_denominator = max(min(3, len(selected_ids)), 1)
    precision_at_three = len(set(selected_ids[:3]) & relevant) / precision_denominator
    packs_by_id = {pack.pack_id: pack for pack in packs}
    deterministically_ineligible = {
        pack_id
        for pack_id in should_abstain
        if pack_id in packs_by_id
        and not pipeline.history_ranker.assess(packs_by_id[pack_id]).eligible
    }
    abstention_correctness = len(deterministically_ineligible) / max(len(should_abstain), 1)

    generated = []
    for pack in packs:
        if pack.pack_id not in selected_ids:
            continue
        result = pipeline.generate(pack)
        if result.status in {
            PipelineStatusV11.NEEDS_SOURCE_VERIFICATION,
            PipelineStatusV11.NEEDS_MEANING_CONFIRMATION,
        }:
            continue
        generated.append((pack, result))

    reference_total = 0
    valid_reference_total = 0
    expected_perspectives = 0
    actual_perspectives = 0
    distinct_perspective_sets = 0
    consent_leaks = 0
    valid_quests = 0
    for pack, result in generated:
        input_ids = {event.event_id for event in pack.match_events}
        output_ids: list[str] = []
        if result.memory:
            output_ids.extend(item.event_id for item in result.memory.evidence)
        output_ids.extend(
            event_id
            for perspective in result.player_perspectives
            for event_id in perspective.evidence_event_ids
        )
        if result.next_chapter:
            output_ids.extend(
                event_id
                for objective in result.next_chapter.objectives
                for event_id in objective.source_event_ids
            )
        reference_total += len(output_ids)
        valid_reference_total += sum(event_id in input_ids for event_id in output_ids)

        expected = sum(member.opted_in for member in pack.squad.members)
        expected_perspectives += expected
        actual_perspectives += len(result.player_perspectives)
        messages = {item.message.strip().lower() for item in result.player_perspectives}
        distinct_perspective_sets += int(len(messages) == len(result.player_perspectives))
        serialized = result.model_dump_json()
        consent_leaks += sum(
            int(
                contains_identity(serialized, member.display_name)
                or contains_identity(serialized, member.player_id)
            )
            for member in pack.squad.members
            if not member.opted_in
        )
        valid_quests += int(result.validation.passed and result.next_chapter is not None)

    usage = pipeline.usage_totals
    input_rate = float(os.getenv("OPENAI_INPUT_COST_PER_MILLION", "1.0"))
    output_rate = float(os.getenv("OPENAI_OUTPUT_COST_PER_MILLION", "6.0"))
    estimated_cost = (
        usage["input_tokens"] * input_rate + usage["output_tokens"] * output_rate
    ) / 1_000_000

    return {
        "provider": provider,
        "model": pipeline.model_name,
        "prompt_version": "grounded-v1",
        "pipeline_version": discovery.metadata["pipeline_version"],
        "fixture": str(fixture_path),
        "candidate_precision_at_3": round(precision_at_three, 4),
        "abstention_correctness": round(abstention_correctness, 4),
        "evidence_reference_precision": round(valid_reference_total / max(reference_total, 1), 4),
        "perspective_coverage": round(actual_perspectives / max(expected_perspectives, 1), 4),
        "perspective_distinctness": round(distinct_perspective_sets / max(len(generated), 1), 4),
        "consent_leak_count": consent_leaks,
        "quest_verifiability": round(valid_quests / max(len(generated), 1), 4),
        "generated_candidate_count": len(generated),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "token_usage": usage,
        "estimated_cost_usd": round(estimated_cost, 6),
        "pricing_assumption_per_million_tokens": {
            "input": input_rate,
            "output": output_rate,
        },
    }


def main() -> int:
    args = parse_args()
    report = evaluate(args.provider, args.fixture, args.labels)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
