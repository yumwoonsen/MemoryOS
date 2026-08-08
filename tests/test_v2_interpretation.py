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
from backend.models.v2_schemas import (
    ClaimPredicate,
    GroundedClaim,
    InterpretDeliveryResultV2,
    MemoryProposalV2,
    RawTelemetryBatchV2,
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
from backend.services.v2_validator import ProposalValidatorV2
from backend.v2_pipeline import MemoryInterpretationPipelineV2

DATA_PATH = Path(__file__).resolve().parents[1] / "backend" / "data" / "raw_telemetry_v2.json"
client = TestClient(app)
REAL_BUILD_CONFIGURED_V2_PIPELINE = api._build_configured_v2_pipeline


def raw_payload() -> dict[str, object]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def parsed_batch() -> RawTelemetryBatchV2:
    return RawTelemetryBatchV2.model_validate(raw_payload())


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
    assert body["schema_version"] == "2.0"
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
    assert "ff-player-7f3c" not in json.dumps(body)
    prepared = TelemetryPreparerV2().prepare(parsed_batch())
    assert any(
        event.actor_id == "anonymous:squadmate:4"
        for match in prepared.normalized.matches
        for event in match.events
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
        proposals: list[MemoryProposalV2 | OpenAIProviderError],
    ) -> None:
        self.proposals = proposals
        self.calls = 0
        self.requests: list[dict[str, object]] = []

    @property
    def observability(self) -> dict[str, object]:
        return {"calls": self.calls}

    def generate(self, **kwargs: object) -> MemoryProposalV2:
        proposal = self.proposals[min(self.calls, len(self.proposals) - 1)]
        self.calls += 1
        self.requests.append(kwargs)
        if isinstance(proposal, OpenAIProviderError):
            raise proposal
        return proposal


def test_live_interpreter_gets_one_bounded_grounding_correction() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().propose(prepared)
    bad_claims = list(valid.claims)
    bad_claims[0] = bad_claims[0].model_copy(update={"supporting_event_ids": ["unknown"]})
    invalid = valid.model_copy(update={"claims": bad_claims})
    generator = SequenceGenerator([invalid, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert result.validation.correction_attempted is True
    assert result.studio_trace.correction_attempted is True
    assert generator.calls == 2


def test_live_interpreter_repairs_one_malformed_provider_output() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().propose(prepared)
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
    assert correction_payload["correction"]["validation_issue_codes"] == ["provider_schema_invalid"]
    correction_instruction = correction_payload["correction"]["instruction"]
    assert "emit every schema field" in correction_instruction
    assert "claim target_id, location, value, and value_key" in correction_instruction


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


def test_provider_repair_and_grounding_repair_share_one_attempt_budget() -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().propose(prepared)
    bad_claims = list(valid.claims)
    bad_claims[0] = bad_claims[0].model_copy(update={"supporting_event_ids": ["unknown"]})
    invalid = valid.model_copy(update={"claims": bad_claims})
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


@pytest.mark.parametrize("correction_kind", ["provider_schema", "grounding"])
def test_correction_payload_over_limit_fails_closed_without_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    correction_kind: str,
) -> None:
    batch = parsed_batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    valid = MemoryInterpreterV2().propose(prepared)
    if correction_kind == "provider_schema":
        first_result: MemoryProposalV2 | OpenAIProviderError = OpenAIProviderError(
            stage="memory_interpretation",
            code="provider_invalid_response",
            retryable=False,
        )
    else:
        bad_claims = list(valid.claims)
        bad_claims[0] = bad_claims[0].model_copy(update={"supporting_event_ids": ["unknown"]})
        first_result = valid.model_copy(update={"claims": bad_claims})
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
    valid = MemoryInterpreterV2().propose(prepared)
    invalid = valid.model_copy(update={"title": "Bearer abcdefghijklmnop"})
    generator = SequenceGenerator([invalid, valid])

    result = MemoryInterpretationPipelineV2(generator).interpret_delivery(batch)

    assert result.status == "rejected"
    assert "secret_exposure" in result.reason_codes
    assert result.memory is None
    assert result.grounded_claims == []
    assert generator.calls == 1


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
    ledger_event_ids = {
        fact["evidence_id"]
        for fact in provider_payload["evidence_ledger"]["facts"]
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


@pytest.mark.parametrize("context_change", ["inactive", "mode_unavailable"])
def test_mission_feasibility_requires_active_players_and_available_mode(
    context_change: str,
) -> None:
    payload = raw_payload()
    if context_change == "inactive":
        payload["current_context"]["active_player_ids"] = ["ff-player-lee"]
    else:
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
