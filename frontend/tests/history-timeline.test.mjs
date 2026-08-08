import assert from "node:assert/strict";
import test from "node:test";

import historicalPacks from "../../backend/data/historical_memory_packs.json" with { type: "json" };
import { buildSafeHistoryItems } from "../lib/history-timeline-core.mjs";

test("history keeps only verified, confirmed, deduplicated, consent-safe matches", () => {
  const items = buildSafeHistoryItems(historicalPacks);

  assert.equal(items.length, 2);
  assert.equal(items.filter((item) => item.played_at === "2026-05-10T20:00:00+08:00").length, 1);
  assert.ok(items.every((item) => item.opted_in_count >= 2));
  const privateMatch = items.find((item) => item.played_at === "2026-07-01T20:00:00+08:00");
  assert.equal(privateMatch?.consent_safe_moments, 2);
});

test("history output excludes captions, identities, raw events, and review internals", () => {
  const items = buildSafeHistoryItems(historicalPacks);
  const serialized = JSON.stringify(items);
  const allowedKeys = [
    "consent_safe_moments",
    "game",
    "map_name",
    "mode",
    "opted_in_count",
    "placement",
    "played_at",
  ];

  for (const item of items) {
    assert.deepEqual(Object.keys(item).sort(), allowedKeys);
  }
  assert.doesNotMatch(
    serialized,
    /caption|display_name|player_id|pack_id|match_id|event_id|actor_id|target_id|location|match_events|tags|reactions|current_context|source_status|meaning_status|human_review/i,
  );
  assert.doesNotMatch(serialized, /H-MATCH|h-private|"(?:Lee|Mei|Jo)"|Peak|Final Zone|vehicle_escape|Telemetry under review|Not one to resurface/i);
});
