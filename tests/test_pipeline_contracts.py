"""Focused regressions for deterministic control fields at the AI boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.agents.perspective_agent import PerspectiveAgent
from backend.models.schemas import MemoryPackV11, PerspectiveSet, PipelineStatusV11, QuestRecipe
from backend.pipeline import MemoryPipeline

DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


class SequenceGenerator:
    provider_name = "test"
    model_name = "control-field-regression"

    def __init__(self, responses: list[BaseModel]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        prompt_name: str,
        payload: dict[str, Any],
        response_model: type[BaseModel],
        stage: str,
    ) -> BaseModel:
        self.calls.append({"stage": stage, "payload": payload})
        response = self.responses.pop(0)
        assert isinstance(response, response_model), stage
        return response


class RetryingSequenceGenerator(SequenceGenerator):
    semantic_retry_limit = 1
    narrative_fallback_enabled = True


def test_pipeline_overwrites_model_authored_confidence_and_confirmation() -> None:
    payload = json.loads((DATA_DIR / "historical_memory_packs.json").read_text(encoding="utf-8"))[0]
    pack = MemoryPackV11.model_validate(payload)
    baseline = MemoryPipeline().generate(pack)
    assert baseline.memory is not None
    assert baseline.next_chapter is not None

    model_memory = baseline.memory.model_copy(update={"confidence": 0.01, "human_confirmed": False})
    generator = SequenceGenerator(
        [
            model_memory,
            PerspectiveSet(perspectives=baseline.player_perspectives),
            baseline.next_chapter,
        ]
    )

    result = MemoryPipeline(generator).generate(pack)

    assert result.status == PipelineStatusV11.READY
    assert result.memory is not None
    assert result.memory.confidence == result.discovery.signal_score
    assert result.memory.human_confirmed is True


def test_model_authors_player_facing_output_but_not_control_fields() -> None:
    payload = json.loads((DATA_DIR / "historical_memory_packs.json").read_text(encoding="utf-8"))[0]
    pack = MemoryPackV11.model_validate(payload)
    baseline = MemoryPipeline().generate(pack)
    assert baseline.memory is not None
    assert baseline.next_chapter is not None

    model_memory = baseline.memory.model_copy(
        update={
            "title": f"Model cut: {baseline.memory.title}",
            "summary": f"Model-framed memory: {baseline.memory.summary}",
            "evidence": [],
        }
    )
    model_perspectives = [
        perspective.model_copy(
            update={
                "display_name": "untrusted-model-label",
                "message": f"Your model-personalized lens: {perspective.message}",
                "evidence_event_ids": [],
            }
        )
        for perspective in baseline.player_perspectives
    ]
    model_objectives = [
        objective.model_copy(
            update={
                "description": f"Model-authored quest line: {objective.description}",
                "required": False,
                "source_event_ids": [],
            }
        )
        for objective in baseline.next_chapter.objectives
    ]
    model_quest = baseline.next_chapter.model_copy(
        update={
            "title": f"Model cut: {baseline.next_chapter.title}",
            "mission": f"Model-authored mission: {baseline.next_chapter.mission}",
            "recipe": QuestRecipe.RESOLVE,
            "objectives": model_objectives,
        }
    )
    generator = SequenceGenerator(
        [
            model_memory,
            PerspectiveSet(perspectives=model_perspectives),
            model_quest,
        ]
    )

    result = MemoryPipeline(generator).generate(pack)

    assert result.status == PipelineStatusV11.READY
    assert result.memory is not None
    assert result.next_chapter is not None
    assert result.memory.title == model_memory.title
    assert result.memory.summary == model_memory.summary
    assert result.memory.evidence == baseline.memory.evidence
    assert [item.message for item in result.player_perspectives] == [
        item.message for item in model_perspectives
    ]
    assert [item.display_name for item in result.player_perspectives] == [
        item.display_name for item in baseline.player_perspectives
    ]
    assert [item.evidence_event_ids for item in result.player_perspectives] == [
        item.evidence_event_ids for item in baseline.player_perspectives
    ]
    perspective_scaffolds = generator.calls[1]["payload"]["required_perspective_scaffolds"]
    expected_meanings = PerspectiveAgent().create(pack, result.memory)
    assert [item["required_meaning"] for item in perspective_scaffolds] == [
        item.message for item in expected_meanings
    ]
    assert all("message" not in item for item in perspective_scaffolds)
    assert result.next_chapter.title == model_quest.title
    assert result.next_chapter.mission == model_quest.mission
    assert result.next_chapter.recipe == QuestRecipe.RESOLVE
    assert [item.description for item in result.next_chapter.objectives] == [
        item.description for item in model_objectives
    ]
    assert [
        item.model_dump(mode="json", exclude={"description"})
        for item in result.next_chapter.objectives
    ] == [
        item.model_dump(mode="json", exclude={"description"})
        for item in baseline.next_chapter.objectives
    ]


def test_live_pipeline_retries_one_rejected_semantic_stage_with_feedback() -> None:
    payload = json.loads((DATA_DIR / "historical_memory_packs.json").read_text(encoding="utf-8"))[0]
    pack = MemoryPackV11.model_validate(payload)
    baseline = MemoryPipeline().generate(pack)
    assert baseline.memory is not None
    assert baseline.next_chapter is not None

    first_person = [
        perspective.model_copy(
            update={"message": (f"I remember {perspective.display_name}'s moment at Clock Tower.")}
        )
        for perspective in baseline.player_perspectives
    ]
    generator = RetryingSequenceGenerator(
        [
            baseline.memory,
            PerspectiveSet(perspectives=first_person),
            PerspectiveSet(perspectives=baseline.player_perspectives),
            baseline.next_chapter,
        ]
    )

    result = MemoryPipeline(generator).generate(pack)

    assert result.status == PipelineStatusV11.READY
    assert [call["stage"] for call in generator.calls] == [
        "memory_discovery",
        "perspectives",
        "perspectives",
        "quest_generation",
    ]
    feedback = generator.calls[2]["payload"]["validation_feedback_codes"]
    assert "perspective_not_second_person" in feedback


def test_live_pipeline_keeps_safe_model_perspectives_and_falls_back_invalid_one() -> None:
    payload = json.loads((DATA_DIR / "historical_memory_packs.json").read_text(encoding="utf-8"))[0]
    pack = MemoryPackV11.model_validate(payload)
    baseline = MemoryPipeline().generate(pack)
    assert baseline.memory is not None
    assert baseline.next_chapter is not None

    generated_perspectives = []
    for perspective in baseline.player_perspectives:
        if perspective.player_id == "lee":
            message = (
                "You were revived by Mei at Clock Tower and drove the squad out with 2 passengers."
            )
        else:
            message = f"Your AI retelling: {perspective.message}"
        generated_perspectives.append(perspective.model_copy(update={"message": message}))

    rejected_set = PerspectiveSet(perspectives=generated_perspectives)
    generator = RetryingSequenceGenerator(
        [
            baseline.memory,
            rejected_set,
            rejected_set,
            baseline.next_chapter,
        ]
    )

    result = MemoryPipeline(generator).generate(pack)

    assert result.status == PipelineStatusV11.READY
    messages = {item.player_id: item.message for item in result.player_perspectives}
    baseline_messages = {item.player_id: item.message for item in baseline.player_perspectives}
    assert messages["lee"] == baseline_messages["lee"]
    assert messages["mei"].startswith("Your AI retelling:")
    assert result.metadata["narrative_fallbacks"] == {"perspectives": 1}


def test_live_pipeline_keeps_safe_quest_prose_and_falls_back_invalid_line() -> None:
    payload = json.loads((DATA_DIR / "historical_memory_packs.json").read_text(encoding="utf-8"))[0]
    pack = MemoryPackV11.model_validate(payload)
    baseline = MemoryPipeline().generate(pack)
    assert baseline.memory is not None
    assert baseline.next_chapter is not None

    objectives = list(baseline.next_chapter.objectives)
    objectives[0] = objectives[0].model_copy(
        update={"description": "Do something unrelated in the next match."}
    )
    generated_quest = baseline.next_chapter.model_copy(
        update={
            "title": f"AI Remix: {baseline.next_chapter.title}",
            "objectives": objectives,
        }
    )
    generator = RetryingSequenceGenerator(
        [
            baseline.memory,
            PerspectiveSet(perspectives=baseline.player_perspectives),
            generated_quest,
            generated_quest,
        ]
    )

    result = MemoryPipeline(generator).generate(pack)

    assert result.status == PipelineStatusV11.READY
    assert result.next_chapter is not None
    assert result.next_chapter.title.startswith("AI Remix:")
    assert (
        result.next_chapter.objectives[0].description
        == baseline.next_chapter.objectives[0].description
    )
    assert result.metadata["narrative_fallbacks"] == {"quest": 1}
