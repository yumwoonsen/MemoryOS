"""HTTP contract smoke tests."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "phase": "1",
        "provider": "deterministic",
        "model": "rules-v1",
    }


def test_discovery_endpoint_returns_versioned_output() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    response = client.post("/v1/memories/discover", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "ready"
    assert body["validation"]["passed"] is True
