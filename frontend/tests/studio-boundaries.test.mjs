import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("Studio exposes deliberate scenario preparation and quota-labelled execution", async () => {
  const dashboard = await source("../app/studio/studio-dashboard.tsx");

  for (const copy of [
    "Prepare scenario — no AI call",
    "Run new live interpretation — uses provider quota",
    "One correction attempt may use a second provider call.",
    "Backend configured",
    "Saved live replay — not a fresh AI run",
    "Latest player app decision",
    "Safe code:",
  ]) {
    assert.match(dashboard, new RegExp(copy.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(dashboard, /disabled=\{running \|\| preparing \|\| !catalog\}/);
  assert.match(dashboard, /if \(runningLock\.current \|\| preparing\) return/);
  assert.match(dashboard, /if \(!selectedScenario \|\| !canRun \|\| runningLock\.current\) return/);
  assert.match(dashboard, /\{result && selectedScenario && actual \?/);
  assert.match(dashboard, /if \(!flow\.delivery\?\.delivery_id\)/);
  assert.match(dashboard, /const deliveryId = flow\.delivery\.delivery_id/);
  assert.match(dashboard, /body: JSON\.stringify\(\{ delivery_id: deliveryId \}\)/);
  assert.match(dashboard, /result\?\.studio_trace \?\? null/);
  assert.match(dashboard, /inspection-only replay/);
});

test("saved replay stays Studio-only while the player parser remains live-AI-only", async () => {
  const contract = await source("../lib/ai-memory-contract.ts");

  assert.match(
    contract,
    /content_origin: "live_ai_validated";[\s\S]*export type StudioPendingDeliveryV2/,
  );
  assert.match(
    contract,
    /StudioPendingDeliveryV2 = Omit<PendingDeliveryV2, "metadata">[\s\S]*"saved_live_replay"/,
  );
  assert.match(
    contract,
    /parseInterpretDeliveryV2[\s\S]*parsed\.metadata\.content_origin !== "live_ai_validated"/,
  );
});

test("Studio live route fails closed for noncanonical success and absent exact replay", async () => {
  const interpretRoute = await source("../app/api/studio/scenarios/interpret/route.ts");
  const providerErrorBoundary = await source("../lib/studio-provider-error.ts");
  const replayManifest = JSON.parse(await source("../data/studio-replays/manifest.json"));
  const healthRoute = await source("../app/api/studio/health/route.ts");

  assert.match(interpretRoute, /metadata\.mode !== "live_ai"/);
  assert.match(interpretRoute, /metadata\.content_origin !== "live_ai_validated"/);
  assert.match(interpretRoute, /code: "noncanonical_live_result"/);
  assert.match(interpretRoute, /code: "studio_live_run_withheld"/);
  assert.match(interpretRoute, /parseSafeStudioProviderFailure/);
  assert.match(providerErrorBoundary, /"memory_interpretation_correction"/);
  assert.match(providerErrorBoundary, /\["provider_rate_limited", true\]/);
  assert.match(providerErrorBoundary, /retryable !== expectedRetryability/);
  assert.match(providerErrorBoundary, /Provider-authored messages and every unrecognised field are intentionally ignored/);
  assert.deepEqual(replayManifest, { schema_version: "1.0", replays: [] });
  assert.match(healthRoute, /Live interpretation is unavailable/);
  assert.doesNotMatch(healthRoute, /runs (?:are|will use).*sample replay/i);
});

test("both provider-consuming routes share the strict local-browser gate", async () => {
  const serverBoundary = await source("../lib/memoryos-server.ts");
  const playerRoute = await source("../app/api/delivery/prepare/route.ts");
  const studioRoute = await source("../app/api/studio/scenarios/interpret/route.ts");

  assert.match(serverBoundary, /\["localhost", "127\.0\.0\.1", "\[::1\]"\]/);
  assert.match(serverBoundary, /if \(!origin \|\| origin !== requestUrl\.origin\) return false/);
  assert.match(serverBoundary, /!fetchSite \|\| fetchSite === "same-origin"/);
  assert.match(playerRoute, /isTrustedLocalBrowserRequest\(request\)/);
  assert.match(studioRoute, /isTrustedLocalBrowserRequest\(request\)/);
});
