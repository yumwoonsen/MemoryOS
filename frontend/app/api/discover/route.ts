import { getDemoResult } from "@/lib/demo-results";
import type { MemoryPack } from "@/lib/types";

const configuredApi = process.env.MEMORYOS_API_URL;
const localApi = configuredApi ?? "http://127.0.0.1:8000";

function shouldCallBackend(request: Request) {
  if (configuredApi) return true;

  const hostname = new URL(request.url).hostname;
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function sampleResponse(memoryPack: MemoryPack) {
  const fallback = getDemoResult(memoryPack);
  if (!fallback) {
    return Response.json(
      { message: "MemoryOS is unavailable and this pack has no demo result." },
      { status: 503 },
    );
  }

  return Response.json(fallback, {
    headers: { "x-memoryos-mode": "sample" },
  });
}

export async function POST(request: Request) {
  let memoryPack: MemoryPack;

  try {
    memoryPack = (await request.json()) as MemoryPack;
  } catch {
    return Response.json({ message: "The Memory Pack was not valid JSON." }, { status: 400 });
  }

  if (!shouldCallBackend(request)) {
    return sampleResponse(memoryPack);
  }

  try {
    const response = await fetch(`${localApi}/v1/memories/discover`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(memoryPack),
      signal: AbortSignal.timeout(2500),
      cache: "no-store",
    });
    const payload = await response.json();

    return Response.json(payload, {
      status: response.status,
      headers: {
        "x-memoryos-mode": "live",
      },
    });
  } catch {
    return sampleResponse(memoryPack);
  }
}
