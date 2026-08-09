"""Contract tests for the unified, consent-consistent synthetic squad history."""

from __future__ import annotations

import json
from pathlib import Path

from backend.models.v2_schemas import MissionFamilyV2, RawTelemetryBatchV2
from backend.services.v2_preparation import TelemetryPreparerV2

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "data"
    / "v2_evaluation"
    / "unified_squad_history.json"
)


def unified_batch() -> RawTelemetryBatchV2:
    return RawTelemetryBatchV2.model_validate(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def test_fixture_uses_one_invitation_safe_roster_for_the_entire_history() -> None:
    batch = unified_batch()

    assert [player.player_id for player in batch.squad.players] == [
        "ff-player-lee",
        "ff-player-mei",
        "ff-player-amir",
        "ff-player-jo",
    ]
    assert all(player.consent.memory_appearance for player in batch.squad.players)
    assert all(player.consent.identity_display for player in batch.squad.players)
    assert all(player.consent.mission_invitation for player in batch.squad.players)
    assert batch.media_references == []


def test_rich_match_is_one_coherent_pochinok_payback_episode() -> None:
    batch = unified_batch()
    match = next(item for item in batch.matches if item.match_id == "ff-unified-pochinok-01")
    events = match.events

    assert [event.provider_event_type for event in events] == [
        "SQUAD_MEMBER_LANDED",
        "SQUAD_MEMBER_LANDED",
        "SQUAD_MEMBER_LANDED",
        "SQUAD_MEMBER_LANDED",
        "PLAYER_KNOCKED",
        "TEAMMATE_REVIVED",
        "KILL_ASSIST",
        "PLAYER_ELIMINATED_OPPONENT",
        "SQUAD_ENTERED_VEHICLE",
        "SQUAD_EXITED_DAMAGE_ZONE",
    ]
    assert {event.location for event in events} == {"Pochinok"}
    assert events == sorted(events, key=lambda event: event.timestamp_seconds)

    revive = next(event for event in events if event.provider_event_type == "TEAMMATE_REVIVED")
    assist = next(event for event in events if event.provider_event_type == "KILL_ASSIST")
    elimination = next(
        event for event in events if event.provider_event_type == "PLAYER_ELIMINATED_OPPONENT"
    )
    vehicle_entry = next(
        event for event in events if event.provider_event_type == "SQUAD_ENTERED_VEHICLE"
    )
    zone_escape = next(
        event for event in events if event.provider_event_type == "SQUAD_EXITED_DAMAGE_ZONE"
    )
    assert (revive.actor_id, revive.target_id) == ("ff-player-mei", "ff-player-lee")
    assert (assist.actor_id, assist.target_id) == ("ff-player-lee", "ff-player-mei")
    assert elimination.actor_id == "ff-player-mei"
    assert 0 < elimination.timestamp_seconds - revive.timestamp_seconds <= 60
    assert elimination.timestamp_seconds - assist.timestamp_seconds <= 30
    assert vehicle_entry.details["squad_members_aboard"] == 4
    assert zone_escape.details["squad_members_alive"] == 4
    assert elimination.timestamp_seconds < vehicle_entry.timestamp_seconds


def test_preparation_exposes_every_grounded_family_from_the_unified_history() -> None:
    prepared = TelemetryPreparerV2().prepare(unified_batch())

    assert prepared.issues == []
    assert prepared.story_brief is not None
    assert {
        MissionFamilyV2.REUNION,
        MissionFamilyV2.ROLE_REVERSAL,
        MissionFamilyV2.REDEMPTION,
        MissionFamilyV2.RETURN_TO_PLACE,
        MissionFamilyV2.LANDING_RENDEZVOUS,
        MissionFamilyV2.DUO_ASSIST,
    }.issubset({affordance.family for affordance in prepared.mission_affordances})

    rich_window = next(
        window for window in prepared.windows if window.match_id == "ff-unified-pochinok-01"
    )
    assert len(rich_window.event_ids) == 10
    assert set(rich_window.participant_ids) == {
        "ff-player-lee",
        "ff-player-mei",
        "ff-player-amir",
        "ff-player-jo",
    }


def test_rich_window_can_compile_a_five_step_grounded_chapter() -> None:
    prepared = TelemetryPreparerV2().prepare(unified_batch())
    candidate_by_id = {
        candidate.candidate_id: candidate for candidate in prepared.mission_candidates
    }
    rich = next(
        affordance
        for affordance in prepared.mission_affordances
        if affordance.window_id.startswith("window:ff-unified-pochinok-01")
        and affordance.family == MissionFamilyV2.LANDING_RENDEZVOUS
    )
    metrics = [
        candidate_by_id[candidate_id].verification.metric
        for candidate_id in rich.objective_candidate_ids
    ]

    assert len(rich.objective_candidate_ids) == 5
    assert metrics == [
        "squad.participant_ids",
        "match.invited_squad_lands_at_location",
        "match.first_squad_revive_actor_id",
        "match.assigned_player_assisted_elimination_player_ids",
        "squad.matches_completed",
    ]
    assert rich.parameters["landing_location"] == "Pochinok"
    assert rich.parameters["assister_player_id"] == "ff-player-lee"
    assert rich.parameters["elimination_player_id"] == "ff-player-mei"


def test_repeated_near_misses_ground_redemption_across_both_matches() -> None:
    prepared = TelemetryPreparerV2().prepare(unified_batch())
    redemption = next(
        affordance
        for affordance in prepared.mission_affordances
        if affordance.family == MissionFamilyV2.REDEMPTION
    )

    assert set(redemption.source_match_ids) == {
        "ff-unified-pochinok-01",
        "ff-unified-near-miss-02",
    }
    assert redemption.parameters["source_placements"] == ["5", "4"]
    assert redemption.parameters["target_placement_max"] == 3
