"""Version 2 contracts for AI-first, evidence-grounded memory interpretation.

The public input deliberately contains telemetry and limited context only.  Generated
story fields live exclusively in :class:`MemoryProposalV2` and delivery output models.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from backend.models.schemas import (
    DeliveryDecision,
    DeliveryDeclineReason,
    MemoryType,
    QuestRecipe,
    StrictModel,
    VerificationRule,
)

TelemetryValue = str | int | float | bool | list[str]
ClaimValue = str | int | float | bool | list[str]


class ConsentPermissionsV2(StrictModel):
    memory_appearance: bool
    identity_display: bool
    media_use: bool
    mission_invitation: bool


class RawPlayerV2(StrictModel):
    player_id: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    consent: ConsentPermissionsV2


class RawSquadV2(StrictModel):
    squad_id: str = Field(min_length=1, max_length=128)
    players: list[RawPlayerV2] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def unique_players(self) -> RawSquadV2:
        player_ids = [player.player_id for player in self.players]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("squad player_id values must be unique")
        return self


class RawTelemetryEventV2(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    provider_event_type: str = Field(min_length=1, max_length=64)
    actor_id: str | None = Field(default=None, min_length=1, max_length=128)
    target_id: str | None = Field(default=None, min_length=1, max_length=128)
    timestamp_seconds: int = Field(ge=0, le=86_400)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    details: dict[str, TelemetryValue] = Field(default_factory=dict, max_length=16)

    @model_validator(mode="after")
    def bounded_details(self) -> RawTelemetryEventV2:
        for key, value in self.details.items():
            if not key or len(key) > 64:
                raise ValueError("event detail keys must contain 1 to 64 characters")
            if isinstance(value, str) and len(value) > 100:
                raise ValueError("event detail string values must be at most 100 characters")
            if isinstance(value, list) and (
                len(value) > 8 or any(not item or len(item) > 64 for item in value)
            ):
                raise ValueError("event detail lists must contain up to eight short strings")
        return self


class RawMatchV2(StrictModel):
    match_id: str = Field(min_length=1, max_length=128)
    game: str = Field(min_length=1, max_length=64)
    mode: str = Field(min_length=1, max_length=64)
    map_name: str | None = Field(default=None, min_length=1, max_length=100)
    started_at: datetime
    ended_at: datetime | None = None
    placement: int | None = Field(default=None, ge=1, le=100)
    result: str | None = Field(default=None, min_length=1, max_length=64)
    events: list[RawTelemetryEventV2] = Field(min_length=1, max_length=250)

    @model_validator(mode="after")
    def chronological_and_unique(self) -> RawMatchV2:
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("match event_id values must be unique")
        if self.ended_at is not None:
            if self.ended_at <= self.started_at:
                raise ValueError("ended_at must be later than started_at")
            duration = int((self.ended_at - self.started_at).total_seconds())
            if any(event.timestamp_seconds > duration for event in self.events):
                raise ValueError("event timestamp_seconds must fall within the match")
        return self


class SquadHistoryV2(StrictModel):
    previous_session_at: list[datetime] = Field(default_factory=list, max_length=50)
    days_since_full_squad: int | None = Field(default=None, ge=0, le=3650)
    recent_rematch_count: int = Field(default=0, ge=0, le=100)


class CurrentContextV2(StrictModel):
    active_player_ids: list[str] = Field(default_factory=list, max_length=4)
    available_modes: list[str] = Field(default_factory=list, max_length=20)
    reunion_eligible: bool = True

    @field_validator("active_player_ids", "available_modes")
    @classmethod
    def unique_non_empty_values(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 128 for item in value):
            raise ValueError("context values must contain 1 to 128 characters")
        if len(value) != len(set(value)):
            raise ValueError("context values must be unique")
        return value


class SocialContextV2(StrictModel):
    reaction_counts: dict[str, int] = Field(default_factory=dict, max_length=8)
    saved_clip: bool = False
    event_tags: list[str] = Field(default_factory=list, max_length=8)
    player_caption: str | None = Field(default=None, min_length=1, max_length=120)
    caption_author_player_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def bounded_social_values(self) -> SocialContextV2:
        if any(
            not key or len(key) > 40 or value < 0 for key, value in self.reaction_counts.items()
        ):
            raise ValueError("reaction counts require short names and non-negative values")
        if any(not tag or len(tag) > 40 for tag in self.event_tags):
            raise ValueError("event tags must contain 1 to 40 characters")
        if self.caption_author_player_id and not self.player_caption:
            raise ValueError("caption_author_player_id requires player_caption")
        return self


class MediaReferenceV2(StrictModel):
    media_id: str = Field(min_length=1, max_length=128)
    kind: Literal["clip", "thumbnail", "keyframe"]
    event_ids: list[str] = Field(min_length=1, max_length=20)
    consented_player_ids: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def unique_references(self) -> MediaReferenceV2:
        if len(self.event_ids) != len(set(self.event_ids)):
            raise ValueError("media event_ids must be unique")
        if len(self.consented_player_ids) != len(set(self.consented_player_ids)):
            raise ValueError("media consented_player_ids must be unique")
        return self


class RawTelemetryBatchV2(StrictModel):
    """Realistic telemetry-only input. Unknown/pre-authored fields fail validation."""

    schema_version: Literal["2.0", "2.1"] = "2.0"
    request_id: str = Field(min_length=1, max_length=128)
    target_player_id: str = Field(min_length=1, max_length=128)
    squad: RawSquadV2
    matches: list[RawMatchV2] = Field(min_length=1, max_length=50)
    squad_history: SquadHistoryV2 = Field(default_factory=SquadHistoryV2)
    current_context: CurrentContextV2 = Field(default_factory=CurrentContextV2)
    social_context: SocialContextV2 | None = None
    media_references: list[MediaReferenceV2] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def references_and_ids_are_consistent(self) -> RawTelemetryBatchV2:
        players = {player.player_id: player for player in self.squad.players}
        if self.target_player_id not in players:
            raise ValueError("target_player_id must belong to the squad")
        match_ids = [match.match_id for match in self.matches]
        if len(match_ids) != len(set(match_ids)):
            raise ValueError("match_id values must be unique")
        events = [event for match in self.matches for event in match.events]
        event_ids = [event.event_id for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event_id values must be unique across the request")
        referenced_players = {
            player_id
            for event in events
            for player_id in (event.actor_id, event.target_id)
            if player_id is not None
        }
        unknown_players = referenced_players - players.keys()
        if unknown_players:
            raise ValueError(f"events reference unknown squad players: {sorted(unknown_players)}")
        unknown_active = set(self.current_context.active_player_ids) - players.keys()
        if unknown_active:
            raise ValueError(
                f"current context references unknown players: {sorted(unknown_active)}"
            )
        if self.social_context and self.social_context.caption_author_player_id:
            if self.social_context.caption_author_player_id not in players:
                raise ValueError("caption author must belong to the squad")
        for media in self.media_references:
            missing_events = set(media.event_ids) - set(event_ids)
            if missing_events:
                raise ValueError(f"media references unknown events: {sorted(missing_events)}")
            missing_players = set(media.consented_player_ids) - players.keys()
            if missing_players:
                raise ValueError(f"media references unknown players: {sorted(missing_players)}")
        return self


class InterpretVariedDeliveryRequestV2(StrictModel):
    """Trusted-server request for one controlled mission-variation generation."""

    telemetry: RawTelemetryBatchV2
    generation_nonce: str = Field(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description=("Bounded opaque nonce generated by the trusted server for this generation."),
    )


class CanonicalEventType(StrEnum):
    LANDING = "landing"
    KNOCK = "knock"
    ELIMINATION = "elimination"
    REVIVE = "revive"
    ASSIST = "assist"
    HEAL = "heal"
    VEHICLE_ENTER = "vehicle_enter"
    VEHICLE_EXIT = "vehicle_exit"
    ESCAPE = "escape"
    ZONE_MOVE = "zone_move"
    LOOT = "loot"
    SIGNAL = "signal"
    MATCH_COMPLETE = "match_complete"


class NormalizedPlayerV2(StrictModel):
    player_id: str
    display_name: str
    memory_eligible: bool
    identity_visible: bool
    media_eligible: bool
    invitation_eligible: bool


class NormalizedEventV2(StrictModel):
    event_id: str
    match_id: str
    event_type: CanonicalEventType
    event_scope: Literal["player", "squad", "match"] = "player"
    actor_id: str | None = None
    target_id: str | None = None
    timestamp_seconds: int
    location: str | None = None
    details: dict[str, TelemetryValue] = Field(default_factory=dict)


class NormalizedMatchV2(StrictModel):
    match_id: str
    game: str
    mode: str
    map_name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    placement: int | None = None
    result: str | None = None
    events: list[NormalizedEventV2]


class NormalizedTelemetryV2(StrictModel):
    request_id: str
    target_player_id: str
    squad_id: str
    players: list[NormalizedPlayerV2]
    matches: list[NormalizedMatchV2]
    squad_history: SquadHistoryV2
    current_context: CurrentContextV2
    social_context: SocialContextV2 | None = None
    media_references: list[MediaReferenceV2] = Field(default_factory=list)


class EvidenceFactV2(StrictModel):
    evidence_id: str
    kind: Literal["event", "match", "context", "social"]
    match_id: str | None = None
    event_type: CanonicalEventType | None = None
    event_scope: Literal["player", "squad", "match"] | None = None
    actor_id: str | None = None
    target_id: str | None = None
    timestamp_seconds: int | None = None
    location: str | None = None
    value: TelemetryValue | None = None
    details: dict[str, TelemetryValue] = Field(default_factory=dict)


class ConsentSafeEvidenceLedgerV2(StrictModel):
    request_id: str
    target_player_id: str
    players: list[NormalizedPlayerV2]
    facts: list[EvidenceFactV2]
    human_context: dict[str, Any] = Field(default_factory=dict)


class EligibleEventWindow(StrictModel):
    window_id: str
    match_id: str
    event_ids: list[str] = Field(min_length=1, max_length=20)
    participant_ids: list[str] = Field(default_factory=list, max_length=4)
    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(ge=0)


class MissionObjectiveRoleV2(StrEnum):
    """Backend-owned purpose of one player-visible chapter objective."""

    PREREQUISITE = "prerequisite"
    PRIMARY = "primary"
    SUPPORT = "support"
    BONUS = "bonus"
    COMPLETION = "completion"


class MissionCompatibilityTagV2(StrEnum):
    """Neutral mechanical tags used by the deterministic chapter composer."""

    SQUAD_ENTRY = "squad_entry"
    LOCATION = "location"
    INDIVIDUAL_ASSIGNMENT = "individual_assignment"
    SQUAD_COORDINATION = "squad_coordination"
    COMBAT = "combat"
    SUPPORT_ACTION = "support_action"
    TACTICAL = "tactical"
    VEHICLE = "vehicle"
    PLACEMENT = "placement"
    MATCH_COMPLETION = "match_completion"


class MissionCapabilityCandidate(StrictModel):
    candidate_id: str
    window_id: str
    recipe: QuestRecipe
    objective_role: MissionObjectiveRoleV2
    required: bool
    compatibility_tags: list[MissionCompatibilityTagV2] = Field(min_length=1, max_length=4)
    assigned_player_id: str | None = None
    source_event_ids: list[str] = Field(min_length=1, max_length=20)
    verification: VerificationRule

    @model_validator(mode="after")
    def objective_metadata_is_consistent(self) -> MissionCapabilityCandidate:
        if self.required != (self.objective_role != MissionObjectiveRoleV2.BONUS):
            raise ValueError("only bonus mission objectives may be optional")
        if len(self.compatibility_tags) != len(set(self.compatibility_tags)):
            raise ValueError("mission compatibility tags must be unique")
        return self


class MissionFamilyV2(StrEnum):
    REUNION = "reunion"
    ROLE_REVERSAL = "role_reversal"
    REDEMPTION = "redemption"
    RETURN_TO_PLACE = "return_to_place"
    LANDING_RENDEZVOUS = "landing_rendezvous"
    DUO_ASSIST = "duo_assist"


class MissionSelectionReasonCodeV2(StrEnum):
    SHARED_SQUAD_REUNION = "shared_squad_reunion"
    DIRECTLY_INVERTS_ORIGINAL_ROLES = "directly_inverts_original_roles"
    PLAYER_SPECIFIC = "player_specific"
    REPEATED_NEAR_MISS = "repeated_near_miss"
    MEASURABLE_IMPROVEMENT = "measurable_improvement"
    DETERMINISTICALLY_VERIFIABLE = "deterministically_verifiable"
    SHARED_LOCATION_CALLBACK = "shared_location_callback"
    SHARED_LANDING_POINT = "shared_landing_point"
    PROVEN_ASSIST_PAIR = "proven_assist_pair"


class MissionAffordanceV2(StrictModel):
    """One complete, backend-feasible continuation offered to the interpreter."""

    affordance_id: str = Field(min_length=1, max_length=160)
    family: MissionFamilyV2
    window_id: str = Field(min_length=1, max_length=128)
    source_event_ids: list[str] = Field(min_length=1, max_length=20)
    source_match_ids: list[str] = Field(min_length=1, max_length=10)
    source_context_ids: list[str] = Field(default_factory=list, max_length=10)
    parameters: dict[str, TelemetryValue] = Field(default_factory=dict, max_length=12)
    objective_candidate_ids: list[str] = Field(
        min_length=1,
        max_length=5,
        description=(
            "Ordered backend-owned chapter objectives: squad-entry prerequisite, one to three "
            "compatible grounded gameplay mechanics, and match completion."
        ),
    )
    allowed_reason_codes: list[MissionSelectionReasonCodeV2] = Field(
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def unique_references(self) -> MissionAffordanceV2:
        for field_name in (
            "source_event_ids",
            "source_match_ids",
            "source_context_ids",
            "objective_candidate_ids",
            "allowed_reason_codes",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} values must be unique")
        return self


class PlayerEventRoleScopeV2(StrictModel):
    """Events a narrator may describe actively, passively, or collectively."""

    actor: list[str] = Field(default_factory=list, max_length=20)
    target: list[str] = Field(default_factory=list, max_length=20)
    full_squad: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_event_references(self) -> PlayerEventRoleScopeV2:
        for values in (
            self.actor,
            self.target,
            self.full_squad,
        ):
            if len(values) != len(set(values)):
                raise ValueError("player event role scope IDs must be unique")
        return self


class EvidenceBoundFieldV2(StrEnum):
    HEALTH_STATE = "health_state"
    ZONE_STATE = "zone_state"
    WEAPON_CLASS = "weapon_class"
    VEHICLE_TYPE = "vehicle_type"
    ITEM_TYPE = "item_type"
    PING_TYPE = "ping_type"
    ZONE_PHASE = "zone_phase"


class AuthoringConstraintsV2(StrictModel):
    """Neutral provider guidance; the evidence ledger remains authoritative."""

    player_event_roles: dict[str, PlayerEventRoleScopeV2] = Field(
        min_length=2,
        max_length=4,
    )
    evidence_bound_terms: dict[str, dict[EvidenceBoundFieldV2, str | int]] = Field(
        default_factory=dict,
        max_length=40,
    )

    @model_validator(mode="after")
    def bounded_constraints(self) -> AuthoringConstraintsV2:
        if any(not event_id or len(event_id) > 180 for event_id in self.evidence_bound_terms):
            raise ValueError("evidence-bound term IDs must contain 1 to 180 characters")
        if any(len(terms) > 12 for terms in self.evidence_bound_terms.values()):
            raise ValueError("evidence-bound term groups may contain at most twelve fields")
        return self


class StoryBriefV2(StrictModel):
    """Compact, consent-safe provider input assembled from authoritative evidence."""

    request_id: str
    target_player_id: str
    players_requiring_perspectives: list[NormalizedPlayerV2]
    invitation_player_ids: list[str] = Field(min_length=2, max_length=4)
    active_player_ids: list[str] = Field(default_factory=list, max_length=4)
    evidence_ledger: ConsentSafeEvidenceLedgerV2
    eligible_event_windows: list[EligibleEventWindow] = Field(min_length=1, max_length=4)
    mission_candidates: list[MissionCapabilityCandidate] = Field(min_length=1, max_length=120)
    mission_affordances: list[MissionAffordanceV2] = Field(min_length=1, max_length=32)
    authoring_constraints: AuthoringConstraintsV2
    squad_history: SquadHistoryV2
    current_context: CurrentContextV2
    media_references: list[MediaReferenceV2] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def authoring_scopes_match_perspective_roster(self) -> StoryBriefV2:
        required_player_ids = {player.player_id for player in self.players_requiring_perspectives}
        scoped_player_ids = set(self.authoring_constraints.player_event_roles)
        if scoped_player_ids != required_player_ids:
            raise ValueError("player event role scopes must match players requiring perspectives")
        if any(
            not 2 <= len(affordance.objective_candidate_ids) <= 5
            for affordance in self.mission_affordances
        ):
            raise ValueError("offered mission affordances must contain two to five objectives")
        candidate_by_id = {
            candidate.candidate_id: candidate for candidate in self.mission_candidates
        }
        for affordance in self.mission_affordances:
            objectives = [candidate_by_id[item] for item in affordance.objective_candidate_ids]
            roles = [objective.objective_role for objective in objectives]
            if (
                roles.count(MissionObjectiveRoleV2.PREREQUISITE) != 1
                or roles.count(MissionObjectiveRoleV2.COMPLETION) != 1
                or roles[0] != MissionObjectiveRoleV2.PREREQUISITE
                or roles[-1] != MissionObjectiveRoleV2.COMPLETION
            ):
                raise ValueError(
                    "mission affordances require one leading prerequisite and one final completion"
                )
            expected_primary_count = 0 if affordance.family == MissionFamilyV2.REUNION else 1
            if roles.count(MissionObjectiveRoleV2.PRIMARY) != expected_primary_count:
                raise ValueError("mission affordance primary objective count does not match family")
            if (
                roles.count(MissionObjectiveRoleV2.SUPPORT) > 2
                or roles.count(MissionObjectiveRoleV2.BONUS) > 2
            ):
                raise ValueError(
                    "mission affordances may contain at most two support or bonus steps"
                )
        return self


class MissionSelectionV2(StrictModel):
    ranked_affordance_ids: list[str] = Field(min_length=1, max_length=32)
    selected_affordance_id: str = Field(min_length=1, max_length=160)
    selected_family: MissionFamilyV2
    reason_codes: list[MissionSelectionReasonCodeV2] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def selected_first_and_unique(self) -> MissionSelectionV2:
        if len(self.ranked_affordance_ids) != len(set(self.ranked_affordance_ids)):
            raise ValueError("ranked_affordance_ids must be unique")
        if self.ranked_affordance_ids[0] != self.selected_affordance_id:
            raise ValueError("selected_affordance_id must rank first")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must be unique")
        return self


class ClaimPredicate(StrEnum):
    PARTICIPATED_MATCH = "participated_match"
    PLAYED_GAME = "played_game"
    PLAYED_MODE = "played_mode"
    PLAYED_MAP = "played_map"
    PLACED = "placed"
    MATCH_RESULT = "match_result"
    LANDED = "landed"
    KNOCKED = "knocked"
    WAS_KNOCKED = "was_knocked"
    ELIMINATED = "eliminated"
    WAS_ELIMINATED = "was_eliminated"
    REVIVED = "revived"
    ASSISTED = "assisted"
    HEALED = "healed"
    ENTERED_VEHICLE = "entered_vehicle"
    EXITED_VEHICLE = "exited_vehicle"
    ESCAPED = "escaped"
    MOVED_ZONE = "moved_zone"
    LOOTED = "looted"
    SIGNALLED = "signalled"
    COMPLETED_MATCH = "completed_match"
    CONNECTED_EPISODE = "connected_episode"
    CURRENT_REUNION_OPPORTUNITY = "current_reunion_opportunity"
    MISSION_RULE = "mission_rule"


class GroundedClaim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=128)
    output_section: str = Field(min_length=1, max_length=128)
    subject_id: str = Field(min_length=1, max_length=128)
    predicate: ClaimPredicate
    target_id: str | None = Field(default=None, min_length=1, max_length=128)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    value: ClaimValue | None = None
    value_key: str | None = Field(default=None, min_length=1, max_length=64)
    supporting_event_ids: list[str] = Field(default_factory=list, max_length=20)
    supporting_context_ids: list[str] = Field(default_factory=list, max_length=10)
    supporting_mission_candidate_ids: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def has_support(self) -> GroundedClaim:
        if not (
            self.supporting_event_ids
            or self.supporting_context_ids
            or self.supporting_mission_candidate_ids
        ):
            raise ValueError("claims require at least one structured support reference")
        return self


class ProposedPerspectiveV2(StrictModel):
    player_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=400)
    evidence_event_ids: list[str] = Field(min_length=1, max_length=20)


class ProposedMissionObjectiveV2(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=400)
    objective_role: MissionObjectiveRoleV2
    required: bool

    @model_validator(mode="after")
    def role_matches_requirement(self) -> ProposedMissionObjectiveV2:
        if self.required != (self.objective_role != MissionObjectiveRoleV2.BONUS):
            raise ValueError("only bonus proposed objectives may be optional")
        return self


class ProposedMissionV2(StrictModel):
    affordance_id: str = Field(min_length=1, max_length=160)
    family: MissionFamilyV2
    ranked_affordance_ids: list[str] = Field(min_length=1, max_length=32)
    selection_reason_codes: list[MissionSelectionReasonCodeV2] = Field(
        min_length=1,
        max_length=8,
    )
    title: str = Field(min_length=1, max_length=120)
    mission: str = Field(min_length=1, max_length=500)
    recipe: QuestRecipe
    objectives: list[ProposedMissionObjectiveV2] = Field(min_length=2, max_length=5)


class MemoryProposalV2(StrictModel):
    selected_match_id: str = Field(min_length=1, max_length=128)
    selected_window_id: str = Field(min_length=1, max_length=128)
    selected_event_ids: list[str] = Field(min_length=1, max_length=20)
    memory_type: MemoryType
    narrative_angle: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=100)
    notification_teaser: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=500)
    why_this_matters_now: str = Field(min_length=1, max_length=240)
    perspectives: list[ProposedPerspectiveV2] = Field(min_length=1, max_length=4)
    mission: ProposedMissionV2
    claims: list[GroundedClaim] = Field(min_length=1, max_length=50)
    media_id: str | None = Field(default=None, min_length=1, max_length=128)


class CompactSectionDraftV2(StrictModel):
    """One fixed authored section plus the evidence IDs supporting its text."""

    text: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(
        min_length=1,
        max_length=20,
        description=(
            "Every event, match, or context ID needed by each factual term in this section; "
            "omit unrelated IDs."
        ),
    )

    @model_validator(mode="after")
    def unique_evidence(self) -> CompactSectionDraftV2:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("section evidence_ids must be unique")
        return self


class CompactPerspectiveV2(StrictModel):
    player_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(
        min_length=1,
        max_length=20,
        description=(
            "Every selected-window event ID needed by each action, player, location, and typed "
            "detail in this message."
        ),
    )

    @model_validator(mode="after")
    def unique_evidence(self) -> CompactPerspectiveV2:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("perspective evidence_ids must be unique")
        return self


class CompactMissionChoiceV2(StrictModel):
    ranked_affordance_ids: list[str] = Field(min_length=1, max_length=32)
    selected_affordance_id: str = Field(min_length=1, max_length=160)
    selection_reason_codes: list[MissionSelectionReasonCodeV2] = Field(
        min_length=1,
        max_length=8,
    )
    title: str = Field(min_length=1, max_length=120)
    story_bridge: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "AI-authored narrative connection for the selected affordance. Authoritative "
            "objective wording is compiled from backend-owned candidates."
        ),
    )

    @model_validator(mode="after")
    def ranking_and_reasons_are_unique(self) -> CompactMissionChoiceV2:
        if len(self.ranked_affordance_ids) != len(set(self.ranked_affordance_ids)):
            raise ValueError("ranked_affordance_ids must be unique")
        if self.ranked_affordance_ids[0] != self.selected_affordance_id:
            raise ValueError("selected_affordance_id must rank first")
        if len(self.selection_reason_codes) != len(set(self.selection_reason_codes)):
            raise ValueError("selection_reason_codes must be unique")
        return self


class CompactMemoryProposalV2(StrictModel):
    """Small provider-facing proposal; authoritative delivery fields are not model-authored."""

    selected_window_id: str = Field(min_length=1, max_length=128)
    memory_type: MemoryType
    narrative_angle: str = Field(min_length=1, max_length=160)
    title: CompactSectionDraftV2
    notification_teaser: CompactSectionDraftV2
    summary: CompactSectionDraftV2
    why_this_matters_now: CompactSectionDraftV2
    perspectives: list[CompactPerspectiveV2] = Field(min_length=1, max_length=4)
    mission: CompactMissionChoiceV2

    @model_validator(mode="after")
    def unique_perspective_ids(self) -> CompactMemoryProposalV2:
        perspective_ids = [item.player_id for item in self.perspectives]
        if len(perspective_ids) != len(set(perspective_ids)):
            raise ValueError("perspective player_id values must be unique")
        return self


class InterpretationDecisionKindV2(StrEnum):
    GENERATE = "generate"
    ABSTAIN = "abstain"


class InterpretationAbstentionReasonV2(StrEnum):
    NO_MEANINGFUL_EPISODE = "no_meaningful_episode"


class CompactInterpretationDecisionV2(StrictModel):
    decision: InterpretationDecisionKindV2
    abstention_reason_code: InterpretationAbstentionReasonV2 | None
    proposal: CompactMemoryProposalV2 | None

    @model_validator(mode="after")
    def payload_matches_decision(self) -> CompactInterpretationDecisionV2:
        if self.decision == InterpretationDecisionKindV2.GENERATE:
            if self.proposal is None or self.abstention_reason_code is not None:
                raise ValueError("generate requires a proposal and no abstention reason")
        elif self.proposal is not None or self.abstention_reason_code is None:
            raise ValueError("abstain requires one reason and no proposal")
        return self


class V2ValidationIssue(StrictModel):
    code: str = Field(min_length=1, max_length=100)
    severity: Literal["warning", "error"]
    message: str = Field(min_length=1, max_length=240)


class ProposalValidationReportV2(StrictModel):
    passed: bool
    correction_attempted: bool = False
    issues: list[V2ValidationIssue] = Field(default_factory=list)


class DeliveryMemoryV2(StrictModel):
    title: str
    memory_type: MemoryType
    summary: str
    notification_teaser: str
    why_this_matters_now: str
    selected_match_id: str
    selected_event_ids: list[str]
    media_reference: MediaReferenceV2 | None = None


class DeliveryPerspectiveV2(StrictModel):
    player_id: str
    display_name: str
    message: str
    evidence_event_ids: list[str]


class DeliveryMissionObjectiveV2(StrictModel):
    objective_id: str
    description: str
    assigned_player_id: str | None = None
    objective_role: MissionObjectiveRoleV2
    required: bool
    verification: VerificationRule
    source_event_ids: list[str]

    @model_validator(mode="after")
    def role_matches_requirement(self) -> DeliveryMissionObjectiveV2:
        if self.required != (self.objective_role != MissionObjectiveRoleV2.BONUS):
            raise ValueError("only bonus delivery objectives may be optional")
        return self


class DeliveryNextChapterV2(StrictModel):
    family: MissionFamilyV2
    invitation_player_ids: list[str] = Field(min_length=2, max_length=4)
    title: str
    mission: str
    recipe: QuestRecipe
    objectives: list[DeliveryMissionObjectiveV2] = Field(min_length=2, max_length=5)


class StudioTraceStageV2(StrictModel):
    stage: Literal[
        "deterministic_preparation",
        "ai_interpretation",
        "deterministic_validation",
        "player_decision",
    ]
    status: Literal["complete", "rejected", "withheld", "pending"]
    summary: str
    issue_codes: list[str] = Field(default_factory=list)


class StudioClaimTraceV2(StrictModel):
    claim_id: str
    output_section: str
    predicate: ClaimPredicate
    evidence_ids: list[str]


class StudioInterpretationTraceV2(StrictModel):
    trace_id: str
    stages: list[StudioTraceStageV2]
    normalized_match_count: int = Field(ge=0)
    normalized_event_count: int = Field(ge=0)
    privacy_redaction_count: int = Field(ge=0)
    eligible_windows: list[EligibleEventWindow] = Field(default_factory=list)
    mission_candidates: list[MissionCapabilityCandidate] = Field(default_factory=list)
    mission_affordances: list[MissionAffordanceV2] = Field(default_factory=list)
    mission_selection: MissionSelectionV2 | None = None
    invitation_eligible_count: int = Field(default=0, ge=0, le=4)
    active_player_count: int = Field(default=0, ge=0, le=4)
    claim_mappings: list[StudioClaimTraceV2] = Field(default_factory=list)
    correction_attempted: bool = False
    source_quality_flag: bool = False


class InterpretDeliveryStatusV2(StrEnum):
    PENDING_PLAYER_DECISION = "pending_player_decision"
    NOT_GENERATED = "not_generated"
    REJECTED = "rejected"


class InterpretDeliveryResultV2(StrictModel):
    schema_version: Literal["2.1"] = "2.1"
    request_id: str
    delivery_id: str | None = None
    status: InterpretDeliveryStatusV2
    reason_codes: list[str] = Field(default_factory=list)
    memory: DeliveryMemoryV2 | None = None
    player_perspectives: list[DeliveryPerspectiveV2] = Field(default_factory=list)
    next_chapter: DeliveryNextChapterV2 | None = None
    grounded_claims: list[GroundedClaim] = Field(default_factory=list)
    validation: ProposalValidationReportV2
    studio_trace: StudioInterpretationTraceV2
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def artifacts_match_status(self) -> InterpretDeliveryResultV2:
        if self.status == InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION:
            if not (
                self.delivery_id
                and self.memory
                and self.player_perspectives
                and self.next_chapter
                and self.grounded_claims
                and self.validation.passed
            ):
                raise ValueError("pending deliveries require complete validated artifacts")
            if self.reason_codes:
                raise ValueError("pending deliveries cannot include rejection reasons")
        elif self.status == InterpretDeliveryStatusV2.REJECTED:
            if any(
                (
                    self.delivery_id,
                    self.memory,
                    self.player_perspectives,
                    self.next_chapter,
                    self.grounded_claims,
                )
            ):
                raise ValueError("rejected deliveries must withhold all generated artifacts")
            if self.validation.passed or not self.reason_codes:
                raise ValueError("rejected deliveries require failed validation and reasons")
        else:
            if any(
                (
                    self.delivery_id,
                    self.memory,
                    self.player_perspectives,
                    self.next_chapter,
                    self.grounded_claims,
                )
            ):
                raise ValueError("not-generated results must withhold all generated artifacts")
            if not self.validation.passed or self.reason_codes != ["ai_no_meaningful_episode"]:
                raise ValueError(
                    "not-generated results require a passed abstention and its reason code"
                )
        return self


class RecordDeliveryDecisionRequestV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    decision: DeliveryDecision
    decline_reason: DeliveryDeclineReason | None = None

    @model_validator(mode="after")
    def decline_reason_matches_decision(self) -> RecordDeliveryDecisionRequestV2:
        if self.decision == DeliveryDecision.ACCEPTED and self.decline_reason is not None:
            raise ValueError("accepted decisions cannot include decline_reason")
        if self.decision == DeliveryDecision.DECLINED and self.decline_reason is None:
            raise ValueError("declined decisions require exactly one decline_reason")
        return self


class DeliveryDecisionRecordV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    delivery_id: str
    decision: DeliveryDecision
    decline_reason: DeliveryDeclineReason | None = None
    delivery_status: Literal["mission_started", "suppressed"]
    source_quality_flag: bool
