import rawTelemetry from "@/data/raw_telemetry_v2.json";
import {
  consentSafeTelemetryView,
  isDeliveryBoundToTelemetryV2,
  parseInterpretDeliveryV2,
  parseRawTelemetryBatchV2,
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

const prototypeTelemetry = parseRawTelemetryBatchV2(rawTelemetry as unknown);
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

  const submittedTelemetry = parseRawTelemetryBatchV2(body);
  const telemetry = submittedTelemetry ?? (
    isRecord(body)
      && typeof body.request_id === "string"
      && prototypeTelemetry
      && body.request_id === prototypeTelemetry.request_id
      ? prototypeTelemetry
      : null
  );
  if (!telemetry) {
    return Response.json(
      { stage: "frontend_proxy", code: "invalid_raw_telemetry_v2", retryable: false, message: "A valid v2 telemetry request is required." },
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
