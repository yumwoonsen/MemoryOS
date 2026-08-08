"""AI-first orchestration for the MemoryOS v2 telemetry contract."""

from __future__ import annotations

import os
from uuid import uuid4

from dotenv import load_dotenv

from backend.models.v2_schemas import (
    DeliveryMemoryV2,
    DeliveryMissionObjectiveV2,
    DeliveryNextChapterV2,
    DeliveryPerspectiveV2,
    InterpretDeliveryResultV2,
    InterpretDeliveryStatusV2,
    ProposalValidationReportV2,
    RawTelemetryBatchV2,
    StudioClaimTraceV2,
    StudioInterpretationTraceV2,
    StudioTraceStageV2,
    V2ValidationIssue,
)
from backend.pipeline import LazyGroqStructuredGenerator, LazyOpenAIStructuredGenerator
from backend.services.identity import identifier_contains_identity
from backend.services.openai_client import OpenAIProviderError
from backend.services.structured_generator import StructuredGenerator
from backend.services.v2_delivery_repository import (
    V2DeliveryRepository,
    v2_delivery_repository,
)
from backend.services.v2_interpreter import MemoryInterpreterV2, ProviderInputLimitError
from backend.services.v2_preparation import PreparedInterpretationV2, TelemetryPreparerV2
from backend.services.v2_proposal_expander import CompactProposalExpansionError
from backend.services.v2_validator import FATAL_VALIDATION_CODES, ProposalValidatorV2


