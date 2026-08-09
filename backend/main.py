"""FastAPI entrypoint for AI-first v2 interpretation and v1 compatibility routes."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

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
from backend.models.v2_schemas import (
    DeliveryDecisionRecordV2,
    InterpretDeliveryResultV2,
    InterpretVariedDeliveryRequestV2,
    RawTelemetryBatchV2,
    RecordDeliveryDecisionRequestV2,
    StudioInterpretationTraceV2,
)
from backend.models.v2_studio_schemas import (
    StudioScenarioCatalogV2,
    StudioScenarioInterpretationV2,
    StudioScenarioPreparationV2,
)
from backend.pipeline import MemoryPipeline, build_pipeline
from backend.services.delivery_store import delivery_decision_store
from backend.services.openai_client import OpenAIProviderError
from backend.services.v2_delivery_repository import v2_delivery_repository
from backend.services.v2_studio_scenarios import studio_scenario_registry_v2
from backend.v2_pipeline import MemoryInterpretationPipelineV2, build_v2_pipeline

logger = logging.getLogger(__name__)


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
    description=(
        "Interpret trusted gameplay telemetry into grounded squad memories and personalized "
        "next chapters. Legacy v1.1 routes remain available during the v2 migration."
    ),
    version="0.3.0",
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
    "/v2/memories/interpret-delivery",
    "/v2/memories/interpret-varied-delivery",
    "/v2/deliveries/{delivery_id}/decision",
}


@app.middleware("http")
async def protect_sensitive_routes(request: Request, call_next):
    """Optionally restrict data-bearing API routes to a trusted server-side proxy."""

    expected = os.getenv("MEMORYOS_PROXY_TOKEN")
    if expected and _is_protected_request(request.method, request.url.path):
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


def _is_protected_post_path(path: str) -> bool:
    if path in PROTECTED_POST_PATHS:
        return True
    if path.startswith("/v2/studio/scenarios/"):
        return path.endswith("/prepare") or path.endswith("/interpret")
    return path.startswith("/v2/deliveries/") and path.endswith("/decision")


def _is_protected_request(method: str, path: str) -> bool:
    if method == "POST":
        return _is_protected_post_path(path)
    return method == "GET" and path.startswith("/v2/deliveries/") and path.endswith("/trace")


@app.get("/health", tags=["system"], response_model=None)
def health() -> dict[str, str] | JSONResponse:
    try:
        pipeline = _build_configured_pipeline()
        pipeline.validate_provider_configuration()
    except OpenAIProviderError as error:
        return _provider_error_response(error)
    return {
        "status": "ok",
        "phase": "v1-compatibility+v2",
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
    deprecated=True,
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
    deprecated=True,
)
def prepare_delivery(request: PrepareDeliveryRequest) -> MemoryDeliveryResult | JSONResponse:
    """Prepare one trusted squad memory for an accept-or-decline delivery."""

    try:
        return _build_configured_pipeline().prepare_delivery(request.memory_packs)
    except OpenAIProviderError as error:
        return _provider_error_response(error)


@app.post(
    "/v2/memories/interpret-delivery",
    response_model=InterpretDeliveryResultV2,
    response_model_exclude_none=True,
    responses={503: {"model": ProviderErrorBody}},
    tags=["memory-interpretation-v2"],
)
def interpret_delivery_v2(
    request: RawTelemetryBatchV2,
) -> InterpretDeliveryResultV2 | JSONResponse:
    """Interpret telemetry into one fully validated player delivery or fail closed."""

    try:
        result = _build_configured_v2_pipeline().interpret_delivery(request)
        issue_codes = [issue.code for issue in result.validation.issues]
        logger.log(
            logging.WARNING if result.status.value == "rejected" else logging.INFO,
            "v2_interpretation_complete status=%s correction_attempted=%s issue_codes=%s",
            result.status.value,
            result.validation.correction_attempted,
            ",".join(issue_codes) or "none",
        )
        return result
    except OpenAIProviderError as error:
        return _provider_error_response(error)


@app.post(
    "/v2/memories/interpret-varied-delivery",
    response_model=InterpretDeliveryResultV2,
    response_model_exclude_none=True,
    responses={503: {"model": ProviderErrorBody}},
    tags=["memory-interpretation-v2"],
)
def interpret_varied_delivery_v2(
    request: InterpretVariedDeliveryRequestV2,
) -> InterpretDeliveryResultV2 | JSONResponse:
    """Interpret telemetry within a bounded, cooldown-aware mission-family pool."""

    try:
        result = _build_configured_v2_pipeline().interpret_delivery(
            request.telemetry,
            variation_seed=request.generation_nonce,
        )
        issue_codes = [issue.code for issue in result.validation.issues]
        logger.log(
            logging.WARNING if result.status.value == "rejected" else logging.INFO,
            "v2_varied_interpretation_complete status=%s correction_attempted=%s issue_codes=%s",
            result.status.value,
            result.validation.correction_attempted,
            ",".join(issue_codes) or "none",
        )
        return result
    except OpenAIProviderError as error:
        return _provider_error_response(error)


@app.get(
    "/v2/studio/scenarios",
    response_model=StudioScenarioCatalogV2,
    tags=["developer-studio-v2"],
)
def list_studio_scenarios_v2(response: Response) -> StudioScenarioCatalogV2:
    """List the exact synthetic fixtures available to Developer Studio."""

    response.headers["Cache-Control"] = "no-store"
    return studio_scenario_registry_v2.catalog()


@app.post(
    "/v2/studio/scenarios/{scenario_id}/prepare",
    response_model=StudioScenarioPreparationV2,
    responses={
        404: {"model": ProviderErrorBody},
        422: {"model": ProviderErrorBody},
    },
    tags=["developer-studio-v2"],
)
async def prepare_studio_scenario_v2(
    scenario_id: str,
    request: Request,
    response: Response,
) -> StudioScenarioPreparationV2 | JSONResponse:
    """Inspect normalization, privacy, windows, and affordances without a model call."""

    body_error = await _reject_studio_scenario_body(request)
    if body_error is not None:
        return body_error
    try:
        result = studio_scenario_registry_v2.prepare(scenario_id)
    except KeyError:
        return _studio_scenario_error(
            status_code=404,
            code="unknown_studio_scenario",
            message="The requested Developer Studio scenario is not registered.",
        )
    response.headers["Cache-Control"] = "no-store"
    return result


@app.post(
    "/v2/studio/scenarios/{scenario_id}/interpret",
    response_model=StudioScenarioInterpretationV2,
    responses={
        404: {"model": ProviderErrorBody},
        422: {"model": ProviderErrorBody},
        503: {"model": ProviderErrorBody},
    },
    tags=["developer-studio-v2"],
)
async def interpret_studio_scenario_v2(
    scenario_id: str,
    request: Request,
    response: Response,
) -> StudioScenarioInterpretationV2 | JSONResponse:
    """Run one registered fixture through the unchanged live v2 interpretation pipeline."""

    body_error = await _reject_studio_scenario_body(request)
    if body_error is not None:
        return body_error
    try:
        registered = studio_scenario_registry_v2.get(scenario_id)
    except KeyError:
        return _studio_scenario_error(
            status_code=404,
            code="unknown_studio_scenario",
            message="The requested Developer Studio scenario is not registered.",
        )
    try:
        # Evaluation expectations remain on `registered.descriptor`; only the strict
        # raw telemetry fixture crosses the existing player-pipeline boundary.
        pipeline = _build_configured_v2_pipeline()
        result = await asyncio.to_thread(pipeline.interpret_delivery, registered.telemetry)
    except OpenAIProviderError as error:
        return _provider_error_response(error)
    response.headers["Cache-Control"] = "no-store"
    return StudioScenarioInterpretationV2(
        scenario=registered.descriptor,
        result=result,
    )


@app.post(
    "/v2/deliveries/{delivery_id}/decision",
    response_model=DeliveryDecisionRecordV2,
    response_model_exclude_none=True,
    responses={404: {"model": ProviderErrorBody}},
    tags=["memory-interpretation-v2"],
)
def record_delivery_decision_v2(
    delivery_id: str,
    request: RecordDeliveryDecisionRequestV2,
) -> DeliveryDecisionRecordV2 | JSONResponse:
    """Capture exactly one prototype relevance decision for a validated v2 delivery."""

    result = v2_delivery_repository.record_decision(
        delivery_id,
        request.decision,
        request.decline_reason,
    )
    if result is None:
        return JSONResponse(
            status_code=404,
            content={
                "stage": "player_decision",
                "code": "unknown_delivery",
                "retryable": False,
                "message": "This validated delivery is no longer available.",
            },
            headers={"Cache-Control": "no-store"},
        )
    return result


@app.get(
    "/v2/deliveries/{delivery_id}/trace",
    response_model=StudioInterpretationTraceV2,
    responses={404: {"model": ProviderErrorBody}},
    tags=["memory-interpretation-v2"],
)
def get_delivery_trace_v2(
    delivery_id: str,
    response: Response,
) -> StudioInterpretationTraceV2 | JSONResponse:
    """Return a sanitized Studio trace, including the recorded player decision."""

    trace = v2_delivery_repository.get_trace(delivery_id)
    if trace is None:
        return JSONResponse(
            status_code=404,
            content={
                "stage": "studio_trace",
                "code": "unknown_delivery",
                "retryable": False,
                "message": "This validated delivery trace is no longer available.",
            },
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return trace


@app.post(
    "/v1/memories/record-delivery-decision",
    response_model=RecordDeliveryDecisionResponse,
    responses={404: {"model": ProviderErrorBody}},
    tags=["memory-engine"],
    deprecated=True,
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
    deprecated=True,
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

        stopped_stage = result.metadata.get("stopped_stage")
        generated_stage_order = [
            "memory_discovery",
            "perspectives",
            "quest_generation",
        ]
        if result.memory is None and stopped_stage in {
            *generated_stage_order,
            "validation",
        }:
            yield _ndjson_event(
                type="stage",
                stage="review_and_discovery",
                status="complete",
                message="Evidence, consent, and review checks passed.",
            )
            stop_index = (
                generated_stage_order.index(stopped_stage)
                if stopped_stage in generated_stage_order
                else len(generated_stage_order)
            )
            for stage in generated_stage_order[:stop_index]:
                yield _ndjson_event(
                    type="stage",
                    stage=stage,
                    status="complete",
                    observability=_stage_observability(result.metadata, stage),
                )
            if stopped_stage in generated_stage_order:
                yield _ndjson_event(
                    type="stage",
                    stage=stopped_stage,
                    status="stopped",
                    message=f"Generation stopped during {stopped_stage.replace('_', ' ')}.",
                    observability=_stage_observability(result.metadata, stopped_stage),
                )
            yield _ndjson_event(
                type="stage",
                stage="validation",
                status="failed",
                preview=result.validation.model_dump(mode="json"),
            )
        elif result.memory is None:
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
        headers={"Cache-Control": "no-store"},
    )


async def _reject_studio_scenario_body(request: Request) -> JSONResponse | None:
    """Named Studio routes select server fixtures and never accept telemetry overrides."""

    if await request.body():
        return _studio_scenario_error(
            status_code=422,
            code="studio_request_body_not_allowed",
            message="Registered Developer Studio scenarios do not accept a request body.",
        )
    return None


def _studio_scenario_error(*, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "stage": "studio_scenario",
            "code": code,
            "retryable": False,
            "message": message,
        },
        headers={"Cache-Control": "no-store"},
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


def _build_configured_v2_pipeline() -> MemoryInterpretationPipelineV2:
    try:
        pipeline = build_v2_pipeline()
        pipeline.validate_provider_configuration()
        if pipeline.execution_mode != "live_ai":
            raise OpenAIProviderError(
                stage="configuration",
                code="live_ai_required",
                retryable=False,
            )
        return pipeline
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
