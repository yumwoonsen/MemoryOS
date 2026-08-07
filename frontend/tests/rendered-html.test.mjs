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
  assert.match(html, /The original squad/i);
  assert.match(html, /Load this memory/i);
  assert.match(mainHtml, /href="\/studio"/i);
  assert.match(mainHtml, /Open the MemoryOS Developer Studio/i);
  assert.match(html, /free-fire-map-v2\.webp/i);
  assert.match(html, /free-fire-map-mobile-v2\.webp/i);
  assert.match(html, /https:\/\/memoryos\.example\/og\.png/);
  assert.doesNotMatch(
    mainHtml,
    /Worst Plan, Best Night|Your side of the story|What actually happened|Return the Favour|Play this challenge|Demo simulation|clock-tower-town-v2|Memory Pack|Run Memory Engine|Choose a memory signal|Facts in\. Verified chapter out\.|Canonical transformation|Tactical Round|COD Mobile|Review Studio/i,
  );
});

test("server-renders the AI Memory Inbox while it safely prepares a delivery", async () => {
  const response = await render("/history");
  assert.equal(response.status, 200);
  const html = await response.text();
  const mainHtml = html.slice(html.indexOf("<main"), html.indexOf("</main>") + "</main>".length);
  assert.match(html, /Memory inbox/i);
  assert.match(html, /Bringing a squad moment back/i);
  assert.match(html, /Preparing a grounded memory and a new chapter/i);
  assert.match(mainHtml, /href="\/studio"/i);
  assert.match(mainHtml, /Open the MemoryOS Developer Studio/i);
  assert.doesNotMatch(mainHtml, /Did this gameplay event happen|Review squad memories|Facts:/i);
});

test("keeps the loaded player story in a simple evidence-first order", async () => {
  const source = await readFile(new URL("../app/memory-experience.tsx", import.meta.url), "utf8");
  const gist = source.indexOf("memory-gist-label");
  const recap = source.indexOf("What actually happened");
  const perspective = source.indexOf("Your side of the story");
  const chapter = source.indexOf("Next Chapter");

  assert.ok(gist > -1 && gist < recap);
  assert.ok(recap < perspective);
  assert.ok(perspective < chapter);
  assert.doesNotMatch(
    source,
    /Challenge rules|objectiveRule|Verified live|Verified preview|Confirm this memory|\?\?\s*result\.player_perspectives\[0\]/i,
  );
});

test("does not ship the disposable starter preview", async () => {
  const response = await render();
  const html = await response.text();

  assert.doesNotMatch(html, /codex-preview/);
  assert.doesNotMatch(html, /react-loading-skeleton/);
  assert.doesNotMatch(html, /Your site is taking shape/);
});

test("keeps only the latest Battle Royale source pack", async () => {
  const dataFiles = (await readdir(new URL("../data/", import.meta.url))).sort();
  assert.deepEqual(dataFiles, ["funny_memory.json"]);
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
  assert.equal(result.metadata.factual_renderer, "closed-v1");
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
  assert.match(html, /Developer Dashboard/i);
  assert.match(html, /Synthetic gameplay pack/i);
  assert.match(html, /Pipeline snapshots/i);
  assert.match(html, /Generation inspector/i);
  assert.match(html, /Run pipeline audit/i);
  assert.match(html, /Open player view/i);
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

test("Studio preserves the hosted fallback reason when an edited pack has no replay", async () => {
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
  assert.match(browserBundle, /\/api\/discover/);
  assert.match(browserBundle, /\/api\/studio\/generate-stream/);
  assert.match(browserBundle, /Pipeline snapshots/i);
  assert.match(browserBundle, /\/api\/history/);
  assert.match(browserBundle, /\/api\/generate/);
  assert.match(browserBundle, /Loading squad memory/i);
  assert.match(browserBundle, /The gist/i);
  assert.match(browserBundle, /What actually happened/i);
  assert.match(browserBundle, /Your side of the story/i);
  assert.match(browserBundle, /Next Chapter/i);
  assert.match(browserBundle, /Play this challenge/i);
  assert.match(browserBundle, /View from the start/i);
  assert.doesNotMatch(
    browserBundle,
    /Memory Pack ready|Build this story|Generating from verified data|Match evidence remains the source of truth|Challenge rules|Verified live|Verified preview/i,
  );
  assert.doesNotMatch(
    browserBundle,
    /Choose a memory signal|One HP Reset|Match FF-M999|memory-pack-comeback|memory-pack-insufficient|Command Post/i,
  );
});

test("delivery routes stay server-side proxies and consumer UI has only accept or decline choices", async () => {
  const prepareRoute = await readFile(new URL("../app/api/delivery/prepare/route.ts", import.meta.url), "utf8");
  const decisionRoute = await readFile(new URL("../app/api/delivery/decision/route.ts", import.meta.url), "utf8");
  const historyPage = await readFile(new URL("../app/history/page.tsx", import.meta.url), "utf8");
  const historyClient = await readFile(new URL("../app/history/history-experience.tsx", import.meta.url), "utf8");
  assert.match(prepareRoute, /prepare-delivery/);
  assert.match(decisionRoute, /record-delivery-decision/);
  assert.match(historyPage, /backend\/data\/historical_memory_packs\.json/);
  assert.match(historyClient, /Accept mission/);
  assert.match(historyClient, /Not relevant to me/);
  assert.match(historyClient, /Details are wrong/);
  assert.doesNotMatch(historyClient, /Did this gameplay event happen|Facts:|Review this moment/);
  assert.doesNotMatch(historyClient, /127\.0\.0\.1:8000/);
});
