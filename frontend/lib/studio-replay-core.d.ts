import type { StudioScenarioDescriptorV2 } from "./studio-scenarios";

export type StudioReplayEnvelope = {
  replay_schema_version: "1.0";
  scenario: Pick<StudioScenarioDescriptorV2, "scenario_id" | "fixture_sha256" | "fixture_revision">;
  provenance: {
    provider: string;
    model: string;
    prompt_version: string;
    result_schema_version: "2.1";
    captured_at: string;
  };
  result: Record<string, unknown>;
};

export function exactStudioScenarioVersion(
  expected: StudioScenarioDescriptorV2,
  actual: StudioReplayEnvelope["scenario"],
): boolean;

export function parseStudioReplayEnvelope(
  value: unknown,
  expectedScenario: StudioScenarioDescriptorV2,
): StudioReplayEnvelope | null;

export function studioReplayArtifactsFromManifest(manifest: unknown): unknown[] | null;
