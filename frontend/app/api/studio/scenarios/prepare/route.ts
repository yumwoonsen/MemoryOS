import { isRecord, isSameOriginRequest } from "@/lib/memoryos-server";
import { proxyStudioScenarioEndpoint } from "@/lib/studio-scenario-server";
import {
  parseStudioScenarioDescriptor,
  parseStudioScenarioPreparation,
  sameStudioScenarioVersion,
} from "@/lib/studio-scenarios";

const privateHeaders = { "cache-control": "no-store" };

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return Response.json(
      { stage: "studio_scenario", code: "cross_origin_studio_request", retryable: false, message: "Studio preparation is same-origin only." },
      { status: 403, headers: privateHeaders },
    );
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { stage: "studio_scenario", code: "invalid_json", retryable: false, message: "The Studio request was not valid JSON." },
      { status: 400, headers: privateHeaders },
    );
  }
  const scenario = isRecord(body) && Object.keys(body).length === 1
    ? parseStudioScenarioDescriptor(body.scenario)
    : null;
  if (!scenario) {
    return Response.json(
      { stage: "studio_scenario", code: "invalid_studio_scenario", retryable: false, message: "An exact catalog scenario is required." },
      { status: 422, headers: privateHeaders },
    );
  }
  const upstream = await proxyStudioScenarioEndpoint(
    `/v2/studio/scenarios/${encodeURIComponent(scenario.scenario_id)}/prepare`,
    "POST",
    10_000,
  );
  if (!upstream.ok) return upstream;
  const preparation = parseStudioScenarioPreparation(await upstream.json());
  if (!preparation || !sameStudioScenarioVersion(scenario, preparation.scenario)) {
    return Response.json(
      { stage: "studio_scenario", code: "scenario_version_mismatch", retryable: false, message: "The prepared fixture did not match the selected scenario version." },
      { status: 502, headers: privateHeaders },
    );
  }
  return Response.json(preparation, { headers: privateHeaders });
}