class MemoryInterpretationPipelineV2:
    def __init__(
        self,
        generator: StructuredGenerator | None = None,
        *,
        repository: V2DeliveryRepository | None = None,
    ) -> None:
        self.preparer = TelemetryPreparerV2()
        self.interpreter = MemoryInterpreterV2(generator)
        self.validator = ProposalValidatorV2()
        self.repository = repository or v2_delivery_repository

    @property
    def provider_name(self) -> str:
        return self.interpreter.provider_name

    @property
    def model_name(self) -> str:
        return self.interpreter.model_name

    @property
    def execution_mode(self) -> str:
        return self.interpreter.mode

    def validate_provider_configuration(self) -> None:
        self.interpreter.validate_configuration()

    def interpret_delivery(self, batch: RawTelemetryBatchV2) -> InterpretDeliveryResultV2:
        prepared = self.preparer.prepare(batch)
        if prepared.issues:
            validation = ProposalValidationReportV2(passed=False, issues=prepared.issues)
            return self._rejected(
                batch,
                prepared,
                validation,
                preparation_failed=True,
            )

        correction_attempted = False
        try:
            proposal = self.interpreter.propose(prepared)
        except ProviderInputLimitError:
            return self._provider_input_limit_rejection(
                batch,
                prepared,
                preparation_failed=True,
            )
        except CompactProposalExpansionError as error:
            if self.execution_mode != "live_ai" or error.code in FATAL_VALIDATION_CODES:
                return self._expansion_rejection(batch, prepared, error)
            correction_attempted = True
            try:
                proposal = self.interpreter.propose(
                    prepared,
                    validation_feedback=self._safe_correction_feedback(
                        prepared,
                        [error.issue()],
                    ),
                )
            except ProviderInputLimitError:
                return self._provider_input_limit_rejection(
                    batch,
                    prepared,
                    correction_attempted=True,
                )
            except CompactProposalExpansionError as correction_error:
                return self._expansion_rejection(
                    batch,
                    prepared,
                    correction_error,
                    correction_attempted=True,
                )
        except OpenAIProviderError as error:
            if self.execution_mode != "live_ai" or error.code != "provider_invalid_response":
                raise
            correction_attempted = True
            # The correction request contains only consent-safe evidence plus a
            # stable code and deterministic message. Rejected provider prose is
            # never retained or sent back to the model.
            try:
                proposal = self.interpreter.propose(
                    prepared,
                    validation_feedback=[
                        {"code": "provider_schema_invalid"},
                    ],
                )
            except ProviderInputLimitError:
                return self._provider_input_limit_rejection(
                    batch,
                    prepared,
                    correction_attempted=True,
                )
            except CompactProposalExpansionError as correction_error:
                return self._expansion_rejection(
                    batch,
                    prepared,
                    correction_error,
                    correction_attempted=True,
                )
        validation = self.validator.validate(
            prepared,
            proposal,
            correction_attempted=correction_attempted,
        )
        if (
            not validation.passed
            and not correction_attempted
            and self.execution_mode == "live_ai"
            and not any(issue.code in FATAL_VALIDATION_CODES for issue in validation.issues)
        ):
            correction_attempted = True
            try:
                proposal = self.interpreter.propose(
                    prepared,
                    validation_feedback=self._safe_correction_feedback(
                        prepared,
                        validation.issues,
                    ),
                )
            except ProviderInputLimitError:
                return self._provider_input_limit_rejection(
                    batch,
                    prepared,
                    correction_attempted=True,
                )
            except CompactProposalExpansionError as correction_error:
                return self._expansion_rejection(
                    batch,
                    prepared,
                    correction_error,
                    correction_attempted=True,
                )
            validation = self.validator.validate(
                prepared,
                proposal,
                correction_attempted=True,
            )
        if not validation.passed:
            return self._rejected(batch, prepared, validation)

        assert prepared.normalized is not None
        candidate_map = {
            candidate.candidate_id: candidate for candidate in prepared.mission_candidates
        }
        player_map = {player.player_id: player for player in prepared.normalized.players}
        media_map = {media.media_id: media for media in prepared.normalized.media_references}
        selected_media = media_map.get(proposal.media_id) if proposal.media_id else None
        objectives = []
        for proposed_objective in proposal.mission.objectives:
            candidate = candidate_map[proposed_objective.candidate_id]
            objectives.append(
                DeliveryMissionObjectiveV2(
                    objective_id=candidate.candidate_id,
                    description=proposed_objective.description,
                    assigned_player_id=candidate.assigned_player_id,
                    required=True,
                    verification=candidate.verification,
                    source_event_ids=candidate.source_event_ids,
                )
            )
        trace = self._trace(
            batch,
            prepared,
            validation,
            correction_attempted=correction_attempted,
            claim_mappings=[
                StudioClaimTraceV2(
                    claim_id=claim.claim_id,
                    output_section=claim.output_section,
                    predicate=claim.predicate,
                    evidence_ids=[
                        *claim.supporting_event_ids,
                        *claim.supporting_context_ids,
                        *claim.supporting_mission_candidate_ids,
                    ],
                )
                for claim in proposal.claims
            ],
        )
        delivery_id = uuid4().hex
        self.repository.register(delivery_id, trace)
        return InterpretDeliveryResultV2(
            request_id=batch.request_id,
            delivery_id=delivery_id,
            status=InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION,
            memory=DeliveryMemoryV2(
                title=proposal.title,
                memory_type=proposal.memory_type,
                summary=proposal.summary,
                notification_teaser=proposal.notification_teaser,
                why_this_matters_now=proposal.why_this_matters_now,
                selected_match_id=proposal.selected_match_id,
                selected_event_ids=proposal.selected_event_ids,
                media_reference=selected_media,
            ),
            player_perspectives=[
                DeliveryPerspectiveV2(
                    player_id=perspective.player_id,
                    display_name=player_map[perspective.player_id].display_name,
                    message=perspective.message,
                    evidence_event_ids=perspective.evidence_event_ids,
                )
                for perspective in proposal.perspectives
            ],
            next_chapter=DeliveryNextChapterV2(
                title=proposal.mission.title,
                mission=proposal.mission.mission,
                recipe=proposal.mission.recipe,
                objectives=objectives,
            ),
            grounded_claims=proposal.claims,
            validation=validation,
            studio_trace=trace,
            metadata=self._metadata(),
        )

    def _provider_input_limit_rejection(
        self,
        batch: RawTelemetryBatchV2,
        prepared: PreparedInterpretationV2,
        *,
        preparation_failed: bool = False,
        correction_attempted: bool = False,
    ) -> InterpretDeliveryResultV2:
        validation = ProposalValidationReportV2(
            passed=False,
            correction_attempted=correction_attempted,
            issues=[
                V2ValidationIssue(
                    code="provider_input_too_large",
                    severity="error",
                    message="The sanitized provider payload exceeded its byte limit.",
                )
            ],
        )
        return self._rejected(
            batch,
            prepared,
            validation,
            preparation_failed=preparation_failed,
        )

    @staticmethod
    def _safe_correction_feedback(
        prepared: PreparedInterpretationV2,
        issues: list[V2ValidationIssue],
    ) -> list[dict[str, str]]:
        """Reduce internal issues to bounded codes and consent-safe section identifiers."""

        allowed_sections = {
            "title",
            "notification_teaser",
            "summary",
            "why_this_matters_now",
            "mission",
        }
        if prepared.normalized is not None:
            allowed_sections.update(
                f"perspective:{player.player_id}"
                for player in prepared.normalized.players
                if player.memory_eligible
            )
        allowed_sections.update(
            f"objective:{candidate.candidate_id}" for candidate in prepared.mission_candidates
        )
        static_sections = {
            "why_now_evidence_mismatch": "why_this_matters_now",
        }
        feedback: list[dict[str, str]] = []
        seen: set[tuple[str, str | None]] = set()
        for issue in issues:
            section = static_sections.get(issue.code)
            if section is None:
                section = next(
                    (
                        candidate
                        for candidate in allowed_sections
                        if issue.message.startswith(f"Section {candidate} ")
                    ),
                    None,
                )
            key = (issue.code, section)
            if key in seen:
                continue
            seen.add(key)
            hint = {"code": issue.code}
            if section is not None:
                hint["section"] = section
            feedback.append(hint)
            if len(feedback) == 16:
                break
        return feedback

    def _expansion_rejection(
        self,
        batch: RawTelemetryBatchV2,
        prepared: PreparedInterpretationV2,
        error: CompactProposalExpansionError,
        *,
        correction_attempted: bool = False,
    ) -> InterpretDeliveryResultV2:
        return self._rejected(
            batch,
            prepared,
            ProposalValidationReportV2(
                passed=False,
                correction_attempted=correction_attempted,
                issues=[error.issue()],
            ),
        )

    def _rejected(
        self,
        batch: RawTelemetryBatchV2,
        prepared: PreparedInterpretationV2,
        validation: ProposalValidationReportV2,
        *,
        preparation_failed: bool = False,
    ) -> InterpretDeliveryResultV2:
        if preparation_failed:
            validation = self._public_preparation_validation(validation)
        return InterpretDeliveryResultV2(
            request_id=self._public_request_id(batch, prepared, preparation_failed),
            status=InterpretDeliveryStatusV2.REJECTED,
            reason_codes=[issue.code for issue in validation.issues],
            validation=validation,
            studio_trace=self._trace(
                batch,
                prepared,
                validation,
                preparation_failed=preparation_failed,
                correction_attempted=validation.correction_attempted,
            ),
            metadata=self._metadata(),
        )

    def _trace(
        self,
        batch: RawTelemetryBatchV2,
        prepared: PreparedInterpretationV2,
        validation: ProposalValidationReportV2,
        *,
        preparation_failed: bool = False,
        correction_attempted: bool = False,
        claim_mappings: list[StudioClaimTraceV2] | None = None,
    ) -> StudioInterpretationTraceV2:
        if preparation_failed:
            stages = [
                StudioTraceStageV2(
                    stage="deterministic_preparation",
                    status="rejected",
                    summary=(
                        "Telemetry, eligibility, consent, or media checks rejected the request."
                    ),
                    issue_codes=[issue.code for issue in validation.issues],
                ),
                StudioTraceStageV2(
                    stage="ai_interpretation",
                    status="withheld",
                    summary="No model call was made.",
                ),
                StudioTraceStageV2(
                    stage="deterministic_validation",
                    status="withheld",
                    summary="There was no proposal to validate.",
                ),
                StudioTraceStageV2(
                    stage="player_decision",
                    status="withheld",
                    summary="No player delivery was created.",
                ),
            ]
        else:
            stages = [
                StudioTraceStageV2(
                    stage="deterministic_preparation",
                    status="complete",
                    summary="Telemetry was normalized and privacy-filtered before interpretation.",
                ),
                StudioTraceStageV2(
                    stage="ai_interpretation",
                    status="complete" if validation.passed else "withheld",
                    summary=(
                        "One complete typed memory proposal was produced."
                        if validation.passed
                        else "A proposal was produced but its prose is withheld from this trace."
                    ),
                ),
                StudioTraceStageV2(
                    stage="deterministic_validation",
                    status="complete" if validation.passed else "rejected",
                    summary=(
                        "All evidence, consent, and mission checks passed."
                        if validation.passed
                        else "The proposal failed deterministic validation and was withheld."
                    ),
                    issue_codes=[issue.code for issue in validation.issues],
                ),
                StudioTraceStageV2(
                    stage="player_decision",
                    status="pending" if validation.passed else "withheld",
                    summary=(
                        "Waiting for one accept-or-decline decision."
                        if validation.passed
                        else "No player delivery was created."
                    ),
                ),
            ]
        normalized = prepared.normalized
        return StudioInterpretationTraceV2(
            trace_id=TelemetryPreparerV2.trace_id(batch.request_id),
            stages=stages,
            normalized_match_count=len(normalized.matches) if normalized else 0,
            normalized_event_count=(
                sum(len(match.events) for match in normalized.matches) if normalized else 0
            ),
            privacy_redaction_count=prepared.privacy_redaction_count,
            # A rejected preparation can contain attacker-controlled opaque IDs.
            # Keep only safe aggregate counts and issue codes at that boundary.
            eligible_windows=[] if preparation_failed else prepared.windows,
            mission_candidates=[] if preparation_failed else prepared.mission_candidates,
            claim_mappings=[] if preparation_failed else (claim_mappings or []),
            correction_attempted=correction_attempted,
        )

    @staticmethod
    def _public_preparation_validation(
        validation: ProposalValidationReportV2,
    ) -> ProposalValidationReportV2:
        return ProposalValidationReportV2(
            passed=False,
            correction_attempted=validation.correction_attempted,
            issues=[
                issue.model_copy(
                    update={"message": "The request failed a deterministic preparation check."}
                )
                for issue in validation.issues
            ],
        )

    @staticmethod
    def _public_request_id(
        batch: RawTelemetryBatchV2,
        prepared: PreparedInterpretationV2,
        preparation_failed: bool,
    ) -> str:
        if preparation_failed and any(
            identifier_contains_identity(batch.request_id, term)
            for term in prepared.forbidden_identity_terms
        ):
            return TelemetryPreparerV2.trace_id(batch.request_id).replace("trace_", "request_", 1)
        return batch.request_id

    def _metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "pipeline_version": "ai-grounded-interpretation-v2",
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": self.execution_mode,
            "prompt_version": self.interpreter.prompt_version,
            "narrative_fallback": False,
            "storage": "process_local_prototype",
        }
        if self.interpreter.observability:
            metadata["observability"] = self.interpreter.observability
        return metadata


def build_v2_pipeline(provider: str | None = None) -> MemoryInterpretationPipelineV2:
    load_dotenv()
    selected = (provider or os.getenv("MEMORYOS_PROVIDER", "deterministic")).strip().lower()
    if selected == "deterministic":
        return MemoryInterpretationPipelineV2()
    if selected == "groq":
        return MemoryInterpretationPipelineV2(LazyGroqStructuredGenerator())
    if selected == "openai":
        return MemoryInterpretationPipelineV2(LazyOpenAIStructuredGenerator())
    raise ValueError("MEMORYOS_PROVIDER must be 'deterministic', 'openai', or 'groq'")
