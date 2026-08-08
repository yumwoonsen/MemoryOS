import type { Metadata } from "next";
import rawTelemetry from "@/data/raw_telemetry_v2.json";
import { consentSafeTelemetryView } from "@/lib/ai-memory-contract";
import type { RawTelemetryBatchV2 } from "@/lib/ai-memory-contract";
import { StudioDashboard } from "./studio-dashboard";

export const metadata: Metadata = {
  title: "MemoryOS Studio",
  description: "Inspect the evidence, model boundary, structured outputs, and validation behind MemoryOS.",
  robots: { index: false, follow: false },
};

export default function StudioPage() {
  const telemetry = rawTelemetry as unknown as RawTelemetryBatchV2;
  return <StudioDashboard telemetry={consentSafeTelemetryView(telemetry)} />;
}
