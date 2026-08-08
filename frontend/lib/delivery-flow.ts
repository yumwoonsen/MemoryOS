import {
  parseDecisionConfirmationV2,
} from "@/lib/ai-memory-contract";
import type {
  DecisionRequestV2,
  DeliveryDeclineReasonV2,
  DeliveryDecisionRecordV2,
} from "@/lib/ai-memory-contract";
import {
  isPlayerDeliveryBoundToSeed,
  parsePlayerDeliveryResultV2,
} from "@/lib/player-delivery";
import type {
  PlayerDeliveryResultV2,
  PlayerExperienceSeedV2,
  PlayerPendingDeliveryProjectionV2,
} from "@/lib/player-delivery";

export type PendingDelivery = PlayerPendingDeliveryProjectionV2;
export type DeliveryDeclineReason = DeliveryDeclineReasonV2;
export type DecisionRequest =
  | { decision: "accepted" }
  | { decision: "declined"; decline_reason: DeliveryDeclineReasonV2 };

export function decisionPayload(request: DecisionRequest): DecisionRequestV2 {
  return { schema_version: "2.0", ...request } as DecisionRequestV2;
}

export function parsePlayerDelivery(value: unknown): PlayerDeliveryResultV2 | null {
  return parsePlayerDeliveryResultV2(value);
}

export function isDeliveryBoundToSeed(
  delivery: PendingDelivery,
  seed: PlayerExperienceSeedV2,
) {
  return isPlayerDeliveryBoundToSeed(delivery, seed);
}

export function isDecisionConfirmation(
  value: unknown,
  deliveryId: string,
  request: DecisionRequest,
): value is DeliveryDecisionRecordV2 {
  return Boolean(parseDecisionConfirmationV2(value, deliveryId, decisionPayload(request)));
}

export function deliveryModeLabel(delivery: PendingDelivery) {
  return delivery.metadata.content_origin === "live_ai_validated" ? "Live AI" : undefined;
}

export function challengeTitle(title: string) {
  return title.split(":").at(-1)?.trim() || title;
}
