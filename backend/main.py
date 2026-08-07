"""FastAPI entrypoint for the Phase 1/2 Memory Engine."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse, StreamingResponse

from backend.models.schemas import (
    GenerateMemoryRequest,
    GenerateStreamEvent,
    HistoricalDiscoveryRequest,
    HistoricalDiscoveryResponse,
    LegacyMemoryPack,
    MemoryDeliveryResult,
    MemoryEngineResult,
    MemoryEngineResultV11,
    PrepareDeliveryRequest,
    ProviderErrorBody,
    RecordDeliveryDecisionRequest,
    RecordDeliveryDecisionResponse,
)
from backend.pipeline import MemoryPipeline, build_pipeline
from backend.services.delivery_store import delivery_decision_store
from backend.services.openai_client import OpenAIProviderError


class NDJSONStreamingResponse(StreamingResponse):
    """Streaming response whose OpenAPI media type matches its wire format."""

    media_type = "application/x-ndjson"


GENERATE_STREAM_EVENT_SCHEMA = {
    "type": "object",
    "oneOf": [
        {"$ref": "#/components/schemas/GenerateStreamStageEvent"},
        {"$ref": "#/components/schemas/GenerateStreamErrorEvent"},
        {"$ref": "#/components/schemas/GenerateStreamResultEvent"},
    ],
    "discriminator": {
        "propertyName": "type",
        "mapping": {
            "stage": "#/components/schemas/GenerateStreamStageEvent",
            "error": "#/components/schemas/GenerateStreamErrorEvent",
            "result": "#/components/schemas/GenerateStreamResultEvent",
        },
    },
}

app = FastAPI(
    title="Garena Next Chapter — MemoryOS",
    description="Discover grounded squad memories and turn them into personalized next chapters.",
    version="0.2.0",
)

default_origins = (
    "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:5173,http://localhost:5173"
)
allowed_origins = [
    origin.strip()
    for origin in os.getenv("MEMORYOS_CORS_ORIGINS", default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-MemoryOS-Proxy-Token"],
)

PROTECTED_POST_PATHS = {
    "/v1/memories/discover",
    "/v1/memories/discover-history",
    "/v1/memories/generate",
    "/v1/memories/generate-stream",
    "/v1/memories/prepare-delivery",
    "/v1/memories/record-delivery-decision",
}


@app.middleware("http")
async def require_trusted_proxy(request: Request, call_next):
    """Optionally restrict data-bearing POST routes to a trusted server-side proxy."""

    expected = os.getenv("MEMORYOS_PROXY_TOKEN")
    if expected and request.method == "POST" and request.url.path in PROTECTED_POST_PATHS:
        supplied = request.headers.get("X-MemoryOS-Proxy-Token", "")
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            return JSONResponse(
                status_code=401,
                content={
                    "stage": "authentication",
                    "code": "proxy_authentication_failed",
                    "retryable": False,
                    "message": "A valid trusted-proxy token is required.",
                },
                headers={"Cache-Control": "no-store"},
            )
    return await call_next(request)


@app.get("/health", tags=["system"], response_model=None)
def health() -> dict[str, str] | JSONResponse:
    try:
        pipeline = _build_configured_pipeline()
        pipeline.validate_provider_configuration()
    except OpenAIProviderError as error:
        return _provider_error_response(error)
    return {
        "status": "ok",
        "phase": "1",
        "provider": pipeline.provider_name,
        "model": pipeline.model_name,
        "mode": pipeline.execution_mode,
    }


@app.post(
    "/v1/memories/discover",
    response_model=MemoryEngineResult,
    response_model_exclude_none=True,
    responses={503: {"model": ProviderErrorBody}},
    tags=["memory-engine"],
    deprecated=True,
)
def discover_memory(memory_pack: LegacyMemoryPack) -> MemoryEngineResult | JSONResponse:
    """Legacy v1.0 full-pipeline adapter retained during the migration window."""

    try:
        return _build_configured_pipeline().run(memory_pack)
    except OpenAIProviderError as error:
        return _provider_error_response(error)


@app.post(
    "/v1/memories/discover-history",
    response_model=HistoricalDiscoveryResponse,
    response_model_exclude_none=True,
    tags=["memory-engine"],
)
def discover_history(request: HistoricalDiscoveryRequest) -> HistoricalDiscoveryResponse:
    """Rank historical candidates deterministically without model calls."""

    return MemoryPipeline().discover_history(request)


@app.post(
    "/v1/memories/generate",
    response_model=MemoryEngineResultV11,
    response_model_exclude_none=True,
    responses={503: {"model": ProviderErrorBody}},
    tags=["memory-engine"],
)
def generate_memory(request: GenerateMemoryRequest) -> MemoryEngineResultV11 | JSONResponse:
    """Expand a reviewed candidate into perspectives and a grounded quest."""

    try:
        return _build_configured_pipeline().generate(request.memory_pack)
    except OpenAIProviderError as error:
        return _provider_error_response(error)


@app.post(
    "/v1/memories/prepare-delivery",
    response_model=MemoryDeliveryResult,
    response_model_exclude_none=True,
    responses={503: {"model": ProviderErrorBody}},
    tags=["memory-engine"],
)
def prepare_delivery(request: PrepareDeliveryRequest) -> MemoryDeliveryResult | JSONResponse:
    """Prepare one trusted squad memory for an accept-or-decline delivery."""

    try:
        return _build_configured_pipeline().prepare_delivery(request.memory_packs)
    except OpenAIProviderError as error:
        return _provider_error_response(error)


@app.post(
    "/v1/memories/record-delivery-decision",
    response_model=RecordDeliveryDecisionResponse,
    responses={404: {"model": ProviderErrorBody}},
    tags=["memory-engine"],
)
def record_delivery_decision(
    request: RecordDeliveryDecisionRequest,
) -> RecordDeliveryDecisionResponse | JSONResponse:
    """Record a prototype accept/decline decision for a prepared delivery."""

    result = delivery_decision_store.record(
        request.delivery_id,
        request.decision,
        request.decline_reason,
    )
    if result is None:
        return JSONResponse(
            status_code=404,
            content={
                "stage": "delivery_decision",
                "code": "unknown_delivery",
                "retryable": False,
                "message": "This prepared delivery is no longer available.",
            },
        )
    return result


@app.post(
    "/v1/memories/generate-stream",
    response_model=GenerateStreamEvent,
    response_class=NDJSONStreamingResponse,
    response_model_exclude_none=True,
    responses={
        200: {
            "description": "Newline-delimited generation events; the schema describes one line.",
            "content": {"application/x-ndjson": {"schema": GENERATE_STREAM_EVENT_SCHEMA}},
        }
    },
    tags=["memory-engine"],
)
def generate_memory_stream(request: GenerateMemoryRequest) -> NDJSONStreamingResponse:
    """Expose the canonical generation result as newline-delimited stage events."""

    async def events() -> AsyncIterator[str]:
        yield _ndjson_event(
            type="stage",
            stage="review_and_discovery",
            status="working",
            message="Rechecking evidence, consent, and review state.",
        )
        try:
            pipeline = _build_configured_pipeline()
            result = await asyncio.to_thread(pipeline.generate, request.memory_pack)
        except OpenAIProviderError as error:
            yield _ndjson_event(type="error", **error.as_dict())
            return

        if result.memory is None:
            yield _ndjson_event(
                type="stage",
                stage="review_and_discovery",
                status="stopped",
                message=f"Generation stopped with status {result.status.value}.",
            )
        else:
            yield _ndjson_event(
                type="stage",
                stage="memory_discovery",
                status="complete",
                preview=result.memory.model_dump(mode="json"),
                observability=_stage_observability(result.metadata, "memory_discovery"),
            )
            yield _ndjson_event(
                type="stage",
                stage="perspectives",
                status="complete",
                preview=[item.model_dump(mode="json") for item in result.player_perspectives],
                observability=_stage_observability(result.metadata, "perspectives"),
            )
            yield _ndjson_event(
                type="stage",
                stage="quest_generation",
                status="complete",
                preview=(
                    result.next_chapter.model_dump(mode="json") if result.next_chapter else None
                ),
                observability=_stage_observability(result.metadata, "quest_generation"),
            )
            yield _ndjson_event(
                type="stage",
                stage="validation",
                status="complete" if result.validation.passed else "failed",
                preview=result.validation.model_dump(mode="json"),
            )

        yield _ndjson_event(
            type="result",
            result=result.model_dump(mode="json", exclude_none=True),
        )

    return NDJSONStreamingResponse(
        events(),
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def _provider_error_response(error: OpenAIProviderError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            **error.as_dict(),
            "message": "The live AI provider could not complete this generation stage.",
        },
    )


def _build_configured_pipeline() -> MemoryPipeline:
    try:
        return build_pipeline()
    except ValueError:
        raise OpenAIProviderError(
            stage="configuration",
            code="invalid_provider",
            retryable=False,
        ) from None


def _ndjson_event(**payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _stage_observability(metadata: dict[str, object], stage: str) -> dict[str, object] | None:
    """Select one safe provider metric snapshot for a completed stream stage."""

    observability = metadata.get("observability")
    if not isinstance(observability, dict):
        return None
    stages = observability.get("stages")
    if not isinstance(stages, list):
        return None
    return next(
        (
            dict(item)
            for item in reversed(stages)
            if isinstance(item, dict) and item.get("stage") == stage
        ),
        None,
    )
