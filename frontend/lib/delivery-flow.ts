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

export function playerPreparationError(value: unknown) {
  const code = value && typeof value === "object" && !Array.isArray(value)
    && typeof (value as Record<string, unknown>).code === "string"
    ? (value as Record<string, unknown>).code as string
    : null;

  if (code === "memory_withheld") {
    return "MemoryOS withheld this draft because it did not pass the grounding checks.";
  }
  if (code === "provider_rate_limited" || code === "provider_quota_exhausted") {
    return "The live memory service has reached its current usage limit. Try again after the limit resets.";
  }
  if (code === "provider_authentication_failed" || code === "missing_api_key") {
    return "The live memory service is not configured correctly right now.";
  }
  if (code === "provider_timeout" || code === "generation_timeout") {
    return "The live memory service took too long to finish. Try again once.";
  }
  if (code === "provider_unavailable") {
    return "The live AI service is temporarily unavailable. Try again shortly.";
  }
  if (code === "backend_unavailable") {
    return "The MemoryOS service is not reachable right now.";
  }
  if (code === "provider_output_limit" || code === "provider_invalid_response") {
    return "The AI response was incomplete, so MemoryOS withheld it safely.";
  }
  return "Your squad memory is not available right now.";
}

export function playerPreparationRetryable(value: unknown) {
  return Boolean(
    value
    && typeof value === "object"
    && !Array.isArray(value)
    && (value as Record<string, unknown>).retryable === true,
  );
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
  return delivery.metadata.content_origin === "live_ai_validated"
    ? "AI-prepared · evidence-checked"
    : undefined;
}

export function challengeTitle(title: string) {
  return title.split(":").at(-1)?.trim() || title;
}
