"""Focused regressions for the request-scoped W/A/O provider boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.models.v2_provider_schemas import (
    MissionObjectiveKindV2,
    ProviderInterpretationDecisionV2,
)
from backend.models.v2_schemas import RawTelemetryBatchV2
from backend.services.prompt_loader import load_prompt
from backend.services.v2_interpreter import MemoryInterpreterV2
from backend.services.v2_preparation import TelemetryPreparerV2
from backend.v2_pipeline import MemoryInterpretationPipelineV2

DATA_PATH = Path(__file__).resolve().parents[1] / "backend" / "data" / "raw_telemetry_v2.json"


def parsed_batch() -> RawTelemetryBatchV2:
    return RawTelemetryBatchV2.model_validate_json(DATA_PATH.read_text(encoding="utf-8"))


def raw_payload() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


class ProviderDecisionSequence:
    provider_name = "test-live"
    model_name = "provider-handle-fixture"

    def __init__(self, *decisions: ProviderInterpretationDecisionV2) -> None:
        self.decisions = decisions
        self.calls = 0
        self.requests: list[dict[str, Any]] = []

    @property
    def observability(self) -> dict[str, int]:
        return {"calls": self.calls}

    def generate(self, **kwargs: Any) -> ProviderInterpretationDecisionV2:
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        self.requests.append(kwargs)
        return decision


def mission_update(
    decision: ProviderInterpretationDecisionV2,
    **updates: object,
) -> ProviderInterpretationDecisionV2:
    assert decision.proposal is not None
    mission = decision.proposal.mission.model_copy(update=updates)
    proposal = decision.proposal.model_copy(update={"mission": mission})
    return decision.model_copy(update={"proposal": proposal})


def test_provider_projection_uses_short_relational_w_a_o_references() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())

    story_brief = MemoryInterpreterV2._provider_payload(prepared)["story_brief"]
    windows = story_brief["windows"]
    affordances = story_brief["affordances"]
    window_refs = [item["window_ref"] for item in windows]
    affordance_refs = [item["affordance_ref"] for item in affordances]
    objective_refs = [
        objective["objective_ref"]
        for affordance in affordances
        for objective in affordance["objectives"]
    ]

    assert window_refs == [f"W{index}" for index in range(1, len(windows) + 1)]
    assert affordance_refs == [f"A{index}" for index in range(1, len(affordances) + 1)]
    assert objective_refs == [f"O{index}" for index in range(1, len(objective_refs) + 1)]
    assert len(objective_refs) == len(set(objective_refs))
    assert {item["window_ref"] for item in affordances}.issubset(window_refs)
    assert all("window_id" not in item for item in windows)
    assert all("affordance_id" not in item for item in affordances)
    assert all(
        {"candidate_id", "verification"}.isdisjoint(objective)
        for affordance in affordances
        for objective in affordance["objectives"]
    )


def test_active_prompt_asks_ai_to_choose_story_continuity_without_positional_bias() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    affordances = MemoryInterpreterV2._provider_catalog(prepared).brief.affordances
    prompt = load_prompt("memory_interpreter_v2_11.txt")

    # The backend continues to offer the general reunion option first in its neutral catalogue.
    # Mission quality therefore comes from the AI selection rubric, not hidden list ordering.
    assert [item.family.value for item in affordances] == ["reunion", "role_reversal"]
    assert MemoryInterpreterV2.prompt_version == "memory-interpreter-v2.11-backend-mission-copy"
    assert (
        "A# input order, reference number, objective count, and ease of wording "
        "are not preference signals"
    ) in prompt
    assert "source_role_binding + event_actor" in prompt
    assert "repeated source_match_ids + placement_at_most" in prompt
    assert "Treat reunion as the general fallback" in prompt
    assert "Never invent meaning merely to avoid reunion" in prompt
    assert "story_bridge" in prompt
    assert "objective_descriptions" not in prompt
    assert "other source_match_ids are\n  selection context only" in prompt
    assert "at least one event ID from that W#" in prompt
    assert "Perspectives\n  must differ" in prompt
    assert "Keep perspectives category-free" in prompt
    assert (
        "unsupported_categorical_detail: remove every exact categorical or zone value"
        in " ".join(prompt.split())
    )


def test_provider_objectives_expose_complete_backend_owned_required_terms() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    story_brief = MemoryInterpreterV2._provider_catalog(prepared).brief
    objectives = [
        objective for affordance in story_brief.affordances for objective in affordance.objectives
    ]
    participants = next(
        item for item in objectives if item.kind == MissionObjectiveKindV2.REQUIRED_PARTICIPANTS
    )
    completed_match = next(
        item for item in objectives if item.kind == MissionObjectiveKindV2.COMPLETED_MATCHES
    )
    first_reviver = next(
        item for item in objectives if item.kind == MissionObjectiveKindV2.EVENT_ACTOR
    )

    assert participants.required_terms == ["invited squad", "play", "match"]
    assert completed_match.required_terms == ["complete", "at least 1", "match"]
    assert first_reviver.required_terms == ["Lee", "completes", "first", "revive"]
    assert first_reviver.assigned_player_id == "ff-player-lee"
    assert all(
        not term.startswith("ff-player-")
        for objective in objectives
        for term in objective.required_terms
    )


def test_provider_mission_output_contains_selection_and_story_bridge_only() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    assert decision.proposal is not None

    mission_payload = decision.proposal.mission.model_dump(mode="json")

    assert set(mission_payload) == {
        "ranked_affordance_refs",
        "selection_reason_codes",
        "title",
        "story_bridge",
    }
    assert "mission" not in mission_payload
    assert "objective_descriptions" not in mission_payload
    assert mission_payload["ranked_affordance_refs"]
    assert mission_payload["selection_reason_codes"]
    assert mission_payload["story_bridge"]


def test_required_terms_use_a_safe_label_for_an_identity_hidden_future_actor() -> None:
    payload = raw_payload()
    old_player_id = "ff-player-lee"
    private_player_id = "player-one"
    payload["target_player_id"] = private_player_id
    player = payload["squad"]["players"][0]
    player["player_id"] = private_player_id
    player["display_name"] = "SecretAlias"
    player["consent"]["identity_display"] = False
    payload["current_context"]["active_player_ids"] = [
        private_player_id if player_id == old_player_id else player_id
        for player_id in payload["current_context"]["active_player_ids"]
    ]
    payload["social_context"]["caption_author_player_id"] = private_player_id
    payload["media_references"][0]["consented_player_ids"] = [
        private_player_id if player_id == old_player_id else player_id
        for player_id in payload["media_references"][0]["consented_player_ids"]
    ]
    for event in payload["matches"][0]["events"]:
        if event.get("actor_id") == old_player_id:
            event["actor_id"] = private_player_id
        if event.get("target_id") == old_player_id:
            event["target_id"] = private_player_id

    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))
    story_brief = MemoryInterpreterV2._provider_catalog(prepared).brief
    first_reviver = next(
        objective
        for affordance in story_brief.affordances
        for objective in affordance.objectives
        if objective.kind == MissionObjectiveKindV2.EVENT_ACTOR
    )
    serialized = story_brief.model_dump_json()

    assert prepared.issues == []
    assert first_reviver.required_terms == [
        "Player 1",
        "completes",
        "first",
        "revive",
    ]
    assert first_reviver.assigned_player_id == "anonymous:squadmate:1"
    assert "SecretAlias" not in serialized
    assert private_player_id not in serialized


def test_role_reversal_keeps_source_rescuer_and_future_reviver_distinct() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    interpreter = MemoryInterpreterV2()
    story_brief = interpreter._provider_catalog(prepared).brief
    role_reversal = next(
        affordance for affordance in story_brief.affordances if affordance.family == "role_reversal"
    )
    binding = role_reversal.source_role_binding
    decision = interpreter.demo_provider_decision(prepared)
    assert binding is not None
    assert decision.proposal is not None

    assert binding.source_event_id == "ffevt-04-revive-lee"
    assert binding.source_actor_id == "ff-player-mei"
    assert binding.source_target_id == "ff-player-lee"
    assert binding.future_actor_id == "ff-player-lee"
    assert "Mei revived" in decision.proposal.summary.text
    assert "Lee revived" not in decision.proposal.summary.text
    assert "role reversal" in decision.proposal.mission.story_bridge.casefold()
    assert "first revive" not in decision.proposal.mission.story_bridge.casefold()
    assert "first revival" not in decision.proposal.mission.story_bridge.casefold()


def test_provider_handle_decision_round_trips_to_canonical_delivery_controls() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    interpreter = MemoryInterpreterV2()
    decision = interpreter.demo_provider_decision(prepared)
    assert decision.proposal is not None
    selected_ref = decision.proposal.mission.ranked_affordance_refs[0]
    projected_affordances = interpreter._provider_payload(prepared)["story_brief"]["affordances"]
    selected_projection = next(
        item for item in projected_affordances if item["affordance_ref"] == selected_ref
    )
    canonical_affordance = next(
        item
        for item in prepared.mission_affordances
        if item.family.value == selected_projection["family"]
        and item.source_event_ids == selected_projection["source_event_ids"]
        and item.source_match_ids == selected_projection["source_match_ids"]
    )
    generator = ProviderDecisionSequence(decision)

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is False
    assert generator.calls == 1
    assert generator.requests[0]["response_model"] is ProviderInterpretationDecisionV2
    assert generator.requests[0]["prompt_name"] == "memory_interpreter_v2_11.txt"
    assert result.studio_trace.mission_selection is not None
    assert (
        result.studio_trace.mission_selection.selected_affordance_id
        == canonical_affordance.affordance_id
    )
    assert [item.objective_id for item in result.next_chapter.objectives] == (
        canonical_affordance.objective_candidate_ids
    )
    assert result.next_chapter.mission == decision.proposal.mission.story_bridge
    candidate_by_id = {
        candidate.candidate_id: candidate for candidate in prepared.mission_candidates
    }
    descriptions_by_metric = {
        candidate_by_id[item.objective_id].verification.metric: item.description
        for item in result.next_chapter.objectives
    }
    assert descriptions_by_metric == {
        "squad.participant_ids": "Play a match with the invited squad.",
        "squad.matches_completed": "Complete at least 1 match.",
        "match.first_squad_revive_actor_id": "Lee completes the squad's first revive.",
    }


def test_story_bridge_can_paraphrase_role_reversal_without_repeating_mission_rules() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    assert decision.proposal is not None
    paraphrased = mission_update(
        decision,
        title="Return the Favour",
        story_bridge="Mei brought Lee back then. This time, Lee can return the favour.",
    )
    paraphrased = ProviderInterpretationDecisionV2.model_validate(
        paraphrased.model_dump(mode="json")
    )

    result = MemoryInterpretationPipelineV2(
        ProviderDecisionSequence(paraphrased)
    ).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.passed is True
    assert not any(issue.code == "mission_rule_not_expressed" for issue in result.validation.issues)
    assert result.next_chapter is not None
    assert result.next_chapter.mission == paraphrased.proposal.mission.story_bridge
    assert [item.description for item in result.next_chapter.objectives] == [
        "Play a match with the invited squad.",
        "Complete at least 1 match.",
        "Lee completes the squad's first revive.",
    ]


def test_story_bridge_with_unoffered_mechanics_fails_closed_after_one_correction() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    assert decision.proposal is not None
    invalid = mission_update(
        decision,
        story_bridge=("Return the favour by winning the next match without taking any damage."),
    )
    generator = ProviderDecisionSequence(invalid, invalid)

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert "mission_capability_language_mismatch" in result.reason_codes
    assert result.validation.correction_attempted is True
    assert generator.calls == 2
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.grounded_claims == []


@pytest.mark.parametrize(
    ("mission_title", "expected_issue"),
    [
        ("Win Without Taking Damage", "mission_capability_language_mismatch"),
        ("Complete 20 Matches", "mission_target_mismatch"),
        ("Mei Completes the First Revive", "mission_target_mismatch"),
    ],
)
def test_mission_title_cannot_add_unoffered_or_inconsistent_rules(
    mission_title: str,
    expected_issue: str,
) -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    invalid = mission_update(decision, title=mission_title)
    generator = ProviderDecisionSequence(invalid, invalid)

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert expected_issue in result.reason_codes
    assert result.validation.correction_attempted is True
    assert generator.calls == 2
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.grounded_claims == []


def test_mission_framing_can_reference_supported_past_reviver_without_reassigning_rule() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    supported = mission_update(
        decision,
        title="Return the Favour",
        story_bridge="Mei revived Lee last time. Now Lee can return the favour.",
    )

    result = MemoryInterpretationPipelineV2(ProviderDecisionSequence(supported)).interpret_delivery(
        batch
    )

    assert result.status == "pending_player_decision"
    assert result.validation.passed is True
    assert result.validation.issues == []


def test_supported_reunion_choice_remains_valid_when_story_specific_option_is_offered() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    interpreter = MemoryInterpreterV2()
    decision = interpreter.demo_provider_decision(prepared)
    assert decision.proposal is not None
    catalog = interpreter._provider_catalog(prepared)
    reunion = next(
        affordance
        for affordance in catalog.brief.affordances
        if affordance.family.value == "reunion"
    )
    remaining_refs = [
        affordance.affordance_ref
        for affordance in catalog.brief.affordances
        if affordance.affordance_ref != reunion.affordance_ref
    ]
    reunion_decision = mission_update(
        decision,
        ranked_affordance_refs=[reunion.affordance_ref, *remaining_refs],
        selection_reason_codes=[reunion.allowed_reason_codes[0]],
        title="Return Together",
        story_bridge="The squad has been apart long enough. Bring everyone back together.",
    )
    # Revalidate model copies so the fake provider follows the strict output contract.
    reunion_decision = ProviderInterpretationDecisionV2.model_validate(
        reunion_decision.model_dump(mode="json")
    )
    generator = ProviderDecisionSequence(reunion_decision)

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.passed is True
    assert result.next_chapter is not None
    assert result.next_chapter.family.value == "reunion"
    assert result.next_chapter.mission == (
        "The squad has been apart long enough. Bring everyone back together."
    )
    assert [item.description for item in result.next_chapter.objectives] == [
        "Play a match with the invited squad.",
        "Complete at least 1 match.",
    ]
    assert result.studio_trace.mission_selection is not None
    assert result.studio_trace.mission_selection.selected_family.value == "reunion"


def test_provider_references_accept_case_and_surrounding_whitespace() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    assert decision.proposal is not None
    mission = decision.proposal.mission
    normalized_variant = mission_update(
        decision,
        ranked_affordance_refs=[f" {item.lower()} " for item in mission.ranked_affordance_refs],
    )
    generator = ProviderDecisionSequence(normalized_variant)

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is False
    assert generator.calls == 1


def test_duplicate_equivalent_affordance_ranking_references_are_deduplicated() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    assert decision.proposal is not None
    mission = decision.proposal.mission
    duplicate_variant = mission_update(
        decision,
        ranked_affordance_refs=[
            mission.ranked_affordance_refs[0],
            f" {mission.ranked_affordance_refs[0].lower()} ",
            *mission.ranked_affordance_refs[1:],
        ],
    )
    generator = ProviderDecisionSequence(duplicate_variant)

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is False
    assert result.studio_trace.mission_selection is not None
    assert len(result.studio_trace.mission_selection.ranked_affordance_ids) == len(
        prepared.mission_affordances
    )


def test_unknown_selected_a99_fails_closed_after_one_correction() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    assert decision.proposal is not None
    invalid = mission_update(
        decision,
        ranked_affordance_refs=["A99", *decision.proposal.mission.ranked_affordance_refs[1:]],
    )
    generator = ProviderDecisionSequence(invalid, invalid)

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert result.reason_codes == ["invented_mission_affordance"]
    assert result.validation.correction_attempted is True
    assert generator.calls == 2
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.grounded_claims == []


def test_provider_requires_one_perspective_per_eligible_player_and_fails_closed() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    assert decision.proposal is not None
    required_player_ids = {
        player.player_id for player in prepared.story_brief.players_requiring_perspectives
    }
    assert {item.player_id for item in decision.proposal.perspectives} == required_player_ids
    invalid_proposal = decision.proposal.model_copy(
        update={"perspectives": decision.proposal.perspectives[:-1]}
    )
    invalid = decision.model_copy(update={"proposal": invalid_proposal})
    generator = ProviderDecisionSequence(invalid, invalid)

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert result.reason_codes == ["perspective_roster_mismatch"]
    assert result.validation.correction_attempted is True
    assert generator.calls == 2
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.grounded_claims == []


def test_provider_projection_remains_bounded_with_short_references() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    payload = MemoryInterpreterV2._provider_payload(prepared)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    assert len(encoded) <= 96_000
    assert len(encoded) < len(prepared.story_brief.model_dump_json().encode("utf-8"))
