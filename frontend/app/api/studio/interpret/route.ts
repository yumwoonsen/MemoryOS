import rawTelemetry from "@/data/raw_telemetry_v2.json";
import { parseRawTelemetryBatchV2 } from "@/lib/ai-memory-contract";
import { isRecord, proxyMemoryOsPayload } from "@/lib/memoryos-server";
import { createStudioDemoResult } from "@/lib/studio-demo";

const configuredApi = process.env.MEMORYOS_API_URL?.trim();
const MAX_REQUEST_BYTES = 256_000;
const noStoreHeaders = { "cache-control": "no-store" };

function sampleResponse(reason: "hosted-sample" | "offline-studio-sample") {
  const result = createStudioDemoResult();
  if (!result) {
    return Response.json(
      {
        stage: "studio_demo",
        code: "sample_result_unavailable",
        retryable: false,
        message: "No safe fixed Studio demonstration is available.",
      },
      { status: 503, headers: { ...noStoreHeaders, "x-memoryos-mode": "sample", "x-memoryos-fallback": reason } },
    );
  }
  return Response.json(result, {
    headers: {
      "cache-control": "no-store",
      "x-memoryos-mode": "sample",
      "x-memoryos-fallback": reason,
    },
  });
}

export async function POST(request: Request) {
  const bodyText = await request.text();
  if (new TextEncoder().encode(bodyText).byteLength > MAX_REQUEST_BYTES) {
    return Response.json(
      { stage: "input", code: "telemetry_too_large", retryable: false, message: "The telemetry batch exceeds the Studio limit." },
      { status: 413, headers: noStoreHeaders },
    );
  }

  let body: unknown;
  try {
    body = JSON.parse(bodyText) as unknown;
  } catch {
    return Response.json(
      { stage: "input", code: "invalid_json", retryable: false, message: "The telemetry batch was not valid JSON." },
      { status: 400, headers: noStoreHeaders },
    );
  }
  const prototypeTelemetry = rawTelemetry as unknown;
  const telemetry = parseRawTelemetryBatchV2(body) ?? (
    isRecord(body)
      && typeof body.request_id === "string"
      && isRecord(prototypeTelemetry)
      && body.request_id === prototypeTelemetry.request_id
      ? parseRawTelemetryBatchV2(prototypeTelemetry)
      : null
  );
  if (!telemetry) {
    return Response.json(
      { stage: "input", code: "invalid_raw_telemetry_v2", retryable: false, message: "The telemetry did not match the v2 raw input contract." },
      { status: 422, headers: noStoreHeaders },
    );
  }

  const hostname = new URL(request.url).hostname;
  const isLocal = hostname === "localhost"
    || hostname === "127.0.0.1"
    || hostname === "[::1]";
  if (!configuredApi && !isLocal) return sampleResponse("hosted-sample");

  const response = await proxyMemoryOsPayload(telemetry, "/v2/memories/interpret-delivery");
  if (response.status === 503) {
    return sampleResponse("offline-studio-sample");
  }
  return response;
}
