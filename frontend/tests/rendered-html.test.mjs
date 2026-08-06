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
  assert.match(html, /free-fire-map-v2\.webp/i);
  assert.match(html, /free-fire-map-mobile-v2\.webp/i);
  assert.match(html, /https:\/\/memoryos\.example\/og\.png/);
  assert.doesNotMatch(
    mainHtml,
    /Worst Plan, Best Night|Your side of the story|What actually happened|Return the Favour|Play this challenge|Demo simulation|clock-tower-town-v2|Memory Pack|Run Memory Engine|Choose a memory signal|Facts in\. Verified chapter out\.|Canonical transformation|Tactical Round|COD Mobile|Review Studio/i,
  );
});

test("server-renders the Phase 2B squad-history entry without exposing a generated memory", async () => {
  const response = await render("/history");
  assert.equal(response.status, 200);
  const html = await response.text();
  const mainHtml = html.slice(html.indexOf("<main"), html.indexOf("</main>") + "</main>".length);
  assert.match(html, /Your squad history/i);
  assert.match(html, /A few moments may be worth another look/i);
  assert.match(html, /uses match evidence and squad context/i);
  assert.match(html, /does not decide what matters to you/i);
  assert.match(html, /Review squad memories/i);
  assert.doesNotMatch(mainHtml, /Worst Plan, Best Night|Your side of the story|Next Chapter/i);
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

test("leaves the dedicated Review Studio deferred", async () => {
  const response = await render("/studio");
  assert.equal(response.status, 404);
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

test("history routes stay server-side proxies and retain the backend fixture as one source", async () => {
  const historyRoute = await readFile(new URL("../app/api/history/route.ts", import.meta.url), "utf8");
  const generateRoute = await readFile(new URL("../app/api/generate/route.ts", import.meta.url), "utf8");
  const historyPage = await readFile(new URL("../app/history/page.tsx", import.meta.url), "utf8");
  const historyClient = await readFile(new URL("../app/history/history-experience.tsx", import.meta.url), "utf8");
  assert.match(historyRoute, /discover-history/);
  assert.match(generateRoute, /\/v1\/memories\/generate/);
  assert.match(historyPage, /backend\/data\/historical_memory_packs\.json/);
  assert.match(historyClient, /Did this gameplay event happen as described/);
  assert.match(historyClient, /Is this a memory worth keeping or continuing/);
  assert.match(historyClient, /value\.status === "ready"/);
  assert.doesNotMatch(historyClient, /127\.0\.0\.1:8000/);
});
