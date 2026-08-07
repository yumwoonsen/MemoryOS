import assert from "node:assert/strict";
import test from "node:test";

import {
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
    verification: { metric: "squad_member_ids", operator: "contains_all", target: ["lee", "mei"] },
  },
  {
    objective_id: "location",
    description: "Return to Clock Tower.",
    required: true,
    verification: { metric: "visited_locations", operator: "contains_all", target: ["Clock Tower"] },
  },
  {
    objective_id: "revive",
    description: "Lee revives Mei.",
    required: true,
    verification: { metric: "revives.lee.targets", operator: "contains_all", target: ["mei"] },
  },
];

test("builds invitation recipients only from privacy-safe perspectives", () => {
  const invitees = buildInvitees([
    { player_id: "lee", display_name: "Lee" },
    { player_id: "mei", display_name: "Mei" },
    { player_id: "mei", display_name: "Duplicate Mei" },
  ], "lee");

  assert.deepEqual(invitees, [
    { player_id: "lee", display_name: "Lee", is_current_player: true },
    { player_id: "mei", display_name: "Mei", is_current_player: false },
  ]);
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
  ], "lee");
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
    metrics: { ...matchResult.metrics, visited_locations: ["Final Zone"] },
  });
  assert.equal(incomplete.complete, false);
  assert.equal(createContinuationChapter(
    { title: "Worst Plan, Best Night" },
    { title: "Chapter II: Return the Favour" },
    incomplete,
  ), null);
});
