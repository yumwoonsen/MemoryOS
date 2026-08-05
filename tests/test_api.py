"""HTTP contract smoke tests."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as api
from backend.main import app
from backend.services.openai_client import OpenAIProviderError

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


def load_history_payload() -> list[dict[str, object]]:
    return json.loads((DATA_DIR / "historical_memory_packs.json").read_text(encoding="utf-8"))


def test_history_endpoint_returns_ranked_v11_candidates() -> None:
    response = client.post(
        "/v1/memories/discover-history",
        json={"schema_version": "1.1", "memory_packs": load_history_payload(), "limit": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.1"
    assert [item["rank"] for item in body["candidates"]] == [1, 2, 3]
    assert body["filters"]["below_threshold"] == 1
    assert body["metadata"]["provider"] == "deterministic"


def test_generate_endpoint_stops_before_ai_when_review_is_incomplete() -> None:
    pack = load_history_payload()[1]
    response = client.post(
        "/v1/memories/generate",
        json={"schema_version": "1.1", "memory_pack": pack},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_source_verification"
    assert "memory" not in body
    assert "next_chapter" not in body


def test_legacy_endpoint_rejects_v11_input() -> None:
    response = client.post("/v1/memories/discover", json=load_history_payload()[0])

    assert response.status_code == 422


def test_legacy_endpoint_requires_explicit_current_consent() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))
    payload["squad"]["members"][0].pop("opted_in")

    response = client.post("/v1/memories/discover", json=payload)

    assert response.status_code == 422


def test_history_endpoint_rejects_mixed_squads() -> None:
    packs = load_history_payload()[:2]
    packs[1]["squad"]["squad_id"] = "different-squad"

    response = client.post(
        "/v1/memories/discover-history",
        json={"schema_version": "1.1", "memory_packs": packs},
    )

    assert response.status_code == 422


def test_history_endpoint_rejects_mixed_target_players() -> None:
    packs = load_history_payload()[:2]
    packs[1]["player_profile"]["player_id"] = "mei"

    response = client.post(
        "/v1/memories/discover-history",
        json={"schema_version": "1.1", "memory_packs": packs},
    )

    assert response.status_code == 422


def test_history_endpoint_rejects_more_than_fifty_packs() -> None:
    base = load_history_payload()[0]
    packs = []
    for index in range(51):
        item = copy.deepcopy(base)
        item["pack_id"] = f"history-limit-{index:02d}"
        item["match"]["match_id"] = f"H-LIMIT-{index:02d}"
        packs.append(item)

    response = client.post(
        "/v1/memories/discover-history",
        json={"schema_version": "1.1", "memory_packs": packs},
    )

    assert response.status_code == 422


def test_local_frontend_origin_is_allowed() -> None:
    response = client.options(
        "/v1/memories/discover-history",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_openapi_exposes_v11_contracts_and_deprecated_legacy_route() -> None:
    schema = client.get("/openapi.json").json()

    legacy_operation = schema["paths"]["/v1/memories/discover"]["post"]
    assert legacy_operation["deprecated"] is True
    assert legacy_operation["responses"]["503"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ProviderErrorBody")
    assert "/v1/memories/discover-history" in schema["paths"]
    assert "/v1/memories/generate" in schema["paths"]
    assert "HistoricalDiscoveryRequest" in schema["components"]["schemas"]
    assert "MemoryEngineResultV11" in schema["components"]["schemas"]
    result_schema = schema["components"]["schemas"]["MemoryEngineResultV11"]
    assert result_schema["properties"]["status"]["$ref"].endswith("/PipelineStatusV11")
    assert schema["components"]["schemas"]["PipelineStatusV11"]["enum"] == [
        "ready",
        "needs_source_verification",
        "needs_meaning_confirmation",
        "rejected",
    ]
    assert "human_review" not in schema["components"]["schemas"]["MemoryPack"]["properties"]
    assert "human_review" not in schema["components"]["schemas"]["LegacyMemoryPack"]["properties"]
    assert "human_review" in schema["components"]["schemas"]["MemoryPackV11"]["properties"]
    assert "opted_in" in schema["components"]["schemas"]["LegacySquadMember"]["required"]

    stream_response = schema["paths"]["/v1/memories/generate-stream"]["post"]["responses"]["200"]
    assert set(stream_response["content"]) == {"application/x-ndjson"}
    event_schema = stream_response["content"]["application/x-ndjson"]["schema"]
    assert event_schema["discriminator"]["propertyName"] == "type"
    assert {item["$ref"].rsplit("/", 1)[-1] for item in event_schema["oneOf"]} == {
        "GenerateStreamStageEvent",
        "GenerateStreamErrorEvent",
        "GenerateStreamResultEvent",
    }


def test_v10_pack_uses_phase_2_metadata_on_generate() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))

    response = client.post(
        "/v1/memories/generate",
        json={"schema_version": "1.1", "memory_pack": payload},
    )

    assert response.status_code == 200
    assert response.json()["metadata"]["pipeline_version"] == "phase-2-generation-v1"


def test_review_gate_precedes_live_provider_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORYOS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    request = {"schema_version": "1.1", "memory_pack": load_history_payload()[1]}

    response = client.post("/v1/memories/generate", json=request)

    assert response.status_code == 200
    assert response.json()["status"] == "needs_source_verification"
    assert response.json()["metadata"]["provider"] == "openai"

    stream_response = client.post("/v1/memories/generate-stream", json=request)
    events = [json.loads(line) for line in stream_response.text.splitlines()]
    assert stream_response.status_code == 200
    assert all(event["type"] != "error" for event in events)
    assert events[-1]["type"] == "result"
    assert events[-1]["result"]["status"] == "needs_source_verification"


class BrokenPipeline:
    def generate(self, memory_pack: object) -> None:
        raise OpenAIProviderError(
            stage="quest_generation",
            code="provider_timeout",
            retryable=True,
        )


def test_provider_failure_is_a_safe_structured_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "build_pipeline", lambda: BrokenPipeline())
    response = client.post(
        "/v1/memories/generate",
        json={"schema_version": "1.1", "memory_pack": load_history_payload()[0]},
    )

    assert response.status_code == 503
    assert response.json() == {
        "stage": "quest_generation",
        "code": "provider_timeout",
        "retryable": True,
        "message": "The live AI provider could not complete this generation stage.",
    }


def test_stream_emits_typed_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "build_pipeline", lambda: BrokenPipeline())
    response = client.post(
        "/v1/memories/generate-stream",
        json={"schema_version": "1.1", "memory_pack": load_history_payload()[0]},
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1] == {
        "type": "error",
        "stage": "quest_generation",
        "code": "provider_timeout",
        "retryable": True,
    }
