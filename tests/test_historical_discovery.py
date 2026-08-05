"""Phase 2 historical ranking, trust, privacy, and generation tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from backend.agents.validator_agent import ValidatorAgent
from backend.models.schemas import (
    EvidenceRef,
    GenerateMemoryRequest,
    HistoricalDiscoveryRequest,
    MeaningStatus,
    MemoryPack,
    MemoryPackV11,
    PerspectiveSet,
    PipelineStatus,
    PipelineStatusV11,
    SourceStatus,
)
from backend.pipeline import MemoryPipeline
from backend.services.evidence import sanitize_memory_pack
from backend.services.identity import contains_identity

DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


def load_history() -> list[MemoryPack]:
    payload = json.loads((DATA_DIR / "historical_memory_packs.json").read_text(encoding="utf-8"))
    return [MemoryPackV11.model_validate(item) for item in payload]


class CountingGenerator:
    provider_name = "test"
    model_name = "must-not-run"

    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self,
        *,
        prompt_name: str,
        payload: dict[str, Any],
        response_model: type[BaseModel],
        stage: str,
    ) -> BaseModel:
        self.calls += 1
        raise AssertionError(f"provider was called during {stage}")


class GenerationStopped(RuntimeError):
    pass


class CapturingGenerator:
    provider_name = "capture"
    model_name = "capture-only"

    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def generate(
        self,
        *,
        prompt_name: str,
        payload: dict[str, Any],
        response_model: type[BaseModel],
        stage: str,
    ) -> BaseModel:
        self.payload = payload
        raise GenerationStopped


class SequenceGenerator:
    provider_name = "test"
    model_name = "typed-sequence"

    def __init__(self, responses: list[BaseModel]) -> None:
        self.responses = list(responses)
        self.stages: list[str] = []

    def generate(
        self,
        *,
        prompt_name: str,
        payload: dict[str, Any],
        response_model: type[BaseModel],
        stage: str,
    ) -> BaseModel:
        self.stages.append(stage)
        response = self.responses.pop(0)
        assert isinstance(response, response_model)
        return response


def test_history_ranking_is_stable_explainable_and_privacy_safe() -> None:
    packs = load_history()
    request = HistoricalDiscoveryRequest(memory_packs=packs)

    first = MemoryPipeline().discover_history(request)
    second = MemoryPipeline().discover_history(request)

    assert first == second
    assert len(first.candidates) == 3
    assert first.candidates[0].pack_id == "history-chaos-001"
    assert first.filters.received == 7
    assert first.filters.below_threshold == 1
    assert first.filters.duplicates_removed == 1
    assert first.filters.disputed == 1
    assert first.filters.dismissed == 1
    assert first.metadata["provider"] == "deterministic"

    for candidate in first.candidates:
        breakdown = candidate.score_breakdown
        eligibility_score = round(
            breakdown.evidence_strength
            + breakdown.human_signals
            + breakdown.squad_specificity
            + breakdown.resurfacing_relevance,
            4,
        )
        assert breakdown.total == eligibility_score
        assert candidate.score == eligibility_score
        assert candidate.ranking_score == round(eligibility_score - breakdown.diversity_penalty, 4)
        assert candidate.reasons

    private = next(
        item for item in first.candidates if item.pack_id == "history-clutch-private-001"
    )
    serialized = private.model_dump_json().lower()
    assert '"jo"' not in serialized
    assert "anonymous_squadmate_1" in serialized
    assert private.redactions


def test_history_filters_before_deduplicating() -> None:
    base = load_history()[0]
    duplicate_payload = base.model_dump(mode="json")
    duplicate_payload["pack_id"] = "history-chaos-duplicate"
    duplicate_payload["reactions"] = {"laugh_count": 0, "fire_count": 0, "saved": False}
    duplicate = MemoryPackV11.model_validate(duplicate_payload)

    disputed_payload = base.model_dump(mode="json")
    disputed_payload["pack_id"] = "history-chaos-disputed"
    disputed_payload["human_review"]["source_status"] = "disputed"
    disputed = MemoryPackV11.model_validate(disputed_payload)

    response = MemoryPipeline().discover_history(
        HistoricalDiscoveryRequest(memory_packs=[disputed, duplicate, base], limit=3)
    )

    assert response.filters.disputed == 1
    assert response.filters.duplicates_removed == 1
    assert [item.pack_id for item in response.candidates] == [base.pack_id]


def test_history_hard_filters_are_counted_separately() -> None:
    base = load_history()[1]
    payloads = []
    for suffix in ("disputed", "dismissed", "no-events"):
        payload = base.model_dump(mode="json")
        payload["pack_id"] = f"history-{suffix}"
        payload["match"]["match_id"] = f"H-MATCH-{suffix.upper()}"
        payloads.append(payload)
    payloads[0]["human_review"]["source_status"] = "disputed"
    payloads[1]["human_review"]["meaning_status"] = "dismissed"
    payloads[2]["match_events"] = []

    response = MemoryPipeline().discover_history(
        HistoricalDiscoveryRequest(
            memory_packs=[MemoryPackV11.model_validate(payload) for payload in payloads]
        )
    )

    assert response.candidates == []
    assert response.filters.disputed == 1
    assert response.filters.dismissed == 1
    assert response.filters.no_grounded_events == 1


def test_history_filters_a_consistently_opted_out_target() -> None:
    payload = load_history()[1].model_dump(mode="json")
    payload["pack_id"] = "history-target-out"
    payload["match"]["match_id"] = "H-MATCH-TARGET-OUT"
    payload["squad"]["members"][0]["opted_in"] = False

    response = MemoryPipeline().discover_history(
        HistoricalDiscoveryRequest(memory_packs=[MemoryPackV11.model_validate(payload)])
    )

    assert response.candidates == []
    assert response.filters.target_opted_out == 1


def test_diversity_penalty_promotes_a_different_memory_type() -> None:
    chaos, comeback, repeated_chaos = load_history()[:3]
    payload = repeated_chaos.model_dump(mode="json")
    payload["reactions"] = {"laugh_count": 0, "fire_count": 0, "saved": False}
    repeated_chaos = MemoryPackV11.model_validate(payload)

    response = MemoryPipeline().discover_history(
        HistoricalDiscoveryRequest(memory_packs=[chaos, repeated_chaos, comeback])
    )

    assert [candidate.memory_type.value for candidate in response.candidates[:2]] == [
        "chaos",
        "comeback",
    ]
    assert response.candidates[2].score_breakdown.diversity_penalty == 0.08


def test_ranking_ties_use_recency_then_pack_id_independent_of_input_order() -> None:
    base = load_history()[1].model_dump(mode="json")
    packs = []
    for pack_id, match_id, played_at in (
        ("tie-b", "TIE-MATCH-B", "2026-05-01T12:00:00+00:00"),
        ("tie-newest", "TIE-MATCH-NEWEST", "2026-06-01T12:00:00+00:00"),
        ("tie-a", "TIE-MATCH-A", "2026-05-01T12:00:00"),
    ):
        payload = {**base, "pack_id": pack_id}
        payload["match"] = {
            **base["match"],
            "match_id": match_id,
            "played_at": played_at,
        }
        packs.append(MemoryPackV11.model_validate(payload))

    response = MemoryPipeline().discover_history(
        HistoricalDiscoveryRequest(memory_packs=packs, limit=3)
    )
    reversed_response = MemoryPipeline().discover_history(
        HistoricalDiscoveryRequest(memory_packs=list(reversed(packs)), limit=3)
    )

    expected_order = [
        "tie-newest",
        "tie-a",
        "tie-b",
    ]
    assert [candidate.pack_id for candidate in response.candidates] == expected_order
    assert [candidate.pack_id for candidate in reversed_response.candidates] == expected_order


def test_historical_ranking_never_calls_a_configured_generator() -> None:
    generator = CountingGenerator()

    response = MemoryPipeline(generator).discover_history(
        HistoricalDiscoveryRequest(memory_packs=load_history())
    )

    assert response.candidates
    assert response.metadata["provider"] == "deterministic"
    assert generator.calls == 0


def test_history_rejects_mixed_squads_and_duplicate_pack_ids() -> None:
    first, second = load_history()[:2]
    other_payload = second.model_dump(mode="json")
    other_payload["squad"]["squad_id"] = "another-squad"
    other = MemoryPackV11.model_validate(other_payload)

    with pytest.raises(ValidationError, match="same squad"):
        HistoricalDiscoveryRequest(memory_packs=[first, other])
    with pytest.raises(ValidationError, match="unique pack_id"):
        HistoricalDiscoveryRequest(memory_packs=[first, first])


def test_v11_requires_split_review_and_explicit_consent() -> None:
    payload = load_history()[0].model_dump(mode="json")
    payload.pop("human_review")
    with pytest.raises(ValidationError, match="human_review|Field required"):
        MemoryPackV11.model_validate(payload)

    payload = load_history()[0].model_dump(mode="json")
    payload["squad"]["members"][0].pop("opted_in")
    with pytest.raises(ValidationError, match="opted_in|Field required"):
        MemoryPackV11.model_validate(payload)


def test_new_endpoints_require_explicit_consent_on_legacy_packs() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    for member in payload["squad"]["members"]:
        member.pop("opted_in")
    legacy_pack = MemoryPack.model_validate(payload)

    with pytest.raises(ValidationError, match="legacy packs require explicit opted_in"):
        HistoricalDiscoveryRequest(memory_packs=[legacy_pack])

    with pytest.raises(ValidationError, match="legacy packs require explicit opted_in"):
        GenerateMemoryRequest(memory_pack=legacy_pack)


def test_consent_snapshot_must_be_consistent_across_history() -> None:
    first, second = load_history()[:2]
    payload = second.model_dump(mode="json")
    payload["squad"]["members"][0]["opted_in"] = False
    changed_consent = MemoryPackV11.model_validate(payload)

    with pytest.raises(ValidationError, match="current consent snapshot"):
        HistoricalDiscoveryRequest(memory_packs=[first, changed_consent])


def test_opted_out_identity_cannot_be_embedded_in_opaque_ids() -> None:
    payload = load_history()[2].model_dump(mode="json")
    payload["match"]["match_id"] = "match-jo-private"

    with pytest.raises(ValidationError, match="opaque identifiers"):
        MemoryPackV11.model_validate(payload)


def test_opaque_id_checks_normalized_display_name_separators() -> None:
    payload = load_history()[2].model_dump(mode="json")
    for member in payload["squad"]["members"]:
        if member["player_id"] == "jo":
            member["player_id"] = "private-driver"
            member["display_name"] = "Jo Lee"
    for event in payload["match_events"]:
        if event.get("actor_id") == "jo":
            event["actor_id"] = "private-driver"
        if event.get("target_id") == "jo":
            event["target_id"] = "private-driver"
    payload["current_context"]["active_member_ids"] = [
        "private-driver" if player_id == "jo" else player_id
        for player_id in payload["current_context"]["active_member_ids"]
    ]
    payload["match"]["match_id"] = "match-jo-lee-private"

    with pytest.raises(ValidationError, match="opaque identifiers"):
        MemoryPackV11.model_validate(payload)


def test_redaction_expansion_stays_within_output_contracts() -> None:
    payload = load_history()[2].model_dump(mode="json")
    payload["human_memory"]["caption"] = "Jo-" * 40
    private = MemoryPackV11.model_validate(payload)

    safe_pack, redactions = sanitize_memory_pack(private)
    result = MemoryPipeline().generate(private)

    assert safe_pack.human_memory is not None
    assert len(safe_pack.human_memory.caption or "") <= 120
    assert not re.search(r"(?<!\w)jo(?!\w)", safe_pack.model_dump_json(), re.IGNORECASE)
    assert redactions
    assert result.status == PipelineStatusV11.READY


def test_trusted_numeric_event_details_reject_non_numeric_values() -> None:
    payload = load_history()[0].model_dump(mode="json")
    escape = next(event for event in payload["match_events"] if event["type"] == "vehicle_escape")
    escape["details"]["passengers"] = "many"

    with pytest.raises(ValidationError, match="non-negative integer"):
        MemoryPackV11.model_validate(payload)


def test_roster_rejects_cross_member_identity_collisions() -> None:
    payload = load_history()[2].model_dump(mode="json")
    mei = next(member for member in payload["squad"]["members"] if member["player_id"] == "mei")
    mei["display_name"] = "Jo"

    with pytest.raises(ValidationError, match="must not collide"):
        MemoryPackV11.model_validate(payload)


def test_incomplete_review_states_never_call_the_model() -> None:
    unreviewed = load_history()[1]
    generator = CountingGenerator()

    result = MemoryPipeline(generator).generate(unreviewed)

    assert result.status == PipelineStatusV11.NEEDS_SOURCE_VERIFICATION
    assert result.memory is None
    assert generator.calls == 0

    payload = unreviewed.model_dump(mode="json")
    payload["human_review"] = {
        "source_status": SourceStatus.VERIFIED,
        "meaning_status": MeaningStatus.UNREVIEWED,
    }
    meaning_pending = MemoryPackV11.model_validate(payload)
    result = MemoryPipeline(generator).generate(meaning_pending)
    assert result.status == PipelineStatusV11.NEEDS_MEANING_CONFIRMATION
    assert generator.calls == 0


def test_selected_generation_redacts_opted_out_identity_and_assignments() -> None:
    private = load_history()[2]

    result = MemoryPipeline().generate(private)

    assert result.status == PipelineStatusV11.READY
    assert result.memory is not None
    assert result.next_chapter is not None
    output = result.model_dump_json().lower()
    assert '"jo"' not in output
    assert "jo drove" not in output
    assert {item.player_id for item in result.player_perspectives} == {"lee", "mei"}
    assert all(
        objective.assigned_player_id != "anonymous_squadmate_1"
        for objective in result.next_chapter.objectives
    )
    assert result.validation.passed is True


def test_normalized_opted_out_identity_cannot_reappear_in_generated_output() -> None:
    payload = load_history()[2].model_dump(mode="json")
    for member in payload["squad"]["members"]:
        if member["player_id"] == "jo":
            member["player_id"] = "private_user"
            member["display_name"] = "Hidden"
    for event in payload["match_events"]:
        if event.get("actor_id") == "jo":
            event["actor_id"] = "private_user"
        if event.get("target_id") == "jo":
            event["target_id"] = "private_user"
    payload["current_context"]["active_member_ids"] = [
        "private_user" if player_id == "jo" else player_id
        for player_id in payload["current_context"]["active_member_ids"]
    ]
    if payload.get("human_memory", {}).get("author_player_id") == "jo":
        payload["human_memory"]["author_player_id"] = "private_user"
    private = MemoryPackV11.model_validate(payload)

    baseline = MemoryPipeline().generate(private)
    assert baseline.memory is not None
    leaking_memory = baseline.memory.model_copy(update={"title": "private user"})

    result = MemoryPipeline(SequenceGenerator([leaking_memory])).generate(private)

    assert result.status == PipelineStatusV11.REJECTED
    assert result.memory is None
    assert "opted_out_identity_leak" in {issue.code for issue in result.validation.issues}
    serialized = result.model_dump_json()
    assert not contains_identity(serialized, "private_user")
    assert not contains_identity(serialized, "Hidden")


def test_opted_out_identity_is_removed_before_the_first_model_call() -> None:
    payload = load_history()[2].model_dump(mode="json")
    payload["match_events"][1]["details"]["driver_note"] = "Jo chose the route"
    private = MemoryPackV11.model_validate(payload)
    generator = CapturingGenerator()

    with pytest.raises(GenerationStopped):
        MemoryPipeline(generator).generate(private)

    assert generator.payload is not None
    serialized = json.dumps(generator.payload)
    assert not re.search(r"(?<![\w])jo(?![\w])", serialized, re.IGNORECASE)
    assert "anonymous_squadmate_1" in serialized


def test_invalid_memory_stage_stops_before_perspective_generation() -> None:
    pack = load_history()[0]
    baseline = MemoryPipeline().generate(pack)
    assert baseline.memory is not None
    bad_memory = baseline.memory.model_copy(
        update={"summary": "Zara deliberately betrayed the squad."}
    )
    generator = SequenceGenerator([bad_memory])

    result = MemoryPipeline(generator).generate(pack)

    assert result.status == PipelineStatusV11.REJECTED
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.metadata["stopped_stage"] == "memory_discovery"
    assert generator.stages == ["memory_discovery"]


def test_invalid_perspective_stage_stops_before_quest_generation() -> None:
    pack = load_history()[0]
    baseline = MemoryPipeline().generate(pack)
    assert baseline.memory is not None
    perspectives = list(baseline.player_perspectives)
    perspectives[0] = perspectives[0].model_copy(
        update={"message": "Zara knew Lee was terrified at Imaginary Harbor."}
    )
    generator = SequenceGenerator([baseline.memory, PerspectiveSet(perspectives=perspectives)])

    result = MemoryPipeline(generator).generate(pack)

    assert result.status == PipelineStatusV11.REJECTED
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.metadata["stopped_stage"] == "perspectives"
    assert generator.stages == ["memory_discovery", "perspectives"]


def test_opted_out_identity_in_structured_quest_fields_is_never_returned() -> None:
    pack = load_history()[2]
    baseline = MemoryPipeline().generate(pack)
    assert baseline.memory is not None
    assert baseline.next_chapter is not None
    bad_quest = baseline.next_chapter.model_copy(deep=True)
    objective = bad_quest.objectives[0]
    bad_quest.objectives[0] = objective.model_copy(
        update={
            "objective_id": "jo-secret-objective",
            "verification": objective.verification.model_copy(update={"target": ["jo"]}),
        }
    )
    generator = SequenceGenerator(
        [
            baseline.memory,
            PerspectiveSet(perspectives=baseline.player_perspectives),
            bad_quest,
        ]
    )

    result = MemoryPipeline(generator).generate(pack)

    assert result.status == PipelineStatusV11.REJECTED
    assert result.next_chapter is None
    assert "opted_out_identity_leak" in {issue.code for issue in result.validation.issues}
    assert not re.search(r"(?<!\w)jo(?!\w)", result.model_dump_json(), re.IGNORECASE)


def test_legacy_confirmation_normalizes_without_breaking_v1_endpoint_behavior() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    pack = MemoryPack.model_validate(payload)

    legacy = MemoryPipeline().run(pack)
    modern = MemoryPipeline().generate(pack)

    assert legacy.schema_version == "1.0"
    assert legacy.status == PipelineStatus.READY
    assert modern.schema_version == "1.1"
    assert modern.source_status == SourceStatus.VERIFIED
    assert modern.meaning_status == MeaningStatus.CONFIRMED
    assert modern.metadata["compatibility_conversion"]


def test_validator_rejects_duplicate_players_bad_event_types_and_bad_assignees() -> None:
    pack = load_history()[0]
    result = MemoryPipeline().generate(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    bad_memory = result.memory.model_copy(
        update={
            "evidence": [
                EvidenceRef(
                    event_id=result.memory.evidence[0].event_id,
                    event_type="invented_event_type",
                    significance=result.memory.evidence[0].significance,
                )
            ]
        }
    )
    duplicate = result.player_perspectives[0].model_copy()
    bad_quest = result.next_chapter.model_copy(deep=True)
    bad_quest.objectives[0].assigned_player_id = "unknown-player"

    report = ValidatorAgent().validate(
        pack,
        bad_memory,
        [*result.player_perspectives, duplicate],
        bad_quest,
    )
    codes = {issue.code for issue in report.issues}
    assert report.passed is False
    assert "memory_event_type_mismatch" in codes
    assert "duplicate_player_perspective" in codes
    assert "invalid_quest_assignee" in codes


def test_validator_rejects_unsupported_location_and_numeric_claims() -> None:
    pack = load_history()[0]
    result = MemoryPipeline().generate(pack)
    assert result.memory is not None
    assert result.next_chapter is not None
    fabricated = result.memory.model_copy(
        update={"summary": "At Imaginary Harbor, Lee completed 99 revives."}
    )

    report = ValidatorAgent().validate(
        pack,
        fabricated,
        result.player_perspectives,
        result.next_chapter,
    )
    codes = {issue.code for issue in report.issues}
    assert "unsupported_location_claim" in codes
    assert "unsupported_numeric_claim" in codes
