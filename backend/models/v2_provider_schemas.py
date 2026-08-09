"""Compact provider-only contracts for MemoryOS v2 interpretation.

Request-scoped W/A/O selection references end at the interpreter boundary.
Consent-safe evidence IDs remain available for grounding, while canonical mission
selection IDs, verification rules, delivery models, and Studio traces stay backend-owned.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from backend.models.schemas import MemoryType, StrictModel
from backend.models.v2_schemas import (
    AuthoringConstraintsV2,
    CanonicalEventType,
    CompactPerspectiveV2,
    CompactSectionDraftV2,
    ConsentSafeEvidenceLedgerV2,
    CurrentContextV2,
    InterpretationAbstentionReasonV2,
    InterpretationDecisionKindV2,
    MediaReferenceV2,
    MissionFamilyV2,
    MissionSelectionReasonCodeV2,
    NormalizedPlayerV2,
    SquadHistoryV2,
)

ProviderReference = Annotated[
    str,
    Field(
        min_length=1,
        max_length=16,
        description="Request-scoped W, A, or O reference; copied from the supplied brief.",
    ),
]


class ProviderWindowV2(StrictModel):
    window_ref: ProviderReference
    match_id: str = Field(min_length=1, max_length=128)
    event_ids: list[str] = Field(min_length=1, max_length=20)
    participant_ids: list[str] = Field(default_factory=list, max_length=4)
    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(ge=0)


class MissionObjectiveKindV2(StrEnum):
    REQUIRED_PARTICIPANTS = "required_participants"
    COMPLETED_MATCHES = "completed_matches"
    EVENT_ACTOR = "event_actor"
    PLACEMENT_AT_MOST = "placement_at_most"


class ProviderMissionObjectiveV2(StrictModel):
    objective_ref: ProviderReference
    kind: MissionObjectiveKindV2
    required_terms: list[str] = Field(
        min_length=1,
        max_length=6,
        description=(
            "Backend-owned mechanical anchors that explain the objective. The backend renders "
            "the authoritative player-facing requirement; these terms do not prescribe the "
            "AI-authored story bridge."
        ),
    )
    roster_ref: Literal["invitation_player_ids"] | None = None
    assigned_player_id: str | None = Field(default=None, min_length=1, max_length=128)
    event_type: CanonicalEventType | None = None
    ordinal: Literal["first"] | None = None
    minimum_count: int | None = Field(default=None, ge=1, le=100)
    placement_at_most: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def fields_match_kind(self) -> ProviderMissionObjectiveV2:
        normalized_terms = [term.strip().casefold() for term in self.required_terms]
        if any(not term or len(term) > 64 for term in normalized_terms):
            raise ValueError("mission objective required terms must contain 1 to 64 characters")
        if len(normalized_terms) != len(set(normalized_terms)):
            raise ValueError("mission objective required terms must be unique")
        supplied = {
            "roster_ref": self.roster_ref is not None,
            "assigned_player_id": self.assigned_player_id is not None,
            "event_type": self.event_type is not None,
            "ordinal": self.ordinal is not None,
            "minimum_count": self.minimum_count is not None,
            "placement_at_most": self.placement_at_most is not None,
        }
        expected = {
            MissionObjectiveKindV2.REQUIRED_PARTICIPANTS: {"roster_ref"},
            MissionObjectiveKindV2.COMPLETED_MATCHES: {"minimum_count"},
            MissionObjectiveKindV2.EVENT_ACTOR: {
                "assigned_player_id",
                "event_type",
                "ordinal",
            },
            MissionObjectiveKindV2.PLACEMENT_AT_MOST: {"placement_at_most"},
        }[self.kind]
        if {field for field, present in supplied.items() if present} != expected:
            raise ValueError("mission objective capability fields must match its kind")
        return self


class ProviderSourceRoleBindingV2(StrictModel):
    source_event_id: str = Field(min_length=1, max_length=128)
    event_type: CanonicalEventType
    source_actor_id: str = Field(min_length=1, max_length=128)
    source_target_id: str = Field(min_length=1, max_length=128)
    future_actor_id: str = Field(min_length=1, max_length=128)


class ProviderMissionAffordanceV2(StrictModel):
    affordance_ref: ProviderReference
    family: MissionFamilyV2
    window_ref: ProviderReference
    source_event_ids: list[str] = Field(min_length=1, max_length=20)
    source_match_ids: list[str] = Field(min_length=1, max_length=10)
    source_context_ids: list[str] = Field(default_factory=list, max_length=10)
    allowed_reason_codes: list[MissionSelectionReasonCodeV2] = Field(
        min_length=1,
        max_length=8,
    )
    objectives: list[ProviderMissionObjectiveV2] = Field(min_length=1, max_length=10)
    source_role_binding: ProviderSourceRoleBindingV2 | None = None

    @model_validator(mode="after")
    def references_and_role_binding_are_consistent(self) -> ProviderMissionAffordanceV2:
        objective_refs = [objective.objective_ref for objective in self.objectives]
        if len(objective_refs) != len(set(objective_refs)):
            raise ValueError("provider objective references must be unique per affordance")
        if self.family == MissionFamilyV2.ROLE_REVERSAL:
            if self.source_role_binding is None:
                raise ValueError("role reversal requires one neutral source-role binding")
            if self.source_role_binding.source_event_id not in self.source_event_ids:
                raise ValueError("source-role binding must reference an affordance source event")
            event_actor_objectives = [
                objective
                for objective in self.objectives
                if objective.kind == MissionObjectiveKindV2.EVENT_ACTOR
            ]
            if (
                len(event_actor_objectives) != 1
                or event_actor_objectives[0].assigned_player_id
                != self.source_role_binding.future_actor_id
            ):
                raise ValueError("role reversal must bind its one future event actor")
        elif self.source_role_binding is not None:
            raise ValueError("source-role binding is allowed only for role reversal")
        return self


class ProviderStoryBriefV2(StrictModel):
    request_id: str
    target_player_id: str
    players_requiring_perspectives: list[NormalizedPlayerV2]
    invitation_player_ids: list[str] = Field(min_length=2, max_length=4)
    active_player_ids: list[str] = Field(default_factory=list, max_length=4)
    evidence_ledger: ConsentSafeEvidenceLedgerV2
    windows: list[ProviderWindowV2] = Field(min_length=1, max_length=4)
    affordances: list[ProviderMissionAffordanceV2] = Field(min_length=1, max_length=32)
    authoring_constraints: AuthoringConstraintsV2
    squad_history: SquadHistoryV2
    current_context: CurrentContextV2
    media_references: list[MediaReferenceV2] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def provider_references_are_consistent(self) -> ProviderStoryBriefV2:
        window_refs = [window.window_ref for window in self.windows]
        affordance_refs = [affordance.affordance_ref for affordance in self.affordances]
        objective_refs = [
            objective.objective_ref
            for affordance in self.affordances
            for objective in affordance.objectives
        ]
        if len(window_refs) != len(set(window_refs)):
            raise ValueError("provider window references must be unique")
        if len(affordance_refs) != len(set(affordance_refs)):
            raise ValueError("provider affordance references must be unique")
        if len(objective_refs) != len(set(objective_refs)):
            raise ValueError("provider objective references must be globally unique")
        window_by_ref = {window.window_ref: window for window in self.windows}
        invitation_roster = set(self.invitation_player_ids)
        for affordance in self.affordances:
            window = window_by_ref.get(affordance.window_ref)
            if window is None:
                raise ValueError("provider affordance must reference an offered window")
            if not set(affordance.source_event_ids).issubset(window.event_ids):
                raise ValueError("provider affordance source events must belong to its window")
            binding = affordance.source_role_binding
            if binding and not {
                binding.source_actor_id,
                binding.source_target_id,
                binding.future_actor_id,
            }.issubset(invitation_roster):
                raise ValueError("provider role bindings must use invitation-safe players")
            for objective in affordance.objectives:
                if (
                    objective.assigned_player_id is not None
                    and objective.assigned_player_id not in invitation_roster
                ):
                    raise ValueError("provider objective assignees must be invitation-safe")
        required_player_ids = {player.player_id for player in self.players_requiring_perspectives}
        if set(self.authoring_constraints.player_event_roles) != required_player_ids:
            raise ValueError("provider role scopes must match the perspective roster")
        return self


class ProviderMissionChoiceV2(StrictModel):
    ranked_affordance_refs: list[ProviderReference] = Field(min_length=1, max_length=32)
    selection_reason_codes: list[MissionSelectionReasonCodeV2] = Field(
        min_length=1,
        max_length=8,
    )
    title: str = Field(min_length=1, max_length=120)
    story_bridge: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "A short narrative connection between the selected episode and affordance. "
            "The backend, not this text, owns and renders the mission requirements."
        ),
    )

    @model_validator(mode="after")
    def unique_reason_codes(self) -> ProviderMissionChoiceV2:
        if len(self.selection_reason_codes) != len(set(self.selection_reason_codes)):
            raise ValueError("selection_reason_codes must be unique")
        return self


class ProviderMemoryProposalV2(StrictModel):
    memory_type: MemoryType
    narrative_angle: str = Field(min_length=1, max_length=160)
    title: CompactSectionDraftV2
    notification_teaser: CompactSectionDraftV2
    summary: CompactSectionDraftV2
    why_this_matters_now: CompactSectionDraftV2
    perspectives: list[CompactPerspectiveV2] = Field(min_length=1, max_length=4)
    mission: ProviderMissionChoiceV2

    @model_validator(mode="after")
    def unique_perspective_ids(self) -> ProviderMemoryProposalV2:
        player_ids = [item.player_id for item in self.perspectives]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("perspective player_id values must be unique")
        return self


class ProviderInterpretationDecisionV2(StrictModel):
    decision: InterpretationDecisionKindV2
    abstention_reason_code: InterpretationAbstentionReasonV2 | None
    proposal: ProviderMemoryProposalV2 | None

    @model_validator(mode="after")
    def payload_matches_decision(self) -> ProviderInterpretationDecisionV2:
        if self.decision == InterpretationDecisionKindV2.GENERATE:
            if self.proposal is None or self.abstention_reason_code is not None:
                raise ValueError("generate requires a proposal and no abstention reason")
        elif self.proposal is not None or self.abstention_reason_code is None:
            raise ValueError("abstain requires one reason and no proposal")
        return self
