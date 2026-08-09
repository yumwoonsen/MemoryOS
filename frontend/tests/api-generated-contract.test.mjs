import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const expectedMissionFamilies = [
  "reunion",
  "role_reversal",
  "redemption",
  "return_to_place",
  "landing_rendezvous",
  "duo_assist",
];
const expectedObjectiveRoles = ["prerequisite", "primary", "support", "bonus", "completion"];

test("generated API types retain the current V2 mission contract", async () => {
  const [openApiText, generated] = await Promise.all([
    readFile(new URL("../openapi.json", import.meta.url), "utf8"),
    readFile(new URL("../lib/api.generated.ts", import.meta.url), "utf8"),
  ]);
  const schemas = JSON.parse(openApiText).components.schemas;
  const nextChapter = schemas.DeliveryNextChapterV2;

  assert.deepEqual(schemas.MissionFamilyV2.enum, expectedMissionFamilies);
  assert.deepEqual(schemas.MissionObjectiveRoleV2.enum, expectedObjectiveRoles);
  assert.equal(nextChapter.properties.invitation_player_ids.minItems, 2);
  assert.equal(nextChapter.properties.invitation_player_ids.maxItems, 4);
  assert.equal(nextChapter.properties.objectives.minItems, 2);
  assert.equal(nextChapter.properties.objectives.maxItems, 5);
  assert.deepEqual(
    new Set(nextChapter.required),
    new Set(["family", "invitation_player_ids", "title", "mission", "recipe", "objectives"]),
  );

  assert.ok(generated.includes(
    `MissionFamilyV2: ${expectedMissionFamilies.map(JSON.stringify).join(" | ")};`,
  ));
  assert.ok(generated.includes(
    `MissionObjectiveRoleV2: ${expectedObjectiveRoles.map(JSON.stringify).join(" | ")};`,
  ));
  const generatedNextChapter = generated.slice(
    generated.indexOf("DeliveryNextChapterV2: {"),
    generated.indexOf("/** DeliveryPerspectiveV2 */"),
  );
  for (const field of ["family", "invitation_player_ids", "mission", "objectives", "recipe", "title"]) {
    assert.match(generatedNextChapter, new RegExp(`\\b${field}[?:]`));
  }
});
