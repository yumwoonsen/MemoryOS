import rescueTelemetryFixture from "@/data/raw_telemetry_v2.json";
import duoAssistTelemetryFixture from "@/data/player-scenarios/duo_assist.json";
import landingRendezvousTelemetryFixture from "@/data/player-scenarios/landing_rendezvous.json";
import repeatedNearMissTelemetryFixture from "@/data/player-scenarios/repeated_near_miss.json";
import {
  parseRawTelemetryBatchV2,
  type RawTelemetryBatchV2,
} from "@/lib/ai-memory-contract";
import {
  isPlayerExperienceRef,
  playerExperienceRefs,
  type PlayerExperienceRef,
} from "@/lib/player-scenarios";
import {
  projectTelemetryForPlayerStart,
  type PlayerExperienceSeedV2,
} from "@/lib/player-delivery";

const fixtureByExperience: Record<PlayerExperienceRef, unknown> = {
  "memory-01": rescueTelemetryFixture,
  "memory-02": landingRendezvousTelemetryFixture,
  "memory-03": duoAssistTelemetryFixture,
  "memory-04": repeatedNearMissTelemetryFixture,
};

function requirePlayerTelemetryFixture(
  experienceRef: PlayerExperienceRef,
): RawTelemetryBatchV2 {
  const telemetry = parseRawTelemetryBatchV2(fixtureByExperience[experienceRef]);
  if (!telemetry) {
    throw new Error(`Invalid player demo telemetry fixture: ${experienceRef}`);
  }
  return telemetry;
}

const telemetryByExperience = Object.fromEntries(
  playerExperienceRefs.map((experienceRef) => [
    experienceRef,
    requirePlayerTelemetryFixture(experienceRef),
  ]),
) as Record<PlayerExperienceRef, RawTelemetryBatchV2>;

export function playerExperienceSeeds(): PlayerExperienceSeedV2[] {
  return playerExperienceRefs.map((experienceRef) =>
    projectTelemetryForPlayerStart(telemetryByExperience[experienceRef], experienceRef));
}

export function playerExperienceTelemetry(
  experienceRef: unknown,
  requestId: unknown,
): RawTelemetryBatchV2 | null {
  if (!isPlayerExperienceRef(experienceRef) || typeof requestId !== "string") return null;
  const telemetry = telemetryByExperience[experienceRef];
  return telemetry.request_id === requestId ? telemetry : null;
}
