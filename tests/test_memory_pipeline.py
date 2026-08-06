"""Golden-path and safety tests for the Phase 1 pipeline."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.agents.validator_agent import ValidatorAgent
from backend.models.schemas import (
    EvidenceRef,
    MemoryPack,
    MemoryRecord,
    NextChapter,
    PerspectiveSet,
    PipelineStatus,
)
from backend.pipeline import MemoryPipeline, build_pipeline

DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


def load_pack(filename: str) -> MemoryPack:
    payload = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
    return MemoryPack.model_validate(payload)


def test_confirmed_funny_memory_completes_the_pipeline() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert result.memory is not None
    assert result.memory.title == "Worst Plan, Best Night"
    assert result.next_chapter is not None
    assert result.validation.passed is True
    assert result.validation.human_review_required is False
    assert {item.player_id for item in result.player_perspectives} == {
        "lee",
        "mei",
        "jo",
        "amir",
    }
    assert len({item.message for item in result.player_perspectives}) == 4


def test_all_generated_references_are_grounded_in_input_events() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    input_event_ids = {event.event_id for event in pack.match_events}
    generated_event_ids = {item.event_id for item in result.memory.evidence}
    generated_event_ids.update(
        event_id
        for perspective in result.player_perspectives
        for event_id in perspective.evidence_event_ids
    )
    generated_event_ids.update(
        event_id
        for objective in result.next_chapter.objectives
        for event_id in objective.source_event_ids
    )

    assert generated_event_ids <= input_event_ids
    assert result.validation.scores.evidence_grounding == 1.0
    assert result.validation.scores.quest_connection > 0


def test_strong_unconfirmed_candidate_requires_human_review() -> None:
    pack = load_pack("comeback_memory.json")
    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.NEEDS_HUMAN_CONFIRMATION
    assert result.memory is not None
    assert result.memory.human_confirmed is False
    assert result.validation.passed is True
    assert result.validation.human_review_required is True
    assert "human_confirmation_required" in {issue.code for issue in result.validation.issues}


def test_weak_memory_abstains_without_generating_content() -> None:
    pack = load_pack("insufficient_memory.json")
    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.REJECTED
    assert result.discovery.eligible is False
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert result.validation.passed is True
    assert result.validation.issues[0].code == "insufficient_memory_signal"


def test_unknown_players_are_rejected_at_the_input_boundary() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["match_events"][0]["actor_id"] = "not-a-squad-member"

    with pytest.raises(ValidationError, match="unknown squad players"):
        MemoryPack.model_validate(payload)


def test_validator_rejects_invented_evidence() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    invented_memory = result.memory.model_copy(
        update={
            "evidence": [
                EvidenceRef(
                    event_id="evt-invented",
                    event_type="friendship_power",
                    significance="An event that never occurred",
                )
            ]
        }
    )
    report = ValidatorAgent().validate(
        pack,
        invented_memory,
        result.player_perspectives,
        result.next_chapter,
    )

    assert report.passed is False
    assert "ungrounded_memory_evidence" in {issue.code for issue in report.issues}


def test_validator_rejects_unsupported_relationship_claims() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    unsupported_memory = result.memory.model_copy(
        update={"summary": "Mei proved she is Lee's best friend."}
    )
    report = ValidatorAgent().validate(
        pack,
        unsupported_memory,
        result.player_perspectives,
        result.next_chapter,
    )

    assert report.passed is False
    assert "unsupported_relationship_claim" in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    "caption",
    ["Best friend clutch", "Best friend " + ("x" * 108)],
)
def test_attributed_player_caption_can_contain_relationship_context(caption: str) -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["human_memory"]["caption"] = caption
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert "unsupported_relationship_claim" not in {
        issue.code for issue in result.validation.issues
    }


def test_player_caption_does_not_whitelist_independent_model_claims() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["human_memory"]["caption"] = "Best friend"
    pack = MemoryPack.model_validate(payload)
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    unsupported_memory = result.memory.model_copy(
        update={"summary": "Lee and Mei are best friend forever."}
    )
    report = ValidatorAgent().validate(
        pack,
        unsupported_memory,
        result.player_perspectives,
        result.next_chapter,
    )

    assert report.passed is False
    assert "unsupported_relationship_claim" in {issue.code for issue in report.issues}


def test_human_signals_without_gameplay_events_abstain_safely() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["match_events"] = []
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.REJECTED
    assert result.discovery.signal_score >= result.discovery.threshold
    assert "no grounded gameplay event is available as evidence" in result.discovery.reasons
    assert result.memory is None
    assert result.player_perspectives == []
    assert result.next_chapter is None
    assert "missing_grounded_gameplay" in {issue.code for issue in result.validation.issues}


def test_squad_memory_requires_two_opted_in_members() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    for member in payload["squad"]["members"][1:]:
        member["opted_in"] = False
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.REJECTED
    assert "fewer than two squad members are opted in" in result.discovery.reasons
    assert "insufficient_opted_in_members" in {issue.code for issue in result.validation.issues}


@pytest.mark.parametrize("caption_length", [98, 99, 100, 101, 120])
def test_supported_caption_lengths_fit_generated_title_contracts(
    caption_length: int,
) -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["human_memory"]["caption"] = "x" * caption_length
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert result.memory is not None
    assert result.next_chapter is not None
    assert len(result.memory.title) <= 100
    assert len(result.next_chapter.title) <= 120


def test_whitespace_only_caption_uses_a_grounded_fallback_title() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["human_memory"]["caption"] = "   "
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.memory is not None
    assert result.memory.title == "The Clock Tower Rescue"
    assert "player-authored caption" not in result.discovery.reasons


@pytest.mark.parametrize(
    ("raw_passengers", "expected_target"),
    [("many", 2), ("3", 3), (-4, 2), (0, 2), (True, 2), (2.5, 2), (99, 3)],
)
def test_vehicle_passenger_target_is_safe_and_bounded(
    raw_passengers: str | int | float | bool,
    expected_target: int,
) -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["match_events"][2]["details"]["passengers"] = raw_passengers
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert result.next_chapter is not None
    driver_objective = next(
        objective
        for objective in result.next_chapter.objectives
        if objective.objective_id == "driver-seat-open"
    )
    assert driver_objective.verification.target == expected_target


@pytest.mark.parametrize(
    "escape_updates",
    [
        {"timestamp_seconds": 1000},
        {"timestamp_seconds": 1300},
        {"location": "Peak"},
        {"location": None},
    ],
)
def test_disconnected_events_do_not_receive_a_causal_pattern_bonus(
    escape_updates: dict[str, str | int | None],
) -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["match_events"][2].update(escape_updates)
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.memory is not None
    assert "connected rescue-and-escape pattern" not in result.discovery.reasons
    assert "before" not in result.memory.summary


def test_causal_summary_uses_the_connected_pair_location() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["match_events"] = [
        {
            "event_id": "evt-last-alive-alpha",
            "type": "last_player_alive",
            "actor_id": "amir",
            "timestamp_seconds": 100,
            "location": "Alpha",
            "importance": "high",
            "details": {},
        },
        {
            "event_id": "evt-revive-alpha",
            "type": "revive",
            "actor_id": "mei",
            "target_id": "lee",
            "timestamp_seconds": 110,
            "location": "Alpha",
            "importance": "high",
            "details": {},
        },
        {
            "event_id": "evt-revive-bravo",
            "type": "revive",
            "actor_id": "jo",
            "target_id": "amir",
            "timestamp_seconds": 200,
            "location": "Bravo",
            "importance": "high",
            "details": {},
        },
        {
            "event_id": "evt-escape-bravo",
            "type": "vehicle_escape",
            "actor_id": "amir",
            "timestamp_seconds": 210,
            "location": "Bravo",
            "importance": "high",
            "details": {"passengers": 3},
        },
    ]
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.memory is not None
    assert result.memory.summary.startswith("At Bravo, Jo revived Amir before Amir drove")


def test_comeback_pattern_requires_the_last_survivor_to_perform_the_revive() -> None:
    payload = json.loads((DATA_DIR / "comeback_memory.json").read_text(encoding="utf-8"))
    payload["match_events"][1]["actor_id"] = "kay"
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.memory is not None
    assert "last-player-alive comeback pattern" not in result.discovery.reasons
    assert "brought" not in result.memory.summary


def test_generic_actor_perspectives_remain_factually_distinct() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    for index, (event, member) in enumerate(
        zip(payload["match_events"], payload["squad"]["members"], strict=True), start=1
    ):
        event.update(
            {
                "event_id": f"evt-elimination-{index}",
                "type": "elimination",
                "actor_id": member["player_id"],
                "target_id": None,
                "timestamp_seconds": 100 + index,
                "location": "Clock Tower",
                "importance": "high",
                "details": {},
            }
        )
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert result.validation.scores.perspective_distinctness == 1.0
    assert len({item.message for item in result.player_perspectives}) == 4


def test_validator_rejects_evidence_event_type_mismatch() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    first_evidence = result.memory.evidence[0].model_copy(update={"event_type": "friendship_power"})
    mismatched_memory = result.memory.model_copy(
        update={"evidence": [first_evidence, *result.memory.evidence[1:]]}
    )
    report = ValidatorAgent().validate(
        pack,
        mismatched_memory,
        result.player_perspectives,
        result.next_chapter,
    )

    assert report.passed is False
    assert "memory_evidence_type_mismatch" in {issue.code for issue in report.issues}
    assert report.scores.evidence_grounding < 1.0


def test_validator_requires_exactly_one_perspective_per_player() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    duplicate = result.player_perspectives[0].model_copy(
        update={"message": "A separate sentence cannot hide a duplicate player record."}
    )
    report = ValidatorAgent().validate(
        pack,
        result.memory,
        [*result.player_perspectives, duplicate],
        result.next_chapter,
    )

    assert report.passed is False
    assert "duplicate_player_perspective" in {issue.code for issue in report.issues}


def test_validator_rejects_spoofed_perspective_display_name() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    spoofed = result.player_perspectives[0].model_copy(update={"display_name": "Not Lee"})
    report = ValidatorAgent().validate(
        pack,
        result.memory,
        [spoofed, *result.player_perspectives[1:]],
        result.next_chapter,
    )

    assert report.passed is False
    assert "perspective_display_name_mismatch" in {issue.code for issue in report.issues}


def test_perspective_evidence_must_belong_to_the_discovered_memory() -> None:
    pack = load_pack("comeback_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    memory_event_ids = {item.event_id for item in result.memory.evidence}
    outside_event_id = next(
        event.event_id for event in pack.match_events if event.event_id not in memory_event_ids
    )
    disconnected = result.player_perspectives[0].model_copy(
        update={"evidence_event_ids": [outside_event_id]}
    )
    report = ValidatorAgent().validate(
        pack,
        result.memory,
        [disconnected, *result.player_perspectives[1:]],
        result.next_chapter,
    )

    assert report.passed is False
    assert "perspective_not_connected_to_memory" in {issue.code for issue in report.issues}


def test_validator_checks_every_quest_objective_independently() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    first = result.next_chapter.objectives[0]
    invalid = first.model_copy(
        update={
            "assigned_player_id": "intruder",
            "source_event_ids": [],
            "verification": first.verification.model_copy(update={"metric": "win_at_any_cost"}),
        }
    )
    duplicate = result.next_chapter.objectives[1].model_copy(
        update={"objective_id": first.objective_id}
    )
    invalid_quest = result.next_chapter.model_copy(
        update={"objectives": [invalid, duplicate, *result.next_chapter.objectives[2:]]}
    )
    report = ValidatorAgent().validate(
        pack,
        result.memory,
        result.player_perspectives,
        invalid_quest,
    )
    codes = {issue.code for issue in report.issues}

    assert report.passed is False
    assert "invalid_quest_assignee" in codes
    assert "missing_quest_objective_evidence" in codes
    assert "duplicate_quest_objective_id" in codes
    assert "unsupported_verification_metric" in codes


def test_verification_rules_must_match_their_source_events() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    objectives = list(result.next_chapter.objectives)
    location_index = next(
        index
        for index, objective in enumerate(objectives)
        if objective.objective_id == "return-to-location"
    )
    driver_index = next(
        index
        for index, objective in enumerate(objectives)
        if objective.objective_id == "driver-seat-open"
    )
    revive_index = next(
        index
        for index, objective in enumerate(objectives)
        if objective.objective_id == "return-the-favour"
    )
    revive_event_id = next(event.event_id for event in pack.match_events if event.type == "revive")
    objectives[location_index] = objectives[location_index].model_copy(
        update={
            "verification": objectives[location_index].verification.model_copy(
                update={"target": ["The Moon"]}
            )
        }
    )
    objectives[driver_index] = objectives[driver_index].model_copy(
        update={"source_event_ids": [revive_event_id]}
    )
    objectives[revive_index] = objectives[revive_index].model_copy(
        update={
            "verification": objectives[revive_index].verification.model_copy(
                update={"target": ["mei", "amir"]}
            )
        }
    )
    invalid_quest = result.next_chapter.model_copy(update={"objectives": objectives})

    report = ValidatorAgent().validate(
        pack,
        result.memory,
        result.player_perspectives,
        invalid_quest,
    )
    codes = {issue.code for issue in report.issues}

    assert report.passed is False
    assert "invalid_location_verification" in codes
    assert "invalid_revive_verification" in codes
    assert "invalid_vehicle_escape_verification" in codes


def test_quest_requires_more_than_repeated_participant_anchors() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    participant_objective = result.next_chapter.objectives[0]
    repeated_objectives = [
        participant_objective.model_copy(update={"objective_id": f"participants-{index}"})
        for index in range(3)
    ]
    generic_quest = result.next_chapter.model_copy(update={"objectives": repeated_objectives})

    report = ValidatorAgent().validate(
        pack,
        result.memory,
        result.player_perspectives,
        generic_quest,
    )

    assert report.passed is False
    assert report.scores.specificity == 0.33
    assert "insufficient_quest_specificity" in {issue.code for issue in report.issues}


def test_quest_requires_exactly_one_required_squad_reunion_objective() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    participant = result.next_chapter.objectives[0]
    without_participants = result.next_chapter.model_copy(
        update={"objectives": result.next_chapter.objectives[1:]}
    )
    optional_participants = result.next_chapter.model_copy(
        update={
            "objectives": [
                participant.model_copy(update={"required": False}),
                *result.next_chapter.objectives[1:],
            ]
        }
    )

    missing_report = ValidatorAgent().validate(
        pack,
        result.memory,
        result.player_perspectives,
        without_participants,
    )
    optional_report = ValidatorAgent().validate(
        pack,
        result.memory,
        result.player_perspectives,
        optional_participants,
    )

    assert missing_report.passed is False
    assert "invalid_participant_objective_count" in {issue.code for issue in missing_report.issues}
    assert optional_report.passed is False
    assert "participant_objective_must_be_required" in {
        issue.code for issue in optional_report.issues
    }


def test_validator_rejects_malformed_objective_targets_and_descriptions() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    objectives = list(result.next_chapter.objectives)
    revive_index = next(
        index
        for index, objective in enumerate(objectives)
        if objective.objective_id == "return-the-favour"
    )
    driver_index = next(
        index
        for index, objective in enumerate(objectives)
        if objective.objective_id == "driver-seat-open"
    )
    objectives[revive_index] = objectives[revive_index].model_copy(
        update={
            "description": "   ",
            "verification": objectives[revive_index].verification.model_copy(
                update={"target": ["lee", "lee"]}
            ),
        }
    )
    objectives[driver_index] = objectives[driver_index].model_copy(
        update={
            "verification": objectives[driver_index].verification.model_copy(update={"target": 2.5})
        }
    )
    invalid_quest = result.next_chapter.model_copy(update={"objectives": objectives})

    report = ValidatorAgent().validate(
        pack,
        result.memory,
        result.player_perspectives,
        invalid_quest,
    )
    codes = {issue.code for issue in report.issues}

    assert report.passed is False
    assert "invalid_quest_objective_description" in codes
    assert "invalid_revive_verification" in codes
    assert "invalid_vehicle_escape_verification" in codes


def test_deterministic_quest_never_assigns_an_opted_out_player() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["squad"]["members"][0]["opted_in"] = False
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert result.next_chapter is not None
    assert "lee" not in {item.player_id for item in result.player_perspectives}
    assert "lee" not in {
        objective.assigned_player_id
        for objective in result.next_chapter.objectives
        if objective.assigned_player_id is not None
    }


@pytest.mark.parametrize(
    "unsafe_description",
    [
        "Lose on purpose, then shoot your teammate.",
        "Do not hesitate; deliberately lose.",
        "Avoid enemies, then use friendly fire.",
    ],
)
def test_validator_rejects_unsafe_quest_instructions(
    unsafe_description: str,
) -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    unsafe_objective = result.next_chapter.objectives[0].model_copy(
        update={"description": unsafe_description}
    )
    unsafe_quest = result.next_chapter.model_copy(
        update={"objectives": [unsafe_objective, *result.next_chapter.objectives[1:]]}
    )
    report = ValidatorAgent().validate(
        pack,
        result.memory,
        result.player_perspectives,
        unsafe_quest,
    )

    assert report.passed is False
    assert "unsafe_quest_instruction" in {issue.code for issue in report.issues}


def test_validator_does_not_flag_safety_language_that_prohibits_harm() -> None:
    pack = load_pack("funny_memory.json")
    result = MemoryPipeline().run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    safe_objective = result.next_chapter.objectives[0].model_copy(
        update={"description": "Complete the reunion while avoiding friendly fire."}
    )
    safe_quest = result.next_chapter.model_copy(
        update={"objectives": [safe_objective, *result.next_chapter.objectives[1:]]}
    )
    report = ValidatorAgent().validate(
        pack,
        result.memory,
        result.player_perspectives,
        safe_quest,
    )

    assert report.passed is True
    assert "unsafe_quest_instruction" not in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    "caption",
    ["Friendly fire fail", "Throw the match", "Teamkill memory"],
)
def test_player_caption_can_name_an_unsafe_incident_without_instructing_it(
    caption: str,
) -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["human_memory"]["caption"] = caption
    pack = MemoryPack.model_validate(payload)

    result = MemoryPipeline().run(pack)

    assert result.status == PipelineStatus.READY
    assert "unsafe_quest_instruction" not in {issue.code for issue in result.validation.issues}


def test_provider_name_is_trimmed_and_case_normalized() -> None:
    pipeline = build_pipeline("  DeTeRmInIsTiC  ")

    assert pipeline.provider_name == "deterministic"


def test_model_prose_is_replaced_by_canonical_rendering_before_validation() -> None:
    pack = load_pack("funny_memory.json")
    baseline = MemoryPipeline().run(pack)
    assert baseline.memory is not None
    assert baseline.next_chapter is not None

    hostile_memory = baseline.memory.model_copy(
        update={
            "title": "Invented Best Friend Story",
            "summary": "Lee scored 99 eliminations and became Mei's soulmate.",
            "evidence": [
                item.model_copy(update={"significance": "Invented 99 elimination claim"})
                for item in baseline.memory.evidence
            ],
        }
    )
    hostile_perspectives = PerspectiveSet(
        perspectives=[
            item.model_copy(update={"message": "Sabotage your squad and lose on purpose."})
            for item in baseline.player_perspectives
        ]
    )
    hostile_quest = baseline.next_chapter.model_copy(
        update={
            "title": "Unsafe invented quest",
            "mission": "Throw the match.",
            "objectives": [
                item.model_copy(update={"description": "Refuse every revive."})
                for item in baseline.next_chapter.objectives
            ],
        }
    )

    class ScriptedGenerator:
        provider_name = "scripted"
        model_name = "adversarial-fixture"

        def generate(self, *, response_model, **_kwargs):
            outputs = {
                MemoryRecord: hostile_memory,
                PerspectiveSet: hostile_perspectives,
                NextChapter: hostile_quest,
            }
            return outputs[response_model]

    result = MemoryPipeline(ScriptedGenerator()).run(pack)
    assert result.memory is not None
    assert result.next_chapter is not None

    rendered_text = " ".join(
        [
            result.memory.title,
            result.memory.summary,
            *(item.significance for item in result.memory.evidence),
            *(item.message for item in result.player_perspectives),
            result.next_chapter.title,
            result.next_chapter.mission,
            *(item.description for item in result.next_chapter.objectives),
        ]
    ).casefold()
    assert result.status == PipelineStatus.READY
    assert result.validation.passed is True
    assert result.metadata["prose_renderer"] == "canonical-v1"
    assert "99 elimination" not in rendered_text
    assert "soulmate" not in rendered_text
    assert "sabotage" not in rendered_text
    assert "throw the match" not in rendered_text
