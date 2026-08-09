import { isRecord, isTrustedLocalBrowserRequest } from "@/lib/memoryos-server";
import { compatibleStudioReplay } from "@/lib/studio-replay";
import {
  parseSafeStudioProviderFailure,
  studioProviderFailureMessage,
} from "@/lib/studio-provider-error";
import { proxyStudioScenarioEndpoint } from "@/lib/studio-scenario-server";
import {
  parseStudioScenarioDescriptor,
  parseStudioScenarioInterpretation,
  sameStudioScenarioVersion,
} from "@/lib/studio-scenarios";

const privateHeaders = { "cache-control": "no-store" };

export async function POST(request: Request) {
  if (!isTrustedLocalBrowserRequest(request)) {
    return Response.json(
      { stage: "studio_scenario", code: "local_browser_required", retryable: false, message: "Live Studio interpretation is available only from this local application." },
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
      { stage: "studio_scenario", code: "invalid_studio_scenario", retryable: false, message: "An exact prepared scenario is required." },
      { status: 422, headers: privateHeaders },
    );
  }

  const upstream = await proxyStudioScenarioEndpoint(
    `/v2/studio/scenarios/${encodeURIComponent(scenario.scenario_id)}/interpret`,
    "POST",
    130_000,
  );
  if (!upstream.ok) {
    if (upstream.status === 503) {
      const replay = compatibleStudioReplay(scenario);
      if (replay) {
        return Response.json(replay, {
          headers: {
            ...privateHeaders,
            "x-memoryos-mode": "saved-replay",
          },
        });
      }
      let upstreamFailure: unknown = null;
      try {
        upstreamFailure = await upstream.json();
      } catch {
        // A malformed 503 body must never escape the generic withheld boundary.
      }
      const providerFailure = parseSafeStudioProviderFailure(upstreamFailure);
      if (providerFailure) {
        return Response.json(
          {
            ...providerFailure,
            message: studioProviderFailureMessage(providerFailure.code),
          },
          { status: 503, headers: privateHeaders },
        );
      }
      return Response.json(
        {
          stage: "studio_scenario",
          code: "studio_live_run_withheld",
          retryable: false,
          message: "The live run failed and no compatible saved replay is available for this exact fixture version.",
        },
        { status: 503, headers: privateHeaders },
      );
    }
    return upstream;
  }

  const interpreted = parseStudioScenarioInterpretation(await upstream.json());
  if (!interpreted || !sameStudioScenarioVersion(scenario, interpreted.scenario)) {
    return Response.json(
      { stage: "studio_scenario", code: "scenario_version_mismatch", retryable: false, message: "The live result did not match the prepared scenario version." },
      { status: 502, headers: privateHeaders },
    );
  }
  if (interpreted.result.status === "pending_player_decision"
    && (interpreted.result.metadata.mode !== "live_ai"
      || interpreted.result.metadata.content_origin !== "live_ai_validated")) {
    return Response.json(
      {
        stage: "studio_scenario",
        code: "noncanonical_live_result",
        retryable: false,
        message: "The provider result was not a validated live-AI interpretation.",
      },
      { status: 502, headers: privateHeaders },
    );
  }
  const contentOrigin = interpreted.result.status === "pending_player_decision"
    ? "live_ai_validated"
    : "no_player_content";
  return Response.json(
    {
      ...interpreted,
      content_origin: contentOrigin,
      replay_provenance: null,
    },
    { headers: { ...privateHeaders, "x-memoryos-mode": "live" } },
  );
}
