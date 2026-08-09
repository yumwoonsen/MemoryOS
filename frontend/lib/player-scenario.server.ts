import unifiedSquadHistoryFixture from "@/data/player-scenarios/unified_squad_history.json";
import {
  parseRawTelemetryBatchV2,
  type RawTelemetryBatchV2,
} from "@/lib/ai-memory-contract";
import type { PlayerExperienceRef } from "@/lib/player-scenarios";
import {
  projectTelemetryForPlayerStart,
  type PlayerExperienceSeedV2,
} from "@/lib/player-delivery";

const PLAYER_EXPERIENCE_REF: PlayerExperienceRef = "squad-signal-01";

function requirePlayerTelemetryFixture(): RawTelemetryBatchV2 {
  const telemetry = parseRawTelemetryBatchV2(unifiedSquadHistoryFixture);
  if (!telemetry) {
    throw new Error("Invalid unified player squad-history fixture.");
  }
  return telemetry;
}

const unifiedTelemetry = requirePlayerTelemetryFixture();

// This is the only raw-telemetry registry for the player app. It stays in a
// server-only module and is resolved only after an exact opaque-ref/request-id
// binding check.
const playerExperienceRegistry = new Map<PlayerExperienceRef, RawTelemetryBatchV2>([
  [PLAYER_EXPERIENCE_REF, unifiedTelemetry],
]);

export function playerExperienceSeed(): PlayerExperienceSeedV2 {
  return projectTelemetryForPlayerStart(unifiedTelemetry, PLAYER_EXPERIENCE_REF);
}

export function playerExperienceTelemetry(
  experienceRef: unknown,
  requestId: unknown,
): RawTelemetryBatchV2 | null {
  if (experienceRef !== PLAYER_EXPERIENCE_REF || typeof requestId !== "string") return null;
  const telemetry = playerExperienceRegistry.get(PLAYER_EXPERIENCE_REF);
  if (!telemetry) return null;
  return telemetry.request_id === requestId ? telemetry : null;
}
