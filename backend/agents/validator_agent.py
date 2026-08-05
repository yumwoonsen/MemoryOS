"""Deterministic grounding, personalization, quest, and safety checks."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from backend.agents.memory_agent import MemoryAgent
from backend.agents.perspective_agent import PerspectiveAgent
from backend.models.schemas import (
    DiscoveryAssessment,
    IssueSeverity,
    MatchEvent,
    MeaningStatus,
    MemoryPack,
    MemoryRecord,
    NextChapter,
    PipelineStatusV11,
    PlayerPerspective,
    QualityScores,
    QuestObjective,
    SourceStatus,
    ValidationIssue,
    ValidationReport,
)
from backend.services.evidence import SAFE_DETAIL_KEYS, literal_passenger_target
from backend.services.identity import identity_pattern


@dataclass(frozen=True)
class _FactualSegment:
    """A generated text fragment and the finite facts it is allowed to use."""

    text: str
    event_ids: tuple[str, ...]
    extra_numbers: tuple[float, ...] = ()
    allow_all_opted_in_players: bool = False
    speaker_player_id: str | None = None
    validate_facts: bool = True
    bind_action_roles: bool = True


class ValidatorAgent:
    unsupported_relationship_terms = {
        "best friend",
        "soulmate",
        "closest friend",
        "like family",
    }
    unsupported_emotional_terms = {
        "afraid",
        "angry",
        "anxious",
        "ashamed",
        "embarrassed",
        "furious",
        "jealous",
        "sad",
        "scared",
        "terrified",
    }
    unsupported_intent_terms = {
        "believed",
        "deliberately",
        "felt",
        "hoped",
        "intentionally",
        "knew",
        "on purpose",
        "wanted",
    }
    unsupported_action_terms = {
        "abandoned",
        "betrayed",
        "sabotaged",
        "surrendered",
    }
    event_action_patterns: dict[str, tuple[str, ...]] = {
        "elimination": (
            r"\beliminat(?:e|ed|es|ing|ion|ions)\b",
            r"\bkill(?:ed|s|ing)?\b",
        ),
        "knockdown": (r"\bknock(?:ed|s|ing)?\s+(?:down|out)\b",),
        "revive": (
            r"\breviv(?:e|ed|es|ing)\b",
            r"\brescu(?:e|ed|es|ing)\b",
            r"\bbrought\b.{0,40}\bback\b",
        ),
        "vehicle_escape": (
            r"\bdrov(?:e|en)\b",
            r"\bdriv(?:e|es|ing)\b",
            r"\bvehicle escape\b",
            r"\bgetaway\b",
        ),
        "retreat_ping": (
            r"\bretreat(?:ed|s|ing)?\b",
            r"\brotation route\b",
            r"\broute caller\b",
        ),
        "last_player_alive": (
            r"\blast (?:squad )?(?:member|player) alive\b",
            r"\blast surviving player\b",
        ),
        "final_zone_survival": (r"\bfinal zone survival\b",),
        "cover_fire": (r"\bcover fire\b",),
    }
    _claim_verbs = (
        "abandoned|betrayed|believed|called|calls|completed|drove|drives|"
        "eliminated|eliminates|felt|helped|helps|hoped|killed|kills|knew|"
        "rescued|rescues|revived|revives|sabotaged|saved|saves|surrendered|"
        "wanted"
    )
    _generic_claim_subjects = {
        "a squadmate",
        "an anonymous squadmate",
        "it",
        "that",
        "the squad",
        "they",
        "this",
        "we",
        "you",
    }
    generic_location_phrases = {
        "the match",
        "the late game",
        "the final rotation",
        "the final circle",
        "the first contested location",
    }

    def abstention_report(self, assessment: DiscoveryAssessment) -> ValidationReport:
        return ValidationReport(
            passed=True,
            human_review_required=False,
            scores=self._empty_scores(),
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

    def review_pending_report(
        self, status: PipelineStatusV11, assessment: DiscoveryAssessment
    ) -> ValidationReport:
        if status == PipelineStatusV11.NEEDS_SOURCE_VERIFICATION:
            code = "source_verification_required"
            message = "A player must verify that the source events describe the match."
        else:
            code = "meaning_confirmation_required"
            message = "A player must confirm that this candidate is personally meaningful."
        return ValidationReport(
            passed=True,
            human_review_required=True,
            scores=self._empty_scores(),
            issues=[ValidationIssue(code=code, severity=IssueSeverity.WARNING, message=message)],
        )

    def validate_memory_stage(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        *,
        forbidden_terms: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Validate a discovered memory before it is sent to the perspective stage."""

        issues = self._validate_memory_evidence(pack, memory)
        canonical_memory = MemoryAgent().preview(pack, memory.confidence)
        if (
            memory.summary != canonical_memory.summary
            or memory.evidence != canonical_memory.evidence
        ):
            issues.append(
                self._error(
                    "noncanonical_memory_facts",
                    "Memory facts must use the closed renderer for the selected evidence.",
                )
            )
        meaning_confirmed = pack.meaning_status == MeaningStatus.CONFIRMED
        if memory.human_confirmed != meaning_confirmed:
            issues.append(
                self._error(
                    "confirmation_state_mismatch",
                    "Generated memory confirmation does not match the normalized review state.",
                )
            )
        memory_ids = tuple(item.event_id for item in memory.evidence)
        caption_title = (
            pack.human_memory.caption.strip().title()[:100]
            if pack.human_memory and pack.human_memory.caption
            else None
        )
        segments = [
            _FactualSegment(
                memory.title,
                memory_ids,
                validate_facts=memory.title != caption_title,
            ),
            _FactualSegment(memory.summary, memory_ids),
            *(_FactualSegment(item.significance, (item.event_id,)) for item in memory.evidence),
        ]
        issues.extend(
            self._validate_generated_language(pack, segments, forbidden_terms=forbidden_terms)
        )
        issues.extend(
            self._structured_privacy_issues(
                [
                    memory.title,
                    memory.summary,
                    *(reference.event_id for reference in memory.evidence),
                    *(reference.event_type for reference in memory.evidence),
                    *(reference.significance for reference in memory.evidence),
                ],
                forbidden_terms,
            )
        )
        return self._finalize_stage_issues(issues, forbidden_terms)

    def validate_perspective_stage(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        perspectives: list[PlayerPerspective],
        *,
        forbidden_terms: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Validate perspectives before they are sent to the quest stage."""

        issues = self._validate_perspective_structure(pack, perspectives)
        input_event_ids = {event.event_id for event in pack.match_events}
        memory_event_ids = {reference.event_id for reference in memory.evidence}
        canonical_by_player = (
            {
                perspective.player_id: perspective
                for perspective in PerspectiveAgent().create(pack, memory)
            }
            if memory_event_ids <= input_event_ids
            else {}
        )
        if not canonical_by_player or any(
            canonical_by_player.get(perspective.player_id) is None
            or perspective.message != canonical_by_player[perspective.player_id].message
            or perspective.evidence_event_ids
            != canonical_by_player[perspective.player_id].evidence_event_ids
            for perspective in perspectives
        ):
            issues.append(
                self._error(
                    "noncanonical_perspective_facts",
                    "Perspective facts must use the closed player-specific renderer.",
                )
            )
        segments = [
            _FactualSegment(
                perspective.message,
                tuple(dict.fromkeys(perspective.evidence_event_ids)),
                speaker_player_id=perspective.player_id,
            )
            for perspective in perspectives
        ]
        issues.extend(
            self._validate_generated_language(pack, segments, forbidden_terms=forbidden_terms)
        )
        issues.extend(
            self._structured_privacy_issues(
                [
                    value
                    for perspective in perspectives
                    for value in (
                        perspective.player_id,
                        perspective.display_name,
                        perspective.message,
                        *perspective.evidence_event_ids,
                    )
                ],
                forbidden_terms,
            )
        )
        return self._finalize_stage_issues(issues, forbidden_terms)

    def validate_perspectives_stage(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        perspectives: list[PlayerPerspective],
        *,
        forbidden_terms: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Compatibility alias for callers using the plural stage name."""

        return self.validate_perspective_stage(
            pack,
            memory,
            perspectives,
            forbidden_terms=forbidden_terms,
        )

    def stage_failure_report(self, issues: list[ValidationIssue]) -> ValidationReport:
        """Create the fail-closed report used when an intermediate stage is rejected."""

        issues = self._deduplicate_issues(issues)
        has_errors = any(issue.severity == IssueSeverity.ERROR for issue in issues)
        return ValidationReport(
            passed=not has_errors,
            human_review_required=has_errors,
            scores=self._empty_scores(),
            issues=issues,
        )

    def validate_quest_stage(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        quest: NextChapter,
        *,
        forbidden_terms: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Validate a quest's rule semantics and generated wording."""

        issues = self._validate_quest_rules(
            pack, {item.event_id for item in memory.evidence}, quest
        )
        issues.extend(
            issue
            for objective in quest.objectives
            for issue in self._validate_objective_description(pack, objective)
        )
        quest_ids = tuple(
            dict.fromkeys(
                event_id
                for objective in quest.objectives
                for event_id in objective.source_event_ids
            )
        )
        memory_ids = tuple(item.event_id for item in memory.evidence)
        shared_ids = tuple(dict.fromkeys((*quest_ids, *memory_ids)))
        safe_title = quest.title.replace(memory.title, "the selected memory")
        safe_mission = quest.mission.replace(memory.title, "the selected memory")
        segments = [
            _FactualSegment(
                safe_title,
                shared_ids,
                allow_all_opted_in_players=True,
                bind_action_roles=False,
            ),
            _FactualSegment(
                safe_mission,
                shared_ids,
                allow_all_opted_in_players=True,
                bind_action_roles=False,
            ),
            *(
                _FactualSegment(
                    objective.description,
                    tuple(objective.source_event_ids),
                    extra_numbers=self._numeric_rule_targets(objective),
                    allow_all_opted_in_players=True,
                    bind_action_roles=False,
                )
                for objective in quest.objectives
            ),
        ]
        issues.extend(
            self._validate_generated_language(
                pack,
                segments,
                forbidden_terms=forbidden_terms,
            )
        )
        issues.extend(
            self._structured_privacy_issues(
                [
                    quest.title,
                    quest.mission,
                    quest.recipe.value,
                    *(
                        value
                        for objective in quest.objectives
                        for value in (
                            objective.objective_id,
                            objective.description,
                            objective.assigned_player_id or "",
                            objective.verification.metric,
                            objective.verification.operator,
                            str(objective.verification.target),
                            *objective.source_event_ids,
                        )
                    ),
                ],
                forbidden_terms,
            )
        )
        return self._finalize_stage_issues(issues, forbidden_terms)

    def validate(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        perspectives: list[PlayerPerspective],
        quest: NextChapter,
        *,
        forbidden_terms: set[str] | None = None,
    ) -> ValidationReport:
        issues = [
            *self.validate_memory_stage(pack, memory, forbidden_terms=forbidden_terms),
            *self.validate_perspective_stage(
                pack,
                memory,
                perspectives,
                forbidden_terms=forbidden_terms,
            ),
            *self.validate_quest_stage(
                pack,
                memory,
                quest,
                forbidden_terms=forbidden_terms,
            ),
        ]
        issues = self._deduplicate_issues(issues)
        input_event_ids = {event.event_id for event in pack.match_events}
        memory_event_ids = {item.event_id for item in memory.evidence}
        perspective_evidence = {
            event_id for item in perspectives for event_id in item.evidence_event_ids
        }

        meaning_confirmed = pack.meaning_status == MeaningStatus.CONFIRMED
        source_verified = pack.source_status == SourceStatus.VERIFIED
        if not source_verified:
            issues.append(
                ValidationIssue(
                    code="source_verification_required",
                    severity=IssueSeverity.WARNING,
                    message="A player must verify the source before re-engagement use.",
                )
            )
        if not meaning_confirmed:
            issues.append(
                ValidationIssue(
                    code="human_confirmation_required",
                    severity=IssueSeverity.WARNING,
                    message="A player must confirm this candidate before re-engagement use.",
                )
            )

        quest_source_ids = {
            event_id for objective in quest.objectives for event_id in objective.source_event_ids
        }
        evidence_references = memory_event_ids | perspective_evidence | quest_source_ids
        valid_references = evidence_references.intersection(input_event_ids)
        grounding_score = len(valid_references) / max(len(evidence_references), 1)
        quest_connection = len(quest_source_ids.intersection(memory_event_ids)) / max(
            len(memory_event_ids), 1
        )
        specificity = min(len(quest.objectives) / 3, 1.0)
        normalized_messages = {item.message.strip().lower() for item in perspectives}
        distinctness = len(normalized_messages) / max(len(perspectives), 1)

        has_errors = any(issue.severity == IssueSeverity.ERROR for issue in issues)
        return ValidationReport(
            passed=not has_errors,
            human_review_required=not source_verified or not meaning_confirmed or has_errors,
            scores=QualityScores(
                specificity=round(specificity, 2),
                evidence_grounding=round(grounding_score, 2),
                perspective_distinctness=round(distinctness, 2),
                quest_connection=round(min(quest_connection, 1.0), 2),
            ),
            issues=issues,
        )

    def _validate_memory_evidence(
        self, pack: MemoryPack, memory: MemoryRecord
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        event_by_id = {event.event_id: event for event in pack.match_events}
        input_event_ids = set(event_by_id)
        memory_evidence_ids = [item.event_id for item in memory.evidence]
        memory_event_ids = set(memory_evidence_ids)

        if len(memory_evidence_ids) != len(memory_event_ids):
            issues.append(
                self._error(
                    "duplicate_memory_evidence",
                    "A memory may cite each source event only once.",
                )
            )

        unknown_memory_evidence = memory_event_ids - input_event_ids
        if unknown_memory_evidence:
            issues.append(
                self._error(
                    "ungrounded_memory_evidence",
                    f"Memory cites unknown event IDs: {sorted(unknown_memory_evidence)}",
                )
            )
        for reference in memory.evidence:
            event = event_by_id.get(reference.event_id)
            if event and reference.event_type != event.type:
                issues.append(
                    self._error(
                        "memory_event_type_mismatch",
                        f"{reference.event_id} is {event.type}, not {reference.event_type}.",
                    )
                )
        return issues

    def _validate_perspective_structure(
        self, pack: MemoryPack, perspectives: list[PlayerPerspective]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        input_event_ids = {event.event_id for event in pack.match_events}
        opted_in_members = {
            member.player_id: member.display_name
            for member in pack.squad.members
            if member.opted_in
        }

        perspective_ids = [item.player_id for item in perspectives]
        perspective_counts = Counter(perspective_ids)
        duplicates = sorted(
            player_id for player_id, count in perspective_counts.items() if count > 1
        )
        if duplicates:
            issues.append(
                self._error(
                    "duplicate_player_perspective",
                    f"Players received more than one perspective: {duplicates}",
                )
            )
        perspective_member_ids = set(perspective_ids)
        expected_member_ids = set(opted_in_members)
        missing_perspectives = expected_member_ids - perspective_member_ids
        extra_perspectives = perspective_member_ids - expected_member_ids
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
        for perspective in perspectives:
            expected_name = opted_in_members.get(perspective.player_id)
            if expected_name and perspective.display_name != expected_name:
                issues.append(
                    self._error(
                        "perspective_display_name_mismatch",
                        f"Display name for {perspective.player_id} does not match the safe roster.",
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
        if len(normalized_messages) / max(len(perspectives), 1) < 1.0:
            issues.append(
                self._error(
                    "duplicate_perspective_message",
                    "Every opted-in player must receive distinct perspective text.",
                )
            )
        return issues

    def _validate_generated_language(
        self,
        pack: MemoryPack,
        segments: list[_FactualSegment],
        *,
        forbidden_terms: set[str] | None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        generated_text = " ".join(segment.text for segment in segments)
        lowered_text = generated_text.casefold()

        used_relationship_terms = self._terms_in_text(
            lowered_text, self.unsupported_relationship_terms
        )
        if used_relationship_terms:
            issues.append(
                self._error(
                    "unsupported_relationship_claim",
                    f"Unsupported relationship language found: {used_relationship_terms}",
                )
            )

        emotional_or_intent_terms = self._terms_in_text(
            lowered_text,
            self.unsupported_emotional_terms | self.unsupported_intent_terms,
        )
        if emotional_or_intent_terms:
            issues.append(
                self._error(
                    "unsupported_emotional_claim",
                    "Generated text asserts unobserved emotion, knowledge, or intent: "
                    f"{emotional_or_intent_terms}",
                )
            )

        unsupported_actions = self._terms_in_text(lowered_text, self.unsupported_action_terms)
        if unsupported_actions:
            issues.append(
                self._error(
                    "unsupported_action_claim",
                    f"Generated text asserts actions absent from telemetry: {unsupported_actions}",
                )
            )

        leaked_terms = sorted(
            term
            for term in (forbidden_terms or set())
            if term and self._contains_phrase(generated_text, term)
        )
        if leaked_terms:
            issues.append(
                self._error(
                    "opted_out_identity_leak",
                    "Generated content contains an opted-out identity.",
                )
            )

        issues.extend(self._validate_factual_segments(pack, segments))
        return issues

    def _validate_factual_segments(
        self,
        pack: MemoryPack,
        segments: list[_FactualSegment],
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        event_by_id = {event.event_id: event for event in pack.match_events}
        unknown_numbers: set[float] = set()
        unknown_locations: set[str] = set()
        unsupported_players: set[str] = set()
        unknown_players: set[str] = set()
        action_mismatches: set[str] = set()
        unsupported_subject_actions: set[str] = set()
        unsupported_subject_states: set[str] = set()
        opted_in_ids = {member.player_id for member in pack.squad.members if member.opted_in}
        known_names = {member.display_name.casefold() for member in pack.squad.members}

        for segment in segments:
            if not segment.validate_facts:
                continue
            factual_text = self._strip_quoted_context(segment.text)
            cited_events = [
                event_by_id[event_id] for event_id in segment.event_ids if event_id in event_by_id
            ]
            allowed_numbers = self._event_numbers(cited_events) | set(segment.extra_numbers)
            numeric_text = factual_text
            for literal in [
                *(member.display_name for member in pack.squad.members),
                pack.match.map_name,
                *(event.location for event in cited_events),
            ]:
                if literal:
                    numeric_text = re.sub(
                        self._phrase_pattern(literal),
                        " grounded label ",
                        numeric_text,
                        flags=re.IGNORECASE,
                    )
            claimed_numbers = {
                float(value) for value in re.findall(r"(?<![\w])-?\d+(?:\.\d+)?", numeric_text)
            }
            unknown_numbers.update(claimed_numbers - allowed_numbers)

            allowed_locations = {
                self._normalize_phrase(location)
                for location in [
                    pack.match.map_name,
                    *(event.location for event in cited_events),
                ]
                if location
            } | {self._normalize_phrase(item) for item in self.generic_location_phrases}
            for claim in self._location_claims(factual_text):
                normalized_claim = self._normalize_phrase(claim)
                without_quest_suffix = re.sub(r"\s+(?:ii|iii|iv)$", "", normalized_claim)
                if (
                    normalized_claim not in allowed_locations
                    and without_quest_suffix not in allowed_locations
                ):
                    unknown_locations.add(claim)

            involved_ids = {
                player_id
                for event in cited_events
                for player_id in (event.actor_id, event.target_id)
                if player_id
            }
            for member in pack.squad.members:
                if not self._contains_phrase(factual_text, member.display_name):
                    continue
                if segment.allow_all_opted_in_players and member.player_id in opted_in_ids:
                    continue
                if member.player_id not in involved_ids:
                    unsupported_players.add(member.display_name)

            unknown_players.update(self._unknown_claimed_players(factual_text, known_names))

            cited_event_types = {event.type for event in cited_events}
            for required_event_type, patterns in self.event_action_patterns.items():
                if required_event_type in cited_event_types:
                    continue
                if any(re.search(pattern, factual_text, re.IGNORECASE) for pattern in patterns):
                    action_mismatches.add(required_event_type)

            unsupported, attribution, unsupported_states = self._validate_source_action_claims(
                pack,
                factual_text,
                cited_events,
                speaker_player_id=segment.speaker_player_id,
                bind_roles=segment.bind_action_roles,
            )
            unsupported_subject_actions.update(unsupported)
            action_mismatches.update(attribution)
            unsupported_subject_states.update(unsupported_states)

        if unknown_numbers:
            issues.append(
                self._error(
                    "unsupported_numeric_claim",
                    "Factual text contains numbers absent from its evidence: "
                    f"{sorted(unknown_numbers)}",
                )
            )
        if unknown_locations:
            issues.append(
                self._error(
                    "unsupported_location_claim",
                    "Factual text names locations absent from its evidence: "
                    f"{sorted(unknown_locations)}",
                )
            )
        if unsupported_players:
            issues.append(
                self._error(
                    "unsupported_player_claim",
                    "Factual text names players without permitted cited involvement: "
                    f"{sorted(unsupported_players)}",
                )
            )
        if unknown_players:
            issues.append(
                self._error(
                    "unknown_player_claim",
                    f"Factual text contains unknown named actors: {sorted(unknown_players)}",
                )
            )
        if action_mismatches:
            issues.append(
                self._error(
                    "event_action_mismatch",
                    "Factual action language requires uncited event types: "
                    f"{sorted(action_mismatches)}",
                )
            )
        if unsupported_subject_actions:
            issues.append(
                self._error(
                    "unsupported_action_claim",
                    "Generated text uses an action outside the grounded action vocabulary.",
                )
            )
        if unsupported_subject_states:
            issues.append(
                self._error(
                    "unsupported_emotional_claim",
                    "Generated text assigns an unverified state, relationship, or interpretation.",
                )
            )
        return issues

    def _validate_quest_rules(
        self, pack: MemoryPack, memory_event_ids: set[str], quest: NextChapter
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        input_event_ids = {event.event_id for event in pack.match_events}
        event_by_id = {event.event_id: event for event in pack.match_events}
        opted_in_ids = {member.player_id for member in pack.squad.members if member.opted_in}
        known_ids = {member.player_id for member in pack.squad.members}

        objective_ids = [objective.objective_id for objective in quest.objectives]
        if len(objective_ids) != len(set(objective_ids)):
            issues.append(
                self._error("duplicate_quest_objective", "Quest objective IDs must be unique.")
            )
        if len(quest.objectives) < 2:
            issues.append(
                self._error(
                    "insufficient_quest_objectives",
                    "A Next Chapter requires at least two grounded objectives.",
                )
            )
        elif len(quest.objectives) < 3:
            issues.append(
                ValidationIssue(
                    code="weak_quest_specificity",
                    severity=IssueSeverity.WARNING,
                    message="A strong Next Chapter should contain three squad-specific anchors.",
                )
            )

        quest_source_ids: set[str] = set()
        for objective in quest.objectives:
            if len(objective.source_event_ids) != len(set(objective.source_event_ids)):
                issues.append(
                    self._error(
                        "duplicate_quest_evidence",
                        f"Objective {objective.objective_id!r} repeats a source event.",
                    )
                )
            source_ids = set(objective.source_event_ids)
            quest_source_ids.update(source_ids)
            unknown_sources = source_ids - input_event_ids
            if unknown_sources:
                issues.append(
                    self._error(
                        "ungrounded_quest_evidence",
                        f"Quest cites unknown event IDs: {sorted(unknown_sources)}",
                    )
                )
            if objective.assigned_player_id not in {None, *opted_in_ids}:
                issues.append(
                    self._error(
                        "invalid_quest_assignee",
                        "Quest objectives may only be assigned to opted-in squad members.",
                    )
                )

            cited_events = [event_by_id[event_id] for event_id in source_ids & input_event_ids]
            issues.extend(
                self._validate_verification_rule(
                    pack,
                    objective,
                    cited_events,
                    opted_in_ids=opted_in_ids,
                    known_ids=known_ids,
                )
            )

        if not quest_source_ids.intersection(memory_event_ids):
            issues.append(
                self._error(
                    "quest_not_connected_to_memory",
                    "The quest must cite at least one event used by the discovered memory.",
                )
            )
        return issues

    def _validate_source_action_claims(
        self,
        pack: MemoryPack,
        text: str,
        events: list[MatchEvent],
        *,
        speaker_player_id: str | None,
        bind_roles: bool,
    ) -> tuple[set[str], set[str], set[str]]:
        """Validate a deliberately small, closed vocabulary of player action clauses."""

        display_to_id = {
            member.display_name.casefold(): member.player_id for member in pack.squad.members
        }
        subject_labels = sorted(
            [member.display_name for member in pack.squad.members] + ["You"],
            key=len,
            reverse=True,
        )
        subject_pattern = "|".join(re.escape(label) for label in subject_labels)
        action_event_types = {
            "called": "retreat_ping",
            "calls": "retreat_ping",
            "chose": "retreat_ping",
            "chooses": "retreat_ping",
            "defeated": "elimination",
            "defeats": "elimination",
            "drove": "vehicle_escape",
            "drives": "vehicle_escape",
            "eliminated": "elimination",
            "eliminates": "elimination",
            "killed": "elimination",
            "kills": "elimination",
            "knocked": "knockdown",
            "rescued": "revive",
            "rescues": "revive",
            "revived": "revive",
            "revives": "revive",
            "shot": "elimination",
            "shoots": "elimination",
            "survived": "final_zone_survival",
            "survives": "final_zone_survival",
        }
        unsupported: set[str] = set()
        mismatches: set[str] = set()
        unsupported_states: set[str] = set()

        for match in re.finditer(
            rf"(?:^|[.!?]\s+|,\s*|\b(?:before|after|when|where|while)\s+)"
            rf"(?P<subject>{subject_pattern})\s+(?P<verb>[A-Za-z]+)\b",
            text,
            re.IGNORECASE,
        ):
            subject_label = match.group("subject")
            subject_id = (
                speaker_player_id
                if subject_label.casefold() == "you"
                else display_to_id.get(subject_label.casefold())
            )
            verb = match.group("verb").casefold()
            tail = text[match.end() : match.end() + 120]

            if verb == "and":
                continue
            if verb in {"was", "were", "is", "are"}:
                state_result = self._validate_copular_state(
                    pack,
                    subject_id,
                    tail,
                    events,
                    speaker_player_id=speaker_player_id,
                    bind_roles=bind_roles,
                )
                if state_result == "unsupported":
                    unsupported_states.add(verb)
                elif state_result:
                    mismatches.add(state_result)
                continue
            if verb == "came" and re.match(r"\s+back\s+for\b", tail, re.IGNORECASE):
                event_type = "revive"
            elif verb == "brought" and re.search(r"\bback\b", tail, re.IGNORECASE):
                event_type = "revive"
            elif verb == "became" and re.search(r"\b(?:last|surviving)\b", tail, re.IGNORECASE):
                event_type = "last_player_alive"
            elif verb == "completed" and re.search(
                r"\b(?:vehicle\s+escape|escape|getaway)\b", tail, re.IGNORECASE
            ):
                event_type = "vehicle_escape"
            elif verb == "triggered":
                event_type = None
            else:
                event_type = action_event_types.get(verb)
                if event_type is None:
                    unsupported.add(verb)
                    continue

            if not events:
                mismatches.add(event_type or "actor_event")
                continue
            if event_type is None:
                if bind_roles and subject_id not in {event.actor_id for event in events}:
                    mismatches.add("actor_event")
                continue

            typed_events = [event for event in events if event.type == event_type]
            if not typed_events:
                mismatches.add(event_type)
                continue
            if not bind_roles:
                continue
            if subject_id is None:
                mismatches.add(event_type)
                continue

            target_id = self._first_named_object_id(
                tail,
                pack,
                speaker_player_id=speaker_player_id,
            )
            if event_type in {"revive", "elimination", "knockdown"} and target_id:
                grounded = any(
                    event.actor_id == subject_id and event.target_id == target_id
                    for event in typed_events
                )
            else:
                grounded = any(event.actor_id == subject_id for event in typed_events)
            if not grounded:
                mismatches.add(event_type)

        for match in re.finditer(r"\b(?:and|then)\s+([a-z][a-z'-]*)\b", text):
            verb = match.group(1).casefold()
            if verb in {
                "became",
                "brought",
                "called",
                "completed",
                "drove",
                "eliminated",
                "rescued",
                "revived",
                "remix",
                "survived",
                "triggered",
            }:
                continue
            unsupported.add(verb)

        return unsupported, mismatches, unsupported_states

    def _validate_copular_state(
        self,
        pack: MemoryPack,
        subject_id: str | None,
        tail: str,
        events: list[MatchEvent],
        *,
        speaker_player_id: str | None,
        bind_roles: bool,
    ) -> str | None:
        normalized = tail.lstrip().casefold()
        if normalized.startswith("part of"):
            return None
        if re.match(r"(?:the\s+)?last\s+(?:squad\s+)?(?:member|player)", normalized):
            if not bind_roles:
                return None
            return (
                None
                if any(
                    event.type == "last_player_alive" and event.actor_id == subject_id
                    for event in events
                )
                else "last_player_alive"
            )
        if normalized.startswith("revived"):
            if not bind_roles:
                return None
            actor_id = self._first_named_object_id(
                normalized.split("by", 1)[1] if "by" in normalized else "",
                pack,
                speaker_player_id=speaker_player_id,
            )
            return (
                None
                if any(
                    event.type == "revive"
                    and event.actor_id == actor_id
                    and event.target_id == subject_id
                    for event in events
                )
                else "revive"
            )
        return "unsupported"

    @classmethod
    def _first_named_object_id(
        cls,
        text: str,
        pack: MemoryPack,
        *,
        speaker_player_id: str | None,
    ) -> str | None:
        candidates = sorted(
            [(member.display_name, member.player_id) for member in pack.squad.members]
            + [
                ("you", speaker_player_id),
            ],
            key=lambda item: len(item[0]),
            reverse=True,
        )
        matches = [
            (match.start(), -len(label), player_id)
            for label, player_id in candidates
            if player_id
            for match in [re.search(cls._phrase_pattern(label), text, re.IGNORECASE)]
            if match is not None
        ]
        return min(matches)[2] if matches else None

    @staticmethod
    def _strip_quoted_context(text: str) -> str:
        return re.sub(r'["“][^"”]*["”]', " quoted memory ", text)

    def _validate_verification_rule(
        self,
        pack: MemoryPack,
        objective: QuestObjective,
        events: list[MatchEvent],
        *,
        opted_in_ids: set[str],
        known_ids: set[str],
    ) -> list[ValidationIssue]:
        rule = objective.verification
        metric = rule.metric
        issues: list[ValidationIssue] = []

        if metric == "squad_member_ids":
            target_ids = self._string_list(rule.target)
            issues.extend(self._quest_target_issues(target_ids, known_ids, opted_in_ids))
            if (
                rule.operator != "contains_all"
                or target_ids is None
                or len(target_ids) != len(set(target_ids))
                or set(target_ids) != opted_in_ids
                or not events
            ):
                issues.append(
                    self._unsupported_rule(
                        objective,
                        "squad_member_ids requires contains_all and the complete opted-in roster",
                    )
                )
            return issues

        if metric == "visited_locations":
            target_locations = self._string_list(rule.target)
            allowed_locations = {
                self._normalize_phrase(location)
                for location in [pack.match.map_name, *(event.location for event in events)]
                if location
            }
            if (
                rule.operator != "contains_all"
                or not target_locations
                or len(target_locations) != len(set(target_locations))
                or not events
                or any(
                    self._normalize_phrase(location) not in allowed_locations
                    for location in target_locations
                )
            ):
                issues.append(
                    self._unsupported_rule(
                        objective,
                        "visited_locations requires cited map or event locations",
                    )
                )
            return issues

        revive_match = re.fullmatch(r"revives\.([^.]+)\.targets", metric)
        if revive_match:
            actor_id = revive_match.group(1)
            target_ids = self._string_list(rule.target)
            issues.extend(
                self._quest_target_issues([actor_id, *(target_ids or [])], known_ids, opted_in_ids)
            )
            cited_pairs = {
                frozenset((event.actor_id, event.target_id))
                for event in events
                if event.type == "revive" and event.actor_id and event.target_id
            }
            targets_trace_to_pairs = bool(target_ids) and all(
                frozenset((actor_id, target_id)) in cited_pairs for target_id in target_ids
            )
            if (
                rule.operator != "contains_all"
                or not target_ids
                or len(target_ids) != len(set(target_ids))
                or any(event.type != "revive" for event in events)
                or not events
                or not targets_trace_to_pairs
                or objective.assigned_player_id not in {None, actor_id}
            ):
                issues.append(
                    self._unsupported_rule(
                        objective,
                        "revive rules require cited revive participants and contains_all",
                    )
                )
            return issues

        escape_match = re.fullmatch(r"vehicle_escape\.([^.]+)\.passengers", metric)
        if escape_match:
            driver_id = escape_match.group(1)
            issues.extend(self._quest_target_issues([driver_id], known_ids, opted_in_ids))
            passenger_targets = {
                passenger_target
                for event in events
                if event.type == "vehicle_escape"
                for passenger_target in [literal_passenger_target(event)]
                if passenger_target is not None
            }
            numeric_target = isinstance(rule.target, (int, float)) and not isinstance(
                rule.target, bool
            )
            if (
                rule.operator != "at_least"
                or not numeric_target
                or float(rule.target) not in {float(value) for value in passenger_targets}
                or any(event.type != "vehicle_escape" for event in events)
                or not events
                or driver_id not in {event.actor_id for event in events}
                or objective.assigned_player_id not in {None, driver_id}
            ):
                issues.append(
                    self._unsupported_rule(
                        objective,
                        "vehicle escape rules require the cited opted-in driver "
                        "and passenger count",
                    )
                )
            return issues

        if metric == "initial_route_caller_id":
            target_id = rule.target if isinstance(rule.target, str) else None
            issues.extend(
                self._quest_target_issues(
                    [target_id] if target_id is not None else None,
                    known_ids,
                    opted_in_ids,
                )
            )
            if (
                rule.operator != "equals"
                or target_id is None
                or any(event.type != "retreat_ping" for event in events)
                or not events
                or target_id not in {event.actor_id for event in events}
                or objective.assigned_player_id not in {None, target_id}
            ):
                issues.append(
                    self._unsupported_rule(
                        objective,
                        "route caller rules require the cited opted-in retreat caller",
                    )
                )
            return issues

        issues.append(self._unsupported_rule(objective, f"unknown metric {metric!r}"))
        return issues

    def _validate_objective_description(
        self,
        pack: MemoryPack,
        objective: QuestObjective,
    ) -> list[ValidationIssue]:
        """Require one closed, deterministic wording template per verification rule."""

        metric = objective.verification.metric
        target = objective.verification.target
        roster = {member.player_id: member.display_name for member in pack.squad.members}
        event_by_id = {event.event_id: event for event in pack.match_events}
        events = [
            event_by_id[event_id]
            for event_id in objective.source_event_ids
            if event_id in event_by_id
        ]
        expected: str | None = None

        if metric == "squad_member_ids":
            expected = "Complete a match with the opted-in members of the original squad."
        elif metric == "visited_locations":
            locations = self._string_list(target)
            if locations and len(locations) == 1:
                expected = f"Return to {locations[0]} during the new match."
        else:
            revive_match = re.fullmatch(r"revives\.([^.]+)\.targets", metric)
            escape_match = re.fullmatch(r"vehicle_escape\.([^.]+)\.passengers", metric)
            if revive_match:
                actor_id = revive_match.group(1)
                target_ids = self._string_list(target)
                if actor_id in roster and target_ids and len(target_ids) == 1:
                    target_id = target_ids[0]
                    if target_id in roster:
                        expected = (
                            f"{roster[actor_id]} revives {roster[target_id]}, "
                            "reversing the original roles."
                        )
            elif escape_match:
                driver_id = escape_match.group(1)
                escape_event = next(
                    (
                        event
                        for event in events
                        if event.type == "vehicle_escape" and event.actor_id == driver_id
                    ),
                    None,
                )
                if (
                    driver_id in roster
                    and isinstance(target, (int, float))
                    and not isinstance(target, bool)
                    and escape_event is not None
                ):
                    expected = (
                        f"{roster[driver_id]} drives at least {target} teammates out of "
                        f"{escape_event.location or 'danger'}."
                    )
            elif metric == "initial_route_caller_id":
                if isinstance(target, str) and target in roster:
                    expected = f"{roster[target]} chooses the squad's first rotation route."

        if expected is not None and objective.description == expected:
            return []
        return [
            self._error(
                "quest_description_rule_mismatch",
                "Quest objective wording does not describe its verification rule.",
            )
        ]

    def _quest_target_issues(
        self,
        target_ids: list[str] | None,
        known_ids: set[str],
        opted_in_ids: set[str],
    ) -> list[ValidationIssue]:
        if target_ids is None:
            return []
        unknown = sorted(set(target_ids) - known_ids)
        opted_out = sorted((set(target_ids) & known_ids) - opted_in_ids)
        if not unknown and not opted_out:
            return []
        return [
            self._error(
                "invalid_quest_target",
                "Quest verification may reference only opted-in squad members"
                + (f"; unknown={unknown}" if unknown else "")
                + (f"; opted_out={opted_out}" if opted_out else "")
                + ".",
            )
        ]

    @classmethod
    def _structured_privacy_issues(
        cls,
        values: list[str],
        forbidden_terms: set[str] | None,
    ) -> list[ValidationIssue]:
        if any(
            term and cls._contains_phrase(value, term)
            for value in values
            for term in (forbidden_terms or set())
        ):
            return [
                cls._error(
                    "opted_out_identity_leak",
                    "Generated content contains an opted-out identity.",
                )
            ]
        return []

    @classmethod
    def _finalize_stage_issues(
        cls,
        issues: list[ValidationIssue],
        forbidden_terms: set[str] | None,
    ) -> list[ValidationIssue]:
        """Deduplicate issues and scrub any model-echoed private identity from messages."""

        safe_issues = []
        for issue in issues:
            message = issue.message
            if any(
                term and cls._contains_phrase(message, term) for term in (forbidden_terms or set())
            ):
                message = "Generated content failed a grounded privacy or evidence rule."
            safe_issues.append(issue.model_copy(update={"message": message}))
        return cls._deduplicate_issues(safe_issues)

    @classmethod
    def _unknown_claimed_players(cls, text: str, known_names: set[str]) -> set[str]:
        proper_name = r"[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*){0,2}"
        subjects = re.findall(
            rf"(?<![\w])({proper_name})\s+(?=(?:{cls._claim_verbs})\b)",
            text,
        )
        objects = re.findall(
            rf"\b(?:{cls._claim_verbs})\s+({proper_name})(?=\b|[,.!?])",
            text,
        )
        candidates = {cls._normalize_phrase(name) for name in [*subjects, *objects]}
        return {
            name
            for name in candidates
            if name not in known_names and name not in cls._generic_claim_subjects
        }

    @staticmethod
    def _location_claims(text: str) -> set[str]:
        return {
            match.group(1).strip().rstrip(".,")
            for match in re.finditer(
                r"\b(?:At|at|In|in|To|to|From|from|Through|through|Near|near|"
                r"Inside|inside|Outside|outside|Around|around|Across|across|"
                r"Out\s+of|out\s+of)\s+"
                r"([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*)",
                text,
            )
        }

    @staticmethod
    def _event_numbers(events: list[MatchEvent]) -> set[float]:
        values: set[float] = set()
        for event in events:
            if event.timestamp_seconds is not None:
                values.add(float(event.timestamp_seconds))
            values.update(
                float(value)
                for key, value in event.details.items()
                if key in SAFE_DETAIL_KEYS
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            )
        return values

    @staticmethod
    def _numeric_rule_targets(objective: QuestObjective) -> tuple[float, ...]:
        target = objective.verification.target
        if isinstance(target, (int, float)) and not isinstance(target, bool):
            return (float(target),)
        return ()

    @staticmethod
    def _string_list(value: Any) -> list[str] | None:
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) for item in value)
        ):
            return None
        return value

    @classmethod
    def _terms_in_text(cls, lowered_text: str, terms: set[str]) -> list[str]:
        return sorted(term for term in terms if cls._contains_phrase(lowered_text, term))

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        return bool(re.search(ValidatorAgent._phrase_pattern(phrase), text, re.IGNORECASE))

    @staticmethod
    def _phrase_pattern(phrase: str) -> str:
        return identity_pattern(phrase)

    @staticmethod
    def _normalize_phrase(value: str) -> str:
        return " ".join(value.casefold().split())

    def _unsupported_rule(self, objective: QuestObjective, reason: str) -> ValidationIssue:
        return self._error(
            "unsupported_verification_rule",
            f"Objective {objective.objective_id!r}: {reason}.",
        )

    @staticmethod
    def _deduplicate_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
        unique: list[ValidationIssue] = []
        seen: set[tuple[str, str, IssueSeverity]] = set()
        for issue in issues:
            key = (issue.code, issue.message, issue.severity)
            if key not in seen:
                unique.append(issue)
                seen.add(key)
        return unique

    @staticmethod
    def _empty_scores() -> QualityScores:
        return QualityScores(
            specificity=0.0,
            evidence_grounding=1.0,
            perspective_distinctness=0.0,
            quest_connection=0.0,
        )

    @staticmethod
    def _error(code: str, message: str) -> ValidationIssue:
        return ValidationIssue(code=code, severity=IssueSeverity.ERROR, message=message)
