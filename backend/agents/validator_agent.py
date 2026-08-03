"""Deterministic grounding, personalization, quest, and safety checks."""

from __future__ import annotations

from backend.models.schemas import (
    DiscoveryAssessment,
    IssueSeverity,
    MemoryPack,
    MemoryRecord,
    NextChapter,
    PlayerPerspective,
    QualityScores,
    ValidationIssue,
    ValidationReport,
)


class ValidatorAgent:
    unsupported_relationship_terms = {
        "best friend",
        "soulmate",
        "closest friend",
        "like family",
    }

    def abstention_report(self, assessment: DiscoveryAssessment) -> ValidationReport:
        return ValidationReport(
            passed=True,
            human_review_required=False,
            scores=QualityScores(
                specificity=0.0,
                evidence_grounding=1.0,
                perspective_distinctness=0.0,
                quest_connection=0.0,
            ),
            issues=[
                ValidationIssue(
                    code="insufficient_memory_signal",
                    severity=IssueSeverity.INFO,
                    message=(
                        f"Signal score {assessment.signal_score:.2f} is below the "
                        f"{assessment.threshold:.2f} threshold; generation was safely skipped."
                    ),
                )
            ],
        )

    def validate(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        perspectives: list[PlayerPerspective],
        quest: NextChapter,
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        input_event_ids = {event.event_id for event in pack.match_events}
        memory_event_ids = {item.event_id for item in memory.evidence}
        squad_member_ids = {member.player_id for member in pack.squad.members if member.opted_in}

        unknown_memory_evidence = memory_event_ids - input_event_ids
        if unknown_memory_evidence:
            issues.append(
                self._error(
                    "ungrounded_memory_evidence",
                    f"Memory cites unknown event IDs: {sorted(unknown_memory_evidence)}",
                )
            )

        perspective_member_ids = {item.player_id for item in perspectives}
        missing_perspectives = squad_member_ids - perspective_member_ids
        extra_perspectives = perspective_member_ids - squad_member_ids
        if missing_perspectives:
            issues.append(
                self._error(
                    "missing_player_perspective",
                    f"Missing perspectives for: {sorted(missing_perspectives)}",
                )
            )
        if extra_perspectives:
            issues.append(
                self._error(
                    "unknown_player_perspective",
                    "Perspectives reference unknown or opted-out players: "
                    f"{sorted(extra_perspectives)}",
                )
            )

        perspective_evidence = {
            event_id for item in perspectives for event_id in item.evidence_event_ids
        }
        unknown_perspective_evidence = perspective_evidence - input_event_ids
        if unknown_perspective_evidence:
            issues.append(
                self._error(
                    "ungrounded_perspective_evidence",
                    f"Perspectives cite unknown event IDs: {sorted(unknown_perspective_evidence)}",
                )
            )

        normalized_messages = {item.message.strip().lower() for item in perspectives}
        distinctness = len(normalized_messages) / max(len(perspectives), 1)
        if distinctness < 1.0:
            issues.append(
                self._error(
                    "duplicate_player_perspective",
                    "Every opted-in player must receive a distinct perspective.",
                )
            )

        all_generated_text = " ".join(
            [memory.summary, *(item.message for item in perspectives), quest.mission]
        ).lower()
        used_relationship_terms = sorted(
            term for term in self.unsupported_relationship_terms if term in all_generated_text
        )
        if used_relationship_terms:
            issues.append(
                self._error(
                    "unsupported_relationship_claim",
                    f"Unsupported relationship language found: {used_relationship_terms}",
                )
            )

        quest_source_ids = {
            event_id for objective in quest.objectives for event_id in objective.source_event_ids
        }
        unknown_quest_evidence = quest_source_ids - input_event_ids
        if unknown_quest_evidence:
            issues.append(
                self._error(
                    "ungrounded_quest_evidence",
                    f"Quest cites unknown event IDs: {sorted(unknown_quest_evidence)}",
                )
            )
        if len(quest.objectives) < 3:
            issues.append(
                ValidationIssue(
                    code="weak_quest_specificity",
                    severity=IssueSeverity.WARNING,
                    message=(
                        "A strong Next Chapter should contain at least three "
                        "squad-specific anchors."
                    ),
                )
            )
        if not quest_source_ids.intersection(memory_event_ids):
            issues.append(
                self._error(
                    "quest_not_connected_to_memory",
                    "The quest must cite at least one event used by the discovered memory.",
                )
            )

        confirmed = bool(pack.human_memory and pack.human_memory.confirmed)
        if memory.human_confirmed != confirmed:
            issues.append(
                self._error(
                    "confirmation_state_mismatch",
                    "Generated memory confirmation does not match the input Memory Pack.",
                )
            )
        if not confirmed:
            issues.append(
                ValidationIssue(
                    code="human_confirmation_required",
                    severity=IssueSeverity.WARNING,
                    message="A player must confirm this candidate before re-engagement use.",
                )
            )

        evidence_references = memory_event_ids | perspective_evidence | quest_source_ids
        valid_references = evidence_references.intersection(input_event_ids)
        grounding_score = len(valid_references) / max(len(evidence_references), 1)
        quest_connection = len(quest_source_ids.intersection(memory_event_ids)) / max(
            len(memory_event_ids), 1
        )
        specificity = min(len(quest.objectives) / 4, 1.0)

        has_errors = any(issue.severity == IssueSeverity.ERROR for issue in issues)
        return ValidationReport(
            passed=not has_errors,
            human_review_required=not confirmed or has_errors,
            scores=QualityScores(
                specificity=round(specificity, 2),
                evidence_grounding=round(grounding_score, 2),
                perspective_distinctness=round(distinctness, 2),
                quest_connection=round(min(quest_connection, 1.0), 2),
            ),
            issues=issues,
        )

    @staticmethod
    def _error(code: str, message: str) -> ValidationIssue:
        return ValidationIssue(code=code, severity=IssueSeverity.ERROR, message=message)
