"""Strict input and output contracts for the MemoryOS pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class PlayerProfile(StrictModel):
    player_id: str = Field(min_length=1)
    preferred_role: str | None = None


class SquadMember(StrictModel):
    player_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str | None = None
    opted_in: bool = True


class Squad(StrictModel):
    squad_id: str = Field(min_length=1)
    members: list[SquadMember] = Field(min_length=2)
    matches_together: int = Field(ge=0)
    days_since_full_squad: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def members_have_unique_ids(self) -> Squad:
        member_ids = [member.player_id for member in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("squad member player_id values must be unique")
        return self


class MatchContext(StrictModel):
    match_id: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    map_name: str | None = None
    placement: int | None = Field(default=None, ge=1)
    played_at: datetime | None = None


class MatchEvent(StrictModel):
    event_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    actor_id: str | None = None
    target_id: str | None = None
    timestamp_seconds: int | None = Field(default=None, ge=0)
    location: str | None = None
    importance: Importance = Importance.MEDIUM
    details: dict[str, str | int | float | bool] = Field(default_factory=dict)


class HumanMemory(StrictModel):
    caption: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=8)
    author_player_id: str | None = None
    confirmed: bool = False


class Reactions(StrictModel):
    laugh_count: int = Field(default=0, ge=0)
    fire_count: int = Field(default=0, ge=0)
    saved: bool = False


class CurrentContext(StrictModel):
    active_member_ids: list[str] = Field(default_factory=list)
    resurfacing_reason: str | None = None
    original_mode_available: bool = True


class MemoryPack(StrictModel):
    """Garena-style input: gameplay, social, human, and current context signals."""

    schema_version: Literal["1.0"] = "1.0"
    pack_id: str = Field(min_length=1)
    player_profile: PlayerProfile
    squad: Squad
    match: MatchContext
    match_events: list[MatchEvent] = Field(default_factory=list)
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
        return self


class DiscoveryAssessment(StrictModel):
    signal_score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    reasons: list[str]
    eligible: bool


class EvidenceRef(StrictModel):
    event_id: str
    event_type: str
    significance: str


class MemoryRecord(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    memory_type: MemoryType
    summary: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceRef] = Field(min_length=1)
    human_confirmed: bool


class PlayerPerspective(StrictModel):
    player_id: str
    display_name: str
    message: str = Field(min_length=1, max_length=400)
    evidence_event_ids: list[str] = Field(min_length=1)


class PerspectiveSet(StrictModel):
    perspectives: list[PlayerPerspective]


class QuestRecipe(StrEnum):
    RECREATE = "recreate"
    REMIX = "remix"
    RESOLVE = "resolve"


class VerificationRule(StrictModel):
    metric: str
    operator: Literal["equals", "at_least", "contains_all"]
    target: str | int | float | bool | list[str]


class QuestObjective(StrictModel):
    objective_id: str
    description: str
    assigned_player_id: str | None = None
    required: bool = True
    verification: VerificationRule
    source_event_ids: list[str]


class NextChapter(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    mission: str = Field(min_length=1, max_length=500)
    recipe: QuestRecipe
    objectives: list[QuestObjective] = Field(min_length=1)


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
