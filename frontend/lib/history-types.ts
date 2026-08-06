/**
 * Public API aliases derived from `frontend/openapi.json`.
 *
 * Regenerate with `npm run generate:api-types` after exporting FastAPI's schema.
 */
import type { components } from "@/lib/api.generated";

export type MemoryPackV11 = components["schemas"]["MemoryPackV11"];
export type HistoricalCandidate = components["schemas"]["HistoricalCandidate"];
export type HistoricalDiscoveryRequest = components["schemas"]["HistoricalDiscoveryRequest"];
export type HistoricalDiscoveryResponse = components["schemas"]["HistoricalDiscoveryResponse"];
export type GenerateMemoryRequest = components["schemas"]["GenerateMemoryRequest"];
export type MemoryEngineResultV11 = components["schemas"]["MemoryEngineResultV11"];
export type ProviderErrorBody = components["schemas"]["ProviderErrorBody"];

export type ReadyMemoryResult = MemoryEngineResultV11 & {
  status: "ready";
  memory: NonNullable<MemoryEngineResultV11["memory"]>;
  next_chapter: NonNullable<MemoryEngineResultV11["next_chapter"]>;
};
