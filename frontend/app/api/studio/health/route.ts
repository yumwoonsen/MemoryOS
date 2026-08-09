import type { DeveloperHealth } from "@/lib/types";
import { backendRequestHeaders } from "@/lib/memoryos-server";

const normalizedConfiguredApi = process.env.MEMORYOS_API_URL?.trim().replace(/\/+$/, "");
const configuredApi = normalizedConfiguredApi || undefined;
const backendApi = configuredApi ?? "http://127.0.0.1:8000";

function shouldCallBackend(request: Request) {
  if (configuredApi) return true;

  const hostname = new URL(request.url).hostname;
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

function sampleHealth(reason: "hosted-sample" | "backend-unavailable") {
  return Response.json(
    {
      status: "sample",
      mode: "sample",
      inference_mode: "unknown",
      provider: "not-configured",
      model: "not-configured",
      message:
        reason === "hosted-sample"
          ? "No MemoryOS backend is configured for this hosted Studio. Live interpretation is unavailable."
          : "The configured local MemoryOS backend is unavailable. Live interpretation is unavailable.",
    } satisfies DeveloperHealth,
    {
      headers: {
        "cache-control": "no-store",
        "x-memoryos-mode": "sample",
        "x-memoryos-fallback": reason,
      },
    },
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

export async function GET(request: Request) {
  if (!shouldCallBackend(request)) return sampleHealth("hosted-sample");

  let response: Response;
  try {
    response = await fetch(`${backendApi}/health`, {
      cache: "no-store",
      headers: backendRequestHeaders({ json: false }),
      signal: AbortSignal.timeout(5_000),
    });
  } catch {
    return sampleHealth("backend-unavailable");
  }

  const responseText = await response.text();
  let payload: unknown;
  try {
    payload = JSON.parse(responseText) as unknown;
  } catch {
    payload = undefined;
  }

  if (!response.ok || !isRecord(payload)) {
    const code =
      isRecord(payload) && typeof payload.code === "string"
        ? payload.code
        : "backend_health_failed";
    return Response.json(
      {
        status: "error",
        mode: "live",
        inference_mode: "unknown",
        provider: "unavailable",
        model: "unavailable",
        code,
        message: "The configured MemoryOS backend did not pass its health check.",
      } satisfies DeveloperHealth,
      {
        status: response.status >= 400 ? response.status : 503,
        headers: { "cache-control": "no-store", "x-memoryos-mode": "live" },
      },
    );
  }

  return Response.json(
    {
      status: "ok",
      mode: "live",
      inference_mode:
        payload.mode === "live_ai" || payload.mode === "deterministic"
          ? payload.mode
          : payload.provider === "deterministic"
            ? "deterministic"
            : "unknown",
      provider: typeof payload.provider === "string" ? payload.provider : "unknown",
      model: typeof payload.model === "string" ? payload.model : "unknown",
      message: "Connected to the live MemoryOS backend.",
    } satisfies DeveloperHealth,
    {
      headers: { "cache-control": "no-store", "x-memoryos-mode": "live" },
    },
  );
}
