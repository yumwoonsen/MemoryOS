"""Focused v2.1 tests for evidence-driven mission affordances and AI abstention."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from backend.models.v2_schemas import (
    CompactInterpretationDecisionV2,
    InterpretationAbstentionReasonV2,
    InterpretationDecisionKindV2,
    MissionFamilyV2,
    MissionSelectionReasonCodeV2,
    RawTelemetryBatchV2,
)
from backend.services.v2_interpreter import MemoryInterpreterV2
from backend.services.v2_preparation import TelemetryPreparerV2
from backend.services.v2_proposal_expander import (
    CompactProposalExpanderV2,
    CompactProposalExpansionError,
)
from backend.services.v2_validator import ProposalValidatorV2
from backend.v2_pipeline import MemoryInterpretationPipelineV2

DATA_PATH = Path(__file__).resolve().parents[1] / "backend" / "data" / "raw_telemetry_v2.json"


def raw_payload() -> dict[str, object]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def parsed(payload: dict[str, object] | None = None) -> RawTelemetryBatchV2:
    return RawTelemetryBatchV2.model_validate(payload or raw_payload())


def without_revive(payload: dict[str, object]) -> dict[str, object]:
    copied = deepcopy(payload)
    copied["matches"][0]["events"] = [
        event
        for event in copied["matches"][0]["events"]
        if event["provider_event_type"] != "TEAMMATE_REVIVED"
    ]
    copied["media_references"] = []
    return copied


def near_miss_payload() -> dict[str, object]:
    payload = without_revive(raw_payload())
    first = payload["matches"][0]
    second = deepcopy(first)
    second["match_id"] = "ff-match-near-miss-02"
    second["started_at"] = "2026-07-18T12:14:03Z"
    second["ended_at"] = "2026-07-18T12:34:52Z"
    second["placement"] = 4
    for event in second["events"]:
        event["event_id"] = f"{event['event_id']}-near-miss-02"
        if event["provider_event_type"] == "MATCH_PLACEMENT_RECORDED":
            event["details"]["placement"] = 4
    payload["matches"].append(second)
    return payload


class DecisionGenerator:
    provider_name = "test-live"
    model_name = "typed-v2.1"

    def __init__(self, decision: CompactInterpretationDecisionV2) -> None:
        self.decision = decision
        self.calls = 0

    @property
    def observability(self) -> dict[str, int]:
        return {"calls": self.calls}

    def generate(self, **_: object) -> CompactInterpretationDecisionV2:
        self.calls += 1
        return self.decision


def test_hero_offers_reunion_and_role_reversal_for_inactive_invitees() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed())

    assert prepared.issues == []
    assert prepared.story_brief is not None
    assert prepared.story_brief.invitation_player_ids == [
        "ff-player-lee",
        "ff-player-mei",
        "ff-player-amir",
        "ff-player-7f3c",
    ]
    assert prepared.story_brief.active_player_ids == ["ff-player-lee", "ff-player-mei"]
    assert {item.family for item in prepared.mission_affordances} == {
        MissionFamilyV2.REUNION,
        MissionFamilyV2.ROLE_REVERSAL,
    }
    role_reversal = next(
        item
        for item in prepared.mission_affordances
        if item.family == MissionFamilyV2.ROLE_REVERSAL
    )
    rules = {
        item.verification.metric: item.verification.target
        for item in prepared.mission_candidates
        if item.candidate_id in role_reversal.objective_candidate_ids
    }
    assert rules["match.first_squad_revive_actor_id"] == "ff-player-lee"
    assert rules["squad.participant_ids"] == prepared.story_brief.invitation_player_ids


def test_removing_revive_removes_role_reversal_but_keeps_reunion() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed(without_revive(raw_payload())))

    assert prepared.issues == []
    assert {item.family for item in prepared.mission_affordances} == {MissionFamilyV2.REUNION}


def test_repeated_near_misses_offer_and_compile_redemption() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed(near_miss_payload()))

    assert prepared.issues == []
    assert MissionFamilyV2.ROLE_REVERSAL not in {
        item.family for item in prepared.mission_affordances
    }
    redemption = [
        item for item in prepared.mission_affordances if item.family == MissionFamilyV2.REDEMPTION
    ]
    assert len(redemption) == 2
    for affordance in redemption:
        rules = {
            item.verification.metric: item.verification.target
            for item in prepared.mission_candidates
            if item.candidate_id in affordance.objective_candidate_ids
        }
        assert rules["match.top_three_reached"] is True
        assert rules["squad.matches_completed"] == 1

    proposal = MemoryInterpreterV2().propose(prepared)
    assert proposal.mission.family == MissionFamilyV2.REDEMPTION
    assert ProposalValidatorV2().validate(prepared, proposal).passed is True


def test_target_must_be_invitation_eligible() -> None:
    payload = raw_payload()
    payload["squad"]["players"][0]["consent"]["mission_invitation"] = False

    prepared = TelemetryPreparerV2().prepare(parsed(payload))

    assert prepared.mission_affordances == []
    assert "no_feasible_mission" in {item.code for item in prepared.issues}


def test_story_brief_caps_windows_at_four_without_narrative_labels() -> None:
    payload = without_revive(raw_payload())
    source = payload["matches"][0]
    payload["matches"] = []
    for index in range(5):
        match = deepcopy(source)
        match["match_id"] = f"ff-match-window-{index}"
        match["started_at"] = f"2026-07-{10 + index:02d}T12:14:03Z"
        match["ended_at"] = f"2026-07-{10 + index:02d}T12:34:52Z"
        for event in match["events"]:
            event["event_id"] = f"{event['event_id']}-window-{index}"
        payload["matches"].append(match)

    prepared = TelemetryPreparerV2().prepare(parsed(payload))

    assert prepared.story_brief is not None
    assert len(prepared.story_brief.eligible_event_windows) == 4
    serialized = prepared.story_brief.model_dump_json().casefold()
    assert not any(word in serialized for word in ("heroic", "funny", "meaningful", "clutch"))


def test_ai_abstention_returns_not_generated_without_artifacts() -> None:
    decision = CompactInterpretationDecisionV2(
        decision=InterpretationDecisionKindV2.ABSTAIN,
        abstention_reason_code=InterpretationAbstentionReasonV2.NO_MEANINGFUL_EPISODE,
        proposal=None,
    )

    result = MemoryInterpretationPipelineV2(DecisionGenerator(decision)).interpret_delivery(
        parsed()
    )

    assert result.schema_version == "2.1"
    assert result.status == "not_generated"
    assert result.reason_codes == ["ai_no_meaningful_episode"]
    assert result.validation.passed is True
    assert result.memory is None
    assert result.next_chapter is None
    assert result.grounded_claims == []
    assert result.metadata["content_origin"] == "no_player_content"
    assert result.studio_trace.stages[1].status == "complete"


def test_live_generation_has_truthful_content_origin_and_selection_trace() -> None:
    batch = parsed()
    prepared = TelemetryPreparerV2().prepare(batch)
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    decision = CompactInterpretationDecisionV2(
        decision=InterpretationDecisionKindV2.GENERATE,
        abstention_reason_code=None,
        proposal=compact,
    )

    result = MemoryInterpretationPipelineV2(DecisionGenerator(decision)).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.metadata["content_origin"] == "live_ai_validated"
    assert result.metadata["narrative_fallback"] is False
    assert result.next_chapter.family == MissionFamilyV2.ROLE_REVERSAL
    assert result.studio_trace.mission_selection is not None
    assert result.studio_trace.mission_selection.selected_affordance_id == (
        result.next_chapter.objectives[0].objective_id.replace(
            "objective:role_reversal:participants",
            "affordance:role_reversal",
        )
    )


def test_expander_rejects_invented_ranking_reason_and_objective_set() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)

    bad_ranking = compact.model_copy(
        update={
            "mission": compact.mission.model_copy(
                update={"ranked_affordance_ids": ["affordance:invented"]}
            )
        }
    )
    with pytest.raises(CompactProposalExpansionError) as ranking_error:
        CompactProposalExpanderV2().expand(prepared, bad_ranking)
    assert ranking_error.value.code == "mission_affordance_ranking_invalid"

    bad_reason = compact.model_copy(
        update={
            "mission": compact.mission.model_copy(
                update={"selection_reason_codes": [MissionSelectionReasonCodeV2.REPEATED_NEAR_MISS]}
            )
        }
    )
    with pytest.raises(CompactProposalExpansionError) as reason_error:
        CompactProposalExpanderV2().expand(prepared, bad_reason)
    assert reason_error.value.code == "mission_selection_reason_invalid"

    missing_objective = compact.model_copy(
        update={
            "mission": compact.mission.model_copy(
                update={"objective_descriptions": compact.mission.objective_descriptions[:-1]}
            )
        }
    )
    with pytest.raises(CompactProposalExpansionError) as objective_error:
        CompactProposalExpanderV2().expand(prepared, missing_objective)
    assert objective_error.value.code == "mission_objective_set_mismatch"


def test_v2_0_and_v2_1_inputs_both_return_v2_1() -> None:
    for input_version in ("2.0", "2.1"):
        payload = raw_payload()
        payload["schema_version"] = input_version
        result = MemoryInterpretationPipelineV2().interpret_delivery(parsed(payload))
        assert result.schema_version == "2.1"
