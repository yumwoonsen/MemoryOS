import { isTrustedLocalBrowserRequest, proxyMemoryOs } from "@/lib/memoryos-server";

const privateHeaders = { "cache-control": "no-store", "x-memoryos-mode": "live" };

export async function POST(request: Request) {
  if (!isTrustedLocalBrowserRequest(request)) {
    return Response.json(
      {
        stage: "frontend_proxy",
        code: "local_browser_required",
        retryable: false,
        message: "Live AI generation is available only from this local application.",
      },
      { status: 403, headers: privateHeaders },
    );
  }
  return proxyMemoryOs(request, "/v1/memories/generate");
}
