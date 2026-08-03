"""FastAPI entrypoint for the Phase 1 Memory Engine."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.models.schemas import MemoryEngineResult, MemoryPack
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
