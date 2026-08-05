"""Focused adversarial checks for deterministic output validation."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_memory_stage_rejects_actions_outside_closed_grounded_vocabulary() -> None:
    pack, memory, _, _ = generated_artifacts()
    fabricated = memory.model_copy(
        update={"summary": "Lee healed Mei and shared ammunition with Mei."}
    )

    issues = ValidatorAgent().validate_memory_stage(pack, fabricated)

    assert "unsupported_action_claim" in issue_codes(issues)


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
