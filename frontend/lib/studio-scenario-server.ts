import {
  backendRequestHeaders,
  backendUrl,
  errorResponse,
} from "@/lib/memoryos-server";

const noStoreHeaders = { "cache-control": "no-store", "x-memoryos-mode": "live" };

export async function proxyStudioScenarioEndpoint(
  path: string,
  method: "GET" | "POST",
  timeoutMs: number,
) {
  try {
    const response = await fetch(backendUrl(path), {
      method,
      headers: backendRequestHeaders({ json: false }),
      signal: AbortSignal.timeout(timeoutMs),
      cache: "no-store",
    });
    const text = await response.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      return Response.json(
        {
          stage: "studio_scenario",
          code: "invalid_scenario_response",
          retryable: true,
          message: "MemoryOS returned an unreadable Studio scenario response.",
        },
        { status: 502, headers: noStoreHeaders },
      );
    }
    return response.ok
      ? Response.json(payload, { status: response.status, headers: noStoreHeaders })
      : Response.json(errorResponse(payload, response.status), {
          status: response.status,
          headers: noStoreHeaders,
        });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return Response.json(
      {
        stage: "studio_scenario",
        code: timedOut ? "studio_scenario_timeout" : "backend_unavailable",
        retryable: true,
        message: timedOut
          ? "The Studio scenario request exceeded its bounded time window."
          : "The configured MemoryOS backend is unavailable.",
      },
      { status: 503, headers: noStoreHeaders },
    );
  }
}
