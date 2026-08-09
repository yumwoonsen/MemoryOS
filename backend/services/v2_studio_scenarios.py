"""Backend-owned Developer Studio scenarios and zero-provider preparation views."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from backend.models.v2_schemas import (
    InterpretDeliveryStatusV2,
    MissionFamilyV2,
    RawTelemetryBatchV2,
)
from backend.models.v2_studio_schemas import (
    StudioScenarioCatalogV2,
    StudioScenarioDescriptorV2,
    StudioScenarioIdV2,
    StudioScenarioMatchSummaryV2,
    StudioScenarioNormalizationSummaryV2,
    StudioScenarioPreparationStatusV2,
    StudioScenarioPreparationV2,
    StudioScenarioPrivacySummaryV2,
    StudioScenarioTelemetrySummaryV2,
)
from backend.services.v2_preparation import TelemetryPreparerV2

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
EVALUATION_DIR = DATA_DIR / "v2_evaluation"
MANIFEST_PATH = EVALUATION_DIR / "manifest.json"


@dataclass(frozen=True)
class _ScenarioConfig:
    scenario_id: StudioScenarioIdV2
    title: str
    purpose: str
    fixture_path: Path


@dataclass(frozen=True)
class RegisteredStudioScenarioV2:
    descriptor: StudioScenarioDescriptorV2
    telemetry: RawTelemetryBatchV2


_SCENARIO_CONFIGS = (
    _ScenarioConfig(
        scenario_id=StudioScenarioIdV2.RESCUE_ROLE_REVERSAL,
        title="Rescue sequence",
        purpose=("Inspect a connected revive-and-escape sequence from sparse squad telemetry."),
        fixture_path=DATA_DIR / "raw_telemetry_v2.json",
    ),
    _ScenarioConfig(
        scenario_id=StudioScenarioIdV2.LANDING_RENDEZVOUS,
        title="Landing rendezvous",
        purpose=("Inspect a complete invited squad landing together at one named drop point."),
        fixture_path=EVALUATION_DIR / "landing_rendezvous.json",
    ),
    _ScenarioConfig(
        scenario_id=StudioScenarioIdV2.DUO_ASSIST,
        title="Duo assist",
        purpose=("Inspect a consent-safe assist followed by the teammate's elimination."),
        fixture_path=EVALUATION_DIR / "duo_assist.json",
    ),
    _ScenarioConfig(
        scenario_id=StudioScenarioIdV2.REPEATED_NEAR_MISS,
        title="Repeated near misses",
        purpose=("Inspect several squad matches with placements close to a stronger result."),
        fixture_path=EVALUATION_DIR / "repeated_near_miss.json",
    ),
    _ScenarioConfig(
        scenario_id=StudioScenarioIdV2.ORDINARY_SPARSE_TELEMETRY,
        title="Ordinary telemetry",
        purpose=("Inspect sparse squad activity without a strong connected event pattern."),
        fixture_path=EVALUATION_DIR / "ordinary_sparse_telemetry.json",
    ),
)


class StudioScenarioRegistryV2:
    """Load five exact fixtures and their evaluation-only labels from the manifest."""

    def __init__(self, *, preparer: TelemetryPreparerV2 | None = None) -> None:
        self.preparer = preparer or TelemetryPreparerV2()

    def catalog(self) -> StudioScenarioCatalogV2:
        return StudioScenarioCatalogV2(
            scenarios=[self.get(config.scenario_id).descriptor for config in _SCENARIO_CONFIGS]
        )

    def get(self, scenario_id: str | StudioScenarioIdV2) -> RegisteredStudioScenarioV2:
        try:
            typed_id = StudioScenarioIdV2(scenario_id)
        except ValueError as error:
            raise KeyError(str(scenario_id)) from error
        config = next(
            (item for item in _SCENARIO_CONFIGS if item.scenario_id == typed_id),
            None,
        )
        if config is None:
            raise KeyError(str(scenario_id))

        label = self._manifest_label(config)
        fixture_bytes = config.fixture_path.read_bytes()
        digest = sha256(fixture_bytes).hexdigest()
        telemetry = RawTelemetryBatchV2.model_validate_json(fixture_bytes)
        descriptor = StudioScenarioDescriptorV2(
            scenario_id=config.scenario_id,
            title=config.title,
            purpose=config.purpose,
            fixture_sha256=digest,
            fixture_revision=f"2.1:{digest[:12]}",
            expected_status=label["expected_status"],
            expected_mission_family=label["expected_mission_family"],
        )
        return RegisteredStudioScenarioV2(descriptor=descriptor, telemetry=telemetry)

    def prepare(self, scenario_id: str | StudioScenarioIdV2) -> StudioScenarioPreparationV2:
        registered = self.get(scenario_id)
        telemetry = registered.telemetry
        prepared = self.preparer.prepare(telemetry)
        normalized = prepared.normalized
        if normalized is None:
            raise RuntimeError("registered Studio fixture did not produce normalized telemetry")

        issue_codes = list(dict.fromkeys(issue.code for issue in prepared.issues))
        matches = [
            StudioScenarioMatchSummaryV2(
                match_id=match.match_id,
                game=match.game,
                mode=match.mode,
                map_name=match.map_name,
                started_at=match.started_at,
                placement=match.placement,
                event_count=len(match.events),
            )
            for match in normalized.matches
        ]
        memory_eligible_players = [
            player for player in normalized.players if player.memory_eligible
        ]
        invitation_eligible_players = [
            player
            for player in normalized.players
            if player.memory_eligible and player.invitation_eligible
        ]
        return StudioScenarioPreparationV2(
            scenario=registered.descriptor,
            status=(
                StudioScenarioPreparationStatusV2.REJECTED
                if prepared.issues or prepared.story_brief is None
                else StudioScenarioPreparationStatusV2.READY
            ),
            telemetry_summary=StudioScenarioTelemetrySummaryV2(
                request_id=normalized.request_id,
                target_player_id=normalized.target_player_id,
                match_count=len(normalized.matches),
                raw_event_count=sum(len(match.events) for match in telemetry.matches),
                consent_safe_player_count=len(memory_eligible_players),
                invitation_eligible_count=len(invitation_eligible_players),
                active_player_count=len(normalized.current_context.active_player_ids),
                matches=matches,
            ),
            normalization=StudioScenarioNormalizationSummaryV2(
                normalized_match_count=len(normalized.matches),
                normalized_event_count=sum(len(match.events) for match in normalized.matches),
                issue_codes=issue_codes,
            ),
            privacy=StudioScenarioPrivacySummaryV2(
                redaction_count=prepared.privacy_redaction_count,
                anonymous_player_count=sum(
                    not player.identity_visible for player in normalized.players
                ),
            ),
            eligible_windows=prepared.windows,
            mission_candidates=prepared.mission_candidates,
            mission_affordances=prepared.mission_affordances,
        )

    @staticmethod
    def _manifest_label(
        config: _ScenarioConfig,
    ) -> dict[str, InterpretDeliveryStatusV2 | MissionFamilyV2 | None]:
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            cases = manifest["cases"]
            case = next(item for item in cases if item["case_id"] == config.scenario_id.value)
            manifest_fixture = (MANIFEST_PATH.parent / case["fixture"]).resolve(strict=True)
            configured_fixture = config.fixture_path.resolve(strict=True)
            if manifest_fixture != configured_fixture:
                raise ValueError("manifest fixture does not match the registered Studio fixture")
            expected_status = InterpretDeliveryStatusV2(case["expected_status"])
            raw_family = case.get("expected_mission_family")
            expected_family = MissionFamilyV2(raw_family) if raw_family is not None else None
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"invalid offline evaluation label for {config.scenario_id.value}"
            ) from error
        return {
            "expected_status": expected_status,
            "expected_mission_family": expected_family,
        }


studio_scenario_registry_v2 = StudioScenarioRegistryV2()
