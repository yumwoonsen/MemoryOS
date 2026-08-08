"""Expand a fixed-section AI draft into the authoritative MemoryOS proposal."""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from backend.models.v2_schemas import (
    CanonicalEventType,
    ClaimPredicate,
    CompactMemoryProposalV2,
    CompactSectionDraftV2,
    GroundedClaim,
    MemoryProposalV2,
    ProposedMissionObjectiveV2,
    ProposedMissionV2,
    ProposedPerspectiveV2,
    V2ValidationIssue,
)
from backend.services.content_safety import (
    contains_secret_like,
    contains_unsafe_player_content,
)
from backend.services.identity import contains_identity
from backend.services.v2_preparation import (
    PreparedInterpretationV2,
    collective_event_includes_full_squad,
)
from backend.services.v2_validator import (
    ACTION_WORDS,
    PREDICATE_DETAIL_KEYS,
    UNSAFE_MISSION_PATTERN,
    action_language_present,
)

EVENT_PREDICATES = {
    CanonicalEventType.LANDING: ClaimPredicate.LANDED,
    CanonicalEventType.KNOCK: ClaimPredicate.KNOCKED,
    CanonicalEventType.ELIMINATION: ClaimPredicate.ELIMINATED,
    CanonicalEventType.REVIVE: ClaimPredicate.REVIVED,
    CanonicalEventType.ASSIST: ClaimPredicate.ASSISTED,
    CanonicalEventType.HEAL: ClaimPredicate.HEALED,
    CanonicalEventType.VEHICLE_ENTER: ClaimPredicate.ENTERED_VEHICLE,
    CanonicalEventType.VEHICLE_EXIT: ClaimPredicate.EXITED_VEHICLE,
    CanonicalEventType.ESCAPE: ClaimPredicate.ESCAPED,
    CanonicalEventType.ZONE_MOVE: ClaimPredicate.MOVED_ZONE,
    CanonicalEventType.LOOT: ClaimPredicate.LOOTED,
    CanonicalEventType.SIGNAL: ClaimPredicate.SIGNALLED,
    CanonicalEventType.MATCH_COMPLETE: ClaimPredicate.COMPLETED_MATCH,
}
COMPACT_MATCH_EVIDENCE = {
    "match:game": (ClaimPredicate.PLAYED_GAME, "game"),
    "match:mode": (ClaimPredicate.PLAYED_MODE, "mode"),
    "match:map": (ClaimPredicate.PLAYED_MAP, "map"),
    "match:placement": (ClaimPredicate.PLACED, "placement"),
    "match:result": (ClaimPredicate.MATCH_RESULT, "result"),
}
COMPACT_CONTEXT_EVIDENCE = {
    "context:previous_session_at",
    "context:days_since_full_squad",
    "context:recent_rematch_count",
    "context:active_player_ids",
    "context:available_modes",
    "context:reunion_eligible",
}
NUMERIC_DETAIL_CUES = {
    "duration_seconds": ("second", "seconds"),
    "nearby_enemies": ("enemy", "enemies", "nearby enemies"),
    "passengers": ("passenger", "passengers"),
    "placement_reached": ("placement", "placed", "finished"),
    "squad_alive": ("alive", "survived", "survivors"),
    "distance_meters": ("meter", "meters", "metre", "metres"),
    "rank_points": ("rank point", "rank points", "points"),
    "team_members_nearby": (
        "team member",
        "team members",
        "teammate",
        "teammates",
        "squadmate",
        "squadmates",
        "nearby",
    ),
    "zone_phase": ("zone phase", "phase"),
    "squad_members_aboard": (
        "aboard",
        "in the vehicle",
        "squad member",
        "squad members",
    ),
    "squad_members_alive": ("alive", "survived", "survivors"),
    "placement": ("placement", "placed", "finished"),
}
CATEGORICAL_DETAIL_CUES = {
    "health_state": ("health", "hp", "health state"),
    "zone_state": ("zone", "circle", "zone state"),
    "weapon_class": ("weapon", "gun", "with", "using"),
    "vehicle_type": (
        "vehicle",
        "drove",
        "driving",
        "rode",
        "riding",
        "in a",
        "in the",
    ),
    "item_type": ("item", "loot", "looted", "picked up", "collected", "found"),
    "ping_type": ("ping", "pinged", "signal", "signaled", "signalled"),
}
EXPANSION_MESSAGES = {
    "privacy_identity_leak": "Generated content references an opted-out identity.",
    "secret_exposure": "Generated content resembles a secret.",
    "unsafe_generated_content": "Generated content contains unsafe or instruction-leaking text.",
    "unsafe_mission_content": (
        "Mission content requests unsafe, coercive, or credential-related action."
    ),
    "unknown_event_window": "The selected event window is unknown.",
    "invented_mission_candidate": "The selected mission candidate was not offered.",
    "claim_evidence_outside_episode": "A section cites unknown or unrelated evidence.",
    "perspective_claim_evidence_mismatch": (
        "Every perspective requires event evidence from the selected window."
    ),
    "why_now_evidence_mismatch": "Why-this-matters-now may cite only current context signals.",
    "compact_claim_expansion_too_large": (
        "The section evidence expands beyond the authoritative claim limit."
    ),
    "compact_expansion_invalid": "The fixed-section draft cannot form a valid proposal.",
}


