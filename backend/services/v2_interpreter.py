"""Single-proposal interpretation boundary for MemoryOS v2."""

from __future__ import annotations

import json
from typing import Any

from backend.models.schemas import MemoryType, QuestRecipe
from backend.models.v2_schemas import (
    CanonicalEventType,
    ClaimPredicate,
    CompactInterpretationDecisionV2,
    CompactMemoryProposalV2,
    CompactMissionChoiceV2,
    CompactMissionObjectiveDraftV2,
    CompactPerspectiveV2,
    CompactSectionDraftV2,
    GroundedClaim,
    InterpretationAbstentionReasonV2,
    InterpretationDecisionKindV2,
    MemoryProposalV2,
    MissionFamilyV2,
    ProposedMissionObjectiveV2,
    ProposedMissionV2,
    ProposedPerspectiveV2,
)
from backend.services.structured_generator import StructuredGenerator
from backend.services.v2_preparation import PreparedInterpretationV2
from backend.services.v2_proposal_expander import CompactProposalExpanderV2

MAX_PROVIDER_PAYLOAD_BYTES = 96_000


class ProviderInputLimitError(ValueError):
    """The sanitized prompt projection exceeded a deterministic provider boundary."""


EVENT_LANGUAGE: dict[CanonicalEventType, tuple[ClaimPredicate, str]] = {
    CanonicalEventType.LANDING: (ClaimPredicate.LANDED, "landed"),
    CanonicalEventType.KNOCK: (ClaimPredicate.KNOCKED, "knocked an opponent"),
    CanonicalEventType.ELIMINATION: (ClaimPredicate.ELIMINATED, "secured an elimination"),
    CanonicalEventType.REVIVE: (ClaimPredicate.REVIVED, "revived a squadmate"),
    CanonicalEventType.ASSIST: (ClaimPredicate.ASSISTED, "recorded an assist"),
    CanonicalEventType.HEAL: (ClaimPredicate.HEALED, "recovered health"),
    CanonicalEventType.VEHICLE_ENTER: (
        ClaimPredicate.ENTERED_VEHICLE,
        "entered a vehicle",
    ),
    CanonicalEventType.VEHICLE_EXIT: (ClaimPredicate.EXITED_VEHICLE, "left a vehicle"),
    CanonicalEventType.ESCAPE: (ClaimPredicate.ESCAPED, "escaped the area"),
    CanonicalEventType.ZONE_MOVE: (ClaimPredicate.MOVED_ZONE, "rotated toward safety"),
    CanonicalEventType.LOOT: (ClaimPredicate.LOOTED, "collected supplies"),
    CanonicalEventType.SIGNAL: (ClaimPredicate.SIGNALLED, "placed a tactical signal"),
    CanonicalEventType.MATCH_COMPLETE: (
        ClaimPredicate.COMPLETED_MATCH,
        "completed the match",
    ),
}


