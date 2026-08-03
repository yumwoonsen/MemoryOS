"""Golden-path and safety tests for the Phase 1 pipeline."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.agents.validator_agent import ValidatorAgent
from backend.models.schemas import EvidenceRef, MemoryPack, PipelineStatus
from backend.pipeline import MemoryPipeline

DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


def load_pack(filename: str) -> MemoryPack:
    payload = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
    return MemoryPack.model_validate(payload)


def test_confirmed_funny_memory_completes_the_pipeline() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert result.memory is not None
    assert result.memory.title == "Worst Plan, Best Night"
    assert result.next_chapter is not None
    assert result.validation.passed is True
    assert result.validation.human_review_required is False
    assert {item.player_id for item in result.player_perspectives} == {
        "lee",
        "mei",
        "jo",
        "amir",
    }
    assert len({item.message for item in result.player_perspectives}) == 4


def test_all_generated_references_are_grounded_in_input_events() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    input_event_ids = {event.event_id for event in pack.match_events}
    generated_event_ids = {item.event_id for item in result.memory.evidence}
    generated_event_ids.update(
        event_id
        for perspective in result.player_perspectives
        for event_id in perspective.evidence_event_ids
    )
    generated_event_ids.update(
        event_id
        for objective in result.next_chapter.objectives
        for event_id in objective.source_event_ids
    )

    assert generated_event_ids <= input_event_ids
    assert result.validation.scores.evidence_grounding == 1.0
    assert result.validation.scores.quest_connection > 0


def test_strong_unconfirmed_candidate_requires_human_review() -> None:
    pack = load_pack("comeback_memory.json")
    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.NEEDS_HUMAN_CONFIRMATION
    assert result.memory is not None
    assert result.memory.human_confirmed is False
    assert result.validation.passed is True
    assert result.validation.human_review_required is True
    assert "human_confirmation_required" in {issue.code for issue in result.validation.issues}


def test_weak_memory_abstains_without_generating_content() -> None:
    pack = load_pack("insufficient_memory.json")
    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.REJECTED
    assert result.discovery.eligible is False
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.validation.passed is True
    assert result.validation.issues[0].code == "insufficient_memory_signal"


def test_unknown_players_are_rejected_at_the_input_boundary() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["match_events"][0]["actor_id"] = "not-a-squad-member"

    with pytest.raises(ValidationError, match="unknown squad players"):
        MemoryPack.model_validate(payload)


def test_validator_rejects_invented_evidence() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    invented_memory = result.memory.model_copy(
        update={
            "evidence": [
                EvidenceRef(
                    event_id="evt-invented",
                    event_type="friendship_power",
                    significance="An event that never occurred",
                )
            ]
        }
    )
    report = ValidatorAgent().validate(
        pack,
        invented_memory,
        result.player_perspectives,
        result.next_chapter,
    )

    assert report.passed is False
    assert "ungrounded_memory_evidence" in {issue.code for issue in report.issues}


def test_validator_rejects_unsupported_relationship_claims() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    unsupported_memory = result.memory.model_copy(
        update={"summary": "Mei proved she is Lee's best friend."}
    )
    report = ValidatorAgent().validate(
        pack,
        unsupported_memory,
        result.player_perspectives,
        result.next_chapter,
    )

    assert report.passed is False
    assert "unsupported_relationship_claim" in {issue.code for issue in report.issues}
