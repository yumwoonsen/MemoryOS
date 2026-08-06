"""HTTP contract smoke tests."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app, get_pipeline
from backend.pipeline import MemoryPipeline

client = TestClient(app)
DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


@pytest.fixture(autouse=True)
def deterministic_pipeline_override() -> None:
    app.dependency_overrides[get_pipeline] = lambda: MemoryPipeline()
    yield
    app.dependency_overrides.clear()


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "phase": "1",
        "provider": "deterministic",
        "model": "rules-v1",
    }


def test_frontend_origin_can_preflight_discovery() -> None:
    response = client.options(
        "/v1/memories/discover",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_discovery_endpoint_returns_versioned_output() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    response = client.post("/v1/memories/discover", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "ready"
    assert body["validation"]["passed"] is True
    assert set(body["discovery"]) == {"signal_score", "threshold", "reasons", "eligible"}


def test_discovery_endpoint_safely_abstains_without_gameplay_evidence() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["match_events"] = []

    response = client.post("/v1/memories/discover", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert "no grounded gameplay event is available as evidence" in body["discovery"]["reasons"]
    assert "memory" not in body
    assert "next_chapter" not in body


def test_api_tests_do_not_follow_the_developer_provider_environment(monkeypatch) -> None:
    monkeypatch.setenv("MEMORYOS_PROVIDER", "openai")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["provider"] == "deterministic"


def test_invalid_provider_configuration_returns_stable_json(monkeypatch) -> None:
    app.dependency_overrides.clear()
    monkeypatch.setenv("MEMORYOS_PROVIDER", "not-a-provider")
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))

    with TestClient(app, raise_server_exceptions=False) as configured_client:
        responses = [
            configured_client.get("/health"),
            configured_client.post("/v1/memories/discover", json=payload),
        ]

    for response in responses:
        assert response.status_code == 503
        assert response.headers["content-type"].startswith("application/json")
        assert response.json() == {
            "detail": {
                "code": "pipeline_configuration_error",
                "message": "The configured MemoryOS provider is unavailable.",
            }
        }
