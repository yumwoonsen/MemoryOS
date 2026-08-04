"""FastAPI entrypoint for the Phase 1 Memory Engine."""

import asyncio
import json
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.models.schemas import MemoryEngineResult, MemoryPack, PipelineStatus
from backend.pipeline import build_pipeline

app = FastAPI(
    title="Garena Next Chapter — MemoryOS",
    description="Discover grounded squad memories and turn them into personalized next chapters.",
    version="0.1.0",
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
    allow_headers=["Content-Type"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    pipeline = build_pipeline()
    return {
        "status": "ok",
        "phase": "1",
        "provider": pipeline.provider_name,
        "model": pipeline.model_name,
    }


@app.post(
    "/v1/memories/discover",
    response_model=MemoryEngineResult,
    response_model_exclude_none=True,
    tags=["memory-engine"],
)
def discover_memory(memory_pack: MemoryPack) -> MemoryEngineResult:
    """Run all five stages and return the grounded output plus validation report."""

    return build_pipeline().run(memory_pack)


@app.post("/v1/memories/generate-stream", tags=["memory-engine"])
def generate_memory_stream(memory_pack: MemoryPack) -> StreamingResponse:
    """Run the credential-free local engine and stream each visible pipeline stage."""

    async def events():
        started_at = time.perf_counter()
        pipeline = build_pipeline("deterministic")

        def event(payload: dict[str, object]) -> str:
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

        try:
            event_count = len(memory_pack.match_events)
            member_count = len([member for member in memory_pack.squad.members if member.opted_in])

            yield event({
                "type": "stage", "stage": "discovery", "status": "working",
                "message": f"Reading {event_count} grounded match events locally...",
            })
            await asyncio.sleep(0.35)
            assessment, memory = pipeline.memory_agent.discover(memory_pack)
            if memory is None:
                yield event({
                    "type": "stage", "stage": "discovery", "status": "failed",
                    "message": "The notes did not contain enough grounded memory signal yet.",
                })
                yield event({
                    "type": "error",
                    "message": "Add a confirmed caption, tags, or another important match event.",
                })
                return
            yield event({
                "type": "stage", "stage": "discovery", "status": "complete",
                "message": f'Found "{memory.title}"',
                "preview": memory.model_dump(mode="json"),
            })

            await asyncio.sleep(0.15)
            yield event({
                "type": "stage", "stage": "perspectives", "status": "working",
                "message": f"Grounding {member_count} distinct player perspectives locally...",
            })
            await asyncio.sleep(0.35)
            perspectives = pipeline.perspective_agent.create(memory_pack, memory)
            yield event({
                "type": "stage", "stage": "perspectives", "status": "complete",
                "message": f"{len(perspectives)} personal recalls grounded",
                "preview": [item.model_dump(mode="json") for item in perspectives],
            })

            await asyncio.sleep(0.15)
            yield event({
                "type": "stage", "stage": "quest", "status": "working",
                "message": "Remixing the memory into a local squad mission...",
            })
            await asyncio.sleep(0.35)
            quest = pipeline.quest_agent.create(memory_pack, memory, perspectives)
            yield event({
                "type": "stage", "stage": "quest", "status": "complete",
                "message": f'Built "{quest.title}"',
                "preview": quest.model_dump(mode="json"),
            })

            await asyncio.sleep(0.15)
            yield event({
                "type": "stage", "stage": "validation", "status": "working",
                "message": "Checking every local result against the source events...",
            })
            await asyncio.sleep(0.35)
            validation = pipeline.validator_agent.validate(
                memory_pack, memory, perspectives, quest
            )
            yield event({
                "type": "stage", "stage": "validation",
                "status": "complete" if validation.passed else "failed",
                "message": (
                    "Every generated reference is grounded"
                    if validation.passed else "Grounding checks found a problem"
                ),
                "preview": validation.model_dump(mode="json"),
            })

            if not validation.passed:
                status = PipelineStatus.REJECTED
            elif memory.human_confirmed:
                status = PipelineStatus.READY
            else:
                status = PipelineStatus.NEEDS_HUMAN_CONFIRMATION

            result = MemoryEngineResult(
                pack_id=memory_pack.pack_id,
                status=status,
                discovery=assessment,
                memory=memory,
                player_perspectives=perspectives,
                next_chapter=quest,
                validation=validation,
                metadata={
                    "pipeline_version": "local-live-v1",
                    "provider": "local",
                    "model": "grounded-rules-v1",
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
                },
            )
            yield event({
                "type": "result",
                "result": result.model_dump(mode="json", exclude_none=True),
            })
        except Exception as exc:  # pragma: no cover - defensive stream boundary
            yield event({
                "type": "error", "message": f"The local memory engine stopped: {exc}",
            })

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
