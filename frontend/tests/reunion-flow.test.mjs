import assert from "node:assert/strict";
import test from "node:test";

import {
  areInviteesReady,
  buildInvitees,
  createContinuationChapter,
  createSyntheticRematch,
  evaluateRule,
  verifyMission,
} from "../lib/reunion-flow-core.mjs";

const objectives = [
  {
    objective_id: "squad",
    description: "Complete a match with Lee and Mei.",
    required: true,
    verification: { metric: "squad.participant_ids", operator: "contains_all", target: ["lee", "mei"] },
  },
  {
    objective_id: "match",
    description: "Complete one match together.",
    required: true,
    verification: { metric: "squad.matches_completed", operator: "at_least", target: 1 },
  },
  {
    objective_id: "revive",
    description: "Complete one squad revive.",
    required: true,
    verification: { metric: "squad.revive_count", operator: "at_least", target: 1 },
  },
];

test("builds invitation recipients only from privacy-safe perspectives", () => {
  const invitees = buildInvitees([
    { player_id: "lee", display_name: "Lee" },
    { player_id: "mei", display_name: "Mei" },
    { player_id: "mei", display_name: "Duplicate Mei" },
    { player_id: "amir", display_name: "Inactive Amir" },
  ], "lee", ["lee", "mei"]);

  assert.deepEqual(invitees, [
    { player_id: "lee", display_name: "Lee", is_current_player: true },
    { player_id: "mei", display_name: "Mei", is_current_player: false },
  ]);
  assert.equal(areInviteesReady(invitees, ["lee"]), false);
  assert.equal(areInviteesReady(invitees, ["lee", "mei"]), true);
});

test("evaluates every supported mission rule deterministically", () => {
  assert.equal(evaluateRule({ metric: "winner", operator: "equals", target: true }, { winner: true }), true);
  assert.equal(evaluateRule({ metric: "revives", operator: "at_least", target: 2 }, { revives: 3 }), true);
  assert.equal(evaluateRule(
    { metric: "squad", operator: "contains_all", target: ["lee", "mei"] },
    { squad: ["mei", "lee", "amir"] },
  ), true);
  assert.equal(evaluateRule({ metric: "revives", operator: "at_least", target: 2 }, { revives: 1 }), false);
});

test("unlocks Story Continues only after every required objective passes", () => {
  const invitees = buildInvitees([
    { player_id: "lee", display_name: "Lee" },
    { player_id: "mei", display_name: "Mei" },
  ], "lee", ["lee", "mei"]);
  const matchResult = createSyntheticRematch(invitees);
  const verified = verifyMission(objectives, matchResult);

  assert.equal(verified.complete, true);
  assert.equal(verified.required_passed, 3);
  assert.match(
    createContinuationChapter({ title: "Worst Plan, Best Night" }, { title: "Chapter II: Return the Favour" }, verified).summary,
    /verified synthetic rematch/i,
  );

  const incomplete = verifyMission(objectives, {
    ...matchResult,
    metrics: { ...matchResult.metrics, "squad.revive_count": 0 },
  });
  assert.equal(incomplete.complete, false);
  assert.equal(createContinuationChapter(
    { title: "Worst Plan, Best Night" },
    { title: "Chapter II: Return the Favour" },
    incomplete,
  ), null);
});
