"""The checked-in frontend type input must remain FastAPI's canonical schema."""

from __future__ import annotations

import json
from pathlib import Path

from backend.main import app


def test_frontend_openapi_snapshot_matches_fastapi_contract() -> None:
    snapshot_path = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot == app.openapi()
