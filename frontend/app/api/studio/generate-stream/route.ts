import { getDemoResult } from "@/lib/demo-results";
import { backendRequestHeaders, isTrustedLocalBrowserRequest } from "@/lib/memoryos-server";
import type {
  DeveloperErrorEvent,
  DeveloperMemoryEngineResult,
  DeveloperStreamEvent,
  MemoryPack,
} from "@/lib/types";

const normalizedConfiguredApi = process.env.MEMORYOS_API_URL?.trim().replace(/\/+$/, "");
const configuredApi = normalizedConfiguredApi || undefined;
const backendApi = configuredApi ?? "http://127.0.0.1:8000";
const MAX_REQUEST_BYTES = 256_000;
const MAX_STREAM_BYTES = 1_000_000;
const PROVIDER_TIMEOUT_MS = 90_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isBoundedString(value: unknown, maxLength: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= maxLength;
}

function isOptionalString(value: unknown, maxLength: number) {
  return value === undefined || value === null ||
    (typeof value === "string" && value.length <= maxLength);
}

function isNonNegativeInteger(value: unknown) {
  return Number.isInteger(value) && Number(value) >= 0;
}

function hasValidDetails(value: unknown) {
  return value === undefined ||
    (isRecord(value) &&
      Object.keys(value).length <= 16 &&
      Object.entries(value).every(
        ([key, detail]) =>
          key.length <= 64 &&
          (["string", "number", "boolean"].includes(typeof detail)) &&
          (typeof detail !== "string" || detail.length <= 100) &&
          (typeof detail !== "number" || Number.isFinite(detail)),
      ));
}

function isMemoryPackEnvelope(value: unknown): value is MemoryPack {
  if (
    !isRecord(value) ||
    (value.schema_version !== "1.0" && value.schema_version !== "1.1") ||
    !isBoundedString(value.pack_id, 128) ||
    !isRecord(value.player_profile) ||
    !isBoundedString(value.player_profile.player_id, 128) ||
    !isOptionalString(value.player_profile.preferred_role, 64) ||
    !isRecord(value.squad) ||
    !isBoundedString(value.squad.squad_id, 128) ||
    !Array.isArray(value.squad.members) ||
    value.squad.members.length < 2 ||
    value.squad.members.length > 4 ||
    !isNonNegativeInteger(value.squad.matches_together) ||
    !(value.squad.days_since_full_squad === undefined ||
      value.squad.days_since_full_squad === null ||
      isNonNegativeInteger(value.squad.days_since_full_squad)) ||
    !isRecord(value.match) ||
    !isBoundedString(value.match.match_id, 128) ||
    !isBoundedString(value.match.mode, 64) ||
    !isOptionalString(value.match.map_name, 100) ||
    !(value.match.placement === undefined || value.match.placement === null ||
      (Number.isInteger(value.match.placement) && Number(value.match.placement) >= 1)) ||
    !isOptionalString(value.match.played_at, 64) ||
    !Array.isArray(value.match_events) ||
    value.match_events.length > 100
  ) {
    return false;
  }

  const members = value.squad.members;
  if (
    !members.every(
      (member) =>
        isRecord(member) &&
        isBoundedString(member.player_id, 128) &&
        isBoundedString(member.display_name, 64) &&
        isOptionalString(member.role, 64) &&
        typeof member.opted_in === "boolean",
    )
  ) {
    return false;
  }

  const memberIds = members.map(
    (member) => (member as Record<string, unknown>).player_id as string,
  );
  const knownPlayers = new Set(memberIds);
  if (
    knownPlayers.size !== memberIds.length ||
    !knownPlayers.has(value.player_profile.player_id)
  ) {
    return false;
  }

  const events = value.match_events;
  if (
    !events.every(
      (event) =>
        isRecord(event) &&
        isBoundedString(event.event_id, 128) &&
        isBoundedString(event.type, 64) &&
        isOptionalString(event.actor_id, 128) &&
        isOptionalString(event.target_id, 128) &&
        (event.timestamp_seconds === undefined || event.timestamp_seconds === null ||
          isNonNegativeInteger(event.timestamp_seconds)) &&
        isOptionalString(event.location, 100) &&
        (event.importance === undefined || ["low", "medium", "high"].includes(String(event.importance))) &&
        hasValidDetails(event.details) &&
        (event.actor_id === undefined || event.actor_id === null || knownPlayers.has(event.actor_id as string)) &&
        (event.target_id === undefined || event.target_id === null || knownPlayers.has(event.target_id as string)),
    )
  ) {
    return false;
  }

  const eventIds = events.map((event) => (event as Record<string, unknown>).event_id as string);
  if (new Set(eventIds).size !== eventIds.length) return false;

  if (value.schema_version === "1.1") {
    if (
      !isRecord(value.human_review) ||
      !["unreviewed", "verified", "disputed"].includes(String(value.human_review.source_status)) ||
      !["unreviewed", "confirmed", "dismissed"].includes(String(value.human_review.meaning_status))
    ) {
      return false;
    }
  }

  return true;
}

