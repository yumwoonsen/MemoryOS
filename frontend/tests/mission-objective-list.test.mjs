import assert from "node:assert/strict";
import test from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { MissionObjectiveList } from "../app/mission-objective-list.mjs";

function objective(index, objectiveRole, required, description) {
  return {
    objective_ref: `objective-${index}`,
    description,
    objective_role: objectiveRole,
    required,
  };
}

function render(objectives, variant = "memory") {
  return renderToStaticMarkup(createElement(MissionObjectiveList, { objectives, variant }));
}

test("renders every step in a two-objective mission with distinct roles", () => {
  const html = render([
    objective(1, "prerequisite", true, "Enter with the invited squad."),
    objective(2, "completion", true, "Complete the match."),
  ]);

  assert.equal((html.match(/<li/g) ?? []).length, 2);
  assert.match(html, /class="player-objectives"/);
  assert.match(html, /data-objective-role="prerequisite"/);
  assert.match(html, />Prerequisite</);
  assert.match(html, /data-objective-role="completion"/);
  assert.match(html, />Completion</);
});

test("renders all five compound steps in order and visibly labels the bonus", () => {
  const descriptions = [
    "Enter with the invited squad.",
    "Land together at Pochinok.",
    "Lee assists Mei during an elimination.",
    "Leave the zone in the same vehicle.",
    "Complete the match.",
  ];
  const html = render([
    objective(1, "prerequisite", true, descriptions[0]),
    objective(2, "primary", true, descriptions[1]),
    objective(3, "support", true, descriptions[2]),
    objective(4, "bonus", false, descriptions[3]),
    objective(5, "completion", true, descriptions[4]),
  ], "mission");

  assert.equal((html.match(/<li/g) ?? []).length, 5);
  assert.match(html, /class="mission-objective-list"/);
  assert.match(html, /class="mission-objective is-bonus" data-objective-role="bonus"/);
  assert.match(html, />Bonus</);
  assert.ok(descriptions.every((description) => html.includes(description)));
  assert.deepEqual(
    descriptions.map((description) => html.indexOf(description))
      .map((position, index, positions) => index === 0 || position > positions[index - 1]),
    [true, true, true, true, true],
  );
});
