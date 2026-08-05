"""Strict input and output contracts for the MemoryOS pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.services.identity import identifier_contains_identity, identity_tokens


class StrictModel(BaseModel):
    """Reject unknown fields so fixture and integration drift is visible."""

    model_config = ConfigDict(extra="forbid")


class Importance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MemoryType(StrEnum):
    CHAOS = "chaos"
    COMEBACK = "comeback"
    CLUTCH = "clutch"
    RITUAL = "ritual"
    FIRST = "first"
    OTHER = "other"


class PipelineStatus(StrEnum):
    READY = "ready"
    NEEDS_HUMAN_CONFIRMATION = "needs_human_confirmation"
    REJECTED = "rejected"


class PipelineStatusV11(StrEnum):
    READY = "ready"
    NEEDS_SOURCE_VERIFICATION = "needs_source_verification"
    NEEDS_MEANING_CONFIRMATION = "needs_meaning_confirmation"
    REJECTED = "rejected"


class SourceStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    VERIFIED = "verified"
    DISPUTED = "disputed"


class MeaningStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class PlayerProfile(StrictModel):
    player_id: str = Field(min_length=1, max_length=128)
    preferred_role: str | None = Field(default=None, max_length=64)


class SquadMember(StrictModel):
    player_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=64)
    role: str | None = Field(default=None, max_length=64)
    opted_in: bool = True


class Squad(StrictModel):
    squad_id: str = Field(min_length=1, max_length=128)
    members: list[SquadMember] = Field(min_length=2, max_length=4)
    matches_together: int = Field(ge=0)
    days_since_full_squad: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def members_have_unique_ids(self) -> Squad:
        member_ids = [member.player_id for member in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("squad member player_id values must be unique")
        identity_owners: dict[tuple[str, ...], int] = {}
        for index, member in enumerate(self.members):
            for value in (member.player_id, member.display_name):
                key = identity_tokens(value)
                owner = identity_owners.setdefault(key, index)
                if owner != index:
                    raise ValueError(
                        "squad member IDs and display names must not collide across members"
                    )
        return self


class SquadMemberV11(SquadMember):
    opted_in: bool


class SquadV11(Squad):
    members: list[SquadMemberV11] = Field(min_length=2, max_length=4)


class LegacySquadMember(SquadMember):
    """A v1.0 member submitted through the public compatibility endpoint."""

    opted_in: bool


class LegacySquad(Squad):
    """The legacy wire shape with current consent made explicit."""

    members: list[LegacySquadMember] = Field(min_length=2, max_length=4)


class MatchContext(StrictModel):
    match_id: str = Field(min_length=1, max_length=128)
    mode: str = Field(min_length=1, max_length=64)
    map_name: str | None = Field(default=None, max_length=100)
    placement: int | None = Field(default=None, ge=1)
    played_at: datetime | None = None


class MatchEvent(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=64)
    actor_id: str | None = Field(default=None, max_length=128)
    target_id: str | None = Field(default=None, max_length=128)
    timestamp_seconds: int | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=100)
    importance: Importance = Importance.MEDIUM
    details: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=16)


class HumanMemory(StrictModel):
    caption: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=8)
    author_player_id: str | None = Field(default=None, max_length=128)
    confirmed: bool | None = None

    @field_validator("caption")
    @classmethod
    def normalize_caption(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return [tag.strip() for tag in value]

    @model_validator(mode="after")
    def tags_are_bounded(self) -> HumanMemory:
        if any(not tag or len(tag) > 40 for tag in self.tags):
            raise ValueError("human memory tags must contain 1 to 40 characters")
        return self


class HumanMemoryV11(StrictModel):
    caption: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=8)
    author_player_id: str | None = Field(default=None, max_length=128)

    @field_validator("caption")
    @classmethod
    def normalize_caption(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return [tag.strip() for tag in value]

    @model_validator(mode="after")
    def tags_are_bounded(self) -> HumanMemoryV11:
        if any(not tag or len(tag) > 40 for tag in self.tags):
            raise ValueError("human memory tags must contain 1 to 40 characters")
        return self


class HumanReview(StrictModel):
    """Separate factual verification from a player's emotional judgment."""

    source_status: SourceStatus = SourceStatus.UNREVIEWED
    meaning_status: MeaningStatus = MeaningStatus.UNREVIEWED


