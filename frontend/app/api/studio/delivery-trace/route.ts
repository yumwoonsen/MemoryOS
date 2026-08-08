import { isRecord, isSameOriginRequest, proxyMemoryOsGet } from "@/lib/memoryos-server";

const privateHeaders = { "cache-control": "no-store" };

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return Response.json(
      { code: "cross_origin_trace_request", message: "Studio traces are available only to this application." },
      { status: 403, headers: privateHeaders },
    );
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ code: "invalid_json", message: "The trace request was not valid JSON." }, { status: 400, headers: privateHeaders });
  }
  if (!isRecord(body) || typeof body.delivery_id !== "string" || body.delivery_id.length === 0) {
    return Response.json({ code: "invalid_delivery_id", message: "A valid delivery ID is required." }, { status: 422, headers: privateHeaders });
  }
  return proxyMemoryOsGet(`/v2/deliveries/${encodeURIComponent(body.delivery_id)}/trace`);
}
