import assert from "node:assert/strict";
import test from "node:test";

import { isDeliveryBoundToPackCore } from "../lib/delivery-binding-core.mjs";

const pack = {
  pack_id: "PACK-1",
  player_profile: { player_id: "P1" },
  squad: {
    members: [
      { player_id: "P1", display_name: "Lee", opted_in: true },
      { player_id: "P2", display_name: "Mei", opted_in: true },
      { player_id: "P3", display_name: "Hidden", opted_in: false },
    ],
  },
  match_events: [{ event_id: "E1" }, { event_id: "E2" }],
};

const delivery = {
  pack_id: "PACK-1",
  memory: { evidence: [{ event_id: "E1" }] },
  player_perspectives: [
    { player_id: "P1", display_name: "Lee", evidence_event_ids: ["E1"] },
    { player_id: "P2", display_name: "Mei", evidence_event_ids: ["E2"] },
  ],
  next_chapter: {
    objectives: [
      { assigned_player_id: "P1", source_event_ids: ["E1"] },
      { assigned_player_id: null, source_event_ids: ["E2"] },
    ],
  },
};

function changed(mutator) {
  const candidate = structuredClone(delivery);
  mutator(candidate);
  return candidate;
}

test("binds a delivery to the complete opted-in roster and canonical evidence", () => {
  assert.equal(isDeliveryBoundToPackCore(delivery, pack), true);
});

test("rejects opted-out, renamed, missing, duplicate, or unknown delivery data", () => {
  const invalidDeliveries = [
    changed((candidate) => { candidate.player_perspectives[1].player_id = "P3"; }),
    changed((candidate) => { candidate.player_perspectives[1].display_name = "Someone else"; }),
    changed((candidate) => { candidate.player_perspectives.pop(); }),
    changed((candidate) => { candidate.player_perspectives[1].player_id = "P1"; }),
    changed((candidate) => { candidate.player_perspectives[0].evidence_event_ids = ["UNKNOWN"]; }),
    changed((candidate) => { candidate.memory.evidence[0].event_id = "UNKNOWN"; }),
    changed((candidate) => { candidate.next_chapter.objectives[0].assigned_player_id = "P3"; }),
    changed((candidate) => { candidate.next_chapter.objectives[0].source_event_ids = ["UNKNOWN"]; }),
  ];
  for (const candidate of invalidDeliveries) {
    assert.equal(isDeliveryBoundToPackCore(candidate, pack), false);
  }
});
