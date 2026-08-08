"""Typed, offline-only evaluation summaries for v2 interpretation runs.

The evaluator reads completed results, optional human labels, and optional delivery decisions. It
never mutates telemetry, prompts, provider configuration, or model selection.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field, model_validator

from backend.models.schemas import DeliveryDecision, DeliveryDeclineReason, StrictModel
from backend.models.v2_schemas import (
    DeliveryDecisionRecordV2,
    InterpretDeliveryResultV2,
    InterpretDeliveryStatusV2,
    MissionFamilyV2,
)
from backend.services.identity import contains_identity


class V2EvaluationSummary(StrictModel):
    """Legacy-compatible aggregate returned by :func:`summarize_v2_results`."""

    cases: int = Field(ge=0)
    delivered: int = Field(ge=0)
    abstained: int = Field(ge=0)
    rejected: int = Field(default=0, ge=0)
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
    expected_status: InterpretDeliveryStatusV2 | None = None
    expected_mission_family: MissionFamilyV2 | None = None
    forbidden_offered_mission_families: list[MissionFamilyV2] = Field(
        default_factory=list,
        max_length=3,
    )
    mission_variation_group: str | None = Field(default=None, min_length=1, max_length=128)
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

        if self.expected_status is not None and self.expected_deliverable is not None:
            status_is_deliverable = (
                self.expected_status == InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION
            )
            if status_is_deliverable != self.expected_deliverable:
                raise ValueError("expected_status conflicts with expected_deliverable")
        if self.expected_mission_family is not None and self.expected_status not in {
            None,
            InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION,
        }:
            raise ValueError("expected_mission_family requires an expected delivered status")
        if len(self.forbidden_offered_mission_families) != len(
            set(self.forbidden_offered_mission_families)
        ):
            raise ValueError("forbidden offered mission families must be unique")
        if self.mission_variation_group is not None and self.expected_mission_family is None:
            raise ValueError("mission_variation_group requires expected_mission_family")
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
    status_labels_evaluated: int = Field(ge=0)
    correct_status_outcomes: int = Field(ge=0)
    status_accuracy: float | None = Field(default=None, ge=0, le=1)
    typed_abstention_labels_evaluated: int = Field(ge=0)
    correct_typed_abstentions: int = Field(ge=0)
    typed_abstention_accuracy: float | None = Field(default=None, ge=0, le=1)
    rejection_labels_evaluated: int = Field(ge=0)
    correct_rejections: int = Field(ge=0)
    rejection_accuracy: float | None = Field(default=None, ge=0, le=1)
    mission_family_labels_evaluated: int = Field(ge=0)
    correct_mission_families: int = Field(ge=0)
    mission_family_accuracy: float | None = Field(default=None, ge=0, le=1)
    affordance_selection_cases_evaluated: int = Field(ge=0)
    affordance_rankings_unique: int = Field(ge=0)
    affordance_rankings_offered: int = Field(ge=0)
    affordance_selections_ranked_first: int = Field(ge=0)
    affordance_families_consistent: int = Field(ge=0)
    affordance_reason_codes_allowed: int = Field(ge=0)
    affordance_objective_sets_exact: int = Field(ge=0)
    affordance_selections_compliant: int = Field(ge=0)
    affordance_selection_compliance_rate: float = Field(ge=0, le=1)
    forbidden_family_labels_evaluated: int = Field(ge=0)
    forbidden_families_removed: int = Field(ge=0)
    forbidden_family_removal_rate: float | None = Field(default=None, ge=0, le=1)
    mission_variation_groups_evaluated: int = Field(ge=0)
    mission_variation_groups_correct: int = Field(ge=0)
    cross_fixture_family_variation_rate: float | None = Field(default=None, ge=0, le=1)
    provider_observations: int = Field(ge=0)
    provider_request_count: int = Field(ge=0)
    provider_latency_ms_total: float = Field(ge=0)
    provider_input_tokens: int = Field(ge=0)
    provider_output_tokens: int = Field(ge=0)
    feedback_outcomes: list[V2FeedbackOutcomeSummary] = Field(default_factory=list)


def summarize_v2_results(results: list[InterpretDeliveryResultV2]) -> V2EvaluationSummary:
    """Preserve the original structural summary for existing callers."""

    cases = len(results)
    delivered_results = [
        result
        for result in results
        if result.status == InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION
    ]
    delivered = len(delivered_results)
    abstained = sum(result.status == InterpretDeliveryStatusV2.NOT_GENERATED for result in results)
    rejected = sum(result.status == InterpretDeliveryStatusV2.REJECTED for result in results)
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
        abstained=abstained,
        rejected=rejected,
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
        case for case in cases if case.expected_status == InterpretDeliveryStatusV2.NOT_GENERATED
    ]
    correct_abstentions = sum(
        case.result.status == InterpretDeliveryStatusV2.NOT_GENERATED
        for case in expected_abstentions
    )

    status_cases = [case for case in cases if case.expected_status is not None]
    correct_status_outcomes = sum(
        case.result.status == case.expected_status for case in status_cases
    )
    rejection_cases = [
        case for case in status_cases if case.expected_status == InterpretDeliveryStatusV2.REJECTED
    ]
    correct_rejections = sum(
        case.result.status == InterpretDeliveryStatusV2.REJECTED for case in rejection_cases
    )

    family_cases = [case for case in cases if case.expected_mission_family is not None]
    correct_mission_families = sum(
        _selected_mission_family(case.result) == case.expected_mission_family
        for case in family_cases
    )
    affordance_audits = [_audit_affordance_selection(case.result) for case in delivered_cases]
    forbidden_family_cases = [case for case in cases if case.forbidden_offered_mission_families]
    forbidden_families_removed = sum(
        not (set(case.forbidden_offered_mission_families) & _offered_mission_families(case.result))
        for case in forbidden_family_cases
    )
    variation_groups = _variation_groups(cases)
    correct_variation_groups = sum(_variation_group_is_correct(group) for group in variation_groups)

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
            "status_labels_evaluated": len(status_cases),
            "correct_status_outcomes": correct_status_outcomes,
            "status_accuracy": (
                correct_status_outcomes / len(status_cases) if status_cases else None
            ),
            "typed_abstention_labels_evaluated": len(expected_abstentions),
            "correct_typed_abstentions": correct_abstentions,
            "typed_abstention_accuracy": (
                correct_abstentions / len(expected_abstentions) if expected_abstentions else None
            ),
            "rejection_labels_evaluated": len(rejection_cases),
            "correct_rejections": correct_rejections,
            "rejection_accuracy": (
                correct_rejections / len(rejection_cases) if rejection_cases else None
            ),
            "mission_family_labels_evaluated": len(family_cases),
            "correct_mission_families": correct_mission_families,
            "mission_family_accuracy": (
                correct_mission_families / len(family_cases) if family_cases else None
            ),
            "affordance_selection_cases_evaluated": len(affordance_audits),
            "affordance_rankings_unique": sum(item.ranking_unique for item in affordance_audits),
            "affordance_rankings_offered": sum(
                item.ranking_matches_offered for item in affordance_audits
            ),
            "affordance_selections_ranked_first": sum(
                item.selected_ranked_first for item in affordance_audits
            ),
            "affordance_families_consistent": sum(
                item.family_consistent for item in affordance_audits
            ),
            "affordance_reason_codes_allowed": sum(
                item.reason_codes_allowed for item in affordance_audits
            ),
            "affordance_objective_sets_exact": sum(
                item.objective_ids_exact for item in affordance_audits
            ),
            "affordance_selections_compliant": sum(item.compliant for item in affordance_audits),
            "affordance_selection_compliance_rate": (
                sum(item.compliant for item in affordance_audits) / len(affordance_audits)
                if affordance_audits
                else 1.0
            ),
            "forbidden_family_labels_evaluated": len(forbidden_family_cases),
            "forbidden_families_removed": forbidden_families_removed,
            "forbidden_family_removal_rate": (
                forbidden_families_removed / len(forbidden_family_cases)
                if forbidden_family_cases
                else None
            ),
            "mission_variation_groups_evaluated": len(variation_groups),
            "mission_variation_groups_correct": correct_variation_groups,
            "cross_fixture_family_variation_rate": (
                correct_variation_groups / len(variation_groups) if variation_groups else None
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


def _selected_mission_family(result: InterpretDeliveryResultV2) -> MissionFamilyV2 | None:
    if result.next_chapter is not None:
        return result.next_chapter.family
    selection = result.studio_trace.mission_selection
    return selection.selected_family if selection is not None else None


def _offered_mission_families(result: InterpretDeliveryResultV2) -> set[MissionFamilyV2]:
    return {item.family for item in result.studio_trace.mission_affordances}


@dataclass(frozen=True)
class _AffordanceSelectionAudit:
    ranking_unique: bool
    ranking_matches_offered: bool
    selected_ranked_first: bool
    family_consistent: bool
    reason_codes_allowed: bool
    objective_ids_exact: bool

    @property
    def compliant(self) -> bool:
        return all(
            (
                self.ranking_unique,
                self.ranking_matches_offered,
                self.selected_ranked_first,
                self.family_consistent,
                self.reason_codes_allowed,
                self.objective_ids_exact,
            )
        )


def _audit_affordance_selection(result: InterpretDeliveryResultV2) -> _AffordanceSelectionAudit:
    offered = {
        affordance.affordance_id: affordance
        for affordance in result.studio_trace.mission_affordances
    }
    selection = result.studio_trace.mission_selection
    if selection is None or result.next_chapter is None:
        return _AffordanceSelectionAudit(False, False, False, False, False, False)

    ranked = selection.ranked_affordance_ids
    selected = offered.get(selection.selected_affordance_id)
    ranking_unique = bool(ranked) and len(ranked) == len(set(ranked))
    ranking_matches_offered = bool(offered) and set(ranked) == set(offered)
    selected_ranked_first = bool(ranked) and ranked[0] == selection.selected_affordance_id
    family_consistent = bool(
        selected is not None
        and selection.selected_family == selected.family == result.next_chapter.family
    )
    reason_codes_allowed = bool(
        selected is not None
        and selection.reason_codes
        and set(selection.reason_codes).issubset(set(selected.allowed_reason_codes))
    )
    delivered_objective_ids = [item.objective_id for item in result.next_chapter.objectives]
    objective_ids_exact = bool(
        selected is not None
        and len(delivered_objective_ids) == len(set(delivered_objective_ids))
        and set(delivered_objective_ids) == set(selected.objective_candidate_ids)
    )
    return _AffordanceSelectionAudit(
        ranking_unique=ranking_unique,
        ranking_matches_offered=ranking_matches_offered,
        selected_ranked_first=selected_ranked_first,
        family_consistent=family_consistent,
        reason_codes_allowed=reason_codes_allowed,
        objective_ids_exact=objective_ids_exact,
    )


def _variation_groups(
    cases: list[V2OfflineEvaluationCase],
) -> list[list[V2OfflineEvaluationCase]]:
    grouped: dict[str, list[V2OfflineEvaluationCase]] = {}
    for case in cases:
        if case.mission_variation_group is not None:
            grouped.setdefault(case.mission_variation_group, []).append(case)
    return [
        group
        for group in grouped.values()
        if len(group) >= 2 and len({case.expected_mission_family for case in group}) >= 2
    ]


def _variation_group_is_correct(group: list[V2OfflineEvaluationCase]) -> bool:
    expected = [case.expected_mission_family for case in group]
    observed = [_selected_mission_family(case.result) for case in group]
    return observed == expected and len(set(observed)) == len(set(expected))


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
