import assert from "node:assert/strict";
import test from "node:test";

import {
  areInviteesJoined,
  buildInvitees,
  createContinuationChapter,
  createPrototypeMatchOutcome,
} from "../lib/reunion-flow-core.mjs";

const roster = [
  { recipient_ref: "recipient-1", display_name: "Lee", activity: "online", is_current_player: true },
  { recipient_ref: "recipient-2", display_name: "Mei", activity: "online", is_current_player: false },
  { recipient_ref: "recipient-3", display_name: "Amir", activity: "away", is_current_player: false },
  { recipient_ref: "recipient-4", display_name: "Jo", activity: "away", is_current_player: false },
];

const objectives = [
  { objective_ref: "objective-1", description: "Bring the original squad back.", required: true },
  { objective_ref: "objective-2", description: "Complete the selected Next Chapter.", required: true },
];

test("keeps invitation eligibility separate from online activity", () => {
  const invitees = buildInvitees([
    ...roster,
    { ...roster[1], display_name: "Duplicate Mei" },
  ]);

  assert.equal(invitees.length, 4);
  assert.deepEqual(invitees.map((invitee) => invitee.display_name), ["Lee", "Mei", "Amir", "Jo"]);
  assert.deepEqual(invitees.filter((invitee) => invitee.activity === "away").map((invitee) => invitee.display_name), ["Amir", "Jo"]);
});

test("requires every invited recipient to join before the prototype game starts", () => {
  const invitees = buildInvitees(roster);
  const pending = invitees.map((invitee) => ({
    recipient_ref: invitee.recipient_ref,
    response: invitee.is_current_player ? "self_joined" : "pending",
  }));
  assert.equal(areInviteesJoined(invitees, pending), false);

  const joined = pending.map((recipient) => ({
    ...recipient,
    response: recipient.response === "pending" ? "joined" : recipient.response,
  }));
  assert.equal(areInviteesJoined(invitees, joined), true);
});

test("uses a scripted successful outcome with mission-family-specific copy", () => {
  const invitees = buildInvitees(roster);
  const expected = {
    reunion: /full squad completed one match/i,
    role_reversal: /Lee completed the squad's first revival/i,
    redemption: /squad reached the top three/i,
  };

  for (const [family, pattern] of Object.entries(expected)) {
    const familyObjectives = family === "role_reversal"
      ? [{ ...objectives[0], assigned_recipient_ref: "recipient-1" }, objectives[1]]
      : objectives;
    const outcome = createPrototypeMatchOutcome(family, invitees, familyObjectives);
    assert.equal(outcome.complete, true);
    assert.equal(outcome.objective_results.length, 2);
    assert.ok(outcome.objective_results.every((objective) => objective.completed));
    assert.match(outcome.completion_copy, pattern);

    const chapter = createContinuationChapter(
      { title: "Worst Plan, Best Night" },
      { title: "Chapter II: Return the Favour" },
      outcome,
    );
    assert.ok(chapter);
    assert.match(chapter.summary, /In this prototype/i);
    assert.doesNotMatch(chapter.summary, /verified|live telemetry/i);
  }

  const joReversal = createPrototypeMatchOutcome(
    "role_reversal",
    invitees,
    [{ ...objectives[0], assigned_recipient_ref: "recipient-4" }],
  );
  assert.match(joReversal.completion_copy, /Jo completed the squad's first revival/i);
});
