import { getDemoResult } from "@/lib/demo-results";
import type { MemoryApiError, MemoryPack } from "@/lib/types";

const normalizedConfiguredApi = process.env.MEMORYOS_API_URL?.trim().replace(/\/+$/, "");
const configuredApi = normalizedConfiguredApi || undefined;
const backendApi = configuredApi ?? "http://127.0.0.1:8000";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isMemoryPackEnvelope(value: unknown): value is MemoryPack {
  return (
    isRecord(value) &&
    value.schema_version === "1.0" &&
    typeof value.pack_id === "string" &&
    isRecord(value.player_profile) &&
    typeof value.player_profile.player_id === "string" &&
    isRecord(value.squad) &&
    Array.isArray(value.squad.members) &&
    isRecord(value.match) &&
    Array.isArray(value.match_events)
  );
}

function shouldCallBackend(request: Request) {
  if (configuredApi) return true;

  const hostname = new URL(request.url).hostname;
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function sampleResponse(
  memoryPack: MemoryPack,
  reason: "hosted-sample" | "backend-unavailable",
) {
  const fallback = getDemoResult(memoryPack);
  if (!fallback) {
    return Response.json(
      {
        code: "sample_result_unavailable",
        message: "MemoryOS is unavailable and this pack has no demo result.",
      } satisfies MemoryApiError,
      {
        status: 503,
        headers: { "x-memoryos-mode": "sample" },
      },
    );
  }

  return Response.json(fallback, {
    headers: {
      "x-memoryos-mode": "sample",
      "x-memoryos-fallback": reason,
    },
  });
}

function normalizeBackendError(payload: unknown, status: number): MemoryApiError {
  if (payload && typeof payload === "object") {
    const value = payload as Record<string, unknown>;
    if (typeof value.message === "string") {
      return {
        code: typeof value.code === "string" ? value.code : "backend_request_failed",
        message: value.message,
      };
    }
    if (typeof value.detail === "string") {
      return { code: "backend_request_failed", message: value.detail };
    }
    if (value.detail && typeof value.detail === "object") {
      const detail = value.detail as Record<string, unknown>;
      if (typeof detail.message === "string") {
        return {
          code: typeof detail.code === "string" ? detail.code : "backend_request_failed",
          message: detail.message,
        };
      }
    }
  }

  return {
    code: status === 422 ? "memory_pack_validation_error" : "backend_request_failed",
    message:
      status === 422
        ? "The Memory Pack did not match the backend contract."
        : "MemoryOS could not process this Memory Pack.",
  };
}

export async function POST(request: Request) {
  let requestPayload: unknown;

  try {
    requestPayload = await request.json();
  } catch {
    return Response.json(
      {
        code: "invalid_memory_pack_json",
        message: "The Memory Pack was not valid JSON.",
      } satisfies MemoryApiError,
      {
        status: 400,
        headers: { "x-memoryos-mode": "sample" },
      },
    );
  }

  if (!isMemoryPackEnvelope(requestPayload)) {
    return Response.json(
      {
        code: "invalid_memory_pack",
        message: "The Memory Pack did not match the expected envelope.",
      } satisfies MemoryApiError,
      {
        status: 422,
        headers: { "x-memoryos-mode": "sample" },
      },
    );
  }

  const memoryPack = requestPayload;

  if (!shouldCallBackend(request)) {
    return sampleResponse(memoryPack, "hosted-sample");
  }

  let response: Response;
  try {
    response = await fetch(`${backendApi}/v1/memories/discover`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(memoryPack),
      signal: AbortSignal.timeout(20_000),
      cache: "no-store",
    });
  } catch {
    return sampleResponse(memoryPack, "backend-unavailable");
  }

  const responseText = await response.text();
  let payload: unknown;
  try {
    payload = JSON.parse(responseText) as unknown;
  } catch {
    return Response.json(
      {
        code: "upstream_invalid_response",
        message: "MemoryOS returned an unreadable response.",
      } satisfies MemoryApiError,
      {
        status: 502,
        headers: { "x-memoryos-mode": "live" },
      },
    );
  }

  if (!response.ok) {
    return Response.json(normalizeBackendError(payload, response.status), {
      status: response.status,
      headers: { "x-memoryos-mode": "live" },
    });
  }

  return Response.json(payload, {
    status: response.status,
    headers: { "x-memoryos-mode": "live" },
  });
}
