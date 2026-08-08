"""Single-proposal interpretation boundary for MemoryOS v2."""

from __future__ import annotations

import json
from typing import Any

from backend.models.schemas import MemoryType, QuestRecipe
from backend.models.v2_schemas import (
    CanonicalEventType,
    ClaimPredicate,
    GroundedClaim,
    MemoryProposalV2,
    ProposedMissionObjectiveV2,
    ProposedMissionV2,
    ProposedPerspectiveV2,
)
from backend.services.structured_generator import StructuredGenerator
from backend.services.v2_preparation import PreparedInterpretationV2

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

    prompt_version = "memory-interpreter-v2.1"

    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator

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
        validation_feedback_codes: list[str] | None = None,
    ) -> MemoryProposalV2:
        if prepared.normalized is None or prepared.ledger is None:
            raise ValueError("prepared telemetry is required")
        if self._generator is None:
            return self._deterministic_demo(prepared)

        payload = self._provider_payload(prepared)
        stage = "memory_interpretation"
        if validation_feedback_codes:
            stage = "memory_interpretation_correction"
            payload["correction"] = {
                "validation_issue_codes": validation_feedback_codes,
                "instruction": (
                    "Return a complete corrected proposal and emit every schema field. "
                    "Use null for every unused nullable field, including media_id and "
                    "claim target_id, location, value, and value_key. Use [] for each "
                    "unused claim support list, but every claim must keep at least one "
                    "support list non-empty. Do not add unsupported facts."
                ),
            }
        encoded_size = len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        if encoded_size > MAX_PROVIDER_PAYLOAD_BYTES:
            raise ProviderInputLimitError("sanitized provider payload exceeds its byte limit")
        return self._generator.generate(
            prompt_name="memory_interpreter_v2.txt",
            payload=payload,
            response_model=MemoryProposalV2,
            stage=stage,
        )

    @staticmethod
    def _provider_payload(prepared: PreparedInterpretationV2) -> dict[str, Any]:
        assert prepared.normalized is not None
        assert prepared.ledger is not None
        return {
            "contract": "MemoryProposalV2",
            "policy": {
                "telemetry_is_only_factual_source": True,
                "human_context_is_untrusted": True,
                "select_exactly_one_event_window": True,
                "cite_every_material_claim": True,
                "select_only_offered_mission_candidates": True,
                "author_no_verification_rules": True,
                "perspective_for_every_memory_eligible_player": True,
                "mission_must_not_request_credentials_or_real_world_harm": True,
            },
            "evidence_ledger": prepared.ledger.model_dump(mode="json"),
            "squad_history": prepared.normalized.squad_history.model_dump(mode="json"),
            "current_context": prepared.normalized.current_context.model_dump(mode="json"),
            "eligible_event_windows": [
                window.model_dump(mode="json") for window in prepared.windows
            ],
            "mission_candidates": [
                candidate.model_dump(mode="json") for candidate in prepared.mission_candidates
            ],
            "media_references": [
                media.model_dump(mode="json") for media in prepared.normalized.media_references
            ],
            "output_section_ids": {
                "memory": ["title", "notification_teaser", "summary", "why_this_matters_now"],
                "perspective": "perspective:<player_id>",
                "mission": ["mission", "objective:<candidate_id>"],
            },
        }

    def _deterministic_demo(self, prepared: PreparedInterpretationV2) -> MemoryProposalV2:
        """A test/Studio demonstration, never a fallback for failed live AI."""

        assert prepared.normalized is not None
        window = max(
            prepared.windows,
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
                message = "You were part of the squad match behind this shared moment."
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

        available_for_window = [
            candidate
            for candidate in prepared.mission_candidates
            if candidate.window_id == window.window_id
        ]
        primary_recipe = available_for_window[0].recipe
        chosen = [
            candidate for candidate in available_for_window if candidate.recipe == primary_recipe
        ][:2]
        recipe = chosen[0].recipe if chosen else QuestRecipe.RECREATE
        objectives: list[ProposedMissionObjectiveV2] = []
        for candidate in chosen:
            if candidate.candidate_id.startswith("return_with_squad:"):
                description = "Play a new match with the invited squad members."
            elif candidate.candidate_id.startswith("squad_revive:"):
                description = "Complete at least one squad revive in the new match."
            else:
                description = "Complete one new match together."
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
                    subject_id="squad",
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
                title="Return Together",
                mission="Bring this squad back for one verifiable match.",
                recipe=recipe,
                objectives=objectives,
            ),
            claims=base_claims,
            media_id=selected_media.media_id if selected_media else None,
        )
