"""Deterministic preparation for the telemetry-first v2 interpretation pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from backend.models.schemas import QuestRecipe, VerificationRule
from backend.models.v2_schemas import (
    AuthoringConstraintsV2,
    CanonicalEventType,
    ConsentSafeEvidenceLedgerV2,
    CurrentContextV2,
    EligibleEventWindow,
    EvidenceBoundFieldV2,
    EvidenceFactV2,
    MediaReferenceV2,
    MissionAffordanceV2,
    MissionCapabilityCandidate,
    MissionFamilyV2,
    MissionSelectionReasonCodeV2,
    NormalizedEventV2,
    NormalizedMatchV2,
    NormalizedPlayerV2,
    NormalizedTelemetryV2,
    PlayerEventRoleScopeV2,
    RawTelemetryBatchV2,
    SocialContextV2,
    StoryBriefV2,
    V2ValidationIssue,
)
from backend.services.content_safety import (
    contains_secret_like,
    contains_unsafe_player_content,
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
    "squad_entered_vehicle": (CanonicalEventType.VEHICLE_ENTER, "squad_performs"),
    "vehicle_exit": (CanonicalEventType.VEHICLE_EXIT, "actor_performs"),
    "exited_vehicle": (CanonicalEventType.VEHICLE_EXIT, "actor_performs"),
    "escape": (CanonicalEventType.ESCAPE, "actor_performs"),
    "vehicle_escape": (CanonicalEventType.ESCAPE, "actor_performs"),
    "squad_exited_damage_zone": (CanonicalEventType.ESCAPE, "squad_performs"),
    "zone_move": (CanonicalEventType.ZONE_MOVE, "actor_performs"),
    "zone_rotation": (CanonicalEventType.ZONE_MOVE, "actor_performs"),
    "loot": (CanonicalEventType.LOOT, "actor_performs"),
    "item_picked_up": (CanonicalEventType.LOOT, "actor_performs"),
    "tactical_ping_placed": (CanonicalEventType.SIGNAL, "actor_performs"),
    "match_complete": (CanonicalEventType.MATCH_COMPLETE, "match_records"),
    "match_end": (CanonicalEventType.MATCH_COMPLETE, "match_records"),
    "match_placement_recorded": (CanonicalEventType.MATCH_COMPLETE, "match_records"),
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

ALLOWED_CATEGORICAL_DETAILS = {
    "health_state": {"critical", "low", "stable", "full", "unknown"},
    "zone_state": {"closing", "closed", "safe", "shrinking", "unknown"},
    "weapon_class": {
        "assault_rifle",
        "smg",
        "shotgun",
        "sniper",
        "marksman_rifle",
        "lmg",
        "pistol",
        "melee",
        "throwable",
        "launcher",
        "other",
        "unknown",
    },
    "vehicle_type": {
        "pickup",
        "jeep",
        "sports_car",
        "amphibian",
        "motorcycle",
        "tuk_tuk",
        "monster_truck",
        "other",
        "unknown",
    },
    "item_type": {
        "weapon",
        "ammo",
        "armor",
        "helmet",
        "medkit",
        "inhaler",
        "grenade",
        "utility",
        "attachment",
        "token",
        "supply",
        "other",
        "unknown",
    },
    "ping_type": {
        "retreat",
        "attack",
        "defend",
        "move",
        "enemy",
        "loot",
        "help",
        "regroup",
        "other",
        "unknown",
    },
}

INTEGER_DETAIL_MAXIMUMS = {
    "count": 100,
    "duration_seconds": 86_400,
    "nearby_enemies": 100,
    "passengers": 20,
    "placement_reached": 100,
    "squad_alive": 4,
    "distance_meters": 100_000,
    "rank_points": 1_000_000,
    "team_members_nearby": 4,
    "zone_phase": 20,
    "squad_members_aboard": 4,
    "squad_members_alive": 4,
    "placement": 100,
}

MAX_ELIGIBLE_WINDOWS = 6
MAX_WINDOW_EVENTS = 10
MAX_WINDOW_SPAN_SECONDS = 120
MAX_PROVIDER_EVENTS = MAX_ELIGIBLE_WINDOWS * MAX_WINDOW_EVENTS
MIN_CHAPTER_OBJECTIVES = 2
MAX_CHAPTER_OBJECTIVES = 5

_CHAPTER_BASE_METRICS = {
    "squad.participant_ids",
    "squad.matches_completed",
}
_CHAPTER_PRIMARY_METRIC = {
    MissionFamilyV2.ROLE_REVERSAL: "match.first_squad_revive_actor_id",
    MissionFamilyV2.REDEMPTION: "match.top_three_reached",
    MissionFamilyV2.RETURN_TO_PLACE: "match.invited_squad_visits_location",
    MissionFamilyV2.LANDING_RENDEZVOUS: "match.invited_squad_lands_at_location",
    MissionFamilyV2.DUO_ASSIST: (
        "match.assigned_player_assisted_elimination_player_ids"
    ),
}
_CHAPTER_EXTRA_PRIORITY = {
    "match.invited_squad_lands_at_location": 0,
    "match.assigned_player_assisted_elimination_player_ids": 1,
    "match.first_squad_revive_actor_id": 2,
    "match.invited_squad_visits_location": 3,
}
_CHAPTER_EXECUTION_ORDER = {
    "match.invited_squad_lands_at_location": 0,
    "match.invited_squad_visits_location": 1,
    "match.first_squad_revive_actor_id": 2,
    "match.assigned_player_assisted_elimination_player_ids": 3,
    "match.top_three_reached": 4,
}
_CHAPTER_FAMILY_RECIPE = {
    MissionFamilyV2.REUNION: QuestRecipe.RECREATE,
    MissionFamilyV2.ROLE_REVERSAL: QuestRecipe.REMIX,
    MissionFamilyV2.REDEMPTION: QuestRecipe.RESOLVE,
    MissionFamilyV2.RETURN_TO_PLACE: QuestRecipe.RECREATE,
    MissionFamilyV2.LANDING_RENDEZVOUS: QuestRecipe.RECREATE,
    MissionFamilyV2.DUO_ASSIST: QuestRecipe.REMIX,
}
MAX_PROVIDER_CORE_BYTES = 80_000

COLLECTIVE_MEMBERSHIP_DETAIL = {
    CanonicalEventType.VEHICLE_ENTER: "squad_members_aboard",
    CanonicalEventType.ESCAPE: "squad_members_alive",
}


def collective_event_includes_full_squad(
    event: NormalizedEventV2,
    normalized: NormalizedTelemetryV2,
) -> bool:
    """Return true only when an explicit squad event proves full-roster participation."""

    membership_key = COLLECTIVE_MEMBERSHIP_DETAIL.get(event.event_type)
    return bool(
        event.event_scope == "squad"
        and membership_key
        and event.details.get(membership_key) == len(normalized.players)
    )


@dataclass(frozen=True)
class PreparedInterpretationV2:
    normalized: NormalizedTelemetryV2 | None
    ledger: ConsentSafeEvidenceLedgerV2 | None
    windows: list[EligibleEventWindow]
    mission_candidates: list[MissionCapabilityCandidate]
    mission_affordances: list[MissionAffordanceV2]
    story_brief: StoryBriefV2 | None
    issues: list[V2ValidationIssue]
    privacy_redaction_count: int
    forbidden_identity_terms: frozenset[str]


class TelemetryPreparerV2:
    """Normalize Free Fire telemetry, enforce privacy, and create neutral candidates."""

    def prepare(self, batch: RawTelemetryBatchV2) -> PreparedInterpretationV2:
        issues: list[V2ValidationIssue] = []
        if contains_secret_like(batch.model_dump_json()):
            issues.append(
                self._issue(
                    "secret_in_input",
                    "Input contains text that resembles a credential or secret.",
                )
            )
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
                event_scope = "player"
                if role_mapping == "actor_performs" and actor_id is None:
                    issues.append(
                        self._issue(
                            "missing_event_actor",
                            f"Event {event.event_id} requires an actor.",
                        )
                    )
                    continue
                if role_mapping == "actor_is_target":
                    if actor_id is None:
                        issues.append(
                            self._issue(
                                "missing_event_target",
                                f"Event {event.event_id} requires the affected player.",
                            )
                        )
                        continue
                    target_id, actor_id = actor_id, target_id
                elif role_mapping == "target_performs":
                    if target_id is None:
                        issues.append(
                            self._issue(
                                "missing_event_actor",
                                f"Event {event.event_id} requires the acting player.",
                            )
                        )
                        continue
                    actor_id, target_id = target_id, actor_id
                elif role_mapping == "squad_performs":
                    actor_id, target_id = None, None
                    event_scope = "squad"
                elif role_mapping == "match_records":
                    actor_id, target_id = None, None
                    event_scope = "match"
                events.append(
                    NormalizedEventV2(
                        event_id=event.event_id,
                        match_id=match.match_id,
                        event_type=canonical_type,
                        event_scope=event_scope,
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
        windows = self._story_windows(normalized, self._build_windows(normalized))
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
        mission_candidates, mission_affordances = self._mission_candidates(normalized, windows)
        if not mission_affordances:
            issues.append(
                self._issue(
                    "no_feasible_mission",
                    "No deterministic mission capability is available for this context.",
                )
            )
        ledger = self._ledger(normalized)
        authoring_constraints = self._authoring_constraints(normalized)
        invitation_player_ids = [
            player.player_id
            for player in normalized.players
            if player.memory_eligible and player.invitation_eligible
        ]
        story_brief = (
            StoryBriefV2(
                request_id=normalized.request_id,
                target_player_id=normalized.target_player_id,
                players_requiring_perspectives=[
                    player for player in normalized.players if player.memory_eligible
                ],
                invitation_player_ids=invitation_player_ids,
                active_player_ids=normalized.current_context.active_player_ids,
                evidence_ledger=ledger,
                eligible_event_windows=windows,
                mission_candidates=mission_candidates,
                mission_affordances=mission_affordances,
                authoring_constraints=authoring_constraints,
                squad_history=normalized.squad_history,
                current_context=normalized.current_context,
                media_references=normalized.media_references,
            )
            if mission_affordances
            else None
        )
        provider_core = {
            "story_brief": story_brief.model_dump(mode="json") if story_brief else None,
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
            mission_affordances=mission_affordances,
            story_brief=story_brief,
            issues=issues,
            privacy_redaction_count=privacy_redaction_count,
            forbidden_identity_terms=frozenset(forbidden_terms),
        )

    @staticmethod
    def _details_valid(details: dict[str, object]) -> bool:
        for key in INTEGER_DETAIL_KEYS & details.keys():
            value = details[key]
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
                or value > INTEGER_DETAIL_MAXIMUMS[key]
            ):
                return False
        for key, allowed in ALLOWED_CATEGORICAL_DETAILS.items():
            if key in details:
                value = details[key]
                if not isinstance(value, str) or value not in allowed:
                    return False
        if set(details) - INTEGER_DETAIL_KEYS - ALLOWED_CATEGORICAL_DETAILS.keys():
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
        if caption and (
            any(contains_identity(caption, term) for term in forbidden_terms)
            or contains_secret_like(caption)
            or contains_unsafe_player_content(caption)
        ):
            caption = None
            author = None
        safe_tags = [
            tag
            for tag in social.event_tags
            if not any(contains_identity(tag, term) for term in forbidden_terms)
            and not contains_secret_like(tag)
            and not contains_unsafe_player_content(tag)
        ]
        safe_reactions = {
            key: value
            for key, value in social.reaction_counts.items()
            if not contains_secret_like(key) and not contains_unsafe_player_content(key)
        }
        return social.model_copy(
            update={
                "player_caption": caption,
                "caption_author_player_id": aliases.get(author) if author else None,
                "event_tags": safe_tags,
                "reaction_counts": safe_reactions,
            }
        )

    @staticmethod
    def _safe_media(batch, raw_players, aliases, issues) -> list[MediaReferenceV2]:
        events_by_id = {event.event_id: event for match in batch.matches for event in match.events}
        safe_media: list[MediaReferenceV2] = []
        for media in batch.media_references:
            visible_people: set[str] = {
                player_id
                for event_id in media.event_ids
                for player_id in (
                    events_by_id[event_id].actor_id,
                    events_by_id[event_id].target_id,
                )
                if player_id is not None
            }
            if any(
                (
                    mapping := FREE_FIRE_EVENT_MAP.get(
                        events_by_id[event_id].provider_event_type.strip().lower()
                    )
                )
                and mapping[1] in {"squad_performs", "match_records"}
                for event_id in media.event_ids
            ):
                visible_people.update(raw_players)
            consented = set(media.consented_player_ids)
            if any(
                not raw_players[player_id].consent.memory_appearance
                or not raw_players[player_id].consent.media_use
                for player_id in consented
            ) or not visible_people.issubset(consented):
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
    def _story_windows(
        normalized: NormalizedTelemetryV2,
        windows: list[EligibleEventWindow],
    ) -> list[EligibleEventWindow]:
        """Cap provider windows by structural facts, never narrative significance."""

        started_at = {match.match_id: match.started_at.timestamp() for match in normalized.matches}
        return sorted(
            windows,
            key=lambda item: (
                -len(item.participant_ids),
                -len(item.event_ids),
                -started_at[item.match_id],
                item.window_id,
            ),
        )[:4]

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
    ) -> tuple[list[MissionCapabilityCandidate], list[MissionAffordanceV2]]:
        if not windows or not normalized.current_context.reunion_eligible:
            return [], []
        invited_ids = [
            player.player_id
            for player in normalized.players
            if player.memory_eligible and player.invitation_eligible
        ]
        if len(invited_ids) < 2 or normalized.target_player_id not in invited_ids:
            return [], []
        candidates: list[MissionCapabilityCandidate] = []
        affordances: list[MissionAffordanceV2] = []
        all_events = {
            event.event_id: event for match in normalized.matches for event in match.events
        }
        near_miss_match_ids_by_game_mode: dict[tuple[str, str], list[str]] = {}
        for near_miss in normalized.matches:
            if near_miss.placement is None or not 4 <= near_miss.placement <= 6:
                continue
            near_miss_match_ids_by_game_mode.setdefault(
                (near_miss.game, near_miss.mode),
                [],
            ).append(near_miss.match_id)
        for window in windows:
            match = next(
                (item for item in normalized.matches if item.match_id == window.match_id),
                None,
            )
            if match is None or match.mode not in normalized.current_context.available_modes:
                continue
            near_miss_match_ids = near_miss_match_ids_by_game_mode.get(
                (match.game, match.mode),
                [],
            )
            suffix = window.window_id.replace(":", "_")
            source_ids = window.event_ids
            reunion_id = f"affordance:reunion:{suffix}"
            reunion_candidates = [
                MissionCapabilityCandidate(
                    candidate_id=f"objective:reunion:participants:{suffix}",
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
                    candidate_id=f"objective:reunion:match:{suffix}",
                    window_id=window.window_id,
                    recipe=QuestRecipe.RECREATE,
                    source_event_ids=source_ids,
                    verification=VerificationRule(
                        metric="squad.matches_completed",
                        operator="at_least",
                        target=1,
                    ),
                ),
            ]
            candidates.extend(reunion_candidates)
            affordances.append(
                MissionAffordanceV2(
                    affordance_id=reunion_id,
                    family=MissionFamilyV2.REUNION,
                    window_id=window.window_id,
                    source_event_ids=source_ids,
                    source_match_ids=[window.match_id],
                    source_context_ids=["context:reunion_eligible"],
                    parameters={"invitation_player_ids": invited_ids},
                    objective_candidate_ids=[
                        candidate.candidate_id for candidate in reunion_candidates
                    ],
                    allowed_reason_codes=[
                        MissionSelectionReasonCodeV2.SHARED_SQUAD_REUNION,
                        MissionSelectionReasonCodeV2.DETERMINISTICALLY_VERIFIABLE,
                    ],
                )
            )

            first_landing_by_player: dict[str, NormalizedEventV2] = {}
            for event in sorted(
                (all_events[event_id] for event_id in source_ids),
                key=lambda item: (item.timestamp_seconds, item.event_id),
            ):
                if (
                    event.event_type == CanonicalEventType.LANDING
                    and event.actor_id in invited_ids
                ):
                    assert event.actor_id is not None
                    first_landing_by_player.setdefault(event.actor_id, event)
            landing_events_by_location: dict[str, list[NormalizedEventV2]] = {}
            for event in first_landing_by_player.values():
                if event.location:
                    landing_events_by_location.setdefault(event.location, []).append(event)
            complete_landing_groups: list[tuple[str, list[NormalizedEventV2]]] = []
            for location, landing_events in landing_events_by_location.items():
                rendezvous_events = sorted(
                    landing_events,
                    key=lambda item: (item.timestamp_seconds, item.event_id),
                )
                if (
                    {event.actor_id for event in rendezvous_events} == set(invited_ids)
                    and max(event.timestamp_seconds for event in rendezvous_events)
                    - min(event.timestamp_seconds for event in rendezvous_events)
                    <= 30
                ):
                    complete_landing_groups.append((location, rendezvous_events))
            if complete_landing_groups:
                landing_location, landing_events = sorted(
                    complete_landing_groups,
                    key=lambda item: (item[0].casefold(), item[0]),
                )[0]
                landing_source_ids = [event.event_id for event in landing_events]
                landing_candidate = MissionCapabilityCandidate(
                    candidate_id=f"objective:landing_rendezvous:location:{suffix}",
                    window_id=window.window_id,
                    recipe=QuestRecipe.RECREATE,
                    source_event_ids=landing_source_ids,
                    verification=VerificationRule(
                        metric="match.invited_squad_lands_at_location",
                        operator="equals",
                        target=landing_location,
                    ),
                )
                candidates.append(landing_candidate)
                affordances.append(
                    MissionAffordanceV2(
                        affordance_id=f"affordance:landing_rendezvous:{suffix}",
                        family=MissionFamilyV2.LANDING_RENDEZVOUS,
                        window_id=window.window_id,
                        source_event_ids=landing_source_ids,
                        source_match_ids=[window.match_id],
                        source_context_ids=["context:reunion_eligible"],
                        parameters={
                            "landing_location": landing_location,
                            "invitation_player_ids": invited_ids,
                        },
                        # The final composition pass replaces this shared bootstrap
                        # reference with affordance-local 2-to-5 chapter candidates.
                        objective_candidate_ids=[
                            reunion_candidates[0].candidate_id,
                            landing_candidate.candidate_id,
                        ],
                        allowed_reason_codes=[
                            MissionSelectionReasonCodeV2.SHARED_LANDING_POINT,
                            MissionSelectionReasonCodeV2.DETERMINISTICALLY_VERIFIABLE,
                        ],
                    )
                )

            # A named rescue location can become a verifiable return point.  Keep this
            # tied to an actual revive in the selected episode so a generic location
            # never becomes a fabricated mission hook.
            rescue_locations = [
                event.location
                for event_id in source_ids
                for event in [all_events[event_id]]
                if event.event_type == CanonicalEventType.REVIVE and event.location
            ]
            if rescue_locations:
                return_location = rescue_locations[0]
                assert return_location is not None
                return_source_ids = [
                    event_id
                    for event_id in source_ids
                    if all_events[event_id].location == return_location
                ]
                return_candidate = MissionCapabilityCandidate(
                    candidate_id=f"objective:return_to_place:location:{suffix}",
                    window_id=window.window_id,
                    recipe=QuestRecipe.RECREATE,
                    source_event_ids=return_source_ids,
                    verification=VerificationRule(
                        metric="match.invited_squad_visits_location",
                        operator="equals",
                        target=return_location,
                    ),
                )
                candidates.append(return_candidate)
                affordances.append(
                    MissionAffordanceV2(
                        affordance_id=f"affordance:return_to_place:{suffix}",
                        family=MissionFamilyV2.RETURN_TO_PLACE,
                        window_id=window.window_id,
                        source_event_ids=return_source_ids,
                        source_match_ids=[window.match_id],
                        source_context_ids=["context:reunion_eligible"],
                        parameters={
                            "return_location": return_location,
                            "invitation_player_ids": invited_ids,
                        },
                        objective_candidate_ids=[
                            reunion_candidates[0].candidate_id,
                            return_candidate.candidate_id,
                        ],
                        allowed_reason_codes=[
                            MissionSelectionReasonCodeV2.SHARED_LOCATION_CALLBACK,
                            MissionSelectionReasonCodeV2.DETERMINISTICALLY_VERIFIABLE,
                        ],
                    )
                )

            eligible_revives = [
                all_events[event_id]
                for event_id in source_ids
                if all_events[event_id].event_type == CanonicalEventType.REVIVE
                and all_events[event_id].actor_id in invited_ids
                and all_events[event_id].target_id in invited_ids
                and all_events[event_id].actor_id != all_events[event_id].target_id
            ]
            # One deterministic role-reversal affordance per window keeps the Story Brief bounded.
            for revive_index, revive in enumerate(eligible_revives[:1], start=1):
                assert revive.actor_id is not None
                assert revive.target_id is not None
                role_suffix = f"{suffix}:{revive_index}"
                role_candidates = [
                    MissionCapabilityCandidate(
                        candidate_id=f"objective:role_reversal:participants:{role_suffix}",
                        window_id=window.window_id,
                        recipe=QuestRecipe.REMIX,
                        source_event_ids=source_ids,
                        verification=VerificationRule(
                            metric="squad.participant_ids",
                            operator="contains_all",
                            target=invited_ids,
                        ),
                    ),
                    MissionCapabilityCandidate(
                        candidate_id=f"objective:role_reversal:match:{role_suffix}",
                        window_id=window.window_id,
                        recipe=QuestRecipe.REMIX,
                        source_event_ids=source_ids,
                        verification=VerificationRule(
                            metric="squad.matches_completed",
                            operator="at_least",
                            target=1,
                        ),
                    ),
                    MissionCapabilityCandidate(
                        candidate_id=f"objective:role_reversal:first_revive:{role_suffix}",
                        window_id=window.window_id,
                        recipe=QuestRecipe.REMIX,
                        assigned_player_id=revive.target_id,
                        source_event_ids=[revive.event_id],
                        verification=VerificationRule(
                            metric="match.first_squad_revive_actor_id",
                            operator="equals",
                            target=revive.target_id,
                        ),
                    ),
                ]
                candidates.extend(role_candidates)
                affordances.append(
                    MissionAffordanceV2(
                        affordance_id=f"affordance:role_reversal:{role_suffix}",
                        family=MissionFamilyV2.ROLE_REVERSAL,
                        window_id=window.window_id,
                        source_event_ids=[revive.event_id],
                        source_match_ids=[window.match_id],
                        parameters={
                            "original_rescuer_id": revive.actor_id,
                            "original_saved_player_id": revive.target_id,
                            "invitation_player_ids": invited_ids,
                        },
                        objective_candidate_ids=[
                            candidate.candidate_id for candidate in role_candidates
                        ],
                        allowed_reason_codes=[
                            MissionSelectionReasonCodeV2.DIRECTLY_INVERTS_ORIGINAL_ROLES,
                            MissionSelectionReasonCodeV2.PLAYER_SPECIFIC,
                            MissionSelectionReasonCodeV2.DETERMINISTICALLY_VERIFIABLE,
                        ],
                    )
                )

            assist_pairs: list[tuple[NormalizedEventV2, NormalizedEventV2]] = []
            for event_id in source_ids:
                assist = all_events[event_id]
                if (
                    assist.event_type != CanonicalEventType.ASSIST
                    or assist.actor_id not in invited_ids
                    or assist.target_id not in invited_ids
                    or assist.actor_id == assist.target_id
                    or not assist.location
                ):
                    continue
                paired_elimination = next(
                    (
                        all_events[candidate_id]
                        for candidate_id in source_ids
                        if all_events[candidate_id].event_type
                        == CanonicalEventType.ELIMINATION
                        and all_events[candidate_id].actor_id == assist.target_id
                        and all_events[candidate_id].location == assist.location
                        and 0
                        <= all_events[candidate_id].timestamp_seconds
                        - assist.timestamp_seconds
                        <= 30
                    ),
                    None,
                )
                if paired_elimination is not None:
                    assist_pairs.append((assist, paired_elimination))
            # One typed pair per episode keeps the provider catalogue bounded.
            for pair_index, (assist, elimination) in enumerate(assist_pairs[:1], start=1):
                assert assist.actor_id is not None
                assert assist.target_id is not None
                duo_suffix = f"{suffix}:{pair_index}"
                duo_candidate = MissionCapabilityCandidate(
                    candidate_id=f"objective:duo_assist:pair:{duo_suffix}",
                    window_id=window.window_id,
                    recipe=QuestRecipe.REMIX,
                    assigned_player_id=assist.actor_id,
                    source_event_ids=[assist.event_id, elimination.event_id],
                    verification=VerificationRule(
                        metric="match.assigned_player_assisted_elimination_player_ids",
                        operator="contains_all",
                        target=[assist.target_id],
                    ),
                )
                candidates.append(duo_candidate)
                affordances.append(
                    MissionAffordanceV2(
                        affordance_id=f"affordance:duo_assist:{duo_suffix}",
                        family=MissionFamilyV2.DUO_ASSIST,
                        window_id=window.window_id,
                        source_event_ids=[assist.event_id, elimination.event_id],
                        source_match_ids=[window.match_id],
                        parameters={
                            "assister_player_id": assist.actor_id,
                            "elimination_player_id": assist.target_id,
                            "assist_window_seconds": 30,
                            "invitation_player_ids": invited_ids,
                        },
                        objective_candidate_ids=[
                            reunion_candidates[0].candidate_id,
                            duo_candidate.candidate_id,
                        ],
                        allowed_reason_codes=[
                            MissionSelectionReasonCodeV2.PROVEN_ASSIST_PAIR,
                            MissionSelectionReasonCodeV2.PLAYER_SPECIFIC,
                            MissionSelectionReasonCodeV2.DETERMINISTICALLY_VERIFIABLE,
                        ],
                    )
                )

            if len(near_miss_match_ids) >= 2 and window.match_id in near_miss_match_ids:
                redemption_candidates = [
                    MissionCapabilityCandidate(
                        candidate_id=f"objective:redemption:participants:{suffix}",
                        window_id=window.window_id,
                        recipe=QuestRecipe.RESOLVE,
                        source_event_ids=source_ids,
                        verification=VerificationRule(
                            metric="squad.participant_ids",
                            operator="contains_all",
                            target=invited_ids,
                        ),
                    ),
                    MissionCapabilityCandidate(
                        candidate_id=f"objective:redemption:match:{suffix}",
                        window_id=window.window_id,
                        recipe=QuestRecipe.RESOLVE,
                        source_event_ids=source_ids,
                        verification=VerificationRule(
                            metric="squad.matches_completed",
                            operator="at_least",
                            target=1,
                        ),
                    ),
                    MissionCapabilityCandidate(
                        candidate_id=f"objective:redemption:top_three:{suffix}",
                        window_id=window.window_id,
                        recipe=QuestRecipe.RESOLVE,
                        source_event_ids=source_ids,
                        verification=VerificationRule(
                            metric="match.top_three_reached",
                            operator="equals",
                            target=True,
                        ),
                    ),
                ]
                candidates.extend(redemption_candidates)
                affordances.append(
                    MissionAffordanceV2(
                        affordance_id=f"affordance:redemption:{suffix}",
                        family=MissionFamilyV2.REDEMPTION,
                        window_id=window.window_id,
                        source_event_ids=source_ids,
                        source_match_ids=near_miss_match_ids,
                        parameters={
                            "source_placements": [
                                str(item.placement)
                                for item in normalized.matches
                                if item.match_id in near_miss_match_ids
                            ],
                            "target_placement_max": 3,
                            "invitation_player_ids": invited_ids,
                        },
                        objective_candidate_ids=[
                            candidate.candidate_id for candidate in redemption_candidates
                        ],
                        allowed_reason_codes=[
                            MissionSelectionReasonCodeV2.REPEATED_NEAR_MISS,
                            MissionSelectionReasonCodeV2.MEASURABLE_IMPROVEMENT,
                            MissionSelectionReasonCodeV2.DETERMINISTICALLY_VERIFIABLE,
                        ],
                    )
                )
        return TelemetryPreparerV2._compose_chapter_objectives(candidates, affordances)

    @staticmethod
    def _compose_chapter_objectives(
        candidates: list[MissionCapabilityCandidate],
        affordances: list[MissionAffordanceV2],
    ) -> tuple[list[MissionCapabilityCandidate], list[MissionAffordanceV2]]:
        """Turn atomic capabilities into ordered, evidence-safe 2-to-5 step chapters.

        The interpreter still chooses exactly one affordance.  This pass makes that
        affordance a complete chapter: invitation-safe entry, one to three compatible
        mechanics from the same neutral event window, and match completion.  Candidate
        IDs remain affordance-local because provider objective references are globally
        unique within a Story Brief.
        """

        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        affordances_by_window: dict[str, list[MissionAffordanceV2]] = {}
        for affordance in affordances:
            affordances_by_window.setdefault(affordance.window_id, []).append(affordance)

        composed_candidates: list[MissionCapabilityCandidate] = []
        composed_affordances: list[MissionAffordanceV2] = []
        for window_affordances in affordances_by_window.values():
            reunion = next(
                (
                    affordance
                    for affordance in window_affordances
                    if affordance.family == MissionFamilyV2.REUNION
                ),
                None,
            )
            if reunion is None:
                continue
            reunion_candidates = [
                candidate_by_id[candidate_id]
                for candidate_id in reunion.objective_candidate_ids
            ]
            baseline_by_metric = {
                candidate.verification.metric: candidate for candidate in reunion_candidates
            }
            if set(baseline_by_metric) != _CHAPTER_BASE_METRICS:
                continue

            mechanic_sources: dict[
                str,
                tuple[MissionCapabilityCandidate, MissionAffordanceV2],
            ] = {}
            for source_affordance in sorted(
                window_affordances,
                key=lambda item: item.affordance_id,
            ):
                primary_metric = _CHAPTER_PRIMARY_METRIC.get(source_affordance.family)
                if primary_metric is None or primary_metric in mechanic_sources:
                    continue
                primary_candidate = next(
                    (
                        candidate_by_id[candidate_id]
                        for candidate_id in source_affordance.objective_candidate_ids
                        if candidate_by_id[candidate_id].verification.metric == primary_metric
                    ),
                    None,
                )
                if primary_candidate is not None:
                    mechanic_sources[primary_metric] = (
                        primary_candidate,
                        source_affordance,
                    )

            for affordance in window_affordances:
                if affordance.family == MissionFamilyV2.REUNION:
                    chapter_candidates = [
                        candidate.model_copy(
                            update={"recipe": _CHAPTER_FAMILY_RECIPE[affordance.family]}
                        )
                        for candidate in reunion_candidates
                    ]
                    composed_candidates.extend(chapter_candidates)
                    composed_affordances.append(
                        affordance.model_copy(
                            update={
                                "objective_candidate_ids": [
                                    candidate.candidate_id for candidate in chapter_candidates
                                ]
                            }
                        )
                    )
                    continue

                primary_metric = _CHAPTER_PRIMARY_METRIC.get(affordance.family)
                if primary_metric is None or primary_metric not in mechanic_sources:
                    continue
                chosen_metrics = [primary_metric]
                if affordance.family != MissionFamilyV2.REDEMPTION:
                    for metric in sorted(
                        mechanic_sources,
                        key=lambda item: (
                            _CHAPTER_EXTRA_PRIORITY.get(item, 100),
                            item,
                        ),
                    ):
                        if metric in chosen_metrics or metric == "match.top_three_reached":
                            continue
                        if {
                            metric,
                            primary_metric,
                        } == {
                            "match.invited_squad_lands_at_location",
                            "match.invited_squad_visits_location",
                        }:
                            continue
                        chosen_metrics.append(metric)
                        if len(chosen_metrics) == MAX_CHAPTER_OBJECTIVES - len(
                            _CHAPTER_BASE_METRICS
                        ):
                            break
                chosen_metrics.sort(
                    key=lambda item: (_CHAPTER_EXECUTION_ORDER.get(item, 100), item)
                )

                recipe = _CHAPTER_FAMILY_RECIPE[affordance.family]
                chapter_parameters = dict(affordance.parameters)
                chapter_source_event_ids = list(affordance.source_event_ids)
                chapter_source_match_ids = list(affordance.source_match_ids)
                chapter_source_context_ids = list(affordance.source_context_ids)
                chapter_candidates = [
                    TelemetryPreparerV2._clone_chapter_candidate(
                        baseline_by_metric["squad.participant_ids"],
                        affordance,
                        recipe,
                        "participants",
                    )
                ]
                for metric in chosen_metrics:
                    template, source_affordance = mechanic_sources[metric]
                    token = {
                        "match.first_squad_revive_actor_id": "first_revive",
                        "match.top_three_reached": "top_three",
                        "match.invited_squad_visits_location": "return_location",
                        "match.invited_squad_lands_at_location": "landing",
                        "match.assigned_player_assisted_elimination_player_ids": "duo_assist",
                    }[metric]
                    chapter_candidates.append(
                        TelemetryPreparerV2._clone_chapter_candidate(
                            template,
                            affordance,
                            recipe,
                            token,
                        )
                    )
                    for key, value in source_affordance.parameters.items():
                        existing = chapter_parameters.get(key)
                        if existing is not None and existing != value:
                            raise ValueError(
                                f"chapter parameter {key!r} conflicts within one event window"
                            )
                        chapter_parameters[key] = value
                    chapter_source_event_ids.extend(source_affordance.source_event_ids)
                    chapter_source_match_ids.extend(source_affordance.source_match_ids)
                    chapter_source_context_ids.extend(source_affordance.source_context_ids)
                chapter_candidates.append(
                    TelemetryPreparerV2._clone_chapter_candidate(
                        baseline_by_metric["squad.matches_completed"],
                        affordance,
                        recipe,
                        "complete_match",
                    )
                )
                if not MIN_CHAPTER_OBJECTIVES <= len(chapter_candidates) <= MAX_CHAPTER_OBJECTIVES:
                    raise ValueError("composed chapter must contain two to five objectives")

                composed_candidates.extend(chapter_candidates)
                composed_affordances.append(
                    affordance.model_copy(
                        update={
                            "source_event_ids": list(dict.fromkeys(chapter_source_event_ids)),
                            "source_match_ids": list(dict.fromkeys(chapter_source_match_ids)),
                            "source_context_ids": list(dict.fromkeys(chapter_source_context_ids)),
                            "parameters": chapter_parameters,
                            "objective_candidate_ids": [
                                candidate.candidate_id for candidate in chapter_candidates
                            ],
                        }
                    )
                )
        return composed_candidates, composed_affordances

    @staticmethod
    def _clone_chapter_candidate(
        template: MissionCapabilityCandidate,
        affordance: MissionAffordanceV2,
        recipe: QuestRecipe,
        token: str,
    ) -> MissionCapabilityCandidate:
        suffix = affordance.affordance_id.removeprefix("affordance:").replace(":", "_")
        candidate_id = f"objective:chapter:{suffix}:{token}"
        if len(candidate_id) > 128:
            candidate_id = (
                f"objective:chapter:{affordance.family.value}:{token}:"
                f"{sha256(affordance.affordance_id.encode('utf-8')).hexdigest()[:12]}"
            )
        return template.model_copy(
            update={
                "candidate_id": candidate_id,
                "window_id": affordance.window_id,
                "recipe": recipe,
            }
        )

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
                        event_scope=event.event_scope,
                        actor_id=event.actor_id,
                        target_id=event.target_id,
                        timestamp_seconds=event.timestamp_seconds,
                        location=event.location,
                        details=event.details,
                    )
                )
        history = normalized.squad_history
        if history.previous_session_at:
            facts.append(
                EvidenceFactV2(
                    evidence_id="context:previous_session_at",
                    kind="context",
                    value=[item.isoformat() for item in history.previous_session_at],
                )
            )
        if history.days_since_full_squad is not None:
            facts.append(
                EvidenceFactV2(
                    evidence_id="context:days_since_full_squad",
                    kind="context",
                    value=history.days_since_full_squad,
                )
            )
        facts.append(
            EvidenceFactV2(
                evidence_id="context:recent_rematch_count",
                kind="context",
                value=history.recent_rematch_count,
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
                    evidence_id="context:available_modes",
                    kind="context",
                    value=normalized.current_context.available_modes,
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
    def _authoring_constraints(normalized: NormalizedTelemetryV2) -> AuthoringConstraintsV2:
        """Derive neutral role and terminology guidance from the projected evidence only."""

        events = [event for match in normalized.matches for event in match.events]
        player_scopes: dict[str, PlayerEventRoleScopeV2] = {}
        for player in normalized.players:
            if not player.memory_eligible:
                continue
            player_scopes[player.player_id] = PlayerEventRoleScopeV2(
                actor=[
                    event.event_id
                    for event in events
                    if event.event_scope == "player" and event.actor_id == player.player_id
                ],
                target=[
                    event.event_id
                    for event in events
                    if event.event_scope == "player" and event.target_id == player.player_id
                ],
                full_squad=[
                    event.event_id
                    for event in events
                    if collective_event_includes_full_squad(event, normalized)
                ],
            )

        bound_terms: dict[str, dict[EvidenceBoundFieldV2, str | int]] = {}
        for match in normalized.matches:
            for event in match.events:
                for key, value in event.details.items():
                    if key in ALLOWED_CATEGORICAL_DETAILS:
                        if not isinstance(value, str) or value in {"other", "unknown"}:
                            continue
                        field = EvidenceBoundFieldV2(key)
                    elif key == "zone_phase" and isinstance(value, int):
                        field = EvidenceBoundFieldV2.ZONE_PHASE
                    else:
                        continue
                    bound_terms.setdefault(event.event_id, {})[field] = value
        return AuthoringConstraintsV2(
            player_event_roles=player_scopes,
            evidence_bound_terms=bound_terms,
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
