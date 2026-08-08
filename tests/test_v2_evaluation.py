"""Offline evaluation coverage for the v2 interpretation contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.schemas import DeliveryDecision, DeliveryDeclineReason
from backend.models.v2_schemas import (
    DeliveryDecisionRecordV2,
    InterpretDeliveryResultV2,
    RawTelemetryBatchV2,
)
from backend.services.v2_evaluation import (
    V2ClaimEvaluationLabel,
    V2EvaluationSummary,
    V2OfflineEvaluationCase,
    summarize_v2_evaluation,
    summarize_v2_results,
)
from backend.v2_pipeline import MemoryInterpretationPipelineV2

DATA_PATH = Path(__file__).resolve().parents[1] / "backend" / "data" / "raw_telemetry_v2.json"


def _payload() -> dict[str, object]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _delivered_result() -> InterpretDeliveryResultV2:
    result = MemoryInterpretationPipelineV2().interpret_delivery(
        RawTelemetryBatchV2.model_validate(_payload())
    )
    assert result.status == "pending_player_decision"
    return result


def _rejected_result() -> InterpretDeliveryResultV2:
    payload = _payload()
    payload["current_context"]["reunion_eligible"] = False
    result = MemoryInterpretationPipelineV2().interpret_delivery(
        RawTelemetryBatchV2.model_validate(payload)
    )
    assert result.status == "rejected"
    return result


def _selected_window_id(result: InterpretDeliveryResultV2) -> str:
    assert result.memory is not None
    return next(
        window.window_id
        for window in result.studio_trace.eligible_windows
        if window.match_id == result.memory.selected_match_id
        and window.event_ids == result.memory.selected_event_ids
    )


def test_legacy_summary_contract_remains_available() -> None:
    summary = summarize_v2_results([_delivered_result()])

    assert type(summary) is V2EvaluationSummary
    assert summary.cases == 1
    assert summary.delivered == 1
    assert summary.claim_grounding_rate == 1
    assert summary.mission_feasibility_rate == 1


def test_labelled_selection_abstention_claim_and_correction_metrics() -> None:
    delivered = _delivered_result()
    delivered = delivered.model_copy(
        update={
            "validation": delivered.validation.model_copy(update={"correction_attempted": True})
        }
    )
    rejected = _rejected_result()
    rejected = rejected.model_copy(
        update={"validation": rejected.validation.model_copy(update={"correction_attempted": True})}
    )
    claim_ids = [claim.claim_id for claim in delivered.grounded_claims[:2]]
    cases = [
        V2OfflineEvaluationCase(
            case_id="delivered-labelled",
            result=delivered,
            expected_window_id=_selected_window_id(delivered),
            expected_deliverable=True,
            claim_labels=[
                V2ClaimEvaluationLabel(claim_id=claim_ids[0], supported=True),
                V2ClaimEvaluationLabel(claim_id=claim_ids[1], supported=False),
            ],
        ),
        V2OfflineEvaluationCase(
            case_id="expected-abstention",
            result=rejected,
            expected_deliverable=False,
        ),
    ]

    summary = summarize_v2_evaluation(cases)

    assert summary.episode_labels_evaluated == 1
    assert summary.episode_selection_accuracy == 1
    assert summary.claim_labels_evaluated == 2
    assert summary.claim_grounding_rate == 0.5
    assert summary.unsupported_claim_rate == 0.5
    assert summary.deliverability_accuracy == 1
    assert summary.expected_abstentions == 1
    assert summary.abstention_correctness_rate == 1
    assert summary.correction_attempts == 2
    assert summary.correction_successes == 1
    assert summary.correction_success_rate == 0.5


def test_consent_distinctness_and_story_connection_are_measured() -> None:
    delivered = _delivered_result()
    perspectives = list(delivered.player_perspectives)
    perspectives[1] = perspectives[1].model_copy(update={"message": perspectives[0].message})
    duplicate_perspective = delivered.model_copy(update={"player_perspectives": perspectives})

    assert delivered.next_chapter is not None
    objectives = list(delivered.next_chapter.objectives)
    objectives[0] = objectives[0].model_copy(update={"source_event_ids": ["outside-story"]})
    disconnected_mission = delivered.model_copy(
        update={
            "next_chapter": delivered.next_chapter.model_copy(update={"objectives": objectives})
        }
    )

    leaked_identity = "private-player-name"
    leaked = delivered.model_copy(
        update={"metadata": {**delivered.metadata, "unsafe_debug": leaked_identity}}
    )
    cases = [
        V2OfflineEvaluationCase(case_id="duplicate", result=duplicate_perspective),
        V2OfflineEvaluationCase(case_id="disconnected", result=disconnected_mission),
        V2OfflineEvaluationCase(
            case_id="leak",
            result=leaked,
            forbidden_identity_terms=[leaked_identity],
        ),
    ]

    summary = summarize_v2_evaluation(cases)

    assert summary.perspective_distinctness_rate == pytest.approx(2 / 3)
    assert summary.mission_feasibility_rate == 1
    assert summary.mission_story_connected == 2
    assert summary.mission_story_connection_rate == pytest.approx(2 / 3)
    assert summary.consent_leak_cases == 1
    assert summary.consent_leakage_rate == pytest.approx(1 / 3)


def test_safe_provider_usage_and_feedback_are_grouped_without_mutation() -> None:
    first = _delivered_result()
    second = first.model_copy(update={"delivery_id": "delivery-second"})
    third = first.model_copy(update={"delivery_id": "delivery-third"})
    first_metadata = {
        **first.metadata,
        "model": "model-a",
        "prompt_version": "prompt-a",
        "observability": {
            "totals": {
                "request_count": 2,
                "input_tokens": 120,
                "output_tokens": 30,
                "latency_ms": 45.25,
            }
        },
    }
    second_metadata = {
        **second.metadata,
        "model": "model-a",
        "prompt_version": "prompt-a",
        "observability": {
            "totals": {
                "request_count": 1,
                "input_tokens": 70,
                "output_tokens": 20,
                "latency_ms": 30,
            }
        },
    }
    third_metadata = {
        **third.metadata,
        "model": "model-b",
        "prompt_version": "prompt-b",
    }
    first = first.model_copy(update={"metadata": first_metadata})
    second = second.model_copy(update={"metadata": second_metadata})
    third = third.model_copy(update={"metadata": third_metadata})
    accepted = DeliveryDecisionRecordV2(
        delivery_id=first.delivery_id,
        decision=DeliveryDecision.ACCEPTED,
        delivery_status="mission_started",
        source_quality_flag=False,
    )
    not_relevant = DeliveryDecisionRecordV2(
        delivery_id=second.delivery_id,
        decision=DeliveryDecision.DECLINED,
        decline_reason=DeliveryDeclineReason.NOT_RELEVANT,
        delivery_status="suppressed",
        source_quality_flag=False,
    )
    details_wrong = DeliveryDecisionRecordV2(
        delivery_id=third.delivery_id,
        decision=DeliveryDecision.DECLINED,
        decline_reason=DeliveryDeclineReason.DETAILS_WRONG,
        delivery_status="suppressed",
        source_quality_flag=True,
    )
    original_metadata = first.model_dump(mode="json")["metadata"]

    summary = summarize_v2_evaluation(
        [
            V2OfflineEvaluationCase(case_id="accepted", result=first, decision=accepted),
            V2OfflineEvaluationCase(
                case_id="not-relevant",
                result=second,
                decision=not_relevant,
            ),
            V2OfflineEvaluationCase(
                case_id="details-wrong",
                result=third,
                decision=details_wrong,
            ),
        ]
    )

    assert summary.provider_observations == 2
    assert summary.provider_request_count == 3
    assert summary.provider_input_tokens == 190
    assert summary.provider_output_tokens == 50
    assert summary.provider_latency_ms_total == 75.25
    assert [(item.prompt_version, item.model) for item in summary.feedback_outcomes] == [
        ("prompt-a", "model-a"),
        ("prompt-b", "model-b"),
    ]
    first_group, second_group = summary.feedback_outcomes
    assert first_group.decisions == 2
    assert first_group.accepted == 1
    assert first_group.declined_not_relevant == 1
    assert first_group.acceptance_rate == 0.5
    assert second_group.declined_details_wrong == 1
    assert second_group.source_quality_flags == 1
    assert first.model_dump(mode="json")["metadata"] == original_metadata


def test_case_rejects_unknown_claim_and_mismatched_decision() -> None:
    delivered = _delivered_result()

    with pytest.raises(ValidationError):
        V2OfflineEvaluationCase(
            case_id="unknown-claim",
            result=delivered,
            claim_labels=[V2ClaimEvaluationLabel(claim_id="missing", supported=True)],
        )

    with pytest.raises(ValidationError):
        V2OfflineEvaluationCase(
            case_id="wrong-delivery",
            result=delivered,
            decision=DeliveryDecisionRecordV2(
                delivery_id="another-delivery",
                decision=DeliveryDecision.ACCEPTED,
                delivery_status="mission_started",
                source_quality_flag=False,
            ),
        )
