"""Typed, offline-only evaluation summaries for v2 interpretation runs.

The evaluator reads completed results, optional human labels, and optional delivery decisions. It
never mutates telemetry, prompts, provider configuration, or model selection.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from backend.models.schemas import DeliveryDecision, DeliveryDeclineReason, StrictModel
from backend.models.v2_schemas import (
    DeliveryDecisionRecordV2,
    InterpretDeliveryResultV2,
    InterpretDeliveryStatusV2,
)
from backend.services.identity import contains_identity


class V2EvaluationSummary(StrictModel):
    """Legacy-compatible aggregate returned by :func:`summarize_v2_results`."""

    cases: int = Field(ge=0)
    delivered: int = Field(ge=0)
    abstained: int = Field(ge=0)
    claim_grounding_rate: float = Field(ge=0, le=1)
    unsupported_claim_rate: float = Field(ge=0, le=1)
    consent_leakage_rate: float = Field(ge=0, le=1)
    perspective_distinctness_rate: float = Field(ge=0, le=1)
    mission_feasibility_rate: float = Field(ge=0, le=1)
    correction_attempt_rate: float = Field(ge=0, le=1)


class V2ClaimEvaluationLabel(StrictModel):
    """Offline reviewer judgment for one structured claim."""

    claim_id: str = Field(min_length=1, max_length=128)
    supported: bool


class V2OfflineEvaluationCase(StrictModel):
    """One completed result plus optional labels and feedback used only for evaluation."""

    case_id: str = Field(min_length=1, max_length=128)
    result: InterpretDeliveryResultV2
    expected_window_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_deliverable: bool | None = None
    claim_labels: list[V2ClaimEvaluationLabel] = Field(default_factory=list, max_length=100)
    forbidden_identity_terms: list[str] = Field(default_factory=list, max_length=20)
    decision: DeliveryDecisionRecordV2 | None = None

    @model_validator(mode="after")
    def labels_match_result(self) -> V2OfflineEvaluationCase:
        label_ids = [label.claim_id for label in self.claim_labels]
        if len(label_ids) != len(set(label_ids)):
            raise ValueError("claim labels must use unique claim_id values")
        result_claim_ids = {claim.claim_id for claim in self.result.grounded_claims}
        unknown_claim_ids = set(label_ids) - result_claim_ids
        if unknown_claim_ids:
            raise ValueError("claim labels must reference claims returned by this result")

        normalized_terms = [term.casefold() for term in self.forbidden_identity_terms]
        if any(not term.strip() or len(term) > 128 for term in self.forbidden_identity_terms):
            raise ValueError("forbidden identity terms must contain 1 to 128 characters")
        if len(normalized_terms) != len(set(normalized_terms)):
            raise ValueError("forbidden identity terms must be unique")

        if self.decision is not None and (
            self.result.delivery_id is None or self.decision.delivery_id != self.result.delivery_id
        ):
            raise ValueError("decision must belong to this evaluation result's delivery")
        return self


class V2FeedbackOutcomeSummary(StrictModel):
    """Decision outcomes for one immutable prompt/model cohort."""

    prompt_version: str
    model: str
    evaluated_cases: int = Field(ge=0)
    decisions: int = Field(ge=0)
    no_decision: int = Field(ge=0)
    accepted: int = Field(ge=0)
    declined: int = Field(ge=0)
    declined_not_relevant: int = Field(ge=0)
    declined_details_wrong: int = Field(ge=0)
    source_quality_flags: int = Field(ge=0)
    acceptance_rate: float | None = Field(default=None, ge=0, le=1)


class V2OfflineEvaluationSummary(V2EvaluationSummary):
    """Label-aware offline metrics; all counters expose their evaluation denominator."""

    episode_labels_evaluated: int = Field(ge=0)
    episode_selections_correct: int = Field(ge=0)
    episode_selection_accuracy: float | None = Field(default=None, ge=0, le=1)
    claim_labels_evaluated: int = Field(ge=0)
    grounded_claims: int = Field(ge=0)
    unsupported_claims: int = Field(ge=0)
    consent_leak_cases: int = Field(ge=0)
    mission_story_connected: int = Field(ge=0)
    mission_story_connection_rate: float = Field(ge=0, le=1)
    deliverability_labels_evaluated: int = Field(ge=0)
    correct_deliverability_outcomes: int = Field(ge=0)
    deliverability_accuracy: float | None = Field(default=None, ge=0, le=1)
    expected_abstentions: int = Field(ge=0)
    correct_abstentions: int = Field(ge=0)
    abstention_correctness_rate: float | None = Field(default=None, ge=0, le=1)
    correction_attempts: int = Field(ge=0)
    correction_successes: int = Field(ge=0)
    correction_success_rate: float | None = Field(default=None, ge=0, le=1)
    provider_observations: int = Field(ge=0)
    provider_request_count: int = Field(ge=0)
    provider_latency_ms_total: float = Field(ge=0)
    provider_input_tokens: int = Field(ge=0)
    provider_output_tokens: int = Field(ge=0)
    feedback_outcomes: list[V2FeedbackOutcomeSummary] = Field(default_factory=list)


def summarize_v2_results(results: list[InterpretDeliveryResultV2]) -> V2EvaluationSummary:
    """Preserve the original structural summary for existing callers."""

    cases = len(results)
    delivered_results = [result for result in results if result.validation.passed]
    delivered = len(delivered_results)
    claims = [claim for result in delivered_results for claim in result.grounded_claims]
    grounded = sum(_claim_has_structural_support(claim) for claim in claims)
    claim_count = len(claims)
    privacy_failures = sum("privacy_identity_leak" in result.reason_codes for result in results)
    distinct = sum(_perspectives_are_distinct(result) for result in delivered_results)
    feasible = sum(_mission_is_feasible(result) for result in delivered_results)
    corrections = sum(result.validation.correction_attempted for result in results)
    return V2EvaluationSummary(
        cases=cases,
        delivered=delivered,
        abstained=cases - delivered,
        claim_grounding_rate=grounded / claim_count if claim_count else 1.0,
        unsupported_claim_rate=(claim_count - grounded) / claim_count if claim_count else 0.0,
        consent_leakage_rate=privacy_failures / cases if cases else 0.0,
        perspective_distinctness_rate=distinct / delivered if delivered else 1.0,
        mission_feasibility_rate=feasible / delivered if delivered else 1.0,
        correction_attempt_rate=corrections / cases if cases else 0.0,
    )


def summarize_v2_evaluation(
    cases: list[V2OfflineEvaluationCase],
) -> V2OfflineEvaluationSummary:
    """Aggregate optional labels, safe telemetry, and feedback without changing live behavior."""

    results = [case.result for case in cases]
    base = summarize_v2_results(results).model_dump()
    delivered_cases = [
        case
        for case in cases
        if case.result.status == InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION
    ]

    claim_labels = [label for case in cases for label in case.claim_labels]
    if claim_labels:
        grounded_claims = sum(label.supported for label in claim_labels)
        unsupported_claims = len(claim_labels) - grounded_claims
        base["claim_grounding_rate"] = grounded_claims / len(claim_labels)
        base["unsupported_claim_rate"] = unsupported_claims / len(claim_labels)
    else:
        structural_claims = [
            claim for case in delivered_cases for claim in case.result.grounded_claims
        ]
        grounded_claims = sum(_claim_has_structural_support(claim) for claim in structural_claims)
        unsupported_claims = len(structural_claims) - grounded_claims

    consent_leak_cases = sum(_case_has_consent_leak(case) for case in cases)
    base["consent_leakage_rate"] = consent_leak_cases / len(cases) if cases else 0.0

    episode_cases = [case for case in cases if case.expected_window_id is not None]
    episode_correct = sum(
        _selected_window_id(case.result) == case.expected_window_id for case in episode_cases
    )

    deliverability_cases = [case for case in cases if case.expected_deliverable is not None]
    deliverability_correct = sum(
        _is_delivered(case.result) == case.expected_deliverable for case in deliverability_cases
    )
    expected_abstentions = [
        case for case in deliverability_cases if case.expected_deliverable is False
    ]
    correct_abstentions = sum(not _is_delivered(case.result) for case in expected_abstentions)

    mission_story_connected = sum(
        _mission_connects_to_selected_story(case.result) for case in delivered_cases
    )
    correction_cases = [case for case in cases if case.result.validation.correction_attempted]
    correction_successes = sum(_is_delivered(case.result) for case in correction_cases)

    provider_observations = 0
    provider_request_count = 0
    provider_latency_ms_total = 0.0
    provider_input_tokens = 0
    provider_output_tokens = 0
    for result in results:
        totals = _provider_totals(result)
        if totals is None:
            continue
        provider_observations += 1
        provider_request_count += _safe_non_negative_int(totals.get("request_count"))
        provider_input_tokens += _safe_non_negative_int(totals.get("input_tokens"))
        provider_output_tokens += _safe_non_negative_int(totals.get("output_tokens"))
        provider_latency_ms_total += _safe_non_negative_float(totals.get("latency_ms"))

    feedback_outcomes = _feedback_outcomes(cases)
    base.update(
        {
            "episode_labels_evaluated": len(episode_cases),
            "episode_selections_correct": episode_correct,
            "episode_selection_accuracy": (
                episode_correct / len(episode_cases) if episode_cases else None
            ),
            "claim_labels_evaluated": len(claim_labels),
            "grounded_claims": grounded_claims,
            "unsupported_claims": unsupported_claims,
            "consent_leak_cases": consent_leak_cases,
            "mission_story_connected": mission_story_connected,
            "mission_story_connection_rate": (
                mission_story_connected / len(delivered_cases) if delivered_cases else 1.0
            ),
            "deliverability_labels_evaluated": len(deliverability_cases),
            "correct_deliverability_outcomes": deliverability_correct,
            "deliverability_accuracy": (
                deliverability_correct / len(deliverability_cases) if deliverability_cases else None
            ),
            "expected_abstentions": len(expected_abstentions),
            "correct_abstentions": correct_abstentions,
            "abstention_correctness_rate": (
                correct_abstentions / len(expected_abstentions) if expected_abstentions else None
            ),
            "correction_attempts": len(correction_cases),
            "correction_successes": correction_successes,
            "correction_success_rate": (
                correction_successes / len(correction_cases) if correction_cases else None
            ),
            "provider_observations": provider_observations,
            "provider_request_count": provider_request_count,
            "provider_latency_ms_total": round(provider_latency_ms_total, 2),
            "provider_input_tokens": provider_input_tokens,
            "provider_output_tokens": provider_output_tokens,
            "feedback_outcomes": feedback_outcomes,
        }
    )
    return V2OfflineEvaluationSummary.model_validate(base)


def _claim_has_structural_support(claim) -> bool:
    return bool(
        claim.supporting_event_ids
        or claim.supporting_context_ids
        or claim.supporting_mission_candidate_ids
    )


def _perspectives_are_distinct(result: InterpretDeliveryResultV2) -> bool:
    normalized = {" ".join(item.message.casefold().split()) for item in result.player_perspectives}
    return len(normalized) == len(result.player_perspectives)


def _mission_is_feasible(result: InterpretDeliveryResultV2) -> bool:
    return bool(result.next_chapter and result.next_chapter.objectives)


def _is_delivered(result: InterpretDeliveryResultV2) -> bool:
    return result.status == InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION


def _selected_window_id(result: InterpretDeliveryResultV2) -> str | None:
    if result.memory is None:
        return None
    for window in result.studio_trace.eligible_windows:
        if (
            window.match_id == result.memory.selected_match_id
            and window.event_ids == result.memory.selected_event_ids
        ):
            return window.window_id
    return None


def _case_has_consent_leak(case: V2OfflineEvaluationCase) -> bool:
    if not case.forbidden_identity_terms:
        return "privacy_identity_leak" in case.result.reason_codes
    serialized = case.result.model_dump_json()
    return any(contains_identity(serialized, term) for term in case.forbidden_identity_terms)


def _mission_connects_to_selected_story(result: InterpretDeliveryResultV2) -> bool:
    if result.memory is None or result.next_chapter is None or not result.next_chapter.objectives:
        return False
    selected_event_ids = set(result.memory.selected_event_ids)
    return all(
        objective.source_event_ids and set(objective.source_event_ids).issubset(selected_event_ids)
        for objective in result.next_chapter.objectives
    )


def _provider_totals(result: InterpretDeliveryResultV2) -> dict[str, object] | None:
    observability = result.metadata.get("observability")
    if not isinstance(observability, dict):
        return None
    totals = observability.get("totals")
    return totals if isinstance(totals, dict) else None


def _safe_non_negative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _safe_non_negative_float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return 0.0


def _feedback_outcomes(
    cases: list[V2OfflineEvaluationCase],
) -> list[V2FeedbackOutcomeSummary]:
    groups: dict[tuple[str, str], dict[str, int]] = {}
    for case in cases:
        prompt_version = _metadata_label(case.result, "prompt_version")
        model = _metadata_label(case.result, "model")
        counters = groups.setdefault(
            (prompt_version, model),
            {
                "evaluated_cases": 0,
                "decisions": 0,
                "accepted": 0,
                "declined": 0,
                "declined_not_relevant": 0,
                "declined_details_wrong": 0,
                "source_quality_flags": 0,
            },
        )
        counters["evaluated_cases"] += 1
        decision = case.decision
        if decision is None:
            continue
        counters["decisions"] += 1
        if decision.decision == DeliveryDecision.ACCEPTED:
            counters["accepted"] += 1
        else:
            counters["declined"] += 1
            if decision.decline_reason == DeliveryDeclineReason.NOT_RELEVANT:
                counters["declined_not_relevant"] += 1
            elif decision.decline_reason == DeliveryDeclineReason.DETAILS_WRONG:
                counters["declined_details_wrong"] += 1
        counters["source_quality_flags"] += int(decision.source_quality_flag)

    summaries: list[V2FeedbackOutcomeSummary] = []
    for (prompt_version, model), counters in sorted(groups.items()):
        decisions = counters["decisions"]
        summaries.append(
            V2FeedbackOutcomeSummary(
                prompt_version=prompt_version,
                model=model,
                evaluated_cases=counters["evaluated_cases"],
                decisions=decisions,
                no_decision=counters["evaluated_cases"] - decisions,
                accepted=counters["accepted"],
                declined=counters["declined"],
                declined_not_relevant=counters["declined_not_relevant"],
                declined_details_wrong=counters["declined_details_wrong"],
                source_quality_flags=counters["source_quality_flags"],
                acceptance_rate=counters["accepted"] / decisions if decisions else None,
            )
        )
    return summaries


def _metadata_label(result: InterpretDeliveryResultV2, key: str) -> str:
    value = result.metadata.get(key)
    return value if isinstance(value, str) and value.strip() else "unknown"
