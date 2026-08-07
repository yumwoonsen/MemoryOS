"""Focused adversarial checks for deterministic output validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.agents.validator_agent import ValidatorAgent
from backend.models.schemas import MemoryPack, VerificationRule
from backend.pipeline import MemoryPipeline

DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


def load_confirmed_pack() -> MemoryPack:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    return MemoryPack.model_validate(payload)


def generated_artifacts():
    pack = load_confirmed_pack()
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None
    return pack, result.memory, result.player_perspectives, result.next_chapter


def issue_codes(issues) -> set[str]:
    return {issue.code for issue in issues}


def test_memory_stage_rejects_uncited_actions_and_unsupported_behavior() -> None:
    pack, memory, _, _ = generated_artifacts()
    fabricated = memory.model_copy(
        update={"summary": ("At Clock Tower, Lee eliminated Mei while Jo surrendered.")}
    )

    issues = ValidatorAgent().validate_memory_stage(pack, fabricated)

    assert {"event_action_mismatch", "unsupported_action_claim"} <= issue_codes(issues)


def test_memory_stage_rejects_unknown_people_emotion_and_intent() -> None:
    pack, memory, _, _ = generated_artifacts()
    fabricated = memory.model_copy(
        update={"summary": ("Zara knew Lee was terrified and deliberately betrayed the squad.")}
    )

    issues = ValidatorAgent().validate_memory_stage(pack, fabricated)

    assert {
        "unknown_player_claim",
        "unsupported_emotional_claim",
        "unsupported_action_claim",
    } <= issue_codes(issues)


def test_memory_stage_accepts_known_player_after_temporal_connector() -> None:
    pack, memory, _, _ = generated_artifacts()
    grounded = memory.model_copy(
        update={"summary": "After Amir called for retreat, Mei revived Lee at Clock Tower."}
    )

    issues = ValidatorAgent().validate_memory_stage(pack, grounded)

    assert issues == []


def test_memory_stage_keeps_later_clause_subject_out_of_revive_target() -> None:
    pack, memory, _, _ = generated_artifacts()
    grounded = memory.model_copy(
        update={
            "summary": (
                "Lee survived the final zone after Mei revived him and Jo escaped the vehicle, "
                "while Amir called for retreat three times."
            )
        }
    )

    issues = ValidatorAgent().validate_memory_stage(pack, grounded)

    assert issues == []


def test_memory_stage_rejects_actions_outside_closed_grounded_vocabulary() -> None:
    pack, memory, _, _ = generated_artifacts()
    fabricated = memory.model_copy(
        update={"summary": "Lee healed Mei and shared ammunition with Mei."}
    )

    issues = ValidatorAgent().validate_memory_stage(pack, fabricated)

    assert "unsupported_action_claim" in issue_codes(issues)


def test_memory_stage_rejects_generic_summary_without_cited_detail() -> None:
    pack, memory, _, _ = generated_artifacts()
    generic = memory.model_copy(update={"summary": "A grounded memory selected for the squad."})

    issues = ValidatorAgent().validate_memory_stage(pack, generic)

    assert "memory_summary_missing_evidence_anchor" in issue_codes(issues)


def test_memory_stage_rejects_unverified_player_state_and_relationship() -> None:
    pack, memory, _, _ = generated_artifacts()
    fabricated = memory.model_copy(
        update={"summary": "Lee was ecstatic and trusted Mei completely."}
    )

    issues = ValidatorAgent().validate_memory_stage(pack, fabricated)

    assert {
        "unsupported_emotional_claim",
        "unsupported_action_claim",
    } <= issue_codes(issues)


def test_memory_stage_rejects_confirmation_state_mismatch() -> None:
    pack, memory, _, _ = generated_artifacts()
    mismatched = memory.model_copy(update={"human_confirmed": False})

    issues = ValidatorAgent().validate_memory_stage(pack, mismatched)

    assert "confirmation_state_mismatch" in issue_codes(issues)


def test_perspective_stage_is_a_fail_closed_boundary() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    malformed = perspectives[0].model_copy(
        update={"message": "Lee knew Zara was terrified at Imaginary Harbor."}
    )
    validator = ValidatorAgent()

    issues = validator.validate_perspective_stage(
        pack,
        memory,
        [malformed, *perspectives[1:]],
    )
    report = validator.stage_failure_report(issues)

    assert report.passed is False
    assert report.human_review_required is True
    assert {
        "unknown_player_claim",
        "unsupported_emotional_claim",
        "unsupported_location_claim",
    } <= issue_codes(report.issues)


def test_perspective_action_is_bound_to_owner_and_its_own_citation() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    lee = next(item for item in perspectives if item.player_id == "lee")
    survival_event_id = next(
        event.event_id for event in pack.match_events if event.type == "final_zone_survival"
    )
    wrong = lee.model_copy(
        update={
            "message": "You revived Lee at Clock Tower.",
            "evidence_event_ids": [survival_event_id],
        }
    )

    issues = ValidatorAgent().validate_perspective_stage(
        pack,
        memory,
        [wrong, *(item for item in perspectives if item.player_id != "lee")],
    )

    assert "event_action_mismatch" in issue_codes(issues)


def test_perspective_stage_rejects_generic_or_third_person_model_text() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    generic_messages = [
        "This is your selected memory.",
        "A grounded memory for the player.",
        "Your verified moment is ready.",
        "The selected memory remains available.",
    ]
    generic = [
        perspective.model_copy(update={"message": message})
        for perspective, message in zip(perspectives, generic_messages, strict=True)
    ]

    issues = ValidatorAgent().validate_perspective_stage(pack, memory, generic)

    assert {
        "perspective_not_second_person",
        "perspective_missing_evidence_anchor",
    } <= issue_codes(issues)


def test_perspective_stage_does_not_treat_quoted_you_as_direct_address() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    lee = next(item for item in perspectives if item.player_id == "lee")
    third_person = lee.model_copy(
        update={"message": 'Mei revived Lee at Clock Tower; the caption says "you were there".'}
    )

    issues = ValidatorAgent().validate_perspective_stage(
        pack,
        memory,
        [third_person, *(item for item in perspectives if item.player_id != "lee")],
    )

    assert "perspective_not_second_person" in issue_codes(issues)


def test_perspective_stage_accepts_grounded_second_person_paraphrases() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    messages = {
        "lee": "At Clock Tower, Mei's verified revive brought you back into the match.",
        "mei": "Your revive of Lee at Clock Tower is the event this perspective follows.",
        "jo": "Your drive out of Clock Tower with 3 passengers anchors the getaway.",
        "amir": "Your retreat call at Clock Tower is the cited event in this memory.",
    }
    paraphrased = [
        perspective.model_copy(update={"message": messages[perspective.player_id]})
        for perspective in perspectives
    ]

    issues = ValidatorAgent().validate_perspective_stage(pack, memory, paraphrased)

    assert issues == []


def test_perspective_may_use_verified_shared_memory_as_secondary_context() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    amir = next(item for item in perspectives if item.player_id == "amir")
    contextualized = amir.model_copy(
        update={
            "message": (
                "After Mei revived Lee, your retreat call led into the verified escape "
                "at Clock Tower."
            )
        }
    )
    updated = [contextualized if item.player_id == "amir" else item for item in perspectives]

    issues = ValidatorAgent().validate_perspective_stage(pack, memory, updated)

    assert issues == []


def test_perspective_accepts_grounded_retreat_ping_wording() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    amir = next(item for item in perspectives if item.player_id == "amir")
    pinged = amir.model_copy(update={"message": "You pinged for retreat 3 times from Clock Tower."})
    updated = [pinged if item.player_id == "amir" else item for item in perspectives]

    issues = ValidatorAgent().validate_perspective_stage(pack, memory, updated)

    assert issues == []


def test_perspective_accepts_grounded_ping_after_connector() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    amir = next(item for item in perspectives if item.player_id == "amir")
    pinged = amir.model_copy(
        update={
            "message": (
                "You called for retreat at Clock Tower and then pinged for retreat 3 times."
            )
        }
    )
    updated = [pinged if item.player_id == "amir" else item for item in perspectives]

    issues = ValidatorAgent().validate_perspective_stage(pack, memory, updated)

    assert issues == []


def test_perspective_rejects_inferred_help_after_grounded_retreat_ping() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    amir = next(item for item in perspectives if item.player_id == "amir")
    inferred = amir.model_copy(
        update={
            "message": (
                "You pinged for retreat 3 times and then helped the squad escape from Clock Tower."
            )
        }
    )
    updated = [inferred if item.player_id == "amir" else item for item in perspectives]

    issues = ValidatorAgent().validate_perspective_stage(pack, memory, updated)

    assert "unsupported_action_claim" in issue_codes(issues)


def test_perspective_binds_coordinated_action_to_the_same_player() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    amir = next(item for item in perspectives if item.player_id == "amir")
    wrong_driver = amir.model_copy(
        update={
            "message": (
                "You called for retreat 3 times and drove the squad out of Clock Tower "
                "with 3 passengers."
            )
        }
    )
    updated = [wrong_driver if item.player_id == "amir" else item for item in perspectives]

    issues = ValidatorAgent().validate_perspective_stage(pack, memory, updated)

    assert "event_action_mismatch" in issue_codes(issues)


def test_perspective_accepts_explicit_shared_action_actor() -> None:
    pack, memory, perspectives, _ = generated_artifacts()
    amir = next(item for item in perspectives if item.player_id == "amir")
    grounded = amir.model_copy(
        update={
            "message": (
                "You called for retreat 3 times before Jo drove the squad out of "
                "Clock Tower with 3 passengers."
            )
        }
    )
    updated = [grounded if item.player_id == "amir" else item for item in perspectives]

    issues = ValidatorAgent().validate_perspective_stage(pack, memory, updated)

    assert issues == []


def test_quest_rejects_unknown_roster_targets() -> None:
    pack, memory, _, quest = generated_artifacts()
    bad_quest = quest.model_copy(deep=True)
    objective = bad_quest.objectives[0]
    bad_quest.objectives[0] = objective.model_copy(
        update={
            "verification": VerificationRule(
                metric="squad_member_ids",
                operator="contains_all",
                target=["lee", "mei", "jo", "unknown-player"],
            )
        }
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, bad_quest)

    assert {"invalid_quest_target", "unsupported_verification_rule"} <= issue_codes(issues)


def test_quest_rejects_newly_opted_out_targets_and_assignees() -> None:
    pack, memory, _, quest = generated_artifacts()
    private_payload = pack.model_dump(mode="json")
    for member in private_payload["squad"]["members"]:
        if member["player_id"] == "jo":
            member["opted_in"] = False
    private_pack = MemoryPack.model_validate(private_payload)

    issues = ValidatorAgent().validate_quest_stage(private_pack, memory, quest)

    assert {"invalid_quest_target", "invalid_quest_assignee"} <= issue_codes(issues)


def test_quest_rejects_wrong_metric_actor_count_location_and_action() -> None:
    pack, memory, _, quest = generated_artifacts()
    bad_quest = quest.model_copy(deep=True)
    objective_index = next(
        index
        for index, objective in enumerate(bad_quest.objectives)
        if objective.verification.metric.startswith("vehicle_escape.")
    )
    objective = bad_quest.objectives[objective_index]
    bad_quest.objectives[objective_index] = objective.model_copy(
        update={
            "description": (
                "Lee drives 99 teammates through Imaginary Harbor after an elimination."
            ),
            "assigned_player_id": "lee",
            "verification": VerificationRule(
                metric="vehicle_escape.lee.passengers",
                operator="at_least",
                target=3,
            ),
        }
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, bad_quest)

    assert {
        "unsupported_verification_rule",
        "unsupported_numeric_claim",
        "unsupported_location_claim",
        "event_action_mismatch",
    } <= issue_codes(issues)


def test_quest_rejects_wrong_operator_event_type_and_unknown_metric() -> None:
    pack, memory, _, quest = generated_artifacts()
    bad_quest = quest.model_copy(deep=True)
    revive_index = next(
        index
        for index, objective in enumerate(bad_quest.objectives)
        if objective.verification.metric.startswith("revives.")
    )
    revive = bad_quest.objectives[revive_index]
    escape_event_id = next(
        item.event_id for item in memory.evidence if item.event_type == "vehicle_escape"
    )
    bad_quest.objectives[revive_index] = revive.model_copy(
        update={
            "verification": VerificationRule(
                metric="revives.lee.targets",
                operator="equals",
                target=["mei"],
            ),
            "source_event_ids": [escape_event_id],
        }
    )
    first = bad_quest.objectives[0]
    bad_quest.objectives[0] = first.model_copy(
        update={
            "verification": VerificationRule(
                metric="invented.quest.metric",
                operator="equals",
                target=True,
            )
        }
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, bad_quest)

    assert "unsupported_verification_rule" in issue_codes(issues)
    assert sum(issue.code == "unsupported_verification_rule" for issue in issues) >= 2


def test_quest_description_must_match_its_verification_rule() -> None:
    pack, memory, _, quest = generated_artifacts()
    bad_quest = quest.model_copy(deep=True)
    location_index = next(
        index
        for index, objective in enumerate(bad_quest.objectives)
        if objective.verification.metric == "visited_locations"
    )
    objective = bad_quest.objectives[location_index]
    bad_quest.objectives[location_index] = objective.model_copy(
        update={"description": "Lee revives Mei at Clock Tower."}
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, bad_quest)

    assert "quest_description_rule_mismatch" in issue_codes(issues)


def test_quest_descriptions_reject_negated_or_excluded_requirements() -> None:
    pack, memory, _, quest = generated_artifacts()
    roster = {member.player_id: member.display_name for member in pack.squad.members}
    objectives = {objective.objective_id: objective for objective in quest.objectives}
    location = objectives["return-to-location"].verification.target[0]
    route = objectives["caller-chooses-route"]
    route_caller = route.verification.target
    adversarial_descriptions = {
        "reassemble-original-squad": ("Complete a match without the original squad members."),
        "return-to-location": f"Do not return to {location} during the new match.",
        "caller-chooses-route": (
            f"{roster[route_caller]} chooses any rotation route except the first."
        ),
    }

    for objective_id, description in adversarial_descriptions.items():
        bad_quest = quest.model_copy(deep=True)
        index = next(
            index
            for index, objective in enumerate(bad_quest.objectives)
            if objective.objective_id == objective_id
        )
        bad_quest.objectives[index] = bad_quest.objectives[index].model_copy(
            update={"description": description}
        )

        issues = ValidatorAgent().validate_quest_stage(pack, memory, bad_quest)

        assert "quest_description_rule_mismatch" in issue_codes(issues), objective_id


@pytest.mark.parametrize(
    "ending",
    [
        "zero times.",
        "no times.",
        "once, but it never counts.",
    ],
)
def test_quest_description_rejects_zeroed_revive_instruction(ending: str) -> None:
    pack, memory, _, quest = generated_artifacts()
    roster = {member.player_id: member.display_name for member in pack.squad.members}
    index = next(
        index
        for index, objective in enumerate(quest.objectives)
        if objective.verification.metric.startswith("revives.")
    )
    objective = quest.objectives[index]
    actor_id = objective.verification.metric.split(".")[1]
    target_id = objective.verification.target[0]
    bad_quest = quest.model_copy(deep=True)
    bad_quest.objectives[index] = objective.model_copy(
        update={"description": (f"{roster[actor_id]} revives {roster[target_id]} {ending}")}
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, bad_quest)

    assert "quest_description_rule_mismatch" in issue_codes(issues)


def test_quest_description_binds_revive_actor_and_target_roles() -> None:
    pack, memory, _, quest = generated_artifacts()
    roster = {member.player_id: member.display_name for member in pack.squad.members}
    index = next(
        index
        for index, objective in enumerate(quest.objectives)
        if objective.verification.metric.startswith("revives.")
    )
    objective = quest.objectives[index]
    actor_id = objective.verification.metric.split(".")[1]
    target_id = objective.verification.target[0]
    reversed_descriptions = (
        f"{roster[target_id]} revives {roster[actor_id]}.",
        f"{roster[actor_id]} is rescued by {roster[target_id]}.",
    )

    for description in reversed_descriptions:
        bad_quest = quest.model_copy(deep=True)
        bad_quest.objectives[index] = objective.model_copy(update={"description": description})

        issues = ValidatorAgent().validate_quest_stage(pack, memory, bad_quest)

        assert "quest_description_rule_mismatch" in issue_codes(issues), description


def test_quest_description_allows_passive_revive_roles() -> None:
    pack, memory, _, quest = generated_artifacts()
    roster = {member.player_id: member.display_name for member in pack.squad.members}
    index = next(
        index
        for index, objective in enumerate(quest.objectives)
        if objective.verification.metric.startswith("revives.")
    )
    objective = quest.objectives[index]
    actor_id = objective.verification.metric.split(".")[1]
    target_id = objective.verification.target[0]
    passive_quest = quest.model_copy(deep=True)
    passive_quest.objectives[index] = objective.model_copy(
        update={
            "description": (
                f"{roster[target_id]} is rescued by {roster[actor_id]} in the new match."
            )
        }
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, passive_quest)

    assert "quest_description_rule_mismatch" not in issue_codes(issues)


def test_quest_description_rejects_upper_bound_for_at_least_rule() -> None:
    pack, memory, _, quest = generated_artifacts()
    bad_quest = quest.model_copy(deep=True)
    index = next(
        index
        for index, objective in enumerate(bad_quest.objectives)
        if objective.verification.metric.startswith("vehicle_escape.")
    )
    objective = bad_quest.objectives[index]
    driver_id = objective.verification.metric.split(".")[1]
    driver_name = next(
        member.display_name for member in pack.squad.members if member.player_id == driver_id
    )
    bad_quest.objectives[index] = objective.model_copy(
        update={
            "description": (
                f"{driver_name} drives at most {objective.verification.target} teammates "
                "out of danger."
            )
        }
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, bad_quest)

    assert "quest_description_rule_mismatch" in issue_codes(issues)


def test_quest_description_allows_equivalent_natural_paraphrases() -> None:
    pack, memory, _, quest = generated_artifacts()
    roster = {member.player_id: member.display_name for member in pack.squad.members}
    descriptions: dict[str, str] = {}
    for objective in quest.objectives:
        metric = objective.verification.metric
        if metric == "squad_member_ids":
            descriptions[objective.objective_id] = (
                "Reunite the entire original squad for one match."
            )
        elif metric == "visited_locations":
            descriptions[objective.objective_id] = (
                f"Visit {objective.verification.target[0]} again in the new match."
            )
        elif metric.startswith("revives."):
            actor_id = metric.split(".")[1]
            target_id = objective.verification.target[0]
            descriptions[objective.objective_id] = (
                f"{roster[actor_id]} rescues {roster[target_id]} without hesitation."
            )
        elif metric.startswith("vehicle_escape."):
            driver_id = metric.split(".")[1]
            descriptions[objective.objective_id] = (
                f"{roster[driver_id]} drives no fewer than "
                f"{objective.verification.target} teammates to safety."
            )
        elif metric == "initial_route_caller_id":
            descriptions[objective.objective_id] = (
                f"{roster[objective.verification.target]} calls the opening rotation route."
            )

    paraphrased = quest.model_copy(
        update={
            "objectives": [
                objective.model_copy(update={"description": descriptions[objective.objective_id]})
                for objective in quest.objectives
            ]
        }
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, paraphrased)

    assert "quest_description_rule_mismatch" not in issue_codes(issues)


def test_quest_stage_accepts_grounded_model_style_paraphrases() -> None:
    pack, memory, _, quest = generated_artifacts()
    descriptions = {
        "reassemble-original-squad": "Gather Lee, Mei, Jo, and Amir together in one match.",
        "return-to-location": "Visit Clock Tower during the new match.",
        "return-the-favour": "Lee revives Mei in the new match.",
        "driver-seat-open": (
            "Jo takes a vehicle out of Clock Tower with at least three teammates."
        ),
        "caller-chooses-route": "Amir selects the squad's first rotation route.",
    }
    paraphrased = quest.model_copy(
        update={
            "objectives": [
                objective.model_copy(update={"description": descriptions[objective.objective_id]})
                for objective in quest.objectives
            ]
        }
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, paraphrased)

    assert issues == []


def test_aggregate_quest_rule_rejects_unverifiable_unsafe_player_action() -> None:
    pack, memory, _, quest = generated_artifacts()
    bad_quest = quest.model_copy(deep=True)
    objective = bad_quest.objectives[0]
    bad_quest.objectives[0] = objective.model_copy(
        update={"description": "Complete a squad match where Lee shares a password with Mei."}
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, bad_quest)

    assert {
        "quest_description_rule_mismatch",
        "unsupported_action_claim",
    } <= issue_codes(issues)


def test_valid_deterministic_artifacts_pass_all_stage_boundaries() -> None:
    pack, memory, perspectives, quest = generated_artifacts()
    validator = ValidatorAgent()

    assert validator.validate_memory_stage(pack, memory) == []
    assert validator.validate_perspective_stage(pack, memory, perspectives) == []
    assert validator.validate_quest_stage(pack, memory, quest) == []


def test_quest_requires_one_required_squad_reunion_objective() -> None:
    pack, memory, _, quest = generated_artifacts()
    participant_index = next(
        index
        for index, objective in enumerate(quest.objectives)
        if objective.verification.metric == "squad_member_ids"
    )
    participant = quest.objectives[participant_index]
    remaining = [
        objective for index, objective in enumerate(quest.objectives) if index != participant_index
    ]
    without_participants = quest.model_copy(update={"objectives": remaining})
    optional_participants = quest.model_copy(
        update={
            "objectives": [
                participant.model_copy(update={"required": False}),
                *remaining,
            ]
        }
    )

    missing_codes = issue_codes(
        ValidatorAgent().validate_quest_stage(pack, memory, without_participants)
    )
    optional_codes = issue_codes(
        ValidatorAgent().validate_quest_stage(pack, memory, optional_participants)
    )

    assert "invalid_participant_objective_count" in missing_codes
    assert "participant_objective_must_be_required" in optional_codes


@pytest.mark.parametrize(
    "unsafe_mission",
    [
        "Lose on purpose, then reunite the squad.",
        "Do not hesitate; deliberately lose.",
        "Avoid enemies, then use friendly fire.",
    ],
)
def test_validator_rejects_unsafe_quest_instructions(unsafe_mission: str) -> None:
    pack, memory, _, quest = generated_artifacts()
    unsafe_quest = quest.model_copy(update={"mission": unsafe_mission})

    issues = ValidatorAgent().validate_quest_stage(pack, memory, unsafe_quest)

    assert "unsafe_quest_instruction" in issue_codes(issues)


def test_validator_allows_quest_language_that_prevents_harm() -> None:
    pack, memory, _, quest = generated_artifacts()
    safe_quest = quest.model_copy(
        update={"mission": "Reassemble the squad while avoiding friendly fire."}
    )

    issues = ValidatorAgent().validate_quest_stage(pack, memory, safe_quest)

    assert "unsafe_quest_instruction" not in issue_codes(issues)
