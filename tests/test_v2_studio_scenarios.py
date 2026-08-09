"""Registered Developer Studio scenario contracts and quota-safe preparation tests."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as api
from backend.main import app
from backend.models.v2_schemas import MissionFamilyV2
from backend.services.v2_interpreter import MemoryInterpreterV2
from backend.services.v2_preparation import TelemetryPreparerV2
from backend.services.v2_studio_scenarios import studio_scenario_registry_v2
from backend.v2_pipeline import MemoryInterpretationPipelineV2

client = TestClient(app)
BACKEND_DATA = Path(__file__).resolve().parents[1] / "backend" / "data"

EXPECTED_SCENARIOS = {
    "rescue-role-reversal": ("pending_player_decision", "role_reversal"),
    "repeated-near-miss": ("pending_player_decision", "redemption"),
    "ordinary-sparse-telemetry": ("not_generated", None),
}


def test_studio_catalog_uses_three_manifest_backed_fixtures() -> None:
    response = client.get("/v2/studio/scenarios")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "2.1"
    assert {
        item["scenario_id"]: (
            item["expected_status"],
            item["expected_mission_family"],
        )
        for item in body["scenarios"]
    } == EXPECTED_SCENARIOS
    assert all(item["label_source"] == "offline_evaluation_manifest" for item in body["scenarios"])
    assert all(len(item["fixture_sha256"]) == 64 for item in body["scenarios"])
    assert all(
        item["fixture_revision"] == f"2.1:{item['fixture_sha256'][:12]}"
        for item in body["scenarios"]
    )

    rescue_bytes = (BACKEND_DATA / "raw_telemetry_v2.json").read_bytes()
    rescue = next(
        item for item in body["scenarios"] if item["scenario_id"] == "rescue-role-reversal"
    )
    assert rescue["fixture_sha256"] == sha256(rescue_bytes).hexdigest()


@pytest.mark.parametrize(
    ("scenario_id", "expected_families"),
    [
        ("rescue-role-reversal", {"reunion", "role_reversal"}),
        ("repeated-near-miss", {"reunion", "redemption"}),
        ("ordinary-sparse-telemetry", {"reunion"}),
    ],
)
def test_studio_prepare_is_provider_free_and_exposes_neutral_preparation(
    scenario_id: str,
    expected_families: set[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def provider_pipeline_must_not_be_built():
        raise AssertionError("the deterministic Studio preparation route touched the provider")

    monkeypatch.setattr(api, "_build_configured_v2_pipeline", provider_pipeline_must_not_be_built)

    response = client.post(f"/v2/studio/scenarios/{scenario_id}/prepare")

    assert response.status_code == 200
    body = response.json()
    assert body["scenario"]["scenario_id"] == scenario_id
    assert body["status"] == "ready"
    assert body["normalization"]["normalized_match_count"] >= 1
    assert body["normalization"]["normalized_event_count"] >= 1
    assert body["normalization"]["issue_codes"] == []
    assert (
        body["telemetry_summary"]["raw_event_count"]
        >= body["normalization"]["normalized_event_count"]
    )
    assert body["eligible_windows"]
    assert body["mission_candidates"]
    assert {item["family"] for item in body["mission_affordances"]} == expected_families
    assert "story_brief" not in body
    assert "evidence_ledger" not in body


def test_evaluation_labels_never_enter_telemetry_story_brief_or_provider_payload() -> None:
    registered = studio_scenario_registry_v2.get("rescue-role-reversal")
    prepared = TelemetryPreparerV2().prepare(registered.telemetry)
    assert prepared.story_brief is not None

    forbidden_keys = {
        "scenario_id",
        "title",
        "purpose",
        "fixture_sha256",
        "fixture_revision",
        "expected_status",
        "expected_mission_family",
        "label_source",
    }
    telemetry_keys = _recursive_keys(registered.telemetry.model_dump(mode="json"))
    brief_keys = _recursive_keys(prepared.story_brief.model_dump(mode="json"))
    provider_keys = _recursive_keys(MemoryInterpreterV2._provider_payload(prepared))

    assert not (forbidden_keys & telemetry_keys)
    assert not (forbidden_keys & brief_keys)
    assert not (forbidden_keys & provider_keys)


def test_studio_interpret_uses_only_the_exact_registered_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []

    class CapturingPipeline:
        def interpret_delivery(self, telemetry):
            captured.append(telemetry)
            return MemoryInterpretationPipelineV2().interpret_delivery(telemetry)

    monkeypatch.setattr(api, "_build_configured_v2_pipeline", CapturingPipeline)

    response = client.post("/v2/studio/scenarios/rescue-role-reversal/interpret")

    assert response.status_code == 200
    body = response.json()
    assert body["scenario"]["scenario_id"] == "rescue-role-reversal"
    assert body["result"]["request_id"] == "req-ff-20260808-001"
    assert body["result"]["status"] == "pending_player_decision"
    assert body["result"]["next_chapter"]["family"] == MissionFamilyV2.ROLE_REVERSAL
    assert captured == [studio_scenario_registry_v2.get("rescue-role-reversal").telemetry]


@pytest.mark.parametrize("operation", ["prepare", "interpret"])
def test_named_studio_routes_reject_unknown_scenarios_and_request_bodies(
    operation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def provider_pipeline_must_not_be_built():
        raise AssertionError("invalid Studio requests must stop before provider setup")

    monkeypatch.setattr(api, "_build_configured_v2_pipeline", provider_pipeline_must_not_be_built)

    unknown = client.post(f"/v2/studio/scenarios/not-registered/{operation}")
    substituted = client.post(
        f"/v2/studio/scenarios/rescue-role-reversal/{operation}",
        json={"request_id": "substituted-telemetry"},
    )

    assert unknown.status_code == 404
    assert unknown.json()["code"] == "unknown_studio_scenario"
    assert substituted.status_code == 422
    assert substituted.json()["code"] == "studio_request_body_not_allowed"


def test_studio_scenario_post_routes_honor_the_proxy_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORYOS_PROXY_TOKEN", "studio-proxy-only")

    catalog = client.get("/v2/studio/scenarios")
    missing = client.post("/v2/studio/scenarios/rescue-role-reversal/prepare")
    allowed = client.post(
        "/v2/studio/scenarios/rescue-role-reversal/prepare",
        headers={"X-MemoryOS-Proxy-Token": "studio-proxy-only"},
    )

    assert catalog.status_code == 200
    assert missing.status_code == 401
    assert missing.json()["code"] == "proxy_authentication_failed"
    assert allowed.status_code == 200


def test_openapi_describes_bodyless_studio_scenario_operations() -> None:
    schema = client.get("/openapi.json").json()

    assert "/v2/studio/scenarios" in schema["paths"]
    for operation in ("prepare", "interpret"):
        endpoint = schema["paths"][f"/v2/studio/scenarios/{{scenario_id}}/{operation}"]["post"]
        assert "requestBody" not in endpoint
    assert "StudioScenarioCatalogV2" in schema["components"]["schemas"]
    assert "StudioScenarioPreparationV2" in schema["components"]["schemas"]
    assert "StudioScenarioInterpretationV2" in schema["components"]["schemas"]


def _recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key for nested in value.values() for nested_key in _recursive_keys(nested)
        }
    if isinstance(value, list):
        return {nested_key for nested in value for nested_key in _recursive_keys(nested)}
    return set()
