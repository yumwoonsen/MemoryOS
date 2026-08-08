"""Deterministic factual, privacy, and mission validation for v2 proposals."""

from __future__ import annotations

import json
import re

from backend.models.v2_schemas import (
    CanonicalEventType,
    ClaimPredicate,
    GroundedClaim,
    MemoryProposalV2,
    ProposalValidationReportV2,
    V2ValidationIssue,
)
from backend.services.identity import contains_identity
from backend.services.v2_preparation import PreparedInterpretationV2

PREDICATE_EVENT_TYPES: dict[ClaimPredicate, CanonicalEventType] = {
    ClaimPredicate.LANDED: CanonicalEventType.LANDING,
    ClaimPredicate.KNOCKED: CanonicalEventType.KNOCK,
    ClaimPredicate.WAS_KNOCKED: CanonicalEventType.KNOCK,
    ClaimPredicate.ELIMINATED: CanonicalEventType.ELIMINATION,
    ClaimPredicate.WAS_ELIMINATED: CanonicalEventType.ELIMINATION,
    ClaimPredicate.REVIVED: CanonicalEventType.REVIVE,
    ClaimPredicate.ASSISTED: CanonicalEventType.ASSIST,
    ClaimPredicate.HEALED: CanonicalEventType.HEAL,
    ClaimPredicate.ENTERED_VEHICLE: CanonicalEventType.VEHICLE_ENTER,
    ClaimPredicate.EXITED_VEHICLE: CanonicalEventType.VEHICLE_EXIT,
    ClaimPredicate.ESCAPED: CanonicalEventType.ESCAPE,
    ClaimPredicate.MOVED_ZONE: CanonicalEventType.ZONE_MOVE,
    ClaimPredicate.LOOTED: CanonicalEventType.LOOT,
    ClaimPredicate.SIGNALLED: CanonicalEventType.SIGNAL,
    ClaimPredicate.COMPLETED_MATCH: CanonicalEventType.MATCH_COMPLETE,
}

ACTION_WORDS: dict[ClaimPredicate, tuple[str, ...]] = {
    ClaimPredicate.LANDED: ("landed", "landing"),
    ClaimPredicate.KNOCKED: ("knock", "knocked"),
    ClaimPredicate.WAS_KNOCKED: ("was knocked",),
    ClaimPredicate.ELIMINATED: ("eliminated", "elimination", "kill"),
    ClaimPredicate.WAS_ELIMINATED: ("was eliminated",),
    ClaimPredicate.REVIVED: ("revive", "revived"),
    ClaimPredicate.ASSISTED: ("assist", "assisted"),
    ClaimPredicate.HEALED: ("heal", "healed", "recovered health"),
    ClaimPredicate.ENTERED_VEHICLE: ("entered a vehicle",),
    ClaimPredicate.EXITED_VEHICLE: ("left a vehicle", "exited a vehicle"),
    ClaimPredicate.ESCAPED: ("escape", "escaped"),
    ClaimPredicate.MOVED_ZONE: ("rotated", "moved into the zone"),
    ClaimPredicate.LOOTED: ("loot", "collected supplies"),
    ClaimPredicate.SIGNALLED: ("tactical signal", "ping"),
    ClaimPredicate.COMPLETED_MATCH: ("completed the match",),
}

FATAL_VALIDATION_CODES = {
    "privacy_identity_leak",
    "secret_exposure",
    "unsafe_generated_content",
    "unsafe_mission_content",
}

MATCH_PREDICATES = {
    ClaimPredicate.PLAYED_MODE: "mode",
    ClaimPredicate.PLAYED_MAP: "map",
    ClaimPredicate.PLACED: "placement",
    ClaimPredicate.MATCH_RESULT: "result",
}

