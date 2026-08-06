import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("https://memoryos.example/", {
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

test("server-renders the complete Next Chapter experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Next Chapter — Powered by MemoryOS<\/title>/i);
  assert.match(html, /Your squad has/);
  assert.match(html, /unfinished stories/);
  assert.match(html, /Discover the memory/);
  assert.match(html, /Facts in\. Verified chapter out\./);
  assert.match(html, /Canonical transformation/);
  assert.match(html, /Machine-checkable quest rules/);
  assert.match(html, /Worst Plan, Best Night/);
  assert.match(html, /Needs your call/);
  assert.match(html, /Safely skipped/);
  assert.match(html, /https:\/\/memoryos\.example\/og\.png/);
});

test("does not ship the disposable starter preview", async () => {
  const response = await render();
  const html = await response.text();

  assert.doesNotMatch(html, /codex-preview/);
  assert.doesNotMatch(html, /react-loading-skeleton/);
  assert.doesNotMatch(html, /Your site is taking shape/);
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
  const result = await response.json();
  assert.equal(result.status, "ready");
  assert.equal(result.metadata.prose_renderer, "canonical-v1");
  assert.match(result.player_perspectives[0].message, /Verified revive #1/);
  assert.match(result.next_chapter.mission, /remix "Worst Plan, Best Night"/);
});

test("hosted review sample mirrors the canonical backend contract", async () => {
  const memoryPack = await readFile(
    new URL("../data/comeback_memory.json", import.meta.url),
    "utf8",
  );
  const response = await discover(memoryPack);
  const result = await response.json();

  assert.equal(response.status, 200);
  assert.equal(result.status, "needs_human_confirmation");
  assert.equal(result.validation.scores.specificity, 1);
  assert.deepEqual(
    result.player_perspectives.find((item) => item.player_id === "kay").evidence_event_ids,
    ["evt-final-ten-01"],
  );
});

test("confirming the review sample updates confidence and review state", async () => {
  const memoryPack = JSON.parse(
    await readFile(new URL("../data/comeback_memory.json", import.meta.url), "utf8"),
  );
  memoryPack.human_memory.confirmed = true;
  const response = await discover(JSON.stringify(memoryPack));
  const result = await response.json();

  assert.equal(result.status, "ready");
  assert.equal(result.discovery.signal_score, 1);
  assert.equal(result.memory.confidence, 1);
  assert.ok(result.discovery.reasons.includes("player-confirmed meaning"));
  assert.ok(!result.validation.issues.some((issue) => issue.code === "human_confirmation_required"));
});

test("hosted discovery returns stable JSON errors", async () => {
  const malformed = await discover("not-json");
  assert.equal(malformed.status, 400);
  assert.equal(malformed.headers.get("x-memoryos-mode"), "sample");
  assert.deepEqual(await malformed.json(), {
    code: "invalid_memory_pack_json",
    message: "The Memory Pack was not valid JSON.",
  });

  const memoryPack = JSON.parse(
    await readFile(new URL("../data/funny_memory.json", import.meta.url), "utf8"),
  );
  memoryPack.pack_id = "unknown-pack";
  const unknown = await discover(JSON.stringify(memoryPack));
  assert.equal(unknown.status, 503);
  assert.equal(unknown.headers.get("x-memoryos-mode"), "sample");
  assert.equal((await unknown.json()).code, "sample_result_unavailable");
});

test("stylesheet includes the approved accessible palette", async () => {
  const css = (await readFile(new URL("../app/globals.css", import.meta.url), "utf8")).toLowerCase();

  for (const colour of ["#ffffff", "#52a6ff", "#cfffc0", "#6ec8bd", "#2c2c2c"]) {
    assert.match(css, new RegExp(colour));
  }
  assert.doesNotMatch(css, /#ff7347|#42d7c8|#080b10|#111720/);
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
});
