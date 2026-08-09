import replayManifest from "@/data/studio-replays/manifest.json";
import { parseStudioInterpretDeliveryV2 } from "@/lib/ai-memory-contract";
import type { StudioInterpretDeliveryResultV2 } from "@/lib/ai-memory-contract";
import {
  parseStudioReplayEnvelope,
  studioReplayArtifactsFromManifest,
} from "@/lib/studio-replay-core.mjs";
import type { StudioScenarioDescriptorV2 } from "@/lib/studio-scenarios";

export type SavedLiveReplayProvenance = {
  provider: string;
  model: string;
  prompt_version: string;
  result_schema_version: "2.1";
  captured_at: string;
};

export type StudioSavedLiveReplay = {
  schema_version: "2.1";
  scenario: StudioScenarioDescriptorV2;
  result: StudioInterpretDeliveryResultV2;
  content_origin: "saved_live_replay";
  replay_provenance: SavedLiveReplayProvenance;
};

export function parseCompatibleStudioReplay(
  value: unknown,
  scenario: StudioScenarioDescriptorV2,
): StudioSavedLiveReplay | null {
  const envelope = parseStudioReplayEnvelope(value, scenario);
  if (!envelope) return null;
  const result = parseStudioInterpretDeliveryV2(envelope.result);
  if (!result || result.status !== scenario.expected_status) return null;
  const actualFamily = result.status === "pending_player_decision"
    ? result.next_chapter.family
    : null;
  if (actualFamily !== scenario.expected_mission_family) return null;
  return {
    schema_version: "2.1",
    scenario,
    result,
    content_origin: "saved_live_replay",
    replay_provenance: envelope.provenance,
  };
}

export function compatibleStudioReplay(scenario: StudioScenarioDescriptorV2) {
  const manifest: unknown = replayManifest;
  const artifacts = studioReplayArtifactsFromManifest(manifest);
  if (!artifacts) return null;
  for (const artifact of artifacts) {
    const replay = parseCompatibleStudioReplay(artifact, scenario);
    if (replay) return replay;
  }
  return null;
}