class Reactions(StrictModel):
    laugh_count: int = Field(default=0, ge=0)
    fire_count: int = Field(default=0, ge=0)
    saved: bool = False


class CurrentContext(StrictModel):
    active_member_ids: list[str] = Field(default_factory=list, max_length=4)
    resurfacing_reason: str | None = Field(default=None, max_length=300)
    original_mode_available: bool = True

    @model_validator(mode="after")
    def member_ids_are_bounded(self) -> CurrentContext:
        if any(not player_id or len(player_id) > 128 for player_id in self.active_member_ids):
            raise ValueError("active member IDs must contain 1 to 128 characters")
        return self


class MemoryPack(StrictModel):
    """Garena-style input: gameplay, social, human, and current context signals."""

    schema_version: Literal["1.0"] = "1.0"
    pack_id: str = Field(min_length=1, max_length=128)
    player_profile: PlayerProfile
    squad: Squad
    match: MatchContext
    match_events: list[MatchEvent] = Field(default_factory=list, max_length=100)
    human_memory: HumanMemory | None = None
    reactions: Reactions = Field(default_factory=Reactions)
    current_context: CurrentContext = Field(default_factory=CurrentContext)

    @model_validator(mode="after")
    def references_known_players_and_unique_events(self) -> MemoryPack:
        member_ids = {member.player_id for member in self.squad.members}
        if self.player_profile.player_id not in member_ids:
            raise ValueError("player_profile.player_id must belong to the squad")

        event_ids = [event.event_id for event in self.match_events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("match event_id values must be unique")

        referenced_ids = {
            player_id
            for event in self.match_events
            for player_id in (event.actor_id, event.target_id)
            if player_id is not None
        }
        unknown_ids = referenced_ids - member_ids
        if unknown_ids:
            raise ValueError(f"events reference unknown squad players: {sorted(unknown_ids)}")

        active_unknown = set(self.current_context.active_member_ids) - member_ids
        if active_unknown:
            raise ValueError(
                f"current_context references unknown players: {sorted(active_unknown)}"
            )

        if self.human_memory and self.human_memory.author_player_id:
            if self.human_memory.author_player_id not in member_ids:
                raise ValueError("human_memory.author_player_id must belong to the squad")

        integer_detail_keys = {
            "count",
            "duration_seconds",
            "nearby_enemies",
            "passengers",
            "placement_reached",
            "squad_alive",
        }
        for event in self.match_events:
            if any(len(key) > 64 for key in event.details):
                raise ValueError("event detail keys must be at most 64 characters")
            if any(isinstance(value, str) and len(value) > 100 for value in event.details.values()):
                raise ValueError("event detail string values must be at most 100 characters")
            for key in integer_detail_keys & event.details.keys():
                value = event.details[key]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"event detail {key!r} must be a non-negative integer")
            allowed_states = {
                "health_state": {"critical", "low", "stable", "full", "unknown"},
                "zone_state": {"closing", "closed", "safe", "shrinking", "unknown"},
            }
            for key, allowed in allowed_states.items():
                if key in event.details and event.details[key] not in allowed:
                    raise ValueError(f"event detail {key!r} has an unsupported value")

        human_review = getattr(self, "human_review", None)
        if self.schema_version == "1.1":
            if human_review is None:
                raise ValueError("schema v1.1 requires human_review")
            if self.human_memory and getattr(self.human_memory, "confirmed", None) is not None:
                raise ValueError("schema v1.1 must use human_review instead of confirmed")
            if any("opted_in" not in member.model_fields_set for member in self.squad.members):
                raise ValueError("schema v1.1 requires explicit opted_in for every squad member")

        private_terms = {
            term
            for member in self.squad.members
            if not member.opted_in
            for term in (member.player_id, member.display_name)
        }
        opaque_ids = [
            self.pack_id,
            self.squad.squad_id,
            self.match.match_id,
            *(event.event_id for event in self.match_events),
        ]
        if any(
            identifier_contains_identity(identifier, term)
            for identifier in opaque_ids
            for term in private_terms
        ):
            raise ValueError("opaque identifiers must not contain opted-out identities")
        return self

    @property
    def source_status(self) -> SourceStatus:
        human_review = getattr(self, "human_review", None)
        if self.schema_version == "1.1" and human_review:
            return human_review.source_status
        confirmed = bool(self.human_memory and self.human_memory.confirmed)
        return SourceStatus.VERIFIED if confirmed else SourceStatus.UNREVIEWED

    @property
    def meaning_status(self) -> MeaningStatus:
        human_review = getattr(self, "human_review", None)
        if self.schema_version == "1.1" and human_review:
            return human_review.meaning_status
        confirmed = bool(self.human_memory and self.human_memory.confirmed)
        return MeaningStatus.CONFIRMED if confirmed else MeaningStatus.UNREVIEWED

    @property
    def target_player_opted_in(self) -> bool:
        return next(
            member.opted_in
            for member in self.squad.members
            if member.player_id == self.player_profile.player_id
        )


