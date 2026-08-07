"""Process-local decision capture for the hackathon delivery demo."""

from __future__ import annotations

from threading import Lock

from backend.models.schemas import (
    DeliveryDecision,
    DeliveryDeclineReason,
    RecordDeliveryDecisionResponse,
)


class DeliveryDecisionStore:
    def __init__(self) -> None:
        self._prepared: set[str] = set()
        self._decisions: dict[str, RecordDeliveryDecisionResponse] = {}
        self._lock = Lock()

    def register(self, delivery_id: str) -> None:
        with self._lock:
            self._prepared.add(delivery_id)

    def record(
        self,
        delivery_id: str,
        decision: DeliveryDecision,
        decline_reason: DeliveryDeclineReason | None,
    ) -> RecordDeliveryDecisionResponse | None:
        with self._lock:
            if delivery_id not in self._prepared:
                return None
            response = RecordDeliveryDecisionResponse(
                delivery_id=delivery_id,
                decision=decision,
                decline_reason=decline_reason,
            )
            self._decisions[delivery_id] = response
            return response


delivery_decision_store = DeliveryDecisionStore()
