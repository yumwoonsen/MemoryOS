import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

import { createTestLiveDelivery } from "./fixtures/live-delivery-v2.mjs";

const playerExperienceRef = "squad-signal-01";

async function unifiedPlayerTelemetry() {
  return JSON.parse(
    await readFile(new URL("../data/player-scenarios/unified_squad_history.json", import.meta.url), "utf8"),
  );
}

function playerPrepareBody(telemetry) {
  return JSON.stringify({ experience_ref: playerExperienceRef, request_id: telemetry.request_id });
}

function testStudioScenario() {
  return {
    scenario_id: "rescue-role-reversal",
    title: "Rescue sequence",
    purpose: "Shows role reversal from consent-safe rescue telemetry.",
    fixture_sha256: "a".repeat(64),
    fixture_revision: `2.1:${"a".repeat(12)}`,
    expected_status: "pending_player_decision",
    expected_mission_family: "role_reversal",
    label_source: "offline_evaluation_manifest",
  };
}

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`https://memoryos.example${path}`, {
      headers: { accept: "text/html", host: "memoryos.example" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

async function discover(body) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `api-${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("https://memoryos.example/api/discover", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

async function studioHealth() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `studio-health-${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("https://memoryos.example/api/studio/health"),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

async function studioGenerate(body) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `studio-run-${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("https://memoryos.example/api/studio/generate-stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

async function studioInterpret(body) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `studio-v2-${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("https://memoryos.example/api/studio/interpret", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

async function postWithBackendStub(path, body, upstreamPayload, options = {}) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `boundary-${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  const originalFetch = globalThis.fetch;
  let upstreamRequest = null;
  globalThis.fetch = async (input, init) => {
    upstreamRequest = { input: String(input), init };
    return Response.json(upstreamPayload, { status: options.upstreamStatus ?? 200 });
  };

  try {
    const requestOrigin = options.requestOrigin ?? "http://localhost";
    const browserHeaders = options.browserHeaders === false
      ? {}
      : { origin: requestOrigin, "sec-fetch-site": "same-origin" };
    const headers = new Headers({
      "content-type": "application/json",
      ...browserHeaders,
      ...(options.headers ?? {}),
    });
    const response = await worker.fetch(
      new Request(`${requestOrigin}${path}`, { method: "POST", headers, body }),
      {
        ASSETS: {
          fetch: async () => new Response("Not found", { status: 404 }),
        },
      },
      {
        waitUntil() {},
        passThroughOnException() {},
      },
    );
    return { response, upstreamRequest };
  } finally {
    globalThis.fetch = originalFetch;
  }
}

test("server-renders the unrevealed Battle Royale memory", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  const mainHtml = html.slice(html.indexOf("<main"), html.indexOf("</main>") + "</main>".length);
  assert.match(html, /<title>Garena Next Chapter — MemoryOS<\/title>/i);
  assert.match(html, /data-theme="light"/i);
  assert.match(html, /Battle Royale/i);
  assert.match(html, /aria-busy="false"/i);
  assert.match(html, /Memory waiting/i);
  assert.match(html, /Memory not loaded/i);
  assert.match(html, /A squad memory is waiting/i);
  assert.match(html, /One consent-safe squad history can support several grounded continuations/i);
  assert.match(html, /2(?:<!-- -->)? recent sessions available/i);
  assert.doesNotMatch(html, /Synthetic demo histories|Choose a squad signal|safe fixtures|aria-pressed=/i);
  assert.match(html, /Free Fire/i);
  assert.match(html, /Bermuda/i);
  assert.match(html, /Open the chapter when you are ready/i);
  assert.match(html, /The consent-safe squad/i);
  assert.match(html, /aria-label="4 opted-in squad members"/i);
  assert.match(html, />J<\/span>/i);
  assert.doesNotMatch(html, /ff-player-|anonymous:squadmate|memory_appearance|mission_invitation|rescue-role-reversal|landing-rendezvous|duo-assist|repeated-near-miss/i);
  assert.match(html, /Open current memory/i);
  assert.match(mainHtml, /aria-label="Player sections"/i);
  assert.match(mainHtml, /href="\/mission"/i);
  assert.match(mainHtml, /href="\/history"/i);
  assert.match(mainHtml, /href="\/studio"/i);
  assert.match(mainHtml, /Developer Studio/i);
  assert.match(html, /free-fire-map-v2\.webp/i);
  assert.match(html, /free-fire-map-mobile-v2\.webp/i);
  assert.match(html, /https:\/\/memoryos\.example\/og\.png/);
  assert.doesNotMatch(
    mainHtml,
    /Your side of the story|What actually happened|Accept mission|Story Continues|Send squad invite|clock-tower-town-v2|Memory Pack|Run Memory Engine|Choose a memory signal|Facts in\. Verified chapter out\.|Canonical transformation|Tactical Round|COD Mobile|Review Studio/i,
  );
});

test("server-renders squad history without reopening the current decision flow", async () => {
  const response = await render("/history");
  assert.equal(response.status, 200);
  const html = await response.text();
  const mainHtml = html.slice(html.indexOf("<main"), html.indexOf("</main>") + "</main>".length);
  assert.match(html, /Squad history/i);
  assert.match(html, /The stories your squad kept/i);
  assert.match(html, /Past squad matches/i);
  assert.match(html, /Retained memories/i);
  assert.match(html, /Bermuda/i);
  assert.match(html, /squad match/i);
  assert.match(mainHtml, /<details class="past-memory-item"/i);
  assert.match(mainHtml, /Match details/i);
  assert.match(mainHtml, /Consent-safe moments/i);
  assert.match(mainHtml, /Opted-in players/i);
  assert.match(mainHtml, /href="\/"/i);
  assert.match(mainHtml, /href="\/studio"/i);
  assert.doesNotMatch(mainHtml, /This prototype session|No current-session chapter yet|Accept mission|Decline mission|Send squad invite|Story Continues|Bringing a squad moment back/i);
});

test("server-renders a safe empty mission state without an accepted session handoff", async () => {
  const response = await render("/mission");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /No active mission/i);
  assert.match(html, /Accept a Next Chapter mission first/i);
  assert.match(html, /View current memory/i);
  assert.doesNotMatch(html, /Send squad invite|Simulate rematch|Story Continues/i);
});

test("keeps the loaded player story in a simple evidence-first order", async () => {
  const source = await readFile(new URL("../app/memory-experience.tsx", import.meta.url), "utf8");
  const gist = source.indexOf("player-context-strip");
  const reason = source.indexOf("Why this memory returned");
  const recap = source.indexOf("What actually happened");
  const perspective = source.indexOf("Your side of the story");
  const chapter = source.indexOf("Next Chapter /");
  const objectives = source.indexOf("<MissionObjectiveList", chapter);
  const decision = source.indexOf("Accept mission");

  assert.ok(gist > -1 && gist < reason);
  assert.ok(reason < recap);
  assert.ok(recap < perspective);
  assert.ok(perspective < chapter);
  assert.ok(chapter < objectives);
  assert.ok(objectives < decision);
  assert.ok(chapter < decision);
  assert.doesNotMatch(
    source,
    /Play this challenge|Demo simulation|Challenge rules|objectiveRule|Verified live|Verified preview|Confirm this memory|\?\?\s*result\.player_perspectives\[0\]/i,
  );
});

test("does not ship the disposable starter preview", async () => {
  const response = await render();
  const html = await response.text();

  assert.doesNotMatch(html, /codex-preview/);
  assert.doesNotMatch(html, /react-loading-skeleton/);
  assert.doesNotMatch(html, /Your site is taking shape/);
});

test("ships one exact server-owned player history plus an explicitly empty saved-replay registry", async () => {
  const dataFiles = (await readdir(new URL("../data/", import.meta.url))).sort();
  assert.deepEqual(dataFiles, ["funny_memory.json", "player-scenarios", "raw_telemetry_v2.json", "studio-replays"]);
  const telemetry = JSON.parse(await readFile(new URL("../data/raw_telemetry_v2.json", import.meta.url), "utf8"));
  assert.equal(telemetry.schema_version, "2.0");
  assert.ok(Array.isArray(telemetry.matches));
  for (const forbidden of ["title", "summary", "memory_type", "narrative_angle", "mission", "objectives", "resurfacing_reason", "importance"]) {
    assert.equal(JSON.stringify(telemetry).includes(`"${forbidden}"`), false, `${forbidden} must not pre-author the v2 input`);
  }
  const playerFixtures = (await readdir(new URL("../data/player-scenarios/", import.meta.url))).sort();
  assert.deepEqual(playerFixtures, ["unified_squad_history.json"]);
  const frontendUnified = await readFile(
    new URL("../data/player-scenarios/unified_squad_history.json", import.meta.url),
    "utf8",
  );
  const backendUnified = await readFile(
    new URL("../../backend/data/v2_evaluation/unified_squad_history.json", import.meta.url),
    "utf8",
  );
  assert.equal(frontendUnified, backendUnified, "the frontend server fixture must be an exact canonical copy");
  const unified = JSON.parse(frontendUnified);
  assert.equal(unified.schema_version, "2.1");
  assert.equal(unified.request_id, "req-ff-unified-squad-history-001");
  const replayManifest = JSON.parse(
    await readFile(new URL("../data/studio-replays/manifest.json", import.meta.url), "utf8"),
  );
  assert.deepEqual(replayManifest, { schema_version: "1.0", replays: [] });
});

test("hosted discovery returns a JSON sample instead of proxying localhost", async () => {
  const memoryPack = await readFile(
    new URL("../data/funny_memory.json", import.meta.url),
    "utf8",
  );
  const response = await discover(memoryPack);

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^application\/json\b/i);
  assert.equal(response.headers.get("x-memoryos-mode"), "sample");
  assert.equal(response.headers.get("x-memoryos-fallback"), "hosted-sample");
  const result = await response.json();
  assert.equal(result.status, "ready");
  assert.equal(result.metadata.prompt_version, "narrative-scaffold-v1");
  assert.equal(result.metadata.narrative_boundary, "model-prose-deterministic-controls-v1");
  assert.match(result.player_perspectives[0].message, /Mei came back for you/);
  assert.match(result.next_chapter.mission, /remix Worst Plan, Best Night/);
});

test("hosted discovery returns stable JSON errors", async () => {
  const malformed = await discover("not-json");
  assert.equal(malformed.status, 400);
  assert.equal(malformed.headers.get("x-memoryos-mode"), "sample");
  assert.deepEqual(await malformed.json(), {
    code: "invalid_memory_pack_json",
    message: "The Memory Pack was not valid JSON.",
  });

  for (const invalidBody of ["null", "[]", "{}"]) {
    const invalidPack = await discover(invalidBody);
    assert.equal(invalidPack.status, 422);
    assert.equal((await invalidPack.json()).code, "invalid_memory_pack");
  }

  const memoryPack = JSON.parse(
    await readFile(new URL("../data/funny_memory.json", import.meta.url), "utf8"),
  );
  memoryPack.match_events = [];
  const mismatched = await discover(JSON.stringify(memoryPack));
  assert.equal(mismatched.status, 503);
  assert.equal((await mismatched.json()).code, "sample_result_unavailable");

  memoryPack.match_events = JSON.parse(
    await readFile(new URL("../data/funny_memory.json", import.meta.url), "utf8"),
  ).match_events;
  memoryPack.pack_id = "unknown-pack";
  const unknown = await discover(JSON.stringify(memoryPack));
  assert.equal(unknown.status, 503);
  assert.equal(unknown.headers.get("x-memoryos-mode"), "sample");
  assert.equal((await unknown.json()).code, "sample_result_unavailable");
});

test("ships the compact light palette and original Battle Royale artwork", async () => {
  const css = (await readFile(new URL("../app/globals.css", import.meta.url), "utf8")).toLowerCase();

  for (const colour of ["#edf0e7", "#fffef9", "#171a15", "#d7ff3f", "#5d7000"]) {
    assert.match(css, new RegExp(colour));
  }
  assert.doesNotMatch(css, /#52a6ff|#6ec8bd|#080b10|#111720/);
  assert.match(css, /\.player-evidence summary::after,[\s\S]*\.your-perspective-card summary::after/);
  assert.match(css, /background-size: 12px 2px, 2px 0/);
  assert.match(css, /transition: transform 180ms ease, background-size 180ms ease/);

  for (const asset of [
    "../public/art/heroes/free-fire-map-v2.webp",
    "../public/art/heroes/free-fire-map-mobile-v2.webp",
    "../public/art/landmarks/clock-tower-town-v2.webp",
  ]) {
    const bytes = await readFile(new URL(asset, import.meta.url));
    assert.ok(bytes.length > 1_000, `${asset} should contain optimized artwork`);
    assert.equal(bytes.subarray(0, 4).toString("ascii"), "RIFF");
    assert.equal(bytes.subarray(8, 12).toString("ascii"), "WEBP");
  }
});

test("server-renders the dedicated developer Studio", async () => {
  const response = await render("/studio");
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>MemoryOS Studio/i);
  assert.match(html, /Developer observability/i);
  assert.match(html, /AI-grounded memory trace/i);
  assert.match(html, /Deterministic checkpoint/i);
  assert.match(html, /Judge trace/i);
  assert.match(html, /Delivery inspector/i);
  assert.match(html, /Active generation mode/i);
  assert.match(html, /Provider check/i);
  assert.match(html, /Deterministic preparation/i);
  assert.match(html, /AI interpretation/i);
  assert.match(html, /Deterministic validation/i);
  assert.match(html, /Player decision/i);
  assert.match(html, /Prepare scenario â€” no AI call|Prepare scenario — no AI call/i);
  assert.match(html, /Run new live interpretation â€” uses provider quota|Run new live interpretation — uses provider quota/i);
  assert.match(html, /Open player view/i);
  assert.match(html, /active \/ invite-ready/i);
  assert.match(html, /Latest player app decision/i);
  assert.match(html, /noindex/i);
});

test("hosted Studio reports an unconfigured backend without promising a replay", async () => {
  const response = await studioHealth();

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-memoryos-mode"), "sample");
  assert.equal(response.headers.get("x-memoryos-fallback"), "hosted-sample");
  assert.deepEqual(await response.json(), {
    status: "sample",
    mode: "sample",
    inference_mode: "unknown",
    provider: "not-configured",
    model: "not-configured",
    message:
      "No MemoryOS backend is configured for this hosted Studio. Live interpretation is unavailable.",
  });
});

test("hosted Studio replays typed pipeline snapshots without claiming live AI", async () => {
  const memoryPack = await readFile(
    new URL("../data/funny_memory.json", import.meta.url),
    "utf8",
  );
  const response = await studioGenerate(memoryPack);

  assert.equal(response.status, 200);
  assert.match(
    response.headers.get("content-type") ?? "",
    /^application\/x-ndjson\b/i,
  );
  assert.equal(response.headers.get("x-memoryos-mode"), "sample");
  assert.equal(response.headers.get("x-memoryos-fallback"), "hosted-sample");

  const events = (await response.text())
    .trim()
    .split(/\r?\n/)
    .map((line) => JSON.parse(line));
  assert.deepEqual(
    events.filter((event) => event.type === "stage").map((event) => event.stage),
    [
      "review_and_discovery",
      "memory_discovery",
      "perspectives",
      "quest_generation",
      "validation",
    ],
  );
  assert.equal(events[0].status, "working");
  assert.equal(events.at(-1).type, "result");
  assert.equal(events.at(-1).result.metadata.provider, "deterministic");
});

test("Studio rejects unsafe or oversized developer inputs before generation", async () => {
  const malformedNestedPack = {
    schema_version: "1.0",
    pack_id: "unsafe-pack",
    player_profile: { player_id: "lee" },
    squad: {
      squad_id: "squad",
      members: [null, { player_id: "lee", display_name: "Lee", opted_in: true }],
      matches_together: 1,
    },
    match: { match_id: "match", mode: "battle_royale" },
    match_events: [],
  };
  const malformed = await studioGenerate(JSON.stringify(malformedNestedPack));
  assert.equal(malformed.status, 422);
  assert.equal(JSON.parse((await malformed.text()).trim()).code, "invalid_memory_pack");

  const oversized = await studioGenerate(JSON.stringify({ payload: "x".repeat(256_001) }));
  assert.equal(oversized.status, 413);
  assert.equal(JSON.parse((await oversized.text()).trim()).code, "memory_pack_too_large");
});

test("Studio preserves the hosted fallback reason for its fixed synthetic replay", async () => {
  const memoryPack = JSON.parse(
    await readFile(new URL("../data/funny_memory.json", import.meta.url), "utf8"),
  );
  memoryPack.pack_id = "edited-pack-without-fixture";
  const response = await studioGenerate(JSON.stringify(memoryPack));

  assert.equal(response.status, 503);
  assert.equal(response.headers.get("x-memoryos-mode"), "sample");
  assert.equal(response.headers.get("x-memoryos-fallback"), "hosted-sample");
  assert.equal(JSON.parse((await response.text()).trim()).code, "sample_result_unavailable");
});

test("browser bundle never calls the local backend directly", async () => {
  const assetsRoot = new URL("../dist/client/_next/static/chunks/", import.meta.url);
  const assetNames = (await readdir(assetsRoot)).filter((name) => name.endsWith(".js"));
  const browserBundle = (
    await Promise.all(
      assetNames.map((name) => readFile(new URL(name, assetsRoot), "utf8")),
    )
  ).join("\n");

  assert.doesNotMatch(browserBundle, /127\.0\.0\.1:8000/);
  assert.doesNotMatch(browserBundle, /MEMORYOS_PROXY_TOKEN|x-memoryos-proxy-token/i);
  assert.match(browserBundle, /\/api\/discover/);
  assert.match(browserBundle, /\/api\/studio\/scenarios\/interpret/);
  assert.match(browserBundle, /\/api\/studio\/delivery-trace/);
  assert.match(browserBundle, /AI-grounded memory trace/i);
  assert.match(browserBundle, /Versioned Studio checkpoint/i);
  assert.match(browserBundle, /Run new live interpretation/i);
  assert.match(browserBundle, /Generated proposal withheld/i);
  assert.match(browserBundle, /Deterministic preparation/i);
  assert.match(browserBundle, /AI interpretation/i);
  assert.match(browserBundle, /Deterministic validation/i);
  assert.match(browserBundle, /Player decision/i);
  assert.match(browserBundle, /\/api\/history/);
  assert.match(browserBundle, /\/api\/generate/);
  assert.match(browserBundle, /\/api\/delivery\/prepare/);
  assert.match(browserBundle, /Memory not loaded/i);
  assert.match(browserBundle, /Why this memory returned/i);
  assert.match(browserBundle, /What actually happened/i);
  assert.match(browserBundle, /Your side of the story/i);
  assert.match(browserBundle, /Next Chapter/i);
  assert.match(browserBundle, /Next Chapter mission steps/i);
  assert.match(browserBundle, /Accept mission/i);
  assert.match(browserBundle, /Open mission/i);
  assert.match(browserBundle, /No active mission/i);
  assert.match(browserBundle, /Send squad invite/i);
  assert.match(browserBundle, /Simulate squad accepting/i);
  assert.match(browserBundle, /Start game/i);
  assert.match(browserBundle, /Story continued/i);
  assert.match(browserBundle, /required objectives completed/i);
  assert.match(browserBundle, /Prototype match simulation/i);
  assert.match(browserBundle, /No memory generated/i);
  assert.match(browserBundle, /AI mission selection/i);
  assert.match(browserBundle, /Offered affordance/i);
  assert.match(browserBundle, /Hide this chapter/i);
  assert.match(browserBundle, /Squad history/i);
  assert.match(browserBundle, /Past squad matches/i);
  assert.match(browserBundle, /Match details/i);
  assert.doesNotMatch(browserBundle, /ff-player-/i);
  assert.doesNotMatch(
    browserBundle,
    /Play this challenge|Demo simulation|Memory Pack ready|Build this story|Generating from verified data|Match evidence remains the source of truth|Challenge rules|Verified live|Verified preview/i,
  );
  assert.doesNotMatch(
    browserBundle,
    /Choose a memory signal|One HP Reset|Match FF-M999|memory-pack-comeback|memory-pack-insufficient|Command Post/i,
  );
});

test("consumer decision and reunion paths stay explicit and privacy-safe", async () => {
  const prepareRoute = await readFile(new URL("../app/api/delivery/prepare/route.ts", import.meta.url), "utf8");
  const decisionRoute = await readFile(new URL("../app/api/delivery/decision/route.ts", import.meta.url), "utf8");
  const traceRoute = await readFile(new URL("../app/api/studio/delivery-trace/route.ts", import.meta.url), "utf8");
  const homePage = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const memoryClient = await readFile(new URL("../app/memory-experience.tsx", import.meta.url), "utf8");
  const missionClient = await readFile(new URL("../app/mission/mission-experience.tsx", import.meta.url), "utf8");
  const deliveryFlow = await readFile(new URL("../lib/delivery-flow.ts", import.meta.url), "utf8");
  const v2Contract = await readFile(new URL("../lib/ai-memory-contract.ts", import.meta.url), "utf8");
  const playerProjection = await readFile(new URL("../lib/player-delivery.ts", import.meta.url), "utf8");
  const playerExperienceServer = await readFile(new URL("../lib/player-scenario.server.ts", import.meta.url), "utf8");
  const reunionCore = await readFile(new URL("../lib/reunion-flow-core.mjs", import.meta.url), "utf8");
  const proxySource = await readFile(new URL("../lib/memoryos-server.ts", import.meta.url), "utf8");
  const historyPage = await readFile(new URL("../app/history/page.tsx", import.meta.url), "utf8");
  const historyClient = await readFile(new URL("../app/history/history-experience.tsx", import.meta.url), "utf8");
  const flowProvider = await readFile(new URL("../app/player-flow-provider.tsx", import.meta.url), "utf8");
  const studioClient = await readFile(new URL("../app/studio/studio-dashboard.tsx", import.meta.url), "utf8");
  assert.match(prepareRoute, /\/v2\/memories\/interpret-varied-delivery/);
  assert.match(prepareRoute, /projectPendingDeliveryForPlayer/);
  assert.match(prepareRoute, /isDeliveryBoundToTelemetryV2/);
  assert.match(prepareRoute, /allowedBodyKeys = new Set\(\["experience_ref", "request_id"\]\)/);
  assert.match(prepareRoute, /crypto\.randomUUID\(\)/);
  assert.match(prepareRoute, /\{ telemetry, generation_nonce: generationNonce \}/);
  assert.match(prepareRoute, /safeUpstreamFailure/);
  assert.doesNotMatch(prepareRoute, /parseRawTelemetryBatchV2|submittedTelemetry/);
  assert.match(decisionRoute, /\/v2\/deliveries\/\$\{encodeURIComponent\(deliveryId\)\}\/decision/);
  assert.match(traceRoute, /\/v2\/deliveries\/\$\{encodeURIComponent\(body\.delivery_id\)\}\/trace/);
  assert.match(traceRoute, /isSameOriginRequest/);
  assert.match(proxySource, /x-memoryos-proxy-token/);
  assert.match(proxySource, /cache:\s*"no-store"/);
  assert.match(proxySource, /"cache-control":\s*"no-store"/);
  assert.match(proxySource, /GENERATION_TIMEOUT_MS\s*=\s*130_000/);
  assert.match(proxySource, /code:\s*"generation_timeout"/);
  assert.match(memoryClient, /playerPreparationError\(payload\)/);
  assert.match(memoryClient, /playerPreparationRetryable\(payload\)/);
  assert.match(deliveryFlow, /code === "memory_withheld"/);
  assert.match(deliveryFlow, /did not pass the grounding checks/);
  assert.match(deliveryFlow, /code === "provider_rate_limited"/);
  assert.match(deliveryFlow, /code === "provider_authentication_failed"/);
  assert.match(deliveryFlow, /code === "provider_unavailable"/);
  assert.match(memoryClient, /Generate another grounded chapter/);
  assert.match(memoryClient, /Each rerun uses provider quota and rotates among backend-validated mission plans/);
  assert.match(memoryClient, /if \(!canGenerateAnotherGroundedChapter\(view\.kind\)\) return/);
  assert.match(memoryClient, /resetPlayerFlow\(\);\s*void prepare\(\);/);
  assert.doesNotMatch(deliveryFlow, /validation\.issues|reason_codes|rejected.*prose/is);
  assert.match(homePage, /playerExperienceSeed/);
  assert.doesNotMatch(homePage, /raw_telemetry_v2\.json|RawTelemetryBatchV2|projectTelemetryForPlayerStart/);
  assert.match(playerExperienceServer, /unified_squad_history\.json/);
  assert.match(playerExperienceServer, /"squad-signal-01"/);
  assert.match(playerExperienceServer, /playerExperienceRegistry/);
  assert.doesNotMatch(playerExperienceServer, /raw_telemetry_v2\.json|landing_rendezvous\.json|duo_assist\.json|repeated_near_miss\.json|"memory-0[1-4]"/);
  assert.match(historyPage, /backend\/data\/historical_memory_packs\.json/);
  assert.match(historyPage, /CURRENT_MEMORY_MATCH_ID/);
  assert.match(memoryClient, /Accept mission/);
  assert.match(memoryClient, /Not relevant to me/);
  assert.match(memoryClient, /Details are wrong/);
  assert.match(memoryClient, /Keep reviewing/);
  assert.match(memoryClient, /source-quality signal/);
  assert.match(memoryClient, /Mission accepted/);
  assert.match(memoryClient, /deliveryModeLabel/);
  assert.match(deliveryFlow, /AI-prepared · evidence-checked/);
  assert.match(memoryClient, /AI preparation is in progress; evidence and consent validation are pending/);
  assert.doesNotMatch(memoryClient, /PlayerExperiencePicker|Choose a squad signal|safe fixtures/);
  assert.match(memoryClient, /\/api\/delivery\/prepare/);
  assert.match(memoryClient, /\/api\/delivery\/decision/);
  assert.match(memoryClient, /isDeliveryBoundToSeed/);
  assert.match(memoryClient, /resetPlayerFlow/);
  assert.match(flowProvider, /resetPlayerFlow/);
  assert.match(memoryClient, /declineMission/);
  assert.match(deliveryFlow, /parsePlayerDeliveryResultV2/);
  assert.match(playerProjection, /projectPendingDeliveryForPlayer/);
  assert.match(playerProjection, /content_origin: "live_ai_validated"/);
  assert.match(playerProjection, /verified_moments/);
  assert.match(playerProjection, /placed a tactical signal/);
  assert.doesNotMatch(playerProjection, /placed a retreat ping/);
  assert.match(playerProjection, /perspective:/);
  assert.match(playerProjection, /invitation_roster/);
  assert.doesNotMatch(playerProjection, /participantIndexes|completedMatchIndexes|Play and complete/);
  assert.match(v2Contract, /grounded_render === true/);
  assert.match(v2Contract, /grounded_claims/);
  assert.match(v2Contract, /supporting_mission_candidate_ids/);
  assert.match(v2Contract, /anonymous:squadmate/);
  assert.match(v2Contract, /match:\$\{binding\.selectedMatch\.match_id\}:game/);
  assert.match(v2Contract, /context:previous_session_at/);
  assert.match(v2Contract, /context:recent_rematch_count/);
  assert.match(studioClient, /\/api\/studio\/delivery-trace/);
  assert.match(studioClient, /usePlayerFlow/);
  assert.match(studioClient, /Details-wrong source-quality flag recorded for operations/);
  assert.match(missionClient, /buildInvitees\(delivery\.invitation_roster\)/);
  assert.match(missionClient, /Send squad invite/);
  assert.match(missionClient, /Prototype match simulation/);
  assert.match(missionClient, /scripted successful completion state/);
  assert.match(reunionCore, /role_reversal/);
  assert.match(reunionCore, /redemption/);
  assert.match(reunionCore, /return_to_place/);
  assert.match(reunionCore, /landing_rendezvous/);
  assert.match(reunionCore, /duo_assist/);
  assert.match(reunionCore, /The Favour Returned/);
  assert.match(reunionCore, /The Comeback Complete/);
  assert.match(reunionCore, /Together Again/);
  assert.match(reunionCore, /Same Drop, Same Squad/);
  assert.match(reunionCore, /The Setup and the Finish/);
  assert.match(missionClient, /Story continued/);
  assert.match(missionClient, /Original memory/);
  assert.match(missionClient, /Accepted mission/);
  assert.match(missionClient, /New chapter/);
  assert.match(missionClient, /filter\(\(objective\) => objective\.completed\)/);
  assert.match(missionClient, /Hide this chapter/);
  assert.match(missionClient, /View squad history/);
  assert.match(missionClient, /simulationSequence/);
  assert.match(historyClient, /Squad history/);
  assert.match(historyClient, /Past squad matches/);
  assert.match(flowProvider, /invitationSession/);
  assert.match(flowProvider, /acceptAllInvitees/);
  assert.match(flowProvider, /declineReason/);
  assert.doesNotMatch(historyClient, /Accept mission|Details are wrong|buildInvitees|prepare-delivery/);
  assert.doesNotMatch(missionClient, /Not relevant to me|decline_reason/);
  assert.doesNotMatch(memoryClient, /Deterministic fallback/);
  assert.doesNotMatch(memoryClient, /grounded_claims|studio_trace|claim_mappings/);
  assert.doesNotMatch(missionClient, /grounded_claims|studio_trace|claim_mappings/);
  assert.doesNotMatch(`${memoryClient}\n${missionClient}`, /player_perspectives|RawTelemetryBatchV2|provider_event_type/);
  assert.doesNotMatch(missionClient, /Rules engine|Deterministic prototype continuation/);
  assert.doesNotMatch(missionClient, /Keep in squad history/);
  assert.doesNotMatch(memoryClient, /Open a different memory/);
  assert.doesNotMatch(memoryClient, /resetFlow/);
  assert.doesNotMatch(flowProvider, /sessionStorage|localStorage/);
  assert.doesNotMatch(`${memoryClient}\n${missionClient}\n${historyClient}`, /127\.0\.0\.1:8000/);
});

test("Studio deduplicates rejected issue codes and renders only safe issue copy", async () => {
  const studioClient = await readFile(
    new URL("../app/studio/studio-dashboard.tsx", import.meta.url),
    "utf8",
  );

  assert.match(studioClient, /studioIssueItems\(result\.reason_codes, result\.validation\.issues\)/);
  assert.match(studioClient, /const sectionsByCode = new Map/);
  assert.match(studioClient, /safeStudioIssueMessages\.get\(code\)/);
  assert.match(studioClient, /safeIssueSection\(issue\.message\)/);
  assert.match(studioClient, /Validation stopped this proposal before delivery/);
  assert.match(studioClient, /No title, summary, perspective, or mission is available/);
  assert.match(studioClient, /rejectedIssues\.map/);
  assert.doesNotMatch(
    studioClient,
    /\.\.\.result\.reason_codes[\s\S]*result\.validation\.issues\.map/,
  );
});

test("legacy generic Studio interpretation is retired in favour of versioned scenarios", async () => {
  const response = await studioInterpret(JSON.stringify({ request_id: "req-ff-20260808-001" }));
  assert.equal(response.status, 410);
  assert.deepEqual(await response.json(), {
    stage: "studio_scenario",
    code: "studio_scenario_required",
    retryable: false,
    message: "Select and prepare a versioned Studio scenario before starting a live interpretation.",
  });
});

test("Studio prepares an exact catalog scenario without sending a provider payload", async () => {
  const scenario = testStudioScenario();
  const preparation = {
    schema_version: "2.1",
    scenario,
    status: "ready",
    telemetry_summary: {
      request_id: "req-studio-test",
      target_player_id: "player-1",
      match_count: 1,
      raw_event_count: 1,
      consent_safe_player_count: 2,
      invitation_eligible_count: 2,
      active_player_count: 1,
      matches: [{
        match_id: "match-1",
        game: "free_fire",
        mode: "battle_royale_squad",
        map_name: "Bermuda",
        started_at: "2026-08-09T10:00:00Z",
        placement: 5,
        event_count: 1,
      }],
    },
    normalization: { normalized_match_count: 1, normalized_event_count: 1, issue_codes: [] },
    privacy: { redaction_count: 0, anonymous_player_count: 0 },
    eligible_windows: [{
      window_id: "window-1",
      match_id: "match-1",
      event_ids: ["event-1"],
      participant_ids: ["player-1", "player-2"],
      start_seconds: 1,
      end_seconds: 1,
    }],
    mission_candidates: [
      {
        candidate_id: "candidate-entry",
        window_id: "window-1",
        recipe: "remix",
        objective_role: "prerequisite",
        required: true,
        compatibility_tags: ["squad_entry"],
        assigned_player_id: null,
        source_event_ids: ["event-1"],
        verification: {
          metric: "squad.participant_ids",
          operator: "contains_all",
          target: ["player-1", "player-2"],
        },
      },
      {
        candidate_id: "candidate-0",
        window_id: "window-1",
        recipe: "remix",
        objective_role: "completion",
        required: true,
        compatibility_tags: ["match_completion"],
        assigned_player_id: null,
        source_event_ids: ["event-1"],
        verification: {
          metric: "squad.matches_completed",
          operator: "at_least",
          target: 1,
        },
      },
      {
        candidate_id: "candidate-1",
        window_id: "window-1",
        recipe: "remix",
        objective_role: "primary",
        required: true,
        compatibility_tags: ["support_action", "individual_assignment"],
        assigned_player_id: "player-1",
        source_event_ids: ["event-1"],
        verification: {
          metric: "match.first_squad_revive_actor_id",
          operator: "equals",
          target: "player-1",
        },
      },
    ],
    mission_affordances: [{
      affordance_id: "affordance-1",
      family: "role_reversal",
      window_id: "window-1",
      source_event_ids: ["event-1"],
      source_match_ids: ["match-1"],
      source_context_ids: ["context:reunion_eligible"],
      parameters: {
        original_rescuer_id: "player-2",
        original_saved_player_id: "player-1",
        invitation_player_ids: ["player-1", "player-2"],
      },
      objective_candidate_ids: ["candidate-entry", "candidate-1", "candidate-0"],
      allowed_reason_codes: [
        "directly_inverts_original_roles",
        "deterministically_verifiable",
      ],
    }],
  };
  const prepared = await postWithBackendStub(
    "/api/studio/scenarios/prepare",
    JSON.stringify({ scenario }),
    preparation,
    { requestOrigin: "https://memoryos.example" },
  );
  assert.equal(prepared.response.status, 200);
  assert.deepEqual(await prepared.response.json(), preparation);
  assert.match(prepared.upstreamRequest.input, /\/v2\/studio\/scenarios\/rescue-role-reversal\/prepare$/);
  assert.equal(prepared.upstreamRequest.init.method, "POST");
  assert.equal(prepared.upstreamRequest.init.body, undefined);
  assert.equal(prepared.response.headers.get("cache-control"), "no-store");

  const malformedPreparation = structuredClone(preparation);
  malformedPreparation.mission_affordances[0].allowed_reason_codes = [];
  const malformed = await postWithBackendStub(
    "/api/studio/scenarios/prepare",
    JSON.stringify({ scenario }),
    malformedPreparation,
    { requestOrigin: "https://memoryos.example" },
  );
  assert.equal(malformed.response.status, 502);
  assert.equal((await malformed.response.json()).code, "scenario_version_mismatch");
});

test("Studio accepts grounded landing-rendezvous and duo-assist preparation payloads", async () => {
  const cases = [
    {
      scenarioId: "landing-rendezvous",
      family: "landing_rendezvous",
      metric: "match.invited_squad_lands_at_location",
      target: "Peak",
      operator: "equals",
    },
    {
      scenarioId: "duo-assist",
      family: "duo_assist",
      metric: "match.assigned_player_assisted_elimination_player_ids",
      target: ["player-2"],
      operator: "contains_all",
    },
  ];

  for (const [index, scenarioCase] of cases.entries()) {
    const scenario = {
      ...testStudioScenario(),
      scenario_id: scenarioCase.scenarioId,
      title: scenarioCase.family,
      expected_mission_family: scenarioCase.family,
      fixture_sha256: String(index + 1).repeat(64),
      fixture_revision: `2.1:${String(index + 1).repeat(12)}`,
    };
    const baselineId = `candidate-baseline-${index + 1}`;
    const entryId = `candidate-entry-${index + 1}`;
    const candidateId = `candidate-${index + 1}`;
    const preparation = {
      schema_version: "2.1",
      scenario,
      status: "ready",
      telemetry_summary: {
        request_id: `req-studio-${index + 1}`,
        target_player_id: "player-1",
        match_count: 1,
        raw_event_count: 2,
        consent_safe_player_count: 2,
        invitation_eligible_count: 2,
        active_player_count: 2,
        matches: [{
          match_id: "match-1",
          game: "free_fire",
          mode: "battle_royale_squad",
          map_name: "Bermuda",
          started_at: "2026-08-09T10:00:00Z",
          placement: 5,
          event_count: 2,
        }],
      },
      normalization: { normalized_match_count: 1, normalized_event_count: 2, issue_codes: [] },
      privacy: { redaction_count: 0, anonymous_player_count: 0 },
      eligible_windows: [{
        window_id: "window-1",
        match_id: "match-1",
        event_ids: ["event-1", "event-2"],
        participant_ids: ["player-1", "player-2"],
        start_seconds: 1,
        end_seconds: 2,
      }],
      mission_candidates: [
        {
          candidate_id: entryId,
          window_id: "window-1",
          recipe: "remix",
          objective_role: "prerequisite",
          required: true,
          compatibility_tags: ["squad_entry"],
          assigned_player_id: null,
          source_event_ids: ["event-1"],
          verification: {
            metric: "squad.participant_ids",
            operator: "contains_all",
            target: ["player-1", "player-2"],
          },
        },
        {
          candidate_id: baselineId,
          window_id: "window-1",
          recipe: "remix",
          objective_role: "completion",
          required: true,
          compatibility_tags: ["match_completion"],
          assigned_player_id: null,
          source_event_ids: ["event-1"],
          verification: {
            metric: "squad.matches_completed",
            operator: "at_least",
            target: 1,
          },
        },
        {
          candidate_id: candidateId,
          window_id: "window-1",
          recipe: "remix",
          objective_role: "primary",
          required: true,
          compatibility_tags: scenarioCase.family === "duo_assist"
            ? ["combat", "individual_assignment"]
            : ["location", "squad_coordination"],
          assigned_player_id: scenarioCase.family === "duo_assist" ? "player-1" : null,
          source_event_ids: ["event-1", "event-2"],
          verification: {
            metric: scenarioCase.metric,
            operator: scenarioCase.operator,
            target: scenarioCase.target,
          },
        },
      ],
      mission_affordances: [{
        affordance_id: `affordance-${index + 1}`,
        family: scenarioCase.family,
        window_id: "window-1",
        source_event_ids: ["event-1", "event-2"],
        source_match_ids: ["match-1"],
        source_context_ids: ["context:reunion_eligible"],
        parameters: scenarioCase.family === "landing_rendezvous"
          ? {
              landing_location: "Peak",
              invitation_player_ids: ["player-1", "player-2"],
            }
          : {
              assister_player_id: "player-1",
              elimination_player_id: "player-2",
              assist_window_seconds: 30,
              invitation_player_ids: ["player-1", "player-2"],
            },
        objective_candidate_ids: [entryId, candidateId, baselineId],
        allowed_reason_codes: [
          scenarioCase.family === "landing_rendezvous"
            ? "shared_landing_point"
            : "proven_assist_pair",
          "deterministically_verifiable",
        ],
      }],
    };

    const prepared = await postWithBackendStub(
      "/api/studio/scenarios/prepare",
      JSON.stringify({ scenario }),
      preparation,
      { requestOrigin: "https://memoryos.example" },
    );
    assert.equal(prepared.response.status, 200, scenarioCase.scenarioId);
    const body = await prepared.response.json();
    assert.equal(body.mission_affordances[0].family, scenarioCase.family);
    assert.match(prepared.upstreamRequest.input, new RegExp(`/v2/studio/scenarios/${scenarioCase.scenarioId}/prepare$`));
  }
});

test("provider-consuming routes require a strict local browser request", async () => {
  const telemetry = await unifiedPlayerTelemetry();
  const scenario = testStudioScenario();
  const routeCases = [
    {
      path: "/api/delivery/prepare",
      body: playerPrepareBody(telemetry),
      upstream: createTestLiveDelivery(telemetry),
    },
    {
      path: "/api/studio/scenarios/interpret",
      body: JSON.stringify({ scenario }),
      upstream: {
        schema_version: "2.1",
        scenario,
        result: createTestLiveDelivery(telemetry),
      },
    },
  ];
  const rejectedBrowserShapes = [
    { label: "missing Origin", options: { requestOrigin: "http://localhost", browserHeaders: false } },
    { label: "forged hosted same-origin headers", options: { requestOrigin: "https://memoryos.example" } },
    {
      label: "cross-site fetch",
      options: {
        requestOrigin: "http://localhost",
        headers: { origin: "http://localhost", "sec-fetch-site": "cross-site" },
      },
    },
  ];

  for (const routeCase of routeCases) {
    for (const rejected of rejectedBrowserShapes) {
      const blocked = await postWithBackendStub(
        routeCase.path,
        routeCase.body,
        routeCase.upstream,
        rejected.options,
      );
      assert.equal(blocked.response.status, 403, `${routeCase.path}: ${rejected.label}`);
      assert.equal((await blocked.response.json()).code, "local_browser_required");
      assert.equal(blocked.upstreamRequest, null, `${routeCase.path}: ${rejected.label} must not fetch`);
    }

    const allowed = await postWithBackendStub(
      routeCase.path,
      routeCase.body,
      routeCase.upstream,
      { requestOrigin: "http://localhost" },
    );
    assert.equal(allowed.response.status, 200, `${routeCase.path}: valid localhost browser request`);
    assert.ok(allowed.upstreamRequest, `${routeCase.path}: valid localhost request should reach the backend`);
  }
});

test("player delivery boundary strips judge internals and refuses deterministic or rejected prose", async () => {
  const telemetry = await unifiedPlayerTelemetry();
  const deterministicResult = createTestLiveDelivery(telemetry, { studioOrigin: true });

  const deterministic = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    deterministicResult,
  );
  assert.equal(deterministic.response.status, 422);
  const deterministicBody = await deterministic.response.json();
  assert.equal(deterministicBody.code, "memory_withheld");
  assert.doesNotMatch(JSON.stringify(deterministicBody), /A Squad Moment|grounded_claims|studio_trace/i);

  const liveResult = createTestLiveDelivery(telemetry);
  const live = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    liveResult,
  );
  assert.equal(live.response.status, 200);
  assert.equal(live.response.headers.get("cache-control"), "no-store");
  assert.match(live.upstreamRequest.input, /\/v2\/memories\/interpret-varied-delivery$/);
  const firstUpstreamEnvelope = JSON.parse(live.upstreamRequest.init.body);
  assert.deepEqual(Object.keys(firstUpstreamEnvelope).sort(), ["generation_nonce", "telemetry"]);
  assert.deepEqual(firstUpstreamEnvelope.telemetry, telemetry);
  assert.match(
    firstUpstreamEnvelope.generation_nonce,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );
  const playerDelivery = await live.response.json();
  assert.equal(playerDelivery.schema_version, "2.1");
  assert.equal(playerDelivery.status, "pending_player_decision");
  assert.equal(playerDelivery.metadata.content_origin, "live_ai_validated");
  assert.equal(playerDelivery.perspective.display_name, "Lee");
  assert.equal(playerDelivery.invitation_roster.length, 4);
  assert.equal(playerDelivery.invitation_roster.filter((recipient) => recipient.activity === "away").length, 2);
  assert.ok(playerDelivery.invitation_roster.every((recipient) => /^recipient-\d+$/.test(recipient.recipient_ref)));
  assert.equal(liveResult.next_chapter.objectives.length, 4);
  assert.equal(playerDelivery.next_chapter.objectives.length, 4);
  assert.deepEqual(
    playerDelivery.next_chapter.objectives.slice(0, 2).map((objective) => objective.description),
    ["Play a match with the invited squad.", "Lee completes the squad's first revive."],
  );
  assert.equal(playerDelivery.next_chapter.objectives[1].assigned_recipient_ref, "recipient-1");
  assert.match(playerDelivery.next_chapter.objectives[2].description, /Pochinok/i);
  assert.match(playerDelivery.next_chapter.objectives[3].description, /Complete at least 1 match/i);
  for (const internal of ["player_perspectives", "grounded_claims", "studio_trace", "validation", "reason_codes", "consent", "matches"]) {
    assert.equal(Object.hasOwn(playerDelivery, internal), false, `${internal} must remain server-side`);
  }
  assert.doesNotMatch(JSON.stringify(playerDelivery), /ff-player-|event_id|supporting_|verification|generation_nonce|matches|consent/i);

  const rerun = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    liveResult,
  );
  assert.equal(rerun.response.status, 200);
  const rerunEnvelope = JSON.parse(rerun.upstreamRequest.init.body);
  assert.notEqual(rerunEnvelope.generation_nonce, firstUpstreamEnvelope.generation_nonce);
  assert.doesNotMatch(JSON.stringify(await rerun.response.json()), /generation_nonce|ff-player-|event_id|matches|consent/i);

  const placementResult = structuredClone(liveResult);
  placementResult.next_chapter.family = "redemption";
  placementResult.next_chapter.objectives[1] = {
    ...placementResult.next_chapter.objectives[1],
    description: "Reach the top three in the new match.",
    assigned_player_id: null,
    verification: {
      metric: "match.top_three_reached",
      operator: "equals",
      target: true,
    },
  };
  placementResult.studio_trace.mission_candidates[1] = {
    ...placementResult.studio_trace.mission_candidates[1],
    assigned_player_id: null,
    verification: placementResult.next_chapter.objectives[1].verification,
  };
  placementResult.studio_trace.mission_affordances[0] = {
    ...placementResult.studio_trace.mission_affordances[0],
    family: "redemption",
    parameters: {
      target_placement_max: 3,
      invitation_player_ids: [...placementResult.next_chapter.invitation_player_ids],
    },
    allowed_reason_codes: ["repeated_near_miss", "deterministically_verifiable"],
  };
  placementResult.studio_trace.mission_selection.selected_family = "redemption";
  placementResult.studio_trace.mission_selection.reason_codes = ["repeated_near_miss"];
  const placement = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    placementResult,
  );
  assert.equal(placement.response.status, 200);
  const placementDelivery = await placement.response.json();
  assert.deepEqual(
    placementDelivery.next_chapter.objectives.map((objective) => objective.description),
    [
      "Play a match with the invited squad.",
      "Reach the top three in the new match.",
      "Visit Pochinok with the invited squad.",
      "Complete at least 1 match.",
    ],
  );

  const inconsistentFamily = structuredClone(liveResult);
  inconsistentFamily.next_chapter.family = "duo_assist";
  const inconsistent = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    inconsistentFamily,
  );
  assert.equal(inconsistent.response.status, 422);
  assert.equal((await inconsistent.response.json()).code, "memory_withheld");

  const landingResult = structuredClone(liveResult);
  landingResult.next_chapter.family = "landing_rendezvous";
  landingResult.next_chapter.objectives[1] = {
    ...landingResult.next_chapter.objectives[1],
    description: "Land at Peak with the invited squad.",
    assigned_player_id: null,
    verification: {
      metric: "match.invited_squad_lands_at_location",
      operator: "equals",
      target: "Peak",
    },
  };
  landingResult.studio_trace.mission_candidates[1] = {
    ...landingResult.studio_trace.mission_candidates[1],
    assigned_player_id: null,
    verification: landingResult.next_chapter.objectives[1].verification,
  };
  landingResult.studio_trace.mission_affordances[0] = {
    ...landingResult.studio_trace.mission_affordances[0],
    family: "landing_rendezvous",
    parameters: {
      landing_location: "Peak",
      invitation_player_ids: [...landingResult.next_chapter.invitation_player_ids],
    },
    allowed_reason_codes: ["shared_landing_point", "deterministically_verifiable"],
  };
  landingResult.studio_trace.mission_selection.selected_family = "landing_rendezvous";
  landingResult.studio_trace.mission_selection.reason_codes = ["shared_landing_point"];
  const landing = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    landingResult,
  );
  assert.equal(landing.response.status, 200);
  const landingDelivery = await landing.response.json();
  assert.equal(landingDelivery.next_chapter.family, "landing_rendezvous");
  assert.match(landingDelivery.next_chapter.objectives[1].description, /Land at Peak/i);

  const duoResult = structuredClone(liveResult);
  duoResult.next_chapter.family = "duo_assist";
  duoResult.next_chapter.objectives[1] = {
    ...duoResult.next_chapter.objectives[1],
    description: "Lee assists Mei with an elimination.",
    assigned_player_id: "ff-player-lee",
    verification: {
      metric: "match.assigned_player_assisted_elimination_player_ids",
      operator: "contains_all",
      target: ["ff-player-mei"],
    },
  };
  duoResult.studio_trace.mission_candidates[1] = {
    ...duoResult.studio_trace.mission_candidates[1],
    assigned_player_id: "ff-player-lee",
    verification: duoResult.next_chapter.objectives[1].verification,
  };
  duoResult.studio_trace.mission_affordances[0] = {
    ...duoResult.studio_trace.mission_affordances[0],
    family: "duo_assist",
    parameters: {
      assister_player_id: "ff-player-lee",
      elimination_player_id: "ff-player-mei",
      assist_window_seconds: 30,
      invitation_player_ids: [...duoResult.next_chapter.invitation_player_ids],
    },
    allowed_reason_codes: ["proven_assist_pair", "deterministically_verifiable"],
  };
  duoResult.studio_trace.mission_selection.selected_family = "duo_assist";
  duoResult.studio_trace.mission_selection.reason_codes = ["proven_assist_pair"];
  const duo = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    duoResult,
  );
  assert.equal(duo.response.status, 200);
  const duoDelivery = await duo.response.json();
  assert.equal(duoDelivery.next_chapter.family, "duo_assist");
  assert.match(duoDelivery.next_chapter.objectives[1].description, /Lee assists Mei/i);
  assert.equal(duoDelivery.next_chapter.objectives[1].assigned_recipient_ref, "recipient-1");

  const obsoleteOutput = structuredClone(liveResult);
  obsoleteOutput.schema_version = "2.0";
  const obsolete = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    obsoleteOutput,
  );
  assert.equal(obsolete.response.status, 422);
  assert.equal((await obsolete.response.json()).code, "memory_withheld");

  const disguisedFallback = structuredClone(liveResult);
  disguisedFallback.metadata.grounded_render = true;
  const fallback = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    disguisedFallback,
  );
  assert.equal(fallback.response.status, 422);
  assert.equal((await fallback.response.json()).code, "memory_withheld");

  const savedReplay = structuredClone(liveResult);
  savedReplay.metadata.content_origin = "saved_live_replay";
  const replayAtPlayerBoundary = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    savedReplay,
  );
  assert.equal(replayAtPlayerBoundary.response.status, 422);
  assert.equal((await replayAtPlayerBoundary.response.json()).code, "memory_withheld");

  const abstentionResult = {
    schema_version: "2.1",
    request_id: telemetry.request_id,
    status: "not_generated",
    reason_codes: ["ai_no_meaningful_episode"],
    player_perspectives: [],
    validation: { passed: true, correction_attempted: false, issues: [] },
    studio_trace: deterministicResult.studio_trace,
    metadata: { ...liveResult.metadata, content_origin: "no_player_content" },
  };
  const abstention = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    abstentionResult,
  );
  assert.equal(abstention.response.status, 200);
  assert.deepEqual(await abstention.response.json(), {
    schema_version: "2.1",
    request_id: telemetry.request_id,
    status: "not_generated",
    reason_code: "ai_no_meaningful_episode",
  });

  const rejectedWithSentinel = {
    schema_version: "2.1",
    request_id: telemetry.request_id,
    delivery_id: null,
    status: "rejected",
    reason_codes: ["unsupported_claim"],
    memory: null,
    player_perspectives: [],
    next_chapter: null,
    grounded_claims: [],
    validation: { passed: false, correction_attempted: true, issues: [{ code: "unsupported_claim" }] },
    studio_trace: deterministicResult.studio_trace,
    metadata: liveResult.metadata,
    rejected_generated_prose: "REJECTED_PROSE_MUST_NOT_CROSS_THE_PLAYER_BOUNDARY",
  };
  const rejected = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    rejectedWithSentinel,
  );
  assert.equal(rejected.response.status, 422);
  const rejectedBody = await rejected.response.text();
  assert.doesNotMatch(rejectedBody, /REJECTED_PROSE|unsupported_claim|studio_trace/i);
});

test("player route accepts only opaque allowlisted experience references", async () => {
  const telemetry = await unifiedPlayerTelemetry();
  const upstream = createTestLiveDelivery(telemetry);
  const rejectedBodies = [
    telemetry,
    { experience_ref: "squad-signal-99", request_id: telemetry.request_id },
    { experience_ref: playerExperienceRef, request_id: "req-forged-binding" },
    { experience_ref: playerExperienceRef, request_id: telemetry.request_id, matches: telemetry.matches },
  ];

  for (const body of rejectedBodies) {
    const rejected = await postWithBackendStub(
      "/api/delivery/prepare",
      JSON.stringify(body),
      upstream,
    );
    assert.equal(rejected.response.status, 422);
    assert.equal((await rejected.response.json()).code, "invalid_player_experience");
    assert.equal(rejected.upstreamRequest, null);
  }
});

test("player route never reflects private telemetry or generation nonces from failures", async () => {
  const telemetry = await unifiedPlayerTelemetry();
  const sentinel = "PRIVATE_GENERATION_NONCE_MUST_NOT_CROSS";
  const failed = await postWithBackendStub(
    "/api/delivery/prepare",
    playerPrepareBody(telemetry),
    {
      stage: "memory_interpretation",
      code: "provider_unavailable",
      retryable: true,
      message: `${sentinel}:${telemetry.matches[0].events[0].event_id}`,
      generation_nonce: sentinel,
      telemetry,
    },
    { upstreamStatus: 503 },
  );

  assert.equal(failed.response.status, 503);
  const safeBody = await failed.response.json();
  assert.deepEqual(safeBody, {
    stage: "memory_interpretation",
    code: "provider_unavailable",
    retryable: true,
    message: "The live AI service is temporarily unavailable.",
  });
  assert.doesNotMatch(JSON.stringify(safeBody), new RegExp(`${sentinel}|${telemetry.matches[0].events[0].event_id}`));
});

test("Studio fails closed when a live run has no exact registered replay", async () => {
  const scenario = testStudioScenario();
  const providerMessageSentinel = "PRIVATE_PROVIDER_BODY_MUST_NOT_CROSS";
  const rateLimited = await postWithBackendStub(
    "/api/studio/scenarios/interpret",
    JSON.stringify({ scenario }),
    {
      stage: "memory_interpretation",
      code: "provider_rate_limited",
      retryable: true,
      message: providerMessageSentinel,
      raw_provider_body: providerMessageSentinel,
    },
    { upstreamStatus: 503, requestOrigin: "http://localhost" },
  );
  assert.equal(rateLimited.response.status, 503);
  const safeRateLimit = await rateLimited.response.json();
  assert.deepEqual(
    { stage: safeRateLimit.stage, code: safeRateLimit.code, retryable: safeRateLimit.retryable },
    { stage: "memory_interpretation", code: "provider_rate_limited", retryable: true },
  );
  assert.match(safeRateLimit.message, /rate limit was reached/i);
  assert.doesNotMatch(JSON.stringify(safeRateLimit), new RegExp(providerMessageSentinel));

  const offline = await postWithBackendStub(
    "/api/studio/scenarios/interpret",
    JSON.stringify({ scenario }),
    { stage: "ai_interpretation", code: "live_ai_required", retryable: true, message: "Live AI is unavailable." },
    { upstreamStatus: 503, requestOrigin: "http://localhost" },
  );
  assert.equal(offline.response.status, 503);
  assert.equal(offline.response.headers.get("cache-control"), "no-store");
  assert.equal((await offline.response.json()).code, "studio_live_run_withheld");
  assert.match(offline.upstreamRequest.input, /\/v2\/studio\/scenarios\/rescue-role-reversal\/interpret$/);

  const malformed = await postWithBackendStub(
    "/api/studio/scenarios/interpret",
    JSON.stringify({ scenario }),
    providerMessageSentinel,
    { upstreamStatus: 503, requestOrigin: "http://localhost" },
  );
  assert.equal(malformed.response.status, 503);
  const malformedBody = await malformed.response.json();
  assert.equal(malformedBody.code, "studio_live_run_withheld");
  assert.doesNotMatch(JSON.stringify(malformedBody), new RegExp(providerMessageSentinel));

  const forgedRetryability = await postWithBackendStub(
    "/api/studio/scenarios/interpret",
    JSON.stringify({ scenario }),
    {
      stage: "memory_interpretation",
      code: "provider_rate_limited",
      retryable: false,
      message: providerMessageSentinel,
    },
    { upstreamStatus: 503, requestOrigin: "http://localhost" },
  );
  assert.equal((await forgedRetryability.response.json()).code, "studio_live_run_withheld");

  const telemetry = JSON.parse(
    await readFile(new URL("../data/raw_telemetry_v2.json", import.meta.url), "utf8"),
  );
  const noncanonical = await postWithBackendStub(
    "/api/studio/scenarios/interpret",
    JSON.stringify({ scenario }),
    {
      schema_version: "2.1",
      scenario,
      result: createTestLiveDelivery(telemetry, { studioOrigin: true }),
    },
    { requestOrigin: "http://localhost" },
  );
  assert.equal(noncanonical.response.status, 502);
  assert.equal((await noncanonical.response.json()).code, "noncanonical_live_result");
});

test("Studio trace lookup is same-origin, private, and carries source-quality state", async () => {
  const telemetry = JSON.parse(
    await readFile(new URL("../data/raw_telemetry_v2.json", import.meta.url), "utf8"),
  );
  const qualityTrace = structuredClone(createTestLiveDelivery(telemetry).studio_trace);
  qualityTrace.source_quality_flag = true;
  qualityTrace.stages.at(-1).status = "complete";
  qualityTrace.stages.at(-1).summary = "Details-wrong feedback was recorded for source-quality review.";

  const blocked = await postWithBackendStub(
    "/api/studio/delivery-trace",
    JSON.stringify({ delivery_id: "studio-demo-delivery-001" }),
    qualityTrace,
    { headers: { origin: "https://evil.example", "sec-fetch-site": "cross-site" } },
  );
  assert.equal(blocked.response.status, 403);
  assert.equal(blocked.upstreamRequest, null);
  assert.equal(blocked.response.headers.get("cache-control"), "no-store");

  const allowed = await postWithBackendStub(
    "/api/studio/delivery-trace",
    JSON.stringify({ delivery_id: "studio-demo-delivery-001" }),
    qualityTrace,
    { requestOrigin: "https://memoryos.example" },
  );
  assert.equal(allowed.response.status, 200);
  assert.equal(allowed.response.headers.get("cache-control"), "no-store");
  assert.match(allowed.upstreamRequest.input, /\/v2\/deliveries\/studio-demo-delivery-001\/trace$/);
  assert.equal(allowed.upstreamRequest.init.cache, "no-store");
  const returnedTrace = await allowed.response.json();
  assert.equal(returnedTrace.source_quality_flag, true);
  assert.equal(returnedTrace.stages.at(-1).status, "complete");
});
