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
  {
    objective_ref: "objective-1",
    description: "Bring the original squad back.",
    objective_role: "prerequisite",
    required: true,
  },
  {
    objective_ref: "objective-2",
    description: "Complete the selected Next Chapter.",
    objective_role: "completion",
    required: true,
  },
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
    reunion: { completion: /full squad completed one match/i, chapter: "Together Again" },
    role_reversal: { completion: /Lee completed the squad's first revival/i, chapter: "The Favour Returned" },
    redemption: { completion: /squad reached the top three/i, chapter: "The Comeback Complete" },
    return_to_place: { completion: /invited squad returned to the original location/i, chapter: "Back Where It Began" },
    landing_rendezvous: { completion: /invited squad landed together/i, chapter: "Same Drop, Same Squad" },
    duo_assist: { completion: /assigned duo combined for one elimination/i, chapter: "The Setup and the Finish" },
  };

  for (const [family, expectedResult] of Object.entries(expected)) {
    const familyObjectives = family === "role_reversal"
      ? [{ ...objectives[0], assigned_recipient_ref: "recipient-1" }, objectives[1]]
      : objectives;
    const outcome = createPrototypeMatchOutcome(family, invitees, familyObjectives);
    assert.equal(outcome.complete, true);
    assert.equal(outcome.objective_results.length, 2);
    assert.ok(outcome.objective_results.every((objective) => objective.completed));
    assert.match(outcome.completion_copy, expectedResult.completion);

    const chapter = createContinuationChapter(
      { title: "Worst Plan, Best Night" },
      { title: "Chapter II: Return the Favour" },
      outcome,
    );
    assert.ok(chapter);
    assert.equal(chapter.title, expectedResult.chapter);
    assert.notEqual(chapter.title.toLocaleLowerCase(), "return the favour");
    assert.match(chapter.summary, /Worst Plan, Best Night/);
    assert.match(chapter.summary, /Return the Favour/);
    assert.doesNotMatch(chapter.summary, /verified|live telemetry/i);
  }

  const joReversal = createPrototypeMatchOutcome(
    "role_reversal",
    invitees,
    [{ ...objectives[0], assigned_recipient_ref: "recipient-4" }],
  );
  assert.match(joReversal.completion_copy, /Jo completed the squad's first revival/i);
});

test("uses a distinct fallback when AI mission copy matches the completed title", () => {
  const invitees = buildInvitees(roster);
  const outcome = createPrototypeMatchOutcome("role_reversal", invitees, objectives);
  const chapter = createContinuationChapter(
    { title: "Escape and Recovery" },
    { title: "Chapter II: The Favour Returned" },
    outcome,
  );

  assert.ok(chapter);
  assert.equal(chapter.title, "Roles Reversed");
});

test("reports all five objectives but lets only required objectives determine completion", () => {
  const invitees = buildInvitees(roster);
  const compoundObjectives = [
    objectives[0],
    {
      objective_ref: "objective-2",
      description: "Land together at Pochinok.",
      objective_role: "primary",
      required: true,
    },
    {
      objective_ref: "objective-3",
      description: "Lee assists Mei's elimination.",
      objective_role: "support",
      required: true,
    },
    {
      objective_ref: "objective-4",
      description: "Leave the zone in the same vehicle.",
      objective_role: "bonus",
      required: false,
    },
    {
      ...objectives[1],
      objective_ref: "objective-5",
    },
  ];

  const outcome = createPrototypeMatchOutcome("landing_rendezvous", invitees, compoundObjectives);

  assert.equal(outcome.objective_results.length, 5);
  assert.deepEqual(
    outcome.objective_results.map((objective) => objective.objective_role),
    ["prerequisite", "primary", "support", "bonus", "completion"],
  );
  assert.equal(outcome.objective_results.find((objective) => objective.objective_role === "bonus")?.completed, true);
  assert.equal(outcome.complete, true);
});

test("withholds a continuation chapter for an incomplete outcome", () => {
  const invitees = buildInvitees(roster);
  const outcome = createPrototypeMatchOutcome("reunion", invitees, objectives);

  assert.equal(
    createContinuationChapter(
      { title: "Escape and Recovery" },
      { title: "Chapter II: Together Again" },
      { ...outcome, complete: false },
    ),
    null,
  );
});
