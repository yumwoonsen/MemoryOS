"""Acceptance tests for telemetry-first, fail-closed MemoryOS v2."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import backend.main as api
import backend.services.v2_interpreter as v2_interpreter_module
from backend.main import app
from backend.models.schemas import MemoryType
from backend.models.v2_provider_schemas import ProviderInterpretationDecisionV2
from backend.models.v2_schemas import (
    ClaimPredicate,
    CompactMemoryProposalV2,
    GroundedClaim,
    InterpretDeliveryResultV2,
    RawTelemetryBatchV2,
    V2ValidationIssue,
)
from backend.services.openai_client import OpenAIProviderError
from backend.services.v2_delivery_repository import v2_delivery_repository
from backend.services.v2_evaluation import summarize_v2_results
from backend.services.v2_interpreter import MAX_PROVIDER_PAYLOAD_BYTES, MemoryInterpreterV2
from backend.services.v2_preparation import (
    MAX_PROVIDER_EVENTS,
    MAX_WINDOW_EVENTS,
    MAX_WINDOW_SPAN_SECONDS,
    TelemetryPreparerV2,
)
from backend.services.v2_proposal_expander import CompactProposalExpanderV2
from backend.services.v2_validator import ProposalValidatorV2
from backend.v2_pipeline import MemoryInterpretationPipelineV2

DATA_PATH = Path(__file__).resolve().parents[1] / "backend" / "data" / "raw_telemetry_v2.json"
PLAYER_DATA_PATH = (
    Path(__file__).resolve().parents[1] / "frontend" / "data" / "raw_telemetry_v2.json"
)
FAKE_GITHUB_TOKEN = "ghp_" + ("a" * 36)
client = TestClient(app)
REAL_BUILD_CONFIGURED_V2_PIPELINE = api._build_configured_v2_pipeline


def raw_payload() -> dict[str, object]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def parsed_batch() -> RawTelemetryBatchV2:
    return RawTelemetryBatchV2.model_validate(raw_payload())


def player_batch() -> RawTelemetryBatchV2:
    return RawTelemetryBatchV2.model_validate_json(PLAYER_DATA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def reset_v2_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    v2_delivery_repository.clear()
    monkeypatch.setattr(
        api,
        "_build_configured_v2_pipeline",
        lambda: MemoryInterpretationPipelineV2(),
    )


def test_v2_interprets_telemetry_only_fixture_into_validated_delivery() -> None:
    response = client.post("/v2/memories/interpret-delivery", json=raw_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "2.1"
    assert body["status"] == "pending_player_decision"
    assert body["validation"] == {
        "passed": True,
        "correction_attempted": False,
        "issues": [],
    }
    assert body["memory"]["selected_event_ids"]
    assert body["grounded_claims"]
    assert body["next_chapter"]["objectives"][0]["verification"]["metric"]
    assert body["metadata"]["mode"] == "deterministic_demo"
    assert body["metadata"]["narrative_fallback"] is False
    assert body["next_chapter"]["invitation_player_ids"] == [
        "ff-player-lee",
        "ff-player-mei",
        "ff-player-amir",
        "ff-player-7f3c",
    ]
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    assert all(
        event.actor_id != "not-a-player"
        for match in prepared.normalized.matches
        for event in match.events
    )
    assert all(
        event.actor_id is None and event.target_id is None and event.event_scope == "squad"
        for match in prepared.normalized.matches
        for event in match.events
        if event.event_id in {"ffevt-05-vehicle-enter", "ffevt-06-zone-exit"}
    )


def test_v2_contract_rejects_pre_authored_memory_fields() -> None:
    payload = raw_payload()
    payload["summary"] = "A prewritten story that must not enter the v2 contract."

    response = client.post("/v2/memories/interpret-delivery", json=payload)

    assert response.status_code == 422


def test_v2_can_interpret_without_caption_or_tags() -> None:
    payload = raw_payload()
    payload.pop("social_context")

    response = client.post("/v2/memories/interpret-delivery", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "pending_player_decision"


def test_unknown_provider_event_fails_before_interpretation() -> None:
    payload = raw_payload()
    payload["matches"][0]["events"][2]["provider_event_type"] = "SECRET_STORY_EVENT"

    response = client.post("/v2/memories/interpret-delivery", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert "unsupported_provider_event" in body["reason_codes"]
    assert "memory" not in body
    assert body["studio_trace"]["stages"][1]["status"] == "withheld"


def test_invalid_media_consent_fails_closed() -> None:
    payload = raw_payload()
    payload["squad"]["players"][0]["consent"]["media_use"] = False

    response = client.post("/v2/memories/interpret-delivery", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "media_consent_invalid" in response.json()["reason_codes"]


def test_collective_media_requires_consent_from_the_complete_squad() -> None:
    payload = raw_payload()
    payload["media_references"] = [
        {
            "media_id": "collective-keyframe",
            "kind": "keyframe",
            "event_ids": ["ffevt-05-vehicle-enter"],
            "consented_player_ids": [],
        }
    ]

    response = client.post("/v2/memories/interpret-delivery", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "media_consent_invalid" in response.json()["reason_codes"]


def test_identity_hidden_player_uses_shared_safe_alias_rule() -> None:
    payload = raw_payload()
    payload["squad"]["players"][2]["consent"]["identity_display"] = False

    response = client.post("/v2/memories/interpret-delivery", json=payload)

    assert response.status_code == 200
    body_text = json.dumps(response.json())
    assert "ff-player-amir" not in body_text
    assert "Amir" not in body_text
    assert "anonymous:squadmate:3" in body_text


def test_player_knocked_provider_event_preserves_victim_semantics() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    event = next(
        event
        for match in prepared.normalized.matches
        for event in match.events
        if event.event_id == "ffevt-02-knock-lee"
    )
    proposal = MemoryInterpreterV2().propose(prepared)
    claim = next(
        claim
        for claim in proposal.claims
        if "ffevt-02-knock-lee" in claim.supporting_event_ids
        and claim.predicate == ClaimPredicate.WAS_KNOCKED
    )

    assert event.actor_id is None
    assert event.target_id == "ff-player-lee"
    assert claim.predicate == ClaimPredicate.WAS_KNOCKED
    assert claim.subject_id == "ff-player-lee"
    assert claim.target_id is None
    assert ProposalValidatorV2().validate(prepared, proposal).passed is True


def test_validator_rejects_actor_role_inversion_and_unknown_evidence() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    proposal = MemoryInterpreterV2().propose(prepared)
    claims = list(proposal.claims)
    revive_index = next(
        index for index, claim in enumerate(claims) if claim.predicate == ClaimPredicate.REVIVED
    )
    claims[revive_index] = claims[revive_index].model_copy(
        update={"subject_id": "ff-player-lee", "supporting_event_ids": ["unknown-event"]}
    )

    report = ProposalValidatorV2().validate(
        prepared,
        proposal.model_copy(update={"claims": claims}),
    )

    assert report.passed is False
    assert {issue.code for issue in report.issues} >= {
        "claim_evidence_outside_episode",
        "claim_predicate_not_supported",
    }


def test_match_map_claim_must_match_selected_match_metadata() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    proposal = MemoryInterpreterV2().propose(prepared)
    bad_map_claim = GroundedClaim(
        claim_id="claim:bad-map",
        output_section="summary",
        subject_id="squad",
        predicate=ClaimPredicate.PLAYED_MAP,
        value="Purgatory",
        supporting_context_ids=[f"match:{proposal.selected_match_id}:map"],
    )

    report = ProposalValidatorV2().validate(
        prepared,
        proposal.model_copy(update={"claims": [*proposal.claims, bad_map_claim]}),
    )

    assert report.passed is False
    assert "match_metadata_claim_mismatch" in {issue.code for issue in report.issues}


class SequenceGenerator:
    provider_name = "test-live"
    model_name = "typed-fixture"

    def __init__(
        self,
        proposals: list[CompactMemoryProposalV2 | OpenAIProviderError],
    ) -> None:
        self.proposals = proposals
        self.calls = 0
        self.requests: list[dict[str, object]] = []

    @property
    def observability(self) -> dict[str, object]:
        return {"calls": self.calls}

    def generate(self, **kwargs: object) -> CompactMemoryProposalV2:
        proposal = self.proposals[min(self.calls, len(self.proposals) - 1)]
        self.calls += 1
        self.requests.append(kwargs)
        if isinstance(proposal, OpenAIProviderError):
            raise proposal
        return proposal


def test_live_ai_uses_compact_contract_and_server_derives_authoritative_fields() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    generator = SequenceGenerator([compact])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    window = next(item for item in prepared.windows if item.window_id == compact.selected_window_id)
    selected_affordance = next(
        item
        for item in prepared.mission_affordances
        if item.affordance_id == compact.mission.selected_affordance_id
    )
    candidate_map = {item.candidate_id: item for item in prepared.mission_candidates}
    selected_candidates = [
        candidate_map[candidate_id] for candidate_id in selected_affordance.objective_candidate_ids
    ]
    assert result.status == "pending_player_decision"
    assert generator.requests[0]["response_model"] is ProviderInterpretationDecisionV2
    assert result.memory.selected_match_id == window.match_id
    assert result.memory.selected_event_ids == window.event_ids
    assert result.next_chapter.recipe == selected_candidates[0].recipe
    assert [item.objective_id for item in result.next_chapter.objectives] == [
        candidate.candidate_id for candidate in selected_candidates
    ]
    assert [item.verification for item in result.next_chapter.objectives] == [
        candidate.verification for candidate in selected_candidates
    ]
    assert [item.assigned_player_id for item in result.next_chapter.objectives] == [
        candidate.assigned_player_id for candidate in selected_candidates
    ]
    assert [item.player_id for item in result.player_perspectives] == [
        player.player_id for player in prepared.normalized.players if player.memory_eligible
    ]
    assert result.memory.media_reference is not None
    assert result.grounded_claims


def test_live_ai_requires_an_exact_offered_window_id_then_uses_one_correction() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    invented = valid.model_copy(update={"selected_window_id": "invented-window"})
    generator = SequenceGenerator([invented, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is True
    assert result.memory is not None
    assert result.memory.selected_match_id == prepared.windows[0].match_id
    assert generator.calls == 2
    assert generator.requests[1]["payload"]["correction"]["validation_issues"] == [
        {"code": "unknown_event_window"}
    ]


def test_compact_expander_accepts_exact_selected_match_ledger_evidence_id() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    window = next(item for item in prepared.windows if item.window_id == compact.selected_window_id)
    compact = compact.model_copy(
        update={
            "title": compact.title.model_copy(
                update={
                    "text": "Placement 5",
                    "evidence_ids": [f"match:{window.match_id}:placement"],
                }
            )
        }
    )

    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    title_claim = next(claim for claim in proposal.claims if claim.output_section == "title")
    assert title_claim.predicate == ClaimPredicate.PLACED
    assert title_claim.supporting_context_ids == [f"match:{window.match_id}:placement"]


def test_compact_expander_grounds_the_selected_game_name() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    window = next(item for item in prepared.windows if item.window_id == compact.selected_window_id)
    compact = compact.model_copy(
        update={
            "title": compact.title.model_copy(
                update={
                    "text": "A Free Fire squad memory",
                    "evidence_ids": [f"match:{window.match_id}:game"],
                }
            )
        }
    )

    proposal = CompactProposalExpanderV2().expand(prepared, compact)
    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True
    title_claim = next(claim for claim in proposal.claims if claim.output_section == "title")
    assert title_claim.predicate == ClaimPredicate.PLAYED_GAME
    assert title_claim.value == "free_fire"


def test_redundant_section_evidence_does_not_overflow_authoritative_claims() -> None:
    payload = raw_payload()
    for index in range(8):
        payload["matches"][0]["events"].append(
            {
                "event_id": f"ffevt-cap-{index}",
                "provider_event_type": "SQUAD_MEMBER_LANDED",
                "actor_id": "ff-player-lee" if index % 2 == 0 else "ff-player-mei",
                "timestamp_seconds": 1090 + index,
                "location": "Clock Tower",
                "details": {"team_members_nearby": 3},
            }
        )
    batch = RawTelemetryBatchV2.model_validate(payload)
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    window = next(item for item in prepared.windows if item.window_id == valid.selected_window_id)
    wide_title = valid.title.model_copy(update={"evidence_ids": window.event_ids})
    oversized = valid.model_copy(
        update={
            "title": wide_title,
            "notification_teaser": valid.notification_teaser.model_copy(
                update={"evidence_ids": window.event_ids}
            ),
            "summary": valid.summary.model_copy(update={"evidence_ids": window.event_ids}),
            "perspectives": [
                item.model_copy(update={"evidence_ids": window.event_ids})
                for item in valid.perspectives
            ],
        }
    )
    generator = SequenceGenerator([oversized])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is False
    assert generator.calls == 1
    assert len(result.grounded_claims) <= 50


def test_non_categorical_telemetry_detail_fails_preparation() -> None:
    payload = raw_payload()
    payload["matches"][0]["events"].append(
        {
            "event_id": "ffevt-float-loot",
            "provider_event_type": "ITEM_PICKED_UP",
            "actor_id": "ff-player-amir",
            "timestamp_seconds": 1098,
            "location": "Clock Tower",
            "details": {"item_type": 1.5},
        }
    )
    batch = RawTelemetryBatchV2.model_validate(payload)
    result = MemoryInterpretationPipelineV2().interpret_delivery(batch)

    assert result.status == "rejected"
    assert result.reason_codes == ["invalid_event_detail"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("health_state", "low"),
        ("zone_state", "closing"),
        ("weapon_class", "smg"),
        ("vehicle_type", "pickup"),
        ("item_type", "medkit"),
        ("ping_type", "retreat"),
    ],
)
def test_categorical_detail_lists_fail_closed_without_type_error(
    key: str,
    value: str,
) -> None:
    payload = raw_payload()
    payload["matches"][0]["events"][0]["details"] = {key: [value]}

    result = MemoryInterpretationPipelineV2().interpret_delivery(
        RawTelemetryBatchV2.model_validate(payload)
    )

    assert result.status == "rejected"
    assert result.reason_codes == ["invalid_event_detail"]


def test_perspective_prunes_redundant_unrelated_evidence() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(update={"evidence_ids": ["ffevt-02-knock-lee", "ffevt-03-ping-retreat"]})
        if item.player_id == "ff-player-lee"
        else item
        for item in compact.perspectives
    ]

    result = MemoryInterpretationPipelineV2(
        SequenceGenerator([compact.model_copy(update={"perspectives": perspectives})])
    ).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    predicates = {
        claim.predicate
        for claim in result.grounded_claims
        if claim.output_section == "perspective:ff-player-lee"
    }
    assert ClaimPredicate.WAS_KNOCKED in predicates
    assert ClaimPredicate.PARTICIPATED_MATCH not in predicates
    lee = next(item for item in result.player_perspectives if item.player_id == "ff-player-lee")
    assert lee.evidence_event_ids == ["ffevt-02-knock-lee"]


@pytest.mark.parametrize(
    ("player_id", "message"),
    [
        ("ff-player-amir", "You revived Lee at Clock Tower."),
        ("ff-player-lee", "You revived Mei at Clock Tower."),
    ],
)
def test_perspective_rejects_wrong_actor_or_target_wording(
    player_id: str,
    message: str,
) -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(update={"message": message, "evidence_ids": ["ffevt-04-revive-lee"]})
        if item.player_id == player_id
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "action_role_mismatch" in {issue.code for issue in report.issues}


def test_perspective_accepts_supported_collective_squad_escape() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": (
                    "I pinged a retreat to warn the squad, then we all hopped into the "
                    "pickup to escape."
                ),
                "evidence_ids": [
                    "ffevt-03-ping-retreat",
                    "ffevt-05-vehicle-enter",
                    "ffevt-06-zone-exit",
                ],
            }
        )
        if item.player_id == "ff-player-amir"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_escaping_language_does_not_create_a_false_ping_claim() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": (
                    "I revived Lee at Clock Tower, and we boarded the pickup before escaping "
                    "the zone."
                ),
                "evidence_ids": [
                    "ffevt-04-revive-lee",
                    "ffevt-05-vehicle-enter",
                    "ffevt-06-zone-exit",
                ],
            }
        )
        if item.player_id == "ff-player-mei"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_collective_squad_escape_does_not_prove_a_personal_escape_claim() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "I escaped in the pickup.",
                "evidence_ids": ["ffevt-05-vehicle-enter", "ffevt-06-zone-exit"],
            }
        )
        if item.player_id == "ff-player-amir"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "action_role_mismatch" in {issue.code for issue in report.issues}


def test_missing_actor_event_is_not_reinterpreted_as_a_squad_action() -> None:
    payload = raw_payload()
    ping = next(
        event
        for event in payload["matches"][0]["events"]
        if event["event_id"] == "ffevt-03-ping-retreat"
    )
    ping.pop("actor_id")

    result = MemoryInterpretationPipelineV2().interpret_delivery(
        RawTelemetryBatchV2.model_validate(payload)
    )

    assert result.status == "rejected"
    assert result.reason_codes == ["missing_event_actor"]


@pytest.mark.parametrize(
    ("section", "text"),
    [
        ("title", "Your Escape from Clock Tower"),
        ("perspective:ff-player-amir", "My escape from Clock Tower got the squad out."),
    ],
)
def test_collective_event_rejects_possessive_personal_attribution(
    section: str,
    text: str,
) -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    if section == "title":
        compact = compact.model_copy(
            update={
                "title": compact.title.model_copy(
                    update={"text": text, "evidence_ids": ["ffevt-06-zone-exit"]}
                )
            }
        )
    else:
        perspectives = [
            item.model_copy(update={"message": text, "evidence_ids": ["ffevt-06-zone-exit"]})
            if item.player_id == "ff-player-amir"
            else item
            for item in compact.perspectives
        ]
        compact = compact.model_copy(update={"perspectives": perspectives})
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "action_role_mismatch" in {issue.code for issue in report.issues}


def test_collective_event_accepts_possessive_squad_attribution() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "title": compact.title.model_copy(
                update={
                    "text": "Your squad's escape from Clock Tower",
                    "evidence_ids": ["ffevt-06-zone-exit"],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_hidden_identity_perspective_still_rejects_personal_squad_action() -> None:
    payload = raw_payload()
    payload["squad"]["players"][2]["consent"]["identity_display"] = False
    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    hidden_player = next(
        player
        for player in prepared.normalized.players
        if player.memory_eligible and not player.identity_visible
    )
    perspectives = [
        item.model_copy(
            update={
                "message": "I escaped from Clock Tower.",
                "evidence_ids": ["ffevt-06-zone-exit"],
            }
        )
        if item.player_id == hidden_player.player_id
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "action_role_mismatch" in {issue.code for issue in report.issues}


def test_generic_other_word_is_not_treated_as_a_vehicle_type() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "why_this_matters_now": compact.why_this_matters_now.model_copy(
                update={"text": "No other reunion opportunity is this clear right now."}
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "unsupported_categorical_detail" not in {issue.code for issue in report.issues}


def test_numeric_detail_requires_its_field_meaning_not_just_the_same_number() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "The four of you came together.",
                    "evidence_ids": ["ffevt-05-vehicle-enter"],
                }
            )
        }
    )

    proposal = CompactProposalExpanderV2().expand(prepared, compact)
    summary_claims = [claim for claim in proposal.claims if claim.output_section == "summary"]

    assert not any(claim.value_key == "squad_members_aboard" for claim in summary_claims)


def test_numeric_detail_is_emitted_when_number_and_field_meaning_are_stated() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "All four squad members boarded the pickup.",
                    "evidence_ids": ["ffevt-05-vehicle-enter"],
                }
            )
        }
    )

    proposal = CompactProposalExpanderV2().expand(prepared, compact)
    report = ProposalValidatorV2().validate(prepared, proposal)
    summary_claims = [claim for claim in proposal.claims if claim.output_section == "summary"]

    assert report.passed is True
    assert any(
        claim.value_key == "squad_members_aboard" and claim.value == 4 for claim in summary_claims
    )


def test_categorical_detail_requires_an_associated_field_or_action_cue() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "We found a pickup point.",
                    "evidence_ids": ["ffevt-05-vehicle-enter"],
                }
            )
        }
    )

    proposal = CompactProposalExpanderV2().expand(prepared, compact)
    summary_claims = [claim for claim in proposal.claims if claim.output_section == "summary"]

    assert not any(claim.value_key == "vehicle_type" for claim in summary_claims)


def test_vehicle_wording_requires_vehicle_event_and_exact_vehicle_type() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "We all hopped into a pickup to escape.",
                "evidence_ids": ["ffevt-06-zone-exit"],
            }
        )
        if item.player_id == "ff-player-amir"
        else item
        for item in compact.perspectives
    ]
    missing_vehicle = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )
    missing_report = ProposalValidatorV2().validate(prepared, missing_vehicle)

    perspectives = [
        item.model_copy(
            update={
                "message": "We all hopped into a helicopter to escape.",
                "evidence_ids": ["ffevt-05-vehicle-enter", "ffevt-06-zone-exit"],
            }
        )
        if item.player_id == "ff-player-amir"
        else item
        for item in compact.perspectives
    ]
    wrong_vehicle = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )
    wrong_report = ProposalValidatorV2().validate(prepared, wrong_vehicle)

    assert "unmapped_action_language" in {issue.code for issue in missing_report.issues}
    assert "unsupported_categorical_detail" in {issue.code for issue in missing_report.issues}
    assert "unsupported_categorical_detail" in {issue.code for issue in wrong_report.issues}


def test_player_fixture_category_free_collective_perspective_is_grounded() -> None:
    prepared = TelemetryPreparerV2().prepare(player_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "We escaped the area together.",
                "evidence_ids": ["ffevt-06-zone-exit"],
            }
        )
        if item.player_id == "ff-player-7f3c"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_player_fixture_collective_perspective_rejects_uncited_vehicle_detail() -> None:
    prepared = TelemetryPreparerV2().prepare(player_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "We escaped in the pickup.",
                "evidence_ids": ["ffevt-06-zone-exit"],
            }
        )
        if item.player_id == "ff-player-7f3c"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "unsupported_categorical_detail" in {issue.code for issue in report.issues}


def test_player_fixture_collective_perspective_accepts_canonical_vehicle_detail() -> None:
    prepared = TelemetryPreparerV2().prepare(player_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "We entered the pickup together.",
                "evidence_ids": ["ffevt-05-vehicle-enter"],
            }
        )
        if item.player_id == "ff-player-7f3c"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_collective_perspective_requires_full_squad_membership_evidence() -> None:
    payload = raw_payload()
    vehicle = next(
        event
        for event in payload["matches"][0]["events"]
        if event["event_id"] == "ffevt-05-vehicle-enter"
    )
    vehicle["details"]["squad_members_aboard"] = 1
    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "We entered a vehicle together.",
                "evidence_ids": ["ffevt-05-vehicle-enter"],
            }
        )
        if item.player_id == "ff-player-amir"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "unmapped_action_language" in {issue.code for issue in report.issues}


def test_passive_clause_does_not_bind_the_next_named_player_as_its_target() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "notification_teaser": compact.notification_teaser.model_copy(
                update={
                    "text": (
                        "Lee was knocked, Mei revived him, and the squad fled Clock Tower "
                        "in a pickup."
                    ),
                    "evidence_ids": [
                        "ffevt-02-knock-lee",
                        "ffevt-04-revive-lee",
                        "ffevt-05-vehicle-enter",
                    ],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True
    assert any(
        claim.output_section == "notification_teaser"
        and claim.predicate == ClaimPredicate.ESCAPED
        and claim.supporting_event_ids == ["ffevt-06-zone-exit"]
        for claim in proposal.claims
    )


def test_summary_rejects_cross_event_actor_action_target_recombination() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "Amir revived Lee at Clock Tower.",
                    "evidence_ids": ["ffevt-03-ping-retreat", "ffevt-04-revive-lee"],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "action_role_mismatch" in {issue.code for issue in report.issues}


def test_summary_accepts_supported_actor_action_target_tuple() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "Mei revived Lee at Clock Tower.",
                    "evidence_ids": ["ffevt-04-revive-lee"],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_summary_accepts_explicit_collective_actor_for_squad_event() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "Mei revived Lee so the squad could escape Clock Tower.",
                    "evidence_ids": ["ffevt-04-revive-lee", "ffevt-06-zone-exit"],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_perspective_accepts_explicit_we_for_supported_squad_event() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "I signalled retreat so we could escape Clock Tower.",
                "evidence_ids": ["ffevt-03-ping-retreat", "ffevt-06-zone-exit"],
            }
        )
        if item.player_id == "ff-player-amir"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_summary_rejects_collective_actor_for_player_revive() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "The squad revived Lee at Clock Tower.",
                    "evidence_ids": ["ffevt-04-revive-lee"],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "action_role_mismatch" in {issue.code for issue in report.issues}


def test_perspective_rejects_collective_actor_for_personal_signal() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "We signalled retreat at Clock Tower.",
                "evidence_ids": ["ffevt-03-ping-retreat"],
            }
        )
        if item.player_id == "ff-player-amir"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "action_role_mismatch" in {issue.code for issue in report.issues}


def test_mission_can_connect_supported_source_roles_to_all_selected_rules() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    mission = compact.mission.model_copy(
        update={
            "story_bridge": "Mei revived Lee last time, so the next chapter reverses their roles."
        }
    )
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"mission": mission}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True
    assert any(
        claim.output_section == "mission"
        and claim.predicate == ClaimPredicate.REVIVED
        and claim.subject_id == "ff-player-mei"
        and claim.target_id == "ff-player-lee"
        and claim.supporting_event_ids == ["ffevt-04-revive-lee"]
        for claim in proposal.claims
    )


def test_summary_accepts_supported_affected_player_knock_idiom() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "Lee took a knock at Clock Tower.",
                    "evidence_ids": ["ffevt-02-knock-lee"],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_literal_terms_receive_deterministic_selected_window_evidence() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "title": compact.title.model_copy(
                update={
                    "text": "Clock Tower in Free Fire",
                    "evidence_ids": ["match:game"],
                }
            ),
            "summary": compact.summary.model_copy(
                update={
                    "text": "Mei revived Lee at Clock Tower in Free Fire.",
                    "evidence_ids": ["match:game"],
                }
            ),
        }
    )

    proposal = CompactProposalExpanderV2().expand(prepared, compact)
    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True
    summary_claims = [claim for claim in proposal.claims if claim.output_section == "summary"]
    assert any(claim.predicate == ClaimPredicate.REVIVED for claim in summary_claims)
    assert any(claim.predicate == ClaimPredicate.PLAYED_GAME for claim in summary_claims)


def test_passive_action_wording_keeps_actor_and_target_roles_correct() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "Lee was revived by Mei at Clock Tower.",
                    "evidence_ids": ["ffevt-04-revive-lee"],
                }
            )
        }
    )

    proposal = CompactProposalExpanderV2().expand(prepared, compact)
    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_passive_by_agent_rejects_cross_event_actor_recombination() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "Lee was revived by Amir at Clock Tower.",
                    "evidence_ids": ["ffevt-03-ping-retreat", "ffevt-04-revive-lee"],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "action_role_mismatch" in {issue.code for issue in report.issues}


def test_reference_ids_are_removed_from_player_facing_prose() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": (
                        "Lee was knocked (ffevt-02-knock-lee). Mei revived Lee "
                        "(ffevt-04-revive-lee)."
                    ),
                    "evidence_ids": [
                        "ffevt-02-knock-lee",
                        "ffevt-04-revive-lee",
                    ],
                }
            )
        }
    )

    proposal = CompactProposalExpanderV2().expand(prepared, compact)
    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True
    assert "ffevt-" not in proposal.summary
    assert proposal.summary == "Lee was knocked. Mei revived Lee."


def test_first_person_perspective_keeps_the_perspective_player_as_actor() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "I rushed to revive Lee before we left the zone.",
                "evidence_ids": ["ffevt-04-revive-lee"],
            }
        )
        if item.player_id == "ff-player-mei"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_perspective_literal_support_is_added_only_for_that_player_role() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    perspectives = [
        item.model_copy(
            update={
                "message": "You revived Lee at Clock Tower.",
                "evidence_ids": ["ffevt-03-ping-retreat"],
            }
        )
        if item.player_id == "ff-player-mei"
        else item
        for item in compact.perspectives
    ]
    proposal = CompactProposalExpanderV2().expand(
        prepared,
        compact.model_copy(update={"perspectives": perspectives}),
    )

    report = ProposalValidatorV2().validate(prepared, proposal)
    mei = next(item for item in proposal.perspectives if item.player_id == "ff-player-mei")

    assert report.passed is True
    assert "ffevt-04-revive-lee" in mei.evidence_event_ids


def test_backend_compiles_participant_copy_and_keeps_the_exact_safe_roster_rule() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    proposal = CompactProposalExpanderV2().expand(prepared, compact)
    report = ProposalValidatorV2().validate(prepared, proposal)
    participant = next(
        item
        for item in proposal.mission.objectives
        if next(
            candidate
            for candidate in prepared.mission_candidates
            if candidate.candidate_id == item.candidate_id
        ).verification.metric
        == "squad.participant_ids"
    )
    candidate = next(
        item
        for item in prepared.mission_candidates
        if item.candidate_id == participant.candidate_id
    )

    assert report.passed is True
    assert participant.description == "Play a match with the invited squad."
    assert candidate.verification.target == prepared.story_brief.invitation_player_ids


def test_participant_mission_rejects_unoffered_survival_and_zone_conditions() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "mission": compact.mission.model_copy(
                update={
                    "story_bridge": "Keep Lee and Mei alive until the safe zone closes.",
                }
            )
        }
    )

    proposal = CompactProposalExpanderV2().expand(prepared, compact)
    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "mission_capability_language_mismatch" in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    ("wording", "expected_code"),
    [
        ("Complete two matches as a squad.", "mission_target_mismatch"),
        ("Complete twice as many matches as a squad.", "mission_target_mismatch"),
        ("Complete a couple matches as a squad.", "mission_target_mismatch"),
        ("Finish a pair of matches as a squad.", "mission_target_mismatch"),
        ("Complete a dozen matches as a squad.", "mission_target_mismatch"),
        ("Complete a two-match reunion.", "mission_target_mismatch"),
        ("Finish matches twice.", "mission_target_mismatch"),
        ("Complete two rounds together.", "mission_target_mismatch"),
        ("Complete exactly one match as a squad.", "mission_operator_mismatch"),
        (
            "Complete one match together using only pistols.",
            "mission_capability_language_mismatch",
        ),
        (
            "Complete one match together using sidearms.",
            "mission_capability_language_mismatch",
        ),
        (
            "Complete one match while crouching the entire time.",
            "mission_capability_language_mismatch",
        ),
    ],
)
def test_story_bridge_cannot_change_backend_targets_or_add_conditions(
    wording: str,
    expected_code: str,
) -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={"mission": compact.mission.model_copy(update={"story_bridge": wording})}
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert expected_code in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    "wording",
    [
        "Return the favour in the next chapter.",
        "This time, the rescue roles reverse.",
    ],
)
def test_role_reversal_story_bridge_may_paraphrase_without_repeating_the_rule(
    wording: str,
) -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={"mission": compact.mission.model_copy(update={"story_bridge": wording})}
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True
    assert "mission_rule_not_expressed" not in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    "wording",
    [
        "Complete one match with two squadmates.",
        "Complete one match with all four players.",
    ],
)
def test_match_mission_ignores_numbers_attached_to_other_nouns(wording: str) -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={"mission": compact.mission.model_copy(update={"story_bridge": wording})}
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "mission_target_mismatch" not in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    "wording",
    [
        "Bring the squad back for another chapter.",
        "Give this memory a different ending.",
        "Return the favour together.",
    ],
)
def test_story_bridge_does_not_have_to_repeat_backend_rules(wording: str) -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "mission": compact.mission.model_copy(
                update={
                    "title": "Try Again",
                    "story_bridge": wording,
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True
    assert "mission_rule_not_expressed" not in {issue.code for issue in report.issues}


def test_title_and_story_bridge_are_separate_from_backend_compiled_requirements() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "mission": compact.mission.model_copy(
                update={
                    "title": "Complete One Match Together",
                    "story_bridge": "Bring the squad back for another chapter.",
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True
    assert not any(
        issue.code == "mission_rule_not_expressed" and issue.message.startswith("Section mission ")
        for issue in report.issues
    )
    assert not any(
        issue.code == "mission_rule_not_expressed"
        and issue.message.startswith("Section objective:")
        for issue in report.issues
    )


def test_action_detection_does_not_treat_longer_words_as_gameplay_actions() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "why_this_matters_now": compact.why_this_matters_now.model_copy(
                update={
                    "text": ("A healthy reunion with an assistant coach could be a killer reset.")
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "unmapped_action_language" not in {issue.code for issue in report.issues}


def test_hidden_identity_safe_label_still_requires_grounded_player_involvement() -> None:
    payload = raw_payload()
    payload["squad"]["players"][2]["consent"]["identity_display"] = False
    next(
        event
        for event in payload["matches"][0]["events"]
        if event["event_id"] == "ffevt-03-ping-retreat"
    )["actor_id"] = "ff-player-lee"
    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": "Player 3 watched while Mei revived Lee at Clock Tower.",
                    "evidence_ids": ["ffevt-04-revive-lee"],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert "unmapped_player_identity" in {issue.code for issue in report.issues}
    assert "unsupported_observation_language" in {issue.code for issue in report.issues}
    assert "unmapped_numeric_claim" not in {issue.code for issue in report.issues}


def test_memory_type_and_first_session_angle_must_match_squad_history() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = (
        MemoryInterpreterV2()
        .demo_compact_proposal(prepared)
        .model_copy(
            update={
                "memory_type": MemoryType.FIRST,
                "narrative_angle": "The squad's first-ever match together.",
            }
        )
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert {issue.code for issue in report.issues} >= {
        "memory_type_not_supported",
        "narrative_angle_not_supported",
    }


@pytest.mark.parametrize(
    "history_update",
    [
        {"previous_session_at": ["2026-04-01T12:00:00Z"]},
        {"days_since_full_squad": 0},
        {"recent_rematch_count": 1},
    ],
)
def test_each_prior_squad_history_signal_blocks_first_framing(
    history_update: dict[str, object],
) -> None:
    payload = raw_payload()
    payload["squad_history"] = {
        "previous_session_at": [],
        "days_since_full_squad": None,
        "recent_rematch_count": 0,
        **history_update,
    }
    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))
    compact = (
        MemoryInterpreterV2()
        .demo_compact_proposal(prepared)
        .model_copy(
            update={
                "memory_type": MemoryType.FIRST,
                "narrative_angle": "The squad's first-ever match together.",
            }
        )
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert {issue.code for issue in report.issues} >= {
        "memory_type_not_supported",
        "narrative_angle_not_supported",
    }


def test_first_framing_is_allowed_when_all_prior_history_signals_are_absent() -> None:
    payload = raw_payload()
    payload["squad_history"] = {
        "previous_session_at": [],
        "days_since_full_squad": None,
        "recent_rematch_count": 0,
    }
    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))
    compact = (
        MemoryInterpreterV2()
        .demo_compact_proposal(prepared)
        .model_copy(
            update={
                "memory_type": MemoryType.FIRST,
                "narrative_angle": "The squad's first-ever match together.",
            }
        )
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)
    issue_codes = {issue.code for issue in report.issues}

    assert "memory_type_not_supported" not in issue_codes
    assert "narrative_angle_not_supported" not in issue_codes


def test_prose_rejects_metadata_value_from_another_match() -> None:
    payload = raw_payload()
    second_match = json.loads(json.dumps(payload["matches"][0]))
    second_match["match_id"] = "ff-match-purgatory"
    second_match["map_name"] = "Purgatory"
    for event in second_match["events"]:
        event["event_id"] = f"purgatory-{event['event_id']}"
    payload["matches"].append(second_match)
    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))
    proposal = MemoryInterpreterV2().propose(prepared)
    selected_match = next(
        match
        for match in prepared.normalized.matches
        if match.match_id == proposal.selected_match_id
    )
    wrong_map = next(
        match.map_name
        for match in prepared.normalized.matches
        if match.match_id != selected_match.match_id
    )
    selected_map_claim = GroundedClaim(
        claim_id="claim:summary:selected-map",
        output_section="summary",
        subject_id="squad",
        predicate=ClaimPredicate.PLAYED_MAP,
        value=selected_match.map_name,
        supporting_context_ids=[f"match:{selected_match.match_id}:map"],
    )

    report = ProposalValidatorV2().validate(
        prepared,
        proposal.model_copy(
            update={
                "summary": f"{proposal.summary} On {wrong_map}.",
                "claims": [*proposal.claims, selected_map_claim],
            }
        ),
    )

    assert "unmapped_match_metadata" in {issue.code for issue in report.issues}


def test_why_now_rejects_event_evidence_then_uses_one_correction() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    invalid = valid.model_copy(
        update={
            "why_this_matters_now": valid.why_this_matters_now.model_copy(
                update={"evidence_ids": ["ffevt-02-knock-lee"]}
            )
        }
    )
    generator = SequenceGenerator([invalid, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is True
    assert generator.calls == 2
    assert all(
        claim.predicate == ClaimPredicate.CURRENT_REUNION_OPPORTUNITY
        for claim in result.grounded_claims
        if claim.output_section == "why_this_matters_now"
    )


@pytest.mark.parametrize(
    ("text", "evidence_id"),
    [
        ("The squad last played on 2026-05-10.", "context:previous_session_at"),
        ("Lee and Mei are active now.", "context:active_player_ids"),
        ("Battle royale squad is available now.", "context:available_modes"),
    ],
)
def test_structured_context_aliases_support_their_literal_player_text(
    text: str,
    evidence_id: str,
) -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "why_this_matters_now": compact.why_this_matters_now.model_copy(
                update={"text": text, "evidence_ids": [evidence_id]}
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True


def test_live_interpreter_gets_one_bounded_grounding_correction() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    invalid = valid.model_copy(
        update={"summary": valid.summary.model_copy(update={"evidence_ids": ["unknown"]})}
    )
    generator = SequenceGenerator([invalid, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is True
    assert result.studio_trace.correction_attempted is True
    assert generator.calls == 2
    assert generator.requests[1]["payload"]["correction"]["validation_issues"] == [
        {"code": "claim_evidence_outside_episode", "section": "summary"}
    ]


def test_live_interpreter_repairs_one_malformed_provider_output() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    malformed = OpenAIProviderError(
        stage="memory_interpretation",
        code="provider_invalid_response",
        retryable=False,
    )
    generator = SequenceGenerator([malformed, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is True
    assert result.studio_trace.correction_attempted is True
    assert generator.calls == 2
    correction_payload = generator.requests[1]["payload"]
    assert correction_payload["correction"]["validation_issues"] == [
        {"code": "provider_schema_invalid"}
    ]
    correction_instruction = correction_payload["correction"]["instruction"]
    assert "emit every schema field" in correction_instruction
    assert "ProviderInterpretationDecisionV2" in correction_instruction


def test_grounding_correction_receives_section_specific_safe_feedback() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    rejected_phrase = "BOOYAH victory"
    invalid = valid.model_copy(
        update={
            "summary": valid.summary.model_copy(
                update={"text": f"{valid.summary.text} {rejected_phrase}."}
            )
        }
    )
    generator = SequenceGenerator([invalid, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    feedback = generator.requests[1]["payload"]["correction"]["validation_issues"]
    assert {
        "code": "unsupported_outcome_language",
        "section": "summary",
    } in feedback
    correction_json = json.dumps(generator.requests[1]["payload"])
    assert rejected_phrase not in correction_json
    assert "claims a victory without a matching result" not in correction_json


def test_role_and_category_failures_repair_once_with_unchanged_authoring_scopes() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    rejected_phrase = "Amir revived Lee at Clock Tower, then the squad escaped in a helicopter."
    invalid = valid.model_copy(
        update={
            "summary": valid.summary.model_copy(
                update={
                    "text": rejected_phrase,
                    "evidence_ids": [
                        "ffevt-03-ping-retreat",
                        "ffevt-04-revive-lee",
                        "ffevt-06-zone-exit",
                    ],
                }
            )
        }
    )
    generator = SequenceGenerator([invalid, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is True
    assert generator.calls == 2
    feedback = generator.requests[1]["payload"]["correction"]["validation_issues"]
    assert feedback == [
        {"code": "unsupported_categorical_detail", "section": "summary"},
        {"code": "action_role_mismatch", "section": "summary"},
    ]
    first_scopes = generator.requests[0]["payload"]["story_brief"]["authoring_constraints"]
    correction_scopes = generator.requests[1]["payload"]["story_brief"]["authoring_constraints"]
    assert correction_scopes == first_scopes
    correction = generator.requests[1]["payload"]["correction"]
    assert "remove all exact categorical and zone values" in correction["instruction"]
    assert (
        "Keep every perspective category-free" in correction["strict_section_rules"]["perspectives"]
    )
    assert rejected_phrase not in json.dumps(generator.requests[1]["payload"])


def test_player_fixture_repairs_jo_category_detail_with_one_safe_correction() -> None:
    batch = player_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)

    def jo_perspective(message: str, evidence_ids: list[str]):
        return [
            item.model_copy(update={"message": message, "evidence_ids": evidence_ids})
            if item.player_id == "ff-player-7f3c"
            else item
            for item in valid.perspectives
        ]

    invalid = valid.model_copy(
        update={
            "perspectives": jo_perspective(
                "We escaped in the pickup.",
                ["ffevt-06-zone-exit"],
            )
        }
    )
    corrected = valid.model_copy(
        update={
            "perspectives": jo_perspective(
                "We escaped the area together.",
                ["ffevt-06-zone-exit"],
            )
        }
    )
    generator = SequenceGenerator([invalid, corrected])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is True
    assert generator.calls == 2
    assert generator.requests[1]["payload"]["correction"]["validation_issues"] == [
        {
            "code": "unsupported_categorical_detail",
            "section": "perspective:ff-player-7f3c",
        }
    ]


def test_role_and_category_failure_after_one_correction_withholds_all_artifacts() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    invalid = valid.model_copy(
        update={
            "summary": valid.summary.model_copy(
                update={
                    "text": (
                        "Amir revived Lee at Clock Tower, then the squad escaped in a helicopter."
                    ),
                    "evidence_ids": [
                        "ffevt-03-ping-retreat",
                        "ffevt-04-revive-lee",
                        "ffevt-06-zone-exit",
                    ],
                }
            )
        }
    )
    generator = SequenceGenerator([invalid, invalid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert result.validation.correction_attempted is True
    assert generator.calls == 2
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.grounded_claims == []


def test_correction_feedback_drops_unrecognized_generated_section_scope() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    issue = V2ValidationIssue(
        code="unmapped_player_identity",
        severity="error",
        message="Section perspective:not-in-roster names a player without a matching claim role.",
    )

    feedback = MemoryInterpretationPipelineV2._safe_correction_feedback(prepared, [issue])

    assert feedback == [{"code": "unmapped_player_identity"}]


def test_live_interpreter_propagates_second_malformed_output_after_one_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = OpenAIProviderError(
        stage="memory_interpretation",
        code="provider_invalid_response",
        retryable=False,
    )
    generator = SequenceGenerator([malformed, malformed])
    pipeline = MemoryInterpretationPipelineV2(generator)
    monkeypatch.setattr(api, "_build_configured_v2_pipeline", lambda: pipeline)

    response = client.post("/v2/memories/interpret-delivery", json=raw_payload())

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["code"] == "provider_invalid_response"
    assert "memory" not in response.json()
    assert generator.calls == 2


@pytest.mark.parametrize(
    "code",
    [
        "provider_timeout",
        "provider_authentication_failed",
        "provider_quota_exhausted",
        "provider_refusal",
    ],
)
def test_live_interpreter_does_not_retry_nonrepairable_provider_failures(
    code: str,
) -> None:
    failure = OpenAIProviderError(
        stage="memory_interpretation",
        code=code,
        retryable=code == "provider_timeout",
    )
    generator = SequenceGenerator([failure])

    with pytest.raises(OpenAIProviderError) as raised:
        MemoryInterpretationPipelineV2(generator).interpret_delivery(parsed_batch())

    assert raised.value.code == code
    assert generator.calls == 1


def test_provider_repair_failure_withholds_content_after_one_attempt() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    invalid = valid.model_copy(
        update={
            "summary": valid.summary.model_copy(
                update={"text": valid.summary.text + " BOOYAH victory."}
            )
        }
    )
    malformed = OpenAIProviderError(
        stage="memory_interpretation",
        code="provider_invalid_response",
        retryable=False,
    )
    generator = SequenceGenerator([malformed, invalid, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert result.validation.correction_attempted is True
    assert generator.calls == 2
    assert result.memory is None
    assert result.next_chapter is None
    assert result.metadata["grounded_render"] is False
    assert result.metadata["content_origin"] == "no_player_content"
    assert result.studio_trace.stages[1].status == "withheld"


@pytest.mark.parametrize("correction_kind", ["provider_schema", "grounding"])
def test_correction_payload_over_limit_fails_closed_without_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    correction_kind: str,
) -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    if correction_kind == "provider_schema":
        first_result: CompactMemoryProposalV2 | OpenAIProviderError = OpenAIProviderError(
            stage="memory_interpretation",
            code="provider_invalid_response",
            retryable=False,
        )
    else:
        first_result = valid.model_copy(
            update={"summary": valid.summary.model_copy(update={"evidence_ids": ["unknown"]})}
        )
    generator = SequenceGenerator([first_result, valid])
    base_payload = MemoryInterpreterV2._provider_payload(prepared)
    base_size = len(
        json.dumps(base_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    monkeypatch.setattr(v2_interpreter_module, "MAX_PROVIDER_PAYLOAD_BYTES", base_size)

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert result.reason_codes == ["provider_input_too_large"]
    assert result.validation.correction_attempted is True
    assert result.studio_trace.correction_attempted is True
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.grounded_claims == []
    assert generator.calls == 1


def test_privacy_or_secret_failure_skips_correction() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    invalid = valid.model_copy(
        update={
            "title": valid.title.model_copy(update={"text": "Bearer abcdefghijklmnop"}),
            "mission": valid.mission.model_copy(update={"candidate_id": "invented-candidate"}),
        }
    )
    generator = SequenceGenerator([invalid, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert "secret_exposure" in result.reason_codes
    assert result.memory is None
    assert result.grounded_claims == []
    assert generator.calls == 1


def test_secret_like_untrusted_caption_is_rejected_before_provider_use() -> None:
    payload = raw_payload()
    payload["social_context"]["player_caption"] = FAKE_GITHUB_TOKEN
    batch = RawTelemetryBatchV2.model_validate(payload)
    safe_prepared = TelemetryPreparerV2().prepare(parsed_batch())
    generator = SequenceGenerator([MemoryInterpreterV2().demo_compact_proposal(safe_prepared)])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert result.reason_codes == ["secret_in_input"]
    assert generator.calls == 0
    assert result.memory is None


@pytest.mark.parametrize(
    ("unsafe_title", "expected_code"),
    [
        (FAKE_GITHUB_TOKEN, "secret_exposure"),
        ("Doxx Lee now", "unsafe_generated_content"),
    ],
)
def test_secret_or_unsafe_story_text_fails_without_correction(
    unsafe_title: str,
    expected_code: str,
) -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().demo_compact_proposal(prepared)
    invalid = valid.model_copy(
        update={"title": valid.title.model_copy(update={"text": unsafe_title})}
    )
    generator = SequenceGenerator([invalid, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert expected_code in result.reason_codes
    assert generator.calls == 1
    assert result.memory is None


def test_accept_and_details_wrong_update_sanitized_studio_trace() -> None:
    first = client.post("/v2/memories/interpret-delivery", json=raw_payload()).json()
    accepted = client.post(
        f"/v2/deliveries/{first['delivery_id']}/decision",
        json={"schema_version": "2.0", "decision": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["delivery_status"] == "mission_started"
    assert accepted.json()["source_quality_flag"] is False

    second = client.post("/v2/memories/interpret-delivery", json=raw_payload()).json()
    declined = client.post(
        f"/v2/deliveries/{second['delivery_id']}/decision",
        json={
            "schema_version": "2.0",
            "decision": "declined",
            "decline_reason": "details_wrong",
        },
    )
    assert declined.status_code == 200
    assert declined.json()["delivery_status"] == "suppressed"
    assert declined.json()["source_quality_flag"] is True

    trace = client.get(f"/v2/deliveries/{second['delivery_id']}/trace")
    assert trace.status_code == 200
    assert trace.headers["cache-control"] == "no-store"
    assert trace.json()["source_quality_flag"] is True
    assert trace.json()["stages"][-1]["issue_codes"] == ["source_quality_feedback"]


def test_decline_requires_one_reason_and_unknown_delivery_is_safe() -> None:
    invalid = client.post(
        "/v2/deliveries/missing/decision",
        json={"schema_version": "2.0", "decision": "declined"},
    )
    assert invalid.status_code == 422

    unknown = client.get("/v2/deliveries/missing/trace")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "unknown_delivery"


def test_provider_failure_returns_safe_503_without_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailedPipeline:
        def interpret_delivery(self, _request):
            raise OpenAIProviderError(
                stage="memory_interpretation",
                code="provider_timeout",
                retryable=True,
            )

    monkeypatch.setattr(api, "_build_configured_v2_pipeline", lambda: FailedPipeline())

    response = client.post("/v2/memories/interpret-delivery", json=raw_payload())

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["code"] == "provider_timeout"
    assert "memory" not in response.json()


def test_proxy_token_protects_both_v2_post_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORYOS_PROXY_TOKEN", "trusted")

    interpret = client.post("/v2/memories/interpret-delivery", json=raw_payload())
    decision = client.post(
        "/v2/deliveries/anything/decision",
        json={"schema_version": "2.0", "decision": "accepted"},
    )

    assert interpret.status_code == 401
    assert decision.status_code == 401


def test_proxy_token_protects_studio_trace_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery = client.post("/v2/memories/interpret-delivery", json=raw_payload()).json()
    path = f"/v2/deliveries/{delivery['delivery_id']}/trace"
    monkeypatch.setenv("MEMORYOS_PROXY_TOKEN", "trusted")

    missing = client.get(path)
    allowed = client.get(path, headers={"X-MemoryOS-Proxy-Token": "trusted"})

    assert missing.status_code == 401
    assert missing.headers["cache-control"] == "no-store"
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "no-store"


def test_offline_evaluation_summarizes_without_mutating_outputs() -> None:
    result = MemoryInterpretationPipelineV2().interpret_delivery(parsed_batch())

    summary = summarize_v2_results([result])

    assert summary.cases == 1
    assert summary.delivered == 1
    assert summary.claim_grounding_rate == 1
    assert summary.mission_feasibility_rate == 1


@pytest.mark.parametrize("leak_location", ["result", "social_key"])
def test_recursive_model_input_scan_rejects_private_identity_everywhere(
    leak_location: str,
) -> None:
    payload = raw_payload()
    payload["squad"]["players"][3]["display_name"] = "PrivatePanda"
    payload["squad"]["players"][3]["consent"] = {
        "memory_appearance": False,
        "identity_display": False,
        "media_use": False,
        "mission_invitation": False,
    }
    if leak_location == "result":
        payload["matches"][0]["result"] = "PrivatePanda escaped"
    else:
        payload["social_context"]["reaction_counts"]["PrivatePanda"] = 1

    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))

    assert "privacy_identity_leak_in_model_input" in {issue.code for issue in prepared.issues}


def test_preparation_failure_response_never_echoes_private_identity_in_opaque_ids() -> None:
    payload = raw_payload()
    private_id = payload["squad"]["players"][3]["player_id"]
    private_name = "PrivatePanda"
    payload["squad"]["players"][3]["display_name"] = private_name
    payload["squad"]["players"][3]["consent"] = {
        "memory_appearance": False,
        "identity_display": False,
        "media_use": False,
        "mission_invitation": False,
    }
    payload["matches"][0]["match_id"] = f"match-{private_name}-{private_id}"

    response = client.post("/v2/memories/interpret-delivery", json=payload)

    assert response.status_code == 200
    body = response.json()
    serialized = json.dumps(body)
    assert body["status"] == "rejected"
    assert "opaque_identifier_contains_private_identity" in body["reason_codes"]
    assert body["studio_trace"]["eligible_windows"] == []
    assert body["studio_trace"]["mission_candidates"] == []
    assert private_id not in serialized
    assert private_name not in serialized


def test_perspective_claim_must_bind_subject_and_declared_evidence() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    proposal = MemoryInterpreterV2().propose(prepared)
    claims = list(proposal.claims)
    index = next(
        index
        for index, claim in enumerate(claims)
        if claim.output_section == "perspective:ff-player-lee"
    )
    claims[index] = claims[index].model_copy(
        update={"subject_id": "ff-player-mei", "supporting_event_ids": ["ffevt-03-ping-retreat"]}
    )

    report = ProposalValidatorV2().validate(
        prepared, proposal.model_copy(update={"claims": claims})
    )

    codes = {issue.code for issue in report.issues}
    assert "perspective_claim_subject_mismatch" in codes
    assert "perspective_claim_evidence_mismatch" in codes


def test_perspective_claim_accepts_a_grounded_target_side_role() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    proposal = MemoryInterpreterV2().propose(prepared)
    section = "perspective:ff-player-lee"
    claims = [claim for claim in proposal.claims if claim.output_section != section]
    claims.append(
        GroundedClaim(
            claim_id="claim:perspective:lee:target",
            output_section=section,
            subject_id="ff-player-mei",
            target_id="ff-player-lee",
            predicate=ClaimPredicate.REVIVED,
            location="Clock Tower",
            supporting_event_ids=["ffevt-04-revive-lee"],
        )
    )
    perspectives = [
        item.model_copy(
            update={
                "message": "Mei revived you at Clock Tower.",
                "evidence_event_ids": ["ffevt-04-revive-lee"],
            }
        )
        if item.player_id == "ff-player-lee"
        else item
        for item in proposal.perspectives
    ]

    report = ProposalValidatorV2().validate(
        prepared,
        proposal.model_copy(update={"claims": claims, "perspectives": perspectives}),
    )

    assert report.passed is True


def test_participation_perspective_remains_valid_without_direct_window_action() -> None:
    payload = raw_payload()
    payload["matches"][0]["events"] = [
        event
        for event in payload["matches"][0]["events"]
        if event["event_id"] != "ffevt-03-ping-retreat"
    ]

    result = MemoryInterpretationPipelineV2().interpret_delivery(
        RawTelemetryBatchV2.model_validate(payload)
    )

    assert result.status == "pending_player_decision"
    amir = next(item for item in result.player_perspectives if item.player_id == "ff-player-amir")
    assert amir.evidence_event_ids


def test_mission_candidate_recipe_section_binding_and_safety_are_enforced() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    proposal = MemoryInterpreterV2().propose(prepared)
    other_recipe = next(
        candidate
        for candidate in prepared.mission_candidates
        if candidate.window_id == proposal.selected_window_id
        and candidate.recipe != proposal.mission.recipe
    )
    objectives = list(proposal.mission.objectives)
    objectives[0] = objectives[0].model_copy(
        update={
            "candidate_id": other_recipe.candidate_id,
            "description": "Share your password or else you cannot join.",
        }
    )
    unsafe = proposal.model_copy(
        update={"mission": proposal.mission.model_copy(update={"objectives": objectives})}
    )
    unsafe_report = ProposalValidatorV2().validate(prepared, unsafe)
    assert "unsafe_mission_content" in {issue.code for issue in unsafe_report.issues}

    objectives[0] = objectives[0].model_copy(update={"description": "Complete a new match."})
    mismatched = proposal.model_copy(
        update={"mission": proposal.mission.model_copy(update={"objectives": objectives})}
    )
    mismatch_report = ProposalValidatorV2().validate(prepared, mismatched)
    codes = {issue.code for issue in mismatch_report.issues}
    assert "mission_recipe_mismatch" in codes
    assert "objective_claim_candidate_mismatch" in codes


def test_numeric_action_claim_requires_typed_count_not_unrelated_value() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    proposal = MemoryInterpreterV2().propose(prepared)
    claims = list(proposal.claims)
    revive_index = next(
        index
        for index, claim in enumerate(claims)
        if claim.output_section == "summary" and claim.predicate == ClaimPredicate.REVIVED
    )
    claims[revive_index] = claims[revive_index].model_copy(
        update={"value": 4, "value_key": "zone_phase"}
    )
    tampered = proposal.model_copy(
        update={
            "summary": proposal.summary + " Mei revived Lee 4 times.",
            "claims": claims,
        }
    )

    report = ProposalValidatorV2().validate(prepared, tampered)

    assert "unsupported_action_count" in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    ("fabricated", "expected_code"),
    [
        ("The squad won a BOOYAH victory.", "unsupported_outcome_language"),
        ("They claimed an airdrop.", "unsupported_loot_source"),
    ],
)
def test_fabricated_outcome_and_loot_language_is_rejected(
    fabricated: str,
    expected_code: str,
) -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    proposal = MemoryInterpreterV2().propose(prepared)
    report = ProposalValidatorV2().validate(
        prepared,
        proposal.model_copy(update={"summary": proposal.summary + " " + fabricated}),
    )

    assert expected_code in {issue.code for issue in report.issues}


def test_provider_projection_is_stably_capped_to_offered_window_events() -> None:
    payload = raw_payload()
    events = payload["matches"][0]["events"]
    for index in range(100):
        events.append(
            {
                "event_id": f"bulk-{index:03d}",
                "provider_event_type": "SQUAD_MEMBER_LANDED",
                "actor_id": "ff-player-lee" if index % 2 == 0 else "ff-player-mei",
                "timestamp_seconds": 200 + index,
                "location": "Factory",
                "details": {"team_members_nearby": 2},
            }
        )
    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))
    projected_ids = {
        event.event_id for match in prepared.normalized.matches for event in match.events
    }
    window_ids = {event_id for window in prepared.windows for event_id in window.event_ids}
    provider_payload = MemoryInterpreterV2._provider_payload(prepared)
    assert "normalized_matches" not in provider_payload
    assert "media_references" not in provider_payload
    story_brief = provider_payload["story_brief"]
    assert story_brief["squad_history"] == prepared.normalized.squad_history.model_dump(mode="json")
    assert story_brief["current_context"] == prepared.normalized.current_context.model_dump(
        mode="json"
    )
    assert "policy" not in provider_payload
    ledger_event_ids = {
        fact["evidence_id"]
        for fact in story_brief["evidence_ledger"]["facts"]
        if fact["kind"] == "event"
    }
    assert ledger_event_ids == window_ids
    payload_bytes = len(json.dumps(provider_payload, separators=(",", ":")).encode())

    assert len(projected_ids) <= MAX_PROVIDER_EVENTS
    assert projected_ids == window_ids
    assert all(len(window.event_ids) <= MAX_WINDOW_EVENTS for window in prepared.windows)
    assert all(
        window.end_seconds - window.start_seconds <= MAX_WINDOW_SPAN_SECONDS
        for window in prepared.windows
    )
    assert payload_bytes <= MAX_PROVIDER_PAYLOAD_BYTES


def test_provider_payload_contains_neutral_evidence_bound_authoring_constraints() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    constraints = MemoryInterpreterV2._provider_payload(prepared)["story_brief"][
        "authoring_constraints"
    ]

    assert constraints["player_event_roles"] == {
        "ff-player-lee": {
            "actor": [],
            "target": ["ffevt-02-knock-lee", "ffevt-04-revive-lee"],
            "full_squad": ["ffevt-05-vehicle-enter", "ffevt-06-zone-exit"],
        },
        "ff-player-mei": {
            "actor": ["ffevt-04-revive-lee"],
            "target": [],
            "full_squad": ["ffevt-05-vehicle-enter", "ffevt-06-zone-exit"],
        },
        "ff-player-amir": {
            "actor": ["ffevt-03-ping-retreat"],
            "target": [],
            "full_squad": ["ffevt-05-vehicle-enter", "ffevt-06-zone-exit"],
        },
        "ff-player-7f3c": {
            "actor": [],
            "target": [],
            "full_squad": ["ffevt-05-vehicle-enter", "ffevt-06-zone-exit"],
        },
    }
    assert constraints["evidence_bound_terms"] == {
        "ffevt-02-knock-lee": {"zone_phase": 4},
        "ffevt-03-ping-retreat": {"ping_type": "retreat"},
        "ffevt-04-revive-lee": {"zone_phase": 4},
        "ffevt-05-vehicle-enter": {"vehicle_type": "pickup"},
    }
    assert not any("zone_state" in terms for terms in constraints["evidence_bound_terms"].values())
    forbidden_keys = {
        "title",
        "summary",
        "notification_teaser",
        "memory_type",
        "narrative_angle",
        "mission",
        "importance",
        "emotion",
    }

    def all_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for item in value.values() for key in all_keys(item)}
        if isinstance(value, list):
            return {key for item in value for key in all_keys(item)}
        return set()

    assert all_keys(constraints).isdisjoint(forbidden_keys)


def test_authoring_constraints_ignore_untrusted_story_steering() -> None:
    baseline = raw_payload()
    changed = raw_payload()
    changed["social_context"]["player_caption"] = "Amir's heroic rescue"
    changed["social_context"]["event_tags"] = ["Return the Favour"]
    baseline_prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(baseline))
    changed_prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(changed))

    assert (
        baseline_prepared.story_brief.authoring_constraints
        == changed_prepared.story_brief.authoring_constraints
    )


def test_authoring_constraints_exclude_opted_out_identity() -> None:
    payload = raw_payload()
    private_player = payload["squad"]["players"][3]
    private_player["player_id"] = "private-player-id"
    private_player["display_name"] = "PrivatePanda"
    private_player["consent"] = {
        "memory_appearance": False,
        "identity_display": False,
        "media_use": False,
        "mission_invitation": False,
    }
    for event in payload["matches"][0]["events"]:
        if event.get("actor_id") == "ff-player-7f3c":
            event["actor_id"] = "private-player-id"
        if event.get("target_id") == "ff-player-7f3c":
            event["target_id"] = "private-player-id"

    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))
    serialized = prepared.story_brief.authoring_constraints.model_dump_json()

    assert "private-player-id" not in serialized
    assert "PrivatePanda" not in serialized
    assert "private-player-id" not in prepared.story_brief.authoring_constraints.player_event_roles
    assert "private-player-id" not in prepared.story_brief.invitation_player_ids


def test_exact_authoring_constraint_wording_passes_existing_validator() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
    compact = compact.model_copy(
        update={
            "summary": compact.summary.model_copy(
                update={
                    "text": (
                        "Lee was knocked at Clock Tower. Amir signalled retreat. Mei revived "
                        "Lee. The squad boarded a pickup and escaped Clock Tower."
                    ),
                    "evidence_ids": [
                        "ffevt-02-knock-lee",
                        "ffevt-03-ping-retreat",
                        "ffevt-04-revive-lee",
                        "ffevt-05-vehicle-enter",
                        "ffevt-06-zone-exit",
                    ],
                }
            )
        }
    )
    proposal = CompactProposalExpanderV2().expand(prepared, compact)

    report = ProposalValidatorV2().validate(prepared, proposal)

    assert report.passed is True
    summary_details = {
        (claim.value_key, claim.value)
        for claim in proposal.claims
        if claim.output_section == "summary" and claim.value_key is not None
    }
    assert ("ping_type", "retreat") in summary_details
    assert ("vehicle_type", "pickup") in summary_details


def test_provider_payload_preserves_structured_squad_history_signals() -> None:
    baseline = raw_payload()
    changed = raw_payload()
    changed["squad_history"]["previous_session_at"] = ["2026-04-01T12:00:00Z"]
    changed["squad_history"]["recent_rematch_count"] = 7
    baseline_prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(baseline))
    changed_prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(changed))

    baseline_payload = MemoryInterpreterV2._provider_payload(baseline_prepared)
    changed_payload = MemoryInterpreterV2._provider_payload(changed_prepared)

    baseline_brief = baseline_payload["story_brief"]
    changed_brief = changed_payload["story_brief"]
    assert baseline_brief["squad_history"] != changed_brief["squad_history"]
    assert changed_brief["squad_history"]["recent_rematch_count"] == 7
    context_fact_ids = {
        fact["evidence_id"]
        for fact in changed_brief["evidence_ledger"]["facts"]
        if fact["kind"] == "context"
    }
    assert context_fact_ids >= {
        "context:previous_session_at",
        "context:recent_rematch_count",
        "context:available_modes",
    }


def test_provider_payload_omits_only_null_placeholders() -> None:
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    provider_payload = MemoryInterpreterV2._provider_payload(prepared)
    story_brief = provider_payload["story_brief"]

    def contains_none(value: object) -> bool:
        if isinstance(value, dict):
            return any(contains_none(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_none(item) for item in value)
        return value is None

    assert contains_none(story_brief) is False
    assert story_brief["target_player_id"] == prepared.story_brief.target_player_id
    assert story_brief["windows"]
    assert story_brief["affordances"]
    assert any(
        player["media_eligible"] is False
        for player in story_brief["players_requiring_perspectives"]
    )


def test_inactive_but_consented_players_remain_invitation_eligible() -> None:
    payload = raw_payload()
    payload["current_context"]["active_player_ids"] = ["ff-player-lee"]

    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))

    assert prepared.mission_candidates
    assert prepared.story_brief.invitation_player_ids == [
        "ff-player-lee",
        "ff-player-mei",
        "ff-player-amir",
        "ff-player-7f3c",
    ]


def test_mission_feasibility_requires_an_available_mode() -> None:
    payload = raw_payload()
    payload["current_context"]["available_modes"] = ["clash_squad"]

    prepared = TelemetryPreparerV2().prepare(RawTelemetryBatchV2.model_validate(payload))

    assert prepared.mission_candidates == []
    assert "no_feasible_mission" in {issue.code for issue in prepared.issues}


def test_delivery_status_invariants_reject_artifact_status_mismatch() -> None:
    valid = MemoryInterpretationPipelineV2().interpret_delivery(parsed_batch())
    payload = valid.model_dump(mode="json")
    payload["status"] = "rejected"
    payload["reason_codes"] = ["forced_mismatch"]

    with pytest.raises(ValidationError):
        InterpretDeliveryResultV2.model_validate(payload)


def test_public_v2_endpoint_requires_live_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "_build_configured_v2_pipeline", REAL_BUILD_CONFIGURED_V2_PIPELINE)
    monkeypatch.setenv("MEMORYOS_PROVIDER", "deterministic")

    response = client.post("/v2/memories/interpret-delivery", json=raw_payload())

    assert response.status_code == 503
    assert response.json()["code"] == "live_ai_required"
