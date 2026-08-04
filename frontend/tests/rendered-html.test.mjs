import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);

async function render() {
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the MemoryOS Review Studio", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>MemoryOS Review Studio<\/title>/i);
  assert.match(html, /Watch the AI build a memory/i);
  assert.match(html, /Make this memory live/i);
  assert.match(html, /Does this feel like your squad\?/i);
  assert.match(html, /Worst Plan, Best Night/i);
  assert.match(html, /The next chapter/i);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});
