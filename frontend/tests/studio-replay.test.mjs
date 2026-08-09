import assert from "node:assert/strict";
import test from "node:test";

import {
  exactStudioScenarioVersion,
  parseStudioReplayEnvelope,
  studioReplayArtifactsFromManifest,
} from "../lib/studio-replay-core.mjs";
import { hasStudioModeOriginPair } from "../lib/studio-result-provenance-core.mjs";

const rescueScenario = {
  scenario_id: "rescue-role-reversal",
  fixture_sha256: "a".repeat(64),
  fixture_revision: `2.1:${"a".repeat(12)}`,
};

const ordinaryScenario = {
  scenario_id: "ordinary-sparse-telemetry",
  fixture_sha256: "b".repeat(64),
  fixture_revision: `2.1:${"b".repeat(12)}`,
};

function replayEnvelope(scenario = rescueScenario, status = "pending_player_decision") {
  const noPlayerContent = status !== "pending_player_decision";
  return {
    replay_schema_version: "1.0",
    scenario: { ...scenario },
    provenance: {
      provider: "gemini",
      model: "gemini-2.5-flash",
      prompt_version: "memory-interpreter-v2.1",
      result_schema_version: "2.1",
      captured_at: "2026-08-09T10:15:30Z",
    },
    result: {
      schema_version: "2.1",
      status,
      metadata: {
        provider: "gemini",
        model: "gemini-2.5-flash",
        mode: "saved_replay",
        prompt_version: "memory-interpreter-v2.1",
        content_origin: noPlayerContent ? "no_player_content" : "saved_live_replay",
      },
    },
  };
}

test("Studio metadata accepts only canonical mode and content-origin pairs", () => {
  for (const [status, mode, origin] of [
    ["pending_player_decision", "live_ai", "live_ai_validated"],
    ["pending_player_decision", "deterministic_demo", "deterministic_studio_sample"],
    ["pending_player_decision", "saved_replay", "saved_live_replay"],
    ["not_generated", "live_ai", "no_player_content"],
    ["not_generated", "deterministic_demo", "no_player_content"],
    ["not_generated", "saved_replay", "no_player_content"],
    ["rejected", "live_ai", "no_player_content"],
    ["rejected", "deterministic_demo", "no_player_content"],
    ["rejected", "saved_replay", "no_player_content"],
  ]) {
    assert.equal(hasStudioModeOriginPair(status, mode, origin), true);
  }

  for (const [status, mode, origin] of [
    ["pending_player_decision", "live_ai", "saved_live_replay"],
    ["pending_player_decision", "saved_replay", "live_ai_validated"],
    ["pending_player_decision", "deterministic_demo", "saved_live_replay"],
    ["not_generated", "saved_replay", "saved_live_replay"],
    ["not_generated", "deterministic_demo", "deterministic_studio_sample"],
    ["pending_player_decision", "deterministic", "deterministic_studio_sample"],
    ["rejected", "saved_replay", "live_ai_validated"],
    ["unknown", "saved_replay", "no_player_content"],
  ]) {
    assert.equal(hasStudioModeOriginPair(status, mode, origin), false);
  }
});

test("saved Studio replays require an exact fixture hash and revision", () => {
  const valid = replayEnvelope();
  assert.ok(exactStudioScenarioVersion(rescueScenario, valid.scenario));
  assert.ok(parseStudioReplayEnvelope(valid, rescueScenario));

  for (const mutation of [
    (value) => { value.scenario.fixture_sha256 = "c".repeat(64); },
    (value) => { value.scenario.fixture_revision = `2.1:${"c".repeat(12)}`; },
    (value) => { value.replay_schema_version = "2.0"; },
    (value) => { value.provenance.result_schema_version = "2.0"; },
    (value) => { value.provenance.captured_at = "yesterday"; },
    (value) => { value.result.metadata.provider = "different-provider"; },
    (value) => { value.result.metadata.mode = "live_ai"; },
    (value) => { value.result.metadata.content_origin = "live_ai_validated"; },
  ]) {
    const changed = structuredClone(valid);
    mutation(changed);
    assert.equal(parseStudioReplayEnvelope(changed, rescueScenario), null);
  }
});

test("ordinary telemetry can replay an exact saved live abstention without player content", () => {
  const abstention = replayEnvelope(ordinaryScenario, "not_generated");
  assert.equal(abstention.result.metadata.content_origin, "no_player_content");
  assert.ok(parseStudioReplayEnvelope(abstention, ordinaryScenario));

  const unsafeLiveMode = structuredClone(abstention);
  unsafeLiveMode.result.metadata.mode = "live_ai";
  assert.equal(parseStudioReplayEnvelope(unsafeLiveMode, ordinaryScenario), null);

  const unsafePendingOrigin = structuredClone(abstention);
  unsafePendingOrigin.result.metadata.content_origin = "saved_live_replay";
  assert.equal(parseStudioReplayEnvelope(unsafePendingOrigin, ordinaryScenario), null);
});

test("the replay manifest is strict and exposes only registered artifacts", () => {
  const replay = replayEnvelope();
  assert.deepEqual(
    studioReplayArtifactsFromManifest({ schema_version: "1.0", replays: [replay] }),
    [replay],
  );
  assert.deepEqual(
    studioReplayArtifactsFromManifest({ schema_version: "1.0", replays: [] }),
    [],
  );
  assert.equal(studioReplayArtifactsFromManifest({ schema_version: "2.0", replays: [replay] }), null);
  assert.equal(
    studioReplayArtifactsFromManifest({ schema_version: "1.0", replays: [replay], fallback: true }),
    null,
  );
});
