"""Focused regressions for deterministic control fields at the AI boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.models.schemas import MemoryPackV11, PerspectiveSet, PipelineStatusV11
from backend.pipeline import MemoryPipeline

DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


class SequenceGenerator:
    provider_name = "test"
    model_name = "control-field-regression"

    def __init__(self, responses: list[BaseModel]) -> None:
        self.responses = list(responses)

    def generate(
        self,
        *,
        prompt_name: str,
        payload: dict[str, Any],
        response_model: type[BaseModel],
        stage: str,
    ) -> BaseModel:
        response = self.responses.pop(0)
        assert isinstance(response, response_model), stage
        return response


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
