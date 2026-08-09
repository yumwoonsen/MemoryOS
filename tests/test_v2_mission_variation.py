"""Focused tests for deterministic, cooldown-aware mission-family rotation."""

from __future__ import annotations

from backend.models.v2_schemas import (
    MissionAffordanceV2,
    MissionFamilyV2,
    MissionSelectionReasonCodeV2,
)
from backend.services.v2_mission_variation import MissionVariationPolicyV2


def affordance(identifier: str, family: MissionFamilyV2) -> MissionAffordanceV2:
    return MissionAffordanceV2(
        affordance_id=identifier,
        family=family,
        window_id="window:grounded",
        source_event_ids=[f"event:{identifier}"],
        source_match_ids=["match:grounded"],
        source_context_ids=["context:reunion_eligible"],
        parameters={},
        objective_candidate_ids=[
            f"objective:{identifier}:participants",
            f"objective:{identifier}:complete",
        ],
        allowed_reason_codes=[
            MissionSelectionReasonCodeV2.DETERMINISTICALLY_VERIFIABLE
        ],
    )


def offered_affordances() -> list[MissionAffordanceV2]:
    return [
        affordance("affordance:reunion", MissionFamilyV2.REUNION),
        affordance("affordance:landing:alpha", MissionFamilyV2.LANDING_RENDEZVOUS),
        affordance("affordance:landing:beta", MissionFamilyV2.LANDING_RENDEZVOUS),
        affordance("affordance:assist", MissionFamilyV2.DUO_ASSIST),
        affordance("affordance:redemption", MissionFamilyV2.REDEMPTION),
    ]


def test_selection_is_reproducible_and_invariant_to_affordance_input_order() -> None:
    policy = MissionVariationPolicyV2()
    offered = offered_affordances()

    forward = policy.select(offered, seed="squad-47:generation-3")
    reversed_input = policy.select(
        list(reversed(offered)),
        seed="squad-47:generation-3",
    )

    assert forward == reversed_input
    assert forward.ranked_affordance_ids[0] == forward.selected_affordance_id
    assert set(forward.ranked_affordance_ids) == {
        item.affordance_id for item in offered
    }


def test_specialized_family_always_beats_available_reunion_fallback() -> None:
    decision = MissionVariationPolicyV2().select(
        [
            affordance("affordance:reunion", MissionFamilyV2.REUNION),
            affordance("affordance:assist", MissionFamilyV2.DUO_ASSIST),
        ],
        seed="specialized-first",
        recent_families=[MissionFamilyV2.DUO_ASSIST],
    )

    assert decision.selected_family == MissionFamilyV2.DUO_ASSIST
    assert decision.selected_affordance_id == "affordance:assist"


def test_recent_family_is_deferred_when_another_specialized_family_exists() -> None:
    policy = MissionVariationPolicyV2(recent_family_cooldown=2)
    offered = offered_affordances()
    previous = policy.select(offered, seed="rotation-seed")

    current = policy.select(
        offered,
        seed="rotation-seed",
        recent_families=[previous.selected_family],
    )

    assert current.selected_family != previous.selected_family
    assert previous.selected_family in current.deferred_recent_families
    assert current.selected_family != MissionFamilyV2.REUNION


def test_exhausted_specialized_bag_resets_without_falling_back_to_reunion() -> None:
    offered = offered_affordances()
    specialized = [
        MissionFamilyV2.LANDING_RENDEZVOUS,
        MissionFamilyV2.DUO_ASSIST,
        MissionFamilyV2.REDEMPTION,
    ]

    decision = MissionVariationPolicyV2(recent_family_cooldown=3).select(
        offered,
        seed="reset-seed",
        recent_families=specialized,
    )

    assert decision.selected_family in specialized
    assert decision.selected_family != MissionFamilyV2.REUNION
    assert decision.deferred_recent_families == ()


def test_selection_never_invents_an_unavailable_family() -> None:
    offered = [
        affordance("affordance:return", MissionFamilyV2.RETURN_TO_PLACE),
        affordance("affordance:role", MissionFamilyV2.ROLE_REVERSAL),
    ]
    available = {item.family for item in offered}

    for seed in range(25):
        decision = MissionVariationPolicyV2().select(
            offered,
            seed=seed,
            recent_families=[MissionFamilyV2.LANDING_RENDEZVOUS],
        )
        assert decision.selected_family in available
        assert decision.selected_affordance_id in {
            item.affordance_id for item in offered
        }


def test_reunion_is_selected_when_it_is_the_only_grounded_affordance() -> None:
    decision = MissionVariationPolicyV2().select(
        [affordance("affordance:reunion", MissionFamilyV2.REUNION)],
        seed="fallback",
    )

    assert decision.selected_family == MissionFamilyV2.REUNION
    assert decision.ranked_affordance_ids == ("affordance:reunion",)


def test_different_generation_seeds_exercise_multiple_specialized_families() -> None:
    policy = MissionVariationPolicyV2()
    selected = {
        policy.select(offered_affordances(), seed=f"generation:{index}").selected_family
        for index in range(24)
    }

    assert MissionFamilyV2.REUNION not in selected
    assert selected == {
        MissionFamilyV2.LANDING_RENDEZVOUS,
        MissionFamilyV2.DUO_ASSIST,
        MissionFamilyV2.REDEMPTION,
    }