class CompactProposalExpansionError(ValueError):
    """A safe structural failure supplied to at most one bounded correction attempt."""

    def __init__(self, code: str, *, section: str | None = None) -> None:
        self.code = code
        self.section = section
        super().__init__(EXPANSION_MESSAGES[code])

    def issue(self) -> V2ValidationIssue:
        message = EXPANSION_MESSAGES[self.code]
        if self.section:
            message = f"Section {self.section} {message[0].lower()}{message[1:]}"
        return V2ValidationIssue(
            code=self.code,
            severity="error",
            message=message,
        )


class CompactProposalExpanderV2:
    """Derive claims, roles, roster, media, and mission controls from trusted inputs."""

    def expand(
        self,
        prepared: PreparedInterpretationV2,
        compact: CompactMemoryProposalV2,
    ) -> MemoryProposalV2:
        try:
            return self._expand_authoritative(prepared, compact)
        except CompactProposalExpansionError:
            raise
        except (ValidationError, ValueError, TypeError, StopIteration):
            raise CompactProposalExpansionError("compact_expansion_invalid") from None

    def _expand_authoritative(
        self,
        prepared: PreparedInterpretationV2,
        compact: CompactMemoryProposalV2,
    ) -> MemoryProposalV2:
        if prepared.normalized is None:
            raise CompactProposalExpansionError("unknown_event_window")
        self._fail_on_fatal_content(prepared, compact)
        compact = self._without_reference_metadata(prepared, compact)
        window = next(
            (item for item in prepared.windows if item.window_id == compact.selected_window_id),
            None,
        )
        if window is None:
            raise CompactProposalExpansionError("unknown_event_window")
        selected_event_ids = list(window.event_ids)
        event_map = {
            event.event_id: event for match in prepared.normalized.matches for event in match.events
        }
        selected_events = {event_id: event_map[event_id] for event_id in selected_event_ids}
        match = next(
            item for item in prepared.normalized.matches if item.match_id == window.match_id
        )

        candidate_map = {
            candidate.candidate_id: candidate for candidate in prepared.mission_candidates
        }
        candidate = candidate_map.get(compact.mission.candidate_id)
        if candidate is None:
            raise CompactProposalExpansionError("invented_mission_candidate")

        claims: list[GroundedClaim] = []
        sections = (
            ("title", compact.title),
            ("notification_teaser", compact.notification_teaser),
            ("summary", compact.summary),
            ("why_this_matters_now", compact.why_this_matters_now),
        )
        for section_index, (section_name, section) in enumerate(sections, start=1):
            if section_name == "why_this_matters_now" and any(
                evidence_id not in COMPACT_CONTEXT_EVIDENCE for evidence_id in section.evidence_ids
            ):
                raise CompactProposalExpansionError(
                    "why_now_evidence_mismatch",
                    section=section_name,
                )
            claims.extend(
                self._expand_section(
                    section,
                    output_section=section_name,
                    claim_prefix=f"claim:section:{section_index}",
                    selected_events=selected_events,
                    match=match,
                    prepared=prepared,
                )
            )

        roster_order = {
            player.player_id: index
            for index, player in enumerate(prepared.normalized.players)
            if player.memory_eligible
        }
        ordered_perspectives = sorted(
            compact.perspectives,
            key=lambda item: roster_order.get(item.player_id, len(roster_order)),
        )
        perspectives: list[ProposedPerspectiveV2] = []
        for perspective_index, perspective in enumerate(ordered_perspectives, start=1):
            section = f"perspective:{perspective.player_id}"
            inferred_evidence_ids = [
                event_id
                for event_id in self._infer_literal_evidence_ids(
                    perspective.message,
                    selected_events=selected_events,
                    match=match,
                    prepared=prepared,
                    perspective_player_id=perspective.player_id,
                )
                if event_id in selected_events
            ]
            literal_direct_evidence_ids = [
                event_id
                for event_id in inferred_evidence_ids
                if perspective.player_id
                in {
                    selected_events[event_id].actor_id,
                    selected_events[event_id].target_id,
                }
            ]
            explicit_evidence_ids = self._ordered_event_evidence(
                perspective.evidence_ids,
                selected_event_ids,
            )
            relevant_explicit_ids = [
                event_id for event_id in explicit_evidence_ids if event_id in inferred_evidence_ids
            ]
            evidence_event_ids = self._ordered_event_evidence(
                list(
                    dict.fromkeys(
                        [*literal_direct_evidence_ids, *relevant_explicit_ids]
                        or explicit_evidence_ids[:1]
                    )
                ),
                selected_event_ids,
            )
            if not evidence_event_ids:
                raise CompactProposalExpansionError(
                    "perspective_claim_evidence_mismatch",
                    section=section,
                )
            perspective_events = [selected_events[event_id] for event_id in evidence_event_ids]
            for event_index, event in enumerate(perspective_events, start=1):
                if perspective.player_id in {event.actor_id, event.target_id}:
                    claims.extend(
                        self._event_claims(
                            event,
                            text=perspective.message,
                            output_section=section,
                            claim_prefix=(f"claim:perspective:{perspective_index}:{event_index}"),
                        )
                    )
                elif collective_event_includes_full_squad(event, prepared.normalized):
                    claims.extend(
                        self._event_claims(
                            event,
                            text=perspective.message,
                            output_section=section,
                            claim_prefix=(
                                f"claim:perspective:{perspective_index}:{event_index}:squad"
                            ),
                        )
                    )
                    claims.append(
                        GroundedClaim(
                            claim_id=(
                                f"claim:perspective:{perspective_index}:{event_index}:participation"
                            ),
                            output_section=section,
                            subject_id=perspective.player_id,
                            predicate=ClaimPredicate.PARTICIPATED_MATCH,
                            supporting_event_ids=[event.event_id],
                        )
                    )
                else:
                    claims.append(
                        GroundedClaim(
                            claim_id=(
                                f"claim:perspective:{perspective_index}:{event_index}:participation"
                            ),
                            output_section=section,
                            subject_id=perspective.player_id,
                            predicate=ClaimPredicate.PARTICIPATED_MATCH,
                            supporting_event_ids=[event.event_id],
                        )
                    )
            perspectives.append(
                ProposedPerspectiveV2(
                    player_id=perspective.player_id,
                    message=perspective.message,
                    evidence_event_ids=evidence_event_ids,
                )
            )

        if len(claims) + 2 > 50:
            raise CompactProposalExpansionError("compact_claim_expansion_too_large")
        objective = ProposedMissionObjectiveV2(
            candidate_id=candidate.candidate_id,
            description=compact.mission.objective_description,
        )
        claims.extend(
            [
                GroundedClaim(
                    claim_id="claim:mission:rule",
                    output_section="mission",
                    subject_id=candidate.assigned_player_id or "squad",
                    predicate=ClaimPredicate.MISSION_RULE,
                    supporting_mission_candidate_ids=[candidate.candidate_id],
                ),
                GroundedClaim(
                    claim_id="claim:objective:rule",
                    output_section=f"objective:{candidate.candidate_id}",
                    subject_id=candidate.assigned_player_id or "squad",
                    predicate=ClaimPredicate.MISSION_RULE,
                    supporting_mission_candidate_ids=[candidate.candidate_id],
                ),
            ]
        )
        selected_media = next(
            (
                media
                for media in prepared.normalized.media_references
                if set(media.event_ids).issubset(selected_event_ids)
            ),
            None,
        )
        return MemoryProposalV2(
            selected_match_id=window.match_id,
            selected_window_id=window.window_id,
            selected_event_ids=selected_event_ids,
            memory_type=compact.memory_type,
            narrative_angle=compact.narrative_angle,
            title=compact.title.text,
            notification_teaser=compact.notification_teaser.text,
            summary=compact.summary.text,
            why_this_matters_now=compact.why_this_matters_now.text,
            perspectives=perspectives,
            mission=ProposedMissionV2(
                title=compact.mission.title,
                mission=compact.mission.mission,
                recipe=candidate.recipe,
                objectives=[objective],
            ),
            claims=claims,
            media_id=selected_media.media_id if selected_media else None,
        )

    def _expand_section(
        self,
        section: CompactSectionDraftV2,
        *,
        output_section: str,
        claim_prefix: str,
        selected_events: dict[str, object],
        match,
        prepared: PreparedInterpretationV2,
    ) -> list[GroundedClaim]:
        normalized_evidence_ids = list(
            dict.fromkeys(
                self._normalize_match_evidence_id(evidence_id, match.match_id)
                for evidence_id in section.evidence_ids
            )
        )
        inferred_evidence_ids: list[str] = []
        if output_section != "why_this_matters_now":
            inferred_evidence_ids = self._infer_literal_evidence_ids(
                section.text,
                selected_events=selected_events,
                match=match,
                prepared=prepared,
            )
            normalized_evidence_ids.extend(
                evidence_id
                for evidence_id in inferred_evidence_ids
                if evidence_id not in normalized_evidence_ids
            )
        explicit_event_ids = [
            self._normalize_match_evidence_id(evidence_id, match.match_id)
            for evidence_id in section.evidence_ids
            if self._normalize_match_evidence_id(evidence_id, match.match_id) in selected_events
        ]
        inferred_event_ids = [
            evidence_id for evidence_id in inferred_evidence_ids if evidence_id in selected_events
        ]
        event_ids = self._ordered_event_evidence(
            inferred_event_ids or explicit_event_ids[:1],
            list(selected_events),
        )
        all_event_ids = [
            evidence_id for evidence_id in normalized_evidence_ids if evidence_id in selected_events
        ]
        context_ids = [
            evidence_id
            for evidence_id in normalized_evidence_ids
            if evidence_id in COMPACT_CONTEXT_EVIDENCE or evidence_id in COMPACT_MATCH_EVIDENCE
        ]
        if len(all_event_ids) + len(context_ids) != len(normalized_evidence_ids):
            raise CompactProposalExpansionError(
                "claim_evidence_outside_episode",
                section=output_section,
            )
        claims = [
            claim
            for index, event_id in enumerate(event_ids, start=1)
            for claim in self._event_claims(
                selected_events[event_id],
                text=section.text,
                output_section=output_section,
                claim_prefix=f"{claim_prefix}:event:{index}",
            )
        ]
        claims.extend(
            self._context_claim(
                context_id,
                output_section=output_section,
                claim_id=f"{claim_prefix}:context:{index}",
                match=match,
                prepared=prepared,
            )
            for index, context_id in enumerate(context_ids, start=1)
        )
        return claims

    @staticmethod
    def _normalize_match_evidence_id(evidence_id: str, selected_match_id: str) -> str:
        """Accept an exact selected-match ledger ID and reduce it to its compact alias."""

        prefix = f"match:{selected_match_id}:"
        if evidence_id.startswith(prefix):
            alias = f"match:{evidence_id[len(prefix) :]}"
            if alias in COMPACT_MATCH_EVIDENCE:
                return alias
        return evidence_id

    @staticmethod
    def _event_claims(
        event,
        *,
        text: str,
        output_section: str,
        claim_prefix: str,
    ) -> list[GroundedClaim]:
        predicate = CompactProposalExpanderV2._event_predicate(event)
        passive = predicate in {ClaimPredicate.WAS_KNOCKED, ClaimPredicate.WAS_ELIMINATED}
        common = {
            "output_section": output_section,
            "subject_id": (
                event.target_id
                if passive
                else ("squad" if event.event_scope in {"squad", "match"} else event.actor_id)
            ),
            "predicate": predicate,
            "target_id": None if passive else event.target_id,
            "location": event.location,
            "supporting_event_ids": [event.event_id],
        }
        claims = [GroundedClaim(claim_id=f"{claim_prefix}:base", **common)]
        supported_details = [
            (key, value)
            for key, value in event.details.items()
            if key in PREDICATE_DETAIL_KEYS[predicate]
            and CompactProposalExpanderV2._detail_is_mentioned(
                text,
                key,
                value,
                predicate=predicate,
            )
        ]
        claims.extend(
            GroundedClaim(
                claim_id=f"{claim_prefix}:detail:{index}",
                value=value,
                value_key=key,
                **common,
            )
            for index, (key, value) in enumerate(supported_details, start=1)
        )
        return claims

    @staticmethod
    def _detail_is_mentioned(
        text: str,
        key: str,
        value: object,
        *,
        predicate: ClaimPredicate | None = None,
    ) -> bool:
        normalized = text.casefold().replace("_", " ")
        if key in {"squad_members_alive", "squad_alive"} and any(
            term in normalized for term in ("alive", "survive")
        ):
            return True
        if isinstance(value, bool):
            return str(value).casefold() in normalized
        if isinstance(value, str):
            if value in {"other", "unknown"}:
                return False
            value_pattern = r"(?<!\w)" + re.escape(value.casefold().replace("_", " ")) + r"(?!\w)"
            if not re.search(value_pattern, normalized):
                return False
            cue_terms = list(CATEGORICAL_DETAIL_CUES.get(key, ()))
            if predicate is not None and key in {
                "weapon_class",
                "vehicle_type",
                "item_type",
                "ping_type",
            }:
                cue_terms.extend(ACTION_WORDS.get(predicate, ()))
            if not cue_terms:
                return False
            cue_pattern = (
                r"(?<!\w)(?:"
                + "|".join(
                    re.escape(term) for term in sorted(set(cue_terms), key=len, reverse=True)
                )
                + r")(?!\w)"
            )
            return bool(
                re.search(
                    rf"(?:{value_pattern}.{{0,48}}{cue_pattern}|"
                    rf"{cue_pattern}.{{0,48}}{value_pattern})",
                    normalized,
                )
            )
        if isinstance(value, (int, float)):
            number_words = {
                0: "zero",
                1: "one",
                2: "two",
                3: "three",
                4: "four",
                5: "five",
                6: "six",
                7: "seven",
                8: "eight",
                9: "nine",
                10: "ten",
            }
            number_forms = [re.escape(str(value))]
            if isinstance(value, int) and value in number_words:
                number_forms.append(number_words[value])
            number_pattern = r"(?<!\w)(?:" + "|".join(number_forms) + r")(?!\w)"
            if not re.search(number_pattern, normalized):
                return False
            cue_terms = NUMERIC_DETAIL_CUES.get(key)
            if key == "count" and predicate is not None:
                cue_terms = ACTION_WORDS.get(predicate)
            if not cue_terms:
                return False
            cue_pattern = (
                r"(?<!\w)(?:"
                + "|".join(
                    re.escape(term) for term in sorted(set(cue_terms), key=len, reverse=True)
                )
                + r")(?!\w)"
            )
            return bool(
                re.search(
                    rf"(?:{number_pattern}.{{0,32}}{cue_pattern}|"
                    rf"{cue_pattern}.{{0,32}}{number_pattern})",
                    normalized,
                )
            )
        if isinstance(value, list):
            return any(
                isinstance(item, str) and item.casefold().replace("_", " ") in normalized
                for item in value
            )
        return False

    @staticmethod
    def _event_predicate(event) -> ClaimPredicate:
        predicate = EVENT_PREDICATES[event.event_type]
        if event.actor_id is None and event.target_id is not None:
            if event.event_type == CanonicalEventType.KNOCK:
                return ClaimPredicate.WAS_KNOCKED
            if event.event_type == CanonicalEventType.ELIMINATION:
                return ClaimPredicate.WAS_ELIMINATED
        return predicate

    def _infer_literal_evidence_ids(
        self,
        text: str,
        *,
        selected_events: dict[str, object],
        match,
        prepared: PreparedInterpretationV2,
        perspective_player_id: str | None = None,
    ) -> list[str]:
        """Resolve literal prose terms to selected-window facts without interpreting meaning."""

        normalized = text.casefold()
        mentioned_players = {
            player.player_id
            for player in prepared.normalized.players
            if player.memory_eligible and contains_identity(text, player.display_name)
        }
        if perspective_player_id and re.search(
            r"(?<!\w)(?:i|me|my|you|your)(?!\w)",
            normalized,
        ):
            mentioned_players.add(perspective_player_id)
        mentioned_locations = {
            event.location
            for event in selected_events.values()
            if event.location and contains_identity(text, event.location)
        }
        mentioned_predicates = {
            predicate
            for predicate, terms in ACTION_WORDS.items()
            if any(action_language_present(normalized, term) for term in terms)
        }
        mentioned_details = {
            (key, json.dumps(value, sort_keys=True))
            for event in selected_events.values()
            for key, value in event.details.items()
            if self._detail_is_mentioned(
                text,
                key,
                value,
                predicate=self._event_predicate(event),
            )
        }

        def predicate_matches(event, predicate: ClaimPredicate) -> bool:
            actual = self._event_predicate(event)
            if predicate == ClaimPredicate.KNOCKED:
                return actual in {ClaimPredicate.KNOCKED, ClaimPredicate.WAS_KNOCKED}
            if predicate == ClaimPredicate.ELIMINATED:
                return actual in {
                    ClaimPredicate.ELIMINATED,
                    ClaimPredicate.WAS_ELIMINATED,
                }
            return actual == predicate

        def event_score(event) -> int:
            return (
                sum(
                    player_id in {event.actor_id, event.target_id}
                    for player_id in mentioned_players
                )
                + sum(event.location == location for location in mentioned_locations)
                + sum(
                    predicate_matches(event, predicate)
                    for predicate in mentioned_predicates
                    if predicate in EVENT_PREDICATES.values()
                    or predicate
                    in {
                        ClaimPredicate.WAS_KNOCKED,
                        ClaimPredicate.WAS_ELIMINATED,
                    }
                )
                + sum(
                    json.dumps(event.details.get(key), sort_keys=True) == encoded_value
                    for key, encoded_value in mentioned_details
                )
            )

        ordered_events = list(selected_events.items())
        inferred: list[str] = []
        constraints = [
            [
                (event_id, event)
                for event_id, event in ordered_events
                if player_id in {event.actor_id, event.target_id}
            ]
            for player_id in mentioned_players
        ]
        constraints.extend(
            [(event_id, event) for event_id, event in ordered_events if event.location == location]
            for location in mentioned_locations
        )
        constraints.extend(
            [
                (event_id, event)
                for event_id, event in ordered_events
                if json.dumps(event.details.get(key), sort_keys=True) == encoded_value
            ]
            for key, encoded_value in mentioned_details
        )
        constraints.extend(
            [
                (event_id, event)
                for event_id, event in ordered_events
                if predicate_matches(event, predicate)
            ]
            for predicate in mentioned_predicates
            if predicate in EVENT_PREDICATES.values()
            or predicate
            in {
                ClaimPredicate.KNOCKED,
                ClaimPredicate.WAS_KNOCKED,
                ClaimPredicate.ELIMINATED,
                ClaimPredicate.WAS_ELIMINATED,
            }
        )
        event_order = {event_id: index for index, (event_id, _) in enumerate(ordered_events)}
        for candidates in constraints:
            if not candidates:
                continue
            event_id, _ = max(
                candidates,
                key=lambda item: (event_score(item[1]), -event_order[item[0]]),
            )
            if event_id not in inferred:
                inferred.append(event_id)

        match_values = {
            "match:game": match.game.replace("_", " "),
            "match:mode": match.mode.replace("_", " "),
            "match:map": match.map_name,
            "match:result": match.result,
        }
        inferred.extend(
            evidence_id
            for evidence_id, value in match_values.items()
            if value and value.casefold() in normalized and evidence_id not in inferred
        )
        if match.placement is not None and re.search(
            rf"(?<!\d){match.placement}(?!\d)",
            normalized,
        ):
            inferred.append("match:placement")
        return inferred

    def _context_claim(
        self,
        evidence_id: str,
        *,
        output_section: str,
        claim_id: str,
        match,
        prepared: PreparedInterpretationV2,
    ) -> GroundedClaim:
        if evidence_id in COMPACT_MATCH_EVIDENCE:
            predicate, field = COMPACT_MATCH_EVIDENCE[evidence_id]
            value = {
                "game": match.game,
                "mode": match.mode,
                "map": match.map_name,
                "placement": match.placement,
                "result": match.result,
            }[field]
            return GroundedClaim(
                claim_id=claim_id,
                output_section=output_section,
                subject_id="squad",
                predicate=predicate,
                value=value,
                supporting_context_ids=[f"match:{match.match_id}:{field}"],
            )
        return GroundedClaim(
            claim_id=claim_id,
            output_section=output_section,
            subject_id="squad",
            predicate=ClaimPredicate.CURRENT_REUNION_OPPORTUNITY,
            value=self._context_value(evidence_id, prepared),
            supporting_context_ids=[evidence_id],
        )

    @staticmethod
    def _ordered_event_evidence(evidence_ids: list[str], ordering: list[str]) -> list[str]:
        evidence_set = set(evidence_ids)
        if len(evidence_set) != len(evidence_ids) or not evidence_set.issubset(ordering):
            raise CompactProposalExpansionError("perspective_claim_evidence_mismatch")
        return [event_id for event_id in ordering if event_id in evidence_set]

    @staticmethod
    def _fail_on_fatal_content(
        prepared: PreparedInterpretationV2,
        compact: CompactMemoryProposalV2,
    ) -> None:
        serialized = json.dumps(compact.model_dump(mode="json"), ensure_ascii=False)
        if any(contains_identity(serialized, term) for term in prepared.forbidden_identity_terms):
            raise CompactProposalExpansionError("privacy_identity_leak")
        if contains_secret_like(serialized):
            raise CompactProposalExpansionError("secret_exposure")
        if contains_unsafe_player_content(serialized):
            raise CompactProposalExpansionError("unsafe_generated_content")
        mission_text = " ".join(
            (
                compact.mission.title,
                compact.mission.mission,
                compact.mission.objective_description,
            )
        )
        if UNSAFE_MISSION_PATTERN.search(mission_text):
            raise CompactProposalExpansionError("unsafe_mission_content")

    @classmethod
    def _without_reference_metadata(
        cls,
        prepared: PreparedInterpretationV2,
        compact: CompactMemoryProposalV2,
    ) -> CompactMemoryProposalV2:
        """Remove copied technical IDs from prose while retaining typed reference fields."""

        assert prepared.normalized is not None
        assert prepared.ledger is not None
        references = {
            *(fact.evidence_id for fact in prepared.ledger.facts),
            *(player.player_id for player in prepared.normalized.players),
            *(match.match_id for match in prepared.normalized.matches),
            *(window.window_id for window in prepared.windows),
            *(candidate.candidate_id for candidate in prepared.mission_candidates),
            *(candidate.verification.metric for candidate in prepared.mission_candidates),
            *(candidate.verification.operator for candidate in prepared.mission_candidates),
            *(media.media_id for media in prepared.normalized.media_references),
            *COMPACT_MATCH_EVIDENCE,
            *COMPACT_CONTEXT_EVIDENCE,
        }

        def clean(value: str) -> str:
            return cls._clean_reference_metadata(value, references)

        return compact.model_copy(
            update={
                "title": compact.title.model_copy(update={"text": clean(compact.title.text)}),
                "notification_teaser": compact.notification_teaser.model_copy(
                    update={"text": clean(compact.notification_teaser.text)}
                ),
                "summary": compact.summary.model_copy(update={"text": clean(compact.summary.text)}),
                "why_this_matters_now": compact.why_this_matters_now.model_copy(
                    update={"text": clean(compact.why_this_matters_now.text)}
                ),
                "perspectives": [
                    perspective.model_copy(update={"message": clean(perspective.message)})
                    for perspective in compact.perspectives
                ],
                "mission": compact.mission.model_copy(
                    update={
                        "title": clean(compact.mission.title),
                        "mission": clean(compact.mission.mission),
                        "objective_description": clean(compact.mission.objective_description),
                    }
                ),
            }
        )

    @staticmethod
    def _clean_reference_metadata(text: str, references: set[str]) -> str:
        cleaned = text
        for reference in sorted(references, key=len, reverse=True):
            cleaned = re.sub(re.escape(reference), "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\(\s*[,;]*\s*\)", "", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"([,;])\s*([,;])", r"\1", cleaned)
        cleaned = " ".join(cleaned.split()).strip(" ,;:")
        return cleaned

    @staticmethod
    def _context_value(evidence_id: str, prepared: PreparedInterpretationV2):
        assert prepared.normalized is not None
        values = {
            "context:previous_session_at": [
                item.isoformat() for item in prepared.normalized.squad_history.previous_session_at
            ],
            "context:days_since_full_squad": (
                prepared.normalized.squad_history.days_since_full_squad
            ),
            "context:recent_rematch_count": (
                prepared.normalized.squad_history.recent_rematch_count
            ),
            "context:active_player_ids": prepared.normalized.current_context.active_player_ids,
            "context:available_modes": prepared.normalized.current_context.available_modes,
            "context:reunion_eligible": prepared.normalized.current_context.reunion_eligible,
        }
        return values[evidence_id]
