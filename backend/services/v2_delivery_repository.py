"""Prototype repository boundary for v2 delivery decisions and judge traces.

The implementation is deliberately process-local.  The interface is the seam for future
authenticated, retention-reviewed persistence; it must not be described as durable storage.
"""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Protocol

from backend.models.schemas import DeliveryDecision, DeliveryDeclineReason
from backend.models.v2_schemas import (
    DeliveryDecisionRecordV2,
    StudioInterpretationTraceV2,
)


class V2DeliveryRepository(Protocol):
    def register(self, delivery_id: str, trace: StudioInterpretationTraceV2) -> None: ...

    def record_decision(
        self,
        delivery_id: str,
        decision: DeliveryDecision,
        decline_reason: DeliveryDeclineReason | None,
    ) -> DeliveryDecisionRecordV2 | None: ...

    def get_trace(self, delivery_id: str) -> StudioInterpretationTraceV2 | None: ...


class InMemoryV2DeliveryRepository:
    def __init__(self) -> None:
        self._traces: dict[str, StudioInterpretationTraceV2] = {}
        self._decisions: dict[str, DeliveryDecisionRecordV2] = {}
        self._lock = Lock()

    def register(self, delivery_id: str, trace: StudioInterpretationTraceV2) -> None:
        with self._lock:
            self._traces[delivery_id] = deepcopy(trace)

    def record_decision(
        self,
        delivery_id: str,
        decision: DeliveryDecision,
        decline_reason: DeliveryDeclineReason | None,
    ) -> DeliveryDecisionRecordV2 | None:
        with self._lock:
            if delivery_id not in self._traces:
                return None
            existing = self._decisions.get(delivery_id)
            if existing is not None:
                return deepcopy(existing)
            source_quality_flag = decline_reason == DeliveryDeclineReason.DETAILS_WRONG
            record = DeliveryDecisionRecordV2(
                delivery_id=delivery_id,
                decision=decision,
                decline_reason=decline_reason,
                delivery_status=(
                    "mission_started" if decision == DeliveryDecision.ACCEPTED else "suppressed"
                ),
                source_quality_flag=source_quality_flag,
            )
            self._decisions[delivery_id] = record
            trace = self._traces[delivery_id]
            stages = list(trace.stages)
            stages[-1] = stages[-1].model_copy(
                update={
                    "status": "complete",
                    "summary": (
                        "Player accepted the reunion mission."
                        if decision == DeliveryDecision.ACCEPTED
                        else "Player declined and this delivery was suppressed."
                    ),
                    "issue_codes": (["source_quality_feedback"] if source_quality_flag else []),
                }
            )
            self._traces[delivery_id] = trace.model_copy(
                update={
                    "stages": stages,
                    "source_quality_flag": source_quality_flag,
                }
            )
            return deepcopy(record)

    def get_trace(self, delivery_id: str) -> StudioInterpretationTraceV2 | None:
        with self._lock:
            trace = self._traces.get(delivery_id)
            return deepcopy(trace) if trace is not None else None

    def clear(self) -> None:
        """Test-only reset for process-local state."""

        with self._lock:
            self._traces.clear()
            self._decisions.clear()


v2_delivery_repository = InMemoryV2DeliveryRepository()
