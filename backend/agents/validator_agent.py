"""Deterministic grounding, personalization, quest, and safety checks."""

from __future__ import annotations

import re
from collections import Counter

from backend.models.schemas import (
    DiscoveryAssessment,
    IssueSeverity,
    MatchEvent,
    MemoryPack,
    MemoryRecord,
    NextChapter,
    PlayerPerspective,
    QualityScores,
    QuestObjective,
    ValidationIssue,
    ValidationReport,
)
from backend.services.text import truncate_text


class ValidatorAgent:
    unsupported_relationship_terms = {
        "best friend",
        "soulmate",
        "closest friend",
        "like family",
    }
    unsafe_quest_terms = {
        "attack your teammate",
        "deliberately lose",
        "deliberately losing",
        "friendly fire",
        "intentionally lose",
        "intentionally losing",
        "kill your teammate",
        "lose on purpose",
        "self harm",
        "shoot a teammate",
        "shoot your teammate",
        "suicide",
        "team kill",
        "teamkill",
        "throw the match",
    }

    def abstention_report(
        self, assessment: DiscoveryAssessment, pack: MemoryPack
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        if not pack.match_events:
            issues.append(
                ValidationIssue(
                    code="missing_grounded_gameplay",
                    severity=IssueSeverity.INFO,
                    message=(
                        "Generation was safely skipped because no grounded gameplay event "
                        "is available as evidence."
                    ),
                )
            )
        if sum(member.opted_in for member in pack.squad.members) < 2:
            issues.append(
                ValidationIssue(
                    code="insufficient_opted_in_members",
                    severity=IssueSeverity.INFO,
                    message=(
                        "Generation was safely skipped because a squad memory requires at "
                        "least two opted-in members."
                    ),
                )
            )
        if assessment.signal_score < assessment.threshold:
            issues.append(
                ValidationIssue(
                    code="insufficient_memory_signal",
                    severity=IssueSeverity.INFO,
                    message=(
                        f"Signal score {assessment.signal_score:.2f} is below the "
                        f"{assessment.threshold:.2f} threshold; generation was safely skipped."
                    ),
                )
            )
        if not issues:
            issues.append(
                ValidationIssue(
                    code="generation_safely_skipped",
                    severity=IssueSeverity.INFO,
                    message="Generation was safely skipped by the deterministic discovery gate.",
                )
            )

        return ValidationReport(
            passed=True,
            human_review_required=False,
            scores=QualityScores(
                specificity=0.0,
                evidence_grounding=1.0,
                perspective_distinctness=0.0,
                quest_connection=0.0,
            ),
            issues=issues,
        )

    def validate(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        perspectives: list[PlayerPerspective],
        quest: NextChapter,
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        input_events = {event.event_id: event for event in pack.match_events}
        input_event_ids = set(input_events)
        memory_event_id_list = [item.event_id for item in memory.evidence]
        memory_event_ids = set(memory_event_id_list)
        opted_in_members = {
            member.player_id: member for member in pack.squad.members if member.opted_in
        }
        opted_in_ids = set(opted_in_members)

        unknown_memory_evidence = memory_event_ids - input_event_ids
        if unknown_memory_evidence:
            issues.append(
                self._error(
                    "ungrounded_memory_evidence",
                    f"Memory cites unknown event IDs: {sorted(unknown_memory_evidence)}",
                )
            )

        duplicate_memory_evidence = sorted(
            event_id for event_id, count in Counter(memory_event_id_list).items() if count > 1
        )
        if duplicate_memory_evidence:
            issues.append(
                self._error(
                    "duplicate_memory_evidence",
                    f"Memory cites event IDs more than once: {duplicate_memory_evidence}",
                )
            )

        mismatched_event_types = sorted(
            evidence.event_id
            for evidence in memory.evidence
            if evidence.event_id in input_events
            and evidence.event_type != input_events[evidence.event_id].type
        )
        if mismatched_event_types:
            issues.append(
                self._error(
                    "memory_evidence_type_mismatch",
                    "Memory evidence event types do not match the input for: "
                    f"{mismatched_event_types}",
                )
            )

        perspective_counts = Counter(item.player_id for item in perspectives)
        perspective_member_ids = set(perspective_counts)
        missing_perspectives = opted_in_ids - perspective_member_ids
        extra_perspectives = perspective_member_ids - opted_in_ids
        duplicate_perspectives = sorted(
            player_id for player_id, count in perspective_counts.items() if count > 1
        )
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
        if duplicate_perspectives:
            issues.append(
                self._error(
                    "duplicate_player_perspective",
                    "Exactly one perspective is allowed per opted-in player; duplicates found "
                    f"for: {duplicate_perspectives}",
                )
            )

        mismatched_display_names = sorted(
            item.player_id
            for item in perspectives
            if item.player_id in opted_in_members
            and item.display_name != opted_in_members[item.player_id].display_name
        )
        if mismatched_display_names:
            issues.append(
                self._error(
                    "perspective_display_name_mismatch",
                    "Perspective display names do not match the squad record for: "
                    f"{mismatched_display_names}",
                )
            )

        empty_perspective_evidence = sorted(
            item.player_id for item in perspectives if not item.evidence_event_ids
        )
        if empty_perspective_evidence:
            issues.append(
                self._error(
                    "missing_perspective_evidence",
                    "Perspectives require at least one evidence event for: "
                    f"{empty_perspective_evidence}",
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
        disconnected_perspective_evidence = (
            perspective_evidence & input_event_ids
        ) - memory_event_ids
        if disconnected_perspective_evidence:
            issues.append(
                self._error(
                    "perspective_not_connected_to_memory",
                    "Perspectives cite input events outside the discovered memory: "
                    f"{sorted(disconnected_perspective_evidence)}",
                )
            )

        display_names = [member.display_name for member in pack.squad.members]
        normalized_messages = {
            self._perspective_template(item.message, display_names) for item in perspectives
        }
        distinctness = len(normalized_messages) / max(len(perspectives), 1)
        if distinctness < 1.0:
            issues.append(
                self._error(
                    "duplicate_player_perspective_content",
                    "Every opted-in player must receive a distinct, role-specific perspective.",
                )
            )

        attributed_title = self._attributed_human_title(pack, memory)
        perspective_claims = [
            self._strip_quoted_attribution(item.message, attributed_title) for item in perspectives
        ]
        quest_title_claim = quest.title
        if attributed_title and quest_title_claim.casefold().startswith(
            attributed_title.casefold()
        ):
            quest_title_claim = quest_title_claim[len(attributed_title) :]
        generated_text = " ".join(
            [
                "" if attributed_title else memory.title,
                memory.summary,
                *(item.significance for item in memory.evidence),
                *perspective_claims,
                quest_title_claim,
                self._strip_quoted_attribution(quest.mission, attributed_title),
                *(objective.description for objective in quest.objectives),
            ]
        )
        used_relationship_terms = self._find_terms(
            generated_text,
            self.unsupported_relationship_terms,
        )
        if used_relationship_terms:
            issues.append(
                self._error(
                    "unsupported_relationship_claim",
                    f"Unsupported relationship language found: {used_relationship_terms}",
                )
            )

        unsafe_quest_text = " ".join(
            [
                quest_title_claim,
                self._strip_quoted_attribution(quest.mission, attributed_title),
                *(item.description for item in quest.objectives),
            ]
        )
        unsafe_terms = self._find_unsafe_terms(unsafe_quest_text)
        if unsafe_terms:
            issues.append(
                self._error(
                    "unsafe_quest_instruction",
                    f"Unsafe quest language found: {unsafe_terms}",
                )
            )

        objective_ids = [objective.objective_id for objective in quest.objectives]
        duplicate_objective_ids = sorted(
            objective_id for objective_id, count in Counter(objective_ids).items() if count > 1
        )
        if duplicate_objective_ids:
            issues.append(
                self._error(
                    "duplicate_quest_objective_id",
                    f"Quest objective IDs must be unique: {duplicate_objective_ids}",
                )
            )
        if any(not objective_id.strip() for objective_id in objective_ids):
            issues.append(
                self._error(
                    "invalid_quest_objective_id",
                    "Every quest objective requires a nonblank objective ID.",
                )
            )

        connected_objective_count = 0
        quest_source_ids: set[str] = set()
        specificity_anchors: set[str] = set()
        participant_objectives: list[QuestObjective] = []
        for objective in quest.objectives:
            source_ids = set(objective.source_event_ids)
            quest_source_ids.update(source_ids)
            objective_label = objective.objective_id or "<blank>"

            if not objective.description.strip():
                issues.append(
                    self._error(
                        "invalid_quest_objective_description",
                        f"Quest objective {objective_label!r} requires a nonblank description.",
                    )
                )

            if not source_ids:
                issues.append(
                    self._error(
                        "missing_quest_objective_evidence",
                        f"Quest objective {objective_label!r} has no source event IDs.",
                    )
                )
            unknown_sources = source_ids - input_event_ids
            if unknown_sources:
                issues.append(
                    self._error(
                        "ungrounded_quest_evidence",
                        f"Quest objective {objective_label!r} cites unknown event IDs: "
                        f"{sorted(unknown_sources)}",
                    )
                )
            disconnected_sources = (source_ids & input_event_ids) - memory_event_ids
            if disconnected_sources:
                issues.append(
                    self._error(
                        "quest_objective_not_connected_to_memory",
                        f"Quest objective {objective_label!r} cites events outside the memory: "
                        f"{sorted(disconnected_sources)}",
                    )
                )
            source_is_connected = bool(
                source_ids and not unknown_sources and not disconnected_sources
            )

            assignee_is_valid = not (
                objective.assigned_player_id is not None
                and objective.assigned_player_id not in opted_in_ids
            )
            if not assignee_is_valid:
                issues.append(
                    self._error(
                        "invalid_quest_assignee",
                        f"Quest objective {objective_label!r} is assigned to an unknown or "
                        "opted-out player.",
                    )
                )

            verification_issues, anchor = self._validate_verification(
                objective,
                opted_in_ids,
                input_events,
                pack.match.map_name,
            )
            issues.extend(verification_issues)
            if anchor and not verification_issues:
                specificity_anchors.add(anchor)
                if anchor == "participants":
                    participant_objectives.append(objective)
            if source_is_connected and assignee_is_valid and not verification_issues:
                connected_objective_count += 1

        if len(participant_objectives) != 1:
            issues.append(
                self._error(
                    "invalid_participant_objective_count",
                    "A Next Chapter requires exactly one valid squad reunion objective.",
                )
            )
        elif not participant_objectives[0].required:
            issues.append(
                self._error(
                    "participant_objective_must_be_required",
                    "The squad reunion objective cannot be optional.",
                )
            )

        has_secondary_anchor = bool(specificity_anchors.intersection({"location", "role_action"}))
        if not has_secondary_anchor:
            issues.append(
                self._error(
                    "insufficient_quest_specificity",
                    "A usable Next Chapter needs a grounded location or role action in addition "
                    "to the squad reunion.",
                )
            )
        elif len(specificity_anchors) < 3:
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

        reference_checks = [
            event_id in input_events
            and all(
                item.event_type == input_events[event_id].type
                for item in memory.evidence
                if item.event_id == event_id
            )
            for event_id in memory_event_ids
        ]
        reference_checks.extend(
            event_id in input_event_ids and event_id in memory_event_ids
            for event_id in perspective_evidence
        )
        reference_checks.extend(
            event_id in input_event_ids and event_id in memory_event_ids
            for event_id in quest_source_ids
        )
        grounding_score = sum(reference_checks) / max(len(reference_checks), 1)
        quest_connection = connected_objective_count / max(len(quest.objectives), 1)
        specificity = len(specificity_anchors) / 3

        has_errors = any(issue.severity == IssueSeverity.ERROR for issue in issues)
        return ValidationReport(
            passed=not has_errors,
            human_review_required=not confirmed or has_errors,
            scores=QualityScores(
                specificity=round(min(specificity, 1.0), 2),
                evidence_grounding=round(grounding_score, 2),
                perspective_distinctness=round(distinctness, 2),
                quest_connection=round(quest_connection, 2),
            ),
            issues=issues,
        )

    def _validate_verification(
        self,
        objective: QuestObjective,
        opted_in_ids: set[str],
        input_events: dict[str, MatchEvent],
        match_location: str | None,
    ) -> tuple[list[ValidationIssue], str | None]:
        issues: list[ValidationIssue] = []
        rule = objective.verification
        target = rule.target
        objective_label = objective.objective_id or "<blank>"
        source_events = [
            input_events[event_id]
            for event_id in objective.source_event_ids
            if event_id in input_events
        ]

        if rule.metric == "squad_member_ids":
            if (
                rule.operator != "contains_all"
                or not isinstance(target, list)
                or set(target) != opted_in_ids
                or len(target) != len(set(target))
            ):
                issues.append(
                    self._error(
                        "invalid_squad_verification",
                        f"Quest objective {objective_label!r} must verify every opted-in member.",
                    )
                )
            return issues, "participants"

        if rule.metric == "visited_locations":
            grounded_locations = {
                event.location for event in source_events if event.location is not None
            }
            if match_location:
                grounded_locations.add(match_location)
            normalized_targets = (
                [self._normalize_text(item) for item in target] if isinstance(target, list) else []
            )
            normalized_grounded_locations = {
                self._normalize_text(location) for location in grounded_locations
            }
            valid_target = (
                isinstance(target, list)
                and bool(target)
                and all(isinstance(item, str) and item.strip() for item in target)
                and len(normalized_targets) == len(set(normalized_targets))
                and set(normalized_targets).issubset(normalized_grounded_locations)
            )
            if rule.operator != "contains_all" or not valid_target:
                issues.append(
                    self._error(
                        "invalid_location_verification",
                        f"Quest objective {objective_label!r} has an invalid location rule.",
                    )
                )
            return issues, "location"

        if rule.metric == "initial_route_caller_id":
            grounded_caller = any(
                event.type == "retreat_ping" and event.actor_id == target for event in source_events
            )
            if (
                rule.operator != "equals"
                or not isinstance(target, str)
                or target not in opted_in_ids
                or objective.assigned_player_id != target
                or not grounded_caller
            ):
                issues.append(
                    self._error(
                        "invalid_route_caller_verification",
                        f"Quest objective {objective_label!r} has an invalid route-caller rule.",
                    )
                )
            return issues, "role_action"

        revive_actor = self._metric_subject(rule.metric, "revives.", ".targets")
        if revive_actor is not None:
            target_ids = set(target) if isinstance(target, list) else set()
            valid_targets = (
                isinstance(target, list)
                and bool(target)
                and len(target) == len(target_ids)
                and target_ids.issubset(opted_in_ids)
                and revive_actor not in target_ids
            )
            grounded_revive = valid_targets and all(
                any(
                    event.type == "revive"
                    and (
                        (event.actor_id == revive_actor and event.target_id == target_id)
                        or (event.target_id == revive_actor and event.actor_id == target_id)
                    )
                    for event in source_events
                )
                for target_id in target_ids
            )
            if (
                rule.operator != "contains_all"
                or revive_actor not in opted_in_ids
                or objective.assigned_player_id != revive_actor
                or not valid_targets
                or not grounded_revive
            ):
                issues.append(
                    self._error(
                        "invalid_revive_verification",
                        f"Quest objective {objective_label!r} has an invalid revive rule.",
                    )
                )
            return issues, "role_action"

        driver_id = self._metric_subject(rule.metric, "vehicle_escape.", ".passengers")
        if driver_id is not None:
            numeric_target = (
                isinstance(target, int)
                and not isinstance(target, bool)
                and target >= 1
                and target <= max(len(opted_in_ids) - 1, 0)
            )
            grounded_escape = any(
                event.type == "vehicle_escape" and event.actor_id == driver_id
                for event in source_events
            )
            if (
                rule.operator != "at_least"
                or driver_id not in opted_in_ids
                or objective.assigned_player_id != driver_id
                or not numeric_target
                or not grounded_escape
            ):
                issues.append(
                    self._error(
                        "invalid_vehicle_escape_verification",
                        f"Quest objective {objective_label!r} has an invalid vehicle rule.",
                    )
                )
            return issues, "role_action"

        issues.append(
            self._error(
                "unsupported_verification_metric",
                f"Quest objective {objective_label!r} uses unsupported metric {rule.metric!r}.",
            )
        )
        return issues, None

    @classmethod
    def _find_terms(cls, text: str, terms: set[str]) -> list[str]:
        normalized_text = cls._normalize_text(text)
        return sorted(
            term
            for term in terms
            if re.search(rf"\b{re.escape(cls._normalize_text(term))}\b", normalized_text)
        )

    @staticmethod
    def _attributed_human_title(pack: MemoryPack, memory: MemoryRecord) -> str | None:
        caption = (pack.human_memory.caption or "").strip() if pack.human_memory else ""
        if not caption:
            return None
        expected_title = truncate_text(caption.title(), 100)
        return memory.title if memory.title == expected_title else None

    @staticmethod
    def _strip_quoted_attribution(text: str, attributed_title: str | None) -> str:
        if not attributed_title:
            return text
        pattern = rf'(["“])\s*{re.escape(attributed_title)}\.?\s*(["”])'
        return re.sub(pattern, " ", text, flags=re.IGNORECASE)

    @classmethod
    def _find_unsafe_terms(cls, text: str) -> list[str]:
        normalized_text = cls._normalize_text(text)
        safe_prefixes = {
            "avoid",
            "avoiding",
            "never",
            "no",
            "not",
            "prevent",
            "preventing",
            "without",
        }
        found: list[str] = []
        for term in cls.unsafe_quest_terms:
            pattern = rf"\b{re.escape(cls._normalize_text(term))}\b"
            for match in re.finditer(pattern, normalized_text):
                prefix_tokens = normalized_text[: match.start()].split()
                if prefix_tokens and prefix_tokens[-1] in safe_prefixes:
                    continue
                found.append(term)
                break
        return sorted(found)

    @classmethod
    def _perspective_template(cls, message: str, display_names: list[str]) -> str:
        template = cls._normalize_text(message)
        normalized_names = sorted(
            (cls._normalize_text(name) for name in display_names), key=len, reverse=True
        )
        for name in normalized_names:
            if name:
                template = re.sub(rf"\b{re.escape(name)}\b", "<player>", template)
        return template

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())

    @staticmethod
    def _metric_subject(metric: str, prefix: str, suffix: str) -> str | None:
        if not metric.startswith(prefix) or not metric.endswith(suffix):
            return None
        subject = metric[len(prefix) : -len(suffix)]
        return subject or None

    @staticmethod
    def _error(code: str, message: str) -> ValidationIssue:
        return ValidationIssue(code=code, severity=IssueSeverity.ERROR, message=message)
