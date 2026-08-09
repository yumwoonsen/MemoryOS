import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

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
    const headers = new Headers({ "content-type": "application/json", ...(options.headers ?? {}) });
    const response = await worker.fetch(
      new Request(`${options.requestOrigin ?? "https://memoryos.example"}${path}`, { method: "POST", headers, body }),
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
  assert.match(html, /Free Fire/i);
  assert.match(html, /Bermuda/i);
  assert.match(html, /Your original squad left a story behind/i);
  assert.match(html, /The consent-safe squad/i);
  assert.match(html, /aria-label="4 opted-in squad members"/i);
  assert.match(html, />J<\/span>/i);
  assert.doesNotMatch(html, /ff-player-|anonymous:squadmate|memory_appearance|mission_invitation/i);
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
  assert.match(html, /Accept a reunion mission first/i);
  assert.match(html, /View current memory/i);
  assert.doesNotMatch(html, /Send squad invite|Simulate rematch|Story Continues/i);
});

test("keeps the loaded player story in a simple evidence-first order", async () => {
  const source = await readFile(new URL("../app/memory-experience.tsx", import.meta.url), "utf8");
  const gist = source.indexOf("player-context-strip");
  const reason = source.indexOf("Why this memory returned");
  const recap = source.indexOf("What actually happened");
  const perspective = source.indexOf("Your side of the story");
  const chapter = source.indexOf("Reunion idea");
  const objectives = source.indexOf("player-objectives");
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

test("ships one legacy sample and one raw v2 telemetry fixture", async () => {
  const dataFiles = (await readdir(new URL("../data/", import.meta.url))).sort();
  assert.deepEqual(dataFiles, ["funny_memory.json", "raw_telemetry_v2.json"]);
  const telemetry = JSON.parse(await readFile(new URL("../data/raw_telemetry_v2.json", import.meta.url), "utf8"));
  assert.equal(telemetry.schema_version, "2.0");
  assert.ok(Array.isArray(telemetry.matches));
  for (const forbidden of ["title", "summary", "memory_type", "narrative_angle", "mission", "objectives", "resurfacing_reason", "importance"]) {
    assert.equal(JSON.stringify(telemetry).includes(`"${forbidden}"`), false, `${forbidden} must not pre-author the v2 input`);
  }
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
  assert.match(html, /Sanitized telemetry summary/i);
  assert.match(html, /Judge trace/i);
  assert.match(html, /Delivery inspector/i);
  assert.match(html, /Active generation mode/i);
  assert.match(html, /Provider check/i);
  assert.match(html, /Deterministic preparation/i);
  assert.match(html, /AI interpretation/i);
  assert.match(html, /Deterministic validation/i);
  assert.match(html, /Player decision/i);
  assert.match(html, /Run v2 interpretation audit/i);
  assert.match(html, /Open player view/i);
  assert.match(html, /active \/ invite-ready/i);
  assert.match(html, /2(?:<!-- -->)?\s*\/(?:<!-- -->)?\s*4/i);
  assert.match(html, /noindex/i);
});

test("hosted Studio labels its health state as a sample replay", async () => {
  const response = await studioHealth();

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-memoryos-mode"), "sample");
  assert.equal(response.headers.get("x-memoryos-fallback"), "hosted-sample");
  assert.deepEqual(await response.json(), {
    status: "sample",
    mode: "sample",
    inference_mode: "sample_replay",
    provider: "sample-replay",
    model: "precomputed-fixture",
    message:
      "No hosted MemoryOS backend is configured. Studio runs are labelled as sample replays.",
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
  assert.match(browserBundle, /\/api\/studio\/interpret/);
  assert.match(browserBundle, /\/api\/studio\/delivery-trace/);
  assert.match(browserBundle, /AI-grounded memory trace/i);
  assert.match(browserBundle, /Deterministic Studio demonstration/i);
  assert.match(browserBundle, /Run v2 interpretation audit/i);
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
  assert.match(browserBundle, /Reunion idea/i);
  assert.match(browserBundle, /Reunion mission steps/i);
  assert.match(browserBundle, /Accept mission/i);
  assert.match(browserBundle, /Open reunion mission/i);
  assert.match(browserBundle, /No active mission/i);
  assert.match(browserBundle, /Send squad invite/i);
  assert.match(browserBundle, /Simulate squad accepting/i);
  assert.match(browserBundle, /Start game/i);
  assert.match(browserBundle, /Story Continues/i);
  assert.match(browserBundle, /prototype objectives completed/i);
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
  const reunionCore = await readFile(new URL("../lib/reunion-flow-core.mjs", import.meta.url), "utf8");
  const proxySource = await readFile(new URL("../lib/memoryos-server.ts", import.meta.url), "utf8");
  const historyPage = await readFile(new URL("../app/history/page.tsx", import.meta.url), "utf8");
  const historyClient = await readFile(new URL("../app/history/history-experience.tsx", import.meta.url), "utf8");
  const flowProvider = await readFile(new URL("../app/player-flow-provider.tsx", import.meta.url), "utf8");
  const studioClient = await readFile(new URL("../app/studio/studio-dashboard.tsx", import.meta.url), "utf8");
  assert.match(prepareRoute, /\/v2\/memories\/interpret-delivery/);
  assert.match(prepareRoute, /projectPendingDeliveryForPlayer/);
  assert.match(prepareRoute, /isDeliveryBoundToTelemetryV2/);
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
  assert.match(memoryClient, /view\.retryable \? \(\) => void prepare\(\) : undefined/);
  assert.doesNotMatch(deliveryFlow, /validation\.issues|reason_codes|rejected.*prose/is);
  assert.match(homePage, /raw_telemetry_v2\.json/);
  assert.match(homePage, /projectTelemetryForPlayerStart/);
  assert.match(historyPage, /backend\/data\/historical_memory_packs\.json/);
  assert.match(historyPage, /CURRENT_MEMORY_MATCH_ID/);
  assert.match(memoryClient, /Accept mission/);
  assert.match(memoryClient, /Not relevant to me/);
  assert.match(memoryClient, /Details are wrong/);
  assert.match(memoryClient, /Keep reviewing/);
  assert.match(memoryClient, /source-quality signal/);
  assert.match(memoryClient, /Mission accepted/);
  assert.match(memoryClient, /deliveryModeLabel/);
  assert.match(memoryClient, /\/api\/delivery\/prepare/);
  assert.match(memoryClient, /\/api\/delivery\/decision/);
  assert.match(memoryClient, /isDeliveryBoundToSeed/);
  assert.match(memoryClient, /declineMission/);
  assert.match(deliveryFlow, /parsePlayerDeliveryResultV2/);
  assert.match(playerProjection, /projectPendingDeliveryForPlayer/);
  assert.match(playerProjection, /content_origin: "live_ai_validated"/);
  assert.match(playerProjection, /verified_moments/);
  assert.match(playerProjection, /perspective:/);
  assert.match(playerProjection, /invitation_roster/);
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
  assert.match(missionClient, /Story Continues/);
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
  assert.doesNotMatch(memoryClient, /Deterministic fallback|evidence-checked/);
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

test("hosted v2 Studio exposes a grounded, privacy-safe responsibility trace", async () => {
  const response = await studioInterpret(JSON.stringify({ request_id: "req-ff-20260808-001" }));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-memoryos-mode"), "sample");
  assert.equal(response.headers.get("x-memoryos-fallback"), "hosted-sample");
  const result = await response.json();
  assert.equal(result.schema_version, "2.1");
  assert.equal(result.status, "pending_player_decision");
  assert.equal(result.metadata.mode, "deterministic");
  assert.deepEqual(
    result.studio_trace.stages.map((stage) => stage.stage),
    ["deterministic_preparation", "ai_interpretation", "deterministic_validation", "player_decision"],
  );
  assert.equal(result.studio_trace.stages.at(-1).status, "pending");
  assert.equal(result.studio_trace.source_quality_flag, false);
  assert.equal(result.studio_trace.normalized_match_count, 2);
  assert.equal(result.studio_trace.normalized_event_count, 10);
  assert.equal(result.studio_trace.privacy_redaction_count, 0);
  assert.equal(result.studio_trace.eligible_windows.length, 1);
  assert.equal(result.studio_trace.active_player_count, 2);
  assert.equal(result.studio_trace.invitation_eligible_count, 4);
  assert.deepEqual(result.studio_trace.mission_affordances.map((item) => item.family), ["reunion", "role_reversal"]);
  assert.equal(result.studio_trace.mission_selection.selected_family, "role_reversal");
  assert.equal(result.metadata.content_origin, "deterministic_studio_sample");
  assert.equal(result.metadata.model, "fixed-synthetic-studio-fixture");
  assert.match(result.studio_trace.stages[0].summary, /fixed synthetic telemetry.*one neutral event window/i);
  assert.ok(result.grounded_claims.length > 0);
  assert.equal(result.studio_trace.claim_mappings.length, result.grounded_claims.length);
  assert.equal(
    result.next_chapter.objectives[0].objective_id,
    "reunion_participants:remix:window_ff-match-01J4Y7M8W2_2",
  );
  assert.equal(result.player_perspectives.length, 4);

  const selectedAffordance = result.studio_trace.mission_affordances.find(
    (item) => item.affordance_id === result.studio_trace.mission_selection.selected_affordance_id,
  );
  assert.ok(selectedAffordance);
  assert.deepEqual(
    result.next_chapter.objectives.map((objective) => objective.objective_id),
    selectedAffordance.objective_candidate_ids,
  );
  const candidatesById = new Map(
    result.studio_trace.mission_candidates.map((candidate) => [candidate.candidate_id, candidate]),
  );
  for (const candidateId of selectedAffordance.objective_candidate_ids) {
    assert.equal(candidatesById.get(candidateId)?.recipe, result.next_chapter.recipe);
  }

  const syntheticFixture = JSON.parse(
    await readFile(new URL("../data/raw_telemetry_v2.json", import.meta.url), "utf8"),
  );
  const expectedInvitees = syntheticFixture.squad.players
    .filter((player) => player.consent.memory_appearance && player.consent.mission_invitation)
    .map((player) => player.player_id);
  assert.deepEqual(result.next_chapter.invitation_player_ids, expectedInvitees);
  assert.deepEqual(
    result.next_chapter.objectives[0].verification.target,
    expectedInvitees,
  );

  const v21Telemetry = JSON.parse(
    await readFile(new URL("../data/raw_telemetry_v2.json", import.meta.url), "utf8"),
  );
  v21Telemetry.schema_version = "2.1";
  const v21Response = await studioInterpret(JSON.stringify(v21Telemetry));
  assert.equal(v21Response.status, 200);

  const invalid = await studioInterpret("{}");
  assert.equal(invalid.status, 422);
  assert.equal((await invalid.json()).code, "invalid_raw_telemetry_v2");
});

test("hosted Studio replay never derives identities from an opted-out submitted batch", async () => {
  const submitted = JSON.parse(
    await readFile(new URL("../data/raw_telemetry_v2.json", import.meta.url), "utf8"),
  );
  submitted.request_id = "req-private-submission-must-not-replay";
  submitted.squad.squad_id = "submitted-private-squad";

  const replacementIds = new Map(
    submitted.squad.players.map((player, index) => [player.player_id, `submitted-private-player-${index + 1}`]),
  );
  submitted.target_player_id = replacementIds.get(submitted.target_player_id);
  submitted.squad.players.forEach((player, index) => {
    player.player_id = replacementIds.get(player.player_id);
    player.display_name = `DO_NOT_REPLAY_PLAYER_${index + 1}`;
    player.consent = {
      memory_appearance: false,
      identity_display: false,
      media_use: false,
      mission_invitation: false,
    };
  });
  submitted.matches.forEach((match) => {
    match.events.forEach((event) => {
      if (event.actor_id) event.actor_id = replacementIds.get(event.actor_id);
      if (event.target_id) event.target_id = replacementIds.get(event.target_id);
    });
  });
  submitted.current_context.active_player_ids = submitted.current_context.active_player_ids.map(
    (playerId) => replacementIds.get(playerId),
  );
  submitted.media_references.forEach((media) => {
    media.consented_player_ids = media.consented_player_ids.map((playerId) => replacementIds.get(playerId));
  });

  const response = await studioInterpret(JSON.stringify(submitted));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-memoryos-mode"), "sample");
  assert.equal(response.headers.get("x-memoryos-fallback"), "hosted-sample");
  const result = await response.json();
  const resultJson = JSON.stringify(result);

  assert.equal(result.request_id, "req-ff-20260808-001");
  assert.equal(result.metadata.content_origin, "deterministic_studio_sample");
  assert.equal(result.metadata.model, "fixed-synthetic-studio-fixture");
  assert.match(result.studio_trace.stages[0].summary, /fixed synthetic telemetry/i);
  assert.doesNotMatch(resultJson, /req-private-submission|submitted-private|DO_NOT_REPLAY/i);
});

test("player delivery boundary strips judge internals and refuses deterministic or rejected prose", async () => {
  const studioResponse = await studioInterpret(JSON.stringify({ request_id: "req-ff-20260808-001" }));
  const deterministicResult = await studioResponse.json();

  const deterministic = await postWithBackendStub(
    "/api/delivery/prepare",
    JSON.stringify({ request_id: "req-ff-20260808-001" }),
    deterministicResult,
  );
  assert.equal(deterministic.response.status, 422);
  const deterministicBody = await deterministic.response.json();
  assert.equal(deterministicBody.code, "memory_withheld");
  assert.doesNotMatch(JSON.stringify(deterministicBody), /A Squad Moment|grounded_claims|studio_trace/i);

  const liveResult = structuredClone(deterministicResult);
  liveResult.metadata = {
    provider: "groq",
    model: "openai/gpt-oss-120b",
    mode: "live_ai",
    prompt_version: "memory-interpreter-v2.11-backend-mission-copy",
    content_origin: "live_ai_validated",
    grounded_render: false,
    narrative_fallback: false,
  };
  const live = await postWithBackendStub(
    "/api/delivery/prepare",
    JSON.stringify({ request_id: "req-ff-20260808-001" }),
    liveResult,
  );
  assert.equal(live.response.status, 200);
  assert.equal(live.response.headers.get("cache-control"), "no-store");
  const playerDelivery = await live.response.json();
  assert.equal(playerDelivery.schema_version, "2.1");
  assert.equal(playerDelivery.status, "pending_player_decision");
  assert.equal(playerDelivery.metadata.content_origin, "live_ai_validated");
  assert.equal(playerDelivery.perspective.display_name, "Lee");
  assert.equal(playerDelivery.invitation_roster.length, 4);
  assert.equal(playerDelivery.invitation_roster.filter((recipient) => recipient.activity === "away").length, 2);
  assert.ok(playerDelivery.invitation_roster.every((recipient) => /^recipient-\d+$/.test(recipient.recipient_ref)));
  assert.equal(liveResult.next_chapter.objectives.length, 3);
  assert.equal(playerDelivery.next_chapter.objectives.length, 2);
  assert.equal(
    playerDelivery.next_chapter.objectives[0].description,
    "Play and complete one match with the invited squad.",
  );
  assert.match(playerDelivery.next_chapter.objectives[1].description, /Lee.*first revive/i);
  assert.equal(playerDelivery.next_chapter.objectives[1].assigned_recipient_ref, "recipient-1");
  for (const internal of ["player_perspectives", "grounded_claims", "studio_trace", "validation", "reason_codes", "consent", "matches"]) {
    assert.equal(Object.hasOwn(playerDelivery, internal), false, `${internal} must remain server-side`);
  }
  assert.doesNotMatch(JSON.stringify(playerDelivery), /ff-player-|event_id|supporting_|verification/i);

  const placementResult = structuredClone(liveResult);
  placementResult.next_chapter.family = "redemption";
  placementResult.next_chapter.objectives[2] = {
    ...placementResult.next_chapter.objectives[2],
    description: "Reach the top three in the new match.",
    assigned_player_id: null,
    verification: {
      metric: "match.top_three_reached",
      operator: "equals",
      target: true,
    },
  };
  const placement = await postWithBackendStub(
    "/api/delivery/prepare",
    JSON.stringify({ request_id: "req-ff-20260808-001" }),
    placementResult,
  );
  assert.equal(placement.response.status, 200);
  const placementDelivery = await placement.response.json();
  assert.deepEqual(
    placementDelivery.next_chapter.objectives.map((objective) => objective.description),
    [
      "Play and complete one match with the invited squad.",
      "Reach the top three in the new match.",
    ],
  );

  const obsoleteOutput = structuredClone(liveResult);
  obsoleteOutput.schema_version = "2.0";
  const obsolete = await postWithBackendStub(
    "/api/delivery/prepare",
    JSON.stringify({ request_id: "req-ff-20260808-001" }),
    obsoleteOutput,
  );
  assert.equal(obsolete.response.status, 422);
  assert.equal((await obsolete.response.json()).code, "memory_withheld");

  const disguisedFallback = structuredClone(liveResult);
  disguisedFallback.metadata.grounded_render = true;
  const fallback = await postWithBackendStub(
    "/api/delivery/prepare",
    JSON.stringify({ request_id: "req-ff-20260808-001" }),
    disguisedFallback,
  );
  assert.equal(fallback.response.status, 422);
  assert.equal((await fallback.response.json()).code, "memory_withheld");

  const abstentionResult = {
    schema_version: "2.1",
    request_id: "req-ff-20260808-001",
    status: "not_generated",
    reason_codes: ["ai_no_meaningful_episode"],
    player_perspectives: [],
    validation: { passed: true, correction_attempted: false, issues: [] },
    studio_trace: deterministicResult.studio_trace,
    metadata: { ...liveResult.metadata, content_origin: "no_player_content" },
  };
  const abstention = await postWithBackendStub(
    "/api/delivery/prepare",
    JSON.stringify({ request_id: "req-ff-20260808-001" }),
    abstentionResult,
  );
  assert.equal(abstention.response.status, 200);
  assert.deepEqual(await abstention.response.json(), {
    schema_version: "2.1",
    request_id: "req-ff-20260808-001",
    status: "not_generated",
    reason_code: "ai_no_meaningful_episode",
  });

  const rejectedWithSentinel = {
    schema_version: "2.1",
    request_id: "req-ff-20260808-001",
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
    JSON.stringify({ request_id: "req-ff-20260808-001" }),
    rejectedWithSentinel,
  );
  assert.equal(rejected.response.status, 422);
  const rejectedBody = await rejected.response.text();
  assert.doesNotMatch(rejectedBody, /REJECTED_PROSE|unsupported_claim|studio_trace/i);
});

test("player route safely projects an identity-hidden target and invitee through backend aliases", async () => {
  const telemetry = JSON.parse(
    await readFile(new URL("../data/raw_telemetry_v2.json", import.meta.url), "utf8"),
  );
  telemetry.squad.players.find((player) => player.player_id === "ff-player-lee").consent.identity_display = false;
  telemetry.squad.players.find((player) => player.player_id === "ff-player-amir").consent.identity_display = false;

  const sampleResponse = await studioInterpret(JSON.stringify({ request_id: telemetry.request_id }));
  const visibleSample = await sampleResponse.json();
  const aliasedJson = JSON.stringify(visibleSample)
    .replaceAll("ff-player-lee", "anonymous:squadmate:1")
    .replaceAll("ff-player-amir", "anonymous:squadmate:3")
    .replaceAll("Lee", "Player 1")
    .replaceAll("Amir", "Player 3");
  const hiddenDelivery = JSON.parse(aliasedJson);
  hiddenDelivery.metadata = {
    ...hiddenDelivery.metadata,
    provider: "groq",
    model: "openai/gpt-oss-20b",
    mode: "live_ai",
    prompt_version: "memory-interpreter-v2.11-backend-mission-copy",
    content_origin: "live_ai_validated",
    grounded_render: false,
    narrative_fallback: false,
  };

  const projected = await postWithBackendStub(
    "/api/delivery/prepare",
    JSON.stringify(telemetry),
    hiddenDelivery,
  );
  assert.equal(projected.response.status, 200);
  const playerDelivery = await projected.response.json();

  assert.equal(playerDelivery.perspective.display_name, "Player 1");
  assert.equal(playerDelivery.perspective.recipient_ref, "recipient-1");
  assert.deepEqual(
    playerDelivery.invitation_roster.map((recipient) => recipient.display_name),
    ["Player 1", "Mei", "Player 3", "Jo"],
  );
  assert.equal(playerDelivery.invitation_roster.find((recipient) => recipient.display_name === "Player 3").activity, "away");
  assert.ok(playerDelivery.invitation_roster.every((recipient) => /^recipient-\d+$/.test(recipient.recipient_ref)));
  assert.match(playerDelivery.verified_moments.map((moment) => moment.label).join(" / "), /A squadmate was knocked/i);

  const playerJson = JSON.stringify(playerDelivery);
  assert.doesNotMatch(playerJson, /ff-player-lee|ff-player-amir|anonymous:squadmate/i);
  assert.doesNotMatch(playerJson, /"Lee"|"Amir"/i);
  assert.doesNotMatch(playerJson, /identity_display|mission_invitation|player_perspectives|grounded_claims|studio_trace/i);

  const leakyDelivery = structuredClone(hiddenDelivery);
  leakyDelivery.memory.summary = "Lee / ff-player-lee / anonymous:squadmate:1";
  const blockedLeak = await postWithBackendStub(
    "/api/delivery/prepare",
    JSON.stringify(telemetry),
    leakyDelivery,
  );
  assert.equal(blockedLeak.response.status, 502);
  const blockedBody = await blockedLeak.response.text();
  assert.match(blockedBody, /player_projection_failed/i);
  assert.doesNotMatch(blockedBody, /ff-player-lee|anonymous:squadmate|"Lee"/i);
});

test("Studio turns a canonical live-provider 503 into an explicitly offline audit sample", async () => {
  const offline = await postWithBackendStub(
    "/api/studio/interpret",
    JSON.stringify({ request_id: "req-ff-20260808-001" }),
    { stage: "ai_interpretation", code: "live_ai_required", retryable: true, message: "Live AI is unavailable." },
    { upstreamStatus: 503, requestOrigin: "http://localhost" },
  );
  assert.equal(offline.response.status, 200);
  assert.equal(offline.response.headers.get("x-memoryos-mode"), "sample");
  assert.equal(offline.response.headers.get("x-memoryos-fallback"), "offline-studio-sample");
  assert.equal(offline.response.headers.get("cache-control"), "no-store");
  const result = await offline.response.json();
  assert.equal(result.metadata.mode, "deterministic");
  assert.match(result.studio_trace.stages[1].summary, /saved demonstration proposal/i);
});

test("Studio trace lookup is same-origin, private, and carries source-quality state", async () => {
  const studioResponse = await studioInterpret(JSON.stringify({ request_id: "req-ff-20260808-001" }));
  const result = await studioResponse.json();
  const qualityTrace = structuredClone(result.studio_trace);
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
    { headers: { origin: "https://memoryos.example", "sec-fetch-site": "same-origin" } },
  );
  assert.equal(allowed.response.status, 200);
  assert.equal(allowed.response.headers.get("cache-control"), "no-store");
  assert.match(allowed.upstreamRequest.input, /\/v2\/deliveries\/studio-demo-delivery-001\/trace$/);
  assert.equal(allowed.upstreamRequest.init.cache, "no-store");
  const returnedTrace = await allowed.response.json();
  assert.equal(returnedTrace.source_quality_flag, true);
  assert.equal(returnedTrace.stages.at(-1).status, "complete");
});
