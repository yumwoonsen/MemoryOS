"""Strict Developer Studio contracts for the registered v2 evaluation scenarios.

These models deliberately keep offline expectations beside Studio provenance rather
than embedding them in raw telemetry or the provider-facing story brief.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from backend.models.schemas import StrictModel
from backend.models.v2_schemas import (
    EligibleEventWindow,
    InterpretDeliveryResultV2,
    InterpretDeliveryStatusV2,
    MissionAffordanceV2,
    MissionCapabilityCandidate,
    MissionFamilyV2,
)


class StudioScenarioIdV2(StrEnum):
    RESCUE_ROLE_REVERSAL = "rescue-role-reversal"
    LANDING_RENDEZVOUS = "landing-rendezvous"
    DUO_ASSIST = "duo-assist"
    REPEATED_NEAR_MISS = "repeated-near-miss"
    ORDINARY_SPARSE_TELEMETRY = "ordinary-sparse-telemetry"


class StudioScenarioDescriptorV2(StrictModel):
    scenario_id: StudioScenarioIdV2
    title: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=240)
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_revision: str = Field(pattern=r"^2\.1:[0-9a-f]{12}$")
    expected_status: InterpretDeliveryStatusV2
    expected_mission_family: MissionFamilyV2 | None = None
    label_source: Literal["offline_evaluation_manifest"] = "offline_evaluation_manifest"

    @model_validator(mode="after")
    def expectation_is_coherent(self) -> StudioScenarioDescriptorV2:
        expects_delivery = self.expected_status == InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION
        if expects_delivery != (self.expected_mission_family is not None):
            raise ValueError("only pending delivery scenarios require an expected mission family")
        return self


class StudioScenarioCatalogV2(StrictModel):
    schema_version: Literal["2.1"] = "2.1"
    scenarios: list[StudioScenarioDescriptorV2] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def contains_each_scenario_once(self) -> StudioScenarioCatalogV2:
        scenario_ids = [item.scenario_id for item in self.scenarios]
        if len(set(scenario_ids)) != len(StudioScenarioIdV2):
            raise ValueError("Studio scenario catalog must contain each registered scenario once")
        return self


class StudioScenarioMatchSummaryV2(StrictModel):
    match_id: str
    game: str
    mode: str
    map_name: str | None = None
    started_at: datetime
    placement: int | None = Field(default=None, ge=1, le=100)
    event_count: int = Field(ge=0)


class StudioScenarioTelemetrySummaryV2(StrictModel):
    request_id: str
    target_player_id: str
    match_count: int = Field(ge=0)
    raw_event_count: int = Field(ge=0)
    consent_safe_player_count: int = Field(ge=0, le=4)
    invitation_eligible_count: int = Field(ge=0, le=4)
    active_player_count: int = Field(ge=0, le=4)
    matches: list[StudioScenarioMatchSummaryV2] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def match_count_matches_projection(self) -> StudioScenarioTelemetrySummaryV2:
        if self.match_count != len(self.matches):
            raise ValueError("match_count must equal the number of sanitized match summaries")
        return self


class StudioScenarioNormalizationSummaryV2(StrictModel):
    normalized_match_count: int = Field(ge=0)
    normalized_event_count: int = Field(ge=0)
    issue_codes: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def issue_codes_are_unique(self) -> StudioScenarioNormalizationSummaryV2:
        if len(self.issue_codes) != len(set(self.issue_codes)):
            raise ValueError("normalization issue codes must be unique")
        return self


class StudioScenarioPrivacySummaryV2(StrictModel):
    redaction_count: int = Field(ge=0)
    anonymous_player_count: int = Field(ge=0, le=4)


class StudioScenarioPreparationStatusV2(StrEnum):
    READY = "ready"
    REJECTED = "rejected"


class StudioScenarioPreparationV2(StrictModel):
    schema_version: Literal["2.1"] = "2.1"
    scenario: StudioScenarioDescriptorV2
    status: StudioScenarioPreparationStatusV2
    telemetry_summary: StudioScenarioTelemetrySummaryV2
    normalization: StudioScenarioNormalizationSummaryV2
    privacy: StudioScenarioPrivacySummaryV2
    eligible_windows: list[EligibleEventWindow] = Field(default_factory=list, max_length=6)
    mission_candidates: list[MissionCapabilityCandidate] = Field(
        default_factory=list,
        max_length=120,
    )
    mission_affordances: list[MissionAffordanceV2] = Field(
        default_factory=list,
        max_length=32,
    )

    @model_validator(mode="after")
    def preparation_references_are_consistent(self) -> StudioScenarioPreparationV2:
        if self.status == StudioScenarioPreparationStatusV2.READY:
            if self.normalization.issue_codes:
                raise ValueError("ready Studio preparation cannot contain issue codes")
            if not (self.eligible_windows and self.mission_candidates and self.mission_affordances):
                raise ValueError("ready Studio preparation requires windows and mission options")
        elif not self.normalization.issue_codes:
            raise ValueError("rejected Studio preparation requires at least one issue code")

        window_ids = {window.window_id for window in self.eligible_windows}
        candidate_ids = {candidate.candidate_id for candidate in self.mission_candidates}
        if any(candidate.window_id not in window_ids for candidate in self.mission_candidates):
            raise ValueError("mission candidates must reference offered event windows")
        if any(
            affordance.window_id not in window_ids
            or not set(affordance.objective_candidate_ids).issubset(candidate_ids)
            for affordance in self.mission_affordances
        ):
            raise ValueError("mission affordances must reference offered windows and candidates")
        return self


class StudioScenarioInterpretationV2(StrictModel):
    schema_version: Literal["2.1"] = "2.1"
    scenario: StudioScenarioDescriptorV2
    result: InterpretDeliveryResultV2
