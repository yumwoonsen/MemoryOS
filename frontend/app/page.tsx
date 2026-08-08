import { MemoryExperience } from "./memory-experience";
import rawTelemetry from "@/data/raw_telemetry_v2.json";
import type { RawTelemetryBatchV2 } from "@/lib/ai-memory-contract";
import { projectTelemetryForPlayerStart } from "@/lib/player-delivery";

export default function Home() {
  const telemetry = rawTelemetry as unknown as RawTelemetryBatchV2;
  return <MemoryExperience seed={projectTelemetryForPlayerStart(telemetry)} />;
}
