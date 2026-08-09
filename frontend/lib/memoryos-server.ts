import type { ProviderErrorBody } from "@/lib/history-types";

const normalizedConfiguredApi = process.env.MEMORYOS_API_URL?.trim().replace(/\/+$/, "");
const backendApi = normalizedConfiguredApi || "http://127.0.0.1:8000";
const proxyToken = process.env.MEMORYOS_PROXY_TOKEN?.trim();
// One Gemini attempt can take up to 60 seconds and MemoryOS may make one
// explicit semantic correction. Keep the trusted proxy alive for that bounded
// path instead of aborting a valid correction at the old 90-second ceiling.
const GENERATION_TIMEOUT_MS = 130_000;

function proxyResponseHeaders() {
  return { "cache-control": "no-store", "x-memoryos-mode": "live" };
}

function proxyTransportFailure(error: unknown) {
  const timedOut = error instanceof Error && error.name === "TimeoutError";
  return Response.json(
    timedOut
      ? {
          stage: "frontend_proxy",
          code: "generation_timeout",
          retryable: true,
          message: "MemoryOS did not finish within the bounded generation window.",
        }
      : {
          stage: "frontend_proxy",
          code: "backend_unavailable",
          retryable: true,
          message: "The configured MemoryOS backend is unavailable. Start it and try again.",
        },
    { status: 503, headers: proxyResponseHeaders() },
  );
}

export function backendUrl(path: string) {
  return `${backendApi}${path}`;
}

export function backendRequestHeaders({ json = true }: { json?: boolean } = {}) {
  const headers = new Headers();
  if (json) headers.set("content-type", "application/json");
  if (proxyToken) headers.set("x-memoryos-proxy-token", proxyToken);
  return headers;
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
    return Response.json({ stage: "frontend_proxy", code: "invalid_json", retryable: false, message: "The request was not valid JSON." }, { status: 400, headers: proxyResponseHeaders() });
  }
  return proxyMemoryOsPayload(body, path);
}

export async function proxyMemoryOsPayload(body: unknown, path: string): Promise<Response> {
  try {
    const response = await fetch(backendUrl(path), {
      method: "POST",
      headers: backendRequestHeaders(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(GENERATION_TIMEOUT_MS),
      cache: "no-store",
    });
    const text = await response.text();
    let payload: unknown;
    try { payload = JSON.parse(text); } catch {
      return Response.json({ stage: "frontend_proxy", code: "upstream_invalid_response", retryable: true, message: "MemoryOS returned an unreadable response." }, { status: 502, headers: proxyResponseHeaders() });
    }
    return response.ok
      ? Response.json(payload, { status: response.status, headers: proxyResponseHeaders() })
      : Response.json(errorResponse(payload, response.status), { status: response.status, headers: proxyResponseHeaders() });
  } catch (error) {
    return proxyTransportFailure(error);
  }
}

export function isSameOriginRequest(request: Request) {
  const requestUrl = new URL(request.url);
  const origin = request.headers.get("origin");
  if (origin && origin !== requestUrl.origin) return false;
  const fetchSite = request.headers.get("sec-fetch-site");
  return !fetchSite || fetchSite === "same-origin";
}

export async function proxyMemoryOsGet(path: string): Promise<Response> {
  try {
    const response = await fetch(backendUrl(path), {
      method: "GET",
      headers: backendRequestHeaders({ json: false }),
      signal: AbortSignal.timeout(GENERATION_TIMEOUT_MS),
      cache: "no-store",
    });
    const text = await response.text();
    let payload: unknown;
    try { payload = JSON.parse(text); } catch {
      return Response.json({ stage: "frontend_proxy", code: "upstream_invalid_response", retryable: true, message: "MemoryOS returned an unreadable response." }, { status: 502, headers: proxyResponseHeaders() });
    }
    return response.ok
      ? Response.json(payload, { status: response.status, headers: proxyResponseHeaders() })
      : Response.json(errorResponse(payload, response.status), { status: response.status, headers: proxyResponseHeaders() });
  } catch (error) {
    return proxyTransportFailure(error);
  }
}
