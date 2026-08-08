import { isRecord, proxyMemoryOsPayload } from "@/lib/memoryos-server";

const privateHeaders = { "cache-control": "no-store" };

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json(
      { stage: "frontend_proxy", code: "invalid_json", retryable: false, message: "The request was not valid JSON." },
      { status: 400, headers: privateHeaders },
    );
  }
  if (!isRecord(payload) || typeof payload.delivery_id !== "string" || payload.delivery_id.length === 0) {
    return Response.json(
      { stage: "frontend_proxy", code: "invalid_delivery_id", retryable: false, message: "A valid delivery ID is required." },
      { status: 422, headers: privateHeaders },
    );
  }
  const { delivery_id: deliveryId, ...decision } = payload;
  return proxyMemoryOsPayload(
    decision,
    `/v2/deliveries/${encodeURIComponent(deliveryId)}/decision`,
  );
}
