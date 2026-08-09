const providerFailureStages = new Set([
  "configuration",
  "memory_interpretation",
  "memory_interpretation_correction",
]);

const providerFailureRetryability = new Map<string, boolean>([
  ["invalid_output_token_limit", false],
  ["invalid_provider", false],
  ["live_ai_required", false],
  ["missing_api_key", false],
  ["provider_authentication_failed", false],
  ["provider_connection_error", true],
  ["provider_error", false],
  ["provider_invalid_response", false],
  ["provider_no_output", false],
  ["provider_output_limit", false],
  ["provider_permission_denied", false],
  ["provider_quota_exhausted", false],
  ["provider_rate_limited", true],
  ["provider_refusal", false],
  ["provider_request_rejected", false],
  ["provider_timeout", true],
  ["provider_unavailable", true],
  ["provider_unexpected_error", false],
]);

const providerFailureMessages = new Map<string, string>([
  ["invalid_output_token_limit", "The configured AI output limit is not valid."],
  ["invalid_provider", "The configured AI provider is not supported."],
  ["live_ai_required", "This Studio run requires a configured live AI provider."],
  ["missing_api_key", "The configured AI provider is missing its API key."],
  ["provider_authentication_failed", "The AI provider rejected the configured credentials."],
  ["provider_connection_error", "MemoryOS could not connect to the AI provider."],
  ["provider_error", "The AI provider could not complete this request."],
  ["provider_invalid_response", "The AI provider returned a response that did not match the required contract."],
  ["provider_no_output", "The AI provider returned no usable structured output."],
  ["provider_output_limit", "The AI provider reached the configured output limit before completing its response."],
  ["provider_permission_denied", "The AI provider account does not have permission to use this request."],
  ["provider_quota_exhausted", "The AI provider account has no remaining quota for this request."],
  ["provider_rate_limited", "The AI provider rate limit was reached. Wait for the limit to reset before running again."],
  ["provider_refusal", "The AI provider declined to produce the required structured response."],
  ["provider_request_rejected", "The AI provider rejected the request before interpretation could complete."],
  ["provider_timeout", "The AI provider did not respond within the bounded generation window."],
  ["provider_unavailable", "The AI provider is temporarily unavailable."],
  ["provider_unexpected_error", "The AI provider stopped for an unexpected, safely withheld reason."],
]);

export type SafeStudioProviderFailure = {
  stage: string;
  code: string;
  retryable: boolean;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

/**
 * Reduce a backend 503 to the same small public boundary used by replay capture.
 * Provider-authored messages and every unrecognised field are intentionally ignored.
 */
export function parseSafeStudioProviderFailure(value: unknown): SafeStudioProviderFailure | null {
  if (!isRecord(value)) return null;
  const { stage, code, retryable } = value;
  if (typeof stage !== "string" || !providerFailureStages.has(stage)) return null;
  if (typeof code !== "string") return null;
  const expectedRetryability = providerFailureRetryability.get(code);
  if (expectedRetryability === undefined || retryable !== expectedRetryability) return null;
  return { stage, code, retryable: expectedRetryability };
}

export function studioProviderFailureMessage(code: string) {
  return providerFailureMessages.get(code)
    ?? "The live AI provider could not complete this Studio run.";
}
