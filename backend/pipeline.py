"""Orchestration for input -> discovery -> perspectives -> quest -> validation."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from backend.agents.memory_agent import MemoryAgent
from backend.agents.perspective_agent import PerspectiveAgent
from backend.agents.quest_agent import QuestAgent
from backend.agents.validator_agent import ValidatorAgent
from backend.models.schemas import (
    HistoricalDiscoveryRequest,
    HistoricalDiscoveryResponse,
    MeaningStatus,
    MemoryEngineResult,
    MemoryEngineResultV11,
    MemoryPack,
    MemoryPackV11,
    MemoryRecord,
    PipelineStatus,
    PipelineStatusV11,
    SourceStatus,
)
from backend.services.evidence import sanitize_memory_pack
from backend.services.historical_discovery import HistoricalMemoryRanker
from backend.services.structured_generator import StructuredGenerator


class LazyOpenAIStructuredGenerator:
    """Expose provider metadata immediately but create the SDK client only on first generation."""

    provider_name = "openai"

    def __init__(self) -> None:
        from backend.services.openai_client import DEFAULT_MODEL

        self.model_name = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self._delegate: StructuredGenerator | None = None

    @property
    def usage_totals(self) -> dict[str, int]:
        if self._delegate is None:
            return {"input_tokens": 0, "output_tokens": 0}
        return dict(getattr(self._delegate, "usage_totals", {}))

    def generate(self, **kwargs: Any) -> Any:
        if self._delegate is None:
            from backend.services.openai_client import OpenAIStructuredGenerator

            self._delegate = OpenAIStructuredGenerator(self.model_name)
        return self._delegate.generate(**kwargs)


class MemoryPipeline:
    """A small orchestrator with swappable generation and deterministic validation."""

    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator
        self.memory_agent = MemoryAgent(generator)
        self.perspective_agent = PerspectiveAgent(generator)
        self.quest_agent = QuestAgent(generator)
        self.validator_agent = ValidatorAgent()
        self.history_ranker = HistoricalMemoryRanker()

    @property
    def provider_name(self) -> str:
        return self._generator.provider_name if self._generator else "deterministic"

    @property
    def model_name(self) -> str:
        return self._generator.model_name if self._generator else "rules-v1"

    @property
    def usage_totals(self) -> dict[str, int]:
        usage = getattr(self._generator, "usage_totals", None)
        return dict(usage) if usage is not None else {"input_tokens": 0, "output_tokens": 0}

    def run(self, pack: MemoryPack) -> MemoryEngineResult:
        if not pack.target_player_opted_in:
            assessment = self.history_ranker.assess(pack)
            return MemoryEngineResult(
                pack_id=pack.pack_id,
                status=PipelineStatus.REJECTED,
                discovery=assessment,
                validation=self.validator_agent.abstention_report(assessment),
                metadata=self._metadata(pack),
            )
        safe_pack, redactions = sanitize_memory_pack(pack)
        forbidden_terms = self._opted_out_terms(pack)
        assessment, memory = self.memory_agent.discover(safe_pack)
        if memory is None:
            return MemoryEngineResult(
                pack_id=pack.pack_id,
                status=PipelineStatus.REJECTED,
                discovery=assessment,
                validation=self.validator_agent.abstention_report(assessment),
                metadata=self._metadata(pack, len(redactions)),
            )

        memory = self._authoritative_memory_state(pack, assessment.signal_score, memory)

        memory_stage = self.validator_agent.stage_failure_report(
            self.validator_agent.validate_memory_stage(
                safe_pack,
                memory,
                forbidden_terms=forbidden_terms,
            )
        )
        if not memory_stage.passed:
            return MemoryEngineResult(
                pack_id=pack.pack_id,
                status=PipelineStatus.REJECTED,
                discovery=assessment,
                validation=memory_stage,
                metadata=self._stage_metadata(pack, len(redactions), "memory_discovery"),
            )

        perspectives = self.perspective_agent.create(safe_pack, memory)
        perspective_stage = self.validator_agent.stage_failure_report(
            self.validator_agent.validate_perspective_stage(
                safe_pack,
                memory,
                perspectives,
                forbidden_terms=forbidden_terms,
            )
        )
        if not perspective_stage.passed:
            return MemoryEngineResult(
                pack_id=pack.pack_id,
                status=PipelineStatus.REJECTED,
                discovery=assessment,
                validation=perspective_stage,
                metadata=self._stage_metadata(pack, len(redactions), "perspectives"),
            )

        quest = self.quest_agent.create(safe_pack, memory, perspectives)
        validation = self.validator_agent.validate(
            safe_pack,
            memory,
            perspectives,
            quest,
            forbidden_terms=forbidden_terms,
        )

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
            memory=memory if validation.passed else None,
            player_perspectives=perspectives if validation.passed else [],
            next_chapter=quest if validation.passed else None,
            validation=validation,
            metadata=self._metadata(pack, len(redactions)),
        )

    def discover_history(self, request: HistoricalDiscoveryRequest) -> HistoricalDiscoveryResponse:
        """Rank historical candidates without invoking the configured generator."""

        return self.history_ranker.discover(request)

    def generate(self, pack: MemoryPack | MemoryPackV11) -> MemoryEngineResultV11:
        """Generate a selected candidate only after both review gates pass."""

        assessment = self.history_ranker.assess(pack)
        if not assessment.eligible:
            return MemoryEngineResultV11(
                pack_id=pack.pack_id,
                status=PipelineStatusV11.REJECTED,
                discovery=assessment,
                source_status=pack.source_status,
                meaning_status=pack.meaning_status,
                validation=self.validator_agent.abstention_report(assessment),
                metadata=self._generation_metadata(pack),
            )

        if pack.source_status != SourceStatus.VERIFIED:
            status = PipelineStatusV11.NEEDS_SOURCE_VERIFICATION
            return MemoryEngineResultV11(
                pack_id=pack.pack_id,
                status=status,
                discovery=assessment,
                source_status=pack.source_status,
                meaning_status=pack.meaning_status,
                validation=self.validator_agent.review_pending_report(status, assessment),
                metadata=self._generation_metadata(pack),
            )

        if pack.meaning_status != MeaningStatus.CONFIRMED:
            status = PipelineStatusV11.NEEDS_MEANING_CONFIRMATION
            return MemoryEngineResultV11(
                pack_id=pack.pack_id,
                status=status,
                discovery=assessment,
                source_status=pack.source_status,
                meaning_status=pack.meaning_status,
                validation=self.validator_agent.review_pending_report(status, assessment),
                metadata=self._generation_metadata(pack),
            )

        safe_pack, redactions = sanitize_memory_pack(pack)
        forbidden_terms = self._opted_out_terms(pack)
        assessment, memory = self.memory_agent.discover_from_assessment(safe_pack, assessment)
        if memory is None:  # pragma: no cover - assessment is already eligible
            return MemoryEngineResultV11(
                pack_id=pack.pack_id,
                status=PipelineStatusV11.REJECTED,
                discovery=assessment,
                source_status=pack.source_status,
                meaning_status=pack.meaning_status,
                validation=self.validator_agent.abstention_report(assessment),
                metadata=self._generation_metadata(pack, len(redactions)),
            )

        memory = self._authoritative_memory_state(pack, assessment.signal_score, memory)

        memory_stage = self.validator_agent.stage_failure_report(
            self.validator_agent.validate_memory_stage(
                safe_pack,
                memory,
                forbidden_terms=forbidden_terms,
            )
        )
        if not memory_stage.passed:
            return MemoryEngineResultV11(
                pack_id=pack.pack_id,
                status=PipelineStatusV11.REJECTED,
                discovery=assessment,
                source_status=pack.source_status,
                meaning_status=pack.meaning_status,
                validation=memory_stage,
                metadata=self._generation_stage_metadata(pack, len(redactions), "memory_discovery"),
            )

        perspectives = self.perspective_agent.create(safe_pack, memory)
        perspective_stage = self.validator_agent.stage_failure_report(
            self.validator_agent.validate_perspective_stage(
                safe_pack,
                memory,
                perspectives,
                forbidden_terms=forbidden_terms,
            )
        )
        if not perspective_stage.passed:
            return MemoryEngineResultV11(
                pack_id=pack.pack_id,
                status=PipelineStatusV11.REJECTED,
                discovery=assessment,
                source_status=pack.source_status,
                meaning_status=pack.meaning_status,
                validation=perspective_stage,
                metadata=self._generation_stage_metadata(pack, len(redactions), "perspectives"),
            )

        quest = self.quest_agent.create(safe_pack, memory, perspectives)
        validation = self.validator_agent.validate(
            safe_pack,
            memory,
            perspectives,
            quest,
            forbidden_terms=forbidden_terms,
        )
        status = PipelineStatusV11.READY if validation.passed else PipelineStatusV11.REJECTED
        return MemoryEngineResultV11(
            pack_id=pack.pack_id,
            status=status,
            discovery=assessment,
            source_status=pack.source_status,
            meaning_status=pack.meaning_status,
            memory=memory if validation.passed else None,
            player_perspectives=perspectives if validation.passed else [],
            next_chapter=quest if validation.passed else None,
            validation=validation,
            metadata=self._generation_metadata(pack, len(redactions)),
        )

    def _metadata(
        self,
        pack: MemoryPack | MemoryPackV11,
        redaction_count: int = 0,
        *,
        pipeline_version: str | None = None,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "pipeline_version": pipeline_version
            or ("phase-1-v1" if pack.schema_version == "1.0" else "phase-2-generation-v1"),
            "provider": self.provider_name,
            "model": self.model_name,
            "prompt_version": "grounded-v1",
            "factual_renderer": "closed-v1",
            "redaction_count": redaction_count,
            "compatibility_conversion": (
                "v1.0 confirmed normalized to split review states"
                if pack.schema_version == "1.0"
                else None
            ),
        }
        usage = getattr(self._generator, "usage_totals", None)
        if usage is not None:
            metadata["usage"] = usage
        return metadata

    def _generation_metadata(
        self, pack: MemoryPack | MemoryPackV11, redaction_count: int = 0
    ) -> dict[str, object]:
        return self._metadata(
            pack,
            redaction_count,
            pipeline_version="phase-2-generation-v1",
        )

    def _stage_metadata(
        self,
        pack: MemoryPack | MemoryPackV11,
        redaction_count: int,
        stage: str,
    ) -> dict[str, object]:
        metadata = self._metadata(pack, redaction_count)
        metadata["stopped_stage"] = stage
        return metadata

    def _generation_stage_metadata(
        self,
        pack: MemoryPack | MemoryPackV11,
        redaction_count: int,
        stage: str,
    ) -> dict[str, object]:
        metadata = self._generation_metadata(pack, redaction_count)
        metadata["stopped_stage"] = stage
        return metadata

    @staticmethod
    def _authoritative_memory_state(
        pack: MemoryPack | MemoryPackV11,
        signal_score: float,
        memory: MemoryRecord,
    ) -> MemoryRecord:
        """Replace model-authored control fields with deterministic pipeline state."""

        return memory.model_copy(
            update={
                "confidence": signal_score,
                "human_confirmed": pack.meaning_status == MeaningStatus.CONFIRMED,
            }
        )

    @staticmethod
    def _opted_out_terms(pack: MemoryPack | MemoryPackV11) -> set[str]:
        return {
            term
            for member in pack.squad.members
            if not member.opted_in
            for term in (member.player_id, member.display_name)
        }


def build_pipeline(provider: str | None = None) -> MemoryPipeline:
    """Build a pipeline from explicit configuration or environment variables."""

    load_dotenv()
    selected_provider = (
        (provider or os.getenv("MEMORYOS_PROVIDER", "deterministic")).strip().lower()
    )
    if selected_provider == "deterministic":
        return MemoryPipeline()
    if selected_provider == "openai":
        return MemoryPipeline(LazyOpenAIStructuredGenerator())
    raise ValueError("MEMORYOS_PROVIDER must be either 'deterministic' or 'openai'")