class MemoryInterpreterV2:
    """Ask one live provider for a complete proposal, or run an explicit demo interpreter."""

    prompt_version = "memory-interpreter-v2.6-mission-affordances"

    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator
        self._expander = CompactProposalExpanderV2()

    @property
    def provider_name(self) -> str:
        return self._generator.provider_name if self._generator else "deterministic"

    @property
    def model_name(self) -> str:
        return self._generator.model_name if self._generator else "grounded-demo-v2"

    @property
    def mode(self) -> str:
        return "live_ai" if self._generator else "deterministic_demo"

    @property
    def observability(self) -> dict[str, object]:
        value = getattr(self._generator, "observability", {})
        return dict(value) if isinstance(value, dict) else {}

    def validate_configuration(self) -> None:
        validate = getattr(self._generator, "validate_configuration", None)
        if validate:
            validate()

    def propose(
        self,
        prepared: PreparedInterpretationV2,
        *,
        validation_feedback: list[dict[str, str]] | None = None,
    ) -> MemoryProposalV2 | InterpretationAbstentionReasonV2:
        if prepared.normalized is None or prepared.ledger is None or prepared.story_brief is None:
            raise ValueError("prepared telemetry is required")
        if self._generator is None:
            return self._deterministic_demo(prepared)

        payload = self._provider_payload(prepared)
        stage = "memory_interpretation"
        if validation_feedback:
            stage = "memory_interpretation_correction"
            payload["correction"] = {
                "validation_issues": validation_feedback,
                "instruction": (
                    "Return one complete corrected CompactInterpretationDecisionV2 and emit "
                    "every schema field. Resolve each issue in its allowlisted section when "
                    "supplied. This is a strict rewrite, not an edit: do not carry over any "
                    "unsupported context from a prior draft. Rank only offered affordances, put "
                    "the selection first, use only its reason codes, and describe every compiled "
                    "objective. When text mentions a player, action, location, match value, "
                    "category, or number, cite exact support or remove that wording."
                ),
                "strict_section_rules": {
                    "story": (
                        "Use only literal facts from the selected evidence IDs. Do not use a "
                        "category word such as a vehicle, zone, weapon, item, or ping type unless "
                        "the cited event carries that exact typed value."
                    ),
                    "perspectives": (
                        "Write one short first-person sentence per narrator. It may describe only "
                        "that narrator's direct actor or target event, or a cited full-squad event "
                        "using we/the squad. Do not mention any other player's action, including "
                        "as before/after context."
                    ),
                    "mission": (
                        "Use only the selected affordance and its referenced objective candidates. "
                        "Do not mention a past event, location, outcome, or player unless that "
                        "affordance explicitly allows it."
                    ),
                },
            }
        encoded_size = len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        if encoded_size > MAX_PROVIDER_PAYLOAD_BYTES:
            raise ProviderInputLimitError("sanitized provider payload exceeds its byte limit")
        decision = self._generator.generate(
            prompt_name="memory_interpreter_v2_6.txt",
            payload=payload,
            response_model=CompactInterpretationDecisionV2,
            stage=stage,
        )
        # Compatibility for test generators and v2.0 provider fixtures during migration.
        if isinstance(decision, CompactMemoryProposalV2):
            decision = CompactInterpretationDecisionV2(
                decision=InterpretationDecisionKindV2.GENERATE,
                abstention_reason_code=None,
                proposal=decision,
            )
        if decision.decision == InterpretationDecisionKindV2.ABSTAIN:
            assert decision.abstention_reason_code is not None
            return decision.abstention_reason_code
        assert decision.proposal is not None
        return self._expander.expand(prepared, decision.proposal)

    @staticmethod
    def _provider_payload(prepared: PreparedInterpretationV2) -> dict[str, Any]:
        assert prepared.normalized is not None
        assert prepared.ledger is not None
        assert prepared.story_brief is not None
        return {
            "contract": "CompactInterpretationDecisionV2",
            # Empty optional placeholders add tokens but carry no evidence. Keep every
            # concrete value—including false privacy/capability signals—while omitting
            # only nulls from the provider projection.
            "story_brief": prepared.story_brief.model_dump(
                mode="json",
                exclude_none=True,
            ),
        }

    def demo_compact_proposal(
        self,
        prepared: PreparedInterpretationV2,
    ) -> CompactMemoryProposalV2:
        """Return a compact deterministic fixture for provider-boundary tests."""

        canonical = self._deterministic_demo(prepared)
        objectives = canonical.mission.objectives
        return CompactMemoryProposalV2(
            selected_window_id=canonical.selected_window_id,
            memory_type=canonical.memory_type,
            narrative_angle=canonical.narrative_angle,
            title=self._compact_section(canonical, "title", canonical.title),
            notification_teaser=self._compact_section(
                canonical,
                "notification_teaser",
                canonical.notification_teaser,
            ),
            summary=self._compact_section(canonical, "summary", canonical.summary),
            why_this_matters_now=self._compact_section(
                canonical,
                "why_this_matters_now",
                canonical.why_this_matters_now,
            ),
            perspectives=[
                CompactPerspectiveV2(
                    player_id=item.player_id,
                    message=item.message,
                    evidence_ids=item.evidence_event_ids,
                )
                for item in canonical.perspectives
            ],
            mission=CompactMissionChoiceV2(
                ranked_affordance_ids=canonical.mission.ranked_affordance_ids,
                selected_affordance_id=canonical.mission.affordance_id,
                selection_reason_codes=canonical.mission.selection_reason_codes,
                title=canonical.mission.title,
                mission=canonical.mission.mission,
                objective_descriptions=[
                    CompactMissionObjectiveDraftV2(
                        candidate_id=objective.candidate_id,
                        description=objective.description,
                    )
                    for objective in objectives
                ],
            ),
        )

    @classmethod
    def _compact_section(
        cls,
        canonical: MemoryProposalV2,
        output_section: str,
        text: str,
    ) -> CompactSectionDraftV2:
        evidence_ids: list[str] = []
        for claim in canonical.claims:
            if claim.output_section != output_section:
                continue
            evidence_ids.extend(claim.supporting_event_ids)
            evidence_ids.extend(
                cls._compact_context_id(context_id, canonical.selected_match_id)
                for context_id in claim.supporting_context_ids
            )
        return CompactSectionDraftV2(
            text=text,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
        )

    @staticmethod
    def _compact_context_id(context_id: str, selected_match_id: str) -> str:
        prefix = f"match:{selected_match_id}:"
        if context_id.startswith(prefix):
            return f"match:{context_id[len(prefix) :]}"
        return context_id

    def _deterministic_demo(self, prepared: PreparedInterpretationV2) -> MemoryProposalV2:
        """A test/Studio demonstration, never a fallback for failed live AI."""

        assert prepared.normalized is not None
        affordance_window_ids = {item.window_id for item in prepared.mission_affordances}
        window = max(
            [item for item in prepared.windows if item.window_id in affordance_window_ids],
            key=lambda item: (len(item.event_ids), len(item.participant_ids), item.window_id),
        )
        matches = {match.match_id: match for match in prepared.normalized.matches}
        match = matches[window.match_id]
        event_map = {event.event_id: event for event in match.events}
        events = [event_map[event_id] for event_id in window.event_ids]
        people = {player.player_id: player for player in prepared.normalized.players}
        location = next((event.location for event in events if event.location), None)
        place_phrase = f" at {location}" if location else ""
        event_types = {event.event_type for event in events}
        if CanonicalEventType.REVIVE in event_types:
            memory_type = MemoryType.COMEBACK
            angle = "A squadmate recovery connected a short sequence of shared actions."
        elif CanonicalEventType.ESCAPE in event_types:
            memory_type = MemoryType.CHAOS
            angle = "Several squad actions formed one connected escape sequence."
        elif CanonicalEventType.KNOCK in event_types:
            memory_type = MemoryType.CLUTCH
            angle = "The squad's actions converged during a compact combat sequence."
        else:
            memory_type = MemoryType.OTHER
            angle = "The telemetry shows a connected sequence involving the squad."

        title = f"A Squad Moment{place_phrase}"
        teaser = f"Your squad shared a connected moment{place_phrase}."
        sentences: list[str] = []
        action_claims: list[GroundedClaim] = []
        for index, event in enumerate(events[:3], start=1):
            predicate, language = EVENT_LANGUAGE[event.event_type]
            if event.event_type == CanonicalEventType.KNOCK and event.actor_id is None:
                predicate, language = ClaimPredicate.WAS_KNOCKED, "was knocked"
            elif event.event_type == CanonicalEventType.ELIMINATION and event.actor_id is None:
                predicate, language = ClaimPredicate.WAS_ELIMINATED, "was eliminated"
            subject_id = event.actor_id or event.target_id or "squad"
            name = people.get(subject_id).display_name if subject_id in people else "The squad"
            target_name = (
                people[event.target_id].display_name
                if event.target_id and event.target_id in people
                else None
            )
            suffix = f" for {target_name}" if target_name and event.target_id != subject_id else ""
            event_place = f" at {event.location}" if event.location else ""
            sentences.append(f"{name} {language}{suffix}{event_place}.")
            action_claims.append(
                GroundedClaim(
                    claim_id=f"claim:summary:{index}",
                    output_section="summary",
                    subject_id=subject_id,
                    predicate=predicate,
                    target_id=(
                        None
                        if predicate in {ClaimPredicate.WAS_KNOCKED, ClaimPredicate.WAS_ELIMINATED}
                        else event.target_id
                    ),
                    location=event.location,
                    supporting_event_ids=[event.event_id],
                )
            )
        summary = " ".join(sentences)
        if not summary:
            summary = f"The squad completed a connected sequence{place_phrase}."

        base_claims = [
            GroundedClaim(
                claim_id=f"claim:{section}",
                output_section=section,
                subject_id="squad",
                predicate=ClaimPredicate.CONNECTED_EPISODE,
                location=location,
                supporting_event_ids=window.event_ids,
            )
            for section in ("title", "notification_teaser")
        ]
        base_claims.extend(action_claims)

        history = prepared.normalized.squad_history
        if history.days_since_full_squad is not None:
            why_now = (
                f"It has been {history.days_since_full_squad} days since the full squad played."
            )
            context_ids = ["context:days_since_full_squad"]
            context_value: int | list[str] = history.days_since_full_squad
        else:
            why_now = "The current squad context allows a reunion invitation."
            context_ids = ["context:reunion_eligible"]
            context_value = True
        base_claims.append(
            GroundedClaim(
                claim_id="claim:why-now",
                output_section="why_this_matters_now",
                subject_id="squad",
                predicate=ClaimPredicate.CURRENT_REUNION_OPPORTUNITY,
                value=context_value,
                supporting_context_ids=context_ids,
            )
        )

        perspectives: list[ProposedPerspectiveV2] = []
        for player in prepared.normalized.players:
            if not player.memory_eligible:
                continue
            direct = next(
                (
                    event
                    for event in events
                    if player.player_id in {event.actor_id, event.target_id}
                ),
                None,
            )
            if direct and direct.actor_id == player.player_id:
                predicate, language = EVENT_LANGUAGE[direct.event_type]
                direct_place = f" at {direct.location}" if direct.location else ""
                message = f"You {language}{direct_place}; that action became part of this moment."
                target_id = direct.target_id
            else:
                predicate = ClaimPredicate.PARTICIPATED_MATCH
                message = (
                    f"{player.display_name}, you were part of the squad match behind this "
                    "shared moment."
                )
                target_id = None
            evidence_ids = [direct.event_id] if direct else [window.event_ids[0]]
            perspectives.append(
                ProposedPerspectiveV2(
                    player_id=player.player_id,
                    message=message,
                    evidence_event_ids=evidence_ids,
                )
            )
            base_claims.append(
                GroundedClaim(
                    claim_id=f"claim:perspective:{player.player_id}",
                    output_section=f"perspective:{player.player_id}",
                    subject_id=player.player_id,
                    predicate=predicate,
                    target_id=target_id,
                    location=direct.location if direct else None,
                    supporting_event_ids=evidence_ids,
                )
            )

        available_affordances = [
            affordance
            for affordance in prepared.mission_affordances
            if affordance.window_id == window.window_id
        ]
        family_priority = {
            MissionFamilyV2.ROLE_REVERSAL: 0,
            MissionFamilyV2.REDEMPTION: 1,
            MissionFamilyV2.REUNION: 2,
        }
        selected_affordance = min(
            available_affordances,
            key=lambda item: (family_priority[item.family], item.affordance_id),
        )
        candidate_map = {
            candidate.candidate_id: candidate for candidate in prepared.mission_candidates
        }
        chosen = [
            candidate_map[candidate_id]
            for candidate_id in selected_affordance.objective_candidate_ids
        ]
        recipe = chosen[0].recipe if chosen else QuestRecipe.RECREATE
        objectives: list[ProposedMissionObjectiveV2] = []
        for candidate in chosen:
            if candidate.verification.metric == "squad.participant_ids":
                description = "Play a new match with the invited squad members."
            elif candidate.verification.metric == "squad.matches_completed":
                description = "Complete one new match together."
            elif candidate.verification.metric == "match.first_squad_revive_actor_id":
                assigned = people[str(candidate.verification.target)].display_name
                description = f"Have {assigned} complete the squad's first revival."
            else:
                description = "Reach the top three in the new match."
            objectives.append(
                ProposedMissionObjectiveV2(
                    candidate_id=candidate.candidate_id,
                    description=description,
                )
            )
            base_claims.append(
                GroundedClaim(
                    claim_id=f"claim:objective:{candidate.candidate_id}",
                    output_section=f"objective:{candidate.candidate_id}",
                    subject_id=candidate.assigned_player_id or "squad",
                    predicate=ClaimPredicate.MISSION_RULE,
                    supporting_mission_candidate_ids=[candidate.candidate_id],
                )
            )
        base_claims.append(
            GroundedClaim(
                claim_id="claim:mission",
                output_section="mission",
                subject_id="squad",
                predicate=ClaimPredicate.MISSION_RULE,
                supporting_mission_candidate_ids=[item.candidate_id for item in chosen],
            )
        )
        selected_media = next(
            (
                media
                for media in prepared.normalized.media_references
                if set(media.event_ids).issubset(window.event_ids)
            ),
            None,
        )
        if selected_affordance.family == MissionFamilyV2.ROLE_REVERSAL:
            assigned_id = str(
                next(
                    candidate.verification.target
                    for candidate in chosen
                    if candidate.verification.metric == "match.first_squad_revive_actor_id"
                )
            )
            assigned_name = people[assigned_id].display_name
            mission_title = "Return the Favour"
            mission_text = (
                "Play one new match with the invited squad and have "
                f"{assigned_name} complete the squad's first revival."
            )
        elif selected_affordance.family == MissionFamilyV2.REDEMPTION:
            mission_title = "Finish the Final Circle"
            mission_text = (
                "Play one new match with the invited squad and reach the top three together."
            )
        else:
            mission_title = "Return Together"
            mission_text = "Play one new match with the invited squad members."
        ranked_affordance_ids = [
            selected_affordance.affordance_id,
            *sorted(
                affordance.affordance_id
                for affordance in prepared.mission_affordances
                if affordance.affordance_id != selected_affordance.affordance_id
            ),
        ]
        return MemoryProposalV2(
            selected_match_id=window.match_id,
            selected_window_id=window.window_id,
            selected_event_ids=window.event_ids,
            memory_type=memory_type,
            narrative_angle=angle,
            title=title,
            notification_teaser=teaser,
            summary=summary,
            why_this_matters_now=why_now,
            perspectives=perspectives,
            mission=ProposedMissionV2(
                affordance_id=selected_affordance.affordance_id,
                family=selected_affordance.family,
                ranked_affordance_ids=ranked_affordance_ids,
                selection_reason_codes=[selected_affordance.allowed_reason_codes[0]],
                title=mission_title,
                mission=mission_text,
                recipe=recipe,
                objectives=objectives,
            ),
            claims=base_claims,
            media_id=selected_media.media_id if selected_media else None,
        )
