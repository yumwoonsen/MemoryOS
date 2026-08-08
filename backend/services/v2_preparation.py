"""Deterministic preparation for the telemetry-first v2 interpretation pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from backend.models.schemas import QuestRecipe, VerificationRule
from backend.models.v2_schemas import (
    CanonicalEventType,
    ConsentSafeEvidenceLedgerV2,
    CurrentContextV2,
    EligibleEventWindow,
    EvidenceFactV2,
    MediaReferenceV2,
    MissionCapabilityCandidate,
    NormalizedEventV2,
    NormalizedMatchV2,
    NormalizedPlayerV2,
    NormalizedTelemetryV2,
    RawTelemetryBatchV2,
    SocialContextV2,
    V2ValidationIssue,
)
from backend.services.identity import contains_identity, identifier_contains_identity

FREE_FIRE_EVENT_MAP: dict[str, tuple[CanonicalEventType, str]] = {
    "landing": (CanonicalEventType.LANDING, "actor_performs"),
    "land": (CanonicalEventType.LANDING, "actor_performs"),
    "player_landed": (CanonicalEventType.LANDING, "actor_performs"),
    "squad_member_landed": (CanonicalEventType.LANDING, "actor_performs"),
    "knock": (CanonicalEventType.KNOCK, "actor_performs"),
    # Garena-style PLAYER_KNOCKED identifies the victim in actor_id.  The adapter
    # deliberately converts that provider role instead of letting narrative code
    # guess whether the player dealt or received the knock.
    "player_knocked": (CanonicalEventType.KNOCK, "actor_is_target"),
    "enemy_knocked": (CanonicalEventType.KNOCK, "actor_performs"),
    "elimination": (CanonicalEventType.ELIMINATION, "actor_performs"),
    "kill": (CanonicalEventType.ELIMINATION, "actor_performs"),
    "player_eliminated": (CanonicalEventType.ELIMINATION, "actor_is_target"),
    "player_eliminated_opponent": (CanonicalEventType.ELIMINATION, "actor_performs"),
    "revive": (CanonicalEventType.REVIVE, "actor_performs"),
    "player_revived": (CanonicalEventType.REVIVE, "target_performs"),
    "teammate_revived": (CanonicalEventType.REVIVE, "actor_performs"),
    "assist": (CanonicalEventType.ASSIST, "actor_performs"),
    "kill_assist": (CanonicalEventType.ASSIST, "actor_performs"),
    "heal": (CanonicalEventType.HEAL, "actor_performs"),
    "player_healed": (CanonicalEventType.HEAL, "actor_performs"),
    "vehicle_enter": (CanonicalEventType.VEHICLE_ENTER, "actor_performs"),
    "entered_vehicle": (CanonicalEventType.VEHICLE_ENTER, "actor_performs"),
    "squad_entered_vehicle": (CanonicalEventType.VEHICLE_ENTER, "actor_performs"),
    "vehicle_exit": (CanonicalEventType.VEHICLE_EXIT, "actor_performs"),
    "exited_vehicle": (CanonicalEventType.VEHICLE_EXIT, "actor_performs"),
    "escape": (CanonicalEventType.ESCAPE, "actor_performs"),
    "vehicle_escape": (CanonicalEventType.ESCAPE, "actor_performs"),
    "squad_exited_damage_zone": (CanonicalEventType.ESCAPE, "actor_performs"),
    "zone_move": (CanonicalEventType.ZONE_MOVE, "actor_performs"),
    "zone_rotation": (CanonicalEventType.ZONE_MOVE, "actor_performs"),
    "loot": (CanonicalEventType.LOOT, "actor_performs"),
    "item_picked_up": (CanonicalEventType.LOOT, "actor_performs"),
    "tactical_ping_placed": (CanonicalEventType.SIGNAL, "actor_performs"),
    "match_complete": (CanonicalEventType.MATCH_COMPLETE, "actor_performs"),
    "match_end": (CanonicalEventType.MATCH_COMPLETE, "actor_performs"),
    "match_placement_recorded": (CanonicalEventType.MATCH_COMPLETE, "actor_performs"),
}

GAME_ALIASES = {
    "free_fire": "free_fire",
    "free fire": "free_fire",
    "freefire": "free_fire",
    "garena_free_fire": "free_fire",
}

ALLOWED_DETAIL_KEYS = {
    "count",
    "duration_seconds",
    "nearby_enemies",
    "passengers",
    "placement_reached",
    "squad_alive",
    "health_state",
    "zone_state",
    "weapon_class",
    "vehicle_type",
    "distance_meters",
    "rank_points",
    "item_type",
    "team_members_nearby",
    "zone_phase",
    "squad_members_aboard",
    "squad_members_alive",
    "placement",
    "ping_type",
}

INTEGER_DETAIL_KEYS = {
    "count",
    "duration_seconds",
    "nearby_enemies",
    "passengers",
    "placement_reached",
    "squad_alive",
    "distance_meters",
    "rank_points",
    "team_members_nearby",
    "zone_phase",
    "squad_members_aboard",
    "squad_members_alive",
    "placement",
}

ALLOWED_DETAIL_STATES = {
    "health_state": {"critical", "low", "stable", "full", "unknown"},
    "zone_state": {"closing", "closed", "safe", "shrinking", "unknown"},
}

MAX_ELIGIBLE_WINDOWS = 6
MAX_WINDOW_EVENTS = 10
MAX_WINDOW_SPAN_SECONDS = 120
MAX_PROVIDER_EVENTS = MAX_ELIGIBLE_WINDOWS * MAX_WINDOW_EVENTS
MAX_PROVIDER_CORE_BYTES = 80_000


@dataclass(frozen=True)
class PreparedInterpretationV2:
    normalized: NormalizedTelemetryV2 | None
    ledger: ConsentSafeEvidenceLedgerV2 | None
    windows: list[EligibleEventWindow]
    mission_candidates: list[MissionCapabilityCandidate]
    issues: list[V2ValidationIssue]
    privacy_redaction_count: int
    forbidden_identity_terms: frozenset[str]


class TelemetryPreparerV2:
    """Normalize Free Fire telemetry, enforce privacy, and create neutral candidates."""

    def prepare(self, batch: RawTelemetryBatchV2) -> PreparedInterpretationV2:
        issues: list[V2ValidationIssue] = []
        raw_players = {player.player_id: player for player in batch.squad.players}
        forbidden_terms = {
            term
            for player in batch.squad.players
            if not player.consent.memory_appearance or not player.consent.identity_display
            for term in (player.player_id, player.display_name)
            if term
        }
        if not raw_players[batch.target_player_id].consent.memory_appearance:
            issues.append(self._issue("target_not_consented", "Target player has not opted in."))

        eligible_players = [
            player for player in batch.squad.players if player.consent.memory_appearance
        ]
        if len(eligible_players) < 2:
            issues.append(
                self._issue(
                    "insufficient_consented_players",
                    "At least two consented squad members are required.",
                )
            )
        if not batch.current_context.reunion_eligible:
            issues.append(
                self._issue("reunion_not_eligible", "Current context does not allow a reunion.")
            )

        opaque_ids = [
            batch.request_id,
            batch.squad.squad_id,
            *(match.match_id for match in batch.matches),
            *(event.event_id for match in batch.matches for event in match.events),
            *(media.media_id for media in batch.media_references),
        ]
        if any(
            identifier_contains_identity(identifier, term)
            for identifier in opaque_ids
            for term in forbidden_terms
        ):
            issues.append(
                self._issue(
                    "opaque_identifier_contains_private_identity",
                    "Opaque identifiers cannot contain an opted-out identity.",
                )
            )

        telemetry_strings = [
            value
            for match in batch.matches
            for event in match.events
            for value in (
                event.location,
                *(item for item in event.details.values() if isinstance(item, str)),
            )
            if isinstance(value, str)
        ]
        if any(
            contains_identity(value, term)
            for value in telemetry_strings
            for term in forbidden_terms
        ):
            issues.append(
                self._issue(
                    "telemetry_identity_leak",
                    "Telemetry text contains an identity that is outside the consent boundary.",
                )
            )

        aliases: dict[str, str] = {}
        normalized_players: list[NormalizedPlayerV2] = []
        privacy_redaction_count = 0
        for roster_index, player in enumerate(batch.squad.players, start=1):
            if not player.consent.memory_appearance:
                privacy_redaction_count += 1
                safe_id = f"anonymous:squadmate:{roster_index}"
                display_name = "A squadmate"
                aliases[player.player_id] = safe_id
                normalized_players.append(
                    NormalizedPlayerV2(
                        player_id=safe_id,
                        display_name=display_name,
                        memory_eligible=False,
                        identity_visible=False,
                        media_eligible=False,
                        invitation_eligible=False,
                    )
                )
                continue
            if player.consent.identity_display and player.display_name:
                aliases[player.player_id] = player.player_id
                display_name = player.display_name
            else:
                privacy_redaction_count += 1
                aliases[player.player_id] = f"anonymous:squadmate:{roster_index}"
                display_name = f"Player {roster_index}"
            normalized_players.append(
                NormalizedPlayerV2(
                    player_id=aliases[player.player_id],
                    display_name=display_name,
                    memory_eligible=True,
                    identity_visible=player.consent.identity_display,
                    media_eligible=player.consent.media_use,
                    invitation_eligible=player.consent.mission_invitation,
                )
            )

        normalized_matches: list[NormalizedMatchV2] = []
        for match in batch.matches:
            game = GAME_ALIASES.get(match.game.strip().lower())
            if game is None:
                issues.append(
                    self._issue(
                        "unsupported_game_adapter",
                        f"No telemetry adapter is available for match {match.match_id}.",
                    )
                )
                continue
            events: list[NormalizedEventV2] = []
            for event in sorted(
                match.events, key=lambda item: (item.timestamp_seconds, item.event_id)
            ):
                mapping = FREE_FIRE_EVENT_MAP.get(event.provider_event_type.strip().lower())
                if mapping is None:
                    issues.append(
                        self._issue(
                            "unsupported_provider_event",
                            f"Event {event.event_id} has an unsupported provider event type.",
                        )
                    )
                    continue
                unsupported_keys = set(event.details) - ALLOWED_DETAIL_KEYS
                if unsupported_keys:
                    issues.append(
                        self._issue(
                            "unsupported_event_detail",
                            f"Event {event.event_id} contains unsupported detail fields.",
                        )
                    )
                    continue
                if not self._details_valid(event.details):
                    issues.append(
                        self._issue(
                            "invalid_event_detail",
                            f"Event {event.event_id} contains an invalid detail value.",
                        )
                    )
                    continue
                canonical_type, role_mapping = mapping
                actor_id = aliases.get(event.actor_id) if event.actor_id else None
                target_id = aliases.get(event.target_id) if event.target_id else None
                if role_mapping == "actor_is_target":
                    target_id, actor_id = actor_id, target_id
                elif role_mapping == "target_performs":
                    actor_id, target_id = target_id, actor_id
                events.append(
                    NormalizedEventV2(
                        event_id=event.event_id,
                        match_id=match.match_id,
                        event_type=canonical_type,
                        actor_id=actor_id,
                        target_id=target_id,
                        timestamp_seconds=event.timestamp_seconds,
                        location=event.location,
                        details=event.details,
                    )
                )
            normalized_matches.append(
                NormalizedMatchV2(
                    match_id=match.match_id,
                    game=game,
                    mode=match.mode,
                    map_name=match.map_name,
                    started_at=match.started_at,
                    ended_at=match.ended_at,
                    placement=match.placement,
                    result=match.result,
                    events=events,
                )
            )

        safe_active_ids = [
            aliases[player_id]
            for player_id in batch.current_context.active_player_ids
            if raw_players[player_id].consent.memory_appearance
        ]
        current_context = CurrentContextV2(
            active_player_ids=safe_active_ids,
            available_modes=batch.current_context.available_modes,
            reunion_eligible=batch.current_context.reunion_eligible,
        )
        safe_social = self._safe_social_context(batch, raw_players, aliases, forbidden_terms)
        safe_media = self._safe_media(batch, raw_players, aliases, issues)
        normalized = NormalizedTelemetryV2(
            request_id=batch.request_id,
            target_player_id=aliases[batch.target_player_id],
            squad_id=batch.squad.squad_id,
            players=normalized_players,
            matches=normalized_matches,
            squad_history=batch.squad_history,
            current_context=current_context,
            social_context=safe_social,
            media_references=safe_media,
        )
        windows = self._build_windows(normalized)
        if not windows:
            issues.append(
                self._issue(
                    "insufficient_connected_evidence",
                    "No consent-safe connected event window could be constructed.",
                )
            )
        offered_event_ids = {event_id for window in windows for event_id in window.event_ids}
        offered_match_ids = {window.match_id for window in windows}
        projected_matches = [
            match.model_copy(
                update={
                    "events": [
                        event for event in match.events if event.event_id in offered_event_ids
                    ]
                }
            )
            for match in normalized.matches
            if match.match_id in offered_match_ids
        ]
        projected_media = [
            media
            for media in normalized.media_references
            if set(media.event_ids).issubset(offered_event_ids)
        ]
        normalized = normalized.model_copy(
            update={"matches": projected_matches, "media_references": projected_media}
        )
        mission_candidates = self._mission_candidates(normalized, windows)
        if not mission_candidates:
            issues.append(
                self._issue(
                    "no_feasible_mission",
                    "No deterministic mission capability is available for this context.",
                )
            )
        ledger = self._ledger(normalized)
        provider_core = {
            "evidence_ledger": ledger.model_dump(mode="json"),
            "squad_history": normalized.squad_history.model_dump(mode="json"),
            "current_context": normalized.current_context.model_dump(mode="json"),
            "eligible_event_windows": [window.model_dump(mode="json") for window in windows],
            "mission_candidates": [
                candidate.model_dump(mode="json") for candidate in mission_candidates
            ],
            "media_references": [
                media.model_dump(mode="json") for media in normalized.media_references
            ],
        }
        outbound_strings = list(self._recursive_strings(provider_core))
        if any(
            contains_identity(value, term) for value in outbound_strings for term in forbidden_terms
        ):
            issues.append(
                self._issue(
                    "privacy_identity_leak_in_model_input",
                    "Consent-filtered model input still contains a private identity.",
                )
            )
        provider_core_bytes = len(
            json.dumps(provider_core, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        if provider_core_bytes > MAX_PROVIDER_CORE_BYTES:
            issues.append(
                self._issue(
                    "provider_input_too_large",
                    "The consent-safe evidence projection exceeds the provider input limit.",
                )
            )
        return PreparedInterpretationV2(
            normalized=normalized,
            ledger=ledger,
            windows=windows,
            mission_candidates=mission_candidates,
            issues=issues,
            privacy_redaction_count=privacy_redaction_count,
            forbidden_identity_terms=frozenset(forbidden_terms),
        )

    @staticmethod
    def _details_valid(details: dict[str, object]) -> bool:
        for key in INTEGER_DETAIL_KEYS & details.keys():
            value = details[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return False
        for key, allowed in ALLOWED_DETAIL_STATES.items():
            if key in details and details[key] not in allowed:
                return False
        return True

    @staticmethod
    def _safe_social_context(
        batch, raw_players, aliases, forbidden_terms
    ) -> SocialContextV2 | None:
        social = batch.social_context
        if social is None:
            return None
        author = social.caption_author_player_id
        if author and not raw_players[author].consent.memory_appearance:
            return SocialContextV2(
                reaction_counts=social.reaction_counts,
                saved_clip=social.saved_clip,
                event_tags=[],
            )
        caption = social.player_caption
        if caption and any(contains_identity(caption, term) for term in forbidden_terms):
            caption = None
            author = None
        safe_tags = [
            tag
            for tag in social.event_tags
            if not any(contains_identity(tag, term) for term in forbidden_terms)
        ]
        return social.model_copy(
            update={
                "player_caption": caption,
                "caption_author_player_id": aliases.get(author) if author else None,
                "event_tags": safe_tags,
            }
        )

    @staticmethod
    def _safe_media(batch, raw_players, aliases, issues) -> list[MediaReferenceV2]:
        events_by_id = {event.event_id: event for match in batch.matches for event in match.events}
        safe_media: list[MediaReferenceV2] = []
        for media in batch.media_references:
            visible_people = {
                player_id
                for event_id in media.event_ids
                for player_id in (
                    events_by_id[event_id].actor_id,
                    events_by_id[event_id].target_id,
                )
                if player_id is not None
            }
            consented = set(media.consented_player_ids)
            if any(
                not raw_players[player_id].consent.media_use or player_id not in consented
                for player_id in visible_people
            ):
                issues.append(
                    V2ValidationIssue(
                        code="media_consent_invalid",
                        severity="error",
                        message=(
                            f"Media {media.media_id} is not consented for every referenced player."
                        ),
                    )
                )
                continue
            safe_media.append(
                media.model_copy(
                    update={
                        "consented_player_ids": [
                            aliases[player_id] for player_id in media.consented_player_ids
                        ]
                    }
                )
            )
        return safe_media

    @staticmethod
    def _build_windows(normalized: NormalizedTelemetryV2) -> list[EligibleEventWindow]:
        windows: list[EligibleEventWindow] = []
        eligible_ids = {player.player_id for player in normalized.players if player.memory_eligible}
        total_events = 0
        ordered_matches = sorted(
            normalized.matches,
            key=lambda item: (item.started_at, item.match_id),
        )
        for match in ordered_matches:
            events = match.events
            unseen = set(range(len(events)))
            components: list[list[int]] = []
            while unseen:
                root = min(unseen)
                unseen.remove(root)
                component = {root}
                frontier = [root]
                while frontier:
                    current = frontier.pop()
                    for candidate in list(unseen):
                        if TelemetryPreparerV2._events_connected(
                            events[current], events[candidate]
                        ):
                            unseen.remove(candidate)
                            component.add(candidate)
                            frontier.append(candidate)
                components.append(sorted(component))
            window_index = 0
            for component in components:
                component_events = [events[event_index] for event_index in component]
                chunks: list[list[NormalizedEventV2]] = []
                chunk: list[NormalizedEventV2] = []
                for event in component_events:
                    if chunk and (
                        len(chunk) >= MAX_WINDOW_EVENTS
                        or event.timestamp_seconds - chunk[0].timestamp_seconds
                        > MAX_WINDOW_SPAN_SECONDS
                    ):
                        chunks.append(chunk)
                        chunk = []
                    chunk.append(event)
                if chunk:
                    chunks.append(chunk)
                for selected in chunks:
                    if len(windows) >= MAX_ELIGIBLE_WINDOWS:
                        return windows
                    remaining = MAX_PROVIDER_EVENTS - total_events
                    if remaining < 2:
                        return windows
                    selected = selected[:remaining]
                    window_index += 1
                    participants = sorted(
                        {
                            player_id
                            for event in selected
                            for player_id in (event.actor_id, event.target_id)
                            if player_id in eligible_ids
                        }
                    )
                    if len(selected) < 2 or len(participants) < 2:
                        continue
                    windows.append(
                        EligibleEventWindow(
                            window_id=f"window:{match.match_id}:{window_index}",
                            match_id=match.match_id,
                            event_ids=[event.event_id for event in selected],
                            participant_ids=participants,
                            start_seconds=selected[0].timestamp_seconds,
                            end_seconds=selected[-1].timestamp_seconds,
                        )
                    )
                    total_events += len(selected)
        return windows

    @staticmethod
    def _events_connected(left: NormalizedEventV2, right: NormalizedEventV2) -> bool:
        if abs(left.timestamp_seconds - right.timestamp_seconds) > 90:
            return False
        left_people = {value for value in (left.actor_id, left.target_id) if value}
        right_people = {value for value in (right.actor_id, right.target_id) if value}
        shares_person = bool(left_people & right_people)
        shares_location = bool(left.location and left.location == right.location)
        return shares_person or shares_location

    @staticmethod
    def _mission_candidates(
        normalized: NormalizedTelemetryV2,
        windows: list[EligibleEventWindow],
    ) -> list[MissionCapabilityCandidate]:
        if not windows or not normalized.current_context.reunion_eligible:
            return []
        active_ids = set(normalized.current_context.active_player_ids)
        invited_ids = [
            player.player_id
            for player in normalized.players
            if (
                player.memory_eligible
                and player.invitation_eligible
                and player.player_id in active_ids
            )
        ]
        if len(invited_ids) < 2:
            return []
        candidates: list[MissionCapabilityCandidate] = []
        all_events = {
            event.event_id: event for match in normalized.matches for event in match.events
        }
        for window in windows:
            match = next(
                (item for item in normalized.matches if item.match_id == window.match_id),
                None,
            )
            if match is None or match.mode not in normalized.current_context.available_modes:
                continue
            suffix = window.window_id.replace(":", "_")
            source_ids = window.event_ids
            candidates.extend(
                [
                    MissionCapabilityCandidate(
                        candidate_id=f"return_with_squad:{suffix}",
                        window_id=window.window_id,
                        recipe=QuestRecipe.RECREATE,
                        source_event_ids=source_ids,
                        verification=VerificationRule(
                            metric="squad.participant_ids",
                            operator="contains_all",
                            target=invited_ids,
                        ),
                    ),
                    MissionCapabilityCandidate(
                        candidate_id=f"complete_one_match:{suffix}",
                        window_id=window.window_id,
                        recipe=QuestRecipe.RESOLVE,
                        source_event_ids=source_ids,
                        verification=VerificationRule(
                            metric="squad.matches_completed",
                            operator="at_least",
                            target=1,
                        ),
                    ),
                ]
            )
            event_types = {all_events[event_id].event_type for event_id in source_ids}
            if CanonicalEventType.REVIVE not in event_types:
                continue
            candidates.append(
                MissionCapabilityCandidate(
                    candidate_id=f"squad_revive:{suffix}",
                    window_id=window.window_id,
                    recipe=QuestRecipe.REMIX,
                    source_event_ids=source_ids,
                    verification=VerificationRule(
                        metric="squad.revive_count",
                        operator="at_least",
                        target=1,
                    ),
                )
            )
        return candidates

    @staticmethod
    def _ledger(normalized: NormalizedTelemetryV2) -> ConsentSafeEvidenceLedgerV2:
        facts: list[EvidenceFactV2] = []
        for match in normalized.matches:
            for field, value in (
                ("game", match.game),
                ("mode", match.mode),
                ("map", match.map_name or "unknown"),
                ("placement", match.placement if match.placement is not None else "unknown"),
                ("result", match.result or "unknown"),
            ):
                facts.append(
                    EvidenceFactV2(
                        evidence_id=f"match:{match.match_id}:{field}",
                        kind="match",
                        match_id=match.match_id,
                        value=value,
                    )
                )
            for event in match.events:
                facts.append(
                    EvidenceFactV2(
                        evidence_id=event.event_id,
                        kind="event",
                        match_id=match.match_id,
                        event_type=event.event_type,
                        actor_id=event.actor_id,
                        target_id=event.target_id,
                        timestamp_seconds=event.timestamp_seconds,
                        location=event.location,
                        details=event.details,
                    )
                )
        history = normalized.squad_history
        if history.days_since_full_squad is not None:
            facts.append(
                EvidenceFactV2(
                    evidence_id="context:days_since_full_squad",
                    kind="context",
                    value=history.days_since_full_squad,
                )
            )
        facts.extend(
            [
                EvidenceFactV2(
                    evidence_id="context:active_player_ids",
                    kind="context",
                    value=normalized.current_context.active_player_ids,
                ),
                EvidenceFactV2(
                    evidence_id="context:reunion_eligible",
                    kind="context",
                    value=normalized.current_context.reunion_eligible,
                ),
            ]
        )
        human_context: dict[str, object] = {}
        if normalized.social_context:
            human_context = {
                "trust": "untrusted_player_context_not_factual_telemetry",
                "caption": normalized.social_context.player_caption,
                "tags": normalized.social_context.event_tags,
                "reaction_counts": normalized.social_context.reaction_counts,
                "saved_clip": normalized.social_context.saved_clip,
            }
        return ConsentSafeEvidenceLedgerV2(
            request_id=normalized.request_id,
            target_player_id=normalized.target_player_id,
            players=normalized.players,
            facts=facts,
            human_context=human_context,
        )

    @staticmethod
    def trace_id(request_id: str) -> str:
        return "trace_" + sha256(request_id.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _recursive_strings(value: object):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, nested in value.items():
                yield str(key)
                yield from TelemetryPreparerV2._recursive_strings(nested)
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                yield from TelemetryPreparerV2._recursive_strings(nested)

    @staticmethod
    def _issue(code: str, message: str) -> V2ValidationIssue:
        return V2ValidationIssue(code=code, severity="error", message=message)
