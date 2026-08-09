import assert from "node:assert/strict";
import test from "node:test";

import { safeStudioRuleTarget } from "../lib/studio-safe-display-core.mjs";

const players = [
  { player_id: "ff-player-lee", display_name: "Lee" },
  { player_id: "ff-player-mei", display_name: "Mei" },
];

test("Studio redacts scalar and list verification player IDs", () => {
  assert.equal(safeStudioRuleTarget("ff-player-lee", players), "Lee");
  assert.equal(
    safeStudioRuleTarget(["ff-player-lee", "ff-player-mei"], players),
    "Lee, Mei",
  );
  assert.equal(safeStudioRuleTarget("anonymous:squadmate:3", players), "Anonymous squadmate");
  assert.equal(safeStudioRuleTarget("squad", players), "Eligible squad");
});

test("Studio preserves non-identity scalar verification targets", () => {
  assert.equal(safeStudioRuleTarget("Peak", players), "Peak");
  assert.equal(safeStudioRuleTarget(3, players), "3");
  assert.equal(safeStudioRuleTarget(true, players), "true");
});