function shouldCallBackend(request: Request) {
  if (configuredApi) return true;

  const hostname = new URL(request.url).hostname;
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function ndjsonResponse(
  events: DeveloperStreamEvent[],
  {
    mode,
    fallback,
    status = 200,
  }: {
    mode: "live" | "sample";
    fallback?: string;
    status?: number;
  },
) {
  const headers = new Headers({
    "cache-control": "no-store",
    "content-type": "application/x-ndjson; charset=utf-8",
    "x-content-type-options": "nosniff",
    "x-memoryos-mode": mode,
  });
  if (fallback) headers.set("x-memoryos-fallback", fallback);

  return new Response(`${events.map((event) => JSON.stringify(event)).join("\n")}\n`, {
    status,
    headers,
  });
}

function errorResponse(
  code: string,
  stage: string,
  {
    mode,
    status,
    retryable = false,
    fallback,
  }: {
    mode: "live" | "sample";
    status: number;
    retryable?: boolean;
    fallback?: string;
  },
) {
  return ndjsonResponse(
    [
      {
        type: "error",
        stage,
        code,
        retryable,
        message: "MemoryOS could not complete this Studio run.",
      },
    ],
    { mode, status, fallback },
  );
}

function sampleResponse(
  memoryPack: MemoryPack,
  reason: "hosted-sample" | "backend-unavailable",
) {
  const fallback = getDemoResult(memoryPack);
  if (!fallback) {
    return errorResponse("sample_result_unavailable", "configuration", {
      mode: "sample",
      status: 503,
      fallback: reason,
    });
  }

  const result = fallback as DeveloperMemoryEngineResult;
  const events: DeveloperStreamEvent[] = [
    {
      type: "stage",
      stage: "review_and_discovery",
      status: "working",
      message: "Replaying the saved pipeline snapshots for this synthetic pack.",
    },
  ];

  if (result.memory) {
    events.push(
      {
        type: "stage",
        stage: "memory_discovery",
        status: "complete",
        preview: result.memory,
      },
      {
        type: "stage",
        stage: "perspectives",
        status: "complete",
        preview: result.player_perspectives,
      },
      {
        type: "stage",
        stage: "quest_generation",
        status: "complete",
        preview: result.next_chapter ?? null,
      },
      {
        type: "stage",
        stage: "validation",
        status: result.validation.passed ? "complete" : "failed",
        preview: result.validation,
      },
    );
  } else {
    events.push({
      type: "stage",
      stage: "review_and_discovery",
      status: "stopped",
      message: `The saved result stopped with status ${result.status}.`,
    });
  }

  events.push({ type: "result", result });
  return ndjsonResponse(events, { mode: "sample", fallback: reason });
}

function normalizeProviderError(payload: unknown, status: number): DeveloperErrorEvent {
  if (isRecord(payload)) {
    return {
      type: "error",
      stage: typeof payload.stage === "string" ? payload.stage : "provider",
      code:
        typeof payload.code === "string"
          ? payload.code
          : status === 422
            ? "memory_pack_validation_error"
            : "provider_request_failed",
      retryable: payload.retryable === true,
      message: "The live backend could not complete this Studio run.",
    };
  }

  return {
    type: "error",
    stage: "provider",
    code: status === 422 ? "memory_pack_validation_error" : "upstream_invalid_response",
    retryable: status >= 500,
    message: "The live backend returned an unreadable response.",
  };
}

export async function POST(request: Request) {
  const callsBackend = shouldCallBackend(request);
  if (callsBackend && !isTrustedLocalBrowserRequest(request)) {
    return errorResponse("local_browser_required", "input", {
      mode: "live",
      status: 403,
    });
  }

  const declaredLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_REQUEST_BYTES) {
    return errorResponse("memory_pack_too_large", "input", {
      mode: "sample",
      status: 413,
    });
  }

  let requestText: string;
  try {
    requestText = await request.text();
  } catch {
    return errorResponse("memory_pack_read_failed", "input", {
      mode: "sample",
      status: 400,
    });
  }
  if (new TextEncoder().encode(requestText).byteLength > MAX_REQUEST_BYTES) {
    return errorResponse("memory_pack_too_large", "input", {
      mode: "sample",
      status: 413,
    });
  }

  let requestPayload: unknown;
  try {
    requestPayload = JSON.parse(requestText) as unknown;
  } catch {
    return errorResponse("invalid_memory_pack_json", "input", {
      mode: "sample",
      status: 400,
    });
  }

  if (!isMemoryPackEnvelope(requestPayload)) {
    return errorResponse("invalid_memory_pack", "input", {
      mode: "sample",
      status: 422,
    });
  }

  const memoryPack = requestPayload;
  if (!callsBackend) return sampleResponse(memoryPack, "hosted-sample");

  const upstreamController = new AbortController();
  const abortUpstream = () => upstreamController.abort(request.signal.reason);
  if (request.signal.aborted) abortUpstream();
  else request.signal.addEventListener("abort", abortUpstream, { once: true });
  const timeoutId = setTimeout(() => upstreamController.abort(), PROVIDER_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${backendApi}/v1/memories/generate-stream`, {
      method: "POST",
      headers: backendRequestHeaders(),
      body: JSON.stringify({ schema_version: "1.1", memory_pack: memoryPack }),
      signal: upstreamController.signal,
      cache: "no-store",
    });
  } catch {
    if (request.signal.aborted) {
      return errorResponse("request_cancelled", "provider", {
        mode: "live",
        status: 499,
      });
    }
    return sampleResponse(memoryPack, "backend-unavailable");
  } finally {
    clearTimeout(timeoutId);
    request.signal.removeEventListener("abort", abortUpstream);
  }

  if (!response.ok) {
    const responseText = await response.text();
    let payload: unknown;
    try {
      payload = JSON.parse(responseText) as unknown;
    } catch {
      payload = undefined;
    }
    return ndjsonResponse([normalizeProviderError(payload, response.status)], {
      mode: "live",
      status: response.status,
    });
  }

  if (!response.body) {
    return errorResponse("provider_no_stream", "provider", {
      mode: "live",
      status: 502,
      retryable: true,
    });
  }

  const declaredStreamLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredStreamLength) && declaredStreamLength > MAX_STREAM_BYTES) {
    return errorResponse("provider_stream_too_large", "provider", {
      mode: "live",
      status: 502,
    });
  }

  let streamedBytes = 0;
  const boundedStream = response.body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        streamedBytes += chunk.byteLength;
        if (streamedBytes > MAX_STREAM_BYTES) {
          controller.error(new Error("The provider stream exceeded the Studio response limit."));
          return;
        }
        controller.enqueue(chunk);
      },
    }),
  );

  return new Response(boundedStream, {
    status: response.status,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/x-ndjson; charset=utf-8",
      "x-content-type-options": "nosniff",
      "x-memoryos-mode": "live",
    },
  });
}
