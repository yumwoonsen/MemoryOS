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

test("server-renders the complete Next Chapter experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Next Chapter — Powered by MemoryOS<\/title>/i);
  assert.match(html, /Your squad has/);
  assert.match(html, /unfinished stories/);
  assert.match(html, /Discover the memory/);
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
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `api-${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const memoryPack = await readFile(
    new URL("../data/funny_memory.json", import.meta.url),
    "utf8",
  );

  const response = await worker.fetch(
    new Request("https://memoryos.example/api/discover", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: memoryPack,
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

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^application\/json\b/i);
  assert.equal(response.headers.get("x-memoryos-mode"), "sample");
  assert.equal((await response.json()).status, "ready");
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