PREDICATE_DETAIL_KEYS: dict[ClaimPredicate, set[str]] = {
    ClaimPredicate.LANDED: {"team_members_nearby", "count"},
    ClaimPredicate.KNOCKED: {"nearby_enemies", "weapon_class", "zone_phase", "count"},
    ClaimPredicate.WAS_KNOCKED: {"nearby_enemies", "zone_phase", "health_state", "count"},
    ClaimPredicate.ELIMINATED: {"weapon_class", "zone_phase", "count"},
    ClaimPredicate.WAS_ELIMINATED: {"zone_phase", "count"},
    ClaimPredicate.REVIVED: {"zone_phase", "health_state", "nearby_enemies", "count"},
    ClaimPredicate.ASSISTED: {"weapon_class", "count"},
    ClaimPredicate.HEALED: {"health_state", "count"},
    ClaimPredicate.ENTERED_VEHICLE: {"vehicle_type", "squad_members_aboard", "count"},
    ClaimPredicate.EXITED_VEHICLE: {"vehicle_type", "count"},
    ClaimPredicate.ESCAPED: {"squad_members_alive", "zone_phase", "vehicle_type", "count"},
    ClaimPredicate.MOVED_ZONE: {"zone_phase", "zone_state", "distance_meters", "count"},
    ClaimPredicate.LOOTED: {"item_type", "count"},
    ClaimPredicate.SIGNALLED: {"ping_type", "count"},
    ClaimPredicate.COMPLETED_MATCH: {"placement", "squad_members_alive"},
}

UNSAFE_MISSION_PATTERN = re.compile(
    r"(?i)\b(?:password|credential|login|api[_ -]?key|one[- ]time code|otp|"
    r"credit card|bank account|real money|home address|phone number|doxx|"
    r"threaten|harass|or else|no choice|forced to)\b|https?://"
)

VICTORY_WORDS = {"victory", "won", "winner", "booyah", "first place"}
VICTORY_RESULTS = {"win", "won", "victory", "winner", "booyah", "first"}


