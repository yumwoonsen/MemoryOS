"""Orchestration for input -> discovery -> perspectives -> quest -> validation."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from backend.agents.memory_agent import MemoryAgent
from backend.agents.perspective_agent import PerspectiveAgent
from backend.agents.quest_agent import QuestAgent
from backend.agents.validator_agent import ValidatorAgent
from backend.models.schemas import MemoryEngineResult, MemoryPack, PipelineStatus
from backend.services.structured_generator import StructuredGenerator


class MemoryPipeline:
    """A small orchestrator with swappable generation and deterministic validation."""

    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator
        self.memory_agent = MemoryAgent(generator)
        self.perspective_agent = PerspectiveAgent(generator)
        self.quest_agent = QuestAgent(generator)
        self.validator_agent = ValidatorAgent()

    @property
    def provider_name(self) -> str:
        return self._generator.provider_name if self._generator else "deterministic"

    @property
    def model_name(self) -> str:
        return self._generator.model_name if self._generator else "rules-v1"

    def run(self, pack: MemoryPack) -> MemoryEngineResult:
        assessment, memory = self.memory_agent.discover(pack)
        if memory is None:
            return MemoryEngineResult(
                pack_id=pack.pack_id,
                status=PipelineStatus.REJECTED,
                discovery=assessment,
                validation=self.validator_agent.abstention_report(assessment),
                metadata=self._metadata(),
            )

        perspectives = self.perspective_agent.create(pack, memory)
        quest = self.quest_agent.create(pack, memory, perspectives)
        validation = self.validator_agent.validate(pack, memory, perspectives, quest)

        if not validation.passed:
            status = PipelineStatus.REJECTED
        elif memory.human_confirmed:
            status = PipelineStatus.READY
        else:
            status = PipelineStatus.NEEDS_HUMAN_CONFIRMATION

        return MemoryEngineResult(
            pack_id=pack.pack_id,
            status=status,
            discovery=assessment,
            memory=memory,
            player_perspectives=perspectives,
            next_chapter=quest,
            validation=validation,
            metadata=self._metadata(),
        )

    def _metadata(self) -> dict[str, str]:
        return {
            "pipeline_version": "phase-1-v1",
            "provider": self.provider_name,
            "model": self.model_name,
        }


def build_pipeline(provider: str | None = None) -> MemoryPipeline:
    """Build a pipeline from explicit configuration or environment variables."""

    load_dotenv()
    selected_provider = (provider or os.getenv("MEMORYOS_PROVIDER", "deterministic")).lower()
    if selected_provider == "deterministic":
        return MemoryPipeline()
    if selected_provider == "openai":
        from backend.services.openai_client import OpenAIStructuredGenerator

        return MemoryPipeline(OpenAIStructuredGenerator())
    raise ValueError("MEMORYOS_PROVIDER must be either 'deterministic' or 'openai'")
