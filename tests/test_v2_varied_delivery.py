"""Focused coverage for bounded, pre-authoring v2 mission variation."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as api
from backend.main import app
from backend.models.v2_schemas import (
    CompactMemoryProposalV2,
    MissionFamilyV2,
    RawTelemetryBatchV2,
)
from backend.services.v2_delivery_repository import InMemoryV2DeliveryRepository
from backend.services.v2_interpreter import MemoryInterpreterV2
from backend.services.v2_mission_variation import MissionVariationDecisionV2
from backend.services.v2_preparation import TelemetryPreparerV2
from backend.v2_pipeline import MemoryInterpretationPipelineV2

DATA_ROOT = Path(__file__).resolve().parents[1] / "backend" / "data"
UNIFIED_PATH = DATA_ROOT / "v2_evaluation" / "unified_squad_history.json"
DEFAULT_PATH = DATA_ROOT / "raw_telemetry_v2.json"
NONCE = "generation-000001"
client = TestClient(app)


def _batch(path: Path = UNIFIED_PATH) -> RawTelemetryBatchV2:
    return RawTelemetryBatchV2.model_validate_json(path.read_text(encoding="utf-8"))


class _UnexpectedHistoryRepository(InMemoryV2DeliveryRepository):
    def recent_mission_families(self, trace_id: str, *, limit: int = 2):
        raise AssertionError("the default interpretation path must not consult rotation history")


class _StaticHistoryRepository(InMemoryV2DeliveryRepository):
    def __init__(self, history: list[object]) -> None:
        super().__init__()
        self.history = history
        self.history_calls: list[tuple[str, int]] = []

    def recent_mission_families(self, trace_id: str, *, limit: int = 2):
        self.history_calls.append((trace_id, limit))
        return self.history[-limit:]


class _SequenceGenerator:
    provider_name = "test-live"
    model_name = "typed-fixture"

    def __init__(self, proposal: CompactMemoryProposalV2) -> None:
        self.proposal = proposal
        self.calls = 0

    @property
    def observability(self) -> dict[str, object]:
        return {"calls": self.calls}

    def generate(self, **_: object) -> CompactMemoryProposalV2:
        self.calls += 1
        return self.proposal


def test_default_pipeline_path_is_unchanged_and_does_not_consult_history() -> None:
    batch = _batch(DEFAULT_PATH)
    expected = TelemetryPreparerV2().prepare(batch)
    pipeline = MemoryInterpretationPipelineV2(repository=_UnexpectedHistoryRepository())

    result = pipeline.interpret_delivery(batch)

    assert result.status == "pending_player_decision"
    assert [item.affordance_id for item in result.studio_trace.mission_affordances] == [
        item.affordance_id for item in expected.mission_affordances
    ]
    assert "mission_variation" not in result.metadata


def test_variation_filters_the_exact_top_three_distinct_non_recent_families() -> None:
    batch = _batch()
    prepared = TelemetryPreparerV2().prepare(batch)
    by_family: dict[MissionFamilyV2, list[str]] = {}
    for affordance in prepared.mission_affordances:
        by_family.setdefault(affordance.family, []).append(affordance.affordance_id)
    expected_ids = [
        by_family[MissionFamilyV2.DUO_ASSIST][0],
        by_family[MissionFamilyV2.LANDING_RENDEZVOUS][0],
        by_family[MissionFamilyV2.REDEMPTION][0],
    ]
    ranked_ids = [
        expected_ids[0],
        by_family[MissionFamilyV2.REUNION][0],
        expected_ids[1],
        by_family[MissionFamilyV2.ROLE_REVERSAL][0],
        expected_ids[2],
        *[
            affordance.affordance_id
            for affordance in prepared.mission_affordances
            if affordance.affordance_id
            not in {
                *expected_ids,
                by_family[MissionFamilyV2.REUNION][0],
                by_family[MissionFamilyV2.ROLE_REVERSAL][0],
            }
        ],
    ]

    class FixedPolicy:
        def select(self, *_: object, **__: object) -> MissionVariationDecisionV2:
            return MissionVariationDecisionV2(
                selected_affordance_id=expected_ids[0],
                selected_family=MissionFamilyV2.DUO_ASSIST,
                ranked_affordance_ids=tuple(ranked_ids),
                available_families=tuple(by_family),
                deferred_recent_families=(MissionFamilyV2.ROLE_REVERSAL,),
            )

    repository = _StaticHistoryRepository([MissionFamilyV2.ROLE_REVERSAL])
    pipeline = MemoryInterpretationPipelineV2(repository=repository)
    pipeline.variation_policy = FixedPolicy()  # type: ignore[assignment]

    filtered = pipeline._apply_mission_variation(prepared, generation_nonce=NONCE)

    assert [item.affordance_id for item in filtered.mission_affordances] == expected_ids
    assert len({item.family for item in filtered.mission_affordances}) == 3
    assert filtered.story_brief is not None
    assert filtered.story_brief.mission_affordances == filtered.mission_affordances
    assert filtered.story_brief.eligible_event_windows == filtered.windows
    assert filtered.story_brief.mission_candidates == filtered.mission_candidates
    assert repository.history_calls == [(TelemetryPreparerV2.trace_id(batch.request_id), 2)]


def test_same_seed_is_deterministic_and_history_prevents_an_immediate_repeat() -> None:
    batch = _batch()
    first_pipeline = MemoryInterpretationPipelineV2(repository=InMemoryV2DeliveryRepository())
    mirror_pipeline = MemoryInterpretationPipelineV2(repository=InMemoryV2DeliveryRepository())

    first = first_pipeline.interpret_delivery(batch, variation_seed=NONCE)
    mirror = mirror_pipeline.interpret_delivery(batch, variation_seed=NONCE)
    second = first_pipeline.interpret_delivery(batch, variation_seed=NONCE)

    assert first.status == mirror.status == second.status == "pending_player_decision"
    assert [item.affordance_id for item in first.studio_trace.mission_affordances] == [
        item.affordance_id for item in mirror.studio_trace.mission_affordances
    ]
    assert first.next_chapter is not None and mirror.next_chapter is not None
    assert second.next_chapter is not None
    assert first.next_chapter.family == mirror.next_chapter.family
    assert second.next_chapter.family != first.next_chapter.family
    assert first.metadata["mission_variation"] == {
        "policy": "MissionVariationPolicyV2",
        "pool_size": len(first.studio_trace.mission_affordances),
    }


def test_unknown_and_unavailable_history_values_are_ignored_safely() -> None:
    batch = _batch(DEFAULT_PATH)
    repository = _StaticHistoryRepository(["unknown_legacy_family", MissionFamilyV2.DUO_ASSIST])

    result = MemoryInterpretationPipelineV2(repository=repository).interpret_delivery(
        batch,
        variation_seed=NONCE,
    )

    available = {
        affordance.family for affordance in TelemetryPreparerV2().prepare(batch).mission_affordances
    }
    assert result.status == "pending_player_decision"
    assert result.next_chapter is not None
    assert result.next_chapter.family in available
    assert all(
        affordance.family in available for affordance in result.studio_trace.mission_affordances
    )


def test_live_provider_cannot_select_an_affordance_outside_the_filtered_pool() -> None:
    batch = _batch()
    unfiltered = TelemetryPreparerV2().prepare(batch)
    escaped = MemoryInterpreterV2().demo_compact_proposal(unfiltered)
    escaped_family = next(
        affordance.family
        for affordance in unfiltered.mission_affordances
        if affordance.affordance_id == escaped.mission.selected_affordance_id
    )
    repository = _StaticHistoryRepository([escaped_family])
    generator = _SequenceGenerator(escaped)

    result = MemoryInterpretationPipelineV2(
        generator,
        repository=repository,
    ).interpret_delivery(batch, variation_seed=NONCE)

    assert all(
        affordance.family != escaped_family
        for affordance in result.studio_trace.mission_affordances
    )
    assert result.status == "rejected"
    assert result.delivery_id is None
    assert result.next_chapter is None
    assert {
        "invented_mission_affordance",
        "mission_affordance_ranking_invalid",
    } & set(result.reason_codes)


def test_varied_delivery_api_requires_nested_telemetry_and_a_bounded_nonce(
    monkeypatch,
) -> None:
    batch_payload = json.loads(UNIFIED_PATH.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        api,
        "_build_configured_v2_pipeline",
        lambda: MemoryInterpretationPipelineV2(repository=InMemoryV2DeliveryRepository()),
    )

    response = client.post(
        "/v2/memories/interpret-varied-delivery",
        json={"telemetry": batch_payload, "generation_nonce": NONCE},
    )
    short_nonce = client.post(
        "/v2/memories/interpret-varied-delivery",
        json={"telemetry": batch_payload, "generation_nonce": "too-short"},
    )
    extra_field = client.post(
        "/v2/memories/interpret-varied-delivery",
        json={
            "telemetry": batch_payload,
            "generation_nonce": NONCE,
            "mission_family": "duo_assist",
        },
    )

    assert response.status_code == 200
    assert response.json()["metadata"]["mission_variation"]["pool_size"] <= 3
    assert short_nonce.status_code == 422
    assert extra_field.status_code == 422