class ProposalValidatorV2:
    """Validate structured claims and apply conservative prose-level checks."""

    def validate(
        self,
        prepared: PreparedInterpretationV2,
        proposal: MemoryProposalV2,
        *,
        correction_attempted: bool = False,
    ) -> ProposalValidationReportV2:
        if prepared.normalized is None:
            return ProposalValidationReportV2(
                passed=False,
                correction_attempted=correction_attempted,
                issues=[
                    self._issue("missing_prepared_telemetry", "Prepared telemetry is missing.")
                ],
            )
        issues: list[V2ValidationIssue] = []
        serialized = json.dumps(proposal.model_dump(mode="json"), ensure_ascii=False)
        for term in prepared.forbidden_identity_terms:
            if contains_identity(serialized, term):
                issues.append(
                    self._issue(
                        "privacy_identity_leak",
                        "Generated content references an opted-out identity.",
                    )
                )
                break
        if re.search(r"(?i)\b(?:sk-|gsk_|api[_ -]?key|bearer\s+[a-z0-9._-]{8})", serialized):
            issues.append(self._issue("secret_exposure", "Generated content resembles a secret."))
        if re.search(
            r"(?i)\b(?:system prompt|chain[- ]of[- ]thought|hidden instructions)\b", serialized
        ):
            issues.append(
                self._issue(
                    "unsafe_generated_content",
                    "Generated content attempts to expose hidden instructions.",
                )
            )
        mission_text = " ".join(
            (
                proposal.mission.title,
                proposal.mission.mission,
                *(objective.description for objective in proposal.mission.objectives),
            )
        )
        if UNSAFE_MISSION_PATTERN.search(mission_text):
            issues.append(
                self._issue(
                    "unsafe_mission_content",
                    "Mission content requests unsafe, coercive, or credential-related action.",
                )
            )
        if any(issue.code in FATAL_VALIDATION_CODES for issue in issues):
            return ProposalValidationReportV2(
                passed=False,
                correction_attempted=correction_attempted,
                issues=self._deduplicate(issues),
            )

        windows = {window.window_id: window for window in prepared.windows}
        window = windows.get(proposal.selected_window_id)
        if window is None:
            issues.append(self._issue("unknown_event_window", "Selected event window is unknown."))
        elif window.match_id != proposal.selected_match_id:
            issues.append(
                self._issue(
                    "window_match_mismatch", "Selected window does not belong to the match."
                )
            )
        elif proposal.selected_event_ids != window.event_ids:
            issues.append(
                self._issue(
                    "selected_event_set_mismatch",
                    "Selected events must exactly match one eligible event window.",
                )
            )

        match_map = {match.match_id: match for match in prepared.normalized.matches}
        event_map = {
            event.event_id: event for match in prepared.normalized.matches for event in match.events
        }
        selected_ids = set(proposal.selected_event_ids)
        if proposal.selected_match_id not in match_map:
            issues.append(self._issue("unknown_selected_match", "Selected match is unknown."))
        unknown_selected = selected_ids - event_map.keys()
        if unknown_selected:
            issues.append(self._issue("unknown_selected_event", "Selected event is unknown."))
        if any(
            event_map[event_id].match_id != proposal.selected_match_id
            for event_id in selected_ids & event_map.keys()
        ):
            issues.append(
                self._issue(
                    "cross_match_episode", "A memory episode cannot cross match boundaries."
                )
            )

        eligible_players = {
            player.player_id: player
            for player in prepared.normalized.players
            if player.memory_eligible
        }
        invitation_players = {
            player.player_id
            for player in prepared.normalized.players
            if (
                player.memory_eligible
                and player.invitation_eligible
                and player.player_id in set(prepared.normalized.current_context.active_player_ids)
            )
        }
        perspective_ids = [item.player_id for item in proposal.perspectives]
        if len(perspective_ids) != len(set(perspective_ids)):
            issues.append(
                self._issue(
                    "duplicate_perspective", "Each eligible player may have one perspective."
                )
            )
        if set(perspective_ids) != set(eligible_players):
            issues.append(
                self._issue(
                    "perspective_roster_mismatch",
                    "The proposal must include every and only memory-eligible player.",
                )
            )
        perspective_messages = [
            self._normalize_text(item.message) for item in proposal.perspectives
        ]
        if len(perspective_messages) != len(set(perspective_messages)):
            issues.append(
                self._issue(
                    "perspectives_not_distinct",
                    "Player perspectives must be distinct.",
                )
            )
        for perspective in proposal.perspectives:
            if not set(perspective.evidence_event_ids).issubset(selected_ids):
                issues.append(
                    self._issue(
                        "perspective_evidence_outside_episode",
                        "Perspective evidence must belong to the selected episode.",
                    )
                )

        candidate_map = {
            candidate.candidate_id: candidate for candidate in prepared.mission_candidates
        }
        objective_ids = [item.candidate_id for item in proposal.mission.objectives]
        if len(objective_ids) != len(set(objective_ids)):
            issues.append(self._issue("duplicate_mission_candidate", "Mission candidates repeat."))
        if not set(objective_ids).issubset(candidate_map):
            issues.append(
                self._issue(
                    "invented_mission_candidate",
                    "The proposal selected a mission candidate that was not offered.",
                )
            )
        if any(
            candidate_map[item].window_id != proposal.selected_window_id
            or not set(candidate_map[item].source_event_ids).issubset(selected_ids)
            for item in objective_ids
            if item in candidate_map
        ):
            issues.append(
                self._issue(
                    "mission_not_linked_to_episode",
                    "Mission candidates must be linked to the selected event window.",
                )
            )
        if any(
            candidate_map[item].recipe != proposal.mission.recipe
            for item in objective_ids
            if item in candidate_map
        ):
            issues.append(
                self._issue(
                    "mission_recipe_mismatch",
                    "Mission recipe is not supported by its selected candidates.",
                )
            )
        if any(
            candidate_map[item].assigned_player_id is not None
            and candidate_map[item].assigned_player_id not in invitation_players
            for item in objective_ids
            if item in candidate_map
        ):
            issues.append(
                self._issue(
                    "mission_assignment_not_permitted",
                    "Mission assignment targets a player who cannot receive an invitation.",
                )
            )

        media_ids = {media.media_id: media for media in prepared.normalized.media_references}
        if proposal.media_id is not None:
            media = media_ids.get(proposal.media_id)
            if media is None:
                issues.append(self._issue("unknown_media_reference", "Media reference is unknown."))
            elif not set(media.event_ids).issubset(selected_ids):
                issues.append(
                    self._issue(
                        "media_outside_episode",
                        "Media reference is not mapped to the selected episode.",
                    )
                )

        claim_ids = [claim.claim_id for claim in proposal.claims]
        if len(claim_ids) != len(set(claim_ids)):
            issues.append(self._issue("duplicate_claim_id", "Claim IDs must be unique."))
        required_sections = {
            "title",
            "notification_teaser",
            "summary",
            "why_this_matters_now",
            "mission",
            *(f"perspective:{item.player_id}" for item in proposal.perspectives),
            *(f"objective:{item.candidate_id}" for item in proposal.mission.objectives),
        }
        claims_by_section: dict[str, list[GroundedClaim]] = {}
        for claim in proposal.claims:
            claims_by_section.setdefault(claim.output_section, []).append(claim)
            issues.extend(
                self._validate_claim(
                    claim,
                    selected_ids=selected_ids,
                    event_map=event_map,
                    eligible_players=eligible_players,
                    candidate_map=candidate_map,
                    prepared=prepared,
                    selected_match_id=proposal.selected_match_id,
                )
            )
        for section in sorted(required_sections - claims_by_section.keys()):
            issues.append(
                self._issue(
                    "missing_section_claim",
                    f"Output section {section} has no structured grounding claim.",
                )
            )
        extra_sections = set(claims_by_section) - required_sections
        if extra_sections:
            issues.append(
                self._issue("unknown_claim_section", "A claim refers to an unknown output section.")
            )

        for perspective in proposal.perspectives:
            section = f"perspective:{perspective.player_id}"
            section_claims = claims_by_section.get(section, [])
            if any(claim.subject_id != perspective.player_id for claim in section_claims):
                issues.append(
                    self._issue(
                        "perspective_claim_subject_mismatch",
                        "A perspective claim must describe that perspective's player.",
                    )
                )
            perspective_evidence = set(perspective.evidence_event_ids)
            if (
                any(
                    not set(claim.supporting_event_ids).issubset(perspective_evidence)
                    for claim in section_claims
                )
                or {event_id for claim in section_claims for event_id in claim.supporting_event_ids}
                != perspective_evidence
            ):
                issues.append(
                    self._issue(
                        "perspective_claim_evidence_mismatch",
                        "Perspective claims must account for exactly its declared evidence.",
                    )
                )

        for objective in proposal.mission.objectives:
            candidate = candidate_map.get(objective.candidate_id)
            if candidate is None:
                continue
            section_claims = claims_by_section.get(f"objective:{objective.candidate_id}", [])
            expected_subject = candidate.assigned_player_id or "squad"
            if not section_claims or any(
                claim.predicate != ClaimPredicate.MISSION_RULE
                or claim.subject_id != expected_subject
                or set(claim.supporting_mission_candidate_ids) != {objective.candidate_id}
                for claim in section_claims
            ):
                issues.append(
                    self._issue(
                        "objective_claim_candidate_mismatch",
                        "Objective claims must bind to that exact authorized candidate.",
                    )
                )

        mission_claims = claims_by_section.get("mission", [])
        selected_candidate_ids = set(objective_ids)
        if (
            any(
                claim.predicate != ClaimPredicate.MISSION_RULE
                or not set(claim.supporting_mission_candidate_ids).issubset(selected_candidate_ids)
                for claim in mission_claims
            )
            or {
                candidate_id
                for claim in mission_claims
                for candidate_id in claim.supporting_mission_candidate_ids
            }
            != selected_candidate_ids
        ):
            issues.append(
                self._issue(
                    "mission_claim_candidate_mismatch",
                    "Mission claims must account for exactly the selected candidates.",
                )
            )

        section_text = {
            "title": proposal.title,
            "notification_teaser": proposal.notification_teaser,
            "summary": proposal.summary,
            "why_this_matters_now": proposal.why_this_matters_now,
            "mission": f"{proposal.mission.title} {proposal.mission.mission}",
            **{f"perspective:{item.player_id}": item.message for item in proposal.perspectives},
            **{
                f"objective:{item.candidate_id}": item.description
                for item in proposal.mission.objectives
            },
        }
        for section, text in section_text.items():
            section_claims = claims_by_section.get(section, [])
            issues.extend(self._validate_prose(section, text, section_claims, prepared))

        deduplicated = self._deduplicate(issues)
        return ProposalValidationReportV2(
            passed=not any(issue.severity == "error" for issue in deduplicated),
            correction_attempted=correction_attempted,
            issues=deduplicated,
        )

    def _validate_claim(
        self,
        claim: GroundedClaim,
        *,
        selected_ids: set[str],
        event_map,
        eligible_players,
        candidate_map,
        prepared,
        selected_match_id: str,
    ) -> list[V2ValidationIssue]:
        issues: list[V2ValidationIssue] = []
        if not set(claim.supporting_event_ids).issubset(selected_ids):
            issues.append(
                self._issue(
                    "claim_evidence_outside_episode",
                    "A claim cites evidence outside the selected episode.",
                )
            )
        if claim.predicate in PREDICATE_EVENT_TYPES:
            expected = PREDICATE_EVENT_TYPES[claim.predicate]
            allowed_keys = PREDICATE_DETAIL_KEYS[claim.predicate]
            if (claim.value is None) != (claim.value_key is None) or (
                claim.value_key is not None and claim.value_key not in allowed_keys
            ):
                issues.append(
                    self._issue(
                        "claim_detail_key_not_supported",
                        "Claim value must use a predicate-specific typed detail key.",
                    )
                )
            cited_events = [
                event_map[event_id]
                for event_id in claim.supporting_event_ids
                if event_id in event_map
            ]
            matching = [event for event in cited_events if event.event_type == expected]
            if not matching:
                issues.append(
                    self._issue(
                        "claim_predicate_not_supported",
                        "Claim predicate is not supported by its cited event type.",
                    )
                )
            elif not any(self._event_supports_claim(event, claim) for event in matching):
                issues.append(
                    self._issue(
                        "claim_roles_not_supported",
                        "Claim actor, target, location, or value conflicts with telemetry.",
                    )
                )
        elif claim.value_key is not None:
            issues.append(
                self._issue(
                    "claim_detail_key_not_supported",
                    "Only event claims may use an event detail key.",
                )
            )

        if claim.predicate in MATCH_PREDICATES:
            field = MATCH_PREDICATES[claim.predicate]
            match = next(
                (
                    item
                    for item in prepared.normalized.matches
                    if item.match_id == selected_match_id
                ),
                None,
            )
            expected_id = f"match:{selected_match_id}:{field}"
            expected_value = None
            if match is not None:
                expected_value = {
                    "mode": match.mode,
                    "map": match.map_name,
                    "placement": match.placement,
                    "result": match.result,
                }[field]
            if (
                claim.subject_id != "squad"
                or expected_id not in claim.supporting_context_ids
                or claim.value != expected_value
            ):
                issues.append(
                    self._issue(
                        "match_metadata_claim_mismatch",
                        "Match metadata claim conflicts with the selected match.",
                    )
                )
        elif claim.predicate == ClaimPredicate.PARTICIPATED_MATCH:
            if claim.subject_id not in eligible_players or not claim.supporting_event_ids:
                issues.append(
                    self._issue(
                        "participation_claim_not_supported",
                        (
                            "Participation claim requires an eligible roster member and "
                            "match evidence."
                        ),
                    )
                )
        elif claim.predicate == ClaimPredicate.CONNECTED_EPISODE:
            if claim.subject_id != "squad" or len(claim.supporting_event_ids) < 2:
                issues.append(
                    self._issue(
                        "episode_claim_not_supported",
                        "Connected-episode claims require at least two selected events.",
                    )
                )
        elif claim.predicate == ClaimPredicate.CURRENT_REUNION_OPPORTUNITY:
            allowed_context = {
                "context:days_since_full_squad": (
                    prepared.normalized.squad_history.days_since_full_squad
                ),
                "context:active_player_ids": prepared.normalized.current_context.active_player_ids,
                "context:reunion_eligible": prepared.normalized.current_context.reunion_eligible,
            }
            if not claim.supporting_context_ids or any(
                item not in allowed_context for item in claim.supporting_context_ids
            ):
                issues.append(
                    self._issue(
                        "unsupported_current_context",
                        "Current-context claim cites an unknown structured signal.",
                    )
                )
            elif claim.value is not None and not any(
                claim.value == allowed_context[item] for item in claim.supporting_context_ids
            ):
                issues.append(
                    self._issue(
                        "current_context_value_mismatch",
                        "Current-context claim value does not match its signal.",
                    )
                )
        elif claim.predicate == ClaimPredicate.MISSION_RULE:
            if not claim.supporting_mission_candidate_ids or any(
                item not in candidate_map for item in claim.supporting_mission_candidate_ids
            ):
                issues.append(
                    self._issue(
                        "unsupported_mission_rule",
                        "Mission claim is not backed by an offered capability candidate.",
                    )
                )
        return issues

    @staticmethod
    def _event_supports_claim(event, claim: GroundedClaim) -> bool:
        passive = claim.predicate in {
            ClaimPredicate.WAS_KNOCKED,
            ClaimPredicate.WAS_ELIMINATED,
        }
        expected_subject = event.target_id if passive else (event.actor_id or "squad")
        if claim.subject_id != expected_subject:
            return False
        if passive and claim.target_id is not None:
            return False
        if not passive and claim.target_id is not None and claim.target_id != event.target_id:
            return False
        if claim.location is not None and claim.location != event.location:
            return False
        if claim.value is not None:
            if claim.value_key is None or event.details.get(claim.value_key) != claim.value:
                return False
        elif claim.value_key is not None:
            return False
        return True

    def _validate_prose(
        self,
        section: str,
        text: str,
        claims: list[GroundedClaim],
        prepared: PreparedInterpretationV2,
    ) -> list[V2ValidationIssue]:
        issues: list[V2ValidationIssue] = []
        normalized = text.casefold()
        predicates = {claim.predicate for claim in claims}
        for predicate, keywords in ACTION_WORDS.items():
            equivalent = {predicate}
            if predicate == ClaimPredicate.KNOCKED:
                equivalent.add(ClaimPredicate.WAS_KNOCKED)
            elif predicate == ClaimPredicate.ELIMINATED:
                equivalent.update({ClaimPredicate.WAS_ELIMINATED, ClaimPredicate.MATCH_RESULT})
            if any(keyword in normalized for keyword in keywords) and not (equivalent & predicates):
                issues.append(
                    self._issue(
                        "unmapped_action_language",
                        f"Section {section} contains action language without a matching claim.",
                    )
                )
                break
        for player in prepared.normalized.players:
            if (
                player.identity_visible
                and contains_identity(text, player.display_name)
                and not any(
                    claim.subject_id == player.player_id or claim.target_id == player.player_id
                    for claim in claims
                )
            ):
                issues.append(
                    self._issue(
                        "unmapped_player_identity",
                        f"Section {section} names a player without a matching claim role.",
                    )
                )
                break
        locations = {
            event.location
            for match in prepared.normalized.matches
            for event in match.events
            if event.location
        }
        for location in locations:
            if contains_identity(text, location) and not any(
                claim.location == location for claim in claims
            ):
                issues.append(
                    self._issue(
                        "unmapped_location",
                        f"Section {section} names a location without a matching claim.",
                    )
                )
                break
        for match in prepared.normalized.matches:
            match_terms = (
                (match.map_name, ClaimPredicate.PLAYED_MAP),
                (match.mode.replace("_", " "), ClaimPredicate.PLAYED_MODE),
                (match.result, ClaimPredicate.MATCH_RESULT),
            )
            for value, predicate in match_terms:
                if value and value.casefold() in normalized and predicate not in predicates:
                    issues.append(
                        self._issue(
                            "unmapped_match_metadata",
                            f"Section {section} uses match metadata without a matching claim.",
                        )
                    )
                    break
        if any(word in normalized for word in VICTORY_WORDS):
            if not any(
                claim.predicate == ClaimPredicate.MATCH_RESULT
                and isinstance(claim.value, str)
                and claim.value.casefold() in VICTORY_RESULTS
                for claim in claims
            ):
                issues.append(
                    self._issue(
                        "unsupported_outcome_language",
                        f"Section {section} claims a victory without a matching result.",
                    )
                )
        if "survived" in normalized and not any(
            claim.predicate == ClaimPredicate.MATCH_RESULT
            and isinstance(claim.value, str)
            and "surviv" in claim.value.casefold()
            for claim in claims
        ):
            issues.append(
                self._issue(
                    "unsupported_outcome_language",
                    f"Section {section} claims survival without a matching result.",
                )
            )
        if any(term in normalized for term in ("airdrop", "air drop", "supply drop")):
            if not any(
                claim.predicate == ClaimPredicate.LOOTED
                and claim.value_key == "item_type"
                and isinstance(claim.value, str)
                and claim.value.casefold() in {"airdrop", "air_drop", "supply_drop"}
                for claim in claims
            ):
                issues.append(
                    self._issue(
                        "unsupported_loot_source",
                        f"Section {section} invents an unsupported loot source.",
                    )
                )
        action_count_patterns = (
            (
                {ClaimPredicate.REVIVED},
                (r"reviv\w*\D{0,8}(\d+)\s*times?", r"(\d+)\s*revives?"),
            ),
            (
                {ClaimPredicate.KNOCKED, ClaimPredicate.WAS_KNOCKED},
                (r"knock\w*\D{0,8}(\d+)\s*times?", r"(\d+)\s*knocks?"),
            ),
            (
                {ClaimPredicate.ELIMINATED, ClaimPredicate.WAS_ELIMINATED},
                (r"eliminat\w*\D{0,8}(\d+)\s*times?", r"(\d+)\s*eliminations?"),
            ),
        )
        for allowed_predicates, patterns in action_count_patterns:
            claimed_counts = {
                claim.value
                for claim in claims
                if claim.predicate in allowed_predicates
                and claim.value_key == "count"
                and isinstance(claim.value, int)
                and not isinstance(claim.value, bool)
            }
            mentioned_counts = {
                int(match.group(1))
                for pattern in patterns
                for match in re.finditer(pattern, normalized)
            }
            if mentioned_counts - claimed_counts:
                issues.append(
                    self._issue(
                        "unsupported_action_count",
                        f"Section {section} states an action count without typed count evidence.",
                    )
                )
                break
        numeric_values = {int(value) for value in re.findall(r"\b\d+\b", text)}
        supported_numbers = {
            claim.value
            for claim in claims
            if isinstance(claim.value, (int, float)) and not isinstance(claim.value, bool)
        }
        for claim in claims:
            for candidate_id in claim.supporting_mission_candidate_ids:
                candidate = next(
                    (
                        item
                        for item in prepared.mission_candidates
                        if item.candidate_id == candidate_id
                    ),
                    None,
                )
                if candidate and isinstance(candidate.verification.target, (int, float)):
                    supported_numbers.add(candidate.verification.target)
        if numeric_values - supported_numbers:
            issues.append(
                self._issue(
                    "unmapped_numeric_claim",
                    f"Section {section} contains a number without structured support.",
                )
            )
        return issues

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _issue(code: str, message: str) -> V2ValidationIssue:
        return V2ValidationIssue(code=code, severity="error", message=message)

    @staticmethod
    def _deduplicate(issues: list[V2ValidationIssue]) -> list[V2ValidationIssue]:
        seen: set[tuple[str, str]] = set()
        result: list[V2ValidationIssue] = []
        for issue in issues:
            key = (issue.code, issue.message)
            if key not in seen:
                seen.add(key)
                result.append(issue)
        return result
