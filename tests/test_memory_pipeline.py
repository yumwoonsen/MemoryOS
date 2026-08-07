"""Golden-path and safety tests for the Phase 1 pipeline."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.agents.validator_agent import ValidatorAgent
from backend.models.schemas import EvidenceRef, MemoryPack, PipelineStatus
from backend.pipeline import MemoryPipeline, build_pipeline

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


def test_human_signals_without_gameplay_evidence_abstain_safely() -> None:
    pack = load_pack("funny_memory.json").model_copy(update={"match_events": []})
    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.REJECTED
    assert result.discovery.eligible is False
    assert result.discovery.reasons == ["no grounded gameplay events were present"]
    assert result.memory is None


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


def test_player_authored_caption_is_attributed_context_not_a_model_claim() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["human_memory"]["caption"] = "Best friend clutch"
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert "unsupported_relationship_claim" not in {
        issue.code for issue in result.validation.issues
    }


def test_squad_memory_requires_two_opted_in_members() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    for member in payload["squad"]["members"][1:]:
        member["opted_in"] = False
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.REJECTED
    assert result.discovery.reasons == ["fewer than two squad members are opted in"]
    assert {issue.code for issue in result.validation.issues} == {"insufficient_opted_in_members"}


@pytest.mark.parametrize(
    "escape_updates",
    [
        {"timestamp_seconds": 1000},
        {"timestamp_seconds": 1300},
        {"location": "Peak"},
        {"location": None},
    ],
)
def test_disconnected_events_do_not_receive_a_connected_pattern_bonus(
    escape_updates: dict[str, str | int | None],
) -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["match_events"][2].update(escape_updates)
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.memory is not None
    assert "connected rescue-and-escape pattern" not in result.discovery.reasons
    assert " before " not in result.memory.summary


def test_connected_summary_uses_the_connected_pair_location() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["match_events"] = [
        {
            "event_id": "evt-revive-alpha",
            "type": "revive",
            "actor_id": "mei",
            "target_id": "lee",
            "timestamp_seconds": 100,
            "location": "Alpha",
            "importance": "high",
            "details": {},
        },
        {
            "event_id": "evt-revive-bravo",
            "type": "revive",
            "actor_id": "jo",
            "target_id": "amir",
            "timestamp_seconds": 200,
            "location": "Bravo",
            "importance": "high",
            "details": {},
        },
        {
            "event_id": "evt-escape-bravo",
            "type": "vehicle_escape",
            "actor_id": "amir",
            "timestamp_seconds": 210,
            "location": "Bravo",
            "importance": "high",
            "details": {"passengers": 3},
        },
    ]
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.memory is not None
    assert result.memory.summary.startswith("At Bravo, Jo revived Amir before Amir drove")


def test_generic_actor_perspectives_remain_distinct() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    for index, (event, member) in enumerate(
        zip(payload["match_events"], payload["squad"]["members"], strict=True), start=1
    ):
        event.update(
            {
                "event_id": f"evt-elimination-{index}",
                "type": "elimination",
                "actor_id": member["player_id"],
                "target_id": None,
                "timestamp_seconds": 100 + index,
                "location": "Clock Tower",
                "importance": "high",
                "details": {},
            }
        )
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert len({perspective.message for perspective in result.player_perspectives}) == 4


def test_provider_name_is_trimmed_and_case_normalized() -> None:
    assert build_pipeline("  DeTeRmInIsTiC  ").provider_name == "deterministic"
    assert build_pipeline("  GrOq  ").provider_name == "groq"
    assert build_pipeline("groq").model_name == "openai/gpt-oss-20b"
