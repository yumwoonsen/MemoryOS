"""FastAPI entrypoint for the Phase 1 Memory Engine."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.models.schemas import MemoryEngineResult, MemoryPack
from backend.pipeline import build_pipeline

app = FastAPI(
    title="Garena Next Chapter — MemoryOS",
    description="Discover grounded squad memories and turn them into personalized next chapters.",
    version="0.1.0",
)

# The Phase 2 prototype runs its frontend on a separate local development port.
# Keep the browser boundary narrow while allowing that UI to call the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type"],
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
