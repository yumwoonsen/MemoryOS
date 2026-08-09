"""Process-local delivery repository behavior used by mission rotation."""

from backend.models.v2_schemas import (
    MissionFamilyV2,
    MissionSelectionReasonCodeV2,
    MissionSelectionV2,
    StudioInterpretationTraceV2,
)
from backend.services.v2_delivery_repository import InMemoryV2DeliveryRepository


def _trace(trace_id: str, family: MissionFamilyV2) -> StudioInterpretationTraceV2:
    affordance_id = f"affordance:{family.value}:test"
    return StudioInterpretationTraceV2(
        trace_id=trace_id,
        stages=[],
        normalized_match_count=1,
        normalized_event_count=1,
        privacy_redaction_count=0,
        mission_selection=MissionSelectionV2(
            ranked_affordance_ids=[affordance_id],
            selected_affordance_id=affordance_id,
            selected_family=family,
            reason_codes=[MissionSelectionReasonCodeV2.DETERMINISTICALLY_VERIFIABLE],
        ),
    )


def test_repository_tracks_bounded_family_history_per_signal() -> None:
    repository = InMemoryV2DeliveryRepository()

    repository.register("delivery-1", _trace("trace-a", MissionFamilyV2.ROLE_REVERSAL))
    repository.register("delivery-2", _trace("trace-b", MissionFamilyV2.REDEMPTION))
    repository.register("delivery-3", _trace("trace-a", MissionFamilyV2.DUO_ASSIST))
    repository.register("delivery-4", _trace("trace-a", MissionFamilyV2.LANDING_RENDEZVOUS))

    assert repository.recent_mission_families("trace-a") == [
        MissionFamilyV2.DUO_ASSIST,
        MissionFamilyV2.LANDING_RENDEZVOUS,
    ]
    assert repository.recent_mission_families("trace-a", limit=1) == [
        MissionFamilyV2.LANDING_RENDEZVOUS
    ]
    assert repository.recent_mission_families("trace-b") == [MissionFamilyV2.REDEMPTION]
    assert repository.recent_mission_families("missing") == []


def test_repository_clear_removes_rotation_history() -> None:
    repository = InMemoryV2DeliveryRepository()
    repository.register("delivery-1", _trace("trace-a", MissionFamilyV2.ROLE_REVERSAL))

    repository.clear()

    assert repository.recent_mission_families("trace-a") == []


def test_repository_rejects_negative_history_limit() -> None:
    repository = InMemoryV2DeliveryRepository()

    try:
        repository.recent_mission_families("trace-a", limit=-1)
    except ValueError as error:
        assert str(error) == "limit must be non-negative"
    else:
        raise AssertionError("negative family-history limits must fail")
