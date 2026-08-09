import assert from "node:assert/strict";
import test from "node:test";

import {
  studioInitialResultTab,
  studioInspectionDecision,
} from "../lib/studio-inspection-decision-core.mjs";

test("Studio accepts a validated live delivery for inspection by default", () => {
  assert.equal(studioInspectionDecision("live_ai_validated", "pending_player_decision"), "accepted");
  assert.equal(studioInitialResultTab("live_ai_validated", "pending_player_decision"), "mission");
});

test("Studio derives acceptance and the initial tab for every result combination", () => {
  const origins = ["live_ai_validated", "no_player_content", "saved_live_replay"];
  const statuses = ["pending_player_decision", "not_generated", "rejected"];

  for (const origin of origins) {
    for (const status of statuses) {
      const isFreshValidatedDelivery = origin === "live_ai_validated"
        && status === "pending_player_decision";
      assert.equal(
        studioInspectionDecision(origin, status),
        isFreshValidatedDelivery ? "accepted" : null,
        `${origin} / ${status}`,
      );
      assert.equal(
        studioInitialResultTab(origin, status),
        isFreshValidatedDelivery ? "mission" : "summary",
        `${origin} / ${status}`,
      );
    }
  }

  assert.equal(studioInspectionDecision(null, null), null);
});
