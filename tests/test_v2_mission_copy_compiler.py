"""Focused tests for deterministic mission objective copy compilation."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from backend.models.schemas import QuestRecipe
from backend.models.v2_schemas import (
    MissionAffordanceV2,
    MissionCapabilityCandidate,
    MissionFamilyV2,
    MissionSelectionReasonCodeV2,
)
from backend.services.v2_mission_copy_compiler import (
    MissionCopyCompilationError,
    compile_mission_objective_descriptions,
)

WINDOW_ID = "window:hero"
EVENT_ID = "event:hero"
SAFE_NAMES = {"player:lee": "Lee", "player:mei": "Mei"}


def candidate(
    candidate_id: str,
    metric: str,
    operator: str,
    target: str | int | bool | list[str],
    *,
    assigned_player_id: str | None = None,
) -> MissionCapabilityCandidate:
    return MissionCapabilityCandidate.model_validate(
        {
            "candidate_id": candidate_id,
            "window_id": WINDOW_ID,
            "recipe": QuestRecipe.REMIX,
            "assigned_player_id": assigned_player_id,
            "source_event_ids": [EVENT_ID],
            "verification": {
                "metric": metric,
                "operator": operator,
                "target": target,
            },
        }
    )


def affordance(candidates: Sequence[MissionCapabilityCandidate]) -> MissionAffordanceV2:
    return MissionAffordanceV2(
        affordance_id="affordance:hero",
        family=MissionFamilyV2.ROLE_REVERSAL,
        window_id=WINDOW_ID,
        source_event_ids=[EVENT_ID],
        source_match_ids=["match:hero"],
        parameters={},
        objective_candidate_ids=[item.candidate_id for item in candidates],
        allowed_reason_codes=[
            MissionSelectionReasonCodeV2.DETERMINISTICALLY_VERIFIABLE,
        ],
    )


def test_compiles_all_supported_rules_in_affordance_order() -> None:
    candidates = [
        candidate(
            "objective:participants",
            "squad.participant_ids",
            "contains_all",
            ["player:lee", "player:mei"],
        ),
        candidate("objective:matches", "squad.matches_completed", "at_least", 2),
        candidate(
            "objective:first-revive",
            "match.first_squad_revive_actor_id",
            "equals",
            "player:lee",
            assigned_player_id="player:lee",
        ),
        candidate("objective:top-three", "match.top_three_reached", "equals", True),
    ]

    descriptions = compile_mission_objective_descriptions(
        affordance(candidates), candidates, SAFE_NAMES
    )

    assert list(descriptions) == [item.candidate_id for item in candidates]
    assert descriptions == {
        "objective:participants": "Play a match with the invited squad.",
        "objective:matches": "Complete at least 2 matches.",
        "objective:first-revive": "Lee completes the squad's first revive.",
        "objective:top-three": "Reach the top 3 in the new match.",
    }


def test_compiles_singular_match_copy() -> None:
    candidates = [
        candidate("objective:matches", "squad.matches_completed", "at_least", 1),
    ]

    descriptions = compile_mission_objective_descriptions(
        affordance(candidates), candidates, SAFE_NAMES
    )

    assert descriptions["objective:matches"] == "Complete at least 1 match."


@pytest.mark.parametrize(
    ("invalid_candidate", "safe_names"),
    [
        (
            candidate("objective:unsupported", "squad.kill_count", "at_least", 1),
            SAFE_NAMES,
        ),
        (
            candidate("objective:matches", "squad.matches_completed", "equals", 1),
            SAFE_NAMES,
        ),
        (
            candidate("objective:matches", "squad.matches_completed", "at_least", 0),
            SAFE_NAMES,
        ),
        (
            candidate(
                "objective:first-revive",
                "match.first_squad_revive_actor_id",
                "equals",
                "player:lee",
                assigned_player_id="player:mei",
            ),
            SAFE_NAMES,
        ),
        (
            candidate(
                "objective:first-revive",
                "match.first_squad_revive_actor_id",
                "equals",
                "player:lee",
                assigned_player_id="player:lee",
            ),
            {"player:mei": "Mei"},
        ),
        (
            candidate("objective:top-three", "match.top_three_reached", "equals", False),
            SAFE_NAMES,
        ),
    ],
)
def test_fails_closed_for_unsupported_or_inconsistent_rules(
    invalid_candidate: MissionCapabilityCandidate,
    safe_names: dict[str, str],
) -> None:
    with pytest.raises(MissionCopyCompilationError):
        compile_mission_objective_descriptions(
            affordance([invalid_candidate]),
            [invalid_candidate],
            safe_names,
        )


def test_fails_closed_when_candidates_do_not_match_affordance_order() -> None:
    participants = candidate(
        "objective:participants",
        "squad.participant_ids",
        "contains_all",
        ["player:lee", "player:mei"],
    )
    matches = candidate("objective:matches", "squad.matches_completed", "at_least", 1)
    selected_affordance = affordance([participants, matches])

    with pytest.raises(MissionCopyCompilationError, match="objective order"):
        compile_mission_objective_descriptions(
            selected_affordance,
            [matches, participants],
            SAFE_NAMES,
        )


def test_fails_closed_when_candidate_belongs_to_another_window() -> None:
    matches = candidate("objective:matches", "squad.matches_completed", "at_least", 1)
    other_window = matches.model_copy(update={"window_id": "window:other"})

    with pytest.raises(MissionCopyCompilationError, match="different event window"):
        compile_mission_objective_descriptions(
            affordance([matches]),
            [other_window],
            SAFE_NAMES,
        )
