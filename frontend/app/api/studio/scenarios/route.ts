import { isSameOriginRequest } from "@/lib/memoryos-server";
import { proxyStudioScenarioEndpoint } from "@/lib/studio-scenario-server";
import { parseStudioScenarioCatalog } from "@/lib/studio-scenarios";

const privateHeaders = { "cache-control": "no-store" };

export async function GET(request: Request) {
  if (!isSameOriginRequest(request)) {
    return Response.json(
      {
        stage: "studio_scenario",
        code: "cross_origin_studio_request",
        retryable: false,
        message: "Studio scenarios are available only to this application.",
      },
      { status: 403, headers: privateHeaders },
    );
  }
  const upstream = await proxyStudioScenarioEndpoint("/v2/studio/scenarios", "GET", 5_000);
  if (!upstream.ok) return upstream;
  const payload: unknown = await upstream.json();
  const catalog = parseStudioScenarioCatalog(payload);
  return catalog
    ? Response.json(catalog, { headers: privateHeaders })
    : Response.json(
        {
          stage: "studio_scenario",
          code: "invalid_scenario_catalog",
          retryable: false,
          message: "The Studio scenario catalog failed its frontend contract check.",
        },
        { status: 502, headers: privateHeaders },
      );
}
