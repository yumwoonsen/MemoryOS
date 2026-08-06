import { proxyMemoryOs } from "@/lib/memoryos-server";

export async function POST(request: Request) {
  return proxyMemoryOs(request, "/v1/memories/discover-history");
}