class LegacyMemoryPack(MemoryPack):
    """The deprecated endpoint accepts only the original v1.0 wire contract."""

    schema_version: Literal["1.0"] = "1.0"
    squad: LegacySquad


class MemoryPackV11(MemoryPack):
    """Canonical Phase 2 input with explicit consent and split review state."""

    schema_version: Literal["1.1"] = "1.1"
    squad: SquadV11
    human_memory: HumanMemoryV11 | None = None
    human_review: HumanReview


class DiscoveryAssessment(StrictModel):
    signal_score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    reasons: list[str] = Field(max_length=20)
    eligible: bool


class EvidenceRef(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=64)
    significance: str = Field(min_length=1, max_length=300)


class MemoryRecord(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    memory_type: MemoryType
    summary: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=10)
    human_confirmed: bool


class PlayerPerspective(StrictModel):
    player_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=400)
    evidence_event_ids: list[str] = Field(min_length=1, max_length=10)


class PerspectiveSet(StrictModel):
    perspectives: list[PlayerPerspective] = Field(min_length=1, max_length=4)


class QuestRecipe(StrEnum):
    RECREATE = "recreate"
    REMIX = "remix"
    RESOLVE = "resolve"


class VerificationRule(StrictModel):
    metric: str = Field(min_length=1, max_length=128)
    operator: Literal["equals", "at_least", "contains_all"]
    target: str | int | float | bool | list[str]


class QuestObjective(StrictModel):
    objective_id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=400)
    assigned_player_id: str | None = Field(default=None, max_length=128)
    required: bool = True
    verification: VerificationRule
    source_event_ids: list[str] = Field(min_length=1, max_length=10)


