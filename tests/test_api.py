"""HTTP contract smoke tests."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as api
from backend.main import app
from backend.models.schemas import IssueSeverity, PipelineStatusV11, ValidationIssue
from backend.pipeline import MemoryPipeline
from backend.services.openai_client import OpenAIProviderError

client = TestClient(app)
DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "phase": "v1-compatibility+v2",
        "provider": "deterministic",
        "model": "rules-v1",
        "mode": "deterministic",
    }


def test_groq_health_requires_a_server_side_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEMORYOS_PROVIDER", "groq")
    # An explicit empty value keeps python-dotenv from repopulating the key
    # from a developer's local .env file during this isolated configuration test.
    monkeypatch.setenv("GROQ_API_KEY", "")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "stage": "configuration",
        "code": "missing_api_key",
        "retryable": False,
        "message": "The live AI provider could not complete this generation stage.",
    }


def test_gemini_health_requires_a_server_side_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEMORYOS_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "stage": "configuration",
        "code": "missing_api_key",
        "retryable": False,
        "message": "The live AI provider could not complete this generation stage.",
    }


def test_gemini_health_reports_configured_provider_without_spending_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORYOS_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-only-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-flash")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "phase": "v1-compatibility+v2",
        "provider": "gemini",
        "model": "gemini-3.6-flash",
        "mode": "live_ai",
    }


def test_gemini_health_rejects_an_invalid_v2_output_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORYOS_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-only-key")
    monkeypatch.setenv("GEMINI_V2_MAX_OUTPUT_TOKENS", "not-a-number")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "stage": "configuration",
        "code": "invalid_output_token_limit",
        "retryable": False,
        "message": "The live AI provider could not complete this generation stage.",
    }


def test_invalid_provider_configuration_returns_safe_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORYOS_PROVIDER", "not-a-provider")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "stage": "configuration",
        "code": "invalid_provider",
        "retryable": False,
        "message": "The live AI provider could not complete this generation stage.",
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


def test_prepare_delivery_generates_a_pending_player_decision_and_records_choices() -> None:
    payload = load_history_payload()
    for pack in payload:
        if pack["human_review"]["source_status"] == "verified":
            pack["human_review"]["meaning_status"] = "unreviewed"

    response = client.post(
        "/v1/memories/prepare-delivery",
        json={"schema_version": "1.1", "memory_packs": payload},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_player_decision"
    assert body["source_status"] == "verified"
    assert body["meaning_status"] == "unreviewed"
    assert body["memory"]["human_confirmed"] is False
    assert body["narrative"]["teaser"]
    assert body["next_chapter"]

    accepted = client.post(
        "/v1/memories/record-delivery-decision",
        json={"delivery_id": body["delivery_id"], "decision": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["decision"] == "accepted"


def test_delivery_decline_requires_a_structured_reason_and_unknown_delivery_fails_closed() -> None:
    invalid = client.post(
        "/v1/memories/record-delivery-decision",
        json={"delivery_id": "missing", "decision": "declined"},
    )
    assert invalid.status_code == 422

    unknown = client.post(
        "/v1/memories/record-delivery-decision",
        json={"delivery_id": "missing", "decision": "declined", "decline_reason": "details_wrong"},
    )
    assert unknown.status_code == 404


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
    assert "x-memoryos-proxy-token" in response.headers["access-control-allow-headers"].lower()


def test_optional_proxy_token_protects_data_routes_but_not_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORYOS_PROXY_TOKEN", "server-only-secret")
    request = {"schema_version": "1.1", "memory_packs": load_history_payload(), "limit": 3}

    health_response = client.get("/health")
    missing = client.post("/v1/memories/discover-history", json=request)
    wrong = client.post(
        "/v1/memories/discover-history",
        json=request,
        headers={"X-MemoryOS-Proxy-Token": "wrong-secret"},
    )
    allowed = client.post(
        "/v1/memories/discover-history",
        json=request,
        headers={"X-MemoryOS-Proxy-Token": "server-only-secret"},
    )

    assert health_response.status_code == 200
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["code"] == "proxy_authentication_failed"
    assert "server-only-secret" not in missing.text
    assert allowed.status_code == 200


def test_openapi_exposes_v11_contracts_and_deprecated_legacy_route() -> None:
    schema = client.get("/openapi.json").json()

    legacy_operation = schema["paths"]["/v1/memories/discover"]["post"]
    assert legacy_operation["deprecated"] is True
    assert legacy_operation["responses"]["503"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ProviderErrorBody")
    assert "/v1/memories/discover-history" in schema["paths"]
    assert "/v1/memories/generate" in schema["paths"]
    for path in (
        "/v1/memories/generate",
        "/v1/memories/prepare-delivery",
        "/v1/memories/record-delivery-decision",
        "/v1/memories/generate-stream",
    ):
        assert schema["paths"][path]["post"]["deprecated"] is True
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
    stage_schema = schema["components"]["schemas"]["GenerateStreamStageEvent"]
    assert "observability" in stage_schema["properties"]


def test_v10_pack_uses_phase_2_metadata_on_generate() -> None:
    payload = json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))

    response = client.post(
        "/v1/memories/generate",
        json={"schema_version": "1.1", "memory_pack": payload},
    )

    assert response.status_code == 200
    metadata = response.json()["metadata"]
    assert metadata["pipeline_version"] == "phase-2-generation-v1"
    assert metadata["prompt_version"] == "narrative-scaffold-v1"
    assert metadata["narrative_boundary"] == "model-prose-deterministic-controls-v1"
    assert "factual_renderer" not in metadata


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


def test_review_gate_also_precedes_groq_provider_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORYOS_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    request = {"schema_version": "1.1", "memory_pack": load_history_payload()[1]}

    response = client.post("/v1/memories/generate", json=request)

    assert response.status_code == 200
    assert response.json()["status"] == "needs_source_verification"
    assert response.json()["metadata"]["provider"] == "groq"
    assert response.json()["metadata"]["mode"] == "live_ai"


def test_review_gate_also_precedes_gemini_provider_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORYOS_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    request = {"schema_version": "1.1", "memory_pack": load_history_payload()[1]}

    response = client.post("/v1/memories/generate", json=request)

    assert response.status_code == 200
    assert response.json()["status"] == "needs_source_verification"
    assert response.json()["metadata"]["provider"] == "gemini"
    assert response.json()["metadata"]["mode"] == "live_ai"


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


def test_stream_reports_the_actual_rejected_generation_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RejectedPerspectivePipeline:
        def generate(self, memory_pack: object):
            ready = MemoryPipeline().generate(memory_pack)
            validation = ready.validation.model_copy(
                update={
                    "passed": False,
                    "human_review_required": True,
                    "issues": [
                        ValidationIssue(
                            code="event_action_mismatch",
                            severity=IssueSeverity.ERROR,
                            message="A perspective used an action outside its evidence scope.",
                        )
                    ],
                }
            )
            return ready.model_copy(
                update={
                    "status": PipelineStatusV11.REJECTED,
                    "memory": None,
                    "player_perspectives": [],
                    "next_chapter": None,
                    "validation": validation,
                    "metadata": {**ready.metadata, "stopped_stage": "perspectives"},
                }
            )

    monkeypatch.setattr(api, "build_pipeline", lambda: RejectedPerspectivePipeline())
    response = client.post(
        "/v1/memories/generate-stream",
        json={"schema_version": "1.1", "memory_pack": load_history_payload()[0]},
    )

    events = [json.loads(line) for line in response.text.splitlines()]
    stage_states = [
        (event["stage"], event["status"]) for event in events if event["type"] == "stage"
    ]

    assert stage_states == [
        ("review_and_discovery", "working"),
        ("review_and_discovery", "complete"),
        ("memory_discovery", "complete"),
        ("perspectives", "stopped"),
        ("validation", "failed"),
    ]
    assert events[-1]["result"]["metadata"]["stopped_stage"] == "perspectives"
