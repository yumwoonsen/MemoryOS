import type { ProviderErrorBody } from "@/lib/history-types";

const normalizedConfiguredApi = process.env.MEMORYOS_API_URL?.trim().replace(/\/+$/, "");
const backendApi = normalizedConfiguredApi || "http://127.0.0.1:8000";

export function backendUrl(path: string) {
  return `${backendApi}${path}`;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

export function errorResponse(payload: unknown, status: number) {
  const fallback: ProviderErrorBody = {
    stage: "frontend_proxy",
    code: status === 422 ? "request_validation_error" : "backend_request_failed",
    retryable: status >= 500,
    message: status === 422
      ? "The MemoryOS request did not match the expected contract."
      : "MemoryOS could not complete this request.",
  };
  if (!isRecord(payload)) return fallback;
  return {
    stage: typeof payload.stage === "string" ? payload.stage : fallback.stage,
    code: typeof payload.code === "string" ? payload.code : fallback.code,
    retryable: typeof payload.retryable === "boolean" ? payload.retryable : fallback.retryable,
    message: typeof payload.message === "string" ? payload.message : fallback.message,
  } satisfies ProviderErrorBody;
}

export async function proxyMemoryOs(request: Request, path: string): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ stage: "frontend_proxy", code: "invalid_json", retryable: false, message: "The request was not valid JSON." }, { status: 400 });
  }
  try {
    const response = await fetch(backendUrl(path), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(20_000),
      cache: "no-store",
    });
    const text = await response.text();
    let payload: unknown;
    try { payload = JSON.parse(text); } catch {
      return Response.json({ stage: "frontend_proxy", code: "upstream_invalid_response", retryable: true, message: "MemoryOS returned an unreadable response." }, { status: 502 });
    }
    return response.ok
      ? Response.json(payload, { status: response.status, headers: { "x-memoryos-mode": "live" } })
      : Response.json(errorResponse(payload, response.status), { status: response.status, headers: { "x-memoryos-mode": "live" } });
  } catch {
    return Response.json({ stage: "frontend_proxy", code: "backend_unavailable", retryable: true, message: "MemoryOS is unavailable. Start the deterministic backend and try again." }, { status: 503 });
  }
}