class NextChapter(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    mission: str = Field(min_length=1, max_length=500)
    recipe: QuestRecipe
    objectives: list[QuestObjective] = Field(min_length=1, max_length=10)


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationIssue(StrictModel):
    code: str
    severity: IssueSeverity
    message: str


class QualityScores(StrictModel):
    specificity: float = Field(ge=0, le=1)
    evidence_grounding: float = Field(ge=0, le=1)
    perspective_distinctness: float = Field(ge=0, le=1)
    quest_connection: float = Field(ge=0, le=1)


class ValidationReport(StrictModel):
    passed: bool
    human_review_required: bool
    scores: QualityScores
    issues: list[ValidationIssue] = Field(default_factory=list)


class MemoryEngineResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    pack_id: str
    status: PipelineStatus
    discovery: DiscoveryAssessment
    memory: MemoryRecord | None = None
    player_perspectives: list[PlayerPerspective] = Field(default_factory=list)
    next_chapter: NextChapter | None = None
    validation: ValidationReport
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateScoreBreakdown(StrictModel):
    """Weighted eligibility contributions; total excludes the ranking-only penalty."""

    evidence_strength: float = Field(ge=0, le=0.35)
    human_signals: float = Field(ge=0, le=0.30)
    squad_specificity: float = Field(ge=0, le=0.20)
    resurfacing_relevance: float = Field(ge=0, le=0.15)
    diversity_penalty: float = Field(default=0, ge=0, le=0.08)
    total: float = Field(ge=0, le=1)


class RedactionNotice(StrictModel):
    alias: str
    reason: Literal["player_opted_out"] = "player_opted_out"


class HistoricalCandidate(StrictModel):
    rank: int = Field(ge=1)
    pack_id: str
    match_id: str
    memory_type: MemoryType
    title: str
    summary: str
    score: float = Field(ge=0, le=1)
    ranking_score: float = Field(ge=0, le=1)
    score_breakdown: CandidateScoreBreakdown
    reasons: list[str]
    source_status: SourceStatus
    meaning_status: MeaningStatus
    redactions: list[RedactionNotice] = Field(default_factory=list)


class HistoricalDiscoveryRequest(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    memory_packs: list[MemoryPack | MemoryPackV11] = Field(min_length=1, max_length=50)
    limit: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def packs_share_squad_and_target(self) -> HistoricalDiscoveryRequest:
        for pack in self.memory_packs:
            if pack.schema_version == "1.0" and any(
                "opted_in" not in member.model_fields_set for member in pack.squad.members
            ):
                raise ValueError(
                    "legacy packs require explicit opted_in for every squad member "
                    "on v1.1 endpoints"
                )
        squad_ids = {pack.squad.squad_id for pack in self.memory_packs}
        player_ids = {pack.player_profile.player_id for pack in self.memory_packs}
        if len(squad_ids) != 1:
            raise ValueError("all memory_packs must belong to the same squad")
        if len(player_ids) != 1:
            raise ValueError("all memory_packs must target the same player")
        roster_ids = [
            {member.player_id for member in pack.squad.members} for pack in self.memory_packs
        ]
        if any(member_ids != roster_ids[0] for member_ids in roster_ids[1:]):
            raise ValueError("all memory_packs must use the same squad member IDs")
        consent_states: dict[str, set[bool]] = {}
        for pack in self.memory_packs:
            for member in pack.squad.members:
                consent_states.setdefault(member.player_id, set()).add(member.opted_in)
        if any(len(states) != 1 for states in consent_states.values()):
            raise ValueError("all memory_packs must use one current consent snapshot")
        pack_ids = [pack.pack_id for pack in self.memory_packs]
        if len(pack_ids) != len(set(pack_ids)):
            raise ValueError("memory_packs must have unique pack_id values")
        return self


class HistoricalFilterCounts(StrictModel):
    received: int = Field(ge=0)
    duplicates_removed: int = Field(ge=0)
    no_grounded_events: int = Field(ge=0)
    below_threshold: int = Field(ge=0)
    disputed: int = Field(ge=0)
    dismissed: int = Field(ge=0)
    target_opted_out: int = Field(ge=0)
    eligible_not_selected: int = Field(ge=0)


class HistoricalDiscoveryResponse(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    candidates: list[HistoricalCandidate]
    filters: HistoricalFilterCounts
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateMemoryRequest(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    memory_pack: MemoryPack | MemoryPackV11

    @model_validator(mode="after")
    def legacy_pack_has_current_consent(self) -> GenerateMemoryRequest:
        if self.memory_pack.schema_version == "1.0" and any(
            "opted_in" not in member.model_fields_set for member in self.memory_pack.squad.members
        ):
            raise ValueError(
                "legacy packs require explicit opted_in for every squad member on v1.1 endpoints"
            )
        return self


class MemoryEngineResultV11(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    pack_id: str
    status: PipelineStatusV11
    discovery: DiscoveryAssessment
    source_status: SourceStatus
    meaning_status: MeaningStatus
    memory: MemoryRecord | None = None
    player_perspectives: list[PlayerPerspective] = Field(default_factory=list)
    next_chapter: NextChapter | None = None
    validation: ValidationReport
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderErrorBody(StrictModel):
    code: str
    stage: str
    retryable: bool
    message: str


class GenerateStreamStageEvent(StrictModel):
    """One progress snapshot in the NDJSON generation stream."""

    type: Literal["stage"] = "stage"
    stage: Literal[
        "review_and_discovery",
        "memory_discovery",
        "perspectives",
        "quest_generation",
        "validation",
    ]
    status: Literal["working", "complete", "stopped", "failed"]
    message: str | None = None
    preview: MemoryRecord | list[PlayerPerspective] | NextChapter | ValidationReport | None = None


class GenerateStreamErrorEvent(StrictModel):
    """A safe provider failure emitted after an NDJSON stream has begun."""

    type: Literal["error"] = "error"
    stage: str
    code: str
    retryable: bool


class GenerateStreamResultEvent(StrictModel):
    """The canonical v1.1 result emitted as the final NDJSON record."""

    type: Literal["result"] = "result"
    result: MemoryEngineResultV11


GenerateStreamEvent = Annotated[
    GenerateStreamStageEvent | GenerateStreamErrorEvent | GenerateStreamResultEvent,
    Field(discriminator="type"),
]
