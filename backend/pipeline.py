"""Orchestration for input -> discovery -> perspectives -> quest -> validation."""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

from backend.agents.memory_agent import MemoryAgent
from backend.agents.perspective_agent import PerspectiveAgent
from backend.agents.quest_agent import QuestAgent
from backend.agents.validator_agent import ValidatorAgent
from backend.models.schemas import (
    DeliveryNarrative,
    DeliveryStatus,
    HistoricalDiscoveryRequest,
    HistoricalDiscoveryResponse,
    MeaningStatus,
    MemoryDeliveryResult,
    MemoryEngineResult,
    MemoryEngineResultV11,
    MemoryPack,
    MemoryPackV11,
    MemoryRecord,
    PipelineStatus,
    PipelineStatusV11,
    SourceStatus,
)
from backend.services.delivery_store import delivery_decision_store
from backend.services.evidence import sanitize_memory_pack
from backend.services.historical_discovery import HistoricalMemoryRanker
from backend.services.provider_observability import empty_observability
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

    @property
    def observability(self) -> dict[str, object]:
        if self._delegate is None:
            return empty_observability(
                provider=self.provider_name,
                model=self.model_name,
                mode="live_ai",
                configured_max_retries=2,
            )
        return dict(getattr(self._delegate, "observability", {}))

    def validate_configuration(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            from backend.services.openai_client import OpenAIProviderError

            raise OpenAIProviderError(
                stage="configuration",
                code="missing_api_key",
                retryable=False,
            )

    def generate(self, **kwargs: Any) -> Any:
        if self._delegate is None:
            from backend.services.openai_client import OpenAIStructuredGenerator

            self._delegate = OpenAIStructuredGenerator(self.model_name)
        return self._delegate.generate(**kwargs)


class LazyGroqStructuredGenerator:
    """Expose Groq metadata while deferring key validation until a model stage runs."""

    provider_name = "groq"

    def __init__(self) -> None:
        from backend.services.groq_client import DEFAULT_MODEL

        self.model_name = os.getenv("GROQ_MODEL") or DEFAULT_MODEL
        self._delegate: StructuredGenerator | None = None

    @property
    def usage_totals(self) -> dict[str, int]:
        if self._delegate is None:
            return {"input_tokens": 0, "output_tokens": 0}
        return dict(getattr(self._delegate, "usage_totals", {}))

    @property
    def observability(self) -> dict[str, object]:
        if self._delegate is None:
            return empty_observability(
                provider=self.provider_name,
                model=self.model_name,
                mode="live_ai",
                configured_max_retries=2,
            )
        return dict(getattr(self._delegate, "observability", {}))

    def validate_configuration(self) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or not api_key.strip():
            from backend.services.groq_client import GroqProviderError

            raise GroqProviderError(
                stage="configuration",
                code="missing_api_key",
                retryable=False,
            )

    def generate(self, **kwargs: Any) -> Any:
        if self._delegate is None:
            from backend.services.groq_client import GroqStructuredGenerator

            self._delegate = GroqStructuredGenerator(self.model_name)
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
    def execution_mode(self) -> str:
        return "live_ai" if self._generator else "deterministic"

    @property
    def usage_totals(self) -> dict[str, int]:
        usage = getattr(self._generator, "usage_totals", None)
        return dict(usage) if usage is not None else {"input_tokens": 0, "output_tokens": 0}

    @property
    def observability(self) -> dict[str, object]:
        snapshot = getattr(self._generator, "observability", None)
        if snapshot is not None:
            return dict(snapshot)
        return empty_observability(
            provider=self.provider_name,
            model=self.model_name,
            mode="deterministic" if self._generator is None else "live_ai",
        )

    def validate_provider_configuration(self) -> None:
        """Check credential presence without constructing a client or making a model call."""

        validate = getattr(self._generator, "validate_configuration", None)
        if validate is not None:
            validate()

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

    def prepare_delivery(self, packs: list[MemoryPackV11]) -> MemoryDeliveryResult:
        """Prepare one trusted moment without treating player relevance as confirmed."""

        discovery = self.discover_history(
            HistoricalDiscoveryRequest(schema_version="1.1", memory_packs=packs, limit=10)
        )
        pack_by_id = {pack.pack_id: pack for pack in packs}
        candidate = next(
            (item for item in discovery.candidates if item.source_status == SourceStatus.VERIFIED),
            None,
        )
        if candidate is None:
            pack = packs[0]
            assessment = self.history_ranker.assess(pack)
            return MemoryDeliveryResult(
                pack_id=pack.pack_id,
                status=DeliveryStatus.REJECTED,
                source_status=pack.source_status,
                meaning_status=pack.meaning_status,
                validation=self.validator_agent.abstention_report(assessment),
                metadata={
                    "pipeline_version": "phase-2-delivery-v1",
                    "provider": self.provider_name,
                },
            )

        pack = pack_by_id[candidate.pack_id]
        delivery_pack = pack.model_copy(
            update={
                "human_review": pack.human_review.model_copy(
                    update={"meaning_status": MeaningStatus.CONFIRMED}
                )
            }
        )
        generated = self.generate(delivery_pack)
        if (
            generated.status != PipelineStatusV11.READY
            or generated.memory is None
            or generated.next_chapter is None
        ):
            return MemoryDeliveryResult(
                pack_id=pack.pack_id,
                status=DeliveryStatus.REJECTED,
                source_status=pack.source_status,
                meaning_status=pack.meaning_status,
                validation=generated.validation,
                metadata={**generated.metadata, "pipeline_version": "phase-2-delivery-v1"},
            )

        delivery_id = uuid4().hex
        delivery_decision_store.register(delivery_id)
        return MemoryDeliveryResult(
            delivery_id=delivery_id,
            pack_id=pack.pack_id,
            status=DeliveryStatus.PENDING_PLAYER_DECISION,
            source_status=pack.source_status,
            meaning_status=pack.meaning_status,
            memory=generated.memory.model_copy(update={"human_confirmed": False}),
            player_perspectives=generated.player_perspectives,
            next_chapter=generated.next_chapter,
            narrative=DeliveryNarrative(
                teaser=f"{generated.memory.title} is waiting for your squad.",
                why_this_surfaced=" · ".join(candidate.reasons[:2]),
            ),
            validation=generated.validation,
            metadata={**generated.metadata, "pipeline_version": "phase-2-delivery-v1"},
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
            "mode": self.execution_mode,
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
        metadata["observability"] = self.observability
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
    if selected_provider == "groq":
        return MemoryPipeline(LazyGroqStructuredGenerator())
    raise ValueError("MEMORYOS_PROVIDER must be 'deterministic', 'openai', or 'groq'")
