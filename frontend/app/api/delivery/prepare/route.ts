import {
  consentSafeTelemetryView,
  isDeliveryBoundToTelemetryV2,
  parseInterpretDeliveryV2,
} from "@/lib/ai-memory-contract";
import {
  isRecord,
  isTrustedLocalBrowserRequest,
  proxyMemoryOsPayload,
} from "@/lib/memoryos-server";
import {
  projectNotGeneratedForPlayer,
  projectPendingDeliveryForPlayer,
} from "@/lib/player-delivery";
import { playerExperienceTelemetry } from "@/lib/player-scenario.server";

const privateHeaders = { "cache-control": "no-store", "x-memoryos-mode": "live" };

export async function POST(request: Request) {
  if (!isTrustedLocalBrowserRequest(request)) {
    return Response.json(
      {
        stage: "frontend_proxy",
        code: "local_browser_required",
        retryable: false,
        message: "Live AI memory preparation is available only from this local application.",
      },
      { status: 403, headers: privateHeaders },
    );
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { stage: "frontend_proxy", code: "invalid_json", retryable: false, message: "The request was not valid JSON." },
      { status: 400, headers: privateHeaders },
    );
  }

  const allowedBodyKeys = new Set(["experience_ref", "request_id"]);
  const telemetry = isRecord(body)
    && Object.keys(body).length === allowedBodyKeys.size
    && Object.keys(body).every((key) => allowedBodyKeys.has(key))
    ? playerExperienceTelemetry(body.experience_ref, body.request_id)
    : null;
  if (!telemetry) {
    return Response.json(
      {
        stage: "frontend_proxy",
        code: "invalid_player_experience",
        retryable: false,
        message: "A valid local player experience reference is required.",
      },
      { status: 422, headers: privateHeaders },
    );
  }
  const upstream = await proxyMemoryOsPayload(telemetry, "/v2/memories/interpret-delivery");
  if (!upstream.ok) return upstream;

  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return Response.json(
      { stage: "frontend_proxy", code: "invalid_live_delivery", retryable: true, message: "MemoryOS did not return a safe live delivery." },
      { status: 502, headers: privateHeaders },
    );
  }
  const parsed = parseInterpretDeliveryV2(payload);
  if (parsed?.status === "not_generated") {
    return Response.json(projectNotGeneratedForPlayer(telemetry.request_id), { headers: privateHeaders });
  }
  if (!parsed || parsed.status !== "pending_player_decision") {
    return Response.json(
      { stage: "delivery", code: "memory_withheld", retryable: false, message: "No fully grounded squad memory is available." },
      { status: 422, headers: privateHeaders },
    );
  }
  const safeTelemetry = consentSafeTelemetryView(telemetry);
  if (!isDeliveryBoundToTelemetryV2(parsed, safeTelemetry)) {
    return Response.json(
      { stage: "frontend_validation", code: "delivery_binding_failed", retryable: false, message: "The live delivery did not match the consent-safe telemetry." },
      { status: 502, headers: privateHeaders },
    );
  }
  const playerProjection = projectPendingDeliveryForPlayer(parsed, telemetry);
  if (!playerProjection) {
    return Response.json(
      { stage: "frontend_projection", code: "player_projection_failed", retryable: false, message: "The validated memory could not be projected safely." },
      { status: 502, headers: privateHeaders },
    );
  }
  return Response.json(playerProjection, { headers: privateHeaders });
}
