import assert from "node:assert/strict";
import test from "node:test";

import { canGenerateAnotherGroundedChapter } from "../lib/player-rerun-flow-core.mjs";

test("reruns are available only after terminal player outcomes", () => {
  for (const state of ["no_memory", "error", "declined"]) {
    assert.equal(canGenerateAnotherGroundedChapter(state), true, state);
  }

  for (const state of [
    "unrevealed",
    "loading",
    "ready",
    "decline",
    "sending",
    "decision_error",
    "accepted",
  ]) {
    assert.equal(canGenerateAnotherGroundedChapter(state), false, state);
  }
});
