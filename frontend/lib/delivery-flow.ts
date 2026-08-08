import {
  isPlayerDeliveryBoundToTelemetryV2,
  parseDecisionConfirmationV2,
  parsePlayerPendingDeliveryV2,
} from "@/lib/ai-memory-contract";
import type {
  DecisionRequestV2,
  DeliveryDeclineReasonV2,
  DeliveryDecisionRecordV2,
  PlayerPendingDeliveryV2,
  RawTelemetryBatchV2,
} from "@/lib/ai-memory-contract";

export type PendingDelivery = PlayerPendingDeliveryV2;
export type DeliveryDeclineReason = DeliveryDeclineReasonV2;
export type DecisionRequest =
  | { decision: "accepted" }
  | { decision: "declined"; decline_reason: DeliveryDeclineReasonV2 };

export function decisionPayload(request: DecisionRequest): DecisionRequestV2 {
  return { schema_version: "2.0", ...request } as DecisionRequestV2;
}

export function isPendingDelivery(value: unknown): value is PendingDelivery {
  return Boolean(parsePlayerPendingDeliveryV2(value));
}

export function isDeliveryBoundToTelemetry(
  delivery: PendingDelivery,
  telemetry: RawTelemetryBatchV2,
) {
  return isPlayerDeliveryBoundToTelemetryV2(delivery, telemetry);
}

export function isDecisionConfirmation(
  value: unknown,
  deliveryId: string,
  request: DecisionRequest,
): value is DeliveryDecisionRecordV2 {
  return Boolean(parseDecisionConfirmationV2(value, deliveryId, decisionPayload(request)));
}

export function deliveryModeLabel(delivery: PendingDelivery) {
  return delivery.metadata.mode === "live_ai" ? "Live AI" : undefined;
}

export function challengeTitle(title: string) {
  return title.split(":").at(-1)?.trim() || title;
}
